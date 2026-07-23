"""Entrypoint del collector (servizio di raccolta in background).

Fase 2: avvia davvero lo scheduler.
- ``init_db()`` assicura lo schema.
- ``CollectorScheduler`` (APScheduler, jobstore persistente su DB) parte e
  registra i job ricorrenti (discovery + snapshot social placeholder).
- La discovery riceve il riferimento allo scheduler per poter pianificare
  gli snapshot dei giochi appena scoperti.
- Shutdown pulito su Ctrl+C (SIGINT) / SIGTERM.

Modalita' ``--once``: esegue UN singolo giro di raccolta (discovery +
snapshot + social) emettendo il progresso su stdout, poi termina. E' la
modalita' usata dal bottone "Raccogli ora" della GUI, che avvia questo
script come processo separato. ``--no-social`` salta la fase social.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading

from core.config import get_settings
from core.db import init_db
from collector import discovery
from collector.scheduler import CollectorScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gamestracker.collector")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GamesTracker collector")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Esegue un singolo giro di raccolta e termina (usato dalla GUI).",
    )
    parser.add_argument(
        "--no-social",
        action="store_true",
        help="In modalita' --once, salta la fase di raccolta social.",
    )
    return parser.parse_args()


def main() -> None:
    """Avvia il collector e resta in esecuzione fino a Ctrl+C."""
    settings = get_settings()
    init_db()  # schema idempotente

    scheduler = CollectorScheduler(db_url=settings.db_url)
    # La discovery usa lo scheduler per pianificare gli snapshot dei nuovi giochi.
    discovery.set_scheduler(scheduler)
    scheduler.start()

    logger.info("Collector avviato. DB: %s", settings.db_url)
    logger.info(
        "Discovery ogni %dh | soglia quality score: %s",
        settings.discovery_interval_hours, settings.quality_score_threshold,
    )
    logger.info("Premi Ctrl+C per fermare.")

    # Attende un segnale di stop (SIGINT/SIGTERM) senza busy-loop.
    stop_event = threading.Event()

    def _handle_stop(signum, frame):  # noqa: ANN001
        logger.info("Ricevuto segnale %s: arresto in corso...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_stop)
    try:
        signal.signal(signal.SIGTERM, _handle_stop)
    except (ValueError, AttributeError):
        # SIGTERM non disponibile su alcune piattaforme/thread.
        pass

    try:
        stop_event.wait()
    finally:
        scheduler.shutdown(wait=True)
        logger.info("Collector fermato.")


def run_once_mode(include_social: bool = True) -> None:
    """Esegue un singolo giro di raccolta emettendo il progresso su stdout.

    I log applicativi restano su stderr (basicConfig), quindi non inquinano il
    flusso di progresso su stdout letto dalla GUI.
    """
    from collector.run_once import run_once

    run_once(include_social=include_social)


if __name__ == "__main__":
    args = _parse_args()
    if args.once:
        run_once_mode(include_social=not args.no_social)
    else:
        main()
