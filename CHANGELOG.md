# Changelog

All notable changes to GamesTracker are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Planned
- RAWG, IGDB, HowLongToBeat, OpenCritic integrations
- TikTok / Instagram / X no-auth scrapers
- AI sentiment analysis (local transformer model)
- FastAPI web dashboard
- Docker + docker-compose
- GitHub Actions CI/CD
- Discord + Telegram notifications

---

## [2.0.0] — 2026-07-23

Major expansion: social scraping engine, new data source integrations, AI analysis layer, web dashboard, DevOps infrastructure, and community documentation.

### Added

#### Data Sources
- RAWG API integration — rich game metadata, genres, ratings, screenshots
- IGDB (Twitch) integration — authoritative game database with release calendar
- HowLongToBeat integration — playtime data by completion category
- OpenCritic integration — review aggregation and critic scores
- TikTok no-auth scraper — public post metrics via scraping approach
- Instagram no-auth scraper — public profile and post data
- X/Twitter scraper via Nitter — public tweet data without API key
- Reddit no-auth fallback — public JSON endpoint as backup to PRAW

#### Analysis
- AI sentiment analysis pipeline — transformer-based scoring of reviews and social posts
- Market gap finder — identifies under-served genres with data-driven opportunity scoring
- Launch health score — composite day-1 indicator predicting trajectory vs. historical breakouts

#### Web Dashboard (FastAPI)
- Browser-based read-only view of all collected data
- HTMX + Jinja2 — minimal JavaScript, fast page loads
- Live game rankings by quality score and growth rate
- Genre trend charts (embedded Chart.js)
- Individual game pages with full marketing timeline
- Embeddable widgets for external use

#### DevOps
- Dockerfile — multi-stage build (collector + web dashboard)
- docker-compose.yml — full stack: collector service + web service + volume for DB
- GitHub Actions CI workflow — ruff lint + pytest on push and pull request
- `.env.example` — complete with all new variables (RAWG, IGDB, scraping, notifications)

#### Notifications
- Discord webhook integration — alert on viral game detection and score thresholds
- Telegram bot integration — same alerts via Telegram channel

#### Community
- MIT License
- CONTRIBUTING.md — full contributor guide with patterns for sources, analysis, and GUI
- CODE_OF_CONDUCT.md — Contributor Covenant v2.1
- CHANGELOG.md — this file
- README.md rewritten as reference-grade open-source documentation

#### .claude Agents
- `social-scraper-engineer` — specialized agent for the scraping engine
- `devops-engineer` — specialized agent for Docker, CI/CD, and infrastructure
- `web-engineer` — specialized agent for FastAPI + HTMX web dashboard

#### .claude Commands
- `/run-tests` — run the full test suite with coverage
- `/add-source` — guided template for adding a new data source
- `/health-check` — verify all services are running
- `/scraping-status` — check the status of all active scraping jobs

### Changed
- `config/.env.example` expanded with all new variables
- `.claude/reference/data-sources.md` updated with RAWG, IGDB, HLtB, OpenCritic, TikTok, Instagram, X endpoints
- `.claude/reference/code-map.md` updated with all new modules
- `.claude/readme.md` updated to reference all new agents and commands

---

## [1.0.0] — 2026-07-21

Initial MVP release. Full end-to-end pipeline from data collection to desktop GUI, with bilingual reporting and quality score filtering.

### Added

#### Data Sources
- Steam discovery — AppList diffing + explore/new HTML scraping
- Steam Store API — appdetails (name, genres, developer, publisher, price, demo, trailer)
- Steam reviews tracking — append-only snapshot of `query_summary` (total, positive, negative)
- Steam player count — `GetNumberOfCurrentPlayers` with graceful key-optional degradation
- SteamSpy — owner estimates, CCU, tag data for trend analysis
- itch.io discovery — official RSS feed (`new-and-popular.xml`, tag feeds)
- itch.io game detail — OpenGraph / JSON-LD parsing from game pages
- YouTube Data API v3 — video search, view/like/comment tracking, quota-aware
- Reddit (PRAW) — post search across indie subreddits, dedup, read-only OAuth
- Manual social post import — TikTok/Instagram URL + metrics added via GUI dialog

#### Collector (Background Service)
- APScheduler with SQLAlchemy persistent job store (survives restarts)
- Discovery jobs: Steam + itch.io, configurable interval (default 6h)
- Snapshot jobs: +24h, +48h, +1 week, +1 month — append-only, backfill-aware
- Idempotent persistence — dedup on `(platform, external_id)`, no duplicate games
- Graceful error handling — network failures are logged and skipped, never crash

#### Analysis
- Quality score (0–100) — 5-component weighted score with log-normalization and multiplier penalties
- Growth metrics — `compute_deltas()` for all snapshot windows (+24h/48h/1w/1mo)
- Turning point detection — identifies spikes and drops in the growth curve
- Genre trend aggregation — pandas-based ranking of genres by growth rate
- Report generation — per-game and per-genre reports in IT and EN
- HTML export (always) and optional PDF export (weasyprint)

#### Desktop GUI (PyQt6)
- Dashboard — paginated game list, platform filter, quality score slider
- Game detail — metadata, quality score breakdown, marketing timeline, charts
- Trends view — genre ranking with sortable growth table
- Reports view — list of generated reports with preview and HTML export
- Manual import dialog — paste social post URL + metrics for TikTok/Instagram
- Language switch IT/EN — live at runtime via menu, no restart needed
- Background query workers — heavy DB queries run in QThreadPool, UI stays responsive

#### Core Infrastructure
- SQLAlchemy 2.x ORM with SQLite default (PostgreSQL-portable schema)
- Append-only snapshot tables — time series never overwritten
- `core/sources/_http.py` — shared HTTP client with retry/backoff, User-Agent, per-source throttling
- python-dotenv config — all secrets from `config/.env`, graceful degradation if keys missing
- i18n system — all UI strings in `gui/i18n/strings.py`, no hardcoded text

#### Tests
- 118 passed, 2 skipped (GUI tests skip without PyQt6 + display)
- 100% mocked — no real network calls in any test
- Coverage: sources, persistence, analysis, GUI data access, i18n, manual import

---

[Unreleased]: https://github.com/Kekko16004/GamesTracker/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/Kekko16004/GamesTracker/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/Kekko16004/GamesTracker/releases/tag/v1.0.0
