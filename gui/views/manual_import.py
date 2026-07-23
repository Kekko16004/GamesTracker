"""Dialog di import manuale di un post social (TikTok/Instagram/altri).

Raccoglie i campi visibili di un post (URL, data, metriche, handle) e li salva
chiamando ``core.sources.social.manual_import.import_manual_post`` — l'UNICA
via con cui la GUI scrive dati social (input utente, non rete).

La logica di scrittura e' isolata in :func:`save_manual_post`, funzione pura
rispetto a Qt (apre una transazione e delega alla funzione di ``core``), cosi'
da poter essere testata senza istanziare la dialog. La dialog e' un sottile
strato di raccolta input sopra di essa.

Le metriche lasciate vuote restano ``None`` ("dato non raccolto" ≠ 0). Tutte
le stringhe passano dall'i18n (nessun testo hardcoded).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.models import SocialPlatform
from core.sources.social.manual_import import (
    ManualImportError,
    import_manual_post,
)
from gui.i18n import tr, translator

# Piattaforme proposte nel selettore (TikTok/Instagram in cima: caso d'uso base).
_PLATFORM_CHOICES: tuple[SocialPlatform, ...] = (
    SocialPlatform.TIKTOK,
    SocialPlatform.INSTAGRAM,
    SocialPlatform.YOUTUBE,
    SocialPlatform.REDDIT,
    SocialPlatform.TWITTER,
)


class ImportOutcome(Enum):
    """Esito di un import manuale."""

    SAVED = "saved"
    DUPLICATE = "duplicate"


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Interpreta una data ``YYYY-MM-DD`` (UTC); ``None`` se vuota/non valida."""
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise ManualImportError(f"Data non valida (usa YYYY-MM-DD): {value!r}") from exc
    return parsed.replace(tzinfo=timezone.utc)


