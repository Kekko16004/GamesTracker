# Health Check

Verify that all GamesTracker services and configurations are working correctly.

## Usage

```
/health-check
```

## Checks Performed

### 1. Database

```bash
python3 -c "
from core.db import init_db, session_scope
from core.models import Game
init_db()
with session_scope() as s:
    count = s.query(Game).count()
    print(f'DB OK — {count} games tracked')
"
```

Expected: `DB OK — N games tracked` (N can be 0 on first run)

### 2. Configuration

```bash
python3 -c "
from core.config import get_settings
s = get_settings()
print('DB_URL:', s.db_url)
print('APP_LANG:', s.app_lang)
print('Steam key:', 'SET' if s.steam_web_api_key else 'MISSING (optional)')
print('YouTube key:', 'SET' if s.youtube_api_key else 'MISSING (YouTube disabled)')
print('Reddit creds:', 'SET' if s.reddit_client_id else 'MISSING (Reddit disabled)')
print('Scraping:', s.scraping_enabled)
print('Notifications:', s.notifications_enabled)
"
```

### 3. Collector (if running)

```bash
# Check if collector process is running
pgrep -f run_collector.py && echo "Collector: RUNNING" || echo "Collector: NOT RUNNING"
```

### 4. Web Dashboard (if running)

```bash
curl -s http://localhost:${WEB_PORT:-8080}/health | python3 -m json.tool
```

Expected: `{"status": "ok", "game_count": N}`

### 5. Test suite (quick sanity check)

```bash
python -m pytest tests/ -q --tb=no
```

Expected: all tests pass (118+), 2 skipped.

## Diagnosing Common Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | Virtualenv not active | `source venv/bin/activate` |
| `DB OK — 0 games` after 24h | Collector never ran or crashed | Check collector logs |
| YouTube/Reddit disabled | API keys missing | Edit `config/.env` |
| Scraping disabled | `SCRAPING_ENABLED=false` | Set to `true` in `.env` (optional) |
| Web 500 errors | DB not initialized | Run collector first to init DB |
