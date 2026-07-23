"""Job di snapshot: esegue una misura per un singolo gioco.

Chiamato dallo scheduler ai vari offset (h24/h48/w1/m1) e dalla discovery
(discovery snapshot). Per un gioco Steam interroga i client reviews /
players / steamspy e fa append su ``game_snapshots`` con lo
``snapshot_type`` corretto. Per itch non ci sono metriche pubbliche
equivalenti (nessun review/player count), quindi lo snapshot registra al
piu' il prezzo corrente.

Progettato per NON crashare: ogni client degrada a ``None`` su errore e il
job logga e continua. Idempotenza: gli snapshot sono append-only per
design; questo job non deduplica (ogni finestra e' una misura distinta).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from core.db import session_scope
from core.models import Game, Platform, SnapshotType
from core.sources import steam_players, steam_reviews, steam_store, steamspy
from collector.persistence import append_game_snapshot, build_store_extra, get_game
from collector.jobs.scoring import score_and_report

logger = logging.getLogger(__name__)


def run_snapshot(
    platform: str,
    external_id: str,
    snapshot_type: str,
    *,
    captured_at: Optional[datetime] = None,
) -> bool:
    """Esegue uno snapshot per un gioco identificato da (platform, external_id).

    Args:
        platform: "steam" | "itch".
        external_id: appid Steam o url itch.
        snapshot_type: valore di ``SnapshotType`` (h24/h48/w1/m1/discovery/manual).
        captured_at: timestamp da usare (per backfill); default = ora.

    Ritorna ``True`` se lo snapshot e' stato registrato, ``False`` altrimenti.
    Non solleva: gli errori dei client sono gia' gestiti a monte.
    """
    try:
        plat = Platform(platform)
        snap_type = SnapshotType(snapshot_type)
    except ValueError as exc:
        logger.error("run_snapshot: parametro non valido (%s)", exc)
        return False

    with session_scope() as session:
        game = get_game(session, plat, external_id)
        if game is None:
            logger.warning(
                "run_snapshot: gioco non trovato %s:%s", platform, external_id
            )
            return False

        if plat == Platform.STEAM:
            return _snapshot_steam(session, game, snap_type, captured_at)
        return _snapshot_itch(session, game, snap_type, captured_at)


def _snapshot_steam(
    session, game: Game, snap_type: SnapshotType, captured_at: Optional[datetime]
) -> bool:
    """Snapshot Steam: reviews + player count + stime SteamSpy."""
    appid = game.external_id
    reviews = steam_reviews.fetch_review_summary(appid)
    players = steam_players.fetch_current_players(appid)
    spy = steamspy.fetch_appdetails(appid)
    # Ri-fetch della pagina store per popolare i segnali di qualita' pagina
    # nello snapshot (trailer/screenshot/descrizione). Degrada se assente.
    details = steam_store.fetch_appdetails(appid)
    extra = build_store_extra(details) if details is not None else None

    append_game_snapshot(
        session,
        game,
        snap_type,
        reviews=reviews,
        current_players=players,
        steamspy=spy,
        captured_at=captured_at,
        extra=extra,
    )
    score_and_report(session, game.id)
    return True


def _snapshot_itch(
    session, game: Game, snap_type: SnapshotType, captured_at: Optional[datetime]
) -> bool:
    """Snapshot itch: nessuna metrica review/player pubblica.

    Registra comunque una riga (prezzo corrente) per marcare la finestra
    temporale. In futuro potra' includere metriche derivate.
    """
    append_game_snapshot(
        session,
        game,
        snap_type,
        price=game.price,
        captured_at=captured_at,
        extra={"note": "itch: nessuna metrica review/player pubblica"},
    )
    score_and_report(session, game.id)
    return True
