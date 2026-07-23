"""Test per le nuove sorgenti dati (parsing puro, nessuna rete reale).

Tutte le funzioni di parsing sono pure (no rete, no DB): i test usano
payload JSON fabbricati a mano o mock httpx per le funzioni fetch.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# RAWG
# ---------------------------------------------------------------------------

from core.sources.rawg import (
    parse_game_detail as rawg_parse_detail,
    parse_search_results as rawg_parse_search,
    parse_screenshots as rawg_parse_screenshots,
    RawgGame,
    _parse_date,
    _get_api_key,
    search_games as rawg_search,
    fetch_game_detail as rawg_fetch_detail,
    fetch_screenshots as rawg_fetch_screenshots,
)


def _rawg_detail_payload() -> dict:
    return {
        "id": 3498,
        "name": "Grand Theft Auto V",
        "released": "2013-09-17",
        "rating": 4.47,
        "ratings_count": 6117,
        "metacritic": 97,
        "genres": [{"id": 4, "name": "Action"}, {"id": 3, "name": "Adventure"}],
        "tags": [
            {"id": 31, "name": "Singleplayer", "language": "eng"},
            {"id": 7, "name": "Multiplayer", "language": "eng"},
            {"id": 999, "name": "Mehrspielermodus", "language": "deu"},  # non-eng: skip
        ],
        "platforms": [
            {"platform": {"id": 4, "name": "PC"}},
            {"platform": {"id": 1, "name": "Xbox One"}},
        ],
        "short_screenshots": [
            {"id": 1, "image": "https://media.rawg.io/s1.jpg"},
            {"id": 2, "image": "https://media.rawg.io/s2.jpg"},
        ],
        "description_raw": "An open world action-adventure game.",
        "background_image": "https://media.rawg.io/bg.jpg",
    }


def test_rawg_parse_game_detail():
    data = rawg_parse_detail(_rawg_detail_payload())
    assert data is not None
    assert data.rawg_id == 3498
    assert data.name == "Grand Theft Auto V"
    assert data.released == date(2013, 9, 17)
    assert data.rating == 4.47
    assert data.ratings_count == 6117
    assert data.metacritic == 97
    assert "Action" in data.genres
    assert "Adventure" in data.genres
    # Solo tag in lingua inglese.
    assert "Singleplayer" in data.tags
    assert "Multiplayer" in data.tags
    assert "Mehrspielermodus" not in data.tags
    assert "PC" in data.platforms
    assert len(data.screenshots) == 2
    assert data.description == "An open world action-adventure game."
    assert data.background_image == "https://media.rawg.io/bg.jpg"


def test_rawg_parse_game_detail_missing_id():
    assert rawg_parse_detail({"name": "No ID"}) is None


def test_rawg_parse_game_detail_minimal():
    data = rawg_parse_detail({"id": 1, "name": "Minimal"})
    assert data is not None
    assert data.rawg_id == 1
    assert data.name == "Minimal"
    assert data.released is None
    assert data.metacritic is None
    assert data.genres == []
    assert data.tags == []


def test_rawg_parse_search_results():
    payload = {
        "count": 2,
        "results": [
            {"id": 1, "name": "Game A", "rating": 4.0},
            {"id": 2, "name": "Game B", "released": "2020-01-01"},
        ],
    }
    games = rawg_parse_search(payload)
    assert len(games) == 2
    assert games[0].name == "Game A"
    assert games[1].released == date(2020, 1, 1)


def test_rawg_parse_search_results_empty():
    assert rawg_parse_search({"count": 0, "results": []}) == []


def test_rawg_parse_screenshots():
    payload = {
        "count": 3,
        "results": [
            {"id": 1, "image": "https://media.rawg.io/s1.jpg"},
            {"id": 2, "image": "https://media.rawg.io/s2.jpg"},
            {"id": 3},  # no image: skip
        ],
    }
    urls = rawg_parse_screenshots(payload)
    assert len(urls) == 2
    assert "https://media.rawg.io/s1.jpg" in urls


def test_rawg_parse_date():
    assert _parse_date("2013-09-17") == date(2013, 9, 17)
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("invalid") is None
    # Tronca eventuali timestamp.
    assert _parse_date("2020-06-15T00:00:00") == date(2020, 6, 15)


def test_rawg_search_no_key(monkeypatch):
    """Senza API key, search_games ritorna lista vuota senza sollevare."""
    monkeypatch.delenv("RAWG_API_KEY", raising=False)
    result = rawg_search("Portal")
    assert result == []


def test_rawg_fetch_detail_no_key(monkeypatch):
    """Senza API key, fetch_game_detail ritorna None."""
    monkeypatch.delenv("RAWG_API_KEY", raising=False)
    result = rawg_fetch_detail(3498)
    assert result is None


def test_rawg_fetch_screenshots_no_key(monkeypatch):
    monkeypatch.delenv("RAWG_API_KEY", raising=False)
    result = rawg_fetch_screenshots(3498)
    assert result == []


def test_rawg_search_with_key_mocked(monkeypatch):
    """Con API key, search_games chiama la rete (mockato)."""
    monkeypatch.setenv("RAWG_API_KEY", "testkey")
    mock_payload = {
        "count": 1,
        "results": [{"id": 1, "name": "Portal"}],
    }
    with patch("core.sources.rawg.request_json", return_value=mock_payload):
        result = rawg_search("Portal", page_size=5)
    assert len(result) == 1
    assert result[0].name == "Portal"


def test_rawg_search_network_error(monkeypatch):
    """Errore di rete -> lista vuota, no eccezione."""
    monkeypatch.setenv("RAWG_API_KEY", "testkey")
    with patch("core.sources.rawg.request_json", side_effect=Exception("timeout")):
        result = rawg_search("Portal")
    assert result == []


def test_rawg_fetch_detail_mocked(monkeypatch):
    monkeypatch.setenv("RAWG_API_KEY", "testkey")
    with patch("core.sources.rawg.request_json", return_value=_rawg_detail_payload()):
        result = rawg_fetch_detail(3498)
    assert result is not None
    assert result.metacritic == 97


# ---------------------------------------------------------------------------
# IGDB
# ---------------------------------------------------------------------------

from core.sources.igdb import (
    parse_games as igdb_parse_games,
    _igdb_image_url,
    _get_credentials as igdb_creds,
    search_games as igdb_search,
    fetch_game_detail as igdb_fetch_detail,
    fetch_covers as igdb_fetch_covers,
    _token_cache,
)


def _igdb_game_payload() -> list:
    return [
        {
            "id": 1942,
            "name": "The Witcher 3: Wild Hunt",
            "rating": 92.5,
            "aggregated_rating": 91.8,
            "first_release_date": 1431993600,
            "genres": [{"id": 5, "name": "Role-playing (RPG)"}],
            "themes": [{"id": 1, "name": "Action"}],
            "game_modes": [{"id": 1, "name": "Single player"}],
            "cover": {"id": 1, "image_id": "co1wyy"},
            "hypes": 142,
            "screenshots": [{"image_id": "scabc123"}],
            "videos": [{"video_id": "yt_vid_id"}],
        }
    ]


def test_igdb_parse_games():
    games = igdb_parse_games(_igdb_game_payload())
    assert len(games) == 1
    g = games[0]
    assert g.igdb_id == 1942
    assert g.name == "The Witcher 3: Wild Hunt"
    assert g.rating == 92.5
    assert g.aggregated_rating == 91.8
    assert g.first_release_date == 1431993600
    assert "Role-playing (RPG)" in g.genres
    assert "Action" in g.themes
    assert "Single player" in g.game_modes
    assert "co1wyy" in g.cover_url
    assert g.hypes == 142
    assert len(g.screenshots) == 1
    assert "scabc123" in g.screenshots[0]
    assert g.video_ids == ["yt_vid_id"]


def test_igdb_parse_games_empty():
    assert igdb_parse_games([]) == []


def test_igdb_parse_games_missing_id():
    games = igdb_parse_games([{"name": "No ID"}])
    assert games == []


def test_igdb_parse_games_minimal():
    games = igdb_parse_games([{"id": 1, "name": "Minimal"}])
    assert len(games) == 1
    g = games[0]
    assert g.igdb_id == 1
    assert g.name == "Minimal"
    assert g.genres == []
    assert g.cover_url is None
    assert g.screenshots == []
    assert g.video_ids == []


def test_igdb_image_url():
    url = _igdb_image_url("co1wyy", "cover_big")
    assert "co1wyy" in url
    assert "cover_big" in url
    assert url.startswith("https://images.igdb.com")


def test_igdb_no_credentials(monkeypatch):
    """Senza credenziali, le funzioni fetch ritornano None/vuoto."""
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    # Azzera cache token per forzare il lookup.
    _token_cache.clear()
    result = igdb_search("Witcher")
    assert result == []
    result2 = igdb_fetch_detail(1942)
    assert result2 is None
    result3 = igdb_fetch_covers([1942])
    assert result3 == {}


def test_igdb_search_mocked(monkeypatch):
    """Con credenziali e token mockato, search_games funziona."""
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "csecret")
    _token_cache["token"] = "fake_token"
    _token_cache["expires_at"] = 9999999999.0

    with patch("core.sources.igdb._igdb_post", return_value=_igdb_game_payload()):
        result = igdb_search("Witcher")
    assert len(result) == 1
    assert result[0].name == "The Witcher 3: Wild Hunt"


def test_igdb_fetch_detail_mocked(monkeypatch):
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "csecret")
    _token_cache["token"] = "fake_token"
    _token_cache["expires_at"] = 9999999999.0

    with patch("core.sources.igdb._igdb_post", return_value=_igdb_game_payload()):
        result = igdb_fetch_detail(1942)
    assert result is not None
    assert result.igdb_id == 1942


def test_igdb_fetch_covers_mocked(monkeypatch):
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "csecret")
    _token_cache["token"] = "fake_token"
    _token_cache["expires_at"] = 9999999999.0

    cover_payload = [{"game": 1942, "image_id": "co1wyy"}]
    with patch("core.sources.igdb._igdb_post", return_value=cover_payload):
        result = igdb_fetch_covers([1942])
    assert 1942 in result
    assert "co1wyy" in result[1942]


# ---------------------------------------------------------------------------
# HowLongToBeat
# ---------------------------------------------------------------------------

from core.sources.howlongtobeat import (
    parse_search_result as hltb_parse,
    _secs_to_hours,
    search_game as hltb_search,
)


def _hltb_payload() -> dict:
    return {
        "data": [
            {
                "game_id": 10270,
                "game_name": "Portal 2",
                "comp_main": 28800,    # 8h in secondi
                "comp_plus": 43200,    # 12h in secondi
                "comp_100": 79200,     # 22h in secondi
                "review_score": 97,
            }
        ]
    }


def test_hltb_secs_to_hours():
    assert _secs_to_hours(3600) == 1.0
    assert _secs_to_hours(7200) == 2.0
    assert _secs_to_hours(0) is None
    assert _secs_to_hours(None) is None
    assert _secs_to_hours(-100) is None
    # Valori gia' in ore (< 3600).
    assert _secs_to_hours(8.5) == 8.5


def test_hltb_parse_search_result():
    result = hltb_parse(_hltb_payload())
    assert result is not None
    assert result.title == "Portal 2"
    assert result.hltb_id == 10270
    assert result.main_story == 8.0
    assert result.main_extra == 12.0
    assert result.completionist == 22.0
    assert result.review_score == 97


def test_hltb_parse_empty():
    assert hltb_parse({"data": []}) is None


def test_hltb_parse_missing_data():
    assert hltb_parse({}) is None


def test_hltb_parse_no_name():
    payload = {"data": [{"game_id": 1, "comp_main": 3600}]}
    # game_name mancante -> None
    assert hltb_parse(payload) is None


def test_hltb_parse_alternative_path():
    """Payload con path alternativo pageProps.games.data."""
    payload = {
        "pageProps": {
            "games": {
                "data": [{"game_id": 1, "game_name": "Celeste", "comp_main": 14400}]
            }
        }
    }
    result = hltb_parse(payload)
    assert result is not None
    assert result.title == "Celeste"
    assert result.main_story == 4.0


def test_hltb_search_empty_title():
    result = hltb_search("")
    assert result is None


def test_hltb_search_mocked():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _hltb_payload()
    mock_resp.raise_for_status = MagicMock()

    with patch("core.sources.howlongtobeat.build_client") as mock_build:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_build.return_value = mock_client

        result = hltb_search("Portal 2", http_client=mock_client)

    assert result is not None
    assert result.title == "Portal 2"


def test_hltb_search_network_error():
    with patch("core.sources.howlongtobeat.build_client") as mock_build:
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("network error")
        mock_build.return_value = mock_client

        result = hltb_search("Portal 2", http_client=mock_client)

    assert result is None


# ---------------------------------------------------------------------------
# OpenCritic
# ---------------------------------------------------------------------------

from core.sources.opencritic import (
    parse_search_results as oc_parse_search,
    parse_game_detail as oc_parse_detail,
    search_game as oc_search,
    fetch_game_detail as oc_fetch_detail,
    OC_DIRECT_URL,
)


def _oc_detail_payload() -> dict:
    return {
        "id": 10667,
        "name": "Elden Ring",
        "topCriticScore": 96.0,
        "percentRecommended": 98.0,
        "tier": "Mighty",
        "numReviews": 174,
        "numTopCriticReviews": 88,
        "Platforms": [{"id": 1, "name": "PC"}, {"id": 2, "name": "PS5"}],
        "Genres": [{"id": 1, "name": "RPG"}, {"id": 2, "name": "Action"}],
    }


def test_oc_parse_search_results():
    payload = [
        {"id": 10667, "name": "Elden Ring", "topCriticScore": 96.0},
        {"id": 99999, "name": "Upcoming Game", "topCriticScore": -1},  # non ancora uscito
    ]
    results = oc_parse_search(payload)
    assert len(results) == 2
    er = results[0]
    assert er.oc_id == 10667
    assert er.name == "Elden Ring"
    assert er.top_critic_score == 96.0
    # Score -1 -> None.
    assert results[1].top_critic_score is None


def test_oc_parse_search_results_empty():
    assert oc_parse_search([]) == []


def test_oc_parse_search_missing_id():
    results = oc_parse_search([{"name": "No ID"}])
    assert results == []


def test_oc_parse_game_detail():
    data = oc_parse_detail(_oc_detail_payload())
    assert data is not None
    assert data.oc_id == 10667
    assert data.name == "Elden Ring"
    assert data.top_critic_score == 96.0
    assert data.percent_recommended == 98.0
    assert data.tier == "Mighty"
    assert data.num_reviews == 174
    assert data.num_top_critic_reviews == 88
    assert "PC" in data.platforms
    assert "RPG" in data.genres


def test_oc_parse_game_detail_missing_id():
    assert oc_parse_detail({"name": "No ID"}) is None


def test_oc_parse_game_detail_negative_score():
    payload = {"id": 1, "name": "Unreleased", "topCriticScore": -1}
    data = oc_parse_detail(payload)
    assert data is not None
    assert data.top_critic_score is None


def test_oc_search_mocked(monkeypatch):
    """Ricerca OpenCritic con HTTP mockato (endpoint diretto)."""
    monkeypatch.delenv("OPENCRITIC_USE_RAPIDAPI", raising=False)
    payload = [{"id": 10667, "name": "Elden Ring", "topCriticScore": 96.0}]
    with patch("core.sources.opencritic.request_json", return_value=payload):
        results = oc_search("Elden Ring")
    assert len(results) == 1
    assert results[0].oc_id == 10667


def test_oc_search_network_error(monkeypatch):
    """Errore di rete -> lista vuota, no eccezione."""
    monkeypatch.delenv("OPENCRITIC_USE_RAPIDAPI", raising=False)
    with patch("core.sources.opencritic.request_json", side_effect=Exception("timeout")):
        results = oc_search("Elden Ring")
    assert results == []


def test_oc_fetch_detail_mocked(monkeypatch):
    monkeypatch.delenv("OPENCRITIC_USE_RAPIDAPI", raising=False)
    with patch("core.sources.opencritic.request_json", return_value=_oc_detail_payload()):
        result = oc_fetch_detail(10667)
    assert result is not None
    assert result.tier == "Mighty"


def test_oc_fetch_detail_rapidapi_no_key(monkeypatch):
    """RapidAPI abilitata ma senza key -> None."""
    monkeypatch.setenv("OPENCRITIC_USE_RAPIDAPI", "1")
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    result = oc_fetch_detail(10667)
    assert result is None


def test_oc_search_rapidapi_no_key(monkeypatch):
    monkeypatch.setenv("OPENCRITIC_USE_RAPIDAPI", "1")
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    results = oc_search("Elden Ring")
    assert results == []
