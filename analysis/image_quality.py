"""Analisi tecnica delle immagini della pagina store (PURA, no PyQt6).

Valuta gli asset visivi che il dev carica nel simulatore — copertina
(header capsule), immagine verticale (library/main capsule) e screenshot —
su due piani OGGETTIVI (mai il gusto estetico, che e' fuori scopo):

1. **Dimensioni e proporzioni** vs le specifiche pubbliche di Steam
   (risoluzione troppo bassa, aspect ratio sbagliato, scaling/cropping).
2. **Qualita' tecnica dei pixel** (Livello A): nitidezza (sfocatura),
   contrasto, vivacita' del colore (colorfulness), luminosita'. Sono
   difetti *misurabili* dai pixel — un banner sfocato, slavato o troppo
   scuro — non un giudizio artistico.

La GUI estrae i pixel con ``QImage`` e passa qui un ``numpy.ndarray`` HxWx3
(uint8, RGB) — questo modulo resta puro e testabile senza Qt. numpy e' gia'
una dipendenza (arriva con pandas).

Specifiche Steam usate come riferimento (pubbliche, 2026):
- header capsule:      460 x 215   (ratio ~2.14:1)
- main/library capsule (verticale): 600 x 900   (ratio 2:3)
- screenshot consigliato: 1920 x 1080 (16:9), minimo accettabile 1280x720
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np

# Specifiche di riferimento Steam.
HEADER_SPEC = (460, 215)
CAPSULE_VERTICAL_SPEC = (600, 900)
SCREENSHOT_RECOMMENDED = (1920, 1080)
SCREENSHOT_MIN = (1280, 720)

_HEADER_RATIO = HEADER_SPEC[0] / HEADER_SPEC[1]          # ~2.139
_VERTICAL_RATIO = CAPSULE_VERTICAL_SPEC[0] / CAPSULE_VERTICAL_SPEC[1]  # 0.667
_WIDE_RATIO = 16 / 9                                     # ~1.778

# Tolleranza relativa sull'aspect ratio prima di segnalare un problema.
_RATIO_TOL = 0.06


# --- Soglie qualita' pixel (Livello A) -----------------------------------
# Euristiche conservative: preferiamo NON segnalare piuttosto che dare falsi
# allarmi (un capsule minimalista puo' essere legittimamente "piatto"). Sono
# proxy tecnici, non un giudizio artistico.
SHARPNESS_BLURRY = 12.0        # varianza del Laplaciano sotto cui e' "molle"
SHARPNESS_VERY_BLURRY = 4.0    # sotto cui e' quasi certamente sfocata
CONTRAST_LOW = 0.10            # deviazione std luminanza (0-1) sotto cui piatta
BRIGHTNESS_DARK = 0.16         # luminanza media sotto cui troppo scura
BRIGHTNESS_WASHED = 0.90       # luminanza media sopra cui slavata/bruciata
COLORFULNESS_DULL = 8.0        # colorfulness Hasler-Susstrunk sotto cui spenta


@dataclass
class ImageMetrics:
    """Metriche tecniche misurate dai pixel di un'immagine."""

    sharpness: float           # varianza del Laplaciano (piu' alto = piu' nitido)
    contrast: float            # std luminanza normalizzata 0-1
    brightness: float          # luminanza media 0-1
    colorfulness: float        # metrica Hasler-Susstrunk (0 = grigio)

    def to_dict(self) -> dict[str, float]:
        return {
            "sharpness": round(self.sharpness, 2),
            "contrast": round(self.contrast, 4),
            "brightness": round(self.brightness, 4),
            "colorfulness": round(self.colorfulness, 2),
        }


@dataclass
class ImageVerdict:
    """Esito dell'analisi di una singola immagine."""

    kind: str                 # "header" | "cover" | "screenshot"
    width: int
    height: int
    ok: bool = True
    issues: list[str] = field(default_factory=list)   # codici i18n
    severity: str = "ok"      # "ok" | "warn" | "error"
    metrics: Optional[ImageMetrics] = None            # None se pixel non forniti

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "ok": self.ok,
            "issues": list(self.issues),
            "severity": self.severity,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


def _ratio_off(actual: float, target: float, tol: float = _RATIO_TOL) -> bool:
    """True se il ratio si discosta oltre ``tol`` (relativo) dal target."""
    if target <= 0:
        return False
    return abs(actual - target) / target > tol


