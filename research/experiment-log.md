# Experiment Log

> Append-only. New entries at top. Never delete existing entries.

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
