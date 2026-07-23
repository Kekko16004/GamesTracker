"""Benchmark per genere — profili tipici di un indie recente (EURISTICI).

Questo modulo fornisce **stime di riferimento** per genere/tag usate dal
simulatore di quality score in due modi:

1. **Recensioni immaginate** — se il dev non inserisce le recensioni (gioco
   non ancora uscito), stimiamo un profilo plausibile (numero recensioni a
   ~1 mese dal lancio e % positive) *tipico di quel genere*, cosi' da
   mostrare uno scenario "atteso al lancio" accanto al punteggio reale.
2. **Norme di pagina store** — quanti screenshot, se ci si aspetta un
   trailer, lunghezza descrizione tipica dei progetti curati del genere,
   per dare consigli mirati ("i roguelike curati hanno ~12 screenshot").

IMPORTANTE — onesta' intellettuale (playbook §regola d'oro):
questi NON sono percentili calcolati su un corpus. Sono **stime di dominio**
ragionevoli per un indie "mediamente riuscito" ~1 mese dopo il lancio.
Servono a dare un ordine di grandezza e consigli qualitativi, non un verdetto
numerico preciso. Quando il corpus reale sara' abbastanza grande, la fonte di
verita' diventera' l'idea #1 (benchmark a percentili su ``game_snapshots``);
questo modulo resta come fallback pre-corpus. Ogni consumatore deve marcare i
valori come "stima" nell'output verso l'utente.

Modulo PURO: nessuna dipendenza da PyQt6, DB o rete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class GenreBenchmark:
    """Profilo di riferimento (stimato) per un genere indie recente."""

    median_review_count: int
    """Numero recensioni tipico ~1 mese dopo il lancio (indie 'riuscito')."""
    pct_positive: float
    """% recensioni positive tipica del genere (0-100)."""
    median_screenshots: int
    """Numero di screenshot dei progetti curati del genere."""
    trailer_expected: bool
    """Se il genere si aspetta praticamente sempre un trailer."""
    median_desc_length: int
    """Lunghezza descrizione tipica (caratteri) di una scheda curata."""
    note: str = ""
    """Nota di dominio breve (mostrabile come contesto)."""


# --- Tabella euristica per genere/tag ------------------------------------
# Chiavi in minuscolo. Valori stimati per un indie "mediamente riuscito"
# ~1 mese dal lancio. Le % positive riflettono le medie note per genere
# (i cozy/puzzle tendono piu' alte, i competitivi/early-access piu' basse).
GENRE_BENCHMARKS: dict[str, GenreBenchmark] = {
    "roguelike": GenreBenchmark(1200, 92.0, 12, True, 1400,
        "Community forte; la profondita' sistemica premia le recensioni positive."),
    "roguelite": GenreBenchmark(1200, 92.0, 12, True, 1400,
        "Come i roguelike: la rigiocabilita' sostiene volume e % positive."),
    "metroidvania": GenreBenchmark(800, 91.0, 12, True, 1300,
        "Genere esigente sull'estetica: trailer e screenshot contano molto."),
    "deckbuilder": GenreBenchmark(900, 90.0, 10, True, 1300,
        "Nicchia appassionata; screenshot che mostrano sinergie di carte."),
    "card game": GenreBenchmark(700, 88.0, 10, True, 1200, ""),
    "horror": GenreBenchmark(600, 85.0, 10, True, 1100,
        "Molto guidato da streamer/YouTube; il trailer e' decisivo."),
    "cozy": GenreBenchmark(500, 94.0, 10, True, 1100,
        "Pubblico caloroso, % positive alta; estetica della capsule cruciale."),
    "farming sim": GenreBenchmark(600, 92.0, 10, True, 1200, ""),
    "life sim": GenreBenchmark(500, 90.0, 10, True, 1100, ""),
    "simulation": GenreBenchmark(500, 88.0, 10, True, 1200, ""),
    "city builder": GenreBenchmark(700, 89.0, 12, True, 1400, ""),
    "management": GenreBenchmark(600, 88.0, 10, True, 1300, ""),
    "puzzle": GenreBenchmark(350, 93.0, 8, True, 900,
        "Volumi piu' bassi ma % positive alta; GIF/clip dei meccanismi aiutano."),
    "platformer": GenreBenchmark(450, 90.0, 10, True, 1000, ""),
    "visual novel": GenreBenchmark(300, 92.0, 8, True, 1200,
        "Nicchia; la descrizione (storia, personaggi) pesa piu' del trailer."),
    "rpg": GenreBenchmark(900, 89.0, 12, True, 1600,
        "Descrizione lunga attesa: sistemi, mondo, build."),
    "jrpg": GenreBenchmark(700, 90.0, 12, True, 1500, ""),
    "strategy": GenreBenchmark(700, 88.0, 12, True, 1500, ""),
    "tower defense": GenreBenchmark(500, 89.0, 10, True, 1100, ""),
    "survival": GenreBenchmark(1500, 82.0, 12, True, 1400,
        "Spesso Early Access: volumi alti ma % positive piu' bassa all'inizio."),
    "sandbox": GenreBenchmark(1000, 84.0, 12, True, 1300, ""),
    "shooter": GenreBenchmark(1000, 84.0, 12, True, 1200, ""),
    "action": GenreBenchmark(700, 86.0, 12, True, 1200, ""),
    "adventure": GenreBenchmark(500, 89.0, 10, True, 1200, ""),
    "point & click": GenreBenchmark(350, 91.0, 8, True, 1100, ""),
    "racing": GenreBenchmark(500, 85.0, 10, True, 1000, ""),
    "sports": GenreBenchmark(400, 82.0, 10, True, 1000, ""),
    "fighting": GenreBenchmark(500, 84.0, 10, True, 1000, ""),
    "rhythm": GenreBenchmark(400, 92.0, 8, True, 900, ""),
    "casual": GenreBenchmark(300, 88.0, 8, True, 800, ""),
    "party": GenreBenchmark(400, 88.0, 10, True, 900, ""),
    "idle": GenreBenchmark(600, 86.0, 8, True, 800, ""),
    "open world": GenreBenchmark(1000, 85.0, 14, True, 1600, ""),
    "stealth": GenreBenchmark(450, 88.0, 10, True, 1100, ""),
    "tactical": GenreBenchmark(600, 89.0, 12, True, 1400, ""),
    "sim": GenreBenchmark(500, 88.0, 10, True, 1200, ""),
}

# Sinonimi -> chiave canonica nella tabella.
_ALIASES: dict[str, str] = {
    "rogue-like": "roguelike",
    "rogue-lite": "roguelite",
    "roguelikes": "roguelike",
    "deck building": "deckbuilder",
    "deck builder": "deckbuilder",
    "deck-building": "deckbuilder",
    "card battler": "card game",
    "collectible card game": "card game",
    "farming": "farming sim",
    "farm sim": "farming sim",
    "life simulation": "life sim",
    "colony sim": "management",
    "cozy game": "cozy",
    "wholesome": "cozy",
    "relaxing": "cozy",
    "psychological horror": "horror",
    "survival horror": "horror",
    "jrpgs": "jrpg",
    "action rpg": "rpg",
    "arpg": "rpg",
    "crpg": "rpg",
    "turn-based strategy": "strategy",
    "real-time strategy": "strategy",
    "rts": "strategy",
    "4x": "strategy",
    "grand strategy": "strategy",
    "auto battler": "deckbuilder",
    "first-person shooter": "shooter",
    "fps": "shooter",
    "third-person shooter": "shooter",
    "twin stick shooter": "shooter",
    "bullet hell": "shooter",
    "hack and slash": "action",
    "beat 'em up": "action",
    "2d platformer": "platformer",
    "3d platformer": "platformer",
    "precision platformer": "platformer",
    "point and click": "point & click",
    "point-and-click": "point & click",
    "walking simulator": "adventure",
    "narrative": "adventure",
    "story rich": "adventure",
    "interactive fiction": "visual novel",
    "dating sim": "visual novel",
    "crafting": "survival",
    "base building": "survival",
    "building": "city builder",
    "colony": "management",
    "tycoon": "management",
    "business": "management",
    "automation": "management",
    "puzzle platformer": "puzzle",
    "logic": "puzzle",
    "match 3": "puzzle",
    "match-3": "puzzle",
    "clicker": "idle",
    "incremental": "idle",
    "driving": "racing",
    "kart racing": "racing",
    "soulslike": "action",
    "souls-like": "action",
    "arena shooter": "shooter",
}

# Default generico quando nessun genere/tag e' riconosciuto.
DEFAULT_BENCHMARK = GenreBenchmark(
    median_review_count=400,
    pct_positive=87.0,
    median_screenshots=8,
    trailer_expected=True,
    median_desc_length=1000,
    note="Stima generica indie (genere non riconosciuto).",
)


def _normalize(term: str) -> Optional[str]:
    """Normalizza un genere/tag alla chiave canonica, o ``None``."""
    if not term:
        return None
    key = term.strip().lower()
    if key in GENRE_BENCHMARKS:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    # Match parziale: "Action Roguelike" -> "roguelike".
    for canonical in GENRE_BENCHMARKS:
        if canonical in key:
            return canonical
    for alias, canonical in _ALIASES.items():
        if alias in key:
            return canonical
    return None


def matched_genres(
    genres: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
) -> list[str]:
    """Ritorna le chiavi canoniche riconosciute da generi+tag (ordine, dedup)."""
    seen: list[str] = []
    for term in list(genres or []) + list(tags or []):
        canonical = _normalize(term)
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen


def lookup(
    genres: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
) -> tuple[GenreBenchmark, list[str]]:
    """Trova il benchmark di riferimento per un gioco.

    Se piu' generi/tag combaciano, media i campi numerici (piu' robusto di
    scegliere uno solo). Ritorna ``(benchmark, matched_keys)``; se nessuna
    corrispondenza, ``(DEFAULT_BENCHMARK, [])``.
    """
    keys = matched_genres(genres, tags)
    if not keys:
        return DEFAULT_BENCHMARK, []

    bms = [GENRE_BENCHMARKS[k] for k in keys]
    n = len(bms)
    avg = GenreBenchmark(
        median_review_count=round(sum(b.median_review_count for b in bms) / n),
        pct_positive=round(sum(b.pct_positive for b in bms) / n, 1),
        median_screenshots=round(sum(b.median_screenshots for b in bms) / n),
        trailer_expected=any(b.trailer_expected for b in bms),
        median_desc_length=round(sum(b.median_desc_length for b in bms) / n),
        note=next((b.note for b in bms if b.note), ""),
    )
    return avg, keys


def estimate_reviews(
    genres: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
) -> dict[str, object]:
    """Stima un profilo recensioni 'atteso al lancio' per il genere.

    Ritorna un dict compatibile con ``compute_quality_score`` (chiavi
    ``total_reviews``/``total_positive``/``total_negative``) piu' i metadati
    ``estimated=True`` e ``matched`` (generi riconosciuti) per l'onesta'
    verso l'utente. NON e' una predizione: e' un ordine di grandezza tipico.
    """
    bm, keys = lookup(genres, tags)
    total = bm.median_review_count
    positive = round(total * bm.pct_positive / 100.0)
    return {
        "total_reviews": total,
        "total_positive": positive,
        "total_negative": total - positive,
        "review_score_desc": None,
        "estimated": True,
        "matched": keys,
        "pct_positive": bm.pct_positive,
    }
