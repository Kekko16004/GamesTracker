"""Job social: raccoglie i post YouTube (+ Reddit opzionale) per i giochi tracciati.

Riempie il job ricorrente ``_job_social_snapshot`` dello scheduler. Per
ogni gioco:

- costruisce una ``GameQuery`` (titolo + generi/tag + developer/publisher);
- cerca i video su YouTube e ne salva statistiche/post (``social_posts``);
- se le credenziali Reddit sono configurate, cerca anche su Reddit;
- **gating quota**: la ricerca allargata a developer/publisher e ai video
  pre-lancio costa piu' quota/rilevanza, quindi si attiva SOLO per i giochi
  "promettenti" (``quality_score`` >= soglia), come deciso con l'utente.

Condivide UNA sola ``QuotaTracker`` per l'intero giro, per rispettare il
budget giornaliero YouTube (10k unita'). Degrada senza crashare: se la key
manca la sorgente e' ``enabled=False`` e il job non fa nulla.

TikTok / Instagram / X / Reddit (no-auth): ora coperti anche dallo
scraping controllato in ``core.sources.social.scraping_orchestrator``
(attivabile con SCRAPING_ENABLED=true in config/.env). L'import manuale
via GUI resta sempre disponibile come fallback.
Reddit PRAW: opzionale — attivo solo se REDDIT_CLIENT_ID/SECRET/USER_AGENT
sono configurati in config/.env.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from core.config import get_settings
from core.db import session_scope
from core.models import Game, Platform
from core.sources.social.base import GameQuery
from core.sources.social.youtube import build_youtube_source, QuotaTracker
from core.sources.social.persistence import save_posts

logger = logging.getLogger(__name__)

# Numero massimo di giochi processati per giro (protegge la quota).
MAX_GAMES_PER_RUN = 60


def _is_promising(game: Game, threshold: float) -> bool:
    """Un gioco e' 'promettente' se ha uno score >= soglia (non scartato)."""
    return (
        game.quality_score is not None
        and game.quality_score >= threshold
        and not game.discarded
    )


def _build_reddit_source_optional():
    """Costruisce RedditSource se le credenziali sono presenti, altrimenti None."""
    try:
        from core.sources.social.reddit import build_reddit_source
        source = build_reddit_source()
        if source.enabled:
            logger.info("Job social: Reddit abilitato.")
            return source
        logger.info(
            "Job social: Reddit disabilitato (credenziali mancanti in config/.env: "
            "REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT)."
        )
    except Exception as exc:
        logger.warning("Job social: Reddit non disponibile (%s).", exc)
    return None


def run_social_collection(limit: int = MAX_GAMES_PER_RUN) -> dict[str, int]:
    """Raccoglie i post social YouTube (+ Reddit opzionale) per i giochi nel DB.

    Ritorna un riepilogo dei conteggi. Non solleva: logga e continua.
    """
    stats = {"games": 0, "promising": 0, "posts_saved": 0, "skipped_disabled": 0}
    settings = get_settings()
    threshold = settings.quality_score_threshold

    quota = QuotaTracker()
    youtube = build_youtube_source(settings=settings, quota=quota)
    reddit = _build_reddit_source_optional()

    if not youtube.enabled and reddit is None:
        logger.info(
            "Job social: nessuna sorgente attiva "
            "(YouTube: manca YOUTUBE_API_KEY; Reddit: mancano credenziali). "
            "TikTok/Instagram/X: usa import manuale dalla GUI."
        )
        stats["skipped_disabled"] = 1
        return stats

    # Legge la lista dei giochi in una transazione breve; poi lavora per id.
    with session_scope() as session:
        games = list(
            session.scalars(
                select(Game).where(Game.platform == Platform.STEAM).order_by(Game.id)
            )
        )
        work = [
            (
                g.id,
                GameQuery.from_game(g),
                _is_promising(g, threshold),
            )
            for g in games[:limit]
        ]

    for game_id, query, promising in work:
        stats["games"] += 1
        if promising:
            stats["promising"] += 1
        try:
            all_posts = []
            if youtube.enabled:
                all_posts += youtube.collect_posts(
                    query,
                    include_team=promising,
                    capture_pre_launch=promising,
                )
            if reddit is not None:
                all_posts += reddit.collect_posts(query)
            if all_posts:
                saved = save_posts(game_id, all_posts)
                stats["posts_saved"] += saved
        except Exception:
            logger.exception("Job social: errore su game_id=%s", game_id)

    logger.info(
        "Job social: giochi=%(games)s, promettenti=%(promising)s, "
        "post salvati=%(posts_saved)s", stats,
    )
    return stats
