# 🎮 GamesTracker

> **Real market intelligence for indie game developers** — track new releases, decode viral growth, and find your marketing edge with hard data.

[![CI](https://github.com/Kekko16004/GamesTracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Kekko16004/GamesTracker/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

**GamesTracker** is an open-source desktop + web intelligence platform for indie game developers. It continuously collects data from Steam, itch.io, YouTube, Reddit and social platforms, scores every game against a quality filter, and surfaces the patterns that separate viral breakout hits from the noise.

- **Understand what genres are winning right now** — aggregated growth data across hundreds of new releases, updated every few hours
- **Decode marketing timelines** — see exactly when demos, trailers, and social posts correlated with player count and review spikes
- **Stop guessing, start tracking** — quality-scored, time-series data persisted forever so trends become visible over weeks and months

> UI language: **bilingual IT/EN** (switch at runtime). All documentation and code is in English.

---

## Architecture

Two fully independent processes communicate only through a shared SQLite database — the collector runs 24/7 in the background while the GUI stays lightweight and always-snappy.

```
  DATA SOURCES              COLLECTOR (background)              CONSUMERS
  ┌──────────┐             ┌─────────────────────────┐
  │  Steam   │──────────►  │ APScheduler (persistent) │
  │  itch.io │             │  · Discovery: new games  │
  │  YouTube │──────────►  │  · Snapshots +24h/48h/   │──────► SQLite DB ◄──── GUI (PyQt6)
  │  Reddit  │             │    +1w / +1mo            │            │             (read-only)
  │  RAWG    │──────────►  │  · Social collectors     │            │
  │  IGDB    │             │  · AI sentiment scoring  │            └──────────► Web Dashboard
  │  TikTok* │──────────►  └─────────────────────────┘                         (FastAPI)
  │  Instagram│
  │  HLtB    │             * social scrapers (rate-limited, graceful degradation)
  │  OpenCritic│
  └──────────┘
                                   Analysis Layer
                         ┌──────────────────────────────┐
                         │ quality_score · growth · trend│
                         │ AI sentiment · market gaps    │
                         │ launch health · reports IT/EN │
                         └──────────────────────────────┘
```

---

## Feature Matrix

| Feature | Status | Notes |
|---|---|---|
| Steam discovery (new releases) | ✅ Implemented | AppList diff + explore/new |
| itch.io discovery (RSS) | ✅ Implemented | Official RSS feed |
| Steam review tracking | ✅ Implemented | Append-only snapshots |
| Steam player count | ✅ Implemented | GetNumberOfCurrentPlayers |
| SteamSpy owner estimates | ✅ Implemented | Trend proxy |
| YouTube video tracking | ✅ Implemented | Data API v3, quota-aware |
| Reddit mentions | ✅ Implemented | PRAW, read-only |
| Quality score (0–100) | ✅ Implemented | Anti-trash filter |
| Growth tracking (+24h/48h/1w/1mo) | ✅ Implemented | Append-only time series |
| Genre trend analysis | ✅ Implemented | pandas aggregation |
| Bilingual reports (IT/EN) | ✅ Implemented | HTML + PDF export |
| PyQt6 desktop GUI | ✅ Implemented | Dashboard, detail, trends, reports |
| Manual social post import | ✅ Implemented | TikTok/IG URL + metrics |
| RAWG game database | 🚧 In progress | Rich metadata enrichment |
| IGDB (Twitch) | 🚧 In progress | Authoritative game metadata |
| HowLongToBeat | 🚧 In progress | Playtime data |
| OpenCritic | 🚧 In progress | Review aggregation |
| TikTok scraping (no-auth) | 🚧 In progress | Nitter-style approach |
| Instagram scraping | 🚧 In progress | Public profile data |
| X/Twitter scraping | 🚧 In progress | No-auth public data |
| AI sentiment analysis | 🚧 In progress | Reviews + social posts |
| Market gap finder | 🚧 In progress | Under-served genres |
| Launch health score | 🚧 In progress | Composite launch indicator |
| FastAPI web dashboard | 🚧 In progress | HTMX + Jinja2 |
| Docker / docker-compose | 🚧 In progress | Multi-stage build |
| Discord / Telegram notifications | 🚧 In progress | Webhook alerts |
| GitHub Actions CI/CD | 🚧 In progress | Lint + test on push |

---

## Screenshots

| Dashboard | Game Detail | Trends |
|---|---|---|
| ![Dashboard view showing tracked games with quality score filter slider](docs/screenshots/dashboard.png) | ![Game detail view with marketing timeline, review chart and player count graph](docs/screenshots/game_detail.png) | ![Genre trend aggregation showing growth rates by category](docs/screenshots/trends.png) |

| Reports | Web Dashboard |
|---|---|
| ![Bilingual IT/EN report viewer with HTML export](docs/screenshots/reports.png) | ![FastAPI web dashboard with live game metrics](docs/screenshots/web_dashboard.png) |

> Screenshots coming soon — run the app and contribute your own!

---

## Quick Start

```bash
# 1. Clone and create virtualenv
git clone https://github.com/Kekko16004/GamesTracker.git && cd GamesTracker
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (API keys optional — app degrades gracefully without them)
cp config/.env.example config/.env

# Start the background collector (leave running)
python run_collector.py

# Open the desktop GUI (separate terminal)
python run_gui.py
```

The collector must run continuously to build the time-series data that powers everything. Start it once and leave it running — on first launch it discovers games and schedules snapshot jobs automatically. The GUI reads only from the database and can be opened/closed freely.

---

## Docker Quick Start

```bash
# Build and start everything (collector + web dashboard)
docker-compose up -d

# View logs
docker-compose logs -f collector

# Stop
docker-compose down
```

The Docker setup runs the collector as a service and exposes the web dashboard on port `8080` by default. The SQLite database is persisted in a named volume. See [docker-compose.yml](docker-compose.yml) for full configuration.

---

## Configuration

All configuration is done via environment variables in `config/.env` (copy from `config/.env.example`). **Never commit `.env`.**

### Core API Keys

| Variable | Source | Required | Notes |
|---|---|---|---|
| `STEAM_WEB_API_KEY` | [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) | Optional | Free. Enables player count. Degrades gracefully. |
| `YOUTUBE_API_KEY` | Google Cloud Console | Needed for YouTube | Free tier: 10,000 units/day |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) | Needed for Reddit | Script app type |
| `REDDIT_CLIENT_SECRET` | Same as above | Needed for Reddit | |
| `REDDIT_USER_AGENT` | Your choice | Needed for Reddit | Format: `AppName/version by u/username` |
| `RAWG_API_KEY` | [rawg.io/apidocs](https://rawg.io/apidocs) | Optional | Free tier available |
| `TWITCH_CLIENT_ID` | [dev.twitch.tv](https://dev.twitch.tv/console) | Needed for IGDB | IGDB is Twitch-owned |
| `TWITCH_CLIENT_SECRET` | Same as above | Needed for IGDB | |

### Social Scraping

| Variable | Default | Notes |
|---|---|---|
| `SCRAPING_ENABLED` | `false` | Master switch for social scrapers |
| `SCRAPING_INTERVAL_HOURS` | `6` | How often scrapers run |
| `NITTER_INSTANCE` | `https://nitter.net` | Self-hosted Nitter for X/Twitter |
| `PROXY_URL` | _(empty)_ | HTTP proxy for scrapers (optional) |

### Notifications

| Variable | Default | Notes |
|---|---|---|
| `NOTIFICATIONS_ENABLED` | `false` | Master switch |
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord channel webhook URL |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Telegram bot token |
| `TELEGRAM_CHAT_ID` | _(empty)_ | Target chat/channel ID |

### Application

| Variable | Default | Notes |
|---|---|---|
| `DB_URL` | `sqlite:///data/gamestracker.db` | SQLAlchemy URL. Supports PostgreSQL. |
| `APP_LANG` | `it` | Default UI language: `it` or `en` |
| `QUALITY_SCORE_THRESHOLD` | `40` | Games below this score are filtered as "trash" |
| `DISCOVERY_INTERVAL_HOURS` | `6` | How often to scan for new releases |
| `WEB_PORT` | `8080` | Port for the FastAPI web dashboard |
| `HTTP_USER_AGENT` | `GamesTracker/2.0` | Identifies the app in HTTP requests (ToS compliance) |

---

## Web Dashboard

The FastAPI web dashboard provides a browser-based read-only view of all tracked data — useful for sharing insights with a team or accessing from a remote server.

```bash
# Start the web dashboard (requires the collector DB to be populated)
python -m uvicorn web.app:app --port 8080 --reload
```

Navigate to `http://localhost:8080`. The dashboard is built with HTMX + Jinja2 for a fast, minimal-JS experience. It reads the same SQLite database as the desktop GUI — no separate data layer.

**Web dashboard features:**
- Live game rankings by quality score and growth rate
- Genre trend charts
- Individual game pages with full marketing timeline
- Embeddable widgets (iframe-friendly)

---

## Social Scraping

GamesTracker includes a modular social scraping engine in `core/sources/social/` that collects public data from platforms that do not provide developer-friendly APIs.

### Approach by Platform

| Platform | Method | Auth Required | Status | Notes |
|---|---|---|---|---|
| YouTube | Official Data API v3 | API key | ✅ Active | Quota-aware, 10k units/day |
| Reddit | PRAW (official OAuth) | Client credentials | ✅ Active | 100 QPM, read-only |
| TikTok | No-auth public scraping | None | 🚧 Beta | Rate-limited, graceful degradation |
| Instagram | Public profile scraping | None | 🚧 Beta | Rate-limited, proxy-aware |
| X/Twitter | Nitter instance scraping | None | 🚧 Beta | Requires self-hosted or public Nitter |

**Design principles for the scraper engine:**
- **Graceful degradation**: if a scraper fails (rate limit, block, ToS change), the collector continues without crashing — it logs the failure and skips.
- **Rate limiting**: each scraper implements per-platform throttling based on empirically observed limits.
- **ToS awareness**: the app only scrapes publicly visible data. It never requires user login or session tokens for third-party accounts.
- **Proxy support**: set `PROXY_URL` to route scraper traffic through a proxy.
- **Manual fallback**: for TikTok and Instagram, the desktop GUI includes a "Add social post" dialog so you can paste URLs and metrics manually. This is always available regardless of scraper status.

---

## AI Features

GamesTracker includes an analysis layer that applies lightweight AI models to the collected data.

### Sentiment Analysis
Runs on Steam reviews and Reddit posts to surface positive/negative sentiment trends over time. Implemented with a local transformer model (no API required).

### Market Gap Finder
Analyzes genre distribution and quality scores to identify categories with high demand but low supply of quality titles — potential opportunities.

### Launch Health Score
A composite indicator computed at launch day that predicts the trajectory of a game based on its first-week metrics pattern compared to historical breakout games in the same genre.

---

## Contributing

We welcome contributions from developers, data engineers, and game industry researchers. GamesTracker is built to be extended — adding a new data source is a matter of implementing one clean Python class.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, including:
- Dev environment setup
- Code style (ruff, type hints, tested modules)
- How to add a new data source
- How to add a new analysis module
- How to add GUI views
- PR checklist

---

## Roadmap

**v2.1 (next):**
- [ ] RAWG + IGDB + HowLongToBeat + OpenCritic integrations
- [ ] TikTok / Instagram / X no-auth scrapers (stable)
- [ ] AI sentiment analysis (local transformer)
- [ ] FastAPI web dashboard (beta)
- [ ] Discord + Telegram notifications

**v2.2:**
- [ ] Market gap finder
- [ ] Launch health score
- [ ] Docker + docker-compose
- [ ] GitHub Actions CI/CD

**v3.0:**
- [ ] PostgreSQL support (multi-user)
- [ ] REST API for third-party integrations
- [ ] Plugin system for custom data sources
- [ ] Cloud-hosted option

---

## License

MIT License — see [LICENSE](LICENSE) for details. Copyright 2026 Kekko16004.

---

## Star History

If GamesTracker helps your game development decisions, consider giving it a star — it helps other indie devs discover the project.

---

Made with ❤️ for the indie game development community.
*"Stop guessing. Start tracking."*
