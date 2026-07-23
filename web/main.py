"""FastAPI application for GamesTracker web dashboard.

Serves HTML pages (Jinja2 + HTMX) and a JSON API that reads from the
same SQLite database used by the desktop GUI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from gui.simulator_logic import SimulatorInputs, simulate_score
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
    allow_methods=["GET", "POST"],
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
    max_score: float = Query(100.0, ge=0.0, le=100.0),
    sort_by: str = Query("quality_score"),
    genre: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    developer: Optional[str] = Query(None),
    revenue: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
) -> HTMLResponse:
    """Main dashboard — game cards grid with advanced filtering."""
    games = da.get_games_list(
        platform=platform,
        min_score=min_score,
        max_score=max_score,
        sort_by=sort_by,
        genre=genre,
        tag=tag,
        search=search,
        developer=developer,
        revenue_filter=revenue,
        min_price=min_price,
        max_price=max_price,
    )
    stats = da.get_dashboard_stats(min_score=0.0)
    genres = da.get_available_genres()
    tags = da.get_available_tags()

    # Detect HTMX partial request (only re-render the cards grid).
    if request.headers.get("HX-Request"):
        ctx = {**_base_context(request), "games": games}
        return templates.TemplateResponse(request, "partials/game_list.html", ctx)

    ctx = {
        **_base_context(request),
        "games": games,
        "stats": stats,
        "genres": genres,
        "tags": tags,
        "current_platform": platform or "",
        "current_min_score": min_score,
        "current_max_score": max_score,
        "current_sort": sort_by,
        "current_genre": genre or "",
        "current_tag": tag or "",
        "current_search": search or "",
        "current_developer": developer or "",
        "current_revenue": revenue or "",
        "current_min_price": min_price if min_price is not None else "",
        "current_max_price": max_price if max_price is not None else "",
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Scan Now (trigger collector from web)
# ---------------------------------------------------------------------------


@app.post("/scan", tags=["pages"])
async def scan_now(request: Request) -> JSONResponse:
    """Trigger a one-shot collection run (same as GUI 'Raccogli ora').

    Runs in a background thread so the web request returns immediately.
    The collector writes to the shared SQLite DB.
    """
    import threading

    def _run_collector():
        try:
            from collector.run_once import run_once
            run_once(include_social=True)
        except Exception:
            log.exception("Scan Now: collector failed")

    thread = threading.Thread(target=_run_collector, daemon=True)
    thread.start()
    return JSONResponse({"status": "started", "message": "Collection started in background"})


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
    """AI Copilot — data-driven game marketing assistant."""
    context_data = da.get_ai_context_data()
    ctx = {
        **_base_context(request),
        "context_games": context_data.get("total_tracked", 0),
    }
    return templates.TemplateResponse(request, "ai.html", ctx)


@app.post("/api/ai/generate", tags=["api"])
async def ai_generate(request: Request) -> JSONResponse:
    """Generate game marketing materials using the AI copilot.

    Accepts a JSON body with the game brief, loads real market context
    from tracked games, and returns descriptions, titles, image prompts,
    tags, and marketing hooks — all grounded in actual data.
    """
    import asyncio

    body = await request.json()
    desc = (body.get("game_description") or "").strip()
    if not desc:
        return JSONResponse({"error": "game_description is required"}, status_code=400)

    # Load real market context from DB.
    trending_data = da.get_ai_context_data()

    try:
        from core.ai.llm_client import LLMClient, load_llm_config, LLMError
        from core.ai.game_copilot import GameBrief, GameCopilot

        config = load_llm_config()
        if not config.api_key:
            return JSONResponse({
                "error": "AI non configurata. Aggiungi in config/.env:\n"
                         "AI_PROVIDER=openrouter\n"
                         "AI_API_KEY=sk-or-v1-...\n"
                         "AI_MODEL=anthropic/claude-sonnet-4"
            }, status_code=400)

        playtime = None
        if body.get("estimated_playtime_hours"):
            try:
                playtime = float(body["estimated_playtime_hours"])
            except (TypeError, ValueError):
                pass

        brief = GameBrief(
            game_description=desc,
            genre=body.get("genre") or None,
            art_style=body.get("art_style") or None,
            target_audience=body.get("target_audience") or None,
            similar_games=(body.get("similar_games") or "").split(",") if body.get("similar_games") else None,
            character_description=body.get("character_description") or None,
            estimated_playtime_hours=playtime,
        )

        client = LLMClient(config)
        copilot = GameCopilot(client=client, trending_data=trending_data)

        try:
            result = await copilot.generate_all(brief)
        finally:
            await client.close()

        # Serialize CopilotResult to dict.
        return JSONResponse({
            "steam_description_short": getattr(result, "steam_description_short", ""),
            "steam_description_long": getattr(result, "steam_description_long", ""),
            "titles": getattr(result, "titles", []),
            "image_prompts": getattr(result, "image_prompts", {}),
            "tags": getattr(result, "tags", []),
            "elevator_pitch": getattr(result, "elevator_pitch", ""),
            "marketing_hooks": getattr(result, "marketing_hooks", []),
        })
    except ImportError:
        return JSONResponse({
            "error": "Modulo AI non disponibile. Verifica che core/ai/ esista."
        }, status_code=500)
    except Exception as exc:
        log.exception("AI generation failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Quality Score Simulator
# ---------------------------------------------------------------------------


def _split_csv(value: str) -> list[str]:
    """Splits a comma-separated form field into a clean list of strings."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _form_float(form: Any, key: str, default: float = 0.0) -> float:
    """Reads a float from form data, tolerating empty strings."""
    raw = form.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _form_int(form: Any, key: str, default: int = 0) -> int:
    """Reads an int from form data, tolerating empty strings and floats."""
    raw = form.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _form_bool(form: Any, key: str) -> bool:
    """Reads a checkbox from form data (present with any value => True)."""
    return form.get(key) is not None


