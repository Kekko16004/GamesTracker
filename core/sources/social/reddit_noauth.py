"""Reddit async scraper without API key — public JSON API only.

Supplements the existing PRAW-based ``RedditSource`` (``reddit.py``) with a
credential-free alternative that uses Reddit's public JSON API endpoints:

    GET https://www.reddit.com/r/{subreddit}/search.json
        ?q={game_title}&sort=new&limit=25&restrict_sr=on

No OAuth tokens, no PRAW, no credentials required.  Reddit allows up to ~30
unauthenticated JSON API requests per minute (enforced server-side via
User-Agent and IP; the rate limiter here stays conservative at 30 rpm).

Subreddits monitored by default (from ``marketing-playbook.md`` §3.1 + task
spec): ``indiegaming``, ``gamedev``, ``Games``, ``pcgaming``, ``steam``,
``itchio``.

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

# Default subreddits to search (task spec + marketing-playbook).
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

    Mapping (playbook §2.2):
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
    can be used together — the orchestrator deduplicates on ``post_url``.

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
        """Scrapes Reddit for posts mentioning ``game_title``.

        Strategy (optimized for rate limits):
        1. ONE global search via RSS (catches all subreddits at once)
        2. If global search fails, try the first 2 gaming subreddits
        This keeps requests to 1-3 per game instead of 6+.

        Returns:
            Deduplicated list of ``SocialPost``; empty on failure.
        """
        all_posts: list[SocialPost] = []

        # Primary: global search (1 request, covers all subreddits)
        global_posts = await self._search_subreddit("all", game_title)
        all_posts.extend(global_posts)

        # Fallback: try 2 key subreddits if global found nothing
        if not global_posts:
            for sub in self._subreddits[:2]:
                sub_posts = await self._search_subreddit(sub, game_title)
                all_posts.extend(sub_posts)
                if sub_posts:
                    break  # got results, stop

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
        """Searches a single subreddit via Reddit RSS feed (Atom XML).

        Reddit's JSON API now returns 403 for unauthenticated requests,
        but the RSS/Atom feed endpoints still work reliably:

            GET https://www.reddit.com/r/{subreddit}/search.rss
                ?q={query}&sort=new&limit=25

        Falls back to the global search RSS if subreddit-specific fails.
        """
        import xml.etree.ElementTree as ET

        # Use RSS feed instead of JSON API (JSON returns 403 since ~2025)
        if subreddit.lower() == "all":
            url = f"{_REDDIT_API_BASE}/search.rss"
        else:
            url = f"{_REDDIT_API_BASE}/r/{subreddit}/search.rss"
        params = {
            "q": game_title,
            "sort": "new",
            "limit": self._search_limit,
            "restrict_sr": "on",
        }
        extra_headers = {
            "User-Agent": _REDDIT_UA,
            "Accept": "application/atom+xml, application/rss+xml, */*",
        }

        try:
            resp = await self._get(url, params=params, extra_headers=extra_headers)
            if not resp or not hasattr(resp, 'text') or not resp.text:
                # Fallback: try global search
                url = f"{_REDDIT_API_BASE}/search.rss"
                params.pop("restrict_sr", None)
                resp = await self._get(url, params=params, extra_headers=extra_headers)
                if not resp or not hasattr(resp, 'text'):
                    return []

            # Parse Atom XML feed
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                logger.debug("[reddit-noauth] Failed to parse RSS from r/%s", subreddit)
                return []

            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries = root.findall('atom:entry', ns)

            posts: list[SocialPost] = []
            for entry in entries:
                title_el = entry.find('atom:title', ns)
                link_el = entry.find('atom:link', ns)
                updated_el = entry.find('atom:updated', ns)
                author_el = entry.find('atom:author/atom:name', ns)
                content_el = entry.find('atom:content', ns)

                title = title_el.text if title_el is not None else None
                link = link_el.get('href', '') if link_el is not None else ''
                author = author_el.text if author_el is not None else None

                if not link or not title:
                    continue

                # Filter: only keep posts that actually mention the game
                if game_title.lower() not in (title or '').lower():
                    # Check content too
                    content_text = content_el.text if content_el is not None else ''
                    if game_title.lower() not in (content_text or '').lower():
                        continue

                posted_at = None
                if updated_el is not None and updated_el.text:
                    try:
                        posted_at = datetime.fromisoformat(
                            updated_el.text.replace('Z', '+00:00')
                        )
                    except (ValueError, TypeError):
                        pass

                posts.append(SocialPost(
                    platform=PLATFORM,
                    post_url=link,
                    author=author.replace('/u/', '') if author else None,
                    title=title[:500] if title else None,
                    views=None,
                    likes=None,  # RSS doesn't include scores
                    comments=None,
                    shares=None,
                    posted_at=posted_at,
                    collected_at=datetime.utcnow(),
                    subreddit=subreddit,
                ))

            return posts

        except Exception as exc:
            logger.debug("[reddit-noauth] RSS search failed for r/%s: %s", subreddit, exc)
            return []

    async def _search_subreddit_json_DEPRECATED(
        self, subreddit: str, game_title: str
    ) -> list[SocialPost]:
        """DEPRECATED: JSON API returns 403 since ~2025. Kept for reference."""
        url = f"{_REDDIT_API_BASE}/r/{subreddit}/search.json"
        params = {
            "q": f'"{game_title}"',
            "sort": "new",
            "limit": self._search_limit,
            "restrict_sr": "on",
            "type": "link",
        }
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
