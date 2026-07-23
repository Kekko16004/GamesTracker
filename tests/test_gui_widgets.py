"""Smoke test dei widget/viste GUI in modalita' offscreen.

Richiede PyQt6: se non e' installabile nell'ambiente i test vengono
saltati (skip), cosi' la suite del data_access resta comunque verde.
Imposta ``QT_QPA_PLATFORM=offscreen`` per non aprire finestre reali.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 non disponibile nell'ambiente")
pytest.importorskip("pyqtgraph", reason="pyqtgraph non disponibile")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import (
    Base,
    Game,
    GameSnapshot,
    Platform,
    SnapshotType,
)
from gui.data_access import GameRepository


@pytest.fixture(scope="module")
def qapp():
    """Istanza unica di QApplication per il modulo (offscreen)."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def repo():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session() as s:
        g = Game(
            platform=Platform.STEAM,
            external_id="1",
            title="Test Game",
            genres=["Action"],
            release_date=date.today(),
            quality_score=70.0,
        )
        s.add(g)
        s.flush()
        s.add(
            GameSnapshot(
                game_id=g.id,
                captured_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                snapshot_type=SnapshotType.DISCOVERY,
                total_reviews=100,
            )
        )
        s.commit()
    return GameRepository(Session)


def test_quality_slider(qapp):
    from gui.widgets.quality_slider import QualityThresholdSlider

    slider = QualityThresholdSlider(initial=30)
    assert slider.value() == 30
    slider.set_value(75)
    assert slider.value() == 75


def test_language_switch_retranslates(qapp):
    from gui.i18n import translator
    from gui.widgets.quality_slider import QualityThresholdSlider

    translator.set_language("it")
    slider = QualityThresholdSlider()
    translator.set_language("en")
    # Nessuna eccezione: il widget si ri-traduce via observer.
    slider.retranslate()
    translator.set_language("it")


def test_dashboard_builds(qapp, repo):
    from gui.views.dashboard import DashboardView

    view = DashboardView(repo)
    qapp.processEvents()
    assert view is not None


def test_main_window_builds(qapp, repo):
    from gui.app import MainWindow

    window = MainWindow(repo)
    qapp.processEvents()
    # Le viste nello stack: dashboard, trends, reports, simulator, detail.
    assert window._stack.count() == 5


def test_empty_db_no_crash(qapp):
    from gui.views.dashboard import DashboardView

    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    view = DashboardView(GameRepository(Session))
    qapp.processEvents()
    assert view is not None
