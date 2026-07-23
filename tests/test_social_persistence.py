"""Test della persistenza social su DB SQLite temporaneo.

Copre: upsert account con dedup, append snapshot, dedup post su post_url,
salvataggio collezione di post e conteggio inserimenti nuovi.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.models import Base, Game, Platform, SocialAccount, SocialPost, SocialSnapshot
from core.sources.social.base import (
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
)
from core.sources.social.persistence import (
    append_account_snapshot,
    append_post,
    save_posts,
    upsert_account,
)


@pytest.fixture
def session():
    """Sessione su un DB SQLite in-memory con schema creato."""
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def game(session) -> Game:
    g = Game(platform=Platform.STEAM, external_id="12345", title="Hollow Star")
    session.add(g)
    session.flush()
    return g


def test_upsert_account_dedup(session, game):
    acc = NormalizedAccount(
        platform="youtube", handle="chan1", url="https://youtube.com/chan1"
    )
    a1 = upsert_account(session, game.id, acc)
    a2 = upsert_account(session, game.id, acc)  # stesso game+platform+handle

    assert a1.id == a2.id
    count = session.execute(
        select(SocialAccount).where(SocialAccount.game_id == game.id)
    ).scalars().all()
    assert len(count) == 1


def test_upsert_enriches_missing_fields(session, game):
    upsert_account(session, game.id, NormalizedAccount(platform="youtube", handle="c"))
    enriched = upsert_account(
        session,
        game.id,
        NormalizedAccount(
            platform="youtube", handle="c", url="https://y.com/c", discovered_via="store"
        ),
    )
    assert enriched.url == "https://y.com/c"
    assert enriched.discovered_via == "store"


def test_append_snapshot(session, game):
    acc = upsert_account(session, game.id, NormalizedAccount(platform="youtube", handle="c"))
    append_account_snapshot(
        session,
        acc.id,
        NormalizedAccountSnapshot(followers=5000, total_posts=42, extra={"collection": "api"}),
    )
    append_account_snapshot(
        session,
        acc.id,
        NormalizedAccountSnapshot(followers=5200, total_posts=43),
    )
    snaps = session.execute(
        select(SocialSnapshot).where(SocialSnapshot.social_account_id == acc.id)
    ).scalars().all()
    assert len(snaps) == 2  # append-only, serie storica
    assert snaps[0].followers == 5000


def test_append_post_idempotent_on_url(session, game):
    post = NormalizedPost(
        platform="reddit",
        post_url="https://reddit.com/r/x/comments/1/",
        subreddit="IndieGaming",
        posted_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        title="Hi",
        likes=10,
        comments=2,
    )
    first = append_post(session, game.id, post)
    dup = append_post(session, game.id, post)  # stesso post_url

    assert first is not None
    assert dup is None
    rows = session.execute(
        select(SocialPost).where(SocialPost.game_id == game.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].likes == 10
    assert rows[0].views is None  # dato non raccolto = None


def test_save_posts_counts_only_new(session, game):
    posts = [
        NormalizedPost(platform="youtube", post_url="u1", title="a"),
        NormalizedPost(platform="youtube", post_url="u2", title="b"),
        NormalizedPost(platform="youtube", post_url="u1", title="a-dup"),  # dup
    ]
    inserted = save_posts(game.id, posts, session=session)
    assert inserted == 2

    # Ri-salvando gli stessi, nessun nuovo inserimento (idempotenza).
    again = save_posts(game.id, posts, session=session)
    assert again == 0


def test_post_without_url_dedup_fallback(session, game):
    p = NormalizedPost(
        platform="reddit",
        post_url=None,
        title="No URL",
        posted_at=datetime(2025, 2, 2, tzinfo=timezone.utc),
        subreddit="indiegames",
    )
    assert append_post(session, game.id, p) is not None
    assert append_post(session, game.id, p) is None  # stesso (platform,title,posted_at)
