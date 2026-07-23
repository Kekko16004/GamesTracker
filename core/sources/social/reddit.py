"""Client Reddit (PRAW).

Cerca menzioni di un gioco nei subreddit del marketing-playbook (§3.1) e
globalmente, ed estrae i dati mappabili su ``social_posts`` (playbook §2.2):
subreddit, post_url, posted_at (created_utc -> datetime UTC), title,
score/upvotes -> likes, num_comments -> comments.

Rate limit: OAuth consente ~100 QPM; PRAW lo gestisce internamente
(``ratelimit_seconds``). Degrada senza crashare se le credenziali mancano:
``enabled = False`` e le funzioni restituiscono liste vuote.

Reddit non ha un "account del gioco" con follower nel modello classico:
``social_snapshots`` e' poco rilevante (playbook §2.2). Rileviamo comunque un
eventuale account ufficiale del dev se emerge dagli autori dei post.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import MissingConfigError, Settings, get_settings
from core.sources.social.base import (
    GameQuery,
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
)
from core.sources.social.keywords import subreddits_for_game

logger = logging.getLogger(__name__)

# Numero massimo di risultati per singola ricerca (evita raffiche inutili).
DEFAULT_SEARCH_LIMIT = 25


def _created_to_datetime(created_utc: Any) -> Optional[datetime]:
    """Converte ``created_utc`` (epoch secondi) in datetime UTC."""
    if created_utc is None:
        return None
    try:
        return datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _to_int(value: Any) -> Optional[int]:
    """Converte una metrica in int; ``None`` se assente (mai 0 di default)."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def submission_to_post(submission: Any) -> NormalizedPost:
    """Normalizza una PRAW ``Submission`` in ``NormalizedPost``.

    Mapping (playbook §2.2): ``score`` -> likes, ``num_comments`` -> comments,
    ``created_utc`` -> posted_at, ``subreddit`` -> subreddit. Reddit non ha
    "views" pubbliche affidabili -> ``None``.
    """
    subreddit = getattr(submission, "subreddit", None)
    # subreddit puo' essere un oggetto Subreddit o gia' una stringa.
    sub_name = getattr(subreddit, "display_name", None) or (
        str(subreddit) if subreddit is not None else None
    )
    permalink = getattr(submission, "permalink", None)
    url = (
        f"https://www.reddit.com{permalink}"
        if permalink
        else getattr(submission, "url", None)
    )
    return NormalizedPost(
        platform="reddit",
        post_url=url,
        posted_at=_created_to_datetime(getattr(submission, "created_utc", None)),
        title=getattr(submission, "title", None),
        views=None,  # non disponibile via API pubblica
        likes=_to_int(getattr(submission, "score", None)),
        comments=_to_int(getattr(submission, "num_comments", None)),
        shares=None,
        subreddit=sub_name,
    )


class RedditSource:
    """Sorgente social Reddit. Implementa il protocollo ``SocialSource``."""

    platform = "reddit"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Any = None,
    ) -> None:
        """Costruisce la sorgente.

        ``client`` (una ``praw.Reddit``) puo' essere iniettato nei test. Se
        ``None`` e le credenziali esistono, viene costruito lazy alla prima
        chiamata per non fallire l'import.
        """
        self._settings = settings or get_settings()
        self._client = client
        # enabled se ho un client iniettato oppure tutte le credenziali.
        creds_present = bool(
            self._settings.reddit_client_id
            and self._settings.reddit_client_secret
            and self._settings.reddit_user_agent
        )
        self.enabled = client is not None or creds_present

        if not self.enabled:
            logger.info(
                "Sorgente Reddit disabilitata: credenziali REDDIT_* mancanti."
            )

    # -- client lazy -------------------------------------------------------
    def _get_client(self) -> Any:
        """Restituisce il client PRAW, costruendolo alla prima necessita'."""
        if self._client is not None:
            return self._client
        try:
            client_id, client_secret, user_agent = (
                self._settings.require_reddit_credentials()
            )
        except MissingConfigError as exc:
            logger.warning("Reddit non utilizzabile: %s", exc)
            raise

        import praw

        self._client = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            # PRAW attende automaticamente il reset del rate limit (<=5 min).
            ratelimit_seconds=300,
            check_for_updates=False,
        )
        # Modalita' sola lettura: non pubblichiamo nulla.
        try:
            self._client.read_only = True
        except Exception:  # noqa: BLE001 - alcune versioni/mocks non lo espongono
            pass
        return self._client

    # -- ricerca -----------------------------------------------------------
    def _search_subreddit(
        self, subreddit_name: str, query: str, limit: int
    ) -> list[NormalizedPost]:
        """Cerca ``query`` in un singolo subreddit; degrada su errore."""
        client = self._get_client()
        posts: list[NormalizedPost] = []
        try:
            subreddit = client.subreddit(subreddit_name)
            for submission in subreddit.search(query, limit=limit):
                posts.append(submission_to_post(submission))
        except Exception as exc:  # noqa: BLE001 - subreddit inesistente/privato/ban
            logger.warning(
                "Reddit: ricerca fallita in r/%s per %r: %s",
                subreddit_name,
                query,
                exc,
            )
        return posts

    def _search_global(self, query: str, limit: int) -> list[NormalizedPost]:
        """Ricerca globale su r/all."""
        return self._search_subreddit("all", query, limit)

    def collect_posts(
        self,
        game: GameQuery,
        limit: int = DEFAULT_SEARCH_LIMIT,
        include_global: bool = True,
    ) -> list[NormalizedPost]:
        """Raccoglie menzioni del gioco nei subreddit target + globale.

        Cerca il titolo esatto (tra virgolette) nei subreddit del playbook per
        genere/tag e, se ``include_global``, anche su r/all. Deduplica sui
        ``post_url`` (uno stesso post puo' emergere in piu' ricerche).
        """
        if not self.enabled:
            return []

        title = game.title.strip()
        query = f'"{title}"'
        subs = subreddits_for_game(game.genres, game.tags)

        collected: list[NormalizedPost] = []
        for sub in subs:
            collected.extend(self._search_subreddit(sub, query, limit))
        if include_global:
            collected.extend(self._search_global(query, limit))

        # Dedup sui post_url preservando l'ordine (primo vince).
        seen: set[str] = set()
        unique: list[NormalizedPost] = []
        for post in collected:
            key = post.post_url or f"{post.subreddit}:{post.title}"
            if key not in seen:
                seen.add(key)
                unique.append(post)
        return unique

    # -- account -----------------------------------------------------------
    def find_accounts(self, game: GameQuery) -> list[NormalizedAccount]:
        """Reddit raramente ha un 'account ufficiale del gioco'.

        Non deduciamo account dagli autori (troppo rumoroso e a rischio falsi
        positivi): restituiamo lista vuota. La scoperta di un eventuale profilo
        dev spetta al collector (es. link nella pagina store).
        """
        return []

    def snapshot_account(
        self, account: NormalizedAccount
    ) -> Optional[NormalizedAccountSnapshot]:
        """Reddit non ha follower per gioco: nessuno snapshot rilevante."""
        return None


def build_reddit_source(settings: Optional[Settings] = None) -> RedditSource:
    """Factory: costruisce la sorgente Reddit dalle impostazioni correnti."""
    return RedditSource(settings=settings)
