"""Test delle metriche di crescita su serie temporali note (funzioni pure)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from analysis import growth

UTC = timezone.utc


def _snap(day: int, reviews=None, players=None):
    base = datetime(2026, 6, 1, tzinfo=UTC)
    return {
        "captured_at": base + timedelta(days=day),
        "total_reviews": reviews,
        "current_players": players,
    }


def test_compute_deltas_known_series():
    snaps = [_snap(0, reviews=100), _snap(1, reviews=160), _snap(2, reviews=200)]
    deltas = growth.compute_deltas(snaps, "total_reviews")
    assert len(deltas) == 2
    assert deltas[0]["delta"] == 60
    assert deltas[0]["rate"] == 0.6
    # 60 recensioni in 24h.
    assert round(deltas[0]["per_hour"], 3) == round(60 / 24, 3)


def test_growth_over_window():
    snaps = [_snap(0, reviews=100), _snap(1, reviews=150), _snap(2, reviews=300)]
    # now = giorno2; finestra 48h -> window_start = giorno0 (base=100).
    now = datetime(2026, 6, 3, tzinfo=UTC)
    w = growth.growth_over_window(snaps, "total_reviews", hours=48, now=now)
    assert w is not None
    assert w["from_value"] == 100
    assert w["to_value"] == 300
    assert w["rate"] == 2.0
    # Finestra piu' stretta (24h) -> base = giorno1 (150).
    w2 = growth.growth_over_window(snaps, "total_reviews", hours=24, now=now)
    assert w2["from_value"] == 150
    assert w2["rate"] == 1.0


def test_compute_growth_metrics_overall_rate():
    snaps = [_snap(0, reviews=100, players=50),
             _snap(7, reviews=400, players=200)]
    m = growth.compute_growth_metrics(snaps)
    assert m["reviews_growth_rate"] == 3.0   # (400-100)/100
    assert m["players_growth_rate"] == 3.0   # (200-50)/50
    assert "reviews_windows" in m and "players_windows" in m


def test_find_turning_points_detects_acceleration():
    # Pendenza piatta poi accelerazione marcata.
    snaps = [
        _snap(0, reviews=100),
        _snap(1, reviews=110),   # +10/giorno
        _snap(2, reviews=120),   # +10/giorno (piatta)
        _snap(3, reviews=400),   # +280/giorno (svolta)
        _snap(4, reviews=700),
    ]
    turns = growth.find_turning_points(snaps, metric="total_reviews", accel_factor=2.0)
    assert turns, "dovrebbe individuare almeno un punto di svolta"
    # La svolta e' attorno al giorno 2->3.
    dates = [t["at"].day for t in turns]
    assert 3 in dates


def test_no_turning_point_on_flat_series():
    snaps = [_snap(i, reviews=100 + i * 5) for i in range(5)]
    turns = growth.find_turning_points(snaps, metric="total_reviews", accel_factor=3.0)
    assert turns == []


def test_follower_growth():
    base = datetime(2026, 6, 1, tzinfo=UTC)
    social = [
        {"captured_at": base, "followers": 1000},
        {"captured_at": base + timedelta(days=7), "followers": 3000},
    ]
    fg = growth.follower_growth(social)
    assert fg["followers_growth_rate"] == 2.0


def test_insufficient_data_returns_none():
    assert growth.growth_over_window([_snap(0, reviews=100)], "total_reviews", 24) is None
    m = growth.compute_growth_metrics([_snap(0, reviews=100)])
    assert m["reviews_growth_rate"] is None
