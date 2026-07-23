"""Quality score 0-100 anti-trash per GamesTracker.

Implementa lo score descritto in ``.claude/reference/quality-score.md``:
somma pesata di 5 componenti normalizzate 0-1 (poi x100), piu' penalita'
e flag "trash".

Design:
- ``compute_quality_score(game_data, weights=None) -> (score, breakdown)``
  e' una **funzione pura**: input = dati gia' estratti, output = punteggio
  e dettaglio per componente (per spiegarlo nella GUI). Nessun accesso al
  DB, nessuna rete.
- ``build_game_data(session, game_id)`` estrae dal DB la struttura che la
  funzione pura si aspetta.
- ``score_game(session, game_id, ...)`` fa il giro completo: carica,
  calcola, aggiorna ``games.quality_score`` e ``games.discarded``.

I pesi sono CONFIGURABILI: ``DEFAULT_WEIGHTS`` e' un dizionario
sovrascrivibile passato alla funzione pura. La taratura scelta e le note
di validazione sono documentate in fondo al modulo.

Regole trasversali (dal playbook e dalla spec):
- Dati mancanti = **neutro**, non zero (non penalizzare la mancata
  raccolta, es. TikTok/IG).
- Conteggi (recensioni, menzioni, follower) **log-scalati** prima di
  normalizzare, cosi' un singolo outlier non schiaccia gli altri.
- Le stime SteamSpy sono approssimative: usate solo come segnale debole.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# --- Pesi delle 5 componenti principali (sommano a 1.0) -------------------
# Allineati a quality-score.md. Sovrascrivibili passando un dict a
# compute_quality_score(weights=...).
DEFAULT_WEIGHTS: dict[str, float] = {
    "store_page": 0.25,   # qualita' pagina store
    "reviews": 0.30,      # reception recensioni
    "social": 0.20,       # engagement social
    "growth": 0.15,       # crescita / traiettoria
    "care": 0.10,         # segnali di cura
}

# Pesi interni della componente social (dal marketing-playbook §5.1).
DEFAULT_SOCIAL_SUBWEIGHTS: dict[str, float] = {
    "active_accounts": 0.25,   # presenza account attivi
    "mentions": 0.35,          # menzioni Reddit/YouTube (log-scala)
    "post_volume": 0.20,       # volume/cadenza post (log-scala)
    "follower_trend": 0.20,    # traiettoria follower
}

# Valori di riferimento per la log-normalizzazione.
# TARATI sul corpus reale (76 giochi, discovery 2026-07-21): il precedente
# REF_REVIEWS=2000 era ~= p75 reale (2101) e faceva saturare il segnale
# volume (un gioco mediano da ~880 recensioni gia' prendeva ~0.9). Alzato al
# ~p95 del corpus Steam (~24k) cosi' il volume differenzia davvero i giochi.
# I riferimenti social restano provvisori finche' non arrivano dati social
# reali (oggi la componente social e' neutra 0.5 per assenza di dati).
REF_REVIEWS = 24000.0       # ~p95 del corpus Steam (era 2000, saturava)
REF_MENTIONS_ENGAGEMENT = 5000.0  # provvisorio: nessun dato social ancora
REF_POST_COUNT = 60.0       # provvisorio: nessun dato social ancora

# Soglia di default sotto cui un gioco viene scartato (allineata a
# core.config.Settings.quality_score_threshold).
DEFAULT_DISCARD_THRESHOLD = 40.0


@dataclass
class Breakdown:
    """Dettaglio per componente del quality score (per la GUI)."""

    components: dict[str, float] = field(default_factory=dict)
    """Sotto-punteggi 0-1 per componente (prima del peso)."""
    weighted: dict[str, float] = field(default_factory=dict)
    """Contributo pesato di ciascuna componente (0-100)."""
    social_detail: dict[str, float] = field(default_factory=dict)
    """Dettaglio dei 4 sotto-segnali social (0-1)."""
    penalties: list[str] = field(default_factory=list)
    """Elenco leggibile delle penalita'/flag trash applicate."""
    penalty_factor: float = 1.0
    """Fattore moltiplicativo finale (1.0 = nessuna penalita')."""
    flags: dict[str, bool] = field(default_factory=dict)
    """Flag booleani (es. hard_trash) utili alla GUI."""
    weights: dict[str, float] = field(default_factory=dict)
    """Pesi effettivamente usati (per trasparenza)."""

    def to_dict(self) -> dict[str, Any]:
        """Serializza il breakdown in un dict json-friendly."""
        return {
            "components": self.components,
            "weighted": self.weighted,
            "social_detail": self.social_detail,
            "penalties": self.penalties,
            "penalty_factor": self.penalty_factor,
            "flags": self.flags,
            "weights": self.weights,
        }


