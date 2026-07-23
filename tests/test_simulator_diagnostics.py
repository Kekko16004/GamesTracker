"""Test della diagnostica del simulatore (controfattuali, puri)."""

from __future__ import annotations

from gui.simulator_diagnostics import diagnose
from gui.simulator_logic import SimulatorInputs


def _weak_page() -> SimulatorInputs:
    """Pagina povera ma non trash totale (per avere suggerimenti utili)."""
    return SimulatorInputs(
        title="Gioco",
        description="Breve descrizione del gioco appena sufficiente qui.",
        screenshot_count=2,
        has_trailer=False,
        has_header=False,
        genres=["Roguelike"],
        tags=["Pixel Graphics"],
        price=9.99,
        review_count=0,
    )


def test_diagnose_suggests_trailer_first_or_high():
    diag = diagnose(_weak_page())
    codes = [s.code for s in diag.suggestions]
    assert "simulator.diag.add_trailer" in codes
    # I delta sono ordinati decrescenti.
    deltas = [s.delta for s in diag.suggestions]
    assert deltas == sorted(deltas, reverse=True)


def test_all_deltas_non_negative_and_measured():
    diag = diagnose(_weak_page())
    assert diag.suggestions  # ci sono suggerimenti
    for s in diag.suggestions:
        assert s.delta >= 0.0


def test_expected_score_present_when_no_reviews():
    diag = diagnose(_weak_page())
    assert diag.expected_estimated is True
    assert diag.expected_score is not None
    # Con recensioni immaginate lo score atteso è >= dello score reale
    # (le recensioni tipiche del genere aggiungono segnale positivo).
    assert diag.expected_score >= diag.score - 0.01


def test_no_expected_score_when_reviews_given():
    inp = _weak_page()
    inp.review_count = 500
    inp.review_pct_positive = 90.0
    diag = diagnose(inp)
    assert diag.expected_score is None
    assert diag.expected_estimated is False


def test_strong_page_has_strengths_and_high_rating():
    inp = SimulatorInputs(
        title="Ottimo",
        description="Descrizione molto lunga e curata. " * 30,
        screenshot_count=14,
        has_trailer=True,
        has_header=True,
        genres=["Roguelike"],
        tags=["Pixel Graphics", "Difficult", "Great Soundtrack"],
        price=14.99,
        has_demo=True,
        developer_other_games=True,
        has_official_site=True,
        review_count=3000,
        review_pct_positive=93.0,
        social_platforms=2,
        social_post_count=40,
    )
    diag = diagnose(inp)
    assert "simulator.strength.trailer" in diag.strengths
    assert diag.rating_code in (
        "simulator.rating.excellent", "simulator.rating.good")


def test_rating_codes_cover_range():
    from gui.simulator_diagnostics import _rating_code
    assert _rating_code(85) == "simulator.rating.excellent"
    assert _rating_code(70) == "simulator.rating.good"
    assert _rating_code(55) == "simulator.rating.fair"
    assert _rating_code(42) == "simulator.rating.weak"
    assert _rating_code(10) == "simulator.rating.trash"
