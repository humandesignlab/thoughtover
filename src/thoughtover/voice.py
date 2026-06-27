"""The "voice" stage: ElevenLabs speaks each approved line in your cloned voice.

This only ever voices the lines handed to it (the curated script). It never sees
model output directly. Each language can use its own cloned voice id from config.
The SDK is imported lazily.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import Config
from .script import ScriptLine

_OUTPUT_FORMAT = "mp3_44100_128"


def voice_lines(
    lines: list[ScriptLine],
    config: Config,
    out_dir: Path,
    lang: str,
    *,
    log: Callable[[str], None] = print,
) -> list[Path]:
    """Voice each script line to an mp3 in ``out_dir``, returning the file paths."""
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs

    voice_id = config.voice_id_for(lang)
    client = ElevenLabs(api_key=config.elevenlabs_api_key)
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = VoiceSettings(
        stability=config.narration_stability,
        similarity_boost=config.narration_similarity,
        style=config.narration_style,
        use_speaker_boost=config.narration_speaker_boost,
        speed=config.narration_speed,
    )

    paths: list[Path] = []
    total = len(lines)
    for index, line in enumerate(lines):
        log(f"voicing {index + 1}/{total}: [{line.t}] {line.text}")
        if config.elevenlabs_model == "eleven_v3" and "[" in line.text:
            log(
                "  (v3: inline tags — emotion, [strong X accent], pauses — "
                "passed through to the model)"
            )
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=config.elevenlabs_model,
            text=line.text,
            output_format=_OUTPUT_FORMAT,
            voice_settings=settings,
        )
        path = out_dir / f"{index:03d}.mp3"
        with open(path, "wb") as handle:
            for chunk in audio:
                if chunk:
                    handle.write(chunk)
        paths.append(path)
    return paths
