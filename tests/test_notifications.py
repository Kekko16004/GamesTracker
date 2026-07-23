"""Tests for core/notifications.py.

All HTTP calls are mocked via httpx.MockTransport so no real network traffic
is generated. The NOTIFICATIONS_ENABLED env var is set to "true" for every
test that exercises actual dispatch; individual tests that verify the "disabled"
guard leave it unset.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from core.notifications import (
    VALID_TYPES,
    _ChannelConfig,
    _discord_payload_for,
    _tg_text_for,
    send_notification,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DISCORD_URL = "https://discord.com/api/webhooks/000/test"
_TG_TOKEN = "123456:AABBCC"
_TG_CHAT = "-100999"


def _make_cfg(discord: bool = True, telegram: bool = True) -> _ChannelConfig:
    return _ChannelConfig(
        discord_webhook_url=_DISCORD_URL if discord else "",
        telegram_bot_token=_TG_TOKEN if telegram else "",
        telegram_chat_id=_TG_CHAT if telegram else "",
    )


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Records every request made through the client."""

    def __init__(self, status_code: int = 204):
        self.requests: list[httpx.Request] = []
        self._status = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, content=b"")


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Unit tests — payload builders (no network)
# ---------------------------------------------------------------------------

class TestDiscordPayloadBuilder:
    def test_game_spike_keys(self):
        data = {
            "game_name": "TestGame",
            "platform": "Steam",
            "current_players": 5000,
            "previous_players": 1000,
            "pct_change": 400.0,
        }
        payload = _discord_payload_for("game_spike", data)
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "TestGame" in embed["title"]
        fields = {f["name"]: f["value"] for f in embed.get("fields", [])}
        assert fields["Current players"] == "5,000"
        assert fields["Previous players"] == "1,000"
        assert "+400.0%" in fields["Change"]

    def test_weekly_digest_caps_at_20_games(self):
        games = [{"game_name": f"Game{i}", "pct_change": float(i)} for i in range(30)]
        data = {"games": games, "period_label": "last 7 days"}
        payload = _discord_payload_for("weekly_digest", data)
        description = payload["embeds"][0]["description"]
        # Should contain at most 20 bullet lines
        assert description.count("•") <= 20

    def test_social_mention_with_url(self):
        data = {
            "game_name": "Celeste",
            "platform": "Steam",
            "source": "Reddit",
            "url": "https://reddit.com/r/games/abc",
            "snippet": "This game is incredible",
        }
        payload = _discord_payload_for("new_social_mention", data)
        embed = payload["embeds"][0]
        fields = {f["name"]: f["value"] for f in embed.get("fields", [])}
        assert "reddit.com" in fields["Link"]
        assert "incredible" in fields["Preview"]

    def test_quality_threshold_crossed(self):
        data = {
            "game_name": "Hades",
            "platform": "Steam",
            "score": 87.5,
            "threshold": 40.0,
            "direction": "above",
        }
        payload = _discord_payload_for("quality_threshold_crossed", data)
        embed = payload["embeds"][0]
        fields = {f["name"]: f["value"] for f in embed.get("fields", [])}
        assert fields["Score"] == "87.5"
        assert fields["Direction"] == "Above"

    def test_unknown_type_returns_generic(self):
        payload = _discord_payload_for("mystery_event", {"x": 1})
        assert "mystery_event" in payload["embeds"][0]["title"]

    def test_embed_has_timestamp(self):
        payload = _discord_payload_for("game_spike", {"game_name": "X", "platform": "Y"})
        assert "timestamp" in payload["embeds"][0]


class TestTelegramTextBuilder:
    def test_game_spike_contains_percentage(self):
        data = {
            "game_name": "FEZ",
            "platform": "Steam",
            "current_players": 800,
            "previous_players": 200,
            "pct_change": 300.0,
        }
        text = _tg_text_for("game_spike", data)
        assert "300.0" in text
        assert "FEZ" in text

    def test_weekly_digest_lists_games(self):
        games = [
            {"game_name": "Game A", "pct_change": 10.5},
            {"game_name": "Game B", "pct_change": -3.2},
        ]
        text = _tg_text_for("weekly_digest", {"games": games, "period_label": "last 7 days"})
        assert "Game A" in text
        assert "Game B" in text

    def test_social_mention_optional_url(self):
        data = {
            "game_name": "Undertale",
            "platform": "Steam",
            "source": "YouTube",
        }
        # Should not raise even without url/snippet
        text = _tg_text_for("new_social_mention", data)
        assert "Undertale" in text

    def test_quality_threshold_direction(self):
        data = {
            "game_name": "Hollow Knight",
            "platform": "Steam",
            "score": 35.0,
            "threshold": 40.0,
            "direction": "below",
        }
        text = _tg_text_for("quality_threshold_crossed", data)
        assert "below" in text.lower()


