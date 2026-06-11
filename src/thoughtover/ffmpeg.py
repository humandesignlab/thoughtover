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


def _duck_gain(duck_db: float) -> float:
    return 10.0 ** (duck_db / 20.0)


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
    clip: Path, tracks: list[NarrationTrack], duck_db: float, video_duration: float
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

    gain = _duck_gain(duck_db)
    out_labels: list[str] = []
    metadata: list[str] = []
    for ti, track in enumerate(tracks):
        ducks = [
            f"volume=enable='between(t,{s.start:.3f},{s.start + s.duration:.3f})'"
            f":volume={gain:.4f}"
            for s in track.segments
        ]
        ducked = f"ducked{ti}"
        filters.append(f"[{bases[ti]}]{','.join(ducks) if ducks else 'anull'}[{ducked}]")

        delayed: list[str] = []
        for si, segment in enumerate(track.segments):
            delay_ms = int(round(segment.start * 1000))
            label = f"d{ti}_{si}"
            filters.append(
                f"[{segment_input[(ti, si)]}:a]adelay={delay_ms}:all=1[{label}]"
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
    *,
    log: Callable[[str], None] = print,
) -> Path:
    """Render the narrated video: video copied, narration placed over ducked audio."""
    video_duration = probe_duration(clip)
    inputs, filter_complex, out_labels, metadata = _build(
        clip, tracks, duck_db, video_duration
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
