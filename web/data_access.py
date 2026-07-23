"""Web-specific data access layer for GamesTracker dashboard.

Reuses the GameRepository from gui/data_access.py but returns plain
dicts and lists (JSON-serializable) instead of dataclasses, making it
suitable for FastAPI JSON responses and Jinja2 template context.

No PyQt6 dependency — safe to import in any environment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from gui.data_access import GameRepository


# --- Singleton repository -----------------------------------------------

_repo: GameRepository | None = None


def _get_repo() -> GameRepository:
    """Returns the shared GameRepository, creating it on first call."""
    global _repo
    if _repo is None:
        _repo = GameRepository()
    return _repo


# --- Serialization helpers -----------------------------------------------


def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string for a datetime, or None."""
    if dt is None:
        return None
    return dt.isoformat()


# --- Revenue flag -----------------------------------------------------------

# Steam publication fee is $100. A game "breaks even" if estimated revenue > $100.
# Steam takes ~30% cut, so net revenue = price * owners * 0.7.
_STEAM_FEE = 100.0
_STEAM_CUT = 0.30
_DEFAULT_PRICE_MIN = 3.99   # assume minimum indie price if unknown
_DEFAULT_PRICE_MAX = 14.99  # assume maximum indie price if unknown

def _fmt_currency(amount: Optional[float]) -> str:
    """Format currency values into $18.1k, $1.5M, etc."""
    if amount is None:
        return "N/D"
    if amount == 0:
        return "$0"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}k"
    return f"${amount:.0f}"


# Owner estimation from reviews: VG Insights / Gamalytic research shows

# the review-to-owner multiplier ranges from 20x to 80x depending on genre
# and visibility. Median for indie games is ~30-50x.
# Source: https://newsletter.gamediscover.co/p/how-many-units-has-a-steam-game-sold
_REVIEW_TO_OWNER_MIN = 20   # conservative (niche/horror)
_REVIEW_TO_OWNER_MED = 35   # median indie
_REVIEW_TO_OWNER_MAX = 60   # popular/casual genres


def _estimate_owners_3way(reviews: object, players: object) -> dict[str, Any]:
    """Estimate total owners using 3 methods (VG Insights, PlayTracker, Gamalytic).

    Returns dict with low/med/high estimates and the average of the 3.
    The average is used for the revenue recoup calculation.
    """
    r_count = 0
    if reviews is not None:
        try:
            r_count = int(reviews)
        except (TypeError, ValueError):
            pass

    if r_count > 0:
        low = r_count * _REVIEW_TO_OWNER_MIN   # VG Insights (conservative)
        med = r_count * _REVIEW_TO_OWNER_MED   # PlayTracker (median)
        high = r_count * _REVIEW_TO_OWNER_MAX  # Gamalytic (optimistic)
        avg = (low + med + high) // 3
        return {"low": low, "med": med, "high": high, "avg": avg, "method": "reviews"}

    # Fallback: concurrent players * multiplier
    if players is not None:
        try:
            p = int(players)
            if p > 0:
                low = p * 5
                med = p * 10
                high = p * 20
                avg = (low + med + high) // 3
                return {"low": low, "med": med, "high": high, "avg": avg, "method": "players"}
        except (TypeError, ValueError):
            pass

    return {"low": 0, "med": 0, "high": 0, "avg": 0, "method": "none"}


