"""Client Steam Web API — player count live.

Endpoint:
``https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=<APPID>``

Ritorna ``{ response: { player_count, result } }``. Solo per giochi gia'
usciti. Molte fonti indicano che l'endpoint funziona anche SENZA key; se
``STEAM_WEB_API_KEY`` e' configurata la passiamo (via
``require_steam_web_api_key`` di core.config), altrimenti degradiamo con
un log invece di crashare.

Ritorna l'int ``player_count`` o ``None``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from core.config import MissingConfigError, get_settings
from core.sources._http import Throttle, request_json

logger = logging.getLogger(__name__)

CURRENT_PLAYERS_URL = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)

# Rate limit prudente per l'API Web (burst per IP -> 429).
_throttle = Throttle(min_interval=1.0)


def parse_player_count(payload: dict[str, Any]) -> Optional[int]:
    """Estrae ``player_count`` dalla risposta.

    ``response.result`` == 1 indica successo. Ritorna ``None`` se il
    risultato non e' valido (es. appid senza dati player).
    """
    response = payload.get("response")
    if not isinstance(response, dict):
        return None
    # result == 1 => ok. Se assente ma player_count presente, accettiamo.
    result = response.get("result")
    if result is not None and result != 1:
        return None
    count = response.get("player_count")
    if count is None:
        return None
    try:
        return int(count)
    except (ValueError, TypeError):
        return None


def fetch_current_players(
    appid: str | int,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[int]:
    """Scarica il player count live di un gioco.

    Usa la Steam Web API key se configurata; se manca, prova comunque
    senza key (l'endpoint spesso funziona lo stesso) e logga un avviso.
    Non solleva: ritorna ``None`` in caso di errore.
    """
    settings = get_settings()
    params: dict[str, Any] = {"appid": str(appid)}
    try:
        params["key"] = settings.require_steam_web_api_key()
    except MissingConfigError:
        logger.info(
            "STEAM_WEB_API_KEY assente: provo GetNumberOfCurrentPlayers senza key "
            "(appid=%s)", appid,
        )

    try:
        payload = request_json(
            CURRENT_PLAYERS_URL, client=client, params=params, throttle=_throttle,
        )
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_current_players appid=%s fallito: %s", appid, exc)
        return None
    if not isinstance(payload, dict):
        return None
    return parse_player_count(payload)
