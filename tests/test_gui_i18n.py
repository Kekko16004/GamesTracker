"""Test del sistema i18n (``gui.i18n``). Non richiede PyQt6."""

from __future__ import annotations

from gui.i18n import Translator, available_languages
from gui.i18n.strings import STRINGS, SUPPORTED_LANGS


def test_all_keys_have_all_languages():
    """Ogni chiave deve avere una traduzione in tutte le lingue supportate."""
    for key, entry in STRINGS.items():
        for lang in SUPPORTED_LANGS:
            assert lang in entry, f"chiave '{key}' senza lingua '{lang}'"
            assert entry[lang].strip(), f"chiave '{key}' vuota per '{lang}'"


def test_translation_switch():
    t = Translator("it")
    assert t.tr("nav.dashboard") == "Dashboard"
    assert t.tr("common.platform") == "Piattaforma"
    t.set_language("en")
    assert t.tr("common.platform") == "Platform"


def test_placeholders():
    t = Translator("it")
    assert t.tr("quality.value", value=40) == "Soglia: 40"
    t.set_language("en")
    assert t.tr("quality.value", value=40) == "Threshold: 40"


def test_missing_key_returns_key():
    t = Translator("it")
    assert t.tr("does.not.exist") == "does.not.exist"


def test_invalid_language_falls_back():
    t = Translator("de")  # non supportata -> fallback it
    assert t.language == "it"
    t.set_language("fr")
    assert t.language == "it"


def test_observer_notified_on_change():
    t = Translator("it")
    seen: list[str] = []
    unsub = t.subscribe(lambda lang: seen.append(lang))
    t.set_language("en")
    assert seen == ["en"]
    # Nessuna notifica se la lingua non cambia.
    t.set_language("en")
    assert seen == ["en"]
    unsub()
    t.set_language("it")
    assert seen == ["en"]


def test_available_languages():
    langs = dict(available_languages())
    assert langs["it"] == "Italiano"
    assert langs["en"] == "English"
