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
- Mostly reactive — often a specific thing on the trail, in this moment. Not every
  thought has to be about what's on screen; a rare stray memory, random opinion,
  or half-line of a song is fine when the persona allows it and the pacing earns
  a detour.
- Sincere. Mean the small true thing. Do not reach for a laugh; if it is funny,
  the funny falls out of the sincerity.
- Land it and move on. Say the thing, let it sit, back to the trail.
- Do not narrate the soundtrack. Never name a sound ("wind noise", "tires
  skidding"); lean into the moment instead.
- Do not recap the footage. The viewer can already see the trail, so a line that
  states what just happened ("he let me go first", "there's a hill", "a dog
  barks") is dead weight. React to the moment; do not announce it.
- Skip the setup. Cut throat-clearing lead-ins and filler ("nice guy", "oh look")
  and open on the thought itself. The line is the take, not the thing that
  prompted it. The beat sheet is context for you, not lines to echo.
- Do not meta-narrate. Never announce that you are thinking, remembering, or
  noticing ("I'm thinking about", "I can't stop thinking", "I notice that").
  Just have the thought.

The persona supplies the character on top of this: who is speaking, their wit,
their values, their language.
"""
