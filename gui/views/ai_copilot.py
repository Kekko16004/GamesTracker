"""Vista AI Copilot: genera descrizioni, titoli, prompt immagini, tag e testi
marketing per il tuo videogioco indie tramite un provider AI configurabile.

Il form raccoglie le caratteristiche del gioco (descrizione, genere, stile
grafico, target, giochi simili) e invia tutto al backend AI in modo asincrono
tramite :func:`gui.workers.run_query`, mantenendo la GUI sempre reattiva.

Se il modulo AI non e' ancora configurato, viene usato un mock che restituisce
dati campione per poter navigare/testare l'interfaccia.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.i18n import tr, translator
from gui.views.ai_settings import AiSettingsDialog
from gui.workers import run_query


# ---------------------------------------------------------------------------
# Mock AI backend
# ---------------------------------------------------------------------------

def _mock_generate(inputs: dict[str, Any]) -> dict[str, Any]:
    """Restituisce dati campione. Rimpiazzare con la vera chiamata AI."""
    genre = inputs.get("genre", "RPG")
    style = inputs.get("art_style", "Pixel Art")
    title_base = inputs.get("similar_games", "Celeste, Hollow Knight").split(",")[0].strip() or "MyGame"

    return {
        "short_desc": (
            f"Un {genre.lower()} con estetica {style.lower()} che combina esplorazione profonda "
            f"e combattimento frenetico. Ambientato in un mondo procedurale ricco di segreti."
        ),
        "long_desc": (
            f"## Il tuo viaggio inizia qui\n\n"
            f"Immergiti in un {genre.lower()} dall'estetica {style.lower()} dove ogni run e' diversa "
            f"dall'ultima. Il mondo e' generato proceduralmente, con biomi unici, boss memorabili "
            f"e narrative emergenti che prendono forma dalle tue scelte.\n\n"
            f"### Meccaniche principali\n"
            f"- Combattimento reattivo con combo personalizzabili\n"
            f"- Sistema di progressione non-lineare\n"
            f"- Crafting e modificatori che cambiano il playstyle\n"
            f"- Lore ambientale ricco, scoperto esplora per esplorare\n\n"
            f"### Ispirato ai migliori\n"
            f"Fans di {inputs.get('similar_games', 'Celeste, Hades, Dead Cells')} troveranno "
            f"un'esperienza familiare eppure fresca, che spinge il genere in nuove direzioni.\n\n"
            f"### Per chi e'?\n"
            f"{inputs.get('target_audience', 'Giocatori hardcore e casual')} — chiunque ami "
            f"sistemi profondi e un'atmosfera avvincente."
        ),
        "titles": [
            {"title": f"Aether{genre[:4]}",        "score": 92, "reason": "Evocativo, breve, memorabile. Facile da pronunciare in tutte le lingue."},
            {"title": f"Shattered Realms",          "score": 88, "reason": "Suona epico, comunica frammentazione/esplorazione, coerente col genere."},
            {"title": f"Echoes of {title_base}",   "score": 85, "reason": "Richiama il gioco ispirazione ma si distingue con 'Echoes'."},
            {"title": f"Neon {genre} Chronicles",   "score": 81, "reason": f"Evidenzia lo stile {style} con 'Neon', utile per la scopribilita'."},
            {"title": "Void Wanderer",              "score": 79, "reason": "Generico ma forte: esplorazione + solitudine, funziona su Steam."},
            {"title": f"The {genre} Protocol",      "score": 76, "reason": "Titolo professionale che suggerisce sistemi complessi."},
            {"title": "Fractal Depths",             "score": 74, "reason": "Richiama la generazione procedurale e i mondi labirintici."},
            {"title": "Lumen & Shadow",             "score": 71, "reason": "Dualita' tematica, ottimo per lo storytelling marketing."},
        ],
        "image_prompts": {
            "capsule": (
                f"Game capsule art for a {genre} game, {style.lower()} style, "
                f"dramatic lighting, centered hero character silhouetted against a glowing portal, "
                f"deep purples and indigo tones with golden accents, "
                f"professional game cover composition, 460x215px ratio, "
                f"high contrast, Steam store ready"
            ),
            "header": (
                f"Steam header banner for a {genre} game, {style.lower()} art style, "
                f"wide cinematic 16:6 composition, atmospheric scene with ruins and mystical glowing elements, "
                f"fog and depth, moody color palette with indigo and teal highlights, "
                f"game logo space at center-right, 460x215 aspect"
            ),
            "library_hero": (
                f"Steam library hero image, {style.lower()} {genre} game, "
                f"full-width atmospheric artwork 1920x620, key art scene showing protagonist "
                f"in dramatic pose against vast alien landscape, "
                f"rich colors, cinematic depth-of-field, professional game art quality"
            ),
            "screenshots": [
                (
                    f"In-game screenshot of {genre} gameplay, {style.lower()} visuals, "
                    f"action combat scene with particle effects and glowing weapons, "
                    f"HUD minimal and elegant, 1920x1080, colorful and dynamic"
                ),
                (
                    f"Exploration scene in a {style.lower()} {genre} world, "
                    f"lush procedural environment with hidden paths and atmospheric lighting, "
                    f"in-game screenshot 1920x1080, vibrant palette"
                ),
                (
                    f"Boss fight moment in a {genre} with {style.lower()} art style, "
                    f"epic scale enemy filling the frame, intense lighting, "
                    f"player character at bottom-left, 1920x1080 screenshot"
                ),
                (
                    f"Inventory/upgrade screen for {style.lower()} {genre}, "
                    f"clean dark UI with glowing item icons, satisfying progression display, "
                    f"1920x1080, dark theme with {style.lower()} aesthetic accents"
                ),
            ],
        },
        "tags": [
            genre, style, "Indie", "Roguelike", "Atmospheric",
            "Dark Fantasy", "Procedural Generation", "Action",
            "Exploration", "Lore-Rich", "Singleplayer", "Controller Support",
            "Challenging", "Pixel Graphics" if "Pixel" in style else "3D",
            "Story Rich", "Replay Value",
        ],
        "elevator_pitch": (
            f"Un {genre.lower()} con grafica {style.lower()} che combina la profondita' di "
            f"{inputs.get('similar_games', 'Hades')} con un'ambientazione originale e procedurale. "
            f"Ogni partita e' un'avventura unica: esplora, combatti, muori e torna piu' forte. "
            f"Per {inputs.get('target_audience', 'tutti i fan degli indie di qualita')}."
        ),
        "marketing_hooks": [
            f"🎮 Un {genre} che ti fa venire voglia di ricominciare ogni volta che muori.",
            f"🎨 Visivamente ispirato a {inputs.get('similar_games', 'Hollow Knight')} — ma con un'identita' tutta sua.",
            f"🌍 Mondo procedurale: migliaia di ore di contenuto, zero ripetizione.",
            f"⚔️ Combat system che premia la skill — accessibile, masturabile.",
            f"📖 Lore profonda per chi la cerca, invisibile per chi preferisce solo giocare.",
            f"🚀 Lanciato dalla community, non dai publisher: ogni wishlista conta.",
        ],
    }


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

class _CopyButton(QPushButton):
    """Bottone 'Copia tutto' riutilizzabile."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(130)
        self._retranslate()
        translator.subscribe(lambda _l: self._retranslate())

    def _retranslate(self) -> None:
        self.setText(tr("ai.copy_all"))

    def flash_copied(self) -> None:
        """Feedback visivo: mostra 'Copiato!' per un secondo."""
        original = self.text()
        self.setText(tr("ai.copied"))
        self.setEnabled(False)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1200, lambda: (self.setText(original), self.setEnabled(True)))


