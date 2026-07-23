"""Pulizia dei report duplicati nel database.

Per ogni combinazione (game_id, genre, lang), mantiene SOLO il report
piu' recente e cancella tutti gli altri. Eseguire una volta per ripulire
i duplicati accumulati prima del fix dell'upsert.

Uso::

    python scripts/cleanup_duplicate_reports.py

Non richiede API key. Backup del DB consigliato prima di eseguire.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import delete, func, select

# Assicura che il progetto sia nel path.
sys.path.insert(0, ".")

from core.db import init_db, session_scope  # noqa: E402
from core.models import AnalysisReport  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def cleanup() -> int:
    """Rimuove i report duplicati, mantenendo solo il piu' recente per chiave.

    Ritorna il numero di righe eliminate.
    """
    init_db()
    deleted = 0

    with session_scope() as session:
        # Per ogni (game_id, genre, lang), trova l'id del report piu' recente.
        latest_subq = (
            select(func.max(AnalysisReport.id).label("keep_id"))
            .group_by(
                AnalysisReport.game_id,
                AnalysisReport.genre,
                AnalysisReport.lang,
            )
            .subquery()
        )

        # Conta quanti sono da eliminare.
        total = session.scalar(select(func.count(AnalysisReport.id)))
        keep = session.scalar(
            select(func.count()).select_from(latest_subq)
        )
        to_delete = (total or 0) - (keep or 0)

        if to_delete <= 0:
            logger.info("Nessun duplicato trovato. Report totali: %s", total)
            return 0

        logger.info(
            "Report totali: %s | Da mantenere: %s | Duplicati da eliminare: %s",
            total, keep, to_delete,
        )

        # Cancella tutti i report il cui id NON e' nel set dei "piu' recenti".
        keep_ids = select(latest_subq.c.keep_id)
        result = session.execute(
            delete(AnalysisReport).where(
                AnalysisReport.id.notin_(keep_ids)
            )
        )
        deleted = result.rowcount
        logger.info("Eliminati %s report duplicati.", deleted)

    return deleted


if __name__ == "__main__":
    n = cleanup()
    if n > 0:
        logger.info("Fatto! Riavvia la GUI per vedere i report puliti.")
    else:
        logger.info("Il database era gia' pulito.")
