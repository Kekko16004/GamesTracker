"""Slider riutilizzabile per la soglia del quality score (0-100).

Emette il segnale ``thresholdChanged(int)`` quando l'utente rilascia lo
slider (non a ogni tick) per evitare query ripetute sul thread UI. Il
valore corrente e' sempre leggibile via :meth:`value`.

Tutte le stringhe passano da ``gui.i18n`` (nessun testo hardcoded) e il
widget si registra al translator per aggiornarsi al cambio lingua.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from gui.i18n import tr, translator


class QualityThresholdSlider(QWidget):
    """Slider orizzontale 0-100 con etichetta traducibile e valore live."""

    thresholdChanged = pyqtSignal(int)

    def __init__(self, initial: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui(initial)
        # Si ri-traduce automaticamente al cambio lingua.
        self._unsubscribe = translator.subscribe(lambda _lang: self.retranslate())

    def _build_ui(self, initial: int) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._caption = QLabel()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(100)
        self._slider.setValue(max(0, min(100, initial)))
        self._slider.setSingleStep(1)
        self._slider.setPageStep(5)
        self._slider.setTickInterval(10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        # Accessibilita': navigabile da tastiera e con nome accessibile.
        self._slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._value_label = QLabel()
        self._value_label.setMinimumWidth(110)

        # Aggiorna l'etichetta live mentre si trascina, ma emette il
        # segnale (che scatena le query) solo al rilascio.
        self._slider.valueChanged.connect(self._on_value_changed)
        self._slider.sliderReleased.connect(
            lambda: self.thresholdChanged.emit(self._slider.value())
        )

        layout.addWidget(self._caption)
        layout.addWidget(self._slider, stretch=1)
        layout.addWidget(self._value_label)

        self.retranslate()
        self._update_value_label(self._slider.value())

    def _on_value_changed(self, value: int) -> None:
        self._update_value_label(value)

    def _update_value_label(self, value: int) -> None:
        self._value_label.setText(tr("quality.value", value=value))

    def retranslate(self) -> None:
        """Riapplica le stringhe tradotte (chiamato al cambio lingua)."""
        self._caption.setText(tr("quality.threshold_label"))
        self._caption.setToolTip(tr("quality.threshold_tooltip"))
        self._slider.setToolTip(tr("quality.threshold_tooltip"))
        self._slider.setAccessibleName(tr("quality.threshold_label"))
        self._update_value_label(self._slider.value())

    def value(self) -> int:
        """Valore corrente della soglia (0-100)."""
        return self._slider.value()

    def set_value(self, value: int) -> None:
        """Imposta il valore della soglia senza emettere ``thresholdChanged``."""
        self._slider.setValue(max(0, min(100, value)))

    def closeEvent(self, event) -> None:  # noqa: ANN001
        """Annulla la sottoscrizione al translator alla chiusura."""
        self._unsubscribe()
        super().closeEvent(event)
