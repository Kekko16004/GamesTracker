"""Helper condivisi per i test dell'analysis (dataset sintetici in DB).

Non e' un conftest.py per non interferire con la discovery di pytest sugli
altri test; e' importato esplicitamente dai test_analysis_*.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    Base,
    Game,
    GameSnapshot,
    Platform,
    SnapshotType,
    SocialAccount,
    SocialPlatform,
    SocialPost,
    SocialSnapshot,
)

UTC = timezone.utc


def make_memory_session() -> tuple[Session, object]:
    """Crea una sessione su SQLite in memoria con FK attive."""
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, conn_record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return factory(), engine


def add_good_game(session: Session, base_time: datetime | None = None) -> Game:
    """Gioco chiaramente BUONO: scheda ricca, ottime recensioni, social vivo."""
    base = base_time or datetime(2026, 6, 1, tzinfo=UTC)
    game = Game(
        platform=Platform.STEAM,
        external_id="good-1",
        title="Stellar Roguelike",
        developer="Bright Studio",
        genres=["Roguelike", "Action"],
        tags=["Pixel Graphics", "Difficult", "Great Soundtrack"],
        release_date=date(2026, 5, 15),
        has_demo=True,
        demo_release_date=date(2026, 3, 1),
        price=14.99,
        is_free=False,
        store_url="https://store.steampowered.com/app/1",
        header_image="https://img/header1.jpg",
    )
    # Due snapshot: crescita recensioni forte.
    game.snapshots.append(GameSnapshot(
        captured_at=base,
        snapshot_type=SnapshotType.DISCOVERY,
        total_reviews=500, total_positive=470, total_negative=30,
        review_score_desc="Very Positive", current_players=800,
        price=14.99,
        extra={
            "has_trailer": True, "screenshot_count": 8,
            "description_length": 1200, "developer_other_games": 3,
            "has_official_site": True,
        },
    ))
    game.snapshots.append(GameSnapshot(
        captured_at=base + timedelta(days=7),
        snapshot_type=SnapshotType.W1,
        total_reviews=1500, total_positive=1425, total_negative=75,
        review_score_desc="Very Positive", current_players=2000,
        price=14.99,
        extra={
            "has_trailer": True, "screenshot_count": 8,
            "description_length": 1200, "developer_other_games": 3,
            "has_official_site": True,
        },
    ))
    # Social attivo: account + snapshot follower in crescita + post con engagement.
    acc = SocialAccount(platform=SocialPlatform.YOUTUBE, handle="brightstudio",
                        url="https://youtube.com/@brightstudio")
    acc.snapshots.append(SocialSnapshot(captured_at=base, followers=1000, total_posts=20))
    acc.snapshots.append(SocialSnapshot(
        captured_at=base + timedelta(days=7), followers=2500, total_posts=25))
    game.social_accounts.append(acc)
    for i in range(6):
        game.social_posts.append(SocialPost(
            platform=SocialPlatform.REDDIT, subreddit="IndieGaming",
            posted_at=base - timedelta(days=10) + timedelta(days=i * 2),
            title=f"Devlog update {i}", likes=400 + i * 50, comments=60 + i * 10,
        ))
    session.add(game)
    session.flush()
    return game


def add_mid_game(session: Session, base_time: datetime | None = None) -> Game:
    """Gioco MEDIO: scheda decente, recensioni miste, poco social."""
    base = base_time or datetime(2026, 6, 1, tzinfo=UTC)
    game = Game(
        platform=Platform.STEAM,
        external_id="mid-1",
        title="Average Platformer",
        developer="Solo Dev",
        genres=["Platformer"],
        tags=["2D", "Indie"],
        release_date=date(2026, 5, 20),
        has_demo=False,
        price=4.99,
        is_free=False,
        store_url="https://store.steampowered.com/app/2",
        header_image="https://img/header2.jpg",
    )
    game.snapshots.append(GameSnapshot(
        captured_at=base,
        snapshot_type=SnapshotType.DISCOVERY,
        total_reviews=40, total_positive=28, total_negative=12,
        review_score_desc="Mixed", current_players=30,
        price=4.99,
        extra={
            "has_trailer": True, "screenshot_count": 3,
            "description_length": 400, "developer_other_games": 0,
        },
    ))
    game.snapshots.append(GameSnapshot(
        captured_at=base + timedelta(days=7),
        snapshot_type=SnapshotType.W1,
        total_reviews=55, total_positive=38, total_negative=17,
        review_score_desc="Mixed", current_players=25,
        price=4.99,
        extra={
            "has_trailer": True, "screenshot_count": 3,
            "description_length": 400, "developer_other_games": 0,
        },
    ))
    # Un solo post, engagement modesto.
    game.social_posts.append(SocialPost(
        platform=SocialPlatform.REDDIT, subreddit="indiegames",
        posted_at=base - timedelta(days=5), title="My new game",
        likes=15, comments=3,
    ))
    session.add(game)
    session.flush()
    return game


def add_trash_game(session: Session, base_time: datetime | None = None) -> Game:
    """Gioco TRASH/asset-flip: niente scheda, zero recensioni, prezzo 0."""
    base = base_time or datetime(2026, 6, 1, tzinfo=UTC)
    game = Game(
        platform=Platform.STEAM,
        external_id="trash-1",
        title="Cheap Asset Flip",
        developer="Spam Publisher",
        genres=[],
        tags=[],
        release_date=date(2026, 5, 25),
        has_demo=False,
        price=0.0,
        is_free=True,
        store_url="https://store.steampowered.com/app/3",
        header_image=None,
    )
    game.snapshots.append(GameSnapshot(
        captured_at=base,
        snapshot_type=SnapshotType.DISCOVERY,
        total_reviews=0, total_positive=0, total_negative=0,
        current_players=0, price=0.0,
        extra={
            "has_trailer": False, "screenshot_count": 0,
            "description_length": 5, "asset_flip_tags": True,
            "placeholder_description": True,
        },
    ))
    session.add(game)
    session.flush()
    return game
