"""Liste di default (subreddit, keyword YouTube) dal marketing-playbook.

Centralizza le liste riutilizzabili di ``marketing-playbook.md`` §3 cosi' che
l'agente/utente possa aggiornarle qui senza toccare la logica dei client.
Include la mappatura genere → subreddit e i "size tier" dei subreddit
generalisti (usati dal data-analyst per pesare l'engagement, §3.1).
"""

from __future__ import annotations

# --- Reddit: subreddit generalisti di discovery (playbook §3.1) -----------
SUBREDDITS_GENERAL: list[str] = [
    "IndieGaming",
    "indiegames",
    "IndieDev",
    "gamedev",
    "Games",
    "gaming",
    "pcgaming",
]

# Vetrine / feedback dedicate.
SUBREDDITS_SHOWCASE: list[str] = [
    "playmygame",
    "DestroyMyGame",
    "IMadeThis",
    "SideProject",
    "WishlistWednesday",
]

# Mappa genere/tag (lowercase) → subreddit dedicati (playbook §3.1).
SUBREDDITS_BY_GENRE: dict[str, list[str]] = {
    "horror": ["HorrorGaming", "survivalhorror"],
    "roguelike": ["roguelikes", "roguelites"],
    "roguelite": ["roguelikes", "roguelites"],
    "metroidvania": ["metroidvania"],
    "rpg": ["rpg_gamers"],
    "jrpg": ["JRPG"],
    "crpg": ["CRPG"],
    "strategy": ["RealTimeStrategy", "4Xgaming"],
    "city-builder": ["BaseBuildingGames", "citybuilders"],
    "simulation": ["simulationgaming"],
    "puzzle": ["PuzzleVideoGames"],
    "platformer": ["platformers"],
    "cozy": ["CozyGamers"],
    "farming": ["farmingsimulator"],
    "survival": ["survivalgaming", "survivalcrafting"],
    "pixel-art": ["PixelArt"],
    "vr": ["virtualreality", "OculusQuest"],
    "deckbuilder": ["deckbuilders"],
}

# Size tier indicativo dei subreddit generalisti: usato per pesare
# l'engagement (500 upvote in un sub piccolo valgono piu' che in uno enorme).
# Valori: 3 = enorme/rumoroso, 2 = grande curato, 1 = di nicchia.
SUBREDDIT_SIZE_TIER: dict[str, int] = {
    "gaming": 3,
    "Games": 2,
    "pcgaming": 2,
    "IndieGaming": 2,
    "indiegames": 1,
    "IndieDev": 1,
    "gamedev": 1,
}

# --- YouTube: suffissi di ricerca per gioco (playbook §3.3) ---------------
# Combinati col titolo esatto: es. '"Titolo" gameplay'.
YOUTUBE_QUERY_SUFFIXES: list[str] = [
    "gameplay",
    "demo",
    "trailer",
    "review",
    "first look",
]

# --- Tag di genere per la discovery (playbook §3.4) -----------------------
GENRE_TAGS: list[str] = [
    "roguelike",
    "metroidvania",
    "horror",
    "rpg",
    "strategy",
    "simulation",
    "puzzle",
    "platformer",
    "deckbuilder",
    "survival",
    "cozy",
    "visual-novel",
    "pixel-art",
    "souls-like",
    "city-builder",
    "farming",
]


def subreddits_for_game(
    genres: list[str] | None,
    tags: list[str] | None,
    include_showcase: bool = False,
) -> list[str]:
    """Restituisce i subreddit target per un gioco.

    Combina i generalisti con quelli per-genere derivati da ``genres``/``tags``
    (case-insensitive). Ordine stabile e senza duplicati.
    """
    result: list[str] = list(SUBREDDITS_GENERAL)
    if include_showcase:
        result.extend(SUBREDDITS_SHOWCASE)

    for term in (genres or []) + (tags or []):
        key = term.strip().lower().replace(" ", "-")
        for sub in SUBREDDITS_BY_GENRE.get(key, []):
            result.append(sub)

    # Dedup preservando l'ordine.
    seen: set[str] = set()
    ordered: list[str] = []
    for sub in result:
        low = sub.lower()
        if low not in seen:
            seen.add(low)
            ordered.append(sub)
    return ordered
