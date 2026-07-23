"""Tabelle riutilizzabili (QTableView + model generico) per la GUI.

Il :class:`DataclassTableModel` mostra una lista di oggetti (dataclass o
qualsiasi oggetto con attributi) definendo le colonne come coppie
``(chiave_i18n, funzione_estrazione)``. Cosi' le liste giochi/post/report
condividono lo stesso model senza duplicare codice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from gui.i18n import tr
from gui.widgets.sorting import sort_rows


@dataclass
class Column:
    """Definizione di una colonna della tabella.

    Attributi:
        header_key: chiave i18n per l'intestazione.
        extractor: funzione ``oggetto -> valore`` mostrato nella cella.
        align_right: allinea a destra (utile per i numeri).
    """

    header_key: str
    extractor: Callable[[Any], Any]
    align_right: bool = False


class DataclassTableModel(QAbstractTableModel):
    """Model generico su una lista di oggetti e una lista di :class:`Column`."""

    def __init__(
        self,
        columns: Sequence[Column],
        rows: Sequence[Any] | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: list[Any] = list(rows or [])
        # Ordine originale (per il reset del ciclo 3-stati) e stato di sort.
        self._original_rows: list[Any] = list(self._rows)
        self._sort_column: int | None = None
        # 0 = nessuno, 1 = crescente, 2 = decrescente.
        self._sort_state: int = 0

    # --- API dati ---------------------------------------------------------

    def set_rows(self, rows: Sequence[Any]) -> None:
        """Sostituisce i dati mostrati (reset completo del model).

        Dati nuovi = azzera lo stato di sort (l'ordine originale cambia).
        """
        self.beginResetModel()
        self._rows = list(rows)
        self._original_rows = list(self._rows)
        self._sort_column = None
        self._sort_state = 0
        self.endResetModel()

    def row_object(self, row: int) -> Any | None:
        """Oggetto sorgente della riga ``row`` (per gestire il click)."""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # --- Ordinamento a 3 stati -------------------------------------------

    def cycle_sort(self, column: int) -> None:
        """Cicla l'ordinamento della colonna ``column`` su 3 stati.

        1o click = crescente, 2o = decrescente, 3o = ripristina l'ordine
        originale. Cliccare una colonna diversa riparte dal crescente.
        """
        if not (0 <= column < len(self._columns)):
            return
        if self._sort_column != column:
            # Nuova colonna: parte da crescente.
            self._sort_column = column
            self._sort_state = 1
        else:
            # Stessa colonna: avanza nel ciclo 0 -> 1 -> 2 -> 0.
            self._sort_state = (self._sort_state + 1) % 3

        self.beginResetModel()
        if self._sort_state == 0:
            # Reset all'ordine originale.
            self._rows = list(self._original_rows)
            self._sort_column = None
        else:
            extractor = self._columns[column].extractor
            self._rows = sort_rows(
                self._original_rows,
                extractor,
                descending=(self._sort_state == 2),
            )
        self.endResetModel()

    def sort_state(self) -> tuple[int | None, int]:
        """Stato corrente del sort: ``(colonna, stato)`` (per i test/indicatore)."""
        return (self._sort_column, self._sort_state)

    # --- Override QAbstractTableModel ------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        column = self._columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            value = column.extractor(self._rows[index.row()])
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and column.align_right:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            label = tr(self._columns[section].header_key)
            # Indicatore visivo dello stato di sort sulla colonna attiva.
            if section == self._sort_column and self._sort_state == 1:
                label = f"{label}  ▲"  # freccia su = crescente
            elif section == self._sort_column and self._sort_state == 2:
                label = f"{label}  ▼"  # freccia giu = decrescente
            return label
        return section + 1

    def retranslate(self) -> None:
        """Notifica il refresh delle intestazioni dopo un cambio lingua."""
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, max(0, len(self._columns) - 1)
        )


class DataTableView(QTableView):
    """QTableView preconfigurata: selezione per riga, header elastico, a11y."""

    def __init__(self, columns: Sequence[Column], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._model = DataclassTableModel(columns)
        self.setModel(self._model)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        # Navigazione da tastiera abilitata.
        self.setTabKeyNavigation(True)
        # Sort a 3 stati: click sull'header -> cicla ordinamento della colonna.
        # (setSortingEnabled resta False: usiamo il nostro ciclo custom.)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._model.cycle_sort)

    def set_rows(self, rows: Sequence[Any]) -> None:
        """Aggiorna i dati mostrati."""
        self._model.set_rows(rows)

    def row_object(self, row: int) -> Any | None:
        """Oggetto sorgente della riga ``row``."""
        return self._model.row_object(row)

    def retranslate(self) -> None:
        """Propaga la ritraduzione delle intestazioni al model."""
        self._model.retranslate()
