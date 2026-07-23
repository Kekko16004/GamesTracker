"""Modelli ORM (SQLAlchemy 2.x, typed) per GamesTracker.

Schema fedele a ``.claude/reference/data-model.md``.

Principi:
- **Append-only** per le tabelle ``*_snapshots``: ogni misura nel tempo e'
  una nuova riga, mai un update.
- Dedup su ``(platform, external_id)`` in ``games`` (UNIQUE).
- Enum applicativi per platform / snapshot_type / lang, memorizzati come
  stringhe (portabile a Postgres).
- Campi ``json`` (generi, tag, extra, data) tramite il tipo ``JSON`` di
  SQLAlchemy (mappato a TEXT/JSON su SQLite, JSONB-compatibile su Postgres).
- Indici sui campi di query frequenti (game_id, captured_at, platform).
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base dichiarativa comune a tutti i modelli."""


def _utcnow() -> datetime:
    """Timestamp UTC timezone-aware (default per i campi datetime)."""
    return datetime.now(timezone.utc)


# --- Enum applicativi -----------------------------------------------------


class Platform(str, enum.Enum):
    """Piattaforma di provenienza di un gioco."""

    STEAM = "steam"
    ITCH = "itch"


class SocialPlatform(str, enum.Enum):
    """Piattaforma social collegata a un gioco."""

    YOUTUBE = "youtube"
    REDDIT = "reddit"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    DISCORD = "discord"


class SnapshotType(str, enum.Enum):
    """Tipo di snapshot: canonico (h24/h48/w1/m1), discovery o manuale."""

    DISCOVERY = "discovery"
    H24 = "h24"
    H48 = "h48"
    W1 = "w1"
    M1 = "m1"
    MANUAL = "manual"


class Lang(str, enum.Enum):
    """Lingua di un report generato."""

    IT = "it"
    EN = "en"


# Enum SQLAlchemy riusabili. native_enum=False -> memorizzati come VARCHAR,
# scelta portabile e neutra tra SQLite e Postgres.
_platform_enum = SAEnum(
    Platform, native_enum=False, validate_strings=True, length=16
)
_social_platform_enum = SAEnum(
    SocialPlatform, native_enum=False, validate_strings=True, length=16
)
_snapshot_type_enum = SAEnum(
    SnapshotType, native_enum=False, validate_strings=True, length=16
)
_lang_enum = SAEnum(Lang, native_enum=False, validate_strings=True, length=4)


# --- Tabelle --------------------------------------------------------------


