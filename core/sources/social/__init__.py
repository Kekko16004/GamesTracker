"""Sorgenti social di GamesTracker.

Fase 3: YouTube + Reddit (API ufficiali). Fase 6: TikTok + Instagram
(base a import manuale, ToS-safe, dietro la stessa interfaccia).

Espone l'interfaccia comune ``SocialSource`` con le dataclass normalizzate, i
client social e le funzioni di persistenza + l'import manuale.
"""

from core.sources.social.base import (
    GameQuery,
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
    SocialSource,
)
from core.sources.social.instagram import (
    InstagramSource,
    build_instagram_source,
    is_instagram_url,
    parse_instagram_url,
)
from core.sources.social.manual_import import (
    ManualImportError,
    import_manual_post,
)
from core.sources.social.persistence import (
    append_account_snapshot,
    append_post,
    save_account_with_snapshot,
    save_posts,
    upsert_account,
)
from core.sources.social.reddit import RedditSource, build_reddit_source
from core.sources.social.tiktok import (
    TikTokSource,
    build_tiktok_source,
    is_tiktok_url,
    parse_tiktok_url,
)
from core.sources.social.youtube import (
    QuotaExceededError,
    QuotaTracker,
    YouTubeSource,
    build_youtube_source,
)

__all__ = [
    "GameQuery",
    "NormalizedAccount",
    "NormalizedAccountSnapshot",
    "NormalizedPost",
    "SocialSource",
    "YouTubeSource",
    "build_youtube_source",
    "QuotaTracker",
    "QuotaExceededError",
    "RedditSource",
    "build_reddit_source",
    "TikTokSource",
    "build_tiktok_source",
    "is_tiktok_url",
    "parse_tiktok_url",
    "InstagramSource",
    "build_instagram_source",
    "is_instagram_url",
    "parse_instagram_url",
    "import_manual_post",
    "ManualImportError",
    "upsert_account",
    "append_account_snapshot",
    "append_post",
    "save_posts",
    "save_account_with_snapshot",
]
