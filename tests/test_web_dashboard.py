"""Tests for the GamesTracker web dashboard (FastAPI).

Uses:
- TestClient from fastapi.testclient (no live server needed)
- An in-memory SQLite database seeded with fixture data

The tests mock ``web.data_access._repo`` so no real DB file is required.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Make sure project root is on path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures — minimal test data
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

GAME_1 = {
    "id": 1,
    "platform": "steam",
    "external_id": "123456",
    "title": "Hollow Caverns",
    "developer": "Pixel Dev",
    "publisher": "Pixel Dev",
    "genres": ["Action", "Indie"],
    "tags": ["roguelike", "pixel-art"],
    "release_date": "2025-06-01",
    "has_demo": True,
    "demo_release_date": "2025-03-01",
    "price": 12.99,
    "is_free": False,
    "store_url": "https://store.steampowered.com/app/123456",
    "header_image": None,
    "quality_score": 78.5,
    "discarded": False,
    "latest_reviews": 450,
    "latest_players": 120,
    "review_growth": 200,
    "snapshots": [
        {
            "captured_at": "2026-01-10T12:00:00+00:00",
            "snapshot_type": "h24",
            "total_reviews": 250,
            "total_positive": 230,
            "total_negative": 20,
            "current_players": 95,
        },
        {
            "captured_at": "2026-01-15T12:00:00+00:00",
            "snapshot_type": "h24",
            "total_reviews": 450,
            "total_positive": 420,
            "total_negative": 30,
            "current_players": 120,
        },
    ],
    "timeline": [
        {
            "kind": "demo",
            "when": "2025-03-01T00:00:00+00:00",
            "label": "Demo released",
            "platform": None,
            "url": None,
        },
        {
            "kind": "release",
            "when": "2025-06-01T00:00:00+00:00",
            "label": "Game released",
            "platform": None,
            "url": None,
        },
    ],
    "social_accounts": [
        {
            "id": 1,
            "platform": "twitter",
            "handle": "pixeldev",
            "url": "https://twitter.com/pixeldev",
            "discovered_via": None,
            "latest_followers": 3200,
        }
    ],
    "social_posts": [
        {
            "id": 1,
            "platform": "reddit",
            "posted_at": "2025-06-02T10:00:00+00:00",
            "title": "Just launched Hollow Caverns!",
            "subreddit": "indiegaming",
            "url": "https://reddit.com/r/indiegaming/...",
            "views": 5000,
            "likes": 320,
            "comments": 45,
            "shares": None,
        }
    ],
}

GAME_2 = {
    "id": 2,
    "platform": "itch",
    "external_id": "abc",
    "title": "Star Drift",
    "developer": "Solo Dev",
    "publisher": None,
    "genres": ["Strategy"],
    "tags": [],
    "release_date": None,
    "has_demo": False,
    "demo_release_date": None,
    "price": None,
    "is_free": True,
    "store_url": "https://solodev.itch.io/star-drift",
    "header_image": None,
    "quality_score": 45.0,
    "discarded": False,
    "latest_reviews": None,
    "latest_players": None,
    "review_growth": None,
    "snapshots": [],
    "timeline": [],
    "social_accounts": [],
    "social_posts": [],
}

TREND_DATA = {
    "genre_trends": [
        {"genre": "Action", "game_count": 5, "avg_quality_score": 65.0, "total_review_growth": 800},
        {"genre": "Strategy", "game_count": 3, "avg_quality_score": 55.0, "total_review_growth": 400},
    ],
    "top_growing": [
        {"id": 1, "title": "Hollow Caverns", "platform": "steam", "quality_score": 78.5, "review_growth": 200, "genres": ["Action"]},
    ],
    "genre_distribution": {"Action": 5, "Strategy": 3},
    "stats": {"total_games": 8, "visible_games": 7, "discarded_games": 1, "recent_releases": 2},
}

STATS = {"total_games": 8, "visible_games": 7, "discarded_games": 1, "recent_releases": 2}

REPORTS = [
    {
        "id": 1,
        "game_id": 1,
        "game_title": "Hollow Caverns",
        "genre": None,
        "lang": "en",
        "generated_at": "2026-01-15T10:00:00+00:00",
        "summary_preview": "Strong growth in the first week.",
    }
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_da(
    games: list[dict[str, Any]] | None = None,
    detail: dict[str, Any] | None = None,
    trends: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    reports: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a MagicMock that stands in for the web.data_access module."""
    mock = MagicMock()
    mock.get_games_list.return_value = games if games is not None else [GAME_1, GAME_2]
    mock.get_game_detail.return_value = detail  # None = not found
    mock.get_game_snapshots.return_value = detail["snapshots"] if detail else []
    mock.get_game_social.return_value = {
        "accounts": detail["social_accounts"] if detail else [],
        "posts": detail["social_posts"] if detail else [],
    }
    mock.get_trend_data.return_value = trends if trends is not None else TREND_DATA
    mock.get_dashboard_stats.return_value = stats if stats is not None else STATS
    mock.get_reports_list.return_value = reports if reports is not None else REPORTS
    mock.get_available_genres.return_value = ["Action", "Indie", "Strategy"]
    mock.get_report_detail.return_value = (
        {**REPORTS[0], "summary": "Full summary text.", "data": {}}
        if reports is not False
        else None
    )
    return mock


