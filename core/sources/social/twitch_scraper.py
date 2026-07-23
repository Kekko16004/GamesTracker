"""Twitch stream/VOD scraper for GamesTracker.

Searches Twitch for streams and VODs of tracked games using the public
Twitch API (requires no auth for basic search) and Sullygnome for
historical stream data.

Rate limit: 20 requests/minute.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from core.sources.social.base_scraper import BaseScraper, SocialPost

logger = logging.getLogger(__name__)

# Sullygnome provides public stream statistics without auth.
_SULLYGNOME_SEARCH = "https://sullygnome.com/api/tables/tablegamesearch/30/0/0/0/desc/0/100"
_TWITCH_CLIPS_SEARCH = "https://clips.twitch.tv"


class TwitchScraper(BaseScraper):
    """Scrapes Twitch stream data for indie games.

    Uses public endpoints:
    - Sullygnome API for historical stream data (viewers, hours watched)
    - Twitch clips page scraping for viral clip detection
    """

    platform = "twitch"

    async def scrape(self, game_title: str) -> list[SocialPost]:
        """Search for Twitch streams/clips mentioning the game."""
        posts: list[SocialPost] = []

        # Strategy 1: Sullygnome game search (public, no auth)
        try:
            url = f"https://sullygnome.com/api/tables/tablegamesearch/30/0/0/0/desc/0/100"
            params = {"search": game_title}
            data = await self._get_json(url, params=params)
            if data and isinstance(data, dict):
                games_data = data.get("data", [])
                for item in games_data[:5]:
                    name = item.get("name", "")
                    if game_title.lower() in name.lower():
                        viewers = item.get("viewerminutes", 0)
                        hours = item.get("streamtime", 0)
                        channels = item.get("channels", 0)
                        posts.append(SocialPost(
                            platform="twitch",
                            post_url=f"https://www.twitch.tv/directory/game/{name.replace(' ', '%20')}",
                            title=f"Twitch: {name} — {channels} streamers, {viewers} viewer-minutes",
                            views=viewers,
                            likes=channels,  # repurpose: number of channels
                            comments=None,
                            shares=None,
                            posted_at=None,
                            subreddit=None,
                        ))
        except Exception:
            logger.debug("[twitch] Sullygnome search failed for %r", game_title)

        # Strategy 2: Search Twitch clips page
        try:
            clips_url = f"https://www.twitch.tv/search?term={game_title}&type=channels"
            resp = await self._get(clips_url)
            if resp and hasattr(resp, 'text'):
                # Extract channel names from search results
                channels = re.findall(
                    r'data-a-target="preview-card-channel-link"[^>]*href="/([^"]+)"',
                    resp.text if hasattr(resp, 'text') else str(resp),
                )
                for ch in channels[:3]:
                    posts.append(SocialPost(
                        platform="twitch",
                        post_url=f"https://www.twitch.tv/{ch}",
                        title=f"Twitch streamer: {ch} (plays {game_title})",
                        views=None,
                        likes=None,
                        comments=None,
                        shares=None,
                        posted_at=None,
                        subreddit=None,
                    ))
        except Exception:
            logger.debug("[twitch] Clips search failed for %r", game_title)

        return posts


class KickScraper(BaseScraper):
    """Scrapes Kick.com for streams of tracked games.

    Uses public search endpoint (no auth required).
    """

    platform = "kick"

    async def scrape(self, game_title: str) -> list[SocialPost]:
        """Search Kick for streams of the game."""
        posts: list[SocialPost] = []

        try:
            url = f"https://kick.com/api/v2/search?query={game_title}"
            data = await self._get_json(url)
            if data and isinstance(data, dict):
                channels = data.get("channels", [])
                for ch in channels[:5]:
                    username = ch.get("slug", ch.get("username", ""))
                    is_live = ch.get("is_live", False)
                    followers = ch.get("followers_count", 0)
                    if username:
                        posts.append(SocialPost(
                            platform="kick",
                            post_url=f"https://kick.com/{username}",
                            title=f"Kick: {username} {'🔴 LIVE' if is_live else ''} ({followers} followers)",
                            views=followers,
                            likes=None,
                            comments=None,
                            shares=None,
                            posted_at=None,
                            subreddit=None,
                        ))
        except Exception:
            logger.debug("[kick] Search failed for %r", game_title)

        return posts


def build_twitch_scraper(
    requests_per_minute: int = 20,
    proxy_url: Optional[str] = None,
) -> TwitchScraper:
    """Factory for TwitchScraper."""
    return TwitchScraper(requests_per_minute=requests_per_minute, proxy_url=proxy_url)


def build_kick_scraper(
    requests_per_minute: int = 20,
    proxy_url: Optional[str] = None,
) -> KickScraper:
    """Factory for KickScraper."""
    return KickScraper(requests_per_minute=requests_per_minute, proxy_url=proxy_url)