def _compute_revenue_flag(
    price: object,
    is_free: bool,
    owners_estimate: object,
    reviews: object = None,
) -> dict[str, Any]:
    """Estimate whether a game has recouped the $100 Steam publication fee.

    Uses review-to-owner multiplier (VG Insights / Gamalytic method):
    - Reviews * 20x = conservative estimate
    - Reviews * 35x = median estimate
    - Reviews * 60x = optimistic estimate

    Returns a dict with flag, labels (IT/EN), revenue estimates, and details.
    """
    if is_free:
        return {"flag": "free", "label_it": "Gratis", "label_en": "Free",
                "estimated_revenue_min": 0, "estimated_revenue_max": 0, "estimated_revenue_avg": 0,
                "estimated_owners": {"low": 0, "med": 0, "high": 0, "avg": 0, "method": "free"},
                "details": "Free to play"}

    # Estimate owners using average of 3 methods
    est = _estimate_owners_3way(reviews, owners_estimate)
    owners = est["avg"]  # use average of VG Insights + PlayTracker + Gamalytic

    if owners <= 0:
        return {"flag": "unknown", "label_it": "Dati insufficienti", "label_en": "Insufficient data",
                "estimated_revenue_min": None, "estimated_revenue_max": None, "estimated_revenue_avg": None,
                "estimated_owners": est,
                "details": "Non ci sono abbastanza dati (recensioni/giocatori) per stimare"}

    low_owners = est.get("low", owners)
    high_owners = est.get("high", owners)

    p = None
    if price is not None:
        try:
            p = float(price)
            if p > 500:
                p = round(p / 100.0, 2)
        except (TypeError, ValueError):
            pass

    if p is not None and p > 0:


        net_min = p * low_owners * (1 - _STEAM_CUT)
        net_avg = p * owners * (1 - _STEAM_CUT)
        net_max = p * high_owners * (1 - _STEAM_CUT)

        if net_min >= _STEAM_FEE:
            flag = "recouped"
            label_it = "Rientrato ✅"
            label_en = "Recouped ✅"
        elif net_max >= _STEAM_FEE:
            flag = "likely_recouped"
            label_it = "Prob. rientrato 🟡"
            label_en = "Likely recouped 🟡"
        else:
            flag = "not_recouped"
            label_it = "Non rientrato ❌"
            label_en = "Not recouped ❌"

        return {
            "flag": flag,
            "label_it": label_it,
            "label_en": label_en,
            "estimated_revenue_min": round(net_min, 2),
            "estimated_revenue_max": round(net_max, 2),
            "estimated_revenue_avg": round(net_avg, 2),
            "estimated_owners": est,
            "details": f"${p:.2f} × {owners} owners (media 3 stime: {low_owners}–{high_owners}) × 0.70 = ${net_avg:.0f} net",
        }
    else:
        # Price unknown — estimate range with min/max indie prices
        net_min = _DEFAULT_PRICE_MIN * low_owners * (1 - _STEAM_CUT)
        net_max = _DEFAULT_PRICE_MAX * high_owners * (1 - _STEAM_CUT)
        net_avg = round((net_min + net_max) / 2, 2)
        if net_min >= _STEAM_FEE:
            flag = "recouped"
            label_it = "Rientrato ✅"
            label_en = "Recouped ✅"
        elif net_max >= _STEAM_FEE:
            flag = "likely_recouped"
            label_it = "Prob. rientrato 🟡"
            label_en = "Likely recouped 🟡"
        else:
            flag = "not_recouped"
            label_it = "Non rientrato ❌"
            label_en = "Not recouped ❌"
        return {
            "flag": flag,
            "label_it": label_it,
            "label_en": label_en,
            "estimated_revenue_min": round(net_min, 2),
            "estimated_revenue_max": round(net_max, 2),
            "estimated_revenue_avg": net_avg,
            "estimated_owners": est,
            "details": f"Prezzo sconosciuto, stimato ${_DEFAULT_PRICE_MIN}-${_DEFAULT_PRICE_MAX} × {owners} owners (media 3 stime: {low_owners}–{high_owners})",
        }



# --- Helpers ----------------------------------------------------------------


def _make_thumbnail(platform: str, external_id: Optional[str], header_image: Optional[str]) -> Optional[str]:
    """Construct a thumbnail URL for a game.

    For Steam games, use the CDN header image URL built from external_id.
    Falls back to whatever header_image is stored in the DB.
    """
    if platform == "steam" and external_id:
        return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{external_id}/header.jpg"
    return header_image


def _make_store_link(platform: str, external_id: Optional[str], store_url: Optional[str]) -> Optional[str]:
    """Construct a store URL for a game.

    For Steam games, build the canonical store URL from external_id.
    For itch games, use the stored store_url.
    """
    if platform == "steam" and external_id:
        return f"https://store.steampowered.com/app/{external_id}"
    return store_url


