"""Livello di accesso al database (SQLAlchemy 2.x).

Fornisce engine, session factory e utility per l'inizializzazione dello
schema. Il DB di default e' SQLite (in ``data/gamestracker.db``) ma lo
schema e' pensato per essere portabile a Postgres: nessuna feature
SQLite-only.

Per SQLite viene attivato il vincolo delle foreign key (``PRAGMA
foreign_keys=ON``), che di default e' disattivato.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings, get_settings
from core.models import Base


def _enable_sqlite_fk(engine: Engine) -> None:
    """Attiva ``PRAGMA foreign_keys=ON`` su ogni connessione SQLite."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _ensure_sqlite_dir(db_url: str) -> None:
    """Crea la cartella del file SQLite se necessario (es. data/)."""
    prefix = "sqlite:///"
    if db_url.startswith(prefix) and ":memory:" not in db_url:
        db_path = Path(db_url[len(prefix):])
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(settings: Settings | None = None, echo: bool = False) -> Engine:
    """Crea e configura un ``Engine`` SQLAlchemy.

    Per SQLite abilita le foreign key. Usa ``future=True`` (stile 2.x).
    """
    settings = settings or get_settings()
    db_url = settings.db_url
    _ensure_sqlite_dir(db_url)

    connect_args = {}
    if db_url.startswith("sqlite"):
        # Consente l'uso della connessione tra thread (collector + GUI).
        connect_args["check_same_thread"] = False

    engine = create_engine(
        db_url,
        echo=echo,
        future=True,
        connect_args=connect_args,
    )

    if db_url.startswith("sqlite"):
        _enable_sqlite_fk(engine)

    return engine


# Engine e session factory a livello di modulo (lazy via funzioni sotto).
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    """Restituisce l'engine condiviso, creandolo alla prima chiamata."""
    global _engine
    if _engine is None:
        _engine = create_db_engine(settings)
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Restituisce la ``sessionmaker`` condivisa (session factory)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(settings),
            expire_on_commit=False,
            future=True,
        )
    return _SessionFactory


def init_db(engine: Engine | None = None, settings: Settings | None = None) -> Engine:
    """Crea tutte le tabelle definite sui modelli (``create_all``).

    Idempotente: le tabelle gia' esistenti non vengono ricreate.
    Restituisce l'engine usato.
    """
    engine = engine or get_engine(settings)
    Base.metadata.create_all(engine)
    return engine


# Alias esplicito richiesto dalla spec.
create_all = init_db


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Context manager transazionale: commit su successo, rollback su errore.

    Uso::

        with session_scope() as session:
            session.add(obj)
    """
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
