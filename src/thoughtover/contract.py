"""The universal narration contract.

This is the tool's craft layer, applied to *every* persona: how good ride
narration works. It is deliberately separate from the persona files, which only
describe a character. Keeping the two apart means a casually written persona
still inherits this quality floor, and it is hard to slop out.

Phase 2 feeds NARRATION_CONTRACT to Claude alongside the selected persona and
the language-neutral beat sheet.
"""

from __future__ import annotations

NARRATION_CONTRACT = """\
# Narration contract

These rules are how good ride narration works. They apply to every persona and
are not the persona's job to restate. Write the thoughts laid over the footage,
not a voice-over describing it.

## Form
- One thought per line, in the format `[mm:ss] thought`, timestamped to the beat.
- First person, present tense. These are the rider's inner thoughts, not commentary.

## Craft
- Sparse. Long silences are good. A line should feel earned, never filled in.
- Short. A handful of words. If it runs long, it is probably explaining.
- Reactive. Respond to a specific thing on the trail, in this moment.
- Sincere. Mean the small true thing. Do not reach for a laugh; if it is funny,
  the funny falls out of the sincerity.
- Land it and move on. Say the thing, let it sit, back to the trail.
- Do not narrate the soundtrack. Never name a sound ("wind noise", "tires
  skidding"); lean into the moment instead.

The persona supplies the character on top of this: who is speaking, their wit,
their values, their language.
"""
