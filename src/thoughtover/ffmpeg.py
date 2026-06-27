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


@dataclass(frozen=True)
class MixSettings:
    """Every audio/sound-design knob for a render, bundled for the assembler."""

    duck_db: float
    narration_gain_db: float
    duck_fade: float
    inner_voice: bool
    inner_voice_reverb: float
    ambience_highpass_hz: float
    ambience_carve_db: float
    loudnorm: bool
    output_lufs: float
    output_true_peak: float


# The MP4 muxer stores stream language as ISO 639-2 (three letters); 2-letter
# codes are silently dropped. Map the ones we ship and fall back to the input.
_ISO639_2 = {"en": "eng", "es": "spa"}


def _iso639_2(lang: str) -> str:
    return _ISO639_2.get(lang, lang)


def _db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _inner_voice_chain(reverb: float) -> str:
    """ASMR-ish "inside the head" treatment: warm, close, dark, softly compressed.

    Proximity = low-mid body + strong de-airing (not "in the room"). Gentle
    compression keeps whispers and sighs intact. ``reverb`` (0..1) adds a short
    low mental slap; 0 stays bone-conduction dry.
    """
    chain = [
        "highpass=f=80",
        "equalizer=f=160:width_type=q:w=0.9:g=3.5",
        "equalizer=f=320:width_type=q:w=1.2:g=1.5",
        "treble=g=-6:f=4000",
        "acompressor=threshold=-22dB:ratio=2:attack=3:release=200:makeup=2",
    ]
    r = max(0.0, min(reverb, 1.0))
    if r > 0:
        wet = 0.85 + r * 0.15
        chain.append(
            f"aecho=in_gain=1:out_gain={wet:.2f}:delays=42|68:"
            f"decays={r * 0.45:.3f}|{r * 0.28:.3f}"
        )
    return ",".join(chain)


def _ambience_highpass(highpass_hz: float) -> str:
    """Clear subsonic rumble from the trail bed."""
    if highpass_hz and highpass_hz > 0:
        return f"highpass=f={highpass_hz:.0f}"
    return ""


def _speech_windows(segments: list[Segment], fade: float) -> list[tuple[float, float]]:
    """Time ranges (with fade padding) where narration is active."""
    windows: list[tuple[float, float]] = []
    for s in segments:
        start = max(0.0, s.start - fade)
        end = s.start + s.duration + fade
        windows.append((start, end))
    return windows


