"""The "see and hear" stage: Gemini watches the clip, returns a beat sheet.

The clip goes to Gemini as native video, sampled above 1 FPS so fast descents
keep detail, with its audio track alongside the frames. Gemini returns a
language-neutral, timestamped beat sheet, never a narrating voice. The SDK is
imported lazily so the rest of the tool does not require it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .beats import Beat, beats_from_json
from .config import Config

_UPLOAD_POLL_SECONDS = 2.0
_UPLOAD_TIMEOUT_SECONDS = 300.0

BEATS_PROMPT = """\
You are watching a mountain-bike point-of-view trail clip, with its audio track.
Produce a timestamped beat sheet of what actually happens on the trail: what is
seen, and -- only when there is a genuinely useful sound cue -- what is heard.

Rules:
- Output a JSON array. Each beat is {"t": "mm:ss", "see": "...", "hear": "..."}.
  "hear" is optional: include it only for a meaningful, non-ambient sound cue
  (a brake, a skid, tires on gravel, a bird, a sudden gust). Omit it otherwise.
- "t" is the timestamp (mm:ss) measured from the start of the clip.
- Describe concretely and neutrally what happens: terrain, obstacles, line
  choices, riders, animals, scenery, effort. No narration, no first person, no
  opinions, no voice. This sheet is language-neutral and reused across languages.
- Treat speech as reliable; treat non-speech sound labels as approximate.
- Be selective. One beat per notable moment a rider would actually react to,
  not one per second. Prefer a sparse, high-signal sheet.

Return only the JSON array, ordered by time.
"""


def generate_beats(
    clip: Path,
    config: Config,
    *,
    log: Callable[[str], None] = print,
) -> list[Beat]:
    """Upload the clip, watch it above 1 FPS, and return the beat sheet."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.gemini_api_key)

    log(f"uploading {clip.name} to Gemini...")
    uploaded = client.files.upload(file=str(clip))

    waited = 0.0
    while uploaded.state.name == "PROCESSING":
        if waited >= _UPLOAD_TIMEOUT_SECONDS:
            raise TimeoutError("Gemini is still processing the upload after 5 minutes.")
        time.sleep(_UPLOAD_POLL_SECONDS)
        waited += _UPLOAD_POLL_SECONDS
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name != "ACTIVE":
        raise RuntimeError(f"Gemini upload failed (state={uploaded.state.name}).")

    log(f"watching at {config.gemini_video_fps} FPS with {config.gemini_model}...")
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(
                            file_uri=uploaded.uri,
                            mime_type=uploaded.mime_type,
                        ),
                        video_metadata=types.VideoMetadata(
                            fps=config.gemini_video_fps
                        ),
                    ),
                    types.Part(text=BEATS_PROMPT),
                ]
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[Beat],
                temperature=0.4,
            ),
        )
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

    parsed = response.parsed
    if parsed:
        return list(parsed)
    if response.text:
        return beats_from_json(response.text)
    raise RuntimeError("Gemini returned no beat sheet.")
