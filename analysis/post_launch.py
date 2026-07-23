"""Autopsia del post-lancio: cosa succede DOPO lo spike di lancio.

Questo modulo e' il COMPLEMENTO di ``reports._prelaunch_analysis`` (che
studia il "prima"): qui analizziamo la fase DOPO il picco di lancio di un
gioco. Calcola:

1. Il **picco di lancio** su una metrica (recensioni o player count).
2. La **half-life** (emivita) del decadimento post-picco: quanto in fretta
   si dimezza lo SLANCIO (pendenza per-ora), non il valore assoluto — le
   recensioni sono cumulative e non scendono, quindi si usa la derivata;
   per ``current_players`` si puo' usare il valore che invece scende davvero.
3. Le **"seconde vite"** (secondi picchi): nuovi rialzi marcati della
   pendenza dopo che lo slancio del lancio si e' esaurito.
4. La **co-occorrenza** di quei rimbalzi con eventi osservabili (sconti,
   uscita da Early Access, festival, impennate social). SOLO co-occorrenza,
   MAI causalita' — e' il principio non negoziabile del progetto.
5. Un **suggeritore di leve** post-lancio aggregato per genere: quali eventi
   co-occorrono piu' spesso con un secondo picco nel corpus del genere.

Tutte le funzioni di analisi sono **pure**: operano su liste di dict di
snapshot/post/game gia' estratti dal DB (stessa forma usata da
``growth.py`` e ``reports.py``), senza rete ne' accesso diretto al DB.
L'unico accesso al DB e' isolato nella sottile ``analyze_genre_levers_from_db``.

Riusa le convenzioni e le funzioni di ``analysis.growth``: ``_sorted_points``,
``compute_deltas``, ``find_turning_points``, ``_as_utc``, ``_slope``.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence

from analysis.growth import (
    _as_utc,
    _sorted_points,
    compute_deltas,
    find_turning_points,
)


# ==========================================================================
# Helper locali (serializzazione + date)
# ==========================================================================
# NB: replichiamo qui due micro-helper equivalenti a quelli di reports.py
# (``_iso``/``_to_date``/``_json_safe``) SOLO per evitare un import circolare:
# reports.py importa post_launch.py, quindi post_launch non puo' importare
# reports a livello di modulo. Sono funzioni banali.


def _iso(d: Any) -> Any:
    """Serializza date/datetime in stringa ISO; lascia intatto il resto."""
    if isinstance(d, (date, datetime)):
        return d.isoformat()
    return d


def _to_date(d: Any) -> Optional[date]:
    """Normalizza a ``date`` (accetta date/datetime/ISO string)."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _json_safe(obj: Any) -> Any:
    """Rende un oggetto ricorsivamente json-serializzabile (date -> ISO)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


# ==========================================================================
# 1. Picco di lancio
# ==========================================================================


def find_launch_peak(
    snapshots: Sequence[dict[str, Any]],
    metric: str = "total_reviews",
    mode: str = "auto",
) -> Optional[dict[str, Any]]:
    """Individua il picco di lancio su una metrica (FUNZIONE PURA).

    ``mode``:
    - ``"value"``: punto di massimo valore (adatto a ``current_players``,
      che sale e scende davvero).
    - ``"velocity"``: intervallo di massima pendenza per-ora (adatto a
      ``total_reviews``, cumulativa: il "valore" massimo sarebbe sempre
      l'ultimo punto, quindi si guarda lo slancio).
    - ``"auto"``: velocity per ``total_reviews``, value altrimenti.

    Ritorna ``{"at": datetime, "value": float, "velocity": float|None,
    "mode": str}`` oppure ``None`` se la serie e' troppo corta (< 2 punti).
    """
    points = _sorted_points(snapshots, metric)
    if len(points) < 2:
        return None

    resolved = mode
    if resolved == "auto":
        resolved = "velocity" if metric == "total_reviews" else "value"

    if resolved == "value":
        idx = max(range(len(points)), key=lambda i: points[i][1])
        t, v = points[idx]
        return {"at": t, "value": v, "velocity": None, "mode": "value"}

    # velocity: intervallo di massima pendenza per-ora.
    deltas = compute_deltas(snapshots, metric)
    best: Optional[dict[str, Any]] = None
    for d in deltas:
        ph = d.get("per_hour")
        if ph is None:
            continue
        if best is None or ph > best["per_hour"]:
            best = d
    if best is None:
        return None
    return {
        "at": best["to"],
        "value": best["to_value"],
        "velocity": best["per_hour"],
        "mode": "velocity",
    }


# ==========================================================================
# 2. Half-life del decadimento post-picco
# ==========================================================================


def _linfit(xs: Sequence[float], ys: Sequence[float]) -> Optional[tuple[float, float]]:
    """Regressione lineare minimi quadrati; ritorna (slope, intercept)."""
    n = len(xs)
    if n < 2:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:  # x tutti uguali -> pendenza indeterminata
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def _r_squared(
    xs: Sequence[float], ys: Sequence[float], slope: float, intercept: float
) -> Optional[float]:
    """Coefficiente di determinazione della retta di fit."""
    n = len(ys)
    if n < 2:
        return None
    mean_y = sum(ys) / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    if ss_tot == 0:
        return None
    return round(1 - ss_res / ss_tot, 3)


def _decay_series(
    snapshots: Sequence[dict[str, Any]],
    metric: str,
    peak_t: datetime,
) -> tuple[list[float], list[float]]:
    """Serie del decadimento post-picco: ``(x_giorni, y)``.

    - ``current_players``: usa il VALORE dopo il picco (scende davvero).
    - metriche cumulative (``total_reviews``): usa la PENDENZA per-ora degli
      intervalli che iniziano al/dopo il picco (lo slancio, che decade).
    """
    xs: list[float] = []
    ys: list[float] = []
    if metric == "current_players":
        for t, v in _sorted_points(snapshots, metric):
            if t > peak_t:
                xs.append((t - peak_t).total_seconds() / 86400.0)
                ys.append(v)
        return xs, ys

    for d in compute_deltas(snapshots, metric):
        ph = d.get("per_hour")
        if ph is None:
            continue
        if d["from"] >= peak_t:  # intervallo che parte dal picco in poi
            mid = d["from"] + (d["to"] - d["from"]) / 2
            xs.append((mid - peak_t).total_seconds() / 86400.0)
            ys.append(ph)
    return xs, ys


def estimate_half_life(
    snapshots: Sequence[dict[str, Any]],
    metric: str = "total_reviews",
    peak: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Stima l'emivita del decadimento dello slancio post-picco (PURA).

    Fit esponenziale semplice ``y = y0 * exp(-lambda * t)`` via regressione
    log-lineare sulla serie di decadimento (vedi ``_decay_series``).
    ``half_life = ln(2) / lambda`` in GIORNI.

    Degrada SEMPRE con onesta': se non ci sono abbastanza punti oltre il
    picco ritorna ``half_life_days=None`` con un ``reason`` esplicito.
    Dichiara SEMPRE ``n`` (numero di punti usati oltre il picco).
    """
    if peak is None:
        peak = find_launch_peak(snapshots, metric)
    if peak is None:
        return {"half_life_days": None, "n": 0, "metric": metric,
                "reason": "no_peak"}

    peak_t = peak["at"]
    if not isinstance(peak_t, datetime):
        pd = _to_date(peak_t)
        if pd is None:
            return {"half_life_days": None, "n": 0, "metric": metric,
                    "reason": "no_peak"}
        peak_t = _as_utc(datetime(pd.year, pd.month, pd.day))

    xs, ys = _decay_series(snapshots, metric, peak_t)
    n = len(xs)
    if n < 2:
        return {"half_life_days": None, "n": n, "metric": metric,
                "reason": "insufficient_points_after_peak"}

    # Fit log-lineare solo sui punti positivi (log richiede y > 0).
    lx = [x for x, y in zip(xs, ys) if y > 0]
    ly = [math.log(y) for y in ys if y > 0]
    if len(lx) < 2:
        return {"half_life_days": None, "n": n, "metric": metric,
                "reason": "insufficient_positive_points"}

    fit = _linfit(lx, ly)
    if fit is None:
        return {"half_life_days": None, "n": n, "metric": metric,
                "reason": "degenerate_fit"}
    slope, intercept = fit
    lam = -slope
    if lam <= 1e-9:
        # Pendenza non decrescente: lo slancio non si dimezza (o cresce).
        return {"half_life_days": None, "n": n, "metric": metric,
                "lambda_per_day": lam, "reason": "no_decay"}

    half_life = math.log(2) / lam
    return {
        "half_life_days": round(half_life, 2),
        "n": n,
        "lambda_per_day": round(lam, 5),
        "r_squared": _r_squared(lx, ly, slope, intercept),
        "metric": metric,
        "reason": None,
    }


# ==========================================================================
# 3. Seconde vite / secondi picchi
# ==========================================================================


def find_second_winds(
    snapshots: Sequence[dict[str, Any]],
    metric: str = "total_reviews",
    peak: Optional[dict[str, Any]] = None,
    accel_factor: float = 2.0,
    min_abs_slope: float = 0.0,
) -> list[dict[str, Any]]:
    """Rileva le "seconde vite": rialzi marcati della pendenza DOPO il picco.

    Riusa ``growth.find_turning_points`` (stesso criterio di accelerazione
    del playbook) e tiene solo i punti di svolta successivi al picco di
    lancio. ``rebound`` = entita' del rimbalzo (rapporto di accelerazione
    slope_after/slope_before). FUNZIONE PURA.
    """
    if peak is None:
        peak = find_launch_peak(snapshots, metric)
    if peak is None:
        return []
    peak_t = peak["at"]
    if not isinstance(peak_t, datetime):
        pd = _to_date(peak_t)
        peak_t = _as_utc(datetime(pd.year, pd.month, pd.day)) if pd else None
    if peak_t is None:
        return []

    turns = find_turning_points(
        snapshots, metric=metric,
        accel_factor=accel_factor, min_abs_slope=min_abs_slope,
    )
    out: list[dict[str, Any]] = []
    for tp in turns:
        if tp["at"] > peak_t:
            out.append({
                "at": tp["at"],
                "value": tp["value"],
                "slope_before": tp["slope_before"],
                "slope_after": tp["slope_after"],
                "rebound": tp.get("accel_ratio"),
            })
    return out


# ==========================================================================
# 4. Co-occorrenza dei rimbalzi con eventi osservabili
# ==========================================================================


def _ea_state(snap: dict[str, Any]) -> tuple[Optional[bool], bool]:
    """Stato Early Access di uno snapshot: ``(is_ea, data_available)``.

    Best-effort sui dati disponibili: cerca ``extra.early_access`` (bool) o
    una lista di tag/generi in ``extra`` che contenga "early access".
    """
    ex = snap.get("extra") or {}
    if not isinstance(ex, dict):
        return None, False
    if "early_access" in ex:
        return bool(ex["early_access"]), True
    tags = ex.get("tags")
    if tags is None:
        tags = ex.get("genres")
    if isinstance(tags, (list, tuple)):
        return any("early access" in str(x).lower() for x in tags), True
    return None, False


def _detect_ea_exit(
    snapshots: Sequence[dict[str, Any]],
    lo: datetime,
    hi: datetime,
) -> Optional[dict[str, Any]]:
    """Rileva una transizione Early Access True->False nella finestra.

    Ritorna un evento se la transizione cade in ``[lo, hi]``. Se i dati EA
    non sono disponibili (< 2 snapshot con informazione EA) ritorna ``None``:
    l'assenza non e' un'affermazione, e il chiamante puo' segnalarlo.
    """
    states: list[tuple[datetime, Optional[bool]]] = []
    ordered = sorted(
        [s for s in snapshots if s.get("captured_at") is not None],
        key=lambda s: _as_utc(s["captured_at"]),
    )
    for s in ordered:
        st, avail = _ea_state(s)
        if avail:
            states.append((_as_utc(s["captured_at"]), st))
    if len(states) < 2:
        return None
    for (t0, s0), (t1, s1) in zip(states, states[1:]):
        if s0 is True and s1 is False and lo <= t1 <= hi:
            return {"type": "ea_exit", "t": t1}
    return None


def detect_cooccurring_events(
    snapshots: Sequence[dict[str, Any]],
    posts: Sequence[dict[str, Any]],
    around: datetime,
    festival_windows: Optional[Sequence[dict[str, Any]]] = None,
    window_days: float = 10.0,
    social_surge_min: int = 2,
) -> list[dict[str, Any]]:
    """Eventi osservabili che CO-OCCORRONO con un rimbalzo (PURA).

    Cerca, nella finestra ``around +/- window_days``:
    - ``discount``: calo del ``price`` tra snapshot consecutivi;
    - ``ea_exit``: uscita da Early Access / salto di versione (best-effort);
    - ``festival``: ``around`` cade in una finestra-festival passata come
      parametro (nessun calendario hardcodato: se la lista e' vuota, salta);
    - ``social_surge``: >= ``social_surge_min`` post social nella finestra.

    IMPORTANTE: SOLO co-occorrenza, MAI causalita'. Il chiamante deve
    presentare questi eventi come "coincidono con", non "hanno causato".
    """
    around = _as_utc(around)
    lo = around - timedelta(days=window_days)
    hi = around + timedelta(days=window_days)
    events: list[dict[str, Any]] = []

    # --- Sconto: delta negativo sul prezzo tra snapshot consecutivi ---
    for d in compute_deltas(snapshots, "price"):
        delta = d.get("delta")
        if delta is not None and delta < 0 and lo <= d["to"] <= hi:
            events.append({
                "type": "discount",
                "t": d["to"],
                "old_price": d["from_value"],
                "new_price": d["to_value"],
                "drop": -delta,
            })

    # --- Uscita da Early Access / salto di versione ---
    ea = _detect_ea_exit(snapshots, lo, hi)
    if ea is not None:
        events.append(ea)

    # --- Festival (calendario iniettato, mai hardcodato) ---
    around_d = around.date()
    for f in festival_windows or []:
        s = _to_date(f.get("start"))
        e = _to_date(f.get("end"))
        if s and e and s <= around_d <= e:
            events.append({
                "type": "festival",
                "name": f.get("name"),
                "start": s,
                "end": e,
            })

    # --- Impennata di post social nella finestra ---
    n_posts = 0
    for p in posts:
        pt = p.get("posted_at")
        if pt is None:
            continue
        pt = _as_utc(pt) if isinstance(pt, datetime) else None
        if pt is not None and lo <= pt <= hi:
            n_posts += 1
    if n_posts >= social_surge_min:
        events.append({
            "type": "social_surge",
            "n_posts": n_posts,
            "window_days": window_days,
        })

    return events


# ==========================================================================
# Orchestrazione per-gioco
# ==========================================================================

# Numero minimo di snapshot per un'autopsia significativa (picco + decadimento).
MIN_SNAPSHOTS = 3


def analyze_post_launch(
    game: dict[str, Any],
    snapshots: Sequence[dict[str, Any]],
    posts: Sequence[dict[str, Any]],
    metric: str = "total_reviews",
    festival_windows: Optional[Sequence[dict[str, Any]]] = None,
    window_days: float = 10.0,
    accel_factor: float = 2.0,
    social_surge_min: int = 2,
) -> dict[str, Any]:
    """Autopsia post-lancio completa per un gioco (FUNZIONE PURA, json-safe).

    Mette insieme picco, half-life, seconde vite e co-occorrenze. Degrada
    con onesta': con meno di ``MIN_SNAPSHOTS`` punti utili ritorna
    ``status="insufficient"`` dichiarando ``n_snapshots``, senza inventare.

    Ritorna un dict json-serializzabile (date come ISO string) con:
    ``metric, n_snapshots, genres, status, peak, half_life, second_winds
    (ognuno con ``events``), levers_observed``.
    """
    points = _sorted_points(snapshots, metric)
    n = len(points)
    genres = [str(x) for x in
              ((game.get("genres") or []) + (game.get("tags") or []))]

    base: dict[str, Any] = {"metric": metric, "n_snapshots": n, "genres": genres}

    if n < MIN_SNAPSHOTS:
        base.update({
            "status": "insufficient",
            "peak": None,
            "half_life": {"half_life_days": None, "n": 0, "metric": metric,
                          "reason": "insufficient_snapshots"},
            "second_winds": [],
            "levers_observed": [],
        })
        return _json_safe(base)

    peak = find_launch_peak(snapshots, metric)
    half = estimate_half_life(snapshots, metric, peak=peak)
    winds = find_second_winds(snapshots, metric, peak=peak,
                              accel_factor=accel_factor)

    sw_out: list[dict[str, Any]] = []
    levers: set[str] = set()
    for w in winds:
        evs = detect_cooccurring_events(
            snapshots, posts, w["at"],
            festival_windows=festival_windows,
            window_days=window_days,
            social_surge_min=social_surge_min,
        )
        for e in evs:
            levers.add(e["type"])
        sw_out.append({**w, "events": evs})

    base.update({
        "status": "ok",
        "peak": peak,
        "half_life": half,
        "second_winds": sw_out,
        "levers_observed": sorted(levers),
    })
    return _json_safe(base)


# ==========================================================================
# 5. Suggeritore di leve post-lancio (aggregazione per genere)
# ==========================================================================


def aggregate_genre_levers(
    analyses: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggrega per genere le leve osservate (co-occorrenze) su piu' giochi.

    ``analyses`` = lista di dict prodotti da ``analyze_post_launch``. Per
    ogni genere conta in quanti giochi ciascun tipo di evento CO-OCCORRE con
    almeno un secondo picco, e la frequenza sul campione N.

    Onesta': l'output dice "osservato in X/N giochi del genere", mai
    "fara' crescere". Usa pandas per l'aggregazione. FUNZIONE PURA.

    Ritorna una lista ordinata di
    ``{"genre", "n_games", "n_games_with_second_wind", "levers": [
        {"lever", "games_with_cooccurrence", "n_games", "frequency"} ...]}``.
    """
    import pandas as pd

    membership: list[dict[str, Any]] = []
    lever_rows: list[dict[str, Any]] = []
    for idx, a in enumerate(analyses):
        genres = a.get("genres") or []
        has_wind = bool(a.get("second_winds"))
        levers = a.get("levers_observed") or []
        for g in genres:
            membership.append({"genre": g, "game": idx, "has_wind": has_wind})
            for lv in levers:
                lever_rows.append({"genre": g, "game": idx, "lever": lv})

    mdf = pd.DataFrame(membership)
    if mdf.empty:
        return []

    n_by_genre = mdf.groupby("genre")["game"].nunique()
    wind_by_genre = (
        mdf[mdf["has_wind"]].groupby("genre")["game"].nunique()
        if mdf["has_wind"].any() else pd.Series(dtype="int64")
    )
    ldf = pd.DataFrame(lever_rows)

    result: list[dict[str, Any]] = []
    for genre, n_games in n_by_genre.items():
        n_games = int(n_games)
        levers_list: list[dict[str, Any]] = []
        if not ldf.empty:
            sub = ldf[ldf["genre"] == genre]
            if not sub.empty:
                counts = sub.groupby("lever")["game"].nunique().sort_values(
                    ascending=False)
                for lever, c in counts.items():
                    c = int(c)
                    levers_list.append({
                        "lever": lever,
                        "games_with_cooccurrence": c,
                        "n_games": n_games,
                        "frequency": round(c / n_games, 3) if n_games else 0.0,
                    })
        result.append({
            "genre": genre,
            "n_games": n_games,
            "n_games_with_second_wind": int(wind_by_genre.get(genre, 0)),
            "levers": levers_list,
        })

    # Ordina: prima i generi con piu' leve osservate, poi campione piu' grande.
    result.sort(key=lambda r: (-len(r["levers"]), -r["n_games"], r["genre"]))
    return result


# ==========================================================================
# ACCESSO AL DB (sottile, isolato — il core resta puro)
# ==========================================================================


def analyze_genre_levers_from_db(
    session,
    genre: str,
    festival_windows: Optional[Sequence[dict[str, Any]]] = None,
    metric: str = "total_reviews",
) -> dict[str, Any]:
    """Raccoglie dal DB le serie di tutti i giochi di un genere e ne aggrega
    le leve post-lancio. L'ACCESSO AL DB e' confinato qui; il calcolo e'
    delegato alle funzioni pure sopra.

    Ritorna ``{"genre", "n_games", "n_games_with_second_wind", "levers",
    "analyses"}`` (tutto json-serializzabile).
    """
    from sqlalchemy import select

    from core.models import Game, GameSnapshot, SocialPost

    games = list(session.scalars(select(Game)))
    analyses: list[dict[str, Any]] = []
    for g in games:
        combined = (g.genres or []) + (g.tags or [])
        if genre not in combined:
            continue
        snaps = list(session.scalars(
            select(GameSnapshot)
            .where(GameSnapshot.game_id == g.id)
            .order_by(GameSnapshot.captured_at)
        ))
        posts = list(session.scalars(
            select(SocialPost).where(SocialPost.game_id == g.id)
        ))
        game_dict = {
            "title": g.title,
            "genres": g.genres or [],
            "tags": g.tags or [],
        }
        snap_dicts = [
            {
                "captured_at": s.captured_at,
                "total_reviews": s.total_reviews,
                "current_players": s.current_players,
                "price": s.price,
                "extra": s.extra,
            }
            for s in snaps
        ]
        post_dicts = [
            {
                "posted_at": p.posted_at,
                "platform": p.platform.value if hasattr(p.platform, "value")
                else p.platform,
            }
            for p in posts
        ]
        analyses.append(analyze_post_launch(
            game_dict, snap_dicts, post_dicts,
            metric=metric, festival_windows=festival_windows,
        ))

    agg = aggregate_genre_levers(analyses)
    for row in agg:
        if row["genre"] == genre:
            return {**row, "analyses": analyses}
    return {
        "genre": genre,
        "n_games": len(analyses),
        "n_games_with_second_wind": 0,
        "levers": [],
        "analyses": analyses,
    }
