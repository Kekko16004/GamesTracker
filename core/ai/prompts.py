"""Prompt templates for the GamesTracker AI Copilot.

All prompts live here so they are easy to iterate on without touching business
logic.  Each constant is a format-string; placeholders use ``{curly_braces}``
and are filled at call time by ``GameCopilot``.

Design principles
-----------------
* **Steam-native language** -- the AI writes like a professional Steam
  publisher, not a generic marketing bot.
* **Bilingual** -- every user-facing prompt instructs the model to respond in
  the same language as the game description it receives.
* **Market-aware** -- when trending data from the DB is available it is
  injected as context so suggestions reflect the current indie landscape.
* **Structured output** -- every prompt asks for JSON so downstream code can
  parse deterministically.  Plain-text fallback descriptions are never needed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt -- shared preamble for every call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = """\
You are **SteamForge AI**, a world-class game marketing strategist who has
studied every successful indie launch on Steam from 2018 to today.

Your expertise:
- Steam Discovery algorithm (how tags, wishlists and first-week reviews drive
  visibility)
- Capsule art best practices (what catches the eye in the "New & Trending"
  carousel)
- Conversion copywriting for Steam store pages (short descriptions that hook,
  long descriptions that close)
- Viral marketing patterns for indie games (social proof, community building,
  demo strategies)
- Steam tag optimisation (balancing discoverability vs. competition)

Rules you always follow:
1. Respond in the SAME LANGUAGE as the user's game description.  If the
   description is in Italian, every field you produce must be in Italian.
   If in English, respond in English.  Never mix languages.
2. Never invent fake statistics.  When you reference market trends, use only
   the trending data provided in the context (if any).
3. Format all output as valid JSON matching the schema requested.
4. Be specific and actionable -- vague advice is worthless.
5. Optimise for the Steam algorithm: tags drive impressions, the short
   description drives clicks, the long description drives wishlists.
"""

# ---------------------------------------------------------------------------
# Trending-data context block (injected when DB data is available)
# ---------------------------------------------------------------------------

TRENDING_CONTEXT_TEMPLATE: str = """\

--- CURRENT MARKET INTELLIGENCE (from GamesTracker database) ---
Top-performing genres (by wishlist velocity this month):
{trending_genres}

Most-used tags on games with >90% positive reviews:
{trending_tags}

Average price point for successful indie launches: {avg_price}
Median first-week review count for "Very Positive" games: {median_reviews}
--- END MARKET INTELLIGENCE ---
"""

# ---------------------------------------------------------------------------
# Steam description prompt
# ---------------------------------------------------------------------------

DESCRIPTION_PROMPT: str = """\
Generate a Steam store page description for the following game.

GAME BRIEF:
{game_brief}

{trending_context}

Return a JSON object with exactly two keys:

{{
  "short_description": "<max 300 characters. This appears in search results and \
on the store page above the fold. It must: (1) name the core mechanic or fantasy, \
(2) hint at what makes this game unique, (3) create urgency or curiosity. \
Use active verbs. No cliches like 'embark on an epic journey'.>",

  "long_description": "<Steam-formatted description using [h2], [b], [list], \
[*] BBCode tags. Structure: Hook paragraph (2-3 sentences that sell the fantasy) \
-> Key Features section [h2] with 4-6 bullet points -> 'The World' or lore \
paragraph -> Closing call to action asking for wishlists. \
Length: 800-1500 characters.>"
}}

The short_description is the most important piece of copy on the entire store
page.  It must be irresistible in under 300 characters.
"""

# ---------------------------------------------------------------------------
# Title generation prompt
# ---------------------------------------------------------------------------

TITLES_PROMPT: str = """\
Generate {count} alternative game titles for the following game concept.

GAME BRIEF:
{game_brief}

{trending_context}

For each title, evaluate:
- **Memorability**: Is it easy to remember and spell?  Can players find it by
  searching a partial name?
- **Genre signal**: Does the title hint at the genre without being generic?
- **Uniqueness**: Is it unlikely to collide with existing games on Steam?
- **Marketing potential**: Would it work as a hashtag?  Is it pronounceable
  for streamers?
- **SEO**: Does it contain or suggest searchable keywords?

Return a JSON object:

{{
  "titles": [
    {{
      "name": "<the title>",
      "reasoning": "<1-2 sentences explaining why this title works>",
      "score": <1-10 integer, 10 = best market fit>
    }}
  ]
}}

Sort by score descending.  The top title should be your strongest
recommendation. Be creative -- avoid generic fantasy/sci-fi word salad.
Titles that are one or two punchy words tend to outperform long subtitled names
for indie games.
"""

# ---------------------------------------------------------------------------
# Image prompt generation
# ---------------------------------------------------------------------------

IMAGE_PROMPTS_PROMPT: str = """\
Generate detailed image-generation prompts (for Stable Diffusion, DALL-E, or
Midjourney) for the following game's Steam store assets.

GAME BRIEF:
{game_brief}

You must produce prompts for these exact Steam asset types with their required
aspect ratios and composition rules:

1. **capsule_main** (460x215 px, ~2.14:1 landscape)
   The primary capsule shown in search results and the store carousel.
   Requirements: game title/logo area centered, key art background that
   communicates genre at a glance, high contrast so it reads at thumbnail
   size.  Mood and colour palette must match the game's tone.

