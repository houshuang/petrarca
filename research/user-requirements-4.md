# User Requirements — Interview Round 4 (Core Philosophy)

## The Tab Overwhelm Problem
- "Almost all the time" has too many tabs
- Past note-taking workflows: Roam Research, Logseq (both ingested into otak)
- Spent a ton of time on note-taking but often didn't feel the value
- Now often just reads some tabs and closes the rest
- Core pattern: start reading → follow interesting threads → rabbit hole → never come back to origin → lose place → feel overwhelmed
- Can be exciting but frustrating

## The Note-Taking Paradox
Three phases the user has gone through:
1. **Just reading** — no notes. Loved Jane Jacobs in college, can now only recall 3 bullet points
2. **Obsessive note-taking** (Roam Research) — still struggled with synthesis, unsustainable time in front of laptop
3. **Targeted reading** — read 4 books about Caesar, natural repetition at high level. But knowledge fades as you move away

**None of these felt right.** The sweet spot hasn't been found.

## What "Knowing" Means (Critical Design Input)
> "I now feel like I have enough overview of Caesar that I can confidently read articles about that time period and 'place them', assimilate new knowledge."

**"Done" = able to PLACE new knowledge.** Not recall facts, not pass a test, but having enough framework that new information has somewhere to attach. This is the "hooks" concept — anchors that make new learning stick.

## The Design Challenge (User's Own Words)
> "A very soft touch would be if the system knew everything I had read in the past few years and when I read something new it could help me / prompt me to make connections with previous material... and that it would be easy for me to go back and see not the whole thing but maybe a synthesis + my notes/thoughts"

Key constraints:
- **Soft touch** — not demanding, not another obligation
- **System remembers** — it knows your reading history
- **Connection prompting** — when reading new material, surface relevant past reading
- **Synthesis over source** — when revisiting, show a synthesis + your notes, not the raw original
- **Low effort** — must not require Roam-level time investment

## The Fundamental Tension
> "I am very unsure about this. Much easier to figure out in terms of language learning... This is a big experiment."

For language learning (alif), the knowledge model is clear: words → lemmas → roots → FSRS states.
For conceptual reading, it's genuinely unknown:
- What is the "unit" of knowledge? (Not a fact. Not a whole book. Something in between.)
- How do you track "understanding" vs "recall"?
- How much effort can you ask of the reader without it becoming unsustainable?
- How do you do spaced re-engagement without making it feel like homework?

## Design Implications

### Must NOT be:
- Another note-taking obligation
- Fact-level spaced repetition
- Something that requires laptop time
- Something that makes reading feel like work

### Must BE:
- Nearly effortless signal collection (reading itself IS the signal)
- Smart about making connections you wouldn't make yourself
- Good at synthesis (showing you a compressed, enriched version of what you read before)
- Respectful of whatever time you have (30 seconds or 30 minutes)
- An experiment — the system itself should be designed for rapid iteration on these unknowns
