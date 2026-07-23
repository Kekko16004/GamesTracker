"""Test della generazione report per-gioco e per-genere (IT/EN)."""

from __future__ import annotations

import json

import pytest

from analysis import reports
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


@pytest.mark.parametrize("lang", ["it", "en"])
def test_game_report_summary_and_data(session, lang):
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang=lang, persist=True)

    # Summary non vuoto e nella lingua giusta (marker di sezione).
    assert report["summary"].strip()
    if lang == "it":
        assert "Panoramica" in report["summary"]
        assert "CO-OCCORRENZE" in report["summary"]  # disclaimer causalita'
    else:
        assert "Overview" in report["summary"]
        assert "CO-OCCURRENCES" in report["summary"]

    # data json-serializzabile.
    data = report["data"]
    json.dumps(data)  # non deve sollevare
    assert data["kind"] == "game"
    assert "reviews_timeseries" in data["charts"]
    assert "posts_by_platform" in data["charts"]
    assert "top_posts_engagement" in data["charts"]
    # Report salvato.
    assert "report_id" in report


def test_game_report_disclaimers_always_present(session):
    """I disclaimer proxy + correlazione ci sono anche per un gioco trash."""
    game = add_trash_game(session)
    report = reports.generate_game_report(session, game.id, lang="it", persist=False)
    assert "SteamSpy" in report["summary"]
    assert "CO-OCCORRENZE" in report["summary"]


def test_game_report_timeline_has_demo_and_release(session):
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang="it", persist=False)
    events = report["data"]["events"]
    kinds = {e["kind"] for e in events}
    assert "demo" in kinds
    assert "release" in kinds
    assert "post" in kinds


@pytest.mark.parametrize("lang", ["it", "en"])
def test_genre_report(session, lang):
    add_good_game(session)   # Roguelike
    add_mid_game(session)
    report = reports.generate_genre_report(session, "Roguelike", lang=lang, persist=True)
    assert report["summary"].strip()
    json.dumps(report["data"])
    assert report["data"]["kind"] == "genre"
    assert report["data"]["genre"] == "Roguelike"
    assert "report_id" in report


def test_genre_report_small_sample_warning(session):
    add_good_game(session)  # 1 solo gioco Roguelike
    report = reports.generate_genre_report(session, "Roguelike", lang="it", persist=False)
    # N<5 -> avviso campione piccolo.
    assert "ATTENZIONE" in report["summary"] or "campione piccolo" in report["summary"]


def test_report_persisted_in_db(session):
    game = add_good_game(session)
    reports.generate_game_report(session, game.id, lang="it", persist=True)
    session.flush()

    from sqlalchemy import select

    from core.models import AnalysisReport, Lang

    row = session.scalar(select(AnalysisReport).where(AnalysisReport.game_id == game.id))
    assert row is not None
    assert row.lang == Lang.IT
    assert row.summary
    assert isinstance(row.data, dict)


def test_export_html(session):
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang="en", persist=False)
    html = reports.export_html(report)
    assert "<html>" in html and "</html>" in html
    assert "<h2>" in html  # sezioni renderizzate


def test_export_pdf_hook_returns_none_or_path(session, tmp_path):
    """L'hook PDF non deve sollevare: torna path o None se manca la lib."""
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang="it", persist=False)
    out = reports.export_pdf(report, str(tmp_path / "r.pdf"))
    assert out is None or out.endswith(".pdf")


# --- Analisi pre-lancio (hype pre-esistente vs crescita da lancio) ---

from datetime import date, datetime, timezone


def test_prelaunch_detects_preexisting_hype():
    """Early access + molti post pre-release -> hype pre-esistente."""
    game = {
        "release_date": date(2026, 7, 9),
        "demo_release_date": date(2026, 1, 1),
        "tags": ["Early Access"],
        "genres": ["Action"],
        "first_seen_at": datetime(2026, 1, 5, tzinfo=timezone.utc),
    }
    posts = [
        {"posted_at": datetime(2026, 3, 1, tzinfo=timezone.utc), "platform": "youtube"},
        {"posted_at": datetime(2026, 4, 1, tzinfo=timezone.utc), "platform": "youtube"},
        {"posted_at": datetime(2026, 5, 1, tzinfo=timezone.utc), "platform": "youtube"},
        {"posted_at": datetime(2026, 7, 12, tzinfo=timezone.utc), "platform": "youtube"},
    ]
    res = reports._prelaunch_analysis(game, posts)
    assert res["verdict"] == "preexisting"
    assert res["preexisting_hype"] is True
    assert res["n_pre"] == 3 and res["n_post"] == 1
    assert "prelaunch_signal_early_access" in res["signals"]


def test_prelaunch_detects_launch_driven():
    """Nessun segnale pre-lancio, attivita' concentrata dopo la release."""
    game = {
        "release_date": date(2026, 7, 1),
        "demo_release_date": date(2026, 6, 28),
        "tags": ["Indie"],
        "genres": ["Puzzle"],
        "first_seen_at": datetime(2026, 6, 29, tzinfo=timezone.utc),
    }
    posts = [
        {"posted_at": datetime(2026, 7, 5, tzinfo=timezone.utc), "platform": "youtube"},
        {"posted_at": datetime(2026, 7, 8, tzinfo=timezone.utc), "platform": "youtube"},
    ]
    res = reports._prelaunch_analysis(game, posts)
    assert res["verdict"] == "launch_driven"
    assert res["preexisting_hype"] is False
    assert res["n_post"] == 2 and res["n_pre"] == 0


def test_prelaunch_insufficient_without_release():
    res = reports._prelaunch_analysis({"release_date": None}, [])
    assert res["verdict"] == "insufficient"


def test_report_includes_prelaunch_section(session):
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang="it", persist=False)
    assert "prelaunch" in report["data"]
    # La sezione compare nel summary.
    assert "pre-lancio" in report["summary"].lower() or "Interesse" in report["summary"]
