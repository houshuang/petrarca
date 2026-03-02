# User Requirements — Interview Notes

## Reading Contexts (Multi-Modal)

### 1. Work-break browsing (Web, short bursts)
- Opens Twitter during breaks, sees interesting stuff, bookmarks it, never returns
- Opens many tabs that never close
- Not in the mood for long reading during work
- **Need**: Quick triage — is this worth my time? Save intelligently, not just bookmark

### 2. Article reading (Web + Mobile, 5-30 min)
- Occasionally gets through an article
- Currently no note-taking or tracking
- Preparing a Claude Code presentation Friday — feels overwhelmed by volume
- **Pain**: Most Claude Code articles are fluff ("this changes everything"), some are shallow experience reports. Occasionally there's a genuinely new tool or deep framework insight
- **Need**: Filter by novelty AND credibility. Credibility of author matters but is hard to assess

### 3. Kindle books (Mobile, deep reading sessions)
- History, cultural theory — often dry
- Multiple books going simultaneously
- Forgets context between sessions (what was happening in that chapter?)
- Sometimes needs more background knowledge before continuing
- **Need**: Not filtering (chose the book already) but scheduling, AI-enhancing, context restoration
- Has experience with ../bookifier generating enhanced Kindle epubs (pre-reads, translations, etc.)
- A system that knew the reader well could generate much more targeted commentary on new books

### 4. Paper books (Physical, deep reading at fireplace etc.)
- Would love a digital companion: photo a page, speak reflections, have it transcribed and linked
- ../alif has textbook scanning code (OCR → word-level analysis) as inspiration
- Integration between physical and digital is valued

### 5. Atomic vs Deep reading (key insight)
- 6 minutes waiting for someone = atomic reading
- Fireplace with a book = deep reading
- **Bidirectional preparation**:
  - Atomic CAN PREPARE for deep read (linguistically, semantically)
  - Atomic CAN REINFORCE after deep read (memory, review)
  - These are not separate — they're a cycle

## Key Design Insights from User

### Knowledge building, not fact drilling
> "How do I read a lot in history and feel like it's not just going out the other window, but I'm actually building up a deep conceptual understanding of a field? But the key is that trying to do spaced repetition on every single fact I encounter is going to be completely useless and unmotivating."

This is CRITICAL. The SRS component must work at the concept/framework level, not individual facts. The user wants to build mental models, not memorize trivia.

### Voice notes as first-class input
> "I have often missed the opportunity to take voice notes while reading something — just hit record and speak, and have it transcribed and linked to the context."

Voice → transcription → linked to reading context → fed into knowledge model → influences future AI enhancement. This is a rich signal source.

### Unobtrusive but rich mobile interaction
- Alif inspiration: highlighting unknown words provides dual signal (marked = unknown, unmarked = known)
- Need equivalent for article reading — what gestures/taps give rich signal without breaking flow?
- Whatever the interaction is, it must work well on mobile during quick sessions

### Information modeling for LLM access
> "One of the key things will be figuring out how to model the information in a way that the LLM can easily access — both about what I've read and my level of knowledge/interest."

Two modeling challenges:
1. **What has the user read?** (reading history, highlights, notes, time spent)
2. **What does the user know/care about?** (derived from #1 but more abstract — concepts, frameworks, interest levels)

### Credibility assessment
- Author credibility matters for filtering but is hard to assess automatically
- Some articles are by knowledgeable practitioners, others by hype-surfing content creators
- Need some way to signal or learn credibility

## Use Case Prioritization (inferred)

1. **Immediate**: Claude Code article filtering for Friday presentation
2. **High value**: Article triage from Twitter/RSS — stop the bookmark graveyard
3. **High value**: Kindle book enhancement — context restoration, pre-reads, note-taking
4. **Medium**: Deep reading companion with voice notes
5. **Future**: Paper book companion (OCR + voice)
6. **Future**: Custom podcasts from reading material

## Reference Projects
- `../bookifier` — custom Kindle epub generation with pre-reads, translations
- `../alif` — textbook scanning, word-level knowledge tracking, physical-digital integration
