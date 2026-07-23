"""Client Steam — review summary (``appreviews``).

Cuore del review tracking. Endpoint:
``https://store.steampowered.com/appreviews/<APPID>?json=1``

Facciamo UNA chiamata leggera leggendo solo ``query_summary``
(total_reviews, total_positive, total_negative, review_score,
review_score_desc). Non scarichiamo le review singole.

Parametri usati:
- ``json=1``
- ``language=all`` (tutte le lingue)
- ``purchase_type=all`` (conteggio pubblico completo)
- ``review_type=all`` (evita la trappola per cui ``total_reviews`` viene
  sovrascritto con positive/negative)
- ``num_per_page=0`` (non ci servono le review, solo il summary)

NON usiamo la libreria ``steamreviews`` (richiede Python 3.11+).
Il client ritorna una dataclass ``SteamReviewSummary`` o ``None``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

# Rate limit prudente condiviso con lo store (stesso host).
_throttle = Throttle(min_interval=1.5)


@dataclass
class SteamReviewSummary:
    """Riepilogo recensioni di un gioco Steam (da ``query_summary``)."""

    total_reviews: Optional[int] = None
    total_positive: Optional[int] = None
    total_negative: Optional[int] = None
    review_score: Optional[int] = None
    review_score_desc: Optional[str] = None


def parse_query_summary(payload: dict[str, Any]) -> Optional[SteamReviewSummary]:
    """Estrae il ``query_summary`` dalla risposta ``appreviews``.

    Ritorna ``None`` se ``success`` non e' 1 o manca ``query_summary``.
    Nota: con ``review_type=all`` il campo ``total_reviews`` e' affidabile;
    in fallback lo ricalcoliamo come positive + negative.
    """
    if payload.get("success") != 1:
        logger.info("appreviews: success != 1")
        return None
    summary = payload.get("query_summary")
    if not summary:
        logger.info("appreviews: query_summary assente")
        return None

    total_positive = summary.get("total_positive")
    total_negative = summary.get("total_negative")
    total_reviews = summary.get("total_reviews")

    # Fallback difensivo: se il totale manca ma abbiamo pos/neg, sommiamo.
    if total_reviews is None and (
        total_positive is not None or total_negative is not None
    ):
        total_reviews = (total_positive or 0) + (total_negative or 0)

    return SteamReviewSummary(
        total_reviews=total_reviews,
        total_positive=total_positive,
        total_negative=total_negative,
        review_score=summary.get("review_score"),
        review_score_desc=summary.get("review_score_desc"),
    )


def fetch_review_summary(
    appid: str | int,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[SteamReviewSummary]:
    """Scarica il riepilogo recensioni di un gioco (1 chiamata leggera).

    Non solleva: logga e ritorna ``None`` in caso di errore.
    """
    params = {
        "json": "1",
        "language": "all",
        "purchase_type": "all",
        "review_type": "all",
        "num_per_page": "0",
        # Include eventuali review-bomb nel conteggio pubblico.
        "filter_offtopic_activity": "0",
    }
    url = APPREVIEWS_URL.format(appid=appid)
    try:
        payload = request_json(
            url, client=client, params=params, throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_review_summary appid=%s fallito: %s", appid, exc)
        return None
    if not isinstance(payload, dict):
        logger.warning("fetch_review_summary appid=%s: payload inatteso", appid)
        return None
    return parse_query_summary(payload)