def _lowest_components(breakdown: dict[str, Any], n: int = 2) -> list[str]:
    """Returns the ``n`` lowest-scoring component names from a breakdown."""
    components = breakdown.get("components") or {}
    ordered = sorted(components.items(), key=lambda kv: kv[1])
    return [name for name, _score in ordered[:n]]


_SIMULATOR_TIPS: dict[str, str] = {
    "store_page": (
        "Add a trailer, at least 5 screenshots, and a longer description "
        "(600+ characters) with clear genres/tags to boost your store page score."
    ),
    "reviews": (
        "Reviews carry the highest weight (30%). Focus on getting more players "
        "to leave reviews, and aim for a high positive percentage."
    ),
    "social": (
        "Be active on more platforms and post more consistently. Even modest, "
        "regular posting improves this component."
    ),
    "growth": (
        "Growth is measured over time from real snapshots and stays neutral "
        "here in the simulator — it isn't something you can directly input."
    ),
    "care": (
        "Add a demo, list an official site, and consider your pricing — these "
        "'care signals' show players the project is actively maintained."
    ),
}


@app.get("/simulator", response_class=HTMLResponse, tags=["pages"])
async def simulator_page(request: Request) -> HTMLResponse:
    """Quality Score Simulator — empty form, no result yet."""
    ctx = {**_base_context(request), "result": None}
    return templates.TemplateResponse(request, "simulator.html", ctx)


@app.post("/simulator", response_class=HTMLResponse, tags=["pages"])
async def simulator_calculate(request: Request) -> HTMLResponse:
    """Parses the simulator form, computes the quality score, and renders results."""
    form = await request.form()

    inputs = SimulatorInputs(
        title=str(form.get("title") or ""),
        description=str(form.get("description") or ""),
        screenshot_count=_form_int(form, "screenshot_count"),
        has_trailer=_form_bool(form, "has_trailer"),
        has_header=_form_bool(form, "has_header"),
        genres=_split_csv(str(form.get("genres") or "")),
        tags=_split_csv(str(form.get("tags") or "")),
        price=_form_float(form, "price"),
        is_free=_form_bool(form, "is_free"),
        has_demo=_form_bool(form, "has_demo"),
        developer_other_games=_form_bool(form, "developer_other_games"),
        has_official_site=_form_bool(form, "has_official_site"),
        review_pct_positive=_form_float(form, "review_pct_positive"),
        review_count=_form_int(form, "review_count"),
        social_platforms=_form_int(form, "social_platforms"),
        social_post_count=_form_int(form, "social_post_count"),
    )

    score, breakdown = simulate_score(inputs)

    result = {
        "score": score,
        "breakdown": breakdown,
        "score_class": _score_class(score),
        "lowest_components": _lowest_components(breakdown),
        "tips": _SIMULATOR_TIPS,
        "inputs": {
            "title": inputs.title,
            "description": inputs.description,
            "screenshot_count": inputs.screenshot_count,
            "has_trailer": inputs.has_trailer,
            "has_header": inputs.has_header,
            "genres": ", ".join(inputs.genres),
            "tags": ", ".join(inputs.tags),
            "price": inputs.price,
            "is_free": inputs.is_free,
            "has_demo": inputs.has_demo,
            "developer_other_games": inputs.developer_other_games,
            "has_official_site": inputs.has_official_site,
            "review_count": inputs.review_count,
            "review_pct_positive": inputs.review_pct_positive,
            "social_platforms": inputs.social_platforms,
            "social_post_count": inputs.social_post_count,
        },
    }

    ctx = {**_base_context(request), "result": result}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "partials/simulator_results.html", ctx)
    return templates.TemplateResponse(request, "simulator.html", ctx)


# ---------------------------------------------------------------------------
# Manual Social Post Import
# ---------------------------------------------------------------------------


@app.post("/game/{game_id}/add-post", tags=["pages"])
async def add_social_post(request: Request, game_id: int):
    """Saves a manually-entered social post for a game via the core import path."""
    detail = da.get_game_detail(game_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    form = await request.form()

    platform = str(form.get("platform") or "").strip()
    url = str(form.get("url") or "").strip()
    title = str(form.get("title") or "").strip() or None
    handle = str(form.get("handle") or "").strip() or None

    posted_at_raw = str(form.get("posted_at") or "").strip()
    posted_at: Optional[datetime] = None
    if posted_at_raw:
        try:
            posted_at = datetime.strptime(posted_at_raw, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            posted_at = None

    def _metric(key: str) -> Optional[int]:
        raw = str(form.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    if not platform or not url:
        raise HTTPException(status_code=400, detail="platform and url are required")

    from core.db import session_scope
    from core.sources.social.manual_import import ManualImportError, import_manual_post

    try:
        with session_scope() as session:
            import_manual_post(
                session,
                game_id=game_id,
                platform=platform,
                url=url,
                posted_at=posted_at,
                title=title,
                views=_metric("views"),
                likes=_metric("likes"),
                comments=_metric("comments"),
                shares=_metric("shares"),
                handle=handle,
            )
    except ManualImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url=f"/game/{game_id}", status_code=303)


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
