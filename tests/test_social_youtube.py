"""Test della sorgente YouTube: parsing search+videos, quota, canali.

Nessuna chiamata reale: iniettiamo un client mock che imita la fluent-API di
google-api-python-client (``client.search().list(...).execute()`` ecc.).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import Settings
from core.sources.social.base import GameQuery, NormalizedAccount
from core.sources.social.youtube import (
    COST_SEARCH,
    COST_VIDEOS,
    QuotaExceededError,
    QuotaTracker,
    YouTubeSource,
)


class _FakeExecutable:
    """Oggetto con ``.execute()`` che ritorna una risposta preimpostata."""

    def __init__(self, response: dict) -> None:
        self._response = response

    def execute(self) -> dict:
        return self._response


class _FakeResource:
    """Imita una risorsa API (search/videos/channels) con ``.list(...)``."""

    def __init__(self, response: dict, calls: list) -> None:
        self._response = response
        self._calls = calls

    def list(self, **kwargs):  # noqa: ANN003
        self._calls.append(kwargs)
        return _FakeExecutable(self._response)


class FakeYouTubeClient:
    """Client YouTube fittizio con risposte configurabili per endpoint."""

    def __init__(
        self,
        search_response: dict | None = None,
        videos_response: dict | None = None,
        channels_response: dict | None = None,
    ) -> None:
        self.search_response = search_response or {"items": []}
        self.videos_response = videos_response or {"items": []}
        self.channels_response = channels_response or {"items": []}
        self.search_calls: list = []
        self.videos_calls: list = []
        self.channels_calls: list = []

    def search(self):
        return _FakeResource(self.search_response, self.search_calls)

    def videos(self):
        return _FakeResource(self.videos_response, self.videos_calls)

    def channels(self):
        return _FakeResource(self.channels_response, self.channels_calls)


@pytest.fixture
def game() -> GameQuery:
    return GameQuery(title="Hollow Star", genres=["metroidvania"], tags=["pixel-art"])


def _source(client, tmp_path, quota=None) -> YouTubeSource:
    settings = Settings(youtube_api_key="", data_dir=tmp_path)
    return YouTubeSource(
        settings=settings,
        client=client,
        quota=quota,
        cache_dir=tmp_path / "yt_cache",
    )


def test_search_parsing_and_quota(game, tmp_path):
    client = FakeYouTubeClient(
        search_response={
            "items": [
                {"id": {"videoId": "abc123"}},
                {"id": {"videoId": "def456"}},
                {"id": {"kind": "channel"}},  # da ignorare (no videoId)
            ]
        }
    )
    quota = QuotaTracker(daily_limit=1000)
    src = _source(client, tmp_path, quota)

    ids = src.search_video_ids(game, use_cache=False)

    assert ids == ["abc123", "def456"]
    assert quota.used == COST_SEARCH  # una search = 100 unita'
    assert len(client.search_calls) == 1


def test_search_uses_cache_second_call(game, tmp_path):
    client = FakeYouTubeClient(
        search_response={"items": [{"id": {"videoId": "abc123"}}]}
    )
    quota = QuotaTracker(daily_limit=1000)
    src = _source(client, tmp_path, quota)

    first = src.search_video_ids(game, use_cache=True)
    second = src.search_video_ids(game, use_cache=True)

    assert first == second == ["abc123"]
    # La seconda chiamata NON spende quota (cache hit).
    assert quota.used == COST_SEARCH
    assert len(client.search_calls) == 1


def test_fetch_video_stats_parsing(tmp_path):
    client = FakeYouTubeClient(
        videos_response={
            "items": [
                {
                    "id": "abc123",
                    "snippet": {
                        "title": "Hollow Star - Official Trailer",
                        "publishedAt": "2025-03-01T12:00:00Z",
                    },
                    "statistics": {
                        "viewCount": "15000",
                        "likeCount": "800",
                        "commentCount": "45",
                    },
                },
                {
                    "id": "def456",
                    "snippet": {
                        "title": "Gameplay",
                        "publishedAt": "2025-03-05T09:30:00Z",
                    },
                    # likeCount/commentCount disabilitati -> assenti -> None
                    "statistics": {"viewCount": "2000"},
                },
            ]
        }
    )
    quota = QuotaTracker(daily_limit=1000)
    src = _source(client, tmp_path, quota)

    posts = src.fetch_video_stats(["abc123", "def456"])

    assert len(posts) == 2
    p0 = posts[0]
    assert p0.platform == "youtube"
    assert p0.post_url == "https://www.youtube.com/watch?v=abc123"
    assert p0.title == "Hollow Star - Official Trailer"
    assert p0.posted_at == datetime(2025, 3, 1, 12, 0, tzinfo=timezone.utc)
    assert p0.views == 15000
    assert p0.likes == 800
    assert p0.comments == 45
    # Metriche assenti = None, MAI 0.
    assert posts[1].likes is None
    assert posts[1].comments is None
    assert posts[1].views == 2000
    # batch singolo = 1 unita'
    assert quota.used == COST_VIDEOS


def test_batching_50_ids_one_unit_each(tmp_path):
    client = FakeYouTubeClient(videos_response={"items": []})
    quota = QuotaTracker(daily_limit=1000)
    src = _source(client, tmp_path, quota)

    # 120 id => 3 batch (50+50+20) => 3 unita'
    src.fetch_video_stats([f"id{i}" for i in range(120)])

    assert len(client.videos_calls) == 3
    assert quota.used == 3 * COST_VIDEOS


def test_quota_exceeded_raises(game, tmp_path):
    client = FakeYouTubeClient()
    quota = QuotaTracker(daily_limit=50)  # meno del costo di una search (100)
    src = _source(client, tmp_path, quota)

    with pytest.raises(QuotaExceededError):
        src.search_video_ids(game, use_cache=False)
    # Nessuna chiamata effettuata perche' la quota blocca prima.
    assert len(client.search_calls) == 0


def test_channels_parsing_hidden_subscribers(tmp_path):
    client = FakeYouTubeClient(
        channels_response={
            "items": [
                {
                    "id": "chan1",
                    "snippet": {"title": "DevStudio", "customUrl": "@devstudio"},
                    "statistics": {
                        "subscriberCount": "5000",
                        "videoCount": "42",
                        "viewCount": "999999",
                        "hiddenSubscriberCount": False,
                    },
                },
                {
                    "id": "chan2",
                    "snippet": {"title": "Hidden"},
                    "statistics": {
                        "subscriberCount": "0",
                        "videoCount": "10",
                        "hiddenSubscriberCount": True,
                    },
                },
            ]
        }
    )
    src = _source(client, tmp_path)

    data = src.fetch_channels(["chan1", "chan2"])
    assert data["chan1"]["subscribers"] == 5000
    assert data["chan1"]["videos"] == 42
    assert data["chan1"]["handle"] == "@devstudio"
    # subscriber nascosti -> None, non 0
    assert data["chan2"]["subscribers"] is None


def test_snapshot_account_from_channel(tmp_path):
    client = FakeYouTubeClient(
        channels_response={
            "items": [
                {
                    "id": "chan1",
                    "snippet": {"title": "DevStudio"},
                    "statistics": {
                        "subscriberCount": "5000",
                        "videoCount": "42",
                        "viewCount": "999999",
                        "hiddenSubscriberCount": False,
                    },
                }
            ]
        }
    )
    src = _source(client, tmp_path)
    acc = NormalizedAccount(platform="youtube", handle="chan1")

    snap = src.snapshot_account(acc)
    assert snap is not None
    assert snap.followers == 5000
    assert snap.total_posts == 42
    assert snap.extra["collection"] == "api"


def test_disabled_when_no_key(tmp_path):
    settings = Settings(youtube_api_key="", data_dir=tmp_path)
    src = YouTubeSource(settings=settings, cache_dir=tmp_path / "c")
    assert src.enabled is False
    # Degrada senza crashare: liste vuote.
    game = GameQuery(title="Whatever")
    assert src.search_video_ids(game) == []
    assert src.collect_posts(game) == []


def test_include_team_adds_developer_publisher_to_query(tmp_path):
    """Con include_team, dev/publisher entrano nella query di ricerca."""
    client = FakeYouTubeClient(
        search_response={"items": [{"id": {"videoId": "x"}}]}
    )
    src = _source(client, tmp_path, QuotaTracker(daily_limit=1000))
    game = GameQuery(title="Palworld", developer="Pocketpair", publisher="Pocketpair")

    src.search_video_ids(game, use_cache=False, include_team=True)

    q = client.search_calls[0]["q"]
    assert "Pocketpair" in q
    assert '"Palworld"' in q


def test_include_team_uses_distinct_cache_key(tmp_path):
    """La query con team non deve riusare la cache della query base."""
    client = FakeYouTubeClient(
        search_response={"items": [{"id": {"videoId": "x"}}]}
    )
    src = _source(client, tmp_path, QuotaTracker(daily_limit=1000))
    game = GameQuery(title="Palworld", developer="Pocketpair")

    src.search_video_ids(game, use_cache=True, include_team=False)
    src.search_video_ids(game, use_cache=True, include_team=True)

    # Cache key diversa => due chiamate reali (nessun falso cache-hit).
    assert len(client.search_calls) == 2


def test_capture_pre_launch_drops_published_after(tmp_path):
    """capture_pre_launch non limita publishedAfter alla data demo."""
    client = FakeYouTubeClient(
        search_response={"items": [{"id": {"videoId": "x"}}]}
    )
    src = _source(client, tmp_path, QuotaTracker(daily_limit=1000))
    game = GameQuery(
        title="Palworld",
        demo_release_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    # Senza pre-launch: publishedAfter = data demo.
    src.search_video_ids(game, use_cache=False, capture_pre_launch=False)
    assert "publishedAfter" in client.search_calls[0]

    # Con pre-launch: nessun limite temporale (cattura i video pre-demo).
    src.search_video_ids(game, use_cache=False, capture_pre_launch=True)
    assert "publishedAfter" not in client.search_calls[1]
