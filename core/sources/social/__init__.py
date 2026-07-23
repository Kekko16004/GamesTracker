"""Sorgenti social di GamesTracker.

Fase 3: YouTube + Reddit (API ufficiali). Fase 6: TikTok + Instagram
(base a import manuale, ToS-safe, dietro la stessa interfaccia).

Espone l'interfaccia comune ``SocialSource`` con le dataclass normalizzate, i
client social e le funzioni di persistenza + l'import manuale.

Fase 7 (scraping engine): aggiunge scraper async basati su httpx per
TikTok, Instagram, X/Twitter (via Nitter RSS) e Reddit senza API key.
L'orchestratore coordina tutti gli scraper e salva i risultati nel DB.
"""

from core.sources.social.base import (
    GameQuery,
    NormalizedAccount,
    NormalizedAccountSnapshot,
    NormalizedPost,
    SocialSource,
)
from core.sources.social.base_scraper import BaseScraper, SocialPost
from core.sources.social.instagram import (
    InstagramSource,
    build_instagram_source,
    is_instagram_url,
    parse_instagram_url,
)
from core.sources.social.instagram_scraper import (
    InstagramScraper,
    build_instagram_scraper,
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
from core.sources.social.reddit_noauth import (
    RedditNoAuthScraper,
    build_reddit_noauth_scraper,
)
from core.sources.social.scraping_orchestrator import (
    ScrapingOrchestrator,
    run_once_sync,
    run_social_scraping_job,
    social_post_to_normalized,
)
from core.sources.social.tiktok import (
    TikTokSource,
    build_tiktok_source,
    is_tiktok_url,
    parse_tiktok_url,
)
from core.sources.social.tiktok_scraper import (
    TikTokScraper,
    build_tiktok_scraper,
)
from core.sources.social.x_scraper import XScraper, build_x_scraper
from core.sources.social.youtube import (
    QuotaExceededError,
    QuotaTracker,
    YouTubeSource,
    build_youtube_source,
)

__all__ = [
    # Shared data model
    "GameQuery",
    "NormalizedAccount",
    "NormalizedAccountSnapshot",
    "NormalizedPost",
    "SocialSource",
    # Async scraper base + dataclass
    "BaseScraper",
    "SocialPost",
    # YouTube (API)
    "YouTubeSource",
    "build_youtube_source",
    "QuotaTracker",
    "QuotaExceededError",
    # Reddit (PRAW API)
    "RedditSource",
    "build_reddit_source",
    # Reddit (no-auth async scraper)
    "RedditNoAuthScraper",
    "build_reddit_noauth_scraper",
    # TikTok (manual import legacy)
    "TikTokSource",
    "build_tiktok_source",
    "is_tiktok_url",
    "parse_tiktok_url",
    # TikTok (async scraper)
    "TikTokScraper",
    "build_tiktok_scraper",
    # Instagram (manual import legacy)
    "InstagramSource",
    "build_instagram_source",
    "is_instagram_url",
    "parse_instagram_url",
    # Instagram (async scraper)
    "InstagramScraper",
    "build_instagram_scraper",
    # X/Twitter (async scraper via Nitter RSS)
    "XScraper",
    "build_x_scraper",
    # Scraping orchestrator
    "ScrapingOrchestrator",
    "run_once_sync",
    "run_social_scraping_job",
    "social_post_to_normalized",
    # Manual import
    "import_manual_post",
    "ManualImportError",
    # Persistence
    "upsert_account",
    "append_account_snapshot",
    "append_post",
    "save_posts",
    "save_account_with_snapshot",
]
