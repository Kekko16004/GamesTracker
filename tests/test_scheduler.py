"""Test della logica di schedule/backfill (funzione pura, no APScheduler)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.models import SnapshotType
from collector.scheduler import compute_snapshot_schedule


def _dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_schedule_full_when_just_discovered():
    """Gioco scoperto ora -> tutte e 4 le finestre future."""
    base = _dt(2026, 7, 21, 12, 0)
    now = base  # scoperto esattamente alla base
    schedule = compute_snapshot_schedule(base, now=now)
    types = [t for t, _ in schedule]
    assert types == [
        SnapshotType.H24, SnapshotType.H48, SnapshotType.W1, SnapshotType.M1
    ]
    # Ordinati per data crescente.
    dates = [d for _, d in schedule]
    assert dates == sorted(dates)


def test_backfill_late_discovery_skips_past_windows():
    """Gioco scoperto 10 giorni dopo la release -> solo m1 resta futuro.

    Con base = release date, a +10 giorni: h24 (+1g), h48 (+2g), w1 (+7g)
    sono gia' passati -> saltati. m1 (+30g) e' ancora futuro.
    """
    release = _dt(2026, 7, 1, 0, 0)
    now = release + timedelta(days=10)
    schedule = compute_snapshot_schedule(release, now=now)
    types = [t for t, _ in schedule]
    assert types == [SnapshotType.M1]


def test_backfill_only_w1_and_m1():
    """Gioco scoperto tra +48h e +7g -> restano w1 e m1."""
    release = _dt(2026, 7, 1, 0, 0)
    now = release + timedelta(days=3)  # h24 e h48 passati, w1/m1 futuri
    schedule = compute_snapshot_schedule(release, now=now)
    types = [t for t, _ in schedule]
    assert types == [SnapshotType.W1, SnapshotType.M1]


def test_all_windows_past():
    """Gioco scoperto oltre 30 giorni dopo -> nessuna finestra futura."""
    release = _dt(2026, 1, 1, 0, 0)
    now = release + timedelta(days=40)
    schedule = compute_snapshot_schedule(release, now=now)
    assert schedule == []


def test_naive_base_time_handled():
    """base_time naive non deve rompere il confronto con now tz-aware."""
    base = datetime(2026, 7, 21, 12, 0)  # naive
    now = _dt(2026, 7, 21, 12, 0)
    schedule = compute_snapshot_schedule(base, now=now)
    assert len(schedule) == 4
