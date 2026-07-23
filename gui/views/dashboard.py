"""Vista Dashboard: panoramica dei giochi tracciati.

Mostra metriche di sintesi, filtri (piattaforma + slider soglia quality
score), distribuzione per genere e la lista giochi filtrata. Il click su
un gioco emette ``gameSelected(int)`` per aprire il dettaglio.

Tutte le query passano dal ``GameRepository`` ed eseguono fuori dal thread
UI via ``run_query``. Su DB vuoto mostra uno stato vuoto gentile.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.collect_runner import CollectRunner
from gui.data_access import GameRepository, GameRow
from gui.i18n import tr, translator
from gui.widgets.charts import BarChart
from gui.widgets.common import EmptyState, MetricCard
from gui.widgets.quality_slider import QualityThresholdSlider
from gui.widgets.tables import Column, DataTableView
from gui.workers import run_query


def _fmt(value: object) -> object:
    """Formatta un valore per la tabella (None -> n/d tradotto)."""
    return tr("common.na") if value is None else value


class DashboardView(QWidget):
    """Panoramica principale con filtri e lista giochi."""

    gameSelected = pyqtSignal(int)

    def __init__(self, repo: GameRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._threshold = 0
        self._platform: str | None = None
        self._genre: str | None = None
        self._runner = CollectRunner(self)
        self._runner.progressChanged.connect(self._on_collect_progress)
        self._runner.finished.connect(self._on_collect_finished)
        self._runner.failed.connect(self._on_collect_failed)

        self._build_ui()
        translator.subscribe(lambda _l: self.retranslate())
        self.refresh()

    # --- Costruzione UI ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Riga raccolta dati: bottone "Raccogli ora" + opzione social + barra.
        # Avvia run_collector.py --once come PROCESSO SEPARATO (la GUI non fa
        # rete): l'avanzamento arriva via stdout e aggiorna la barra.
        collect_row = QHBoxLayout()
        self._collect_button = QPushButton()
        self._collect_button.clicked.connect(self._on_collect_clicked)
        self._collect_social = QCheckBox()
        self._collect_social.setChecked(True)
        self._collect_status = QLabel()
        self._collect_bar = QProgressBar()
        self._collect_bar.setVisible(False)
        self._collect_status.setVisible(False)
        collect_row.addWidget(self._collect_button)
        collect_row.addWidget(self._collect_social)
        collect_row.addWidget(self._collect_status)
        collect_row.addWidget(self._collect_bar, stretch=1)
        collect_row.addStretch()
        root.addLayout(collect_row)

        # Riga metriche (card).
        self._card_total = MetricCard("dashboard.tracked_games")
        self._card_visible = MetricCard("dashboard.visible_games")
        self._card_discarded = MetricCard("dashboard.discarded_games")
        self._card_recent = MetricCard("dashboard.recent_releases")
        cards = QHBoxLayout()
        for card in (
            self._card_total,
            self._card_visible,
            self._card_discarded,
            self._card_recent,
        ):
            cards.addWidget(card)
        root.addLayout(cards)

        # Riga filtri: piattaforma, genere, slider soglia.
        filters = QHBoxLayout()
        self._platform_label = QLabel()
        self._platform_combo = QComboBox()
        self._platform_combo.currentIndexChanged.connect(self._on_platform_changed)

        self._genre_label = QLabel()
        self._genre_combo = QComboBox()
        self._genre_combo.currentIndexChanged.connect(self._on_genre_changed)

        self._slider = QualityThresholdSlider(initial=0)
        self._slider.thresholdChanged.connect(self._on_threshold_changed)

        filters.addWidget(self._platform_label)
        filters.addWidget(self._platform_combo)
        filters.addWidget(self._genre_label)
        filters.addWidget(self._genre_combo)
        filters.addWidget(self._slider, stretch=1)
        root.addLayout(filters)

        # Distribuzione per genere (grafico a barre).
        self._genre_chart_label = QLabel()
        self._genre_chart = BarChart()
        root.addWidget(self._genre_chart_label)
        root.addWidget(self._genre_chart, stretch=1)

        # Tabella giochi (dentro uno stack per alternare con lo stato vuoto).
        self._table = DataTableView(
            [
                Column("common.title", lambda g: g.title),
                Column("common.developer", lambda g: _fmt(g.developer)),
                Column("common.platform", lambda g: g.platform),
                Column("common.release_date", lambda g: _fmt(g.release_date)),
                Column(
                    "common.quality_score",
                    lambda g: (
                        round(g.quality_score, 1)
                        if g.quality_score is not None
                        else tr("common.na")
                    ),
                    align_right=True,
                ),
                Column(
                    "common.reviews",
                    lambda g: _fmt(g.latest_reviews),
                    align_right=True,
                ),
                Column(
                    "dashboard.growth_reviews",
                    lambda g: _fmt(g.review_growth),
                    align_right=True,
                ),
            ]
        )
        self._table.doubleClicked.connect(self._on_row_activated)

        self._empty = EmptyState()
        self._stack = QStackedWidget()
        self._stack.addWidget(self._table)  # index 0
        self._stack.addWidget(self._empty)  # index 1
        root.addWidget(self._stack, stretch=2)

        self.retranslate()

    # --- Gestione filtri --------------------------------------------------

    def _on_platform_changed(self, index: int) -> None:
        self._platform = self._platform_combo.itemData(index)
        self.refresh_list()

    def _on_genre_changed(self, index: int) -> None:
        self._genre = self._genre_combo.itemData(index)
        self.refresh_list()

    def _on_threshold_changed(self, value: int) -> None:
        self._threshold = value
        self.refresh()

    def _on_row_activated(self, index) -> None:  # noqa: ANN001
        game = self._table.row_object(index.row())
        if isinstance(game, GameRow):
            self.gameSelected.emit(game.id)

    # --- Raccolta dati (processo separato) --------------------------------

    def _on_collect_clicked(self) -> None:
        """Avvia la raccolta come processo separato e mostra la barra."""
        if self._runner.is_running():
            return
        self._collect_button.setEnabled(False)
        self._collect_social.setEnabled(False)
        self._collect_status.setText(tr("collect.running"))
        self._collect_status.setVisible(True)
        # Parte indeterminata: la prima fase (discovery) non ha un totale.
        self._collect_bar.setRange(0, 0)
        self._collect_bar.setVisible(True)
        self._runner.start(include_social=self._collect_social.isChecked())

    def _on_collect_progress(
        self, phase: str, status: str, current: int, total: int, message: str
    ) -> None:
        """Aggiorna barra e stato a ogni evento di progresso del collector."""
        if total > 0:
            self._collect_bar.setRange(0, total)
            self._collect_bar.setValue(current)
        else:
            # Totale sconosciuto -> barra indeterminata.
            self._collect_bar.setRange(0, 0)
        key = f"collect.phase.{phase}"
        label = tr(key)
        if label == key:  # nessuna traduzione per questa fase: fallback generico
            label = tr("collect.running")
        self._collect_status.setText(label)

    def _on_collect_finished(self, ok: bool) -> None:
        """Ripristina i controlli a fine raccolta e ricarica i dati dal DB."""
        self._collect_bar.setVisible(False)
        self._collect_status.setText(tr("collect.done"))
        self._collect_button.setEnabled(True)
        self._collect_social.setEnabled(True)
        self.refresh()

    def _on_collect_failed(self, message: str) -> None:
        """Mostra l'errore di raccolta e ripristina i controlli."""
        self._collect_bar.setVisible(False)
        self._collect_status.setVisible(True)
        self._collect_status.setText(tr("collect.error", message=message))
        self._collect_button.setEnabled(True)
        self._collect_social.setEnabled(True)

    # --- Caricamento dati (fuori dal thread UI) ---------------------------

    def refresh(self) -> None:
        """Ricarica metriche, filtri, grafico e lista."""
        run_query(self._repo.has_any_data, self._on_has_data)

    def _on_has_data(self, has_data: bool) -> None:
        if not has_data:
            self._empty.set_keys("empty.no_data.title", "empty.no_data.body")
            self._stack.setCurrentWidget(self._empty)
            for card in (
                self._card_total,
                self._card_visible,
                self._card_discarded,
                self._card_recent,
            ):
                card.set_value(0)
            return
        self._populate_genre_filter()
        threshold = float(self._threshold)
        run_query(
            lambda: self._repo.dashboard_stats(min_quality_score=threshold),
            self._on_stats,
        )
        run_query(
            lambda: self._repo.genre_distribution(min_quality_score=threshold),
            self._on_genre_dist,
        )
        self.refresh_list()

    def _populate_genre_filter(self) -> None:
        run_query(self._repo.available_genres, self._on_genres)

    def _on_genres(self, genres: list[str]) -> None:
        current = self._genre
        self._genre_combo.blockSignals(True)
        self._genre_combo.clear()
        self._genre_combo.addItem(tr("common.genre.all"), None)
        for g in genres:
            self._genre_combo.addItem(g, g)
        # Ripristina selezione se ancora presente.
        idx = self._genre_combo.findData(current)
        self._genre_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._genre_combo.blockSignals(False)

    def _on_stats(self, stats) -> None:  # noqa: ANN001
        self._card_total.set_value(stats.total_games)
        self._card_visible.set_value(stats.visible_games)
        self._card_discarded.set_value(stats.discarded_games)
        self._card_recent.set_value(stats.recent_releases)

    def _on_genre_dist(self, dist: dict[str, int]) -> None:
        labels = list(dist.keys())[:12]
        values = [dist[k] for k in labels]
        self._genre_chart.plot_counts(labels, values)

    def refresh_list(self) -> None:
        """Ricarica solo la lista giochi in base ai filtri correnti."""
        threshold = float(self._threshold)
        platform = self._platform
        genre = self._genre
        run_query(
            lambda: self._repo.list_games(
                min_quality_score=threshold,
                platform=platform,
                genre=genre,
            ),
            self._on_games,
        )

    def _on_games(self, games: list[GameRow]) -> None:
        if not games:
            self._empty.set_keys("empty.no_data.title", "empty.no_games")
            self._stack.setCurrentWidget(self._empty)
            return
        self._table.set_rows(games)
        self._stack.setCurrentWidget(self._table)

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        """Riapplica tutte le stringhe visibili."""
        self._collect_button.setText(tr("collect.button"))
        self._collect_social.setText(tr("collect.include_social"))
        self._platform_label.setText(tr("common.platform"))
        self._genre_label.setText(tr("common.genre"))
        self._genre_chart_label.setText(tr("dashboard.genre_distribution"))

        # Ricostruisce il combo piattaforma preservando la selezione.
        self._platform_combo.blockSignals(True)
        current = self._platform
        self._platform_combo.clear()
        self._platform_combo.addItem(tr("common.platform.all"), None)
        self._platform_combo.addItem(tr("common.platform.steam"), "steam")
        self._platform_combo.addItem(tr("common.platform.itch"), "itch")
        idx = self._platform_combo.findData(current)
        self._platform_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._platform_combo.blockSignals(False)

        for card in (
            self._card_total,
            self._card_visible,
            self._card_discarded,
            self._card_recent,
        ):
            card.retranslate()
        self._slider.retranslate()
        self._table.retranslate()
        self._empty.retranslate()
