"""Piccoli widget di supporto condivisi (stato vuoto, card metrica)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from gui.i18n import tr


class EmptyState(QWidget):
    """Messaggio gentile di "nessun dato" (mai un crash su DB vuoto).

    Riceve chiavi i18n per titolo e corpo, cosi' e' traducibile a runtime.
    """

    def __init__(
        self,
        title_key: str = "empty.no_data.title",
        body_key: str = "empty.no_data.body",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title_key = title_key
        self._body_key = body_key

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title = QLabel()
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = self._title.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self._title.setFont(title_font)

        self._body = QLabel()
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)

        layout.addWidget(self._title)
        layout.addWidget(self._body)
        self.retranslate()

    def set_keys(self, title_key: str, body_key: str) -> None:
        """Cambia le chiavi mostrate e ri-traduce."""
        self._title_key = title_key
        self._body_key = body_key
        self.retranslate()

    def retranslate(self) -> None:
        """Riapplica i testi tradotti."""
        self._title.setText(tr(self._title_key))
        self._body.setText(tr(self._body_key))


class MetricCard(QFrame):
    """Card compatta con un valore grande e un'etichetta tradotta sotto."""

    def __init__(self, label_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label_key = label_key
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._value = QLabel("0")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_font = self._value.font()
        value_font.setPointSize(value_font.pointSize() + 8)
        value_font.setBold(True)
        self._value.setFont(value_font)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)

        layout.addWidget(self._value)
        layout.addWidget(self._label)
        self.retranslate()

    def set_value(self, value: object) -> None:
        """Aggiorna il valore numerico mostrato."""
        self._value.setText(str(value))
        # Nome accessibile: "<valore> <etichetta>".
        self.setAccessibleName(f"{value} {tr(self._label_key)}")

    def retranslate(self) -> None:
        """Riapplica l'etichetta tradotta."""
        self._label.setText(tr(self._label_key))
