"""Utility HTTP condivise tra i client sorgente.

Fornisce:
- un client ``httpx`` preconfigurato con User-Agent identificabile;
- una funzione ``request_json`` / ``request_text`` con retry/backoff su
  errori di rete e HTTP 429/5xx;
- un ``Throttle`` semplice per rispettare i rate limit (min intervallo tra
  chiamate), sicuro per l'uso da piu' thread (lo scheduler puo' avere
  worker concorrenti).

Principio: i client non devono MAI far crashare il collector. Le funzioni
qui sollevano eccezioni solo dopo aver esaurito i retry; sta al chiamante
gestirle e degradare (ritornando ``None`` / struttura vuota + log).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

# Codici HTTP per cui ha senso ritentare (transitori / rate limit).
_RETRY_STATUS = {429, 500, 502, 503, 504}


class Throttle:
    """Limitatore di frequenza: garantisce un intervallo minimo tra chiamate.

    Thread-safe. Usato per rispettare i rate limit delle sorgenti (es.
    SteamSpy 1 req/s, itch.io 1 req ogni 2-3s).
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        """Blocca finche' non e' passato ``min_interval`` dall'ultima chiamata."""
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


def build_client(
    *,
    timeout: float = 15.0,
    headers: Optional[dict[str, str]] = None,
) -> httpx.Client:
    """Crea un ``httpx.Client`` con User-Agent identificabile.

    Lo User-Agent viene letto da ``Settings.http_user_agent`` (config/.env).
    """
    settings = get_settings()
    base_headers = {"User-Agent": settings.http_user_agent}
    if headers:
        base_headers.update(headers)
    return httpx.Client(
        timeout=timeout,
        headers=base_headers,
        follow_redirects=True,
    )


def _request(
    method: str,
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    params: Optional[dict[str, Any]] = None,
    throttle: Optional[Throttle] = None,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    timeout: float = 15.0,
) -> httpx.Response:
    """Esegue una richiesta HTTP con retry/backoff.

    Ritenta su errori di rete e su HTTP in ``_RETRY_STATUS`` (429/5xx),
    con backoff esponenziale. Solleva l'ultima eccezione se i retry si
    esauriscono. Il chiamante DEVE gestire l'eccezione.
    """
    owns_client = client is None
    cli = client or build_client(timeout=timeout)
    last_exc: Optional[Exception] = None
    try:
        for attempt in range(max_retries):
            if throttle is not None:
                throttle.wait()
            try:
                resp = cli.request(method, url, params=params)
            except httpx.HTTPError as exc:  # errore di rete/timeout
                last_exc = exc
                logger.warning(
                    "HTTP %s %s tentativo %d/%d fallito: %s",
                    method, url, attempt + 1, max_retries, exc,
                )
            else:
                if resp.status_code in _RETRY_STATUS:
                    last_exc = httpx.HTTPStatusError(
                        f"status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    logger.warning(
                        "HTTP %s %s -> %d (tentativo %d/%d)",
                        method, url, resp.status_code, attempt + 1, max_retries,
                    )
                else:
                    return resp
            # backoff esponenziale prima del prossimo tentativo
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (2 ** attempt))
        # Retry esauriti.
        assert last_exc is not None
        raise last_exc
    finally:
        if owns_client:
            cli.close()


def request_json(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    params: Optional[dict[str, Any]] = None,
    throttle: Optional[Throttle] = None,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    timeout: float = 15.0,
) -> Any:
    """GET che ritorna JSON decodificato, con retry/backoff.

    Solleva eccezione a retry esauriti o se il body non e' JSON valido.
    """
    resp = _request(
        "GET", url,
        client=client, params=params, throttle=throttle,
        max_retries=max_retries, backoff_base=backoff_base, timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def request_text(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
    params: Optional[dict[str, Any]] = None,
    throttle: Optional[Throttle] = None,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    timeout: float = 15.0,
) -> str:
    """GET che ritorna il body come testo, con retry/backoff."""
    resp = _request(
        "GET", url,
        client=client, params=params, throttle=throttle,
        max_retries=max_retries, backoff_base=backoff_base, timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text
