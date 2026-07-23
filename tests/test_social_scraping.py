"""Comprehensive tests for the social media scraping engine.

Tests cover:
- Each scraper's parsing logic with mocked HTTP responses
- Orchestrator deduplication
- Rate limiting behaviour
- Retry logic with exponential back-off
- All tests work without network access (mock httpx responses)

Import strategy: modules are imported directly (not through the package
``__init__.py``) to avoid triggering optional heavy dependencies (sqlalchemy,
praw) that may not be installed in the test environment.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Direct module loading helpers (bypass __init__.py chains)
# ---------------------------------------------------------------------------

_SOCIAL_DIR = Path(__file__).resolve().parent.parent / "core" / "sources" / "social"


def _load(name: str):
    """Loads a module by filename from the social/ directory, bypassing __init__.py."""
    path = _SOCIAL_DIR / f"{name}.py"
    full_name = f"core.sources.social.{name}"
    # Use cached module if already loaded to preserve class identity.
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load modules once for all tests.
_base_mod = _load("base_scraper")
_tiktok_mod = _load("tiktok_scraper")
_ig_mod = _load("instagram_scraper")
_x_mod = _load("x_scraper")
_reddit_mod = _load("reddit_noauth")
# base.py (NormalizedPost) — may need sqlalchemy; guard with try.
try:
    _base_social = _load("base")
    _HAS_BASE = True
except Exception:
    _HAS_BASE = False

# Also try to load scraping_orchestrator (needs base.py / persistence).
try:
    _orch_mod = _load("scraping_orchestrator")
    _HAS_ORCH = True
except Exception:
    _HAS_ORCH = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(coro):
    """Runs an async coroutine synchronously (compatible with Python 3.9+)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_response(
    status_code: int = 200,
    text: str = "",
    json_data: Any = None,
) -> MagicMock:
    """Creates a mock ``httpx.Response``."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(side_effect=ValueError("no json"))
    return resp


def _make_http_client_mock(response: MagicMock) -> MagicMock:
    """Creates a mock ``httpx.AsyncClient`` context manager returning ``response``."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# base_scraper tests
# ---------------------------------------------------------------------------


