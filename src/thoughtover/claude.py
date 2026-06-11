"""The "write" stage: Claude turns beats into thoughts in the persona's voice.

The beat sheet, the tool's narration contract, and the selected persona go to
Claude, which writes sparse, first-person, timestamped thoughts. Languages are
regenerated, not translated: the same character thinks natively in the target
language, with the landings re-found. The SDK is imported lazily.
"""

from __future__ import annotations

from collections.abc import Callable

from .beats import Beat, beats_to_prompt_json
from .config import Config
from .contract import NARRATION_CONTRACT
from .personas import Persona

_MAX_TOKENS = 2000

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
}


def _language_name(lang: str) -> str:
    return LANGUAGE_NAMES.get(lang, lang)


def _system_prompt(persona: Persona, lang: str) -> str:
    language = _language_name(lang)
    return (
        f"{NARRATION_CONTRACT}\n\n"
        "# Persona (the character speaking)\n\n"
        f"{persona.text}\n\n"
        "# Language\n\n"
        f"Write every thought in {language}. Do not translate from another "
        f"language; think natively in {language} and re-find the landings so the "
        "timing stays alive."
    )


def _user_prompt(beats: list[Beat]) -> str:
    return (
        "Here is the language-neutral beat sheet for the clip (JSON). Each beat is "
        "a moment on the trail.\n\n"
        f"{beats_to_prompt_json(beats)}\n\n"
        "Write the rider's inner thoughts as the thoughts laid over this footage: "
        "sparse, first-person, present-tense, in the persona's voice. Format each "
        "as `[mm:ss] thought`, one per line. Use only timestamps drawn from the "
        "beats above. Most beats should get no line at all -- silence is good, a "
        "line must feel earned. Do not describe or narrate the footage, and never "
        "name a sound. Output only the lines, nothing else."
    )


def write_thoughts(
    beats: list[Beat],
    persona: Persona,
    lang: str,
    config: Config,
    *,
    log: Callable[[str], None] = print,
) -> str:
    """Draft the script text (raw `[mm:ss] thought` lines) for the given beats."""
    from anthropic import Anthropic

    client = Anthropic(api_key=config.anthropic_api_key)
    log(f"writing thoughts with {config.anthropic_model} as persona '{persona.name}'...")
    message = client.messages.create(
        model=config.anthropic_model,
        max_tokens=_MAX_TOKENS,
        system=_system_prompt(persona, lang),
        messages=[{"role": "user", "content": _user_prompt(beats)}],
    )
    return "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
