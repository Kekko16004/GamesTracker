"""Test del job di scoring del collector (`collector/jobs/scoring.py`).

Verifica che ``score_and_report`` popoli ``games.quality_score`` e crei una
riga in ``analysis_reports``, riusando la sessione passata. Nessuna rete.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from core.models import AnalysisReport, Game, GameSnapshot, Platform, SnapshotType
from collector.jobs.scoring import score_and_report
from tests.conftest_analysis import make_memory_session

UTC = timezone.utc


def _make_game_with_snapshot(session) -> Game:
    game = Game(
        platform=Platform.STEAM,
        external_id="score-1",
        title="Scoring Test Game",
        developer="Test Studio",
        genres=["Action", "Indie"],
        tags=["Great Soundtrack"],
        release_date=date(2026, 7, 1),
        price=9.99,
        is_free=False,
        header_image="https://img/header.jpg",
    )
    session.add(game)
    session.flush()
    snap = GameSnapshot(
        game_id=game.id,
        snapshot_type=SnapshotType.DISCOVERY,
        captured_at=datetime(2026, 7, 2, tzinfo=UTC),
        total_reviews=500,
        total_positive=450,
        total_negative=50,
        review_score_desc="Very Positive",
        current_players=1200,
        extra={
            "has_trailer": True,
            "screenshot_count": 6,
            "description_length": 240,
            "placeholder_description": False,
        },
    )
    session.add(snap)
    session.flush()
    return game


def test_score_and_report_populates_score_and_report():
    session, _engine = make_memory_session()
    try:
        game = _make_game_with_snapshot(session)
        assert game.quality_score is None

        score_and_report(session, game.id, lang="it")

        refreshed = session.get(Game, game.id)
        assert refreshed.quality_score is not None
        assert 0.0 <= refreshed.quality_score <= 100.0

        reports = session.query(AnalysisReport).filter(
            AnalysisReport.game_id == game.id
        ).all()
        assert len(reports) == 1
        assert reports[0].summary  # non vuoto
    finally:
        session.close()


def test_score_and_report_does_not_raise_on_missing_game():
    session, _engine = make_memory_session()
    try:
        # game_id inesistente: non deve sollevare (logga e continua).
        score_and_report(session, 99999, lang="it")
    finally:
        session.close()
