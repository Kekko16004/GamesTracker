"""Temi QSS per GamesTracker.

Esporta DARK_THEME e LIGHT_THEME. Il tema scuro e' applicato di default
all'avvio dalla funzione :func:`gui.app.run`; l'utente puo' cambiarlo
a runtime dal menu Tema.
"""

DARK_THEME = """
QMainWindow, QWidget { background-color: #1a1d27; color: #e4e7ef; }
QMenuBar { background-color: #12141c; color: #e4e7ef; }
QMenuBar::item:selected { background-color: #2e3347; }
QMenu { background-color: #1a1d27; color: #e4e7ef; border: 1px solid #2e3347; }
QMenu::item:selected { background-color: #6366f1; }
QToolBar { background-color: #12141c; border-bottom: 1px solid #2e3347; spacing: 4px; }
QToolBar QToolButton { color: #9ca3b8; padding: 6px 12px; border-radius: 4px; }
QToolBar QToolButton:hover { background-color: #2e3347; color: #e4e7ef; }
QPushButton { background-color: #6366f1; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; }
QPushButton:hover { background-color: #818cf8; }
QPushButton:pressed { background-color: #4f46e5; }
QPushButton:disabled { background-color: #2e3347; color: #6b7280; }
QComboBox { background-color: #242836; color: #e4e7ef; border: 1px solid #2e3347; padding: 4px 8px; border-radius: 4px; }
QComboBox:hover { border-color: #6366f1; }
QComboBox QAbstractItemView { background-color: #1a1d27; color: #e4e7ef; selection-background-color: #6366f1; }
QCheckBox { color: #e4e7ef; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #2e3347; border-radius: 3px; background: #242836; }
QCheckBox::indicator:checked { background-color: #6366f1; border-color: #6366f1; }
QLabel { color: #e4e7ef; }
QProgressBar { border: 1px solid #2e3347; border-radius: 4px; background-color: #242836; text-align: center; color: #e4e7ef; }
QProgressBar::chunk { background-color: #6366f1; border-radius: 3px; }
QTableView, QTreeView, QListView { background-color: #242836; color: #e4e7ef; border: 1px solid #2e3347; gridline-color: #2e3347; selection-background-color: #6366f1; alternate-background-color: #1e2130; }
QHeaderView::section { background-color: #1a1d27; color: #9ca3b8; border: none; border-bottom: 1px solid #2e3347; padding: 6px; font-weight: 600; }
QScrollBar:vertical { background-color: #1a1d27; width: 10px; }
QScrollBar::handle:vertical { background-color: #2e3347; border-radius: 5px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background-color: #6366f1; }
QSlider::groove:horizontal { background: #2e3347; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #6366f1; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
QTabWidget::pane { border: 1px solid #2e3347; background-color: #1a1d27; }
QTabBar::tab { background-color: #242836; color: #9ca3b8; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background-color: #1a1d27; color: #6366f1; border-bottom: 2px solid #6366f1; }
QTextEdit, QPlainTextEdit { background-color: #242836; color: #e4e7ef; border: 1px solid #2e3347; }
QGroupBox { border: 1px solid #2e3347; border-radius: 6px; margin-top: 12px; padding-top: 16px; color: #e4e7ef; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QStatusBar { background-color: #12141c; color: #9ca3b8; }
QToolTip { background-color: #242836; color: #e4e7ef; border: 1px solid #2e3347; padding: 4px; }
"""

LIGHT_THEME = ""  # Empty = system default (Qt's native look)
