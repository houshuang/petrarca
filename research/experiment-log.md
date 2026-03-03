# Experiment Log

> Append-only. New entries at top. Never delete existing entries.

---

## 2026-03-03 — Sprint: Highlighting, Dedup, Exploration, Live Pipeline

**What**: Full implementation sprint covering 8 parts across 19 files. Two concrete use cases driving the work: (1) live Twitter/Readwise pipeline running every 4 hours, (2) guided topic exploration mode for Sicily research trip.

**Implemented**:

1. **Paragraph highlighting** (`types.ts`, `persistence.ts`, `store.ts`, `reader.tsx`, `library.tsx`): Long-press any paragraph in full article view → amber highlight with haptic feedback. Highlights persisted to AsyncStorage. New "Highlights" view mode in Library tab groups highlights by article, sorted by recency. 4-second action bar appears after highlighting with "Research this" option.

2. **Dedup detection** (`build_articles.py`, `types.ts`, `reader.tsx`, `index.tsx`): Pipeline computes Jaccard similarity on topics + claim words between new and existing articles. Articles with score > 0.5 get `similar_articles` array. Reader shows amber "Similar to: [title]" banner below summary. Feed cards show italic dedup indicator.

3. **Topic synthesis prominence** (`content-sync.ts`, `store.ts`, `index.tsx`): Syntheses now downloaded from server alongside articles/concepts. Loaded from cached content on init. Purple synthesis cards shown in topic clusters view.

4. **Research agent enhancement** (`reader.tsx`, `index.tsx`, `stats.tsx`): "Research this" button on highlights sends paragraph text to research server. Auto-fetch research results on app launch with banner "N research results ready". Research results section promoted higher in Progress tab. Purple badge in reader top bar shows count for current article.

5. **Topic exploration mode** (`explore_topic.py`, `import_url.py`, `index.tsx`, `research-server.py`): New `explore_topic.py` takes seed topic, uses `claude -p` to generate 12-15 subtopics with URLs. `import_url.py` fetches and processes URLs through pipeline, supports Wikipedia H2 chunking. Feed shows "Exploring: {tag}" sections with breadth-first subtopic mixing. New `/research/explore` endpoint finds more content for subtopics user shows interest in.

6. **Live content pipeline** (`content-refresh.sh`, `fetch_twitter_bookmarks.py`, `fetch_readwise_reader.py`): Server-side cron every 4 hours. Fetches Twitter bookmarks via twikit + Readwise Reader via API. Runs `build_articles.py` and `generate_syntheses.py`. Copies output to nginx content directory. App syncs on launch via manifest hash comparison.

7. **Honest assessment** (`research/honest-assessment.md`): Frank self-critique document covering what works, what doesn't, risk-ranked assumptions, experiments that would matter.

**Server deployment**:
- Python venv with twikit, requests, trafilatura on Hetzner
- nginx content server on port 8083
- 4-hour cron at `/etc/cron.d/petrarca-refresh`
- Initial run: 50 Twitter bookmarks, 11,900 Readwise items fetched, 10 articles built, 11 concepts extracted
- Research server restarted with `/research/explore` endpoint
- Twikit cookies + Readwise token deployed

**Measurement events added**: `paragraph_highlight`, `paragraph_unhighlight`, `highlight_research_tap`

**Files changed**: 19 files, +2543 lines

---

## 2026-03-03 — Remaining Gap Fixes: Content Refresh, Research Agents, Synthesis, Connections

**What**: 7-agent swarm implementing all remaining gaps from the user journey analysis. These complete the core vision: live content, background research, cross-article synthesis, in-reading connections, knowledge pre-seeding, and scroll position persistence.

**Implemented (7 tasks)**:

1. **Concept ID stability** (`build_articles.py`): Switched from sequential `c0001` to `sha256(text)[:10]` hash-based IDs. Concept states, reviews, and notes now survive pipeline re-runs. All 176 concepts regenerated with stable IDs.

2. **Content refresh** (`content-sync.ts`, `store.ts`, `build_articles.py`, `setup-content-server.sh`): Full architecture for live content updates. Pipeline generates manifest.json with content hashes. App loads cached remote content on launch, checks for updates in background, merges new content preserving all user state. nginx serves on port 8083, cron runs pipeline daily at 7 AM UTC on Hetzner. Pipeline now supports `PETRARCA_SOURCES` env var for server-side source paths.