# --- Helper di normalizzazione -------------------------------------------


def _clamp01(x: float) -> float:
    """Vincola un valore nell'intervallo [0, 1]."""
    return max(0.0, min(1.0, x))


def log_norm(value: Optional[float], ref: float) -> float:
    """Normalizza un conteggio in [0,1] con scala logaritmica.

    ``norm = log(1+x) / log(1+ref)``. Un valore ``None`` o negativo torna
    0.0 (assenza di segnale positivo, non penalita').
    """
    if value is None or value <= 0 or ref <= 0:
        return 0.0
    return _clamp01(math.log1p(value) / math.log1p(ref))


# --- Sotto-punteggi delle 5 componenti ------------------------------------


def _score_store_page(store: dict[str, Any]) -> float:
    """Qualita' della pagina store (0-1).

    Segnali: trailer, n. screenshot, lunghezza descrizione, tag/generi
    sensati, header image. Dati assenti pesano poco ma non sono neutri:
    una pagina senza contenuti E' un segnale negativo (spec anti-trash).

    Eccezione: se la pagina NON e' stata ispezionabile per screenshot/trailer
    (``store_inspected=False``, es. itch), quei due segnali vengono esclusi
    dalla media invece di contare 0 — altrimenti penalizzeremmo un dato che
    la piattaforma non espone (playbook §2.5).
    """
    inspected = store.get("store_inspected", True)
    parts: list[float] = []
    if inspected:
        # Trailer (0/1) — peso alto: la sua assenza e' un flag trash.
        parts.append(1.0 if store.get("has_trailer") else 0.0)
        # Screenshot: saturazione a 5+.
        shots = store.get("screenshot_count") or 0
        parts.append(_clamp01(shots / 5.0))
    # Descrizione: saturazione a ~600 caratteri (una scheda decente).
    desc_len = store.get("description_length") or 0
    if desc_len or inspected:
        parts.append(_clamp01(desc_len / 600.0))
    # Tag/generi sensati: almeno 3 tra tag+generi.
    n_tags = len(store.get("tags") or []) + len(store.get("genres") or [])
    parts.append(_clamp01(n_tags / 3.0))
    # Header image presente.
    parts.append(1.0 if store.get("header_image") else 0.0)
    return sum(parts) / len(parts) if parts else 0.5


def _score_reviews(reviews: dict[str, Any]) -> float:
    """Reception recensioni (0-1).

    Combina % positive (peso maggiore) e volume log-scalato. Se non ci
    sono ancora recensioni (pre-release o appena uscito) torna un valore
    **neutro** (0.5): assenza di dati non e' colpa del gioco.
    """
    total = reviews.get("total_reviews")
    if not total:  # None o 0 -> neutro
        return 0.5
    positive = reviews.get("total_positive") or 0
    pct_positive = positive / total if total else 0.0
    volume = log_norm(total, REF_REVIEWS)
    # 70% qualita' (% positive), 30% volume.
    return _clamp01(0.70 * pct_positive + 0.30 * volume)


