"""Interfaccia comune per le sorgenti social e strutture dati normalizzate.

Definisce il contratto ``SocialSource`` che ogni client social (YouTube,
Reddit e, in Fase 6, TikTok/Instagram) implementa, piu' le dataclass di
trasporto usate per passare i dati grezzi al layer di persistenza.

Principio dati (vedi ``marketing-playbook.md`` §2.5): **"dato non raccolto"
non e' "dato assente"**. Un campo che non abbiamo potuto raccogliere resta
``None``, mai ``0``. Lo ``0`` significa "misurato ed e' zero".

Questo modulo non conosce nulla delle sorgenti Steam/itch: e' pensato per
essere condiviso solo tra le sorgenti social.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class NormalizedAccount:
    """Profilo social ufficiale mappabile su ``social_accounts``.

    La coppia ``(platform, handle)`` per un dato ``game_id`` e' la chiave di
    deduplicazione lato persistenza.
    """

    platform: str  # valore di SocialPlatform (es. "youtube", "reddit")
    handle: Optional[str] = None
    url: Optional[str] = None
    discovered_via: Optional[str] = None


@dataclass
class NormalizedAccountSnapshot:
    """Metrica di un profilo nel tempo, mappabile su ``social_snapshots``.

    ``followers`` e ``total_posts`` sono ``None`` se non raccolti. ``extra``
    ospita metriche specifiche di piattaforma e il marcatore di provenienza
    (``{"collection": "api"|"manual"|"unavailable"}``) suggerito dal playbook.
    """

    followers: Optional[int] = None
    total_posts: Optional[int] = None
    extra: Optional[dict[str, Any]] = None


@dataclass
class NormalizedPost:
    """Singolo post/menzione, mappabile su ``social_posts``.

    ``post_url`` e' la chiave di idempotenza (per ``game_id``): lo stesso URL
    non viene mai inserito due volte. Le metriche assenti restano ``None``.
    """

    platform: str  # valore di SocialPlatform
    post_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    title: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    subreddit: Optional[str] = None  # solo Reddit


@dataclass
class GameQuery:
    """Vista minimale di un gioco per le ricerche social.

    Evita di accoppiare le sorgenti social al modello ORM ``Game``: si puo'
    costruire da un ``Game`` (``GameQuery.from_game(game)``) o a mano nei test.
    """

    title: str
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    release_date: Optional[datetime] = None
    demo_release_date: Optional[datetime] = None
    store_url: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None

    @classmethod
    def from_game(cls, game: Any) -> "GameQuery":
        """Costruisce una ``GameQuery`` da un modello ``Game`` (duck-typed)."""
        return cls(
            title=game.title,
            genres=list(game.genres or []),
            tags=list(game.tags or []),
            release_date=getattr(game, "release_date", None),
            demo_release_date=getattr(game, "demo_release_date", None),
            store_url=getattr(game, "store_url", None),
            developer=getattr(game, "developer", None),
            publisher=getattr(game, "publisher", None),
        )


@runtime_checkable
class SocialSource(Protocol):
    """Contratto comune a tutte le sorgenti social.

    Ogni implementazione degrada senza sollevare eccezioni quando le
    credenziali mancano: espone ``enabled = False`` e restituisce liste
    vuote / ``None``.
    """

    #: valore di ``SocialPlatform`` gestito dalla sorgente.
    platform: str
    #: ``False`` se la sorgente e' disabilitata (key/credenziali mancanti).
    enabled: bool

    def find_accounts(self, game: GameQuery) -> list[NormalizedAccount]:
        """Cerca gli account social ufficiali del gioco."""
        ...

    def collect_posts(self, game: GameQuery) -> list[NormalizedPost]:
        """Raccoglie post/menzioni rilevanti per il gioco."""
        ...

    def snapshot_account(
        self, account: NormalizedAccount
    ) -> Optional[NormalizedAccountSnapshot]:
        """Rileva le metriche correnti di un account (follower, n° post)."""
        ...
