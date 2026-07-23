"""Test della logica pura del simulatore di quality score (no PyQt6)."""

from __future__ import annotations

from gui.simulator_logic import (
    SimulatorInputs,
    build_game_data_from_inputs,
    simulate_score,
)


def test_well_made_game_scores_high():
    """Pagina ricca + buone recensioni -> score alto, nessuna penalità store."""
    inp = SimulatorInputs(
        title="Bel Gioco",
        description="Una descrizione lunga e curata " * 30,  # >600 char
        screenshot_count=8,
        has_trailer=True,
        has_header=True,
        genres=["Roguelike", "Action"],
        tags=["Pixel Graphics", "Great Soundtrack", "Difficult"],
        price=14.99,
        has_demo=True,
        developer_other_games=True,
        has_official_site=True,
        review_pct_positive=92.0,
        review_count=3000,
        social_platforms=2,
        social_post_count=40,
    )
    score, breakdown = simulate_score(inp)
    assert score >= 70.0
    assert "no_screenshots_and_no_trailer" not in breakdown["penalties"]


def test_empty_game_scores_low_with_penalties():
    """Pagina vuota + gratis + zero recensioni -> score basso con penalità."""
    inp = SimulatorInputs(
        title="Vuoto",
        description="",          # placeholder
        screenshot_count=0,
        has_trailer=False,
        has_header=False,
        genres=[],
        tags=[],
        price=0.0,
        is_free=True,
        review_count=0,
    )
    score, breakdown = simulate_score(inp)
    assert score < 40.0
    assert "no_screenshots_and_no_trailer" in breakdown["penalties"]


def test_zero_counts_become_neutral_none():
    """I conteggi lasciati a 0 diventano None (neutri), non 0 penalizzanti."""
    inp = SimulatorInputs(review_count=0, social_platforms=0, social_post_count=0)
    data = build_game_data_from_inputs(inp)
    assert data["reviews"]["total_reviews"] is None
    assert data["social"]["active_platforms"] is None
    assert data["social"]["post_count"] is None
    # store sempre "inspected" nel simulatore.
    assert data["store"]["store_inspected"] is True


def test_review_split_computed_from_percentage():
    inp = SimulatorInputs(review_count=1000, review_pct_positive=90.0)
    data = build_game_data_from_inputs(inp)
    assert data["reviews"]["total_reviews"] == 1000
    assert data["reviews"]["total_positive"] == 900
    assert data["reviews"]["total_negative"] == 100


def test_breakdown_has_expected_shape():
    score, breakdown = simulate_score(SimulatorInputs(screenshot_count=5, has_trailer=True))
    assert 0.0 <= score <= 100.0
    for key in ("components", "weighted", "penalties", "penalty_factor", "flags"):
        assert key in breakdown
