"""The "write" stage: Claude turns beats into v3-ready script lines.

Claude writes sparse, first-person thoughts **and** performs the ElevenLabs UI
"Enhance" step: inline ``[audio tags]`` for eleven_v3 delivery without changing
the spoken words. The beat sheet, narration contract, and persona go to Claude.
Languages are regenerated, not translated. The SDK is imported lazily.
"""

from __future__ import annotations

from collections.abc import Callable

from .beats import Beat, beats_to_prompt_json
from .config import Config
from .contract import NARRATION_CONTRACT
from .personas import Persona

_MAX_TOKENS = 2000

_V3_TAGS = (
    " You are also doing ElevenLabs v3 'Enhance': prepend [audio tags] to the "
    "spoken text for delivery -- do not alter the words themselves (only tags, "
    "punctuation, emphasis). Be generous with tags; they are the delivery. "
    "Combine multiple tags per line (accent + emotion + body) when the thought "
    "shifts register; experiment with combinations. Match tags to the clone's "
    "character -- a dry/carrilla inner voice fits [dry] [sarcastic] [annoyed] "
    "[resigned] [sighs] [snorts] better than cartoon [giggles] unless the voice "
    "supports it. Text structure matters strongly in v3: write spoken natural "
    "speech, short clauses, clear punctuation between tagged segments (period "
    "before each new tag block). Example: [strong Mexican accent] [annoyed] esa "
    "sombra va a madre. [sighs] yo aquí bofeando. Almost every line needs tags; "
    "aim for 16-24 tags in a short script. Tags in square brackets; spoken text "
    "otherwise."
)

_V3_ACCENT_ES = (
    " Jacobo (Spanish): start every line with [strong Mexican accent] or "
    "[strong northern Mexican accent] before emotion tags; at most one line per "
    "script may use [strong Mexico City accent] for the chilango 20% leak."
)

_ANTI_RECAP = (
    " CRITICAL anti-redundancy (same rule as English Nate): never recap the "
    "footage or state the obvious — the viewer already saw it. Do NOT describe "
    "what is on screen (dogs, shadow, lake view, fork, uphill, rocks, runner, "
    "'buenos días', scenery). Do NOT echo beat-sheet words. Skip the event; "
    "land the take about YOU — your body, your mistake, food, garage, social "
    "debt, stray memory. If the first half of a line could be a caption for the "
    "clip, rewrite it."
)

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


def _user_prompt(beats: list[Beat], lang: str) -> str:
    native = ""
    if lang == "es":
        native = (
            " Write native Spanish inner monologue with the persona's specific life "
            "context (place, food, body, identity) -- never a translation of how an "
            "English line would say the same beat. Do not reuse template phrases or "
            "copy example lines from the persona file verbatim. Vary wording across "
            "lines. Mix reactive lines with stray thoughts not tied to what is on "
            "screen (food, music hum, garage, family texture, random opinions). "
            "Avoid a mechanical beat-by-beat commentary script. "
            "Use Chihuahua/northern Mexican slang (chihuahuismos): va a madre, la "
            "regué, la neta, nomás, cañón, gacho, reburujado, bofeando, ay ay — not "
            "neutral textbook Spanish. hecho la mocha = fast (not tired). "
            "petatearse = die (not tired). bofeando = out of breath on effort. "
            "ay ay ONLY when something does not add up, is exaggerated, or not "
            "credible -- never for trash or physical mess (use qué gacho or pinchi "
            "cochinero). reburujado = confusion in head or situation (wrong fork, "
            "mixed up) -- never for items or litter. "
            "At most ONE food/casa stray line per script; do not default to menudo "
            "de la suegra -- rotate troquita, Scout, body, music hum, burrito, "
            "asadero, pastor, desk-week texture. "
            "Rarely weave one Mexican refran (dicho) per short script when it lands "
            "ironically on your situation -- not a moral lecture (pool in persona: "
            "no por mucho madrugar, mas vale mana que fuerza, camaron que se duerme, "
            "del plato a la boca, salio mas caro el caldo, se me junto el lavado, "
            "de lengua me como un taco, si son peras me las como, al buen entendedor, "
            "zapatero a tus zapatos, perro que ladra, etc.). "
            "0-1 per script; never stack with another punchline. Never ay Chihuahua. "
            "Use natural groserias for flavor (1-3 lines per short script), never as "
            "insults. Prefer short northern bursts: no mames, pinchi/pinche + thing "
            "(pinchi subida!), al tiro (Gen-X -- feeling sharp/on point), jodido or "
            "bofeado (exhausted), pendejada (absurd situation). bien verga = sharp as "
            "hell -- use very rarely. a la verga ONLY as imperative + a la verga, always "
            "to yourself (callate/sacate/vete/sientate, a la verga -- dismissive punchline "
            "at your own whine or head noise); never as state (hoy ando bien a la verga). "
            "Never pendejo/cabron as insult. Not PG. "
            f"{_V3_TAGS}{_V3_ACCENT_ES}{_ANTI_RECAP}\n\n"
        )
    return (
        "Here is the language-neutral beat sheet for the clip (JSON). Each beat is "
        "a moment on the trail.\n\n"
        f"{beats_to_prompt_json(beats)}\n\n"
        f"{native}"
        f"{_V3_TAGS if native == '' else ''}"
        f"{_ANTI_RECAP if native == '' else ''}"
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
        messages=[{"role": "user", "content": _user_prompt(beats, lang)}],
    )
    return "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
