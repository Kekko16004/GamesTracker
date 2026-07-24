"""X/Twitter async scraper — RSS bridge via Nitter + fallback instances.

Strategy (2026 update):
1. **Nitter RSS feed** (``https://<nitter_instance>/search/rss?q=<query>``):
   Nitter is an open-source Twitter frontend that exposes RSS feeds of search
   results without requiring a Twitter API key. The Nitter instance URL is
   configurable (``NITTER_INSTANCE`` env var, default ``nitter.privacydev.net``).
2. **Fallback instances**: if the primary Nitter instance fails (403/timeout),
   tries 2 additional public Nitter instances before giving up.
3. **Synthetic post**: when ALL Nitter instances are down (which is common in
   2026 as most public instances return 403), creates a synthetic post
   containing a direct X search URL so the user can check manually.

RSS item parsing extracts: tweet text (title), author, timestamp, and where
available: likes, retweets, and replies from the RSS description HTML.

Rate limit: 15 requests/minute (conservative; Nitter instances vary).

Graceful degradation: every method is wrapped so errors only produce a log
entry and an empty list, never a crash.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus

from core.sources.social.base_scraper import BaseScraper, SocialPost

logger = logging.getLogger(__name__)

PLATFORM = "twitter"

# Default Nitter instance -- configurable via NITTER_INSTANCE env var.
DEFAULT_NITTER_INSTANCE = "nitter.privacydev.net"

# Fallback Nitter instances to try when the primary fails.
# Most public Nitter instances return 403 as of 2026, but self-hosted
# instances or newer forks may still work.
_FALLBACK_NITTER_INSTANCES: list[str] = [
    "nitter.net",
    "nitter.cz",
]

# RSS namespaces used by Nitter / Atom.
_RSS_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Patterns to extract engagement numbers from Nitter's RSS description HTML.
# Example: "♻ 12 · ❤️ 45 · 💬 3"  or plain text "12 retweets, 45 likes"
_RETWEET_RE = re.compile(r"(?:♻|RT)\s*[:\-]?\s*(\d+)", re.IGNORECASE)
_LIKE_RE = re.compile(r"(?:❤|♥|like[s]?)\s*[:\-]?\s*(\d+)", re.IGNORECASE)
_REPLY_RE = re.compile(r"(?:💬|repl(?:y|ies)?)\s*[:\-]?\s*(\d+)", re.IGNORECASE)

# Nitter HTML search page patterns.
_TWEET_LINK_RE = re.compile(
    r'href="(/[^/]+/status/\d+)"', re.IGNORECASE
)
_TWEET_TEXT_RE = re.compile(
    r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Removes HTML tags and unescapes entities from a string."""
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parses an RFC 2822 datetime string into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:  # noqa: BLE001
        return None


def _extract_metrics_from_description(description: str) -> dict:
    """Extracts engagement metrics from the HTML in an RSS <description> field.

    Returns a dict with keys: likes, retweets, replies (all Optional[int]).
    """
    rt_m = _RETWEET_RE.search(description)
    like_m = _LIKE_RE.search(description)
    reply_m = _REPLY_RE.search(description)
    return {
        "retweets": int(rt_m.group(1)) if rt_m else None,
        "likes": int(like_m.group(1)) if like_m else None,
        "replies": int(reply_m.group(1)) if reply_m else None,
    }


def _rss_item_to_social_post(
    item: ET.Element, nitter_base: str
) -> Optional[SocialPost]:
    """Converts a single RSS <item> element to a ``SocialPost``.

    Returns ``None`` if the minimum required fields are absent.
    """
    title_el = item.find("title")
    link_el = item.find("link")
    pubdate_el = item.find("pubDate")
    desc_el = item.find("description")
    author_el = item.find("dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"})

    title_text = (title_el.text or "").strip() if title_el is not None else None
    link_text = (link_el.text or "").strip() if link_el is not None else None
    desc_text = (desc_el.text or "") if desc_el is not None else ""
    author_text = (author_el.text or "").strip() if author_el is not None else None

    if not link_text:
        return None

    # Nitter links are relative; make them absolute.
    if link_text.startswith("/"):
        link_text = f"https://{nitter_base}{link_text}"
    # Convert Nitter URL back to twitter.com URL for canonical key.
    twitter_url = re.sub(
        r"https?://[^/]+/([^/]+/status/\d+)",
        r"https://twitter.com/\1",
        link_text,
    )

    posted_at = _parse_rss_datetime(
        pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else None
    )

    metrics = _extract_metrics_from_description(_strip_html(desc_text))

    return SocialPost(
        platform=PLATFORM,
        post_url=twitter_url,
        author=author_text,
        title=_strip_html(title_text)[:500] if title_text else None,
        views=None,  # X/Twitter doesn't expose view counts via RSS.
        likes=metrics["likes"],
        comments=metrics["replies"],
        shares=metrics["retweets"],
        posted_at=posted_at,
        collected_at=datetime.utcnow(),
        extra={"nitter_url": link_text},
    )


