"""Render orchestration: voice the approved script, then place, duck, and mux.

This consumes only the curated script lines passed to it. Overlap handling is
the v1 shortcut from the spec: if a line would start before the previous one
finishes, nudge it a touch later rather than mixing two voices on top of
each other.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import Config
from .ffmpeg import NarrationTrack, Segment, assemble, probe_duration
from .script import ScriptLine
from .voice import voice_lines

OVERLAP_GAP_SECONDS = 0.12


def plan_segments(lines: list[ScriptLine], audio_paths: list[Path]) -> list[Segment]:
    """Place each voiced line at its timestamp, nudging later lines off overlaps."""
    items = sorted(
        zip(lines, audio_paths, strict=True), key=lambda pair: pair[0].seconds
    )
    segments: list[Segment] = []
    previous_end = 0.0
    for line, path in items:
        duration = probe_duration(path)
        start = line.seconds
        if start < previous_end + OVERLAP_GAP_SECONDS:
            start = previous_end + OVERLAP_GAP_SECONDS
        segments.append(Segment(path=path, start=start, duration=duration))
        previous_end = start + duration
    return segments


def render(
    clip: Path,
    lines: list[ScriptLine],
    lang: str,
    output: Path,
    narration_dir: Path,
    config: Config,
    *,
    log: Callable[[str], None] = print,
) -> Path:
    """Voice the lines, plan their placement, and assemble the narrated video."""
    audio_paths = voice_lines(lines, config, narration_dir, log=log)
    segments = plan_segments(lines, audio_paths)
    track = NarrationTrack(lang=lang, segments=segments)
    return assemble(clip, [track], output, config.narration_duck_db, log=log)
