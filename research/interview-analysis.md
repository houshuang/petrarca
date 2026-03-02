# Interview Analysis — Incremental Reading & Knowledge Building Ideas

Extracted from `interview.md` (LLM interview with Stian about app concept). Language-learning specifics excluded; focus on incremental reading and knowledge-building concepts.

## Core Incremental Reading Ideas from Stian

### 1. Progressive Text Engagement
> "I'm interested in the idea of incremental reading... where you're starting to read a complex text. You can split any paragraph into smaller pieces, schedule them for review, add comments."

Key elements:
- Start reading complex text
- Split into smaller reviewable pieces on the fly
- Schedule pieces for future review (spaced)
- Add comments/annotations as you go

### 2. Audio Annotation While Reading
> "I really want to be able to quickly use audio to take comments as I'm reading and have that together with the original text in a way that I can review later"

- Voice notes attached to text segments
- Low-friction capture (don't break reading flow)
- Audio + original text kept together for review
- Build out ideas over time through repeated engagement

### 3. Knowledge Base Building
> "Maybe over time kind of build out my ideas, tagging questions and so on, so that this becomes not only an amazing language learning tool, but also a tool to read about history, for example, and slowly build out my knowledge base"

- Not just retention — active knowledge construction
- Tagging and questioning while reading
- Cross-domain: history, technical topics, etc.
- Gradual accumulation across many reading sessions

### 4. Implicit Skills Tree / Knowledge Model
> "There might be some kind of underlying domain knowledge skills tree that is generated on the fly"

- Auto-generated concept graph from reading activity
- Not hand-authored — inferred from what the user reads and how they interact
- Tracks what concepts the user has encountered vs. mastered

## From the Research Section (GPT-5 Thinking output)

### SuperMemo Incremental Reading Pipeline
The interview's research section identified the core IR pipeline:
1. **Import** — bring in articles/texts
2. **Extract** — select key passages while reading
3. **Cloze** — turn extracts into review items
4. **Schedule** — priority queue with spaced repetition

### Key UX Patterns Identified
- Sentence-level selection
- One-click "extract to review"
- Automatic cloze from selected spans
- Per-item priority sliders
- Priority queue management

### Modern Analogues Referenced
- **Readlang / LingQ**: click-to-translate with sentence playback, generate review items from clicks
- **Polar Bookshelf**: IR-like workflows
- **RemNote**: integrated FSRS
- **Readwise Reader**: extract/highlight → review pipeline

### Knowledge Modeling Approaches Referenced
- Open Learner Modeling (SMILI framework)
- Bayesian Knowledge Tracing (BKT)
- Deep Knowledge Tracing (DKT)
- Knowledge Space Theory (KST / ALEKS)
- Auto-building prerequisite graphs from text

## What Evolved into the Current Petrarca Vision

The interview was originally about language learning, but the incremental reading and knowledge-building ideas are the seed of Petrarca. The evolution:

1. **Language learning → General reading**: Same core mechanics (track knowledge, schedule review, progressive engagement) but applied to any topic
2. **Word-level knowledge → Concept-level knowledge**: Instead of tracking vocabulary, track concepts/facts/ideas the user has encountered
3. **Generated sentences → Real articles**: Instead of LLM-generated practice sentences, work with real-world articles from RSS, Twitter, etc.
4. **New addition: Pre-filtering**: Not in the original interview — the idea that the system should scan incoming articles and estimate their novelty/value BEFORE the user reads them

## Key Design Questions Raised
1. How to represent "what the user knows" at concept level (not word level)?
2. How to score an article's novelty relative to user's current knowledge?
3. What are the right user signals during reading? (I know this / interesting / save / not relevant)
4. How to balance depth (incremental reading of one article) vs. breadth (scanning many articles)?
5. How much of SuperMemo's IR complexity is actually needed vs. simpler approaches?
