"""Dialog di configurazione del provider AI per il Copilot.

Permette di scegliere il provider (OpenAI, OpenRouter, Anthropic, Custom),
inserire la chiave API, selezionare il modello, regolare temperatura e
max_tokens. Le impostazioni vengono salvate in ``config/.env``.
"""

from __future__ import annotations

import os
import pathlib

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.i18n import tr, translator


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------

_PROVIDERS: list[dict] = [
    {
        "name": "OpenAI",
        "key": "openai",
        "hint_it": "Ottieni la chiave su platform.openai.com/api-keys",
        "hint_en": "Get your key at platform.openai.com/api-keys",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "base_url": "https://api.openai.com/v1",
    },
    {
        "name": "OpenRouter",
        "key": "openrouter",
        "hint_it": "Ottieni la chiave su openrouter.ai/keys",
        "hint_en": "Get your key at openrouter.ai/keys",
        "models": [
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
            "meta-llama/llama-3.1-405b",
            "mistralai/mistral-large",
        ],
        "base_url": "https://openrouter.ai/api/v1",
    },
    {
        "name": "Anthropic",
        "key": "anthropic",
        "hint_it": "Ottieni la chiave su console.anthropic.com/keys",
        "hint_en": "Get your key at console.anthropic.com/keys",
        "models": ["claude-sonnet-4-5", "claude-haiku-3"],
        "base_url": "https://api.anthropic.com/v1",
    },
    {
        "name": "Custom",
        "key": "custom",
        "hint_it": "Inserisci il tuo server OpenAI-compatible (es. LM Studio, Ollama...)",
        "hint_en": "Enter your OpenAI-compatible server (e.g. LM Studio, Ollama...)",
        "models": [],
        "base_url": "",
    },
]


def _provider_by_key(key: str) -> dict:
    for p in _PROVIDERS:
        if p["key"] == key:
            return p
    return _PROVIDERS[0]


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env_path() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    # Walk up to project root (contains config/ dir).
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = parent / "config" / ".env"
        if candidate.parent.exists():
            return candidate
    return pathlib.Path("config") / ".env"


