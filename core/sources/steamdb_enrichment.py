"""SteamDB-style game data enrichment.

Fetches additional data points from public endpoints that Steam's own API
does not provide (or hides behind authentication):

- **Price data**: from Steam Store API (appdetails) — includes price,
  discount, currency by region.
- **Twitch stats**: from Sullygnome public API — viewers, stream hours,
  channels.
- **Owner estimates**: computed from review count using the VG Insights /
  Gamalytic / PlayTracker multiplier method.

All functions are pure data fetchers that return dicts.  They handle
errors gracefully (return empty/None, never crash).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# HTTP client timeout.
_TIMEOUT = 15.0
_USER_AGENT = "GamesTracker/2.0 (+https://github.com/Kekko16004/GamesTracker)"

# Owner estimation multipliers (VG Insights / Gamalytic research).
_REVIEW_MULTIPLIER_LOW = 20
_REVIEW_MULTIPLIER_MED = 35
_REVIEW_MULTIPLIER_HIGH = 60


async def fetch_steam_price(appid: str, cc: str = "us") -> Optional[dict[str, Any]]:
    """Fetch price data from Steam Store API for a given app ID.

    Parameters
    ----------
    appid : str
        Steam application ID (e.g. "730" for CS2).
    cc : str
        Country code for regional pricing (default: "us").

    Returns
    -------
    dict or None
        ``{price, discount_percent, currency, initial_price, is_free, coming_soon}``
    """
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={cc}&filters=price_overview,basic"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        app_data = data.get(str(appid), {})
        if not app_data.get("success"):
            return None

        info = app_data.get("data", {})
        is_free = info.get("is_free", False)
        coming_soon = info.get("release_date", {}).get("coming_soon", False)

        price_info = info.get("price_overview")
        if price_info:
            return {
                "price": price_info.get("final", 0) / 100.0,
                "initial_price": price_info.get("initial", 0) / 100.0,
                "discount_percent": price_info.get("discount_percent", 0),
                "currency": price_info.get("currency", "USD"),
                "is_free": is_free,
                "coming_soon": coming_soon,
            }
        return {
            "price": 0.0,
            "initial_price": 0.0,
            "discount_percent": 0,
            "currency": "USD",
            "is_free": is_free,
            "coming_soon": coming_soon,
        }
    except Exception as exc:
        logger.debug("Steam price fetch failed for appid=%s: %s", appid, exc)
        return None


async def fetch_twitch_stats(game_name: str) -> Optional[dict[str, Any]]:
    """Fetch Twitch streaming stats from Sullygnome (public, no auth).

    Returns stats like viewers, stream hours, channels for the past 30 days.
    """
    url = "https://sullygnome.com/api/tables/tablegamesearch/30/0/0/0/desc/0/20"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={
            "User-Agent": _USER_AGENT,
            "Referer": "https://sullygnome.com/",
        }) as client:
            resp = await client.get(url, params={"search": game_name})
            if resp.status_code != 200:
                return None
            data = resp.json()

        games = data.get("data", [])
        # Find best match by name.
        needle = game_name.lower()
        for g in games:
            name = g.get("name", "")
            if needle in name.lower():
                return {
                    "game_name": name,
                    "viewer_hours": g.get("viewerminutes", 0),
                    "stream_hours": g.get("streamtime", 0),
                    "channels": g.get("channels", 0),
                    "avg_viewers": g.get("avgviewers", 0),
                    "peak_viewers": g.get("peakviewers", 0),
                    "avg_channels": g.get("avgchannels", 0),
                    "followers_gain": g.get("followersgain", 0),
                }
        return None
    except Exception as exc:
        logger.debug("Twitch stats fetch failed for %r: %s", game_name, exc)
        return None


def estimate_owners_from_reviews(
    review_count: int,
) -> dict[str, Any]:
    """Estimate total game owners from review count.

    Uses the VG Insights / Gamalytic / PlayTracker method:
    - Conservative (niche/horror): reviews × 20
    - Median (indie): reviews × 35
    - Optimistic (casual/popular): reviews × 60

    Returns a dict with low/med/high estimates.
    """
    if review_count <= 0:
        return {"low": 0, "med": 0, "high": 0, "review_count": 0}
    return {
        "low": review_count * _REVIEW_MULTIPLIER_LOW,
        "med": review_count * _REVIEW_MULTIPLIER_MED,
        "high": review_count * _REVIEW_MULTIPLIER_HIGH,
        "review_count": review_count,
    }


async def enrich_game_data(
    appid: str,
    game_name: str,
    review_count: int = 0,
    cc: str = "us",
) -> dict[str, Any]:
    """Fetch all enrichment data for a game in one call.

    Combines Steam price, Twitch stats, and owner estimates.
    All sub-fetches are independent; failures in one don't block others.
    """
    import asyncio

    price_task = fetch_steam_price(appid, cc=cc)
    twitch_task = fetch_twitch_stats(game_name)

    price, twitch = await asyncio.gather(price_task, twitch_task)

    owners = estimate_owners_from_reviews(review_count)

    return {
        "price_data": price,
        "twitch_stats": twitch,
        "owner_estimates": owners,
    }
