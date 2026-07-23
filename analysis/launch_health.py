"""Launch Health — score composito 0-100 pre/post lancio.

Combina cinque segnali per valutare la "salute" del lancio di un gioco:

    a) Social velocity       — menzioni/giorno e tendenza (crescente/stabile/calante)
    b) Review sentiment      — trend miglioramento/peggioramento delle review
    c) Player trajectory     — tasso di crescita del player count
    d) Marketing coverage    — demo, trailer, social post PRE-lancio
    e) Quality score         — score esistente del sistema (quality_score.py)

Ciascun segnale contribuisce con un peso configurabile. I segnali mancanti
sono trattati come neutri (0.5), mai come zero — stesso principio di
quality_score.py.

Funzione principale:
    ``compute_launch_health(game_id, session) -> LaunchHealth``

Design:
- Funzione pura ``_compute_health(signals) -> (score, breakdown)`` testabile.
- Accesso al DB isolato in ``_collect_signals(game_id, session) -> dict``.
- ``LaunchHealth`` dataclass serializzabile per la GUI.

Pesi di default (configurabili):
    social_velocity: 0.25
    review_sentiment: 0.25
    player_trajectory: 0.20
    marketing_coverage: 0.15
    quality_score: 0.15
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Pesi di default
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "social_velocity": 0.25,
    "review_sentiment": 0.25,
    "player_trajectory": 0.20,
    "marketing_coverage": 0.15,
    "quality_score": 0.15,
}


# ---------------------------------------------------------------------------
# Dataclass output
# ---------------------------------------------------------------------------


@dataclass
class SignalBreakdown:
    """Dettaglio di un singolo segnale del launch health."""

    name: str
    raw_value: Optional[float]     # Valore grezzo (es. mentions/day)
    normalized: float              # Valore normalizzato 0-1
    weight: float                  # Peso nel calcolo composito
    contribution: float            # normalized * weight * 100
    available: bool                # False se il dato e' assente (neutro usato)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LaunchHealth:
    """Score di salute del lancio composito 0-100.

    Ogni segnale ha il proprio ``SignalBreakdown`` per il drill-down nella GUI.
    """

    game_id: int
    score: float                            # 0-100
    signals: list[SignalBreakdown] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    label: str = ""                         # "Excellent" / "Good" / "Fair" / "At Risk"

    def to_dict(self) -> dict[str, Any]:
        """Serializza in un dict json-friendly."""
        return {
            "game_id": self.game_id,
            "score": self.score,
            "label": self.label,
            "weights": self.weights,
            "signals": [
                {
                    "name": s.name,
                    "raw_value": s.raw_value,
                    "normalized": round(s.normalized, 4),
                    "weight": s.weight,
                    "contribution": round(s.contribution, 2),
                    "available": s.available,
                    "detail": s.detail,
                }
                for s in self.signals
            ],
        }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _log_norm(value: Optional[float], ref: float) -> float:
    """Normalizza su [0,1] con scala logaritmica (stessa logica di quality_score)."""
    if value is None or value <= 0 or ref <= 0:
        return 0.0
    return _clamp01(math.log1p(value) / math.log1p(ref))


def _health_label(score: float) -> str:
    """Etichetta leggibile basata sullo score."""
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "At Risk"


# ---------------------------------------------------------------------------
# Calcolo dei singoli segnali (funzioni pure)
# ---------------------------------------------------------------------------


def _score_social_velocity(
    posts: list[dict[str, Any]],
    release_date: Optional[datetime],
    *,
    window_days: int = 30,
    ref_mentions_per_day: float = 5.0,
) -> SignalBreakdown:
    """Velocita' delle menzioni social (menzioni/giorno nell'ultima finestra).

    Considera i post nell'arco di ``window_days`` giorni prima della data di
    riferimento (lancio o oggi se non ancora uscito). Calcola anche il trend
    confrontando la prima meta' con la seconda meta' della finestra.
    """
    now = datetime.now(timezone.utc)
    ref = release_date or now
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    window_start = ref - timedelta(days=window_days)

    recent_posts = [
        p for p in posts
        if p.get("posted_at") and _as_utc(p["posted_at"]) >= window_start
    ]
    n = len(recent_posts)
    mentions_per_day = n / window_days if window_days > 0 else 0.0

    # Trend: confronta prima vs seconda meta' della finestra.
    mid = window_start + timedelta(days=window_days / 2)
    first_half = [p for p in recent_posts if _as_utc(p["posted_at"]) < mid]
    second_half = [p for p in recent_posts if _as_utc(p["posted_at"]) >= mid]
    trend_direction: str
    if len(first_half) + len(second_half) < 2:
        trend_direction = "unknown"
    elif len(second_half) >= len(first_half):
        trend_direction = "increasing" if len(second_half) > len(first_half) else "stable"
    else:
        trend_direction = "declining"

    normalized = _log_norm(mentions_per_day, ref_mentions_per_day)
    # Bonus/malus per trend.
    if trend_direction == "increasing":
        normalized = _clamp01(normalized * 1.15)
    elif trend_direction == "declining" and normalized > 0:
        normalized = _clamp01(normalized * 0.85)

    return SignalBreakdown(
        name="social_velocity",
        raw_value=round(mentions_per_day, 3),
        normalized=normalized,
        weight=0.0,  # viene impostato dal chiamante
        contribution=0.0,
        available=len(posts) > 0,
        detail={
            "n_posts_in_window": n,
            "window_days": window_days,
            "trend_direction": trend_direction,
            "first_half_posts": len(first_half),
            "second_half_posts": len(second_half),
        },
    )


def _score_review_sentiment(
    snapshots: list[dict[str, Any]],
    *,
    recent_days: int = 60,
) -> SignalBreakdown:
    """Trend del sentiment delle review (miglioramento vs peggioramento).

    Confronta la % di positive nell'ultimo snapshot vs nello snapshot di
    ``recent_days`` fa (o il piu' vecchio disponibile).
    """
    if not snapshots:
        return SignalBreakdown(
            name="review_sentiment",
            raw_value=None,
            normalized=0.5,
            weight=0.0,
            contribution=0.0,
            available=False,
            detail={"reason": "no_snapshots"},
        )

    now = datetime.now(timezone.utc)
    ordered = sorted(
        [s for s in snapshots if s.get("captured_at") is not None],
        key=lambda s: _as_utc(s["captured_at"]),
    )

    latest = ordered[-1]
    pct_latest = _pct_positive(latest)

    cutoff = now - timedelta(days=recent_days)
    older = [s for s in ordered if _as_utc(s["captured_at"]) <= cutoff]
    pct_old = _pct_positive(older[0] if older else ordered[0]) if len(ordered) >= 2 else None

    trend_delta: Optional[float] = None
    if pct_latest is not None and pct_old is not None:
        trend_delta = pct_latest - pct_old

    # Normalizzazione: % positive centrata su 0.7 (70% positive = neutro).
    if pct_latest is None:
        normalized = 0.5
        available = False
    else:
        # 0-1 basato sulla % positive, con bonus/malus trend.
        base = _clamp01(pct_latest)
        if trend_delta is not None:
            # Trend positivo/negativo: +/- fino a 0.1 di bonus/malus.
            base = _clamp01(base + trend_delta * 0.5)
        normalized = base
        available = True

    return SignalBreakdown(
        name="review_sentiment",
        raw_value=round(pct_latest, 4) if pct_latest is not None else None,
        normalized=normalized,
        weight=0.0,
        contribution=0.0,
        available=available,
        detail={
            "pct_positive_latest": pct_latest,
            "pct_positive_old": pct_old,
            "trend_delta": round(trend_delta, 4) if trend_delta is not None else None,
            "n_snapshots": len(ordered),
        },
    )


def _score_player_trajectory(
    snapshots: list[dict[str, Any]],
    *,
    ref_growth_rate: float = 0.20,
) -> SignalBreakdown:
    """Traiettoria del player count (tasso di crescita relativo).

    Usa il tasso di crescita tra il primo e l'ultimo snapshot con player
    count disponibile. 0 = piatto; positivo = crescita; negativo = declino.
    """
    points = [
        (_as_utc(s["captured_at"]), s["current_players"])
        for s in snapshots
        if s.get("captured_at") and s.get("current_players") is not None
    ]
    points.sort(key=lambda p: p[0])

    if len(points) < 2:
        return SignalBreakdown(
            name="player_trajectory",
            raw_value=None,
            normalized=0.5,
            weight=0.0,
            contribution=0.0,
            available=False,
            detail={"reason": "insufficient_points"},
        )

    first_val = points[0][1]
    last_val = points[-1][1]
    growth_rate: Optional[float] = None
    if first_val and first_val > 0:
        growth_rate = (last_val - first_val) / first_val
    else:
        growth_rate = 0.0

    # Centra su 0.5: crescita nulla = neutro, crescita > ref_growth_rate = 1.
    normalized = _clamp01(0.5 + growth_rate / (ref_growth_rate * 2.0))

    return SignalBreakdown(
        name="player_trajectory",
        raw_value=round(growth_rate, 4),
        normalized=normalized,
        weight=0.0,
        contribution=0.0,
        available=True,
        detail={
            "first_players": int(points[0][1]),
            "last_players": int(points[-1][1]),
            "growth_rate": round(growth_rate, 4),
            "n_points": len(points),
        },
    )


def _score_marketing_coverage(
    game_data: dict[str, Any],
    posts: list[dict[str, Any]],
    release_date: Optional[datetime],
) -> SignalBreakdown:
    """Copertura marketing pre-lancio.

    Segnali:
    - Demo disponibile          (peso 1)
    - Trailer presente          (peso 1)
    - Post social pre-lancio    (peso 1 se >= 3 post prima della release)
    - Immagine header presente  (peso 0.5)
    """
    has_demo = bool(game_data.get("has_demo"))
    has_trailer = bool(game_data.get("has_trailer"))
    has_header = bool(game_data.get("header_image"))

    pre_launch_posts = 0
    if release_date:
        ref = release_date.replace(tzinfo=timezone.utc) if release_date.tzinfo is None else release_date
        pre_launch_posts = sum(
            1 for p in posts
            if p.get("posted_at") and _as_utc(p["posted_at"]) < ref
        )

    parts: list[float] = [
        1.0 if has_demo else 0.0,
        1.0 if has_trailer else 0.0,
        1.0 if pre_launch_posts >= 3 else (pre_launch_posts / 3.0),
        1.0 if has_header else 0.0,
    ]
    normalized = sum(parts) / len(parts)

    return SignalBreakdown(
        name="marketing_coverage",
        raw_value=round(normalized, 4),
        normalized=normalized,
        weight=0.0,
        contribution=0.0,
        available=True,
        detail={
            "has_demo": has_demo,
            "has_trailer": has_trailer,
            "has_header_image": has_header,
            "pre_launch_posts": pre_launch_posts,
        },
    )


def _score_quality(quality_score: Optional[float]) -> SignalBreakdown:
    """Contributo del quality score esistente (normalizzato su [0,1])."""
    if quality_score is None:
        return SignalBreakdown(
            name="quality_score",
            raw_value=None,
            normalized=0.5,
            weight=0.0,
            contribution=0.0,
            available=False,
            detail={"reason": "not_yet_calculated"},
        )
    normalized = _clamp01(quality_score / 100.0)
    return SignalBreakdown(
        name="quality_score",
        raw_value=quality_score,
        normalized=normalized,
        weight=0.0,
        contribution=0.0,
        available=True,
        detail={"quality_score": quality_score},
    )


# ---------------------------------------------------------------------------
# Funzione pura di calcolo composito
# ---------------------------------------------------------------------------


def _compute_health(
    signals: dict[str, SignalBreakdown],
    weights: dict[str, float],
) -> tuple[float, list[SignalBreakdown]]:
    """Calcola lo score composito da un dict di segnali e pesi (FUNZIONE PURA).

    Ritorna ``(score_0_100, lista_signal_breakdown_con_contribution)``.
    """
    total_w = sum(weights.values()) or 1.0
    score_raw = 0.0
    out_signals: list[SignalBreakdown] = []

    for name, breakdown in signals.items():
        w = weights.get(name, 0.0)
        breakdown.weight = w
        contribution = breakdown.normalized * w / total_w * 100.0
        breakdown.contribution = round(contribution, 2)
        score_raw += breakdown.normalized * w
        out_signals.append(breakdown)

    score = _clamp01(score_raw / total_w) * 100.0
    return round(score, 2), out_signals


# ---------------------------------------------------------------------------
# Helper di accesso ai dati
# ---------------------------------------------------------------------------


def _as_utc(dt: Any) -> datetime:
    """Rende un datetime timezone-aware in UTC."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _pct_positive(snap: dict[str, Any]) -> Optional[float]:
    """Calcola % positive da un snapshot dict."""
    total = snap.get("total_reviews")
    positive = snap.get("total_positive")
    if not total or total == 0:
        return None
    return (positive or 0) / total


# ---------------------------------------------------------------------------
# Raccolta dati dal DB
# ---------------------------------------------------------------------------


def _collect_signals(game_id: int, session) -> dict[str, Any]:
    """Raccoglie i dati necessari dal DB per calcolare il launch health.

    Ritorna un dict con tutti i dati grezzi (non calcolati).
    """
    from sqlalchemy import select, desc

    from core.models import Game, GameSnapshot, SocialPost

    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game id={game_id} non trovato")

    snaps = list(
        session.scalars(
            select(GameSnapshot)
            .where(GameSnapshot.game_id == game_id)
            .order_by(GameSnapshot.captured_at)
        )
    )
    posts = list(
        session.scalars(
            select(SocialPost).where(SocialPost.game_id == game_id)
        )
    )

    latest_snap = snaps[-1] if snaps else None
    extra = (latest_snap.extra if latest_snap and latest_snap.extra else {}) or {}

    snap_dicts = [
        {
            "captured_at": s.captured_at,
            "current_players": s.current_players,
            "total_reviews": s.total_reviews,
            "total_positive": s.total_positive,
        }
        for s in snaps
    ]
    post_dicts = [
        {
            "posted_at": p.posted_at,
            "platform": p.platform,
            "likes": p.likes,
            "comments": p.comments,
        }
        for p in posts
    ]

    release_dt: Optional[datetime] = None
    if game.release_date:
        from datetime import datetime as _dt
        release_dt = _dt(
            game.release_date.year,
            game.release_date.month,
            game.release_date.day,
            tzinfo=timezone.utc,
        )

    return {
        "game": {
            "has_demo": game.has_demo,
            "has_trailer": bool(extra.get("has_trailer")),
            "header_image": game.header_image,
            "quality_score": game.quality_score,
        },
        "snapshots": snap_dicts,
        "posts": post_dicts,
        "release_date": release_dt,
    }


# ---------------------------------------------------------------------------
# Funzione pubblica principale
# ---------------------------------------------------------------------------


def compute_launch_health(
    game_id: int,
    session,
    weights: Optional[dict[str, float]] = None,
) -> LaunchHealth:
    """Calcola il launch health score composito per un gioco.

    Non solleva: in caso di errore DB ritorna un LaunchHealth con score 0.0.

    Parametri
    ---------
    game_id:
        ID del gioco nel DB.
    session:
        Sessione SQLAlchemy attiva.
    weights:
        Pesi custom (default: ``DEFAULT_WEIGHTS``).

    Ritorna
    -------
    ``LaunchHealth`` dataclass con score 0-100 e breakdown per segnale.
    """
    w = dict(weights or DEFAULT_WEIGHTS)

    try:
        raw = _collect_signals(game_id, session)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "compute_launch_health game_id=%s: errore raccolta dati: %s",
            game_id, exc,
        )
        return LaunchHealth(
            game_id=game_id,
            score=0.0,
            label="At Risk",
            weights=w,
        )

    release_date: Optional[datetime] = raw["release_date"]
    game_data = raw["game"]
    snap_dicts = raw["snapshots"]
    post_dicts = raw["posts"]

    # Calcola i singoli segnali.
    signals: dict[str, SignalBreakdown] = {
        "social_velocity": _score_social_velocity(post_dicts, release_date),
        "review_sentiment": _score_review_sentiment(snap_dicts),
        "player_trajectory": _score_player_trajectory(snap_dicts),
        "marketing_coverage": _score_marketing_coverage(
            game_data, post_dicts, release_date
        ),
        "quality_score": _score_quality(game_data.get("quality_score")),
    }

    score, signal_list = _compute_health(signals, w)
    return LaunchHealth(
        game_id=game_id,
        score=score,
        signals=signal_list,
        weights=w,
        label=_health_label(score),
    )
