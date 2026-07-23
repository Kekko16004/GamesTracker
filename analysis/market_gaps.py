"""Market gap finder — combinazioni genere/meccanica sottoservite.

Analizza il corpus di giochi raccolti per individuare dove c'e' alta
domanda (player count + social engagement) ma bassa offerta (pochi titoli)
per un dato genere/tag.

Usa i benchmark di ``genre_benchmarks.py`` come riferimento per la "domanda
attesa" di un genere, e confronta con i dati reali del corpus.

Funzione principale:
    ``find_market_gaps(session) -> list[MarketGap]``

Design:
- PURO il calcolo: opera su snapshot gia' estratti, senza side-effect.
- L'accesso al DB e' isolato nella funzione ``find_market_gaps`` che raccoglie
  i dati e delega il calcolo alla funzione pura ``compute_gaps``.
- Output: lista di ``MarketGap`` dataclass, ordinata per opportunity_score DESC.

Concetti:
- ``supply``:        numero di giochi in quel genere nel corpus.
- ``avg_quality``:   qualita' media (quality_score) dei giochi del genere.
- ``demand_signal``: segnale di domanda relativo (media log-norm player+review).
- ``competition_level``: "low" / "medium" / "high" basato sulla supply.
- ``opportunity_score``: punteggio composito 0-100 (alta domanda, bassa supply,
                         bassa qualita' media -> grande opportunita').
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from analysis.genre_benchmarks import GENRE_BENCHMARKS, matched_genres


# ---------------------------------------------------------------------------
# Dataclass output
# ---------------------------------------------------------------------------


@dataclass
class MarketGap:
    """Opportunita' di mercato per un genere/tag.

    Tutti i campi numerici sono arrotondati per la leggibilita'.
    """

    genre: str
    game_count: int                     # N. giochi nel corpus per questo genere
    avg_quality_score: Optional[float]  # Qualita' media (0-100), None se vuoto
    competition_level: str              # "low" | "medium" | "high"
    demand_signal: float                # 0-1: quanto e' "richiesto" il genere
    opportunity_score: float            # 0-100: quanto e' appetibile il gap
    benchmark_median_reviews: int       # Benchmark di riferimento del genere
    game_ids: list[int] = field(default_factory=list)  # ID dei giochi nel corpus


# ---------------------------------------------------------------------------
# Calcolo puro
# ---------------------------------------------------------------------------


def _log_norm(value: float, ref: float) -> float:
    """Normalizza un valore su [0,1] con scala logaritmica."""
    if value <= 0 or ref <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(ref))


def _competition_level(count: int) -> str:
    """Livello di competizione in base al numero di giochi del genere."""
    if count <= 3:
        return "low"
    if count <= 10:
        return "medium"
    return "high"


def compute_gaps(
    genre_data: dict[str, dict[str, Any]],
    *,
    ref_players: float = 5000.0,
    ref_reviews: float = 2000.0,
    supply_penalty_ref: float = 15.0,
) -> list[MarketGap]:
    """Calcola le opportunita' di mercato da dati gia' aggregati (FUNZIONE PURA).

    Parametri
    ---------
    genre_data:
        Dict ``{genre: {game_count, avg_quality, avg_players, avg_reviews,
        game_ids, benchmark_median_reviews}}``.
    ref_players:
        Valore di riferimento per log-normalizzare avg_players.
    ref_reviews:
        Valore di riferimento per log-normalizzare avg_reviews.
    supply_penalty_ref:
        N. di giochi oltre il quale il mercato e' considerato saturo.

    Ritorna
    -------
    Lista di ``MarketGap`` ordinata per opportunity_score DESC.
    """
    gaps: list[MarketGap] = []

    for genre, info in genre_data.items():
        game_count = info.get("game_count", 0)
        avg_quality = info.get("avg_quality")
        avg_players = info.get("avg_players") or 0.0
        avg_reviews = info.get("avg_reviews") or 0.0
        game_ids = info.get("game_ids") or []
        bm_reviews = info.get("benchmark_median_reviews", 400)

        # --- Demand signal (0-1) ---
        # Combina player count e review count normalizzati.
        d_players = _log_norm(avg_players, ref_players)
        d_reviews = _log_norm(avg_reviews, ref_reviews)
        # Confronta anche con il benchmark del genere: se il benchmark
        # suggerisce alta domanda ma il corpus e' scarso, e' un segnale forte.
        bm_norm = _log_norm(bm_reviews, ref_reviews)
        demand_signal = round((0.40 * d_players + 0.35 * d_reviews + 0.25 * bm_norm), 4)

        # --- Supply factor (0-1): penalizza generi gia' saturi ---
        supply_factor = max(0.0, 1.0 - _log_norm(game_count, supply_penalty_ref))

        # --- Quality gap (0-1): bassa qualita' media -> maggior spazio ---
        if avg_quality is not None:
            quality_gap = max(0.0, 1.0 - avg_quality / 100.0)
        else:
            quality_gap = 0.5  # neutro se non abbiamo dati

        # --- Opportunity score 0-100 ---
        # Alta domanda + bassa supply + bassa qualita' esistente = opportunita'
        raw = (
            0.45 * demand_signal
            + 0.35 * supply_factor
            + 0.20 * quality_gap
        )
        opportunity_score = round(min(100.0, raw * 100.0), 2)

        competition = _competition_level(game_count)

        gaps.append(MarketGap(
            genre=genre,
            game_count=game_count,
            avg_quality_score=round(avg_quality, 2) if avg_quality is not None else None,
            competition_level=competition,
            demand_signal=demand_signal,
            opportunity_score=opportunity_score,
            benchmark_median_reviews=bm_reviews,
            game_ids=game_ids,
        ))

    # Ordina per opportunity_score DESC, poi per demand_signal DESC come spareggio.
    gaps.sort(key=lambda g: (-g.opportunity_score, -g.demand_signal, g.genre))
    return gaps


# ---------------------------------------------------------------------------
# Accesso al DB (sottile, isolato)
# ---------------------------------------------------------------------------


def _aggregate_by_genre(
    games: list[Any],
    snapshots_by_game: dict[int, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Aggrega i giochi del corpus per genere.

    Ritorna un dict ``{genre: {game_count, avg_quality, avg_players,
    avg_reviews, game_ids, benchmark_median_reviews}}``.
    """
    genre_map: dict[str, dict[str, Any]] = {}

    for game in games:
        genres_raw = list(game.genres or []) + list(game.tags or [])
        canonical_genres = matched_genres(game.genres, game.tags)
        if not canonical_genres:
            continue  # Genere non riconosciuto: non contribuisce all'analisi.

        # Ultimo snapshot per player/review count.
        snaps = snapshots_by_game.get(game.id, [])
        last_snap = snaps[-1] if snaps else None
        avg_players = float(last_snap.get("current_players") or 0) if last_snap else 0.0
        avg_reviews = float(last_snap.get("total_reviews") or 0) if last_snap else 0.0

        quality = game.quality_score  # None se non ancora calcolato.

        for genre in canonical_genres:
            bm = GENRE_BENCHMARKS.get(genre)
            bm_reviews = bm.median_review_count if bm else 400

            if genre not in genre_map:
                genre_map[genre] = {
                    "game_count": 0,
                    "quality_sum": 0.0,
                    "quality_n": 0,
                    "players_sum": 0.0,
                    "reviews_sum": 0.0,
                    "game_ids": [],
                    "benchmark_median_reviews": bm_reviews,
                }
            gd = genre_map[genre]
            gd["game_count"] += 1
            gd["players_sum"] += avg_players
            gd["reviews_sum"] += avg_reviews
            gd["game_ids"].append(game.id)
            if quality is not None:
                gd["quality_sum"] += quality
                gd["quality_n"] += 1

    # Calcola medie.
    result: dict[str, dict[str, Any]] = {}
    for genre, gd in genre_map.items():
        n = gd["game_count"]
        qn = gd["quality_n"]
        result[genre] = {
            "game_count": n,
            "avg_quality": gd["quality_sum"] / qn if qn > 0 else None,
            "avg_players": gd["players_sum"] / n if n > 0 else 0.0,
            "avg_reviews": gd["reviews_sum"] / n if n > 0 else 0.0,
            "game_ids": gd["game_ids"],
            "benchmark_median_reviews": gd["benchmark_median_reviews"],
        }
    return result


