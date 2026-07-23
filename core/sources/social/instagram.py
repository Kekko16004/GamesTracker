"""Sorgente social Instagram — base a IMPORT MANUALE (ToS-safe).

Decisione di progetto (locked, vedi ``decisions.md`` §2 e
``existing-solutions.md`` §b): Instagram NON offre un percorso affidabile per
raccogliere metriche di post altrui. ``instaloader`` nel 2025/26 incontra
login-wall, 401/429 e **alto rischio di ban** dell'account usato: e' quindi
sconsigliato e resta solo come hook opzionale, disabilitato di default.

La BASE e' l'**import manuale**: l'utente incolla l'URL di un post/reel e le
metriche visibili, che normalizziamo in ``NormalizedPost``/``NormalizedAccount``.
Vedi ``manual_import.py`` per la funzione usata dalla GUI.

Come TikTok, la sorgente rispetta il protocollo ``SocialSource`` cosi' che un
domani si possa innestare un backend (servizio a pagamento) senza cambiare
l'interfaccia. ``enabled = False`` di default e ``collect_posts`` ritorna vuoto.

Principio dati: "dato non raccolto" ≠ "assente" → campi mancanti ``None``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from core.sources.social.base import (
    GameQuery,
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
)

logger = logging.getLogger(__name__)

PLATFORM = "instagram"

_INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}

# /p/<code>/  (post)  |  /reel/<code>/  |  /reels/<code>/  |  /tv/<code>/
_POST_RE = re.compile(r"^/(?:p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]+)/?")
# /<username>/p/<code>/  (post con username nel path)
_USER_POST_RE = re.compile(
    r"^/(?P<user>[A-Za-z0-9._]+)/(?:p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]+)/?"
)
# /<username>/  (profilo) — esclude le route note non-profilo.
_PROFILE_RE = re.compile(r"^/(?P<user>[A-Za-z0-9._]+)/?$")
_RESERVED_PATHS = {"p", "reel", "reels", "tv", "explore", "accounts", "stories"}


def is_instagram_url(url: Optional[str]) -> bool:
    """``True`` se ``url`` e' un URL Instagram plausibile (host riconosciuto)."""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, AttributeError):
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.netloc or "").lower()
    return host in _INSTAGRAM_HOSTS


def parse_instagram_url(url: Optional[str]) -> dict[str, Optional[str]]:
    """Estrae ``handle`` e ``shortcode`` da un URL Instagram, dove possibile.

    Ritorna ``{"handle": ..., "shortcode": ...}`` con ``None`` per cio' che
    non si e' potuto ricavare (i post ``/p/<code>/`` non contengono l'handle).

    Solleva ``ValueError`` se l'URL non e' un URL Instagram riconoscibile.
    """
    if not is_instagram_url(url):
        raise ValueError(f"URL Instagram non valido: {url!r}")

    parsed = urlparse(url.strip())
    path = parsed.path or ""

    match = _USER_POST_RE.match(path)
    if match and match.group("user") not in _RESERVED_PATHS:
        return {
            "handle": _normalize_handle(match.group("user")),
            "shortcode": match.group("code"),
        }

    match = _POST_RE.match(path)
    if match:
        return {"handle": None, "shortcode": match.group("code")}

    match = _PROFILE_RE.match(path)
    if match and match.group("user") not in _RESERVED_PATHS:
        return {"handle": _normalize_handle(match.group("user")), "shortcode": None}

    # Host valido ma path non parsabile: URL comunque usabile come chiave.
    return {"handle": None, "shortcode": None}


def _normalize_handle(handle: Optional[str]) -> Optional[str]:
    """Normalizza un handle Instagram: senza ``@``, lowercase, trim."""
    if not handle:
        return None
    handle = handle.strip().lstrip("@").strip()
    return handle.lower() or None


def account_from_url(
    url: str, discovered_via: str = "manual"
) -> Optional[NormalizedAccount]:
    """Costruisce un ``NormalizedAccount`` IG dall'handle nell'URL, se c'e'.

    Helper a livello di modulo (riusato da ``manual_import``). Ritorna ``None``
    se l'URL non contiene un handle deducibile (es. ``/p/<code>/``).
    """
    handle = parse_instagram_url(url).get("handle")
    if not handle:
        return None
    return NormalizedAccount(
        platform=PLATFORM,
        handle=handle,
        url=f"https://www.instagram.com/{handle}/",
        discovered_via=discovered_via,
    )


class InstagramSource:
    """Sorgente social Instagram. Implementa il protocollo ``SocialSource``.

    Base a import manuale: l'hook automatico e' disabilitato di default e
    ``instaloader`` e' sconsigliato (rischio ban). Passare ``enabled=True`` e
    un ``collector`` per attivare un backend quando disponibile.
    """

    platform = PLATFORM

    def __init__(self, enabled: bool = False, collector: Optional[object] = None) -> None:
        self._collector = collector
        self.enabled = bool(enabled and collector is not None)
        if not self.enabled:
            logger.info(
                "Sorgente Instagram in modalita' import manuale (raccolta "
                "automatica disabilitata: instaloader sconsigliato, rischio ban)."
            )

    # -- protocollo SocialSource ------------------------------------------
    def collect_posts(self, game: GameQuery) -> list[NormalizedPost]:
        """Hook di raccolta automatica. Vuoto di default (import manuale)."""
        if not self.enabled or self._collector is None:
            logger.info(
                "Instagram: sorgente automatica non disponibile, usare import "
                "manuale (manual_import.import_manual_post)."
            )
            return []
        try:
            return list(self._collector.collect_posts(game))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - backend opzionale, mai bloccare
            logger.warning("Instagram: collector opzionale fallito: %s", exc)
            return []

    def find_accounts(self, game: GameQuery) -> list[NormalizedAccount]:
        """Nessuna scoperta automatica affidabile: lista vuota."""
        return []

    def snapshot_account(
        self, account: NormalizedAccount
    ) -> Optional[NormalizedAccountSnapshot]:
        """Nessuno snapshot follower automatico (no API): ``None``."""
        return None

    # -- import manuale ----------------------------------------------------
    def account_from_url(
        self, url: str, discovered_via: str = "manual"
    ) -> Optional[NormalizedAccount]:
        """Costruisce un ``NormalizedAccount`` dall'handle nell'URL, se c'e'."""
        return account_from_url(url, discovered_via=discovered_via)

    def normalize_manual_post(
        self,
        url: str,
        posted_at: Optional[datetime] = None,
        title: Optional[str] = None,
        views: Optional[int] = None,
        likes: Optional[int] = None,
        comments: Optional[int] = None,
        shares: Optional[int] = None,
    ) -> NormalizedPost:
        """Normalizza dati inseriti a mano in un ``NormalizedPost`` Instagram.

        Valida l'URL (solleva ``ValueError`` se non e' Instagram) e lascia a
        ``None`` ogni metrica non fornita (mai ``0`` di default).
        """
        parse_instagram_url(url)
        return NormalizedPost(
            platform=PLATFORM,
            post_url=url.strip(),
            posted_at=posted_at,
            title=title,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
        )


def build_instagram_source(
    enabled: bool = False, collector: Optional[object] = None
) -> InstagramSource:
    """Factory: costruisce la sorgente Instagram (import manuale di default)."""
    return InstagramSource(enabled=enabled, collector=collector)
