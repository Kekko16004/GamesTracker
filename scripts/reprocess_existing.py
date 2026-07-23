"""Script one-shot: riprocessa i giochi gia' presenti nel DB.

Motivo: i giochi scoperti prima dell'aggancio di scoring/report (e prima
della persistenza dei dati pagina store in ``game_snapshots.extra``) hanno
``quality_score = NULL`` e nessun report. Questo script:

1. per ogni gioco Steam, ri-fetcha ``appdetails`` e aggiorna l'ULTIMO
   snapshot con i segnali pagina store (trailer/screenshot/descrizione),
   cosi' la componente store_page del quality score non e' cieca;
2. calcola il quality score (persistito su ``games.quality_score`` +
   ``discarded``);
3. genera il report per-gioco (persistito su ``analysis_reports``).

Richiede RETE VIVA (fa chiamate a Steam). Rispetta i throttle dei client.
Non crasha sui singoli errori: logga e continua.

Uso:
    venv/Scripts/python scripts/reprocess_existing.py            # con re-fetch store
    venv/Scripts/python scripts/reprocess_existing.py --no-fetch # solo score/report
    venv/Scripts/python scripts/reprocess_existing.py --limit 5  # primi N giochi

Con ``--no-fetch`` non aggiorna gli snapshot (store_page resta debole per i
giochi senza ``extra``), ma calcola comunque score+report dai dati presenti.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Consente l'esecuzione come `python scripts/reprocess_existing.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from core.db import session_scope, init_db
from core.models import Game, GameSnapshot, Platform
from core.sources import steam_store
from collector.persistence import build_store_extra
from collector.jobs.scoring import score_and_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reprocess")


def _latest_snapshot(session, game_id: int) -> GameSnapshot | None:
    return session.scalars(
        select(GameSnapshot)
        .where(GameSnapshot.game_id == game_id)
        .order_by(GameSnapshot.captured_at.desc())
    ).first()


def reprocess(no_fetch: bool = False, limit: int | None = None) -> dict[str, int]:
    stats = {"total": 0, "store_updated": 0, "scored": 0, "errors": 0}

    with session_scope() as session:
        games = list(session.scalars(select(Game).order_by(Game.id)))
        if limit is not None:
            games = games[:limit]
        game_ids = [g.id for g in games]

    for game_id in game_ids:
        stats["total"] += 1
        try:
            # 1) Aggiorna lo store data sull'ultimo snapshot (solo Steam).
            if not no_fetch:
                with session_scope() as session:
                    game = session.get(Game, game_id)
                    if game is not None and game.platform == Platform.STEAM:
                        details = steam_store.fetch_appdetails(game.external_id)
                        if details is not None:
                            snap = _latest_snapshot(session, game_id)
                            if snap is not None:
                                merged = dict(snap.extra or {})
                                merged.update(build_store_extra(details))
                                snap.extra = merged
                                stats["store_updated"] += 1

            # 2+3) Score + report (transazione separata, riusa la session).
            with session_scope() as session:
                score_and_report(session, game_id)
                stats["scored"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception("Errore nel riprocessare game_id=%s", game_id)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Riprocessa i giochi esistenti.")
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="Non ri-fetchare Steam: calcola score/report dai soli dati presenti.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Riprocessa al piu' N giochi (per test).",
    )
    args = parser.parse_args()

    init_db()
    logger.info(
        "Avvio riprocessamento (no_fetch=%s, limit=%s)...", args.no_fetch, args.limit
    )
    stats = reprocess(no_fetch=args.no_fetch, limit=args.limit)
    logger.info(
        "Fatto. Giochi=%(total)s, store aggiornati=%(store_updated)s, "
        "score+report=%(scored)s, errori=%(errors)s", stats,
    )


if __name__ == "__main__":
    main()
