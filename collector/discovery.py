"""Job di discovery: trova nuove uscite Steam + itch, crea i games,
registra lo snapshot ``discovery`` e schedula gli snapshot futuri.

Flusso per ciascuna sorgente:
1. discovery degli identificatori (appid Steam da explore/new; url itch da RSS);
2. per ogni nuovo id: fetch dei dettagli, upsert idempotente su ``games``;
3. append di uno snapshot ``discovery`` (baseline);
4. schedulazione degli snapshot futuri h24/h48/w1/m1 (con backfill) usando
   lo scheduler condiviso, se registrato.

Idempotente: rieseguire non duplica i giochi (dedup su platform+external_id)
e ripianifica i job con lo stesso id (``replace_existing``).

Lo scheduler viene iniettato via ``set_scheduler`` all'avvio del collector,
cosi' la discovery puo' schedulare gli snapshot. Se assente (es. run manuale
senza scheduler), la discovery raccoglie e persiste comunque, saltando solo
la pianificazione.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from core.db import session_scope
from core.models import Game, Platform, SnapshotType
from core.sources import (
    itch,
    steam_discovery,
    steam_reviews,
    steam_players,
    steam_store,
    steamspy,
)
from collector.persistence import (
    append_game_snapshot,
    build_store_extra,
    get_game,
    upsert_itch_game,
    upsert_steam_game,
)
from collector.jobs.scoring import score_and_report

logger = logging.getLogger(__name__)

# Scheduler condiviso (iniettato dal collector all'avvio). Puo' restare None.
_scheduler = None

# Limite di sicurezza: quanti nuovi giochi processare per ciclo (evita di
# martellare le sorgenti con centinaia di fetch in un solo giro).
MAX_NEW_PER_CYCLE = 40

# Finestra di freschezza: si tracciano solo giochi usciti entro questi giorni.
# L'utente vuole analizzare solo uscite recenti (max ~2 settimane).
MAX_RELEASE_AGE_DAYS = 14


def _is_recent_release(
    release_date: Optional[date], *, coming_soon: bool = False
) -> bool:
    """True se il gioco e' abbastanza recente da essere tracciato.

    Regole:
    - senza release date: lo teniamo (spesso indie appena pubblicati o con
      data non parsata; non vogliamo perderli).
    - ``coming_soon`` (non ancora uscito): lo teniamo, e' un'uscita imminente
      che vorremo seguire dal day one.
    - con release date: solo se uscito da <= ``MAX_RELEASE_AGE_DAYS`` giorni
      e non nel futuro remoto.
    """
    if release_date is None or coming_soon:
        return True
    today = datetime.now(timezone.utc).date()
    age = (today - release_date).days
    return age <= MAX_RELEASE_AGE_DAYS


def set_scheduler(scheduler) -> None:
    """Registra lo scheduler condiviso usato per pianificare gli snapshot."""
    global _scheduler
    _scheduler = scheduler


def _base_time_for(game: Game) -> datetime:
    """Base temporale per lo schedule: release date se disponibile, altrimenti
    ``first_seen_at``. La release date rende corretto il backfill dei giochi
    scoperti in ritardo."""
    if game.release_date is not None:
        return datetime(
            game.release_date.year,
            game.release_date.month,
            game.release_date.day,
            tzinfo=timezone.utc,
        )
    return game.first_seen_at or datetime.now(timezone.utc)


def _schedule_snapshots(game: Game) -> None:
    """Schedula gli snapshot futuri per un gioco, se lo scheduler c'e'."""
    if _scheduler is None:
        return
    _scheduler.schedule_game_snapshots(
        game.platform.value, game.external_id, _base_time_for(game),
    )


def _title_exists(session, title: str) -> bool:
    """Returns True if any game with this exact title already exists in the DB.

    Used for cross-platform deduplication: a game discovered on itch and then
    on Steam (same title, different external_id) should not create two rows.
    The primary dedup key remains (platform, external_id); this is an extra
    guard for games that appear on both stores with identical titles.
    """
    from sqlalchemy import func as sa_func

    return session.scalar(
        select(Game.id).where(
            sa_func.lower(Game.title) == title.strip().lower()
        ).limit(1)
    ) is not None


def discover_steam(limit: int = MAX_NEW_PER_CYCLE) -> int:
    """Discovery Steam: explore/new -> nuovi appid -> games + snapshot discovery.

    Ritorna il numero di NUOVI giochi creati.
    """
    appids = steam_discovery.fetch_new_releases()
    if not appids:
        logger.info("discover_steam: nessun appid da explore/new.")
        return 0

    created = 0
    for appid in appids:
        if created >= limit:
            break
        # Salta se gia' noto (evita fetch inutili).
        with session_scope() as session:
            if get_game(session, Platform.STEAM, appid) is not None:
                continue

        details = steam_store.fetch_appdetails(appid)
        if details is None:
            continue
        # Ignora contenuti non-gioco (dlc/demo/musica) per la discovery.
        if details.type and details.type not in ("game",):
            logger.info("Skip appid=%s tipo=%s", appid, details.type)
            continue
        # Filtro freschezza: solo uscite recenti (max ~2 settimane).
        if not _is_recent_release(
            details.release_date, coming_soon=details.coming_soon
        ):
            logger.info(
                "Skip appid=%s: uscito il %s (oltre la finestra %dgg)",
                appid, details.release_date, MAX_RELEASE_AGE_DAYS,
            )
            continue

        spy = steamspy.fetch_appdetails(appid)
        reviews = steam_reviews.fetch_review_summary(appid)
        players = steam_players.fetch_current_players(appid)

        with session_scope() as session:
            # Ricontrolla dedup dentro la transazione (idempotenza).
            if get_game(session, Platform.STEAM, appid) is not None:
                continue
            # Cross-platform title dedup: skip if same title already tracked
            # (e.g. game already discovered on itch with same title).
            if details.name and _title_exists(session, details.name):
                logger.info(
                    "Skip appid=%s: titolo %r gia' presente (altro platform)",
                    appid, details.name,
                )
                continue
            game = upsert_steam_game(session, details, steamspy=spy)
            session.flush()  # assegna game.id
            append_game_snapshot(
                session, game, SnapshotType.DISCOVERY,
                reviews=reviews, current_players=players, steamspy=spy,
                extra=build_store_extra(details),
            )
            _schedule_snapshots(game)
            score_and_report(session, game.id)
            created += 1
    logger.info("discover_steam: %d nuovi giochi.", created)
    return created


def discover_itch(limit: int = MAX_NEW_PER_CYCLE) -> int:
    """Discovery itch: feed RSS -> pagine gioco -> games + snapshot discovery.

    Ritorna il numero di NUOVI giochi creati.
    """
    items = itch.fetch_new_and_popular()
    if not items:
        logger.info("discover_itch: feed vuoto.")
        return 0

    created = 0
    for item in items:
        if created >= limit:
            break
        with session_scope() as session:
            if get_game(session, Platform.ITCH, item.url) is not None:
                continue

        data = itch.fetch_game_page(item.url)
        if data is None:
            # Fallback: usa i dati minimi del feed.
            data = itch.ItchGameData(
                url=item.url, title=item.title, author=item.author,
                header_image=item.thumbnail,
            )
        # Filtro freschezza: solo uscite recenti (max ~2 settimane).
        # itch spesso non espone la data: in quel caso _is_recent_release
        # ritorna True e il gioco viene tenuto (dal feed new-and-popular
        # sono comunque uscite recenti).
        if not _is_recent_release(data.release_date):
            logger.info(
                "Skip itch %s: uscito il %s (oltre la finestra %dgg)",
                item.url, data.release_date, MAX_RELEASE_AGE_DAYS,
            )
            continue

        with session_scope() as session:
            if get_game(session, Platform.ITCH, item.url) is not None:
                continue
            # Cross-platform title dedup: skip if same title already tracked
            # (e.g. game already discovered on Steam with same title).
            if data.title and _title_exists(session, data.title):
                logger.info(
                    "Skip itch %s: titolo %r gia' presente (altro platform)",
                    item.url, data.title,
                )
                continue
            game = upsert_itch_game(session, data)
            session.flush()
            append_game_snapshot(
                session, game, SnapshotType.DISCOVERY, price=game.price,
            )
            _schedule_snapshots(game)
            score_and_report(session, game.id)
            created += 1
    logger.info("discover_itch: %d nuovi giochi.", created)
    return created


def run_discovery() -> dict[str, int]:
    """Esegue un ciclo completo di discovery (Steam + itch).

    Non solleva: gli errori dei client sono gestiti a monte. Ritorna il
    conteggio dei nuovi giochi per sorgente.
    """
    logger.info("=== Ciclo di discovery avviato ===")
    result = {"steam": 0, "itch": 0}
    try:
        result["steam"] = discover_steam()
    except Exception:  # noqa: BLE001 - non far crashare lo scheduler
        logger.exception("discover_steam ha sollevato un'eccezione")
    try:
        result["itch"] = discover_itch()
    except Exception:  # noqa: BLE001
        logger.exception("discover_itch ha sollevato un'eccezione")
    logger.info("=== Discovery completata: %s ===", result)
    return result
