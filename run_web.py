#!/usr/bin/env python3
"""Entry point for the GamesTracker web dashboard.

Usage:
    python run_web.py               # development (auto-reload)
    python run_web.py --no-reload   # production-ish (no reload)
    python run_web.py --port 9000   # custom port
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on the Python path so that `core`, `gui`,
# and `web` are all importable when running directly.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GamesTracker web dashboard (FastAPI + Uvicorn)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        default=False,
        help="Disable auto-reload (use in production)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Uvicorn log level (default: info)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reload = not args.no_reload

    print(f"[GamesTracker] Starting web dashboard on http://{args.host}:{args.port}")
    if reload:
        print("[GamesTracker] Auto-reload enabled — change any file to reload.")

    uvicorn.run(
        "web.main:app",
        host=args.host,
        port=args.port,
        reload=reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
