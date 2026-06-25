"""Render orchestration: voice the approved script, then place, duck, and mux.

This consumes only the curated script lines passed to it. Each thought lands a
beat after its event (the reaction lag), so it reads like the rider realizing
something rather than narrating in lockstep. Overlap handling is the v1 shortcut
from the spec: if a line would start before the previous one finishes, nudge it
a touch later rather than mixing two voices on top of each other.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import Config
from .ffmpeg import MixSettings, NarrationTrack, Segment, assemble, probe_duration
from .script import ScriptLine
from .voice import voice_lines

OVERLAP_GAP_SECONDS = 0.12


def plan_segments(
    lines: list[ScriptLine], audio_paths: list[Path], reaction_lag: float = 0.0
) -> list[Segment]:
    """Place each voiced line a beat after its timestamp, nudging off overlaps."""
    items = sorted(
        zip(lines, audio_paths, strict=True), key=lambda pair: pair[0].seconds
    )
    segments: list[Segment] = []
    previous_end = 0.0
    for line, path in items:
        duration = probe_duration(path)
        start = line.seconds + reaction_lag
        if start < previous_end + OVERLAP_GAP_SECONDS:
            start = previous_end + OVERLAP_GAP_SECONDS
        segments.append(Segment(path=path, start=start, duration=duration))
        previous_end = start + duration
    return segments


def _existing_voices(narration_dir: Path, count: int) -> list[Path] | None:
    """Return the already-voiced mp3s if all are present, else None."""
    paths = [narration_dir / f"{i:03d}.mp3" for i in range(count)]
    return paths if all(p.is_file() for p in paths) else None


def render(
    clip: Path,
    lines: list[ScriptLine],
    lang: str,
    output: Path,
    narration_dir: Path,
    config: Config,
    *,
    reuse_voices: bool = False,
    log: Callable[[str], None] = print,
) -> Path:
    """Voice the lines, plan their placement, and assemble the narrated video."""
    audio_paths = _existing_voices(narration_dir, len(lines)) if reuse_voices else None
    if audio_paths is not None:
        log(f"reusing {len(audio_paths)} voiced lines from {narration_dir}")
    else:
        audio_paths = voice_lines(lines, config, narration_dir, lang, log=log)

    segments = plan_segments(lines, audio_paths, config.narration_reaction_lag)
    track = NarrationTrack(lang=lang, segments=segments)
    mix = MixSettings(
        duck_db=config.narration_duck_db,
        narration_gain_db=config.narration_gain_db,
        duck_fade=config.narration_duck_fade,
        inner_voice=config.narration_inner_voice,
        inner_voice_reverb=config.narration_inner_voice_reverb,
        ambience_highpass_hz=config.ambience_highpass_hz,
        ambience_carve_db=config.ambience_carve_db,
        loudnorm=config.loudnorm,
        output_lufs=config.output_lufs,
        output_true_peak=config.output_true_peak,
    )
    return assemble(clip, [track], output, mix, log=log)
