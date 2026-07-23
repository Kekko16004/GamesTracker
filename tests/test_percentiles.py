"""Test del confronto a percentili (Livello B, puro)."""

from __future__ import annotations

from analysis import percentiles as pc


def test_quantile_median_odd():
    assert pc.quantile(list(range(1, 10)), 0.5) == 5.0


def test_quantile_empty_is_zero():
    assert pc.quantile([], 0.5) == 0.0


def test_quantile_single_value():
    assert pc.quantile([7.0], 0.9) == 7.0


def test_percentile_of_empty_is_neutral():
    assert pc.percentile_of(5.0, []) == 50.0


def test_percentile_monotonic():
    dist = list(range(0, 100))
    low = pc.percentile_of(10, dist)
    high = pc.percentile_of(90, dist)
    assert low < high


def test_position_below_median():
    dist = pc.synthetic_distribution(12, n=25)
    r = pc.position(4, dist, estimated=True)
    assert r.below_median
    assert not r.is_top
    assert r.estimated
    assert r.sample_size == 25


def test_position_top_quartile():
    dist = pc.synthetic_distribution(10, n=25)
    r = pc.position(20, dist)
    assert r.is_top
    assert r.percentile >= 75.0


def test_synthetic_distribution_shape():
    d = pc.synthetic_distribution(10, spread=0.5, n=11)
    assert len(d) == 11
    assert d[0] < d[-1]
    # centro ~ mediana
    assert abs(d[len(d) // 2] - 10) < 1e-6


def test_synthetic_distribution_degenerate():
    assert pc.synthetic_distribution(0, n=10) == []
    assert pc.synthetic_distribution(10, n=0) == []
    assert pc.synthetic_distribution(10, n=1) == [10]
