# Run Tests

Run the full GamesTracker test suite with coverage reporting.

## Usage

```
/run-tests
```

## What this does

1. Activates the project virtualenv (if not already active)
2. Runs the full test suite with pytest
3. Reports coverage for core/, analysis/, and gui/
4. Shows a summary of passed, failed, and skipped tests

## Commands

```bash
# Full suite (fast, mocked — no network required)
python -m pytest tests/ -q

# With coverage report
python -m pytest tests/ --cov=core --cov=analysis --cov=gui --cov-report=term-missing -q

# Verbose (shows test names)
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_<name>.py -v

# Single test
python -m pytest tests/test_<name>.py::test_function_name -v
```

## Expected baseline

```
118 passed, 2 skipped   (2 skipped = GUI tests without PyQt6 display)
```

If the count drops or any previously passing test fails, investigate before committing.

## Notes

- All tests are mocked — no API keys or network access needed.
- GUI tests (marked with `pytest.importorskip("PyQt6")`) auto-skip in headless environments.
- If you see import errors, run `pip install -r requirements.txt` first.
