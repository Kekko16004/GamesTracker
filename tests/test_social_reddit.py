"""Test della sorgente Reddit: parsing submission->post, ricerca, dedup.

Nessuna chiamata reale ne' credenziali: iniettiamo un client PRAW fittizio.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.config import Settings
from core.sources.social.base import GameQuery
from core.sources.social.reddit import (
    RedditSource,
    submission_to_post,
)


class FakeSubreddit:
    """Nome di subreddit con ``display_name`` come l'oggetto PRAW."""

    def __init__(self, name: str) -> None:
        self.display_name = name

    def __str__(self) -> str:
        return self.display_name


class FakeSubmission:
    """Imita una PRAW ``Submission`` con i soli attributi che leggiamo."""

    def __init__(
        self,
        title: str,
        score: int,
        num_comments: int,
        created_utc: float,
        permalink: str,
        subreddit: str,
    ) -> None:
        self.title = title
        self.score = score
        self.num_comments = num_comments
        self.created_utc = created_utc
        self.permalink = permalink
        self.subreddit = FakeSubreddit(subreddit)


class FakeSubredditResource:
    """Risorsa subreddit con ``.search(query, limit)``."""

    def __init__(self, name: str, results: list[FakeSubmission]) -> None:
        self.name = name
        self._results = results
        self.search_calls: list = []

    def search(self, query, limit=None, **kwargs):  # noqa: ANN001, ANN003
        self.search_calls.append((self.name, query, limit))
        return list(self._results)


class FakeReddit:
    """Client PRAW fittizio: mappa nome subreddit -> risultati."""

    def __init__(self, results_by_sub: dict[str, list[FakeSubmission]]) -> None:
        self._results_by_sub = results_by_sub
        self.requested_subs: list[str] = []
        self.read_only = False

    def subreddit(self, name: str) -> FakeSubredditResource:
        self.requested_subs.append(name)
        return FakeSubredditResource(name, self._results_by_sub.get(name, []))


def _make_submission(title="Great game", score=120, comments=30, url_id="t3_x"):
    return FakeSubmission(
        title=title,
        score=score,
        num_comments=comments,
        created_utc=1_700_000_000.0,  # 2023-11-14T22:13:20Z
        permalink=f"/r/IndieGaming/comments/{url_id}/great_game/",
        subreddit="IndieGaming",
    )


def test_submission_to_post_mapping():
    sub = _make_submission()
    post = submission_to_post(sub)

    assert post.platform == "reddit"
    assert post.subreddit == "IndieGaming"
    assert post.post_url == (
        "https://www.reddit.com/r/IndieGaming/comments/t3_x/great_game/"
    )
    assert post.title == "Great game"
    assert post.likes == 120  # score -> likes
    assert post.comments == 30  # num_comments -> comments
    assert post.views is None  # non disponibile
    assert post.posted_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_collect_posts_dedup_across_subs():
    # Lo stesso post (stesso permalink) emerge in due ricerche -> 1 solo record.
    shared = _make_submission(title="Shared", url_id="dup1")
    only_general = _make_submission(title="Only general", url_id="gen1")

    client = FakeReddit(
        {
            "IndieGaming": [shared, only_general],
            "metroidvania": [shared],  # duplicato
            "all": [shared],  # duplicato globale
        }
    )
    settings = Settings()
    src = RedditSource(settings=settings, client=client)
    assert src.enabled is True

    game = GameQuery(title="Shared", genres=["metroidvania"])
    posts = src.collect_posts(game, limit=10, include_global=True)

    titles = sorted(p.title for p in posts)
    assert titles == ["Only general", "Shared"]  # dedup: Shared una sola volta


def test_search_queries_target_subreddits():
    client = FakeReddit({})
    src = RedditSource(settings=Settings(), client=client)
    game = GameQuery(title="Cave Diver", genres=["horror"])

    src.collect_posts(game, include_global=True)

    # Deve aver interrogato i generalisti + horror + all.
    assert "IndieGaming" in client.requested_subs
    assert "HorrorGaming" in client.requested_subs
    assert "all" in client.requested_subs


def test_disabled_without_credentials():
    settings = Settings(
        reddit_client_id="",
        reddit_client_secret="",
        reddit_user_agent="",
    )
    src = RedditSource(settings=settings)
    assert src.enabled is False
    # Degrada: nessun risultato, nessun crash.
    assert src.collect_posts(GameQuery(title="X")) == []


def test_enabled_with_credentials_but_lazy_client():
    settings = Settings(
        reddit_client_id="id",
        reddit_client_secret="secret",
        reddit_user_agent="agent",
    )
    src = RedditSource(settings=settings)
    assert src.enabled is True  # abilitata, client costruito solo su chiamata
