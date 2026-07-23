"""Test della logica di import manuale della GUI.

Testa ``save_manual_post`` (chiamata a ``import_manual_post`` + commit) senza
istanziare la dialog. La dialog Qt richiede PyQt6: se assente, il modulo si
puo' comunque importare perche' ``save_manual_post`` non tocca Qt finche' non
si costruisce la dialog. Uno smoke test opzionale della dialog usa offscreen +
skip se PyQt6 manca.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.models import Base, Game, Platform, SocialPost

pytest.importorskip("PyQt6", reason="PyQt6 non disponibile nell'ambiente")

from gui.views.manual_import import ImportOutcome, save_manual_post


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session() as s:
        g = Game(platform=Platform.STEAM, external_id="1", title="Test Game")
        s.add(g)
        s.commit()
    return Session


def _game_id(factory) -> int:
    with factory() as s:
        return s.execute(select(Game.id)).scalar_one()


def test_save_manual_post_persists(factory):
    gid = _game_id(factory)
    outcome = save_manual_post(
        game_id=gid,
        platform="tiktok",
        url="https://www.tiktok.com/@dev/video/7300000000000000000",
        posted_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        views=1000,
        likes=50,
        session_factory=factory,
    )
    assert outcome is ImportOutcome.SAVED
    with factory() as s:
        rows = s.execute(select(SocialPost)).scalars().all()
        assert len(rows) == 1
        assert rows[0].views == 1000
        assert rows[0].comments is None  # non fornito = None


def test_save_manual_post_duplicate(factory):
    gid = _game_id(factory)
    url = "https://www.instagram.com/p/Cabc123/"
    first = save_manual_post(
        game_id=gid, platform="instagram", url=url, likes=10, session_factory=factory
    )
    dup = save_manual_post(
        game_id=gid, platform="instagram", url=url, likes=99, session_factory=factory
    )
    assert first is ImportOutcome.SAVED
    assert dup is ImportOutcome.DUPLICATE
    with factory() as s:
        rows = s.execute(select(SocialPost)).scalars().all()
        assert len(rows) == 1


def test_save_manual_post_invalid_url_propagates(factory):
    from core.sources.social.manual_import import ManualImportError

    gid = _game_id(factory)
    with pytest.raises(ManualImportError):
        save_manual_post(
            game_id=gid,
            platform="tiktok",
            url="https://youtube.com/x",
            session_factory=factory,
        )


def test_dialog_instantiates_offscreen(factory):
    """Smoke test: la dialog si costruisce e traduce senza crashare."""
    from PyQt6.QtWidgets import QApplication

    from gui.views.manual_import import ManualImportDialog

    app = QApplication.instance() or QApplication([])
    gid = _game_id(factory)
    dialog = ManualImportDialog(gid, session_factory=factory)
    # I campi metrica esistono e partono vuoti.
    assert dialog._views_edit.text() == ""
    # Cambio lingua non deve crashare la retranslate.
    dialog.retranslate()
    dialog.close()