class TestBaseScraper:
    """Tests for BaseScraper: rate limiter, retry logic, UA rotation."""

    def test_rate_limiter_slows_requests(self):
        """RateLimiter should insert a delay between requests at the configured rate."""
        _RateLimiter = _base_mod._RateLimiter
        limiter = _RateLimiter(requests_per_minute=60)  # 1 req/sec = 1s gap

        async def _two_requests():
            await limiter.acquire()
            await limiter.acquire()

        start = time.monotonic()
        run(_two_requests())
        elapsed = time.monotonic() - start
        # Should have waited approximately 1 second between the two.
        assert elapsed >= 0.9, f"Expected >= 0.9s elapsed, got {elapsed:.3f}s"

    def test_rate_limiter_high_rpm_fast(self):
        """At very high RPM, two requests complete nearly instantly."""
        _RateLimiter = _base_mod._RateLimiter
        limiter = _RateLimiter(requests_per_minute=6000)  # 100 req/sec

        async def _two_requests():
            await limiter.acquire()
            await limiter.acquire()

        start = time.monotonic()
        run(_two_requests())
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"Expected < 0.2s, got {elapsed:.3f}s"

    def test_to_int_conversions(self):
        """_to_int should follow the data principle: None != 0."""
        BaseScraper = _base_mod.BaseScraper
        assert BaseScraper._to_int(None) is None
        assert BaseScraper._to_int("42") == 42
        assert BaseScraper._to_int(0) == 0
        assert BaseScraper._to_int("0") == 0
        assert BaseScraper._to_int("abc") is None
        assert BaseScraper._to_int(True) is None   # booleans -> None by design
        assert BaseScraper._to_int(3.9) == 3

    def test_retry_on_retryable_status(self):
        """_get should retry on 429/503 and return the last response after max retries."""
        BaseScraper = _base_mod.BaseScraper

        class _Scraper(BaseScraper):
            platform = "test"
            async def scrape(self, game_title, **kwargs):
                return []

        scraper = _Scraper(requests_per_minute=6000)
        call_count = 0

        async def _fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_response(status_code=503)

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=_fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new=AsyncMock()):
                response = run(scraper._get("https://example.com"))

        # MAX_RETRIES=3: initial + 3 retries = 4 total calls.
        assert call_count == 4
        assert response.status_code == 503

    def test_retry_on_transport_error(self):
        """_get should retry on network errors and eventually raise."""
        import httpx as _httpx
        BaseScraper = _base_mod.BaseScraper

        class _Scraper(BaseScraper):
            platform = "test"
            async def scrape(self, game_title, **kwargs):
                return []

        scraper = _Scraper(requests_per_minute=6000)
        call_count = 0

        async def _fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise _httpx.TransportError("network error")

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=_fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(_httpx.TransportError):
                    run(scraper._get("https://example.com"))

        assert call_count == 4  # 1 initial + 3 retries

    def test_get_json_returns_none_on_non_200(self):
        """_get_json should return None (not raise) on non-200 status."""
        BaseScraper = _base_mod.BaseScraper

        class _Scraper(BaseScraper):
            platform = "test"
            async def scrape(self, game_title, **kwargs):
                return []

        scraper = _Scraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=500)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            result = run(scraper._get_json("https://example.com"))

        assert result is None

    def test_get_json_returns_parsed_data(self):
        """_get_json should parse and return JSON on 200."""
        BaseScraper = _base_mod.BaseScraper

        class _Scraper(BaseScraper):
            platform = "test"
            async def scrape(self, game_title, **kwargs):
                return []

        scraper = _Scraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, json_data={"key": "value"})

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            result = run(scraper._get_json("https://example.com"))

        assert result == {"key": "value"}

    def test_build_client_rotates_ua(self):
        """_build_client should produce different User-Agent strings across calls."""
        BaseScraper = _base_mod.BaseScraper

        class _Scraper(BaseScraper):
            platform = "test"
            async def scrape(self, game_title, **kwargs):
                return []

        scraper = _Scraper(requests_per_minute=6000)
        uas = set()
        for _ in range(30):
            client = scraper._build_client()
            uas.add(client.headers.get("user-agent", ""))
        # With 10+ UAs in the pool, we expect at least 3 distinct values in 30 draws.
        assert len(uas) >= 3

    def test_user_agent_pool_has_10_plus(self):
        """The UA pool should contain at least 10 distinct browser strings."""
        pool = _base_mod._USER_AGENTS
        assert len(pool) >= 10
        assert len(set(pool)) >= 10


# ---------------------------------------------------------------------------
# TikTok scraper tests
# ---------------------------------------------------------------------------


