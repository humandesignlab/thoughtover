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
_GENERATE_MAX_ATTEMPTS = 5
_GENERATE_RETRY_BASE_SECONDS = 8.0


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    """True for transient capacity/rate-limit failures from the Gemini API."""
    code = getattr(exc, "code", None)
    if code in {429, 500, 503, 504}:
        return True
    message = str(exc).upper()
    return "UNAVAILABLE" in message or "RESOURCE_EXHAUSTED" in message or "503" in message


def _generate_with_retry(
    client: object,
    *,
    model: str,
    contents: object,
    config: object,
    log: Callable[[str], None],
) -> object:
    """Call generate_content with backoff on transient Gemini failures."""
    last: BaseException | None = None
    for attempt in range(1, _GENERATE_MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            if not _is_retryable_gemini_error(exc) or attempt >= _GENERATE_MAX_ATTEMPTS:
                raise
            last = exc
            wait = _GENERATE_RETRY_BASE_SECONDS * attempt
            log(
                f"Gemini busy ({exc}); retrying in {wait:.0f}s "
                f"(attempt {attempt}/{_GENERATE_MAX_ATTEMPTS})..."
            )
            time.sleep(wait)
    assert last is not None
    raise last

BEATS_PROMPT = """\
You are watching a mountain-bike point-of-view trail clip, with its audio track.
Produce a timestamped beat sheet of what actually happens on the trail: what is
seen, and -- only when there is a genuinely useful sound cue -- what is heard.

Rules:
- Output a JSON array. Each beat is {"t": "mm:ss", "see": "...", "hear": "..."}.
  "hear" is optional: include it only for a meaningful, non-ambient sound cue
  (a brake, a skid, tires on gravel, a bird, a sudden gust). Omit it otherwise.
- "t" is the timestamp (mm:ss) measured from the start of the clip.
- Describe each moment richly and specifically, not as a single bland label.
  Capture the salient detail: terrain and obstacles, line choices, effort, and
  especially people, animals, and interactions -- what they are doing, their
  body language, how they react to the rider, and the apparent cause when it is
  visibly supported. For example, prefer "a man pulls his leashed dog close and
  grips its collar as it lunges and barks at the rider" over "a dog barks". Two
  short sentences are fine when a moment earns it.
- Stay neutral and observational: third person, no narration, no first person,
  no opinions, no inner voice. This sheet is language-neutral and reused across
  languages.
- Describe only what is actually visible or audible. You may note an apparent
  cause when the visuals support it, but do not invent intent, dialogue, or
  detail you cannot see or hear. Treat speech as reliable; treat non-speech
  sound labels as approximate.
- Be selective about which moments you log -- the moments a rider would actually
  react to, not one per second -- but describe each logged moment in full.

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
    content = types.Content(
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
    )
    gen_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[Beat],
        temperature=0.4,
    )
    try:
        response = _generate_with_retry(
            client,
            model=config.gemini_model,
            contents=content,
            config=gen_config,
            log=log,
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
