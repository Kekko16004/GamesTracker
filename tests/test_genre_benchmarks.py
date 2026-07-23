"""Test del modulo benchmark per genere (stime euristiche, pure)."""

from __future__ import annotations

from analysis import genre_benchmarks as gb


def test_known_genre_matched():
    bm, keys = gb.lookup(genres=["Roguelike"], tags=[])
    assert "roguelike" in keys
    assert bm.median_review_count > 0
    assert 0 < bm.pct_positive <= 100


def test_alias_resolved():
    bm, keys = gb.lookup(genres=["Rogue-like"], tags=[])
    assert "roguelike" in keys


def test_partial_match_in_tag():
    # "Action Roguelike" deve risolvere a roguelike via match parziale.
    _bm, keys = gb.lookup(genres=[], tags=["Action Roguelike"])
    assert "roguelike" in keys


def test_unknown_genre_falls_back_to_default():
    bm, keys = gb.lookup(genres=["Zzzunknown"], tags=[])
    assert keys == []
    assert bm is gb.DEFAULT_BENCHMARK


def test_multiple_genres_are_averaged():
    bm, keys = gb.lookup(genres=["Puzzle", "Roguelike"], tags=[])
    assert set(keys) == {"puzzle", "roguelike"}
    puzzle = gb.GENRE_BENCHMARKS["puzzle"]
    rogue = gb.GENRE_BENCHMARKS["roguelike"]
    expected = round((puzzle.median_review_count + rogue.median_review_count) / 2)
    assert bm.median_review_count == expected


def test_estimate_reviews_shape_and_consistency():
    est = gb.estimate_reviews(genres=["Cozy"], tags=[])
    assert est["estimated"] is True
    assert est["total_reviews"] > 0
    assert est["total_positive"] + est["total_negative"] == est["total_reviews"]
    # positive coerente con pct_positive.
    assert est["total_positive"] <= est["total_reviews"]
    assert "cozy" in est["matched"]


def test_estimate_reviews_unknown_uses_default():
    est = gb.estimate_reviews(genres=[], tags=[])
    assert est["total_reviews"] == gb.DEFAULT_BENCHMARK.median_review_count
    assert est["matched"] == []
