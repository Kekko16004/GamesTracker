"""Sorgente social TikTok — base a IMPORT MANUALE (ToS-safe).

Decisione di progetto (locked, vedi ``decisions.md`` §2 e
``existing-solutions.md`` §b): TikTok NON offre API pubblica affidabile per
raccogliere metriche di post altrui. Ogni scraping non ufficiale
(es. ``TikTokApi``) e' fragile, contro i ToS e a rischio blocco IP/token.

Percio' la BASE di questa sorgente e' l'**import manuale**: l'utente incolla
l'URL di un post e le metriche visibili (views/like/comment/share) e noi le
normalizziamo in ``NormalizedPost``/``NormalizedAccount``. Vedi
``manual_import.py`` per la funzione end-to-end usata dalla GUI.

Un domani si potra' innestare uno scraper (``TikTokApi``) o un servizio a
pagamento (Apify, Bright Data, ...) implementando ``collect_posts`` senza
toccare il resto: la sorgente rispetta il protocollo ``SocialSource`` come
YouTube/Reddit. L'hook automatico e' **disabilitato di default**
(``enabled = False``) e ``collect_posts`` ritorna vuoto con un log chiaro.

Principio dati: "dato non raccolto" ≠ "assente" → i campi mancanti restano
``None``, mai ``0``.
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

PLATFORM = "tiktok"

# Host riconosciuti come TikTok (inclusi gli short link vm./vt.).
_TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}

# /@handle/video/<id>  oppure  /@handle/photo/<id>
_VIDEO_RE = re.compile(r"^/@(?P<handle>[^/]+)/(?:video|photo)/(?P<id>\d+)")
# /@handle  (pagina profilo)
_PROFILE_RE = re.compile(r"^/@(?P<handle>[^/]+)/?$")


def is_tiktok_url(url: Optional[str]) -> bool:
    """``True`` se ``url`` e' un URL TikTok plausibile (host riconosciuto)."""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, AttributeError):
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.netloc or "").lower()
    return host in _TIKTOK_HOSTS


def parse_tiktok_url(url: Optional[str]) -> dict[str, Optional[str]]:
    """Estrae ``handle`` e ``video_id`` da un URL TikTok, dove possibile.

    Ritorna sempre un dict ``{"handle": ..., "video_id": ...}`` con valori
    ``None`` per cio' che non si e' potuto ricavare. Per gli short link
    (``vm.tiktok.com/XXXX``) non si puo' dedurre nulla senza risolvere il
    redirect (che richiederebbe rete): ``handle``/``video_id`` restano
    ``None`` ma l'URL resta valido come chiave del post.

    Solleva ``ValueError`` se l'URL non e' un URL TikTok riconoscibile.
    """
    if not is_tiktok_url(url):
        raise ValueError(f"URL TikTok non valido: {url!r}")

    parsed = urlparse(url.strip())
    path = parsed.path or ""

    match = _VIDEO_RE.match(path)
    if match:
        return {
            "handle": _normalize_handle(match.group("handle")),
            "video_id": match.group("id"),
        }

    match = _PROFILE_RE.match(path)
    if match:
        return {"handle": _normalize_handle(match.group("handle")), "video_id": None}

    # Host valido (es. short link) ma path non parsabile: URL comunque usabile.
    return {"handle": None, "video_id": None}


def _normalize_handle(handle: Optional[str]) -> Optional[str]:
    """Normalizza un handle TikTok: senza ``@`` iniziale, lowercase, trim."""
    if not handle:
        return None
    handle = handle.strip().lstrip("@").strip()
    return handle.lower() or None


def account_from_url(
    url: str, discovered_via: str = "manual"
) -> Optional[NormalizedAccount]:
    """Costruisce un ``NormalizedAccount`` TikTok dall'handle nell'URL, se c'e'.

    Helper a livello di modulo (riusato da ``manual_import``). Ritorna ``None``
    se l'URL non contiene un handle deducibile (es. short link).
    """
    handle = parse_tiktok_url(url).get("handle")
    if not handle:
        return None
    return NormalizedAccount(
        platform=PLATFORM,
        handle=handle,
        url=f"https://www.tiktok.com/@{handle}",
        discovered_via=discovered_via,
    )


class TikTokSource:
    """Sorgente social TikTok. Implementa il protocollo ``SocialSource``.

    Base a import manuale: l'hook di raccolta automatica e' disabilitato di
    default. Passare ``enabled=True`` (e in futuro un ``collector`` iniettato)
    per attivare un backend di scraping/servizio quando disponibile.
    """

    platform = PLATFORM

    def __init__(self, enabled: bool = False, collector: Optional[object] = None) -> None:
        """Costruisce la sorgente.

        ``collector`` e' un eventuale backend futuro (scraper/servizio) con un
        metodo ``collect_posts(game) -> list[NormalizedPost]``. Se assente, la
        sorgente resta in modalita' import manuale (nessuna rete).
        """
        self._collector = collector
        # Abilitata solo se esplicitamente richiesto E c'e' un backend.
        self.enabled = bool(enabled and collector is not None)
        if not self.enabled:
            logger.info(
                "Sorgente TikTok in modalita' import manuale (raccolta "
                "automatica disabilitata: nessuna API affidabile/ToS-safe)."
            )

    # -- protocollo SocialSource ------------------------------------------
    def collect_posts(self, game: GameQuery) -> list[NormalizedPost]:
        """Hook di raccolta automatica. Vuoto di default (import manuale).

        Se un ``collector`` e' stato iniettato e la sorgente e' abilitata,
        delega a esso; altrimenti logga e ritorna lista vuota senza crashare.
        """
        if not self.enabled or self._collector is None:
            logger.info(
                "TikTok: sorgente automatica non disponibile, usare import "
                "manuale (manual_import.import_manual_post)."
            )
            return []
        try:
            return list(self._collector.collect_posts(game))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - backend opzionale, mai bloccare
            logger.warning("TikTok: collector opzionale fallito: %s", exc)
            return []

    def find_accounts(self, game: GameQuery) -> list[NormalizedAccount]:
        """Nessuna scoperta automatica affidabile: lista vuota.

        Gli account TikTok si aggiungono via import manuale (dal post o dal
        profilo ufficiale del gioco).
        """
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
        """Normalizza dati inseriti a mano in un ``NormalizedPost`` TikTok.

        Valida l'URL (solleva ``ValueError`` se non e' TikTok) e lascia a
        ``None`` ogni metrica non fornita (mai ``0`` di default).
        """
        # Valida l'URL; l'handle estratto non serve nel post ma conferma la validita'.
        parse_tiktok_url(url)
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


def build_tiktok_source(
    enabled: bool = False, collector: Optional[object] = None
) -> TikTokSource:
    """Factory: costruisce la sorgente TikTok (import manuale di default)."""
    return TikTokSource(enabled=enabled, collector=collector)
