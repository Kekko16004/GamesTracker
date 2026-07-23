"""Test dell'import manuale social (TikTok/Instagram) — nessuna rete.

Copre: validazione/parsing URL, normalizzazione in ``NormalizedPost``,
salvataggio idempotente su ``post_url``, metriche non fornite = ``None``
(mai 0), e deduzione dell'account dall'handle nell'URL. DB SQLite in-memory.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.models import Base, Game, Platform, SocialAccount, SocialPost, SocialPlatform
from core.sources.social import instagram, tiktok
from core.sources.social.manual_import import (
    ManualImportError,
    import_manual_post,
)


@pytest.fixture
def session():
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
    g = Game(platform=Platform.STEAM, external_id="777", title="Neon Drift")
    session.add(g)
    session.flush()
    return g


# --- validazione / parsing URL ------------------------------------------


def test_tiktok_url_validation():
    assert tiktok.is_tiktok_url("https://www.tiktok.com/@dev/video/7300000000000000000")
    assert tiktok.is_tiktok_url("https://vm.tiktok.com/ZM12345/")
    assert not tiktok.is_tiktok_url("https://youtube.com/watch?v=x")
    assert not tiktok.is_tiktok_url("not-a-url")
    assert not tiktok.is_tiktok_url(None)


def test_tiktok_parse_extracts_handle_and_id():
    parsed = tiktok.parse_tiktok_url(
        "https://www.tiktok.com/@Dev.Studio/video/7300000000000000000"
    )
    assert parsed["handle"] == "dev.studio"  # normalizzato lowercase
    assert parsed["video_id"] == "7300000000000000000"


def test_tiktok_parse_shortlink_no_handle():
    # Short link: host valido ma handle non deducibile senza rete.
    parsed = tiktok.parse_tiktok_url("https://vm.tiktok.com/ZM12345/")
    assert parsed["handle"] is None
    assert parsed["video_id"] is None


def test_tiktok_parse_invalid_raises():
    with pytest.raises(ValueError):
        tiktok.parse_tiktok_url("https://example.com/x")


def test_instagram_url_validation():
    assert instagram.is_instagram_url("https://www.instagram.com/p/Cabc123/")
    assert instagram.is_instagram_url("https://instagram.com/reel/Cxyz/")
    assert not instagram.is_instagram_url("https://tiktok.com/@x/video/1")
    assert not instagram.is_instagram_url(None)


def test_instagram_parse_variants():
    assert instagram.parse_instagram_url("https://www.instagram.com/p/Cabc123/") == {
        "handle": None,
        "shortcode": "Cabc123",
    }
    assert instagram.parse_instagram_url(
        "https://www.instagram.com/mystudio/reel/Cxyz/"
    ) == {"handle": "mystudio", "shortcode": "Cxyz"}
    assert instagram.parse_instagram_url("https://www.instagram.com/mystudio/") == {
        "handle": "mystudio",
        "shortcode": None,
    }


def test_instagram_parse_invalid_raises():
    with pytest.raises(ValueError):
        instagram.parse_instagram_url("https://example.com/p/x/")


# --- normalizzazione via sorgenti ---------------------------------------


def test_tiktok_normalize_manual_post_keeps_none_metrics():
    src = tiktok.TikTokSource()
    post = src.normalize_manual_post(
        "https://www.tiktok.com/@dev/video/7300000000000000000",
        likes=100,
    )
    assert post.platform == "tiktok"
    assert post.likes == 100
    assert post.views is None  # non fornito = non raccolto, NON 0
    assert post.comments is None


# --- import end-to-end ---------------------------------------------------


def test_import_manual_post_saves_and_links_account(session, game):
    created = import_manual_post(
        session,
        game_id=game.id,
        platform="tiktok",
        url="https://www.tiktok.com/@neondev/video/7311111111111111111",
        posted_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        title="Launch trailer",
        views=50000,
        likes=4200,
        comments=180,
    )
    assert created is not None
    assert created.platform == SocialPlatform.TIKTOK
    assert created.views == 50000
    assert created.shares is None  # non fornito = None

    # L'account e' stato dedotto dall'handle nell'URL.
    accounts = session.execute(
        select(SocialAccount).where(SocialAccount.game_id == game.id)
    ).scalars().all()
    assert len(accounts) == 1
    assert accounts[0].handle == "neondev"
    assert accounts[0].platform == SocialPlatform.TIKTOK


def test_import_manual_post_idempotent_on_url(session, game):
    url = "https://www.instagram.com/p/Cabc123/"
    first = import_manual_post(session, game.id, "instagram", url, likes=10)
    dup = import_manual_post(session, game.id, "instagram", url, likes=999)

    assert first is not None
    assert dup is None  # stesso URL -> nessun duplicato
    rows = session.execute(
        select(SocialPost).where(SocialPost.game_id == game.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].likes == 10  # il primo vince, nessun overwrite


def test_import_manual_post_rejects_bad_url(session, game):
    with pytest.raises(ManualImportError):
        import_manual_post(session, game.id, "tiktok", "https://youtube.com/x")


def test_import_manual_post_rejects_bad_platform(session, game):
    with pytest.raises(ManualImportError):
        import_manual_post(session, game.id, "myspace", "https://myspace.com/x")


def test_import_manual_post_rejects_negative_metric(session, game):
    with pytest.raises(ManualImportError):
        import_manual_post(
            session,
            game.id,
            "tiktok",
            "https://www.tiktok.com/@x/video/7300000000000000000",
            likes=-5,
        )


def test_import_manual_post_empty_url_raises(session, game):
    with pytest.raises(ManualImportError):
        import_manual_post(session, game.id, "tiktok", "   ")


def test_import_manual_post_explicit_handle_wins(session, game):
    import_manual_post(
        session,
        game.id,
        "instagram",
        "https://www.instagram.com/p/Cxyz999/",  # niente handle nell'URL
        handle="@OfficialGame",
    )
    accounts = session.execute(
        select(SocialAccount).where(SocialAccount.game_id == game.id)
    ).scalars().all()
    assert len(accounts) == 1
    assert accounts[0].handle == "officialgame"  # normalizzato


# --- sorgenti: enabled=False e collect_posts vuoto -----------------------


def test_tiktok_source_disabled_by_default():
    src = tiktok.TikTokSource()
    assert src.enabled is False
    from core.sources.social.base import GameQuery

    assert src.collect_posts(GameQuery(title="X")) == []
    assert src.find_accounts(GameQuery(title="X")) == []


def test_instagram_source_disabled_by_default():
    src = instagram.InstagramSource()
    assert src.enabled is False
    from core.sources.social.base import GameQuery

    assert src.collect_posts(GameQuery(title="X")) == []
    assert src.find_accounts(GameQuery(title="X")) == []


def test_source_stays_disabled_without_backend_even_if_enabled_flag():
    # enabled=True ma nessun collector -> resta disabilitata (no scraping fittizio).
    src = tiktok.TikTokSource(enabled=True, collector=None)
    assert src.enabled is False


def test_source_enabled_with_backend_delegates():
    from core.sources.social.base import GameQuery, NormalizedPost

    class FakeCollector:
        def collect_posts(self, game):  # noqa: ANN001
            return [NormalizedPost(platform="tiktok", post_url="u1")]

    src = tiktok.TikTokSource(enabled=True, collector=FakeCollector())
    assert src.enabled is True
    posts = src.collect_posts(GameQuery(title="X"))
    assert len(posts) == 1 and posts[0].post_url == "u1"


def test_sources_implement_protocol():
    from core.sources.social.base import SocialSource

    assert isinstance(tiktok.TikTokSource(), SocialSource)
    assert isinstance(instagram.InstagramSource(), SocialSource)
