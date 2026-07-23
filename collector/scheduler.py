"""Scheduler del collector (APScheduler con jobstore persistente).

Responsabilita':
- pianificare, alla scoperta di un gioco, i job di snapshot canonici
  (h24/h48/w1/m1) con offset dalla base temporale (release date se
  disponibile, altrimenti first_seen);
- **backfill**: se un gioco e' scoperto in ritardo, NON bloccare; le
  finestre gia' passate vengono semplicemente saltate (nessun dato
  inventato), quelle future vengono schedulate (vedi tracking-schedule.md);
- job ricorrente di discovery (intervallo da config);
- job ricorrente di snapshot social (placeholder Fase 3, hook pulito).

Il jobstore e' ``SQLAlchemyJobStore`` sullo stesso DB: i job sopravvivono
al riavvio del collector.

La logica di calcolo dello schedule (``compute_snapshot_schedule``) e' una
funzione pura, testabile senza APScheduler ne' DB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from core.config import get_settings
from core.models import SnapshotType

logger = logging.getLogger(__name__)

# Offset canonici dei tipi di snapshot rispetto alla base temporale.
SNAPSHOT_OFFSETS: dict[SnapshotType, timedelta] = {
    SnapshotType.H24: timedelta(hours=24),
    SnapshotType.H48: timedelta(hours=48),
    SnapshotType.W1: timedelta(days=7),
    SnapshotType.M1: timedelta(days=30),
}


def compute_snapshot_schedule(
    base_time: datetime,
    now: Optional[datetime] = None,
) -> list[tuple[SnapshotType, datetime]]:
    """Calcola i job di snapshot FUTURI da schedulare.

    Per ogni tipo canonico (h24/h48/w1/m1) calcola il ``run_date`` come
    ``base_time + offset``. Include solo le finestre ancora nel futuro
    rispetto a ``now``: le finestre gia' passate vengono saltate (backfill
    = nessun dato inventato, coerente con tracking-schedule.md).

    Esempio backfill: gioco scoperto 10 giorni dopo la release -> h24 e h48
    sono nel passato (saltati), w1 e' appena passato o imminente, m1 futuro.

    Args:
        base_time: base temporale (release date o first_seen).
        now: istante corrente (default ``datetime.now(tz)``); iniettabile
            per i test.

    Ritorna lista di ``(SnapshotType, run_date)`` ordinata per run_date.
    """
    if now is None:
        now = datetime.now(base_time.tzinfo or timezone.utc)
    # Normalizza timezone: se base_time e' naive, trattalo come now.tzinfo.
    if base_time.tzinfo is None and now.tzinfo is not None:
        base_time = base_time.replace(tzinfo=now.tzinfo)
    if now.tzinfo is None and base_time.tzinfo is not None:
        now = now.replace(tzinfo=base_time.tzinfo)

    schedule: list[tuple[SnapshotType, datetime]] = []
    for snap_type, offset in SNAPSHOT_OFFSETS.items():
        run_date = base_time + offset
        if run_date > now:
            schedule.append((snap_type, run_date))
    schedule.sort(key=lambda x: x[1])
    return schedule


# --- Funzioni-job a livello di modulo -------------------------------------
# APScheduler con jobstore persistente serializza i job come riferimenti
# importabili (path modulo:funzione), quindi devono stare a livello modulo.


def _job_snapshot(platform: str, external_id: str, snapshot_type: str) -> None:
    """Wrapper job: esegue uno snapshot (import lazy per evitare cicli)."""
    from collector.jobs.snapshot import run_snapshot

    run_snapshot(platform, external_id, snapshot_type)


def _job_discovery() -> None:
    """Wrapper job: esegue un ciclo di discovery (import lazy)."""
    from collector.discovery import run_discovery

    run_discovery()


def _job_social_snapshot() -> None:
    """Job ricorrente di raccolta social (YouTube).

    Collega i client social al collector: per ogni gioco tracciato cerca i
    video YouTube e salva i post. La ricerca allargata a developer/publisher
    e ai video pre-lancio e' attivata solo per i giochi promettenti (gating
    quota). Import lazy per evitare cicli e non caricare le API se non serve.
    """
    from collector.jobs.social import run_social_collection

    run_social_collection()


DISCOVERY_JOB_ID = "discovery_recurring"
SOCIAL_SNAPSHOT_JOB_ID = "social_snapshot_recurring"


class CollectorScheduler:
    """Incapsula il ``BackgroundScheduler`` di APScheduler.

    Jobstore persistente su DB (``SQLAlchemyJobStore``) cosi' i job
    sopravvivono al riavvio. Espone metodi per pianificare gli snapshot di
    un gioco (con backfill) e i job ricorrenti.
    """

    def __init__(self, db_url: Optional[str] = None) -> None:
        settings = get_settings()
        self._db_url = db_url or settings.db_url
        jobstores = {
            "default": SQLAlchemyJobStore(url=self._db_url, tablename="apscheduler_jobs")
        }
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            timezone=timezone.utc,
            job_defaults={"coalesce": True, "misfire_grace_time": 3600},
        )

    def start(self) -> None:
        """Avvia lo scheduler e registra i job ricorrenti."""
        self.scheduler.start()
        self._ensure_recurring_jobs()
        logger.info("Scheduler avviato (jobstore=%s).", self._db_url)

    def shutdown(self, wait: bool = True) -> None:
        """Ferma lo scheduler in modo pulito."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler fermato.")

    def _ensure_recurring_jobs(self) -> None:
        """Registra (idempotente) i job ricorrenti di discovery e social."""
        settings = get_settings()
        hours = max(1, settings.discovery_interval_hours)
        self.scheduler.add_job(
            _job_discovery,
            trigger="interval",
            hours=hours,
            id=DISCOVERY_JOB_ID,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),  # primo giro subito
        )
        self.scheduler.add_job(
            _job_social_snapshot,
            trigger="interval",
            days=1,
            id=SOCIAL_SNAPSHOT_JOB_ID,
            replace_existing=True,
        )

    def schedule_game_snapshots(
        self,
        platform: str,
        external_id: str,
        base_time: datetime,
        now: Optional[datetime] = None,
    ) -> list[SnapshotType]:
        """Pianifica gli snapshot canonici futuri per un gioco (con backfill).

        Le finestre gia' passate vengono saltate. Ritorna la lista dei tipi
        effettivamente schedulati.
        """
        scheduled: list[SnapshotType] = []
        for snap_type, run_date in compute_snapshot_schedule(base_time, now):
            job_id = f"snap_{platform}_{external_id}_{snap_type.value}"
            self.scheduler.add_job(
                _job_snapshot,
                trigger="date",
                run_date=run_date,
                args=[platform, external_id, snap_type.value],
                id=job_id,
                replace_existing=True,
            )
            scheduled.append(snap_type)
        logger.info(
            "Schedulati %d snapshot per %s:%s (%s)",
            len(scheduled), platform, external_id,
            ", ".join(s.value for s in scheduled) or "nessuno (tutti passati)",
        )
        return scheduled
