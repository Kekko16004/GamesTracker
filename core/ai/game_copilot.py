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
    """Everything the user tells us about the game they are building.

    Only ``game_description`` is required.  Every other field enriches the
    context the AI uses to generate better output.
    """

    game_description: str
    genre: str | None = None
    mechanics: list[str] = field(default_factory=list)
    art_style: str | None = None
    target_audience: str | None = None
    similar_games: list[str] = field(default_factory=list)

    def to_context_block(self) -> str:
        """Serialise the brief into a human-readable block for prompt
        injection."""
        lines: list[str] = [f"Description: {self.game_description}"]
        if self.genre:
            lines.append(f"Genre: {self.genre}")
        if self.mechanics:
            lines.append(f"Core mechanics: {', '.join(self.mechanics)}")
        if self.art_style:
            lines.append(f"Art style: {self.art_style}")
        if self.target_audience:
            lines.append(f"Target audience: {self.target_audience}")
        if self.similar_games:
            lines.append(f"Similar games: {', '.join(self.similar_games)}")
        return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# GameCopilot
# ---------------------------------------------------------------------------


class GameCopilot:
    """Orchestrates all AI generation tasks for a game.

    Parameters
    ----------
    client:
        An :class:`LLMClient` instance.  If *None*, the module-level singleton
        returned by :func:`get_llm_client` is used.
    trending_data:
        Optional dictionary with trending market intelligence from the
        database.  Keys used (all optional):

        - ``trending_genres`` -- list of ``{"genre": str, "velocity": int}``
        - ``trending_tags`` -- list of str
        - ``avg_price`` -- float
        - ``median_reviews`` -- int
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        trending_data: dict[str, Any] | None = None,
    ) -> None:
        self._client: LLMClient = client or get_llm_client()
        self._trending_data: dict[str, Any] = trending_data or {}

    # -- Public API ---------------------------------------------------------

    async def generate_all(self, brief: GameBrief) -> CopilotResult:
        """Run every generator in parallel and return a :class:`CopilotResult`.

        Individual failures are logged but do not abort the whole run --
        the result will contain empty strings / lists for the failed parts.
        """
        result = CopilotResult()

        # Fan-out all five generators concurrently.
        desc_task = asyncio.create_task(
            self._safe(self.generate_description(brief), "description")
        )
        titles_task = asyncio.create_task(
            self._safe(self.generate_titles(brief), "titles")
        )
        images_task = asyncio.create_task(
            self._safe(self.generate_image_prompts(brief), "image_prompts")
        )
        tags_task = asyncio.create_task(
            self._safe(self.generate_tags(brief), "tags")
        )
        marketing_task = asyncio.create_task(
            self._safe(self.generate_marketing(brief), "marketing")
        )

        desc_out, titles_out, images_out, tags_out, marketing_out = await asyncio.gather(
            desc_task, titles_task, images_task, tags_task, marketing_task,
        )

        # Unpack results (safe wrappers return None on failure).
        if desc_out is not None:
            result.steam_description_short, result.steam_description_long = desc_out

        if titles_out is not None:
            result.titles = titles_out

        if images_out is not None:
            result.image_prompts = images_out

        if tags_out is not None:
            result.tags = tags_out

        if marketing_out is not None:
            result.elevator_pitch, result.marketing_hooks = marketing_out

        return result

    # -- Individual generators ----------------------------------------------

    async def generate_description(
        self, brief: GameBrief
    ) -> tuple[str, str]:
        """Generate short + long Steam store descriptions.

        Returns
        -------
        tuple[str, str]
            ``(short_description, long_description)``
        """
        prompt = DESCRIPTION_PROMPT.format(
            game_brief=brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = await self._call_json(prompt)
        return (
            data.get("short_description", ""),
            data.get("long_description", ""),
        )

    async def generate_titles(
        self, brief: GameBrief, count: int = 10
    ) -> list[dict[str, Any]]:
        """Generate *count* alternative game titles ranked by market fit.

        Each entry is ``{"name": str, "reasoning": str, "score": int}``.
        """
        prompt = TITLES_PROMPT.format(
            count=count,
            game_brief=brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = await self._call_json(prompt)
        titles: list[dict[str, Any]] = data.get("titles", [])
        # Ensure descending sort by score even if the model did not.
        titles.sort(key=lambda t: t.get("score", 0), reverse=True)
        return titles

    async def generate_image_prompts(
        self, brief: GameBrief
    ) -> dict[str, str]:
        """Generate image-generation prompts for every Steam asset type.

        Returns a dict keyed by asset name (``capsule_main``, ``header_image``,
        ``library_hero``, ``screenshot_1`` etc.).
        """
        prompt = IMAGE_PROMPTS_PROMPT.format(
            game_brief=brief.to_context_block(),
        )
        data = await self._call_json(prompt)
        # Ensure all expected keys exist (fill missing with empty string).
        expected_keys = [
            "capsule_main",
            "capsule_small",
            "header_image",
            "library_hero",
            "screenshot_1",
            "screenshot_2",
            "screenshot_3",
        ]
        return {k: data.get(k, "") for k in expected_keys}

    async def generate_tags(self, brief: GameBrief) -> list[str]:
        """Generate an optimised list of 20 Steam tags sorted by priority."""
        prompt = TAGS_PROMPT.format(
            game_brief=brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = await self._call_json(prompt)
        tags: list[str] = data.get("tags", [])
        return tags

    async def generate_marketing(
        self, brief: GameBrief
    ) -> tuple[str, list[dict[str, str]]]:
        """Generate elevator pitch and marketing hooks.

        Returns
        -------
        tuple[str, list[dict[str, str]]]
            ``(elevator_pitch, hooks)`` where each hook is
            ``{"context": str, "text": str}``.
        """
        prompt = MARKETING_PROMPT.format(
            game_brief=brief.to_context_block(),
            trending_context=self._build_trending_context(),
        )
        data = await self._call_json(prompt)
        return (
            data.get("elevator_pitch", ""),
            data.get("hooks", []),
        )

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

    async def _call_json(self, user_prompt: str) -> dict[str, Any]:
        """Send a system + user message pair and parse the JSON reply."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        return await self._client.chat_json(messages)

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
