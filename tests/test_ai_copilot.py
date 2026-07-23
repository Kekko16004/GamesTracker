"""Tests for the GamesTracker AI Copilot.

All tests run OFFLINE — no real HTTP calls are made.
httpx is mocked via pytest monkeypatch / unittest.mock.patch.

Coverage:
  - LLMConfig loading from environment
  - Provider base-URL resolution
  - LLMClient.chat: success, 401, 429 retry, JSON parsing, custom endpoint
  - MissingAPIKeyError when api_key is empty
  - GameCopilot.build_brief, generate_description, generate_titles,
    generate_image_prompts, generate_tags, generate_marketing, generate_all
  - SYSTEM_PROMPT non-empty and all PROMPT_TEMPLATES are strings
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(content: str, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response with OpenAI-format JSON body."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = json.dumps(
        {
            "choices": [
                {"message": {"content": content, "role": "assistant"}}
            ]
        }
    )
    mock_resp.json.return_value = json.loads(mock_resp.text)
    return mock_resp


def _make_error_response(status_code: int, body: str = "error") -> MagicMock:
    """Build a fake httpx.Response for error cases."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body
    mock_resp.json.return_value = {"error": body}
    return mock_resp


# ---------------------------------------------------------------------------
# LLMConfig tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_config_defaults(self):
        """With no env vars set, defaults match the spec."""
        from core.ai.llm_client import load_config

        with patch.dict("os.environ", {}, clear=True):
            cfg = load_config()

        assert cfg.provider == "openrouter"
        assert cfg.api_key == ""
        assert cfg.base_url == ""
        assert cfg.model == "anthropic/claude-sonnet-4"
        assert cfg.max_tokens == 4096
        assert cfg.temperature == pytest.approx(0.7)

    def test_load_config_from_env(self, monkeypatch):
        """Environment variables override all defaults."""
        from core.ai.llm_client import load_config

        monkeypatch.setenv("AI_PROVIDER", "openai")
        monkeypatch.setenv("AI_API_KEY", "sk-test-key")
        monkeypatch.setenv("AI_BASE_URL", "https://custom.example.com/v1")
        monkeypatch.setenv("AI_MODEL", "gpt-4o")
        monkeypatch.setenv("AI_MAX_TOKENS", "2048")
        monkeypatch.setenv("AI_TEMPERATURE", "0.3")

        cfg = load_config()

        assert cfg.provider == "openai"
        assert cfg.api_key == "sk-test-key"
        assert cfg.base_url == "https://custom.example.com/v1"
        assert cfg.model == "gpt-4o"
        assert cfg.max_tokens == 2048
        assert cfg.temperature == pytest.approx(0.3)

    def test_load_config_empty_strings_use_defaults(self, monkeypatch):
        """Empty string env vars fall back to defaults (mirrors _get_str behaviour)."""
        from core.ai.llm_client import load_config

        monkeypatch.setenv("AI_PROVIDER", "")
        monkeypatch.setenv("AI_MODEL", "   ")  # whitespace only

        cfg = load_config()

        assert cfg.provider == "openrouter"
        assert cfg.model == "anthropic/claude-sonnet-4"


# ---------------------------------------------------------------------------
# Provider base-URL resolution tests
# ---------------------------------------------------------------------------