def _apply_dynamic_carve(
    filters: list[str],
    input_label: str,
    output_label: str,
    segments: list[Segment],
    carve_db: float,
    fade: float,
) -> None:
    """Carve a voice pocket in the bed midrange, only while narration is active."""
    if not carve_db or carve_db >= 0 or not segments:
        filters.append(f"[{input_label}]anull[{output_label}]")
        return
    current = input_label
    for si, (start, end) in enumerate(_speech_windows(segments, fade)):
        step = f"{output_label}_c{si}"
        filters.append(
            f"[{current}]equalizer=f=2000:width_type=q:w=1.2:g={carve_db:.2f}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{step}]"
        )
        current = step
    if current != output_label:
        filters.append(f"[{current}]anull[{output_label}]")


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
    mix: MixSettings,
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

    duck = _db_to_gain(mix.duck_db)
    narration_gain = _db_to_gain(mix.narration_gain_db)
    inner = _inner_voice_chain(mix.inner_voice_reverb) if mix.inner_voice else ""
    mixed_labels: list[str] = []
    metadata: list[str] = []
    for ti, track in enumerate(tracks):
        # Trail bed ONLY: high-pass, timed mid carve (voice pocket), duck envelope.
        # Never run _inner_voice_chain on the bed — that chain is narration-only.
        bed_in = bases[ti]
        hp = _ambience_highpass(mix.ambience_highpass_hz)
        if hp:
            bed_hp = f"bed{ti}_hp"
            filters.append(f"[{bed_in}]{hp}[{bed_hp}]")
            bed_in = bed_hp
        bed_carved = f"bed{ti}"
        _apply_dynamic_carve(
            filters, bed_in, bed_carved, track.segments, mix.ambience_carve_db, mix.duck_fade
        )
        ducked = f"ducked{ti}"
        expr = _duck_expr(track.segments, duck, mix.duck_fade)
        if expr is not None:
            filters.append(f"[{bed_carved}]volume=eval=frame:volume='{expr}'[{ducked}]")
        else:
            filters.append(f"[{bed_carved}]anull[{ducked}]")

        # Each voiced line: inner-voice treatment, place at its time, set level.
        delayed: list[str] = []
        for si, segment in enumerate(track.segments):
            delay_ms = int(round(segment.start * 1000))
            label = f"d{ti}_{si}"
            seg_parts: list[str] = []
            if inner:
                seg_parts.append(inner)
            seg_parts.append(f"adelay={delay_ms}:all=1")
            seg_parts.append("afade=t=in:st=0:d=0.07")
            seg_parts.append(f"volume={narration_gain:.4f}")
            filters.append(f"[{segment_input[(ti, si)]}:a]{','.join(seg_parts)}[{label}]")
            delayed.append(f"[{label}]")

        mixed = f"mixed{ti}"
        mix_inputs = f"[{ducked}]" + "".join(delayed)
        filters.append(
            f"{mix_inputs}amix=inputs={1 + len(delayed)}:duration=first:normalize=0[{mixed}]"
        )
        mixed_labels.append(mixed)
        metadata += [f"-metadata:s:a:{ti}", f"language={_iso639_2(track.lang)}"]

    return inputs, ";".join(filters), mixed_labels, metadata


def _parse_loudnorm_json(stderr: str) -> dict[str, str]:
    """Extract the loudnorm measurement JSON block from ffmpeg stderr."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("loudnorm measurement failed: no JSON in ffmpeg output")
    return json.loads(stderr[start : end + 1])


def _measure_loudnorm(
    inputs: list[str],
    filter_complex: str,
    mixed_label: str,
    mix: MixSettings,
) -> dict[str, str]:
    """Pass 1: measure integrated loudness so pass 2 can hit the target precisely."""
    measure = (
        f"[{mixed_label}]loudnorm=I={mix.output_lufs:.1f}:TP={mix.output_true_peak:.1f}:"
        f"LRA=11:print_format=json[fnull]"
    )
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", f"{filter_complex};{measure}",
        "-map", "[fnull]", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return _parse_loudnorm_json(result.stderr)


def _loudnorm_apply(
    mixed_label: str, out_label: str, mix: MixSettings, measured: dict[str, str]
) -> str:
    """Pass 2: apply loudnorm with measured values for accurate targeting."""
    return (
        f"[{mixed_label}]loudnorm=I={mix.output_lufs:.1f}:TP={mix.output_true_peak:.1f}:LRA=11:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true[{out_label}]"
    )


def assemble(
    clip: Path,
    tracks: list[NarrationTrack],
    output: Path,
    mix: MixSettings,
    *,
    log: Callable[[str], None] = print,
) -> Path:
    """Render the narrated video: video copied, narration placed over ducked audio."""
    video_duration = probe_duration(clip)
    inputs, filter_complex, mixed_labels, metadata = _build(
        clip, tracks, mix, video_duration
    )

    if mix.loudnorm and mixed_labels:
        loudnorm_filters: list[str] = []
        out_labels: list[str] = []
        for ti, mixed in enumerate(mixed_labels):
            measured = _measure_loudnorm(inputs, filter_complex, mixed, mix)
            log(
                f"loudnorm pass 1 (track {ti}): measured {measured.get('input_i')} LUFS "
                f"(target {mix.output_lufs})"
            )
            aout = f"aout{ti}"
            loudnorm_filters.append(_loudnorm_apply(mixed, aout, mix, measured))
            out_labels.append(aout)
        filter_complex = filter_complex + ";" + ";".join(loudnorm_filters)
    else:
        out_labels = mixed_labels

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
