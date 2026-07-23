"""Entrypoint della GUI PyQt6.

Avvia l'app desktop di GamesTracker. La GUI legge SOLO dal DB (via
``core.db`` + ``gui.data_access``): nessuna chiamata di rete diretta. Lo
schema DB viene inizializzato in modo idempotente (nessuna scrittura di
dati) e la lingua di default arriva da ``core.config`` (APP_LANG).

Uso::

    python run_gui.py
"""

from __future__ import annotations

import sys


def main() -> int:
    """Avvia la GUI e ritorna il codice di uscita del processo."""
    from gui.app import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
