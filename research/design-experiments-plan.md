# Plan: Petrarca Deep Design Experiments

## Context

The article-first redesign (previous plan) is complete: 12 articles from Twitter bookmarks, a 4-tab progressive reader (Summary/Claims/Sections/Full), Feed/Library/Stats screens, full interaction logging.

**Problem**: The current app is a basic read-later prototype. The vision (synthesized from 4 user interviews + 7 research documents) calls for something radically more ambitious: knowledge-aware filtering, semantic zoom, gesture-rich signals, spaced concept-level re-engagement, voice notes, and a reading experience that adapts to available time. We have 12 articles when we could have hundreds. We have discrete tab navigation when research calls for fluid depth transitions. We have no knowledge model, no scheduling, no gestures beyond tap.

**What the user wants**: "Go deeper with design and exploration. Come up with hypotheses and test design experiments. Be very ambitious and systematic."

**Approach**: Structured as sequential experiments, each with a hypothesis, implementation, measurement via the existing logging system, and success criteria. Content expansion first (prerequisite), then reader experience, then triage/feed, then knowledge infrastructure.

---

## Phase 0: Content Expansion (Prerequisite for Everything)

**Goal**: Go from 12 articles to 100+ across diverse topics, giving us enough content to make reading experiments meaningful.

### 0a. Expand Twitter bookmark pipeline beyond Claude Code
- Current filter scores only for Claude Code relevance (score ≥ 0.8)
- Remove topic filter entirely — process ALL 200 bookmarks that have fetchable URLs
- Keep the 3-tier extraction and LLM processing

### 0b. Integrate Readwise Reader as second source
- 11,598 items at `/Users/stian/src/otak/data/readwise_reader.json` (4 years of reading history)
- Categories: 8,533 RSS + 2,796 articles + 105 email + 98 tweets + 52 PDFs
- **Content field is null** — metadata only (title, URL, author, word_count, reading_progress)
- Pipeline: filter by category (article, rss) → deduplicate by URL against existing articles → fetch content via 3-tier extraction → LLM processing
- Start with items that have `reading_progress > 0` (items user actually engaged with) — highest signal
- **Target ~50 articles total** (mix of Twitter + Readwise) for initial experiment batch
- Aim for topic diversity: sample across history, AI/tech, policy, literature, cultural theory

### 0c. Multi-topic article set
- Goal: articles spanning user's actual interests (history, cultural theory, AI/tech, policy, literature)
- The Readwise data naturally covers this breadth
- Tag articles by broad domain during LLM processing

### 0d. Pipeline enhancements
- Add `--source readwise` flag to `build_articles.py`
- Add incremental mode: skip articles already in `articles.json` (by URL dedup)
- Add progress reporting (X of Y processed)
- Faster LLM: consider Gemini Flash via otak's `llm_providers.py` for bulk processing (1000x cheaper than Claude for summaries)

**Files**: `scripts/build_articles.py` (modify), `data/articles.json` (regenerate)

---

## Phase 1: Reader Experience Experiments

The reader is the core product. The current discrete-tab reader is functional but basic. These experiments test specific hypotheses about what makes reading better.

### Experiment 1A: Fluid Depth Transitions
**Hypothesis**: Continuous vertical scrolling through depth levels (summary flows into claims flows into sections) produces deeper reading than discrete tabs, because removing the decision to "switch tabs" reduces friction.

**Implementation**: Replace the current tab-based reader entirely with a single scrollable document:
- Article header (title, author, source, metadata)
- Full summary paragraph
- Divider: "Key Claims"
- Claims list (with knew-it/new-to-me buttons inline)
- Divider: "Sections"
- Section cards with summaries, expandable to full content
- Divider: "Full Article"
- Complete markdown content
- Sticky floating depth indicator showing current position (not tabs — just a label: "Summary · Claims · Sections · Full")
- Scroll position determines reading depth automatically

**Measurement**: Log `scroll_depth_pct`, `time_at_depth`, `depth_transitions`, `signals_given`. Compare against current tab-based metrics.

**Success**: Users reach deeper depth levels, give more signals per article, spend more total time.

