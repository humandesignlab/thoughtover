"""Persona resolution and loading.

A persona is the *character* on top of the narration contract. Files are named
``personas/<name>.<lang>.md``. Private personas live in ``personas/local/``
(gitignored) and are selected exactly like any shipped preset; local files win
when a name collides, so you can shadow a shipped persona with your own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT

PERSONAS_DIR = REPO_ROOT / "personas"
LOCAL_DIR = PERSONAS_DIR / "local"


@dataclass(frozen=True)
class Persona:
    """A loaded persona file: who is speaking, in one language."""

    name: str
    lang: str
    path: Path
    text: str


class PersonaNotFoundError(FileNotFoundError):
    """Raised when no persona file matches the requested name and language."""

    def __init__(self, name: str, lang: str, available: list[str]) -> None:
        self.name = name
        self.lang = lang
        self.available = available
        wanted = f"{name}.{lang}.md"
        if available:
            options = ", ".join(available)
            hint = f"Available for --lang {lang}: {options}."
        else:
            hint = (
                f"No personas found for --lang {lang}. "
                f"Add personas/{name}.{lang}.md (or personas/local/{name}.{lang}.md)."
            )
        super().__init__(
            f"Persona '{name}' not found for language '{lang}' (looked for {wanted}).\n{hint}"
        )


def resolve_persona_path(name: str, lang: str) -> Path | None:
    """Return the path for ``<name>.<lang>.md``, preferring personas/local/."""
    filename = f"{name}.{lang}.md"
    for directory in (LOCAL_DIR, PERSONAS_DIR):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def available_personas(lang: str) -> list[str]:
    """Sorted, de-duplicated persona names available for a given language."""
    suffix = f".{lang}.md"
    names: set[str] = set()
    for directory in (PERSONAS_DIR, LOCAL_DIR):
        if not directory.is_dir():
            continue
        for path in directory.glob(f"*{suffix}"):
            names.add(path.name[: -len(suffix)])
    return sorted(names)


def load_persona(name: str, lang: str) -> Persona:
    """Load the persona file for ``name``/``lang`` or raise PersonaNotFoundError."""
    path = resolve_persona_path(name, lang)
    if path is None:
        raise PersonaNotFoundError(name, lang, available_personas(lang))
    return Persona(name=name, lang=lang, path=path, text=path.read_text(encoding="utf-8"))
