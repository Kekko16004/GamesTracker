"""Aggregazioni di trend per genere/tag con pandas.

Risponde a domande tipo: quali generi crescono ora (media della crescita
recensioni/player per genere), timing tipico demo -> release -> picco,
distribuzioni degli score. Ritorna strutture gia' pronte per i grafici
della GUI (liste di dict json-serializzabili).

Design:
- ``build_games_frame`` costruisce un ``DataFrame`` a partire da record
  gia' estratti dal DB (funzione pura su input list-of-dict).
- Le funzioni di aggregazione lavorano sul DataFrame -> testabili senza rete.
- ``collect_trend_input(session)`` e' l'unico punto che tocca il DB e
  produce l'input per ``build_games_frame``.

Nota dominio: le stime SteamSpy sono approssimative; qui si usano solo le
traiettorie relative, mai valori assoluti come verita'.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import pandas as pd

from analysis.growth import compute_growth_metrics


def build_games_frame(records: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Costruisce il DataFrame dei giochi per le aggregazioni.

    Ogni record e' un dict con almeno: ``game_id``, ``title``, ``genres``
    (lista), ``tags`` (lista), ``quality_score``, ``discarded``,
    ``reviews_growth_rate``, ``players_growth_rate``, ``release_date``,
    ``demo_release_date``, ``days_demo_to_release``, ``days_release_to_peak``.
    Funzione pura.
    """
    df = pd.DataFrame(list(records))
    # Colonne attese anche su input vuoto (evita KeyError a valle).
    expected = [
        "game_id", "title", "genres", "tags", "quality_score", "discarded",
        "reviews_growth_rate", "players_growth_rate", "release_date",
        "demo_release_date", "days_demo_to_release", "days_release_to_peak",
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    return df


def _explode_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Esplode una colonna-lista (genres/tags) una riga per elemento."""
    if df.empty:
        return df.assign(**{column[:-1] if column.endswith("s") else column: []})
    exploded = df.copy()
    exploded[column] = exploded[column].apply(
        lambda v: v if isinstance(v, (list, tuple)) and len(v) else [None]
    )
    exploded = exploded.explode(column, ignore_index=True)
    return exploded


def growth_by_genre(
    df: pd.DataFrame,
    include_discarded: bool = False,
    min_games: int = 1,
) -> list[dict[str, Any]]:
    """Media della crescita per genere (quali generi tirano ora).

    Ritorna una lista di dict ordinata per crescita recensioni media
    decrescente: ``{genre, n_games, avg_reviews_growth, avg_players_growth,
    avg_quality_score}``. Funzione pura sul DataFrame.
    """
    if df.empty:
        return []
    work = df if include_discarded else df[df["discarded"] != True]  # noqa: E712
    exploded = _explode_by(work, "genres")
    exploded = exploded[exploded["genres"].notna()]
    if exploded.empty:
        return []

    grouped = exploded.groupby("genres", dropna=True)
    out: list[dict[str, Any]] = []
    for genre, g in grouped:
        n = len(g)
        if n < min_games:
            continue
        out.append(
            {
                "genre": genre,
                "n_games": int(n),
                "avg_reviews_growth": _safe_mean(g["reviews_growth_rate"]),
                "avg_players_growth": _safe_mean(g["players_growth_rate"]),
                "avg_quality_score": _safe_mean(g["quality_score"]),
            }
        )
    out.sort(
        key=lambda d: (d["avg_reviews_growth"] is None, -(d["avg_reviews_growth"] or 0))
    )
    return out


def timing_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Timing tipico demo -> release -> picco (mediana e media).

    Aggrega ``days_demo_to_release`` e ``days_release_to_peak`` su tutto il
    campione. Ritorna anche N per dichiarare la dimensione del campione
    (correlazione, non causalita'). Funzione pura.
    """
    def _stats(col: str) -> dict[str, Any]:
        if col not in df.columns:
            return {"n": 0, "median": None, "mean": None}
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        return {
            "n": int(s.count()),
            "median": float(s.median()) if not s.empty else None,
            "mean": round(float(s.mean()), 2) if not s.empty else None,
        }

    return {
        "demo_to_release": _stats("days_demo_to_release"),
        "release_to_peak": _stats("days_release_to_peak"),
    }


def timing_by_genre(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Timing demo->release->picco mediano per genere. Funzione pura."""
    if df.empty:
        return []
    exploded = _explode_by(df, "genres")
    exploded = exploded[exploded["genres"].notna()]
    if exploded.empty:
        return []
    out: list[dict[str, Any]] = []
    for genre, g in exploded.groupby("genres", dropna=True):
        d2r = pd.to_numeric(g["days_demo_to_release"], errors="coerce").dropna()
        r2p = pd.to_numeric(g["days_release_to_peak"], errors="coerce").dropna()
        out.append(
            {
                "genre": genre,
                "n_games": int(len(g)),
                "median_demo_to_release": float(d2r.median()) if not d2r.empty else None,
                "median_release_to_peak": float(r2p.median()) if not r2p.empty else None,
            }
        )
    out.sort(key=lambda d: -d["n_games"])
    return out


def quality_distribution(df: pd.DataFrame, bins: int = 10) -> dict[str, Any]:
    """Distribuzione degli score qualita' (istogramma) per la GUI.

    Ritorna edges e counts dell'istogramma su [0,100], piu' statistiche
    riassuntive. Funzione pura.
    """
    s = pd.to_numeric(df.get("quality_score"), errors="coerce").dropna() \
        if not df.empty else pd.Series(dtype="float")
    if s.empty:
        return {"bins": [], "counts": [], "n": 0, "median": None, "mean": None}
    counts, edges = _histogram(s, bins)
    return {
        "bins": [round(float(e), 2) for e in edges],
        "counts": [int(c) for c in counts],
        "n": int(s.count()),
        "median": round(float(s.median()), 2),
        "mean": round(float(s.mean()), 2),
    }


def _histogram(s: pd.Series, bins: int) -> tuple[list[int], list[float]]:
    """Istogramma su [0,100] senza dipendere da numpy direttamente."""
    lo, hi = 0.0, 100.0
    width = (hi - lo) / bins
    edges = [lo + i * width for i in range(bins + 1)]
    counts = [0] * bins
    for v in s:
        idx = int((v - lo) / width)
        if idx == bins:
            idx = bins - 1
        if 0 <= idx < bins:
            counts[idx] += 1
    return counts, edges


def _safe_mean(series: pd.Series) -> Optional[float]:
    """Media ignorando i None/NaN; None se tutto vuoto."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    return round(float(s.mean()), 4) if not s.empty else None


# --- Accesso al DB (unico punto non puro) ---------------------------------


def collect_trend_input(session, include_discarded: bool = True) -> list[dict[str, Any]]:
    """Estrae dal DB i record per ``build_games_frame``.

    Per ogni gioco calcola i growth rate dai suoi snapshot e i timing
    demo->release->picco. Ritorna una lista di dict pronta per il frame.
    """
    from sqlalchemy import select

    from core.models import Game, GameSnapshot

    records: list[dict[str, Any]] = []
    # Use DISTINCT to guard against any ORM-level duplicate rows.
    seen_ids: set[int] = set()
    games = list(session.scalars(select(Game).distinct()))
    for game in games:
        if game.id in seen_ids:
            continue
        seen_ids.add(game.id)
        snaps = list(
            session.scalars(
                select(GameSnapshot)
                .where(GameSnapshot.game_id == game.id)
                .order_by(GameSnapshot.captured_at)
            )
        )
        snap_dicts = [
            {
                "captured_at": s.captured_at,
                "total_reviews": s.total_reviews,
                "current_players": s.current_players,
            }
            for s in snaps
        ]
        gm = compute_growth_metrics(snap_dicts)

        days_demo_to_release = None
        if game.demo_release_date and game.release_date:
            days_demo_to_release = (game.release_date - game.demo_release_date).days

        days_release_to_peak = _days_release_to_peak(game, snaps)

        records.append(
            {
                "game_id": game.id,
                "title": game.title,
                "genres": game.genres or [],
                "tags": game.tags or [],
                "quality_score": game.quality_score,
                "discarded": game.discarded,
                "reviews_growth_rate": gm.get("reviews_growth_rate"),
                "players_growth_rate": gm.get("players_growth_rate"),
                "release_date": game.release_date.isoformat() if game.release_date else None,
                "demo_release_date": (
                    game.demo_release_date.isoformat()
                    if game.demo_release_date else None
                ),
                "days_demo_to_release": days_demo_to_release,
                "days_release_to_peak": days_release_to_peak,
            }
        )
    return records


def _days_release_to_peak(game, snaps) -> Optional[int]:
    """Giorni tra la release e il picco di player count osservato."""
    if not game.release_date or not snaps:
        return None
    peak_snap = None
    peak_val = -1
    for s in snaps:
        if s.current_players is not None and s.current_players > peak_val:
            peak_val = s.current_players
            peak_snap = s
    if peak_snap is None:
        return None
    captured = peak_snap.captured_at
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return (captured.date() - game.release_date).days
