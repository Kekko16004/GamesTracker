"""Entrypoint della GUI PyQt6 di GamesTracker.

Definisce :class:`MainWindow` (navigazione tra le viste: dashboard, trend,
report, dettaglio gioco) e :func:`run` che avvia la ``QApplication``.

La GUI legge SOLO dal DB via ``core.db`` + ``gui.data_access``: nessuna
chiamata di rete diretta. La lingua di default arriva da ``core.config``
(APP_LANG) e puo' essere cambiata a runtime dal menu Lingua.
"""

from __future__ import annotations

import sys

from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QToolBar,
)

from gui.data_access import GameRepository
from gui.i18n import available_languages, tr, translator
from gui.views.ai_copilot import AiCopilotView
from gui.views.dashboard import DashboardView
from gui.views.game_detail import GameDetailView
from gui.views.reports import ReportsView
from gui.views.simulator import SimulatorView
from gui.views.trends import TrendsView


class MainWindow(QMainWindow):
    """Finestra principale con toolbar di navigazione e stack di viste."""

    def __init__(self, repo: GameRepository | None = None) -> None:
        super().__init__()
        self._repo = repo or GameRepository()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Istanzia le viste.
        self._dashboard = DashboardView(self._repo)
        self._trends = TrendsView(self._repo)
        self._reports = ReportsView(self._repo)
        self._simulator = SimulatorView()
        self._detail = GameDetailView(self._repo)
        self._ai_copilot = AiCopilotView()

        for view in (self._dashboard, self._trends, self._reports,
                     self._simulator, self._detail, self._ai_copilot):
            self._stack.addWidget(view)

        # Navigazione tra le viste.
        self._dashboard.gameSelected.connect(self._open_detail)
        self._detail.backRequested.connect(
            lambda: self._stack.setCurrentWidget(self._dashboard)
        )

        self._build_toolbar()
        self._build_menu()

        self._stack.setCurrentWidget(self._dashboard)
        translator.subscribe(lambda _l: self.retranslate())
        self.resize(1100, 720)
        self.retranslate()

    # --- Toolbar / menu ---------------------------------------------------

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        self._act_dashboard = QAction(self)
        self._act_trends = QAction(self)
        self._act_reports = QAction(self)
        self._act_simulator = QAction(self)
        self._act_ai_copilot = QAction(self)
        self._act_dashboard.triggered.connect(
            lambda: self._stack.setCurrentWidget(self._dashboard)
        )
        self._act_trends.triggered.connect(
            lambda: self._stack.setCurrentWidget(self._trends)
        )
        self._act_reports.triggered.connect(
            lambda: self._stack.setCurrentWidget(self._reports)
        )
        self._act_simulator.triggered.connect(
            lambda: self._stack.setCurrentWidget(self._simulator)
        )
        self._act_ai_copilot.triggered.connect(
            lambda: self._stack.setCurrentWidget(self._ai_copilot)
        )
        for act in (self._act_dashboard, self._act_trends, self._act_reports,
                    self._act_simulator, self._act_ai_copilot):
            self._toolbar.addAction(act)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        # Menu Vista.
        self._view_menu = menubar.addMenu("")
        self._view_menu.addAction(self._act_dashboard)
        self._view_menu.addAction(self._act_trends)
        self._view_menu.addAction(self._act_reports)
        self._view_menu.addAction(self._act_simulator)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._act_ai_copilot)

        # Menu Tema con gruppo esclusivo.
        from gui.theme import DARK_THEME, LIGHT_THEME
        self._theme_menu = menubar.addMenu("")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._act_dark = QAction("Scuro / Dark", self)
        self._act_dark.setCheckable(True)
        self._act_dark.setChecked(True)
        self._act_light = QAction("Chiaro / Light", self)
        self._act_light.setCheckable(True)
        self._theme_group.addAction(self._act_dark)
        self._theme_group.addAction(self._act_light)
        self._theme_menu.addAction(self._act_dark)
        self._theme_menu.addAction(self._act_light)
        self._act_dark.triggered.connect(
            lambda: QApplication.instance().setStyleSheet(DARK_THEME)
        )
        self._act_light.triggered.connect(
            lambda: QApplication.instance().setStyleSheet(LIGHT_THEME)
        )

        # Menu Lingua con gruppo esclusivo.
        self._lang_menu = menubar.addMenu("")
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        for code, label in available_languages():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(code == translator.language)
            act.triggered.connect(lambda _checked, c=code: self._set_language(c))
            self._lang_group.addAction(act)
            self._lang_menu.addAction(act)
            self._lang_actions[code] = act

    # --- Navigazione ------------------------------------------------------

    def _open_detail(self, game_id: int) -> None:
        """Apre la vista dettaglio per il gioco selezionato."""
        self._detail.load_game(game_id)
        self._stack.setCurrentWidget(self._detail)

    def _set_language(self, code: str) -> None:
        """Cambia la lingua della UI a runtime."""
        translator.set_language(code)

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        """Riapplica titoli finestra, toolbar e menu."""
        self.setWindowTitle(tr("app.title"))
        self._act_dashboard.setText(tr("nav.dashboard"))
        self._act_trends.setText(tr("nav.trends"))
        self._act_reports.setText(tr("nav.reports"))
        self._act_simulator.setText(tr("nav.simulator"))
        self._act_ai_copilot.setText(tr("nav.ai_copilot"))
        self._view_menu.setTitle(tr("app.menu.view"))
        self._theme_menu.setTitle(tr("app.menu.theme"))
        self._lang_menu.setTitle(tr("app.menu.language"))
        # Sincronizza il check della lingua attiva.
        for code, act in self._lang_actions.items():
            act.setChecked(code == translator.language)


def run(argv: list[str] | None = None) -> int:
    """Avvia la QApplication con la MainWindow. Ritorna il codice di uscita.

    Inizializza il DB in sola lettura (crea lo schema se manca, senza
    scrivere dati) e imposta la lingua di default da ``core.config``.
    """
    argv = argv if argv is not None else sys.argv

    # Lingua di default da config (APP_LANG), senza fallire se manca.
    try:
        from core.config import get_settings

        translator.set_language(get_settings().app_lang)
    except Exception:
        pass

    # Assicura che lo schema esista (idempotente, nessuna scrittura di dati).
    try:
        from core.db import init_db

        init_db()
    except Exception:
        # La GUI puo' comunque avviarsi mostrando stati vuoti.
        pass

    app = QApplication(argv)
    from gui.theme import DARK_THEME
    app.setStyleSheet(DARK_THEME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
