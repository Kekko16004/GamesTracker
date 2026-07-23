"""Test per le funzionalita' AI: sentiment, market gaps, launch health.

Tutte le funzioni di analisi sono pure o usano mock leggeri del DB.
Nessuna rete, nessuna API esterna.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ai_sentiment
# ---------------------------------------------------------------------------

from analysis.ai_sentiment import classify_review, game_sentiment_summary


class TestClassifyReview:
    def test_empty_text(self):
        result = classify_review("")
        assert result == [("praise", 0.1)]

    def test_bug_report(self):
        text = "The game crashes every time I open the inventory. Very buggy."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "bug_report" in categories
        # Confidence > soglia minima.
        conf = dict(labels)
        assert conf["bug_report"] > 0.15

    def test_performance_issue(self):
        text = "Terrible FPS drops in the forest area. Very laggy and stuttering constantly."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "performance_issue" in categories

    def test_praise(self):
        text = "Absolutely amazing masterpiece! Must play, highly recommend! 10/10."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "praise" in categories
        conf = dict(labels)
        assert conf["praise"] > 0.5

    def test_feature_request(self):
        text = "Would be nice if they added co-op. Please add controller support. I wish it had more levels."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "feature_request" in categories

    def test_content_feedback(self):
        text = "Game is too short. The story is interesting but repetitive gameplay."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "content_feedback" in categories

    def test_ui_ux(self):
        text = "The UI is terrible and clunky controls. Hard to navigate the menu. Font too small."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "ui_ux" in categories

    def test_monetization(self):
        text = "Way overpriced. Not worth the price. Too many DLC and microtransactions. Pay to win."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert "monetization" in categories

    def test_multilabel(self):
        """Una review puo' avere piu' categorie contemporaneamente."""
        text = "Amazing game but it crashes constantly. Overpriced for the content."
        labels = classify_review(text)
        categories = [l[0] for l in labels]
        assert len(categories) >= 2

    def test_fallback_no_strong_signal(self):
        """Testo neutro o generico -> fallback praise."""
        text = "I played this game for a while."
        labels = classify_review(text)
        # Almeno un risultato ritornato.
        assert len(labels) >= 1
        # Se nessuna categoria supera la soglia, e' il fallback.
        assert labels[0][0] in {
            "praise", "bug_report", "performance_issue",
            "feature_request", "content_feedback", "ui_ux", "monetization",
        }

    def test_output_sorted_by_confidence(self):
        text = "Amazing masterpiece. Must buy. 10/10. Highly recommend this excellent game."
        labels = classify_review(text)
        confidences = [l[1] for l in labels]
        assert confidences == sorted(confidences, reverse=True)

    def test_confidence_in_range(self):
        text = "Crashes and freezes all the time. Memory leak. Black screen bug."
        labels = classify_review(text)
        for cat, conf in labels:
            assert 0.0 <= conf <= 1.0, f"confidence fuori range per {cat}: {conf}"

    def test_case_insensitive(self):
        """Le keyword devono matchare indipendentemente dal case."""
        upper = classify_review("CRASHES CONSTANTLY. VERY BUGGY GAME.")
        lower = classify_review("crashes constantly. very buggy game.")
        cats_upper = {l[0] for l in upper}
        cats_lower = {l[0] for l in lower}
        assert cats_upper == cats_lower


class TestGameSentimentSummary:
    def _make_mock_session(self, post_titles: list[str]) -> MagicMock:
        """Crea una sessione mock con SocialPost fittizi."""
        session = MagicMock()
        posts = []
        now = datetime.now(timezone.utc)
        for i, title in enumerate(post_titles):
            p = MagicMock()
            p.title = title
            p.posted_at = now
            posts.append(p)

        # Simula session.scalars(...).
        scalars_result = MagicMock()
        scalars_result.__iter__ = MagicMock(return_value=iter(posts))
        session.scalars.return_value = scalars_result
        return session

    def test_no_posts(self):
        session = self._make_mock_session([])
        result = game_sentiment_summary(1, session)
        assert result["n_reviews"] == 0
        assert result["distribution"] == {}
        assert result["top_category"] is None

    def test_with_posts(self):
        titles = [
            "Amazing game, highly recommend!",
            "Game crashes every time I open the map.",
            "Too expensive and full of DLC.",
        ]
        session = self._make_mock_session(titles)
        result = game_sentiment_summary(1, session, max_reviews=10)
        assert result["n_reviews"] == 3
        assert result["game_id"] == 1
        assert isinstance(result["distribution"], dict)
        assert isinstance(result["categories"], list)
        assert result["top_category"] is not None

    def test_distribution_fractions_valid(self):
        titles = [
            "Crashes all the time, very buggy.",
            "Laggy FPS drops stuttering.",
            "Amazing masterpiece 10/10.",
            "Please add co-op support.",
        ]
        session = self._make_mock_session(titles)
        result = game_sentiment_summary(1, session)
        for cat, frac in result["distribution"].items():
            assert 0.0 <= frac <= 1.0, f"fraction fuori range per {cat}"

    def test_categories_sorted_by_count(self):
        # Tutti bug report.
        titles = ["Game crashes." for _ in range(5)] + ["Amazing game!"]
        session = self._make_mock_session(titles)
        result = game_sentiment_summary(1, session)
        cats = result["categories"]
        if len(cats) >= 2:
            assert cats[0]["count"] >= cats[1]["count"]

    def test_category_fields(self):
        session = self._make_mock_session(["Game crashes a lot, very buggy."])
        result = game_sentiment_summary(1, session)
        for cat_info in result["categories"]:
            assert "category" in cat_info
            assert "count" in cat_info
            assert "fraction" in cat_info
            assert "avg_confidence" in cat_info


# ---------------------------------------------------------------------------
# market_gaps
# ---------------------------------------------------------------------------

from analysis.market_gaps import (
    compute_gaps,
    _competition_level,
    _log_norm,
    _aggregate_by_genre,
    MarketGap,
)


class TestComputeGaps:
    def _make_genre_data(self) -> dict:
        return {
            "roguelike": {
                "game_count": 2,
                "avg_quality": 65.0,
                "avg_players": 3000.0,
                "avg_reviews": 800.0,
                "game_ids": [1, 2],
                "benchmark_median_reviews": 1200,
            },
            "cozy": {
                "game_count": 15,
                "avg_quality": 75.0,
                "avg_players": 200.0,
                "avg_reviews": 150.0,
                "game_ids": list(range(15)),
                "benchmark_median_reviews": 500,
            },
            "horror": {
                "game_count": 1,
                "avg_quality": 30.0,
                "avg_players": 5000.0,
                "avg_reviews": 2000.0,
                "game_ids": [20],
                "benchmark_median_reviews": 600,
            },
        }

    def test_returns_market_gaps(self):
        gaps = compute_gaps(self._make_genre_data())
        assert isinstance(gaps, list)
        assert len(gaps) == 3

    def test_sorted_by_opportunity_desc(self):
        gaps = compute_gaps(self._make_genre_data())
        scores = [g.opportunity_score for g in gaps]
        assert scores == sorted(scores, reverse=True)

    def test_horror_high_demand_low_supply_high_opportunity(self):
        gaps = compute_gaps(self._make_genre_data())
        horror = next((g for g in gaps if g.genre == "horror"), None)
        assert horror is not None
        # Bassa supply (1 gioco) + alta domanda -> alta opportunita'.
        assert horror.competition_level == "low"
        assert horror.opportunity_score > 50

    def test_cozy_high_supply_lower_opportunity(self):
        gaps = compute_gaps(self._make_genre_data())
        cozy = next((g for g in gaps if g.genre == "cozy"), None)
        assert cozy is not None
        assert cozy.competition_level == "high"

    def test_opportunity_score_range(self):
        gaps = compute_gaps(self._make_genre_data())
        for g in gaps:
            assert 0.0 <= g.opportunity_score <= 100.0

    def test_demand_signal_range(self):
        gaps = compute_gaps(self._make_genre_data())
        for g in gaps:
            assert 0.0 <= g.demand_signal <= 1.0

    def test_empty_genre_data(self):
        gaps = compute_gaps({})
        assert gaps == []

    def test_no_quality_data(self):
        genre_data = {
            "puzzle": {
                "game_count": 3,
                "avg_quality": None,  # Non ancora calcolato.
                "avg_players": 1000.0,
                "avg_reviews": 300.0,
                "game_ids": [1, 2, 3],
                "benchmark_median_reviews": 350,
            }
        }
        gaps = compute_gaps(genre_data)
        assert len(gaps) == 1
        assert gaps[0].avg_quality_score is None

    def test_game_ids_preserved(self):
        genre_data = {
            "roguelike": {
                "game_count": 2,
                "avg_quality": 70.0,
                "avg_players": 1000.0,
                "avg_reviews": 500.0,
                "game_ids": [10, 20],
                "benchmark_median_reviews": 1200,
            }
        }
        gaps = compute_gaps(genre_data)
        assert gaps[0].game_ids == [10, 20]


class TestCompetitionLevel:
    def test_low(self):
        assert _competition_level(1) == "low"
        assert _competition_level(3) == "low"

    def test_medium(self):
        assert _competition_level(4) == "medium"
        assert _competition_level(10) == "medium"

    def test_high(self):
        assert _competition_level(11) == "high"
        assert _competition_level(100) == "high"


class TestLogNorm:
    def test_zero(self):
        assert _log_norm(0.0, 100.0) == 0.0

    def test_negative(self):
        assert _log_norm(-5.0, 100.0) == 0.0

    def test_at_ref(self):
        result = _log_norm(100.0, 100.0)
        assert result == 1.0

    def test_above_ref_clamped(self):
        result = _log_norm(10000.0, 100.0)
        assert result == 1.0

    def test_proportional(self):
        low = _log_norm(10.0, 1000.0)
        mid = _log_norm(100.0, 1000.0)
        assert low < mid < 1.0


class TestFindMarketGaps:
    """Test di integrazione leggero con DB mockato."""

    def _make_mock_game(self, game_id: int, genres: list, tags: list,
                        quality: float | None = None) -> MagicMock:
        g = MagicMock()
        g.id = game_id
        g.genres = genres
        g.tags = tags
        g.quality_score = quality
        g.discarded = False
        return g

    def test_find_market_gaps_empty_db(self):
        from analysis.market_gaps import find_market_gaps
        session = MagicMock()
        scalars = MagicMock()
        scalars.__iter__ = MagicMock(return_value=iter([]))
        session.scalars.return_value = scalars
        result = find_market_gaps(session)
        assert result == []

    def test_find_market_gaps_with_games(self):
        from analysis.market_gaps import find_market_gaps
        games = [
            self._make_mock_game(1, ["Roguelike"], [], quality=70.0),
            self._make_mock_game(2, ["Roguelike"], [], quality=60.0),
            self._make_mock_game(3, ["Horror"], [], quality=None),
        ]

        session = MagicMock()
        call_count = 0

        def scalars_side_effect(query):
            nonlocal call_count
            mock = MagicMock()
            if call_count == 0:
                # Prima chiamata: giochi.
                mock.__iter__ = MagicMock(return_value=iter(games))
            else:
                # Seconda chiamata: snapshot.
                mock.__iter__ = MagicMock(return_value=iter([]))
            call_count += 1
            return mock

        session.scalars.side_effect = scalars_side_effect
        result = find_market_gaps(session)
        # Risultati devono contenere roguelike e horror.
        genres_found = {g.genre for g in result}
        assert "roguelike" in genres_found


# ---------------------------------------------------------------------------
# launch_health
# ---------------------------------------------------------------------------

from analysis.launch_health import (
    LaunchHealth,
    SignalBreakdown,
    _score_social_velocity,
    _score_review_sentiment,
    _score_player_trajectory,
    _score_marketing_coverage,
    _score_quality,
    _compute_health,
    _health_label,
    _clamp01,
    compute_launch_health,
    DEFAULT_WEIGHTS,
)


class TestHealthLabel:
    def test_excellent(self):
        assert _health_label(85) == "Excellent"
        assert _health_label(80) == "Excellent"

    def test_good(self):
        assert _health_label(70) == "Good"
        assert _health_label(60) == "Good"

    def test_fair(self):
        assert _health_label(55) == "Fair"
        assert _health_label(40) == "Fair"

    def test_at_risk(self):
        assert _health_label(39) == "At Risk"
        assert _health_label(0) == "At Risk"


class TestScoreSocialVelocity:
    def _make_posts(self, n: int, days_ago: float = 5.0) -> list[dict]:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        posted_at = now - timedelta(days=days_ago)
        return [{"posted_at": posted_at, "platform": "reddit"} for _ in range(n)]

    def test_no_posts(self):
        bd = _score_social_velocity([], None)
        assert bd.name == "social_velocity"
        assert not bd.available
        assert bd.normalized == 0.0

    def test_with_posts(self):
        posts = self._make_posts(10, days_ago=5.0)
        bd = _score_social_velocity(posts, None, window_days=30)
        assert bd.available
        assert bd.normalized > 0.0
        assert bd.raw_value > 0.0

    def test_normalized_in_range(self):
        posts = self._make_posts(1000, days_ago=1.0)
        bd = _score_social_velocity(posts, None)
        assert 0.0 <= bd.normalized <= 1.0


class TestScoreReviewSentiment:
    def _snap(self, total: int, positive: int, days_ago: int = 0) -> dict:
        from datetime import timedelta
        return {
            "captured_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
            "total_reviews": total,
            "total_positive": positive,
        }

    def test_no_snapshots(self):
        bd = _score_review_sentiment([])
        assert not bd.available
        assert bd.normalized == 0.5

    def test_high_positive(self):
        snaps = [self._snap(1000, 950, 60), self._snap(1200, 1140, 0)]
        bd = _score_review_sentiment(snaps)
        assert bd.available
        assert bd.normalized > 0.7

    def test_low_positive(self):
        snaps = [self._snap(1000, 500, 0)]
        bd = _score_review_sentiment(snaps)
        assert bd.normalized < 0.7

    def test_single_snapshot(self):
        bd = _score_review_sentiment([self._snap(100, 80, 0)])
        assert bd.available
        assert 0.0 <= bd.normalized <= 1.0


class TestScorePlayerTrajectory:
    def _snap(self, players: int, days_ago: int) -> dict:
        from datetime import timedelta
        return {
            "captured_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
            "current_players": players,
        }

    def test_insufficient_points(self):
        bd = _score_player_trajectory([self._snap(100, 0)])
        assert not bd.available
        assert bd.normalized == 0.5

    def test_growing(self):
        snaps = [self._snap(100, 30), self._snap(200, 0)]
        bd = _score_player_trajectory(snaps)
        assert bd.available
        assert bd.normalized > 0.5

    def test_declining(self):
        snaps = [self._snap(500, 30), self._snap(100, 0)]
        bd = _score_player_trajectory(snaps)
        assert bd.available
        assert bd.normalized < 0.5

    def test_stable(self):
        snaps = [self._snap(100, 30), self._snap(100, 0)]
        bd = _score_player_trajectory(snaps)
        assert bd.available
        assert abs(bd.normalized - 0.5) < 0.1


class TestScoreMarketingCoverage:
    def test_all_signals(self):
        game_data = {"has_demo": True, "has_trailer": True, "header_image": "https://img"}
        release = datetime.now(timezone.utc)
        from datetime import timedelta
        posts = [
            {"posted_at": release - timedelta(days=i + 5)} for i in range(5)
        ]
        bd = _score_marketing_coverage(game_data, posts, release)
        assert bd.normalized > 0.7

    def test_no_signals(self):
        game_data = {"has_demo": False, "has_trailer": False, "header_image": None}
        bd = _score_marketing_coverage(game_data, [], None)
        assert bd.normalized < 0.5

    def test_normalized_in_range(self):
        game_data = {"has_demo": True, "has_trailer": False, "header_image": None}
        bd = _score_marketing_coverage(game_data, [], None)
        assert 0.0 <= bd.normalized <= 1.0


class TestScoreQuality:
    def test_no_quality(self):
        bd = _score_quality(None)
        assert not bd.available
        assert bd.normalized == 0.5

    def test_high_quality(self):
        bd = _score_quality(90.0)
        assert bd.available
        assert bd.normalized == pytest.approx(0.9, rel=1e-4)

    def test_zero_quality(self):
        bd = _score_quality(0.0)
        assert bd.normalized == 0.0

    def test_max_quality(self):
        bd = _score_quality(100.0)
        assert bd.normalized == 1.0


class TestComputeHealth:
    def _make_signal(self, name: str, normalized: float) -> SignalBreakdown:
        return SignalBreakdown(
            name=name,
            raw_value=None,
            normalized=normalized,
            weight=0.0,
            contribution=0.0,
            available=True,
        )

    def test_all_perfect(self):
        signals = {
            "social_velocity": self._make_signal("social_velocity", 1.0),
            "review_sentiment": self._make_signal("review_sentiment", 1.0),
            "player_trajectory": self._make_signal("player_trajectory", 1.0),
            "marketing_coverage": self._make_signal("marketing_coverage", 1.0),
            "quality_score": self._make_signal("quality_score", 1.0),
        }
        score, _ = _compute_health(signals, DEFAULT_WEIGHTS)
        assert score == pytest.approx(100.0, rel=1e-4)

    def test_all_zero(self):
        signals = {
            "social_velocity": self._make_signal("social_velocity", 0.0),
            "review_sentiment": self._make_signal("review_sentiment", 0.0),
            "player_trajectory": self._make_signal("player_trajectory", 0.0),
            "marketing_coverage": self._make_signal("marketing_coverage", 0.0),
            "quality_score": self._make_signal("quality_score", 0.0),
        }
        score, _ = _compute_health(signals, DEFAULT_WEIGHTS)
        assert score == pytest.approx(0.0, rel=1e-4)

    def test_all_neutral(self):
        signals = {
            k: self._make_signal(k, 0.5)
            for k in ["social_velocity", "review_sentiment",
                      "player_trajectory", "marketing_coverage", "quality_score"]
        }
        score, _ = _compute_health(signals, DEFAULT_WEIGHTS)
        assert score == pytest.approx(50.0, rel=1e-4)

    def test_contributions_sum_to_score(self):
        signals = {
            "social_velocity": self._make_signal("social_velocity", 0.8),
            "review_sentiment": self._make_signal("review_sentiment", 0.6),
            "player_trajectory": self._make_signal("player_trajectory", 0.4),
            "marketing_coverage": self._make_signal("marketing_coverage", 0.7),
            "quality_score": self._make_signal("quality_score", 0.5),
        }
        score, signal_list = _compute_health(signals, DEFAULT_WEIGHTS)
        total_contribution = sum(s.contribution for s in signal_list)
        assert total_contribution == pytest.approx(score, rel=1e-4)


class TestComputeLaunchHealth:
    """Test di integrazione leggero con DB mockato."""

    def _make_session(self, game_has_quality: bool = True) -> MagicMock:
        session = MagicMock()
        game = MagicMock()
        game.has_demo = True
        game.header_image = "https://img"
        game.quality_score = 72.0 if game_has_quality else None
        game.release_date = None

        from datetime import date
        game.release_date = date(2026, 1, 1)

        session.get.return_value = game

        # Snapshot.
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        snaps = []
        for i in range(5, 0, -1):
            s = MagicMock()
            s.captured_at = now - timedelta(days=i * 7)
            s.current_players = 100 + i * 50
            s.total_reviews = 200 + i * 100
            s.total_positive = int((200 + i * 100) * 0.85)
            s.extra = {"has_trailer": True}
            snaps.append(s)

        posts = []
        for i in range(8):
            p = MagicMock()
            p.posted_at = now - timedelta(days=i * 3)
            p.platform = "reddit"
            p.likes = 10
            p.comments = 5
            posts.append(p)

        call_count = 0

        def scalars_side_effect(query):
            nonlocal call_count
            mock = MagicMock()
            if call_count == 0:
                mock.__iter__ = MagicMock(return_value=iter(snaps))
            else:
                mock.__iter__ = MagicMock(return_value=iter(posts))
            call_count += 1
            return mock

        session.scalars.side_effect = scalars_side_effect
        return session

    def test_returns_launch_health(self):
        session = self._make_session()
        result = compute_launch_health(1, session)
        assert isinstance(result, LaunchHealth)
        assert result.game_id == 1

    def test_score_in_range(self):
        session = self._make_session()
        result = compute_launch_health(1, session)
        assert 0.0 <= result.score <= 100.0

    def test_label_set(self):
        session = self._make_session()
        result = compute_launch_health(1, session)
        assert result.label in ("Excellent", "Good", "Fair", "At Risk")

    def test_signals_present(self):
        session = self._make_session()
        result = compute_launch_health(1, session)
        signal_names = {s.name for s in result.signals}
        assert "social_velocity" in signal_names
        assert "review_sentiment" in signal_names
        assert "player_trajectory" in signal_names
        assert "marketing_coverage" in signal_names
        assert "quality_score" in signal_names

    def test_to_dict(self):
        session = self._make_session()
        result = compute_launch_health(1, session)
        d = result.to_dict()
        assert "game_id" in d
        assert "score" in d
        assert "label" in d
        assert "signals" in d
        assert isinstance(d["signals"], list)

    def test_game_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        result = compute_launch_health(999, session)
        assert result.score == 0.0
        assert result.label == "At Risk"

    def test_custom_weights(self):
        session = self._make_session()
        weights = {
            "social_velocity": 0.5,
            "review_sentiment": 0.5,
            "player_trajectory": 0.0,
            "marketing_coverage": 0.0,
            "quality_score": 0.0,
        }
        result = compute_launch_health(1, session, weights=weights)
        assert isinstance(result, LaunchHealth)
        assert result.weights == weights