3. **Pre-seed knowledge** (`preseed_knowledge.py`, `store.ts`): Reads 537 Readwise items with >30% reading progress, matches against concept topics, pre-seeds 61/176 concepts as "encountered" on fresh install. Eliminates cold start — novelty scores differentiate from day 1.

4. **In-reading connection prompts** (`reader.tsx`, `store.ts`): New `getConceptConnections()` finds concepts matching a claim that the user has encountered in other articles. `ConnectionIndicator` component shows subtle purple pill below claims: "{topic} · seen in N other articles". Tappable to expand article titles. Logs `reader_connection_shown` and `reader_connection_tap`.

5. **Background research agents** (`reader.tsx`, `research.ts`, `research-server.py`, `stats.tsx`): Full pipeline: voice note transcription → "Research this?" banner → POST to Hetzner server → `claude -p` background research → results fetched in Progress tab. Server runs as systemd service. Results show perspectives, recommendations, connections in expandable cards.

6. **Cross-article synthesis** (`generate_syntheses.py`, `syntheses.json`, `index.tsx`, `store.ts`): Groups articles by primary topic, generates synthesis via `claude -p` for topics with 3+ articles. 2 syntheses generated (claude-code, ai-agents). Shown as purple-accented cards at top of expanded topic clusters in Topics view.

7. **Return-to-position** (`reader.tsx`, `store.ts`, `types.ts`): Saves scroll position every 2s, restores on re-entry with "Continuing where you left off" fade indicator. Clears when article fully read.

**Measurement events added**: `content_downloaded`, `content_refreshed`, `knowledge_preseed`, `reader_connection_shown`, `reader_connection_tap`, `research_triggered`, `research_result_viewed`, `synthesis_viewed`, `reader_position_restored`, `review_session_end_early`

---

## 2026-03-03 — User Journey Audit + Critical Gap Fixes

**What**: Comprehensive audit of assumed user journey vs. actual implementation, identifying 28 gaps and 5 critical assumption mismatches. Then a 5-agent parallel swarm to research, simulate, and fix the highest-impact gaps.

**User Journey Analysis** (`research/user-journey-analysis.md`):
Walked through 7 phases of expected use (first launch → months of habitual use). Found the biggest mismatches between what the design vision promises and what the implementation delivers:
1. Static content (no refresh mechanism — app dies after week 1)
2. "Reading is the signal" not true (only explicit button taps update knowledge model)
3. Cold start (all articles show "Mostly new", knowledge model too thin)
4. Background research agents unbuilt (key interview request)
5. Full article markdown rendering broken at deepest reading level

**Fixes Applied (3 agents, parallel)**:

1. **Markdown rendering** (`reader.tsx`, `markdown-utils.ts`): Rewrote MarkdownText to use proper block splitting (preserving code fences), ordered lists, blockquotes, italic, image alt-text. Added `splitMarkdownBlocks()` and `parseMarkdownBlock()` with 26 passing tests.

2. **Implicit signals → knowledge model** (`store.ts`, `reader.tsx`): New `processImplicitEncounter(articleId)` function. When user dwells >60s in claims/sections/full zone, all unknown concepts for that article auto-transition to "encountered". Fires once per reader session, excludes summary zone. Logs `implicit_concept_encounter` events.

3. **Review UX** (`review.tsx`, `store.ts`): Session capped at 7 items (`SESSION_CAP = 7`). "Done for now" messaging replaces "Session complete!" — soft hint shows remaining items. New `getMatchingClaims(conceptId)` function finds relevant claim excerpts via contentWords overlap (>0.2 threshold), shown on review cards for context.

**Research Delivered (2 agents, parallel)**:

4. **Knowledge model simulation** (`scripts/simulate_knowledge_model.py`): Modeled behavior over realistic usage. Key findings: 55% of articles had zero concepts (invisible to knowledge model), 25% of concepts unreachable at 0.3 threshold. Recommended: extract concepts for ALL articles, lower threshold, aim for ~280 concepts.

