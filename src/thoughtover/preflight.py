"""Startup checks: fail clearly and early when the environment is not ready.

``draft`` needs the Gemini and Claude keys. ``render`` needs the ElevenLabs key
and voice id, plus ffmpeg/ffprobe on PATH for placing, ducking, and muxing.
"""

from __future__ import annotations

import shutil

from .config import Config

FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


class FfmpegMissingError(RuntimeError):
    """Raised when ffmpeg (or ffprobe) is not available on PATH."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        tools = ", ".join(missing)
        super().__init__(
            f"Required tool(s) not found on PATH: {tools}.\n"
            "Install ffmpeg (it bundles ffprobe), e.g. `brew install ffmpeg` on macOS, "
            "then re-run."
        )


def check_ffmpeg() -> None:
    """Ensure ffmpeg and ffprobe are callable, or raise FfmpegMissingError."""
    missing = [tool for tool in FFMPEG_TOOLS if shutil.which(tool) is None]
    if missing:
        raise FfmpegMissingError(missing)


def preflight_draft(config: Config) -> None:
    """Validate everything the draft pipeline (Gemini + Claude) requires."""
    config.require("gemini_api_key", "anthropic_api_key")


def preflight_render(config: Config) -> None:
    """Validate everything the render pipeline (ElevenLabs + ffmpeg) requires."""
    check_ffmpeg()
    config.require("elevenlabs_api_key", "elevenlabs_voice_id")
