"""Scraper HowLongToBeat - stima durata di gioco.

Non esiste un'API ufficiale. Usiamo una POST a:
    ``https://howlongtobeat.com/api/search``
con body JSON e header ``Referer: https://howlongtobeat.com``.

La struttura della risposta puo' cambiare senza preavviso (sito pubblico).
Il modulo e' progettato per degradare: se il parsing fallisce logga e
ritorna ``None`` senza crashare il collector.

Fetch: ore story (main story), story+extra, completionist, review score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, build_client

logger = logging.getLogger(__name__)

HLTB_SEARCH_URL = "https://howlongtobeat.com/api/search"
HLTB_REFERER = "https://howlongtobeat.com"

# Rate limit gentile: 1 richiesta ogni 2s (sito pubblico senza API key).
_throttle = Throttle(min_interval=2.0)


@dataclass
class HltbData:
    """Stima di durata di un gioco da HowLongToBeat.

    Tutti i valori di durata sono espressi in ORE (float). ``None`` indica
    dato non disponibile. ``review_score`` e' una percentuale (0-100) o ``None``.
    """

    title: str
    hltb_id: Optional[int] = None
    main_story: Optional[float] = None     # Solo storia principale
    main_extra: Optional[float] = None     # Storia + extra
    completionist: Optional[float] = None  # 100% completamento
    review_score: Optional[int] = None     # % di voti positivi (0-100)


# ---------------------------------------------------------------------------
# Parsing (funzione pura, testabile senza rete)
# ---------------------------------------------------------------------------


def _secs_to_hours(secs: Optional[Any]) -> Optional[float]:
    """Converte secondi (int o float) in ore, arrotondati a 1 decimale.

    HLTB memorizza le durate in secondi internamente; altri formati di
    risposta usano gia' le ore. Gestiamo entrambi: se il valore e' >= 3600
    lo trattiamo come secondi, altrimenti come ore dirette.
    Ritorna ``None`` se il valore e' None, 0, o non convertibile.
    """
    if secs is None:
        return None
    try:
        val = float(secs)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    # Soglia euristica: se >3600 probabilmente e' in secondi.
    if val >= 3600:
        return round(val / 3600.0, 1)
    return round(val, 1)


def parse_search_result(payload: dict[str, Any]) -> Optional[HltbData]:
    """Parsa il primo risultato utile della ricerca HLTB.

    La struttura attesa e' ``{"data": [...], "pageProps": {...}}``.
    Prende il primo elemento di ``data`` con un nome plausibile.
    Ritorna ``None`` se nessun risultato trovato o struttura inattesa.
    """
    # La risposta puo' essere wrappata in pageProps/data o direttamente in data.
    data = payload.get("data")
    if data is None:
        # Alcuni path alternativi osservati nel sito.
        data = (payload.get("pageProps") or {}).get("games", {}).get("data")
    if not isinstance(data, list) or not data:
        logger.info("hltb parse_search_result: lista data assente o vuota")
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    title = first.get("game_name") or first.get("game_alias") or ""
    if not title:
        return None

    hltb_id = first.get("game_id")
    main_story = _secs_to_hours(first.get("comp_main"))
    main_extra = _secs_to_hours(first.get("comp_plus"))
    completionist = _secs_to_hours(first.get("comp_100"))
    review_score = first.get("review_score")
    if review_score is not None:
        try:
            review_score = int(review_score)
        except (TypeError, ValueError):
            review_score = None

    return HltbData(
        title=title,
        hltb_id=int(hltb_id) if hltb_id is not None else None,
        main_story=main_story,
        main_extra=main_extra,
        completionist=completionist,
        review_score=review_score,
    )


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def search_game(
    title: str,
    *,
    http_client: Optional[httpx.Client] = None,
) -> Optional[HltbData]:
    """Cerca un gioco su HowLongToBeat per titolo.

    Non solleva: logga e ritorna ``None`` in caso di errore.

    Args:
        title: Titolo del gioco da cercare.
        http_client: ``httpx.Client`` riusabile (opzionale).
    """
    if not title.strip():
        return None

    _throttle.wait()
    owns_client = http_client is None
    cli = http_client or build_client(
        headers={"Referer": HLTB_REFERER}
    )
    # Payload della ricerca (struttura osservata aprile 2025).
    body = {
        "searchType": "games",
        "searchTerms": title.split(),
        "searchPage": 1,
        "size": 5,
        "searchOptions": {
            "games": {
                "userId": 0,
                "platform": "",
                "sortCategory": "popular",
                "rangeCategory": "main",
                "rangeTime": {"min": None, "max": None},
                "gameplay": {"perspective": "", "flow": "", "genre": ""},
                "rangeYear": {"min": "", "max": ""},
                "modifier": "",
            },
            "users": {"sortCategory": "postcount"},
            "filter": "",
            "sort": 0,
            "randomizer": 0,
        },
    }
    try:
        resp = cli.post(
            HLTB_SEARCH_URL,
            json=body,
            headers={
                "Referer": HLTB_REFERER,
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("hltb search_game title=%r fallito: %s", title, exc)
        return None
    finally:
        if owns_client:
            cli.close()

    if not isinstance(payload, dict):
        logger.warning("hltb search_game: payload inatteso per %r", title)
        return None

    result = parse_search_result(payload)
    if result is None:
        logger.info("hltb search_game: nessun risultato per %r", title)
    return result
