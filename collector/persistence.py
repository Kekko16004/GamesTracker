"""Persistenza idempotente: mapping dati normalizzati -> modelli ORM.

Prende i dati normalizzati dai client sorgente (dataclass di
``core.sources``) e li scrive sul DB con:
- **upsert idempotente** su ``games`` (dedup su ``platform + external_id``);
- **append** su ``game_snapshots`` (mai update: serie storica);
- **upsert** su ``social_accounts`` (dedup su ``game_id + platform + url``).

Usa ``session_scope`` di ``core.db``. Nessun client di rete qui: solo DB.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import (
    Game,
    GameSnapshot,
    Platform,
    SnapshotType,
    SocialAccount,
    SocialPlatform,
)
from core.sources.itch import ItchGameData
from core.sources.steam_reviews import SteamReviewSummary
from core.sources.steam_store import SteamStoreData
from core.sources.steamspy import SteamSpyData

logger = logging.getLogger(__name__)


# Descrizioni sotto questa soglia (o vuote) sono trattate come placeholder
# dalla componente store_page del quality score.
_PLACEHOLDER_DESC_MIN_LEN = 30


def build_store_extra(details: SteamStoreData) -> dict:
    """Costruisce il dict ``extra`` con i segnali di qualita' della pagina store.

    Estrae dai dati gia' raccolti da ``steam_store`` i campi che il quality
    score (``analysis.quality_score.build_game_data``) legge da
    ``game_snapshots.extra``: presenza trailer, n. screenshot, lunghezza
    descrizione, flag descrizione-placeholder. NON fa chiamate di rete.

    ``asset_flip_tags`` resta un hook (lista mantenuta dal research-scout):
    per ora non popolato per evitare falsi positivi sugli indie validi.
    """
    desc = details.short_description or ""
    desc_len = len(desc.strip())
    extra: dict = {
        "has_trailer": bool(details.has_trailer),
        "screenshot_count": len(details.screenshots or []),
        "description_length": desc_len,
        "placeholder_description": desc_len < _PLACEHOLDER_DESC_MIN_LEN,
    }
    return extra


def get_game(
    session: Session, platform: Platform, external_id: str
) -> Optional[Game]:
    """Ritorna il gioco per ``(platform, external_id)`` o ``None``."""
    return session.scalar(
        select(Game).where(
            Game.platform == platform,
            Game.external_id == str(external_id),
        )
    )


def upsert_steam_game(
    session: Session,
    data: SteamStoreData,
    *,
    steamspy: Optional[SteamSpyData] = None,
) -> Game:
    """Crea o aggiorna un ``Game`` Steam dai dati dello store.

    Idempotente: se il gioco esiste (dedup su appid) aggiorna i campi
    anagrafici; altrimenti lo crea. Non tocca ``first_seen_at`` se gia'
    presente. Ritorna il ``Game`` gestito dalla sessione.
    """
    game = get_game(session, Platform.STEAM, data.appid)
    is_new = game is None
    if game is None:
        game = Game(platform=Platform.STEAM, external_id=data.appid)
        session.add(game)

    game.title = data.name or game.title or ""
    game.developer = (data.developers[0] if data.developers else None) or game.developer
    game.publisher = (data.publishers[0] if data.publishers else None) or game.publisher
    game.genres = data.genres or game.genres
    # Tag: usiamo categorie store + eventuali tag SteamSpy.
    tags = list(data.categories or [])
    if steamspy and steamspy.tags:
        for t in steamspy.tags:
            if t not in tags:
                tags.append(t)
    if tags:
        game.tags = tags
    if data.release_date is not None:
        game.release_date = data.release_date
    game.is_free = data.is_free
    if data.price is not None:
        game.price = data.price
    game.store_url = data.store_url or game.store_url
    game.header_image = data.header_image or game.header_image
    if data.demo_appids:
        game.has_demo = True

    if is_new:
        logger.info("Nuovo gioco Steam: appid=%s %r", data.appid, game.title)
    return game


def upsert_itch_game(session: Session, data: ItchGameData) -> Game:
    """Crea o aggiorna un ``Game`` itch dai dati della pagina.

    Dedup su ``external_id`` = url della pagina gioco (slug stabile).
    """
    game = get_game(session, Platform.ITCH, data.url)
    is_new = game is None
    if game is None:
        game = Game(platform=Platform.ITCH, external_id=data.url)
        session.add(game)

    game.title = data.title or game.title or ""
    game.developer = data.author or game.developer
    game.genres = data.genres or game.genres
    game.tags = data.tags or game.tags
    if data.release_date is not None:
        game.release_date = data.release_date
    game.is_free = data.is_free
    if data.price is not None:
        game.price = data.price
    game.store_url = data.url
    game.header_image = data.header_image or game.header_image
    if data.has_demo:
        game.has_demo = True

    # Link social autore -> social_accounts (upsert).
    for link in data.social_links:
        _upsert_social_account(
            session, game, link.get("platform"), link.get("url"),
            discovered_via="itch_page",
        )

    if is_new:
        logger.info("Nuovo gioco itch: %s %r", data.url, game.title)
    return game


def _upsert_social_account(
    session: Session,
    game: Game,
    platform_str: Optional[str],
    url: Optional[str],
    *,
    handle: Optional[str] = None,
    discovered_via: Optional[str] = None,
) -> Optional[SocialAccount]:
    """Upsert di un ``SocialAccount`` (dedup su game + platform + url)."""
    if not platform_str or not url:
        return None
    try:
        platform = SocialPlatform(platform_str)
    except ValueError:
        logger.info("Piattaforma social sconosciuta: %r", platform_str)
        return None

    # Il gioco potrebbe non avere ancora id (nuovo, non ancora flush):
    # cerchiamo tra gli account gia' collegati in memoria + DB.
    existing = None
    if game.id is not None:
        existing = session.scalar(
            select(SocialAccount).where(
                SocialAccount.game_id == game.id,
                SocialAccount.platform == platform,
                SocialAccount.url == url,
            )
        )
    if existing is None:
        existing = next(
            (
                a for a in game.social_accounts
                if a.platform == platform and a.url == url
            ),
            None,
        )
    if existing is not None:
        return existing

    account = SocialAccount(
        platform=platform, url=url, handle=handle, discovered_via=discovered_via,
    )
    game.social_accounts.append(account)
    return account


def append_game_snapshot(
    session: Session,
    game: Game,
    snapshot_type: SnapshotType,
    *,
    reviews: Optional[SteamReviewSummary] = None,
    current_players: Optional[int] = None,
    steamspy: Optional[SteamSpyData] = None,
    price: Optional[float] = None,
    captured_at=None,
    extra: Optional[dict] = None,
) -> GameSnapshot:
    """Aggiunge (append-only) uno snapshot metriche a un gioco.

    Combina i dati dei client Steam (reviews/players/steamspy). Mai
    aggiorna righe esistenti: ogni chiamata crea una nuova riga. Ritorna
    lo ``GameSnapshot`` creato.
    """
    snap = GameSnapshot(snapshot_type=snapshot_type)
    if captured_at is not None:
        snap.captured_at = captured_at

    if reviews is not None:
        snap.total_reviews = reviews.total_reviews
        snap.total_positive = reviews.total_positive
        snap.total_negative = reviews.total_negative
        snap.review_score_desc = reviews.review_score_desc

    snap.current_players = current_players

    if steamspy is not None:
        snap.steamspy_owners = steamspy.owners
        snap.steamspy_estimate = steamspy.owners_estimate

    # Prezzo esplicito o, in fallback, quello anagrafico del gioco.
    snap.price = price if price is not None else game.price

    if extra:
        snap.extra = extra

    game.snapshots.append(snap)
    logger.info(
        "Snapshot %s per game_id=%s (reviews=%s players=%s)",
        snapshot_type.value, game.id, snap.total_reviews, snap.current_players,
    )
    return snap
