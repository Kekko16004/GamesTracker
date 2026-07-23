"""Vista Simulatore Quality Score.

Permette a un dev di inserire le info del proprio gioco (pagina store,
recensioni stimate, social, segnali di cura) e ottenere in tempo reale il
quality score 0-100 con:
- il breakdown per componente e le penalita';
- lo score "atteso al lancio" (recensioni immaginate dal genere) quando il
  gioco non e' ancora uscito;
- la diagnostica "cosa manca", ordinata per impatto misurato sul punteggio;
- la valutazione tecnica di copertina/header/screenshot caricati: dimensioni
  e proporzioni vs specifiche Steam PIU' la qualita' dei pixel (nitidezza,
  contrasto, colore, luminosita');
- la valutazione tecnica della descrizione (leggibilita', struttura,
  scopribilita' vs tag, densita' di fuffa, hook).

Nessun accesso al DB: usa solo logica pura (``gui.simulator_logic``,
``gui.simulator_diagnostics``, ``analysis.image_quality``,
``analysis.text_quality``, ``analysis.genre_benchmarks``). Le immagini vengono
lette con ``QImage``, i pixel estratti in un ``numpy.ndarray`` e passati ai
moduli puri; l'analisi vera resta pura e testabile senza Qt.
"""

from __future__ import annotations

import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from analysis import image_quality
from analysis import text_quality
from gui.i18n import tr, translator
from gui.simulator_diagnostics import diagnose
from gui.simulator_logic import SimulatorInputs, simulate_score


def _csv(text: str) -> list[str]:
    """Divide una stringa 'a, b, c' in lista pulita."""
    return [p.strip() for p in (text or "").split(",") if p.strip()]


def _qimage_to_rgb(img: QImage) -> np.ndarray | None:
    """Estrae i pixel di una QImage in un ndarray HxWx3 uint8 RGB.

    Ritorna None se l'immagine e' vuota/illeggibile. Restiamo dentro la GUI
    (l'unico punto che tocca Qt); il risultato e' un array puro che passiamo
    ai moduli di analisi testabili senza Qt.
    """
    if img is None or img.isNull():
        return None
    conv = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h = conv.width(), conv.height()
    if w <= 0 or h <= 0:
        return None
    ptr = conv.constBits()
    ptr.setsize(conv.sizeInBytes())
    stride = conv.bytesPerLine()
    arr = np.frombuffer(ptr, np.uint8).reshape((h, stride))
    return arr[:, : w * 3].reshape((h, w, 3)).copy()


