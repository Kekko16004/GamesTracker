"""Import manuale di post social (ToS-safe) — funzione unica per la GUI.

Questo modulo espone ``import_manual_post``: valida un URL social, lo
normalizza in un ``NormalizedPost`` (e, se possibile, in un
``NormalizedAccount``) e lo salva in modo **idempotente** riusando la
persistenza esistente (``save_posts`` / ``save_account_with_snapshot``).

E' l'UNICA via con cui la GUI scrive dati social: input dell'utente, non
rete. Coerente con la decisione locked "base = import manuale" per TikTok e
Instagram (ma la funzione accetta anche le altre piattaforme social, cosi'
si puo' incollare a mano un link YouTube/Reddit/Twitter/Discord se serve).

Principi rispettati:
- **Dedup su post_url**: reinserire lo stesso URL non duplica (``append_post``).
- **"Dato non raccolto" ≠ 0**: metriche non fornite restano ``None``.
- Nessuna logica di persistenza duplicata: si delega a ``persistence``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.models import SocialPlatform, SocialPost
from core.sources.social.base import NormalizedAccount, NormalizedPost
from core.sources.social.instagram import (
    account_from_url as _ig_account_from_url,
    is_instagram_url,
)
from core.sources.social.persistence import (
    append_post,
    save_account_with_snapshot,
)
from core.sources.social.tiktok import (
    account_from_url as _tt_account_from_url,
    is_tiktok_url,
)

logger = logging.getLogger(__name__)


class ManualImportError(ValueError):
    """Errore di validazione dell'import manuale (URL/piattaforma/metriche)."""


def _coerce_platform(platform: str | SocialPlatform) -> SocialPlatform:
    """Converte/valida la piattaforma; solleva ``ManualImportError`` se ignota."""
    if isinstance(platform, SocialPlatform):
        return platform
    try:
        return SocialPlatform(str(platform).strip().lower())
    except ValueError as exc:
        valid = ", ".join(p.value for p in SocialPlatform)
        raise ManualImportError(
            f"Piattaforma social non valida: {platform!r}. Ammesse: {valid}."
        ) from exc


def _validate_url_for_platform(platform: SocialPlatform, url: str) -> None:
    """Valida l'URL rispetto alla piattaforma (solo dove abbiamo un parser).

    Per TikTok/Instagram applica la validazione dedicata. Per le altre
    piattaforme accetta qualunque URL non vuoto (l'utente incolla un link
    gia' visto). Solleva ``ManualImportError`` se non valido.
    """
    if platform == SocialPlatform.TIKTOK:
        if not is_tiktok_url(url):
            raise ManualImportError(f"URL TikTok non valido: {url!r}")
    elif platform == SocialPlatform.INSTAGRAM:
        if not is_instagram_url(url):
            raise ManualImportError(f"URL Instagram non valido: {url!r}")


def _optional_account(
    platform: SocialPlatform, url: str, handle: Optional[str]
) -> Optional[NormalizedAccount]:
    """Costruisce un ``NormalizedAccount`` da handle esplicito o dall'URL.

    L'handle passato dall'utente ha precedenza; altrimenti si tenta di
    dedurlo dall'URL per TikTok/Instagram. ``None`` se non ricavabile.
    """
    if handle:
        clean = handle.strip().lstrip("@").strip().lower()
        if clean:
            return NormalizedAccount(
                platform=platform.value, handle=clean, discovered_via="manual"
            )
    if platform == SocialPlatform.TIKTOK:
        return _tt_account_from_url(url)
    if platform == SocialPlatform.INSTAGRAM:
        return _ig_account_from_url(url)
    return None


def _coerce_metric(value: object, name: str) -> Optional[int]:
    """Converte una metrica in int non negativo; ``None`` se non fornita.

    ``None``/stringa vuota => ``None`` (dato non raccolto, MAI 0). Un valore
    negativo o non numerico solleva ``ManualImportError``.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise ManualImportError(f"Metrica {name!r} non numerica: {value!r}") from exc
    if ivalue < 0:
        raise ManualImportError(f"Metrica {name!r} negativa: {ivalue}")
    return ivalue


def import_manual_post(
    session: Session,
    game_id: int,
    platform: str | SocialPlatform,
    url: str,
    posted_at: Optional[datetime] = None,
    title: Optional[str] = None,
    views: Optional[int] = None,
    likes: Optional[int] = None,
    comments: Optional[int] = None,
    shares: Optional[int] = None,
    handle: Optional[str] = None,
) -> Optional[SocialPost]:
    """Valida, normalizza e salva un post social inserito a mano.

    Parametri:
        session: sessione SQLAlchemy attiva (il commit spetta al chiamante o
            al ``session_scope`` che la avvolge).
        game_id: id del gioco a cui collegare il post.
        platform: valore di ``SocialPlatform`` (o l'enum stesso).
        url: URL del post (validato per TikTok/Instagram).
        posted_at: data/ora di pubblicazione (opzionale).
        title: titolo/descrizione (opzionale).
        views/likes/comments/shares: metriche visibili; ``None`` se non note
            (mai ``0`` di default). Valori negativi/non numerici => errore.
        handle: handle dell'account (opzionale; altrimenti dedotto dall'URL).

    Ritorna il ``SocialPost`` creato, oppure ``None`` se era un duplicato
    (idempotenza su ``post_url``). Solleva ``ManualImportError`` in caso di
    input non valido.
    """
    if not url or not url.strip():
        raise ManualImportError("URL del post mancante.")

    social_platform = _coerce_platform(platform)
    clean_url = url.strip()
    _validate_url_for_platform(social_platform, clean_url)

    post = NormalizedPost(
        platform=social_platform.value,
        post_url=clean_url,
        posted_at=posted_at,
        title=(title.strip() if isinstance(title, str) and title.strip() else None),
        views=_coerce_metric(views, "views"),
        likes=_coerce_metric(likes, "likes"),
        comments=_coerce_metric(comments, "comments"),
        shares=_coerce_metric(shares, "shares"),
    )

    # Se ricaviamo un account, lo colleghiamo (upsert idempotente, senza
    # snapshot: l'import manuale di un post non misura i follower).
    account = _optional_account(social_platform, clean_url, handle)
    if account is not None:
        save_account_with_snapshot(game_id, account, snapshot=None, session=session)

    created = append_post(session, game_id, post)
    if created is None:
        logger.info(
            "Import manuale: post gia' presente (dedup su URL) %s", clean_url
        )
    else:
        logger.info(
            "Import manuale: salvato post %s (%s) per game_id=%s",
            clean_url,
            social_platform.value,
            game_id,
        )
    return created
