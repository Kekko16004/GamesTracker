"""Sistema di internazionalizzazione (i18n) IT/EN con switch a runtime.

Uso tipico::

    from gui.i18n import translator, tr

    translator.set_language("en")
    label.setText(tr("nav.dashboard"))

Il :class:`Translator` mantiene la lingua corrente come stato di modulo
(singleton ``translator``) e notifica gli osservatori quando la lingua
cambia, cosi' che le viste possano ri-tradursi senza riavvio.

Questo modulo NON dipende da PyQt6: e' testabile senza QApplication.
"""

from __future__ import annotations

from typing import Callable

from gui.i18n.strings import LANG_LABELS, STRINGS, SUPPORTED_LANGS

# Lingua di fallback se una chiave manca nella lingua richiesta.
_FALLBACK_LANG = "it"


class Translator:
    """Gestore della lingua corrente e risoluzione delle stringhe.

    Mantiene un elenco di callback (osservatori) invocati a ogni cambio
    lingua: le viste vi si registrano per aggiornare i propri testi.
    """

    def __init__(self, lang: str = "it") -> None:
        self._lang = self._normalize(lang)
        self._observers: list[Callable[[str], None]] = []

    @staticmethod
    def _normalize(lang: str | None) -> str:
        """Riporta la lingua a una di quelle supportate (default fallback)."""
        if lang is None:
            return _FALLBACK_LANG
        lang = lang.strip().lower()
        return lang if lang in SUPPORTED_LANGS else _FALLBACK_LANG

    @property
    def language(self) -> str:
        """Lingua correntemente attiva (codice ISO breve, es. ``it``)."""
        return self._lang

    def set_language(self, lang: str) -> None:
        """Imposta la lingua e notifica gli osservatori se e' cambiata."""
        new_lang = self._normalize(lang)
        if new_lang == self._lang:
            return
        self._lang = new_lang
        for observer in list(self._observers):
            observer(new_lang)

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        """Registra un osservatore del cambio lingua.

        Restituisce una funzione per annullare la registrazione.
        """
        self._observers.append(callback)

        def _unsubscribe() -> None:
            if callback in self._observers:
                self._observers.remove(callback)

        return _unsubscribe

    def tr(self, key: str, **kwargs: object) -> str:
        """Traduce ``key`` nella lingua corrente.

        Se la chiave non esiste restituisce la chiave stessa (utile per
        individuare stringhe mancanti in sviluppo). I ``kwargs`` vengono
        applicati come segnaposto ``str.format``.
        """
        entry = STRINGS.get(key)
        if entry is None:
            return key
        text = entry.get(self._lang) or entry.get(_FALLBACK_LANG) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text


# Singleton di modulo: unica istanza condivisa dall'intera GUI.
translator = Translator()


def tr(key: str, **kwargs: object) -> str:
    """Scorciatoia per :meth:`Translator.tr` sul translator condiviso."""
    return translator.tr(key, **kwargs)


def set_language(lang: str) -> None:
    """Scorciatoia per impostare la lingua sul translator condiviso."""
    translator.set_language(lang)


def available_languages() -> list[tuple[str, str]]:
    """Ritorna coppie ``(codice, etichetta)`` per popolare un selettore."""
    return [(code, LANG_LABELS.get(code, code)) for code in SUPPORTED_LANGS]


__all__ = [
    "Translator",
    "translator",
    "tr",
    "set_language",
    "available_languages",
    "SUPPORTED_LANGS",
]