def _score_social(social: dict[str, Any],
                  subweights: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Engagement social (0-1) con i 4 sotto-segnali del playbook §5.1.

    Degrada con grazia: i sotto-segnali senza dati usano un valore neutro
    (0.5) e i pesi vengono rinormalizzati su quelli disponibili, cosi' un
    dev piccolo non viene punito per l'assenza di TikTok/IG.
    """
    detail: dict[str, float] = {}

    # 1) Presenza account attivi: 0/0.5/1 secondo n. piattaforme attive.
    active = social.get("active_platforms")
    if active is None:
        detail["active_accounts"] = 0.5
    else:
        detail["active_accounts"] = _clamp01(active / 2.0)

    # 2) Menzioni Reddit/YouTube: engagement cumulato log-scalato.
    mentions_eng = social.get("mentions_engagement")
    if mentions_eng is None:
        detail["mentions"] = 0.5
    else:
        detail["mentions"] = log_norm(mentions_eng, REF_MENTIONS_ENGAGEMENT)

    # 3) Volume post: cadenza log-scalata.
    post_count = social.get("post_count")
    if post_count is None:
        detail["post_volume"] = 0.5
    else:
        detail["post_volume"] = log_norm(post_count, REF_POST_COUNT)

    # 4) Traiettoria follower: crescita positiva = premio; 1 solo snapshot
    #    o assenza dati = neutro (0.5).
    ftrend = social.get("follower_trend")
    detail["follower_trend"] = 0.5 if ftrend is None else _clamp01(ftrend)

    # Penalita' anti-spam/bot (playbook §5.3): abbassa i segnali gonfiati.
    if social.get("suspicious_engagement"):
        detail["mentions"] = min(detail["mentions"], 0.3)
        detail["follower_trend"] = min(detail["follower_trend"], 0.3)

    # Media pesata sui sotto-segnali (tutti presenti come neutri qui).
    total_w = sum(subweights.values())
    score = sum(detail[k] * w for k, w in subweights.items()) / total_w
    return _clamp01(score), detail


def _score_growth(growth: dict[str, Any]) -> float:
    """Crescita / traiettoria (0-1).

    Usa i tassi di crescita gia' calcolati (vedi growth.py). Traiettoria
    positiva = premio, piatta = neutro, negativa = leggermente sotto la
    media. Assenza dati (pre-release) = neutro (0.5).
    """
    rate = growth.get("reviews_growth_rate")
    if rate is None:
        rate = growth.get("players_growth_rate")
    if rate is None:
        return 0.5  # nessun dato di crescita ancora
    # Mappa un tasso di crescita relativo su [0,1]:
    # 0% -> 0.5 ; +50%+ -> ~1.0 ; -50%- -> ~0.0
    return _clamp01(0.5 + rate)


def _score_care(care: dict[str, Any]) -> float:
    """Segnali di cura (0-1): demo, altri giochi del dev, prezzo, sito."""
    parts: list[float] = []
    parts.append(1.0 if care.get("has_demo") else 0.0)
    # Developer con altri giochi (portfolio): saturazione a 2+.
    others = care.get("developer_other_games") or 0
    parts.append(_clamp01(others / 2.0))
    # Prezzo "non sospetto": un prezzo > 0 e' un segnale lieve di serieta'.
    # Gratis non e' negativo di per se' (molti indie validi sono free).
    price = care.get("price")
    is_free = care.get("is_free")
    if is_free:
        parts.append(0.5)  # neutro
    elif price and price > 0:
        parts.append(1.0)
    else:
        parts.append(0.5)  # prezzo sconosciuto -> neutro
    # Sito ufficiale.
    parts.append(1.0 if care.get("has_official_site") else 0.0)
    return sum(parts) / len(parts)


# --- Penalita' / flag trash ----------------------------------------------


def _apply_penalties(game_data: dict[str, Any],
                     breakdown: Breakdown) -> float:
    """Calcola il fattore di penalita' (<=1.0) e popola i flag trash.

    Segue ``quality-score.md`` §Penalita'. Alcuni pattern forzano un
    discard di fatto (fattore molto basso).
    """
    store = game_data.get("store", {})
    reviews = game_data.get("reviews", {})
    social = game_data.get("social", {})
    care = game_data.get("care", {})

    factor = 1.0
    penalties = breakdown.penalties

    no_shots = not (store.get("screenshot_count") or 0)
    no_trailer = not store.get("has_trailer")
    desc_len = store.get("description_length") or 0
    empty_desc = desc_len < 30 or bool(store.get("placeholder_description"))
    # Applica le penalita' screenshot/trailer SOLO se la pagina e' stata
    # ispezionata (Steam). Per itch quei campi non esistono: non penalizzare
    # un dato non raccoglibile (playbook §2.5).
    store_inspected = store.get("store_inspected", True)

    if store_inspected and no_shots and no_trailer:
        factor *= 0.4
        penalties.append("no_screenshots_and_no_trailer")
    elif store_inspected and no_shots:
        factor *= 0.7
        penalties.append("no_screenshots")
    elif store_inspected and no_trailer:
        factor *= 0.85
        penalties.append("no_trailer")

    if store_inspected and empty_desc:
        factor *= 0.6
        penalties.append("empty_or_placeholder_description")

    if store.get("asset_flip_tags"):
        factor *= 0.3
        penalties.append("asset_flip_tags")

    if social.get("suspicious_engagement"):
        penalties.append("suspicious_social_engagement")

    # Shovelware: prezzo 0 + zero social + zero recensioni.
    price0 = bool(care.get("is_free")) or (care.get("price") in (0, 0.0))
    zero_social = not (social.get("active_platforms") or
                       social.get("post_count") or
                       social.get("mentions_engagement"))
    zero_reviews = not (reviews.get("total_reviews") or 0)
    hard_trash = (
        store_inspected and price0 and zero_social and zero_reviews
        and (no_shots or no_trailer)
    )
    if hard_trash:
        factor *= 0.2
        penalties.append("probable_shovelware_zero_content")

    breakdown.flags["hard_trash"] = hard_trash
    breakdown.penalty_factor = round(factor, 4)
    return factor


# --- Funzione pura principale ---------------------------------------------


def compute_quality_score(
    game_data: dict[str, Any],
    weights: Optional[dict[str, float]] = None,
    social_subweights: Optional[dict[str, float]] = None,
) -> tuple[float, dict[str, Any]]:
    """Calcola il quality score 0-100 di un gioco (FUNZIONE PURA).

    Parametri
    ---------
    game_data:
        Dizionario con le chiavi ``store``, ``reviews``, ``social``,
        ``growth``, ``care`` (tutte opzionali; le mancanti diventano
        neutre). Vedi ``build_game_data`` per la struttura completa.
    weights:
        Pesi delle 5 componenti (default ``DEFAULT_WEIGHTS``). Vengono
        rinormalizzati a somma 1 se non sommano gia' a 1.
    social_subweights:
        Pesi interni della componente social (default
        ``DEFAULT_SOCIAL_SUBWEIGHTS``).

    Ritorna
    -------
    ``(score, breakdown_dict)`` dove ``score`` e' 0-100 e
    ``breakdown_dict`` e' il dettaglio json-serializzabile per la GUI.
    """
    w = dict(weights or DEFAULT_WEIGHTS)
    sw = dict(social_subweights or DEFAULT_SOCIAL_SUBWEIGHTS)
    total_w = sum(w.values()) or 1.0

    store = game_data.get("store", {}) or {}
    reviews = game_data.get("reviews", {}) or {}
    social = game_data.get("social", {}) or {}
    growth = game_data.get("growth", {}) or {}
    care = game_data.get("care", {}) or {}

    bd = Breakdown(weights=w)

    c_store = _score_store_page(store)
    c_reviews = _score_reviews(reviews)
    c_social, social_detail = _score_social(social, sw)
    c_growth = _score_growth(growth)
    c_care = _score_care(care)

    bd.components = {
        "store_page": round(c_store, 4),
        "reviews": round(c_reviews, 4),
        "social": round(c_social, 4),
        "growth": round(c_growth, 4),
        "care": round(c_care, 4),
    }
    bd.social_detail = {k: round(v, 4) for k, v in social_detail.items()}

    base = (
        c_store * w.get("store_page", 0)
        + c_reviews * w.get("reviews", 0)
        + c_social * w.get("social", 0)
        + c_growth * w.get("growth", 0)
        + c_care * w.get("care", 0)
    ) / total_w
    base_score = base * 100.0

    factor = _apply_penalties(game_data, bd)
    score = _clamp01(base_score * factor / 100.0) * 100.0

    bd.weighted = {
        "store_page": round(c_store * w.get("store_page", 0) / total_w * 100, 2),
        "reviews": round(c_reviews * w.get("reviews", 0) / total_w * 100, 2),
        "social": round(c_social * w.get("social", 0) / total_w * 100, 2),
        "growth": round(c_growth * w.get("growth", 0) / total_w * 100, 2),
        "care": round(c_care * w.get("care", 0) / total_w * 100, 2),
    }

    return round(score, 2), bd.to_dict()


# --- Estrazione dati dal DB -----------------------------------------------


def _days_ago(dt: Optional[datetime]) -> Optional[float]:
    """Giorni trascorsi da ``dt`` (timezone-aware) a ora, o None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def build_game_data(session, game_id: int,
                    recent_days: int = 90) -> dict[str, Any]:
    """Estrae dal DB la struttura ``game_data`` per il quality score.

    Import locali per evitare dipendenze circolari e mantenere pura la
    parte di calcolo. Usa ``growth.py`` per i tassi di crescita.
    """
    from sqlalchemy import select

    from core.models import (
        Game,
        GameSnapshot,
        SocialAccount,
        SocialPost,
        SocialSnapshot,
    )
    from analysis.growth import compute_growth_metrics

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
    latest = snaps[-1] if snaps else None

    # --- store ---
    extra = (latest.extra if latest and latest.extra else {}) or {}
    # "Ispezionato" = abbiamo potuto leggere screenshot/trailer dalla pagina
    # (vero per Steam via appdetails; falso per itch, che non li espone).
    # Distinguere "pagina vuota" da "dato non raccoglibile" evita di
    # penalizzare gli itch per dati che non esistono (playbook §2.5).
    store_inspected = "screenshot_count" in extra
    store = {
        "store_inspected": store_inspected,
        "has_trailer": bool(extra.get("has_trailer")),
        "screenshot_count": extra.get("screenshot_count"),
        "description_length": extra.get("description_length"),
        "genres": game.genres,
        "tags": game.tags,
        "header_image": game.header_image,
        "asset_flip_tags": extra.get("asset_flip_tags"),
        "placeholder_description": extra.get("placeholder_description"),
    }

    # --- reviews (dall'ultimo snapshot) ---
    reviews = {
        "total_reviews": latest.total_reviews if latest else None,
        "total_positive": latest.total_positive if latest else None,
        "total_negative": latest.total_negative if latest else None,
        "review_score_desc": latest.review_score_desc if latest else None,
    }

    # --- growth ---
    growth_metrics = compute_growth_metrics(
        [
            {
                "captured_at": s.captured_at,
                "total_reviews": s.total_reviews,
                "current_players": s.current_players,
            }
            for s in snaps
        ]
    )
    growth = {
        "reviews_growth_rate": growth_metrics.get("reviews_growth_rate"),
        "players_growth_rate": growth_metrics.get("players_growth_rate"),
    }

    # --- social ---
    accounts = list(
        session.scalars(
            select(SocialAccount).where(SocialAccount.game_id == game_id)
        )
    )
    posts = list(
        session.scalars(
            select(SocialPost).where(SocialPost.game_id == game_id)
        )
    )
    # Piattaforme con attivita' recente (post negli ultimi recent_days).
    active_platforms_set = set()
    mentions_engagement = 0
    for p in posts:
        age = _days_ago(p.posted_at)
        if age is not None and age <= recent_days:
            active_platforms_set.add(p.platform)
        mentions_engagement += (p.likes or 0) + (p.comments or 0) + (p.views or 0)

    # Traiettoria follower: differenza tra primo e ultimo snapshot social.
    follower_trend = None
    for acc in accounts:
        acc_snaps = list(
            session.scalars(
                select(SocialSnapshot)
                .where(SocialSnapshot.social_account_id == acc.id)
                .order_by(SocialSnapshot.captured_at)
            )
        )
        if len(acc_snaps) >= 2:
            first = acc_snaps[0].followers
            last = acc_snaps[-1].followers
            if first and last and first > 0:
                delta = (last - first) / first
                follower_trend = 0.5 + delta  # centrato su neutro

    social = {
        "active_platforms": len(active_platforms_set) if posts else None,
        "mentions_engagement": mentions_engagement if posts else None,
        "post_count": len(posts) if posts else None,
        "follower_trend": follower_trend,
        "suspicious_engagement": extra.get("suspicious_engagement"),
    }

    # --- care ---
    care = {
        "has_demo": game.has_demo,
        "developer_other_games": extra.get("developer_other_games"),
        "price": game.price,
        "is_free": game.is_free,
        "has_official_site": extra.get("has_official_site"),
    }

    return {
        "store": store,
        "reviews": reviews,
        "social": social,
        "growth": growth,
        "care": care,
    }


def score_game(
    session,
    game_id: int,
    weights: Optional[dict[str, float]] = None,
    threshold: Optional[float] = None,
    persist: bool = True,
) -> tuple[float, dict[str, Any]]:
    """Carica i dati di un gioco, calcola lo score e aggiorna il DB.

    Aggiorna ``games.quality_score`` e imposta ``games.discarded`` se lo
    score e' sotto ``threshold`` (default: ``Settings.quality_score_threshold``).
    Ritorna ``(score, breakdown)``.
    """
    from core.models import Game

    if threshold is None:
        try:
            from core.config import get_settings

            threshold = get_settings().quality_score_threshold
        except Exception:
            threshold = DEFAULT_DISCARD_THRESHOLD

    game_data = build_game_data(session, game_id)
    score, breakdown = compute_quality_score(game_data, weights=weights)

    if persist:
        game = session.get(Game, game_id)
        game.quality_score = score
        game.discarded = score < threshold
        session.flush()

    return score, breakdown


# ---------------------------------------------------------------------------
# TARATURA DEI PESI (documentazione) — vedi anche tests/test_analysis_quality.py
# ---------------------------------------------------------------------------
# Pesi finali scelti (allineati a quality-score.md, invariati perche' gia'
# frutto dell'analisi di dominio del social-marketing-analyst):
#   store_page 25% | reviews 30% | social 20% | growth 15% | care 10%
#
# Razionale:
# - reviews (30%) e' il peso maggiore: le recensioni Steam sono il proxy
#   pubblico piu' affidabile di validazione da parte dei giocatori.
# - store_page (25%): la qualita' della scheda separa nettamente i progetti
#   curati dagli asset-flip; la sua assenza fa scattare anche penalita'.
# - social (20%), growth (15%), care (10%) completano il quadro senza
#   penalizzare i dev piccoli (dati mancanti = neutro).
#
# Penalita' moltiplicative (non additive): un gioco senza screenshot NE
# trailer viene ridotto al 40%; un asset-flip conclamato al 30%; lo
# shovelware (prezzo 0 + zero social + zero recensioni + niente media) al
# 20%. Questo garantisce l'ordinamento buono > medio > trash a parita' di
# altre condizioni (validato nei test sintetici).
#
# DA RIVALIDARE SU DATI REALI:
# - I valori di riferimento della log-normalizzazione (REF_REVIEWS,
#   REF_MENTIONS_ENGAGEMENT, REF_POST_COUNT) sono costanti provvisorie:
#   vanno sostituiti con percentili (es. 95°) calcolati sul corpus reale
#   dei giochi raccolti.
# - La soglia di discard (default 40) va calibrata osservando la
#   distribuzione degli score reali (evitare falsi positivi su indie validi).
# - Le liste di "asset_flip_tags" / pattern publisher spam sono mantenute
#   dal research-scout: qui si legge solo il flag booleano.