def save_manual_post(
    game_id: int,
    platform: str | SocialPlatform,
    url: str,
    posted_at: Optional[datetime] = None,
    title: Optional[str] = None,
    views: Optional[int] = None,
    likes: Optional[int] = None,
    comments: Optional[int] = None,
    shares: Optional[int] = None,
    handle: Optional[str] = None,
    session_factory: Optional[Callable[[], object]] = None,
) -> ImportOutcome:
    """Salva un post manuale in una transazione, delegando a ``core``.

    Apre una ``session_scope`` (o usa ``session_factory`` nei test), chiama
    ``import_manual_post`` e committa. Ritorna :class:`ImportOutcome` (SAVED o
    DUPLICATE). Propaga ``ManualImportError`` per input non validi.

    Questa funzione NON tocca widget: e' testabile senza QApplication.
    """
    if session_factory is not None:
        session = session_factory()
        try:
            created = import_manual_post(
                session,
                game_id=game_id,
                platform=platform,
                url=url,
                posted_at=posted_at,
                title=title,
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                handle=handle,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return ImportOutcome.SAVED if created is not None else ImportOutcome.DUPLICATE

    # Percorso produzione: transazione gestita da core.db.session_scope.
    from core.db import session_scope

    with session_scope() as session:
        created = import_manual_post(
            session,
            game_id=game_id,
            platform=platform,
            url=url,
            posted_at=posted_at,
            title=title,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            handle=handle,
        )
    return ImportOutcome.SAVED if created is not None else ImportOutcome.DUPLICATE


class ManualImportDialog(QDialog):
    """Form modale per inserire a mano un post social di un gioco."""

    def __init__(
        self,
        game_id: int,
        parent: QWidget | None = None,
        session_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        super().__init__(parent)
        self._game_id = game_id
        self._session_factory = session_factory
        self.setModal(True)
        self._build_ui()
        self._unsubscribe = translator.subscribe(lambda _l: self.retranslate())
        self.retranslate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._intro = QLabel()
        self._intro.setWordWrap(True)
        root.addWidget(self._intro)

        form = QFormLayout()
        self._platform_combo = QComboBox()
        for plat in _PLATFORM_CHOICES:
            self._platform_combo.addItem(plat.value, plat)
        self._url_edit = QLineEdit()
        self._handle_edit = QLineEdit()
        self._posted_edit = QLineEdit()
        self._posted_edit.setPlaceholderText("YYYY-MM-DD")
        self._title_edit = QLineEdit()
        self._views_edit = QLineEdit()
        self._likes_edit = QLineEdit()
        self._comments_edit = QLineEdit()
        self._shares_edit = QLineEdit()

        self._lbl_platform = QLabel()
        self._lbl_url = QLabel()
        self._lbl_handle = QLabel()
        self._lbl_posted = QLabel()
        self._lbl_title = QLabel()
        self._lbl_views = QLabel()
        self._lbl_likes = QLabel()
        self._lbl_comments = QLabel()
        self._lbl_shares = QLabel()

        form.addRow(self._lbl_platform, self._platform_combo)
        form.addRow(self._lbl_url, self._url_edit)
        form.addRow(self._lbl_handle, self._handle_edit)
        form.addRow(self._lbl_posted, self._posted_edit)
        form.addRow(self._lbl_title, self._title_edit)
        form.addRow(self._lbl_views, self._views_edit)
        form.addRow(self._lbl_likes, self._likes_edit)
        form.addRow(self._lbl_comments, self._comments_edit)
        form.addRow(self._lbl_shares, self._shares_edit)
        root.addLayout(form)

        self._metrics_hint = QLabel()
        self._metrics_hint.setWordWrap(True)
        root.addWidget(self._metrics_hint)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    # --- azioni -----------------------------------------------------------
    def _on_save(self) -> None:
        """Valida i campi e salva; mostra messaggi di esito/errore tradotti."""
        url = self._url_edit.text().strip()
        if not url:
            QMessageBox.warning(
                self, tr("manual.title"), tr("manual.error.url_required")
            )
            return
        platform = self._platform_combo.currentData()
        try:
            posted_at = _parse_date(self._posted_edit.text())
            outcome = save_manual_post(
                game_id=self._game_id,
                platform=platform,
                url=url,
                posted_at=posted_at,
                title=self._title_edit.text() or None,
                views=self._views_edit.text() or None,
                likes=self._likes_edit.text() or None,
                comments=self._comments_edit.text() or None,
                shares=self._shares_edit.text() or None,
                handle=self._handle_edit.text() or None,
                session_factory=self._session_factory,
            )
        except ManualImportError as exc:
            QMessageBox.warning(
                self, tr("manual.title"), tr("manual.error.invalid", error=str(exc))
            )
            return
        except Exception as exc:  # noqa: BLE001 - errori DB/imprevisti
            QMessageBox.critical(
                self,
                tr("manual.title"),
                tr("manual.error.save_failed", error=str(exc)),
            )
            return

        msg = (
            tr("manual.saved")
            if outcome is ImportOutcome.SAVED
            else tr("manual.duplicate")
        )
        QMessageBox.information(self, tr("manual.title"), msg)
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: ANN001 - firma Qt
        """Annulla la sottoscrizione i18n alla chiusura."""
        try:
            self._unsubscribe()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)

    # --- i18n -------------------------------------------------------------
    def retranslate(self) -> None:
        """Riapplica le stringhe visibili nella lingua corrente."""
        self.setWindowTitle(tr("manual.title"))
        self._intro.setText(tr("manual.intro"))
        self._lbl_platform.setText(tr("manual.platform"))
        self._lbl_url.setText(tr("manual.url"))
        self._lbl_handle.setText(tr("manual.handle"))
        self._lbl_posted.setText(tr("manual.posted_at"))
        self._lbl_title.setText(tr("manual.post_title"))
        self._lbl_views.setText(tr("manual.views"))
        self._lbl_likes.setText(tr("manual.likes"))
        self._lbl_comments.setText(tr("manual.comments"))
        self._lbl_shares.setText(tr("manual.shares"))
        self._metrics_hint.setText(tr("manual.metrics_hint"))
        save_btn = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn is not None:
            save_btn.setText(tr("manual.save"))
        if cancel_btn is not None:
            cancel_btn.setText(tr("manual.cancel"))
