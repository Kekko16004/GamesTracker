"""Test delle aggregazioni di trend per genere (pandas)."""

from __future__ import annotations

import pytest

from analysis import trends
from tests.conftest_analysis import (
    add_good_game,
    add_mid_game,
    add_trash_game,
    make_memory_session,
)


@pytest.fixture()
def session():
    sess, engine = make_memory_session()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _records():
    return [
        {"game_id": 1, "title": "A", "genres": ["Roguelike"], "tags": ["Pixel"],
         "quality_score": 80.0, "discarded": False,
         "reviews_growth_rate": 2.0, "players_growth_rate": 1.5,
         "days_demo_to_release": 60, "days_release_to_peak": 3},
        {"game_id": 2, "title": "B", "genres": ["Roguelike"], "tags": [],
         "quality_score": 60.0, "discarded": False,
         "reviews_growth_rate": 1.0, "players_growth_rate": 0.5,
         "days_demo_to_release": 40, "days_release_to_peak": 5},
        {"game_id": 3, "title": "C", "genres": ["Platformer"], "tags": [],
         "quality_score": 30.0, "discarded": True,
         "reviews_growth_rate": 0.1, "players_growth_rate": 0.0,
         "days_demo_to_release": None, "days_release_to_peak": 10},
    ]


def test_growth_by_genre_orders_and_averages():
    df = trends.build_games_frame(_records())
    rows = trends.growth_by_genre(df, include_discarded=False)
    # Solo generi non scartati: Roguelike (2 giochi). Platformer e' discarded.
    genres = {r["genre"]: r for r in rows}
    assert "Roguelike" in genres
    assert genres["Roguelike"]["n_games"] == 2
    # media reviews growth Roguelike = (2.0 + 1.0)/2 = 1.5
    assert genres["Roguelike"]["avg_reviews_growth"] == pytest.approx(1.5)
    # Ordinamento: crescita decrescente, Roguelike primo.
    assert rows[0]["genre"] == "Roguelike"


def test_growth_by_genre_include_discarded():
    df = trends.build_games_frame(_records())
    rows = trends.growth_by_genre(df, include_discarded=True)
    genres = {r["genre"] for r in rows}
    assert "Platformer" in genres


def test_timing_stats_median():
    df = trends.build_games_frame(_records())
    stats = trends.timing_stats(df)
    assert stats["demo_to_release"]["n"] == 2
    assert stats["demo_to_release"]["median"] == 50.0  # median(60,40)
    assert stats["release_to_peak"]["n"] == 3


def test_quality_distribution():
    df = trends.build_games_frame(_records())
    dist = trends.quality_distribution(df, bins=10)
    assert dist["n"] == 3
    assert sum(dist["counts"]) == 3
    assert len(dist["bins"]) == 11


def test_empty_frame_is_safe():
    df = trends.build_games_frame([])
    assert trends.growth_by_genre(df) == []
    assert trends.timing_by_genre(df) == []
    assert trends.quality_distribution(df)["n"] == 0


def test_collect_trend_input_from_db(session):
    add_good_game(session)
    add_mid_game(session)
    add_trash_game(session)
    records = trends.collect_trend_input(session)
    assert len(records) == 3
    df = trends.build_games_frame(records)
    rows = trends.growth_by_genre(df, include_discarded=True)
    # Deve esserci almeno il genere Roguelike dal gioco buono.
    assert any(r["genre"] == "Roguelike" for r in rows)
