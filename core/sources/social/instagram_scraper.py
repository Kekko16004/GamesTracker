"""Instagram async scraper - oembed API + public page scraping (no auth).

Strategy:
1. **oembed API** (``https://graph.facebook.com/v18.0/instagram_oembed?url=...``):
   retrieves structured metadata for a known post URL. This endpoint requires
   no user-level auth (only a Facebook App ID), but degrades gracefully if
   none is configured (returns the raw oembed endpoint fallback).
2. **Public profile page scraping**: parse the ``window._sharedData`` or
   ``__additionalDataLoaded`` JSON embedded in the profile HTML.
3. **Hashtag exploration**: ``/explore/tags/<hashtag>/`` public pages.
4. **Graceful degradation**: if any request is blocked (401/403/429), logs a
   warning and falls back to the manual import hint - never crashes.

Rate limit: 20 requests/minute (Instagram is aggressive; stay conservative).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

from core.sources.social.base_scraper import BaseScraper, SocialPost

logger = logging.getLogger(__name__)

PLATFORM = "instagram"

# oembed endpoint - public, no token needed for the basic (non-embeds) variant.
_OEMBED_URL = "https://api.instagram.com/oembed"
# Graph API oembed (needs app token for full response).
_GRAPH_OEMBED_URL = "https://graph.facebook.com/v18.0/instagram_oembed"
_IG_BASE = "https://www.instagram.com"

# Patterns to extract shared_data / additional data JSON from page source.
_SHARED_DATA_RE = re.compile(
    r"window\._sharedData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL
)
_ADDITIONAL_DATA_RE = re.compile(
    r"window\.__additionalDataLoaded\([^,]+,\s*(\{.*?\})\);\s*</script>", re.DOTALL
)

# Open Graph fallbacks.
_OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', re.I)
_OG_URL_RE = re.compile(r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', re.I)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.I
)

#: HTTP status codes that indicate Instagram is blocking us.
_BLOCKED_STATUSES: frozenset[int] = frozenset({401, 403, 429})


def _parse_shared_data(html: str) -> dict:
    """Extracts the ``window._sharedData`` JSON blob from page HTML."""
    match = _SHARED_DATA_RE.search(html)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, AttributeError):
        return {}


def _extract_edge_posts(data: dict) -> list[dict]:
    """Navigates known paths in shared_data to find post edge nodes."""
    posts: list[dict] = []
    try:
        # Hashtag explore: entry_data.TagPage[0].graphql.hashtag.edge_hashtag_to_media.edges
        tag_pages = data.get("entry_data", {}).get("TagPage", [])
        for tp in tag_pages:
            edges = (
                tp.get("graphql", {})
                .get("hashtag", {})
                .get("edge_hashtag_to_media", {})
                .get("edges", [])
            )
            for e in edges:
                node = e.get("node", {})
                if node:
                    posts.append(node)
        # Profile page: entry_data.ProfilePage[0].graphql.user.edge_owner_to_timeline_media.edges
        profile_pages = data.get("entry_data", {}).get("ProfilePage", [])
        for pp in profile_pages:
            edges = (
                pp.get("graphql", {})
                .get("user", {})
                .get("edge_owner_to_timeline_media", {})
                .get("edges", [])
            )
            for e in edges:
                node = e.get("node", {})
                if node:
                    posts.append(node)
    except (AttributeError, TypeError, KeyError):
        pass
    return posts


def _node_to_social_post(node: dict) -> Optional[SocialPost]:
    """Converts an Instagram GraphQL node to a ``SocialPost``.

    Returns ``None`` if the minimum required fields are absent.
    """
    shortcode = node.get("shortcode")
    if not shortcode:
        return None

    owner = node.get("owner") or {}
    author = owner.get("username") or None

    post_url = f"https://www.instagram.com/p/{shortcode}/"
    taken_at = node.get("taken_at_timestamp")
    posted_at: Optional[datetime] = None
    if taken_at:
        try:
            posted_at = datetime.fromtimestamp(int(taken_at), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            posted_at = None

    # Caption is inside edge_media_to_caption.edges[0].node.text
    caption: Optional[str] = None
    edges = node.get("edge_media_to_caption", {}).get("edges", [])
    if edges:
        caption = edges[0].get("node", {}).get("text", "")[:500] or None

    likes = BaseScraper._to_int(
        node.get("edge_liked_by", {}).get("count")
        or node.get("edge_media_preview_like", {}).get("count")
    )
    comments = BaseScraper._to_int(
        node.get("edge_media_to_comment", {}).get("count")
    )
    views = BaseScraper._to_int(node.get("video_view_count"))

    return SocialPost(
        platform=PLATFORM,
        post_url=post_url,
        author=author,
        title=caption,
        views=views,
        likes=likes,
        comments=comments,
        shares=None,  # Instagram doesn't expose share counts publicly.
        posted_at=posted_at,
        collected_at=datetime.utcnow(),
    )


class InstagramScraper(BaseScraper):
    """Async Instagram scraper using oembed + public page scraping.

    Args:
        requests_per_minute: Max HTTP requests per minute (default 20).
        proxy_url: Optional proxy URL.
        fb_app_id: Optional Facebook App ID for the Graph API oembed endpoint.
            Not required for basic operation.
    """

    platform = PLATFORM

    def __init__(
        self,
        requests_per_minute: int = 20,
        proxy_url: Optional[str] = None,
        fb_app_id: Optional[str] = None,
    ) -> None:
        super().__init__(requests_per_minute=requests_per_minute, proxy_url=proxy_url)
        self._fb_app_id = fb_app_id or None

    async def scrape(self, game_title: str, **kwargs) -> list[SocialPost]:
        """Scrapes Instagram for posts related to ``game_title``.

        Searches public hashtag pages (``#indiegame``, ``#gamedev``, game
        title hashtag). Falls back to manual import hint if blocked.

        Args:
            game_title: Name of the indie game to search.
            post_url: (kwarg) If provided, fetches oembed for this specific URL.

        Returns:
            Deduplicated list of ``SocialPost``; empty on failure/block.
        """
        posts: list[SocialPost] = []

        # 1. Optional oembed for a known post URL.
        post_url: Optional[str] = kwargs.get("post_url")
        if post_url:
            oembed_post = await self._fetch_oembed(post_url)
            if oembed_post:
                posts.append(oembed_post)

        # 2. Hashtag exploration.
        hashtags = ["indiegame", "indiegames", "gamedev"]
        game_tag = re.sub(r"[^a-zA-Z0-9]", "", game_title).lower()
        if game_tag and game_tag not in hashtags:
            hashtags.append(game_tag)

        for tag in hashtags:
            tag_posts = await self._scrape_hashtag(tag, game_title)
            posts.extend(tag_posts)

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

        logger.info(
            "[instagram] scrape(%r): %d posts collected (%d unique)",
            game_title,
            len(posts),
            len(unique),
        )
        return unique

    # -- oembed --------------------------------------------------------------

    async def _fetch_oembed(self, post_url: str) -> Optional[SocialPost]:
        """Fetches oembed metadata for a specific Instagram post URL.

        Tries the public ``api.instagram.com/oembed`` endpoint first, then
        the Graph API variant if an App ID is configured.
        """
        try:
            params: dict = {"url": post_url, "omitscript": "true"}
            data = await self._get_json(
                _OEMBED_URL,
                params=params,
                extra_headers={"Accept": "application/json"},
            )
            if not data:
                # Try Graph API oembed with app token if available.
                if self._fb_app_id:
                    params["app_id"] = self._fb_app_id
                    data = await self._get_json(
                        _GRAPH_OEMBED_URL,
                        params=params,
                        extra_headers={"Accept": "application/json"},
                    )
            if not data:
                return None

            return SocialPost(
                platform=PLATFORM,
                post_url=post_url,
                author=data.get("author_name"),
                title=(data.get("title") or "")[:500] or None,
                views=None,  # oembed doesn't expose metrics.
                likes=None,
                comments=None,
                shares=None,
                posted_at=None,
                collected_at=datetime.utcnow(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[instagram] oembed failed for %s: %s", post_url, exc)
            return None

    # -- hashtag scraping ----------------------------------------------------

    async def _scrape_hashtag(
        self, hashtag: str, game_title: str
    ) -> list[SocialPost]:
        """Scrapes the public Instagram hashtag explore page.

        Parses ``window._sharedData`` JSON. On block (401/403/429) logs a
        warning and falls back to the manual import recommendation.

        Args:
            hashtag: Hashtag without the ``#`` prefix.
            game_title: Used for relevance filtering.

        Returns:
            List of ``SocialPost`` (may be empty).
        """
        url = f"{_IG_BASE}/explore/tags/{urllib.parse.quote(hashtag)}/"
        extra_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.instagram.com/",
        }

        try:
            response = await self._get(url, extra_headers=extra_headers)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[instagram] Failed to fetch hashtag page #%s: %s", hashtag, exc
            )
            return []

        if response.status_code in _BLOCKED_STATUSES:
            logger.warning(
                "[instagram] Blocked (HTTP %d) on #%s - "
                "falling back to manual import. "
                "Use the GUI manual import for Instagram posts.",
                response.status_code,
                hashtag,
            )
            return []

        if response.status_code != 200:
            logger.debug(
                "[instagram] Hashtag page #%s returned HTTP %d",
                hashtag,
                response.status_code,
            )
            return []

        html = response.text
        posts: list[SocialPost] = []

        # Parse shared data JSON.
        shared_data = _parse_shared_data(html)
        nodes = _extract_edge_posts(shared_data)

        title_lower = game_title.lower()
        for node in nodes:
            try:
                post = _node_to_social_post(node)
                if post is None:
                    continue
                # Relevance filter: post must mention the game title.
                caption = (post.title or "").lower()
                if title_lower not in caption:
                    continue
                posts.append(post)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[instagram] Skipping malformed node: %s", exc)

        # OG meta fallback.
        if not nodes:
            og_post = _og_fallback_post(html, url, game_title)
            if og_post:
                posts.append(og_post)

        logger.debug(
            "[instagram] #%s -> %d relevant posts for %r",
            hashtag,
            len(posts),
            game_title,
        )
        return posts


def _og_fallback_post(
    html: str, page_url: str, game_title: str
) -> Optional[SocialPost]:
    """Builds a minimal SocialPost from Open Graph meta tags (last resort)."""
    title_m = _OG_TITLE_RE.search(html)
    if not title_m:
        return None
    title_text = title_m.group(1)
    # Only keep if relevant to the game title.
    if game_title.lower() not in title_text.lower():
        return None
    url_m = _OG_URL_RE.search(html)
    return SocialPost(
        platform=PLATFORM,
        post_url=url_m.group(1) if url_m else page_url,
        author=None,
        title=title_text[:500],
        views=None,
        likes=None,
        comments=None,
        shares=None,
        posted_at=None,
        collected_at=datetime.utcnow(),
    )


def build_instagram_scraper(
    requests_per_minute: int = 20,
    proxy_url: Optional[str] = None,
    fb_app_id: Optional[str] = None,
) -> InstagramScraper:
    """Factory: returns a configured ``InstagramScraper`` instance."""
    return InstagramScraper(
        requests_per_minute=requests_per_minute,
        proxy_url=proxy_url,
        fb_app_id=fb_app_id,
    )
