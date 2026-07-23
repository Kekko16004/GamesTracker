"""Test del layer di accesso dati della GUI (``gui.data_access``).

Questi test NON avviano la GUI: usano solo SQLAlchemy con un DB SQLite in
memoria popolato con dati di esempio. Verificano il filtro per soglia
quality score, il dettaglio gioco con timeline e le aggregazioni trend.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from gui.data_access import GameRepository


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    """DB SQLite in memoria condiviso, con foreign key attive."""
    engine = create_engine("sqlite://", future=True)
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture()
def populated(session_factory):
    """Popola il DB: 3 giochi (buono, medio, trash) + snapshot/social/report."""
    Session = session_factory
    with Session() as s:
        # Gioco valido con crescita marcata e social.
        good = Game(
            platform=Platform.STEAM,
            external_id="1001",
            title="Bright Indie",
            developer="Studio A",
            genres=["Roguelike", "Action"],
            release_date=date.today() - timedelta(days=10),
            has_demo=True,
            demo_release_date=date.today() - timedelta(days=60),
            quality_score=82.0,
            discarded=False,
            store_url="https://store.steampowered.com/app/1001",
        )
        # Gioco medio, altra piattaforma, genere diverso.
        mid = Game(
            platform=Platform.ITCH,
            external_id="cool-game",
            title="Mid Game",
            developer="Studio B",
            genres=["Puzzle"],
            release_date=date.today() - timedelta(days=100),
            quality_score=45.0,
            discarded=False,
        )
        # Trash: sotto soglia e scartato.
        trash = Game(
            platform=Platform.STEAM,
            external_id="9999",
            title="Asset Flip",
            developer="Spam LLC",
            genres=["Action"],
            quality_score=8.0,
            discarded=True,
        )
        s.add_all([good, mid, trash])
        s.flush()

        # Snapshot di crescita per il gioco buono (recensioni +900).
        s.add_all(
            [
                GameSnapshot(
                    game_id=good.id,
                    captured_at=_utc(2026, 6, 1),
                    snapshot_type=SnapshotType.DISCOVERY,
                    total_reviews=100,
                    total_positive=90,
                    total_negative=10,
                    current_players=50,
                ),
                GameSnapshot(
                    game_id=good.id,
                    captured_at=_utc(2026, 6, 8),
                    snapshot_type=SnapshotType.W1,
                    total_reviews=1000,
                    total_positive=920,
                    total_negative=80,
                    current_players=500,
                ),
            ]
        )
        # Snapshot singolo per il gioco medio (nessuna crescita calcolabile).
        s.add(
            GameSnapshot(
                game_id=mid.id,
                captured_at=_utc(2026, 6, 1),
                snapshot_type=SnapshotType.DISCOVERY,
                total_reviews=30,
            )
        )

        # Social account + snapshot follower + post (timeline).
        acc = SocialAccount(
            game_id=good.id,
            platform=SocialPlatform.YOUTUBE,
            handle="brightindie",
            url="https://youtube.com/@brightindie",
            discovered_via="store link",
        )
        s.add(acc)
        s.flush()
        s.add(
            SocialSnapshot(
                social_account_id=acc.id,
                captured_at=_utc(2026, 6, 5),
                followers=12000,
                total_posts=40,
            )
        )
        s.add(
            SocialPost(
                game_id=good.id,
                platform=SocialPlatform.REDDIT,
                post_url="https://reddit.com/r/IndieGaming/x",
                subreddit="IndieGaming",
                posted_at=_utc(2026, 6, 3),
                title="Our demo is live!",
                likes=1500,
                comments=200,
            )
        )

        # Report per-gioco.
        s.add(
            AnalysisReport(
                game_id=good.id,
                lang=Lang.IT,
                generated_at=_utc(2026, 6, 9),
                summary="Strategia demo-first con forte spike Reddit.",
                data={"reviews": [100, 1000], "labels": ["d0", "w1"]},
            )
        )
        s.commit()
    return session_factory


def test_has_any_data(session_factory, populated):
    repo = GameRepository(populated)
    assert repo.has_any_data() is True


def test_has_any_data_empty(session_factory):
    repo = GameRepository(session_factory)
    assert repo.has_any_data() is False


def test_threshold_filters_trash(populated):
    repo = GameRepository(populated)
    # Soglia 0: mostra tutti i non-scartati (good + mid), trash escluso.
    all_visible = repo.list_games(min_quality_score=0)
    titles = {g.title for g in all_visible}
    assert titles == {"Bright Indie", "Mid Game"}

    # Soglia 50: solo il gioco buono resta.
    high = repo.list_games(min_quality_score=50)
    assert [g.title for g in high] == ["Bright Indie"]

    # include_discarded mostra anche il trash.
    with_trash = repo.list_games(min_quality_score=0, include_discarded=True)
    assert "Asset Flip" in {g.title for g in with_trash}


def test_platform_and_genre_filters(populated):
    repo = GameRepository(populated)
    steam_only = repo.list_games(platform="steam")
    assert [g.title for g in steam_only] == ["Bright Indie"]

    itch_only = repo.list_games(platform="itch")
    assert [g.title for g in itch_only] == ["Mid Game"]

    puzzle = repo.list_games(genre="Puzzle")
    assert [g.title for g in puzzle] == ["Mid Game"]


def test_review_growth_and_latest_metrics(populated):
    repo = GameRepository(populated)
    good = next(g for g in repo.list_games() if g.title == "Bright Indie")
    assert good.review_growth == 900
    assert good.latest_reviews == 1000
    assert good.latest_players == 500

    mid = next(g for g in repo.list_games() if g.title == "Mid Game")
    # Un solo snapshot -> crescita non calcolabile.
    assert mid.review_growth is None


def test_dashboard_stats(populated):
    repo = GameRepository(populated)
    stats = repo.dashboard_stats(min_quality_score=50)
    assert stats.total_games == 3
    assert stats.discarded_games == 1
    assert stats.visible_games == 1  # solo good >= 50 e non scartato
    assert stats.recent_releases >= 1  # good uscito 10 gg fa


def test_top_by_growth(populated):
    repo = GameRepository(populated)
    top = repo.top_by_growth(limit=5)
    assert top[0].title == "Bright Indie"
    assert top[0].review_growth == 900


def test_genre_distribution(populated):
    repo = GameRepository(populated)
    dist = repo.genre_distribution()
    # Action compare in good (mid escluso non ha Action); trash escluso.
    assert dist.get("Roguelike") == 1
    assert dist.get("Puzzle") == 1
    assert dist.get("Action") == 1


def test_game_detail_with_timeline(populated):
    repo = GameRepository(populated)
    good = next(g for g in repo.list_games() if g.title == "Bright Indie")
    detail = repo.get_game_detail(good.id)
    assert detail is not None
    assert detail.has_demo is True
    assert len(detail.snapshots) == 2
    assert len(detail.accounts) == 1
    assert detail.accounts[0].latest_followers == 12000
    assert len(detail.posts) == 1

    # Timeline ordinata: demo (60gg fa) -> post (2026-06-03) -> release (10gg fa).
    kinds = [e.kind for e in detail.timeline]
    assert "demo" in kinds and "release" in kinds and "post" in kinds
    whens = [e.when for e in detail.timeline]
    assert whens == sorted(whens)


def test_game_detail_missing(populated):
    repo = GameRepository(populated)
    assert repo.get_game_detail(999999) is None


def test_genre_trends(populated):
    repo = GameRepository(populated)
    trends = repo.genre_trends()
    by_genre = {t.genre: t for t in trends}
    assert by_genre["Roguelike"].total_review_growth == 900
    assert by_genre["Roguelike"].avg_quality_score == 82.0
    assert by_genre["Puzzle"].game_count == 1


def test_reports(populated):
    repo = GameRepository(populated)
    rows = repo.list_reports()
    assert len(rows) == 1
    assert rows[0].game_title == "Bright Indie"
    assert rows[0].lang == "it"

    detail = repo.get_report(rows[0].id)
    assert detail is not None
    assert "demo-first" in detail.summary
    assert detail.data["reviews"] == [100, 1000]


def test_empty_states(session_factory):
    """Con DB vuoto le query non crashano e restituiscono liste/zeri."""
    repo = GameRepository(session_factory)
    assert repo.list_games() == []
    assert repo.recent_releases() == []
    assert repo.top_by_growth() == []
    assert repo.genre_distribution() == {}
    assert repo.genre_trends() == []
    assert repo.list_reports() == []
    stats = repo.dashboard_stats()
    assert stats.total_games == 0