5. **Content refresh architecture** (`research/content-refresh-design.md`): Designed pipeline-on-Hetzner with daily cron, nginx serving JSON on port 8083 with manifest-based change detection, app fetches remote content with bundled fallback. Identified concept ID stability issue (must switch from sequential to hash-based IDs).

**Concept Re-extraction**: Based on simulation findings, re-ran concept extraction on all articles:
- 69 → **186 concepts** (2.7x increase)
- 39 → **107 topics**
- Article coverage: 21/47 (45%) → **47/47 (100%)**
- Concepts per article: median 4, range 2-8
- Cross-article concepts: 8 → **15**

**Measurement events added**: `implicit_concept_encounter` (article_id, trigger_zone, dwell_ms, concepts_updated, concept_ids), `review_session_end_early`

---

## 2026-03-03 — Voice Transcript → Knowledge Model Integration

**What**: Connected voice note transcripts to the knowledge model. Previously, transcripts were displayed but never analyzed. Now they're matched against article concepts, updating concept states and creating linked review notes.

**Implementation**:
- **`processTranscriptForConcepts()`** in `store.ts`: Same content-word matching as claim signals, but with 0.2 threshold (lower than claims' 0.3 — transcripts are noisier, already scoped to article's concepts). Matched concepts marked as `encountered`. Creates `ConceptNote` entries with `voice_note_id` set, deduplicated.
- **`getVoiceNoteById()`** accessor in `store.ts`
- **Wired into transcription flow**: `transcription.ts` calls `processTranscriptForConcepts()` immediately after successful transcription
- **Concept pills in Progress tab**: Expanded voice notes with transcripts show matched concepts as purple pills below the transcript text
- **Voice transcripts in Review tab**: `ReviewCard` shows linked voice note transcripts (mic icon, duration, date) between last note and source articles sections

**Tests**: New `__tests__/transcript-concepts.test.ts` — tests matching, state updates, note creation, deduplication, empty results, `getVoiceNoteById`

**Measurement events**: `transcript_concepts_matched` (article_id, voice_note_id, matched_count, concept_ids)

---

## 2026-03-03 — Spaced Attention Scheduling + Deployment

**What**: Built the spaced attention scheduling system (Phase 4a from plan) and deployed all changes to Hetzner.

**Implementation**:
- **Review tab**: New tab in navigation for concept-level spaced re-engagement
- **Scheduling algorithm**: Expanding intervals with difficulty tracking. Ratings map to multipliers: again(reset to 1d), hard(×1.2), good(×2.5), easy(×3.5). Difficulty adjusts ±0.1-0.3 per review.
- **Priority queue**: Concepts ranked by `overdue × relevance × topic_interest × maturity`. Relevance boosted 1.5× for concepts matching recent reading topics. Topic interest based on article engagement depth. New concepts get 1.3× maturity boost.
- **Review flow**: Card shows concept → previous notes → prompt "How does this connect?" → optional text note → 4-point understanding rating (confused / fuzzy / solid / could teach)
- **Auto-creation**: When claim signals transition a concept from unknown to encountered/known, review states are auto-created. "Known" starts at 7-day interval, "encountered" at 1-day.
- **Knowledge overview**: After completing review session, shows topic-level progress bars

**Types added**: ConceptReview, ConceptNote, ReviewRating
**Store functions**: getReviewQueue(), submitReview(), ensureReviewStates(), getConceptReview()
**Measurement events**: `concept_review` (concept_id, rating, stability_days, engagement_count, has_note)

**Deployment**: `exp://alifstian.duckdns.org:8082` — all features live including fluid reader, triage, knowledge model, voice notes, and review

---

## 2026-03-03 — Bug Fixes + Voice Notes + Connection Prompting

**What**: Fixed critical bugs in knowledge model (NoveltyBadge never rendered, weak concept matching). Added voice note recording, connection prompting, continue reading, and time-aware reading guidance.

**Bug Fixes**:
- NoveltyBadge: returned null when score >= 1.0, which was always true for uninteracted articles. Now returns null only when no concept data available.
- Concept matching: replaced raw word overlap (40% threshold including stop words) with content-word matching (30% threshold, stop words removed). Significantly better matching accuracy.
- Claim highlighting: added fallback word-overlap matching when substring match fails (handles paraphrased claims).
- ClaimSignalPill: now shows current signal state so users know when they've already reviewed a claim.
- triage_complete: moved from render body to useEffect to prevent logging on every render.

