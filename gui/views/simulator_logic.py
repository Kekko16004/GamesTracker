"""Logica pura del Simulatore Quality Score (nessuna dipendenza PyQt6).

Separata dalla view (``simulator.py``) cosi' e' testabile senza
``QApplication``: costruisce il dizionario ``game_data`` a partire dai
valori grezzi del form e delega il calcolo alla funzione pura
``analysis.quality_score.compute_quality_score``.

Il simulatore serve al dev per valutare la SUA pagina/gioco PRIMA della
pubblicazione: raccoglie solo i segnali che un autore puo' conoscere e
lascia neutri (``None``) quelli non compilati, coerentemente con la
semantica anti-trash dello score (dato mancante = neutro, non zero).
"""

from __future__ import annotations

from typing import Any, Optional

from analysis.quality_score import compute_quality_score

# Elenco delle penalita' che lo score puo' emettere: le chiavi i18n
# corrispondenti sono ``simulator.penalty.<nome>`` (vedi strings.py).
KNOWN_PENALTIES: tuple[str, ...] = (
    "no_screenshots_and_no_trailer",
    "no_screenshots",
    "no_trailer",
    "empty_or_placeholder_description",
    "asset_flip_tags",
    "suspicious_social_engagement",
    "probable_shovelware_zero_content",
)


def _split_terms(raw: Optional[str]) -> list[str]:
    """Divide una stringa "a, b, c" in una lista pulita di termini."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def build_game_data_from_inputs(
    *,
    description: str = "",
    screenshot_count: int = 0,
    has_trailer: bool = False,
    has_header_image: bool = True,
    genres: Optional[str] = None,
    tags: Optional[str] = None,
    price: Optional[float] = None,
    is_free: bool = False,
    has_demo: bool = False,
    developer_other_games: bool = False,
    has_official_site: bool = False,
    review_pct_positive: Optional[float] = None,
    review_count: Optional[int] = None,
    social_active_platforms: Optional[int] = None,
    social_post_count: Optional[int] = None,
) -> dict[str, Any]:
    """Costruisce il dict ``game_data`` per ``compute_quality_score``.

    Parametri (tutti opzionali, con valori sensati per un dev):

    - ``description``: testo della descrizione (ne calcoliamo la lunghezza).
    - ``screenshot_count``: numero di screenshot nella pagina store.
    - ``has_trailer`` / ``has_header_image``: presenza di trailer / copertina.
    - ``genres`` / ``tags``: stringhe separate da virgola.
    - ``price`` / ``is_free``: prezzo (se non gratis) e flag gratis.
    - ``has_demo`` / ``developer_other_games`` / ``has_official_site``:
      segnali di cura.
    - ``review_pct_positive`` (0-100) e ``review_count``: recensioni STIMATE.
      Se il conteggio e' assente o 0, le recensioni restano neutre (0.5),
      come per un gioco pre-release.
    - ``social_active_platforms`` / ``social_post_count``: dati social
      opzionali. ``None`` = non specificato -> neutro.

    La pagina e' sempre marcata ``store_inspected=True``: il dev conosce la
    propria pagina, quindi trailer/screenshot mancanti sono segnali reali.
    """
    # --- store ---
    store: dict[str, Any] = {
        "store_inspected": True,
        "has_trailer": bool(has_trailer),
        "screenshot_count": int(screenshot_count or 0),
        "description_length": len(description or ""),
        "genres": _split_terms(genres),
        "tags": _split_terms(tags),
        "header_image": "header" if has_header_image else None,
    }

    # --- reviews (stime del dev) ---
    if review_count and review_count > 0:
        total = int(review_count)
        pct = review_pct_positive if review_pct_positive is not None else 0.0
        pct = max(0.0, min(100.0, float(pct)))
        positive = round(total * pct / 100.0)
        reviews: dict[str, Any] = {
            "total_reviews": total,
            "total_positive": positive,
            "total_negative": total - positive,
            "review_score_desc": None,
        }
    else:
        # Nessuna stima -> neutro (pre-release).
        reviews = {
            "total_reviews": None,
            "total_positive": None,
            "total_negative": None,
            "review_score_desc": None,
        }

    # --- social (opzionale) ---
    social: dict[str, Any] = {
        "active_platforms": social_active_platforms,
        "mentions_engagement": None,
        "post_count": social_post_count,
        "follower_trend": None,
        "suspicious_engagement": None,
    }

    # --- growth: non stimabile pre-release -> neutro ---
    growth: dict[str, Any] = {
        "reviews_growth_rate": None,
        "players_growth_rate": None,
    }

    # --- care ---
    care: dict[str, Any] = {
        "has_demo": bool(has_demo),
        # developer_other_games: bool -> credito parziale (spec bool|None).
        "developer_other_games": True if developer_other_games else None,
        "price": None if is_free else price,
        "is_free": bool(is_free),
        "has_official_site": True if has_official_site else None,
    }

    return {
        "store": store,
        "reviews": reviews,
        "social": social,
        "growth": growth,
        "care": care,
    }


def simulate(**inputs: Any) -> tuple[float, dict[str, Any]]:
    """Costruisce ``game_data`` dagli input e calcola score + breakdown.

    Scorciatoia comoda per la view e i test: accetta gli stessi keyword
    di :func:`build_game_data_from_inputs` e ritorna ``(score, breakdown)``.
    """
    game_data = build_game_data_from_inputs(**inputs)
    return compute_quality_score(game_data)
