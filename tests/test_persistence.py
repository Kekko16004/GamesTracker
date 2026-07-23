"""Test di persistenza idempotente + append snapshot (DB SQLite in memoria)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Base, Game, GameSnapshot, Platform, SnapshotType, SocialAccount
from core.sources.itch import ItchGameData
from core.sources.steam_reviews import SteamReviewSummary
from core.sources.steam_store import SteamStoreData
from core.sources.steamspy import SteamSpyData
from collector.persistence import (
    append_game_snapshot,
    build_store_extra,
    get_game,
    upsert_itch_game,
    upsert_steam_game,
)


def test_build_store_extra_populates_quality_signals():
    """build_store_extra deve esporre i segnali letti dal quality score."""
    details = SteamStoreData(
        appid="1",
        name="Rich Game",
        screenshots=["a", "b", "c", "d"],
        has_trailer=True,
        short_description="Una descrizione di lunghezza ragionevole per il test.",
    )
    extra = build_store_extra(details)
    assert extra["has_trailer"] is True
    assert extra["screenshot_count"] == 4
    assert extra["description_length"] == len(details.short_description)
    assert extra["placeholder_description"] is False


def test_build_store_extra_flags_empty_page():
    details = SteamStoreData(
        appid="2", name="Empty", screenshots=[], has_trailer=False,
        short_description="",
    )
    extra = build_store_extra(details)
    assert extra["has_trailer"] is False
    assert extra["screenshot_count"] == 0
    assert extra["description_length"] == 0
    assert extra["placeholder_description"] is True


@pytest.fixture()
def session() -> Session:
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


def _steam_data(appid="620", name="Portal 2") -> SteamStoreData:
    return SteamStoreData(
        appid=appid,
        name=name,
        type="game",
        developers=["Valve"],
        publishers=["Valve"],
        genres=["Puzzle"],
        categories=["Co-op"],
        release_date=date(2011, 4, 18),
        is_free=False,
        price=9.99,
        header_image="https://img/h.jpg",
        store_url="https://store.steampowered.com/app/620",
    )


def test_upsert_steam_game_idempotent(session: Session):
    upsert_steam_game(session, _steam_data())
    session.commit()
    # Secondo upsert con dati aggiornati: NON crea un duplicato.
    upsert_steam_game(session, _steam_data(name="Portal 2 - Updated"))
    session.commit()

    count = session.scalar(select(func.count()).select_from(Game))
    assert count == 1
    game = get_game(session, Platform.STEAM, "620")
    assert game.title == "Portal 2 - Updated"


def test_upsert_steam_merges_steamspy_tags(session: Session):
    spy = SteamSpyData(appid="620", owners="1 .. 2", tags=["Indie", "Puzzle"])
    game = upsert_steam_game(session, _steam_data(), steamspy=spy)
    session.commit()
    assert "Co-op" in game.tags
    assert "Indie" in game.tags


def test_upsert_itch_game_and_social(session: Session):
    data = ItchGameData(
        url="https://dev1.itch.io/cool",
        title="Cool",
        author="Dev One",
        genres=["Platformer"],
        is_free=True,
        social_links=[{"platform": "twitter", "url": "https://twitter.com/dev1"}],
    )
    game = upsert_itch_game(session, data)
    session.commit()
    assert game.platform == Platform.ITCH
    assert game.external_id == "https://dev1.itch.io/cool"
    accounts = session.scalars(select(SocialAccount)).all()
    assert len(accounts) == 1
    assert accounts[0].platform.value == "twitter"

    # Re-upsert non duplica il social account.
    upsert_itch_game(session, data)
    session.commit()
    assert session.scalar(select(func.count()).select_from(SocialAccount)) == 1


def test_append_game_snapshot(session: Session):
    game = upsert_steam_game(session, _steam_data())
    session.flush()
    reviews = SteamReviewSummary(
        total_reviews=100, total_positive=90, total_negative=10,
        review_score_desc="Very Positive",
    )
    append_game_snapshot(
        session, game, SnapshotType.DISCOVERY, reviews=reviews, current_players=42,
    )
    session.commit()
    # Secondo snapshot: append, non update.
    append_game_snapshot(
        session, game, SnapshotType.H24,
        reviews=SteamReviewSummary(total_reviews=150),
    )
    session.commit()

    snaps = session.scalars(
        select(GameSnapshot).where(GameSnapshot.game_id == game.id)
        .order_by(GameSnapshot.total_reviews)
    ).all()
    assert len(snaps) == 2
    assert snaps[0].total_reviews == 100
    assert snaps[0].current_players == 42
    assert snaps[0].price == 9.99  # ereditato dal gioco
    assert snaps[1].snapshot_type == SnapshotType.H24
