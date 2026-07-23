"""Test dell'analizzatore tecnico delle immagini (puro, no Qt)."""

from __future__ import annotations

import numpy as np

from analysis import image_quality as iq


def test_perfect_header_ok():
    v = iq.analyze_image("header", 460, 215)
    assert v.ok
    assert v.severity == "ok"
    assert v.issues == []


def test_header_too_small_flagged():
    v = iq.analyze_image("header", 200, 94)
    assert not v.ok
    assert "header_too_small" in v.issues
    assert v.severity == "error"


def test_header_wrong_ratio_flagged():
    v = iq.analyze_image("header", 600, 600)  # quadrata: ratio errato
    assert "header_ratio" in v.issues


def test_perfect_cover_ok():
    v = iq.analyze_image("cover", 600, 900)
    assert v.ok


def test_cover_ratio_wrong():
    v = iq.analyze_image("cover", 900, 900)
    assert "cover_ratio" in v.issues


def test_screenshot_recommended_ok():
    v = iq.analyze_image("screenshot", 1920, 1080)
    assert v.ok


def test_screenshot_below_recommended_is_warn():
    v = iq.analyze_image("screenshot", 1280, 720)
    assert v.severity == "warn"
    assert "shot_below_recommended" in v.issues


def test_screenshot_too_small_is_error():
    v = iq.analyze_image("screenshot", 640, 360)
    assert v.severity == "error"
    assert "shot_too_small" in v.issues


def test_unreadable_image():
    v = iq.analyze_image("header", 0, 0)
    assert "unreadable" in v.issues
    assert v.severity == "error"


def test_report_counts():
    report = iq.analyze_images([
        ("header", 460, 215),
        ("cover", 600, 900),
        ("screenshot", 1920, 1080),
        ("screenshot", 640, 360),  # errore
    ])
    assert report.has_header
    assert report.has_cover
    assert report.screenshot_count == 2
    assert report.error_count == 1


# --- Metriche pixel (Livello A) ------------------------------------------

def _rng(h, w, seed):
    """Immagine pseudo-casuale deterministica (no Math.random ban qui: e' test)."""
    state = np.random.RandomState(seed)
    return (state.rand(h, w, 3) * 255).astype("uint8")


def test_flat_gray_is_blurry_dark_flat_dull():
    gray = np.full((215, 460, 3), 20, dtype="uint8")
    v = iq.analyze_image_content("header", 460, 215, gray)
    assert v.metrics is not None
    assert "very_blurry" in v.issues
    assert "too_dark" in v.issues
    assert "low_contrast" in v.issues
    assert "dull_color" in v.issues
    assert v.severity == "warn"  # difetti pixel non superano warn


def test_rich_image_no_pixel_issues():
    rich = _rng(215, 460, seed=7)
    v = iq.analyze_image_content("header", 460, 215, rich)
    assert v.metrics is not None
    # rumore ricco: nitido, contrastato, colorato, luminanza media
    assert "very_blurry" not in v.issues
    assert "low_contrast" not in v.issues
    assert "dull_color" not in v.issues


def test_washed_out_bright_flagged():
    bright = np.full((215, 460, 3), 250, dtype="uint8")
    v = iq.analyze_image_content("header", 460, 215, bright)
    assert "washed_out" in v.issues


def test_metrics_are_deterministic():
    img = _rng(100, 100, seed=3)
    a = iq.measure(img).to_dict()
    b = iq.measure(img).to_dict()
    assert a == b


def test_content_without_pixels_matches_dimensional():
    with_none = iq.analyze_image_content("header", 460, 215, None)
    plain = iq.analyze_image("header", 460, 215)
    assert with_none.to_dict()["issues"] == plain.to_dict()["issues"]
    assert with_none.metrics is None


def test_dimensional_error_and_pixel_issue_coexist():
    # header troppo piccolo (error) + pixel scadenti (warn) -> resta error
    gray = np.full((100, 214, 3), 20, dtype="uint8")
    v = iq.analyze_image_content("header", 214, 100, gray)
    assert "header_too_small" in v.issues
    assert v.severity == "error"
    assert v.metrics is not None


def test_analyze_images_accepts_pixels():
    img = _rng(215, 460, seed=1)
    report = iq.analyze_images([
        ("header", 460, 215, img),
        ("cover", 600, 900),  # senza pixel: ok
    ])
    header_v = report.verdicts[0]
    assert header_v.metrics is not None
    assert report.verdicts[1].metrics is None


def test_colorfulness_gray_is_zero():
    gray = np.full((50, 50, 3), 128, dtype="uint8")
    assert iq.colorfulness(gray) == 0.0


def test_grayscale_and_rgba_inputs_accepted():
    gray2d = np.full((50, 50), 128, dtype="uint8")
    rgba = np.full((50, 50, 4), 128, dtype="uint8")
    assert iq.brightness(gray2d) > 0
    assert iq.brightness(rgba) > 0

