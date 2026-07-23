"""Lancio della raccolta dati come processo separato (``QProcess``).

Vincolo architetturale: la GUI NON fa chiamate di rete e NON importa i
client sorgente. La raccolta gira come processo separato
(``python run_collector.py --once``) che la GUI avvia e di cui osserva lo
stdout per aggiornare una barra di progresso.

Contratto di progresso: il processo stampa su stdout una riga per ogni
avanzamento nel formato::

    @@PROGRESS@@ {"phase": <str>, "status": <str>, "current": <int>,
                  "total": <int|null>, "message": <str>}

dove il marcatore e' ESATTAMENTE ``@@PROGRESS@@ `` (prefisso + spazio)
seguito da un JSON compatto su una sola riga. Le righe di log normali NON
hanno il prefisso e vengono ignorate ai fini della barra.

La funzione :func:`parse_progress_line` e' PURA (nessuna dipendenza da Qt):
questo permette di testare il parsing senza ``QApplication``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

# Marcatore di riga di progresso (prefisso + spazio, esatto).
PROGRESS_MARKER = "@@PROGRESS@@ "

# Chiavi attese in un evento di progresso, con relativi default.
_PROGRESS_DEFAULTS: dict[str, Any] = {
    "phase": "",
    "status": "",
    "current": 0,
    "total": None,
    "message": "",
}


def parse_progress_line(line: str) -> dict | None:
    """Analizza una singola riga di stdout del collector.

    Ritorna un dict normalizzato con le chiavi ``phase``, ``status``,
    ``current``, ``total``, ``message`` se la riga e' un evento di
    progresso valido; ``None`` altrimenti (riga di log normale, prefisso
    assente, o JSON malformato). Non solleva mai eccezioni.
    """
    if line is None:
        return None
    stripped = line.strip()
    if not stripped.startswith(PROGRESS_MARKER):
        return None
    payload = stripped[len(PROGRESS_MARKER):].strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    event = dict(_PROGRESS_DEFAULTS)
    event.update({k: data[k] for k in _PROGRESS_DEFAULTS if k in data})
    return event


def project_root() -> str:
    """Directory radice del progetto (dove risiede ``run_collector.py``)."""
    # gui/collect_runner.py -> gui/ -> <root>
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CollectRunner(QObject):
    """Incapsula il ``QProcess`` che esegue ``run_collector.py --once``.

    Emette segnali Qt man mano che il processo avanza. La logica di parsing
    incrementale bufferizza lo stdout per righe complete (``\\n``); ogni riga
    di progresso valida produce un ``progressChanged``.
    """

    #: (phase, status, current, total, message) — ``total`` puo' essere -1
    #: per indicare "sconosciuto" (barra indeterminata).
    progressChanged = pyqtSignal(str, str, int, int, str)
    #: Emesso a fine ciclo (status "done" o processo terminato con successo).
    finished = pyqtSignal(bool)
    #: Emesso su errore di avvio/esecuzione del processo (messaggio grezzo).
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._buffer = ""
        self._done_seen = False
        self._failed_emitted = False

    def is_running(self) -> bool:
        """True se un processo di raccolta e' attualmente in esecuzione."""
        return (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    def start(self, include_social: bool = True) -> None:
        """Avvia ``run_collector.py --once`` come processo separato.

        Usa lo stesso interprete Python della GUI (``sys.executable``) e la
        radice del progetto come working directory. Se ``include_social`` e'
        ``False`` passa ``--no-social``.
        """
        if self.is_running():
            return

        self._buffer = ""
        self._done_seen = False
        self._failed_emitted = False

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.setWorkingDirectory(project_root())
        proc.readyReadStandardOutput.connect(self._on_ready_read)
        proc.errorOccurred.connect(self._on_error)
        proc.finished.connect(self._on_finished)

        args = ["run_collector.py", "--once"]
        if not include_social:
            args.append("--no-social")

        self._process = proc
        proc.start(sys.executable, args)

    def stop(self) -> None:
        """Termina il processo se in esecuzione (best-effort, non bloccante)."""
        if self._process is not None and self.is_running():
            self._process.kill()

    # --- Parsing incrementale dello stdout --------------------------------

    def _on_ready_read(self) -> None:
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        event = parse_progress_line(line)
        if event is None:
            return
        total = event.get("total")
        total_int = int(total) if isinstance(total, (int, float)) else -1
        self.progressChanged.emit(
            str(event.get("phase", "")),
            str(event.get("status", "")),
            int(event.get("current") or 0),
            total_int,
            str(event.get("message", "")),
        )
        if event.get("status") == "done":
            self._done_seen = True

    # --- Terminazione -----------------------------------------------------

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        if self._failed_emitted:
            return
        self._failed_emitted = True
        msg = self._process.errorString() if self._process else "process error"
        self.failed.emit(msg)

    def _on_finished(self, exit_code: int, exit_status: object) -> None:
        # Svuota eventuale ultima riga rimasta nel buffer (senza \n finale).
        if self._buffer.strip():
            self._handle_line(self._buffer)
            self._buffer = ""
        if self._failed_emitted:
            return
        ok = self._done_seen or exit_code == 0
        self.finished.emit(ok)


__all__ = [
    "PROGRESS_MARKER",
    "parse_progress_line",
    "project_root",
    "CollectRunner",
]