# ---------------------------------------------------------------------------
# Integration tests — send_notification with mocked transport
# ---------------------------------------------------------------------------

class TestSendNotification:
    def _run_notify(self, notification_type, data, channels=None, transport=None, discord=True, telegram=True):
        cfg = _make_cfg(discord=discord, telegram=telegram)
        if transport is None:
            transport = _RecordingTransport()
        client = httpx.AsyncClient(transport=transport)
        _run(
            send_notification(
                notification_type,
                data,
                channels=channels,
                _cfg_override=cfg,
                _client_override=client,
            )
        )
        return transport

    def test_sends_to_discord_when_enabled(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "A", "platform": "Steam"}, transport=t, telegram=False)
            assert len(t.requests) == 1
            assert "discord.com" in str(t.requests[0].url)

    def test_sends_to_telegram_when_enabled(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "A", "platform": "Steam"}, transport=t, discord=False)
            assert len(t.requests) == 1
            assert "telegram.org" in str(t.requests[0].url)

    def test_sends_to_both_channels_by_default(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "A", "platform": "Steam"}, transport=t)
            assert len(t.requests) == 2

    def test_channel_filter_discord_only(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify(
                "game_spike",
                {"game_name": "A", "platform": "Steam"},
                channels=["discord"],
                transport=t,
            )
            urls = [str(r.url) for r in t.requests]
            assert all("discord.com" in u for u in urls)
            assert len(urls) == 1

    def test_notifications_disabled_no_requests(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "false"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "A", "platform": "Steam"}, transport=t)
            assert len(t.requests) == 0

    def test_no_channels_configured_no_requests(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "A", "platform": "Steam"}, transport=t, discord=False, telegram=False)
            assert len(t.requests) == 0

    def test_discord_request_body_is_valid_json(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("game_spike", {"game_name": "Ori", "platform": "Steam", "pct_change": 55.0}, transport=t, telegram=False)
            body = json.loads(t.requests[0].content)
            assert "embeds" in body

    def test_telegram_request_body_contains_chat_id(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify("weekly_digest", {"games": [], "period_label": "last 7 days"}, transport=t, discord=False)
            body = json.loads(t.requests[0].content)
            assert body["chat_id"] == _TG_CHAT

    def test_http_error_does_not_raise(self):
        """A 4xx/5xx response must be logged but not re-raised."""
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport(status_code=400)
            # Should complete without raising
            self._run_notify("game_spike", {"game_name": "X", "platform": "Y"}, transport=t, telegram=False)

    def test_weekly_digest_notification(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            games = [
                {"game_name": "Shovel Knight", "pct_change": 12.3},
                {"game_name": "Cuphead", "pct_change": -5.1},
            ]
            self._run_notify(
                "weekly_digest",
                {"games": games, "period_label": "2024-W03"},
                transport=t,
            )
            assert len(t.requests) == 2  # discord + telegram

    def test_quality_threshold_notification(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            t = _RecordingTransport()
            self._run_notify(
                "quality_threshold_crossed",
                {
                    "game_name": "Dead Cells",
                    "platform": "Steam",
                    "score": 42.0,
                    "threshold": 40.0,
                    "direction": "above",
                },
                transport=t,
            )
            assert len(t.requests) == 2


# ---------------------------------------------------------------------------
# Valid types set
# ---------------------------------------------------------------------------

class TestValidTypes:
    def test_all_four_types_are_valid(self):
        expected = {"game_spike", "new_social_mention", "weekly_digest", "quality_threshold_crossed"}
        assert expected == VALID_TYPES

    def test_channel_config_discord_enabled_false_when_url_missing(self):
        cfg = _ChannelConfig(discord_webhook_url="", telegram_bot_token="x", telegram_chat_id="y")
        assert not cfg.discord_enabled
        assert cfg.telegram_enabled

    def test_channel_config_telegram_disabled_when_partial(self):
        cfg = _ChannelConfig(discord_webhook_url="https://hook", telegram_bot_token="tok", telegram_chat_id="")
        assert not cfg.telegram_enabled
