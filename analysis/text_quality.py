"""Analisi tecnica della descrizione della pagina store (PURA, no PyQt6).

Valuta la descrizione che il dev scrive nel simulatore su piani OGGETTIVI e
misurabili dal testo — mai il gusto o la creativita', che sono fuori scopo.
Un testo puo' essere ottimo pur venendo segnalato qui (es. volutamente breve):
questi sono *proxy tecnici* che aiutano la scopribilita' e la leggibilita',
non un giudizio editoriale.

Piani di analisi (Livello A, offline, deterministico):

1. **Lunghezza & struttura** — troppo corta (poco informativa) o assente;
   presenza di paragrafi/elenchi vs "muro di testo"; numero di frasi.
2. **Leggibilita' (indice Gulpease, calibrato sull'italiano)** — 0-100,
   piu' alto = piu' leggibile. Sotto ~40 il testo e' ostico per il lettore
   medio; utile per capsule/descrizioni brevi che devono "agganciare".
3. **Scopribilita' (allineamento testo <-> tag/genere)** — quanti dei
   tag/generi dichiarati compaiono anche nel testo. Steam pesa il testo per
   la ricerca: tag citati nella descrizione aiutano l'indicizzazione.
4. **Densita' di fuffa** — superlativi/marketing vuoto ("il miglior gioco
   mai creato", "rivoluzionario") che abbassano la credibilita'. Conteggio
   conservativo, solo pattern palesi.
5. **Hook** — la prima frase comunica cosa si fa nel gioco (verbo d'azione
   o genere), o e' generica/vuota? La prima riga e' quella che converte.

Modulo PURO: nessuna dipendenza da PyQt6, DB o rete. Emette codici-issue
i18n (``simulator.text.*``) tradotti dalla GUI IT/EN.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

# --- Soglie (conservative) -----------------------------------------------
DESC_MIN_CHARS = 120          # sotto: descrizione troppo scarna
DESC_SHORT_CHARS = 300        # sotto: corta, meglio ampliare
DESC_WALL_CHARS = 600         # oltre questa lunghezza senza a-capo = muro
GULPEASE_HARD = 40.0          # sotto: leggibilita' difficile
GULPEASE_VERY_HARD = 30.0     # sotto: molto difficile
FLUFF_DENSITY_HIGH = 0.015    # superlativi / parole totali sopra cui "fuffa"
TAG_COVERAGE_LOW = 0.34       # quota di tag citati nel testo sotto cui bassa

# Superlativi / marketing vuoto (pattern palesi, IT + EN). Solo termini che
# quasi sempre sono fuffa; evitiamo falsi positivi su parole legittime.
_FLUFF_PATTERNS = [
    r"miglior\w*", r"rivoluzionar\w*", r"incredibil\w*", r"straordinar\w*",
    r"mozzafiato", r"epic\w*", r"leggendar\w*", r"unico nel suo genere",
    r"mai vist\w*", r"assolutamente", r"perfett\w*", r"capolavoro",
    r"best\b", r"amazing", r"revolutionary", r"incredible", r"stunning",
    r"breathtaking", r"legendary", r"unforgettable", r"must[- ]?have",
    r"greatest", r"ultimate", r"masterpiece",
]
_FLUFF_RE = re.compile("|".join(_FLUFF_PATTERNS), re.IGNORECASE)

# Verbi/segnali d'azione che rendono un hook concreto (IT + EN, radici).
_ACTION_HINTS = [
    "esplor", "costru", "combatt", "sopravvi", "gestisc", "crea", "risolv",
    "scopri", "guida", "difend", "colleziona", "corri", "vola", "coltiva",
    "explore", "build", "fight", "surviv", "manage", "craft", "solve",
    "discover", "drive", "defend", "collect", "race", "farm", "control",
    "play as", "battle", "conquer",
]

# Stopword minime per il matching tag<->testo (evita match su articoli).
_STOP = {
    "the", "and", "of", "a", "an", "game", "di", "il", "la", "le", "lo",
    "un", "una", "e", "gioco", "con", "per", "in",
}


@dataclass
class TextMetrics:
    """Metriche misurate dal testo della descrizione."""

    char_count: int
    word_count: int
    sentence_count: int
    gulpease: float            # indice di leggibilita' IT 0-100
    tag_coverage: float        # quota tag/generi citati nel testo 0-1
    fluff_density: float       # superlativi / parole 0-1
    has_paragraphs: bool       # presenza di a-capo/elenchi
    hook_is_concrete: bool     # la prima frase dice cosa si fa

    def to_dict(self) -> dict[str, object]:
        return {
            "char_count": self.char_count,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "gulpease": round(self.gulpease, 1),
            "tag_coverage": round(self.tag_coverage, 3),
            "fluff_density": round(self.fluff_density, 4),
            "has_paragraphs": self.has_paragraphs,
            "hook_is_concrete": self.hook_is_concrete,
        }


@dataclass
class TextVerdict:
    """Esito dell'analisi della descrizione."""

    ok: bool = True
    issues: list[str] = field(default_factory=list)   # codici i18n
    severity: str = "ok"                              # "ok" | "warn" | "error"
    metrics: Optional[TextMetrics] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "issues": list(self.issues),
            "severity": self.severity,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


