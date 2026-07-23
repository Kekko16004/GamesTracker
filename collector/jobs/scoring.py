"""Job di scoring: calcola il quality score e genera il report per un gioco.

Chiamato dal collector subito dopo aver registrato uno snapshot (discovery
o finestre h24/h48/w1/m1), riusando la sessione DB gia' aperta. Le funzioni
di analisi fanno solo ``session.flush()``: il commit avviene alla chiusura
di ``session_scope`` del chiamante.

Progettato per NON crashare il collector: ogni passo (score, report) e'
isolato in un try/except con logging. Un errore nel report non impedisce lo
score e viceversa.
"""

from __future__ import annotations

import logging
from typing import Optional

from analysis.quality_score import score_game
from analysis.reports import generate_game_report

logger = logging.getLogger(__name__)


def _default_lang() -> str:
    """Lingua dei report dai settings; fallback a 'it' se non disponibile."""
    try:
        from core.config import get_settings

        return get_settings().app_lang or "it"
    except Exception:  # pragma: no cover - config sempre disponibile in pratica
        return "it"


def score_and_report(session, game_id: int, lang: Optional[str] = None) -> None:
    """Calcola quality score e genera il report per ``game_id``.

    Riusa la ``session`` passata (nessun commit qui). Non solleva: logga e
    continua, cosi' il collector prosegue anche se l'analisi di un gioco
    fallisce.
    """
    if lang is None:
        lang = _default_lang()

    try:
        score, _ = score_game(session, game_id, persist=True)
        logger.info("Quality score game_id=%s: %.2f", game_id, score)
    except Exception:
        logger.exception("score_game fallito per game_id=%s", game_id)

    try:
        generate_game_report(session, game_id, lang=lang, persist=True)
        logger.info("Report generato game_id=%s (lang=%s)", game_id, lang)
    except Exception:
        logger.exception("generate_game_report fallito per game_id=%s", game_id)
