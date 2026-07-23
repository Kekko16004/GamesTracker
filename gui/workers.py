"""Esecuzione di query pesanti fuori dal thread UI.

La GUI deve restare reattiva: le query sul DB girano in un ``QThreadPool``
via :class:`QueryRunnable`. Il risultato (o l'errore) torna al chiamante
tramite segnali Qt, che vengono consegnati sul thread UI.

Uso tipico::

    run_query(lambda: repo.list_games(min_quality_score=40),
              on_result=self._populate,
              on_error=self._show_error)
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _WorkerSignals(QObject):
    """Segnali emessi da un :class:`QueryRunnable`."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class QueryRunnable(QRunnable):
    """Esegue una funzione (tipicamente una query read-only) in un thread.

    La funzione non deve toccare widget: deve solo restituire dati. Il
    risultato viene emesso via ``signals.result``.
    """

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _WorkerSignals()

    def run(self) -> None:  # noqa: D401 - override QRunnable
        """Esegue la funzione catturando eventuali eccezioni."""
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - reportiamo il messaggio
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


def run_query(
    fn: Callable[[], Any],
    on_result: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
    pool: QThreadPool | None = None,
) -> QueryRunnable:
    """Esegue ``fn`` in un thread del pool e instrada risultato/errore.

    Restituisce il runnable (utile a mantenerne un riferimento se serve).
    """
    runnable = QueryRunnable(fn)
    runnable.signals.result.connect(on_result)
    if on_error is not None:
        runnable.signals.error.connect(on_error)
    (pool or QThreadPool.globalInstance()).start(runnable)
    return runnable
