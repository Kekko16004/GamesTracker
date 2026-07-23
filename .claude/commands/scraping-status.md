# Scraping Status

Check the current status of all social scraping jobs and recent collection activity.

## Usage

```
/scraping-status
```

## Status Overview

```bash
python3 -c "
from core.config import get_settings
s = get_settings()
print('=== Scraping Configuration ===')
print(f'Enabled: {s.scraping_enabled}')
print(f'Interval: every {s.scraping_interval_hours}h')
print(f'Proxy: {s.proxy_url or "none"}')
print(f'Nitter instance: {s.nitter_instance}')
print()
"
```

## Recent Social Collection Activity

```bash
python3 -c "
from core.db import session_scope, init_db
from core.models import SocialPost, SocialPlatform
from sqlalchemy import func
init_db()
with session_scope() as s:
    print('=== Social Posts (last 7 days) ===')
    rows = (
        s.query(SocialPost.platform, func.count(SocialPost.id).label('count'))
        .filter(SocialPost.collected_at >= func.datetime('now', '-7 days'))
        .group_by(SocialPost.platform)
        .all()
    )
    for platform, count in rows:
        print(f'  {platform}: {count} posts')
    total = s.query(func.count(SocialPost.id)).scalar()
    print(f'  Total ever: {total}')
"
```

## Scraper Health per Platform

For each active scraper, check:
1. Was the last collection attempt successful?
2. How many posts were collected in the last cycle?
3. Are there any rate-limit or block warnings in the logs?

```bash
# Check collector logs (if running as a service)
journalctl -u gamestracker-collector -n 100 --no-pager | grep -i "scraping\|tiktok\|instagram\|nitter\|warning\|error"

# Or if running directly (logs to stdout)
tail -200 logs/collector.log | grep -i "scraping\|warning\|error"
```

## Force a Manual Scraping Run

If you need to trigger an immediate scraping cycle (outside the normal schedule):

```bash
python3 -c "
from core.config import get_settings
from collector.scheduler import CollectorScheduler
# This triggers one immediate run of the social snapshot job
# (requires the collector to be stopped first)
print('Manual trigger not implemented via CLI yet — restart collector to force immediate run')
"
```

## Notes

- `SCRAPING_ENABLED=false` (default) means scrapers are defined but do not run automatically.
- Manual import via the GUI is always available regardless of scraper status.
- If a scraper logs repeated rate-limit warnings, consider enabling `PROXY_URL`.
- Nitter-based X/Twitter scraping depends on the Nitter instance being reachable.