class Game(Base):
    """Anagrafica gioco: una riga per gioco, dedup su (platform, external_id)."""

    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_games_platform_external"),
        Index("ix_games_platform", "platform"),
        Index("ix_games_discarded", "discarded"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[Platform] = mapped_column(_platform_enum, nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    developer: Mapped[Optional[str]] = mapped_column(String(255))
    publisher: Mapped[Optional[str]] = mapped_column(String(255))
    # Liste di stringhe salvate come JSON.
    genres: Mapped[Optional[list[str]]] = mapped_column(JSON)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON)

    release_date: Mapped[Optional[date]] = mapped_column(Date)
    has_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    demo_release_date: Mapped[Optional[date]] = mapped_column(Date)

    price: Mapped[Optional[float]] = mapped_column(Float)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    store_url: Mapped[Optional[str]] = mapped_column(String(1000))
    header_image: Mapped[Optional[str]] = mapped_column(String(1000))

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relazioni (cascade: eliminando un gioco si eliminano i figli).
    snapshots: Mapped[list["GameSnapshot"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    social_accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    social_posts: Mapped[list["SocialPost"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return f"<Game id={self.id} {self.platform}:{self.external_id} {self.title!r}>"


class GameSnapshot(Base):
    """Metriche del gioco nel tempo (append-only)."""

    __tablename__ = "game_snapshots"
    __table_args__ = (
        Index("ix_game_snapshots_game_id", "game_id"),
        Index("ix_game_snapshots_captured_at", "captured_at"),
        Index("ix_game_snapshots_game_captured", "game_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    snapshot_type: Mapped[SnapshotType] = mapped_column(
        _snapshot_type_enum, nullable=False
    )

    total_reviews: Mapped[Optional[int]] = mapped_column(Integer)
    total_positive: Mapped[Optional[int]] = mapped_column(Integer)
    total_negative: Mapped[Optional[int]] = mapped_column(Integer)
    review_score_desc: Mapped[Optional[str]] = mapped_column(String(100))
    current_players: Mapped[Optional[int]] = mapped_column(Integer)
    steamspy_owners: Mapped[Optional[str]] = mapped_column(String(100))
    steamspy_estimate: Mapped[Optional[int]] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    game: Mapped["Game"] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return (
            f"<GameSnapshot id={self.id} game_id={self.game_id} "
            f"type={self.snapshot_type} at={self.captured_at}>"
        )


class SocialAccount(Base):
    """Profilo social collegato a un gioco."""

    __tablename__ = "social_accounts"
    __table_args__ = (
        Index("ix_social_accounts_game_id", "game_id"),
        Index("ix_social_accounts_platform", "platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        _social_platform_enum, nullable=False
    )
    handle: Mapped[Optional[str]] = mapped_column(String(255))
    url: Mapped[Optional[str]] = mapped_column(String(1000))
    discovered_via: Mapped[Optional[str]] = mapped_column(String(255))

    game: Mapped["Game"] = relationship(back_populates="social_accounts")
    snapshots: Mapped[list["SocialSnapshot"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return (
            f"<SocialAccount id={self.id} game_id={self.game_id} "
            f"{self.platform}:{self.handle!r}>"
        )


class SocialSnapshot(Base):
    """Metriche social nel tempo (append-only)."""

    __tablename__ = "social_snapshots"
    __table_args__ = (
        Index("ix_social_snapshots_account_id", "social_account_id"),
        Index("ix_social_snapshots_captured_at", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    social_account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    followers: Mapped[Optional[int]] = mapped_column(Integer)
    total_posts: Mapped[Optional[int]] = mapped_column(Integer)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    account: Mapped["SocialAccount"] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return (
            f"<SocialSnapshot id={self.id} account_id={self.social_account_id} "
            f"at={self.captured_at}>"
        )


class SocialPost(Base):
    """Singoli post/menzioni rilevanti (timeline marketing)."""

    __tablename__ = "social_posts"
    __table_args__ = (
        Index("ix_social_posts_game_id", "game_id"),
        Index("ix_social_posts_platform", "platform"),
        Index("ix_social_posts_posted_at", "posted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        _social_platform_enum, nullable=False
    )
    post_url: Mapped[Optional[str]] = mapped_column(String(1000))
    subreddit: Mapped[Optional[str]] = mapped_column(String(255))
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    title: Mapped[Optional[str]] = mapped_column(String(1000))
    views: Mapped[Optional[int]] = mapped_column(Integer)
    likes: Mapped[Optional[int]] = mapped_column(Integer)
    comments: Mapped[Optional[int]] = mapped_column(Integer)
    shares: Mapped[Optional[int]] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    game: Mapped["Game"] = relationship(back_populates="social_posts")

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return (
            f"<SocialPost id={self.id} game_id={self.game_id} "
            f"{self.platform} posted_at={self.posted_at}>"
        )


class AnalysisReport(Base):
    """Report generati (per-gioco o per-genere), bilingue IT/EN."""

    __tablename__ = "analysis_reports"
    __table_args__ = (
        Index("ix_analysis_reports_game_id", "game_id"),
        Index("ix_analysis_reports_genre", "genre"),
        Index("ix_analysis_reports_generated_at", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: report per-genere non ha game_id.
    game_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE")
    )
    genre: Mapped[Optional[str]] = mapped_column(String(255))
    lang: Mapped[Lang] = mapped_column(_lang_enum, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    summary: Mapped[Optional[str]] = mapped_column(Text)
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return (
            f"<AnalysisReport id={self.id} game_id={self.game_id} "
            f"genre={self.genre!r} lang={self.lang}>"
        )
