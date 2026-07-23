"""Reddit async scraper without API key - public JSON API only.

Supplements the existing PRAW-based ``RedditSource`` (``reddit.py``) with a
credential-free alternative that uses Reddit's public JSON API endpoints:

    GET https://www.reddit.com/r/{subreddit}/search.json
        ?q={game_title}&sort=new&limit=25&restrict_sr=on

No OAuth tokens, no PRAW, no credentials required.  Reddit allows up to ~30
unauthenticated JSON API requests per minute (enforced server-side via
User-Agent and IP; the rate limiter here stays conservative at 30 rpm).

Subreddits monitored by default: ``indiegaming``, ``gamedev``, ``Games``,
``pcgaming``, ``steam``, ``itchio``.

Design notes:
- This module is **additive**: it does NOT replace ``reddit.py`` (PRAW).
  Both can run concurrently; deduplication happens in the orchestrator.
- A custom ``User-Agent`` header is mandatory for Reddit's public API to
  avoid immediate 429 / 503 responses.

Principle: fields that could not be collected remain ``None``, never ``0``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.sources.social.base_scraper import BaseScraper, SocialPost

logger = logging.getLogger(__name__)

PLATFORM = "reddit"

# Reddit public JSON API base URL.
_REDDIT_API_BASE = "https://www.reddit.com"

# Default subreddits to search.
DEFAULT_SUBREDDITS: list[str] = [
    "indiegaming",
    "gamedev",
    "Games",
    "pcgaming",
    "steam",
    "itchio",
]

# Reddit requires a descriptive User-Agent; generic browser UAs get blocked.
_REDDIT_UA = (
    "GamesTracker/1.0 (social scraping engine; "
    "contact: gamestracker@example.com; "
    "+https://github.com/gamestracker)"
)

# Maximum posts per subreddit search request.
DEFAULT_SEARCH_LIMIT = 25


def _created_to_datetime(created_utc: object) -> Optional[datetime]:
    """Converts ``created_utc`` (epoch seconds) to a timezone-aware datetime."""
    if created_utc is None:
        return None
    try:
        return datetime.fromtimestamp(float(created_utc), tz=timezone.utc)  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _post_data_to_social_post(data: dict) -> Optional[SocialPost]:
    """Converts a Reddit API post ``data`` dict to a ``SocialPost``.

    Returns ``None`` if the minimum required fields are absent.

    Mapping:
    - ``score``           -> likes
    - ``num_comments``    -> comments
    - ``created_utc``     -> posted_at
    - ``subreddit``       -> subreddit
    - ``permalink``       -> post_url
    - views / shares      -> None (not available via public API)
    """
    if not isinstance(data, dict):
        return None

    permalink = data.get("permalink")
    if permalink:
        post_url = f"https://www.reddit.com{permalink}"
    else:
        post_url = data.get("url")

    if not post_url:
        return None

    subreddit = data.get("subreddit") or None
    title = (data.get("title") or "")[:500] or None
    author = data.get("author") or None

    likes = BaseScraper._to_int(data.get("score"))
    comments = BaseScraper._to_int(data.get("num_comments"))
    posted_at = _created_to_datetime(data.get("created_utc"))

    return SocialPost(
        platform=PLATFORM,
        post_url=post_url,
        author=author,
        title=title,
        views=None,   # not available via public Reddit API
        likes=likes,
        comments=comments,
        shares=None,  # Reddit does not expose share counts
        posted_at=posted_at,
        collected_at=datetime.utcnow(),
        subreddit=subreddit,
    )


class RedditNoAuthScraper(BaseScraper):
    """Async Reddit scraper using the public JSON API (no credentials needed).

    Supplements the PRAW-based ``RedditSource``; does NOT replace it. Both
    can be used together - the orchestrator deduplicates on ``post_url``.

    Args:
        subreddits: List of subreddits to search (default: ``DEFAULT_SUBREDDITS``).
        requests_per_minute: Max HTTP requests per minute (default 30).
        proxy_url: Optional proxy URL.
        search_limit: Number of posts to request per subreddit (default 25).
    """

    platform = PLATFORM

    def __init__(
        self,
        subreddits: Optional[list[str]] = None,
        requests_per_minute: int = 30,
        proxy_url: Optional[str] = None,
        search_limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> None:
        super().__init__(requests_per_minute=requests_per_minute, proxy_url=proxy_url)
        self._subreddits: list[str] = list(subreddits or DEFAULT_SUBREDDITS)
        self._search_limit = min(max(1, search_limit), 100)  # Reddit max is 100.

    async def scrape(self, game_title: str, **kwargs) -> list[SocialPost]:
        """Scrapes Reddit for posts mentioning ``game_title`` across subreddits.

        Searches each configured subreddit using the public JSON search API,
        then deduplicates by ``post_url`` (preserving first occurrence order).

        Args:
            game_title: Name of the indie game to search.
            include_global: (kwarg bool) Also search ``r/all`` (default False
                to avoid too many requests; PRAW client handles global search).

        Returns:
            Deduplicated list of ``SocialPost``; empty on failure.
        """
        include_global: bool = bool(kwargs.get("include_global", False))

        all_posts: list[SocialPost] = []
        subreddits = list(self._subreddits)
        if include_global and "all" not in [s.lower() for s in subreddits]:
            subreddits.append("all")

        for subreddit in subreddits:
            sub_posts = await self._search_subreddit(subreddit, game_title)
            all_posts.extend(sub_posts)

        # Dedup by post_url, preserving order (first occurrence wins).
        seen: set[str] = set()
        unique: list[SocialPost] = []
        for p in all_posts:
            key = p.post_url or f"{p.subreddit}:{p.title}"
            if key not in seen:
                seen.add(key)
                unique.append(p)

        logger.info(
            "[reddit-noauth] scrape(%r): %d raw posts -> %d unique across %d subreddits",
            game_title,
            len(all_posts),
            len(unique),
            len(subreddits),
        )
        return unique

    async def _search_subreddit(
        self, subreddit: str, game_title: str
    ) -> list[SocialPost]:
        """Searches a single subreddit via the Reddit public JSON API.

        Args:
            subreddit: Subreddit name (without ``r/``).
            game_title: Search query (will be quoted for exact matching).

        Returns:
            List of ``SocialPost``; empty on error.
        """
        url = f"{_REDDIT_API_BASE}/r/{subreddit}/search.json"
        params = {
            "q": f'"{game_title}"',
            "sort": "new",
            "limit": self._search_limit,
            "restrict_sr": "on",
            "type": "link",
        }
        # Reddit requires a descriptive User-Agent; override the rotated UA.
        extra_headers = {
            "User-Agent": _REDDIT_UA,
            "Accept": "application/json",
        }

        try:
            data = await self._get_json(url, params=params, extra_headers=extra_headers)
            if not data:
                return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[reddit-noauth] Search failed in r/%s for %r: %s",
                subreddit,
                game_title,
                exc,
            )
            return []

        posts: list[SocialPost] = []
        try:
            children = data.get("data", {}).get("children", [])
            for child in children:
                post_data = child.get("data", {})
                post = _post_data_to_social_post(post_data)
                if post:
                    posts.append(post)
        except (AttributeError, TypeError, KeyError) as exc:
            logger.warning(
                "[reddit-noauth] Failed to parse response for r/%s: %s",
                subreddit,
                exc,
            )

        logger.debug(
            "[reddit-noauth] r/%s returned %d posts for %r",
            subreddit,
            len(posts),
            game_title,
        )
        return posts


def build_reddit_noauth_scraper(
    subreddits: Optional[list[str]] = None,
    requests_per_minute: int = 30,
    proxy_url: Optional[str] = None,
) -> RedditNoAuthScraper:
    """Factory: returns a configured ``RedditNoAuthScraper`` instance.

    Args:
        subreddits: Override the default subreddit list.
        requests_per_minute: Max requests per minute.
        proxy_url: Optional HTTP/SOCKS proxy URL.
    """
    return RedditNoAuthScraper(
        subreddits=subreddits,
        requests_per_minute=requests_per_minute,
        proxy_url=proxy_url,
    )
