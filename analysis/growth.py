"""Metriche di crescita tra snapshot per un gioco.

Calcola delta e tassi di crescita di ``total_reviews``, ``current_players``
e follower social tra snapshot successivi, e individua i "punti di svolta"
(cambi di pendenza) secondo il metodo del marketing-playbook §4.

Tutte le funzioni principali sono **pure**: operano su liste di dict/snapshot
gia' estratti dal DB, senza rete ne accesso al database. Cosi' sono
testabili con serie temporali note.

Convenzioni:
- Uno "snapshot" e' un dict con almeno ``captured_at`` (datetime) e la
  metrica di interesse (es. ``total_reviews``). Gli snapshot vanno passati
  ordinabili per data; le funzioni li riordinano comunque.
- I tassi di crescita sono **relativi** (frazione, es. 0.25 = +25%) sul
  valore iniziale della finestra; ``None`` quando non calcolabili.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

# Finestre temporali canoniche (in ore) allineate al tracking-schedule.
WINDOWS: dict[str, float] = {
    "h24": 24.0,
    "h48": 48.0,
    "w1": 24.0 * 7,
    "m1": 24.0 * 30,
}


def _as_utc(dt: datetime) -> datetime:
    """Rende un datetime timezone-aware in UTC (assume UTC se naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sorted_points(
    snapshots: Sequence[dict[str, Any]], metric: str
) -> list[tuple[datetime, float]]:
    """Estrae e ordina i punti (data, valore) per una metrica.

    Scarta gli snapshot in cui la metrica e' ``None``. Ritorna una lista
    ordinata per data crescente.
    """
    points: list[tuple[datetime, float]] = []
    for s in snapshots:
        value = s.get(metric)
        captured = s.get("captured_at")
        if value is None or captured is None:
            continue
        points.append((_as_utc(captured), float(value)))
    points.sort(key=lambda p: p[0])
    return points


def compute_deltas(
    snapshots: Sequence[dict[str, Any]], metric: str
) -> list[dict[str, Any]]:
    """Delta assoluti e per-ora tra snapshot consecutivi di una metrica.

    Ritorna una lista di dict con: ``from``, ``to`` (datetime), ``delta``
    (assoluto), ``hours`` (durata), ``per_hour`` (pendenza), ``rate``
    (crescita relativa sul valore iniziale). Funzione pura.
    """
    points = _sorted_points(snapshots, metric)
    out: list[dict[str, Any]] = []
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        hours = (t1 - t0).total_seconds() / 3600.0
        delta = v1 - v0
        out.append(
            {
                "from": t0,
                "to": t1,
                "from_value": v0,
                "to_value": v1,
                "delta": delta,
                "hours": hours,
                "per_hour": (delta / hours) if hours > 0 else None,
                "rate": (delta / v0) if v0 else None,
            }
        )
    return out


def growth_over_window(
    snapshots: Sequence[dict[str, Any]],
    metric: str,
    hours: float,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Crescita di una metrica nelle ultime ``hours`` ore.

    Confronta l'ultimo valore con il primo snapshot che cade dentro la
    finestra ``[now - hours, now]``. Se non ci sono almeno 2 punti nella
    finestra, ripiega sull'ultimo punto prima della finestra come base.
    Ritorna ``None`` se non calcolabile. Funzione pura (``now`` iniettabile).
    """
    points = _sorted_points(snapshots, metric)
    if len(points) < 2:
        return None

    ref_now = _as_utc(now) if now else points[-1][0]
    window_start = ref_now - timedelta(hours=hours)

    # Base: ultimo punto <= window_start, altrimenti il primo punto disponibile.
    base_idx = 0
    for i, (t, _) in enumerate(points):
        if t <= window_start:
            base_idx = i
        else:
            break
    t0, v0 = points[base_idx]
    t1, v1 = points[-1]
    if t1 <= t0:
        return None

    delta = v1 - v0
    span_hours = (t1 - t0).total_seconds() / 3600.0
    return {
        "window_hours": hours,
        "from": t0,
        "to": t1,
        "from_value": v0,
        "to_value": v1,
        "delta": delta,
        "hours": span_hours,
        "per_hour": (delta / span_hours) if span_hours > 0 else None,
        "rate": (delta / v0) if v0 else None,
    }


def compute_growth_metrics(
    snapshots: Sequence[dict[str, Any]],
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Riassunto crescita per un gioco su tutte le finestre canoniche.

    Ritorna un dict con, per ``total_reviews`` e ``current_players``:
    la crescita h24/h48/w1/m1 (rate + delta) e un ``*_growth_rate``
    sintetico (rate complessivo primo->ultimo snapshot) usato dal quality
    score. Funzione pura.
    """
    result: dict[str, Any] = {}
    for metric, short in (("total_reviews", "reviews"),
                          ("current_players", "players")):
        windows: dict[str, Any] = {}
        for name, hours in WINDOWS.items():
            windows[name] = growth_over_window(snapshots, metric, hours, now=now)
        result[f"{short}_windows"] = windows

        # Rate sintetico complessivo (primo -> ultimo punto disponibile).
        points = _sorted_points(snapshots, metric)
        overall_rate = None
        if len(points) >= 2:
            v0 = points[0][1]
            v1 = points[-1][1]
            overall_rate = (v1 - v0) / v0 if v0 else None
        result[f"{short}_growth_rate"] = overall_rate
    return result


def _slope(points: list[tuple[datetime, float]], i0: int, i1: int) -> Optional[float]:
    """Pendenza (valore/ora) tra due indici della serie."""
    t0, v0 = points[i0]
    t1, v1 = points[i1]
    hours = (t1 - t0).total_seconds() / 3600.0
    if hours <= 0:
        return None
    return (v1 - v0) / hours


def find_turning_points(
    snapshots: Sequence[dict[str, Any]],
    metric: str = "total_reviews",
    accel_factor: float = 2.0,
    min_abs_slope: float = 0.0,
) -> list[dict[str, Any]]:
    """Individua i "punti di svolta" (cambi di pendenza) in una serie.

    Un punto interno e' candidato "svolta" quando la pendenza *dopo* di
    esso accelera in modo marcato rispetto alla pendenza *prima*
    (``slope_after >= accel_factor * slope_before``, con slope_before
    positiva o quasi nulla). Questo implementa il criterio di "cambio di
    traiettoria" del playbook §4.2 (la parte di correlazione con i post
    e' gestita in reports.py).

    Parametri
    ---------
    accel_factor:
        Fattore minimo di accelerazione della pendenza per marcare la svolta.
    min_abs_slope:
        Pendenza minima (per-ora) dopo il punto per considerarlo rilevante
        (filtra il rumore su serie piatte).

    Ritorna una lista di dict ``{at, value, slope_before, slope_after,
    accel_ratio}`` ordinata per data. Funzione pura.
    """
    points = _sorted_points(snapshots, metric)
    turns: list[dict[str, Any]] = []
    if len(points) < 3:
        return turns

    for i in range(1, len(points) - 1):
        s_before = _slope(points, i - 1, i)
        s_after = _slope(points, i, i + 1)
        if s_before is None or s_after is None:
            continue
        if abs(s_after) < min_abs_slope:
            continue
        # Accelerazione: la pendenza dopo supera di accel_factor quella prima.
        # Gestisce anche il caso slope_before ~ 0 (partenza da fermo).
        baseline = max(s_before, 1e-9)
        ratio = s_after / baseline if s_before > 0 else float("inf")
        if s_after > 0 and (s_before <= 0 or ratio >= accel_factor):
            turns.append(
                {
                    "at": points[i][0],
                    "value": points[i][1],
                    "slope_before": s_before,
                    "slope_after": s_after,
                    "accel_ratio": None if ratio == float("inf") else round(ratio, 3),
                }
            )
    return turns


def follower_growth(
    social_snapshots: Sequence[dict[str, Any]],
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Crescita follower social (stessa logica delle metriche di gioco).

    Attende snapshot con ``captured_at`` e ``followers``. Ritorna le
    finestre canoniche + il rate complessivo. Funzione pura.
    """
    windows: dict[str, Any] = {}
    for name, hours in WINDOWS.items():
        windows[name] = growth_over_window(social_snapshots, "followers", hours, now=now)
    points = _sorted_points(social_snapshots, "followers")
    overall = None
    if len(points) >= 2 and points[0][1]:
        overall = (points[-1][1] - points[0][1]) / points[0][1]
    return {"followers_windows": windows, "followers_growth_rate": overall}