class SimulatorView(QWidget):
    """Form + risultato + diagnostica del simulatore di quality score."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._live = True
        # Immagini caricate: lista di (kind, width, height, pixels|None).
        self._images: list[tuple] = []
        self._build_ui()
        translator.subscribe(lambda _l: self.retranslate())
        self.retranslate()
        self._recompute()

    # --- Costruzione UI ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._intro = QLabel()
        self._intro.setWordWrap(True)
        root.addWidget(self._intro)

        body = QHBoxLayout()
        root.addLayout(body, stretch=1)

        # Colonna sinistra: form dentro uno scroll (molti campi).
        form_container = QWidget()
        self._form = QFormLayout(form_container)
        self._build_fields()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_container)
        body.addWidget(scroll, stretch=3)

        # Colonna destra: risultato + diagnostica dentro uno scroll.
        result_container = QWidget()
        rc_layout = QVBoxLayout(result_container)
        rc_layout.addWidget(self._build_result_panel())
        rc_layout.addWidget(self._build_diagnosis_panel())
        rc_layout.addStretch(1)
        result_scroll = QScrollArea()
        result_scroll.setWidgetResizable(True)
        result_scroll.setWidget(result_container)
        body.addWidget(result_scroll, stretch=2)

    def _build_fields(self) -> None:
        # Store page.
        self._store_box = QGroupBox()
        store_form = QFormLayout(self._store_box)
        self._f_title = QLineEdit()
        self._f_desc = QTextEdit()
        self._f_desc.setFixedHeight(80)
        self._f_desc_hint = QLabel()
        self._f_desc_hint.setStyleSheet("color: gray; font-size: 11px;")
        self._f_desc_report = QLabel()
        self._f_desc_report.setWordWrap(True)
        self._f_desc_report.setTextFormat(Qt.TextFormat.RichText)
        self._f_shots = QSpinBox()
        self._f_shots.setRange(0, 100)
        self._f_trailer = QCheckBox()
        self._f_header = QCheckBox()
        self._f_genres = QLineEdit()
        self._f_tags = QLineEdit()
        self._lbl_title = QLabel()
        self._lbl_desc = QLabel()
        self._lbl_shots = QLabel()
        self._lbl_genres = QLabel()
        self._lbl_tags = QLabel()
        store_form.addRow(self._lbl_title, self._f_title)
        store_form.addRow(self._lbl_desc, self._f_desc)
        store_form.addRow("", self._f_desc_hint)
        store_form.addRow("", self._f_desc_report)
        store_form.addRow(self._lbl_shots, self._f_shots)
        store_form.addRow(self._f_trailer)
        store_form.addRow(self._f_header)
        store_form.addRow(self._lbl_genres, self._f_genres)
        store_form.addRow(self._lbl_tags, self._f_tags)
        self._form.addRow(self._store_box)

        # Immagini (copertina, header, screenshot).
        self._images_box = QGroupBox()
        img_form = QVBoxLayout(self._images_box)
        self._img_hint = QLabel()
        self._img_hint.setWordWrap(True)
        self._img_hint.setStyleSheet("color: gray; font-size: 11px;")
        img_form.addWidget(self._img_hint)
        btn_row = QHBoxLayout()
        self._btn_load_header = QPushButton()
        self._btn_load_cover = QPushButton()
        self._btn_load_shots = QPushButton()
        self._btn_load_header.clicked.connect(lambda: self._load_images("header"))
        self._btn_load_cover.clicked.connect(lambda: self._load_images("cover"))
        self._btn_load_shots.clicked.connect(
            lambda: self._load_images("screenshot"))
        btn_row.addWidget(self._btn_load_header)
        btn_row.addWidget(self._btn_load_cover)
        btn_row.addWidget(self._btn_load_shots)
        img_form.addLayout(btn_row)
        self._btn_clear_images = QPushButton()
        self._btn_clear_images.clicked.connect(self._clear_images)
        img_form.addWidget(self._btn_clear_images)
        self._img_report = QLabel()
        self._img_report.setWordWrap(True)
        self._img_report.setTextFormat(Qt.TextFormat.RichText)
        img_form.addWidget(self._img_report)
        self._form.addRow(self._images_box)

        # Reviews.
        self._reviews_box = QGroupBox()
        rev_form = QFormLayout(self._reviews_box)
        self._f_review_pct = QSpinBox()
        self._f_review_pct.setRange(0, 100)
        self._f_review_pct.setValue(0)
        self._f_review_count = QSpinBox()
        self._f_review_count.setRange(0, 10_000_000)
        self._f_review_hint = QLabel()
        self._f_review_hint.setStyleSheet("color: gray; font-size: 11px;")
        self._lbl_review_pct = QLabel()
        self._lbl_review_count = QLabel()
        rev_form.addRow(self._lbl_review_pct, self._f_review_pct)
        rev_form.addRow(self._lbl_review_count, self._f_review_count)
        rev_form.addRow("", self._f_review_hint)
        self._form.addRow(self._reviews_box)

        # Care.
        self._care_box = QGroupBox()
        care_form = QFormLayout(self._care_box)
        self._f_price = QDoubleSpinBox()
        self._f_price.setRange(0.0, 1000.0)
        self._f_price.setDecimals(2)
        self._f_free = QCheckBox()
        self._f_demo = QCheckBox()
        self._f_other = QCheckBox()
        self._f_site = QCheckBox()
        self._lbl_price = QLabel()
        care_form.addRow(self._lbl_price, self._f_price)
        care_form.addRow(self._f_free)
        care_form.addRow(self._f_demo)
        care_form.addRow(self._f_other)
        care_form.addRow(self._f_site)
        self._form.addRow(self._care_box)

        # Social (opzionale).
        self._social_box = QGroupBox()
        soc_form = QFormLayout(self._social_box)
        self._f_platforms = QSpinBox()
        self._f_platforms.setRange(0, 10)
        self._f_posts = QSpinBox()
        self._f_posts.setRange(0, 100_000)
        self._f_social_hint = QLabel()
        self._f_social_hint.setStyleSheet("color: gray; font-size: 11px;")
        self._lbl_platforms = QLabel()
        self._lbl_posts = QLabel()
        soc_form.addRow(self._lbl_platforms, self._f_platforms)
        soc_form.addRow(self._lbl_posts, self._f_posts)
        soc_form.addRow("", self._f_social_hint)
        self._form.addRow(self._social_box)

        # Pulsante calcola.
        self._btn = QPushButton()
        self._btn.clicked.connect(self._recompute)
        self._form.addRow(self._btn)

        # Ricalcolo live su ogni cambiamento.
        for w in (self._f_shots, self._f_review_pct, self._f_review_count,
                  self._f_platforms, self._f_posts):
            w.valueChanged.connect(self._on_changed)
        self._f_price.valueChanged.connect(self._on_changed)
        for c in (self._f_trailer, self._f_header, self._f_free, self._f_demo,
                  self._f_other, self._f_site):
            c.stateChanged.connect(self._on_changed)
        for le in (self._f_genres, self._f_tags):
            le.textChanged.connect(self._on_changed)
        self._f_desc.textChanged.connect(self._on_changed)

    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._score_caption = QLabel()
        self._score_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_value = QLabel("—")
        self._score_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_value.setStyleSheet("font-size: 48px; font-weight: bold;")
        self._score_rating = QLabel()
        self._score_rating.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_rating.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._score_caption)
        layout.addWidget(self._score_value)
        layout.addWidget(self._score_rating)

        # Score atteso al lancio (recensioni immaginate).
        self._expected_caption = QLabel()
        self._expected_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._expected_value = QLabel()
        self._expected_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._expected_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #2a7;")
        self._expected_hint = QLabel()
        self._expected_hint.setWordWrap(True)
        self._expected_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._expected_hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._expected_caption)
        layout.addWidget(self._expected_value)
        layout.addWidget(self._expected_hint)

        self._comp_caption = QLabel()
        layout.addWidget(self._comp_caption)
        self._comp_labels: dict[str, QLabel] = {}
        for key in ("store_page", "reviews", "social", "growth", "care"):
            lbl = QLabel()
            layout.addWidget(lbl)
            self._comp_labels[key] = lbl

        self._pen_caption = QLabel()
        layout.addWidget(self._pen_caption)
        self._pen_body = QLabel()
        self._pen_body.setWordWrap(True)
        layout.addWidget(self._pen_body)
        return panel

    def _build_diagnosis_panel(self) -> QWidget:
        box = QGroupBox()
        self._diag_box = box
        layout = QVBoxLayout(box)
        self._diag_intro = QLabel()
        self._diag_intro.setWordWrap(True)
        self._diag_intro.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._diag_intro)
        self._diag_body = QLabel()
        self._diag_body.setWordWrap(True)
        self._diag_body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._diag_body)
        # Punti di forza.
        self._strengths_caption = QLabel()
        self._strengths_caption.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._strengths_caption)
        self._strengths_body = QLabel()
        self._strengths_body.setWordWrap(True)
        self._strengths_body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._strengths_body)
        return box

    # --- Immagini ---------------------------------------------------------

    def _load_images(self, kind: str) -> None:
        """Apri un file dialog e aggiungi le immagini scelte come ``kind``."""
        multi = kind == "screenshot"
        flt = tr("simulator.images.dialog_filter")
        if multi:
            paths, _ = QFileDialog.getOpenFileNames(self, "", "", flt)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "", "", flt)
            paths = [path] if path else []
        for p in paths:
            if not p:
                continue
            img = QImage(p)
            w = img.width() if not img.isNull() else 0
            h = img.height() if not img.isNull() else 0
            pixels = _qimage_to_rgb(img)
            # Per header/cover teniamo solo l'ultima caricata (una sola serve).
            if not multi:
                self._images = [i for i in self._images if i[0] != kind]
            self._images.append((kind, w, h, pixels))
        self._sync_images_to_fields()
        self._recompute()

    def _clear_images(self) -> None:
        self._images = []
        self._sync_images_to_fields()
        self._recompute()

    def _sync_images_to_fields(self) -> None:
        """Riporta i conteggi derivati dalle immagini nei campi di scoring.

        Se il dev carica screenshot/header, quei valori alimentano lo score
        (e la diagnostica) invece di restare solo un report a parte.
        """
        report = image_quality.analyze_images(self._images)
        block = self._live
        self._live = False
        try:
            if report.screenshot_count:
                self._f_shots.setValue(
                    max(self._f_shots.value(), report.screenshot_count))
            if report.has_header:
                self._f_header.setChecked(True)
        finally:
            self._live = block
        self._render_image_report(report)

    def _render_image_report(self, report) -> None:
        """Mostra l'esito tecnico delle immagini caricate (RichText)."""
        if not report.verdicts:
            self._img_report.setText(
                f"<i>{tr('simulator.images.none')}</i>")
            return
        lines = []
        for v in report.verdicts:
            kind_name = tr(f"simulator.image.kind.{v.kind}")
            if v.ok:
                lines.append(
                    "✅ " + tr("simulator.images.item_ok",
                              kind=kind_name, w=v.width, h=v.height))
            else:
                issue = "; ".join(tr(f"simulator.image.{code}")
                                  for code in v.issues)
                icon = "⛔" if v.severity == "error" else "⚠️"
                color = "#c0392b" if v.severity == "error" else "#b8860b"
                lines.append(
                    f"<span style='color:{color}'>{icon} " +
                    tr("simulator.images.item_issue",
                       kind=kind_name, w=v.width, h=v.height, issue=issue) +
                    "</span>")
            # Metriche pixel (Livello A), se disponibili.
            if v.metrics is not None:
                m = v.metrics
                lines.append(
                    "<span style='color:gray; font-size:11px'>&nbsp;&nbsp;" +
                    tr("simulator.image.metrics",
                       sharp=round(m.sharpness, 0),
                       contrast=round(m.contrast * 100),
                       color=round(m.colorfulness, 0),
                       bright=round(m.brightness * 100)) +
                    "</span>")
        summary = tr("simulator.images.summary",
                     shots=report.screenshot_count,
                     header="✓" if report.has_header else "—",
                     cover="✓" if report.has_cover else "—")
        self._img_report.setText(
            f"<b>{summary}</b><br>" + "<br>".join(lines))

    # --- Ricalcolo --------------------------------------------------------

    def _on_changed(self, *_args) -> None:
        if self._live:
            self._recompute()

    def _collect_inputs(self) -> SimulatorInputs:
        return SimulatorInputs(
            title=self._f_title.text(),
            description=self._f_desc.toPlainText(),
            screenshot_count=self._f_shots.value(),
            has_trailer=self._f_trailer.isChecked(),
            has_header=self._f_header.isChecked(),
            genres=_csv(self._f_genres.text()),
            tags=_csv(self._f_tags.text()),
            price=self._f_price.value(),
            is_free=self._f_free.isChecked(),
            has_demo=self._f_demo.isChecked(),
            developer_other_games=self._f_other.isChecked(),
            has_official_site=self._f_site.isChecked(),
            review_pct_positive=float(self._f_review_pct.value()),
            review_count=self._f_review_count.value(),
            social_platforms=self._f_platforms.value(),
            social_post_count=self._f_posts.value(),
        )

    def _recompute(self) -> None:
        inp = self._collect_inputs()
        score, breakdown = simulate_score(inp)
        self._score_value.setText(f"{score:.1f}")

        weighted = breakdown.get("weighted", {})
        for key, lbl in self._comp_labels.items():
            name = tr(f"simulator.component.{key}")
            contrib = weighted.get(key)
            lbl.setText(f"{name}: {contrib:.1f}" if contrib is not None
                        else f"{name}: —")

        penalties = breakdown.get("penalties", [])
        factor = breakdown.get("penalty_factor", 1.0)
        if penalties:
            names = [tr(f"simulator.penalty.{p}") for p in penalties]
            body = "\n".join(f"• {n}" for n in names)
            body += "\n" + tr("simulator.result.penalty_factor",
                              value=round(factor, 2))
            if breakdown.get("flags", {}).get("hard_trash"):
                body += "\n" + tr("simulator.result.hard_trash")
            self._pen_body.setText(body)
        else:
            self._pen_body.setText(tr("simulator.result.no_penalties"))

        # Diagnostica + score atteso al lancio + rating.
        self._render_diagnosis(inp)
        # Qualita' tecnica della descrizione (Livello A).
        self._render_text_report(inp)

    def _render_text_report(self, inp: SimulatorInputs) -> None:
        """Mostra l'analisi tecnica della descrizione (RichText)."""
        tags = list(inp.genres) + list(inp.tags)
        v = text_quality.analyze_text(inp.description, tags)
        if v.metrics is None:
            # Nessun testo: mostra solo l'eventuale codice-issue (missing).
            if v.issues:
                issue = "; ".join(tr(f"simulator.text.{c}") for c in v.issues)
                self._f_desc_report.setText(
                    f"<span style='color:#c0392b'>⛔ {issue}</span>")
            else:
                self._f_desc_report.setText("")
            return
        m = v.metrics
        stats = tr("simulator.text.stats",
                   chars=m.char_count, words=m.word_count,
                   gulpease=round(m.gulpease, 0),
                   coverage=round(m.tag_coverage * 100))
        if v.issues:
            icon = "⛔" if v.severity == "error" else "⚠️"
            color = "#c0392b" if v.severity == "error" else "#b8860b"
            issue = "; ".join(tr(f"simulator.text.{c}") for c in v.issues)
            body = (f"<span style='color:gray'>{stats}</span><br>"
                    f"<span style='color:{color}'>{icon} {issue}</span>")
        else:
            body = (f"<span style='color:gray'>{stats}</span><br>"
                    f"<span style='color:#2a7'>✅ "
                    f"{tr('simulator.text.ok')}</span>")
        self._f_desc_report.setText(body)

    def _render_diagnosis(self, inp: SimulatorInputs) -> None:
        diag = diagnose(inp)

        # Rating qualitativo dello score reale.
        self._score_rating.setText(tr(diag.rating_code))

        # Score atteso al lancio (solo se recensioni non inserite).
        if diag.expected_score is not None:
            self._expected_caption.setVisible(True)
            self._expected_value.setVisible(True)
            self._expected_hint.setVisible(True)
            self._expected_value.setText(f"{diag.expected_score:.1f}")
            if diag.matched_genres:
                self._expected_hint.setText(tr(
                    "simulator.expected.hint",
                    genres=", ".join(diag.matched_genres)))
            else:
                self._expected_hint.setText(
                    tr("simulator.expected.hint_generic"))
        else:
            self._expected_caption.setVisible(False)
            self._expected_value.setVisible(False)
            self._expected_hint.setVisible(False)

        # Suggerimenti ordinati per impatto.
        if diag.suggestions:
            rows = []
            for s in diag.suggestions:
                color = {"critical": "#c0392b", "important": "#b8860b"}.get(
                    s.severity, "#2c3e50")
                delta = tr("simulator.diag.delta", value=round(s.delta, 1))
                text = tr(s.code, **s.params)
                rows.append(
                    f"<div style='margin-bottom:4px'>"
                    f"<b style='color:{color}'>{delta}</b> — {text}</div>")
            self._diag_body.setText("".join(rows))
        else:
            self._diag_body.setText(f"<i>{tr('simulator.diag.none')}</i>")

        # Punti di forza.
        if diag.strengths:
            items = " · ".join(tr(code) for code in diag.strengths)
            self._strengths_caption.setVisible(True)
            self._strengths_body.setVisible(True)
            self._strengths_body.setText(f"✅ {items}")
        else:
            self._strengths_caption.setVisible(False)
            self._strengths_body.setVisible(False)

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        self._intro.setText(tr("simulator.intro"))
        self._store_box.setTitle(tr("simulator.section.store"))
        self._images_box.setTitle(tr("simulator.section.images"))
        self._img_hint.setText(tr("simulator.images.hint"))
        self._btn_load_header.setText(tr("simulator.images.load_header"))
        self._btn_load_cover.setText(tr("simulator.images.load_cover"))
        self._btn_load_shots.setText(tr("simulator.images.load_screenshots"))
        self._btn_clear_images.setText(tr("simulator.images.clear"))
        self._reviews_box.setTitle(tr("simulator.section.reviews"))
        self._care_box.setTitle(tr("simulator.section.care"))
        self._social_box.setTitle(tr("simulator.section.social"))
        self._lbl_title.setText(tr("simulator.field.game_title"))
        self._lbl_desc.setText(tr("simulator.field.description"))
        self._f_desc_hint.setText(tr("simulator.field.description_hint"))
        self._lbl_shots.setText(tr("simulator.field.screenshots"))
        self._f_trailer.setText(tr("simulator.field.has_trailer"))
        self._f_header.setText(tr("simulator.field.has_header"))
        self._lbl_genres.setText(tr("simulator.field.genres"))
        self._lbl_tags.setText(tr("simulator.field.tags"))
        self._lbl_review_pct.setText(tr("simulator.field.review_pct"))
        self._lbl_review_count.setText(tr("simulator.field.review_count"))
        self._f_review_hint.setText(tr("simulator.field.review_hint"))
        self._lbl_price.setText(tr("simulator.field.price"))
        self._f_free.setText(tr("simulator.field.is_free"))
        self._f_demo.setText(tr("simulator.field.has_demo"))
        self._f_other.setText(tr("simulator.field.other_games"))
        self._f_site.setText(tr("simulator.field.official_site"))
        self._lbl_platforms.setText(tr("simulator.field.social_platforms"))
        self._lbl_posts.setText(tr("simulator.field.social_posts"))
        self._f_social_hint.setText(tr("simulator.field.optional_zero"))
        self._btn.setText(tr("simulator.calculate"))
        self._score_caption.setText(tr("simulator.result.score"))
        self._comp_caption.setText(tr("simulator.result.components"))
        self._pen_caption.setText(tr("simulator.result.penalties"))
        self._expected_caption.setText(tr("simulator.expected.caption"))
        self._diag_box.setTitle(tr("simulator.section.diagnosis"))
        self._diag_intro.setText(tr("simulator.diag.intro"))
        self._strengths_caption.setText(tr("simulator.strengths.caption"))
        # Ridisegna report immagini e diagnosi nella nuova lingua.
        self._render_image_report(image_quality.analyze_images(self._images))
        self._recompute()