def _normalize(term: str) -> str:
    """Minuscolo, senza accenti, spazi compattati."""
    t = unicodedata.normalize("NFKD", term or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+(?:\s|$)", text)
    return [p.strip() for p in parts if p.strip()]


def _count_syllables_it(word: str) -> int:
    """Gruppi vocalici come proxy delle sillabe (non serve al Gulpease,
    tenuto per completezza/estensioni). Non usato dal Gulpease."""
    groups = re.findall(r"[aeiouy]+", word.lower())
    return max(1, len(groups))


def gulpease(text: str) -> float:
    """Indice Gulpease (leggibilita' italiano): 89 - 10*(lettere/parole)
    + 300*(frasi/parole). Clampato 0-100. Piu' alto = piu' leggibile.
    """
    letters = sum(1 for c in text if c.isalpha())
    words = re.findall(r"\w+", text)
    n_words = len(words)
    n_sent = max(1, len(_split_sentences(text)))
    if n_words == 0:
        return 0.0
    score = 89.0 - 10.0 * (letters / n_words) + 300.0 * (n_sent / n_words)
    return float(max(0.0, min(100.0, score)))


def _tag_coverage(text_norm: str, tags: Iterable[str]) -> tuple[float, list[str]]:
    """Quota di tag/generi citati nel testo + lista di quelli mancanti."""
    terms = []
    for t in tags:
        n = _normalize(t)
        if not n or n in _STOP:
            continue
        terms.append((t, n))
    if not terms:
        return 1.0, []  # nessun tag da coprire: non penalizzare
    missing: list[str] = []
    hit = 0
    for original, n in terms:
        # match su parola-radice: il tag o la sua prima parola compare nel testo
        head = n.split(" ")[0]
        if head and (head in text_norm):
            hit += 1
        else:
            missing.append(original)
    return hit / len(terms), missing


def _fluff_density(text: str, word_count: int) -> float:
    if word_count == 0:
        return 0.0
    return len(_FLUFF_RE.findall(text)) / word_count


def _hook_is_concrete(text: str) -> bool:
    """La prima frase comunica cosa si fa (verbo d'azione o abbastanza
    informativa)? Euristica: contiene un segnale d'azione, oppure e' una
    frase piena (>=6 parole) e non solo il titolo/uno slogan vuoto."""
    sentences = _split_sentences(text)
    if not sentences:
        return False
    first = _normalize(sentences[0])
    if any(h in first for h in _ACTION_HINTS):
        return True
    return len(first.split()) >= 6 and not _FLUFF_RE.search(sentences[0])


def measure_text(text: str, tags: Iterable[str] = ()) -> TextMetrics:
    """Calcola tutte le metriche testuali della descrizione."""
    text = text or ""
    words = re.findall(r"\w+", text)
    word_count = len(words)
    sentences = _split_sentences(text)
    coverage, _missing = _tag_coverage(_normalize(text), tags)
    return TextMetrics(
        char_count=len(text.strip()),
        word_count=word_count,
        sentence_count=len(sentences),
        gulpease=gulpease(text),
        tag_coverage=coverage,
        fluff_density=_fluff_density(text, word_count),
        has_paragraphs=("\n" in text) or bool(re.search(r"[•\-\*]\s", text)),
        hook_is_concrete=_hook_is_concrete(text),
    )


def analyze_text(text: str, tags: Iterable[str] = ()) -> TextVerdict:
    """Analizza la descrizione e ritorna un verdetto con codici-issue i18n.

    ``tags`` sono generi+tag dichiarati, usati per la scopribilita'. Le
    severita' restano "warn" (consigli), tranne l'assenza totale di testo
    che e' "error" perche' e' un requisito minimo di pagina.
    """
    v = TextVerdict()
    text = (text or "").strip()

    if not text:
        v.ok = False
        v.severity = "error"
        v.issues.append("missing")
        return v

    m = measure_text(text, tags)
    v.metrics = m

    if m.char_count < DESC_MIN_CHARS:
        v.issues.append("too_short")
        v.severity = "error"
    elif m.char_count < DESC_SHORT_CHARS:
        v.issues.append("short")

    # Muro di testo: lungo ma senza struttura visiva.
    if m.char_count >= DESC_WALL_CHARS and not m.has_paragraphs:
        v.issues.append("wall_of_text")

    if m.gulpease < GULPEASE_VERY_HARD:
        v.issues.append("very_hard_read")
    elif m.gulpease < GULPEASE_HARD:
        v.issues.append("hard_read")

    if m.tag_coverage < TAG_COVERAGE_LOW:
        v.issues.append("low_tag_coverage")

    if m.fluff_density > FLUFF_DENSITY_HIGH:
        v.issues.append("fluffy")

    if not m.hook_is_concrete:
        v.issues.append("weak_hook")

    # Consolidamento severita': "error" solo se gia' impostato; il resto warn.
    if v.severity != "error" and v.issues:
        v.severity = "warn"
    v.ok = v.severity == "ok"
    return v
