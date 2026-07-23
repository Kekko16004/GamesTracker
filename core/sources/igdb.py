"""Client IGDB/Twitch — dettaglio giochi via API IGDB v4.

Autenticazione: Twitch OAuth ``client_credentials`` flow.
Legge ``TWITCH_CLIENT_ID`` e ``TWITCH_CLIENT_SECRET`` dall'ambiente.
Se assenti, il modulo e' importabile ma ogni fetch logga un avviso e
ritorna ``None`` / lista vuota (graceful degrade).

Base URL: ``https://api.igdb.com/v4``
Endpoint usati: ``/games``, ``/covers``, ``/screenshots``, ``/game_videos``

IGDB usa il linguaggio Apicalypse: le richieste sono POST con body testuale.
Es.:
    ``fields name,rating; where id = 1942; limit 1;``

I token OAuth scadono dopo ~60 giorni; questo modulo gestisce il refresh
automatico al primo uso e quando il server risponde 401.

Il client ritorna dataclass normalizzate; non scrive sul DB.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from core.sources._http import Throttle, build_client

logger = logging.getLogger(__name__)

IGDB_BASE_URL = "https://api.igdb.com/v4"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# Rate limit prudente: IGDB free tier ha un limite implicito, ~4 req/s.
_throttle = Throttle(min_interval=0.25)

# Cache token in-process (durata ~60 giorni, refresh su 401).
_token_cache: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Gestione credenziali e token OAuth
# ---------------------------------------------------------------------------


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    """Legge TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET dall'ambiente."""
    client_id = os.getenv("TWITCH_CLIENT_ID", "").strip() or None
    client_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip() or None
    return client_id, client_secret


