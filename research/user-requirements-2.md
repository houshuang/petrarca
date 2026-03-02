# User Requirements — Interview Round 2

## History Reading: The "Hooks" Strategy
The user's approach to learning history is through **deep anchor points**:
- Go very deep on pivotal moments (Alexander the Great, Caesar, 1814, Elizabethan period)
- Use multiple modalities: historical fiction, movies, poetry, literature from the era → get a real "sense"
- Then expand outward: surrounding countries, preceding causes, consequences
- Example: Charlemagne → what's happening in Spain, Constantinople, Baghdad? How did Rome's fall lead here? How did Vikings follow?

Multiple knowledge dimensions:
- **Narrative**: Timeline, events, causation chains
- **Structural**: How feudalism/monarchy/monasteries worked
- **Geographic**: Where things are, spatial relationships
- **Conceptual**: Cultural movements, intellectual history (Pirenne thesis, Huizinga's "Waning of the Middle Ages")
- **Literary/Theoretical**: Auerbach's "Mimesis", literary theory applied to historical understanding

Key insight: "Ideally I'd read about something and be able to locate it conceptually" — the goal is a mental map, not a set of facts.

Different reading modes for history:
- Narrative history (Karl XII biography) — chronological, event-driven
- Conceptual history (Pirenne, Huizinga) — thematic, argumentative
- Literary theory (Mimesis) — analytical frameworks applied to texts

**This means the knowledge model needs to handle both factual/temporal knowledge AND conceptual frameworks.**

## Interaction Design
- Needs to be quick but rich
- Should be able to interact with different parts of an article quickly
- Pre-research on what signals are most helpful is needed
- Voice input is very rich but not always available
- **Will require experimentation** — user doesn't have a fixed vision here

## First Prototype: Twitter Bookmarks
- Start with Twitter bookmarks as the content source
- Code exists in ../alif or ../otak for Twitter bookmark extraction
- User is enthusiastic about a quick prototype

## Kindle Integration
- Syncing reading position would be nice but not critical
- Has used highlighting but no system for processing them
- Not a first priority

## Voice Notes: Multiple Purposes
1. **Feedback to the system**: "I already knew this" / "this is interesting"
2. **Research trigger**: Launch a background agent on the Hetzner VM that researches a question, has answers ready next time user returns
3. **Personal notes for review**: Notes that become part of incremental reading themselves
4. **Cross-source synthesis**: Notes from multiple sources synthesized together

## Key References to Investigate
- **../otak**: "has a ton of research on knowledge systems in general" — MUST REVIEW
- **../bookifier**: Custom Kindle epub generation
- **../alif or ../otak**: Twitter bookmark extraction code
- **Andy Matuschak**: Spaced repetition applied to reading/attention
- **Rob Haisfield**: Spaced attention concept
- **Hetzner VM**: Available for background agent work (details in ../alif)

## Conceptual Models to Research
- **Spaced attention** (Matuschak/Haisfield): Not SRS on facts, but scheduled re-engagement with ideas
- **Notes as incremental reading items**: Voice notes and written notes re-enter the review queue
- **Cross-source synthesis**: System combines notes from multiple readings on related topics
- **Background research agents**: Voice question → agent researches → results ready on next visit
