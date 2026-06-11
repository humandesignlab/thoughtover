"""The editable script: ``[mm:ss] thought`` lines, one per line.

This is the file you curate by hand between ``draft`` and ``render``. Blank
lines and lines starting with ``#`` are ignored, so you can leave yourself
notes. Persisted as ``<clip>.<lang>.script.txt``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

LINE_RE = re.compile(r"^\[(\d{1,3}:[0-5]\d)\]\s*(.+?)\s*$")


@dataclass(frozen=True)
class ScriptLine:
    """A single narrated thought, placed at a timestamp."""

    t: str
    text: str

    def render(self) -> str:
        return f"[{self.t}] {self.text}"


def parse_script(text: str) -> list[ScriptLine]:
    """Parse script text into lines, ignoring blanks, comments, and stray prose.

    Only well-formed ``[mm:ss] thought`` lines are kept, so this tolerates model
    output that wraps the lines in explanation.
    """
    lines: list[ScriptLine] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RE.match(stripped)
        if match:
            lines.append(ScriptLine(t=match.group(1), text=match.group(2)))
    return lines


def _header(clip_name: str, lang: str) -> str:
    return (
        f"# {clip_name} - {lang} script. Drafted by the agent; edit before you render.\n"
        "# One '[mm:ss] thought' per line. Blank lines and '#' lines are ignored.\n"
        "# render voices exactly these lines in your cloned voice - nothing else.\n"
    )


def write_script_file(
    path: Path, lines: list[ScriptLine], *, clip_name: str, lang: str
) -> None:
    """Write the editable script with a short header reminding you to curate it."""
    body = "\n".join(line.render() for line in lines)
    path.write_text(_header(clip_name, lang) + "\n" + body + "\n", encoding="utf-8")