class TestTikTokScraper:
    """Tests for TikTokScraper: oembed parsing, hashtag scraping, dedup."""

    _OEMBED_JSON = {
        "author_name": "devstudio42",
        "author_url": "https://www.tiktok.com/@devstudio42",
        "title": "Check out our new indie game #indiegame #pixelart",
        "type": "video",
    }

    _SIGI_HTML = """
    <html><body>
    <script>
    window["SIGI_STATE"] = {
        "ItemModule": {
            "7123456789": {
                "id": "7123456789",
                "desc": "Crystal Quest gameplay #indiegame #gamedev",
                "createTime": "1700000000",
                "author": {"uniqueId": "devstudio"},
                "stats": {
                    "playCount": 15000,
                    "diggCount": 890,
                    "commentCount": 43,
                    "shareCount": 12
                }
            }
        }
    };
    </script>
    </body></html>
    """

    def test_oembed_returns_social_post(self):
        """_fetch_oembed should parse the oembed JSON into a SocialPost."""
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=self._OEMBED_JSON)):
            post = run(scraper._fetch_oembed("https://www.tiktok.com/@devstudio42/video/7123456789"))

        assert post is not None
        assert post.platform == "tiktok"
        assert post.author == "devstudio42"
        assert post.title is not None
        assert "indiegame" in post.title.lower() or "indie" in post.title.lower()
        assert post.views is None  # oembed doesn't expose metrics

    def test_oembed_graceful_failure(self):
        """_fetch_oembed should return None (not raise) when oembed fails."""
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=None)):
            post = run(scraper._fetch_oembed("https://www.tiktok.com/@x/video/1"))

        assert post is None

    def test_scrape_hashtag_parses_sigi_state(self):
        """_scrape_hashtag should extract posts from SIGI_STATE JSON in HTML."""
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._SIGI_HTML)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            posts = run(scraper._scrape_hashtag("indiegame", "Crystal Quest"))

        assert len(posts) == 1
        p = posts[0]
        assert p.platform == "tiktok"
        assert p.views == 15000
        assert p.likes == 890
        assert p.comments == 43
        assert p.shares == 12
        assert p.author == "devstudio"
        assert p.posted_at is not None

    def test_scrape_deduplicates_across_hashtags(self):
        """scrape should deduplicate posts with the same post_url."""
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._SIGI_HTML)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            with patch.object(scraper, "_fetch_oembed", new=AsyncMock(return_value=None)):
                posts = run(scraper.scrape("Crystal Quest"))

        urls = [p.post_url for p in posts if p.post_url]
        assert len(urls) == len(set(urls)), "Duplicate post_urls in scrape output"

    def test_scrape_http_error_returns_empty(self):
        """scrape should return empty list when HTTP requests fail."""
        import httpx as _httpx
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)

        with patch.object(
            scraper, "_get",
            new=AsyncMock(side_effect=_httpx.TransportError("fail")),
        ):
            with patch.object(scraper, "_fetch_oembed", new=AsyncMock(return_value=None)):
                posts = run(scraper.scrape("Crystal Quest"))

        assert posts == []

    def test_hashtag_page_non_200_returns_empty(self):
        """_scrape_hashtag should return [] if the page returns non-200."""
        TikTokScraper = _tiktok_mod.TikTokScraper
        scraper = TikTokScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=404)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            posts = run(scraper._scrape_hashtag("indiegame", "Crystal Quest"))

        assert posts == []

    def test_item_to_social_post_returns_none_for_missing_fields(self):
        """_item_to_social_post should return None when video_id or author is absent."""
        _item_to_social_post = _tiktok_mod._item_to_social_post
        assert _item_to_social_post({}) is None
        assert _item_to_social_post({"id": "123"}) is None  # no author
        assert _item_to_social_post({"author": {"uniqueId": "x"}}) is None  # no id

    def test_sanitise_hashtag(self):
        """_sanitise_hashtag should strip spaces and punctuation."""
        _sanitise_hashtag = _tiktok_mod._sanitise_hashtag
        assert _sanitise_hashtag("Crystal Quest") == "crystalquest"
        assert _sanitise_hashtag("A-B: C!") == "abc"


# ---------------------------------------------------------------------------
# Instagram scraper tests
# ---------------------------------------------------------------------------


