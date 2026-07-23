"""Client OpenCritic — aggregatore recensioni critici.

Supporta due base URL:
- Diretto:  ``https://api.opencritic.com/api``  (no auth per endpoint pubblici)
- RapidAPI: ``https://opencritic-api.p.rapidapi.com`` (richiede ``RAPIDAPI_KEY``)

La variabile ``OPENCRITIC_USE_RAPIDAPI`` (default ``false``) seleziona quale
usare. Se si usa RapidAPI, ``RAPIDAPI_KEY`` e' obbligatoria; altrimenti il
modulo usa direttamente api.opencritic.com (che e' pubblicamente accessibile
per ricerche di base).

Endpoint usati:
- ``/game/search?criteria=<nome>`` — ricerca
- ``/game/{id}``                   — dettaglio (score, percentRecommended, ...)

Il client ritorna dataclass normalizzate; non scrive sul DB.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

# --- URL base e throttle ---------------------------------------------------

OC_DIRECT_URL = "https://api.opencritic.com/api"
OC_RAPIDAPI_URL = "https://opencritic-api.p.rapidapi.com"

# Rate limit prudente: ~1 richiesta ogni 0.5s.
_throttle = Throttle(min_interval=0.5)


# ---------------------------------------------------------------------------
# Configurazione runtime
# ---------------------------------------------------------------------------


def _use_rapidapi() -> bool:
    """Legge OPENCRITIC_USE_RAPIDAPI (1/true/yes -> True)."""
    raw = os.getenv("OPENCRITIC_USE_RAPIDAPI", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _base_url() -> str:
    return OC_RAPIDAPI_URL if _use_rapidapi() else OC_DIRECT_URL


def _rapidapi_key() -> Optional[str]:
    """Legge RAPIDAPI_KEY dall'ambiente; ``None`` se assente/vuota."""
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    return key or None


def _extra_headers() -> dict[str, str]:
    """Headers aggiuntivi per RapidAPI (vuoti se uso diretto)."""
    if not _use_rapidapi():
        return {}
    key = _rapidapi_key()
    if not key:
        return {}
    return {
        "x-rapidapi-host": "opencritic-api.p.rapidapi.com",
        "x-rapidapi-key": key,
    }


# ---------------------------------------------------------------------------
# Dataclass output
# ---------------------------------------------------------------------------


@dataclass
class OpenCriticGame:
    """Dati normalizzati da OpenCritic per un gioco.

    ``top_critic_score`` e' la media dei voti critica (0-100), ``None`` se
    non ancora disponibile. ``percent_recommended`` e' la % di recensioni
    consigliate (0-100).
    """

    oc_id: int
    name: str
    top_critic_score: Optional[float] = None
    percent_recommended: Optional[float] = None
    tier: Optional[str] = None          # "Mighty", "Strong", "Fair", "Weak"
    num_reviews: Optional[int] = None
    num_top_critic_reviews: Optional[int] = None
    platforms: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing (funzioni pure, testabili senza rete)
# ---------------------------------------------------------------------------


def parse_search_results(payload: list[dict[str, Any]]) -> list[OpenCriticGame]:
    """Parsa la risposta di ``/game/search`` in una lista di ``OpenCriticGame``.

    La ricerca ritorna dati parziali (score assente o -1 pre-uscita).
    """
    games: list[OpenCriticGame] = []
    for item in payload:
        oc_id = item.get("id")
        if oc_id is None:
            continue
        name = item.get("name") or ""
        score_raw = item.get("topCriticScore")
        score: Optional[float] = None
        if score_raw is not None:
            try:
                v = float(score_raw)
                score = v if v >= 0 else None
            except (TypeError, ValueError):
                pass

        games.append(OpenCriticGame(
            oc_id=int(oc_id),
            name=name,
            top_critic_score=score,
        ))
    return games


