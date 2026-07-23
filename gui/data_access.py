"""Layer di accesso ai dati per la GUI (sola lettura).

Tutte le query SQLAlchemy che servono alle viste passano da qui: le view
non scrivono query sparse. Le funzioni sono **read-only** (nessun commit,
nessuna modifica) e restituiscono strutture dati semplici (dataclass e
dict) cosi' da essere:

- testabili senza avviare la GUI (nessuna dipendenza da PyQt6);
- disaccoppiate dalle sessioni ORM (niente oggetti lazy che scadono).

Il :class:`GameRepository` riceve una ``session factory`` (callable che
restituisce una ``Session``) o, in alternativa, usa quella condivisa di
``core.db``. Ogni metodo apre e chiude la propria sessione read-only.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import (
    Game,
    GameSnapshot,
    Platform,
    SocialAccount,
    SocialPost,
    SocialSnapshot,
    AnalysisReport,
)

# Tipo della factory di sessione: un callable senza argomenti -> Session.
SessionFactory = Callable[[], Session]


# --- DTO restituiti alla GUI ---------------------------------------------


@dataclass
class GameRow:
    """Riga sintetica di gioco per liste/tabelle e stato vuoto gentile."""

    id: int
    platform: str
    external_id: str
    title: str
    developer: Optional[str]
    genres: list[str]
    release_date: Optional[str]
    quality_score: Optional[float]
    discarded: bool
    store_url: Optional[str]
    header_image: Optional[str]
    # Metriche piu' recenti (da ultimo snapshot), se disponibili.
    latest_reviews: Optional[int] = None
    latest_players: Optional[int] = None
    # Crescita recensioni sul periodo tracciato (delta primo->ultimo snapshot).
    review_growth: Optional[int] = None


@dataclass
class SnapshotPoint:
    """Punto della serie storica di crescita di un gioco."""

    captured_at: datetime
    snapshot_type: str
    total_reviews: Optional[int]
    total_positive: Optional[int]
    total_negative: Optional[int]
    current_players: Optional[int]


@dataclass
class TimelineEvent:
    """Evento di marketing sulla timeline (demo/release/post social)."""

    kind: str  # "demo" | "release" | "post"
    when: datetime
    label: str
    platform: Optional[str] = None
    url: Optional[str] = None


@dataclass
class SocialAccountRow:
    """Account social collegato con l'ultima metrica follower nota."""

    id: int
    platform: str
    handle: Optional[str]
    url: Optional[str]
    discovered_via: Optional[str]
    latest_followers: Optional[int] = None


@dataclass
class SocialPostRow:
    """Post social singolo (menzione rilevante)."""

    id: int
    platform: str
    posted_at: Optional[datetime]
    title: Optional[str]
    subreddit: Optional[str]
    url: Optional[str]
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]
    shares: Optional[int]


@dataclass
class GameDetail:
    """Dettaglio completo di un gioco per la vista dedicata."""

    game: GameRow
    publisher: Optional[str]
    tags: list[str]
    has_demo: bool
    demo_release_date: Optional[str]
    price: Optional[float]
    is_free: bool
    snapshots: list[SnapshotPoint] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    accounts: list[SocialAccountRow] = field(default_factory=list)
    posts: list[SocialPostRow] = field(default_factory=list)


@dataclass
class GenreTrend:
    """Aggregazione per genere usata dalla vista trend."""

    genre: str
    game_count: int
    avg_quality_score: Optional[float]
    total_review_growth: int


@dataclass
class DashboardStats:
    """Metriche di sintesi mostrate in cima alla dashboard."""

    total_games: int
    visible_games: int
    discarded_games: int
    recent_releases: int


@dataclass
class ReportRow:
    """Riga della tabella report (senza il payload pesante ``data``)."""

    id: int
    game_id: Optional[int]
    game_title: Optional[str]
    genre: Optional[str]
    lang: str
    generated_at: Optional[datetime]
    summary_preview: str


@dataclass
class ReportDetail:
    """Report completo con summary e payload dati per i grafici."""

    id: int
    game_id: Optional[int]
    game_title: Optional[str]
    genre: Optional[str]
    lang: str
    generated_at: Optional[datetime]
    summary: str
    data: dict[str, Any]


# --- Repository -----------------------------------------------------------


