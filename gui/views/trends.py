"""Vista Trend: quali generi crescono.

Aggrega i giochi per genere (n. giochi, score medio, crescita totale
recensioni) e li presenta in una tabella e in un grafico a barre. Aiuta a
capire quali generi tirano e con quale traiettoria.

Dati via ``GameRepository.genre_trends`` fuori dal thread UI.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.data_access import GameRepository, GenreTrend
from gui.i18n import tr, translator
from gui.widgets.charts import BarChart
from gui.widgets.common import EmptyState
from gui.widgets.quality_slider import QualityThresholdSlider
from gui.widgets.tables import Column, DataTableView


class TrendsView(QWidget):
    """Trend per genere: tabella aggregata + grafico crescita."""

    def __init__(self, repo: GameRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._threshold = 0
        self._build_ui()
        translator.subscribe(lambda _l: self.retranslate())
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._title = QLabel()
        title_font = self._title.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        self._title.setFont(title_font)
        root.addWidget(self._title)

        # Filtro soglia.
        filters = QHBoxLayout()
        self._slider = QualityThresholdSlider(initial=0)
        self._slider.thresholdChanged.connect(self._on_threshold_changed)
        filters.addWidget(self._slider, stretch=1)
        root.addLayout(filters)

        # Grafico crescita per genere.
        self._chart_label = QLabel()
        self._chart = BarChart()
        self._chart.setMinimumHeight(240)
        root.addWidget(self._chart_label)
        root.addWidget(self._chart, stretch=1)

        # Tabella aggregazioni.
        self._table = DataTableView(
            [
                Column("common.genre", lambda t: t.genre),
                Column("trends.game_count", lambda t: t.game_count, align_right=True),
                Column(
                    "trends.avg_score",
                    lambda t: (
                        round(t.avg_quality_score, 1)
                        if t.avg_quality_score is not None
                        else tr("common.na")
                    ),
                    align_right=True,
                ),
                Column(
                    "trends.total_growth",
                    lambda t: t.total_review_growth,
                    align_right=True,
                ),
            ]
        )
        self._empty = EmptyState("empty.no_data.title", "empty.no_games")
        self._stack = QStackedWidget()
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        root.addWidget(self._stack, stretch=2)

        self.retranslate()

    def _on_threshold_changed(self, value: int) -> None:
        self._threshold = value
        self.refresh()

    def refresh(self) -> None:
        """Ricarica le aggregazioni per genere fuori dal thread UI."""
        # Import locale per evitare dipendenza circolare a import-time.
        from gui.workers import run_query

        threshold = float(self._threshold)
        run_query(
            lambda: self._repo.genre_trends(min_quality_score=threshold),
            self._on_trends,
        )

    def _on_trends(self, trends: list[GenreTrend]) -> None:
        if not trends:
            self._stack.setCurrentWidget(self._empty)
            return
        self._table.set_rows(trends)
        # Ordina per score medio (la "crescita" e' 0 finche' non ci sono piu'
        # snapshot nel tempo) e mostra lo score medio per genere, 0-100.
        top = sorted(
            [t for t in trends if t.avg_quality_score is not None],
            key=lambda t: t.avg_quality_score or 0.0,
            reverse=True,
        )[:12]
        self._chart.plot_values(
            [t.genre for t in top],
            [t.avg_quality_score or 0.0 for t in top],
            y_range=(0.0, 100.0),
        )
        self._stack.setCurrentWidget(self._table)

    def retranslate(self) -> None:
        """Riapplica le stringhe visibili."""
        self._title.setText(tr("trends.title"))
        self._chart_label.setText(tr("trends.avg_score_by_genre"))
        self._slider.retranslate()
        self._table.retranslate()
        self._empty.retranslate()
