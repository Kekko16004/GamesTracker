"""Test dei client sorgente Steam (parsing puro, nessuna rete)."""

from __future__ import annotations

from datetime import date

from core.sources.steam_store import (
    parse_appdetails,
    parse_release_date,
    _parse_date_string,
)
from core.sources.steam_reviews import parse_query_summary
from core.sources.steam_players import parse_player_count
from core.sources.steamspy import parse_appdetails as parse_steamspy, _midpoint_owners
from core.sources.steam_discovery import parse_explore_new, parse_app_list, diff_new_appids


# --- appdetails -----------------------------------------------------------


def _appdetails_success() -> dict:
    return {
        "620": {
            "success": True,
            "data": {
                "type": "game",
                "name": "Portal 2",
                "is_free": False,
                "developers": ["Valve"],
                "publishers": ["Valve"],
                "genres": [{"description": "Puzzle"}, {"description": "Action"}],
                "categories": [{"description": "Co-op"}, {"description": "Single-player"}],
                "release_date": {"coming_soon": False, "date": "18 Apr, 2011"},
                "price_overview": {"final": 999, "currency": "EUR"},
                "header_image": "https://img/header.jpg",
                "screenshots": [{"path_full": "https://img/s1.jpg"}],
                "movies": [{"id": 1}],
                "short_description": "Puzzle game",
                "demos": [{"appid": 999, "description": "Demo"}],
            },
        }
    }


def test_parse_appdetails_success():
    data = parse_appdetails(_appdetails_success(), "620")
    assert data is not None
    assert data.name == "Portal 2"
    assert data.type == "game"
    assert data.developers == ["Valve"]
    assert data.genres == ["Puzzle", "Action"]
    assert "Co-op" in data.categories
    assert data.release_date == date(2011, 4, 18)
    assert data.coming_soon is False
    assert data.price == 9.99
    assert data.currency == "EUR"
    assert data.has_trailer is True
    assert data.is_demo is False
    assert data.demo_appids == ["999"]
    assert data.store_url.endswith("/620")


def test_parse_appdetails_free_game():
    payload = _appdetails_success()
    payload["620"]["data"]["is_free"] = True
    payload["620"]["data"].pop("price_overview")
    data = parse_appdetails(payload, "620")
    assert data.is_free is True
    assert data.price == 0.0


def test_parse_appdetails_failure():
    assert parse_appdetails({"620": {"success": False}}, "620") is None
    assert parse_appdetails({}, "620") is None
    assert parse_appdetails({"620": {"success": True}}, "620") is None


def test_parse_release_date_variants():
    assert _parse_date_string("18 Apr, 2011") == date(2011, 4, 18)
    assert _parse_date_string("Apr 18, 2011") == date(2011, 4, 18)
    assert _parse_date_string("Apr 2011") == date(2011, 4, 1)
    assert _parse_date_string("2011") == date(2011, 1, 1)
    assert _parse_date_string("Coming soon") is None


def test_parse_release_date_coming_soon():
    d, coming = parse_release_date({"coming_soon": True, "date": "Q2 2027"})
    assert coming is True


# --- appreviews query_summary --------------------------------------------


def test_parse_query_summary_ok():
    payload = {
        "success": 1,
        "query_summary": {
            "num_reviews": 0,
            "review_score": 9,
            "review_score_desc": "Overwhelmingly Positive",
            "total_positive": 950,
            "total_negative": 50,
            "total_reviews": 1000,
        },
    }
    summary = parse_query_summary(payload)
    assert summary.total_reviews == 1000
    assert summary.total_positive == 950
    assert summary.total_negative == 50
    assert summary.review_score_desc == "Overwhelmingly Positive"


def test_parse_query_summary_fallback_total():
    payload = {
        "success": 1,
        "query_summary": {"total_positive": 30, "total_negative": 10},
    }
    summary = parse_query_summary(payload)
    assert summary.total_reviews == 40


def test_parse_query_summary_failure():
    assert parse_query_summary({"success": 0}) is None
    assert parse_query_summary({"success": 1}) is None


# --- player count ---------------------------------------------------------


def test_parse_player_count_ok():
    assert parse_player_count({"response": {"player_count": 1234, "result": 1}}) == 1234


def test_parse_player_count_bad_result():
    assert parse_player_count({"response": {"result": 42}}) is None
    assert parse_player_count({"response": {}}) is None
    assert parse_player_count({}) is None


# --- SteamSpy -------------------------------------------------------------


def test_parse_steamspy_ok():
    payload = {
        "appid": 620,
        "name": "Portal 2",
        "developer": "Valve",
        "owners": "10,000,000 .. 20,000,000",
        "ccu": 5000,
        "price": "999",
        "positive": 900,
        "negative": 100,
        "tags": {"Puzzle": 500, "Co-op": 300},
    }
    data = parse_steamspy(payload, "620")
    assert data.owners == "10,000,000 .. 20,000,000"
    assert data.owners_estimate == 15_000_000
    assert data.price == 9.99
    assert data.ccu == 5000
    assert set(data.tags) == {"Puzzle", "Co-op"}


def test_midpoint_owners():
    assert _midpoint_owners("20,000 .. 50,000") == 35000
    assert _midpoint_owners("0 .. 20,000") == 10000
    assert _midpoint_owners("1000") == 1000
    assert _midpoint_owners(None) is None


def test_parse_steamspy_error():
    assert parse_steamspy({"error": "not found"}, "1") is None
    assert parse_steamspy({}, "1") is None


# --- discovery ------------------------------------------------------------


def test_parse_explore_new():
    html = """
    <div class="tab_item" data-ds-appid="620">Portal 2</div>
    <a data-ds-appid="440">TF2</a>
    <div data-ds-appid="620">dup</div>
    <div data-ds-appid="1,2,3">bundle</div>
    """
    appids = parse_explore_new(html)
    assert appids == ["620", "440", "1", "2", "3"]


def test_parse_app_list_and_diff():
    payload = {"applist": {"apps": [
        {"appid": 1, "name": "A"},
        {"appid": 2, "name": "B"},
        {"appid": 3, "name": "C"},
    ]}}
    apps = parse_app_list(payload)
    assert apps == {"1": "A", "2": "B", "3": "C"}
    new = diff_new_appids(apps, known={"1", "2"})
    assert new == ["3"]