class TestInstagramScraper:
    """Tests for InstagramScraper: oembed, shared_data parsing, block handling."""

    _OEMBED_JSON = {
        "author_name": "crystalquestgame",
        "title": "Crystal Quest out now! #indiegame",
    }

    _SHARED_DATA_HTML = (
        "<html><body>"
        '<script type="text/javascript">window._sharedData = '
        + json.dumps({
            "entry_data": {
                "TagPage": [
                    {
                        "graphql": {
                            "hashtag": {
                                "edge_hashtag_to_media": {
                                    "edges": [
                                        {
                                            "node": {
                                                "shortcode": "ABC123",
                                                "taken_at_timestamp": 1700000000,
                                                "owner": {"username": "crystalquestgame"},
                                                "edge_media_to_caption": {
                                                    "edges": [
                                                        {"node": {"text": "Crystal Quest launch day! #indiegame"}}
                                                    ]
                                                },
                                                "edge_liked_by": {"count": 423},
                                                "edge_media_to_comment": {"count": 18},
                                                "video_view_count": None,
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        })
        + ";</script></body></html>"
    )

    def test_oembed_returns_social_post(self):
        """_fetch_oembed should parse oembed JSON into a SocialPost."""
        InstagramScraper = _ig_mod.InstagramScraper
        scraper = InstagramScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=self._OEMBED_JSON)):
            post = run(scraper._fetch_oembed("https://www.instagram.com/p/ABC123/"))

        assert post is not None
        assert post.platform == "instagram"
        assert post.author == "crystalquestgame"
        assert "Crystal Quest" in post.title

    def test_scrape_hashtag_parses_shared_data(self):
        """_scrape_hashtag should parse posts from window._sharedData JSON."""
        InstagramScraper = _ig_mod.InstagramScraper
        scraper = InstagramScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._SHARED_DATA_HTML)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            posts = run(scraper._scrape_hashtag("indiegame", "Crystal Quest"))

        assert len(posts) == 1
        p = posts[0]
        assert p.post_url == "https://www.instagram.com/p/ABC123/"
        assert p.likes == 423
        assert p.comments == 18
        assert p.views is None  # not a video
        assert p.shares is None  # Instagram doesn't expose shares

    def test_scrape_blocked_returns_empty_with_warning(self, caplog):
        """On HTTP 429/403, _scrape_hashtag should return [] and log a warning."""
        import logging
        InstagramScraper = _ig_mod.InstagramScraper
        scraper = InstagramScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=429)

        module_name = _ig_mod.__name__
        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            with caplog.at_level(logging.WARNING, logger=module_name):
                posts = run(scraper._scrape_hashtag("indiegame", "Crystal Quest"))

        assert posts == []
        # Check that a warning mentioning the block was logged.
        messages = " ".join(r.message for r in caplog.records)
        assert "Blocked" in messages or "blocked" in messages or "429" in messages

    def test_oembed_graceful_failure(self):
        """_fetch_oembed should return None when the API fails."""
        InstagramScraper = _ig_mod.InstagramScraper
        scraper = InstagramScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=None)):
            post = run(scraper._fetch_oembed("https://www.instagram.com/p/NOTFOUND/"))

        assert post is None

    def test_scrape_deduplicates_same_url(self):
        """scrape should return unique post_urls across hashtags."""
        InstagramScraper = _ig_mod.InstagramScraper
        scraper = InstagramScraper(requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._SHARED_DATA_HTML)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            with patch.object(scraper, "_fetch_oembed", new=AsyncMock(return_value=None)):
                posts = run(scraper.scrape("Crystal Quest"))

        urls = [p.post_url for p in posts if p.post_url]
        assert len(urls) == len(set(urls))

    def test_node_to_social_post_missing_shortcode_returns_none(self):
        """_node_to_social_post should return None when shortcode is absent."""
        _node_to_social_post = _ig_mod._node_to_social_post
        assert _node_to_social_post({}) is None
        assert _node_to_social_post({"owner": {"username": "x"}}) is None

    def test_parse_shared_data_malformed_json(self):
        """_parse_shared_data should return {} on malformed JSON."""
        _parse_shared_data = _ig_mod._parse_shared_data
        result = _parse_shared_data('<script>window._sharedData = {bad json};</script>')
        assert result == {}


# ---------------------------------------------------------------------------
# X / Twitter scraper tests
# ---------------------------------------------------------------------------


class TestXScraper:
    """Tests for XScraper: RSS parsing, HTML fallback, dedup."""

    _RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Search results for "Crystal Quest"</title>
    <item>
      <title>Just played Crystal Quest - amazing indie game! #indiegame</title>
      <link>https://nitter.privacydev.net/gamer99/status/1234567890</link>
      <dc:creator>gamer99</dc:creator>
      <pubDate>Wed, 14 Nov 2023 22:13:20 +0000</pubDate>
      <description>Just played Crystal Quest &lt;br&gt;&#x267B; 12 &#x2764; 45 &#x1F4AC; 3</description>
    </item>
    <item>
      <title>Crystal Quest gameplay stream tonight! #gamedev #indiegame</title>
      <link>https://nitter.privacydev.net/streamer_sam/status/9876543210</link>
      <dc:creator>streamer_sam</dc:creator>
      <pubDate>Thu, 15 Nov 2023 10:00:00 +0000</pubDate>
      <description>Crystal Quest gameplay stream tonight!</description>
    </item>
  </channel>
</rss>"""

    def test_parse_rss_extracts_posts(self):
        """_parse_rss_content should extract all items from the RSS feed."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(nitter_instance="nitter.privacydev.net", requests_per_minute=6000)
        posts = scraper._parse_rss_content(self._RSS_FEED)

        assert len(posts) == 2
        p0 = posts[0]
        assert p0.platform == "twitter"
        assert p0.author == "gamer99"
        assert "Crystal Quest" in p0.title
        # post_url should be converted to twitter.com domain.
        assert "twitter.com" in p0.post_url
        assert "/gamer99/status/1234567890" in p0.post_url

    def test_rss_metrics_extraction(self):
        """RSS description parsing should extract engagement metrics when present."""
        _extract_metrics_from_description = _x_mod._extract_metrics_from_description
        # Test with unicode symbols that Nitter uses.
        desc = "Some tweet ♻ 12 ❤ 45 💬 3"
        metrics = _extract_metrics_from_description(desc)
        assert metrics["retweets"] == 12
        assert metrics["likes"] == 45
        assert metrics["replies"] == 3

    def test_rss_metrics_none_when_absent(self):
        """Metrics should be None when engagement counts aren't in the description."""
        _extract_metrics_from_description = _x_mod._extract_metrics_from_description
        metrics = _extract_metrics_from_description("No metrics here")
        assert metrics["retweets"] is None
        assert metrics["likes"] is None
        assert metrics["replies"] is None

    def test_scrape_uses_rss_first(self):
        """scrape should prefer RSS and return posts from it."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(nitter_instance="nitter.privacydev.net", requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._RSS_FEED)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            posts = run(scraper.scrape("Crystal Quest"))

        assert len(posts) == 2
        # All posts should be from RSS (with authors set).
        assert all(p.author is not None for p in posts)

    def test_scrape_falls_back_to_html_when_rss_empty(self):
        """scrape should attempt HTML scraping when RSS returns no items."""
        XScraper = _x_mod.XScraper
        empty_rss = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>empty</title></channel></rss>"""
        html_fallback = """
<html><body>
  <a href="/devguy/status/111">tweet</a>
  <div class="tweet-content media-body">Crystal Quest is great!</div>
</body></html>"""

        scraper = XScraper(nitter_instance="nitter.privacydev.net", requests_per_minute=6000)

        async def _mock_get(url, **kwargs):
            if "rss" in url:
                return _make_response(status_code=200, text=empty_rss)
            return _make_response(status_code=200, text=html_fallback)

        with patch.object(scraper, "_get", new=AsyncMock(side_effect=_mock_get)):
            posts = run(scraper.scrape("Crystal Quest"))

        # HTML fallback should have found at least the one tweet link.
        assert len(posts) >= 1
        assert "twitter.com" in posts[0].post_url

    def test_scrape_deduplicates(self):
        """scrape should deduplicate posts with the same post_url."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(nitter_instance="nitter.privacydev.net", requests_per_minute=6000)
        mock_resp = _make_response(status_code=200, text=self._RSS_FEED)

        with patch.object(scraper, "_get", new=AsyncMock(return_value=mock_resp)):
            posts = run(scraper.scrape("Crystal Quest"))

        urls = [p.post_url for p in posts if p.post_url]
        assert len(urls) == len(set(urls))

    def test_rss_parse_error_returns_empty(self):
        """Malformed RSS XML should return empty list without raising."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(requests_per_minute=6000)
        posts = scraper._parse_rss_content("<<<not xml>>>")
        assert posts == []

    def test_parse_rss_posted_at_datetime(self):
        """RSS items should have timezone-aware posted_at datetime."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(requests_per_minute=6000)
        posts = scraper._parse_rss_content(self._RSS_FEED)

        assert posts[0].posted_at is not None
        assert posts[0].posted_at.tzinfo is not None

    def test_strip_html_removes_tags(self):
        """_strip_html should remove HTML tags and unescape entities."""
        _strip_html = _x_mod._strip_html
        assert _strip_html("<b>Hello</b> &amp; <i>world</i>") == "Hello & world"

    def test_nitter_instance_normalises_protocol(self):
        """XScraper should strip http(s):// prefix from nitter_instance."""
        XScraper = _x_mod.XScraper
        scraper = XScraper(nitter_instance="https://nitter.net")
        assert scraper._nitter_instance == "nitter.net"


# ---------------------------------------------------------------------------
# Reddit no-auth scraper tests
# ---------------------------------------------------------------------------


class TestRedditNoAuthScraper:
    """Tests for RedditNoAuthScraper: JSON API parsing, dedup, error handling."""

    _REDDIT_RESPONSE = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Crystal Quest - my new indie game!",
                        "score": 234,
                        "num_comments": 45,
                        "created_utc": 1700000000.0,
                        "permalink": "/r/indiegaming/comments/abc123/crystal_quest/",
                        "subreddit": "indiegaming",
                        "author": "devcrystal",
                        "url": "https://www.reddit.com/r/indiegaming/comments/abc123/",
                    }
                },
                {
                    "data": {
                        "id": "xyz789",
                        "title": "Crystal Quest gameplay impressions",
                        "score": 67,
                        "num_comments": 12,
                        "created_utc": 1700100000.0,
                        "permalink": "/r/indiegaming/comments/xyz789/crystal_quest_gameplay/",
                        "subreddit": "indiegaming",
                        "author": "gamer_review",
                        "url": "https://www.reddit.com/r/indiegaming/comments/xyz789/",
                    }
                },
            ]
        }
    }

    def test_search_subreddit_parses_response(self):
        """_search_subreddit should parse Reddit JSON API response into SocialPosts."""
        RedditNoAuthScraper = _reddit_mod.RedditNoAuthScraper
        scraper = RedditNoAuthScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=self._REDDIT_RESPONSE)):
            posts = run(scraper._search_subreddit("indiegaming", "Crystal Quest"))

        assert len(posts) == 2
        p = posts[0]
        assert p.platform == "reddit"
        assert p.post_url == "https://www.reddit.com/r/indiegaming/comments/abc123/crystal_quest/"
        assert p.likes == 234
        assert p.comments == 45
        assert p.subreddit == "indiegaming"
        assert p.author == "devcrystal"
        assert p.views is None    # Reddit doesn't expose view counts
        assert p.shares is None   # Reddit doesn't expose share counts
        assert p.posted_at is not None
        assert p.posted_at.tzinfo is not None

    def test_post_data_to_social_post_mapping(self):
        """_post_data_to_social_post should map all fields correctly."""
        _post_data_to_social_post = _reddit_mod._post_data_to_social_post
        raw = {
            "title": "Great indie game",
            "score": 500,
            "num_comments": 30,
            "created_utc": 1700000000.0,
            "permalink": "/r/Games/comments/test/great_indie_game/",
            "subreddit": "Games",
            "author": "indie_fan",
        }
        post = _post_data_to_social_post(raw)
        assert post is not None
        assert post.title == "Great indie game"
        assert post.likes == 500
        assert post.comments == 30
        assert post.subreddit == "Games"
        assert post.author == "indie_fan"
        assert post.post_url == "https://www.reddit.com/r/Games/comments/test/great_indie_game/"

    def test_post_data_missing_permalink_uses_url(self):
        """If permalink is absent, fall back to the ``url`` field."""
        _post_data_to_social_post = _reddit_mod._post_data_to_social_post
        raw = {
            "title": "Test",
            "score": 10,
            "num_comments": 2,
            "created_utc": 1700000000.0,
            "url": "https://www.reddit.com/r/test/comments/fallback/",
            "subreddit": "test",
            "author": "user1",
        }
        post = _post_data_to_social_post(raw)
        assert post is not None
        assert "fallback" in post.post_url

    def test_scrape_deduplicates_across_subreddits(self):
        """scrape should deduplicate the same post appearing in multiple subreddits."""
        RedditNoAuthScraper = _reddit_mod.RedditNoAuthScraper
        scraper = RedditNoAuthScraper(
            subreddits=["indiegaming", "gamedev"],
            requests_per_minute=6000,
        )
        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=self._REDDIT_RESPONSE)):
            posts = run(scraper.scrape("Crystal Quest"))

        urls = [p.post_url for p in posts if p.post_url]
        assert len(urls) == len(set(urls)), "Duplicate URLs should be removed"

    def test_api_error_returns_empty(self):
        """Network errors should return empty list without raising."""
        RedditNoAuthScraper = _reddit_mod.RedditNoAuthScraper
        scraper = RedditNoAuthScraper(requests_per_minute=6000)

        with patch.object(scraper, "_get_json", new=AsyncMock(return_value=None)):
            posts = run(scraper.scrape("Crystal Quest"))

        assert posts == []

    def test_post_data_none_returns_none(self):
        """_post_data_to_social_post should return None for non-dict input."""
        _post_data_to_social_post = _reddit_mod._post_data_to_social_post
        assert _post_data_to_social_post(None) is None   # type: ignore[arg-type]
        assert _post_data_to_social_post([]) is None      # type: ignore[arg-type]

    def test_created_to_datetime_conversion(self):
        """Epoch UTC should convert to timezone-aware datetime correctly."""
        _created_to_datetime = _reddit_mod._created_to_datetime
        dt = _created_to_datetime(1700000000.0)
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_created_to_datetime_invalid_returns_none(self):
        """Invalid epoch values should return None without raising."""
        _created_to_datetime = _reddit_mod._created_to_datetime
        assert _created_to_datetime(None) is None
        assert _created_to_datetime("not_a_number") is None
        assert _created_to_datetime(float("inf")) is None

    def test_default_subreddits_contain_expected(self):
        """Default subreddit list should include the required subreddits."""
        DEFAULT = _reddit_mod.DEFAULT_SUBREDDITS
        required = {"indiegaming", "gamedev", "Games", "pcgaming", "steam", "itchio"}
        actual_lower = {s.lower() for s in DEFAULT}
        required_lower = {s.lower() for s in required}
        assert required_lower.issubset(actual_lower), (
            f"Missing subreddits: {required_lower - actual_lower}"
        )


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_ORCH, reason="scraping_orchestrator not importable (missing deps)")
class TestScrapingOrchestrator:
    """Tests for ScrapingOrchestrator: dedup, persistence, resilience."""

    def _make_posts(self, platform: str, urls: list[str]) -> list:
        SocialPost = _base_mod.SocialPost
        return [
            SocialPost(platform=platform, post_url=url, title="Post about game")
            for url in urls
        ]

    def test_scrape_all_deduplicates_across_platforms(self):
        """_scrape_all_for_title should deduplicate posts sharing the same URL."""
        ScrapingOrchestrator = _orch_mod.ScrapingOrchestrator
        orch = ScrapingOrchestrator()

        shared_url = "https://twitter.com/user/status/1234"
        tiktok_posts = self._make_posts("tiktok", ["https://tiktok.com/v/1", shared_url])
        x_posts = self._make_posts("twitter", [shared_url, "https://twitter.com/user/status/999"])
        ig_posts = self._make_posts("instagram", ["https://instagram.com/p/ABCD/"])
        reddit_posts = self._make_posts("reddit", ["https://reddit.com/r/indie/1"])

        with patch.object(orch._tiktok, "scrape", new=AsyncMock(return_value=tiktok_posts)):
            with patch.object(orch._x, "scrape", new=AsyncMock(return_value=x_posts)):
                with patch.object(orch._instagram, "scrape", new=AsyncMock(return_value=ig_posts)):
                    with patch.object(orch._reddit, "scrape", new=AsyncMock(return_value=reddit_posts)):
                        posts = run(orch._scrape_all_for_title("Crystal Quest"))

        urls = [p.post_url for p in posts if p.post_url]
        assert len(urls) == len(set(urls)), "Orchestrator should deduplicate by post_url"
        assert urls.count(shared_url) == 1

    def test_safe_scrape_handles_exception(self):
        """_safe_scrape should return [] when the scraper raises."""
        ScrapingOrchestrator = _orch_mod.ScrapingOrchestrator

        async def _bad_scrape(title, **kwargs):
            raise RuntimeError("simulated crash")

        mock_scraper = MagicMock()
        mock_scraper.scrape = _bad_scrape
        mock_scraper.platform = "bad_platform"

        result = run(ScrapingOrchestrator._safe_scrape(mock_scraper, "Crystal Quest"))
        assert result == []

    def test_run_all_returns_stats(self):
        """run_all should return a stats dict with correct game count."""
        ScrapingOrchestrator = _orch_mod.ScrapingOrchestrator
        SocialPost = _base_mod.SocialPost
        orch = ScrapingOrchestrator()
        posts = [SocialPost(platform="tiktok", post_url="https://tiktok.com/v/1")]

        with patch.object(orch, "_scrape_all_for_title", new=AsyncMock(return_value=posts)):
            stats = run(orch.run_all(["Crystal Quest", "Dungeon Depths"]))

        assert stats["games"] == 2
        assert stats["posts_collected"] == 2
        assert stats["errors"] == 0

    def test_run_all_for_game_ids_calls_save_posts(self):
        """run_all_for_game_ids should call save_posts with normalized posts."""
        ScrapingOrchestrator = _orch_mod.ScrapingOrchestrator
        SocialPost = _base_mod.SocialPost
        orch = ScrapingOrchestrator()
        posts = [SocialPost(platform="reddit", post_url="https://reddit.com/r/x/1")]

        # save_posts is imported lazily inside the method body via:
        #   from core.sources.social.persistence import save_posts
        # Inject a fake persistence module into sys.modules so the lazy import
        # resolves to our mock, then restore afterwards.
        mock_save = MagicMock(return_value=1)
        fake_persistence = MagicMock()
        fake_persistence.save_posts = mock_save
        persistence_key = "core.sources.social.persistence"
        original = sys.modules.get(persistence_key)
        sys.modules[persistence_key] = fake_persistence

        try:
            with patch.object(orch, "_scrape_all_for_title", new=AsyncMock(return_value=posts)):
                stats = run(orch.run_all_for_game_ids({"Crystal Quest": 42}))
        finally:
            if original is None:
                sys.modules.pop(persistence_key, None)
            else:
                sys.modules[persistence_key] = original

        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert call_args[0][0] == 42  # game_id is the first positional arg
        assert stats["posts_saved"] == 1

    def test_social_post_to_normalized_conversion(self):
        """social_post_to_normalized should map all fields correctly."""
        social_post_to_normalized = _orch_mod.social_post_to_normalized
        SocialPost = _base_mod.SocialPost
        post = SocialPost(
            platform="tiktok",
            post_url="https://tiktok.com/v/123",
            title="My indie game launch!",
            views=5000,
            likes=300,
            comments=25,
            shares=10,
            posted_at=datetime(2023, 11, 14, tzinfo=timezone.utc),
            subreddit=None,
        )
        normalized = social_post_to_normalized(post)

        assert normalized.platform == "tiktok"
        assert normalized.post_url == post.post_url
        assert normalized.title == post.title
        assert normalized.views == 5000
        assert normalized.likes == 300
        assert normalized.comments == 25
        assert normalized.shares == 10
        assert normalized.posted_at == post.posted_at
        assert normalized.subreddit is None

    def test_run_once_sync_disabled_returns_zero_stats(self, monkeypatch):
        """run_once_sync should return zero-stats when SCRAPING_ENABLED=false."""
        run_once_sync = _orch_mod.run_once_sync
        monkeypatch.setenv("SCRAPING_ENABLED", "false")
        stats = run_once_sync(game_titles=["Crystal Quest"])

        assert stats["games"] == 0
        assert stats["posts_collected"] == 0

    def test_run_once_sync_with_no_input_returns_zero(self):
        """run_once_sync with neither game_id_map nor game_titles is a no-op."""
        run_once_sync = _orch_mod.run_once_sync
        stats = run_once_sync()
        assert stats["games"] == 0