class TestProviderBaseURLs:
    def test_openai_url(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(provider="openai", base_url="")
        assert cfg.resolved_base_url() == "https://api.openai.com/v1"

    def test_openrouter_url(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(provider="openrouter", base_url="")
        assert cfg.resolved_base_url() == "https://openrouter.ai/api/v1"

    def test_anthropic_url(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(provider="anthropic", base_url="")
        assert cfg.resolved_base_url() == "https://api.anthropic.com/v1"

    def test_custom_url_overrides_provider(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(
            provider="openai",
            base_url="http://localhost:1234/v1",
        )
        assert cfg.resolved_base_url() == "http://localhost:1234/v1"

    def test_trailing_slash_stripped(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(provider="openai", base_url="https://myserver.com/v1/")
        assert not cfg.resolved_base_url().endswith("/")

    def test_unknown_provider_empty_url(self):
        from core.ai.llm_client import LLMConfig

        cfg = LLMConfig(provider="unknown_provider", base_url="")
        assert cfg.resolved_base_url() == ""


# ---------------------------------------------------------------------------
# LLMClient.chat tests
# ---------------------------------------------------------------------------


class TestChatSuccess:
    def test_chat_success(self):
        """A 200 response returns the assistant message content."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(provider="openrouter", api_key="sk-test", model="test-model")
        client = LLMClient(cfg)

        fake_response = _make_openai_response("Hello from the model!")

        with patch("httpx.post", return_value=fake_response) as mock_post:
            result = client.chat("Say hello")

        assert result == "Hello from the model!"
        mock_post.assert_called_once()

        # Verify the Authorization header was set correctly
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"

    def test_chat_sends_system_message(self):
        """System message is included in the messages array when provided."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(provider="openrouter", api_key="sk-test")
        client = LLMClient(cfg)

        fake_response = _make_openai_response("reply")

        with patch("httpx.post", return_value=fake_response) as mock_post:
            client.chat("User msg", system_message="You are a test bot.")

        _, kwargs = mock_post.call_args
        messages = kwargs["json"]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a test bot."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "User msg"

    def test_chat_without_system_message(self):
        """When no system_message is given, only the user message is sent."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(provider="openrouter", api_key="sk-test")
        client = LLMClient(cfg)

        fake_response = _make_openai_response("reply")

        with patch("httpx.post", return_value=fake_response) as mock_post:
            client.chat("Hello")

        _, kwargs = mock_post.call_args
        messages = kwargs["json"]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


class TestChatAuthError:
    def test_chat_auth_error_401(self):
        """HTTP 401 raises AuthError."""
        from core.ai.llm_client import LLMClient, LLMConfig, AuthError

        cfg = LLMConfig(provider="openrouter", api_key="bad-key")
        client = LLMClient(cfg)

        with patch("httpx.post", return_value=_make_error_response(401)):
            with pytest.raises(AuthError) as exc_info:
                client.chat("Hello")

        assert exc_info.value.status_code == 401

    def test_chat_auth_error_403(self):
        """HTTP 403 also raises AuthError."""
        from core.ai.llm_client import LLMClient, LLMConfig, AuthError

        cfg = LLMConfig(provider="openrouter", api_key="bad-key")
        client = LLMClient(cfg)

        with patch("httpx.post", return_value=_make_error_response(403)):
            with pytest.raises(AuthError) as exc_info:
                client.chat("Hello")

        assert exc_info.value.status_code == 403


class TestChatRateLimitRetry:
    def test_chat_rate_limit_retry_then_success(self):
        """On 429, the client retries and succeeds on the next attempt."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(
            provider="openrouter",
            api_key="sk-test",
            max_retries=3,
            retry_delay=0.0,  # no sleep in tests
        )
        client = LLMClient(cfg)

        responses = [
            _make_error_response(429),
            _make_openai_response("Success after retry!"),
        ]

        with patch("httpx.post", side_effect=responses) as mock_post:
            with patch("time.sleep"):  # suppress any sleep
                result = client.chat("Hello")

        assert result == "Success after retry!"
        assert mock_post.call_count == 2

    def test_chat_rate_limit_exhausted_raises(self):
        """When all retries return 429, RateLimitError is raised."""
        from core.ai.llm_client import LLMClient, LLMConfig, RateLimitError

        cfg = LLMConfig(
            provider="openrouter",
            api_key="sk-test",
            max_retries=2,
            retry_delay=0.0,
        )
        client = LLMClient(cfg)

        with patch("httpx.post", return_value=_make_error_response(429)):
            with patch("time.sleep"):
                with pytest.raises(RateLimitError):
                    client.chat("Hello")


class TestChatJSONParsing:
    def test_chat_json_parsing(self):
        """The client returns raw string content; the caller parses JSON."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(provider="openrouter", api_key="sk-test")
        client = LLMClient(cfg)

        payload = {"short": "A puzzle game", "long": "A longer description here."}
        fake_response = _make_openai_response(json.dumps(payload))

        with patch("httpx.post", return_value=fake_response):
            raw = client.chat("Describe a game")

        parsed = json.loads(raw)
        assert parsed["short"] == "A puzzle game"

    def test_malformed_response_raises(self):
        """If the response body lacks expected keys, LLMError is raised."""
        from core.ai.llm_client import LLMClient, LLMConfig, LLMError

        cfg = LLMConfig(provider="openrouter", api_key="sk-test")
        client = LLMClient(cfg)

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.text = '{"choices": []}'  # empty choices array
        bad_resp.json.return_value = {"choices": []}

        with patch("httpx.post", return_value=bad_resp):
            with pytest.raises(LLMError):
                client.chat("Hello")


class TestCustomEndpoint:
    def test_custom_endpoint(self):
        """AI_PROVIDER=custom with AI_BASE_URL uses that URL directly."""
        from core.ai.llm_client import LLMClient, LLMConfig

        cfg = LLMConfig(
            provider="custom",
            api_key="local-key",
            base_url="http://localhost:1234/v1",
            model="local-model",
        )
        client = LLMClient(cfg)

        fake_response = _make_openai_response("Local response")

        with patch("httpx.post", return_value=fake_response) as mock_post:
            result = client.chat("Hello local")

        assert result == "Local response"
        url_called = mock_post.call_args[0][0]
        assert url_called == "http://localhost:1234/v1/chat/completions"


class TestMissingAPIKey:
    def test_missing_api_key_raises(self):
        """Empty api_key raises MissingAPIKeyError before any HTTP call."""
        from core.ai.llm_client import LLMClient, LLMConfig, MissingAPIKeyError

        cfg = LLMConfig(provider="openrouter", api_key="")
        client = LLMClient(cfg)

        with patch("httpx.post") as mock_post:
            with pytest.raises(MissingAPIKeyError):
                client.chat("Hello")

        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# GameCopilot tests
# ---------------------------------------------------------------------------


def _make_mock_client(response_content: str) -> MagicMock:
    """Return a mock LLMClient whose .chat() always returns response_content."""
    mock = MagicMock()
    mock.chat.return_value = response_content
    return mock


SAMPLE_GAME: dict[str, Any] = {
    "name": "Hollow Keep",
    "short_description": "A dark roguelike dungeon crawler with hand-drawn art.",
    "genres": ["Roguelike", "Action"],
    "tags": ["Roguelike", "Dungeon Crawler", "Dark Fantasy", "Indie"],
    "developers": ["Pixel Forge Studio"],
    "price": 14.99,
    "release_date": "2026-03-15",
}


class TestBuildBrief:
    def test_build_brief_contains_name(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert "Hollow Keep" in brief

    def test_build_brief_contains_genres(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert "Roguelike" in brief

    def test_build_brief_contains_price(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert "14.99" in brief

    def test_build_brief_free_game(self):
        from core.ai.game_copilot import GameCopilot

        game = {"name": "FreeGame", "is_free": True}
        copilot = GameCopilot(game, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert "Free" in brief

    def test_build_brief_minimal_data(self):
        """A game dict with only a name should not raise."""
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot({"name": "Minimal"}, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert "Minimal" in brief

    def test_build_brief_is_string(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(""))
        brief = copilot.build_brief()
        assert isinstance(brief, str)
        assert len(brief) > 0


class TestGenerateDescription:
    def test_generate_description_returns_short_and_long(self):
        from core.ai.game_copilot import GameCopilot, DescriptionResult

        payload = {"short": "A thrilling dark roguelike.", "long": "A much longer description."}
        mock_client = _make_mock_client(json.dumps(payload))

        copilot = GameCopilot(SAMPLE_GAME, client=mock_client)
        result = copilot.generate_description()

        assert isinstance(result, DescriptionResult)
        assert result.short == "A thrilling dark roguelike."
        assert result.long == "A much longer description."

    def test_generate_description_to_dict(self):
        from core.ai.game_copilot import GameCopilot

        payload = {"short": "Short.", "long": "Long."}
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(payload)))
        result = copilot.generate_description()
        d = result.to_dict()

        assert "short" in d
        assert "long" in d

    def test_generate_description_strips_markdown_fence(self):
        """LLMs often wrap JSON in ```json ... ``` — the client must handle that."""
        from core.ai.game_copilot import GameCopilot

        payload = {"short": "Short.", "long": "Long."}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(fenced))
        result = copilot.generate_description()

        assert result.short == "Short."


class TestGenerateTitles:
    def test_generate_titles_returns_10(self):
        from core.ai.game_copilot import GameCopilot

        titles = [f"Title {i}" for i in range(10)]
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(titles)))
        result = copilot.generate_titles()

        assert isinstance(result, list)
        assert len(result) == 10

    def test_generate_titles_all_strings(self):
        from core.ai.game_copilot import GameCopilot

        titles = [f"Title {i}" for i in range(10)]
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(titles)))
        result = copilot.generate_titles()

        for t in result:
            assert isinstance(t, str)

    def test_generate_titles_calls_llm(self):
        from core.ai.game_copilot import GameCopilot

        mock_client = _make_mock_client(json.dumps(["T"] * 10))
        copilot = GameCopilot(SAMPLE_GAME, client=mock_client)
        copilot.generate_titles()

        mock_client.chat.assert_called_once()


class TestGenerateImagePrompts:
    def _make_prompts_payload(self) -> dict:
        return {
            "capsule": "Dark dungeon capsule prompt",
            "header": "Atmospheric header prompt",
            "library_hero": "Epic library hero prompt",
            "screenshots": ["Screen 1", "Screen 2", "Screen 3"],
        }

    def test_generate_image_prompts_has_all_types(self):
        from core.ai.game_copilot import GameCopilot, ImagePromptsResult

        payload = self._make_prompts_payload()
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(payload)))
        result = copilot.generate_image_prompts()

        assert isinstance(result, ImagePromptsResult)
        assert result.capsule == "Dark dungeon capsule prompt"
        assert result.header == "Atmospheric header prompt"
        assert result.library_hero == "Epic library hero prompt"
        assert isinstance(result.screenshots, list)
        assert len(result.screenshots) == 3

    def test_generate_image_prompts_to_dict(self):
        from core.ai.game_copilot import GameCopilot

        payload = self._make_prompts_payload()
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(payload)))
        result = copilot.generate_image_prompts()
        d = result.to_dict()

        assert "capsule" in d
        assert "header" in d
        assert "library_hero" in d
        assert "screenshots" in d
        assert isinstance(d["screenshots"], list)


class TestGenerateTags:
    def test_generate_tags_returns_list(self):
        from core.ai.game_copilot import GameCopilot

        tags = ["Roguelike", "Dark Fantasy", "Indie", "Dungeon Crawler"]
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(tags)))
        result = copilot.generate_tags()

        assert isinstance(result, list)
        assert len(result) == 4

    def test_generate_tags_all_strings(self):
        from core.ai.game_copilot import GameCopilot

        tags = ["Tag1", "Tag2", "Tag3"]
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(tags)))
        result = copilot.generate_tags()

        for t in result:
            assert isinstance(t, str)

    def test_generate_tags_up_to_20(self):
        """The method should handle any list length up to 20."""
        from core.ai.game_copilot import GameCopilot

        tags = [f"Tag{i}" for i in range(20)]
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(tags)))
        result = copilot.generate_tags()

        assert len(result) <= 20


class TestGenerateMarketing:
    def test_generate_marketing_returns_pitch_and_hooks(self):
        from core.ai.game_copilot import GameCopilot, MarketingResult

        payload = {
            "pitch": "Survive the dungeon.",
            "hooks": ["Hook 1", "Hook 2", "Hook 3", "Hook 4", "Hook 5"],
        }
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(payload)))
        result = copilot.generate_marketing()

        assert isinstance(result, MarketingResult)
        assert result.pitch == "Survive the dungeon."
        assert isinstance(result.hooks, list)
        assert len(result.hooks) == 5

    def test_generate_marketing_to_dict(self):
        from core.ai.game_copilot import GameCopilot

        payload = {
            "pitch": "A great pitch.",
            "hooks": ["h1", "h2", "h3", "h4", "h5"],
        }
        copilot = GameCopilot(SAMPLE_GAME, client=_make_mock_client(json.dumps(payload)))
        result = copilot.generate_marketing()
        d = result.to_dict()

        assert "pitch" in d
        assert "hooks" in d


class TestGenerateAll:
    def _full_payload_client(self) -> MagicMock:
        """Return a mock client that cycles through all expected response types."""
        responses = [
            # description
            json.dumps({"short": "Short desc.", "long": "Long desc."}),
            # titles
            json.dumps([f"Title {i}" for i in range(10)]),
            # image_prompts
            json.dumps({
                "capsule": "capsule prompt",
                "header": "header prompt",
                "library_hero": "hero prompt",
                "screenshots": ["s1", "s2", "s3"],
            }),
            # tags
            json.dumps(["Tag1", "Tag2", "Tag3"]),
            # marketing
            json.dumps({
                "pitch": "A pitch.",
                "hooks": ["h1", "h2", "h3", "h4", "h5"],
            }),
        ]
        mock = MagicMock()
        mock.chat.side_effect = responses
        return mock

    def test_generate_all_combines_results(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=self._full_payload_client())
        result = copilot.generate_all()

        assert "description" in result
        assert "titles" in result
        assert "image_prompts" in result
        assert "tags" in result
        assert "marketing" in result

    def test_generate_all_makes_five_llm_calls(self):
        from core.ai.game_copilot import GameCopilot

        mock_client = self._full_payload_client()
        copilot = GameCopilot(SAMPLE_GAME, client=mock_client)
        copilot.generate_all()

        assert mock_client.chat.call_count == 5

    def test_generate_all_description_structure(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=self._full_payload_client())
        result = copilot.generate_all()

        assert "short" in result["description"]
        assert "long" in result["description"]

    def test_generate_all_image_prompts_has_screenshots(self):
        from core.ai.game_copilot import GameCopilot

        copilot = GameCopilot(SAMPLE_GAME, client=self._full_payload_client())
        result = copilot.generate_all()

        assert "screenshots" in result["image_prompts"]
        assert isinstance(result["image_prompts"]["screenshots"], list)


# ---------------------------------------------------------------------------
# Prompts tests
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_system_prompt_not_empty(self):
        from core.ai.prompts import SYSTEM_PROMPT

        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT.strip()) > 0

    def test_all_prompt_templates_are_strings(self):
        from core.ai.prompts import PROMPT_TEMPLATES

        assert isinstance(PROMPT_TEMPLATES, dict)
        assert len(PROMPT_TEMPLATES) > 0
        for key, template in PROMPT_TEMPLATES.items():
            assert isinstance(template, str), f"Template '{key}' is not a string"
            assert len(template.strip()) > 0, f"Template '{key}' is empty"

    def test_expected_template_keys_present(self):
        """All task templates used by GameCopilot must exist."""
        from core.ai.prompts import PROMPT_TEMPLATES

        required_keys = {"description", "titles", "image_prompts", "tags", "marketing"}
        assert required_keys.issubset(set(PROMPT_TEMPLATES.keys()))

    def test_templates_contain_brief_placeholder(self):
        """Every template must accept a {brief} placeholder."""
        from core.ai.prompts import PROMPT_TEMPLATES

        for key, template in PROMPT_TEMPLATES.items():
            assert "{brief}" in template, (
                f"Template '{key}' is missing the {{brief}} placeholder"
            )

    def test_system_prompt_mentions_game_dev(self):
        """System prompt should be clearly game-dev focused."""
        from core.ai.prompts import SYSTEM_PROMPT

        lower = SYSTEM_PROMPT.lower()
        assert any(
            word in lower
            for word in ("game", "indie", "steam", "developer")
        )
