"""ffmpeg assembly: place each narration line, duck the trail audio, and mux.

Narration is modeled as a list of audio tracks even when there is only one, so a
second language is appended rather than retrofitted. Each track becomes one
audio stream in the output, tagged with its language. Under each narration line
the original trail audio is ducked by ``duck_db`` decibels.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    """One voiced line: an audio file placed at ``start`` seconds for ``duration``."""

    path: Path
    start: float
    duration: float


@dataclass(frozen=True)
class NarrationTrack:
    """All voiced lines for one language."""

    lang: str
    segments: list[Segment]


# The MP4 muxer stores stream language as ISO 639-2 (three letters); 2-letter
# codes are silently dropped. Map the ones we ship and fall back to the input.
_ISO639_2 = {"en": "eng", "es": "spa"}


def _iso639_2(lang: str) -> str:
    return _ISO639_2.get(lang, lang)


def _db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _duck_expr(segments: list[Segment], duck_gain: float, fade: float) -> str | None:
    """Build a time-varying volume expression that eases the trail down and back.

    Each narration line gets a trapezoid envelope: ramp from full down to
    ``duck_gain`` over ``fade`` seconds before it starts, hold while it plays,
    then ramp back up over ``fade`` seconds after it ends. The overall gain is
    the minimum across lines, so the trail stays ducked through close lines
    instead of bouncing up between them.
    """
    if not segments:
        return None
    d = duck_gain
    terms: list[str] = []
    for s in segments:
        a = s.start - fade            # start easing down
        b = s.start                   # fully ducked
        c = s.start + s.duration      # line ends, start easing up
        e = c + fade                  # back to full
        terms.append(
            f"if(between(t,{a:.3f},{b:.3f}),1-(1-{d:.4f})*(t-{a:.3f})/{fade:.3f},"
            f"if(between(t,{b:.3f},{c:.3f}),{d:.4f},"
            f"if(between(t,{c:.3f},{e:.3f}),{d:.4f}+(1-{d:.4f})*(t-{c:.3f})/{fade:.3f},1)))"
        )
    expr = terms[0]
    for term in terms[1:]:
        expr = f"min({expr},{term})"
    return expr


def probe_duration(path: Path) -> float:
    """Return media duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _has_audio(path: Path) -> bool:
    """Whether the file has at least one audio stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(json.loads(result.stdout).get("streams"))


def _build(
    clip: Path,
    tracks: list[NarrationTrack],
    duck_db: float,
    narration_gain_db: float,
    duck_fade: float,
    video_duration: float,
) -> tuple[list[str], str, list[str], list[str]]:
    """Assemble ffmpeg inputs, the filter_complex, the output maps, and metadata."""
    inputs: list[str] = ["-i", str(clip)]
    next_index = 1

    if _has_audio(clip):
        original = "0:a"
    else:
        inputs += [
            "-f", "lavfi",
            "-t", f"{video_duration:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]
        original = f"{next_index}:a"
        next_index += 1

    segment_input: dict[tuple[int, int], int] = {}
    for ti, track in enumerate(tracks):
        for si, segment in enumerate(track.segments):
            inputs += ["-i", str(segment.path)]
            segment_input[(ti, si)] = next_index
            next_index += 1

    filters: list[str] = []
    if len(tracks) == 1:
        bases = [original]
    else:
        labels = "".join(f"[base{ti}]" for ti in range(len(tracks)))
        filters.append(f"[{original}]asplit={len(tracks)}{labels}")
        bases = [f"base{ti}" for ti in range(len(tracks))]

    duck = _db_to_gain(duck_db)
    narration_gain = _db_to_gain(narration_gain_db)
    out_labels: list[str] = []
    metadata: list[str] = []
    for ti, track in enumerate(tracks):
        ducked = f"ducked{ti}"
        expr = _duck_expr(track.segments, duck, duck_fade)
        if expr is None:
            filters.append(f"[{bases[ti]}]anull[{ducked}]")
        else:
            filters.append(f"[{bases[ti]}]volume=eval=frame:volume='{expr}'[{ducked}]")

        delayed: list[str] = []
        for si, segment in enumerate(track.segments):
            delay_ms = int(round(segment.start * 1000))
            label = f"d{ti}_{si}"
            filters.append(
                f"[{segment_input[(ti, si)]}:a]adelay={delay_ms}:all=1,"
                f"volume={narration_gain:.4f}[{label}]"
            )
            delayed.append(f"[{label}]")

        aout = f"aout{ti}"
        mix_inputs = f"[{ducked}]" + "".join(delayed)
        filters.append(
            f"{mix_inputs}amix=inputs={1 + len(delayed)}:duration=first:normalize=0[{aout}]"
        )
        out_labels.append(aout)
        metadata += [f"-metadata:s:a:{ti}", f"language={_iso639_2(track.lang)}"]

    return inputs, ";".join(filters), out_labels, metadata


def assemble(
    clip: Path,
    tracks: list[NarrationTrack],
    output: Path,
    duck_db: float,
    narration_gain_db: float,
    duck_fade: float,
    *,
    log: Callable[[str], None] = print,
) -> Path:
    """Render the narrated video: video copied, narration placed over ducked audio."""
    video_duration = probe_duration(clip)
    inputs, filter_complex, out_labels, metadata = _build(
        clip, tracks, duck_db, narration_gain_db, duck_fade, video_duration
    )

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "0:v"]
    for label in out_labels:
        cmd += ["-map", f"[{label}]"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", *metadata, "-shortest", str(output)]

    log("assembling with ffmpeg (place, duck, mux)...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-12:]
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(tail)) from exc
    return output
