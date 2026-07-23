"""Notification dispatcher for GamesTracker.

Supports Discord (webhook embeds) and Telegram (Bot API markdown) channels.

Notification types
------------------
game_spike            -- sudden player-count surge on a tracked game
new_social_mention    -- Reddit / YouTube mention exceeding threshold
weekly_digest         -- weekly growth summary across all tracked games
quality_threshold_crossed -- quality score crossed configured threshold

Usage
-----
    from core.notifications import send_notification

    await send_notification(
        "game_spike",
        {
            "game_name": "Hollow Knight",
            "platform": "Steam",
            "current_players": 45_000,
            "previous_players": 12_000,
            "pct_change": 275.0,
        },
    )

Configuration (.env keys)
-------------------------
    DISCORD_WEBHOOK_URL      -- full Discord webhook URL (optional)
    TELEGRAM_BOT_TOKEN       -- Telegram bot token (optional)
    TELEGRAM_CHAT_ID         -- target chat / channel ID (optional)
    NOTIFICATIONS_ENABLED    -- master switch, default false
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEGRAM_API_BASE = "https://api.telegram.org"

# Discord embed colours (decimal)
_COLOUR_SPIKE = 0x00B0F4       # blue
_COLOUR_SOCIAL = 0xF4A100      # amber
_COLOUR_DIGEST = 0x57F287      # green
_COLOUR_QUALITY = 0xED4245     # red

NotificationType = str  # literal union kept as string for extensibility


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _cfg(key: str, default: str = "") -> str:
    """Read a config value from the environment."""
    return os.getenv(key, default).strip()


def _notifications_enabled() -> bool:
    return _cfg("NOTIFICATIONS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


@dataclass
class _ChannelConfig:
    discord_webhook_url: str = field(default_factory=lambda: _cfg("DISCORD_WEBHOOK_URL"))
    telegram_bot_token: str = field(default_factory=lambda: _cfg("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _cfg("TELEGRAM_CHAT_ID"))

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _ts_now() -> str:
    """ISO-8601 timestamp in UTC."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Discord ----------------------------------------------------------------

def _discord_embed(
    title: str,
    description: str,
    colour: int,
    fields: list[dict[str, Any]] | None = None,
    footer: str = "GamesTracker",
) -> dict[str, Any]:
    embed: dict[str, Any] = {
        "title": title,
        "description": description,
        "color": colour,
        "timestamp": _ts_now(),
        "footer": {"text": footer},
    }
    if fields:
        embed["fields"] = fields
    return embed


def _discord_payload_for(notification_type: NotificationType, data: dict[str, Any]) -> dict[str, Any]:
    """Build a Discord webhook payload dict for the given notification type."""
    game = data.get("game_name", "Unknown game")
    platform = data.get("platform", "Unknown platform")

    if notification_type == "game_spike":
        current = data.get("current_players", 0)
        previous = data.get("previous_players", 0)
        pct = data.get("pct_change", 0.0)
        embed = _discord_embed(
            title=f"Player spike — {game}",
            description=(
                f"**{game}** ({platform}) just had a significant player-count surge."
            ),
            colour=_COLOUR_SPIKE,
            fields=[
                {"name": "Current players", "value": f"{current:,}", "inline": True},
                {"name": "Previous players", "value": f"{previous:,}", "inline": True},
                {"name": "Change", "value": f"+{pct:.1f}%", "inline": True},
            ],
        )

    elif notification_type == "new_social_mention":
        source = data.get("source", "Unknown")
        url = data.get("url", "")
        snippet = data.get("snippet", "")
        embed = _discord_embed(
            title=f"New mention — {game}",
            description=(
                f"**{game}** was mentioned on **{source}** ({platform})."
            ),
            colour=_COLOUR_SOCIAL,
            fields=[
                {"name": "Platform", "value": platform, "inline": True},
                {"name": "Source", "value": source, "inline": True},
                *(
                    [{"name": "Preview", "value": snippet[:1024], "inline": False}]
                    if snippet
                    else []
                ),
                *(
                    [{"name": "Link", "value": url, "inline": False}]
                    if url
                    else []
                ),
            ],
        )

    elif notification_type == "weekly_digest":
        games: list[dict[str, Any]] = data.get("games", [])
        period = data.get("period_label", "last 7 days")
        lines = []
        for g in games[:20]:  # cap at 20 to stay inside Discord field limit
            name = g.get("game_name", "?")
            pct = g.get("pct_change", 0.0)
            arrow = "+" if pct >= 0 else ""
            lines.append(f"• **{name}** — {arrow}{pct:.1f}%")
        description = "\n".join(lines) if lines else "No data for this period."
        embed = _discord_embed(
            title=f"Weekly digest ({period})",
            description=description,
            colour=_COLOUR_DIGEST,
            fields=[
                {"name": "Games tracked", "value": str(len(games)), "inline": True},
            ],
        )

    elif notification_type == "quality_threshold_crossed":
        score = data.get("score", 0.0)
        threshold = data.get("threshold", 0.0)
        direction = "above" if data.get("direction", "above") == "above" else "below"
        embed = _discord_embed(
            title=f"Quality threshold crossed — {game}",
            description=(
                f"**{game}** ({platform}) quality score moved **{direction}** the threshold."
            ),
            colour=_COLOUR_QUALITY,
            fields=[
                {"name": "Score", "value": f"{score:.1f}", "inline": True},
                {"name": "Threshold", "value": f"{threshold:.1f}", "inline": True},
                {"name": "Direction", "value": direction.capitalize(), "inline": True},
            ],
        )

    else:
        embed = _discord_embed(
            title=f"GamesTracker notification ({notification_type})",
            description=str(data),
            colour=0x99AAB5,
        )

    return {"embeds": [embed]}