### Experiment 1B: Inline Claim Signals
**Hypothesis**: Presenting claims inline within the full text (highlighted, with tap-to-signal) produces richer signals than showing claims in a separate list, because users can evaluate claims in context.

**Implementation**:
- In the full article text, highlight sentences that match `key_claims[]`
- Tapped highlight shows a floating pill: [Knew this] [New to me] [Save]
- Un-signaled claims have a subtle highlight; signaled ones change color (blue=knew, green=new)
- Visual progress: "7 of 12 claims reviewed"

**Measurement**: Log `claim_signal_in_context` with position, surrounding_text, time_to_signal. Compare signal distribution (knew_it vs interesting ratio) against isolated claim list.

**Success**: More claims get signals, distribution differs from isolated list (showing context matters for judgment).

### Experiment 1C: Implicit Time Tracking
**Hypothesis**: Measuring time spent per section and scroll behavior provides useful signal about user interest even without explicit interactions.

**Implementation**:
- Track `section_enter` / `section_exit` timestamps as user scrolls through content
- Track `scroll_velocity` (fast scan vs. slow read)
- Track `pause_duration` per paragraph (>3 seconds = engaged reading)
- Track `revisit` events (scrolling back to re-read a section)
- All implicit, no UI change

**Measurement**: Correlate implicit time signals with explicit claim signals. Do sections where the user pauses longer also get more "interesting" signals?

**Success**: Strong correlation (r > 0.5) between dwell time and explicit interest signals, validating that time is a reliable implicit signal.

**Files**: `app/app/reader.tsx` (major rewrite), `app/data/types.ts` (extend), `app/data/store.ts` (extend)

---

## Phase 2: Feed & Triage Experiments

### Experiment 2A: Card-Stack Triage
**Hypothesis**: A swipe-based card stack (like Tinder) for new articles produces faster triage decisions than a scrollable list, because forced binary choices prevent the "I'll decide later" paralysis.

**Implementation**:
- New triage mode on Feed screen (toggle: List view / Triage mode)
- Full-screen card: title, summary, topics, source, read time
- Swipe right = "Read later" (stays in feed, marked as interesting)
- Swipe left = "Skip" (archived, can be recovered)
- Swipe up = "Read now" (opens reader immediately)
- Card shows novelty cues: topic pills color-coded by how much user has read on that topic
- After triage complete, feed shows only "Read later" items sorted by priority

**Measurement**: `triage_swipe` with direction, decision time (ms), article_id. Compare: articles triaged per minute, engagement rate (do "read later" items actually get read?).

**Success**: >3x faster triage than list-browse. >50% of "read later" items opened within a week.

### Experiment 2B: Topic Clustering Feed
**Hypothesis**: Grouping articles by topic (with cluster headers showing "3 new articles on Byzantine history") helps users prioritize better than a flat chronological list.

**Implementation**:
- Feed groups articles by topic clusters (using LLM-assigned topics)
- Each cluster: topic name, article count, freshness indicator
- Tap cluster → expands to show article cards within that topic
- "Read the cluster summary" option — LLM-generated synthesis of what's new across all articles in a cluster
- Topics ordered by: (new article count) × (user interest signal for that topic)

**Measurement**: `cluster_expand`, `cluster_summary_read`, `article_from_cluster_tap`. Compare: do users engage with more diverse topics when clustered?

**Success**: Users open articles from ≥3 different topics per session (vs. current behavior of reading from 1-2 topics).

**Files**: `app/app/index.tsx` (major rewrite), `app/app/triage.tsx` (new file for card stack)

---

## Phase 3: Knowledge Model Foundation

### 3a. Concept Extraction
- Extract concepts/claims from all articles during LLM processing
- Each concept: `{ id, text, topic, source_articles[], first_seen, times_encountered }`
- Deduplicate similar concepts across articles (same idea stated differently)
- Store in `data/concepts.json`, loaded by app

### 3b. User Knowledge State
- When user signals "knew this" on a claim → mark related concepts as "known"
- When user signals "new to me" → mark as "encountered"
- Track per-topic familiarity: ratio of known/encountered concepts in that topic
- Types: `ConceptState { concept_id, state: 'unknown'|'encountered'|'known', last_seen, signal_count }`

