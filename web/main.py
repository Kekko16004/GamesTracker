"""FastAPI application for GamesTracker web dashboard.

Serves HTML pages (Jinja2 + HTMX) and a JSON API that reads from the
same SQLite database used by the desktop GUI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web import data_access as da

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

log = logging.getLogger("web.main")

app = FastAPI(
    title="GamesTracker Dashboard",
    description="Indie game growth tracking — web dashboard",
    version="0.1.0",
)

# CORS — allow all origins for the local dashboard use-case.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Static files.
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Jinja2 templates.
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


def _score_class(score: Optional[float]) -> str:
    """CSS class name based on quality score band."""
    if score is None:
        return "score-none"
    if score >= 70:
        return "score-high"
    if score >= 40:
        return "score-mid"
    return "score-low"


def _platform_label(platform: str) -> str:
    """Human-readable platform label."""
    return {"steam": "Steam", "itch": "itch.io"}.get(platform, platform.capitalize())


def _social_icon(platform: str) -> str:
    """Unicode / text icon for a social platform."""
    icons = {
        "youtube": "▶",
        "reddit": "⬆",
        "tiktok": "♪",
        "instagram": "◉",
        "twitter": "𝕏",
        "discord": "◈",
    }
    return icons.get(platform.lower(), "◆")


# Register custom filters on the Jinja2 environment.
templates.env.filters["score_class"] = _score_class
templates.env.filters["platform_label"] = _platform_label
templates.env.filters["social_icon"] = _social_icon


def _base_context(request: Request) -> dict[str, Any]:
    """Common template context shared by all pages."""
    return {"request": request}


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    ctx = {**_base_context(request), "status_code": 404, "detail": exc.detail}
    return templates.TemplateResponse(request, "error.html", ctx, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception) -> HTMLResponse:
    log.exception("Unhandled server error")
    ctx = {**_base_context(request), "status_code": 500, "detail": "Internal server error"}
    return templates.TemplateResponse(request, "error.html", ctx, status_code=500)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Simple health check — returns 200 OK."""
    return {"status": "ok", "service": "GamesTracker Dashboard"}


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, tags=["pages"])
async def dashboard(
    request: Request,
    platform: Optional[str] = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    sort_by: str = Query("quality_score"),
    genre: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> HTMLResponse:
    """Main dashboard — game cards grid with filtering."""
    games = da.get_games_list(
        platform=platform,
        min_score=min_score,
        sort_by=sort_by,
        genre=genre,
        search=search,
    )
    # BUG 4 FIX: stats strip always shows totals, not filtered counts.
    stats = da.get_dashboard_stats(min_score=0.0)
    genres = da.get_available_genres()

    # Detect HTMX partial request (only re-render the cards grid).
    if request.headers.get("HX-Request"):
        ctx = {**_base_context(request), "games": games}
        return templates.TemplateResponse(request, "partials/game_list.html", ctx)

    ctx = {
        **_base_context(request),
        "games": games,
        "stats": stats,
        "genres": genres,
        "current_platform": platform or "",
        "current_min_score": min_score,
        "current_sort": sort_by,
        "current_genre": genre or "",
        "current_search": search or "",
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/game/{game_id}", response_class=HTMLResponse, tags=["pages"])
async def game_detail(request: Request, game_id: int) -> HTMLResponse:
    """Game detail page with charts, social timeline and growth metrics."""
    detail = da.get_game_detail(game_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    ctx = {**_base_context(request), "game": detail}
    return templates.TemplateResponse(request, "game_detail.html", ctx)


@app.get("/trends", response_class=HTMLResponse, tags=["pages"])
async def trends(request: Request, min_score: float = Query(0.0, ge=0.0, le=100.0)) -> HTMLResponse:
    """Genre trends view."""
    data = da.get_trend_data(min_score=min_score)
    ctx = {**_base_context(request), "data": data, "current_min_score": min_score}
    return templates.TemplateResponse(request, "trends.html", ctx)


@app.get("/reports", response_class=HTMLResponse, tags=["pages"])
async def reports(request: Request) -> HTMLResponse:
    """Report viewer."""
    report_list = da.get_reports_list()
    ctx = {**_base_context(request), "reports": report_list}
    return templates.TemplateResponse(request, "reports.html", ctx)


@app.get("/reports/{report_id}", response_class=HTMLResponse, tags=["pages"])
async def report_detail(request: Request, report_id: int) -> HTMLResponse:
    """Full report detail page with game info card, social posts, and charts."""
    rep = da.get_report_detail(report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    game = da.get_game_detail(rep["game_id"]) if rep.get("game_id") else None
    ctx = {**_base_context(request), "report": rep, "game": game}
    return templates.TemplateResponse(request, "report_detail.html", ctx)


@app.get("/social", response_class=HTMLResponse, tags=["pages"])
async def social(
    request: Request,
    platform: Optional[str] = Query(None, description="Filter by social platform"),
) -> HTMLResponse:
    """Dedicated social monitoring page — all posts across all games."""
    posts = da.get_all_social_posts(platform=platform)
    ctx = {
        **_base_context(request),
        "posts": posts,
        "current_platform": platform or "",
        # Collect distinct social platforms present in the data for the filter UI.
        "social_platforms": sorted({p["platform"] for p in da.get_all_social_posts() if p.get("platform")}),
    }
    return templates.TemplateResponse(request, "social.html", ctx)


@app.get("/ai", response_class=HTMLResponse, tags=["pages"])
async def ai_copilot(request: Request) -> HTMLResponse:
    """AI Copilot placeholder page."""
    ctx = {**_base_context(request)}
    return templates.TemplateResponse(request, "ai.html", ctx)


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------


@app.get("/api/games", tags=["api"])
async def api_games(
    platform: Optional[str] = Query(None, description="Filter by platform: steam or itch"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum quality score"),
    sort_by: str = Query("quality_score", description="Sort field: quality_score, growth, recency, title"),
    genre: Optional[str] = Query(None, description="Filter by genre string"),
    search: Optional[str] = Query(None, description="Search game title"),
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """JSON list of games with optional filtering and sorting."""
    return da.get_games_list(
        platform=platform,
        min_score=min_score,
        sort_by=sort_by,
        genre=genre,
        search=search,
        limit=limit,
        offset=offset,
    )


@app.get("/api/game/{game_id}/snapshots", tags=["api"])
async def api_game_snapshots(game_id: int) -> list[dict[str, Any]]:
    """JSON time-series snapshots for a single game."""
    snaps = da.get_game_snapshots(game_id)
    if not snaps:
        # Distinguish missing game from game with no snapshots by checking detail.
        detail = da.get_game_detail(game_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return snaps


@app.get("/api/game/{game_id}/social", tags=["api"])
async def api_game_social(game_id: int) -> dict[str, Any]:
    """JSON social accounts and posts for a single game."""
    detail = da.get_game_detail(game_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return da.get_game_social(game_id)


@app.get("/api/trends", tags=["api"])
async def api_trends(
    min_score: float = Query(0.0, ge=0.0, le=100.0),
) -> dict[str, Any]:
    """JSON genre trend data."""
    return da.get_trend_data(min_score=min_score)


@app.get("/api/reports", tags=["api"])
async def api_reports() -> list[dict[str, Any]]:
    """JSON list of analysis reports."""
    return da.get_reports_list()


@app.get("/api/reports/{report_id}", tags=["api"])
async def api_report_detail(report_id: int) -> dict[str, Any]:
    """JSON detail of a single report."""
    rep = da.get_report_detail(report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return rep