# --- Telegram ---------------------------------------------------------------

def _tg_text_for(notification_type: NotificationType, data: dict[str, Any]) -> str:
    """Build a Telegram MarkdownV2-escaped message string."""

    def esc(text: str) -> str:
        """Escape special MarkdownV2 characters."""
        for ch in r"\_*[]()~`>#+-=|{}.!":
            text = text.replace(ch, f"\\{ch}")
        return text

    game = esc(data.get("game_name", "Unknown game"))
    platform = esc(data.get("platform", "Unknown platform"))

    if notification_type == "game_spike":
        current = data.get("current_players", 0)
        previous = data.get("previous_players", 0)
        pct = data.get("pct_change", 0.0)
        return (
            f"*Player spike — {game}*\n"
            f"Platform: {platform}\n"
            f"Current: *{current:,}* \\| Previous: *{previous:,}*\n"
            f"Change: *\\+{pct:.1f}%*"
        )

    elif notification_type == "new_social_mention":
        source = esc(data.get("source", "Unknown"))
        url = data.get("url", "")
        snippet = esc(data.get("snippet", "")[:300])
        msg = (
            f"*New mention — {game}*\n"
            f"Platform: {platform} \\| Source: {source}\n"
        )
        if snippet:
            msg += f"_{snippet}_\n"
        if url:
            msg += f"[View post]({url})"
        return msg

    elif notification_type == "weekly_digest":
        games: list[dict[str, Any]] = data.get("games", [])
        period = esc(data.get("period_label", "last 7 days"))
        lines = [f"*Weekly digest \\({period}\\)*"]
        for g in games[:20]:
            name = esc(g.get("game_name", "?"))
            pct = g.get("pct_change", 0.0)
            arrow = "\\+" if pct >= 0 else ""
            lines.append(f"• {name} — {arrow}{pct:.1f}%")
        lines.append(f"\n_Games tracked: {len(games)}_")
        return "\n".join(lines)

    elif notification_type == "quality_threshold_crossed":
        score = data.get("score", 0.0)
        threshold = data.get("threshold", 0.0)
        direction = esc(data.get("direction", "above"))
        return (
            f"*Quality threshold crossed — {game}*\n"
            f"Platform: {platform}\n"
            f"Score: *{score:.1f}* \\| Threshold: *{threshold:.1f}*\n"
            f"Direction: *{direction}*"
        )

    else:
        return f"*GamesTracker* \\({esc(notification_type)}\\)\n{esc(str(data))}"


# ---------------------------------------------------------------------------
# HTTP dispatch
# ---------------------------------------------------------------------------

async def _post_discord(
    client: httpx.AsyncClient,
    webhook_url: str,
    payload: dict[str, Any],
) -> None:
    try:
        resp = await client.post(webhook_url, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.debug("Discord notification sent (status %s)", resp.status_code)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Discord webhook returned HTTP %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.error("Discord webhook request failed: %s", exc)


async def _post_telegram(
    client: httpx.AsyncClient,
    bot_token: str,
    chat_id: str,
    text: str,
) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        resp = await client.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.debug("Telegram notification sent (status %s)", resp.status_code)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Telegram API returned HTTP %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.error("Telegram API request failed: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

VALID_TYPES: frozenset[NotificationType] = frozenset(
    {
        "game_spike",
        "new_social_mention",
        "weekly_digest",
        "quality_threshold_crossed",
    }
)


async def send_notification(
    notification_type: NotificationType,
    data: dict[str, Any],
    channels: Sequence[str] | None = None,
    *,
    _cfg_override: _ChannelConfig | None = None,
    _client_override: httpx.AsyncClient | None = None,
) -> None:
    """Dispatch a notification to the configured channels.

    Parameters
    ----------
    notification_type:
        One of ``game_spike``, ``new_social_mention``, ``weekly_digest``,
        ``quality_threshold_crossed``.
    data:
        Dictionary with notification payload. Required keys vary by type:

        ``game_spike``
            game_name, platform, current_players, previous_players, pct_change

        ``new_social_mention``
            game_name, platform, source, url (optional), snippet (optional)

        ``weekly_digest``
            games (list of dicts with game_name, pct_change), period_label

        ``quality_threshold_crossed``
            game_name, platform, score, threshold, direction ("above"/"below")

    channels:
        Subset of ``["discord", "telegram"]`` to target. Defaults to all
        configured channels.
    _cfg_override / _client_override:
        Testing seams — do not use in production code.
    """
    if not _notifications_enabled():
        logger.debug("Notifications disabled (NOTIFICATIONS_ENABLED not set). Skipping.")
        return

    if notification_type not in VALID_TYPES:
        logger.warning(
            "Unknown notification type %r — sending as generic notification.",
            notification_type,
        )

    cfg = _cfg_override if _cfg_override is not None else _ChannelConfig()

    target_channels: set[str]
    if channels is None:
        target_channels = set()
        if cfg.discord_enabled:
            target_channels.add("discord")
        if cfg.telegram_enabled:
            target_channels.add("telegram")
    else:
        target_channels = set(channels)

    if not target_channels:
        logger.debug("No notification channels configured or requested — nothing to send.")
        return

    async def _dispatch(client: httpx.AsyncClient) -> None:
        if "discord" in target_channels and cfg.discord_enabled:
            payload = _discord_payload_for(notification_type, data)
            await _post_discord(client, cfg.discord_webhook_url, payload)

        if "telegram" in target_channels and cfg.telegram_enabled:
            text = _tg_text_for(notification_type, data)
            await _post_telegram(client, cfg.telegram_bot_token, cfg.telegram_chat_id, text)

    if _client_override is not None:
        await _dispatch(_client_override)
    else:
        async with httpx.AsyncClient() as client:
            await _dispatch(client)
