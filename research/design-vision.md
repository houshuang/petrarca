# Petrarca — Design Vision Synthesis

*Compiled from user interviews (4 rounds) and research on incremental reading, spaced attention, prior art, and reference projects. March 2, 2026.*

---

## The Core Problem

The user reads widely (history, cultural theory, technology, policy) across multiple formats (Twitter, articles, Kindle, paper books) and multiple contexts (work breaks, commute, deep reading at home). Despite genuine engagement, most knowledge fades because:

1. **No capture**: Articles are read and forgotten. Twitter bookmarks pile up unopened.
2. **Too much capture is unsustainable**: Past note-taking (Roam, Logseq) took enormous time and still didn't produce synthesis.
3. **Fact-level SRS is unmotivating**: Drilling individual facts from a history book feels like homework and doesn't build understanding.
4. **Volume overwhelms**: Too many articles, too many tabs, too many books going simultaneously. No way to triage efficiently.

## The Insight: Hooks, Not Facts

The user's breakthrough in history learning was the "hooks" strategy: go deep on anchor points (Caesar, Alexander, Charlemagne), then expand outward by causation, geography, and time. Once you have hooks, new knowledge has somewhere to **land**.

> **"Done" = able to PLACE new knowledge.** Having enough framework that new information can be assimilated.

This is the core design principle. Petrarca doesn't optimize for recall. It optimizes for building and maintaining **hooks** — anchor points of understanding that make future reading productive.

## What Petrarca Does (Three Layers)

### Layer 1: Intelligent Triage (Upstream Filtering)
**Problem**: Drowning in content. Most articles tell you nothing new.
**Solution**: Model what you know and care about. Score incoming articles for genuine novelty. Surface only what's worth your time.

- Ingest from Twitter bookmarks, RSS feeds, Readwise, manual input
- Extract key claims/insights from each article
- Compare against your knowledge model: what's genuinely new?
- Rank by: novelty × relevance to your interests × source credibility
- Present for quick triage (30-second interactions on phone)

**Key differentiator**: This happens BEFORE you read, not after. No existing tool does this well.

### Layer 2: Adaptive Reading (Depth on Demand)
**Problem**: Never know how much time you have. Rabbit holes lose you. Tabs multiply.
**Solution**: Every piece of content exists at multiple depths. You go exactly as deep as time allows, and the system remembers your depth.

- Progressive reveal: headline → summary → key claims → full article
- No losing your place — the system tracks where you are across everything
- Rich but unobtrusive signals while reading (details TBD via experimentation)
- Voice notes as first-class input: speak a thought, it's transcribed, linked to context, and fed into the knowledge model
- Works for articles, book chapters, synthesized reports

**Design constraint**: Must not feel like work. Reading itself IS the primary signal.

### Layer 3: Knowledge Maintenance (Spaced Attention)
**Problem**: Knowledge fades. You loved Jane Jacobs in college but can only recall 3 bullet points.
**Solution**: Gentle, concept-level re-engagement — not fact drilling.

- When reading something new, surface connections to past reading: "This relates to the Pirenne thesis you engaged with in January"
- Revisit via synthesis, not source: "Here's what you took away from those 4 Caesar books, plus your voice notes"
- Concept-level prompts: "How does this connect to X?" rather than "What year was Y?"
- User's own notes and voice reflections are the primary material for re-engagement
- Scheduling based on engagement depth, not binary right/wrong

**This layer is the most experimental.** We don't know what works yet. It needs rapid prototyping.

## The Knowledge Model

### What It Tracks
1. **Reading history**: What you've read, how deeply, when
2. **Extracted claims/insights**: Key ideas from each piece of content
3. **User signals**: Marks, highlights, voice notes, time spent, depth reached
4. **Concept anchors (hooks)**: Topics/frameworks where understanding is strong enough to assimilate new material
5. **Interest profile**: What topics and types of content engage you (inferred from behavior)
6. **Connections**: Links between ideas across different sources

### What It Does NOT Track
- Individual facts for drilling
- Reading "scores" or "streaks"
- Anything that makes reading feel like homework

### The Unit of Knowledge
Not a fact (too small). Not a book (too big). Something like a **claim** or **insight** — "the Pirenne thesis argues that the real break from antiquity came with Islamic expansion, not the Germanic invasions." A few sentences that capture a transferable idea.

This maps directly to otak's claims-first architecture, but with a much lighter touch — claims are extracted automatically and refined by user engagement, not hand-authored.

## Two Modes, One System

A critical insight from the interviews: Petrarca serves two fundamentally different reading modes with different needs, different timescales, and different success criteria. They must eventually be one system, but the needs are distinct.

### Mode A: "Firehose" — Fast-Moving Technical/Current Content
**Examples**: Claude Code articles, AI research, tech news, policy updates
**Character**:
- Quality is uncertain — most content is fluff, some is gold
- No single author matters — it's the insight that counts
- Knowledge decays fast (Claude Code article is irrelevant in 2 months)
- High volume, constant stream from Twitter/RSS/newsletters
- Deduplication is crucial (50 articles say the same thing)
- **Memory less important** than noting down specific useful things for later lookup

