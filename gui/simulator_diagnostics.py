"""Diagnostica del simulatore — "cosa manca e quanto vale sistemarlo".

Data una configurazione di input del simulatore, questo modulo produce una
valutazione **azionabile e ordinata**:

- ricalcola il quality score per ogni possibile miglioramento (approccio
  *controfattuale*: "se aggiungessi un trailer, lo score salirebbe di +X"),
- ordina i suggerimenti per impatto reale sul punteggio,
- allega consigli concreti e, dove utile, il confronto col benchmark di
  genere (es. "i cozy curati hanno ~10 screenshot; tu ne hai 3").

E' una **funzione pura**: prende gli ``SimulatorInputs`` e ritorna dati
serializzabili (codici i18n + parametri), nessuna dipendenza da PyQt6.

Il punto di forza e' che i delta sono *misurati*, non inventati: usiamo lo
stesso ``compute_quality_score`` del resto del sistema, quindi il consiglio
riflette esattamente la logica di scoring reale.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from analysis import genre_benchmarks
from gui.simulator_logic import SimulatorInputs, simulate_score


@dataclass
class Suggestion:
    """Un singolo suggerimento migliorativo con impatto misurato."""

    code: str                       # chiave i18n del testo consiglio
    delta: float                    # punti di score guadagnati (>=0)
    params: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"          # "critical" | "important" | "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "delta": round(self.delta, 1),
            "params": self.params,
            "severity": self.severity,
        }


@dataclass
class Diagnosis:
    """Esito completo della diagnostica del simulatore."""

    score: float                    # score reale con gli input attuali
    expected_score: Optional[float] # score "atteso al lancio" (recensioni stimate)
    expected_estimated: bool        # True se expected usa recensioni immaginate
    matched_genres: list[str]       # generi riconosciuti per il benchmark
    suggestions: list[Suggestion]   # ordinati per delta desc
    strengths: list[str]            # codici i18n dei punti di forza
    rating_code: str                # etichetta qualitativa i18n dello score

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "expected_score": (round(self.expected_score, 1)
                               if self.expected_score is not None else None),
            "expected_estimated": self.expected_estimated,
            "matched_genres": self.matched_genres,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "strengths": self.strengths,
            "rating_code": self.rating_code,
        }


# Soglia minima di delta per mostrare un suggerimento (evita rumore).
_MIN_DELTA = 0.3


def _score_of(inp: SimulatorInputs) -> float:
    """Score reale di una configurazione (scarta il breakdown)."""
    score, _ = simulate_score(inp)
    return score


def _rating_code(score: float) -> str:
    """Etichetta qualitativa i18n a partire dallo score 0-100."""
    if score >= 80:
        return "simulator.rating.excellent"
    if score >= 65:
        return "simulator.rating.good"
    if score >= 50:
        return "simulator.rating.fair"
    if score >= 40:
        return "simulator.rating.weak"
    return "simulator.rating.trash"


def _expected_at_launch(inp: SimulatorInputs) -> tuple[Optional[float], bool]:
    """Score 'atteso al lancio' quando le recensioni non sono inserite.

    Se il dev NON ha messo recensioni (gioco non ancora uscito), stimiamo un
    profilo tipico del genere e ricalcoliamo lo score con quelle recensioni
    immaginate. Ritorna ``(expected_score, estimated)``. Se le recensioni ci
    sono gia', ritorna ``(None, False)`` (lo score reale e' gia' completo).
    """
    if inp.review_count and inp.review_count > 0:
        return None, False
    est = genre_benchmarks.estimate_reviews(inp.genres, inp.tags)
    imagined = replace(
        inp,
        review_count=int(est["total_reviews"]),
        review_pct_positive=float(est["pct_positive"]),
    )
    return _score_of(imagined), True


def diagnose(inp: SimulatorInputs) -> Diagnosis:
    """Valuta gli input e produce la diagnosi ordinata per impatto.

    Per ogni leva migliorabile costruiamo una copia degli input con QUELLA
    leva sistemata (e nient'altro), ricalcoliamo lo score e misuriamo il
    delta. I suggerimenti con delta trascurabile vengono scartati.
    """
    base = _score_of(inp)
    bm, matched = genre_benchmarks.lookup(inp.genres, inp.tags)
    suggestions: list[Suggestion] = []
    strengths: list[str] = []

    def add(code: str, fixed: SimulatorInputs, severity: str,
            **params: Any) -> None:
        delta = _score_of(fixed) - base
        if delta >= _MIN_DELTA:
            suggestions.append(
                Suggestion(code=code, delta=delta, severity=severity,
                           params=params)
            )

    # --- Pagina store ---------------------------------------------------
    desc_len = len((inp.description or "").strip())
    if not inp.has_trailer:
        add("simulator.diag.add_trailer",
            replace(inp, has_trailer=True), "critical")
    else:
        strengths.append("simulator.strength.trailer")

    if inp.screenshot_count < bm.median_screenshots:
        add("simulator.diag.more_screenshots",
            replace(inp, screenshot_count=bm.median_screenshots),
            "important" if inp.screenshot_count < 3 else "info",
            current=inp.screenshot_count, target=bm.median_screenshots)
    elif inp.screenshot_count >= bm.median_screenshots:
        strengths.append("simulator.strength.screenshots")

    if not inp.has_header:
        add("simulator.diag.add_header",
            replace(inp, has_header=True), "important")

    if desc_len < bm.median_desc_length:
        # Portiamo la descrizione alla lunghezza tipica del genere per
        # misurare il delta (simuliamo con una stringa lunga quanto serve).
        target_len = bm.median_desc_length
        padded = replace(inp, description=(inp.description or "") +
                         " " * max(0, target_len - desc_len))
        add("simulator.diag.longer_description", padded,
            "important" if desc_len < 200 else "info",
            current=desc_len, target=target_len)
    else:
        strengths.append("simulator.strength.description")

    n_tags = len(inp.genres or []) + len(inp.tags or [])
    if n_tags < 5:
        # 5+ tag/generi sensati aiutano scopribilita' e la componente store.
        extra = ["tag%d" % i for i in range(5 - n_tags)]
        add("simulator.diag.more_tags",
            replace(inp, tags=list(inp.tags or []) + extra),
            "info", current=n_tags, target=5)

    # --- Cura -----------------------------------------------------------
    if not inp.has_demo:
        add("simulator.diag.add_demo",
            replace(inp, has_demo=True), "important")
    else:
        strengths.append("simulator.strength.demo")

    if not inp.has_official_site:
        add("simulator.diag.add_site",
            replace(inp, has_official_site=True), "info")

    # --- Social ---------------------------------------------------------
    if not inp.social_platforms:
        add("simulator.diag.add_social",
            replace(inp, social_platforms=2, social_post_count=max(
                inp.social_post_count, 10)),
            "info")

    # Ordina per impatto (delta) decrescente, poi per severita'.
    sev_rank = {"critical": 0, "important": 1, "info": 2}
    suggestions.sort(key=lambda s: (-s.delta, sev_rank.get(s.severity, 3)))

    expected, estimated = _expected_at_launch(inp)

    return Diagnosis(
        score=base,
        expected_score=expected,
        expected_estimated=estimated,
        matched_genres=matched,
        suggestions=suggestions,
        strengths=strengths,
        rating_code=_rating_code(base),
    )
