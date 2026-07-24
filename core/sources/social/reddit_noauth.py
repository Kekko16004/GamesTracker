"""Reddit async scraper without API key — public RSS (Atom) feed.

Supplements the existing PRAW-based ``RedditSource`` (``reddit.py``) with a
credential-free alternative that uses Reddit's public RSS/Atom feed endpoints:

    GET https://www.reddit.com/r/{subreddit}/search.rss
        ?q={game_title}&sort=new&limit=25&restrict_sr=on

The JSON API (``/search.json``) returns 403 for unauthenticated requests
since ~2025, so this scraper uses the Atom XML feed instead.

No OAuth tokens, no PRAW, no credentials required.  Reddit allows roughly
~30 unauthenticated RSS requests per minute (enforced server-side via
User-Agent and IP; the rate limiter here stays conservative at 30 rpm).

Subreddits monitored by default (from ``marketing-playbook.md`` S3.1 + task
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
import xml.etree.ElementTree as ET
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
        subs_searched = 0

        # Primary: global search (1 request, covers all subreddits)
        global_posts = await self._search_subreddit("all", game_title)
        all_posts.extend(global_posts)
        subs_searched += 1

        # Fallback: try 2 key subreddits if global found nothing
        if not global_posts:
            for sub in self._subreddits[:2]:
                sub_posts = await self._search_subreddit(sub, game_title)
                all_posts.extend(sub_posts)
                subs_searched += 1
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
            subs_searched,
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
        is_global = subreddit.lower() == "all"

        # Use RSS feed instead of JSON API (JSON returns 403 since ~2025)
        if is_global:
            url = f"{_REDDIT_API_BASE}/search.rss"
        else:
            url = f"{_REDDIT_API_BASE}/r/{subreddit}/search.rss"

        params: dict[str, object] = {
            "q": game_title,
            "sort": "new",
            "limit": self._search_limit,
        }
        # restrict_sr only makes sense for subreddit-specific searches
        if not is_global:
            params["restrict_sr"] = "on"

        extra_headers = {
            "User-Agent": _REDDIT_UA,
            "Accept": "application/atom+xml, application/rss+xml, */*",
        }

        try:
            resp = await self._get(url, params=params, extra_headers=extra_headers)
            if not resp or not hasattr(resp, "text") or not resp.text:
                logger.info(
                    "[reddit-noauth] Empty response from r/%s RSS", subreddit
                )
                return []

            # Non-200 responses: log and return empty
            if hasattr(resp, "status_code") and resp.status_code != 200:
                logger.info(
                    "[reddit-noauth] r/%s RSS returned HTTP %d",
                    subreddit,
                    resp.status_code,
                )
                return []

            return self._parse_atom_feed(resp.text, subreddit, game_title)

        except Exception as exc:
            logger.warning(
                "[reddit-noauth] RSS search failed for r/%s: %s", subreddit, exc
            )
            return []

    def _parse_atom_feed(
        self, xml_text: str, subreddit: str, game_title: str
    ) -> list[SocialPost]:
        """Parses a Reddit Atom XML feed into a list of ``SocialPost``.

        Filters entries to only those that mention ``game_title`` in the
        title or content.  Returns empty list on XML parse error.
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.debug(
                "[reddit-noauth] Failed to parse RSS XML from r/%s", subreddit
            )
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        posts: list[SocialPost] = []
        game_lower = game_title.lower()

        for entry in entries:
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            updated_el = entry.find("atom:updated", ns)
            author_el = entry.find("atom:author/atom:name", ns)
            content_el = entry.find("atom:content", ns)

            title = title_el.text if title_el is not None else None
            link = link_el.get("href", "") if link_el is not None else ""
            author = author_el.text if author_el is not None else None

            if not link or not title:
                continue

            # Filter: only keep posts that actually mention the game
            title_text = (title or "").lower()
            content_text = (
                (content_el.text or "") if content_el is not None else ""
            ).lower()
            if game_lower not in title_text and game_lower not in content_text:
                continue

            # Extract subreddit from link URL if possible (e.g. /r/indiegaming/...)
            entry_subreddit = subreddit
            if subreddit.lower() == "all" and "/r/" in link:
                # Try to extract actual subreddit from URL path
                import re

                sub_match = re.search(r"/r/([^/]+)/", link)
                if sub_match:
                    entry_subreddit = sub_match.group(1)

            posted_at = None
            if updated_el is not None and updated_el.text:
                try:
                    posted_at = datetime.fromisoformat(
                        updated_el.text.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Clean author: Reddit RSS sometimes prefixes with /u/
            clean_author = None
            if author:
                clean_author = author.replace("/u/", "").strip() or None

            posts.append(
                SocialPost(
                    platform=PLATFORM,
                    post_url=link,
                    author=clean_author,
                    title=title[:500] if title else None,
                    views=None,
                    likes=None,  # RSS does not include scores
                    comments=None,
                    shares=None,
                    posted_at=posted_at,
                    collected_at=datetime.utcnow(),
                    subreddit=entry_subreddit,
                )
            )

        logger.debug(
            "[reddit-noauth] r/%s RSS: %d entries -> %d relevant for %r",
            subreddit,
            len(entries),
            len(posts),
            game_title,
        )
        return posts

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
