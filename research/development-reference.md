# Petrarca Development Reference

> Comprehensive record of everything built, every hypothesis tested, every design decision made. Updated as the project evolves.

---

## Table of Contents

1. [Project Timeline](#project-timeline)
2. [Architecture Overview](#architecture-overview)
3. [Content Pipeline](#content-pipeline)
4. [Experiments & Hypotheses](#experiments--hypotheses)
5. [Knowledge Model](#knowledge-model)
6. [Spaced Attention Scheduling](#spaced-attention-scheduling)
7. [Voice Notes](#voice-notes)
8. [Key Bug Fixes](#key-bug-fixes)
9. [File Index](#file-index)
10. [What's Not Built Yet](#whats-not-built-yet)
11. [Design Decisions & Tradeoffs](#design-decisions--tradeoffs)

---

## Project Timeline

| Date | Commit | What |
|------|--------|------|
| 2026-03-02 | `0b6f255` | Initial commit — project scaffolding |
| 2026-03-02 | `ea50555` | Deploy script for Hetzner |
| 2026-03-02 | `7c931d4` | Fix missing app/data/ module on deploy |
| 2026-03-02 | `2eaeb03` | Comprehensive interaction logging + signal persistence |
| 2026-03-02 | `2dd7c11` | Article-first redesign: progressive reading at 4 depth levels |
| 2026-03-03 | `41efcaf` | Deep design experiments: fluid reader, triage UI, knowledge model, 51 articles, 69 concepts |
| 2026-03-03 | `b0ff6ba` | Bug fixes + voice notes + connection prompting + continue reading |
| 2026-03-03 | `d3133d6` | Experiment log update |
| 2026-03-03 | `e79506a` | Spaced attention scheduling with Review tab |
| 2026-03-03 | `3854c53` | Experiment log + deployment update |

| 2026-03-03 | `cb17379` | Content refresh, research agents, synthesis, connections, scroll restore |
| 2026-03-03 | `f982e66` | User journey audit: fix implicit signals, markdown, review UX, expand concepts |
| 2026-03-03 | `5068f34` | Highlighting, dedup, exploration, research, content pipeline — 19 files, +2543 lines |
| 2026-03-03 | `5733684` | Update docs: experiment log, dev reference, file index, event log |
| 2026-03-04 | — | Experience redesign: connections, web notes, review context, depth feedback, highlight annotation |
| 2026-03-04 | — | Sicily exploration: 195 articles via explore_topic.py + import_url.py, 781 concepts, 199 connections |
| 2026-03-04 | — | Book Reader (Mode B): full implementation — types, store, content-sync, book-reader.tsx, library shelf, ingestion pipeline, server endpoint, book landing page, context restoration, color-coded cross-book connections. Plus research: Kindle integration, innovative reading UX, 6-week walkthrough simulation |
| 2026-03-04 | — | Book Reader UX polish: chapter transition cards, personal thread in briefings, section mini-map footer, session stats, book completion experience, pipeline enhancements (relationship classification, topic/thesis extraction, key term evolution tracking, books manifest generation) |
| 2026-03-04 | — | Book Reader Session 3: adaptive depth (concept familiarity → skip-to-claims), Socratic reflection prompts, "What you bring" briefing cards, key term familiarity badges, suggested next section in shelf, engagement stats on landing page, enhanced feed book cards |
| 2026-03-05 | — | Concept-centric reader: entity-style concepts (120 named entities replacing 781 sentence-concepts), concept chips zone, ConceptSheet bottom sheet, full article zone rendering fix (sections instead of raw markdown), entity extraction script |

**Deployed**: `exp://alifstian.duckdns.org:8082` (native), `http://alifstian.duckdns.org:8084` (web)

---

## Architecture Overview

### Stack
- **Frontend**: Expo SDK 54 (React Native), expo-router with Tabs layout
- **State**: Module-level variables in `store.ts` (no Redux/Context — fast, simple)
- **Persistence**: AsyncStorage for all user state (signals, reading states, concept states, reviews, voice notes)
- **Logging**: JSONL files via expo-file-system (daily files, sequential write queue)
- **Content**: Static JSON bundles (`articles.json`, `concepts.json`) built offline by Python pipeline
- **Pipeline**: Python script using `trafilatura` for extraction, `claude -p` for LLM processing
- **Deploy**: Hetzner VM via `scripts/deploy.sh` (rsync + expo start)

### Navigation (4 tabs + 1 hidden)
| Tab | Screen | Purpose |
|-----|--------|---------|
| Feed | `index.tsx` | 3 view modes: List, Topics, Triage |
| Library | `library.tsx` | Previously-read articles by recency |
| Review | `review.tsx` | Spaced attention concept review |
| Progress | `stats.tsx` | Reading stats, knowledge map, voice notes, event log |
| (hidden) | `reader.tsx` | Fluid depth article reader |

### Data Flow
```
Twitter Bookmarks ──┐                                    ┌─→ nginx :8083
                    ├─→ build_articles.py ─→ articles.json ─→ app bundle
Readwise Reader ────┘   (every 4h cron)  └─→ concepts.json ─→ app bundle
                                          └─→ manifest.json (hash-based change detection)

App launch → content-sync.ts → check manifest → download if changed → merge preserving user state

User reads → signals claims → updates ConceptState → updates ConceptReview
           → long-press → highlights (persisted)
           → "Research this" → POST /research → claude -p → results on next launch
                           → logs to JSONL
                           → persists to AsyncStorage

explore_topic.py → subtopics + URLs → import_url.py → articles with exploration_tag → feed
```

### Key Types (`app/data/types.ts`)
- `Article`: id, title, author, source_url, hostname, date, content_markdown, sections[], one_line_summary, full_summary, key_claims[], topics[], estimated_read_minutes, content_type, word_count, sources[], similar_articles?, exploration_tag?, parent_id?
- `ArticleSection`: heading, content, summary, key_claims[]
- `ReadingState`: article_id, depth (unread→summary→concepts→sections→full), current_section_index, time_spent_ms
- `UserSignal`: article_id, signal (interesting|knew_it|deep_dive|not_relevant|save), timestamp, depth
- `Concept`: id, name, description, text? (deprecated), topic, source_article_ids[], aliases?[], related_concepts?[]
- `Highlight`: id, article_id, block_index, text, highlighted_at, zone, note?
- `TopicSynthesis`: topic, article_ids[], synthesis_text, generated_at
- `ConceptState`: concept_id, state (unknown|encountered|known), last_seen, signal_count
- `ConceptReview`: concept_id, stability_days, difficulty, due_at, engagement_count, understanding, notes[]
- `VoiceNote`: id, article_id, depth, recorded_at, duration_ms, file_uri, transcript?, transcription_status

---

## Content Pipeline

### `scripts/build_articles.py` (~993 lines)

**Sources**:
1. **Twitter bookmarks** (`~/src/otak/data/twitter_bookmarks.json`): All bookmarks with fetchable URLs. No topic filtering — previously filtered to Claude Code only (score ≥ 0.8), now processes everything.
2. **Readwise Reader** (`~/src/otak/data/readwise_reader.json`): 11,598 items. Content field is null (metadata only). Filtered to articles/RSS with `reading_progress > 0`. Diversity sampling via round-robin across `site_name`.

**3-tier article extraction**:
1. `trafilatura.fetch_url()` + `trafilatura.extract()` — native, fastest
2. `requests` with browser headers + `trafilatura.extract(favor_recall=True)` — handles JS-protected sites
3. `lxml` HTML parsing as last resort — raw text extraction

**LLM processing** (via `claude -p`):
- Generates: sections[], one_line_summary, full_summary, key_claims[], topics[], content_type, estimated_read_minutes
- One `claude -p` call per article with structured JSON prompt

**Concept extraction** (two approaches):

*Legacy (`--concepts-only` flag in `build_articles.py`)*:
- Batches of 5 articles sent to LLM
- Sentence-level concepts — deprecated, replaced by entity extraction

*Entity extraction (`scripts/extract_entity_concepts.py`)*:
- Batches of 5 articles sent to Anthropic API (Claude Sonnet)
- Prompt asks for named entities: people, places, events, theories, techniques (1-6 word noun phrases)
- Each entity: name, description, topic, aliases, source_article_ids
- Cross-batch deduplication via name/alias substring matching
- Second pass extracts `related_concepts` relationships
- Output: `data/concepts.json` with 120 entity-style concepts, 77 with relationships

**CLI flags**:
- `--source twitter|readwise|all`
- `--from filter|fetch|articles` (resume from intermediate step)
- `--concepts-only` (just extract concepts from existing articles)
- `--dry-run` (skip LLM calls)
- `--limit N` (max articles)
- `--incremental` (skip URLs already in articles.json)

**Current output**: 205 articles (195 Sicily exploration + 10 original), 120 entity-style concepts (replacing 781 sentence-concepts), 77 cross-concept relationships

**Exploration pipeline** (`explore_topic.py` → `import_url.py`):
- `explore_topic.py` generates 12-15 subtopics with URLs via `claude -p`, organized into foundational/intermediate/deep tiers
- `import_url.py --from-exploration --chunk` imports all URLs, chunks Wikipedia articles at H2 boundaries
- First run: "Sicily — history, literature, geography, culture" → 15 subtopics, 45 URLs → 195 articles

---

## Experiments & Hypotheses

### Experiment 1A: Fluid Depth Transitions ✅ BUILT

**Hypothesis**: Continuous vertical scrolling through depth levels produces deeper reading than discrete tabs, because removing the "switch tab" decision reduces friction.

**Implementation** (`reader.tsx`, ~2200 lines):
- Single scrollable document: Header → Summary → Concepts → Sections → Full Article
- `FloatingDepthIndicator`: sticky bar at top showing `Summary · Concepts · Sections · Full` with active zone highlighted
- Zone tracking via `onLayout` callbacks → `zonePositions` ref → scroll position comparison
- Reading depth only advances (never regresses) — persisted to `ReadingState`
- Dividers between zones: styled `─── KEY CLAIMS ───` section breaks

**Measurement events**: `reader_scroll_depth`, `reader_section_enter`, `reader_section_exit`, `reader_open`, `reader_close`

**Status**: Built. Needs user testing to compare against previous tab-based metrics.

**Success criteria**: Users reach deeper depth levels, give more signals per article, spend more total time.

---

### Experiment 1B: Inline Claim Signals ✅ BUILT

**Hypothesis**: Presenting claims inline within full text (highlighted, tap-to-signal) produces richer signals than isolated claim list, because context matters for judgment.

**Implementation** (`reader.tsx`):
- `MarkdownText` component with `claimHighlights` prop
- `findMatchingClaim()`: substring match (first 60 chars) with word-overlap fallback (>60% of words >3 chars)
- Color-coded highlights: unsignaled=blue, knew_it=slate, interesting=green, save=blue
- `ClaimSignalPill`: floating overlay with [Knew this] [New to me] [Save] buttons
- Shows `currentSignal` prop — "Already marked · tap to change" for re-reviews
- Claims progress counter: "7 of 12 claims reviewed"

**Measurement events**: `reader_claim_signal_inline` with context=`claims_list` or `full_text_inline`

**Key code**: Claims exist in TWO places — the dedicated claims zone (cards with buttons) AND highlighted in full article text. Both fire the same signal handler → both update `ConceptState`.

---

### Experiment 1C: Implicit Time Tracking ✅ BUILT

**Hypothesis**: Dwell time correlates with explicit interest signals (r > 0.5), validating time as a reliable implicit signal.

**Implementation** (`reader.tsx`):
- **Scroll velocity**: sampled every 200ms, logged when >50px/s, throttled to 1/sec. Distinguishes scanning (fast) vs. reading (slow).
- **Pause detection**: 3-second idle timeout → logs `reader_pause` with scroll position and current zone
- **Revisit detection**: scrolling back >150px below max scroll position → logs `reader_revisit` with from/to positions
- **Zone timing**: `zoneEnterTime` ref tracks enter timestamp per zone → logs duration on zone exit

**Constants**: `PAUSE_THRESHOLD_MS = 3000`, `VELOCITY_SAMPLE_INTERVAL_MS = 200`, `REVISIT_SCROLL_BACK_PX = 150`

**Measurement events**: `reader_scroll_velocity`, `reader_pause`, `reader_revisit`, `reader_section_enter`, `reader_section_exit`

**Status**: Built. Needs log analysis to compute actual correlation with explicit signals.

---

### Experiment 2A: Card-Stack Triage ✅ BUILT

**Hypothesis**: Swipe-based triage produces >3x faster decisions than list browsing, because forced binary choices prevent "I'll decide later" paralysis.

**Implementation** (`index.tsx`, `TriageModeView` + `TriageCard`):
- `PanResponder` with gesture thresholds: swipe right (>30% screen width) = Read Later, left = Skip, up (>15% screen height) = Read Now
- `Animated.spring` for snap-back, `Animated.timing` for dismiss animations
- Card rotation: ±15° at full swipe via `pan.x.interpolate()`
- Stacked cards: top 3 visible, scaling down (1 - index×0.04), translating down (index×8px), fading (1 - index×0.15)
- Action labels fade in as user swipes: green "Read Later" (right), red "Skip" (left), blue "Read Now" (up)
- Triage state persisted to AsyncStorage (`@petrarca/triage_states`)
- Completion screen: "All caught up!" with saved/skipped counts + reset button
- List mode respects triage: after triaging, list shows only `read_later` + `untriaged` items

**Measurement events**: `triage_swipe` (direction, decision, article_id), `triage_mode_enter`, `triage_complete`, `triage_reset`

**Success criteria**: >3x faster triage than list-browse, >50% of "read later" items opened within a week.

---

### Experiment 2B: Topic Clustering Feed ✅ BUILT

**Hypothesis**: Grouping articles by topic helps users engage with ≥3 topics per session (vs. 1-2 with flat list).

**Implementation** (`index.tsx`, `TopicsModeView`):
- Articles grouped by primary topic (`topics[0]`), sorted by cluster size descending
- Collapsible clusters with `LayoutAnimation.Presets.easeInEaseOut` for smooth expand/collapse
- Each cluster: topic name, chevron icon, article count badge
- Expanded cluster shows standard `FeedCard` components

**Measurement events**: `cluster_expand`, `cluster_collapse` with topic and article_count

---

### Experiment 3: Novelty Scoring ✅ BUILT

**Hypothesis**: Showing novelty scores on feed cards changes triage behavior — users prioritize high-novelty articles.

**Implementation** (`store.ts` → `getNoveltyScore()`, `index.tsx` → `NoveltyBadge`):
- Primary: concept-based — `unknown_concepts / total_concepts` for the article
- Fallback: signal-based — `1 - (knew_it_signals / total_signals)` for articles with signals but no concepts
- Returns `null` when no data available (no concepts AND no signals)
- Badge labels: "Mostly new" (≥90%), "X% new" (>60%), "Partly familiar" (>30%), "Mostly known" (≤30%)
- Badge color: green (new), amber (partly familiar), gray (mostly known)

**Measurement**: `feed_item_tap` event includes `novelty` score. Compare: do users preferentially read high-novelty articles?

---

### Experiment 4: Connection Prompting ✅ BUILT

**Hypothesis**: Showing related articles at the end of reading encourages exploration beyond single-article consumption.

**Implementation** (`store.ts` → `getRelatedArticles()`, `reader.tsx`):
- Graph traversal: article → its concepts → other articles sharing those concepts
- Ranked by shared concept count
- "Related Reading" section after full article text
- Cards show: title + "Connects via: concept X · concept Y"
- Limited to top 3 related articles

**Measurement events**: `reader_related_tap` with from_article, to_article, shared_concepts count

---

### Experiment 5: Continue Reading ✅ BUILT

**Hypothesis**: Surfacing partially-read articles reduces abandonment — users resume articles they started.

**Implementation** (`store.ts` → `getInProgressArticles()`, `index.tsx`):
- Filters articles with depth != 'unread' AND depth != 'full'
- Sorted by `last_read_at` descending (most recent first)
- Horizontal scrollable section at top of list view
- Cards: title (2 lines) + depth dot + depth label ("Read summary", "Reviewed claims", etc.)
- Color-coded by depth: blue (summary), purple (claims), amber (sections), green (full)

**Measurement events**: `continue_reading_tap` with article_id and depth

---

### Experiment 6: Time-Aware Reading Guidance ✅ BUILT

**Hypothesis**: Showing time estimates per depth level helps users make better decisions about how deep to go given available time.

**Implementation** (`reader.tsx`):
- Bar below article metadata showing depth/time pairs with icons
- Flash icon: "30s summary" | Bulb icon: "2m claims" | Document icon: "Xm sections" | Book icon: "Xm full"
- Section time is half of full read time; full time is `estimated_read_minutes`

---

## Knowledge Model

### Concept Lifecycle

```
Article processed by entity extraction (extract_entity_concepts.py)
  → LLM extracts named entities: name, description, topic, aliases
  → Deduplication via name/alias substring matching
  → Second pass extracts related_concepts relationships
  → concepts.json (120 entity-style concepts)

User opens reader → concept chips displayed below summary
  → Taps chip → ConceptSheet bottom sheet opens
  → Sets state: Unknown / Learning / Know this
  → ConceptState persisted to AsyncStorage

User signals on claims (still supported)
  → processClaimSignalForConcepts() matches claims to concepts
  → Entity-first matching: substring on concept.name + aliases
  → Fallback to word-overlap for legacy long-form concepts (>6 words)
  → "knew_it" → concept becomes "known"
  → "interesting" → concept becomes "encountered"

User records voice note → Soniox transcribes
  → processTranscriptForConcepts() matches transcript to article's concepts
  → Same entity-first + word-overlap fallback matching
  → Matched concepts become "encountered"
  → ConceptNote created with voice_note_id (deduplicated)
  → Transcript visible in Review tab on matched concepts

ConceptState transitions trigger review creation
  → "unknown" → "encountered": review created, 1-day initial interval
  → "unknown" → "known": review created, 7-day initial interval
  → Review appears in Review tab when due
```

### Concept Matching (`store.ts`)

**Entity-first matching** (primary, for new entity-style concepts):
- `conceptMatchesText(concept, text)`: checks if concept.name or any alias is a substring of the text
- Fast, reliable for short entity names like "Garibaldi" or "Greek colonization"
- Used in: `processClaimSignalForConcepts`, `processTranscriptForConcepts`, `getConceptConnections`, `getMatchingClaims`

**Word-overlap fallback** (for legacy long-form concepts with >6 words):
1. Build `STOP_WORDS` set (200+ common English words)
2. `contentWords(text)`: lowercase, remove punctuation, filter words ≤2 chars and stop words
3. For each article concept, compute `overlap / conceptContent.size`
4. Threshold: >0.3 content word overlap = match for claims, >0.2 for voice transcripts

**Helper functions**:
- `conceptName(c)`: returns `c.name || c.text || ''` — handles both old and new concept formats
- `getConceptsForArticleWithState(articleId)`: returns concepts with their knowledge states for the concept chips UI
- `findConceptsInText(articleId, text)`: finds which concepts from an article appear in a text passage

### Novelty Scoring

Two methods, prioritized:
1. **Concept-based** (preferred): `unknown_concepts / total_concepts` for the article. Uses `articleConceptIndex` (precomputed Map<articleId, conceptId[]>).
2. **Signal-based** (fallback): `1 - (knew_it_count / total_signals)`. Only used when concepts aren't available.
3. Returns `null` when no data at all — badge doesn't render.

### Knowledge Dashboard (`stats.tsx` → `KnowledgeDashboard`)

- `getTopicKnowledgeStats()`: per-topic counts of known/encountered/unknown
- Overall progress bar: (known + encountered) / total concepts
- Per-topic stacked bars: green = known, amber = encountered
- Legend at bottom

---

## Spaced Attention Scheduling

### Design Philosophy

Not flashcards — engagement prompts. The question isn't "what is X?" but "how does X connect to what you've been reading?" Inspired by Matuschak & Haisfield's spaced-everything concept (see `research/spaced-attention.md`).

### Algorithm (`store.ts`)

**Interval calculation** (on review submission):
- Rating 1 (Again/Confused): reset to 1 day, difficulty +0.3
- Rating 2 (Hard/Fuzzy): interval × 1.2, difficulty +0.1
- Rating 3 (Good/Solid): interval × 2.5, difficulty -0.05
- Rating 4 (Easy/Could teach): interval × 3.5, difficulty -0.15
- Stability clamped to [1, 365] days
- Difficulty clamped to [0.3, 3.0]

**Priority queue** (`getReviewQueue()`):
```
priority = overdue_factor × relevance × topic_interest × maturity
```
- `overdue_factor`: min(overdue_days / stability_days, 2.0) — how past-due, capped at 2×
- `relevance`: 1.5 if concept topic matches a recently-read article topic (past 7 days), else 0.7
- `topic_interest`: 1.5 if ≥5 articles read in topic, 1.0 if ≥2, else 0.5
- `maturity`: 1.3 for new concepts (≤1 engagement), 0.8 for mature (≥5), else 1.0

**Auto-creation**: When `updateConceptState()` transitions a concept from `unknown`, a review is auto-created:
- `known` → 7-day initial interval
- `encountered` → 1-day initial interval

### Review UI (`review.tsx`)

Three-phase card flow:
1. **Prompt**: Shows concept text, topic, previous notes, source articles. Asks "How does this connect to what you've been reading?" Options: "Add a note" or "Just rate"
2. **Respond** (optional): TextInput for free-form note. "Continue to rating" button.
3. **Rate**: 4 buttons — Again (red), Hard (amber), Good (green), Easy (blue)

Session flow: progress header ("1 of 10 concepts") → cards → completion screen with topic knowledge overview bars.

**Measurement events**: `concept_review` (concept_id, rating, stability_days, engagement_count, has_note)

---

## Voice Notes

### Recording (`reader.tsx` → `VoiceRecordButton`)

- Uses `expo-av` Audio API
- Permissions check via `Audio.requestPermissionsAsync()`
- Records with `Audio.RecordingOptionsPresets.HIGH_QUALITY`
- Timer display during recording (red styling)
- Note count badge when not recording
- Hidden on web platform (no audio API)

### Storage

- `VoiceNote` type: id, article_id, depth, recorded_at, duration_ms, file_uri, transcription_status
- Persisted to AsyncStorage via `saveVoiceNotes()`
- `transcription_status`: pending → processing → completed | failed

### Transcription (`data/transcription.ts`)

- **Soniox API**: key hardcoded, base `https://api.soniox.com/v1`, model `stt-async-v4`
- **Flow**: upload file → create transcription → poll until complete → get transcript text → cleanup
- **Polling**: 3s interval, 5min timeout
- **Language hints**: en, no, sv, da, it, de, es, fr, zh, id
- **Integration**: After successful transcription, calls `processTranscriptForConcepts()` to link transcript to knowledge model
- **Batch**: `transcribeAllPending()` processes all pending notes sequentially

### Knowledge Model Integration

When a transcript completes:
1. `processTranscriptForConcepts()` matches transcript against article's concepts (0.2 threshold)
2. Matched concepts marked as `encountered`
3. `ConceptNote` created with `voice_note_id` (deduplicated)
4. In Progress tab: expanded voice notes show matched concept pills (purple)
5. In Review tab: `ReviewCard` shows voice transcripts linked to the concept being reviewed

### Stats Display (`stats.tsx`)

- Note count, total duration, unique articles covered
- Last 10 notes with article title, duration, status dot
- Expandable: shows transcript text + matched concept pills (purple)

---

## Key Bug Fixes

### NoveltyBadge never rendered
- **Root cause**: `getNoveltyScore()` returned `1.0` for uninteracted articles (all concepts unknown = 100% novel). Badge component returned `null` when `score >= 1.0`.
- **Fix**: Changed return type to `number | null`. Returns `null` only when no concept data available. Badge renders for all valid scores including 1.0.

### Weak concept-claim matching
- **Root cause**: Word overlap included stop words ("the", "is", "of") inflating match scores. 40% threshold was too high for meaningful words.
- **Fix**: Added `STOP_WORDS` set, `contentWords()` function. Lowered threshold to 0.3 for content-only words.

### Claim highlighting missed paraphrases
- **Root cause**: Only used substring match (first 60 chars of claim in paragraph). Fails when claims are paraphrased.
- **Fix**: Added fallback word-overlap matching (words >3 chars, 60% overlap threshold).

### ClaimSignalPill didn't show prior state
- **Root cause**: No indication when a claim was already signaled. User couldn't tell if they'd already reviewed it.
- **Fix**: Added `currentSignal` prop. Shows "Already marked · tap to change" and highlights active button.

### triage_complete logged on every render
- **Root cause**: `logEvent('triage_complete', ...)` called directly in render body of `TriageModeView`.
- **Fix**: Moved to `useEffect` with `[totalUntriaged]` dependency. Added `triageCompleteLogged` ref to prevent duplicate logs.

### Router not in scope (Continue Reading)
- **Root cause**: `FeedScreen` used `router.push()` in Continue Reading cards but hadn't called `useRouter()`.
- **Fix**: Added `const router = useRouter()` to `FeedScreen`.

### DAY_MS constant ordering
- **Root cause**: `DAY_MS` used in `updateConceptState()` but defined later in file (in scheduling section).
- **Fix**: Moved `const DAY_MS = 24 * 60 * 60 * 1000` to top of `store.ts`.

---

## File Index

### App Code (`app/`)

| File | Lines | Purpose |
|------|-------|---------|
| `data/types.ts` | ~250 | All TypeScript interfaces — Article, Concept, Highlight, TopicSynthesis, Book, BookSection, BookClaim, KeyTerm, CrossBookConnection, BookReadingState, PersonalThreadEntry, etc. |
| `data/store.ts` | ~1100 | Central state management — articles, concepts, highlights, reading states, signals, reviews, novelty scoring, scheduling, transcript→concept matching, highlight notes, claims with attribution, book state (sections, claims, personal thread, progress, context restore) |
| `data/content-sync.ts` | ~170 | Remote content sync — manifest check, download articles/concepts/syntheses/books, lazy chapter section fetching, local cache |
| `data/research.ts` | ~138 | Research agent client — trigger research, fetch results, article-specific queries |
| `data/transcription.ts` | 130 | Soniox voice note transcription — upload, poll, retrieve, concept matching |
| `data/persistence.ts` | ~130 | AsyncStorage load/save pairs for all state including highlights |
| `data/logger.ts` | 103 | JSONL interaction logging with sequential write queue |
| `data/articles.json` | — | Bundled articles (generated by pipeline, updated by content sync) |
| `data/concepts.json` | — | Bundled concepts (generated by pipeline, updated by content sync) |
| `data/syntheses.json` | — | Bundled topic syntheses (generated by pipeline) |
| `app/_layout.tsx` | 86 | Tab navigator: Feed, Library, Review, Progress + hidden Reader |
| `app/reader.tsx` | ~2200 | Fluid depth reader: concept chips zone, ConceptSheet bottom sheet, sections-based full article rendering, highlighting, claim signals, dedup banner, research badge, voice recording, web text notes, claim research buttons, inline highlight annotation, enhanced connections + depth indicator |
| `app/index.tsx` | ~1160 | Feed: List/Topics/Triage, exploration sections, dedup indicators, research banner |
| `app/review.tsx` | ~500 | Spaced attention review: prompt→respond→rate flow, voice transcript display, claims with article attribution, contextual prompts, 3 recent notes |
| `app/stats.tsx` | ~400 | Progress: reading stats, knowledge map, research results, voice notes, event log |
| `app/library.tsx` | ~250 | Library: recent articles + topic view + highlights view |
| `app/markdown-utils.ts` | 167 | Markdown parsing utilities for reader |

### Pipeline (`scripts/`)

| File | Lines | Purpose |
|------|-------|---------|
| `build_articles.py` | ~1050 | Full pipeline: sources → fetch → dedup detection → LLM process → concepts |
| `generate_syntheses.py` | ~166 | Generate topic syntheses for topics with 3+ articles via `claude -p` |
| `explore_topic.py` | ~247 | Generate exploration plan: seed topic → subtopics + URLs via `claude -p` |
| `import_url.py` | ~467 | Import URLs into pipeline: single, batch, exploration plan, Wikipedia chunking |
| `extract_entity_concepts.py` | ~350 | Entity-style concept extraction: batched Anthropic API calls, dedup, relationship extraction |
| `fetch_twitter_bookmarks.py` | ~267 | Fetch Twitter/X bookmarks via twikit (GraphQL API) |
| `fetch_readwise_reader.py` | ~263 | Fetch Readwise Reader items via API |
| `content-refresh.sh` | ~82 | Server cron orchestrator: fetch → build → synthesize → copy to HTTP serving |
| `research-server.py` | ~298 | HTTP server for research agents + exploration research |
| `deploy.sh` | ~24 | Git pull + npm install + restart services on Hetzner |
| `setup-content-server.sh` | ~52 | One-time nginx + cron setup on server |

### Data (`data/`)

| File | Purpose |
|------|---------|
| `articles.json` | Processed articles with sections, summaries, claims, similar_articles |
| `concepts.json` | Extracted concepts across topics |
| `syntheses.json` | Topic syntheses for topics with 3+ articles |
| `manifest.json` | Content hashes for change detection |
| `twitter_bookmarks.json` | Raw fetched Twitter bookmarks (server-side) |
| `readwise_reader.json` | Raw fetched Readwise items (server-side) |
| `bookmarks_filtered.json` | Intermediate: filtered bookmark candidates |
| `articles_fetched.json` | Intermediate: fetched article content before LLM |
| `explorations/*.json` | Exploration plans generated by `explore_topic.py` |

### Research (`research/`)

| File | Purpose |
|------|---------|
| `README.md` | Master index of all research documents |
| `design-vision.md` | Synthesized design vision from 4 interviews + 7 research docs |
| `design-experiments-plan.md` | Original experiment plan (Phases 0-4) |
| `experiment-log.md` | Append-only experiment results |
| `development-reference.md` | This file — comprehensive development record |
| `honest-assessment.md` | Frank self-critique: what works, what doesn't, risk-ranked assumptions |
| `user-journey-analysis.md` | Expected user journey over weeks, gap analysis |
| `content-refresh-design.md` | Architecture for scheduled pipeline + HTTP serving + app sync |
| `interview-analysis.md` | Analysis of initial brainstorm interview |
| `user-requirements.md` | Interview 1: reading contexts, pain points |
| `user-requirements-2.md` | Interview 2: history reading, voice notes, background agents |
| `user-requirements-3.md` | Interview 3: otak status, first experiment, cost prefs |
| `user-requirements-4.md` | Interview 4: hooks philosophy, note-taking paradox |
| `reference-projects.md` | Analysis of ../otak, ../bookifier, ../alif |
| `incremental-reading.md` | SuperMemo, theory, implementations |
| `spaced-attention.md` | Matuschak & Haisfield's spaced-everything |
| `reading-ui-research.md` | CHI/HCI research on reading UIs |
| `voice-processing.md` | Soniox API integration patterns |
| `prior-art.md` | Existing tools and libraries |

---

## What's Not Built Yet

### From the original vision (high priority)

1. ~~**Voice note transcription**~~: ✅ DONE — Soniox integration built, transcripts linked to knowledge model via concept matching

2. ~~**Background research agents**~~: ✅ DONE — "Research this" on highlights + voice notes → POST to Hetzner → `claude -p` → results on next launch. Also exploration-aware `/research/explore` endpoint.

3. ~~**Cross-article synthesis**~~: ✅ DONE — `generate_syntheses.py` groups by topic, generates via `claude -p`. Purple synthesis cards in Topics view. Downloaded via content sync.

4. **Search**: No search across articles or concepts. Even basic text search would be valuable.

5. ~~**Cluster summaries**~~: ✅ DONE — Merged into cross-article synthesis (item 3).

### From the plan (lower priority)

6. **Article priority queue**: Each article scored by `novelty × topic_interest × freshness`. Auto-postpone low-priority items.

7. **Growth over time chart**: Knowledge dashboard shows current state but not trajectory.

8. **Open/configurable algorithms**: User should be able to see and tweak ranking weights.

9. ~~**Progressive summarization**~~: Partially done — paragraph highlighting lets user mark important passages. Not yet feeding highlights back into review summaries.

### Infrastructure

10. ~~**Backend server**~~: ✅ DONE — nginx content server on :8083, research server on :8090, 4-hour cron pipeline. App syncs content on launch.

11. ~~**More content**~~: ✅ Pipeline live — 50 Twitter bookmarks + 11,900 Readwise items as source. Every 4 hours: fetch → build up to 10 new articles → extract concepts → serve via HTTP.

12. **Log analysis tooling**: Logs are captured but there's no analysis pipeline. Need scripts to compute: time per depth, signal distributions, triage speed, concept engagement rates.

### New (identified during sprint)

13. **In-app exploration seed**: Start an exploration from within the app (text input → server → plan → articles appear). Currently requires running `explore_topic.py` manually on server.

14. **Highlight → review integration**: Highlighted paragraphs should feed into the spaced attention review system.

15. **Content quality filtering**: Pipeline ingests some low-quality content (donation pages, short tweets). Need better pre-filtering or quality scoring.

16. **"Why am I seeing this?" on feed cards**: No explanation of why an article is ranked where it is. Could show reading order tags (foundational/intermediate/deep) from exploration plans, or concept overlap reasons.

17. **Concept browser / knowledge map**: Review flow is linear — no way to skip to a specific concept or browse the knowledge graph. Need a topic map view for non-linear review navigation.

18. ~~**Web note-taking**~~: ✅ DONE — `TextNoteInput` component on web, replaces `VoiceRecordButton` which returns null on web.

19. ~~**Inline highlight annotation**~~: ✅ DONE — "Note" button on highlight action bar → TextInput → save to `Highlight.note` via `updateHighlightNote()`.

20. ~~**Claim-level research button**~~: ✅ DONE — "Research" button on each claim card, calls `triggerResearch()` with claim + article context.

21. ~~**Book Reader (Mode B)**~~: ✅ DONE — Full implementation of section-based book reading. `book-reader.tsx` (~1200 lines) with 4-zone progressive depth (Briefing → Claims → Key Terms → Full Text), cross-book connection cards (color-coded: green=agrees, amber=disagrees, blue=extends, purple=evidence), context restoration "Welcome Back" panel (after 3+ days), book landing page with "What You Bring", chapter map, argument-so-far. Library Shelf view with topic grouping and section dots. Ingestion pipeline `ingest_book_petrarca.py` (pymupdf → section splitting → Gemini extraction → cross-book matching). Server endpoint POST /ingest-book.

22. **Kindle integration**: Research completed (see `research/kindle-integration.md`). Readwise API v2 for highlights, kindle-api TypeScript lib for progress. Not yet implemented.

23. **Cross-book topic synthesis**: Synthesis cards exist for articles but not yet for book sections. Need to generate "The Toledo Thread across 4 books" style summaries.

24. **Book-article cross-references**: Book claims should match against article concepts and vice versa. Data model supports this but matching pipeline not yet wired.

25. **Argument Skeleton View**: Visualize thesis → evidence → counterargument tree from BookClaim.supports_claim + is_main fields. Research suggests high pedagogical value (see `research/innovative-reading-patterns.md`).

26. **Socratic Mode**: AI-generated questions personalized to reader's knowledge model. Research shows Socratic beats summary for power readers (Frontiers in Education 2025).

---

## Design Decisions & Tradeoffs

### Why module-level state instead of React Context/Redux?
Store.ts uses plain module variables (`let articles: Article[] = []`). This is intentionally simple — no re-render overhead from context changes, synchronous access from any component via function calls, trivial to understand. The tradeoff is that state changes don't automatically trigger re-renders (components must call `forceUpdate` or use local state that depends on store data). For a single-user experimental app, this is fine.

### Why JSON files instead of a database?
Articles and concepts are generated by the Python pipeline as JSON files, served via nginx, and cached locally on the device. The app checks a manifest hash on launch and downloads new content if changed. This avoids database complexity while supporting live updates every 4 hours. The bundled JSON in the app serves as a fallback when offline or before first sync.

### Why concepts instead of claims as the knowledge unit?
Claims are article-specific statements ("LLMs can generate unit tests"). Concepts are cross-article ideas ("LLM code generation"). Scheduling concepts for review makes more sense because:
- Same concept appears across multiple articles → builds richer understanding
- Concepts are more stable/meaningful than individual claims
- The review prompt "how does this connect?" works better with concepts

### Why expanding intervals instead of full FSRS?
FSRS (used in alif for word-level tracking) is more sophisticated but designed for binary recall (know it / don't). Concept review is on a 4-point scale of understanding depth, not binary. The simpler expanding-interval approach (multiply by 1.2-3.5 based on rating) is adequate for the prototype and easier to tune.

### Why three view modes on one screen instead of separate tabs?
List, Topics, and Triage are different ways to interact with the same article set. Keeping them as toggle modes on one screen (rather than separate navigation tabs) means:
- Triage results immediately affect list view (triaged items hidden)
- User can quickly switch between exploration modes
- Less navigation chrome

### Why claim matching uses word overlap, not embeddings?
Embedding-based matching would be more accurate but requires a model/API call. Word overlap with stop-word removal is fast, runs client-side, and is "good enough" for the matching task (claims are typically close paraphrases of sentences in the article). If accuracy becomes an issue, could add embedding similarity as a pipeline preprocessing step.

---

## Event Logging Reference

Every user interaction is logged to JSONL via `logEvent()`. Events by screen:

### Global
| Event | Data |
|-------|------|
| `session_start` | session_id |
| `store_initialized` | total_articles, total_concepts, loaded_signals, loaded_reading_states, loaded_concept_states, loaded_concept_reviews, loaded_voice_notes |
| `tab_press` | tab |

### Reader
| Event | Data |
|-------|------|
| `reader_open` | article_id, title, previous_depth |
| `reader_close` | article_id, time_spent_ms, final_depth |
| `reader_scroll_depth` | article_id, depth, scroll_y |
| `reader_section_enter` | article_id, section |
| `reader_section_exit` | article_id, section, time_ms |
| `reader_scroll_velocity` | article_id, velocity, direction, section |
| `reader_pause` | article_id, scroll_y, section, pause_duration_ms |
| `reader_revisit` | article_id, from_y, to_y, section |
| `reader_claim_signal_inline` | article_id, claim_index, claim_text, signal, context |
| `reader_section_toggle` | article_id, section_index, heading, expanded |
| `reader_open_source` | article_id, url |
| `reader_related_tap` | from_article, to_article, shared_concepts |
| `reading_state_update` | article_id, depth, section_index, time_spent_ms |
| `paragraph_highlight` | article_id, block_index, zone |
| `paragraph_unhighlight` | article_id, block_index |
| `highlight_research_tap` | article_id, block_index, text_preview |
| `highlight_note_added` | article_id, block_index, note_length |
| `claim_research_tap` | article_id, claim_index |
| `text_note_submitted` | article_id, depth, text_length |
| `reader_connection_shown` | article_id, concept, other_article_count |
| `reader_connection_tap` | article_id, concept, target_article_id |
| `concept_chip_tap` | article_id, concept_id, concept_name |
| `concept_state_change` | concept_id, from, to |
| `concept_sheet_article_tap` | concept_id, target_article |
| `concept_sheet_related_tap` | from_concept, to_concept |
| `concept_explore_tap` | concept_id, concept_name |

### Feed
| Event | Data |
|-------|------|
| `feed_item_tap` | article_id, title, novelty |
| `feed_view_mode` | mode |
| `feed_toggle_filter` | show_all |
| `continue_reading_tap` | article_id, depth |
| `triage_mode_enter` | total_articles |
| `triage_swipe` | direction, decision, article_id, title |
| `triage_complete` | read_later, skipped, total |
| `triage_reset` | — |
| `cluster_expand` | topic, article_count |
| `cluster_collapse` | topic, article_count |

### Review
| Event | Data |
|-------|------|
| `concept_review` | concept_id, rating, stability_days, engagement_count, has_note |
| `review_source_tap` | concept_id, article_id |

### Knowledge Model
| Event | Data |
|-------|------|
| `concept_state_update` | concept_id, state, signal_count |
| `signal` | article_id, signal, title, topics, depth, section_index |

### Voice
| Event | Data |
|-------|------|
| `voice_note_start` | article_id, depth |
| `voice_note_added` | article_id, depth, duration_ms |
| `voice_note_permission_denied` | article_id |
| `voice_note_transcribed` | note_id, article_id |
| `transcript_concepts_matched` | article_id, voice_note_id, matched_count, concept_ids |
| `transcription_start` | note_id, article_id |
| `transcription_complete` | note_id, article_id, length |
| `transcription_empty` | note_id |
| `transcription_error` | note_id, error |
| `transcribe_all_start` | pending_count |
| `transcribe_all_complete` | completed_count |

### Content Sync
| Event | Data |
|-------|------|
| `content_downloaded` | article_count, concept_count, synthesis_count |
| `content_refreshed` | new_articles, new_concepts |
| `knowledge_preseed` | preseeded_count |

### Research
| Event | Data |
|-------|------|
| `research_triggered` | article_id, query |
| `research_result_viewed` | result_id |

### Stats
| Event | Data |
|-------|------|
| `stats_refresh` | — |
| `logs_exported` | — |
