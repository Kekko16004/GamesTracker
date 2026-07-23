"""Widget grafici della GUI.

Due famiglie:

- **Interattivi** (pyqtgraph): serie storiche di crescita e timeline
  marketing, veloci e navigabili (zoom/pan). Usati nelle viste live.
- **Statici** (matplotlib): helper che producono ``Figure`` per l'export
  in PDF/HTML dei report. Non richiedono un canvas interattivo.

I grafici NON fanno query: ricevono dati gia' pronti dal ``data_access``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from gui.i18n import tr

# Configurazione estetica globale pyqtgraph: sfondo chiaro, testo scuro
# (contrasto adeguato per accessibilita').
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "#222222")
pg.setConfigOptions(antialias=True)

# Palette ad alto contrasto, distinguibile anche in scala di grigi.
_DEMO_COLOR = "#1b7837"
_RELEASE_COLOR = "#762a83"
_POST_COLOR = "#e08214"
_REVIEW_COLOR = "#2166ac"
_PLAYER_COLOR = "#b2182b"


def _to_timestamp(dt: datetime) -> float:
    """Converte un datetime in timestamp (asse X pyqtgraph DateAxisItem)."""
    return dt.timestamp()


class GrowthChart(QWidget):
    """Serie storica interattiva: recensioni e player nel tempo.

    Sovrappone eventuali marker di timeline marketing (linee verticali per
    demo/release/post) cosi' da leggere la crescita in relazione agli eventi.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        axis = pg.DateAxisItem(orientation="bottom")
        self._plot = pg.PlotWidget(axisItems={"bottom": axis})
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.addLegend()
        self._plot.setMouseEnabled(x=True, y=True)
        layout.addWidget(self._plot)

    def clear(self) -> None:
        """Svuota il grafico."""
        self._plot.clear()

    def plot_growth(
        self,
        points: Sequence,  # list[SnapshotPoint]
        events: Sequence = (),  # list[TimelineEvent]
    ) -> None:
        """Disegna crescita recensioni/player e marker timeline.

        ``points`` sono oggetti con ``captured_at``, ``total_reviews``,
        ``current_players``. ``events`` sono oggetti con ``when`` e ``kind``.
        """
        self._plot.clear()

        review_pts = [
            (_to_timestamp(p.captured_at), p.total_reviews)
            for p in points
            if p.total_reviews is not None
        ]
        player_pts = [
            (_to_timestamp(p.captured_at), p.current_players)
            for p in points
            if p.current_players is not None
        ]

        if review_pts:
            xs, ys = zip(*review_pts)
            self._plot.plot(
                xs,
                ys,
                pen=pg.mkPen(_REVIEW_COLOR, width=2),
                symbol="o",
                symbolSize=6,
                symbolBrush=_REVIEW_COLOR,
                name=tr("common.reviews"),
            )
        if player_pts:
            xs, ys = zip(*player_pts)
            self._plot.plot(
                xs,
                ys,
                pen=pg.mkPen(_PLAYER_COLOR, width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
                symbol="t",
                symbolSize=6,
                symbolBrush=_PLAYER_COLOR,
                name=tr("common.players"),
            )

        # Marker verticali per gli eventi di marketing.
        color_by_kind = {
            "demo": _DEMO_COLOR,
            "release": _RELEASE_COLOR,
            "post": _POST_COLOR,
        }
        for ev in events:
            color = color_by_kind.get(ev.kind, _POST_COLOR)
            line = pg.InfiniteLine(
                pos=_to_timestamp(ev.when),
                angle=90,
                pen=pg.mkPen(color, width=1, style=pg.QtCore.Qt.PenStyle.DotLine),
                movable=False,
            )
            self._plot.addItem(line)


class BarChart(QWidget):
    """Grafico a barre interattivo (es. distribuzione per genere)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot = pg.PlotWidget()
        self._plot.showGrid(x=False, y=True, alpha=0.3)
        layout.addWidget(self._plot)

    def plot_counts(self, labels: Sequence[str], values: Sequence[int]) -> None:
        """Disegna barre etichettate. ``labels`` sull'asse X, ``values`` in Y."""
        self._plot.clear()
        if not labels:
            return
        xs = list(range(len(labels)))
        bar = pg.BarGraphItem(
            x=xs, height=list(values), width=0.6, brush=_REVIEW_COLOR
        )
        self._plot.addItem(bar)
        axis = self._plot.getAxis("bottom")
        axis.setTicks([list(zip(xs, labels))])

    def plot_values(
        self,
        labels: Sequence[str],
        values: Sequence[float],
        y_range: tuple[float, float] | None = None,
    ) -> None:
        """Disegna barre con valori float (es. score medio 0-100).

        A differenza di :meth:`plot_counts`, gestisce esplicitamente la scala
        Y (via ``y_range`` o auto-range sui valori reali) e accorcia/ruota le
        etichette dei generi per renderle leggibili anche quando sono molte.
        """
        self._plot.clear()
        if not labels:
            return
        xs = list(range(len(labels)))
        heights = [float(v) for v in values]
        bar = pg.BarGraphItem(x=xs, height=heights, width=0.6, brush=_REVIEW_COLOR)
        self._plot.addItem(bar)

        axis = self._plot.getAxis("bottom")
        # Etichette accorciate per non sovrapporsi (i nomi lunghi troncati).
        short = [
            (lbl if len(lbl) <= 12 else lbl[:11] + "…") for lbl in labels
        ]
        axis.setTicks([list(zip(xs, short))])

        # Scala Y leggibile: range esplicito o auto-range con un margine.
        if y_range is not None:
            self._plot.setYRange(*y_range)
        elif heights:
            top = max(heights)
            self._plot.setYRange(0, top * 1.1 if top > 0 else 1)


# --- Helper matplotlib per figure statiche (export report) ----------------


def build_growth_figure(points: Sequence, title: str = ""):
    """Crea una ``matplotlib.figure.Figure`` statica della crescita recensioni.

    Pensata per l'export PDF/HTML dei report (non interattiva). Import di
    matplotlib ritardato per non pesare all'avvio della GUI.
    """
    from matplotlib.figure import Figure

    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    review_pts = [
        (p.captured_at, p.total_reviews)
        for p in points
        if p.total_reviews is not None
    ]
    if review_pts:
        xs, ys = zip(*review_pts)
        ax.plot(xs, ys, color=_REVIEW_COLOR, marker="o", label=tr("common.reviews"))
    ax.set_ylabel(tr("common.reviews"))
    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def build_bar_figure(labels: Sequence[str], values: Sequence[int], title: str = ""):
    """Crea una ``Figure`` a barre statica (per export report)."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    if labels:
        ax.bar(range(len(labels)), list(values), color=_REVIEW_COLOR)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
    if title:
        ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
