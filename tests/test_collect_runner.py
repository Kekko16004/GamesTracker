"""Test del ciclo di raccolta one-shot e del wiring GUI del bottone.

Tre livelli, tutti senza rete:

1. ``parse_progress_line`` (puro, no Qt) — parsing del contratto @@PROGRESS@@.
2. ``run_once`` (collector) — emette gli eventi attesi nell'ordine giusto,
   con ``emit`` iniettato e le fasi mockate (nessun accesso reale a rete/DB
   oltre a ``init_db`` su SQLite in memoria).
3. ``DashboardView`` (offscreen) — smoke test del wiring: i widget di
   raccolta esistono e gli slot reagiscono agli eventi senza sollevare.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest

from gui.collect_runner import PROGRESS_MARKER, parse_progress_line


# --- 1. parse_progress_line (puro) ---------------------------------------

def test_parse_valid_progress_line():
    payload = {
        "phase": "snapshots",
        "status": "progress",
        "current": 3,
        "total": 10,
        "message": "3/10",
    }
    line = PROGRESS_MARKER + json.dumps(payload)
    event = parse_progress_line(line)
    assert event is not None
    assert event["phase"] == "snapshots"
    assert event["status"] == "progress"
    assert event["current"] == 3
    assert event["total"] == 10
    assert event["message"] == "3/10"


def test_parse_fills_defaults_for_missing_keys():
    line = PROGRESS_MARKER + json.dumps({"phase": "discovery"})
    event = parse_progress_line(line)
    assert event is not None
    assert event["phase"] == "discovery"
    # Le chiavi mancanti prendono i default.
    assert event["status"] == ""
    assert event["current"] == 0
    assert event["total"] is None
    assert event["message"] == ""


def test_parse_normal_log_line_returns_none():
    assert parse_progress_line("2026-07-22 [INFO] collector: avviato") is None


def test_parse_marker_without_json_returns_none():
    assert parse_progress_line(PROGRESS_MARKER) is None
    assert parse_progress_line(PROGRESS_MARKER + "   ") is None


def test_parse_malformed_json_returns_none():
    assert parse_progress_line(PROGRESS_MARKER + "{not valid json") is None


def test_parse_json_array_returns_none():
    # JSON valido ma non un dict.
    assert parse_progress_line(PROGRESS_MARKER + "[1, 2, 3]") is None


def test_parse_none_and_empty_return_none():
    assert parse_progress_line(None) is None  # type: ignore[arg-type]
    assert parse_progress_line("") is None


def test_parse_line_with_leading_whitespace():
    line = "   " + PROGRESS_MARKER + json.dumps({"phase": "social"})
    event = parse_progress_line(line)
    assert event is not None
    assert event["phase"] == "social"


# --- 2. run_once (collector) ---------------------------------------------

def test_run_once_emits_ordered_events(monkeypatch):
    """run_once emette start/end per ogni fase e chiude con 'done'."""
    import collector.run_once as ro

    # Nessun accesso reale a rete/DB: mock delle tre fasi + init_db.
    monkeypatch.setattr(ro, "init_db", lambda: None)
    monkeypatch.setattr(
        ro, "_run_discovery_phase",
        lambda emit: emit("discovery", "end", 2, None, "2 nuovi giochi"),
    )
    monkeypatch.setattr(
        ro, "_run_snapshots_phase",
        lambda emit: emit("snapshots", "end", 5, 5, "Snapshot completati"),
    )
    monkeypatch.setattr(
        ro, "_run_social_phase",
        lambda emit: emit("social", "end", 7, None, "7 post salvati"),
    )

    events = []
    ro.run_once(include_social=True, emit=lambda *a: events.append(a))

    phases = [(e[0], e[1]) for e in events]
    assert ("discovery", "end") in phases
    assert ("snapshots", "end") in phases
    assert ("social", "end") in phases
    # L'ultimo evento e' sempre done.
    assert events[-1][0] == "all"
    assert events[-1][1] == "done"


def test_run_once_no_social_skips_social_phase(monkeypatch):
    import collector.run_once as ro

    monkeypatch.setattr(ro, "init_db", lambda: None)
    monkeypatch.setattr(ro, "_run_discovery_phase", lambda emit: None)
    monkeypatch.setattr(ro, "_run_snapshots_phase", lambda emit: None)

    called = {"social": False}

    def _social(emit):
        called["social"] = True

    monkeypatch.setattr(ro, "_run_social_phase", _social)

    events = []
    ro.run_once(include_social=False, emit=lambda *a: events.append(a))

    assert called["social"] is False
    assert events[-1][:2] == ("all", "done")


def test_emit_progress_writes_marker_line(capsys):
    import collector.run_once as ro

    ro.emit_progress("snapshots", "progress", current=1, total=4, message="1/4")
    out = capsys.readouterr().out.strip()
    assert out.startswith(PROGRESS_MARKER)
    # La riga emessa e' riparsabile dal lato GUI.
    event = parse_progress_line(out)
    assert event is not None
    assert event["phase"] == "snapshots"
    assert event["current"] == 1
    assert event["total"] == 4


# --- 3. DashboardView (offscreen) ----------------------------------------

pytest.importorskip("PyQt6", reason="PyQt6 non disponibile nell'ambiente")
pytest.importorskip("pyqtgraph", reason="pyqtgraph non disponibile")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base
from gui.data_access import GameRepository


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolate_translator():
    """Evita che le viste create qui lascino osservatori nel translator globale.

    ``DashboardView`` si iscrive al translator singleton e non si disiscrive:
    senza questo ripristino, un successivo cambio lingua in un altro test
    notificherebbe widget Qt gia' distrutti (RuntimeError). Salva e ripristina
    lista osservatori e lingua attorno a ogni test di questo modulo.
    """
    from gui.i18n import translator

    saved_observers = list(translator._observers)
    saved_lang = translator.language
    yield
    translator._observers[:] = saved_observers
    translator.set_language(saved_lang)


@pytest.fixture()
def empty_repo():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return GameRepository(Session)


def test_dashboard_has_collect_widgets(qapp, empty_repo):
    from gui.views.dashboard import DashboardView

    view = DashboardView(empty_repo)
    # I widget di raccolta esistono e la barra parte nascosta.
    assert view._collect_button is not None
    assert view._collect_bar.isVisible() is False
    assert view._collect_button.text()  # tradotto, non vuoto


def test_dashboard_progress_slots_do_not_raise(qapp, empty_repo):
    from gui.views.dashboard import DashboardView

    view = DashboardView(empty_repo)

    # Fase a totale sconosciuto -> barra indeterminata (range 0,0).
    view._on_collect_progress("discovery", "start", 0, -1, "")
    assert view._collect_bar.minimum() == 0
    assert view._collect_bar.maximum() == 0

    # Fase con totale noto -> barra determinata.
    view._on_collect_progress("snapshots", "progress", 3, 10, "3/10")
    assert view._collect_bar.maximum() == 10
    assert view._collect_bar.value() == 3

    # Fine e fallimento non sollevano e ripristinano il bottone.
    view._on_collect_finished(True)
    assert view._collect_button.isEnabled() is True
    view._on_collect_failed("boom")
    assert view._collect_button.isEnabled() is True
    assert "boom" in view._collect_status.text()
