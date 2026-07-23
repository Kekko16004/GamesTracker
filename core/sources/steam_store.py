"""Client Steam Store — dettaglio app (``appdetails``).

Endpoint (API interna non ufficiale ma stabile):
``https://store.steampowered.com/api/appdetails?appids=<APPID>&l=english``

Ritorna dati anagrafici del gioco gia' strutturati: nome, developer,
publisher, generi, categorie, release date, prezzo, immagini, presenza
trailer, tipo (game/demo). Rispetta un rate limit prudente (~1 richiesta
ogni 1.5s) e usa uno User-Agent identificabile.

Il client NON scrive sul DB: ritorna una dataclass normalizzata
(``SteamStoreData``) o ``None`` in caso di errore / ``success:false``.
La logica di parsing (``parse_appdetails``) e' pura e testabile senza rete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STORE_APP_URL = "https://store.steampowered.com/app/{appid}"

# Rate limit prudente: ~1 richiesta ogni 1.5s (empiricamente sotto il 429).
_throttle = Throttle(min_interval=1.5)

# Mesi in inglese per il parsing della release date (l=english).
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class SteamStoreData:
    """Dati normalizzati di un gioco Steam (da ``appdetails``).

    Pronti per il mapping su ``Game``. I campi non disponibili restano
    ``None`` / liste vuote.
    """

    appid: str
    name: str
    type: Optional[str] = None  # "game" | "demo" | "dlc" | ...
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    release_date: Optional[date] = None
    coming_soon: bool = False
    is_free: bool = False
    price: Optional[float] = None  # prezzo finale in unita' di valuta (es. 9.99)
    currency: Optional[str] = None
    header_image: Optional[str] = None
    screenshots: list[str] = field(default_factory=list)
    has_trailer: bool = False
    is_demo: bool = False  # questo appid E' una demo
    demo_appids: list[str] = field(default_factory=list)  # demo collegate
    store_url: Optional[str] = None
    short_description: Optional[str] = None


def parse_release_date(raw: Optional[dict[str, Any]]) -> tuple[Optional[date], bool]:
    """Estrae ``(date, coming_soon)`` dal blocco ``release_date``.

    Steam ritorna ``{"coming_soon": bool, "date": "18 Apr, 2011"}`` (con
    ``l=english``). Il formato della stringa varia (a volte solo anno o
    mese/anno). Ritorna ``None`` se non parsabile.
    """
    if not raw:
        return None, False
    coming_soon = bool(raw.get("coming_soon", False))
    date_str = (raw.get("date") or "").strip()
    if not date_str:
        return None, coming_soon

    parsed = _parse_date_string(date_str)
    return parsed, coming_soon


def _parse_date_string(date_str: str) -> Optional[date]:
    """Parsa le varianti di data Steam in inglese.

    Gestisce: "18 Apr, 2011", "Apr 18, 2011", "Apr 2011", "2011".
    """
    cleaned = date_str.replace(",", " ")
    tokens = [t for t in cleaned.split() if t]
    day = month = year = None
    for tok in tokens:
        low = tok.lower()[:3]
        if low in _MONTHS:
            month = _MONTHS[low]
        elif tok.isdigit():
            val = int(tok)
            if val > 31:  # anno
                year = val
            else:  # giorno
                day = val
    if year is None:
        return None
    try:
        return date(year, month or 1, day or 1)
    except ValueError:
        return None


def _extract_price(data: dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    """Estrae prezzo finale (in unita' di valuta) e codice valuta.

    ``price_overview.final`` e' in centesimi. Assente se il gioco e'
    gratuito o non ancora prezzato.
    """
    overview = data.get("price_overview")
    if not overview:
        return None, None
    final_cents = overview.get("final")
    currency = overview.get("currency")
    if final_cents is None:
        return None, currency
    return round(final_cents / 100.0, 2), currency


def parse_appdetails(payload: dict[str, Any], appid: str) -> Optional[SteamStoreData]:
    """Parsa la risposta di ``appdetails`` per un singolo appid.

    ``payload`` e' il JSON top-level: ``{ "<appid>": {success, data} }``.
    Ritorna ``None`` se la chiave manca, ``success`` e' ``false`` o
    ``data`` e' assente (app senza dati / rimossa / region-locked).
    """
    entry = payload.get(str(appid))
    if not entry or not entry.get("success"):
        logger.info("appdetails appid=%s: success=false o assente", appid)
        return None
    data = entry.get("data")
    if not data:
        logger.info("appdetails appid=%s: nessun blocco data", appid)
        return None

    release_date, coming_soon = parse_release_date(data.get("release_date"))
    price, currency = _extract_price(data)

    genres = [g.get("description") for g in data.get("genres", []) if g.get("description")]
    categories = [
        c.get("description") for c in data.get("categories", []) if c.get("description")
    ]
    screenshots = [
        s.get("path_full")
        for s in data.get("screenshots", [])
        if s.get("path_full")
    ]
    movies = data.get("movies") or []
    app_type = data.get("type")

    # Demo collegate: il blocco "demos" elenca gli appid delle demo.
    demo_appids = [
        str(d.get("appid"))
        for d in (data.get("demos") or [])
        if d.get("appid") is not None
    ]

    return SteamStoreData(
        appid=str(appid),
        name=data.get("name") or "",
        type=app_type,
        developers=list(data.get("developers", []) or []),
        publishers=list(data.get("publishers", []) or []),
        genres=genres,
        categories=categories,
        release_date=release_date,
        coming_soon=coming_soon,
        is_free=bool(data.get("is_free", False)),
        price=0.0 if data.get("is_free") else price,
        currency=currency,
        header_image=data.get("header_image"),
        screenshots=screenshots,
        has_trailer=len(movies) > 0,
        is_demo=(app_type == "demo"),
        demo_appids=demo_appids,
        store_url=STORE_APP_URL.format(appid=appid),
        short_description=data.get("short_description"),
    )


def fetch_appdetails(
    appid: str | int,
    *,
    lang: str = "english",
    cc: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> Optional[SteamStoreData]:
    """Scarica e normalizza i dettagli di un'app Steam.

    Non solleva: in caso di errore di rete o risposta non valida logga e
    ritorna ``None`` (il collector non deve crashare).

    Args:
        appid: id dell'app Steam.
        lang: lingua dei metadati (default ``english`` per parsing date).
        cc: country code per prezzo/valuta (opzionale).
        client: ``httpx.Client`` riusabile (opzionale).
    """
    params: dict[str, Any] = {"appids": str(appid), "l": lang}
    if cc:
        params["cc"] = cc
    try:
        payload = request_json(
            APPDETAILS_URL, client=client, params=params, throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_appdetails appid=%s fallito: %s", appid, exc)
        return None
    if not isinstance(payload, dict):
        logger.warning("fetch_appdetails appid=%s: payload inatteso", appid)
        return None
    return parse_appdetails(payload, str(appid))
