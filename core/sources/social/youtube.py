"""Client YouTube Data API v3 (google-api-python-client).

Copre le due chiamate che servono per la strategia social (playbook §2.1):
- ``search.list`` per scoprire i video rilevanti di un gioco (costo alto: 100
  unita' a chiamata);
- ``videos.list`` per le statistiche (costo 1 unita', batch fino a 50 id);
- ``channels.list`` per il canale (subscriber/video count, 1 unita').

GESTIONE QUOTA
--------------
La Data API v3 concede **10.000 unita'/giorno** di default (vedi
``data-sources.md``). Costi per chiamata:

===================  =====  =========================================
Endpoint             Costo  Note
===================  =====  =========================================
search.list          100    1 sola per gioco alla scoperta
videos.list          1      fino a 50 id/chiamata -> tracking economico
channels.list        1      fino a 50 id/chiamata
===================  =====  =========================================

Strategia di contenimento implementata:
1. **Batching**: ``videos.list``/``channels.list`` raggruppano fino a 50 id
   per chiamata (1 unita' totale invece di N).
2. **Contatore quota** (``QuotaTracker``): traccia le unita' spese e blocca
   (``QuotaExceededError``) prima di sforare un limite configurabile
   (default 10.000, allineato alla quota gratuita).
3. **Caching**: i ``videoId`` risultato di ``search.list`` vengono cache-ati
   su disco (``data/cache/youtube/``) per non ripetere la ricerca costosa; le
   sole statistiche si aggiornano poi con ``videos.list`` a 1 unita'.

Costo stimato per gioco: **1 search (100) + 1 videos.list (1) + 1
channels.list (1) = ~102 unita' alla scoperta**; refresh successivi ~1-2
unita' (solo statistiche). Con 10k/giorno => ~97 giochi nuovi/giorno oppure
migliaia di refresh statistiche.

Degrada senza crashare se ``YOUTUBE_API_KEY`` manca: ``enabled = False`` e le
funzioni restituiscono liste vuote.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import MissingConfigError, Settings, get_settings
from core.sources.social.base import (
    GameQuery,
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
)
from core.sources.social.keywords import YOUTUBE_QUERY_SUFFIXES

logger = logging.getLogger(__name__)

# Costi in unita' di quota per endpoint (documentazione Google).
COST_SEARCH = 100
COST_VIDEOS = 1
COST_CHANNELS = 1

# Quota gratuita giornaliera di default.
DEFAULT_DAILY_QUOTA = 10_000

# Massimo id per chiamata batch (limite API).
MAX_IDS_PER_CALL = 50


class QuotaExceededError(RuntimeError):
    """Sollevata quando una chiamata sforerebbe il limite di quota."""


class QuotaTracker:
    """Contatore di quota YouTube con limite configurabile.

    Non persiste tra processi (il reset quota Google e' giornaliero, mezzanotte
    Pacific): serve a proteggere una singola run del collector dallo sforare.
    """

    def __init__(self, daily_limit: int = DEFAULT_DAILY_QUOTA) -> None:
        self.daily_limit = daily_limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used)

    def can_afford(self, cost: int) -> bool:
        return self.used + cost <= self.daily_limit

    def charge(self, cost: int) -> None:
        """Registra una spesa; solleva ``QuotaExceededError`` se sfora."""
        if not self.can_afford(cost):
            raise QuotaExceededError(
                f"Quota YouTube insufficiente: servono {cost} unita', "
                f"rimaste {self.remaining}/{self.daily_limit}."
            )
        self.used += cost


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """Converte un timestamp ISO-8601 YouTube (``...Z``) in datetime UTC."""
    if not value:
        return None
    try:
        # publishedAt e' del tipo "2024-05-01T12:00:00Z".
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning("YouTube: publishedAt non parsabile: %r", value)
        return None


def _to_int(value: Any) -> Optional[int]:
    """Converte una metrica in int; ``None`` se assente (mai 0 di default).

    YouTube omette ``likeCount``/``commentCount`` quando disabilitati: in quel
    caso il dato e' "non raccolto" -> ``None``, non ``0``.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeSource:
    """Sorgente social YouTube. Implementa il protocollo ``SocialSource``."""

    platform = "youtube"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        quota: Optional[QuotaTracker] = None,
        client: Any = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Costruisce la sorgente.

        ``client`` puo' essere iniettato (nei test un mock del ``build`` di
        google-api-python-client). Se ``None`` e la key esiste, viene costruito
        alla prima chiamata (lazy) per non fallire l'import.
        """
        self._settings = settings or get_settings()
        self.quota = quota or QuotaTracker(DEFAULT_DAILY_QUOTA)
        self._client = client
        self.enabled = bool(self._settings.youtube_api_key) or client is not None

        base = cache_dir or (self._settings.data_dir / "cache" / "youtube")
        self._cache_dir = Path(base)

        if not self.enabled:
            logger.info(
                "Sorgente YouTube disabilitata: YOUTUBE_API_KEY mancante."
            )

    # -- client lazy -------------------------------------------------------
    def _get_client(self) -> Any:
        """Restituisce il client API, costruendolo alla prima necessita'."""
        if self._client is not None:
            return self._client
        try:
            key = self._settings.require_youtube_api_key()
        except MissingConfigError as exc:
            logger.warning("YouTube non utilizzabile: %s", exc)
            raise
        # Import locale: non appesantire l'import del modulo.
        from googleapiclient.discovery import build

        self._client = build("youtube", "v3", developerKey=key, cache_discovery=False)
        return self._client

    # -- cache dei videoId -------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() else "_" for c in key.lower())[:120]
        return self._cache_dir / f"{safe}.json"

    def _read_cache(self, key: str) -> Optional[list[str]]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("video_ids")
        except (OSError, ValueError):
            return None

    def _write_cache(self, key: str, video_ids: list[str]) -> None:
        path = self._cache_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "video_ids": video_ids,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("YouTube: impossibile scrivere cache %s: %s", path, exc)

    # -- API: search -------------------------------------------------------
    def search_video_ids(
        self,
        game: GameQuery,
        max_results: int = 25,
        use_cache: bool = True,
        published_after: Optional[datetime] = None,
        include_team: bool = False,
        capture_pre_launch: bool = False,
    ) -> list[str]:
        """Cerca i ``videoId`` rilevanti per un gioco (``search.list``).

        Costa ``COST_SEARCH`` (100) unita'. Usa una sola query costruita dal
        titolo esatto piu' i suffissi di genere del playbook, in OR. Il
        risultato viene cache-ato: chiamate successive con ``use_cache=True``
        non spendono quota.

        Args:
            include_team: se ``True``, aggiunge alla query i nomi di
                developer/publisher (scoperta del track record del team;
                playbook). Da usare solo per giochi promettenti per non
                bruciare quota.
            capture_pre_launch: se ``True``, NON limita ``publishedAfter`` alla
                data demo, cosi' cattura anche i video pubblicati MOLTO prima
                della release (hype pre-lancio, es. beta/early-access lunghi).
        """
        if not self.enabled:
            return []

        # Query: titolo esatto (peso maggiore) + keyword del playbook in OR.
        title = game.title.strip()
        parts = [f'"{title}"']
        parts.extend(f'"{title}" {s}' for s in YOUTUBE_QUERY_SUFFIXES)
        # Track record del team: cerca dev/publisher (senza il titolo) per
        # scoprire altri giochi/canali dello stesso studio.
        team_terms: list[str] = []
        if include_team:
            for name in (game.developer, game.publisher):
                name = (name or "").strip()
                if name and name.lower() not in ("n/a", "unknown"):
                    team_terms.append(name)
            # dedup preservando l'ordine (dev == publisher e' comune).
            seen: set[str] = set()
            for t in team_terms:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    parts.append(f'"{t}" game')
        query = " | ".join(parts)

        # La cache key deve variare con i termini che cambiano la query,
        # altrimenti servirebbe un risultato obsoleto.
        team_sig = "+".join(sorted(seen)) if include_team else ""
        cache_key = f"search::{title}::team={team_sig}::pre={int(capture_pre_launch)}"

        if use_cache:
            cached = self._read_cache(cache_key)
            if cached is not None:
                logger.debug("YouTube: cache hit per %r (%d id)", title, len(cached))
                return cached

        # publishedAfter: default = data demo (riduce rumore, playbook §3.3);
        # se capture_pre_launch, non limitare (raccoglie anche i video pre-demo).
        pub_after = published_after
        if pub_after is None and not capture_pre_launch:
            pub_after = game.demo_release_date
        params: dict[str, Any] = {
            "q": query,
            "part": "id",
            "type": "video",
            "order": "relevance",
            "maxResults": min(max_results, 50),
        }
        if pub_after is not None:
            if isinstance(pub_after, datetime) and pub_after.tzinfo is None:
                pub_after = pub_after.replace(tzinfo=timezone.utc)
            iso = (
                pub_after.isoformat()
                if isinstance(pub_after, datetime)
                else datetime(
                    pub_after.year, pub_after.month, pub_after.day, tzinfo=timezone.utc
                ).isoformat()
            )
            params["publishedAfter"] = iso.replace("+00:00", "Z")

        self.quota.charge(COST_SEARCH)
        try:
            response = self._get_client().search().list(**params).execute()
        except Exception as exc:  # noqa: BLE001 - degrada senza crashare
            logger.warning("YouTube search.list fallita per %r: %s", title, exc)
            return []

        video_ids = [
            item["id"]["videoId"]
            for item in response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        self._write_cache(cache_key, video_ids)
        return video_ids

    # -- API: videos.list (batch) -----------------------------------------
    def fetch_video_stats(self, video_ids: list[str]) -> list[NormalizedPost]:
        """Recupera statistiche dei video in batch da 50 (``videos.list``).

        Ogni chiamata costa ``COST_VIDEOS`` (1) indipendentemente dal numero
        di id (fino a 50). Restituisce ``NormalizedPost`` mappabili su
        ``social_posts``.
        """
        if not self.enabled or not video_ids:
            return []

        posts: list[NormalizedPost] = []
        client = self._get_client()

        for start in range(0, len(video_ids), MAX_IDS_PER_CALL):
            batch = video_ids[start : start + MAX_IDS_PER_CALL]
            self.quota.charge(COST_VIDEOS)
            try:
                response = (
                    client.videos()
                    .list(part="snippet,statistics", id=",".join(batch))
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("YouTube videos.list fallita: %s", exc)
                continue

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                vid = item.get("id")
                posts.append(
                    NormalizedPost(
                        platform=self.platform,
                        post_url=f"https://www.youtube.com/watch?v={vid}" if vid else None,
                        posted_at=_parse_iso8601(snippet.get("publishedAt")),
                        title=snippet.get("title"),
                        views=_to_int(stats.get("viewCount")),
                        likes=_to_int(stats.get("likeCount")),
                        comments=_to_int(stats.get("commentCount")),
                        shares=None,  # YouTube non espone shares via API
                    )
                )
        return posts

    # -- API: channels.list ------------------------------------------------
    def fetch_channels(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Recupera dati canale in batch (``channels.list``, 1 unita'/batch).

        Restituisce ``{channel_id: {title, handle, subscribers, videos,
        views}}`` con metriche ``None`` se nascoste.
        """
        if not self.enabled or not channel_ids:
            return {}

        out: dict[str, dict[str, Any]] = {}
        client = self._get_client()
        for start in range(0, len(channel_ids), MAX_IDS_PER_CALL):
            batch = channel_ids[start : start + MAX_IDS_PER_CALL]
            self.quota.charge(COST_CHANNELS)
            try:
                response = (
                    client.channels()
                    .list(part="snippet,statistics", id=",".join(batch))
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("YouTube channels.list fallita: %s", exc)
                continue

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                cid = item.get("id")
                out[cid] = {
                    "title": snippet.get("title"),
                    "handle": snippet.get("customUrl"),
                    "subscribers": (
                        None
                        if stats.get("hiddenSubscriberCount")
                        else _to_int(stats.get("subscriberCount"))
                    ),
                    "videos": _to_int(stats.get("videoCount")),
                    "views": _to_int(stats.get("viewCount")),
                }
        return out

    # -- protocollo SocialSource ------------------------------------------
    def collect_posts(
        self,
        game: GameQuery,
        include_team: bool = False,
        capture_pre_launch: bool = False,
    ) -> list[NormalizedPost]:
        """Scopre i video del gioco e ne raccoglie le statistiche.

        ``include_team`` allarga la ricerca a developer/publisher (track
        record del team); ``capture_pre_launch`` include i video pre-demo per
        misurare l'hype pre-lancio. Entrambi costano piu' rilevanza/quota:
        attivarli dal collector solo dove serve.
        """
        if not self.enabled:
            return []
        video_ids = self.search_video_ids(
            game,
            include_team=include_team,
            capture_pre_launch=capture_pre_launch,
        )
        return self.fetch_video_stats(video_ids)

    def find_accounts(self, game: GameQuery) -> list[NormalizedAccount]:
        """Deduce i canali dai video trovati.

        YouTube non ha un concetto di "account ufficiale del gioco" ricavabile
        direttamente: la scoperta del canale ufficiale spetta al collector
        (es. dal link nella pagina store). Qui restituiamo lista vuota per
        non spendere quota extra; il collector puo' usare ``fetch_channels``.
        """
        return []

    def snapshot_account(
        self, account: NormalizedAccount
    ) -> Optional[NormalizedAccountSnapshot]:
        """Snapshot di un canale (``handle`` = channelId).

        Richiede il channelId in ``account.handle``. Mappa subscriberCount ->
        followers, videoCount -> total_posts.
        """
        if not self.enabled or not account.handle:
            return None
        data = self.fetch_channels([account.handle]).get(account.handle)
        if data is None:
            return None
        return NormalizedAccountSnapshot(
            followers=data.get("subscribers"),
            total_posts=data.get("videos"),
            extra={"views": data.get("views"), "collection": "api"},
        )


def build_youtube_source(
    settings: Optional[Settings] = None,
    quota: Optional[QuotaTracker] = None,
) -> YouTubeSource:
    """Factory: costruisce la sorgente YouTube dalle impostazioni correnti."""
    return YouTubeSource(settings=settings, quota=quota)
