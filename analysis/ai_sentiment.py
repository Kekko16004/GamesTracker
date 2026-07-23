"""Classificatore euristico di sentiment per recensioni Steam.

Nessuna API esterna: classificazione locale basata su keyword dictionary
e regex. Ogni recensione viene classificata in una o piu' categorie
(multi-label), con un confidence score per categoria.

Categorie supportate:
- ``bug_report``        — segnalazioni di bug, crash, errori tecnici
- ``performance_issue`` — problemi di performance (FPS, lag, stuttering)
- ``praise``            — apprezzamento genuino per il gioco
- ``feature_request``   — richieste di funzionalita' o miglioramenti
- ``content_feedback``  — feedback sul contenuto (storia, livelli, durata)
- ``ui_ux``             — feedback su interfaccia e UX
- ``monetization``      — feedback su prezzo, DLC, microtransazioni

Design:
- ``classify_review(text) -> list[tuple[str, float]]``
  Input: testo review (stringa). Output: lista di ``(categoria, confidence)``
  ordinata per confidence DESC. Se nessuna categoria supera la soglia minima,
  ritorna ``[("praise", 0.1)]`` come fallback (assenza di pattern negativi e'
  lievemente positiva).

- ``game_sentiment_summary(game_id, session) -> dict``
  Legge le ultime ``max_reviews`` review dal DB (via SocialPost o un futuro
  campo dedicato), le classifica e ritorna la distribuzione per categoria.

Principio: NESSUN falso positivo e' peggio di un falso negativo per questo
classificatore. I dizionari di keyword sono conservativi: includono pattern
inequivocabili piuttosto che termini ambigui.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Keyword dictionaries per categoria
# ---------------------------------------------------------------------------
# Ogni entry e' una lista di pattern (regex-ready, lowercase).
# Peso: i pattern piu' specifici hanno peso > 1 (default 1).

_KW: dict[str, list[tuple[str, float]]] = {
    "bug_report": [
        (r"\bcrash(ed|es|ing)?\b", 2.0),
        (r"\bfreezes?\b", 2.0),
        (r"\bglitch(es|ed)?\b", 1.5),
        (r"\bbug(s|gy)?\b", 1.5),
        (r"\bbroken\b", 1.5),
        (r"\bnot work(ing)?\b", 1.5),
        (r"\bdoesn.t (load|start|launch)\b", 2.0),
        (r"\bsoftlock(ed|s)?\b", 2.0),
        (r"\bcan.t (save|load|progress)\b", 1.5),
        (r"\berror (message|code|screen)\b", 1.5),
        (r"\bblack screen\b", 1.5),
        (r"\binfini(te|tely) load(ing)?\b", 1.5),
    ],
    "performance_issue": [
        (r"\b(low|bad|terrible|awful)\s+fps\b", 2.0),
        (r"\bfps\s+drop(s)?\b", 2.0),
        (r"\blag(gy|ging)?\b", 1.5),
        (r"\bstutter(s|ing)?\b", 2.0),
        (r"\bframe\s*(rate|drop)\b", 1.5),
        (r"\bperformance\s*(issue|problem|bad|terrible)\b", 1.5),
        (r"\boptimiz(ed|ation|ing)\b", 1.0),
        (r"\bload(ing)?\s*time(s)?\b", 1.0),
        (r"\bjank(y)?\b", 1.5),
        (r"\brunning\s*(slow|poorly|badly|terribly)\b", 1.5),
        (r"\b(cpu|gpu)\s+(usage|spike)\b", 1.5),
        (r"\bmemory\s+leak\b", 2.0),
    ],
    "praise": [
        (r"\bincredible\b", 2.0),
        (r"\bamazing\b", 1.5),
        (r"\boutstanding\b", 2.0),
        (r"\bmasterpiece\b", 2.0),
        (r"\bhighly recommend\b", 2.0),
        (r"\bmust\s*(play|buy|have)\b", 2.0),
        (r"\bgem\b", 1.5),
        (r"\blovely\b", 1.0),
        (r"\bfun(ny)?\b", 1.0),
        (r"\bgreat game\b", 1.5),
        (r"\bperfect\b", 1.5),
        (r"\bbeautiful\b", 1.0),
        (r"\bwell\s*(made|done|designed|written)\b", 1.5),
        (r"\bworth (the\s+)?(price|money|buy(ing)?)\b", 1.5),
        (r"\bexcellent\b", 1.5),
        (r"\bfantastic\b", 1.5),
        (r"\bcouldn.t stop playing\b", 2.0),
        (r"\bwould play again\b", 1.5),
        (r"\b10/10\b", 2.0),
        (r"\b5(/|\s*out of\s*)5\b", 2.0),
    ],
    "feature_request": [
        (r"\bwould (be\s+)?nice (to have|if)\b", 1.5),
        (r"\bplease add\b", 2.0),
        (r"\bwish (there was|it had|it had)\b", 1.5),
        (r"\bneed(s)? (more|a|an)\b", 1.0),
        (r"\bhope (they|devs|developers)\b", 1.5),
        (r"\bwant(ed)? (to see|more|a)\b", 1.0),
        (r"\bmissing\s+feature\b", 1.5),
        (r"\bshould (have|add|include)\b", 1.5),
        (r"\bwould love (to see|if)\b", 1.5),
        (r"\bfeature request\b", 2.0),
        (r"\bcan we (get|have|see)\b", 1.5),
        (r"\badd (support for|more|a|an)\b", 1.0),
    ],
    "content_feedback": [
        (r"\btoo (short|long)\b", 1.5),
        (r"\bstory (is|was|feels?)\b", 1.0),
        (r"\bending (was|is|feels?)\b", 1.5),
        (r"\bcontent (is|feels?|seems?|comes?)\s+thin\b", 2.0),
        (r"\blevel design\b", 1.5),
        (r"\brepetiti(ve|on)\b", 1.5),
        (r"\bno replay(ability)?\b", 1.5),
        (r"\bchapter(s)?\b", 1.0),
        (r"\bhours?\s+of\s+(content|gameplay)\b", 1.0),
        (r"\bgreat (story|writing|narrative|characters)\b", 1.5),
        (r"\bpoor (story|writing|narrative)\b", 1.5),
        (r"\bgame is (short|long)\b", 1.5),
        (r"\bdepleted (content|material)\b", 1.5),
    ],
    "ui_ux": [
        (r"\bui\b", 1.5),
        (r"\binterface\b", 1.0),
        (r"\bmenu (is|feels?|looks?)\b", 1.5),
        (r"\bkeybind(s|ing)?\b", 1.5),
        (r"\bcontroller (support|input|layout)\b", 1.5),
        (r"\buxo?\b", 1.5),
        (r"\bnavigation\s*(is|feels?)\b", 1.0),
        (r"\bclunky\s*(controls?|ui|interface)\b", 2.0),
        (r"\bhard to (read|navigate|find)\b", 1.5),
        (r"\bfont (is|too)\s*(small|big|hard)\b", 1.5),
        (r"\baccessibility\b", 1.0),
        (r"\bhud\b", 1.5),
        (r"\btutorial (is|was|feels?)\b", 1.0),
        (r"\bintuitive\b", 1.0),
        (r"\bconfusing\s*(menu|ui|controls?)\b", 1.5),
    ],
    "monetization": [
        (r"\boverpriced\b", 2.0),
        (r"\btoo expensive\b", 2.0),
        (r"\bnot worth (the\s+)?price\b", 2.0),
        (r"\bdlc\b", 1.5),
        (r"\bmicrotransaction(s)?\b", 2.0),
        (r"\bpay\s*(to\s*win|2\s*win)\b", 2.0),
        (r"\bin.app purchase(s)?\b", 2.0),
        (r"\bmonetization\b", 2.0),
        (r"\bloot\s*box(es)?\b", 2.0),
        (r"\bwait for\s+(a\s+)?sale\b", 1.5),
        (r"\bon\s+sale\b", 1.0),
        (r"\bcontent\s+behind\s+(a\s+)?paywall\b", 2.0),
        (r"\bgood value\b", 1.5),
        (r"\bgreat price\b", 1.5),
    ],
}

# Soglia minima di confidence per includere una categoria nell'output.
_MIN_CONFIDENCE = 0.15

# Valore di confidence massimo normalizzato per categoria.
_MAX_SCORE_REF: dict[str, float] = {
    cat: sum(w for _, w in patterns) for cat, patterns in _KW.items()
}


# ---------------------------------------------------------------------------
# Funzione di classificazione (PURA)
# ---------------------------------------------------------------------------


def classify_review(text: str) -> list[tuple[str, float]]:
    """Classifica una recensione in categorie con confidence score.

    Parametri
    ---------
    text:
        Testo della recensione (qualsiasi lingua, ma i keyword sono in inglese).

    Ritorna
    -------
    Lista di ``(categoria, confidence)`` con confidence in [0, 1], ordinata
    per confidence DESC. Se nessuna categoria supera la soglia minima,
    ritorna ``[("praise", 0.1)]`` come fallback (assenza di segnali negativi
    e' lievemente positiva per definizione del Quality Score).
    """
    if not text:
        return [("praise", 0.1)]

    lower = text.lower()
    scores: dict[str, float] = {}

    for category, patterns in _KW.items():
        raw_score = 0.0
        for pattern, weight in patterns:
            matches = len(re.findall(pattern, lower))
            raw_score += matches * weight
        if raw_score > 0:
            ref = _MAX_SCORE_REF.get(category, 1.0)
            # Normalizza su [0, 1] con saturazione rapida (tangente iperbolica).
            import math
            confidence = round(math.tanh(raw_score / ref * 2.5), 4)
            scores[category] = confidence

    results = [
        (cat, conf) for cat, conf in scores.items() if conf >= _MIN_CONFIDENCE
    ]
    results.sort(key=lambda x: x[1], reverse=True)

    if not results:
        return [("praise", 0.1)]
    return results


# ---------------------------------------------------------------------------
# Riepilogo per gioco (con accesso al DB)
# ---------------------------------------------------------------------------


def game_sentiment_summary(
    game_id: int,
    session,
    max_reviews: int = 200,
) -> dict[str, object]:
    """Classifica le review recenti di un gioco e ritorna la distribuzione.

    Recupera dal DB i ``SocialPost`` del gioco che hanno un titolo (usato
    come testo della review), li classifica con ``classify_review`` e
    aggrega la distribuzione per categoria.

    Parametri
    ---------
    game_id:
        ID del gioco nel DB.
    session:
        Sessione SQLAlchemy attiva (con accesso a ``SocialPost``).
    max_reviews:
        Numero massimo di review da processare (ordinate per data DESC).

    Ritorna
    -------
    Dict con:
    - ``game_id``: l'id passato
    - ``n_reviews``: numero di review analizzate
    - ``distribution``: dict ``{categoria: fraction}`` (somma > 1 per multi-label)
    - ``top_category``: categoria piu' frequente o ``None``
    - ``categories``: lista di ``{category, count, fraction, avg_confidence}``
    """
    from sqlalchemy import select, desc
    from core.models import SocialPost

    posts = list(
        session.scalars(
            select(SocialPost)
            .where(SocialPost.game_id == game_id)
            .where(SocialPost.title.isnot(None))
            .order_by(desc(SocialPost.posted_at))
            .limit(max_reviews)
        )
    )

    if not posts:
        return {
            "game_id": game_id,
            "n_reviews": 0,
            "distribution": {},
            "top_category": None,
            "categories": [],
        }

    # Classifica ogni post.
    cat_counts: dict[str, int] = {cat: 0 for cat in _KW}
    cat_conf_sum: dict[str, float] = {cat: 0.0 for cat in _KW}
    n = len(posts)

    for post in posts:
        text = post.title or ""
        labels = classify_review(text)
        for cat, conf in labels:
            if cat in cat_counts:
                cat_counts[cat] += 1
                cat_conf_sum[cat] += conf

    # Costruisce la distribuzione normalizzata.
    categories: list[dict[str, object]] = []
    for cat in _KW:
        count = cat_counts[cat]
        if count > 0:
            categories.append({
                "category": cat,
                "count": count,
                "fraction": round(count / n, 4),
                "avg_confidence": round(cat_conf_sum[cat] / count, 4),
            })
    categories.sort(key=lambda x: x["count"], reverse=True)

    distribution = {c["category"]: c["fraction"] for c in categories}
    top_category: Optional[str] = categories[0]["category"] if categories else None

    return {
        "game_id": game_id,
        "n_reviews": n,
        "distribution": distribution,
        "top_category": top_category,
        "categories": categories,
    }
