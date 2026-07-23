"""Test dell'analizzatore tecnico della descrizione (puro, no Qt)."""

from __future__ import annotations

from analysis import text_quality as tq


def test_missing_description_is_error():
    v = tq.analyze_text("", ["RPG"])
    assert not v.ok
    assert v.severity == "error"
    assert "missing" in v.issues


def test_too_short_is_error():
    v = tq.analyze_text("Gioco corto.", ["RPG"])
    assert "too_short" in v.issues
    assert v.severity == "error"


def test_good_description_only_minor_warnings():
    text = (
        "Esplora un mondo aperto, costruisci la tua base e sopravvivi agli "
        "attacchi notturni. Un survival craft con grafica pixel curata e un "
        "ciclo giorno/notte che cambia le regole del gioco."
    )
    v = tq.analyze_text(text, ["Survival", "Crafting", "Pixel"])
    assert "missing" not in v.issues
    assert "too_short" not in v.issues
    assert v.metrics is not None
    assert v.metrics.hook_is_concrete


def test_fluff_detected():
    text = (
        "Il miglior gioco mai creato: un capolavoro assoluto, rivoluzionario, "
        "incredibile e straordinario, leggendario sotto ogni aspetto per tutti."
    )
    v = tq.analyze_text(text, ["RPG"])
    assert "fluffy" in v.issues
    assert v.metrics.fluff_density > tq.FLUFF_DENSITY_HIGH


def test_wall_of_text_flagged():
    long_line = ("parola " * 150).strip()  # oltre soglia, senza a-capo
    v = tq.analyze_text(long_line, [])
    assert "wall_of_text" in v.issues
    assert not v.metrics.has_paragraphs


def test_paragraphs_not_wall():
    text = ("Prima riga descrittiva del gioco.\n" * 20)
    v = tq.analyze_text(text, [])
    assert "wall_of_text" not in v.issues
    assert v.metrics.has_paragraphs


def test_tag_coverage_low_when_tags_absent_from_text():
    text = (
        "Un'avventura rilassante tra le nuvole, con musica delicata e un "
        "ritmo lento pensato per staccare la testa dopo una giornata lunga."
    )
    v = tq.analyze_text(text, ["Horror", "Zombie", "Shooter"])
    assert "low_tag_coverage" in v.issues
    assert v.metrics.tag_coverage < tq.TAG_COVERAGE_LOW


def test_tag_coverage_high_when_tags_present():
    text = (
        "Uno shooter horror con zombie ovunque: spara, sopravvivi e "
        "difenditi nella notte piu' lunga della tua carriera da survivor."
    )
    v = tq.analyze_text(text, ["Horror", "Zombie", "Shooter"])
    assert "low_tag_coverage" not in v.issues
    assert v.metrics.tag_coverage >= tq.TAG_COVERAGE_LOW


def test_gulpease_range():
    g = tq.gulpease("Frase semplice. Corta. Chiara.")
    assert 0.0 <= g <= 100.0


def test_no_tags_does_not_penalize_coverage():
    text = "Una descrizione onesta e sufficientemente lunga per non essere corta davvero."
    v = tq.analyze_text(text, [])
    assert "low_tag_coverage" not in v.issues