def _read_env() -> dict[str, str]:
    path = _env_path()
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _write_env(values: dict[str, str]) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing lines to preserve non-AI keys.
    existing: dict[str, str] = {}
    preserved_lines: list[str] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    preserved_lines.append(line.rstrip("\n"))
                    continue
                k, _, v = stripped.partition("=")
                k = k.strip()
                if k not in values:
                    preserved_lines.append(line.rstrip("\n"))
                    existing[k] = v.strip()

    with path.open("w", encoding="utf-8") as f:
        for line in preserved_lines:
            f.write(line + "\n")
        for k, v in values.items():
            f.write(f'{k}="{v}"\n')


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class AiSettingsDialog(QDialog):
    """Dialog di configurazione del provider AI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ai.settings.title"))
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()
        self._load_values()
        translator.subscribe(lambda _l: self.retranslate())
        self.retranslate()

    # --- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(20, 20, 20, 20)

        # Title
        self._title_lbl = QLabel()
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self._title_lbl.setFont(title_font)
        self._title_lbl.setStyleSheet("color: #a5b4fc;")
        root.addWidget(self._title_lbl)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2e3347;")
        root.addWidget(sep)

        # Provider group
        self._provider_group = QGroupBox()
        provider_lay = QFormLayout(self._provider_group)
        provider_lay.setSpacing(10)
        provider_lay.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._provider_lbl = QLabel()
        self._provider_combo = QComboBox()
        for p in _PROVIDERS:
            self._provider_combo.addItem(p["name"], p["key"])
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_lay.addRow(self._provider_lbl, self._provider_combo)

        # API key
        self._key_lbl = QLabel()
        key_row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("sk-...")
        self._show_key_btn = QPushButton("👁")
        self._show_key_btn.setFixedSize(32, 32)
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.setStyleSheet(
            "QPushButton { background: #2e3347; border: 1px solid #2e3347; "
            "border-radius: 4px; font-size: 14px; font-weight: normal; color: #9ca3b8; padding: 0; }"
            "QPushButton:hover { background: #3d4157; }"
            "QPushButton:checked { background: #6366f1; color: white; }"
        )
        self._show_key_btn.toggled.connect(
            lambda on: self._key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self._key_input)
        key_row.addWidget(self._show_key_btn)
        provider_lay.addRow(self._key_lbl, key_row)

        # Hint label
        self._hint_lbl = QLabel()
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.setStyleSheet(
            "color: #6b7280; font-size: 11px; font-style: italic;"
        )
        provider_lay.addRow("", self._hint_lbl)

        # Base URL (Custom only)
        self._url_lbl = QLabel()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://your-server.com/v1")
        provider_lay.addRow(self._url_lbl, self._url_input)

        root.addWidget(self._provider_group)

        # Model group
        self._model_group = QGroupBox()
        model_lay = QFormLayout(self._model_group)
        model_lay.setSpacing(10)
        model_lay.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._model_lbl = QLabel()
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        model_lay.addRow(self._model_lbl, self._model_combo)

        # Temperature
        self._temp_lbl = QLabel()
        temp_row = QHBoxLayout()
        self._temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._temp_slider.setRange(0, 100)
        self._temp_slider.setValue(70)
        self._temp_slider.setTickInterval(10)
        self._temp_value_lbl = QLabel("0.70")
        self._temp_value_lbl.setFixedWidth(36)
        self._temp_value_lbl.setStyleSheet("color: #a5b4fc; font-weight: 600;")
        self._temp_slider.valueChanged.connect(
            lambda v: self._temp_value_lbl.setText(f"{v / 100:.2f}")
        )
        temp_row.addWidget(self._temp_slider)
        temp_row.addWidget(self._temp_value_lbl)
        model_lay.addRow(self._temp_lbl, temp_row)

        # Max tokens
        self._tokens_lbl = QLabel()
        self._tokens_spin = QSpinBox()
        self._tokens_spin.setRange(512, 16384)
        self._tokens_spin.setValue(4096)
        self._tokens_spin.setSingleStep(512)
        self._tokens_spin.setStyleSheet(
            "QSpinBox { background: #242836; border: 1px solid #2e3347; "
            "border-radius: 4px; padding: 4px 8px; color: #e4e7ef; }"
            "QSpinBox:focus { border-color: #6366f1; }"
        )
        model_lay.addRow(self._tokens_lbl, self._tokens_spin)

        root.addWidget(self._model_group)

        # Test connection
        self._test_btn = QPushButton()
        self._test_btn.setStyleSheet(
            "QPushButton { background: #242836; color: #a5b4fc; border: 1px solid #6366f1; "
            "border-radius: 6px; padding: 8px 16px; font-weight: 600; }"
            "QPushButton:hover { background: #6366f1; color: white; }"
            "QPushButton:disabled { background: #1e2130; color: #4b5563; border-color: #2e3347; }"
        )
        self._test_btn.clicked.connect(self._on_test_connection)
        self._test_result_lbl = QLabel()
        self._test_result_lbl.setWordWrap(True)
        self._test_result_lbl.setVisible(False)
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_result_lbl, stretch=1)
        root.addLayout(test_row)

        # Save / Cancel buttons
        btn_box = QDialogButtonBox()
        self._save_btn = btn_box.addButton("", QDialogButtonBox.StandardButton.AcceptRole)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #6366f1; color: white; border: none; "
            "border-radius: 6px; padding: 8px 20px; font-weight: bold; }"
            "QPushButton:hover { background: #818cf8; }"
        )
        self._cancel_btn = btn_box.addButton("", QDialogButtonBox.StandardButton.RejectRole)
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: #242836; color: #9ca3b8; border: 1px solid #2e3347; "
            "border-radius: 6px; padding: 8px 20px; font-weight: normal; }"
            "QPushButton:hover { background: #2e3347; }"
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # --- Provider switching -----------------------------------------------

    def _on_provider_changed(self, _index: int) -> None:
        key = self._provider_combo.currentData()
        provider = _provider_by_key(key)
        is_custom = key == "custom"

        # Show/hide base URL row
        self._url_lbl.setVisible(is_custom)
        self._url_input.setVisible(is_custom)

        # Update hint
        lang = translator.language
        self._hint_lbl.setText(provider.get(f"hint_{lang}", provider.get("hint_en", "")))

        # Update model combo
        self._model_combo.clear()
        models = provider.get("models", [])
        self._model_combo.addItems(models)
        if not is_custom:
            self._url_input.setText(provider.get("base_url", ""))

    # --- Load / save values -----------------------------------------------

    def _load_values(self) -> None:
        env = _read_env()
        provider_key = env.get("AI_PROVIDER", "openai")
        idx = self._provider_combo.findData(provider_key)
        self._provider_combo.setCurrentIndex(max(0, idx))
        self._on_provider_changed(self._provider_combo.currentIndex())

        self._key_input.setText(env.get("AI_API_KEY", ""))
        url = env.get("AI_BASE_URL", "")
        if url:
            self._url_input.setText(url)

        model = env.get("AI_MODEL", "")
        if model:
            idx_m = self._model_combo.findText(model)
            if idx_m >= 0:
                self._model_combo.setCurrentIndex(idx_m)
            else:
                self._model_combo.setCurrentText(model)

        try:
            temp = float(env.get("AI_TEMPERATURE", "0.7"))
            self._temp_slider.setValue(int(temp * 100))
        except ValueError:
            pass

        try:
            tokens = int(env.get("AI_MAX_TOKENS", "4096"))
            self._tokens_spin.setValue(tokens)
        except ValueError:
            pass

    def _on_save(self) -> None:
        values = {
            "AI_PROVIDER": self._provider_combo.currentData() or "openai",
            "AI_API_KEY": self._key_input.text().strip(),
            "AI_BASE_URL": self._url_input.text().strip(),
            "AI_MODEL": self._model_combo.currentText().strip(),
            "AI_TEMPERATURE": f"{self._temp_slider.value() / 100:.2f}",
            "AI_MAX_TOKENS": str(self._tokens_spin.value()),
        }
        try:
            _write_env(values)
            self.accept()
        except Exception as exc:
            self._test_result_lbl.setText(f"Errore salvataggio: {exc}")
            self._test_result_lbl.setStyleSheet("color: #f87171;")
            self._test_result_lbl.setVisible(True)

    # --- Test connection --------------------------------------------------

    def _on_test_connection(self) -> None:
        self._test_btn.setEnabled(False)
        self._test_result_lbl.setVisible(False)

        from gui.workers import run_query

        provider_key = self._provider_combo.currentData()
        api_key = self._key_input.text().strip()
        base_url = self._url_input.text().strip()
        model = self._model_combo.currentText().strip()

        def _do_test():
            return _test_connection(
                provider=provider_key,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )

        run_query(_do_test, self._on_test_result, self._on_test_error)

    def _on_test_result(self, ok: bool) -> None:
        self._test_btn.setEnabled(True)
        if ok:
            self._test_result_lbl.setText(tr("ai.settings.test_success"))
            self._test_result_lbl.setStyleSheet("color: #22c55e; font-weight: 600;")
        else:
            self._test_result_lbl.setText(tr("ai.settings.test_fail"))
            self._test_result_lbl.setStyleSheet("color: #f87171; font-weight: 600;")
        self._test_result_lbl.setVisible(True)
        QTimer.singleShot(4000, lambda: self._test_result_lbl.setVisible(False))

    def _on_test_error(self, error: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_result_lbl.setText(f"{tr('ai.settings.test_fail')}: {error}")
        self._test_result_lbl.setStyleSheet("color: #f87171;")
        self._test_result_lbl.setVisible(True)

    # --- i18n -------------------------------------------------------------

    def retranslate(self) -> None:
        self.setWindowTitle(tr("ai.settings.title"))
        self._title_lbl.setText(tr("ai.settings.title"))
        self._provider_group.setTitle(tr("ai.settings.provider_group"))
        self._provider_lbl.setText(tr("ai.settings.provider"))
        self._key_lbl.setText(tr("ai.settings.api_key"))
        self._url_lbl.setText(tr("ai.settings.base_url"))
        self._model_group.setTitle(tr("ai.settings.model_group"))
        self._model_lbl.setText(tr("ai.settings.model"))
        self._temp_lbl.setText(tr("ai.settings.temperature"))
        self._tokens_lbl.setText(tr("ai.settings.max_tokens"))
        self._test_btn.setText(tr("ai.settings.test"))
        self._save_btn.setText(tr("ai.settings.save"))
        self._cancel_btn.setText(tr("ai.settings.cancel"))
        # Refresh provider hint in case language changed
        key = self._provider_combo.currentData()
        provider = _provider_by_key(key)
        lang = translator.language
        self._hint_lbl.setText(provider.get(f"hint_{lang}", provider.get("hint_en", "")))


# ---------------------------------------------------------------------------
# Test connection helper
# ---------------------------------------------------------------------------

def _test_connection(
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> bool:
    """Tenta una connessione al provider e restituisce True se ha successo."""
    try:
        import urllib.request
        import json as _json

        if provider in ("openai", "openrouter", "custom"):
            url = base_url.rstrip("/") + "/models"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.status == 200

        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            payload = _json.dumps({
                "model": model or "claude-haiku-3",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "ping"}],
            }).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("x-api-key", api_key)
            req.add_header("anthropic-version", "2023-06-01")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200

        return False
    except Exception:
        return False
