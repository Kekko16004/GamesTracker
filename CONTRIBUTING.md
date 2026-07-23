# Contributing to GamesTracker

Thank you for your interest in contributing! GamesTracker is designed to be extended — adding a new data source, a new analysis module, or a new GUI view all follow clear patterns documented here.

## Table of Contents

1. [Dev Environment Setup](#dev-environment-setup)
2. [Code Style](#code-style)
3. [How to Add a New Data Source](#how-to-add-a-new-data-source)
4. [How to Add a New Analysis Module](#how-to-add-a-new-analysis-module)
5. [How to Add GUI Views](#how-to-add-gui-views)
6. [Testing Guidelines](#testing-guidelines)
7. [PR Process and Checklist](#pr-process-and-checklist)

---

## Dev Environment Setup

**Requirements:** Python 3.10.x (the project targets 3.10.11).

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/GamesTracker.git
cd GamesTracker

# 2. Create a virtualenv
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows (PowerShell: venv\Scripts\Activate.ps1)

# 3. Install dependencies (includes dev tools)
pip install -r requirements.txt
pip install ruff pytest

# 4. Set up configuration
cp config/.env.example config/.env
# Edit config/.env — all keys are optional for running tests

# 5. Run the test suite to verify everything works
python -m pytest tests/ -q
# Expected: 118 passed, 2 skipped (GUI tests skip if PyQt6 not installed)

# 6. Start the collector and GUI (optional — for manual testing)
python run_collector.py
python run_gui.py
```

### Environment Notes

- `config/.env` is gitignored — never commit it.
- `data/` (the SQLite DB and cache) is gitignored — only `data/.gitkeep` is tracked.
- Tests use in-memory SQLite and mock all network calls — no API keys needed to run them.

---

## Code Style

### Linter: ruff

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting. Run it before committing:

```bash
ruff check .          # lint
ruff format .         # format
ruff check --fix .    # auto-fix fixable issues
```

The configuration lives in `pyproject.toml` (or `ruff.toml` if present). Key rules:
- Max line length: 100
- Import sorting: `isort` style via ruff
- No unused imports, no undefined names

### Type Hints

All new code must have type annotations. We use `from __future__ import annotations` at the top of files for forward compatibility. Dataclasses and `TypedDict` are preferred for structured data.

```python
# Good
def compute_score(reviews: int, players: int) -> float:
    ...

# Bad (missing hints)
def compute_score(reviews, players):
    ...
```

### Module Isolation

- `core/sources/` modules must not import from `gui/` or depend on any UI framework.
- `analysis/` modules must not import from `gui/`.
- `gui/` modules may import from `core/` and `analysis/`, but must never make network calls — all data comes from the DB via `gui/data_access.py`.

### Error Handling in the Collector

Network errors must never crash the collector. The pattern is:

```python
try:
    data = client.fetch(game_id)
except Exception as exc:
    logger.warning("source fetch failed for %s: %s", game_id, exc)
    return None
```

Always log the error and return `None` or a sentinel. The scheduler will retry on the next cycle.

---

## How to Add a New Data Source

Data sources live in `core/sources/`. Each source is an isolated, testable Python module with no dependency on the GUI or the collector.

### Step 1 — Create the source module

Create `core/sources/<platform>.py`. Implement a function or class that:

1. Accepts configuration (API key, timeout) from `core/config.py` — never hardcode credentials.
2. Returns a typed dataclass — not a raw dict.
3. Handles rate limiting internally (use `core/sources/_http.py`'s `Throttle` and `request_json`).
4. Raises a descriptive exception on unrecoverable errors; returns `None` on "not found" or empty.

```python
# core/sources/my_platform.py
from __future__ import annotations
from dataclasses import dataclass
from core.sources._http import build_client, request_json
from core.config import get_settings

@dataclass
class MyPlatformData:
    external_id: str
    name: str
    rating: float | None

def fetch_game(external_id: str) -> MyPlatformData | None:
    settings = get_settings()
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

### Step 2 — Add configuration

Add the API key variable to `core/config.py` (as an optional `str | None` field) and to `config/.env.example`.

### Step 3 — Wire into the collector

In `collector/jobs/snapshot.py`, import your source and add a call inside `run_snapshot()`. Store the result via `collector/persistence.py` (add a new snapshot table if needed — follow the existing `game_snapshots` pattern from `core/models.py`).

### Step 4 — Write tests

Create `tests/test_<platform>_source.py`. Mock all HTTP calls — no real network access in tests.

```python
# tests/test_my_platform_source.py
from unittest.mock import patch
from core.sources.my_platform import fetch_game, MyPlatformData

def test_fetch_game_parses_response():
    fake_response = {"name": "Test Game", "rating": 8.5}
    with patch("core.sources.my_platform.request_json", return_value=fake_response):
        result = fetch_game("12345")
    assert isinstance(result, MyPlatformData)
    assert result.name == "Test Game"
    assert result.rating == 8.5

def test_fetch_game_returns_none_on_empty():
    with patch("core.sources.my_platform.request_json", return_value=None):
        result = fetch_game("00000")
    assert result is None
```

### Step 5 — Update documentation

- Add the new source to `README.md` feature matrix.
- Add endpoint details to `.claude/reference/data-sources.md`.
- Update `.claude/reference/code-map.md` with the new file.

---

## How to Add a New Analysis Module

Analysis modules live in `analysis/`. They are pure functions that receive data (typically from a SQLAlchemy session) and return structured results.

### Pattern

```python
# analysis/my_metric.py
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy.orm import Session

@dataclass
class MyMetricResult:
    game_id: int
    metric_value: float
    label: str

def compute_my_metric(session: Session, game_id: int) -> MyMetricResult:
    # Query the DB — read-only
    # ... pure computation ...
    return MyMetricResult(game_id=game_id, metric_value=42.0, label="good")
```

Rules:
- Functions are pure where possible — inputs in, result out.
- DB access is read-only. Never write from `analysis/`.
- Heavy pandas computations should use a single `session.execute()` to fetch raw data, then process in-memory.
- Add tests in `tests/test_analysis_<metric>.py` using the in-memory SQLite fixtures in `tests/conftest_analysis.py`.

---

## How to Add GUI Views

GUI views live in `gui/views/`. Each view is a `QWidget` subclass that reads data exclusively through `gui/data_access.py`.

### Pattern

```python
# gui/views/my_view.py
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from gui.data_access import GameRepository
from gui.i18n import tr

class MyView(QWidget):
    def __init__(self, repo: GameRepository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self._label = QLabel(tr("my_view.title"))
        layout.addWidget(self._label)

    def _load_data(self):
        # Use gui/workers.py for heavy queries
        data = self._repo.get_something()
        # update widgets ...
```

Rules:
- All UI strings go through `tr()` from `gui/i18n/__init__.py`. Add the translation keys to `gui/i18n/strings.py` for both `it` and `en`.
- Heavy queries run in `QThreadPool` via `gui/workers.py` — never block the UI thread.
- No network calls from GUI code.
- Add the new view to `gui/app.py`'s `QStackedWidget` and toolbar.
- Write a smoke test in `tests/test_gui_<name>.py` (mark with `pytest.importorskip("PyQt6")`).

---

## Testing Guidelines

- **All tests must be network-free.** Mock every external call with `unittest.mock.patch` or `pytest-mock`.
- **All tests must be idempotent.** Use in-memory SQLite (`:memory:`) for DB tests — see `tests/conftest_analysis.py` for the pattern.
- **Test the parsing logic, not the network.** The most valuable tests verify that your parser handles real-world API response shapes correctly. Capture a real response once, save it as a fixture dict, and use that in tests.
- **Coverage target:** aim for 80%+ on new modules.
- **GUI tests:** mark with `pytest.importorskip("PyQt6")` at the top so they auto-skip in environments without a display.

```bash
# Run all tests
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_steam_sources.py -v

# Run a single test
python -m pytest tests/test_steam_sources.py::test_appdetails_parses_name -v

# Coverage report
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## PR Process and Checklist

1. **Branch from `main`**: `git checkout -b feat/my-new-source main`
2. **Keep PRs focused** — one feature or fix per PR.
3. **Run the full test suite** before opening a PR: `python -m pytest tests/ -q`
4. **Run ruff**: `ruff check . && ruff format .`

### PR Checklist

Before submitting your pull request, confirm:

- [ ] Tests pass locally (`python -m pytest tests/ -q`)
- [ ] Ruff reports no errors (`ruff check .`)
- [ ] All new functions have type annotations
- [ ] New source module has a corresponding test file with mocked HTTP calls
- [ ] `config/.env.example` updated if new env vars were added
- [ ] `README.md` feature matrix updated
- [ ] No API keys or credentials in committed code
- [ ] No `config/.env` or `data/` files committed

### Review Process

- PRs are reviewed within 48 hours.
- All CI checks must pass (lint + tests via GitHub Actions).
- For large changes, open an issue first to discuss the approach before writing code.
- We follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

---

Thank you for helping make GamesTracker better for the entire indie game development community.