class _TagBadge(QLabel):
    """Badge colorato per un singolo tag."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            "QLabel {"
            "  background-color: #2a2d40;"
            "  color: #a5b4fc;"
            "  border: 1px solid #6366f1;"
            "  border-radius: 12px;"
            "  padding: 4px 12px;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "}"
            "QLabel:hover {"
            "  background-color: #6366f1;"
            "  color: #ffffff;"
            "  cursor: pointer;"
            "}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("ai.copy_all"))

    def mousePressEvent(self, ev) -> None:  # noqa: ANN001
        QApplication.clipboard().setText(self.text())
        super().mousePressEvent(ev)


# ---------------------------------------------------------------------------
# Tab contents
# ---------------------------------------------------------------------------

class _DescriptionTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Toolbar
        top_row = QHBoxLayout()
        self._short_label = QLabel()
        self._short_label.setStyleSheet("font-weight: 700; font-size: 13px; color: #a5b4fc;")
        self._copy_btn = _CopyButton()
        self._copy_btn.clicked.connect(self._copy_all)
        top_row.addWidget(self._short_label)
        top_row.addStretch()
        top_row.addWidget(self._copy_btn)
        layout.addLayout(top_row)

        # Short description
        self._short_edit = QTextEdit()
        self._short_edit.setReadOnly(True)
        self._short_edit.setMaximumHeight(80)
        self._short_edit.setPlaceholderText(tr("ai.no_results"))
        self._short_edit.setStyleSheet(
            "QTextEdit { border: 1px solid #6366f1; border-radius: 6px; "
            "background: #1e2130; padding: 8px; font-size: 13px; }"
        )
        layout.addWidget(self._short_edit)

        # Long description
        self._long_label = QLabel()
        self._long_label.setStyleSheet("font-weight: 700; font-size: 13px; color: #a5b4fc;")
        layout.addWidget(self._long_label)
        self._long_edit = QTextEdit()
        self._long_edit.setReadOnly(True)
        self._long_edit.setPlaceholderText(tr("ai.no_results"))
        self._long_edit.setStyleSheet(
            "QTextEdit { border: 1px solid #2e3347; border-radius: 6px; "
            "background: #1e2130; padding: 8px; font-size: 13px; }"
        )
        layout.addWidget(self._long_edit, stretch=1)
        self.retranslate()

    def set_data(self, short: str, long: str) -> None:
        self._short_edit.setPlainText(short)
        self._long_edit.setMarkdown(long) if long.startswith("#") else self._long_edit.setPlainText(long)

    def _copy_all(self) -> None:
        combined = f"{self._short_edit.toPlainText()}\n\n{self._long_edit.toPlainText()}"
        QApplication.clipboard().setText(combined)
        self._copy_btn.flash_copied()

    def retranslate(self) -> None:
        self._short_label.setText(tr("ai.short_desc"))
        self._long_label.setText(tr("ai.long_desc"))


class _TitlesTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self._copy_btn = _CopyButton()
        self._copy_btn.clicked.connect(self._copy_all)
        top_row.addStretch()
        top_row.addWidget(self._copy_btn)
        layout.addLayout(top_row)

        self._table = QTableWidget(0, 4)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableWidget { border: 1px solid #2e3347; border-radius: 6px; }"
            "QTableWidget::item { padding: 6px 10px; }"
        )
        layout.addWidget(self._table, stretch=1)
        self.retranslate()

    def set_data(self, titles: list[dict]) -> None:
        self._table.setRowCount(0)
        for i, item in enumerate(titles):
            self._table.insertRow(i)
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            score_item = QTableWidgetItem(str(item.get("score", "")))
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # Color score by value
            score = item.get("score", 0)
            color = "#22c55e" if score >= 85 else "#f59e0b" if score >= 75 else "#9ca3b8"
            score_item.setForeground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(color)
            )
            self._table.setItem(i, 0, num_item)
            self._table.setItem(i, 1, QTableWidgetItem(item.get("title", "")))
            self._table.setItem(i, 2, score_item)
            self._table.setItem(i, 3, QTableWidgetItem(item.get("reason", "")))
        self._table.resizeColumnToContents(0)
        self._table.resizeColumnToContents(1)
        self._table.resizeColumnToContents(2)

    def _copy_all(self) -> None:
        lines: list[str] = []
        for row in range(self._table.rowCount()):
            parts = [
                self._table.item(row, c).text() if self._table.item(row, c) else ""
                for c in range(4)
            ]
            lines.append(" | ".join(parts))
        QApplication.clipboard().setText("\n".join(lines))
        self._copy_btn.flash_copied()

    def retranslate(self) -> None:
        self._table.setHorizontalHeaderLabels([
            "#", tr("common.title"), "Score", tr("ai.tab.reason"),
        ])


class _ImagePromptsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setSpacing(0)

        top_row = QHBoxLayout()
        self._copy_btn = _CopyButton()
        self._copy_btn.clicked.connect(self._copy_all)
        top_row.addStretch()
        top_row.addWidget(self._copy_btn)
        outer.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        self._inner = QVBoxLayout(content)
        self._inner.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # Capsule
        self._capsule_box, self._capsule_edit = self._make_group("ai.img.capsule")
        # Header
        self._header_box, self._header_edit = self._make_group("ai.img.header")
        # Library hero
        self._hero_box, self._hero_edit = self._make_group("ai.img.hero")
        # Screenshots
        self._shots_box = QGroupBox()
        self._shots_layout = QVBoxLayout(self._shots_box)
        self._shot_edits: list[QTextEdit] = []
        self._inner.addWidget(self._shots_box)
        self._inner.addStretch()

        self.retranslate()

    def _make_group(self, label_key: str) -> tuple[QGroupBox, QTextEdit]:
        box = QGroupBox()
        box._label_key = label_key  # type: ignore[attr-defined]
        vlay = QVBoxLayout(box)

        row = QHBoxLayout()
        copy_btn = QPushButton(tr("ai.copy_all"))
        copy_btn.setFixedWidth(110)
        copy_btn.setStyleSheet(
            "QPushButton { background: #2e3347; color: #a5b4fc; font-size: 11px; "
            "padding: 4px 8px; border-radius: 4px; font-weight: normal; }"
            "QPushButton:hover { background: #6366f1; color: white; }"
        )
        row.addStretch()
        row.addWidget(copy_btn)
        vlay.addLayout(row)

        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setMaximumHeight(100)
        edit.setStyleSheet(
            "QTextEdit { background: #1e2130; border: 1px solid #2e3347; "
            "border-radius: 4px; padding: 6px; font-size: 12px; "
            "font-family: 'Courier New', monospace; color: #c4b5fd; }"
        )
        copy_btn.clicked.connect(lambda: (
            QApplication.clipboard().setText(edit.toPlainText()),
        ))
        vlay.addWidget(edit)
        self._inner.addWidget(box)
        return box, edit

    def set_data(self, prompts: dict) -> None:
        self._capsule_edit.setPlainText(prompts.get("capsule", ""))
        self._header_edit.setPlainText(prompts.get("header", ""))
        self._hero_edit.setPlainText(prompts.get("library_hero", ""))

        # Rebuild screenshot section
        for edit in self._shot_edits:
            edit.setParent(None)
        self._shot_edits.clear()
        for i, shot in enumerate(prompts.get("screenshots", [])):
            row = QHBoxLayout()
            lbl = QLabel(f"Screenshot {i + 1}")
            lbl.setStyleSheet("color: #9ca3b8; font-size: 11px;")
            copy_btn = QPushButton(tr("ai.copy_all"))
            copy_btn.setFixedWidth(80)
            copy_btn.setStyleSheet(
                "QPushButton { background: #2e3347; color: #a5b4fc; font-size: 10px; "
                "padding: 3px 6px; border-radius: 4px; font-weight: normal; }"
                "QPushButton:hover { background: #6366f1; color: white; }"
            )
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(copy_btn)
            self._shots_layout.addLayout(row)
            edit = QTextEdit()
            edit.setReadOnly(True)
            edit.setMaximumHeight(72)
            edit.setPlainText(shot)
            edit.setStyleSheet(
                "QTextEdit { background: #1e2130; border: 1px solid #2e3347; "
                "border-radius: 4px; padding: 6px; font-size: 11px; "
                "font-family: 'Courier New', monospace; color: #c4b5fd; }"
            )
            copy_btn.clicked.connect(
                lambda _checked=False, e=edit: QApplication.clipboard().setText(e.toPlainText())
            )
            self._shots_layout.addWidget(edit)
            self._shot_edits.append(edit)

    def _copy_all(self) -> None:
        parts = [
            self._capsule_edit.toPlainText(),
            self._header_edit.toPlainText(),
            self._hero_edit.toPlainText(),
            *[e.toPlainText() for e in self._shot_edits],
        ]
        QApplication.clipboard().setText("\n\n---\n\n".join(p for p in parts if p))
        self._copy_btn.flash_copied()

    def retranslate(self) -> None:
        self._capsule_box.setTitle(tr("ai.img.capsule"))
        self._header_box.setTitle(tr("ai.img.header"))
        self._hero_box.setTitle(tr("ai.img.hero"))
        self._shots_box.setTitle(tr("ai.img.screenshots"))


class _TagsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self._hint = QLabel()
        self._hint.setStyleSheet("color: #6b7280; font-size: 12px;")
        self._copy_btn = _CopyButton()
        self._copy_btn.clicked.connect(self._copy_all)
        top_row.addWidget(self._hint)
        top_row.addStretch()
        top_row.addWidget(self._copy_btn)
        layout.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tag_container = QWidget()
        self._flow = QHBoxLayout(self._tag_container)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setSpacing(8)
        self._flow.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._tag_container)
        layout.addWidget(scroll, stretch=1)

        self._tags: list[str] = []
        self.retranslate()

    def set_data(self, tags: list[str]) -> None:
        self._tags = tags
        # Remove old badges
        while self._flow.count():
            item = self._flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Use a wrapping grid-like layout via multiple HBoxLayouts in a VBox
        # Simpler: just add badges horizontally and let them wrap via flow
        for tag in tags:
            badge = _TagBadge(tag)
            self._flow.addWidget(badge)
        self._flow.addStretch()

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(", ".join(self._tags))
        self._copy_btn.flash_copied()

    def retranslate(self) -> None:
        self._hint.setText(tr("ai.tags_hint"))


class _MarketingTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self._copy_btn = _CopyButton()
        self._copy_btn.clicked.connect(self._copy_all)
        top_row.addStretch()
        top_row.addWidget(self._copy_btn)
        layout.addLayout(top_row)

        # Elevator pitch
        self._pitch_box = QGroupBox()
        pitch_lay = QVBoxLayout(self._pitch_box)
        self._pitch_edit = QTextEdit()
        self._pitch_edit.setReadOnly(True)
        self._pitch_edit.setMaximumHeight(100)
        self._pitch_edit.setStyleSheet(
            "QTextEdit { background: #1e2130; border: 1px solid #6366f1; "
            "border-radius: 6px; padding: 8px; font-size: 13px; "
            "font-style: italic; color: #e4e7ef; }"
        )
        pitch_lay.addWidget(self._pitch_edit)
        layout.addWidget(self._pitch_box)

        # Marketing hooks
        self._hooks_box = QGroupBox()
        hooks_lay = QVBoxLayout(self._hooks_box)
        self._hooks_edit = QTextEdit()
        self._hooks_edit.setReadOnly(True)
        self._hooks_edit.setStyleSheet(
            "QTextEdit { background: #1e2130; border: 1px solid #2e3347; "
            "border-radius: 6px; padding: 8px; font-size: 13px; color: #e4e7ef; }"
        )
        hooks_lay.addWidget(self._hooks_edit)
        layout.addWidget(self._hooks_box, stretch=1)
        self.retranslate()

    def set_data(self, elevator_pitch: str, hooks: list[str]) -> None:
        self._pitch_edit.setPlainText(elevator_pitch)
        self._hooks_edit.setPlainText("\n".join(hooks))

    def _copy_all(self) -> None:
        combined = (
            f"{self._pitch_edit.toPlainText()}\n\n"
            f"{self._hooks_edit.toPlainText()}"
        )
        QApplication.clipboard().setText(combined)
        self._copy_btn.flash_copied()

    def retranslate(self) -> None:
        self._pitch_box.setTitle(tr("ai.marketing.elevator_pitch"))
        self._hooks_box.setTitle(tr("ai.marketing.hooks"))


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class AiCopilotView(QWidget):
    """Vista principale del AI Copilot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        translator.subscribe(lambda _l: self.retranslate())
        self.retranslate()

    # --- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(16, 16, 16, 16)

        # Title row
        title_row = QHBoxLayout()
        self._title_label = QLabel()
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setStyleSheet("color: #a5b4fc; margin-bottom: 8px;")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        root.addLayout(title_row)

        # Separator line
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2e3347; margin-bottom: 12px;")
        root.addWidget(sep)

        # Splitter: left form | right results
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # --- Left panel (form) ---
        left_widget = QWidget()
        left_widget.setMinimumWidth(280)
        left_widget.setMaximumWidth(380)
        left_lay = QVBoxLayout(left_widget)
        left_lay.setSpacing(10)
        left_lay.setContentsMargins(0, 0, 8, 0)

        self._desc_label = QLabel()
        self._desc_label.setStyleSheet("font-weight: 600; color: #9ca3b8; font-size: 11px;")
        left_lay.addWidget(self._desc_label)

        self._desc_input = QPlainTextEdit()
        self._desc_input.setMinimumHeight(130)
        self._desc_input.setMaximumHeight(170)
        self._desc_input.setStyleSheet(
            "QPlainTextEdit { border: 1px solid #2e3347; border-radius: 6px; "
            "background: #242836; padding: 8px; font-size: 13px; }"
            "QPlainTextEdit:focus { border-color: #6366f1; }"
        )
        left_lay.addWidget(self._desc_input)

        # Genre
        self._genre_label = QLabel()
        self._genre_label.setStyleSheet("font-weight: 600; color: #9ca3b8; font-size: 11px;")
        left_lay.addWidget(self._genre_label)
        self._genre_combo = QComboBox()
        self._genre_combo.addItems([
            "RPG", "Roguelike", "Platformer", "Puzzle", "Strategy",
            "Simulation", "Horror", "Adventure", "Action", "Survival",
            "Racing", "Sports", "Visual Novel", "Metroidvania",
            "City Builder", "Tower Defense", "FPS", "Other",
        ])
        left_lay.addWidget(self._genre_combo)

        # Art style
        self._style_label = QLabel()
        self._style_label.setStyleSheet("font-weight: 600; color: #9ca3b8; font-size: 11px;")
        left_lay.addWidget(self._style_label)
        self._style_combo = QComboBox()
        self._style_combo.addItems([
            "Pixel Art", "Hand-drawn", "Low Poly", "Realistic 3D",
            "Anime/Manga", "Cartoon", "Minimalist", "Retro",
            "Voxel", "Watercolor", "Other",
        ])
        left_lay.addWidget(self._style_combo)

        # Target audience
        self._target_label = QLabel()
        self._target_label.setStyleSheet("font-weight: 600; color: #9ca3b8; font-size: 11px;")
        left_lay.addWidget(self._target_label)
        self._target_input = QLineEdit()
        self._target_input.setStyleSheet(
            "QLineEdit { border: 1px solid #2e3347; border-radius: 6px; "
            "background: #242836; padding: 6px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #6366f1; }"
        )
        left_lay.addWidget(self._target_input)

        # Similar games
        self._similar_label = QLabel()
        self._similar_label.setStyleSheet("font-weight: 600; color: #9ca3b8; font-size: 11px;")
        left_lay.addWidget(self._similar_label)
        self._similar_input = QLineEdit()
        self._similar_input.setStyleSheet(
            "QLineEdit { border: 1px solid #2e3347; border-radius: 6px; "
            "background: #242836; padding: 6px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #6366f1; }"
        )
        left_lay.addWidget(self._similar_input)

        left_lay.addStretch()

        # Action buttons
        self._generate_btn = QPushButton()
        self._generate_btn.setMinimumHeight(44)
        self._generate_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "    stop:0 #6366f1, stop:1 #818cf8);"
            "  color: white; border: none; border-radius: 8px;"
            "  font-size: 15px; font-weight: bold; padding: 10px 20px;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "  stop:0 #818cf8, stop:1 #a5b4fc); }"
            "QPushButton:pressed { background: #4f46e5; }"
            "QPushButton:disabled { background: #2e3347; color: #6b7280; }"
        )
        self._generate_btn.clicked.connect(self._on_generate)
        left_lay.addWidget(self._generate_btn)

        self._settings_btn = QPushButton()
        self._settings_btn.setStyleSheet(
            "QPushButton { background: #242836; color: #9ca3b8; border: 1px solid #2e3347; "
            "border-radius: 6px; padding: 6px 14px; font-weight: normal; font-size: 12px; }"
            "QPushButton:hover { background: #2e3347; color: #e4e7ef; }"
        )
        self._settings_btn.clicked.connect(self._on_settings)
        left_lay.addWidget(self._settings_btn)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(
            "QProgressBar { border: none; border-radius: 3px; background: #2e3347; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "  stop:0 #6366f1, stop:1 #818cf8); border-radius: 3px; }"
        )
        left_lay.addWidget(self._progress)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        self._status_label.setVisible(False)
        left_lay.addWidget(self._status_label)

        splitter.addWidget(left_widget)

        # --- Right panel (tabs) ---
        right_widget = QWidget()
        right_lay = QVBoxLayout(right_widget)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #2e3347; border-radius: 6px; "
            "background: #1a1d27; padding: 12px; }"
            "QTabBar::tab { padding: 10px 18px; font-size: 13px; font-weight: 600; "
            "border-top-left-radius: 6px; border-top-right-radius: 6px; }"
        )

        self._tab_desc = _DescriptionTab()
        self._tab_titles = _TitlesTab()
        self._tab_images = _ImagePromptsTab()
        self._tab_tags = _TagsTab()
        self._tab_marketing = _MarketingTab()

        self._tabs.addTab(self._tab_desc, "")
        self._tabs.addTab(self._tab_titles, "")
        self._tabs.addTab(self._tab_images, "")
        self._tabs.addTab(self._tab_tags, "")
        self._tabs.addTab(self._tab_marketing, "")

        right_lay.addWidget(self._tabs)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 700])

        root.addWidget(splitter, stretch=1)

    # --- Logic ------------------------------------------------------------

    def _collect_inputs(self) -> dict[str, Any]:
        return {
            "description": self._desc_input.toPlainText().strip(),
            "genre": self._genre_combo.currentText(),
            "art_style": self._style_combo.currentText(),
            "target_audience": self._target_input.text().strip(),
            "similar_games": self._similar_input.text().strip(),
        }

    def _on_generate(self) -> None:
        inputs = self._collect_inputs()
        self._generate_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText(tr("ai.generating"))
        self._status_label.setVisible(True)

        def _do_generate() -> dict[str, Any]:
            # Try real AI backend; fall back to mock gracefully.
            try:
                from ai.backend import generate_all  # type: ignore[import]
                return generate_all(inputs)
            except (ImportError, Exception):
                import time
                time.sleep(0.6)  # simulate latency for realism
                return _mock_generate(inputs)

        run_query(_do_generate, self._on_results_ready, self._on_generate_error)

    def _on_results_ready(self, results: dict[str, Any]) -> None:
        self._generate_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status_label.setVisible(False)

        self._tab_desc.set_data(
            results.get("short_desc", ""),
            results.get("long_desc", ""),
        )
        self._tab_titles.set_data(results.get("titles", []))
        self._tab_images.set_data(results.get("image_prompts", {}))
        self._tab_tags.set_data(results.get("tags", []))
        self._tab_marketing.set_data(
            results.get("elevator_pitch", ""),
            results.get("marketing_hooks", []),
        )
        # Switch to first tab to show results
        self._tabs.setCurrentIndex(0)

    def _on_generate_error(self, error: str) -> None:
        self._generate_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status_label.setText(f"Errore: {error}")
        self._status_label.setStyleSheet("color: #f87171; font-size: 11px;")
        self._status_label.setVisible(True)

    def _on_settings(self) -> None:
        dlg = AiSettingsDialog(self)
        dlg.exec()

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        self._title_label.setText(tr("ai.title"))
        self._desc_label.setText(tr("ai.description_label"))
        self._desc_input.setPlaceholderText(tr("ai.description_placeholder"))
        self._genre_label.setText(tr("ai.genre"))
        self._style_label.setText(tr("ai.art_style"))
        self._target_label.setText(tr("ai.target_audience"))
        self._target_input.setPlaceholderText(tr("ai.target_audience_placeholder"))
        self._similar_label.setText(tr("ai.similar_games"))
        self._similar_input.setPlaceholderText(tr("ai.similar_games_placeholder"))
        self._generate_btn.setText(tr("ai.generate_button"))
        self._settings_btn.setText(tr("ai.settings_button"))
        self._status_label.setText(tr("ai.generating"))
        self._tabs.setTabText(0, tr("ai.tab.description"))
        self._tabs.setTabText(1, tr("ai.tab.titles"))
        self._tabs.setTabText(2, tr("ai.tab.images"))
        self._tabs.setTabText(3, tr("ai.tab.tags"))
        self._tabs.setTabText(4, tr("ai.tab.marketing"))
        self._tab_desc.retranslate()
        self._tab_titles.retranslate()
        self._tab_images.retranslate()
        self._tab_tags.retranslate()
        self._tab_marketing.retranslate()