### 3c. Novelty Scoring
- For each article: count concepts that are "unknown" to user vs. "known"
- `novelty_score = unknown_concepts / total_concepts`
- Display on feed cards: "~72% new to you" or "mostly familiar"
- Re-score as user reads more articles (score decreases as knowledge grows)

### 3d. "What You Know" Dashboard
- New section in Stats/Progress screen
- Topic map: topics the user has engaged with, with depth indicators
- Concept count per topic: "AI/Agents: 23 concepts known, 47 encountered, 120 unseen"
- Growth over time chart

**Hypothesis**: Showing novelty scores on feed cards changes triage behavior — users prioritize high-novelty articles over familiar-topic articles.

**Measurement**: Correlation between novelty score and article selection. Do users preferentially read high-novelty articles?

**Files**: `app/data/types.ts` (add Concept, ConceptState), `app/data/store.ts` (concept tracking), `scripts/build_articles.py` (concept extraction), `data/concepts.json` (new), `app/app/stats.tsx` (knowledge dashboard)

---

## Phase 4: Scheduling & Spaced Attention (Future)

Not implemented in this round but designed for:

### 4a. Priority Queue with A-Factor
- Each article gets a priority (0-100) based on: novelty score × topic interest × freshness
- A-Factor scheduling for partially-read articles (resurface at increasing intervals)
- Auto-postpone: low-priority items gracefully defer

### 4b. Concept Cards
- Extracted concepts become schedulable review items
- Not flashcards — engagement prompts: "You're reading about X. How does this relate to Y you encountered last week?"
- Voice note responses as first-class input

### 4c. Voice Notes
- Record button in reader (expo-av recording)
- Soniox async transcription (stt-async-v4)
- Voice notes linked to article + section context
- Transcribed notes feed into concept extraction

---

## Implementation Order

1. **Phase 0** (content expansion) — ~2 hours
   - Modify pipeline, run on expanded sources, generate 100+ articles

2. **Phase 1** (reader experiments) — ~3 hours
   - Build fluid depth reader (1A) + inline claim signals (1B) + implicit tracking (1C)
   - These compose: fluid scrolling is the base, inline claims overlay on it, implicit tracking runs silently

3. **Phase 2** (feed experiments) — ~2 hours
   - Card-stack triage (2A) as toggle on feed
   - Topic clustering (2B) as alternate view mode

4. **Phase 3** (knowledge model) — ~3 hours
   - Concept extraction in pipeline
   - Knowledge state tracking in app
   - Novelty scores on feed cards
   - Knowledge dashboard

5. Deploy, test on device, analyze logs, iterate

## Verification

- Pipeline: `python3 scripts/build_articles.py --from filter` → 100+ articles in `data/articles.json`
- TypeScript: `cd app && npx tsc --noEmit` → clean
- App: `cd app && npx expo start` → all screens render, reader scrolls fluidly, triage swipes work
- Logging: every new interaction produces events in JSONL logs
- Deploy: `bash scripts/deploy.sh` → app accessible on Hetzner server
- Test reading flow: open article → scroll through depths → signal claims → verify reading state persists

## Key Files

| File | Action |
|------|--------|
| `scripts/build_articles.py` | Expand: Readwise source, remove topic filter, concept extraction |
| `data/articles.json` | Regenerate with 100+ articles |
| `data/concepts.json` | New — extracted concepts across articles |
| `app/data/articles.json` | Copy of above for app bundle |
| `app/data/types.ts` | Extend: Concept, ConceptState, implicit tracking types |
| `app/data/store.ts` | Extend: concept tracking, novelty scoring, triage state |
| `app/data/persistence.ts` | Extend: concept states |
| `app/app/reader.tsx` | Major rewrite: fluid depth, inline claims, implicit tracking |
| `app/app/index.tsx` | Major rewrite: triage mode, topic clustering, novelty badges |
| `app/app/triage.tsx` | New: card-stack swipe triage screen |
| `app/app/stats.tsx` | Extend: knowledge dashboard |
| `app/app/_layout.tsx` | Minor: add triage route |
| `research/experiment-log.md` | Append: experiment descriptions and results |
