"""Persistenza dei dati social normalizzati su DB.

Prende gli oggetti normalizzati di ``base`` (``NormalizedAccount``,
``NormalizedAccountSnapshot``, ``NormalizedPost``) e li scrive sulle tabelle
``social_accounts`` / ``social_snapshots`` / ``social_posts`` di
``core.models``, usando ``session_scope`` di ``core.db``.

Regole (playbook + data-model):
- **Dedup account** su ``(game_id, platform, handle)``: non duplica lo stesso
  profilo; aggiorna url/discovered_via se prima erano vuoti.
- **Append-only snapshot**: ogni snapshot e' una riga nuova (serie storica).
- **Idempotenza post**: non inserisce due volte lo stesso ``post_url`` per lo
  stesso gioco. I post senza ``post_url`` sono dedotti su
  ``(platform, title, posted_at)``.
- **Dato non raccolto ≠ 0**: i campi ``None`` restano ``None`` in colonna.

Questo modulo vive in ``core/sources/social/`` (NON in ``collector/``): il
collector si limitera' a chiamare queste funzioni.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_scope
from core.models import (
    SocialAccount,
    SocialPlatform,
    SocialPost,
    SocialSnapshot,
)
from core.sources.social.base import (
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
)

logger = logging.getLogger(__name__)


def _coerce_platform(value: str | SocialPlatform) -> SocialPlatform:
    """Converte una stringa nel corrispondente ``SocialPlatform``."""
    if isinstance(value, SocialPlatform):
        return value
    return SocialPlatform(value)


def upsert_account(
    session: Session,
    game_id: int,
    account: NormalizedAccount,
) -> SocialAccount:
    """Inserisce o recupera un ``SocialAccount`` (dedup game_id+platform+handle).

    Se esiste gia', arricchisce ``url``/``discovered_via`` se erano vuoti.
    Restituisce l'istanza persistente (con ``id`` valorizzato dopo il flush).
    """
    platform = _coerce_platform(account.platform)
    stmt = select(SocialAccount).where(
        SocialAccount.game_id == game_id,
        SocialAccount.platform == platform,
        SocialAccount.handle == account.handle,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        # Arricchimento non distruttivo dei campi mancanti.
        if not existing.url and account.url:
            existing.url = account.url
        if not existing.discovered_via and account.discovered_via:
            existing.discovered_via = account.discovered_via
        return existing

    obj = SocialAccount(
        game_id=game_id,
        platform=platform,
        handle=account.handle,
        url=account.url,
        discovered_via=account.discovered_via,
    )
    session.add(obj)
    session.flush()  # assegna l'id
    return obj


def append_account_snapshot(
    session: Session,
    social_account_id: int,
    snapshot: NormalizedAccountSnapshot,
) -> SocialSnapshot:
    """Aggiunge (append-only) uno snapshot di metriche account."""
    obj = SocialSnapshot(
        social_account_id=social_account_id,
        followers=snapshot.followers,
        total_posts=snapshot.total_posts,
        extra=snapshot.extra,
    )
    session.add(obj)
    session.flush()
    return obj


def _post_exists(session: Session, game_id: int, post: NormalizedPost) -> bool:
    """Verifica l'esistenza di un post per l'idempotenza."""
    platform = _coerce_platform(post.platform)
    if post.post_url:
        stmt = select(SocialPost.id).where(
            SocialPost.game_id == game_id,
            SocialPost.post_url == post.post_url,
        )
    else:
        # Fallback per post senza URL: chiave su (platform, title, posted_at).
        stmt = select(SocialPost.id).where(
            SocialPost.game_id == game_id,
            SocialPost.platform == platform,
            SocialPost.title == post.title,
            SocialPost.posted_at == post.posted_at,
        )
    return session.execute(stmt).first() is not None


def append_post(
    session: Session,
    game_id: int,
    post: NormalizedPost,
) -> Optional[SocialPost]:
    """Inserisce un ``SocialPost`` se non gia' presente (idempotente).

    Restituisce l'istanza creata, oppure ``None`` se era un duplicato.
    """
    if _post_exists(session, game_id, post):
        return None

    obj = SocialPost(
        game_id=game_id,
        platform=_coerce_platform(post.platform),
        post_url=post.post_url,
        subreddit=post.subreddit,
        posted_at=post.posted_at,
        title=post.title,
        views=post.views,
        likes=post.likes,
        comments=post.comments,
        shares=post.shares,
    )
    session.add(obj)
    session.flush()
    return obj


def save_posts(
    game_id: int,
    posts: Iterable[NormalizedPost],
    session: Optional[Session] = None,
) -> int:
    """Salva una collezione di post, deduplicando su ``post_url``.

    Se ``session`` e' passata, usa quella (nessun commit qui). Altrimenti apre
    una ``session_scope`` propria. Restituisce il numero di post *nuovi*
    effettivamente inseriti.
    """
    def _run(sess: Session) -> int:
        inserted = 0
        for post in posts:
            if append_post(sess, game_id, post) is not None:
                inserted += 1
        return inserted

    if session is not None:
        return _run(session)
    with session_scope() as sess:
        return _run(sess)


def save_account_with_snapshot(
    game_id: int,
    account: NormalizedAccount,
    snapshot: Optional[NormalizedAccountSnapshot] = None,
    session: Optional[Session] = None,
) -> int:
    """Upsert di un account + eventuale snapshot append-only.

    Restituisce l'``id`` dell'account. Gestisce da se' la sessione se non
    fornita.
    """
    def _run(sess: Session) -> int:
        acc = upsert_account(sess, game_id, account)
        if snapshot is not None:
            append_account_snapshot(sess, acc.id, snapshot)
        return acc.id

    if session is not None:
        return _run(session)
    with session_scope() as sess:
        return _run(sess)