def _fetch_token(client_id: str, client_secret: str) -> Optional[str]:
    """Esegue il flusso ``client_credentials`` e ritorna l'access token.

    Ritorna ``None`` in caso di errore di rete o risposta non valida.
    """
    try:
        with httpx.Client(timeout=15.0) as cli:
            resp = cli.post(
                TWITCH_TOKEN_URL,
                params={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("igdb _fetch_token fallito: %s", exc)
        return None

    token = data.get("access_token")
    expires_in = data.get("expires_in", 0)
    if token:
        _token_cache["token"] = token
        _token_cache["expires_at"] = time.monotonic() + float(expires_in) - 300
        logger.info("igdb: token acquisito (scade in ~%ds)", expires_in)
    return token or None


def _get_token(force_refresh: bool = False) -> Optional[str]:
    """Ritorna un access token valido, rinfrescandolo se necessario.

    Se le credenziali Twitch mancano ritorna ``None`` (graceful degrade).
    """
    client_id, client_secret = _get_credentials()
    if not client_id or not client_secret:
        logger.warning(
            "TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET mancanti — "
            "sorgente IGDB non disponibile."
        )
        return None

    cached = _token_cache.get("token")
    expires_at = _token_cache.get("expires_at", 0.0)
    if cached and not force_refresh and time.monotonic() < expires_at:
        return cached

    return _fetch_token(client_id, client_secret)


# ---------------------------------------------------------------------------
# Dataclass output
# ---------------------------------------------------------------------------


@dataclass
class IgdbGame:
    """Dati normalizzati di un gioco IGDB.

    I campi non disponibili restano ``None`` / liste vuote.
    """

    igdb_id: int
    name: str
    rating: Optional[float] = None              # media voti utenti IGDB (0-100)
    aggregated_rating: Optional[float] = None   # media voti critica (0-100)
    first_release_date: Optional[int] = None    # Unix timestamp
    genres: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    game_modes: list[str] = field(default_factory=list)
    cover_url: Optional[str] = None
    hypes: Optional[int] = None                 # hype count pre-lancio
    screenshots: list[str] = field(default_factory=list)
    video_ids: list[str] = field(default_factory=list)   # YouTube video IDs


# ---------------------------------------------------------------------------
# Parsing (funzioni pure, testabili senza rete)
# ---------------------------------------------------------------------------


def _igdb_image_url(image_id: str, size: str = "cover_big") -> str:
    """Genera un URL immagine IGDB (CDN) da un image_id.

    Formato: ``https://images.igdb.com/igdb/image/upload/t_{size}/{id}.jpg``
    """
    return f"https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg"


def parse_games(payload: list[dict[str, Any]]) -> list[IgdbGame]:
    """Parsa la lista di risultati ``/games`` in una lista di ``IgdbGame``."""
    games: list[IgdbGame] = []
    for item in payload:
        igdb_id = item.get("id")
        if igdb_id is None:
            continue
        name = item.get("name") or ""

        genres = [g.get("name") for g in (item.get("genres") or []) if g.get("name")]
        themes = [t.get("name") for t in (item.get("themes") or []) if t.get("name")]
        game_modes = [
            m.get("name") for m in (item.get("game_modes") or []) if m.get("name")
        ]

        cover_url: Optional[str] = None
        cover = item.get("cover")
        if isinstance(cover, dict):
            img_id = cover.get("image_id")
            if img_id:
                cover_url = _igdb_image_url(img_id, "cover_big")

        screenshots: list[str] = []
        for s in item.get("screenshots") or []:
            img_id = s.get("image_id") if isinstance(s, dict) else None
            if img_id:
                screenshots.append(_igdb_image_url(img_id, "screenshot_big"))

        video_ids: list[str] = []
        for v in item.get("videos") or []:
            vid = v.get("video_id") if isinstance(v, dict) else None
            if vid:
                video_ids.append(vid)

        games.append(IgdbGame(
            igdb_id=int(igdb_id),
            name=name,
            rating=item.get("rating"),
            aggregated_rating=item.get("aggregated_rating"),
            first_release_date=item.get("first_release_date"),
            genres=genres,
            themes=themes,
            game_modes=game_modes,
            cover_url=cover_url,
            hypes=item.get("hypes"),
            screenshots=screenshots,
            video_ids=video_ids,
        ))
    return games


# ---------------------------------------------------------------------------
# Fetch (richiedono rete + credenziali Twitch)
# ---------------------------------------------------------------------------


def _igdb_post(
    endpoint: str,
    body: str,
    *,
    client_id: str,
    token: str,
    http_client: Optional[httpx.Client] = None,
    max_retries: int = 2,
) -> Optional[list[dict[str, Any]]]:
    """Esegue una POST Apicalypse su un endpoint IGDB.

    Gestisce il re-fetch del token su 401. Ritorna la lista JSON o ``None``.
    """
    owns_client = http_client is None
    cli = http_client or build_client()
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for attempt in range(max_retries + 1):
        _throttle.wait()
        try:
            resp = cli.post(
                f"{IGDB_BASE_URL}/{endpoint.lstrip('/')}",
                content=body.encode(),
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("igdb POST %s tentativo %d fallito: %s",
                           endpoint, attempt + 1, exc)
            if attempt == max_retries:
                if owns_client:
                    cli.close()
                return None
            continue

        if resp.status_code == 401 and attempt == 0:
            # Token scaduto: forza refresh e riprova una volta.
            logger.info("igdb: 401 su %s, rinnovo token", endpoint)
            new_token = _get_token(force_refresh=True)
            if new_token:
                token = new_token
                headers["Authorization"] = f"Bearer {token}"
            continue

        if resp.status_code >= 400:
            logger.warning("igdb POST %s -> HTTP %d", endpoint, resp.status_code)
            if owns_client:
                cli.close()
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("igdb POST %s: body non JSON", endpoint)
            if owns_client:
                cli.close()
            return None

        if owns_client:
            cli.close()
        return data if isinstance(data, list) else None

    if owns_client:
        cli.close()
    return None


def search_games(
    query: str,
    *,
    limit: int = 10,
    http_client: Optional[httpx.Client] = None,
) -> list[IgdbGame]:
    """Cerca giochi su IGDB per nome.

    Non solleva: logga e ritorna lista vuota su errore o credenziali assenti.

    Args:
        query: Titolo da cercare.
        limit: Numero massimo di risultati (max 500 per IGDB).
        http_client: ``httpx.Client`` riusabile (opzionale).
    """
    token = _get_token()
    if token is None:
        return []
    client_id, _ = _get_credentials()
    if not client_id:
        return []

    safe_query = query.replace('"', '\\"')
    body = (
        f'fields name,rating,aggregated_rating,first_release_date,'
        f'genres.name,themes.name,game_modes.name,cover.image_id,hypes,'
        f'screenshots.image_id,videos.video_id;'
        f'search "{safe_query}";'
        f'limit {min(limit, 500)};'
    )
    raw = _igdb_post("games", body, client_id=client_id, token=token,
                     http_client=http_client)
    if raw is None:
        return []
    return parse_games(raw)


def fetch_game_detail(
    igdb_id: int,
    *,
    http_client: Optional[httpx.Client] = None,
) -> Optional[IgdbGame]:
    """Scarica i dettagli completi di un gioco IGDB per ID.

    Non solleva: logga e ritorna ``None`` su errore o credenziali assenti.

    Args:
        igdb_id: ID numerico IGDB del gioco.
        http_client: ``httpx.Client`` riusabile (opzionale).
    """
    token = _get_token()
    if token is None:
        return None
    client_id, _ = _get_credentials()
    if not client_id:
        return None

    body = (
        f"fields name,rating,aggregated_rating,first_release_date,"
        f"genres.name,themes.name,game_modes.name,cover.image_id,hypes,"
        f"screenshots.image_id,videos.video_id;"
        f"where id = {igdb_id};"
        f"limit 1;"
    )
    raw = _igdb_post("games", body, client_id=client_id, token=token,
                     http_client=http_client)
    if not raw:
        return None
    games = parse_games(raw)
    return games[0] if games else None


def fetch_covers(
    game_ids: list[int],
    *,
    http_client: Optional[httpx.Client] = None,
) -> dict[int, str]:
    """Scarica le copertine di una lista di giochi IGDB.

    Ritorna un dict ``{igdb_id: cover_url}``.
    Non solleva: ritorna dict vuoto su errore.
    """
    if not game_ids:
        return {}
    token = _get_token()
    if token is None:
        return {}
    client_id, _ = _get_credentials()
    if not client_id:
        return {}

    ids_str = ",".join(str(i) for i in game_ids)
    body = f"fields game,image_id; where game = ({ids_str}); limit {len(game_ids)};"
    raw = _igdb_post("covers", body, client_id=client_id, token=token,
                     http_client=http_client)
    if not raw:
        return {}
    result: dict[int, str] = {}
    for item in raw:
        gid = item.get("game")
        img_id = item.get("image_id")
        if gid is not None and img_id:
            result[int(gid)] = _igdb_image_url(img_id, "cover_big")
    return result