def analyze_image(kind: str, width: int, height: int) -> ImageVerdict:
    """Analizza una singola immagine e ritorna il verdetto.

    ``kind`` in {"header", "cover", "screenshot"}. Emette codici-issue
    (chiavi i18n ``simulator.image.*``) invece di testo, cosi' la GUI li
    traduce IT/EN.
    """
    v = ImageVerdict(kind=kind, width=int(width or 0), height=int(height or 0))

    if v.width <= 0 or v.height <= 0:
        v.ok = False
        v.severity = "error"
        v.issues.append("unreadable")
        return v

    ratio = v.width / v.height

    if kind == "header":
        if v.width < HEADER_SPEC[0] or v.height < HEADER_SPEC[1]:
            v.issues.append("header_too_small")
            v.severity = "error"
        if _ratio_off(ratio, _HEADER_RATIO):
            v.issues.append("header_ratio")
            v.severity = "error" if v.severity == "error" else "warn"

    elif kind == "cover":
        if v.width < CAPSULE_VERTICAL_SPEC[0] or v.height < CAPSULE_VERTICAL_SPEC[1]:
            v.issues.append("cover_too_small")
            v.severity = "error"
        if _ratio_off(ratio, _VERTICAL_RATIO):
            v.issues.append("cover_ratio")
            v.severity = "error" if v.severity == "error" else "warn"

    elif kind == "screenshot":
        if v.width < SCREENSHOT_MIN[0] or v.height < SCREENSHOT_MIN[1]:
            v.issues.append("shot_too_small")
            v.severity = "error"
        elif v.width < SCREENSHOT_RECOMMENDED[0] or v.height < SCREENSHOT_RECOMMENDED[1]:
            v.issues.append("shot_below_recommended")
            v.severity = "warn"
        if _ratio_off(ratio, _WIDE_RATIO):
            v.issues.append("shot_ratio")
            v.severity = "error" if v.severity == "error" else "warn"

    else:  # tipo sconosciuto: non giudicare
        v.issues.append("unknown_kind")
        v.severity = "warn"

    v.ok = v.severity == "ok"
    return v


# --- Metriche pixel pure (Livello A) -------------------------------------
# Tutte lavorano su un ndarray HxWx3 uint8 RGB. Sono deterministiche e
# testabili senza Qt: la GUI estrae i pixel con QImage e passa qui l'array.

def _as_rgb(arr: Any) -> np.ndarray:
    """Normalizza l'input in float32 HxWx3 nel range 0-255.

    Accetta HxWx3 (RGB/BGR indistinto per le metriche usate) o HxWx4
    (scarta l'alpha) o HxW (grayscale -> replicato su 3 canali).
    """
    a = np.asarray(arr)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    elif a.ndim == 3 and a.shape[2] >= 4:
        a = a[:, :, :3]
    elif a.ndim != 3 or a.shape[2] != 3:
        raise ValueError("atteso array HxWx3 (o HxW / HxWx4)")
    return a.astype(np.float32)


def luminance(rgb: Any) -> np.ndarray:
    """Luminanza percettiva (Rec. 601) 0-1 come mappa HxW."""
    a = _as_rgb(rgb)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    return lum / 255.0


def sharpness(rgb: Any) -> float:
    """Nitidezza = varianza del Laplaciano della luminanza.

    Kernel Laplaciano 3x3 [[0,1,0],[1,-4,1],[0,1,0]] applicato con
    convoluzione manuale (niente scipy). Piu' alto = piu' nitido; valori
    bassi indicano sfocatura/upscaling.
    """
    lum = luminance(rgb) * 255.0
    if lum.shape[0] < 3 or lum.shape[1] < 3:
        return 0.0
    # Laplaciano 4-connesso sui pixel interni (vista, no padding).
    lap = (
        lum[:-2, 1:-1] + lum[2:, 1:-1] + lum[1:-1, :-2] + lum[1:-1, 2:]
        - 4.0 * lum[1:-1, 1:-1]
    )
    return float(lap.var())


def contrast(rgb: Any) -> float:
    """Contrasto = deviazione standard della luminanza (0-1)."""
    return float(luminance(rgb).std())


def brightness(rgb: Any) -> float:
    """Luminosita' = luminanza media (0-1)."""
    return float(luminance(rgb).mean())