**What Petrarca does**:
- AI drinks from the firehose, triages based on quality + deduplication + user's evolving knowledge/interests
- Presents filtered, consolidated view for quick consumption
- UI for: expand, mark, note, go deeper, dismiss
- Immediate feedback loop — you know right away if the filtering is working
- **Start here** — faster to build, faster to validate, helps with Friday presentation

### Mode B: "Deep Shelf" — Enduring Books and Scholarship
**Examples**: History books, cultural theory (Pirenne, Huizinga), literary criticism (Mimesis), philosophy, poetry
**Character**:
- Quality is pre-established — esteemed thinkers, curated selection
- The specific voice and argument of the author matters deeply
- Knowledge should endure — understanding the Pirenne thesis is valuable for years
- Low volume, long engagement (weeks/months per book)
- No deduplication needed — each work is unique
- **Memory and synthesis are crucial** — hooks, connections, long-term understanding

**What Petrarca does**:
- Context restoration ("where was I, what was happening in this chapter")
- AI enhancement (pre-reads, background summaries, connection prompts)
- Voice notes linked to passages
- Synthesis across multiple books on related topics
- Gentle spaced re-engagement with concepts and the user's own reflections
- **Build later** — overlapping infrastructure but different UX, more experimental

### The Overlap
Both modes share:
- The knowledge model (what does the user know/care about)
- The reading UI primitives (progressive reveal, signals, voice notes)
- The backend infrastructure (extraction, embeddings, LLM processing)
- The principle that reading itself is the signal

But Mode A optimizes for **filtering and speed**, while Mode B optimizes for **depth and retention**.

## Reading Contexts (All Must Be Served)

| Context | Duration | Device | Mode | Primary Need |
|---------|----------|--------|------|-------------|
| Work-break Twitter browsing | 2-5 min | Web browser | A | Quick triage, save for later |
| Article reading | 5-30 min | Phone or web | A | Depth on demand, signals |
| Kindle books | 30-90 min | Kindle + phone companion | B | Context restoration, notes, AI enhancement |
| Paper books | 30-90 min | Phone companion | B | Photo page, voice notes |
| Commute/waiting | 2-10 min | Phone | A or B | Micro-sessions, review, triage |

## Technical Architecture (Preliminary)

### What We Can Reuse
- **../otak**: Twitter bookmark fetcher, Readwise fetcher, LLM providers, extraction patterns, salience lenses concept
- **../bookifier**: Pipeline/caching patterns, Kindle epub enhancement
- **../alif**: Expo/React Native mobile setup, FSRS scheduling, physical-digital integration (textbook scanning)

### Stack (Likely)
- **Frontend**: Expo (React Native) — iOS + web from one codebase
- **Backend**: Python (FastAPI) or minimal — could start with just scripts + JSON
- **LLM**: Claude Code CLI (`claude -p`) for all processing (free via Max plan)
- **Database**: SQLite to start (like alif)
- **Embeddings**: For semantic similarity / novelty detection
- **Background processing**: Hetzner VM for research agents

### Key Design Decisions Still Open
1. How to represent the knowledge model (claims graph? embeddings? topic vectors?)
2. What mobile interactions give the richest signals with least effort
3. How to schedule concept-level re-engagement (no binary right/wrong)
4. How much AI enhancement is useful vs. overwhelming
5. Whether Kindle integration is worth the effort vs. manual input

## Experiment Plan

### Experiment 1: Twitter → Claude Code Briefing (This Week)
- Fetch Twitter bookmarks, filter for Claude Code
- Extract articles, deduplicate, summarize
- Build multiple experimental UIs in Expo to test triage/reading
- User tests on phone for Friday presentation prep
- **Success metric**: Does the user find articles they would have missed? Does triage feel fast?

### Experiment 2: Knowledge Signals (Next)
- Add interaction tracking to the reader
- Test different signal mechanisms (swipe, tap, voice, progressive reveal)
- See which interactions feel natural and produce useful data
- **Success metric**: Does the system learn what the user knows?

### Experiment 3: Spaced Re-engagement (Later)
- Based on accumulated reading data, try different re-engagement patterns
- Test concept cards, synthesis views, connection prompts
- **Success metric**: Does the user feel like they're building understanding?

## Guiding Principles

1. **Reading is the interface, not a chore to be optimized away**
2. **The system should be smarter about what to show, not demanding about what to do**
3. **Soft touch over hard obligations** — no streaks, no guilt, no "you have 47 items due"
4. **Synthesis over source** — when revisiting, show what you took away, not the raw original
5. **Time-respectful** — useful in 30 seconds, rewarding in 30 minutes
6. **Experiment-first** — we don't know what works yet, so the system must support rapid iteration
7. **The user's own thoughts (voice notes, reactions) are more valuable than the source material**
