# Experiment Log

> Append-only. New entries at top. Never delete existing entries.

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
