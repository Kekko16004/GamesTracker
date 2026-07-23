"""AI Copilot for indie game developers.

Given a game description (what the game is about, genre, mechanics, art style),
generates everything needed to market the game on Steam:

1. Steam description (short + long, optimised for conversion)
2. 10 alternative titles ranked by market fit
3. Image generation prompts (capsule art, header, screenshots)
4. Optimised Steam tags
5. Marketing hooks / elevator pitch

All generation is async, uses the universal :class:`~core.ai.llm_client.LLMClient`,
and returns typed dataclasses that the GUI / web layer can render directly.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core.ai.llm_client import LLMClient, LLMResponseError, get_llm_client
from core.ai.prompts import (
    DESCRIPTION_PROMPT,
    IMAGE_PROMPTS_PROMPT,
    MARKETING_PROMPT,
    SYSTEM_PROMPT,
    TAGS_PROMPT,
    TITLES_PROMPT,
    TRENDING_CONTEXT_TEMPLATE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes -- input & output
# ---------------------------------------------------------------------------


@dataclass
class GameBrief:
    """Everything the user tells us about the game they are building."""

    game_description: str = ""
    name: str | None = None
    genre: str | None = None
    genres: list[str] = field(default_factory=list)
    mechanics: list[str] = field(default_factory=list)
    art_style: str | None = None
    target_audience: str | None = None
    similar_games: list[str] = field(default_factory=list)
<<<<<<< HEAD
    developers: list[str] = field(default_factory=list)
    price: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameBrief:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "description" in d and not known.get("game_description"):
            known["game_description"] = d["description"]
        if "name" in d and not known.get("game_description"):
            known["game_description"] = str(d["name"])
        return cls(**known)
=======
    character_description: str | None = None
    estimated_playtime_hours: float | None = None
>>>>>>> feat: Twitch/Kick scrapers, character prompts, pricing AI, owner estimation

    def to_context_block(self) -> str:
        """Serialise the brief into a human-readable block for prompt injection."""
        lines: list[str] = []
        if self.name:
            lines.append(f"Name: {self.name}")
        if self.game_description:
            lines.append(f"Description: {self.game_description}")
        if self.genre:
            lines.append(f"Genre: {self.genre}")
        elif self.genres:
            lines.append(f"Genres: {', '.join(self.genres)}")
        if self.price is not None:
            lines.append(f"Price: ${self.price:.2f}" if self.price > 0 else "Price: Free to Play")
        if self.mechanics:
            lines.append(f"Core mechanics: {', '.join(self.mechanics)}")
        if self.art_style:
            lines.append(f"Art style: {self.art_style}")
        if self.target_audience:
            lines.append(f"Target audience: {self.target_audience}")
        if self.similar_games:
            lines.append(f"Similar games: {', '.join(self.similar_games)}")
        if self.character_description:
            lines.append(f"Main character: {self.character_description}")
        if self.estimated_playtime_hours:
            lines.append(f"Estimated playtime: {self.estimated_playtime_hours} hours")
        return "\n".join(lines)



@dataclass
class DescriptionResult:
    short: str = ""
    long: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"short": self.short, "long": self.long}


@dataclass
class ImagePromptsResult:
    capsule: str = ""
    header: str = ""
    screenshots: list[str] = field(default_factory=list)
    avatar: str = ""
    library_hero: str = ""

    def __getitem__(self, key: str) -> Any:
        if key == "screenshots":
            return self.screenshots
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return key == "screenshots" or hasattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capsule": self.capsule,
            "header": self.header,
            "screenshots": self.screenshots,
            "avatar": self.avatar,
            "library_hero": self.library_hero,
        }



@dataclass
class MarketingResult:
    pitch: str = ""
    hooks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"pitch": self.pitch, "hooks": self.hooks}


@dataclass
class CopilotResult:
    """Aggregated output of :meth:`GameCopilot.generate_all`."""

    steam_description_short: str = ""
    steam_description_long: str = ""
    titles: list[dict[str, Any]] = field(default_factory=list)
    image_prompts: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    marketing_hooks: list[dict[str, str]] = field(default_factory=list)
    elevator_pitch: str = ""

    def __getitem__(self, key: str) -> Any:
        if key == "description":
            return {"short": self.steam_description_short, "long": self.steam_description_long}
        if key == "marketing":
            return {"hooks": self.marketing_hooks, "elevator_pitch": self.elevator_pitch}
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return key in ("description", "titles", "image_prompts", "tags", "marketing") or hasattr(self, key)


# ---------------------------------------------------------------------------
# GameCopilot
# ---------------------------------------------------------------------------


class GameCopilot:
    """Orchestrates all AI generation tasks for a game."""

    def __init__(
        self,
        brief: GameBrief | str | dict | LLMClient | None = None,
        client: LLMClient | None = None,
        trending_data: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(brief, LLMClient):
            client = brief
            brief = None
        elif isinstance(brief, str):
            brief = GameBrief(game_description=brief)
        elif isinstance(brief, dict):
            brief = GameBrief.from_dict(brief)

        self.brief: GameBrief | None = brief
        self._client: LLMClient = client or get_llm_client()
        self._trending_data: dict[str, Any] = trending_data or {}

    def build_brief(self, game: GameBrief | dict[str, Any] | str | None = None) -> str:
        target = game if game is not None else self.brief
        if isinstance(target, GameBrief):
            return target.to_context_block()
        if isinstance(target, dict):
            return GameBrief.from_dict(target).to_context_block()
        return str(target or "")

    def _resolve_brief(self, brief: GameBrief | dict | str | None) -> GameBrief:
        b = brief if brief is not None else self.brief
        if isinstance(b, GameBrief):
            return b
        if isinstance(b, dict):
            return GameBrief.from_dict(b)
        if isinstance(b, str):
            return GameBrief(game_description=b)
        return GameBrief()

    # -- Public API ---------------------------------------------------------

    def generate_all(self, brief: GameBrief | dict | str | None = None) -> CopilotResult:
        target_brief = self._resolve_brief(brief)
        desc_out = self.generate_description(target_brief)
        titles_out = self.generate_titles(target_brief)
        images_out = self.generate_image_prompts(target_brief)
        tags_out = self.generate_tags(target_brief)
        marketing_out = self.generate_marketing(target_brief)

        result = CopilotResult()
        if desc_out:
            result.steam_description_short = desc_out.short
            result.steam_description_long = desc_out.long
        if titles_out:
            result.titles = titles_out
        if images_out:
            result.image_prompts = images_out.to_dict()
        if tags_out:
            result.tags = tags_out
        if marketing_out:
            result.elevator_pitch = marketing_out.pitch
            result.marketing_hooks = marketing_out.hooks
        return result

    # -- Individual generators ----------------------------------------------

    def generate_description(
        self, brief: GameBrief | dict | str | None = None
    ) -> DescriptionResult:
        target_brief = self._resolve_brief(brief)
        prompt = DESCRIPTION_PROMPT.format(
            game_brief=target_brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = self._call_json(prompt)
        if isinstance(data, dict):
            short = data.get("short_description") or data.get("short", "")
            long = data.get("long_description") or data.get("long", "")
        else:
            short, long = "", ""
        return DescriptionResult(short=short, long=long)

    def generate_titles(
        self, brief: GameBrief | dict | str | None = None, count: int = 10
    ) -> list[dict[str, Any]] | list[str]:
        target_brief = self._resolve_brief(brief)
        prompt = TITLES_PROMPT.format(
            count=count,
            game_brief=target_brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = self._call_json(prompt)
        titles = data if isinstance(data, list) else (data.get("titles", []) if isinstance(data, dict) else [])
        if isinstance(titles, list) and titles and isinstance(titles[0], dict):
            titles.sort(key=lambda t: t.get("score", 0), reverse=True)
        return titles

    def generate_image_prompts(
        self, brief: GameBrief | dict | str | None = None
    ) -> ImagePromptsResult:
        target_brief = self._resolve_brief(brief)
        prompt = IMAGE_PROMPTS_PROMPT.format(
            game_brief=target_brief.to_context_block(),
        )
        data = self._call_json(prompt)
        if isinstance(data, dict):
            capsule = data.get("capsule") or data.get("capsule_main", "")
            header = data.get("header") or data.get("header_image", "")
            avatar = data.get("avatar") or data.get("library_hero", "")
            library_hero = data.get("library_hero") or data.get("avatar", "")
            screenshots = data.get("screenshots") or [v for k, v in data.items() if k.startswith("screenshot")]
        else:
            capsule, header, avatar, library_hero, screenshots = "", "", "", "", []
        return ImagePromptsResult(capsule=capsule, header=header, screenshots=screenshots, avatar=avatar, library_hero=library_hero)


    def generate_tags(self, brief: GameBrief | dict | str | None = None) -> list[str]:
        target_brief = self._resolve_brief(brief)
        prompt = TAGS_PROMPT.format(
            game_brief=target_brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = self._call_json(prompt)
        tags = data if isinstance(data, list) else (data.get("tags", []) if isinstance(data, dict) else [])
        return tags

    def generate_marketing(
        self, brief: GameBrief | dict | str | None = None
    ) -> MarketingResult:
        target_brief = self._resolve_brief(brief)
        prompt = MARKETING_PROMPT.format(
            game_brief=target_brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = self._call_json(prompt)
        if isinstance(data, dict):
            pitch = data.get("elevator_pitch") or data.get("pitch", "")
            hooks = data.get("hooks", [])
        else:
            pitch, hooks = "", []
        return MarketingResult(pitch=pitch, hooks=hooks)


    # -- Trending context builder -------------------------------------------

    def _build_trending_context(self) -> str:
        """Format the trending data dict into a prompt-injectable block.

        Returns an empty string when no trending data is available so prompts
        degrade gracefully.
        """
        if not self._trending_data:
            return "(No trending market data available at this time.)"

        genres_raw = self._trending_data.get("trending_genres", [])
        if isinstance(genres_raw, list) and genres_raw:
            if isinstance(genres_raw[0], dict):
                genre_lines = [
                    f"  - {g.get('genre', '?')}: velocity {g.get('velocity', '?')}"
                    for g in genres_raw[:10]
                ]
            else:
                genre_lines = [f"  - {g}" for g in genres_raw[:10]]
            genres_str = "\n".join(genre_lines)
        else:
            genres_str = "  (no data)"

        tags_raw = self._trending_data.get("trending_tags", [])
        if isinstance(tags_raw, list) and tags_raw:
            tags_str = ", ".join(str(t) for t in tags_raw[:20])
        else:
            tags_str = "(no data)"

        avg_price = self._trending_data.get("avg_price", "N/A")
        median_reviews = self._trending_data.get("median_reviews", "N/A")

        return TRENDING_CONTEXT_TEMPLATE.format(
            trending_genres=genres_str,
            trending_tags=tags_str,
            avg_price=avg_price,
            median_reviews=median_reviews,
        )

    # -- Internal helpers ---------------------------------------------------

    def _call_json(self, user_prompt: str) -> dict[str, Any]:
        """Send a system + user message pair and parse the JSON reply."""
        res = self._client.chat(user_prompt, system_message=SYSTEM_PROMPT)
        if isinstance(res, str):
            import json
            cleaned = res.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            try:
                return json.loads(cleaned.strip())
            except Exception as e:
                raise LLMResponseError(f"Malformed JSON: {e}")
        if isinstance(res, dict):
            return res
        return {}


    @staticmethod
    async def _safe(coro: Any, label: str) -> Any:
        """Await *coro* and return its result, or ``None`` on error.

        Logs the exception so the caller can continue with partial results.
        """
        try:
            return await coro
        except LLMResponseError:
            logger.exception("AI generation failed for '%s' (bad model output)", label)
            return None
        except Exception:  # noqa: BLE001
            logger.exception("AI generation failed for '%s'", label)
            return None


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def get_copilot(
    trending_data: dict[str, Any] | None = None,
) -> GameCopilot:
    """Create a :class:`GameCopilot` using the module-level LLM singleton."""
    return GameCopilot(client=get_llm_client(), trending_data=trending_data)
