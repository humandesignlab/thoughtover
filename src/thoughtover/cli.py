"""Thoughtover command line: two commands, draft and render.

Phase 1 ships these as stubs. They already accept --lang and --persona, load
config from .env, resolve the persona, and run the same preflight checks the
real pipeline will, so missing keys or ffmpeg fail clearly today.

Core principle, enforced from the start: the agent drafts, you curate, your
voice speaks. ``render`` only ever voices the edited script file; it must never
auto-voice fresh model output.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from .config import MissingConfigError, load_config
from .personas import PersonaNotFoundError, load_persona
from .preflight import FfmpegMissingError, preflight_draft, preflight_render

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Turn a raw mountain bike clip into a video narrated in your cloned voice.",
)

LangOption = typer.Option("en", "--lang", help="Language code for the script and voicing.")
PersonaOption = typer.Option(
    "default", "--persona", help="Persona name, loads personas/<persona>.<lang>.md."
)
ClipArgument = typer.Argument(
    ...,
    exists=False,
    dir_okay=False,
    help="Path to the source clip.",
)


def _fail(message: str) -> NoReturn:
    """Print an error in red and exit non-zero."""
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _base_for(clip: Path, lang: str) -> tuple[Path, Path, Path]:
    """Derive the language-neutral beats path and the language-tagged outputs."""
    stem = clip.with_suffix("")
    beats = stem.with_suffix(".beats.json")
    script = Path(f"{stem}.{lang}.script.txt")
    narrated = Path(f"{stem}.{lang}.narrated.mp4")
    return beats, script, narrated


@app.command()
def draft(
    clip: Path = ClipArgument,
    lang: str = LangOption,
    persona: str = PersonaOption,
) -> None:
    """Draft an editable script from a clip (Gemini beats -> Claude thoughts).

    Stub for Phase 1: validates the environment and resolves the persona, then
    reports what it will produce. The real pipeline lands in Phase 2.
    """
    config = load_config()
    try:
        preflight_draft(config)
    except MissingConfigError as exc:
        _fail(str(exc))

    if not clip.is_file():
        _fail(f"Clip not found: {clip}")

    try:
        chosen = load_persona(persona, lang)
    except PersonaNotFoundError as exc:
        _fail(str(exc))

    beats, script, _ = _base_for(clip, lang)
    typer.echo(f"draft (stub): {clip}")
    typer.echo(f"  lang     : {lang}")
    typer.echo(f"  persona  : {chosen.name} ({chosen.path})")
    typer.echo(f"  gemini   : {config.gemini_model} @ {config.gemini_video_fps} FPS")
    typer.echo(f"  claude   : {config.anthropic_model}")
    typer.echo(f"  -> beats : {beats}  (language-neutral, shared)")
    typer.echo(f"  -> script: {script}  (you edit this)")
    typer.echo("draft pipeline not yet implemented (Phase 2).")


@app.command()
def render(
    clip: Path = ClipArgument,
    lang: str = LangOption,
    persona: str = PersonaOption,
) -> None:
    """Render the finished video from your edited script (ElevenLabs + ffmpeg).

    Stub for Phase 1. render only ever voices the edited script file; it never
    auto-voices fresh model output. The real pipeline lands in Phase 3.
    """
    config = load_config()
    try:
        preflight_render(config)
    except (FfmpegMissingError, MissingConfigError) as exc:
        _fail(str(exc))

    _, script, narrated = _base_for(clip, lang)
    if not script.is_file():
        _fail(
            f"Edited script not found: {script}\n"
            f"Run `thoughtover draft {clip} --lang {lang}` first, then edit the script."
        )

    typer.echo(f"render (stub): {clip}")
    typer.echo(f"  lang     : {lang}")
    typer.echo(f"  voice    : {config.elevenlabs_model} (voice id set)")
    typer.echo(f"  duck     : {config.narration_duck_db} dB under narration")
    typer.echo(f"  <- script: {script}  (the approved file, the only thing voiced)")
    typer.echo(f"  -> video : {narrated}")
    typer.echo("render pipeline not yet implemented (Phase 3).")


if __name__ == "__main__":
    app()
