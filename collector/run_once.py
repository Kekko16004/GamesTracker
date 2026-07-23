"""Ciclo di raccolta ONE-SHOT (usato dal bottone "Raccogli ora" della GUI).

A differenza di ``run_collector.py`` (servizio in background con scheduler),
questo modulo esegue UN singolo giro completo e termina:

1. **discovery** — nuove uscite Steam + itch (``discovery.run_discovery``);
2. **snapshots** — uno snapshot ``MANUAL`` per ogni gioco gia' tracciato,
   cosi' la serie storica avanza anche fuori dagli offset pianificati;
3. **social** — post YouTube (+ Reddit opzionale) se ``include_social``;
4. **scraping** — scraping controllato TikTok, Instagram, X, Reddit (senza
   API key) se ``include_social`` e ``SCRAPING_ENABLED=true`` nel config.

**Contratto di progresso**: ogni avanzamento viene stampato su ``stdout`` come
una riga::

    @@PROGRESS@@ {"phase": ..., "status": ..., "current": ..., "total": ...,
                  "message": ...}

Il marcatore e' ESATTAMENTE ``@@PROGRESS@@ `` (prefisso + spazio) seguito da
JSON compatto su una sola riga, con ``flush`` immediato. Le righe di log
normali vanno su ``stderr`` (via ``logging``) e non hanno il prefisso: la GUI
le ignora ai fini della barra. L'ULTIMO evento e' sempre ``status="done"``.

Progettato per NON crashare: ogni fase e' avvolta in try/except; su errore
emette un evento ``status="error"`` e prosegue con la fase successiva, poi
chiude comunque con ``done``.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Callable, Optional

from sqlalchemy import select

from core.db import init_db, session_scope
from core.models import Game, SnapshotType

logger = logging.getLogger(__name__)

# Marcatore di riga di progresso (deve combaciare con collect_runner.py).
PROGRESS_MARKER = "@@PROGRESS@@ "

# Tipo della callback di emissione: (phase, status, current, total, message).
EmitFn = Callable[[str, str, int, Optional[int], str], None]


def emit_progress(
    phase: str,
    status: str,
    current: int = 0,
    total: Optional[int] = None,
    message: str = "",
) -> None:
    """Stampa un evento di progresso su stdout secondo il contratto.

    Una riga, JSON compatto, flush immediato. ``total=None`` indica una fase a
    durata sconosciuta (la GUI mostra una barra indeterminata).
    """
    payload = json.dumps(
        {
            "phase": phase,
            "status": status,
            "current": current,
            "total": total,
            "message": message,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )
    sys.stdout.write(PROGRESS_MARKER + payload + "\n")
    sys.stdout.flush()


def _run_discovery_phase(emit: EmitFn) -> None:
    """Fase discovery: nuove uscite Steam + itch."""
    from collector import discovery

    emit("discovery", "start", 0, None, "Discovery nuove uscite")
    try:
        result = discovery.run_discovery()
        created = int(result.get("steam", 0)) + int(result.get("itch", 0))
        emit("discovery", "end", created, None, f"{created} nuovi giochi")
    except Exception as exc:  # noqa: BLE001 - non far crashare il giro
        logger.exception("Fase discovery fallita")
        emit("discovery", "error", 0, None, str(exc))


def _run_snapshots_phase(emit: EmitFn) -> None:
    """Fase snapshot: uno snapshot MANUAL per ogni gioco tracciato."""
    from collector.jobs.snapshot import run_snapshot

    # Legge l'elenco (platform, external_id) in una transazione breve.
    with session_scope() as session:
        games = [
            (g.platform.value, g.external_id)
            for g in session.scalars(select(Game).order_by(Game.id))
        ]

    total = len(games)
    emit("snapshots", "start", 0, total, f"{total} giochi da aggiornare")
    for i, (platform, external_id) in enumerate(games, start=1):
        try:
            run_snapshot(platform, external_id, SnapshotType.MANUAL.value)
        except Exception:  # noqa: BLE001 - un gioco non blocca gli altri
            logger.exception(
                "Snapshot fallito per %s:%s", platform, external_id
            )
        emit("snapshots", "progress", i, total, f"{i}/{total}")
    emit("snapshots", "end", total, total, "Snapshot completati")


def _run_social_phase(emit: EmitFn) -> None:
    """Fase social: post YouTube (+ Reddit opzionale)."""
    from collector.jobs.social import run_social_collection

    emit("social", "start", 0, None, "Raccolta social")
    try:
        stats = run_social_collection()
        saved = int(stats.get("posts_saved", 0))
        emit("social", "end", saved, None, f"{saved} post salvati")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fase social fallita")
        emit("social", "error", 0, None, str(exc))


def _run_scraping_phase(emit: EmitFn) -> None:
    """Fase scraping: TikTok, Instagram, X, Reddit (senza API key).

    Usa il nuovo scraping engine (core.sources.social.scraping_orchestrator).
    Attivo SOLO se SCRAPING_ENABLED=true nel config/.env.
    """
    from core.config import get_settings

    settings = get_settings()
    scraping_enabled = getattr(settings, "scraping_enabled", False)

    if not scraping_enabled:
        emit(
            "scraping", "skip", 0, None,
            "Scraping social disabilitato (SCRAPING_ENABLED=false in .env)"
        )
        return

    emit("scraping", "start", 0, None,
         "Scraping TikTok, Instagram, X, Reddit...")
    try:
        from core.sources.social.scraping_orchestrator import run_once_sync
        stats = run_once_sync()
        total = stats.get("total_posts", 0) if isinstance(stats, dict) else 0
        emit("scraping", "end", total, None,
             f"{total} post trovati via scraping")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fase scraping fallita")
        emit("scraping", "error", 0, None, str(exc))


def run_once(include_social: bool = True, emit: EmitFn = emit_progress) -> None:
    """Esegue un singolo giro di raccolta completo emettendo progresso.

    ``emit`` e' iniettabile per i test (default: stampa su stdout). Chiude
    sempre con un evento ``status="done"`` sulla fase ``all``.

    Fasi:
    1. discovery (nuove uscite Steam + itch)
    2. snapshots (aggiornamento dati per ogni gioco tracciato)
    3. social (YouTube API + Reddit PRAW)
    4. scraping (TikTok, Instagram, X, Reddit no-auth) — se abilitato
    """
    init_db()  # schema idempotente
    _run_discovery_phase(emit)
    _run_snapshots_phase(emit)
    if include_social:
        _run_social_phase(emit)
        _run_scraping_phase(emit)
    emit("all", "done", 0, None, "Raccolta completata")


__all__ = ["PROGRESS_MARKER", "emit_progress", "run_once"]