def find_market_gaps(
    session,
    *,
    min_games: int = 1,
    ref_players: float = 5000.0,
    ref_reviews: float = 2000.0,
    supply_penalty_ref: float = 15.0,
) -> list[MarketGap]:
    """Analizza il corpus e ritorna le opportunita' di mercato per genere.

    Parametri
    ---------
    session:
        Sessione SQLAlchemy attiva.
    min_games:
        Includi solo generi con almeno questo numero di giochi nel corpus.
    ref_players / ref_reviews:
        Valori di riferimento per la log-normalizzazione del demand signal.
    supply_penalty_ref:
        N. di giochi oltre il quale il genere e' considerato saturo.

    Ritorna
    -------
    Lista di ``MarketGap`` ordinata per opportunity_score DESC.
    """
    from sqlalchemy import select
    from core.models import Game, GameSnapshot

    # Carica tutti i giochi non scartati.
    games = list(
        session.scalars(
            select(Game).where(Game.discarded.is_(False))
        )
    )

    if not games:
        return []

    # Ultimi snapshot per player/review count.
    game_ids = [g.id for g in games]
    all_snaps = list(
        session.scalars(
            select(GameSnapshot)
            .where(GameSnapshot.game_id.in_(game_ids))
            .order_by(GameSnapshot.game_id, GameSnapshot.captured_at)
        )
    )

    # Raggruppa snapshot per game_id (gia' ordinati).
    snapshots_by_game: dict[int, list[dict[str, Any]]] = {}
    for snap in all_snaps:
        snapshots_by_game.setdefault(snap.game_id, []).append({
            "captured_at": snap.captured_at,
            "current_players": snap.current_players,
            "total_reviews": snap.total_reviews,
        })

    # Aggrega per genere.
    genre_data = _aggregate_by_genre(games, snapshots_by_game)

    # Filtra generi con troppo pochi giochi.
    genre_data = {
        g: d for g, d in genre_data.items()
        if d["game_count"] >= min_games
    }

    return compute_gaps(
        genre_data,
        ref_players=ref_players,
        ref_reviews=ref_reviews,
        supply_penalty_ref=supply_penalty_ref,
    )
