"""Orchestrator for the async social media scraping engine.

Manages all scrapers, runs them on configurable schedules, deduplicates
results by ``post_url``, converts ``SocialPost`` dataclasses to the existing
DB model format (``NormalizedPost``), and saves results via the existing
``core.sources.social.persistence.save_posts`` function.

Configuration (from ``config/.env`` / environment):
    SCRAPING_ENABLED        true/false (default: true)
    SCRAPING_INTERVAL_HOURS integer (default: 6)
    NITTER_INSTANCE         hostname (default: nitter.privacydev.net)
    PROXY_URL               optional proxy URL for all scrapers

Entry points:
    ``run_all(game_titles)``    — runs all scrapers for a list of game titles
    ``run_once_sync(...)``      — sync wrapper for use from APScheduler jobs
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from core.sources.social.base_scraper import SocialPost
from core.sources.social.instagram_scraper import build_instagram_scraper
from core.sources.social.reddit_noauth import build_reddit_noauth_scraper
from core.sources.social.tiktok_scraper import build_tiktok_scraper
from core.sources.social.x_scraper import DEFAULT_NITTER_INSTANCE, build_x_scraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    """Reads a boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Reads an integer environment variable with a fallback default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    """Reads a string environment variable; empty string falls back to default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


# ---------------------------------------------------------------------------
# SocialPost -> NormalizedPost conversion
# ---------------------------------------------------------------------------


def social_post_to_normalized(post: SocialPost):  # -> NormalizedPost
    """Converts a scraper ``SocialPost`` to the existing ``NormalizedPost``.

    This allows the new scrapers to reuse the existing persistence layer
    (``save_posts``) without modification.
    """
    from core.sources.social.base import NormalizedPost

    return NormalizedPost(
        platform=post.platform,
        post_url=post.post_url,
        posted_at=post.posted_at,
        title=post.title,
        views=post.views,
        likes=post.likes,
        comments=post.comments,
        shares=post.shares,
        subreddit=post.subreddit,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class ScrapingOrchestrator:
    """Manages all social scrapers and coordinates their execution.

    Instantiates scrapers based on environment configuration, runs them for
    a list of game titles, deduplicates results in-memory by ``post_url``,
    then persists via the existing ``save_posts`` function.

    Args:
        nitter_instance: Nitter hostname for X/Twitter scraping.
        proxy_url: Optional proxy URL applied to all scrapers.
        tiktok_rpm: TikTok rate limit (requests per minute).
        instagram_rpm: Instagram rate limit.
        x_rpm: X/Twitter rate limit.
        reddit_rpm: Reddit no-auth rate limit.
    """

    def __init__(
        self,
        nitter_instance: str = DEFAULT_NITTER_INSTANCE,
        proxy_url: Optional[str] = None,
        tiktok_rpm: int = 30,
        instagram_rpm: int = 20,
        x_rpm: int = 15,
        reddit_rpm: int = 30,
    ) -> None:
        self._tiktok = build_tiktok_scraper(
            requests_per_minute=tiktok_rpm,
            proxy_url=proxy_url,
        )
        self._instagram = build_instagram_scraper(
            requests_per_minute=instagram_rpm,
            proxy_url=proxy_url,
        )
        self._x = build_x_scraper(
            nitter_instance=nitter_instance,
            requests_per_minute=x_rpm,
            proxy_url=proxy_url,
        )
        self._reddit = build_reddit_noauth_scraper(
            requests_per_minute=reddit_rpm,
            proxy_url=proxy_url,
        )

    async def run_all(self, game_titles: list[str]) -> dict[str, int]:
        """Runs all scrapers for every game title and persists the results.

        Each game title is processed independently. Results are deduplicated
        per-game across all platforms by ``post_url``. If a game cannot be
        found in the DB (by title), the posts are collected and returned in
        the summary but NOT persisted (no ``game_id`` to attach them to).

        To persist posts, callers should either pass ``game_id_map`` (mapping
        title -> game_id) or use ``run_all_for_game_ids``.

        Args:
            game_titles: List of indie game titles to search.

        Returns:
            Dict with summary counts:
            ``{"games": N, "posts_collected": N, "posts_saved": N, "errors": N}``
        """
        stats = {"games": 0, "posts_collected": 0, "posts_saved": 0, "errors": 0}

        for title in game_titles:
            stats["games"] += 1
            try:
                posts = await self._scrape_all_for_title(title)
                stats["posts_collected"] += len(posts)
                logger.info(
                    "[orchestrator] %r -> %d posts collected (not persisted: "
                    "no game_id; use run_all_for_game_ids to save)",
                    title,
                    len(posts),
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[orchestrator] Unexpected error scraping %r", title
                )
                stats["errors"] += 1

        return stats

    async def run_all_for_game_ids(
        self,
        game_id_map: dict[str, int],
    ) -> dict[str, int]:
        """Runs all scrapers and persists results for known game IDs.

        Args:
            game_id_map: Mapping of ``{game_title: game_id}`` for DB persistence.

        Returns:
            Dict with summary counts.
        """
        from core.sources.social.persistence import save_posts

        stats = {"games": 0, "posts_collected": 0, "posts_saved": 0, "errors": 0}

        for title, game_id in game_id_map.items():
            stats["games"] += 1
            try:
                posts = await self._scrape_all_for_title(title)
                stats["posts_collected"] += len(posts)

                if posts and game_id:
                    normalized = [social_post_to_normalized(p) for p in posts]
                    saved = save_posts(game_id, normalized)
                    stats["posts_saved"] += saved
                    logger.info(
                        "[orchestrator] %r (game_id=%d): %d collected, %d new saved",
                        title,
                        game_id,
                        len(posts),
                        saved,
                    )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[orchestrator] Error processing %r (game_id=%s)", title, game_id
                )
                stats["errors"] += 1

        return stats

    async def _scrape_all_for_title(self, game_title: str) -> list[SocialPost]:
        """Runs all scrapers concurrently for a single game title.

        Gathers results from TikTok, Instagram, X/Twitter, and Reddit,
        deduplicated by ``post_url``. Individual scraper failures do not
        abort the others.

        Args:
            game_title: Name of the indie game.

        Returns:
            Deduplicated list of ``SocialPost`` from all platforms.
        """
        tasks = [
            self._safe_scrape(self._tiktok, game_title),
            self._safe_scrape(self._instagram, game_title),
            self._safe_scrape(self._x, game_title),
            self._safe_scrape(self._reddit, game_title),
        ]
        results = await asyncio.gather(*tasks)

        all_posts: list[SocialPost] = []
        for platform_posts in results:
            all_posts.extend(platform_posts)

        # Dedup by post_url across all platforms.
        seen: set[str] = set()
        unique: list[SocialPost] = []
        for p in all_posts:
            key = p.post_url or ""
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
            elif not key:
                unique.append(p)

        return unique

    @staticmethod
    async def _safe_scrape(scraper, game_title: str) -> list[SocialPost]:
        """Runs a scraper, catching all exceptions to ensure resilience.

        Returns empty list on any error (the scraper's own ``scrape`` method
        already handles most errors; this is a last safety net).
        """
        try:
            return await scraper.scrape(game_title)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[orchestrator] Scraper %r failed for %r: %s",
                getattr(scraper, "platform", type(scraper).__name__),
                game_title,
                exc,
            )
            return []


# ---------------------------------------------------------------------------
# Sync wrapper for APScheduler
# ---------------------------------------------------------------------------


def run_once_sync(
    game_id_map: Optional[dict[str, int]] = None,
    game_titles: Optional[list[str]] = None,
) -> dict[str, int]:
    """Synchronous entry point for APScheduler and CLI usage.

    Reads configuration from environment, creates an orchestrator, and runs
    a single scraping pass. Either ``game_id_map`` or ``game_titles`` must
    be provided; ``game_id_map`` is preferred for DB persistence.

    Args:
        game_id_map: ``{game_title: game_id}`` mapping for DB persistence.
        game_titles: Fallback list of titles (no DB persistence).

    Returns:
        Stats dict from the orchestrator.
    """
    enabled = _env_bool("SCRAPING_ENABLED", True)
    if not enabled:
        logger.info("[orchestrator] Scraping disabled via SCRAPING_ENABLED=false.")
        return {"games": 0, "posts_collected": 0, "posts_saved": 0, "errors": 0}

    nitter_instance = _env_str("NITTER_INSTANCE", DEFAULT_NITTER_INSTANCE)
    proxy_url = _env_str("PROXY_URL", "") or None

    orchestrator = ScrapingOrchestrator(
        nitter_instance=nitter_instance,
        proxy_url=proxy_url,
    )

    loop = asyncio.new_event_loop()
    try:
        if game_id_map:
            return loop.run_until_complete(
                orchestrator.run_all_for_game_ids(game_id_map)
            )
        elif game_titles:
            return loop.run_until_complete(orchestrator.run_all(game_titles))
        else:
            logger.warning(
                "[orchestrator] run_once_sync called with no game_id_map or titles."
            )
            return {"games": 0, "posts_collected": 0, "posts_saved": 0, "errors": 0}
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# APScheduler job hook
# ---------------------------------------------------------------------------


def _build_game_id_map_from_db() -> dict[str, int]:
    """Queries the DB for all tracked (non-discarded) games.

    Returns a ``{title: game_id}`` mapping for the orchestrator.
    """
    try:
        from sqlalchemy import select

        from core.db import session_scope
        from core.models import Game

        with session_scope() as session:
            games = list(
                session.scalars(
                    select(Game)
                    .where(Game.discarded.is_(False))
                    .order_by(Game.id)
                )
            )
        return {g.title: g.id for g in games if g.title}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[orchestrator] Could not load games from DB: %s", exc)
        return {}


def run_social_scraping_job() -> dict[str, int]:
    """APScheduler-compatible job: scrapes all tracked games.

    Reads game titles and IDs from the DB, runs all scrapers, and saves
    results. Designed to run every ``SCRAPING_INTERVAL_HOURS`` hours.

    Returns:
        Stats dict from the orchestrator.
    """
    logger.info("[orchestrator] Starting scheduled social scraping job.")
    game_id_map = _build_game_id_map_from_db()
    if not game_id_map:
        logger.info("[orchestrator] No games found in DB; skipping scraping job.")
        return {"games": 0, "posts_collected": 0, "posts_saved": 0, "errors": 0}

    stats = run_once_sync(game_id_map=game_id_map)
    logger.info(
        "[orchestrator] Job complete: games=%(games)s, "
        "collected=%(posts_collected)s, saved=%(posts_saved)s, errors=%(errors)s",
        stats,
    )
    return stats