# ---------------------------------------------------------------------------
# SocialPost dataclass tests
# ---------------------------------------------------------------------------


class TestSocialPostDataclass:
    """Tests for the SocialPost dataclass and its field semantics."""

    def test_default_fields(self):
        """SocialPost should have sensible defaults (None for optional fields)."""
        SocialPost = _base_mod.SocialPost
        post = SocialPost(platform="tiktok")
        assert post.post_url is None
        assert post.views is None
        assert post.likes is None
        assert post.comments is None
        assert post.shares is None
        assert post.posted_at is None
        assert post.subreddit is None
        assert post.extra is None

    def test_collected_at_auto_set(self):
        """collected_at should be set automatically to current UTC time."""
        SocialPost = _base_mod.SocialPost
        before = datetime.utcnow()
        post = SocialPost(platform="reddit")
        after = datetime.utcnow()
        assert before <= post.collected_at <= after

    def test_social_post_fields_match_normalized_post(self):
        """SocialPost should cover all NormalizedPost fields (for conversion)."""
        SocialPost = _base_mod.SocialPost
        social_fields = set(SocialPost.__dataclass_fields__)
        expected_subset = {"platform", "post_url", "posted_at", "title",
                           "views", "likes", "comments", "shares", "subreddit"}
        assert expected_subset.issubset(social_fields), (
            f"Missing fields in SocialPost: {expected_subset - social_fields}"
        )