**New Features**:
- **Voice notes** (expo-av): mic button in reader top bar, records audio linked to article + reading depth context. VoiceNote type with transcription_status field for future Soniox integration. Voice notes summary in stats screen.
- **Connection prompting**: Related articles section at end of reader shows articles sharing concepts. Uses concept graph to find connections ("Connects via: concept X · concept Y").
- **Continue Reading**: horizontal scroll section at top of feed showing partially-read articles sorted by recency.
- **Time guidance**: bar in reader header showing time budget per depth level (30s summary, 2m claims, Xm sections, Xm full).

**Measurement events added**: `voice_note_start`, `voice_note_added`, `voice_note_permission_denied`, `continue_reading_tap`, `reader_related_tap`

---

## 2026-03-03 — Deep Design Experiments (Phase 1-3)

**What**: Major redesign cycle implementing 5 design experiments with specific hypotheses, building on the article-first foundation. Expanded content pipeline from 12 to ~50 articles across diverse topics (history, literature, AI/tech, policy). Built three experimental reader/feed modes.

**Hypotheses & Experiments**:

1. **Experiment 1A — Fluid Depth Transitions**: Replaced 4 discrete tabs with single scrollable document (Summary → Claims → Sections → Full Article). Hypothesis: continuous scrolling reduces friction and produces deeper reading than tab switching. Sticky floating depth indicator tracks position.

2. **Experiment 1B — Inline Claim Signals**: Claims highlighted in full article text with tap-to-signal floating pill. Hypothesis: in-context claim evaluation produces richer signals than isolated claim list. Color-coded: unsignaled=blue, knew_it=slate, interesting=green, save=blue.

3. **Experiment 1C — Implicit Time Tracking**: Silent instrumentation logging section_enter/exit timestamps, scroll_velocity, pause_duration (>3s), revisit events. Hypothesis: dwell time correlates with explicit interest signals (r>0.5).

4. **Experiment 2A — Card-Stack Triage**: Tinder-style swipe cards (right=save, left=skip, up=read now) with spring physics, rotation, stacked card depth. Hypothesis: forced binary choices produce >3x faster triage than list browsing.

5. **Experiment 2B — Topic Clustering**: Articles grouped by primary topic with collapsible headers. Hypothesis: clustering helps users engage with ≥3 topics per session vs 1-2.

**Pipeline Changes**:
- Removed Claude Code topic filter — processes ALL Twitter bookmarks with fetchable URLs
- Added Readwise Reader as second source (11,598 items, filtered to engaged articles with reading_progress > 0)
- Diversity sampling: round-robin across site_names to ensure topic breadth
- Incremental mode: skip URLs already in articles.json
- Target: ~50 articles across history, AI/tech, policy, literature, cultural theory

**UI Changes**:
- `reader.tsx` — Complete rewrite: fluid scrollable document, zone-based depth tracking, inline claim highlights with floating signal pill, implicit scroll/pause/velocity/revisit tracking
- `index.tsx` — Complete rewrite: 3 view modes (List/Topics/Triage), PanResponder card stack with Animated spring physics, LayoutAnimation topic clusters, AsyncStorage triage state persistence

**Measurement**: All interactions logged via logEvent() to JSONL. Events: reader_scroll_depth, reader_section_enter/exit, reader_scroll_velocity, reader_pause, reader_revisit, reader_claim_signal_inline, triage_swipe, cluster_expand/collapse, feed_view_mode.

---

## 2026-03-02 — Article-First Redesign

**What**: Complete redesign from tweet-triage app to article-first progressive reader. New data pipeline fetches actual article content, LLM processes it into sections/summaries/claims, and the app presents content at four progressive depth levels.

**Changes**:

Pipeline:
- New `scripts/build_articles.py` — 4-step pipeline: filter bookmarks → fetch articles (3-tier: trafilatura → requests+trafilatura → lxml) → deduplicate → LLM section/summary processing via `claude -p`
- Follows URLs in quoted tweets, treats long-form tweets (>100 words) as articles themselves
- Outputs `data/articles.json` with structured article data (sections, summaries, claims, topics)

