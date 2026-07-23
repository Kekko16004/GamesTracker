"""Universal LLM client -- works with OpenAI, OpenRouter, Anthropic, or any custom endpoint.

All providers that expose an OpenAI-compatible chat completions endpoint work out
of the box.  The user configures provider, API key, base URL, and model in
``config/.env`` or via the GUI settings dialog.

Supported providers (pre-configured):
- **openai**: api.openai.com (GPT-4o, GPT-4o-mini, etc.)
- **openrouter**: openrouter.ai/api/v1 (access to 200+ models)
- **anthropic**: via OpenAI-compatible proxy (api.anthropic.com with adapter)
- **custom**: any URL with an OpenAI-compatible ``/chat/completions`` endpoint

Config from ``.env``::

    AI_PROVIDER=openrouter          # openai | openrouter | anthropic | custom
    AI_API_KEY=sk-or-v1-xxxx        # API key for the provider
    AI_BASE_URL=                    # custom base URL (auto-set for known providers)
    AI_MODEL=anthropic/claude-sonnet-4  # model identifier
    AI_MAX_TOKENS=4096              # max response tokens
    AI_TEMPERATURE=0.7              # creativity (0.0-1.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from core.config import ENV_FILE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-configured base URLs for known providers
# ---------------------------------------------------------------------------

BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
}

# ---------------------------------------------------------------------------
# Default model per provider (used when AI_MODEL is not set)
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "openrouter": "anthropic/claude-sonnet-4",
    "anthropic": "claude-sonnet-4-20250514",
    "custom": "gpt-4o-mini",
}

# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    """Immutable configuration for the LLM client."""

    provider: str = "openrouter"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    max_retries: int = 3
    retry_delay: float = 0.0

    @property

    def effective_base_url(self) -> str:
        """Return the base URL to use -- explicit override wins, otherwise
        look up the provider in the pre-configured table."""
        if self.base_url:
            return self.base_url.rstrip("/")
        return BASE_URLS.get(self.provider, "")

    @property
    def effective_model(self) -> str:
        """Return the model to use -- explicit wins, otherwise the default
        for the configured provider."""
        if self.model:
            return self.model
        return _DEFAULT_MODELS.get(self.provider, "gpt-4o-mini")

    @property
    def is_configured(self) -> bool:
        """True when the minimum requirements are met (key + reachable URL)."""
        return bool(self.api_key and self.effective_base_url)


    def resolved_base_url(self) -> str:
        """Return the effective base URL for compatibility."""
        return self.effective_base_url


def load_llm_config(env_file: Path | str | None = None) -> LLMConfig:
    """Load LLM settings from environment / ``.env`` file.

    Mirrors the pattern used by :func:`core.config.load_settings`.
    """
    from dotenv import load_dotenv

    path = Path(env_file) if env_file is not None else ENV_FILE
    if path.exists():
        load_dotenv(path, override=False)

    def _s(name: str, default: str = "") -> str:
        raw = os.getenv(name)
        return raw.strip() if raw and raw.strip() else default

    def _i(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def _f(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    return LLMConfig(
        provider=_s("AI_PROVIDER", "openrouter"),
        api_key=_s("AI_API_KEY"),
        base_url=_s("AI_BASE_URL"),
        model=_s("AI_MODEL", "anthropic/claude-sonnet-4"),
        max_tokens=_i("AI_MAX_TOKENS", 4096),
        temperature=_f("AI_TEMPERATURE", 0.7),
    )



load_config = load_llm_config


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class LLMError(RuntimeError):
    """Base exception for LLM client errors."""

    def __init__(self, message: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMAuthError(LLMError):
    """Raised on 401 / 403 responses (bad API key or insufficient quota)."""

    def __init__(self, message: str = "", status_code: int = 401) -> None:
        super().__init__(message, status_code=status_code)



class LLMRateLimitError(LLMError):
    """Raised when retries are exhausted after repeated 429 responses."""


class LLMResponseError(LLMError):
    """Raised when the response body cannot be parsed or is missing content."""


MissingAPIKeyError = LLMAuthError
AuthError = LLMAuthError
RateLimitError = LLMRateLimitError




# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

# Status codes that trigger automatic retry with exponential backoff.
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503})

# Backoff schedule (seconds) for retries.  After the last entry the request
# is abandoned and an exception is raised.
_BACKOFF_SCHEDULE: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)


class LLMClient:
    """Async client for OpenAI-compatible chat completions APIs.

    Usage::

        config = load_llm_config()
        client = LLMClient(config)
        reply = await client.chat([{"role": "user", "content": "Hello!"}])
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._http = httpx.AsyncClient(
            base_url=config.effective_base_url,
            headers=self._build_headers(config),
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
        )

    # -- public API ---------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]] | str,
        system_message: str | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> Any:
        """Send a chat completion request and return the assistant's text."""
        if not self.config.api_key:
            raise LLMAuthError("API key is required")

        if isinstance(messages, str):
            msgs: list[dict[str, str]] = []
            if system_message:
                msgs.append({"role": "system", "content": system_message})
            msgs.append({"role": "user", "content": messages})
        else:
            msgs = list(messages)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            return self._chat_async(msgs, temperature=temperature, max_tokens=max_tokens, response_format=response_format)
        else:
            return self._chat_sync(msgs, temperature=temperature, max_tokens=max_tokens, response_format=response_format)

    async def _chat_async(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.config.effective_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        data = await self._request_with_retry(payload)
        return self._extract_content(data)

    def _chat_sync(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        url = f"{self.config.effective_base_url.rstrip('/')}/chat/completions"
        headers = self._build_headers(self.config)
        payload: dict[str, Any] = {
            "model": self.config.effective_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        attempts = 0
        while True:
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            except Exception as exc:
                raise LLMError(f"HTTP request failed: {exc}") from exc

            if resp.status_code in (401, 403):
                raise LLMAuthError(f"Authentication failed (HTTP {resp.status_code}): {resp.text}", status_code=resp.status_code)

            if resp.status_code in _RETRYABLE_STATUSES:
                if attempts < len(_BACKOFF_SCHEDULE):
                    attempts += 1
                    continue
                raise LLMRateLimitError(f"Rate limit / server error (HTTP {resp.status_code})")
            if resp.status_code != 200:
                raise LLMResponseError(f"HTTP error {resp.status_code}: {resp.text}")

            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as exc:
                raise LLMResponseError(f"Malformed response: {exc}") from exc

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Like :meth:`chat` but parses the response as JSON."""
        res = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        if asyncio.iscoroutine(res):
            text = await res
        else:
            text = res
        return self._parse_json(text)

    async def close(self) -> None:
        """Cleanly shut down the underlying httpx client."""
        await self._http.aclose()


    # -- context manager ----------------------------------------------------

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _build_headers(config: LLMConfig) -> dict[str, str]:
        """Build the authorization headers for the configured provider."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        }
        # OpenRouter requires HTTP-Referer for analytics and ranking.
        if config.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/gamestracker"
            headers["X-Title"] = "GamesTracker"
        return headers

    async def _request_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to ``/chat/completions`` with exponential backoff on
        retryable failures."""
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(
            (*_BACKOFF_SCHEDULE, None),  # None sentinel = final attempt
            start=1,
        ):
            try:
                resp = await self._http.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                logger.warning(
                    "LLM request timed out (attempt %d/%d)",
                    attempt,
                    len(_BACKOFF_SCHEDULE) + 1,
                )
                last_exc = exc
                if backoff is not None:
                    await asyncio.sleep(backoff)
                continue
            except httpx.TransportError as exc:
                logger.warning(
                    "LLM transport error: %s (attempt %d/%d)",
                    exc,
                    attempt,
                    len(_BACKOFF_SCHEDULE) + 1,
                )
                last_exc = exc
                if backoff is not None:
                    await asyncio.sleep(backoff)
                continue

            # -- Auth errors are not retryable. --------------------------------
            if resp.status_code in {401, 403}:
                raise LLMAuthError(
                    f"Authentication failed ({resp.status_code}): "
                    f"{resp.text[:300]}"
                )

            # -- Retryable server errors. --------------------------------------
            if resp.status_code in _RETRYABLE_STATUSES:
                logger.warning(
                    "LLM returned %d (attempt %d/%d)",
                    resp.status_code,
                    attempt,
                    len(_BACKOFF_SCHEDULE) + 1,
                )
                last_exc = LLMError(
                    f"Server returned {resp.status_code}: {resp.text[:300]}"
                )
                if backoff is not None:
                    await asyncio.sleep(backoff)
                continue

            # -- Any other non-2xx is a hard failure. --------------------------
            if resp.status_code >= 400:
                raise LLMError(
                    f"LLM API error {resp.status_code}: {resp.text[:500]}"
                )

            # -- Success. ------------------------------------------------------
            try:
                return resp.json()  # type: ignore[no-any-return]
            except (json.JSONDecodeError, ValueError) as exc:
                raise LLMResponseError(
                    f"Could not decode JSON response: {resp.text[:500]}"
                ) from exc

        # All retries exhausted.
        raise LLMRateLimitError(
            f"All {len(_BACKOFF_SCHEDULE) + 1} attempts failed. "
            f"Last error: {last_exc}"
        )

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        """Pull the assistant message text out of a chat completions response."""
        try:
            choices = data["choices"]
            if not choices:
                raise LLMResponseError("Response contained no choices.")
            return choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                f"Unexpected response structure: {json.dumps(data)[:500]}"
            ) from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Parse a JSON string, tolerating markdown code fences."""
        cleaned = text.strip()
        # Strip ```json ... ``` fences that some models emit.
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n") if "\n" in cleaned else 3
            cleaned = cleaned[first_newline + 1 :]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"Model did not return valid JSON: {text[:500]}"
            ) from exc


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_singleton_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return a module-level singleton :class:`LLMClient`.

    The client is created on first call using :func:`load_llm_config`.
    Subsequent calls return the same instance.
    """
    global _singleton_client  # noqa: PLW0603
    if _singleton_client is None:
        _singleton_client = LLMClient(load_llm_config())
    return _singleton_client


# ---------------------------------------------------------------------------
# Connection test helper
# ---------------------------------------------------------------------------


async def test_connection(config: LLMConfig | None = None) -> tuple[bool, str]:
    """Send a trivial request to verify the LLM configuration works.

    Parameters
    ----------
    config:
        Configuration to test.  When *None*, loads from the environment.

    Returns
    -------
    tuple[bool, str]
        ``(True, model_reply)`` on success, ``(False, error_description)`` on
        failure.
    """
    if config is None:
        config = load_llm_config()

    if not config.is_configured:
        missing: list[str] = []
        if not config.api_key:
            missing.append("AI_API_KEY")
        if not config.effective_base_url:
            missing.append("AI_BASE_URL (or a known AI_PROVIDER)")
        return False, f"Missing configuration: {', '.join(missing)}"

    client = LLMClient(config)
    try:
        reply = await client.chat(
            [{"role": "user", "content": "Say hello in one sentence."}],
            max_tokens=64,
        )
        return True, reply.strip()
    except LLMAuthError as exc:
        return False, f"Authentication failed: {exc}"
    except LLMRateLimitError as exc:
        return False, f"Rate limited / server unavailable: {exc}"
    except LLMError as exc:
        return False, f"LLM error: {exc}"
    except Exception as exc:  # noqa: BLE001 -- catch-all for connection test
        return False, f"Unexpected error: {exc}"
    finally:
        await client.close()
