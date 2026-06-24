# Thoughtover

Turn a raw mountain bike clip into a finished video narrated in your own cloned voice. An agent drafts the thoughts, **you curate them**, and your voice speaks them. The name rides on voice-over: not narration, but the inner thoughts laid over the footage.

## Core principle

Agent drafts, you curate, your voice speaks. `render` only ever voices the script file *you* edited, never fresh model output. The review step is not optional, and it is what keeps the videos sounding like you instead of like AI narration.

## How it works

Drop a clip, get two commands, with one editing step in between.

**`draft <clip>`** produces a script for you to edit. Internally it is a hybrid of two models, kept separate and inspectable:

1. **See and hear (Gemini).** The clip goes to Gemini as native video, sampled above 1 FPS so fast descents keep detail. Gemini reads the audio track alongside the frames, so the beat sheet can draw on sound too (braking, tire crunch, a passing bird). It returns a timestamped, **language-neutral** beat sheet of what happens on the trail, in no narrating voice, so it is shared across languages.
2. **Write (Claude).** The beat sheet, the tool's narration contract, and the selected persona go to Claude, which writes sparse, first-person, timestamped thoughts in that persona's voice.

**You edit the script** (`<clip>.<lang>.script.txt`) — reword, cut, retime. This is the middle step.

**`render <clip>`** turns the approved script into the finished video:

1. **Voice (ElevenLabs).** Each line is spoken in your cloned voice, using a multilingual model so the same voice carries across languages.
2. **Assemble (ffmpeg).** Each line is placed a beat after its timestamp, the trail audio ducks (and eases) underneath it, and everything muxes into `<clip>.<lang>.narrated.mp4`. Render is format-agnostic: the video stream is carried through untouched, so the output keeps the input's exact dimensions and aspect ratio — a vertical 9:16 clip renders as a 9:16 short, no letterboxing or forced 16:9.

### Input

Thoughtover narrates the clip exactly as given. All reframing, cropping (for example wide to vertical), and trimming happen upstream in your editor, before `draft`. You feed it the locked final cut, so what the model sees matches what the viewer sees and the timestamps line up with the delivered video.

## Install

