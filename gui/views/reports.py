"""Vista Report: viewer dei report generati (tabella ``analysis_reports``).

Mostra l'elenco dei report, il summary del report selezionato e un blocco
con i dati strutturati a supporto dei grafici. Include pulsanti di export
PDF/HTML che si appoggiano ad ``analysis.reports`` se disponibile; se il
modulo non e' pronto, l'export mostra un messaggio e NON crasha (hook).

Dati via ``GameRepository.list_reports`` / ``get_report`` fuori dal
thread UI.
"""

from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from gui.data_access import GameRepository, ReportDetail, ReportRow
from gui.i18n import tr, translator
from gui.widgets.common import EmptyState
from gui.widgets.tables import Column, DataTableView
from gui.workers import run_query


def _scope(row: ReportRow) -> str:
    """Etichetta di ambito del report (per gioco vs per genere)."""
    if row.game_id is not None:
        return tr("reports.scope.game")
    return tr("reports.scope.genre")


class ReportsView(QWidget):
    """Elenco report + dettaglio con summary, dati ed export."""

    def __init__(self, repo: GameRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._current: ReportDetail | None = None
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

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sinistra: elenco report.
        self._table = DataTableView(
            [
                Column("common.title", lambda r: r.game_title or r.genre or ""),
                Column("reports.scope.game", _scope),
                Column("app.language", lambda r: r.lang),
                Column(
                    "reports.generated_at",
                    lambda r: (
                        r.generated_at.strftime("%Y-%m-%d")
                        if r.generated_at
                        else tr("common.na")
                    ),
                ),
            ]
        )
        self._table.clicked.connect(self._on_row_clicked)
        splitter.addWidget(self._table)

        # Destra: dettaglio (summary + dati + export).
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self._summary_label = QLabel()
        self._summary = QPlainTextEdit()
        self._summary.setReadOnly(True)
        self._data_label = QLabel()
        self._data = QPlainTextEdit()
        self._data.setReadOnly(True)

        export_row = QHBoxLayout()
        self._btn_html = QPushButton()
        self._btn_pdf = QPushButton()
        self._btn_html.clicked.connect(lambda: self._export("html"))
        self._btn_pdf.clicked.connect(lambda: self._export("pdf"))
        self._btn_html.setEnabled(False)
        self._btn_pdf.setEnabled(False)
        export_row.addWidget(self._btn_html)
        export_row.addWidget(self._btn_pdf)
        export_row.addStretch(1)

        self._detail_placeholder = EmptyState(
            "reports.title", "empty.select_report"
        )
        self._detail_content = QWidget()
        dc_layout = QVBoxLayout(self._detail_content)
        dc_layout.addWidget(self._summary_label)
        dc_layout.addWidget(self._summary, stretch=2)
        dc_layout.addWidget(self._data_label)
        dc_layout.addWidget(self._data, stretch=1)
        dc_layout.addLayout(export_row)

        self._detail_stack = QStackedWidget()
        self._detail_stack.addWidget(self._detail_placeholder)
        self._detail_stack.addWidget(self._detail_content)
        right_layout.addWidget(self._detail_stack)
        splitter.addWidget(right)
        splitter.setSizes([300, 500])

        # Stato vuoto globale (nessun report).
        self._empty = EmptyState("reports.title", "empty.no_reports")
        self._main_stack = QStackedWidget()
        self._main_stack.addWidget(splitter)
        self._main_stack.addWidget(self._empty)
        root.addWidget(self._main_stack, stretch=1)

        self.retranslate()

    # --- Caricamento ------------------------------------------------------

    def refresh(self) -> None:
        """Ricarica l'elenco report fuori dal thread UI."""
        run_query(self._repo.list_reports, self._on_reports)

    def _on_reports(self, reports: list[ReportRow]) -> None:
        if not reports:
            self._main_stack.setCurrentWidget(self._empty)
            return
        self._table.set_rows(reports)
        self._main_stack.setCurrentWidget(self._main_stack.widget(0))

    def _on_row_clicked(self, index) -> None:  # noqa: ANN001
        row = self._table.row_object(index.row())
        if isinstance(row, ReportRow):
            run_query(lambda: self._repo.get_report(row.id), self._on_detail)

    def _on_detail(self, detail: ReportDetail | None) -> None:
        self._current = detail
        if detail is None:
            self._detail_stack.setCurrentWidget(self._detail_placeholder)
            return
        self._summary.setPlainText(detail.summary or tr("common.na"))
        self._data.setPlainText(
            json.dumps(detail.data, indent=2, ensure_ascii=False, default=str)
        )
        self._btn_html.setEnabled(True)
        self._btn_pdf.setEnabled(True)
        self._detail_stack.setCurrentWidget(self._detail_content)

    # --- Export (hook su analysis.reports, degrada con grazia) ------------

    def _export(self, fmt: str) -> None:
        """Esporta il report corrente in HTML o PDF.

        Usa ``analysis.reports`` se importabile. Se il modulo non e'
        disponibile o l'export PDF non e' supportato nell'ambiente, mostra
        un avviso tradotto senza mai sollevare.
        """
        if self._current is None:
            return
        try:
            from analysis import reports as analysis_reports
        except Exception:
            QMessageBox.information(
                self,
                tr("nav.reports"),
                tr("reports.export_unavailable"),
            )
            return

        report_dict = {
            "summary": self._current.summary,
            "data": self._current.data,
        }
        title = self._current.game_title or self._current.genre or tr("nav.reports")

        if fmt == "html":
            path, _ = QFileDialog.getSaveFileName(
                self, tr("reports.export_html"), "report.html", "HTML (*.html)"
            )
            if not path:
                return
            try:
                html_str = analysis_reports.export_html(report_dict, title=title)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(html_str)
            except Exception:
                QMessageBox.information(
                    self, tr("nav.reports"), tr("reports.export_unavailable")
                )
                return
            QMessageBox.information(
                self, tr("nav.reports"), tr("reports.export_done", path=path)
            )
        else:  # pdf
            path, _ = QFileDialog.getSaveFileName(
                self, tr("reports.export_pdf"), "report.pdf", "PDF (*.pdf)"
            )
            if not path:
                return
            result = None
            try:
                result = analysis_reports.export_pdf(report_dict, path, title=title)
            except Exception:
                result = None
            if result:
                QMessageBox.information(
                    self, tr("nav.reports"), tr("reports.export_done", path=path)
                )
            else:
                QMessageBox.information(
                    self, tr("nav.reports"), tr("reports.export_unavailable")
                )

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        """Riapplica le stringhe visibili."""
        self._title.setText(tr("reports.title"))
        self._summary_label.setText(tr("reports.summary"))
        self._data_label.setText(tr("reports.data"))
        self._btn_html.setText(tr("reports.export_html"))
        self._btn_pdf.setText(tr("reports.export_pdf"))
        self._table.retranslate()
        self._empty.retranslate()
        self._detail_placeholder.retranslate()
