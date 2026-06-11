# Thoughtover

Turn a raw mountain bike clip into a finished video narrated in your own cloned voice. An agent drafts the thoughts, **you curate them**, and your voice speaks them. The name rides on voice-over: not narration, but the inner thoughts laid over the footage.

The full design lives in [SPEC.md](SPEC.md). This README is the quick start.

## Core principle

Agent drafts, you curate, your voice speaks. `render` only ever voices the script file *you* edited, never fresh model output. The review step is not optional, and it is what keeps the videos sounding like you instead of like AI narration.

## Install

Requires [uv](https://docs.astral.sh/uv/) and [ffmpeg](https://ffmpeg.org/) on your PATH.

```bash
uv sync
cp .env.example .env   # then fill in your keys, voice id, and model ids
```

## Use

Two commands, with one editing step in between.

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

Both commands default to `--lang en` and `--persona default`.

## Personas

Two layers, kept separate:

- The **narration contract** (in `src/thoughtover/contract.py`) is the tool's craft floor, applied to every persona: sparse, short, sincere, reactive, land it and move on, don't narrate the soundtrack, `[mm:ss]` format.
- A **persona** describes only the character. Files are `personas/<name>.<lang>.md`, selected with `--persona`.

`personas/default.en.md` ships as a plain template. Private personas go in `personas/local/`, which is gitignored, and are selected like any other (`--persona mine`); a local file shadows a shipped one of the same name.

## Status

Phase 1 (scaffold) is in place: the CLI, config, persona resolution, the narration contract, and clear failures when ffmpeg or a required key is missing. The `draft` and `render` pipelines arrive in Phases 2 and 3 (see [SPEC.md](SPEC.md)).