class GameRepository:
    """Espone le query read-only usate dalla GUI.

    Parametri:
        session_factory: callable che ritorna una ``Session``. Se assente,
            usa la factory condivisa di ``core.db`` (lazy import per non
            forzare la creazione dell'engine nei test che iniettano la
            propria factory).
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Apre una sessione read-only (rollback finale, mai commit)."""
        if self._session_factory is not None:
            session = self._session_factory()
        else:
            # Import ritardato: evita di creare l'engine se non serve.
            from core.db import get_session_factory

            session = get_session_factory()()
        try:
            yield session
        finally:
            # Nessuna scrittura: annulla eventuale stato e chiude.
            session.rollback()
            session.close()

    # --- Helper interni ---------------------------------------------------

    @staticmethod
    def _snapshots_for(session: Session, game_id: int) -> list[GameSnapshot]:
        """Snapshot di un gioco ordinati cronologicamente."""
        stmt = (
            select(GameSnapshot)
            .where(GameSnapshot.game_id == game_id)
            .order_by(GameSnapshot.captured_at.asc())
        )
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def _review_growth(snaps: list[GameSnapshot]) -> Optional[int]:
        """Delta recensioni tra primo e ultimo snapshot con valore noto."""
        values = [s.total_reviews for s in snaps if s.total_reviews is not None]
        if len(values) < 2:
            return None
        return values[-1] - values[0]

    @staticmethod
    def _latest_metric(snaps: list[GameSnapshot], attr: str) -> Optional[int]:
        """Ultimo valore non nullo di una metrica lungo gli snapshot."""
        for snap in reversed(snaps):
            value = getattr(snap, attr)
            if value is not None:
                return value
        return None

    def _to_game_row(
        self, game: Game, snaps: list[GameSnapshot] | None = None
    ) -> GameRow:
        """Converte un ``Game`` ORM in :class:`GameRow` con metriche recenti."""
        snaps = snaps if snaps is not None else []
        platform = game.platform.value if hasattr(game.platform, "value") else str(game.platform)
        return GameRow(
            id=game.id,
            platform=platform,
            external_id=game.external_id,
            title=game.title,
            developer=game.developer,
            genres=list(game.genres or []),
            release_date=game.release_date.isoformat() if game.release_date else None,
            quality_score=game.quality_score,
            discarded=game.discarded,
            store_url=game.store_url,
            header_image=game.header_image,
            latest_reviews=self._latest_metric(snaps, "total_reviews"),
            latest_players=self._latest_metric(snaps, "current_players"),
            review_growth=self._review_growth(snaps),
        )

    # --- Query pubbliche: liste e dashboard -------------------------------

    def has_any_data(self) -> bool:
        """True se esiste almeno un gioco (per lo stato vuoto gentile)."""
        with self._session() as session:
            return session.execute(select(Game.id).limit(1)).first() is not None

    def list_games(
        self,
        *,
        min_quality_score: float = 0.0,
        platform: str | None = None,
        genre: str | None = None,
        include_discarded: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GameRow]:
        """Lista giochi filtrata per soglia, piattaforma e genere.

        La soglia ``min_quality_score`` filtra i giochi "trash": vengono
        esclusi quelli con ``quality_score`` inferiore alla soglia. I giochi
        senza punteggio (None) sono inclusi solo se la soglia e' 0 (non
        possiamo affermare che siano sotto soglia).
        """
        with self._session() as session:
            stmt = select(Game).distinct()
            if not include_discarded:
                stmt = stmt.where(Game.discarded.is_(False))
            if platform:
                stmt = stmt.where(Game.platform == platform)
            if min_quality_score > 0:
                stmt = stmt.where(Game.quality_score >= min_quality_score)
            stmt = stmt.order_by(
                Game.quality_score.is_(None), Game.quality_score.desc()
            )
            if offset:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)

            games = list(session.execute(stmt).scalars().all())
            # Secondary dedup by game id in case ORM identity map returns dupes.
            seen_ids: set[int] = set()
            deduped: list[Game] = []
            for g in games:
                if g.id not in seen_ids:
                    seen_ids.add(g.id)
                    deduped.append(g)
            games = deduped

            rows: list[GameRow] = []
            for game in games:
                # Filtro per genere in Python: i generi sono JSON (portabile).
                if genre and genre not in (game.genres or []):
                    continue
                snaps = self._snapshots_for(session, game.id)
                rows.append(self._to_game_row(game, snaps))
            return rows

    def dashboard_stats(
        self, *, min_quality_score: float = 0.0, recent_days: int = 30
    ) -> DashboardStats:
        """Metriche di sintesi per la testata della dashboard."""
        with self._session() as session:
            total = session.execute(
                select(func.count(Game.id))
            ).scalar_one()
            discarded = session.execute(
                select(func.count(Game.id)).where(Game.discarded.is_(True))
            ).scalar_one()

            visible_stmt = select(func.count(Game.id)).where(
                Game.discarded.is_(False)
            )
            if min_quality_score > 0:
                visible_stmt = visible_stmt.where(
                    Game.quality_score >= min_quality_score
                )
            visible = session.execute(visible_stmt).scalar_one()

            cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date()
            recent = session.execute(
                select(func.count(Game.id)).where(
                    Game.release_date.is_not(None),
                    Game.release_date >= cutoff,
                )
            ).scalar_one()

            return DashboardStats(
                total_games=int(total),
                visible_games=int(visible),
                discarded_games=int(discarded),
                recent_releases=int(recent),
            )

    def recent_releases(
        self, *, days: int = 30, min_quality_score: float = 0.0, limit: int = 10
    ) -> list[GameRow]:
        """Giochi usciti negli ultimi ``days`` giorni, ordinati per data."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        with self._session() as session:
            stmt = (
                select(Game)
                .where(
                    Game.discarded.is_(False),
                    Game.release_date.is_not(None),
                    Game.release_date >= cutoff,
                )
                .order_by(Game.release_date.desc())
                .limit(limit)
            )
            if min_quality_score > 0:
                stmt = stmt.where(Game.quality_score >= min_quality_score)
            games = list(session.execute(stmt).scalars().all())
            return [
                self._to_game_row(g, self._snapshots_for(session, g.id))
                for g in games
            ]

    def top_by_growth(
        self, *, min_quality_score: float = 0.0, limit: int = 10
    ) -> list[GameRow]:
        """Giochi con la maggiore crescita recensioni (delta snapshot)."""
        rows = self.list_games(
            min_quality_score=min_quality_score, include_discarded=False
        )
        with_growth = [r for r in rows if r.review_growth is not None]
        with_growth.sort(key=lambda r: r.review_growth or 0, reverse=True)
        return with_growth[:limit]

    def genre_distribution(
        self, *, min_quality_score: float = 0.0
    ) -> dict[str, int]:
        """Conteggio giochi per genere (sopra soglia, non scartati)."""
        rows = self.list_games(
            min_quality_score=min_quality_score, include_discarded=False
        )
        counts: dict[str, int] = {}
        for row in rows:
            for genre in row.genres:
                counts[genre] = counts.get(genre, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    def available_genres(self) -> list[str]:
        """Elenco ordinato dei generi presenti (per popolare i filtri)."""
        with self._session() as session:
            games = session.execute(
                select(Game.genres).where(Game.genres.is_not(None))
            ).scalars().all()
        genres: set[str] = set()
        for g in games:
            for genre in g or []:
                genres.add(genre)
        return sorted(genres)

    # --- Query pubbliche: dettaglio gioco ---------------------------------

    def get_game_detail(self, game_id: int) -> Optional[GameDetail]:
        """Dettaglio completo: anagrafica, snapshot, timeline, social.

        Restituisce ``None`` se il gioco non esiste.
        """
        with self._session() as session:
            game = session.get(Game, game_id)
            if game is None:
                return None

            snaps = self._snapshots_for(session, game_id)
            snap_points = [
                SnapshotPoint(
                    captured_at=s.captured_at,
                    snapshot_type=(
                        s.snapshot_type.value
                        if hasattr(s.snapshot_type, "value")
                        else str(s.snapshot_type)
                    ),
                    total_reviews=s.total_reviews,
                    total_positive=s.total_positive,
                    total_negative=s.total_negative,
                    current_players=s.current_players,
                )
                for s in snaps
            ]

            # Account social + ultimo follower count.
            accounts_stmt = (
                select(SocialAccount)
                .where(SocialAccount.game_id == game_id)
                .order_by(SocialAccount.platform.asc())
            )
            accounts: list[SocialAccountRow] = []
            for acc in session.execute(accounts_stmt).scalars().all():
                last_snap = session.execute(
                    select(SocialSnapshot)
                    .where(SocialSnapshot.social_account_id == acc.id)
                    .order_by(SocialSnapshot.captured_at.desc())
                    .limit(1)
                ).scalars().first()
                accounts.append(
                    SocialAccountRow(
                        id=acc.id,
                        platform=(
                            acc.platform.value
                            if hasattr(acc.platform, "value")
                            else str(acc.platform)
                        ),
                        handle=acc.handle,
                        url=acc.url,
                        discovered_via=acc.discovered_via,
                        latest_followers=(
                            last_snap.followers if last_snap else None
                        ),
                    )
                )

            # Post social (menzioni) ordinati per data.
            posts_stmt = (
                select(SocialPost)
                .where(SocialPost.game_id == game_id)
                .order_by(SocialPost.posted_at.asc())
            )
            posts = [
                SocialPostRow(
                    id=p.id,
                    platform=(
                        p.platform.value
                        if hasattr(p.platform, "value")
                        else str(p.platform)
                    ),
                    posted_at=p.posted_at,
                    title=p.title,
                    subreddit=p.subreddit,
                    url=p.post_url,
                    views=p.views,
                    likes=p.likes,
                    comments=p.comments,
                    shares=p.shares,
                )
                for p in session.execute(posts_stmt).scalars().all()
            ]

            timeline = self._build_timeline(game, posts)

            return GameDetail(
                game=self._to_game_row(game, snaps),
                publisher=game.publisher,
                tags=list(game.tags or []),
                has_demo=game.has_demo,
                demo_release_date=(
                    game.demo_release_date.isoformat()
                    if game.demo_release_date
                    else None
                ),
                price=game.price,
                is_free=game.is_free,
                snapshots=snap_points,
                timeline=timeline,
                accounts=accounts,
                posts=posts,
            )

    @staticmethod
    def _build_timeline(
        game: Game, posts: list[SocialPostRow]
    ) -> list[TimelineEvent]:
        """Costruisce la timeline marketing: demo, release e post social.

        Le date ``date`` (demo/release) sono normalizzate a ``datetime`` a
        mezzanotte UTC per essere ordinabili insieme ai post.
        """
        events: list[TimelineEvent] = []

        def _as_dt(d: Any) -> Optional[datetime]:
            if d is None:
                return None
            if isinstance(d, datetime):
                # SQLite restituisce datetime naive: normalizza a UTC-aware
                # per poter ordinare insieme alle date demo/release.
                if d.tzinfo is None:
                    return d.replace(tzinfo=timezone.utc)
                return d
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

        demo_dt = _as_dt(game.demo_release_date)
        if demo_dt is not None:
            events.append(
                TimelineEvent(kind="demo", when=demo_dt, label="detail.event.demo")
            )
        release_dt = _as_dt(game.release_date)
        if release_dt is not None:
            events.append(
                TimelineEvent(
                    kind="release", when=release_dt, label="detail.event.release"
                )
            )
        for post in posts:
            post_dt = _as_dt(post.posted_at)
            if post_dt is None:
                continue
            events.append(
                TimelineEvent(
                    kind="post",
                    when=post_dt,
                    label=post.title or "detail.event.post",
                    platform=post.platform,
                    url=post.url,
                )
            )

        events.sort(key=lambda e: e.when)
        return events

    # --- Query pubbliche: trend per genere --------------------------------

    def genre_trends(
        self, *, min_quality_score: float = 0.0
    ) -> list[GenreTrend]:
        """Aggregazioni per genere: n. giochi, score medio, crescita totale.

        Utile alla vista trend per capire quali generi crescono. Calcolata
        in Python perche' i generi sono liste JSON (portabile a Postgres).
        """
        rows = self.list_games(
            min_quality_score=min_quality_score, include_discarded=False
        )
        by_genre: dict[str, list[GameRow]] = {}
        for row in rows:
            for genre in row.genres:
                by_genre.setdefault(genre, []).append(row)

        trends: list[GenreTrend] = []
        for genre, grows in by_genre.items():
            scores = [r.quality_score for r in grows if r.quality_score is not None]
            growths = [r.review_growth for r in grows if r.review_growth is not None]
            trends.append(
                GenreTrend(
                    genre=genre,
                    game_count=len(grows),
                    avg_quality_score=(sum(scores) / len(scores) if scores else None),
                    total_review_growth=sum(growths) if growths else 0,
                )
            )
        trends.sort(key=lambda t: t.total_review_growth, reverse=True)
        return trends

    # --- Query pubbliche: report ------------------------------------------

    def list_reports(self, *, limit: int | None = None) -> list[ReportRow]:
        """Elenco report generati (piu' recenti prima), senza payload dati."""
        with self._session() as session:
            stmt = select(AnalysisReport).order_by(
                AnalysisReport.generated_at.desc()
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            reports = list(session.execute(stmt).scalars().all())

            rows: list[ReportRow] = []
            for rep in reports:
                title = None
                if rep.game_id is not None:
                    game = session.get(Game, rep.game_id)
                    title = game.title if game else None
                summary = rep.summary or ""
                preview = summary if len(summary) <= 160 else summary[:157] + "..."
                rows.append(
                    ReportRow(
                        id=rep.id,
                        game_id=rep.game_id,
                        game_title=title,
                        genre=rep.genre,
                        lang=rep.lang.value if hasattr(rep.lang, "value") else str(rep.lang),
                        generated_at=rep.generated_at,
                        summary_preview=preview,
                    )
                )
            return rows

    def get_report(self, report_id: int) -> Optional[ReportDetail]:
        """Report completo con summary e payload ``data`` per i grafici."""
        with self._session() as session:
            rep = session.get(AnalysisReport, report_id)
            if rep is None:
                return None
            title = None
            if rep.game_id is not None:
                game = session.get(Game, rep.game_id)
                title = game.title if game else None
            return ReportDetail(
                id=rep.id,
                game_id=rep.game_id,
                game_title=title,
                genre=rep.genre,
                lang=rep.lang.value if hasattr(rep.lang, "value") else str(rep.lang),
                generated_at=rep.generated_at,
                summary=rep.summary or "",
                data=dict(rep.data or {}),
            )
