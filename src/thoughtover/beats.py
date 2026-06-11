"""The language-neutral beat sheet: what Gemini saw and heard.

A beat sheet describes what happens on the trail in no narrating voice, so it is
shared across languages (Gemini watches once). It is the seam that keeps a second
language cheap. Persisted as ``<clip>.beats.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class Beat(BaseModel):
    """One moment on the trail. ``hear`` is present only for a useful sound cue."""

    t: str
    see: str
    hear: str | None = None


_ADAPTER = TypeAdapter(list[Beat])


def write_beats(path: Path, beats: list[Beat]) -> None:
    """Serialize beats to JSON, dropping empty ``hear`` fields for a clean sheet."""
    data = [beat.model_dump(exclude_none=True) for beat in beats]
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_beats(path: Path) -> list[Beat]:
    """Load and validate a beat sheet from JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _ADAPTER.validate_python(raw)


def beats_from_json(text: str) -> list[Beat]:
    """Validate a beat sheet from a raw JSON string (model output)."""
    return _ADAPTER.validate_python(json.loads(text))


def beats_to_prompt_json(beats: list[Beat]) -> str:
    """Render the beat sheet as compact JSON for handing to the writer."""
    data = [beat.model_dump(exclude_none=True) for beat in beats]
    return json.dumps(data, ensure_ascii=False, indent=2)
