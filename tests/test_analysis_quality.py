"""Test del quality score: ordinamento buono>medio>trash, soglia discard.

Usa dataset sintetici in un DB SQLite in memoria (nessuna rete).
"""

from __future__ import annotations

import pytest

from analysis import quality_score as qs
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


def test_pure_function_returns_score_and_breakdown():
    """compute_quality_score e' pura e ritorna score + breakdown dettagliato."""
    good = {
        "store": {"has_trailer": True, "screenshot_count": 8,
                  "description_length": 1200, "genres": ["Roguelike"],
                  "tags": ["Pixel"], "header_image": "x"},
        "reviews": {"total_reviews": 1500, "total_positive": 1425},
        "social": {"active_platforms": 2, "mentions_engagement": 4000,
                   "post_count": 30, "follower_trend": 0.9},
        "growth": {"reviews_growth_rate": 2.0},
        "care": {"has_demo": True, "developer_other_games": 3,
                 "price": 14.99, "has_official_site": True},
    }
    score, breakdown = qs.compute_quality_score(good)
    assert 0 <= score <= 100
    assert score > 70
    assert set(breakdown["components"]) == {
        "store_page", "reviews", "social", "growth", "care"}
    assert "weighted" in breakdown and "social_detail" in breakdown
    assert breakdown["weights"] == qs.DEFAULT_WEIGHTS


def test_ordering_good_gt_mid_gt_trash(session):
    """Lo score ordina correttamente buono > medio > trash."""
    good = add_good_game(session)
    mid = add_mid_game(session)
    trash = add_trash_game(session)

    s_good, _ = qs.score_game(session, good.id, persist=True)
    s_mid, _ = qs.score_game(session, mid.id, persist=True)
    s_trash, bd_trash = qs.score_game(session, trash.id, persist=True)

    assert s_good > s_mid > s_trash, (s_good, s_mid, s_trash)
    # Il trash deve avere flag/penalita' attive.
    assert bd_trash["flags"]["hard_trash"] is True
    assert bd_trash["penalty_factor"] < 1.0


def test_discard_threshold_applied(session):
    """Sotto soglia -> discarded=True; sopra -> False."""
    good = add_good_game(session)
    trash = add_trash_game(session)

    qs.score_game(session, good.id, threshold=40.0, persist=True)
    qs.score_game(session, trash.id, threshold=40.0, persist=True)
    session.flush()

    from core.models import Game

    g = session.get(Game, good.id)
    tr = session.get(Game, trash.id)
    assert g.quality_score is not None and g.discarded is False
    assert tr.discarded is True


def test_missing_data_is_neutral_not_zero():
    """Dati social/growth assenti = neutro (0.5), non penalizzano a zero."""
    minimal = {
        "store": {"has_trailer": True, "screenshot_count": 5,
                  "description_length": 700, "genres": ["RPG"],
                  "tags": ["Story"], "header_image": "x"},
        "reviews": {"total_reviews": 200, "total_positive": 180},
        # social / growth / care mancanti del tutto
    }
    score, bd = qs.compute_quality_score(minimal)
    assert bd["components"]["social"] == pytest.approx(0.5, abs=0.2)
    assert bd["components"]["growth"] == 0.5
    assert score > 40


def test_weights_are_configurable():
    """Passare pesi custom cambia il risultato (pesi sovrascrivibili)."""
    data = {
        "store": {"has_trailer": True, "screenshot_count": 5,
                  "description_length": 700, "genres": ["RPG"],
                  "tags": ["X"], "header_image": "x"},
        "reviews": {"total_reviews": 10, "total_positive": 9},
        "social": {"active_platforms": 2, "mentions_engagement": 5000,
                   "post_count": 40, "follower_trend": 0.9},
    }
    # Pesi che privilegiano il social vs pesi che privilegiano le reviews.
    social_heavy = {"store_page": 0.1, "reviews": 0.1, "social": 0.6,
                    "growth": 0.1, "care": 0.1}
    reviews_heavy = {"store_page": 0.1, "reviews": 0.7, "social": 0.1,
                     "growth": 0.05, "care": 0.05}
    s_social, _ = qs.compute_quality_score(data, weights=social_heavy)
    s_reviews, _ = qs.compute_quality_score(data, weights=reviews_heavy)
    # Con poche recensioni ma social forte, il set social-heavy deve premiare di piu'.
    assert s_social > s_reviews