class XScraper(BaseScraper):
    """Async X/Twitter scraper using Nitter RSS + HTML fallback.

    Args:
        nitter_instance: Hostname of the Nitter instance to use.
        requests_per_minute: Max HTTP requests per minute (default 15).
        proxy_url: Optional proxy URL.
    """

    platform = PLATFORM

    def __init__(
        self,
        nitter_instance: str = DEFAULT_NITTER_INSTANCE,
        requests_per_minute: int = 15,
        proxy_url: Optional[str] = None,
    ) -> None:
        super().__init__(requests_per_minute=requests_per_minute, proxy_url=proxy_url)
        # Strip protocol prefix if user accidentally included it.
        self._nitter_instance = re.sub(r"^https?://", "", nitter_instance).rstrip("/")

    async def scrape(self, game_title: str, **kwargs) -> list[SocialPost]:
        """Scrapes X/Twitter for posts related to ``game_title`` via Nitter RSS.

        Strategy (2026):
        1. Try RSS feed on the configured (primary) Nitter instance.
        2. Try HTML fallback on the primary instance.
        3. Try 2 additional fallback Nitter instances (RSS + HTML each).
        4. If ALL instances fail, create a synthetic post with a direct
           X search URL so the user can check manually.

        Args:
            game_title: Name of the indie game to search.
            limit: (kwarg) Maximum number of posts to return (default 25).

        Returns:
            Deduplicated list of ``SocialPost``; empty on failure.
        """
        limit: int = int(kwargs.get("limit", 25))
        posts: list[SocialPost] = []

        # Build search query: exact title + indiegame filter.
        query = f'"{game_title}" (#indiegame OR #gamedev OR indie game)'

        # 1. Try the configured (primary) Nitter instance.
        rss_posts = await self._fetch_rss(query)
        posts.extend(rss_posts)

        if not posts:
            html_posts = await self._scrape_html(query)
            posts.extend(html_posts)

        # 2. Try fallback Nitter instances if the primary failed.
        if not posts:
            original_instance = self._nitter_instance
            for fallback in _FALLBACK_NITTER_INSTANCES:
                if fallback == original_instance:
                    continue
                logger.info(
                    "[twitter] Primary Nitter instance failed, trying fallback: %s",
                    fallback,
                )
                self._nitter_instance = fallback
                try:
                    rss_posts = await self._fetch_rss(query)
                    posts.extend(rss_posts)
                    if not posts:
                        html_posts = await self._scrape_html(query)
                        posts.extend(html_posts)
                    if posts:
                        break  # got results from this fallback
                except Exception as exc:
                    logger.debug(
                        "[twitter] Fallback %s also failed: %s", fallback, exc
                    )
            # Restore original instance.
            self._nitter_instance = original_instance

        # 3. If ALL Nitter instances failed, create a synthetic post
        #    with an X search URL so the user can check manually.
        if not posts:
            logger.info(
                "[twitter] All Nitter instances returned 0 results for %r. "
                "X/Twitter scraping requires a working Nitter instance or "
                "direct API access. Creating synthetic search link.",
                game_title,
            )
            x_search_url = (
                f"https://x.com/search?q={quote_plus(game_title + ' indiegame')}"
                f"&src=typed_query&f=live"
            )
            posts.append(
                SocialPost(
                    platform=PLATFORM,
                    post_url=x_search_url,
                    author=None,
                    title=(
                        f"[X Search] No Nitter instances available. "
                        f"Search X manually for: {game_title}"
                    ),
                    views=None,
                    likes=None,
                    comments=None,
                    shares=None,
                    posted_at=None,
                    collected_at=datetime.utcnow(),
                    extra={"synthetic": True, "reason": "all_nitter_instances_down"},
                )
            )

        # Dedup by post_url.
        seen: set[str] = set()
        unique: list[SocialPost] = []
        for p in posts:
            key = p.post_url or ""
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
            elif not key:
                unique.append(p)

        result = unique[:limit]
        logger.info(
            "[twitter] scrape(%r): %d posts (%d unique, limit %d)",
            game_title,
            len(posts),
            len(unique),
            limit,
        )
        return result

    # -- RSS -----------------------------------------------------------------

    async def _fetch_rss(self, query: str) -> list[SocialPost]:
        """Fetches and parses the Nitter RSS search feed for ``query``.

        Returns a list of ``SocialPost``; empty on parse/network error.
        """
        rss_url = (
            f"https://{self._nitter_instance}/search/rss"
            f"?q={quote_plus(query)}&f=tweets"
        )
        try:
            response = await self._get(
                rss_url,
                extra_headers={
                    "Accept": "application/rss+xml, application/xml, text/xml"
                },
            )
            if response.status_code != 200:
                logger.debug(
                    "[twitter] Nitter RSS returned HTTP %d for %s",
                    response.status_code,
                    rss_url,
                )
                return []
            return self._parse_rss_content(response.text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[twitter] RSS fetch failed (instance=%s): %s",
                self._nitter_instance,
                exc,
            )
            return []

    def _parse_rss_content(self, xml_text: str) -> list[SocialPost]:
        """Parses an RSS XML string into a list of ``SocialPost``.

        Returns empty list on XML parse error, empty input, or any other
        issue.  Handles both RSS 2.0 ``<item>`` and Atom ``<entry>`` formats.
        """
        if not xml_text or not xml_text.strip():
            logger.debug("[twitter] Empty RSS content received")
            return []

        posts: list[SocialPost] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.debug("[twitter] RSS XML parse error: %s", exc)
            return []
        except Exception as exc:
            logger.debug("[twitter] Unexpected RSS parse error: %s", exc)
            return []

        channel = root.find("channel")
        if channel is None:
            # Atom format fallback.
            items = root.findall("{http://www.w3.org/2005/Atom}entry")
            for entry in items:
                try:
                    post = self._atom_entry_to_post(entry)
                    if post:
                        posts.append(post)
                except Exception as exc:
                    logger.debug("[twitter] Skipping malformed Atom entry: %s", exc)
            return posts

        for item in channel.findall("item"):
            try:
                post = _rss_item_to_social_post(item, self._nitter_instance)
                if post:
                    posts.append(post)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[twitter] Skipping malformed RSS item: %s", exc)

        logger.debug("[twitter] Parsed %d posts from RSS", len(posts))
        return posts

    def _atom_entry_to_post(self, entry: ET.Element) -> Optional[SocialPost]:
        """Converts an Atom ``<entry>`` element to a ``SocialPost``."""
        ns = "http://www.w3.org/2005/Atom"
        title_el = entry.find(f"{{{ns}}}title")
        link_el = entry.find(f"{{{ns}}}link")
        updated_el = entry.find(f"{{{ns}}}updated")
        author_el = entry.find(f"{{{ns}}}author/{{{ns}}}name")

        link = link_el.get("href", "") if link_el is not None else ""
        if not link:
            return None

        twitter_url = re.sub(
            r"https?://[^/]+/([^/]+/status/\d+)",
            r"https://twitter.com/\1",
            link,
        )
        posted_at: Optional[datetime] = None
        if updated_el is not None and updated_el.text:
            try:
                posted_at = datetime.fromisoformat(
                    updated_el.text.replace("Z", "+00:00")
                )
            except ValueError:
                posted_at = None

        title_text = title_el.text if title_el is not None else None
        author_text = author_el.text if author_el is not None else None

        return SocialPost(
            platform=PLATFORM,
            post_url=twitter_url,
            author=author_text,
            title=_strip_html(title_text)[:500] if title_text else None,
            views=None,
            likes=None,
            comments=None,
            shares=None,
            posted_at=posted_at,
            collected_at=datetime.utcnow(),
        )

    # -- HTML fallback -------------------------------------------------------

    async def _scrape_html(self, query: str) -> list[SocialPost]:
        """Scrapes the Nitter search results HTML page as a fallback.

        Extracts tweet links and text from the rendered HTML.

        Returns a list of ``SocialPost``; empty on failure.
        """
        search_url = (
            f"https://{self._nitter_instance}/search"
            f"?q={quote_plus(query)}&f=tweets"
        )
        try:
            response = await self._get(
                search_url,
                extra_headers={"Accept": "text/html,application/xhtml+xml"},
            )
            if response.status_code != 200:
                logger.debug(
                    "[twitter] Nitter HTML search returned HTTP %d",
                    response.status_code,
                )
                return []
            return self._parse_search_html(response.text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[twitter] HTML fallback failed: %s", exc)
            return []

    def _parse_search_html(self, html: str) -> list[SocialPost]:
        """Parses Nitter search results HTML to extract tweets.

        Returns a list of ``SocialPost``; empty on parse failure.
        """
        posts: list[SocialPost] = []
        link_matches = _TWEET_LINK_RE.findall(html)
        text_matches = _TWEET_TEXT_RE.findall(html)

        for i, path in enumerate(link_matches):
            twitter_url = f"https://twitter.com{path}"
            text = ""
            if i < len(text_matches):
                text = _strip_html(text_matches[i])

            posts.append(
                SocialPost(
                    platform=PLATFORM,
                    post_url=twitter_url,
                    author=None,  # Author extraction from HTML is fragile; skip.
                    title=text[:500] or None,
                    views=None,
                    likes=None,
                    comments=None,
                    shares=None,
                    posted_at=None,
                    collected_at=datetime.utcnow(),
                )
            )

        logger.debug("[twitter] Parsed %d tweets from HTML", len(posts))
        return posts


def build_x_scraper(
    nitter_instance: str = DEFAULT_NITTER_INSTANCE,
    requests_per_minute: int = 15,
    proxy_url: Optional[str] = None,
) -> XScraper:
    """Factory: returns a configured ``XScraper`` instance.

    Args:
        nitter_instance: Nitter hostname (default ``nitter.privacydev.net``).
        requests_per_minute: Max requests per minute.
        proxy_url: Optional HTTP/SOCKS proxy URL.
    """
    return XScraper(
        nitter_instance=nitter_instance,
        requests_per_minute=requests_per_minute,
        proxy_url=proxy_url,
    )
