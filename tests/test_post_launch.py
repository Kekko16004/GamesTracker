"""Test dell'autopsia post-lancio (analysis/post_launch.py).

Dataset sintetici, nessuna chiamata di rete. Copre: picco, half-life
calcolabile, degrado su serie corte, seconde vite con co-occorrenza di
sconto/festival/social, aggregazione leve per genere, integrazione nel
report IT/EN e serializzabilita' json.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from analysis import post_launch as pl
from analysis import reports
from tests.conftest_analysis import add_good_game, make_memory_session

UTC = timezone.utc


def _snap(days, reviews=None, players=None, price=None, extra=None):
    base = datetime(2026, 5, 1, tzinfo=UTC)
    return {
        "captured_at": base + timedelta(days=days),
        "total_reviews": reviews,
        "current_players": players,
        "price": price,
        "extra": extra,
    }


# --- Picco -----------------------------------------------------------------


def test_find_launch_peak_velocity_reviews():
    """Su recensioni cumulative il picco e' l'intervallo di massimo slancio."""
    snaps = [
        _snap(0, reviews=0),
        _snap(1, reviews=1000),   # slancio massimo qui
        _snap(2, reviews=1100),
        _snap(3, reviews=1150),
    ]
    peak = pl.find_launch_peak(snaps, "total_reviews")
    assert peak is not None
    assert peak["mode"] == "velocity"
    assert peak["at"] == snaps[1]["captured_at"]


def test_find_launch_peak_value_players():
    snaps = [
        _snap(0, players=100),
        _snap(1, players=900),   # picco valore
        _snap(2, players=300),
    ]
    peak = pl.find_launch_peak(snaps, "current_players")
    assert peak["mode"] == "value"
    assert peak["value"] == 900


def test_find_launch_peak_too_short():
    assert pl.find_launch_peak([_snap(0, reviews=10)], "total_reviews") is None


# --- Half-life -------------------------------------------------------------


def test_half_life_decays():
    """Slancio recensioni che si dimezza -> half-life stimabile e positiva."""
    # per-hour cala esponenzialmente: pendenze ~ 20,10,5 review/h su step giornalieri
    # costruiamo cumulate con incrementi decrescenti di fattore ~2 al giorno.
    r = [0, 1000, 1500, 1750, 1875]  # delta: 1000,500,250,125 (dimezza ogni step)
    snaps = [_snap(i, reviews=r[i]) for i in range(len(r))]
    hl = pl.estimate_half_life(snaps, "total_reviews")
    assert hl["half_life_days"] is not None
    assert hl["half_life_days"] > 0
    assert hl["n"] >= 2
    # dimezzamento per step giornaliero -> half-life vicina a 1 giorno.
    assert 0.5 < hl["half_life_days"] < 2.0


def test_half_life_insufficient_degrades():
    """Serie senza abbastanza punti dopo il picco -> None con motivo."""
    snaps = [_snap(0, reviews=0), _snap(1, reviews=1000)]
    hl = pl.estimate_half_life(snaps, "total_reviews")
    assert hl["half_life_days"] is None
    assert hl["reason"] is not None
    assert "n" in hl


def test_half_life_no_decay():
    """Picco iniziale, poi slancio costante -> nessun decadimento."""
    # delta: 1000 (picco), poi 100,100,100 costanti dopo il picco.
    r = [0, 1000, 1100, 1200, 1300]
    snaps = [_snap(i, reviews=r[i]) for i in range(len(r))]
    hl = pl.estimate_half_life(snaps, "total_reviews")
    assert hl["half_life_days"] is None
    assert hl["reason"] == "no_decay"


# --- Seconde vite + co-occorrenza -----------------------------------------


def test_second_wind_cooccurs_with_discount():
    """Rimbalzo della pendenza che coincide con un calo di prezzo."""
    # picco iniziale, decadimento, poi nuova accelerazione con sconto.
    snaps = [
        _snap(0, reviews=0, price=20.0),
        _snap(1, reviews=1000, price=20.0),   # picco lancio
        _snap(2, reviews=1050, price=20.0),   # decaduto
        _snap(3, reviews=1070, price=20.0),
        _snap(4, reviews=1090, price=10.0),   # sconto
        _snap(5, reviews=1600, price=10.0),   # seconda vita
    ]
    peak = pl.find_launch_peak(snaps, "total_reviews")
    winds = pl.find_second_winds(snaps, "total_reviews", peak=peak)
    assert winds, "atteso almeno un secondo picco"
    # cerca l'evento sconto nella co-occorrenza di uno dei rimbalzi.
    found_discount = False
    for w in winds:
        evs = pl.detect_cooccurring_events(snaps, [], w["at"])
        if any(e["type"] == "discount" for e in evs):
            found_discount = True
    assert found_discount


def test_cooccurrence_festival_and_social():
    around = datetime(2026, 6, 10, tzinfo=UTC)
    snaps = [_snap(0, reviews=0), _snap(1, reviews=100)]
    posts = [
        {"posted_at": datetime(2026, 6, 9, tzinfo=UTC), "platform": "youtube"},
        {"posted_at": datetime(2026, 6, 11, tzinfo=UTC), "platform": "reddit"},
    ]
    festivals = [{"name": "Summer Fest", "start": date(2026, 6, 8),
                  "end": date(2026, 6, 14)}]
    evs = pl.detect_cooccurring_events(snaps, posts, around,
                                       festival_windows=festivals)
    types = {e["type"] for e in evs}
    assert "festival" in types
    assert "social_surge" in types


def test_cooccurrence_ea_exit():
    snaps = [
        {"captured_at": datetime(2026, 6, 1, tzinfo=UTC), "total_reviews": 100,
         "extra": {"early_access": True}},
        {"captured_at": datetime(2026, 6, 10, tzinfo=UTC), "total_reviews": 200,
         "extra": {"early_access": False}},
    ]
    evs = pl.detect_cooccurring_events(
        snaps, [], datetime(2026, 6, 10, tzinfo=UTC))
    assert any(e["type"] == "ea_exit" for e in evs)


# --- Orchestrazione per-gioco ---------------------------------------------


def test_analyze_post_launch_insufficient():
    out = pl.analyze_post_launch({"genres": ["Action"]},
                                 [_snap(0, reviews=10)], [])
    assert out["status"] == "insufficient"
    assert out["n_snapshots"] == 1
    assert out["peak"] is None
    json.dumps(out)  # json-safe


def test_analyze_post_launch_full_json_safe():
    snaps = [
        _snap(0, reviews=0, price=20.0),
        _snap(1, reviews=1000, price=20.0),
        _snap(2, reviews=1050, price=20.0),
        _snap(3, reviews=1070, price=10.0),
        _snap(4, reviews=1500, price=10.0),
    ]
    out = pl.analyze_post_launch({"genres": ["Roguelike"]}, snaps, [])
    assert out["status"] == "ok"
    assert out["peak"] is not None
    json.dumps(out)  # nessuna data grezza


# --- Aggregazione leve per genere -----------------------------------------


def test_aggregate_genre_levers():
    analyses = [
        {"genres": ["Roguelike"], "second_winds": [{"at": "x"}],
         "levers_observed": ["discount", "social_surge"]},
        {"genres": ["Roguelike"], "second_winds": [{"at": "y"}],
         "levers_observed": ["discount"]},
        {"genres": ["Roguelike"], "second_winds": [],
         "levers_observed": []},
        {"genres": ["Puzzle"], "second_winds": [{"at": "z"}],
         "levers_observed": ["festival"]},
    ]
    agg = pl.aggregate_genre_levers(analyses)
    by_genre = {r["genre"]: r for r in agg}
    rogue = by_genre["Roguelike"]
    assert rogue["n_games"] == 3
    assert rogue["n_games_with_second_wind"] == 2
    lever_map = {l["lever"]: l for l in rogue["levers"]}
    # sconto osservato in 2/3 giochi del genere.
    assert lever_map["discount"]["games_with_cooccurrence"] == 2
    assert lever_map["discount"]["n_games"] == 3
    assert abs(lever_map["discount"]["frequency"] - 2 / 3) < 0.01
    json.dumps(agg)


def test_aggregate_genre_levers_empty():
    assert pl.aggregate_genre_levers([]) == []


# --- Integrazione nel report ----------------------------------------------


@pytest.fixture()
def session():
    sess, engine = make_memory_session()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.mark.parametrize("lang", ["it", "en"])
def test_report_has_post_launch_section(session, lang):
    game = add_good_game(session)
    report = reports.generate_game_report(session, game.id, lang=lang, persist=False)
    if lang == "it":
        assert "Autopsia post-lancio" in report["summary"]
    else:
        assert "Post-launch autopsy" in report["summary"]
    assert "post_launch" in report["data"]
    json.dumps(report["data"])  # resta serializzabile


def test_report_post_launch_degrades_on_single_snapshot(session):
    """La maggioranza dei giochi ha 1 solo snapshot: deve degradare, non crashare."""
    from core.models import Game, GameSnapshot, Platform, SnapshotType

    g = Game(platform=Platform.STEAM, external_id="solo-1", title="Solo Snap",
             genres=["Action"], tags=[])
    g.snapshots.append(GameSnapshot(
        captured_at=datetime(2026, 6, 1, tzinfo=UTC),
        snapshot_type=SnapshotType.DISCOVERY, total_reviews=10,
        current_players=5))
    session.add(g)
    session.flush()

    report = reports.generate_game_report(session, g.id, lang="it", persist=False)
    assert report["data"]["post_launch"]["status"] == "insufficient"
    # Messaggio onesto con N dichiarato.
    assert "insufficienti" in report["summary"].lower()


def test_analyze_genre_levers_from_db(session):
    add_good_game(session)  # Roguelike, 2 snapshot (serie corta -> insufficient)
    out = pl.analyze_genre_levers_from_db(session, "Roguelike")
    assert out["genre"] == "Roguelike"
    assert out["n_games"] >= 1
    assert "levers" in out
    json.dumps(out)
