"""Client Steam — discovery di nuovi appid (nuove uscite).

Due approcci complementari:

1. **Scraping leggero** di ``https://store.steampowered.com/explore/new/``
   per estrarre gli appid dei giochi che Steam mette in evidenza tra le
   nuove uscite. La pagina espone gli appid negli attributi
   ``data-ds-appid`` degli elementi di lista. E' HTML (nessuna API JSON),
   quindi il selettore e' potenzialmente fragile: lo isoliamo in
   ``parse_explore_new`` (testabile) e degradiamo a lista vuota su errore.
   Nota: usiamo il cookie ``birthtime`` implicitamente evitando le pagine
   age-gated; ``explore/new`` non richiede age-gate.

2. **Diffing di GetAppList** (``ISteamApps/GetAppList/v2``): scarica TUTTI
   gli appid (lista enorme) e li confronta con un set noto per trovare i
   nuovi. Non filtra per data/tipo (a carico nostro, via appdetails).
   Utile come complemento a explore/new, che e' curato ma parziale.

Lo scraping HTML e' consentito SOLO per la discovery (vedi decisions.md):
per il dettaglio del gioco si usano gli endpoint JSON.

I client ritornano liste di appid (stringhe). Non scrivono sul DB.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, request_json, request_text

logger = logging.getLogger(__name__)

EXPLORE_NEW_URL = "https://store.steampowered.com/explore/new/"
GETAPPLIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

_throttle = Throttle(min_interval=1.5)

# Regex per estrarre gli appid dagli attributi data-ds-appid della pagina
# explore/new. Un elemento puo' contenere piu' appid separati da virgola
# (bundle); li splittiamo a valle.
_APPID_ATTR_RE = re.compile(r'data-ds-appid="([\d,]+)"')


def parse_explore_new(html: str) -> list[str]:
    """Estrae gli appid dalla pagina ``explore/new`` (HTML).

    Cerca gli attributi ``data-ds-appid``. Deduplica preservando l'ordine
    di apparizione (Steam ordina per rilevanza). Ritorna lista di stringhe.
    """
    appids: list[str] = []
    seen: set[str] = set()
    for match in _APPID_ATTR_RE.findall(html or ""):
        # Un attributo puo' elencare piu' appid (es. "1,2,3"): prendiamo tutti.
        for raw in match.split(","):
            appid = raw.strip()
            if appid and appid.isdigit() and appid not in seen:
                seen.add(appid)
                appids.append(appid)
    return appids


def fetch_new_releases(
    *,
    client: Optional[httpx.Client] = None,
) -> list[str]:
    """Scarica gli appid delle nuove uscite in evidenza (explore/new).

    Non solleva: logga e ritorna lista vuota in caso di errore.
    """
    try:
        html = request_text(
            EXPLORE_NEW_URL, client=client, throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_new_releases (explore/new) fallito: %s", exc)
        return []
    appids = parse_explore_new(html)
    logger.info("explore/new: trovati %d appid", len(appids))
    return appids


def parse_app_list(payload: dict[str, Any]) -> dict[str, str]:
    """Estrae ``{appid: name}`` da ``GetAppList``.

    Ritorna dict vuoto se la struttura non e' quella attesa.
    """
    applist = payload.get("applist") if isinstance(payload, dict) else None
    if not isinstance(applist, dict):
        return {}
    apps = applist.get("apps")
    if not isinstance(apps, list):
        return {}
    result: dict[str, str] = {}
    for app in apps:
        appid = app.get("appid")
        if appid is None:
            continue
        result[str(appid)] = app.get("name") or ""
    return result


def fetch_app_list(
    *,
    client: Optional[httpx.Client] = None,
) -> dict[str, str]:
    """Scarica l'intera lista app Steam (``{appid: name}``).

    Lista enorme (centinaia di migliaia). Non solleva: ritorna ``{}`` su
    errore.
    """
    try:
        payload = request_json(
            GETAPPLIST_URL, client=client, throttle=_throttle, timeout=60.0,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_app_list (GetAppList) fallito: %s", exc)
        return {}
    return parse_app_list(payload)


def diff_new_appids(
    current: dict[str, str] | set[str],
    known: set[str],
) -> list[str]:
    """Ritorna gli appid presenti in ``current`` ma non in ``known``.

    ``current`` puo' essere il dict di ``GetAppList`` o un set di appid.
    Usato per il diffing periodico: il chiamante persiste il set noto.
    """
    current_ids = set(current.keys()) if isinstance(current, dict) else set(current)
    return sorted(current_ids - known, key=lambda x: int(x) if x.isdigit() else 0)
