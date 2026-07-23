"""Vista Dettaglio gioco.

Mostra i dati anagrafici, il quality score, la TIMELINE marketing
(demo/release/post) sovrapposta alla crescita (recensioni/player negli
snapshot) e le liste di account e post social.

Dati caricati via ``GameRepository.get_game_detail`` fuori dal thread UI.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.data_access import GameDetail, GameRepository
from gui.i18n import tr, translator
from gui.widgets.charts import GrowthChart
from gui.widgets.common import EmptyState
from gui.widgets.tables import Column, DataTableView
from gui.workers import run_query


def _fmt(value: object) -> object:
    return tr("common.na") if value is None else value


class GameDetailView(QWidget):
    """Dettaglio di un singolo gioco con timeline e social."""

    backRequested = pyqtSignal()

    def __init__(self, repo: GameRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._detail: GameDetail | None = None
        self._build_ui()
        translator.subscribe(lambda _l: self.retranslate())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Barra superiore: pulsante indietro + titolo.
        top = QHBoxLayout()
        self._back_btn = QPushButton()
        self._back_btn.clicked.connect(self.backRequested.emit)
        self._title = QLabel()
        title_font = self._title.font()
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setBold(True)
        self._title.setFont(title_font)
        top.addWidget(self._back_btn)
        top.addWidget(self._title, stretch=1)
        root.addLayout(top)

        # Contenuto scrollabile.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)

        # Gruppo anagrafica.
        self._overview_group = QGroupBox()
        self._form = QFormLayout(self._overview_group)
        self._lbl_developer = QLabel()
        self._lbl_publisher = QLabel()
        self._lbl_genres = QLabel()
        self._lbl_score = QLabel()
        self._lbl_release = QLabel()
        self._lbl_demo = QLabel()
        self._lbl_price = QLabel()
        self._val_developer = QLabel()
        self._val_publisher = QLabel()
        self._val_genres = QLabel()
        self._val_score = QLabel()
        self._val_release = QLabel()
        self._val_demo = QLabel()
        self._val_price = QLabel()
        self._form.addRow(self._lbl_developer, self._val_developer)
        self._form.addRow(self._lbl_publisher, self._val_publisher)
        self._form.addRow(self._lbl_genres, self._val_genres)
        self._form.addRow(self._lbl_score, self._val_score)
        self._form.addRow(self._lbl_release, self._val_release)
        self._form.addRow(self._lbl_demo, self._val_demo)
        self._form.addRow(self._lbl_price, self._val_price)
        self._content_layout.addWidget(self._overview_group)

        # Gruppo timeline + crescita.
        self._timeline_group = QGroupBox()
        tl_layout = QVBoxLayout(self._timeline_group)
        self._growth_chart = GrowthChart()
        self._growth_chart.setMinimumHeight(260)
        self._empty_snap = EmptyState(
            "empty.no_snapshots", "empty.no_snapshots"
        )
        tl_layout.addWidget(self._growth_chart)
        tl_layout.addWidget(self._empty_snap)
        self._content_layout.addWidget(self._timeline_group)

        # Gruppo social: account + post.
        self._social_group = QGroupBox()
        social_layout = QVBoxLayout(self._social_group)
        # Barra azioni social: import manuale post (TikTok/Instagram/...).
        social_actions = QHBoxLayout()
        self._add_post_btn = QPushButton()
        self._add_post_btn.clicked.connect(self._open_manual_import)
        social_actions.addWidget(self._add_post_btn)
        social_actions.addStretch(1)
        social_layout.addLayout(social_actions)
        self._accounts_label = QLabel()
        self._accounts_table = DataTableView(
            [
                Column("common.platform", lambda a: a.platform),
                Column("detail.accounts", lambda a: _fmt(a.handle)),
                Column(
                    "trends.growing_genres",
                    lambda a: _fmt(a.latest_followers),
                    align_right=True,
                ),
            ]
        )
        self._accounts_table.setMaximumHeight(150)
        self._posts_label = QLabel()
        self._posts_table = DataTableView(
            [
                Column("common.platform", lambda p: p.platform),
                Column("common.title", lambda p: _fmt(p.title)),
                Column(
                    "detail.event.post",
                    lambda p: (
                        p.posted_at.strftime("%Y-%m-%d")
                        if p.posted_at
                        else tr("common.na")
                    ),
                ),
            ]
        )
        self._empty_social = EmptyState("empty.no_social", "empty.no_social")
        social_layout.addWidget(self._accounts_label)
        social_layout.addWidget(self._accounts_table)
        social_layout.addWidget(self._posts_label)
        social_layout.addWidget(self._posts_table)
        social_layout.addWidget(self._empty_social)
        self._content_layout.addWidget(self._social_group)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)
        self.retranslate()

    # --- Caricamento ------------------------------------------------------

    def load_game(self, game_id: int) -> None:
        """Carica il dettaglio del gioco ``game_id`` fuori dal thread UI."""
        run_query(lambda: self._repo.get_game_detail(game_id), self._on_detail)

    def _on_detail(self, detail: GameDetail | None) -> None:
        self._detail = detail
        if detail is None:
            self._title.setText(tr("empty.no_data.title"))
            return
        g = detail.game
        self._title.setText(g.title)
        self._val_developer.setText(str(_fmt(g.developer)))
        self._val_publisher.setText(str(_fmt(detail.publisher)))
        self._val_genres.setText(", ".join(g.genres) if g.genres else tr("common.na"))
        self._val_score.setText(
            str(round(g.quality_score, 1)) if g.quality_score is not None else tr("common.na")
        )
        self._val_release.setText(str(_fmt(g.release_date)))
        self._val_demo.setText(
            detail.demo_release_date
            if detail.demo_release_date
            else (tr("detail.has_demo") if detail.has_demo else tr("detail.no_demo"))
        )
        self._val_price.setText(
            tr("common.free") if detail.is_free else str(_fmt(detail.price))
        )

        # Timeline + crescita.
        if detail.snapshots:
            self._growth_chart.show()
            self._empty_snap.hide()
            self._growth_chart.plot_growth(detail.snapshots, detail.timeline)
        else:
            self._growth_chart.hide()
            self._empty_snap.show()

        # Social.
        has_social = bool(detail.accounts or detail.posts)
        self._accounts_table.set_rows(detail.accounts)
        self._posts_table.set_rows(detail.posts)
        self._accounts_table.setVisible(bool(detail.accounts))
        self._posts_table.setVisible(bool(detail.posts))
        self._empty_social.setVisible(not has_social)

    # --- Import manuale post social --------------------------------------

    def _open_manual_import(self) -> None:
        """Apre la dialog di import manuale per il gioco corrente.

        Import ritardato della dialog per non accoppiare la vista al modulo di
        scrittura finche' serve. Al salvataggio con successo ricarica il
        dettaglio cosi' che il nuovo post compaia subito.
        """
        if self._detail is None:
            return
        from gui.views.manual_import import ManualImportDialog

        game_id = self._detail.game.id
        dialog = ManualImportDialog(game_id, parent=self)
        if dialog.exec():
            # Ricarica il dettaglio (fuori dal thread UI) per mostrare il post.
            self.load_game(game_id)

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        """Riapplica le stringhe visibili."""
        self._back_btn.setText(tr("nav.back"))
        self._overview_group.setTitle(tr("detail.overview"))
        self._timeline_group.setTitle(tr("detail.timeline"))
        self._social_group.setTitle(tr("detail.social"))
        self._lbl_developer.setText(tr("common.developer"))
        self._lbl_publisher.setText(tr("common.publisher"))
        self._lbl_genres.setText(tr("common.genre"))
        self._lbl_score.setText(tr("common.quality_score"))
        self._lbl_release.setText(tr("common.release_date"))
        self._lbl_demo.setText(tr("detail.has_demo"))
        self._lbl_price.setText(tr("detail.price"))
        self._accounts_label.setText(tr("detail.accounts"))
        self._posts_label.setText(tr("detail.posts"))
        self._add_post_btn.setText(tr("detail.add_post"))
        self._accounts_table.retranslate()
        self._posts_table.retranslate()
        self._empty_snap.retranslate()
        self._empty_social.retranslate()
        # Ricarica per riformattare eventuali valori "n/d".
        if self._detail is not None:
            self._on_detail(self._detail)
