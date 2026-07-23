"""Test dei modelli ORM e dei vincoli di schema (nessuna rete).

Copre:
- init_db su un DB SQLite in memoria;
- creazione di game + snapshot + record social;
- vincolo UNIQUE su (platform, external_id) in games;
- natura append-only degli snapshot (due snapshot coesistono).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    Base,
    Game,
    GameSnapshot,
    Lang,
    Platform,
    SnapshotType,
    SocialAccount,
    SocialPlatform,
    SocialPost,
    SocialSnapshot,
    AnalysisReport,
)


@pytest.fixture()
def session() -> Session:
    """Sessione su DB SQLite in memoria con foreign key attive."""
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, conn_record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _make_game(external_id: str = "620") -> Game:
    """Crea un Game di esempio (Portal 2)."""
    return Game(
        platform=Platform.STEAM,
        external_id=external_id,
        title="Portal 2",
        developer="Valve",
        genres=["Puzzle", "Action"],
        tags=["Co-op", "First-Person"],
        release_date=date(2011, 4, 18),
        has_demo=False,
        price=9.99,
        is_free=False,
        store_url="https://store.steampowered.com/app/620",
    )


def test_init_and_create_full_graph(session: Session) -> None:
    """Crea game + snapshot + social e verifica persistenza e JSON."""
    game = _make_game()
    game.snapshots.append(
        GameSnapshot(
            snapshot_type=SnapshotType.DISCOVERY,
            total_reviews=100,
            total_positive=95,
            total_negative=5,
            review_score_desc="Very Positive",
            current_players=1234,
            extra={"source": "test"},
        )
    )
    account = SocialAccount(
        platform=SocialPlatform.YOUTUBE,
        handle="valve",
        url="https://youtube.com/@valve",
        discovered_via="store_link",
    )
    account.snapshots.append(SocialSnapshot(followers=1000, total_posts=42))
    game.social_accounts.append(account)
    game.social_posts.append(
        SocialPost(
            platform=SocialPlatform.REDDIT,
            post_url="https://reddit.com/r/Games/x",
            subreddit="Games",
            posted_at=datetime(2011, 4, 18, tzinfo=timezone.utc),
            title="Portal 2 is out!",
            likes=5000,
            comments=300,
        )
    )
    session.add(game)
    session.add(
        AnalysisReport(
            genre="Puzzle",
            lang=Lang.IT,
            summary="Trend puzzle in crescita",
            data={"points": [1, 2, 3]},
        )
    )
    session.commit()

    loaded = session.scalar(select(Game).where(Game.external_id == "620"))
    assert loaded is not None
    # JSON round-trip
    assert loaded.genres == ["Puzzle", "Action"]
    assert loaded.snapshots[0].extra == {"source": "test"}
    assert loaded.social_accounts[0].snapshots[0].followers == 1000
    assert loaded.social_posts[0].subreddit == "Games"
    # default first_seen_at popolato
    assert loaded.first_seen_at is not None

    report = session.scalar(select(AnalysisReport))
    assert report.game_id is None
    assert report.lang == Lang.IT


def test_unique_platform_external_id(session: Session) -> None:
    """Due giochi con stessa (platform, external_id) violano l'UNIQUE."""
    session.add(_make_game("620"))
    session.commit()

    session.add(_make_game("620"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # Stesso external_id ma piattaforma diversa: consentito.
    other = _make_game("620")
    other.platform = Platform.ITCH
    session.add(other)
    session.commit()
    count = session.scalar(select(func.count()).select_from(Game))
    assert count == 2


def test_snapshots_are_append_only(session: Session) -> None:
    """Due snapshot dello stesso gioco coesistono (append, non update)."""
    game = _make_game()
    session.add(game)
    session.commit()

    session.add(
        GameSnapshot(game_id=game.id, snapshot_type=SnapshotType.H24, total_reviews=100)
    )
    session.commit()
    session.add(
        GameSnapshot(game_id=game.id, snapshot_type=SnapshotType.H48, total_reviews=150)
    )
    session.commit()

    snaps = session.scalars(
        select(GameSnapshot)
        .where(GameSnapshot.game_id == game.id)
        .order_by(GameSnapshot.total_reviews)
    ).all()
    assert len(snaps) == 2
    assert [s.snapshot_type for s in snaps] == [SnapshotType.H24, SnapshotType.H48]
    assert [s.total_reviews for s in snaps] == [100, 150]


def test_foreign_key_enforced(session: Session) -> None:
    """Uno snapshot con game_id inesistente viene rifiutato (FK ON)."""
    session.add(GameSnapshot(game_id=9999, snapshot_type=SnapshotType.MANUAL))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
