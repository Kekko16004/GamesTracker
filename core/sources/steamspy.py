"""Client SteamSpy — stime owner/vendite.

Endpoint: ``https://steamspy.com/api.php?request=appdetails&appid=<APPID>``

Ritorna stime (owner range, ccu, prezzo, tag). Sono APPROSSIMATE: utili
per trend relativi, non per valori assoluti. La fascia owners e' ampia
(es. "20,000 .. 50,000").

Rate limit: 1 richiesta/secondo per ``appdetails`` (dalla doc di
``steamspypi``). Usiamo un throttle dedicato. Facciamo la chiamata via
``httpx`` diretto (endpoint semplice, nessun bisogno della libreria), ma
il parsing e' isolato e testabile.

Il client ritorna ``SteamSpyData`` o ``None``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

STEAMSPY_URL = "https://steamspy.com/api.php"

# Rate limit SteamSpy per appdetails: 1 req/s.
_throttle = Throttle(min_interval=1.0)


@dataclass
class SteamSpyData:
    """Stime SteamSpy per un gioco.

    ``owners`` e' la stringa-fascia originale (es. "20,000 .. 50,000").
    ``owners_estimate`` e' la stima puntuale (punto medio della fascia).
    """

    appid: str
    name: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    owners: Optional[str] = None
    owners_estimate: Optional[int] = None
    ccu: Optional[int] = None  # peak concurrent users (giorno prima)
    price: Optional[float] = None  # prezzo attuale in unita' di valuta
    positive: Optional[int] = None
    negative: Optional[int] = None
    tags: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


def _midpoint_owners(owners: Optional[str]) -> Optional[int]:
    """Calcola il punto medio della fascia owners.

    Es. "20,000 .. 50,000" -> 35000. Ritorna ``None`` se non parsabile.
    """
    if not owners:
        return None
    numbers = re.findall(r"[\d,]+", owners)
    vals = []
    for n in numbers:
        cleaned = n.replace(",", "").strip()
        if cleaned.isdigit():
            vals.append(int(cleaned))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    return (vals[0] + vals[-1]) // 2


def _price_to_float(raw: Any) -> Optional[float]:
    """Converte il prezzo SteamSpy (stringa in centesimi) in unita'.

    SteamSpy ritorna ``price`` come stringa di centesimi (es. "999").
    """
    if raw is None or raw == "":
        return None
    try:
        return round(int(raw) / 100.0, 2)
    except (ValueError, TypeError):
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None


def parse_appdetails(payload: dict[str, Any], appid: str) -> Optional[SteamSpyData]:
    """Parsa la risposta ``appdetails`` di SteamSpy.

    SteamSpy ritorna un oggetto (non wrappato per appid). Per un appid
    inesistente ritorna un oggetto con campi vuoti / a zero: in quel caso
    ritorniamo comunque i dati (owners potrebbe essere "0 .. 20,000").
    Ritorna ``None`` solo se il payload non e' un dict valido o e' vuoto.
    """
    if not isinstance(payload, dict) or not payload:
        return None
    # SteamSpy segnala talvolta errori con {"error": "..."}.
    if payload.get("error"):
        logger.info("SteamSpy appid=%s error: %s", appid, payload.get("error"))
        return None

    # tags puo' essere dict {tag: voti} o lista.
    raw_tags = payload.get("tags")
    tags: list[str] = []
    if isinstance(raw_tags, dict):
        tags = list(raw_tags.keys())
    elif isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]

    owners = payload.get("owners") or None

    return SteamSpyData(
        appid=str(appid),
        name=payload.get("name") or None,
        developer=payload.get("developer") or None,
        publisher=payload.get("publisher") or None,
        owners=owners,
        owners_estimate=_midpoint_owners(owners),
        ccu=payload.get("ccu"),
        price=_price_to_float(payload.get("price")),
        positive=payload.get("positive"),
        negative=payload.get("negative"),
        tags=tags,
    )


def fetch_appdetails(
    appid: str | int,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[SteamSpyData]:
    """Scarica le stime SteamSpy per un gioco.

    Non solleva: logga e ritorna ``None`` in caso di errore.
    """
    params = {"request": "appdetails", "appid": str(appid)}
    try:
        payload = request_json(
            STEAMSPY_URL, client=client, params=params, throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("SteamSpy fetch_appdetails appid=%s fallito: %s", appid, exc)
        return None
    return parse_appdetails(payload, str(appid))