2. **capsule_small** (231x87 px, ~2.66:1 landscape)
   Appears in wishlists, recommendations.  Same composition as capsule_main
   but even simpler -- must read at very small size.  Bold silhouette, minimal
   detail, strong colour contrast.

3. **header_image** (460x215 px, exactly)
   The large image at the top of the store page.  This is KEY ART: no text,
   no logo.  A single striking scene that captures the game's essence.
   Cinematic composition, atmospheric lighting, strong focal point.

4. **library_hero** (3840x1240 px, ultra-wide ~3.1:1)
   The banner in the player's Steam library.  Ultra-wide cinematic panorama.
   Atmospheric, moody, can be more abstract/environmental than other assets.
   Needs to work with the game title overlaid on the left third.

5. **screenshot_1** (1920x1080 px, 16:9)
   A gameplay scene showing the core mechanic in action.  Should look like
   an actual screenshot, not concept art.  Include UI elements if relevant.

6. **screenshot_2** (1920x1080 px, 16:9)
   A different gameplay moment -- show variety.  Could be combat, exploration,
   a puzzle, dialogue, or building depending on the genre.

7. **screenshot_3** (1920x1080 px, 16:9)
   The most visually impressive scene.  This is the "wow" shot that makes
   people wishlist.  Dramatic lighting, scale, or an emotional moment.

Each prompt must specify: subject, composition, camera angle, lighting,
colour palette, art style, mood, and any negative prompts (what to avoid).

Return a JSON object:

{{
  "capsule_main": "<detailed prompt>",
  "capsule_small": "<detailed prompt>",
  "header_image": "<detailed prompt>",
  "library_hero": "<detailed prompt>",
  "screenshot_1": "<detailed prompt>",
  "screenshot_2": "<detailed prompt>",
  "screenshot_3": "<detailed prompt>"
}}
"""

# ---------------------------------------------------------------------------
# Tag optimisation prompt
# ---------------------------------------------------------------------------

TAGS_PROMPT: str = """\
Generate an optimised list of Steam tags for the following game.

GAME BRIEF:
{game_brief}

{trending_context}

Steam tag strategy:
- A game can have up to 20 user-defined tags, but the first 5 carry the most
  weight for the Discovery algorithm.
- Tags drive which queues and recommendations your game appears in.
- Balance between high-traffic tags (more impressions, more competition) and
  niche tags (fewer impressions, but higher conversion and relevance).
- The first tag should be the broadest genre tag (e.g., "Indie", "RPG",
  "Strategy").
- Tags 2-5 should be the most specific descriptors of your game's mechanics
  and feel.
- Tags 6-15 should cover secondary mechanics, themes, aesthetics, and
  audience (e.g., "Female Protagonist", "Pixel Graphics", "Relaxing").
- Tags 16-20 are long-tail / aspirational (e.g., "Hidden Gem", "Great
  Soundtrack").

Return a JSON object:

{{
  "tags": [
    "<tag1 -- highest priority>",
    "<tag2>",
    "..."
  ]
}}

Return exactly 20 tags sorted by priority (most important first).  Use
official Steam tag names (check against the trending data if provided).
"""

# ---------------------------------------------------------------------------
# Marketing hooks / elevator pitch prompt
# ---------------------------------------------------------------------------

MARKETING_PROMPT: str = """\
Generate marketing copy for the following game.

GAME BRIEF:
{game_brief}

{trending_context}

Produce:

1. **elevator_pitch**: A single sentence (max 140 characters) that a developer
   could use as their Twitter/X bio, Reddit flair, or Discord status.  Format:
   "[Game feel] meets [familiar reference] in a [unique twist]." or a
   similarly punchy structure.  Must be intriguing enough that someone clicks
   through to learn more.

2. **hooks**: 5 marketing hooks, each 1-2 sentences, for different contexts:
   - **steam_capsule**: Tagline for the capsule art (very short, fits on image)
   - **social_media**: A tweet/post that would make someone stop scrolling
   - **press_email**: Opening line of a press pitch email
   - **streamer_pitch**: Why a Twitch/YouTube creator should play this
   - **community_post**: First line of a devlog / community update

Return a JSON object:

{{
  "elevator_pitch": "<the pitch>",
  "hooks": [
    {{
      "context": "steam_capsule",
      "text": "<hook text>"
    }},
    {{
      "context": "social_media",
      "text": "<hook text>"
    }},
    {{
      "context": "press_email",
      "text": "<hook text>"
    }},
    {{
      "context": "streamer_pitch",
      "text": "<hook text>"
    }},
    {{
      "context": "community_post",
      "text": "<hook text>"
}}
"""

PROMPT_TEMPLATES: dict[str, str] = {
    "description": DESCRIPTION_PROMPT.replace("{game_brief}", "{brief}"),
    "titles": TITLES_PROMPT.replace("{game_brief}", "{brief}"),
    "image_prompts": IMAGE_PROMPTS_PROMPT.replace("{game_brief}", "{brief}"),
    "tags": TAGS_PROMPT.replace("{game_brief}", "{brief}"),
    "marketing": MARKETING_PROMPT.replace("{game_brief}", "{brief}"),
}


