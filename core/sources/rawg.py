"""Client RAWG.io — ricerca e dettaglio giochi.

Endpoint base: ``https://api.rawg.io/api``

Free tier: 20.000 richieste/mese con API key.
Endpoint usati:
- ``/games``            ricerca per nome
- ``/games/{id}``       dettaglio (nome, rating, metacritic, generi, tag, ...)
- ``/games/{id}/screenshots``  immagini aggiuntive

La API key si legge dalla variabile d'ambiente ``RAWG_API_KEY``. Se assente,
il modulo e' comunque importabile ma ogni funzione di fetch logga un avviso e
ritorna ``None`` / lista vuota, senza sollevare eccezioni — "graceful degrade".

Il client ritorna dataclass normalizzate; non scrive sul DB.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

RAWG_BASE_URL = "https://api.rawg.io/api"

# Rate limit prudente: ~1 richiesta ogni 0.5s (free tier: 20k/mese ~ 0.77/min).
_throttle = Throttle(min_interval=0.5)


def _get_api_key() -> Optional[str]:
    """Legge RAWG_API_KEY dall'ambiente; ritorna ``None`` se assente/vuota."""
    key = os.getenv("RAWG_API_KEY", "").strip()
    return key or None


@dataclass
class RawgGame:
    """Dati normalizzati di un gioco RAWG.

    Pronti per l'arricchimento di un ``Game`` esistente. I campi non
    disponibili restano ``None`` / liste vuote.
    """

    rawg_id: int
    name: str
    released: Optional[date] = None
    rating: Optional[float] = None          # media voto utenti (0-5)
    ratings_count: Optional[int] = None
    metacritic: Optional[int] = None        # Metacritic score (0-100)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    description: Optional[str] = None
    background_image: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsing (funzioni pure, testabili senza rete)
# ---------------------------------------------------------------------------


def _parse_date(raw: Optional[str]) -> Optional[date]:
    """Parsa una data ISO (``YYYY-MM-DD``) in ``date``, o ritorna ``None``."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def parse_game_detail(payload: dict[str, Any]) -> Optional[RawgGame]:
    """Parsa la risposta di ``/games/{id}`` in un ``RawgGame``.

    Ritorna ``None`` se il payload non contiene un ``id`` valido.
    """
    rawg_id = payload.get("id")
    if rawg_id is None:
        logger.info("rawg parse_game_detail: id assente nel payload")
        return None

    name = payload.get("name") or ""

    genres = [
        g.get("name")
        for g in (payload.get("genres") or [])
        if g.get("name")
    ]
    tags = [
        t.get("name")
        for t in (payload.get("tags") or [])
        if t.get("name") and t.get("language") in (None, "eng")
    ]
    platforms = [
        (p.get("platform") or {}).get("name")
        for p in (payload.get("platforms") or [])
        if (p.get("platform") or {}).get("name")
    ]

    # Screenshot dalla chiamata dettaglio (short_screenshots) o come lista di URL.
    screenshots: list[str] = []
    for s in payload.get("short_screenshots") or []:
        img = s.get("image")
        if img:
            screenshots.append(img)

    return RawgGame(
        rawg_id=int(rawg_id),
        name=name,
        released=_parse_date(payload.get("released")),
        rating=payload.get("rating"),
        ratings_count=payload.get("ratings_count"),
        metacritic=payload.get("metacritic"),
        genres=genres,
        tags=tags,
        platforms=platforms,
        screenshots=screenshots,
        description=payload.get("description_raw") or payload.get("description"),
        background_image=payload.get("background_image"),
    )


def parse_search_results(payload: dict[str, Any]) -> list[RawgGame]:
    """Parsa la lista ``/games`` in una lista di ``RawgGame`` parziali.

    La ricerca ritorna meno campi del dettaglio (niente description/tag).
    """
    results = payload.get("results") or []
    games: list[RawgGame] = []
    for item in results:
        parsed = parse_game_detail(item)
        if parsed is not None:
            games.append(parsed)
    return games


def parse_screenshots(payload: dict[str, Any]) -> list[str]:
    """Parsa la lista ``/games/{id}/screenshots`` in URL."""
    return [
        r.get("image")
        for r in (payload.get("results") or [])
        if r.get("image")
    ]


# ---------------------------------------------------------------------------
# Fetch (richiedono rete + API key)
# ---------------------------------------------------------------------------


def _check_key() -> Optional[str]:
    """Controlla la presenza della API key; logga e ritorna ``None`` se assente."""
    key = _get_api_key()
    if key is None:
        logger.warning(
            "RAWG_API_KEY non configurata — sorgente RAWG non disponibile. "
            "Impostare la variabile d'ambiente RAWG_API_KEY per abilitarla."
        )
    return key


def search_games(
    query: str,
    *,
    page_size: int = 10,
    client: Optional[httpx.Client] = None,
) -> list[RawgGame]:
    """Cerca giochi su RAWG per nome.

    Non solleva: logga e ritorna lista vuota su errore o API key assente.

    Args:
        query: Termine di ricerca (es. titolo del gioco).
        page_size: Numero di risultati (max 40 per la free tier).
        client: ``httpx.Client`` riusabile (opzionale).
    """
    key = _check_key()
    if key is None:
        return []
    params: dict[str, Any] = {
        "key": key,
        "search": query,
        "page_size": min(page_size, 40),
    }
    try:
        payload = request_json(
            f"{RAWG_BASE_URL}/games",
            client=client,
            params=params,
            throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("rawg search_games query=%r fallito: %s", query, exc)
        return []
    if not isinstance(payload, dict):
        logger.warning("rawg search_games: payload inatteso")
        return []
    return parse_search_results(payload)


def fetch_game_detail(
    rawg_id: int,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[RawgGame]:
    """Scarica i dettagli completi di un gioco RAWG.

    Non solleva: logga e ritorna ``None`` su errore o API key assente.

    Args:
        rawg_id: ID numerico RAWG del gioco.
        client: ``httpx.Client`` riusabile (opzionale).
    """
    key = _check_key()
    if key is None:
        return None
    params: dict[str, Any] = {"key": key}
    try:
        payload = request_json(
            f"{RAWG_BASE_URL}/games/{rawg_id}",
            client=client,
            params=params,
            throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("rawg fetch_game_detail id=%s fallito: %s", rawg_id, exc)
        return None
    if not isinstance(payload, dict):
        logger.warning("rawg fetch_game_detail id=%s: payload inatteso", rawg_id)
        return None
    return parse_game_detail(payload)


def fetch_screenshots(
    rawg_id: int,
    *,
    client: Optional[httpx.Client] = None,
) -> list[str]:
    """Scarica gli screenshot di un gioco RAWG.

    Non solleva: logga e ritorna lista vuota su errore o API key assente.

    Args:
        rawg_id: ID numerico RAWG del gioco.
        client: ``httpx.Client`` riusabile (opzionale).
    """
    key = _check_key()
    if key is None:
        return []
    params: dict[str, Any] = {"key": key}
    try:
        payload = request_json(
            f"{RAWG_BASE_URL}/games/{rawg_id}/screenshots",
            client=client,
            params=params,
            throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("rawg fetch_screenshots id=%s fallito: %s", rawg_id, exc)
        return []
    if not isinstance(payload, dict):
        return []
    return parse_screenshots(payload)
