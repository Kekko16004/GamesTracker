"""Logica PURA del simulatore di quality score (nessuna dipendenza PyQt6).

Costruisce il dict ``game_data`` atteso da
``analysis.quality_score.compute_quality_score`` a partire da valori
semplici inseriti dall'utente nel form. Isolata qui per essere testabile
senza avviare la GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from analysis.quality_score import compute_quality_score


@dataclass
class SimulatorInputs:
    """Valori grezzi dal form del simulatore (tutti opzionali/neutri)."""

    title: str = ""
    description: str = ""
    screenshot_count: int = 0
    has_trailer: bool = False
    has_header: bool = False
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    price: float = 0.0
    is_free: bool = False
    has_demo: bool = False
    developer_other_games: bool = False
    has_official_site: bool = False
    review_pct_positive: float = 0.0     # 0-100
    review_count: int = 0
    social_platforms: int = 0
    social_post_count: int = 0


def build_game_data_from_inputs(inp: SimulatorInputs) -> dict[str, Any]:
    """Traduce gli input del form nel dict ``game_data`` del quality score.

    Regole di "dato non specificato = neutro": i conteggi lasciati a 0 (o le
    stime a 0) diventano ``None`` cosi' la relativa componente resta neutra
    (0.5) invece di penalizzare. Lo store si considera sempre ``inspected``
    (l'utente sta descrivendo la propria pagina Steam-like).
    """
    desc = inp.description or ""
    desc_len = len(desc.strip())

    store = {
        "store_inspected": True,
        "has_trailer": bool(inp.has_trailer),
        "screenshot_count": int(inp.screenshot_count or 0),
        "description_length": desc_len,
        "genres": list(inp.genres or []),
        "tags": list(inp.tags or []),
        "header_image": "x" if inp.has_header else None,
        "placeholder_description": desc_len < 30,
    }

    # Recensioni: se il conteggio stimato e' 0 -> None (neutro, pre-release).
    if inp.review_count and inp.review_count > 0:
        total = int(inp.review_count)
        positive = int(round(total * (inp.review_pct_positive or 0) / 100.0))
        reviews = {
            "total_reviews": total,
            "total_positive": positive,
            "total_negative": total - positive,
            "review_score_desc": None,
        }
    else:
        reviews = {
            "total_reviews": None,
            "total_positive": None,
            "total_negative": None,
            "review_score_desc": None,
        }

    social = {
        "active_platforms": inp.social_platforms or None,
        "mentions_engagement": None,
        "post_count": inp.social_post_count or None,
        "follower_trend": None,
        "suspicious_engagement": None,
    }

    # Crescita non simulabile a mano: resta neutra.
    growth = {"reviews_growth_rate": None, "players_growth_rate": None}

    care = {
        "has_demo": bool(inp.has_demo),
        "developer_other_games": bool(inp.developer_other_games) or None,
        "is_free": bool(inp.is_free),
        "price": 0.0 if inp.is_free else float(inp.price or 0.0),
        "has_official_site": bool(inp.has_official_site) or None,
    }

    return {
        "store": store,
        "reviews": reviews,
        "social": social,
        "growth": growth,
        "care": care,
    }


def simulate_score(inp: SimulatorInputs) -> tuple[float, dict[str, Any]]:
    """Calcola ``(score, breakdown)`` per gli input dati (funzione pura)."""
    game_data = build_game_data_from_inputs(inp)
    return compute_quality_score(game_data)
