"""Thoughtover command line: two commands, draft and render.

``draft`` runs the hybrid pipeline (Gemini beats -> Claude thoughts) and writes
an editable script. ``render`` is still a Phase 3 stub.

Core principle, enforced from the start: the agent drafts, you curate, your
voice speaks. ``render`` only ever voices the edited script file; it must never
auto-voice fresh model output.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from .beats import read_beats, write_beats
from .config import MissingConfigError, load_config
from .personas import PersonaNotFoundError, load_persona
from .preflight import FfmpegMissingError, preflight_draft, preflight_render
from .script import parse_script, write_script_file

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
    refresh_beats: bool = typer.Option(
        False,
        "--refresh-beats",
        help="Re-watch the clip with Gemini even if a beat sheet already exists.",
    ),
) -> None:
    """Draft an editable script from a clip (Gemini beats -> Claude thoughts).

    Gemini watches the clip once into a language-neutral beat sheet, then Claude
    writes the thoughts from that sheet using the narration contract and the
    selected persona. You then edit the script before rendering.
    """
    from .claude import write_thoughts
    from .gemini import generate_beats

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

    beats_path, script_path, _ = _base_for(clip, lang)

    try:
        if beats_path.is_file() and not refresh_beats:
            typer.echo(f"reusing beat sheet: {beats_path} (pass --refresh-beats to re-watch)")
            beats = read_beats(beats_path)
        else:
            beats = generate_beats(clip, config, log=typer.echo)
            write_beats(beats_path, beats)
            typer.echo(f"wrote beat sheet: {beats_path} ({len(beats)} beats)")

        raw = write_thoughts(beats, chosen, lang, config, log=typer.echo)
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a traceback
        _fail(f"draft failed: {exc}")

    lines = parse_script(raw)
    if not lines:
        _fail(
            "The writer returned no usable `[mm:ss] thought` lines.\n"
            "Re-run, or try a different --persona."
        )

    write_script_file(script_path, lines, clip_name=clip.name, lang=lang)
    typer.echo(f"wrote script: {script_path} ({len(lines)} lines)")
    typer.secho(
        f"Now edit {script_path}, then run `thoughtover render {clip} --lang {lang}`.",
        fg=typer.colors.GREEN,
    )


@app.command()
def render(
    clip: Path = ClipArgument,
    lang: str = LangOption,
    persona: str = PersonaOption,
    reuse_voices: bool = typer.Option(
        False,
        "--reuse-voices",
        help="Reuse already-voiced lines if present (skip ElevenLabs). For tuning the mix/timing without re-billing TTS; only safe when the script is unchanged.",
    ),
) -> None:
    """Render the finished video from your edited script (ElevenLabs + ffmpeg).

    Voices exactly the lines in the edited ``<clip>.<lang>.script.txt`` -- never
    fresh model output -- then places each line a beat after its timestamp,
    ducks the trail audio underneath, and muxes to ``<clip>.<lang>.narrated.mp4``.
    """
    from .render import render as run_render

    config = load_config()
    try:
        preflight_render(config)
    except (FfmpegMissingError, MissingConfigError) as exc:
        _fail(str(exc))

    if not clip.is_file():
        _fail(f"Clip not found: {clip}")

    _, script_path, narrated = _base_for(clip, lang)
    if not script_path.is_file():
        _fail(
            f"Edited script not found: {script_path}\n"
            f"Run `thoughtover draft {clip} --lang {lang}` first, then edit the script."
        )

    lines = parse_script(script_path.read_text(encoding="utf-8"))
    if not lines:
        _fail(f"No `[mm:ss] thought` lines found in {script_path}.")

    narration_dir = Path(f"{clip.with_suffix('')}.{lang}.narration")
    typer.echo(f"voicing {len(lines)} lines from {script_path} ({config.elevenlabs_model})")
    try:
        out = run_render(
            clip, lines, lang, narrated, narration_dir, config,
            reuse_voices=reuse_voices, log=typer.echo,
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a traceback
        _fail(f"render failed: {exc}")

    typer.secho(f"Done. Wrote {out}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