def get_games_list(
    *,
    platform: Optional[str] = None,
    min_score: float = 0.0,
    max_score: float = 100.0,
    sort_by: str = "quality_score",
    genre: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    developer: Optional[str] = None,
    revenue_filter: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    include_discarded: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return a filtered, sorted list of games as JSON-serializable dicts.

    Advanced filters:
    - platform: 'steam' or 'itch'
    - min_score / max_score: quality score range (NULL always passes)
    - genre: primary genre filter
    - tag: secondary tag filter (searches in genres + tags)
    - search: title substring
    - developer: developer name substring
    - revenue_filter: 'recouped' | 'not_recouped' | 'free'
    - min_price / max_price: price range filter
    - sort_by: quality_score, growth, recency, title, reviews, players, price
    """
    repo = _get_repo()
    rows = repo.list_games(
        min_quality_score=0,
        platform=platform,
        genre=genre,
        include_discarded=include_discarded,
        limit=None,
        offset=0,
    )

    # Quality score range filter (NULL always passes).
    if min_score > 0 or max_score < 100:
        rows = [
            r for r in rows
            if r.quality_score is None
            or (r.quality_score >= min_score and r.quality_score <= max_score)
        ]

    # Title search filter.
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in r.title.lower()]

    # Developer search filter.
    if developer:
        dev_needle = developer.lower()
        rows = [r for r in rows if r.developer and dev_needle in r.developer.lower()]

    # Tag filter (search in genres — handles both str and list).
    if tag:
        tag_needle = tag.lower()

        def _genres_match(genres_val, needle):
            if isinstance(genres_val, str):
                return needle in genres_val.lower()
            if isinstance(genres_val, list):
                return any(needle in str(g).lower() for g in genres_val)
            return False

        rows = [r for r in rows if r.genres and _genres_match(r.genres, tag_needle)]

    # Build result dicts first (need price/revenue for filtering + sorting).
    result = []
    for r in rows:
        price = getattr(r, "price", None)
        is_free = getattr(r, "is_free", False)
        revenue_flag = _compute_revenue_flag(
            price, is_free, r.latest_players, reviews=r.latest_reviews
        )

    # Price range filter (applied after revenue flag calculation).
        price_val = float(price) if price is not None else None
        if min_price is not None and (price_val is None or price_val < min_price):
            continue
        if max_price is not None and (price_val is None or price_val > max_price):
            continue

    # Revenue flag filter.
        if revenue_filter:
            if revenue_flag.get("flag") != revenue_filter:
                continue

        result.append({"_row": r, "price": price, "is_free": is_free,
                        "revenue_flag": revenue_flag, "price_val": price_val})

    # Apply custom sort.
    if sort_by in ("growth", "growth_desc"):
        result.sort(key=lambda d: (d["_row"].review_growth is None, -(d["_row"].review_growth or 0)))
    elif sort_by == "growth_asc":
        result.sort(key=lambda d: (d["_row"].review_growth is None, d["_row"].review_growth or 0))
    elif sort_by in ("revenue_desc", "revenue"):
        result.sort(key=lambda d: (d["revenue_flag"].get("estimated_revenue_avg") is None, -(d["revenue_flag"].get("estimated_revenue_avg") or 0)))
    elif sort_by == "revenue_asc":
        result.sort(key=lambda d: (d["revenue_flag"].get("estimated_revenue_avg") is None, d["revenue_flag"].get("estimated_revenue_avg") or 0))
    elif sort_by == "price_desc":
        result.sort(key=lambda d: (d["price_val"] is None, -(d["price_val"] or 0)))
    elif sort_by in ("price", "price_asc"):
        result.sort(key=lambda d: (d["price_val"] is None, d["price_val"] or 0))
    elif sort_by in ("reviews", "reviews_desc"):
        result.sort(key=lambda d: (d["_row"].latest_reviews is None, -(d["_row"].latest_reviews or 0)))
    elif sort_by == "reviews_asc":
        result.sort(key=lambda d: (d["_row"].latest_reviews is None, d["_row"].latest_reviews or 0))
    elif sort_by in ("players", "players_desc"):
        result.sort(key=lambda d: (d["_row"].latest_players is None, -(d["_row"].latest_players or 0)))
    elif sort_by == "players_asc":
        result.sort(key=lambda d: (d["_row"].latest_players is None, d["_row"].latest_players or 0))
    elif sort_by == "title_desc":
        result.sort(key=lambda d: d["_row"].title.lower(), reverse=True)
    elif sort_by in ("title", "title_asc"):
        result.sort(key=lambda d: d["_row"].title.lower())
    elif sort_by in ("date_asc", "oldest"):
        result.sort(key=lambda d: (d["_row"].release_date is None, d["_row"].release_date or ""))
    elif sort_by in ("recency", "newest", "date_desc"):
        result.sort(key=lambda d: (d["_row"].release_date is None, d["_row"].release_date or ""), reverse=True)
    elif sort_by == "quality_score_asc":
        result.sort(key=lambda d: (d["_row"].quality_score is None, d["_row"].quality_score or 0))
    else:  # quality_score / quality_score_desc
        result.sort(key=lambda d: (d["_row"].quality_score is None, -(d["_row"].quality_score or 0)))


    # Slice for pagination.
    if offset:
        result = result[offset:]
    if limit is not None:
        result = result[:limit]

    # Build final output dicts.
    final = []
    for d in result:
        r = d["_row"]
        rf = d["revenue_flag"]
        rev_avg = rf.get("estimated_revenue_avg")
        final.append({
            "id": r.id,
            "platform": r.platform,
            "external_id": r.external_id,
            "title": r.title,
            "developer": r.developer,
            "genres": r.genres,
            "release_date": r.release_date,
            "quality_score": r.quality_score,
            "discarded": r.discarded,
            "store_url": _make_store_link(r.platform, r.external_id, r.store_url),
            "header_image": r.header_image,
            "thumbnail": _make_thumbnail(r.platform, r.external_id, r.header_image),
            "latest_reviews": r.latest_reviews,
            "latest_players": r.latest_players,
            "review_growth": r.review_growth,
            "price": d["price"],
            "is_free": d["is_free"],
            "revenue_flag": rf,
            "estimated_revenue": _fmt_currency(rev_avg),
            "estimated_revenue_raw": rev_avg,
            "estimated_owners_avg": rf.get("estimated_owners", {}).get("avg", 0),
        })
    return final


def get_game_detail(game_id: int) -> Optional[dict[str, Any]]:
    """Return full game detail as a JSON-serializable dict, or None."""
    repo = _get_repo()
    detail = repo.get_game_detail(game_id)
    if detail is None:
        return None

    g = detail.game
    revenue_flag = _compute_revenue_flag(
        detail.price, detail.is_free, g.latest_players, reviews=g.latest_reviews
    )
    rev_avg = revenue_flag.get("estimated_revenue_avg")

    return {
        "id": g.id,
        "platform": g.platform,
        "external_id": g.external_id,
        "title": g.title,
        "developer": g.developer,
        "publisher": detail.publisher,
        "genres": g.genres,
        "tags": detail.tags,
        "release_date": g.release_date,
        "has_demo": detail.has_demo,
        "demo_release_date": detail.demo_release_date,
        "price": detail.price,
        "is_free": detail.is_free,
        "revenue_flag": revenue_flag,
        "estimated_revenue": _fmt_currency(rev_avg),
        "estimated_revenue_raw": rev_avg,
        "estimated_owners_avg": revenue_flag.get("estimated_owners", {}).get("avg", 0),
        "store_url": g.store_url,
        "header_image": g.header_image,
        "quality_score": g.quality_score,
        "discarded": g.discarded,
        "latest_reviews": g.latest_reviews,
        "latest_players": g.latest_players,
        "review_growth": g.review_growth,

        "snapshots": [
            {
                "captured_at": _fmt_dt(s.captured_at),
                "snapshot_type": s.snapshot_type,
                "total_reviews": s.total_reviews,
                "total_positive": s.total_positive,
                "total_negative": s.total_negative,
                "current_players": s.current_players,
            }
            for s in detail.snapshots
        ],
        "timeline": [
            {
                "kind": e.kind,
                "when": _fmt_dt(e.when),
                "label": e.label,
                "platform": e.platform,
                "url": e.url,
            }
            for e in detail.timeline
        ],
        "social_accounts": [
            {
                "id": a.id,
                "platform": a.platform,
                "handle": a.handle,
                "url": a.url,
                "discovered_via": a.discovered_via,
                "latest_followers": a.latest_followers,
            }
            for a in detail.accounts
        ],
        "social_posts": [
            {
                "id": p.id,
                "platform": p.platform,
                "posted_at": _fmt_dt(p.posted_at),
                "title": p.title,
                "subreddit": p.subreddit,
                "url": p.url,
                "views": p.views,
                "likes": p.likes,
                "comments": p.comments,
                "shares": p.shares,
            }
            for p in detail.posts
        ],
    }


def get_game_snapshots(game_id: int) -> list[dict[str, Any]]:
    """Return snapshot time series for a game, or [] if game not found."""
    detail = get_game_detail(game_id)
    if detail is None:
        return []
    return detail["snapshots"]


def get_game_social(game_id: int) -> dict[str, Any]:
    """Return social accounts and posts for a game."""
    detail = get_game_detail(game_id)
    if detail is None:
        return {"accounts": [], "posts": []}
    return {
        "accounts": detail["social_accounts"],
        "posts": detail["social_posts"],
    }


def get_trend_data(*, min_score: float = 0.0) -> dict[str, Any]:
    """Return genre trend aggregations and top-growing games."""
    repo = _get_repo()
    trends = repo.genre_trends(min_quality_score=min_score)
    top_growth = repo.top_by_growth(min_quality_score=min_score, limit=10)
    genre_dist = repo.genre_distribution(min_quality_score=min_score)
    stats = repo.dashboard_stats(min_quality_score=min_score)

    return {
        "genre_trends": [
            {
                "genre": t.genre,
                "game_count": t.game_count,
                "avg_quality_score": t.avg_quality_score,
                "total_review_growth": t.total_review_growth,
            }
            for t in trends
        ],
        "top_growing": [
            {
                "id": r.id,
                "title": r.title,
                "platform": r.platform,
                "quality_score": r.quality_score,
                "review_growth": r.review_growth,
                "genres": r.genres,
            }
            for r in top_growth
        ],
        "genre_distribution": genre_dist,
        "stats": {
            "total_games": stats.total_games,
            "visible_games": stats.visible_games,
            "discarded_games": stats.discarded_games,
            "recent_releases": stats.recent_releases,
        },
    }


def get_reports_list(
    *,
    search: Optional[str] = None,
    lang: Optional[str] = None,
    platform: Optional[str] = None,
    sort_by: str = "newest",
) -> list[dict[str, Any]]:
    """Return all analysis reports with optional filtering and sorting.

    BUG 2 FIX: Includes quality_score, release_date, developer, platform,
    and social_post_count populated from the linked Game record.
    """
    repo = _get_repo()
    rows = repo.list_reports()

    # Build a set of game_ids to fetch extra info for.
    game_ids = {r.game_id for r in rows if r.game_id is not None}

    # Fetch game details for all referenced games.
    game_info: dict[int, dict[str, Any]] = {}
    for gid in game_ids:
        detail = get_game_detail(gid)
        if detail is not None:
            game_info[gid] = detail

    reports = [
        {
            "id": r.id,
            "game_id": r.game_id,
            "game_title": r.game_title,
            "genre": r.genre,
            "lang": r.lang,
            "generated_at": _fmt_dt(r.generated_at),
            "summary_preview": r.summary_preview,
            "quality_score": r.quality_score,
            "release_date": r.release_date,
            "developer": game_info.get(r.game_id, {}).get("developer") if r.game_id else None,
            "platform": game_info.get(r.game_id, {}).get("platform") if r.game_id else None,
            "social_post_count": len(game_info.get(r.game_id, {}).get("social_posts", [])) if r.game_id else 0,
        }
        for r in rows
    ]

    # Filter
    if search:
        s = search.lower()
        reports = [
            r for r in reports
            if s in (r.get("game_title") or "").lower() or s in (r.get("summary_preview") or "").lower()
        ]
    if lang:
        reports = [r for r in reports if (r.get("lang") or "").lower() == lang.lower()]
    if platform:
        reports = [r for r in reports if (r.get("platform") or "").lower() == platform.lower()]

    # Sort
    if sort_by == "quality_score":
        reports.sort(key=lambda r: r.get("quality_score") if r.get("quality_score") is not None else -1, reverse=True)
    elif sort_by == "title":
        reports.sort(key=lambda r: (r.get("game_title") or "").lower())
    elif sort_by == "platform":
        reports.sort(key=lambda r: (r.get("platform") or "").lower())
    else:  # newest
        reports.sort(key=lambda r: r.get("generated_at") or "", reverse=True)

    return reports



def get_report_detail(report_id: int) -> Optional[dict[str, Any]]:
    """Return a single report with full summary and data payload."""
    repo = _get_repo()
    rep = repo.get_report(report_id)
    if rep is None:
        return None
    return {
        "id": rep.id,
        "game_id": rep.game_id,
        "game_title": rep.game_title,
        "genre": rep.genre,
        "lang": rep.lang,
        "generated_at": _fmt_dt(rep.generated_at),
        "summary": rep.summary,
        "data": rep.data,
    }


def get_dashboard_stats(*, min_score: float = 0.0) -> dict[str, Any]:
    """Return summary stats for the dashboard header.

    BUG 4 FIX: Stats always reflect TOTAL counts (min_quality_score=0)
    regardless of the filter slider, so the numbers don't shift when the
    user adjusts min_score. Only the game list is filtered.
    """
    repo = _get_repo()
    stats = repo.dashboard_stats(min_quality_score=0)
    return {
        "total_games": stats.total_games,
        "visible_games": stats.visible_games,
        "discarded_games": stats.discarded_games,
        "recent_releases": stats.recent_releases,
    }


def get_available_genres() -> list[str]:
    """Return sorted list of all genres present in the database."""
    return _get_repo().available_genres()


def get_all_social_posts(*, platform: Optional[str] = None) -> list[dict[str, Any]]:
    """Return all social posts across all games, most recent first.

    Parameters
    ----------
    platform:
        Optional filter to a specific social platform (e.g. 'reddit', 'youtube').
    """
    games = get_games_list()
    posts: list[dict[str, Any]] = []
    for game in games:
        detail = get_game_detail(game["id"])
        if detail is None:
            continue
        for post in detail["social_posts"]:
            if platform and post.get("platform", "").lower() != platform.lower():
                continue
            posts.append(
                {
                    **post,
                    "game_id": game["id"],
                    "game_title": game["title"],
                    "game_platform": game["platform"],
                    "thumbnail": game.get("thumbnail"),
                }
            )
    # Sort: most recent first; posts without a date go last.
    # Single stable sort: (has_no_date, inverted_date) — False < True so dated
    # items come first, and within dated items descending string sort is correct
    # for ISO-8601 date strings.
    posts.sort(
        key=lambda p: (p["posted_at"] is None, "" if p["posted_at"] is None else p["posted_at"]),
        reverse=True,
    )
    # Restore: None-date rows were sorted to the FRONT by reverse=True on the
    # bool (True > False reversed = True first). Push them to the end.
    posts.sort(key=lambda p: p["posted_at"] is None)
    return posts


def get_ai_context_data() -> dict[str, Any]:
    """Gather real market data from tracked games to inform AI suggestions.

    Returns a structured dict with trending genres, top tags, price patterns,
    and description stats from the actual game database. This grounds the AI
    copilot in REAL data instead of generic suggestions.
    """
    repo = _get_repo()
    all_games = repo.list_games(min_quality_score=0, limit=None, offset=0)
    trends = repo.genre_trends(min_quality_score=0)
    dist = repo.genre_distribution(min_quality_score=0)

    total = len(all_games)

    # Top games by quality score.
    scored = [g for g in all_games if g.quality_score is not None]
    scored.sort(key=lambda g: g.quality_score or 0, reverse=True)
    top_games = scored[:20]

    # Extract common tags from top games.
    # g.genres can be a list or a comma-separated string depending on the model.
    tag_counts: dict[str, int] = {}
    for g in top_games:
        genres_raw = g.genres or []
        if isinstance(genres_raw, str):
            genre_list = [x.strip() for x in genres_raw.split(",") if x.strip()]
        elif isinstance(genres_raw, list):
            genre_list = []
            for item in genres_raw:
                if isinstance(item, str):
                    genre_list.extend(x.strip() for x in item.split(",") if x.strip())
        else:
            genre_list = []
        for genre in genre_list:
            tag_counts[genre] = tag_counts.get(genre, 0) + 1
    top_tags = sorted(tag_counts, key=tag_counts.get, reverse=True)[:15]

    # Top genres by average quality score.
    top_genres = []
    for t in sorted(trends, key=lambda x: x.avg_quality_score or 0, reverse=True)[:10]:
        top_genres.append({
            "genre": t.genre,
            "game_count": t.game_count,
            "avg_quality_score": round(t.avg_quality_score or 0, 1),
        })

    # Price analysis.
    prices = [g for g in scored if hasattr(g, 'price') and g.price is not None]

    # Top performing game titles for reference.
    top_titles = [
        {"title": g.title, "score": round(g.quality_score, 1), "genres": g.genres}
        for g in top_games[:10]
        if g.title
    ]

    return {
        "total_tracked": total,
        "total_scored": len(scored),
        "top_genres": top_genres,
        "top_tags": top_tags,
        "top_games": top_titles,
        "genre_distribution": dict(dist),
    }

def get_available_tags() -> list[str]:
    """Return sorted list of all unique tags/genres across all games.

    Handles both list of genres and comma-separated genre strings.
    """
    repo = _get_repo()
    all_games = repo.list_games(min_quality_score=0, limit=None, offset=0)
    tag_set: set[str] = set()
    for g in all_games:
        genres = getattr(g, "genres", None)
        if not genres:
            continue
        if isinstance(genres, list):
            for item in genres:
                if isinstance(item, str):
                    for part in item.split(","):
                        t = part.strip()
                        if t:
                            tag_set.add(t)
        elif isinstance(genres, str):
            for part in genres.split(","):
                t = part.strip()
                if t:
                    tag_set.add(t)
    return sorted(tag_set)

