"""Confronto a percentili vs "top di genere" — Livello B (PURO, no PyQt6/DB).

Il Livello A dice se un asset ha *difetti tecnici oggettivi* (sfocato, corto,
illeggibile). Il Livello B risponde a una domanda diversa e relativa:

    "Rispetto ai giochi *curati* del mio genere, dove mi colloco?"

Non e' un verdetto assoluto: e' una **posizione a percentile** dentro una
distribuzione di riferimento. Serve a trasformare un consiglio vago ("metti
piu' screenshot") in uno misurato ("i top del tuo genere ne hanno ~12, tu 4:
sei nel 15° percentile").

IMPORTANTE — onesta' intellettuale:
- La distribuzione ideale e' calcolata dal corpus reale in ``game_snapshots``
  (idea #1). Finche' il corpus non e' abbastanza grande, si puo' costruire una
  distribuzione sintetica dai benchmark euristici di :mod:`genre_benchmarks`;
  in quel caso l'output DEVE essere marcato come stima (``estimated=True``).
- Il percentile e' relativo alla distribuzione fornita: garbage in, garbage
  out. Il chiamante e' responsabile di passare campioni sensati.

Questo modulo e' PURO: prende in ingresso liste di numeri (i valori del
corpus) e un valore da posizionare, e restituisce percentile + gap. Non legge
il DB direttamente — la costruzione del corpus vive nel layer analysis che ha
la sessione SQLAlchemy.

Modulo PURO: nessuna dipendenza da PyQt6, DB o rete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence


@dataclass
class PercentileResult:
    """Posizione di un valore dentro una distribuzione di riferimento."""

    value: float
    percentile: float          # 0-100: quota del corpus <= value
    median: float              # valore mediano del corpus (riferimento)
    p75: float                 # 75° percentile (soglia "top")
    sample_size: int
    estimated: bool = False    # True se il corpus e' sintetico/euristico

    @property
    def below_median(self) -> bool:
        return self.value < self.median

    @property
    def is_top(self) -> bool:
        """Nel quartile alto del genere."""
        return self.value >= self.p75

    def to_dict(self) -> dict[str, object]:
        return {
            "value": round(self.value, 3),
            "percentile": round(self.percentile, 1),
            "median": round(self.median, 3),
            "p75": round(self.p75, 3),
            "sample_size": self.sample_size,
            "estimated": self.estimated,
            "below_median": self.below_median,
            "is_top": self.is_top,
        }


def _sorted_floats(samples: Iterable[float]) -> list[float]:
    vals = sorted(float(x) for x in samples if x is not None)
    return vals


def quantile(samples: Sequence[float], q: float) -> float:
    """Quantile ``q`` (0-1) con interpolazione lineare (metodo 'linear').

    Implementazione pura (niente numpy) per restare leggeri e testabili.
    """
    vals = _sorted_floats(samples)
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    q = max(0.0, min(1.0, q))
    pos = q * (len(vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


def percentile_of(value: float, samples: Sequence[float]) -> float:
    """Percentile (0-100) di ``value`` nel corpus: quota di campioni <= value.

    Usa il metodo "weak" (<=), robusto ai duplicati; con corpus vuoto ritorna
    50 (neutro: nessuna informazione per collocare il valore).
    """
    vals = _sorted_floats(samples)
    n = len(vals)
    if n == 0:
        return 50.0
    below = sum(1 for x in vals if x <= value)
    return 100.0 * below / n


def position(
    value: float,
    samples: Sequence[float],
    *,
    estimated: bool = False,
) -> PercentileResult:
    """Colloca ``value`` nella distribuzione ``samples``.

    ``estimated`` marca il risultato come basato su corpus sintetico/euristico
    (deve propagarsi nell'output verso l'utente).
    """
    vals = _sorted_floats(samples)
    return PercentileResult(
        value=float(value),
        percentile=percentile_of(value, vals),
        median=quantile(vals, 0.5),
        p75=quantile(vals, 0.75),
        sample_size=len(vals),
        estimated=estimated,
    )


def synthetic_distribution(
    center: float,
    *,
    spread: float = 0.45,
    n: int = 25,
) -> list[float]:
    """Costruisce una distribuzione sintetica plausibile attorno a ``center``.

    Fallback pre-corpus: genera ``n`` valori deterministici (niente random —
    riproducibili e testabili) distribuiti simmetricamente attorno al centro
    con ampiezza relativa ``spread``. Rappresenta i progetti *curati* del
    genere quando non abbiamo ancora dati reali. L'output di chi la usa DEVE
    essere marcato ``estimated=True``.

    La forma e' una rampa lineare da ``center*(1-spread)`` a
    ``center*(1+spread)``: non pretende di essere la vera distribuzione, solo
    un ordine di grandezza con dispersione, sufficiente a dare un percentile
    indicativo.
    """
    if n <= 0 or center <= 0:
        return []
    lo = max(0.0, center * (1.0 - spread))
    hi = center * (1.0 + spread)
    if n == 1:
        return [center]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]