Data model:
- `Article` replaces `Bookmark` as primary entity — includes content_markdown, sections[], key_claims[], reading state tracking
- `ReadingState` tracks per-article depth (unread → summary → claims → sections → full), section position, time spent
- `UserSignal` now references article_id with depth context

UI:
- **Feed** (index.tsx) — article list with title, source, summary, topics, read time
- **Reader** (reader.tsx) — progressive depth: Summary → Claims → Sections → Full article, with depth indicator tabs
- **Library** (library.tsx) — articles you've engaged with, by recency or topic
- **Progress** (stats.tsx) — reading depth breakdown, time spent, topic coverage

Results: 12 articles extracted from 41 filtered bookmarks. Simonwillison posts (previously failed) now extracted via 3-tier approach. Karpathy's 1125-word tweet treated as article.

---

## 2026-03-02 — Add Comprehensive Interaction Logging

**What**: Added JSONL-based interaction logging, persistent signal storage, and instrumented all screens. Modeled after ../alif's dual-layer logging system.

**Changes**:
- `app/data/logger.ts` — JSONL file logger writing daily files to device filesystem (`logs/interactions_YYYY-MM-DD.jsonl`). Session tracking, sequential write queue, export capability.
- `app/data/persistence.ts` — AsyncStorage-based persistence for user signals (survive app restarts).
- `app/data/store.ts` — Wired up persistence (load on init, save on every signal) and logging (log every signal with bookmark context).
- `app/app/_layout.tsx` — Store initialization, session start on app launch, tab press logging.
- `app/app/index.tsx` — Logs: `triage_swipe` (with direction, signal, position, remaining count, expand state), `card_toggle_expand`, `link_open`, `triage_complete`.
- `app/app/briefing.tsx` — Logs: `briefing_item_toggle`, `briefing_signal`, `briefing_topic_toggle`, `briefing_view_mode`, `link_open`.
- `app/app/claims.tsx` — Logs: `claim_source_toggle`, `claim_signal`, `link_open`.
- `app/app/stats.tsx` — Logs: `stats_refresh`, `logs_exported`. Added Event Log section with file listing and share/export.
- Added `expo-file-system` and `@react-native-async-storage/async-storage` dependencies.

**Events tracked**:
| Event | Screen | Data |
|-------|--------|------|
| `session_start` | global | session_id |
| `store_initialized` | global | total_bookmarks, loaded_signals |
| `tab_press` | global | tab name |
| `triage_swipe` | triage | direction, signal, bookmark_id, position, was_expanded, remaining |
| `signal` | all | bookmark_id, signal, author, topics, relevance, content_type |
| `card_toggle_expand` | triage | bookmark_id, expanded |
| `link_open` | all | bookmark_id, url, screen |
| `triage_complete` | triage | totals by signal type |
| `briefing_item_toggle` | briefing | bookmark_id, expanded |
| `briefing_signal` | briefing | bookmark_id, signal |
| `briefing_topic_toggle` | briefing | topic, collapsed, item_count |
| `briefing_view_mode` | briefing | mode |
| `claim_source_toggle` | claims | bookmark_id, claim excerpt, show |
| `claim_signal` | claims | bookmark_id, signal |
| `stats_refresh` | stats | — |
| `logs_exported` | stats | — |

**Rationale**: Since this is an experimental app, all user interactions need to be captured for later analysis — understanding which UI patterns work, how triage decisions are made, whether the swipe-vs-button paradigm affects signal distribution, etc.

---

## 2026-03-02 — Project Kickoff

**What**: Initialized Petrarca project. Analyzed interview.md for incremental reading concepts. Set up research directory structure. Beginning deep research on incremental reading, prior art, and knowledge modeling.

**Context**: User wants a mobile read-later app combining incremental reading, knowledge modeling (what do I already know?), and intelligent article selection (which articles have genuinely new information for me?). Key test case: Claude Code articles — high interest but overwhelming volume.

**Key reference**: ../alif project as model for mobile setup (Expo) and granular knowledge modeling (FSRS at word level → adapt to concept/topic level).