def parse_game_detail(payload: dict[str, Any]) -> Optional[OpenCriticGame]:
    """Parsa la risposta di ``/game/{id}`` in un ``OpenCriticGame``.

    Ritorna ``None`` se il payload non contiene un ``id`` valido.
    """
    oc_id = payload.get("id")
    if oc_id is None:
        logger.info("opencritic parse_game_detail: id assente")
        return None

    name = payload.get("name") or ""

    score_raw = payload.get("topCriticScore")
    top_critic_score: Optional[float] = None
    if score_raw is not None:
        try:
            v = float(score_raw)
            top_critic_score = v if v >= 0 else None
        except (TypeError, ValueError):
            pass

    pct_raw = payload.get("percentRecommended")
    percent_recommended: Optional[float] = None
    if pct_raw is not None:
        try:
            v = float(pct_raw)
            percent_recommended = v if v >= 0 else None
        except (TypeError, ValueError):
            pass

    # Piattaforme: lista di dict {name, ...}.
    platforms = [
        (p.get("name") or p) if isinstance(p, dict) else str(p)
        for p in (payload.get("Platforms") or payload.get("platforms") or [])
        if p
    ]
    # Generi: lista di str o dict.
    genres = [
        (g.get("name") or g) if isinstance(g, dict) else str(g)
        for g in (payload.get("Genres") or payload.get("genres") or [])
        if g
    ]

    return OpenCriticGame(
        oc_id=int(oc_id),
        name=name,
        top_critic_score=top_critic_score,
        percent_recommended=percent_recommended,
        tier=payload.get("tier"),
        num_reviews=payload.get("numReviews"),
        num_top_critic_reviews=payload.get("numTopCriticReviews"),
        platforms=platforms,
        genres=genres,
    )


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def _build_client_for_oc() -> httpx.Client:
    """Costruisce un client httpx con gli header RapidAPI se necessari."""
    from core.sources._http import build_client
    headers = _extra_headers()
    return build_client(headers=headers)


def search_game(
    query: str,
    *,
    client: Optional[httpx.Client] = None,
) -> list[OpenCriticGame]:
    """Cerca un gioco su OpenCritic per nome.

    Non solleva: logga e ritorna lista vuota su errore.
    Se si usa RapidAPI e la key manca, logga e ritorna lista vuota.

    Args:
        query: Titolo (o parte di titolo) da cercare.
        client: ``httpx.Client`` riusabile (opzionale).
    """
    if _use_rapidapi() and not _rapidapi_key():
        logger.warning(
            "RAPIDAPI_KEY mancante — OpenCritic via RapidAPI non disponibile."
        )
        return []

    url = f"{_base_url()}/game/search"
    params: dict[str, Any] = {"criteria": query}
    owns_client = client is None
    cli = client or _build_client_for_oc()
    try:
        payload = request_json(
            url,
            client=cli,
            params=params,
            throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("opencritic search_game query=%r fallito: %s", query, exc)
        return []
    finally:
        if owns_client:
            cli.close()

    if not isinstance(payload, list):
        logger.warning("opencritic search_game: payload inatteso per %r", query)
        return []
    return parse_search_results(payload)


def fetch_game_detail(
    oc_id: int,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[OpenCriticGame]:
    """Scarica i dettagli completi di un gioco OpenCritic per ID.

    Non solleva: logga e ritorna ``None`` su errore.

    Args:
        oc_id: ID numerico OpenCritic del gioco.
        client: ``httpx.Client`` riusabile (opzionale).
    """
    if _use_rapidapi() and not _rapidapi_key():
        logger.warning(
            "RAPIDAPI_KEY mancante — OpenCritic via RapidAPI non disponibile."
        )
        return None

    url = f"{_base_url()}/game/{oc_id}"
    owns_client = client is None
    cli = client or _build_client_for_oc()
    try:
        payload = request_json(
            url,
            client=cli,
            throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("opencritic fetch_game_detail id=%s fallito: %s", oc_id, exc)
        return None
    finally:
        if owns_client:
            cli.close()

    if not isinstance(payload, dict):
        logger.warning("opencritic fetch_game_detail id=%s: payload inatteso", oc_id)
        return None
    return parse_game_detail(payload)
