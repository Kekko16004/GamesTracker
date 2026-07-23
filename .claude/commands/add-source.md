# Add a New Data Source

Guided template for adding a new data source to GamesTracker.

## Usage

```
/add-source
```

## Checklist

Work through these steps in order. Each step has a clear completion criterion.

### 1. Research (delegate to research-scout)

- [ ] Verify the API endpoint URL and authentication method
- [ ] Document the rate limit (requests/second or requests/day)
- [ ] Confirm the response schema (what fields are available)
- [ ] Check robots.txt and ToS for scraping constraints
- [ ] Update `.claude/reference/data-sources.md` with findings

### 2. Create the source module

File: `core/sources/<platform>.py`

- [ ] Define a typed dataclass for the response (e.g., `MyPlatformData`)
- [ ] Implement the main fetch function with type annotations
- [ ] Use `core/sources/_http.py`'s `build_client()` and `request_json()` 
- [ ] Implement `Throttle` for rate limiting
- [ ] Handle missing/null fields gracefully (return `None`, not raise)
- [ ] Add the API key to `core/config.py` as an optional field
- [ ] Degrade gracefully if the key is missing (log a warning, return `None`)

### 3. Add configuration

- [ ] Add the new env var to `core/config.py` (`str | None` field)
- [ ] Add the env var with a comment to `config/.env.example`
- [ ] Add the env var to the README.md configuration table

### 4. Wire into the collector

- [ ] Import and call the source in `collector/jobs/snapshot.py`
- [ ] Persist results via `collector/persistence.py`
- [ ] If new DB columns are needed: update `core/models.py` and document in `reference/data-model.md`

### 5. Write tests

File: `tests/test_<platform>_source.py`

- [ ] Test: normal response parses correctly
- [ ] Test: empty/null response returns `None` without crashing
- [ ] Test: network error (mock exception) returns `None` without crashing
- [ ] Test: missing API key → graceful degradation (no exception)
- [ ] All mocks use `unittest.mock.patch` — NO real network calls

### 6. Update documentation

- [ ] Add row to README.md feature matrix (with status "Implemented" or "In progress")
- [ ] Update `.claude/reference/code-map.md` with the new file
- [ ] Update `.claude/reference/data-sources.md` with endpoint details
- [ ] Update `.claude/context/progress.md` with what was completed

## Template: source module

```python
# core/sources/my_platform.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from core.sources._http import build_client, request_json, Throttle
from core.config import get_settings

logger = logging.getLogger(__name__)
_throttle = Throttle(min_interval=1.0)  # adjust per platform rate limit

@dataclass
class MyPlatformData:
    external_id: str
    name: str
    rating: float | None
    # add fields as needed

def fetch_game(external_id: str) -> MyPlatformData | None:
    settings = get_settings()
    if not settings.my_platform_api_key:
        logger.warning("MY_PLATFORM_API_KEY not set — source disabled")
        return None
    with _throttle:
        client = build_client()
        url = f"https://api.myplatform.com/games/{external_id}"
        data = request_json(client, url, params={"key": settings.my_platform_api_key})
    if data is None:
        return None
    return MyPlatformData(
        external_id=external_id,
        name=data["name"],
        rating=data.get("rating"),
    )
```
