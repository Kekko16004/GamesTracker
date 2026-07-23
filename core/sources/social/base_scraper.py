"""Abstract base class for async social media scrapers with rate limiting.

Provides the ``BaseScraper`` abstract class with:
- Rate limiting via asyncio (configurable requests/minute)
- Retry with exponential backoff (max 3 retries)
- User-Agent rotation (pool of 10+ browser-like UAs)
- Proxy support (optional, configurable)
- Structured logging
- Common data schema (SocialPost dataclass)

Principle: fields that could not be collected remain ``None``, never ``0``.
``0`` means "measured and it is zero".
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent pool (10+ realistic browser UAs, rotated per request)
# ---------------------------------------------------------------------------

_USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Opera on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 OPR/109.0.0.0",
    # Brave on macOS (Chromium-based)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _random_ua() -> str:
    """Returns a randomly selected browser User-Agent string."""
    return random.choice(_USER_AGENTS)


# ---------------------------------------------------------------------------
# SocialPost dataclass (transport between scrapers and persistence layer)
# ---------------------------------------------------------------------------


@dataclass
class SocialPost:
    """Normalised social post returned by async scrapers.

    Maps cleanly to ``core.models.SocialPost`` (ORM) and
    ``core.sources.social.base.NormalizedPost`` (existing transport layer).
    Missing metrics remain ``None`` — never ``0`` — per the data principle.
    """

    platform: str
    post_url: Optional[str] = None
    author: Optional[str] = None
    title: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    posted_at: Optional[datetime] = None
    collected_at: datetime = field(
        default_factory=lambda: datetime.utcnow()  # naive UTC for compat
    )
    subreddit: Optional[str] = None  # Reddit-specific
    extra: Optional[dict] = None  # platform-specific extras


# ---------------------------------------------------------------------------
# Rate limiter (asyncio, token bucket)
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Simple asyncio rate limiter (N requests / 60 seconds).

    Uses a sliding-window approach via ``asyncio.sleep``.
    Thread-safe within a single event loop.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self._rpm = max(1, requests_per_minute)
        # Minimum interval in seconds between consecutive requests.
        self._min_interval: float = 60.0 / self._rpm
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Waits until the next request slot is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            wait = self._min_interval - elapsed
            if wait > 0:
                logger.debug("Rate limiter: waiting %.2fs", wait)
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------

#: Maximum number of retry attempts on transient failures.
MAX_RETRIES: int = 3
#: Base delay (seconds) for exponential back-off: 1s, 2s, 4s, ...
_BACKOFF_BASE: float = 1.0
#: HTTP status codes worth retrying (server-side transient errors).
_RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class BaseScraper(ABC):
    """Abstract base class for async social media scrapers.

    Subclasses implement ``scrape(game_title, **kwargs) -> list[SocialPost]``
    and call ``self._get(url, ...)`` / ``self._get_json(url, ...)`` for HTTP.
    Rate limiting, retry with exponential back-off, UA rotation, and proxy
    support are handled transparently here.

    Args:
        requests_per_minute: Maximum number of HTTP requests per minute.
        proxy_url: Optional HTTP/SOCKS proxy URL (e.g. ``"http://host:port"``).
            ``None`` means no proxy.
        timeout: Per-request timeout in seconds.
    """

    platform: str = ""  # must be set by each subclass

    def __init__(
        self,
        requests_per_minute: int = 30,
        proxy_url: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self._rate_limiter = _RateLimiter(requests_per_minute)
        self._proxy_url = proxy_url or None
        self._timeout = timeout

    # -- public interface -----------------------------------------------

    @abstractmethod
    async def scrape(self, game_title: str, **kwargs) -> list[SocialPost]:
        """Scrape posts related to ``game_title``.

        Must never raise: catch all exceptions, log them, and return a
        (possibly empty) list. The caller depends on this guarantee.

        Args:
            game_title: Name of the indie game to search for.
            **kwargs: Scraper-specific options (e.g. ``hashtags``, ``limit``).

        Returns:
            List of ``SocialPost`` instances; empty list on failure.
        """

    # -- HTTP helpers -------------------------------------------------------

    def _build_client(self, extra_headers: Optional[dict] = None) -> httpx.AsyncClient:
        """Creates an ``httpx.AsyncClient`` with UA rotation and optional proxy."""
        headers = {
            "User-Agent": _random_ua(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if extra_headers:
            headers.update(extra_headers)

        proxy: Optional[str] = self._proxy_url if self._proxy_url else None

        return httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
            proxy=proxy,
        )

    async def _get(
        self,
        url: str,
        *,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> httpx.Response:
        """Performs a GET request with rate limiting and retry back-off.

        Retries up to ``MAX_RETRIES`` times on network errors or retryable
        HTTP status codes, with exponential back-off.

        Args:
            url: Target URL.
            params: Optional query string parameters.
            extra_headers: Additional request headers.

        Returns:
            The ``httpx.Response`` on success.

        Raises:
            httpx.HTTPError: After exhausting all retries.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            try:
                async with self._build_client(extra_headers) as client:
                    response = await client.get(url, params=params)

                if response.status_code in _RETRYABLE_STATUS:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "[%s] HTTP %d for %s (attempt %d/%d), retrying in %.1fs",
                        self.platform,
                        response.status_code,
                        url,
                        attempt + 1,
                        MAX_RETRIES + 1,
                        wait,
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(wait)
                        continue
                    # Exhausted retries - return the last response anyway so
                    # the caller can inspect the status code.
                    return response

                return response

            except (httpx.TransportError, httpx.TimeoutException) as exc:
                wait = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "[%s] Network error on %s (attempt %d/%d): %s - retrying in %.1fs",
                    self.platform,
                    url,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                    wait,
                )
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)

        # All retries exhausted.
        raise httpx.TransportError(
            f"[{self.platform}] All {MAX_RETRIES} retries exhausted for {url}"
        ) from last_exc

    async def _get_json(
        self,
        url: str,
        *,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> Optional[dict]:
        """GET + JSON parse. Returns ``None`` on error (never raises).

        Args:
            url: Target URL expected to return JSON.
            params: Optional query string parameters.
            extra_headers: Additional request headers (e.g. Accept: application/json).

        Returns:
            Parsed JSON dict, or ``None`` if the request or parse failed.
        """
        try:
            response = await self._get(url, params=params, extra_headers=extra_headers)
            if response.status_code == 200:
                return response.json()
            logger.warning(
                "[%s] Non-200 response (%d) from %s",
                self.platform,
                response.status_code,
                url,
            )
        except Exception as exc:  # noqa: BLE001 - caller expects None on any error
            logger.warning("[%s] _get_json failed for %s: %s", self.platform, url, exc)
        return None

    # -- safe integer coercion ----------------------------------------------

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        """Converts a metric value to int; ``None`` if missing or invalid.

        Follows the data principle: ``None`` = "not collected", ``0`` = "zero".
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return None  # avoid treating True/False as 1/0
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