def colorfulness(rgb: Any) -> float:
    """Vivacita' del colore secondo Hasler & Susstrunk (2003).

    M = sqrt(std_rg^2 + std_yb^2) + 0.3 * sqrt(mean_rg^2 + mean_yb^2)
    dove rg = R-G e yb = 0.5*(R+G)-B. 0 = grigio; ~40+ = molto colorato.
    """
    a = _as_rgb(rgb)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    std_root = np.sqrt(rg.std() ** 2 + yb.std() ** 2)
    mean_root = np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    return float(std_root + 0.3 * mean_root)


def measure(rgb: Any) -> ImageMetrics:
    """Calcola tutte le metriche pixel di un'immagine RGB."""
    return ImageMetrics(
        sharpness=sharpness(rgb),
        contrast=contrast(rgb),
        brightness=brightness(rgb),
        colorfulness=colorfulness(rgb),
    )


def _grade_metrics(m: ImageMetrics) -> tuple[list[str], str]:
    """Traduce le metriche in codici-issue conservativi + severita'.

    Solo difetti *tecnici* misurabili, mai gusto estetico. La severita'
    resta "warn": un'immagine tecnicamente povera non e' un blocco, e'
    un consiglio di miglioramento.
    """
    issues: list[str] = []
    if m.sharpness < SHARPNESS_VERY_BLURRY:
        issues.append("very_blurry")
    elif m.sharpness < SHARPNESS_BLURRY:
        issues.append("blurry")
    if m.brightness < BRIGHTNESS_DARK:
        issues.append("too_dark")
    elif m.brightness > BRIGHTNESS_WASHED:
        issues.append("washed_out")
    if m.contrast < CONTRAST_LOW:
        issues.append("low_contrast")
    if m.colorfulness < COLORFULNESS_DULL:
        issues.append("dull_color")
    severity = "warn" if issues else "ok"
    return issues, severity


def analyze_image_content(
    kind: str, width: int, height: int, pixels: Optional[Any] = None
) -> ImageVerdict:
    """Analisi completa: dimensioni/proporzioni + (se forniti) qualita' pixel.

    ``pixels`` e' un ndarray HxWx3 uint8 RGB (o None per la sola analisi
    dimensionale). Le due analisi sono indipendenti: un'immagine puo'
    avere dimensioni giuste ma essere sfocata, o viceversa.
    """
    v = analyze_image(kind, width, height)
    if pixels is None:
        return v
    try:
        m = measure(pixels)
    except (ValueError, TypeError):
        return v  # pixel non interpretabili: teniamo solo il verdetto dimensionale
    v.metrics = m
    pixel_issues, pixel_sev = _grade_metrics(m)
    v.issues.extend(pixel_issues)
    # La severita' peggiore vince, ma i difetti pixel non superano "warn".
    if pixel_sev == "warn" and v.severity == "ok":
        v.severity = "warn"
    v.ok = v.severity == "ok"
    return v


@dataclass
class ImageReport:
    """Sintesi dell'analisi di tutti gli asset caricati."""

    verdicts: list[ImageVerdict] = field(default_factory=list)
    has_header: bool = False
    has_cover: bool = False
    screenshot_count: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.verdicts if v.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for v in self.verdicts if v.severity == "warn")

    def to_dict(self) -> dict[str, object]:
        return {
            "verdicts": [v.to_dict() for v in self.verdicts],
            "has_header": self.has_header,
            "has_cover": self.has_cover,
            "screenshot_count": self.screenshot_count,
            "error_count": self.error_count,
            "warn_count": self.warn_count,
        }


def analyze_images(
    images: Iterable[tuple],
) -> ImageReport:
    """Analizza una lista di immagini.

    Ogni elemento e' ``(kind, width, height)`` oppure
    ``(kind, width, height, pixels)`` dove ``pixels`` e' un ndarray HxWx3
    uint8 RGB (o None). Quando i pixel sono forniti, il verdetto include
    anche le metriche di qualita' (nitidezza/contrasto/colore/luminosita').

    Ritorna un :class:`ImageReport` con i verdetti e i conteggi utili al
    simulatore (n. screenshot validi, presenza header/cover) per alimentare
    anche il quality score.
    """
    report = ImageReport()
    for item in images:
        kind, w, h = item[0], item[1], item[2]
        pixels = item[3] if len(item) > 3 else None
        v = analyze_image_content(kind, w, h, pixels)
        report.verdicts.append(v)
        if kind == "header":
            report.has_header = True
        elif kind == "cover":
            report.has_cover = True
        elif kind == "screenshot":
            report.screenshot_count += 1
    return report
