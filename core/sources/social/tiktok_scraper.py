"""TikTok async scraper — oembed API + profile stats + public web scraping.

Strategy (2026 update):
1. **Profile scraping**: GET ``https://www.tiktok.com/@{handle}`` and parse
   ``__UNIVERSAL_DATA_FOR_REHYDRATION__`` for user stats (followers, video
   count, heart count).  This works reliably because TikTok server-renders
   the profile stats in the initial HTML payload.
2. **oembed API** (``https://www.tiktok.com/oembed?url=...``): retrieves
   structured metadata for a known post URL (title, author, thumbnail).
3. **Public hashtag scraping**: GET ``https://www.tiktok.com/tag/<hashtag>``
   and parse video metadata from ``<script>`` / Open Graph meta tags.
   Hashtags searched: ``#indiegame``, ``#gamedev``, plus a sanitised version
   of the game title.  (Low yield since TikTok no longer includes video
   lists in server-rendered HTML, but kept as a bonus source.)

No login, cookies, or API keys required.
Rate limit: 30 requests/minute (conservative -- TikTok is aggressive on rate
limiting public endpoints).

Graceful degradation: every method is wrapped so errors only produce a log
entry and an empty list, never a crash.
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

PLATFORM = "tiktok"
_OEMBED_URL = "https://www.tiktok.com/oembed"
_TAG_BASE_URL = "https://www.tiktok.com/tag"

# Default hashtags prepended to every game search.
_DEFAULT_HASHTAGS: list[str] = ["indiegame", "gamedev", "indiegames"]

# Regex patterns to extract video metrics from TikTok's public page HTML.
# TikTok changed its data embedding multiple times:
# - Pre-2024: SIGI_STATE
# - 2024: __NEXT_DATA__
# - 2025+: __UNIVERSAL_DATA_FOR_REHYDRATION__
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
_SIGI_STATE_RE = re.compile(
    r'<script[^>]*>\s*window\[(?:"SIGI_STATE"|\'SIGI_STATE\')\]\s*=\s*(\{.*?\});\s*</script>',
    re.DOTALL,
)
_UNIVERSAL_DATA_RE = re.compile(
    r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.DOTALL,
)

# Open Graph / meta tag fallbacks.
_OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', re.I)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.I
)
_OG_URL_RE = re.compile(r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', re.I)


def _sanitise_hashtag(game_title: str) -> str:
    """Converts a game title to a TikTok-compatible hashtag (no spaces/punctuation)."""
    return re.sub(r"[^a-zA-Z0-9]", "", game_title).lower()


def _parse_sigi_state(html: str) -> list[dict]:
    """Attempts to extract video items from the ``SIGI_STATE`` blob in page HTML.

    Returns a list of raw item dicts (may be empty on parse failure).
    """
    match = _SIGI_STATE_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        # The structure varies across TikTok releases; try common paths.
        items_map: dict = {}
        items_map.update(data.get("ItemModule", {}))
        items_map.update(data.get("item_list", {}))
        return list(items_map.values())
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []


def _parse_next_data(html: str) -> list[dict]:
    """Attempts to extract video items from the ``__NEXT_DATA__`` blob."""
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        page_props: dict = (
            data.get("props", {}).get("pageProps", {})
        )
        items = page_props.get("items", [])
        if isinstance(items, list):
            return items
        return []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []


def _parse_universal_data(html: str) -> list[dict]:
    """Extract video items from ``__UNIVERSAL_DATA_FOR_REHYDRATION__`` blob.

    This is TikTok's 2025+ data format. The structure typically contains
    search results under various nested paths.
    """
    match = _UNIVERSAL_DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        items: list[dict] = []

        # Walk the data structure looking for video items.
        # Common paths in 2025-2026 TikTok:
        # - __DEFAULT_SCOPE__["webapp.search"]["searchResult"]["item_list"]
        # - __DEFAULT_SCOPE__["webapp.video-detail"]["itemInfo"]["itemStruct"]
        default_scope = data.get("__DEFAULT_SCOPE__", {})

        # Search results page
        search_data = default_scope.get("webapp.search", {})
        if isinstance(search_data, dict):
            # Try multiple known paths
            for key in ["searchResult", "data"]:
                result = search_data.get(key, {})
                if isinstance(result, dict):
                    item_list = result.get("item_list", result.get("items", []))
                    if isinstance(item_list, list):
                        items.extend(item_list)

        # Also check for video detail page
        video_detail = default_scope.get("webapp.video-detail", {})
        if isinstance(video_detail, dict):
            item_info = video_detail.get("itemInfo", {})
            if isinstance(item_info, dict):
                struct = item_info.get("itemStruct")
                if isinstance(struct, dict):
                    items.append(struct)

        # Fallback: walk all values looking for item_list arrays
        if not items:
            for scope_key, scope_val in default_scope.items():
                if not isinstance(scope_val, dict):
                    continue
                for k, v in scope_val.items():
                    if isinstance(v, dict):
                        il = v.get("item_list", v.get("items", []))
                        if isinstance(il, list) and il:
                            items.extend(il)

        return items
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []


def _item_to_social_post(item: dict) -> Optional[SocialPost]:
    """Converts a raw TikTok item dict (from SIGI/NEXT_DATA) to a SocialPost.

    Returns ``None`` if the item lacks the minimum required fields.
    """
    if not isinstance(item, dict):
        return None

    video_id = item.get("id") or item.get("video", {}).get("id")
    author_info = item.get("author") or item.get("authorInfo") or {}
    if isinstance(author_info, str):
        author_handle = author_info
    else:
        author_handle = (
            author_info.get("uniqueId")
            or author_info.get("unique_id")
            or author_info.get("id")
        )

    if not video_id or not author_handle:
        return None

    post_url = f"https://www.tiktok.com/@{author_handle}/video/{video_id}"
    desc = item.get("desc") or item.get("text") or ""
    create_time = item.get("createTime") or item.get("create_time")
    posted_at: Optional[datetime] = None
    if create_time:
        try:
            posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            posted_at = None

    stats = item.get("stats") or item.get("statistics") or {}
    views = BaseScraper._to_int(
        stats.get("playCount") or stats.get("play_count")
    )
    likes = BaseScraper._to_int(
        stats.get("diggCount") or stats.get("digg_count")
    )
    comments = BaseScraper._to_int(
        stats.get("commentCount") or stats.get("comment_count")
    )
    shares = BaseScraper._to_int(
        stats.get("shareCount") or stats.get("share_count")
    )

    return SocialPost(
        platform=PLATFORM,
        post_url=post_url,
        author=str(author_handle),
        title=desc[:500] if desc else None,
        views=views,
        likes=likes,
        comments=comments,
        shares=shares,
        posted_at=posted_at,
        collected_at=datetime.utcnow(),
    )


class TikTokScraper(BaseScraper):
    """Async TikTok scraper using oembed + public hashtag page scraping.

    Args:
        requests_per_minute: Max HTTP requests per minute (default 30).
        proxy_url: Optional proxy URL for all requests.
        extra_hashtags: Additional hashtags to search beyond the defaults.
    """

    platform = PLATFORM

    def __init__(
        self,
        requests_per_minute: int = 30,
        proxy_url: Optional[str] = None,
        extra_hashtags: Optional[list[str]] = None,
    ) -> None:
        super().__init__(requests_per_minute=requests_per_minute, proxy_url=proxy_url)
        self._extra_hashtags: list[str] = list(extra_hashtags or [])

    async def scrape(self, game_title: str, **kwargs) -> list[SocialPost]:
        """Scrapes TikTok for posts related to ``game_title``.

        Strategy (2026):
        1. Enrich a known post URL via oembed (if provided).
        2. Profile scraping -- get user stats from developer's TikTok handle.
        3. Limited hashtag scraping (2 tags max) as a bonus source.

        Args:
            game_title: Name of the indie game to search.
            post_url: (kwarg) If provided, calls oembed for this URL.
            handle: (kwarg) TikTok handle to scrape profile stats from.
            aliases: (kwarg) List of alternative names (developer, publisher)
                to try as TikTok handles.

        Returns:
            Deduplicated list of ``SocialPost``; empty on failure.
        """
        posts: list[SocialPost] = []

        # 1. Optional oembed for a known post URL.
        post_url: Optional[str] = kwargs.get("post_url")
        if post_url:
            oembed_post = await self._fetch_oembed(post_url)
            if oembed_post:
                posts.append(oembed_post)

        # 2. Profile scraping if handle is known (developer name as handle).
        handle: Optional[str] = kwargs.get("handle")
        if not handle:
            # Derive a candidate handle from the game title.
            handle = re.sub(r"[^a-zA-Z0-9_]", "", game_title.replace(" ", "_")).lower()

        scraped_handles: set[str] = set()
        if handle:
            profile_posts = await self._scrape_profile(handle)
            posts.extend(profile_posts)
            scraped_handles.add(handle.lower())

        # Also try developer/publisher names as handles (from aliases).
        aliases: list[str] = kwargs.get("aliases", [])
        for alias in aliases:
            alias_handle = re.sub(
                r"[^a-zA-Z0-9_]", "", alias.replace(" ", "_")
            ).lower()
            if alias_handle and alias_handle not in scraped_handles:
                scraped_handles.add(alias_handle)
                ap = await self._scrape_profile(alias_handle)
                posts.extend(ap)

        # 3. Limited hashtag scraping as bonus (2 tags max to avoid rate limits).
        hashtags = list(_DEFAULT_HASHTAGS) + list(self._extra_hashtags)
        game_tag = _sanitise_hashtag(game_title)
        if game_tag and game_tag not in hashtags:
            hashtags.append(game_tag)

        for tag in hashtags[:2]:
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
                unique.append(p)  # keep URL-less posts (shouldn't happen often)

        logger.info(
            "[tiktok] scrape(%r): %d posts collected (%d unique)",
            game_title,
            len(posts),
            len(unique),
        )
        return unique

    # -- profile scraping ----------------------------------------------------

    async def _scrape_profile(self, handle: str) -> list[SocialPost]:
        """Scrapes a TikTok user profile page for account-level stats.

        The profile page includes ``__UNIVERSAL_DATA_FOR_REHYDRATION__`` with
        ``webapp.user-detail`` containing: uniqueId, followers, videoCount,
        heartCount.

        We create ONE synthetic ``SocialPost`` representing the profile stats.
        This is the most reliable TikTok data source in 2026 because the
        profile stats are always server-rendered.

        Args:
            handle: TikTok username (without the ``@`` prefix).

        Returns:
            A list with one ``SocialPost`` on success, empty on failure.
        """
        url = f"https://www.tiktok.com/@{handle}"
        try:
            response = await self._get(url)
            if not response or not hasattr(response, "text"):
                return []
            if hasattr(response, "status_code") and response.status_code != 200:
                logger.debug(
                    "[tiktok] Profile page for @%s returned HTTP %d",
                    handle,
                    response.status_code,
                )
                return []
            html = response.text
        except Exception as exc:
            logger.debug("[tiktok] Profile fetch failed for @%s: %s", handle, exc)
            return []

        # Parse __UNIVERSAL_DATA_FOR_REHYDRATION__
        match = _UNIVERSAL_DATA_RE.search(html)
        if not match:
            logger.debug(
                "[tiktok] No __UNIVERSAL_DATA_FOR_REHYDRATION__ in @%s profile",
                handle,
            )
            return []

        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            logger.debug("[tiktok] Failed to parse profile JSON for @%s", handle)
            return []

        user_detail = data.get("__DEFAULT_SCOPE__", {}).get(
            "webapp.user-detail", {}
        )
        user_info = user_detail.get("userInfo", {})
        if not user_info:
            logger.debug("[tiktok] No userInfo found in @%s profile data", handle)
            return []

        user = user_info.get("user", {})
        stats = user_info.get("stats", {})

        unique_id = user.get("uniqueId") or handle
        follower_count = self._to_int(stats.get("followerCount"))
        video_count = self._to_int(stats.get("videoCount"))
        heart_count = self._to_int(stats.get("heartCount"))

        title_parts = [f"TikTok @{unique_id}:"]
        if follower_count is not None:
            title_parts.append(f"{follower_count:,} followers")
        if video_count is not None:
            title_parts.append(f"{video_count:,} videos")
        if heart_count is not None:
            title_parts.append(f"{heart_count:,} likes")

        title = " ".join(title_parts) if len(title_parts) > 1 else None

        logger.info(
            "[tiktok] Profile @%s: followers=%s, videos=%s, hearts=%s",
            unique_id,
            follower_count,
            video_count,
            heart_count,
        )

        return [
            SocialPost(
                platform=PLATFORM,
                post_url=url,
                author=str(unique_id),
                title=title,
                views=heart_count,  # total likes as engagement proxy
                likes=follower_count,  # followers stored in likes field
                comments=video_count,  # video count stored in comments field
                shares=None,
                posted_at=None,
                collected_at=datetime.utcnow(),
            )
        ]

    # -- search page scraping ------------------------------------------------

    async def _scrape_search(self, game_title: str) -> list[SocialPost]:
        """Scrapes TikTok's search results page for videos about the game.

        Uses ``__UNIVERSAL_DATA_FOR_REHYDRATION__`` blob (2025+ format).
        This is the most reliable approach as of 2026.
        """
        import urllib.parse as _up

        url = f"https://www.tiktok.com/search?q={_up.quote(game_title + ' game')}"
        try:
            response = await self._get(url)
            if not response or response.status_code != 200:
                return []
            html = response.text
        except Exception as exc:
            logger.debug("[tiktok] search page failed for %r: %s", game_title, exc)
            return []

        # Parse the 2025+ universal data format
        items = _parse_universal_data(html) or _parse_next_data(html)

        posts: list[SocialPost] = []
        title_lower = game_title.lower()
        for item in items:
            try:
                post = _item_to_social_post(item)
                if post is None:
                    continue
                # Keep posts that mention the game in title/description
                desc = (post.title or "").lower()
                if title_lower in desc or game_title.lower().replace(" ", "") in desc:
                    posts.append(post)
            except Exception:
                pass

        # OG fallback if no structured data
        if not items:
            og_post = _og_fallback_post(html, url)
            if og_post:
                posts.append(og_post)

        logger.debug("[tiktok] search %r -> %d posts", game_title, len(posts))
        return posts

    # -- oembed --------------------------------------------------------------

    async def _fetch_oembed(self, post_url: str) -> Optional[SocialPost]:
        """Calls the TikTok oembed endpoint for a specific post URL.

        Returns a ``SocialPost`` with title/author only (oembed doesn't expose
        view/like counts), or ``None`` on error.
        """
        try:
            data = await self._get_json(
                _OEMBED_URL,
                params={"url": post_url},
                extra_headers={"Accept": "application/json"},
            )
            if not data:
                return None
            return SocialPost(
                platform=PLATFORM,
                post_url=post_url,
                author=data.get("author_name") or data.get("author_url"),
                title=(data.get("title") or "")[:500] or None,
                # oembed doesn't expose engagement metrics.
                views=None,
                likes=None,
                comments=None,
                shares=None,
                posted_at=None,
                collected_at=datetime.utcnow(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[tiktok] oembed failed for %s: %s", post_url, exc)
            return None

    # -- hashtag scraping ----------------------------------------------------

    async def _scrape_hashtag(
        self, hashtag: str, game_title: str
    ) -> list[SocialPost]:
        """Scrapes the public TikTok hashtag page for relevant videos.

        Parses ``__NEXT_DATA__`` / ``SIGI_STATE`` JSON blobs from the HTML.
        Falls back to Open Graph meta tags for a single representative post.
        Filters results to those whose description mentions the game title.

        Args:
            hashtag: Hashtag without the ``#`` prefix.
            game_title: Used for relevance filtering.

        Returns:
            List of ``SocialPost`` (may be empty).
        """
        url = f"{_TAG_BASE_URL}/{urllib.parse.quote(hashtag)}"
        try:
            response = await self._get(url)
            if response.status_code != 200:
                logger.debug(
                    "[tiktok] hashtag page %s returned HTTP %d",
                    url,
                    response.status_code,
                )
                return []
            html = response.text
        except Exception as exc:  # noqa: BLE001
            logger.warning("[tiktok] hashtag page fetch failed for #%s: %s", hashtag, exc)
            return []

        posts: list[SocialPost] = []

        # Try all known data formats (newest first):
        # 2025+: __UNIVERSAL_DATA_FOR_REHYDRATION__
        # 2024: __NEXT_DATA__
        # Pre-2024: SIGI_STATE
        items = (_parse_universal_data(html)
                 or _parse_next_data(html)
                 or _parse_sigi_state(html))

        title_lower = game_title.lower()
        for item in items:
            try:
                post = _item_to_social_post(item)
                if post is None:
                    continue
                # Filter: keep only posts where the description mentions the game.
                desc = (post.title or "").lower()
                if title_lower not in desc and game_title not in desc:
                    continue
                posts.append(post)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[tiktok] skipping malformed item: %s", exc)

        # OG meta fallback: capture a single synthetic post when JSON parse fails.
        if not items:
            og_post = _og_fallback_post(html, url)
            if og_post:
                posts.append(og_post)

        logger.debug(
            "[tiktok] #%s -> %d relevant posts for %r", hashtag, len(posts), game_title
        )
        return posts


def _og_fallback_post(html: str, page_url: str) -> Optional[SocialPost]:
    """Builds a minimal SocialPost from Open Graph meta tags (last resort)."""
    title_m = _OG_TITLE_RE.search(html)
    url_m = _OG_URL_RE.search(html)
    if not title_m:
        return None
    return SocialPost(
        platform=PLATFORM,
        post_url=url_m.group(1) if url_m else page_url,
        author=None,
        title=title_m.group(1)[:500],
        views=None,
        likes=None,
        comments=None,
        shares=None,
        posted_at=None,
        collected_at=datetime.utcnow(),
    )


def build_tiktok_scraper(
    requests_per_minute: int = 30,
    proxy_url: Optional[str] = None,
) -> TikTokScraper:
    """Factory: returns a configured ``TikTokScraper`` instance."""
    return TikTokScraper(
        requests_per_minute=requests_per_minute,
        proxy_url=proxy_url,
    )