# ---------------------------------------------------------------------------
# Shared test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """TestClient with data_access fully mocked."""
    mock_da = _make_mock_da(detail=GAME_1)
    with patch("web.main.da", mock_da):
        from web.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_da


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/health")
        assert resp.status_code == 200

    def test_body_contains_ok(self, client):
        tc, _ = client
        body = resp = tc.get("/health").json()
        assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# Dashboard HTML page
# ---------------------------------------------------------------------------


class TestDashboard:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200

    def test_content_type_html(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_contains_game_title(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert "Hollow Caverns" in resp.text

    def test_contains_stat_strip(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert "Total Games" in resp.text

    def test_htmx_partial_returns_cards_only(self, client):
        tc, _ = client
        resp = tc.get("/", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        # Partial must not include the full base template sidebar
        assert "sidebar__logo" not in resp.text
        assert "Hollow Caverns" in resp.text

    def test_platform_filter_passed_to_da(self, client):
        tc, mock_da = client
        tc.get("/?platform=steam")
        call_kwargs = mock_da.get_games_list.call_args.kwargs
        assert call_kwargs["platform"] == "steam"

    def test_min_score_filter_passed_to_da(self, client):
        tc, mock_da = client
        tc.get("/?min_score=50")
        call_kwargs = mock_da.get_games_list.call_args.kwargs
        assert call_kwargs["min_score"] == 50.0

    def test_sort_by_filter_passed_to_da(self, client):
        tc, mock_da = client
        tc.get("/?sort_by=growth")
        call_kwargs = mock_da.get_games_list.call_args.kwargs
        assert call_kwargs["sort_by"] == "growth"

    def test_search_filter_passed_to_da(self, client):
        tc, mock_da = client
        tc.get("/?search=hollow")
        call_kwargs = mock_da.get_games_list.call_args.kwargs
        assert call_kwargs["search"] == "hollow"

    def test_empty_results_shows_empty_state(self):
        mock_da = _make_mock_da(games=[], detail=None)
        mock_da.get_games_list.return_value = []
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app) as tc:
                resp = tc.get("/?search=nonexistent")
        assert "No games found" in resp.text

    def test_empty_string_query_params_returns_200(self, client):
        tc, _ = client
        url = "/?search=&developer=&platform=&sort_by=quality_score&genre=&tag=&min_score=0&max_score=100&min_price=&max_price=&revenue=likely_recouped"
        resp = tc.get(url)
        assert resp.status_code == 200



# ---------------------------------------------------------------------------
# Game detail page
# ---------------------------------------------------------------------------


class TestGameDetail:
    def test_existing_game_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert resp.status_code == 200

    def test_page_contains_game_title(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "Hollow Caverns" in resp.text

    def test_page_contains_developer(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "Pixel Dev" in resp.text

    def test_page_contains_quality_score(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "78" in resp.text   # score rendered as integer

    def test_page_contains_chart_script(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "playersChart" in resp.text
        assert "reviewsChart" in resp.text

    def test_page_contains_social_accounts(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "twitter" in resp.text.lower()

    def test_page_contains_timeline(self, client):
        tc, _ = client
        resp = tc.get("/game/1")
        assert "demo" in resp.text.lower()
        assert "release" in resp.text.lower()

    def test_missing_game_returns_404(self):
        mock_da = _make_mock_da(detail=None)
        mock_da.get_game_detail.return_value = None
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app, raise_server_exceptions=False) as tc:
                resp = tc.get("/game/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Trends page
# ---------------------------------------------------------------------------


class TestTrends:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/trends")
        assert resp.status_code == 200

    def test_contains_genre_names(self, client):
        tc, _ = client
        resp = tc.get("/trends")
        assert "Action" in resp.text
        assert "Strategy" in resp.text

    def test_contains_top_growing_table(self, client):
        tc, _ = client
        resp = tc.get("/trends")
        assert "Top Growing" in resp.text

    def test_contains_chart_scripts(self, client):
        tc, _ = client
        resp = tc.get("/trends")
        assert "genreCountChart" in resp.text

    def test_empty_trends_shows_empty_state(self):
        empty = {"genre_trends": [], "top_growing": [], "genre_distribution": {}, "stats": STATS}
        mock_da = _make_mock_da(trends=empty, detail=None)
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app) as tc:
                resp = tc.get("/trends")
        assert resp.status_code == 200
        assert "No trend data" in resp.text


# ---------------------------------------------------------------------------
# Reports page
# ---------------------------------------------------------------------------


class TestReports:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/reports")
        assert resp.status_code == 200

    def test_contains_report_game_title(self, client):
        tc, _ = client
        resp = tc.get("/reports")
        assert "Hollow Caverns" in resp.text

    def test_contains_summary_preview(self, client):
        tc, _ = client
        resp = tc.get("/reports")
        assert "Strong growth" in resp.text

    def test_empty_reports_shows_empty_state(self):
        mock_da = _make_mock_da(reports=[], detail=None)
        mock_da.get_reports_list.return_value = []
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app) as tc:
                resp = tc.get("/reports")
        assert "No reports yet" in resp.text


# ---------------------------------------------------------------------------
# JSON API — /api/games
# ---------------------------------------------------------------------------


class TestApiGames:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/api/games")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        tc, _ = client
        data = tc.get("/api/games").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_game_has_required_fields(self, client):
        tc, _ = client
        game = tc.get("/api/games").json()[0]
        for field in ("id", "title", "platform", "quality_score"):
            assert field in game

    def test_platform_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?platform=steam")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["platform"] == "steam"

    def test_min_score_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?min_score=60")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["min_score"] == 60.0

    def test_sort_by_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?sort_by=growth")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["sort_by"] == "growth"

    def test_search_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?search=hollow")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["search"] == "hollow"

    def test_limit_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?limit=5")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["limit"] == 5

    def test_offset_filter(self, client):
        tc, mock_da = client
        tc.get("/api/games?offset=10")
        kwargs = mock_da.get_games_list.call_args.kwargs
        assert kwargs["offset"] == 10


# ---------------------------------------------------------------------------
# JSON API — /api/game/{id}/snapshots
# ---------------------------------------------------------------------------


class TestApiSnapshots:
    def test_returns_200_for_existing(self, client):
        tc, _ = client
        resp = tc.get("/api/game/1/snapshots")
        assert resp.status_code == 200

    def test_returns_list_of_snapshots(self, client):
        tc, _ = client
        data = tc.get("/api/game/1/snapshots").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_snapshot_has_fields(self, client):
        tc, _ = client
        snap = tc.get("/api/game/1/snapshots").json()[0]
        assert "captured_at" in snap
        assert "total_reviews" in snap

    def test_missing_game_returns_404(self):
        mock_da = _make_mock_da(detail=None)
        mock_da.get_game_detail.return_value = None
        mock_da.get_game_snapshots.return_value = []
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app, raise_server_exceptions=False) as tc:
                resp = tc.get("/api/game/9999/snapshots")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# JSON API — /api/game/{id}/social
# ---------------------------------------------------------------------------


class TestApiSocial:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/api/game/1/social")
        assert resp.status_code == 200

    def test_body_has_accounts_and_posts(self, client):
        tc, _ = client
        body = tc.get("/api/game/1/social").json()
        assert "accounts" in body
        assert "posts" in body

    def test_missing_game_returns_404(self):
        mock_da = _make_mock_da(detail=None)
        mock_da.get_game_detail.return_value = None
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app, raise_server_exceptions=False) as tc:
                resp = tc.get("/api/game/9999/social")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# JSON API — /api/trends
# ---------------------------------------------------------------------------


class TestApiTrends:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/api/trends")
        assert resp.status_code == 200

    def test_body_structure(self, client):
        tc, _ = client
        body = tc.get("/api/trends").json()
        assert "genre_trends" in body
        assert "top_growing" in body
        assert "genre_distribution" in body
        assert "stats" in body

    def test_min_score_param(self, client):
        tc, mock_da = client
        tc.get("/api/trends?min_score=40")
        kwargs = mock_da.get_trend_data.call_args.kwargs
        assert kwargs["min_score"] == 40.0


# ---------------------------------------------------------------------------
# JSON API — /api/reports
# ---------------------------------------------------------------------------


class TestApiReports:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/api/reports")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        tc, _ = client
        data = tc.get("/api/reports").json()
        assert isinstance(data, list)

    def test_report_has_fields(self, client):
        tc, _ = client
        rep = tc.get("/api/reports").json()[0]
        assert "id" in rep
        assert "game_title" in rep
        assert "summary_preview" in rep


class TestApiReportDetail:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/api/reports/1")
        assert resp.status_code == 200

    def test_body_has_summary(self, client):
        tc, _ = client
        body = tc.get("/api/reports/1").json()
        assert "summary" in body

    def test_missing_report_returns_404(self):
        mock_da = _make_mock_da(reports=False)
        mock_da.get_report_detail.return_value = None
        with patch("web.main.da", mock_da):
            from web.main import app
            with TestClient(app, raise_server_exceptions=False) as tc:
                resp = tc.get("/api/reports/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Filtering logic — web/data_access.py (unit tests, no HTTP)
# ---------------------------------------------------------------------------


class TestDataAccessFiltering:
    """Unit-test the in-Python filtering/sorting in web.data_access."""

    def _make_repo(self, rows):
        """Construct a GameRepository mock that returns ``rows`` from list_games."""
        from gui.data_access import DashboardStats, GenreTrend, GameRow

        repo = MagicMock()
        repo.list_games.return_value = rows
        repo.top_by_growth.return_value = []
        repo.genre_distribution.return_value = {}
        repo.genre_trends.return_value = []
        repo.dashboard_stats.return_value = DashboardStats(
            total_games=len(rows),
            visible_games=len(rows),
            discarded_games=0,
            recent_releases=0,
        )
        repo.available_genres.return_value = []
        return repo

    def _game_row(self, **kwargs):
        from gui.data_access import GameRow
        defaults = dict(
            id=1, platform="steam", external_id="x", title="Test",
            developer=None, genres=[], release_date=None,
            quality_score=None, discarded=False,
            store_url=None, header_image=None,
            latest_reviews=None, latest_players=None, review_growth=None,
        )
        defaults.update(kwargs)
        return GameRow(**defaults)

    def test_sort_by_quality_score_descending(self):
        from web import data_access as wda

        rows = [
            self._game_row(id=1, title="A", quality_score=30.0),
            self._game_row(id=2, title="B", quality_score=90.0),
            self._game_row(id=3, title="C", quality_score=60.0),
        ]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(sort_by="quality_score")
        scores = [r["quality_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_title_alphabetical(self):
        from web import data_access as wda

        rows = [
            self._game_row(id=1, title="Zelda"),
            self._game_row(id=2, title="Armello"),
            self._game_row(id=3, title="Minecraft"),
        ]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(sort_by="title")
        titles = [r["title"] for r in result]
        assert titles == sorted(titles, key=str.lower)

    def test_sort_by_growth_descending(self):
        from web import data_access as wda

        rows = [
            self._game_row(id=1, title="A", review_growth=100),
            self._game_row(id=2, title="B", review_growth=500),
            self._game_row(id=3, title="C", review_growth=50),
        ]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(sort_by="growth")
        growths = [r["review_growth"] for r in result]
        assert growths == sorted(growths, reverse=True)

    def test_search_filter_case_insensitive(self):
        from web import data_access as wda

        rows = [
            self._game_row(id=1, title="Hollow Caverns"),
            self._game_row(id=2, title="Star Drift"),
        ]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(search="hollow")
        assert len(result) == 1
        assert result[0]["title"] == "Hollow Caverns"

    def test_search_no_match_returns_empty(self):
        from web import data_access as wda

        rows = [self._game_row(id=1, title="Hollow Caverns")]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(search="nonexistent")
        assert result == []

    def test_limit_respected(self):
        from web import data_access as wda

        rows = [self._game_row(id=i, title=f"Game {i}") for i in range(10)]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            result = wda.get_games_list(limit=3)
        assert len(result) == 3

    def test_offset_respected(self):
        from web import data_access as wda

        rows = [self._game_row(id=i, title=f"Game {i}", quality_score=float(i)) for i in range(5)]
        repo = self._make_repo(rows)
        with patch("web.data_access._repo", repo):
            all_results = wda.get_games_list()
            offset_results = wda.get_games_list(offset=2)
        assert offset_results == all_results[2:]

    def test_get_game_detail_none_when_missing(self):
        from web import data_access as wda

        repo = MagicMock()
        repo.get_game_detail.return_value = None
        with patch("web.data_access._repo", repo):
            result = wda.get_game_detail(9999)
        assert result is None

    def test_get_game_snapshots_empty_when_game_missing(self):
        from web import data_access as wda

        repo = MagicMock()
        repo.get_game_detail.return_value = None
        with patch("web.data_access._repo", repo):
            result = wda.get_game_snapshots(9999)
        assert result == []