Requires [uv](https://docs.astral.sh/uv/) and [ffmpeg](https://ffmpeg.org/) on your PATH.

```bash
uv sync
cp .env.example .env   # then fill in your keys, voice id, and (optional) tuning
```

## Use

```bash
# 1. Draft: Gemini watches+hears the clip -> language-neutral beats;
#    Claude writes the thoughts using the narration contract + persona.
uv run thoughtover draft ride.mp4 --lang en --persona default
#    -> ride.beats.json        (language-neutral, shared across languages)
#    -> ride.en.script.txt     (the editable thoughts)

# 2. Edit ride.en.script.txt by hand. Reword, cut, retime. This is the middle step.

# 3. Render: voice the approved script in your cloned voice, then place,
#    duck, and mux with ffmpeg.
uv run thoughtover render ride.mp4 --lang en
#    -> ride.en.narrated.mp4
```

Both commands default to `--lang en` and `--persona default`. `draft` reuses an existing beat sheet (Gemini watches once); pass `--refresh-beats` to re-watch. `render --reuse-voices` re-mixes without re-billing TTS, handy when tuning the mix or timing.

## File formats

Beat sheet, `<clip>.beats.json` (the `hear` field is optional, present when there is a useful sound cue):

```json
[
  { "t": "00:03", "see": "loose rock in the line, front wheel skips", "hear": "tires skid on gravel" },
  { "t": "00:09", "see": "small bird crosses the trail ahead" }
]
```

Script, `<clip>.<lang>.script.txt` (the file you edit):

```
[00:03] ugh, that rock again
[00:09] oh, hey, bird
[00:21] ok this part, this is the part
```

One `[mm:ss] thought` per line. Blank lines and lines starting with `#` are ignored, so you can leave yourself notes.

## Personas

Two layers, kept separate:

- The **narration contract** (in `src/thoughtover/contract.py`) is the tool's craft floor, applied to every persona: sparse, short, sincere, reactive, land it and move on, don't narrate the soundtrack, the `[mm:ss]` format. It is "how good ride narration works," and it is not the persona's job to restate it.
- A **persona** describes only the character: who is speaking, their wit, their values, their language. Files are `personas/<name>.<lang>.md`, selected with `--persona`.

That split means a casually written persona still inherits the quality floor. `personas/default.en.md` ships as a plain template — copy it to make your own. Private personas go in `personas/local/`, which is gitignored, so your own detailed character is never committed; select it like any other (`--persona mine`), and a local file shadows a shipped one of the same name.

## Bilingual (English-only for now)

English is the supported workflow today (`--lang en`, personas like `default` or your own in `personas/local/`). The pipeline is still language-tagged under the hood — beat sheet, script paths, audio tracks — so another language can come back later without a refactor, but it is not tuned or documented yet.

## Configuration

All config lives in `.env` (see `.env.example`); keys are never committed.

- **Providers:** API keys for Gemini, Claude, and ElevenLabs, your cloned voice id, and the model names. Model ids move — verify them against each provider's current docs.
- **Vision:** `GEMINI_VIDEO_FPS` samples above 1 FPS so fast action keeps detail.
- **Mix:** `NARRATION_DUCK_DB` (how far the trail drops under a line), `NARRATION_GAIN_DB` (voice level), `NARRATION_REACTION_LAG` (delay so a line lands a beat after its event, not on top of it), `NARRATION_DUCK_FADE` (ease the trail down/back so it doesn't jump).
- **Voice:** `ELEVENLABS_MODEL` (`eleven_v3` for expressive delivery and inline audio tags; `eleven_multilingual_v2` for steadier speech). With v3, put tags in the script text itself — e.g. `[whispers]`, `[sighs]`, `[sings]` — before the words they affect; lower `NARRATION_STABILITY` (~0.35) helps tags land. `NARRATION_SPEED`, `NARRATION_SIMILARITY`, `NARRATION_STYLE`, `NARRATION_SPEAKER_BOOST` mirror the ElevenLabs sliders, passed on every request so renders are reproducible.
- **Sound design:** `NARRATION_INNER_VOICE`, `NARRATION_INNER_VOICE_REVERB`, `AMBIENCE_HIGHPASS_HZ`, `AMBIENCE_CARVE_DB`, `LOUDNORM`, `OUTPUT_LUFS`, `OUTPUT_TRUE_PEAK` — see below.

## Sound design (the "thought-over" feel)

This is what makes the narration feel like a *thought laid over the footage* rather than a voiceover pasted on top. It is all done at the mix stage in ffmpeg, so it costs nothing to tune — adjust the `.env` knobs and re-render with `--reuse-voices` (no TTS re-billing). The conventions follow how film and game audio treat internal monologue.

- **Inner-voice treatment** (`NARRATION_INNER_VOICE`) — an "inside the head" chain on each voiced line: high-pass to clear rumble, a low-mid bell for chest/bone-conduction warmth, a high-shelf cut to de-"air" it so it reads as internal, and firm compression to keep it close and even. `NARRATION_INNER_VOICE_REVERB` (0..1) adds a very short, low slap that lifts the voice out of the open-air space; `0` stays dry (pure bone-conduction intimacy), higher leans "mental space."
- **Ambience as content, not a music bed** — the trail audio *is* the ride, so it stays present rather than parked far down. `AMBIENCE_HIGHPASS_HZ` clears subsonic rumble; `AMBIENCE_CARVE_DB` carves a "voice pocket" (a midrange dip ~2 kHz) **only while a line is playing** (plus the duck fade padding), so the trail keeps its full tone between thoughts and opens a pocket when the voice lands.
- **Ducking with a smooth envelope** — under each line the trail eases down by `NARRATION_DUCK_DB` and back up over `NARRATION_DUCK_FADE`, staying ducked through closely-spaced lines instead of pumping.
- **Loudness** (`LOUDNORM`) — two-pass EBU R128 normalization: pass 1 measures integrated loudness, pass 2 applies it with `linear=true` so the mix lands on `OUTPUT_LUFS` (≈ −14 for YouTube/TikTok) with an `OUTPUT_TRUE_PEAK` ceiling. Upload-ready and consistent.

The balance to aim for: the voice as the anchor (intelligible, intimate), the trail clearly present underneath, and the two separated by a carved pocket rather than brute volume.

## Scope

One clip at a time, the two commands, the hybrid draft, the editable script, the voiced-and-assembled mp4. Local only.

Thoughtover does not shoot, crop, reframe, or trim video — it narrates the finished clip; all editing is upstream. No web UI, no batch. If two narration lines would overlap, the later one is nudged a touch rather than mixing two voices on top of each other.
