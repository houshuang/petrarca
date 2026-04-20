# Knowledge System Implementation Status

**Date**: April 20, 2026 (last updated — session 87: silent-drop fixes in voice-capture entity pipeline + deploy drift prevention + Claude-only directive)

## Session 87: Voice-Capture Silent-Drop Fixes + Iran Backfill Validation + Claude-only Directive (April 20, 2026)

### What
Session 86 closed with a real Iran Revolution voice capture (`vt_1776697230_4034` entity-path + `vt_1776697289_4034` curriculum-path, 3518 chars, 6 entities, 10 ML cards) that ran the full pipeline end-to-end and exposed five concrete drops. This session addressed the three highest-priority ones and validated them against real data by regenerating the 6 Iran entities' `cached_question` with the new prompt. User ended the session by declaring an end to all Gemini usage ("i can't afford gemini") — saved as a durable preference and scoped into a parallel migration session.

### P0.1 — Pre-gen retry for 429s (`review_engine.py:_pregen_entity_questions`)
`_pregen_entity_questions` previously swallowed LLM failures silently (`if not q: continue`). A Gemini 429 at 15:01:43 dropped Khomeini's entire `cached_question` generation; the only log was `Pre-generated 5/6 questions` with no indication which entity failed. Refactored to return outcome strings (`ok/skip/empty/error`) per entity, log distinctly per failure, and retry `empty`+`error` kids once after a 60s cooldown (matches Gemini's per-minute quota window).

### P0.3 — `_rank_wonderings` helper, rank before truncating (`review_engine.py:1327`)
`wonderings[:5]` dropped the richest wondering from the Iran curriculum-path transcript: *"how did the revolution manage to be both conservative/backward-looking AND inspired by French Revolution and student sit-ins?"* (125 chars, 1 question mark — the 6th in Gemini's emitted order). New helper scores `len(w) + 40 * count('?')`, sorts descending, takes top-k. Applied at both voice-capture sites (`:5581` curriculum path, `:5993` entity path). Validated deterministically: the Iran capture's 6th wondering now ranks #1.

### P1.1 — `temporal_hook` in `_ENRICH_PROMPT` (`review_engine.py:1344`)
All 6 Iran entities had empty `temporal_hook` despite the transcript containing "November 4, 1979", "January 20, 1981", "444 days", "two weeks later". Root cause: `_ENRICH_PROMPT` output schema was `{"rich_answer":"...","memory_hook":"..."}` — `temporal_hook` was initialized to `''` in `_key_fact_to_question` but the prompt never asked the LLM to fill it. Added `temporal_hook` as a third output field with 3 BAD / 3 GOOD examples (all grounded in the Iran transcript's own temporal scaffolding: "444 days from Nov 4 1979 to Jan 20 1981 — Carter's last day, Reagan's first"; "Two weeks after the Shah fled, Feb 1979"; "1953, 26 years before the revolution"). STRICT anti-hallucination clause mirrors the existing `_ENRICH_ENTITY_GRAPH_BLOCK` rule. Consumes `enriched['temporal_hook']` in `_key_fact_to_question` when non-empty.

### Also lifted `import sqlite3` to module scope
`_process_voice_capture_entity_path` had `except sqlite3.OperationalError` with no `sqlite3` binding in scope — a real DB-lock during concurrent microlearning would NameError and the server would return 500. Lifted the import to line 13.

### Iran backfill — P1.1 validation on real data
NULLed `cached_question` for the 6 Iran entities, regenerated via `generate_entity_question()` using the new prompt. **100% temporal_hook fill rate.** Every hook was a specific same-moment anchor, not a vague span:
- Iranian Revolution: *"Nov 4 1979 to Jan 20 1981 — Carter's final day in office, Reagan's first"* (72c)
- Brzezinski: *"During the revolution that overthrew Mohammad Reza I (1978–79)"* (112c)
- Mohammad Reza Pahlavi: *"Two weeks before Khomeini returned to Iran on February 1, 1979"* (62c)
- Khomeini: *"Feb 1979, the same year Brzezinski was navigating the collapse"* (83c)
- Argo: *"November 1979, eight months after Khomeini returned to establish the Islamic Republic"* (85c)
- Jimmy Carter: *"444 days from Nov 4 1979 to Jan 20 1981 — Carter's last day in office, Reagan's first"* (140c)

Regen bypassed Gemini by monkey-patching `_generate_follow_up_queries = lambda *a, **kw: []` — only Claude Sonnet ran for the enrichment path.

### Deploy-script server-drift prevention (`~/src/expo/scripts/deploy.sh`)
Prior agent sessions have occasionally edited files directly in `/opt/petrarca/` on the server to test something live, without committing back. The next deploy then hits a cryptic "local changes would be overwritten by merge" and aborts mid-stream. Added pre-pull server-side `git status --porcelain | grep -v '^??'` check that prints the dirty files + reconciliation commands and hard-aborts before touching the server further. End-to-end verified by injecting a fake drift line, watching the abort fire, and cleaning up. Caught exactly this scenario once already this session (the `import sqlite3` that last turn had applied to the running server but never committed).

### Retention-projection analysis on the Iran capture
Used the regenerated bundle + the 10 ML cards + the transcript to project what the user would retain after a year of perfect recall vs. what the transcript contained. Findings:
- **Gain** (~3× more than the raw capture): specific dates, names (Mendez, Bazargan, Freedom Movement), newspapers (Keyhan, Ettela'at), historical parallels (1953 Mossadegh, Eden/Suez, Augustus), quantitative anchors (52 hostages, 2,500 years).
- **Lost**: 4 failed ML cards (torture, demands misunderstood, transitional PM, Khomeini-at-embassy), the user's uncertainty markers (*"Egypt or Morocco"*, *"I'm not sure who paid"*), the "another shot was fired" moment, one accuracy contradiction (two sibling ML cards disagree on Khomeini's age — 76 vs 78).
- **False alarm**: the "richest wondering dropped" concern resolved itself — the Iran capture was processed *before* this session's `_rank_wonderings` deploy, so `wonderings[:5]` truncated it. Future captures will keep it.

### Claude-only directive
User (end of session): *"let's always use claude, i can't afford gemini"*. Saved as `memory/feedback_claude_only_never_gemini.md` — overrides CLAUDE.md's "Gemini for interactive paths" rule-of-thumb. CLAUDE.md § LLM Calling Discipline updated with a prominent warning pointer. Actual migration scoped for SESSION_88.

### Parallel session prompts for 88 + 89
Wrote two self-contained session prompts so the user can spawn them in parallel worktrees:
- `SESSION_88_GEMINI_TO_CLAUDE.md` — migrate ~60 call sites across 32 files to Claude. Tiered (Tier 1 active live paths, Tier 2 batch scripts, Tier 3 disabled subsystems skip, Tier 4 special cases like `call_with_search` needing user input, Tier 5 experiments optional). First step: remove `claude_llm.py`'s Gemini fallback.
- `SESSION_89_GAP_CLEANUP.md` — P0.2 (ML retry sweep on startup, recovers the 4 failed Iran cards), P1.2 (cross-path wondering dedup), optional P2.x (accuracy + uncertainty preservation). Explicitly tells the agent NOT to chase the "richest wondering dropped" false alarm.

### Files
- MODIFIED: `scripts/review_engine.py` (three fixes + sqlite3 import, +84 / −11 lines)
- MODIFIED: `~/src/expo/scripts/deploy.sh` (drift check, +22 lines)
- MODIFIED: `CLAUDE.md` (LLM Calling Discipline pointer)
- NEW: `memory/feedback_claude_only_never_gemini.md`
- NEW: `SESSION_88_GEMINI_TO_CLAUDE.md`, `SESSION_89_GAP_CLEANUP.md`

### Commits
- `024b7ec` — "Fix silent drops in voice-capture entity pipeline"
- `efd3700` (in `~/src/expo`) — "Check server-side git tree before pulling"

### Next (for Session 88 + 89)
User will spawn both in parallel with `isolation: "worktree"`. 88 migrates Gemini → Claude; 89 recovers the 4 stuck Iran ML cards + dedups cross-path wonderings. Both avoid the other's call sites so they can merge cleanly.

---

## Session 86: Voice Calibration Page + Synthetic-Capture Incident + Provenance Hardening (April 19–20, 2026)

### What
Built a voice-capture calibration HTML page showing, for each transcript, exactly how extracted facts are routed to curriculum nodes and entities, and every quiz "angle" (main question + multicue microlearning_quizzes rows) generated from each fact_id. While demoing it, discovered that most recent `voice_capture` rows were not real user recordings — Session 76–77 agents had POSTed synthetic text to `/explore/capture` to validate pipeline behavior, producing rows stylistically similar to but distinct from the user's actual speech (no disfluencies; factual additions the user had never heard, e.g. "Operation Ajax" in the Iran transcript).

### Calibration page — `/voice/calibration`
- `scripts/voice_calibration.py` (318 lines) builds a per-transcript payload: transcript + `llm_result.facts[]` (with `source_excerpt` → substring-matched spans, `node_ids`, `entities`, confidence), `node_assessments`, `wonderings`, `confidence_tagged`, plus for each touched curriculum node the KI's `cached_question` (main Q, rich_answer, memory_hook, quiz_suggestions, follow_up_queries) and every `microlearning_quizzes` row grouped by `fact_id`. Same for touched `knowledge_entities`.
- `scripts/voice_calibration.html` (≈650 lines) renders inline colored span overlays per fact on the transcript (up to 8-colour palette, distinct per fact), margin fact cards with routing chips / confidence / source_excerpt, per-node cards with a quiz-angle table (header row per fact_id, sub-rows per `microlearning_quizzes` row, `NONE` placeholder where a fact_id has no quiz rows), per-entity cards, "unrouted facts" panel, and "wonderings" panel.
- Hover tooltips on every inline span + fact card summarize routing. Section heading shows first 90 chars of transcript (not `routed_node_title`, which is the router's pick at capture time and misleads when routing misfires — flagged with ⚠ when touched_nodes is empty).
- Provenance badge: 🎙 audio / 📝 text / 🧪 test / ? mode (pre-migration) per row, based on new `input_mode` column.
- Commits: `ab8d2ec` (initial), `e8cb97f` (?limit), `472e914` (tooltips + labels), `ef05e5b` (header fix).

### Verification subagent
Spawned independent reviewer after initial build. Verdict: "YES with caveats" — inline markup, per-fact linkage, angle tables, memory hooks, gap surfacing all present. Real issues raised: empty fact-span tooltips (fixed), confusing "angle types" metric on entity cards (relabelled "multicue angles" + added table explainer), "no memory_hook" label (sharpened to "no memory_hook in cached_question" since this is pipeline truth, not UI bug — book-sourced KIs don't generate hooks).

### Synthetic capture incident
**Discovery**: user noticed the Karl XII transcript section was titled "1693 Earthquake" (router misfire), said the text didn't sound like his speech, and confirmed he had never talked about Aztecs at all. Probe of the DB:
- All `voice_capture` rows had `audio_bytes=0` (misleading — `process_voice_capture()` hardcodes to 0 regardless of actual audio).
- Disfluency count is the real authenticity signal: one `voice_capture` row (vt_1775365719 Sicily, Apr 5) had 35 real `uh/um/like` markers; the other 8 + 2 `voice_capture_entity` rows had 0–2 each.
- Session 75–76 changelog explicitly names "Rollo retest", "Aztec Empire test", and "Iran" as topics agents tested. The original Rollo transcript referenced in Session 70 (`vt_1776097010_8381`) no longer exists.

**Mechanism**: `/explore/capture` JSON endpoint accepts text verbatim (`research-server.py:4645-4652`). No LLM smoothing anywhere in the pipeline (`transcribe_on_server` returns raw Soniox tokens, `_log_voice_transcript` inserts verbatim, no `UPDATE voice_transcripts SET transcript=` anywhere). Prior agents POSTed Claude-composed first-person prose mimicking user style but drawing on Claude's training data (hence facts the user hadn't heard). `cleanup_voice_dupes.py` keyed on `(node_id, audio_bytes)` — since every voice_capture has `audio_bytes=0` and often shares `node_id='general'`, test rows could silently collapse real originals into one row.

### Cleanup
`/tmp/cleanup_synthetic.py --execute` against alif — dry-run first. Removed 9 test transcripts (6 `voice_capture` + 2 `voice_capture_entity` + 1 uncertain Apr 5 linguistic). Aztec-specific cascade: 1 knowledge_item (`ap_world_history_modern:ap_world_h_americas_1200`), 2 microlearning_cards (`ml_1776272606_*`), 8 microlearning_quizzes. Per user decision, Karl XII / Rollo / Narva / Poltava / Viking Paris knowledge_entities + all KI review history on Frederick II / Sicily nodes retained — these represent real knowledge the user has acquired through reading.

**Surviving voice-family rows**: 30 elicitations (real audio), 1 insight, 1 voice_capture (vt_1775365719 Sicily), 1 explore_capture.

### Three-layer hardening (commit `daad91b`)
1. **Provenance stamp**: new `voice_transcripts.input_mode` column (`'audio' | 'text_json' | 'test' | NULL` for pre-migration rows). Threaded through `_log_voice_transcript` → `process_voice_capture` / `_process_voice_capture_entity_path` → `_handle_explore_capture` (assigns based on whether `audio_path` was set). ALTER TABLE run on live DB.
2. **Fix cleanup_voice_dupes dedup key**: now groups on `(substr(transcript, 1, 200), created_at / 600000)` — identical 200-char head within a 10-minute bucket. Test rows no longer collapse real data.
3. **CLAUDE.md § Production Data Discipline**: explicit rule — agents must not POST synthetic text to `/explore/capture`, `/review/voice-elicit`, `/review/voice-memo`, or any user-data ingest endpoint on the live server. Test via `pipeline-tests/run.py`, in-memory SQLite, or dedicated staging. If a test MUST write to prod, pass `input_mode='test'` and document.

### Pipeline gaps observed (from calibration-page work, not fixed this session)
1. Provenance asymmetry: `knowledge_items.sources` records voice_capture entries *without* `capture_id`; `knowledge_entities.sources` preserves it. Makes "which capture contributed to this KI?" unreconstructible from the KI row.
2. Memory_hook missing on book-sourced KIs: `cached_question` from book-ingestion path has no `memory_hook` key; only voice/entity paths populate it. Inconsistent retention-hook coverage across sessions.
3. Entity-path facts don't generate multicue quizzes — `generate_multicue_quizzes()` is curriculum-path only. Karl XII's 6 key_facts → 0 microlearning_quizzes rows.
4. 30–40% of extracted facts are unrouted (no node_ids, no entities) — stored in `voice_transcripts.llm_result.facts[]` with no downstream consumer.
5. Wonderings never surface as cards.
6. Curriculum-path vs entity-path fact_ids use different namespaces (`jerusalem_negotiation` vs `f1` vs `vc_{ts}_{idx}`) — no global uniqueness.
7. `transcript_chunks` stopped being populated for recent captures (0 rows for vt_1776272663).

### Files
- NEW: `scripts/voice_calibration.py`, `scripts/voice_calibration.html`
- MODIFIED: `scripts/research-server.py` (routes + input_mode), `scripts/review_engine.py` (input_mode threading), `scripts/db.py` (schema), `scripts/cleanup_voice_dupes.py` (dedup key), `CLAUDE.md` (rule)

### Commits
`ab8d2ec`, `e8cb97f`, `472e914`, `ef05e5b`, `daad91b`

### Next (for Session 87)
User will record a fresh authentic voice capture. First-session task: verify it arrives with `input_mode='audio'`, view it on `/voice/calibration`, and use it as ground-truth to investigate the pipeline gaps above (especially multicue coverage for entity-path facts + wonderings surfacing).

---

## Session 85: Speculative Card Gate, Recency Decay, Front-Load, Alignment (April 17, 2026)

### Problem
User reported: "I still haven't gotten a single timeline card or role card or causal card, and I also haven't gotten asked about the high priority things that I captured in voice capture... instead I get mostly aspect cards, I did get one card asking five questions at once, none of which I knew or had ever encountered before (about Arabic desert, concept of unity etc) or have said that I want to prioritize. And some quiz cards are centered and some are top-aligned."

Diagnosis:
- User graded only 5–12 cards per session. Round-robin (Session 84) placed structural types at merged positions aspect@5, sequence@10, synchronic@15, cast@19 — user rarely reached past aspect.
- One aspect card shown was "Social Organization and Governance in Pre-Islamic Arabia, 400–622 AD" testing asabiyya, shaykh selection, blood feuds. User had never read about pre-Islamic Arabia. The `≥5 knowledge_items in domain` gate passed because gap-fill KIs from curriculum expansion count as evidence.
- Voice-captured entities (Karl XII of Sweden, Viking Siege of Paris, Rollo) from 2 days ago had lost all recency boost — hard cutoff formula `max(0, 3.0 − age_hours/16)` hits zero at 48h.
- ReviewCard applied `minHeight: windowHeight − 200` + `justifyContent: center` before reveal — every other card type (8 variants) renders top-aligned. Visible inconsistency.

### Fix 1: Per-node evidence gate for structural cards

**Audit**: 74% of aspect cards (386/523) had no real book/voice evidence on their specific node. Entire domains were 100% speculative: Western Music (94 aspect cards, no books), European Architecture (75, no books). Three pre-Islamic Arabia cards each had 1 gap-fill-only KI.

**Root cause**: `_mix_structural_cards()` gated on `COUNT(knowledge_items WHERE curriculum_domain = sc.domain_id) >= 5`. Any KI counted — including auto-created curriculum gap-fills and self-assessment rows — so a domain with one real book and 40 taxonomy-expansion stubs passed the gate for every aspect card.

**Changes**:
- `scripts/curriculum_db.py` `_mix_structural_cards` query: replaced the domain-count gate with an evidence-based gate. Aspect/cast require ≥1 KI on the exact `(node_id, domain_id)` whose `sources` JSON has a `book_id` or `voice_capture`/`transcript_id` entry. Sequence/synchronic/causal require the same evidence at domain grain. Added `AND COALESCE(sc.hidden, 0) = 0`.
- `scripts/generate_aspect_cards.py`, `generate_cast_cards.py`: per-node evidence clause so future batches skip nodes without real evidence.
- `scripts/generate_sequence_cards.py`, `generate_synchronic_cards.py`, `generate_causal_cards.py`: per-domain evidence gate.
- `scripts/migrate_hide_speculative_structural.py` (new): adds `hidden INTEGER DEFAULT 0` column to `structural_cards`, sets `hidden=1` on rows that fail the new gate. Idempotent; `--dry-run` + `--unhide` flags.

**Migration outcome**: aspect 523→137 visible (−386), cast 25→12 (−13), sequence/synchronic/causal unchanged. Per-domain aspect after: Greece 54, Sicily 36, Rome 24, Byzantine 16, Islamic 7, Music 0, Architecture 0.

### Fix 2: Continuous recency decay

**Formula**: `_recency_boost(created_at_ms, now_ms) = 4.0 / (1.0 + age_days / 7.0)`. Values: 0d→4.00, 7d→2.00, 21d→1.00, 90d→0.29, 365d→0.08. Never reaches zero.

**Changes** (`scripts/curriculum_db.py`):
- New `_recency_boost()` helper (line 1270).
- Applied in `knowledge_items` scoring loop (line 1374) — only in `review_count == 0` branch, additive with existing `+ 2.0 + random()`.
- Applied in `knowledge_entities` scoring loop (line 1478) — replaces the old hard-cutoff formula. Only in `review_count == 0`.
- Added `recency_boost` field to `_provenance` dict in both loops so the About-this-card modal can surface it.

**Schema note**: Both `knowledge_items.created_at` and `knowledge_entities.created_at` are milliseconds (verified via `PRAGMA table_info`). No normalization needed.

**Live verification** (before→after top 10):
- Dionysius I (overdue, score 13.22): unchanged
- Emperor Charles the Fat entity from 2 days ago: pos 6 (was absent from top 10), recency=3.22
- Battle of Poltava (Karl XII voice capture): pos 6, recency=3.21
- Greek Warfare (book_chapter, recent): pos 10, recency=1.03
- Reviewed items (review_count > 0) score unchanged — FSRS path untouched.

### Fix 3: Front-loaded structural rhythm

**Before**: `if pos % 3 == 0:` insert structural — hitting merged positions 4, 7, 10, 13, 16. User rarely reached past the first structural.

**After** (`_mix_structural_cards` at ~line 1213):
```python
FRONTLOAD_UNTIL = 10
FRONTLOAD_INTERVAL = 2
NORMAL_INTERVAL = 3
interval = FRONTLOAD_INTERVAL if pos <= FRONTLOAD_UNTIL else NORMAL_INTERVAL
if pos % interval == 0:
    merged.append(structural_items[struct_idx])
```

**Result** (live stream, 2026-04-17): aspect@3, sequence@8, synchronic@11, cast@14, causal@18. All 5 types in first 18 positions regardless of session length.

**Interactions**: `entity_intro` cards interleave at render time so visible spacing is ~3 slots (vs intended 2). Tail-append loop unchanged for when structural bucket drains. Round-robin type order (Session 84) preserved.

### Fix 4: Uniform top-alignment for all cards

**Before** (`app/app/(tabs)/index.tsx` line 574):
```tsx
<View style={[cs.card, !revealed && { minHeight: windowHeight - 200, justifyContent: 'center' }]}>
```

Only `ReviewCard` centered its unanswered state. All 8 other card types (aspect/sequence/synchronic/cast/causal/microlearning/microlearning_quiz/entity_intro) use plain `<View style={cs.card}>`.

**After**: dropped the conditional wrapper, removed the unused `useWindowDimensions` import. One view style replaced (`cs.card` alone).

### Deploy sequence
1. Three agents in parallel (isolated worktrees): evidence gate + recency decay + front-load rhythm.
2. Merged all three branches to main. Non-overlapping regions of `curriculum_db.py` (query, scoring loops, rhythm loop) → clean auto-merge.
3. `deploy.sh petrarca`. Verified MD5 match between local and `/opt/petrarca/scripts/curriculum_db.py`.
4. Live curl of `/curriculum/review/generate` showed all 4 fixes working together.
5. Follow-up commit: alignment fix to `index.tsx`, redeployed.

### Commits
- `332c806` Replace hard-cutoff recency boost with continuous decay
- `3154d96` Gate structural cards on per-node book/voice evidence
- `ac47ab4` Front-load structural cards in merged stream rhythm
- `f248a20` Merge branch 'worktree-agent-aabb8c61'
- `7fe7b77` Merge branch 'worktree-agent-a3802e6e'
- `75edc6d` Align all review cards to top consistently

### Open / noted
- Causal card still appears later than position 15 because round-robin has only 1 causal card in rotation. Generate more causal cards to tighten this.
- Bedouin/pre-Islamic Arabia cards are hidden, not deleted — `--unhide` flag available if the user ever engages with that content.
- Migration file `scripts/migrate_hide_speculative_structural.py` was run once on server; re-running is idempotent. If the schema migration ever needs to be re-applied on a fresh DB, run it before deploying new code.

## Session 84: Structural Card Type Round-Robin (April 17, 2026)

### Problem
User reported "I don't see any of the new card types, just singular quiz questions (not the geographical, the timeline, the role based etc)." Investigation revealed the cards were being served — but ordered such that all 3 aspect slots filled before sequence appeared, with synchronic at item 28, cast at 38, causal at 46. Most sessions ended before the rare types appeared.

### Root cause
`_mix_structural_cards()` in `curriculum_db.py` built `card_rows` by appending each type sequentially: aspect → sequence → synchronic → cast → causal. The merger consumed them in order, so aspect cards always came first.

### Fix
14-line round-robin pass applied to `structural_items` after the build loop and before `STRUCTURAL_ONLY` short-circuit (curriculum_db.py:1158). First pass through types pulls one of each (aspect, sequence, synchronic, cast, causal); second pass picks up the next of each that has supply; continues until all bins drain.

### Verified live ordering after deploy
First 5 structural slots: positions 5, 10, 14, 20, 25 — aspect, sequence, synchronic, cast, causal — exactly one of each. Second pass at 29 (aspect), 34 (sequence), 38 (synchronic), 42 (cast), 46 (aspect — causal supply was 1 in this stream).

## Session 83: Review Quality Polish + Experiment Instrumentation (April 16, 2026)

### Trust Line on Aspect Cards
- Added "3/4 known · 'What year?' due Thursday" line below card title
- Computed client-side from existing FSRS position data (`review_count` + `last_score`)
- Green accent when all positions mastered, hidden on first encounter (0 reviews)
- Added `review_count` and `last_score` to AspectPosition TypeScript interface (server already sent these)
- Title marginBottom reduced 12→4px to accommodate the trust line

### E3 Collateral Exposure Measurement
- `scripts/measure_collateral_exposure.py` — analysis script for the collateral exposure hypothesis
- Reports: total positions, actively graded, collateral-only (stability>1.0 but review_count=0), untouched
- Per-card breakdown showing graded vs collateral vs untouched positions
- Current state: 6 graded positions, 0 collateral-only (all positions on graded cards were actively tested)
- Script flags insufficient data (N<20) and estimates sessions needed for meaningful comparison

### Card Suggestion Generation Pipeline
- `scripts/generate_from_suggestions.py` — turns approved `suggested_cards` into real structural cards via Gemini Flash
- Supports both sequence and synchronic card types
- Entity-level overlap detection against existing structural cards
- `POST /admin/suggested-cards/approve` and `POST /admin/suggested-cards/reject` endpoints
- Generated first card from suggestions: "The Rise of the Norman Kingdom of Sicily" (6 milestones, 1031-1250)
  - Roger I arrival → Fall of Bari → Roger II birth → Coronation → Frederick II birth → Frederick II death
- Installed `python3-dotenv` on server (was missing from apt)

### Type-Specific Aspect Mnemonics (Priority 2)
- `scripts/generate_aspect_mnemonics.py` — batch Gemini Flash job for type-specific mnemonics
- 5 mnemonic strategies keyed by hook_type:
  - TEMPORAL → temporal_anchor: "Same year as X, 50 years after Y"
  - RELATIONAL → role_chain: "X's general who later became Y"
  - STRUCTURAL → cause_effect: "Because X happened, Y led to Z"
  - PARALLEL → contrast: "Unlike X who did A, Y did B"
  - IDENTITY → vivid_detail: "The one who..., the only Roman to..."
- Batch run: 520 aspect cards, ~92% success rate (Gemini Flash timeouts on ~8%)
- Quality verified: mnemonics correctly use type-specific strategies, reference known historical events

### Scale Annotations on Sequence Cards (Priority 3)
- Client-side gap computation: "— 46 years —" shown between timeline milestones (for gaps >= 5 years)
- `scripts/generate_scale_annotations.py` — batch Gemini Flash job for rich historical comparisons
  - Uses user's studied domains for personalized anchors
  - Stores in `question_variants.scale_to_next` per position
- 18 sequence cards processed, 76 annotations generated, 0 errors
- Example: "— 46 years — roughly the same span as Augustus' principate"
- `curriculum_db.py` passes `scale_to_next` through stream when present
- `SequenceCard.tsx` prefers LLM annotation over raw gap, falls back gracefully

## Session 82: Transcript Reprocessing + Card Suggestions (April 16, 2026)

### Gemini Key Fix for Standalone Scripts
- Added `python-dotenv` loading at import time in `gemini_llm.py`
- All scripts that import gemini_llm now auto-load `.env` — no more missing `GEMINI_KEY` when running via SSH

### Voice Transcript Entity Reprocessing
- `scripts/reprocess_all_transcripts.py` — idempotent script to backfill Wikidata entity resolution on historical voice transcripts
- 10 voice_capture + voice_capture_entity transcripts: 4 already resolved (from sessions 77-78), 6 needed reprocessing
- Results: 61 new entity_resolutions (1368→1429), 29 new shared_entities, 87/94 voice resolutions have QIDs
- Lesson learned: must stop research server before running batch DB writes (SQLite write lock contention)

### Voice-Driven Card Suggestion Detection
- `scripts/detect_card_suggestions.py` — scans voice transcript entities, resolves to shared_entities (for dates/domains), detects patterns:
  - **Temporal sequences**: same-domain entities with date gaps <200y, ≥50y span, ≥3 entities
  - **Contemporaries**: cross-domain entities with ≥10y lifetime overlap
- `suggested_cards` table (migration in db.py): stores pending suggestions for admin review
- `GET /admin/suggested-cards` endpoint for reviewing suggestions
- Initial results: 2 sequence suggestions detected:
  1. Sicily succession: Roger I → Roger II → Frederick II (1031–1194)
  2. Norman succession: Rollo → Richard I of Normandy → Gunnora → Æthelred the Unready (860–966)

### Review Stream Validation
- All 5 structural card types flowing: aspect(3), sequence(1), synchronic(2), cast(2), causal(1)
- Full stream: 26 review + 10 ML + 6 entity_intro + 4 quiz + 9 structural = 55 items
- Quick quizzes confirmed present (3,863 in DB across all types)

### Commits
- `48eca21` — Fix: load .env in gemini_llm.py for standalone script access
- `ba6e71e` — Add transcript reprocessing script for Wikidata entity backfill
- `6e242bf` — Voice-driven card suggestion detection + admin endpoint

## Session 81: Stats Enhancement + Collateral Exposure + Leech Detection (April 16, 2026)

### Stats Tab Rebuilt (`stats.tsx`)
- New `/stats/native` endpoint in `curriculum_db.py` (`get_native_stats()`) — single JSON response with all stats data
- **Structural progress bars**: per-domain reviewed/total positions (e.g., "Greece 4/315")
- **Knowledge level stacked bars**: anchored/engaged/mentioned/unknown per domain, legend, node counts
- **Activity heatmap**: 8-week calendar grid, rubric-colored cells by intensity
- **Score distribution**: all-time knew/partly/missed stacked bar with percentages
- **Card type pills**: aspect/cast/causal/sequence/synchronic reviewed/total counts
- No external chart libraries — pure React Native View percentage-width bars

### FSRS Optimizer (`scripts/optimize_fsrs.py`)
- Extracts review history from interaction_log → py-fsrs ReviewLog objects
- Deduplicates events within 60s window per item
- 195 events across 106 cards, 56 with 2+ reviews
- Result: 0% improvement — FSRS-6 defaults adequate at this data volume
- Re-run at 500+ events. Requires `fsrs[optimizer]` extra (torch + pandas)

### Collateral Exposure Tracking (Priority 4 / Experiment E3)
- `record_structural_answer()` now credits anchor positions (visible but not tested) with 30% of normal FSRS stability gain
- Implementation: after grading blanked positions, finds all non-graded positions for card, applies Good rating × 0.3 stability factor
- Logged as `collateral_exposure` events in interaction_log
- Measurement plan: after 2 weeks, compare retention of collateral-exposed vs unexposed positions

### Leech Detection (Priority 5)
- After each "missed" answer on items with 5+ reviews, checks interaction_log for 7 consecutive misses
- Auto-suspends item for 30 days, clears `cached_question` for regeneration on return
- Logged as `leech_suspended` events
- Currently no active leeches (all multi-miss items eventually learned)

### Commits
- `b8ef573` — Enhanced native Stats tab — structural progress, knowledge levels, heatmap
- `a0f3662` — Collateral exposure tracking + leech detection + FSRS optimizer script
- `6d6af79` — Experiment log: FSRS optimizer baseline + collateral exposure E3 setup

## Session 80: Quick Quizzes, Cast Cards, Causal Chains, Stream Rhythm (April 16, 2026)

### Quick Quizzes (Phase 3 — `generate_quick_quizzes.py`)
- 4 quiz types from key_facts: `date_reverse` (414), `order` (15), `role` (323), `causal`/`location` (1,716) — 2,468 new quizzes total, 229 deduped at 0.82 cosine
- `date_reverse` + `order` generated deterministically (principle #7); `role` + `causal` via Gemini Flash in batches of 15
- `quiz_type` column added to `microlearning_quizzes`; total active quizzes: 3,858 (was 1,392)
- Stream interleaving rewritten: structural→quiz→review→review→quiz rhythm ("palate cleanser" pattern). Due quizzes separated from ML low_pool, handled by `_mix_structural_cards()`. Guard against 3+ consecutive quizzes.
- Response time tracking: `MicrolearningQuizCard` tracks `response_time_ms` from display to grade, passed through `recordReviewResult()` to server `log_interaction()`. Subtle timer indicator fades in after 3s.

### Cast Cards (Phase 6a — `generate_cast_cards.py`, `CastCard.tsx`)
- "Cast of characters" cards from nodes with ≥3 person-type entities via `entity_curriculum_links`
- Tests: can you name each person's SPECIFIC role in THIS context? Event-specific roles, not general biography.
- Purple badge (#6B4C8A). Anchor persons shown dimmed with role, 2-3 blanks by FSRS urgency.
- `question_variants` stores role/significance/entity_id per position
- Activation gate: ≥5 KI in domain + ≥1 reviewed KI for the node
- 25 cards, 81 positions across 8 domains (3 failed due to Gemini parse errors)

### Causal Chains (Phase 6b — `generate_causal_cards.py`, `CausalChainCard.tsx`)
- "Why did X lead to Y?" reasoning chains, 3-5 per historical domain (5 domains: Greece, Rome, Sicily, Byzantine, Islamic)
- Brown badge (#8B5E3C). Vertical chain with ↓ arrows. Connection text between links shown only when BOTH adjacent links visible.
- 2 blanks per card (most-due links, first link always anchor)
- `question_variants` stores event/year_display/connection_to_next per link
- 14 chains, 63 links (e.g., "From Land Power to Naval Hegemony", "The Destruction of the Republic", "The Arab-Norman Synthesis")

### Quick Wins
- FSRS `maximum_interval`: 365 → 3650 (well-known items can reach multi-year intervals)
- Voice recency boost: +3.0 at capture, decays to 0 over 48h (entity item scoring in `curriculum_db.py`)
- `ResurfacingItem` type extended with `'cast' | 'causal'`

### Commits
- `e4f6346` — Session 80: Quick quizzes, cast cards, causal chains, stream rhythm
- `63bdbbb` — Fix causal card domain filtering — match by keyword not exact ID

## Session 79: Synchronic Cards + Entity Consolidation (April 16, 2026)

### Priority 0: Entity Consolidation

**Entity-type backfill:** All 11 `knowledge_entities` rows updated from legacy `entity_type='entity'` to correct types (6 persons, 5 events). QID-bearing entities verified against Wikidata P31; others inferred from name.

**Phase 2 question regeneration:** Cleared and regenerated `cached_question` on all 11 entity items using Phase 2 enrichment pipeline (Wikidata props + temporal neighbors + voice co-occurrence). Quality improvement validated:
- Poltava: generic "1709 famine" → graph-grounded "nine years after Narva in 1700"
- Sigfred: generic "Treaty of Wedmore" → "Rollo (whom you've studied, 860-932)"
- Karl XII: generic "Glorious Revolution" → "1693 earthquake devastated Sicily" (cross-domain temporal neighbor)

All 6 QID entities now have cached `wikidata_props_json` (Karl XII: 10 property types).

### Priority 1: Synchronic Cards (Phase 5 of structural-review-redesign)

**Generation** (`generate_synchronic_cards.py`): Finds well-reviewed temporal anchors from knowledge_items, queries `shared_entities` for contemporaries from other studied domains active at anchor year, generates via Gemini Flash with connection texts explaining why each contemporary matters. Key features: 10-year proximity dedup, ≥3 cross-domain threshold, Gemini Flash prompt drops purely coincidental contemporaries.

**10 synchronic cards generated** spanning 734 BC – 1194 AD across 7 domains, 48 total positions. Examples:
- "The World in 321 AD" (Constantine anchor) — Neoplatonism, Koine Greek, Academy, Sicily/Rome
- "The World in 1194 AD" (Frederick II anchor) — Averroes, Al-Andalus, Scholasticism, Constantinople
- "The World in 264 BC" (Punic Wars anchor) — Carthage, Syracuse, Hiero II, Stoicism

**SynchronicCard.tsx**: Geographic layout (domain rows vs timeline), 3 blanks per card (never blanks the anchor), binary grading, connection text revealed after all blanks resolved. Badge color: `colors.info` (blue, distinct from aspect gray and sequence gray).

**Stream integration**: `_mix_structural_cards()` extended to query `card_type='synchronic'` (up to 2 per batch). Same activation gate as aspect cards (≥5 KI in anchor domain). Stream verified: 2 synchronic cards appear in typical 40-item batch alongside 3 aspect, 1 sequence, 20 review, etc.

### Priority 2: Stream Quality Audit

Comprehensive audit of review stream composition. Findings:
- Stream is healthy: 50% review items, 26% structural (3 aspect + 1 sequence + 2 synchronic), 13% ML, 12% entity intros.
- 564 ML cards all due/never-reviewed — infinite backlog but rate-limited by interleaving ratios (1:3 wondering, 1:7 follow_up). Not flooding the stream.
- Structural cards flowing correctly. Sequence cards blocked in 4/5 domains (need ≥3 reviewed aspect positions; only Greece passes).
- Design doc: `research/unified-scoring-design.md` — entity weight tuning analysis. Recommendation: add voice-capture recency boost (+3.0 decaying over 48h), keep other weights static until entity count grows.

### Priority 3b: Entity Date Backfill

28 persons/events backfilled from Wikidata P569/P570/P585. Date coverage: 456/590 (77%) → **484/590 (82%)**. Notable additions to synchronic card pool: Herodotus (-484 to -425), Mehmed II (1432-1481), Scipio Africanus (-235 to -183), Hippocrates (-460 to -370), Battle of Himera (-480). 87 places remain correctly dateless.

### Priority 3c: E5 Baseline

Pre-synchronic-card cross-domain baseline: 85% of voice transcripts contain cross-domain entity mentions (58.5% cross-domain ratio). However, many are shared geographic entities (Rome, Italy, Sicily) that naturally span curricula. True E5 test: novel cross-domain pairs after synchronic card exposure. Baseline saved in `research/unified-scoring-design.md`.

### Priority 3a: Ambiguous Resolution Triage

653 ambiguous entity_resolution rows → only 50 unique entities without QIDs (rest are duplicate attempts from different transcripts). Categorized:
- **Easy wins**: 9 unique entities where top candidate was correct but margin too tight
- **Wrong top match**: Patton→Patton Oswalt, Marathon→the sport, Salamis→the island. Fixed with manual QIDs.
- **Concepts/periods**: 32 entities like "Ancient Skepticism", "Phenomenology" that don't map cleanly to Wikidata entities. Left as ambiguous (appropriate).

**14 entities manually resolved** with verified QIDs: Abu Bakr (Q7271), Umar (Q7412), Al-Mansur (Q188832), Council of Nicaea (Q232572), Germany (Q183), Battle of Salamis (Q133201), Battle of Marathon (Q131222), George S. Patton (Q186492), Reconquista (Q16956), Marcellus (Q170363), Sunni Islam (Q483654), Early Christian Church (Q25393), Ummah (Q177053), Antigonid Macedon (Q170377).

QID coverage: 89.5% → **91.9%** (542/590). Date coverage: 82.0% → **82.4%** (486/590).

### Commits
- `fb3b651` — Synchronic cards + entity consolidation (all changes)
- `8793a6e` — Stream quality audit + unified scoring design + E5 baseline

## Session 78: Phase 2 Entity-Graph Enrichment + Resolver Bug Fixes (April 15, 2026)

### Wikidata Resolver Hardening (limbic, commit `e7d8498`)

**Bug 3 — Karl XII spelling variants (FIXED):** `wbsearchentities` for "Karl XII of Sweden" returned only paintings because Q52934's English label is "Carl XII of Sweden". Added `REGNAL_NAME_VARIANTS` table (20 classes: Karl↔Carl↔Charles, Friedrich↔Frederick, Wilhelm↔William, Håkon↔Haakon, etc.) with regnal-shape gate (only fires on mentions with Roman numerals or "of <place>"). Resolver retries when 0 candidates returned OR `type_hint='person'` but no candidate is Q5 (human). 9 new tests.

**Bug 4 — Count Odo weak-match downgrade (FIXED):** Single-candidate museum (Q67389525, type=0.30, date=0.00) was silently accepted because `total >= 0.55`. Added `_is_weak_structural_match()`: when `type_score < 0.5 AND date_score < 0.5` AND `type_hint` was supplied, `_decide()` returns `ambiguous` instead of `resolved`. 3 new tests. Documented both failure modes in `research/wikidata-resolution-quality.md` (new doc).

### Phase 2: Entity-Graph Enrichment (commit `08c4551`)

`generate_entity_question()` now builds a three-signal context block for the `_ENRICH_PROMPT`:

1. **Wikidata structured properties** — per-type property sets (P22 father, P39 position, P1366 successor for persons; P710 participants, P276 location for battles; etc.). Cached in new column `knowledge_entities.wikidata_props_json` (90-day TTL). Legacy `entity_type='entity'` rows use union-of-all-props fallback.
2. **Scoped temporal neighbors** — entities within ±50y that the user has ALSO captured, joined via `knowledge_entities` OR `entity_curriculum_links → knowledge_items`. Never global `shared_entities` — preserves "user's own graph" constraint.
3. **Voice co-occurrence** — top-N entities most frequently mentioned alongside this one in `voice_transcripts.llm_result.entities_mentioned`. Catches discussed-but-not-yet-anchored entities.

Prompt constraint: enrichment never asserts facts the user didn't capture. Wikidata properties become retrieval prompts ("you captured X reigned Y-Z; who succeeded?"), not assertions. 8 new tests.

### Stretch UX (commit `39c83b2`)

- **Entity badge**: `entity_capture` origin now shows 💬 (unresolved) or 🔷 (Wikidata-linked) in the stream header, distinct from existing 📖/🎙/👤 badges.
- **About-this-card source excerpts**: "VOICE CAPTURE" section shows `knowledge_entities.sources[].source_text` + capture_id. "WIKIDATA" section shows QID when resolved. `generate_review_stream()` now passes entity-path sources through to provenance instead of empty `[]`.
- **Entity intro cards**: `_build_entity_capture_intros()` inserts an entity_intro card before the first review of never-graded entity_capture items when `shared_entities` has a description ≥20 chars.

### Gemini Date Coercion Fix (commit `0a3a304`)

Pre-existing latent bug surfaced during backfill: Gemini occasionally returns `date_start`/`date_end` as strings ("1682") in JSON-mode responses. `_resolve_voice_entities_background` passed these through to `DateRange(start=str)`, crashing inside the resolver with `'<' not supported between instances of 'int' and 'str'`. Added `_coerce_year()` helper that defensively parses int/float/str/None.

### Backfill + End-to-End Validation

Deployed via `bash ~/src/petrarca/scripts/deploy.sh` (rsyncs limbic AND git-pulls petrarca). Re-ran resolution on Karl XII and Viking Paris captures:
- **Karl XII → Q52934** (Carl XII of Sweden) — regnal spelling retry successful. 12/12 mentions resolved.
- **Count Odo → ambiguous** with reason "weak structural match (type=0.30, date=0.00)" — downgrade fired. Hallucination guard then rejected LLM's Q312674 proposal. Correctly stays unresolved.

Regenerated Battle of Poltava `cached_question` with Phase 2 enrichment. Memory hook changed from generic ("1709 famine, Great Frost") to graph-grounded ("nine years after Karl XII's victory at Narva in 1700 — Poltava reversed their fortunes completely"). References Battle of Narva (scoped temporal neighbor) and Karl XII (voice co-occurrence). North-star validated.

### Commits
- `e7d8498` (limbic) — Regnal spelling variants + weak-match downgrade (12 new tests)
- `08c4551` — Phase 2 entity-graph enrichment (8 new tests)
- `39c83b2` — Stretch UX: badge + source excerpts + entity intro cards
- `0a3a304` — Gemini date coercion fix

## Session 77: Entity-First Phase 1 Observation + Cleanup Fixes (April 15, 2026)

### Observation Phase (Priority 0)
Per the Session 77 prompt, the session began with an observation pass against production state — no code until the data was read. Inspection scripts were scp'd to alif and run against `/opt/petrarca/data/petrarca.db`. 11 `knowledge_entities` rows + 2 entity-path voice transcripts (Karl XII `vt_1776272899_7705`, Viking Paris `vt_1776274698_7861`) were small enough to enumerate fact-by-fact rather than sample.

**What worked well in Phase 1:**
- Question quality is genuinely strong. Memory hooks anchored Karl XII to Peter the Great's 1697 Grand Embassy, the 1708 Russian campaign to Napoleon's 1812 Moscow disaster (104 years apart), Charles the Fat's 886 humiliation to the 843 Treaty of Verdun. Match north-star principle 6 (temporal hooks).
- Entity grouping from `VOICE_CAPTURE_ENTITY_PROMPT` was sensible: 5 entities from Karl XII transcript, 6 from Viking Paris. No over-splitting (each date its own entity) or under-splitting (one giant container).
- All 11 entity items appeared correctly in `generate_review_stream()` with `knowledge_weight=6.0` and proper FSRS scheduling. Karl XII graded `knew` → rescheduled +26.9d with stability 8.3d via the existing curriculum-grading codepath.

**Bugs found:**
1. **Double Wikidata resolution fire.** Every mention from entity-path captures had exactly 2 rows in `entity_resolutions` — 17 mentions → 34 rows on Karl XII capture. Root cause: when `process_voice_capture()` falls through to `_process_voice_capture_entity_path()` at line 4991, the entity path fires its own resolution thread, then control returns and the curriculum-path thread fires AGAIN at line 5026 with the same `entities_mentioned` list.
2. **`voice_transcripts.node_title` carried curriculum garbage.** Karl XII transcript was logged as `node_title='1693 Earthquake'`; Viking Paris as `'Charles Ives'`. Caused by the entity path inheriting curriculum-path's loose-name-match fallback.
3. **Karl XII Wikidata resolution failed**: search returned only paintings (Q119811370 by Schröder, Q106357900 by Ankarcrona). The actual person is Q52934 labeled "Carl XII of Sweden" — verified by direct `wbsearchentities` calls. The English spelling "Karl XII" isn't an alias on Q52934.
4. **"Count Odo" mapped to Q67389525 "Count Ödön Széchenyi Fire Brigade Museum"** in Istanbul. Resolver accepted single candidate at `total=0.596 type=0.30 date=0.00` because it crossed the 0.55 threshold — no LLM disambiguation ran (only fires on `ambiguous` status).

**Design gaps:**
- A. Entity cards had `follow_up_queries: []` because `generate_entity_question` only called `_key_fact_to_question` (which generates rich_answer + memory_hook) but not `_generate_follow_up_queries`.
- B. `entity_type` defaulted to literal `"entity"` because the prompt didn't ask for type classification and `shared_entities.entity_type` was rarely populated yet.
- C. Parentheticals and honorifics on entity names broke Wikidata search: "Viking siege of Paris (885-886)", "Emperor Charles the Fat", "Russian Campaign (1708-1709)" all returned `no_match` or wrong matches.

**Findings written to `research/session-77-observations.md`** before any code change.

### Fixes Shipped (commit `5bb9e88`)
- **Bug 1 fix**: added `entity_path_triggered` flag in `process_voice_capture()`; the curriculum-path resolution thread is skipped when entity path took over. Eliminates 2× Gemini extraction + Wikidata search per fallback capture.
- **Bug 2 fix**: `_log_voice_transcript` inside `_process_voice_capture_entity_path` now prefers `next(iter(entity_facts.keys()))` (the LLM's primary entity) over the curriculum-path's `entity_name` arg.
- **Gap A fix**: `generate_entity_question` now calls `_generate_follow_up_queries` after `_key_fact_to_question`, passing `entity_name` as `node_title` and the picked fact's question/answer as `fact_context`.
- **Gap B fix**: added `entity_types` field to `VOICE_CAPTURE_ENTITY_PROMPT` output (one of `person|place|event|battle|dynasty|work|organization|concept`); threaded through entity creation so `knowledge_entities.entity_type` carries the LLM classification when no `shared_entities` row exists.
- **Gap C fix**: added explicit CANONICAL NAMING block to the prompt with BAD/GOOD examples — strip parenthetical date qualifiers, strip honorifics unless part of canonical name (keeps "Pope Gregory VII", "Count Odo of Paris"), prefer common English spellings ("Karl" over "Carl").
- **Backfill**: ran a one-shot script against the 11 existing `knowledge_entities` rows to regenerate `cached_question` so they pick up follow_up_queries. All 11 got 6 follow-ups each. Quality sample for Karl XII: *Voltaire's 1731 History of Charles XII, Baltic German Livonian nobility, Johann Reinhold Patkul, Swedish copper industry*. These follow north-star principle 11 — sideways, not deeper.

### Verified Live
- `petrarca-research` restarted cleanly. `POST /curriculum/review/generate` returns entity items with 6 follow-ups now exposed as top-level field on each card.

### Deferred to Session 78 / Priority 2 (Resolver-Level Work)
- **Bug 3 — Karl XII spelling**: Wikidata search returns only paintings for "Karl XII of Sweden" because Q52934's English label is "Carl XII of Sweden". Requires limbic-level fix: alternate-spelling retry for regnal names (Karl/Carl/Charles, Frederick/Friedrich/Friedrich), or upstream Wikidata alias contribution.
- **Bug 4 — Count Odo → Fire Brigade Museum**: resolver accepted a single candidate with `type_score < 0.5 AND date_score < 0.5`. Fix: require LLM disambiguation when both type and date scores are weak, even on single-candidate matches.

### Commits
`5bb9e88` (all four fixes + observations doc).

## Session 76: Entity-First Architecture Phase 1 + Production Fixes (April 14–15, 2026)

### Production Fixes (deployed first)
- **`STRUCTURAL_ONLY=True` was live** from Session 75 testing — blocked ALL SR and ML cards from the review stream. Only 6 structural cards were being served to the client. Reverted to `False` in `curriculum_db.py:936`.
- **Gemini API key not persisted across server restarts** — the systemd unit lacked `EnvironmentFile=/opt/petrarca/.env`. Added it; 178 pending ML cards can now complete.

### The Architectural Question
User reported: voice captures about topics outside existing curricula (Iran podcast, Rollo/Normans book) produced nothing useful. Traced to the `knowledge_items` table requiring `curriculum_domain NOT NULL` + `curriculum_node_id NOT NULL` — every knowledge tracking flow depends on mapping to a curriculum node first. For genuinely novel topics there is no such node.

Research: re-read `overlapping-curricula-vision.md`, `curriculum-system-audit.md`, `entity-profiles-design.md`. The Session 54 audit already asked "what if no curricula?" and identified curriculum's genuine value (gap analysis, bounded review, progress visualization) vs. its accidental coupling (deduplication, knowledge tracking, voice capture routing).

Wikidata QIDs are strictly better for deduplication than curriculum nodes: `Q155124` is Roger II everywhere, whereas `sicily:roger_ii` and `medieval_europe:roger_ii` are two separate rows today.

Decision: invert the dependency. Entities become the primary knowledge unit; curricula remain as optional overlays for gap analysis and structured review.

### Design Doc
**`research/entity-first-architecture.md`** (new) — 5-phase migration plan with full dependency audit.

### Phase 1 Shipped
- **New `knowledge_entities` table** in `db.py` (schema + migration). Same FSRS/cached_question/key_facts shape as `knowledge_items`, keyed by entity slug (`ent:{slug}`).
- **`VOICE_CAPTURE_ENTITY_PROMPT`** in `review_engine.py` — outputs `entity_facts` grouped by entity name with `{id, question, answer, type, source_excerpt}` format (compatible with `_pick_key_fact()` / `_key_fact_to_question()`).
- **`_process_voice_capture_entity_path()`** in `review_engine.py` — fires when (a) no candidate curriculum nodes, or (b) curriculum LLM returns `node_assessments=[]`. Creates/updates `knowledge_entities` rows, pre-generates cached_questions, triggers ML cards from wonderings, logs transcript, triggers background Wikidata resolution.
- **`generate_entity_question()`** reuses `_pick_key_fact()` + `_key_fact_to_question()` — entity_name substitutes for node_title, `shared_entities.description` (if linked) for node_description. No curriculum context needed.
- **`generate_question()` fallthrough** — if item_id is not in `knowledge_items` or `review_items`, checks `knowledge_entities` and delegates.
- **`record_answer()` lookup** — added `knowledge_entities` after `microlearning_quizzes`. Existing `curriculum_domain` guards naturally skip knowledge_state updates and dependent rescheduling (entity items have neither).
- **Review stream integration** in `curriculum_db.py` `generate_review_stream()` — queries `knowledge_entities` with `knowledge_weight=6.0`, sets pseudo-fields (`curriculum_domain='entity'`, `node_title=entity_name`, `domain_title=entity_type.title()`) so entity items render through the existing `ReviewCard` as `type:'review'` with `provenance.origin='entity_capture'`. Entity items' own `key_facts` surface as `related_facts`.
- **Wikidata backfill** — `_resolve_voice_entities_background()` now calls a `_link_ke()` helper after creating/updating `shared_entities` to update matching `knowledge_entities` rows with `entity_id` and `wikidata_qid`.

### Validation (real captures)
- **Karl XII of Sweden** (novel, no curriculum): 5 entity items — Karl XII, Battle of Narva, Great Northern War, Russian Campaign, Battle of Poltava. Narva auto-linked to Q155726, Poltava to Q152486. Memory hook: *"Karl XII became king the same year Peter the Great returned from his Great Embassy to Western Europe (1697-98)."*
- **Viking siege of Paris 885-886**: 6 entity items — siege, Count Odo, Charles the Fat, Abbo of Saint-Germain, Sigfred, Rollo. Memory hook: *"This 885-886 siege came just 73 years after Charlemagne's death in 814."*
- **Aztec Empire test**: correctly routed to AP World History curriculum (not entity path) — expected behavior, curriculum wins when it exists.
- **Grading**: `POST /curriculum/review/result` with `ent:karl_xii_of_sweden` / `knew` → `stability_days=8.3` (FSRS Easy rating), due 2026-05-12. Confirmed FSRS scheduling works on entity items.

### Bug Fixes During Testing
- **Entity path wasn't triggering** because Gemini Flash domain routing always found SOME candidate nodes (even weak ones). Widened entry point to also fire when curriculum LLM analysis returns `node_assessments=[]`. Replaces the old weak ML-card novel-topic fallback.
- **`database is locked` during pregen** — background thread held an open connection during the slow Claude enrichment call. Refactored per CLAUDE.md write-lock discipline: read → close → slow Claude call → open → write. Each entity gets its own conn per phase.

### Explicitly Not Touched
- Existing `knowledge_items` curriculum flows continue unchanged
- `knowledge_states` table unchanged
- Structural cards remain curriculum-only
- Voice elicitation remains curriculum-based
- No client changes — entity items render as `type:'review'` through existing `ReviewCard`

### Commits
`0f83650` (core), `c975c7d` (entity path fallback widened), `a8b27b6` (write-lock discipline).

## Session 75: Activation Gating + Voice Pipeline + Auth Fix (April 14, 2026)

### Structural Card Expansion
- Generated ~523 new aspect cards across 5 domains (Greece 65, Byzantine 81, Islamic 83, Music 94, Architecture 75) via Gemini Flash batch generation
- Total structural cards: ~648 aspect + 8 sequence = ~656 cards, ~2600+ positions

### Activation Gating (deployed)
- Aspect cards gated by `ASPECT_GATE_THRESHOLD = 5` knowledge items in domain — prevents quizzing on unstudied material
- Sequence cards additionally gated by `SEQUENCE_GATE_THRESHOLD = 3` reviewed aspect positions
- Domain-diverse selection via `ROW_NUMBER() OVER (PARTITION BY domain_id)` — each batch shows cards from different domains
- Active: Sicily, Rome, Greece, Byzantine, Islamic. Blocked: Music, Architecture (0 KI)

### Voice Capture Fix for Novel Topics
- Voice captures about topics outside all curricula (Rollo/Normans, Iran) now extract facts + create ML cards instead of silently dropping
- Updated `VOICE_CAPTURE_ANALYSIS_PROMPT` to always extract facts/wonderings regardless of node matching
- Fallback ML creation from extracted facts when 0 node assessments
- Rollo retest: 9 facts → 9 ML cards (4 wonderings + 5 novel facts). Previously: 0

### Voice Pipeline Audit
- Audited all 38 voice transcripts: 31 with KIs (working), 4 chapter recalls (correct design), 2 novel topics (fixed above), 1 explore capture
- Pipeline verified: confidence_tagged corrections ✅, no ML from missed facts ✅, dedup ✅, domain routing ✅

### Claude Auth Sync Fix
- `sync_claude_auth.sh` updated to read from macOS keychain (`Claude Code-credentials`) instead of stale snapshot file
- Launchd interval reduced from 4h → 2h

## Session 74: Deploy Aspect Cards + FSRS Scheduling + Sequence Cards (April 14, 2026)

### What
Completed Phases 2 and 4 of the structural review redesign: aspect cards fully deployed with FSRS scheduling, and sequence cards built end-to-end.

### Changes
- **FSRS scheduling for structural positions**: `record_structural_answer()` in `review_engine.py` — per-position FSRS with independent `stability_days`, `due_at`, `fsrs_card_json`. Knowledge state updated from `knew/total` ratio (≥80% → anchored, ≥50% → engaged, <50% → mentioned).
- **`POST /structural/grade` endpoint**: Accepts `{card_id, results: [{position_id, score}]}`, returns per-position scheduling. Shared by both aspect and sequence cards.
- **Client wiring**: `gradeStructuralCard()` in `book-api.ts`, called fire-and-forget from `onComplete` in both AspectCard and SequenceCard handlers.
- **4 failed aspect nodes retried**: Frederick II Stupor Mundi, Lucky Luciano, Sicilian Culture, Latin Literature — all generated successfully (14 new positions).
- **Sequence cards** (`generate_sequence_cards.py`): Gathers date-type key_facts + entity date ranges per domain, Gemini identifies natural chronological sequences (5-8 milestones each). 8 sequences generated: "Struggle of the Orders", "Punic Wars", "Collapse of the Republic", "Five Good Emperors", "Late Roman Empire" (Rome) + "Rise and Siege of Syracuse", "Arab-Norman Sicily", "Era of Mafia and State Collusion" (Sicily). 38 milestones total.
- **SequenceCard component** (`app/components/SequenceCard.tsx`): Timeline UI with dot/connector layout, 2 rotating blanks (most-due positions selected by urgency), anchor positions dimmed. Year markers, temporal hook annotations, binary grading, summary + mnemonics for missed.
- **Stream mixing fix**: `_mix_structural_cards()` now queries each type separately (3 aspect + 2 sequence) to prevent aspect cards from monopolizing all slots.
- **Server deploy fix**: Stashed Session 73 direct-deploy artifacts on server before git pull.

### Design decisions
- **Per-position FSRS, not per-card**: Each position in a structural card gets independent scheduling. This mirrors Alif's sentence→word model — one card interaction yields multiple FSRS signals.
- **Binary grading only**: Aspect and sequence cards use knew/missed (no "partly"). Granularity comes from per-position tracking, not per-card nuance.
- **2 blanks per sequence card**: Most-due positions become blanks, rest shown as anchors. Picks by urgency: never-reviewed → most-overdue. Card looks different each appearance.
- **Type-guaranteed mixing**: Separate queries with limits (3+2) rather than one combined query, because 125 due aspect cards were crowding out 8 sequence cards.

### Totals
- 125 aspect cards (529 positions) + 8 sequence cards (38 milestones) = 133 structural cards
- Domains: Sicily (70+3), Rome (55+5)
- All deployed to server and mobile

---

## Session 73: Aspect Cards — Structural Review System Foundation (April 14, 2026)

See commit `2c89f13` for full changes. Schema, generation, component, stream mixing.

---

## Session 72: Review-First 4-Tab Navigation (April 14, 2026)

### What
Implemented Phase 1 of the structural review redesign: the app now opens to Review, with a 4-tab layout (Review / Voice / Stats / More). This is the first user-visible change from the session 71 redesign plan.

### Changes
- **Tab restructure**: Renamed `(tabs)/review.tsx` → `(tabs)/index.tsx` (makes Review the landing screen). Renamed old `(tabs)/index.tsx` → `(tabs)/feed.tsx` (hidden with `href: null`).
- **3 new tab screens**:
  - `voice.tsx` — Hub for Guided Recall, Capture Voice, Knowledge Sweep, Voice Notes
  - `stats.tsx` — Fetches from `/review/stats` + `/curriculum/review/generate` endpoints. Shows due count, domains, source breakdown, link to full dashboard.
  - `more.tsx` — Replaces the PetrarcaDrawer as primary navigation. Library, Explore tools, Projects, System settings.
- **Review screen cleanup**: Removed internal Cards/Voice/Explore sub-tabs. Removed PetrarcaDrawer integration. Date/entity taps now navigate to `/timeline` instead of inline KnowledgeExplorer. Added compact status bar (due count + progress).
- **Floating mic FAB**: Dark circular button on Review tab for one-tap voice capture access.
- **Route fix**: `book-detail.tsx` updated from `/(tabs)/review` → `/(tabs)`.
- **Root layout**: Added missing Stack.Screen entries for voice-elicitation, voice-capture, knowledge-sweep, map.
- **Implementation status**: Updated architecture diagram (4-tab layout) and tab screens table.

### Design decisions
- Voice tab is a hub (cards linking to existing screens) rather than embedding the elicitation/capture UI directly — keeps the tab lightweight and the complex recording screens as full-screen experiences.
- Stats tab fetches real data rather than being a placeholder — immediately useful even before native charts in Phase 7.
- PetrarcaDrawer code preserved but no longer referenced from any active screen. It can be removed in a future cleanup.
- The old Feed tab is hidden (`href: null`) not deleted — all article code preserved per session 71 decision.

### Phase 1 status from design doc
- [x] Restructure navigation: 4 tabs (Review, Voice, Stats, More)
- [x] App opens to Review tab
- [x] Move Library to More tab
- [x] Disable Feed tab (hide, don't delete)
- [x] Add floating mic button on Review tab
- [ ] Disable launchd jobs for Twitter/Kindle/Amazon sync (deferred — low priority, already non-functional)

---

## Session 71: Structural Review Redesign (April 14, 2026)

### What
Major architectural pivot: Petrarca moves from read-later app to quiz-first knowledge retention app. Design document: `research/structural-review-redesign.md`.

### Key decisions
- **Disabled**: Feed tab, article ingestion, Twitter/Readwise/Kindle/Amazon sync, standalone HTML visualizations. Code preserved but inactive. See CLAUDE.md "DISABLED SUBSYSTEMS" section.
- **New card types**: Structural review cards — Aspect (multi-signal per topic), Sequence (temporal ordering), Synchronic (cross-domain contemporaries), Cast (people+roles), Causal Chain, Quick Quiz (fast binary)
- **"Partly" grade eliminated**: Replaced by per-aspect binary knew/missed. Each aspect independently FSRS-scheduled.
- **Voice priority**: Fresh captures (48h) get highest review priority.
- **Navigation**: 4 tabs — Review (landing), Voice, Stats, More
- **Analytics**: In-app native stats screen (replacing standalone HTML pages)
- **FSRS**: maximum_interval raised from 365 to 3650 days

### Analysis findings
- Only 3/265 knowledge_items had actual multicue quizzes (pipeline barely fired)
- 57% of knowledge_items never reviewed; 153/265 overdue
- 38 voice transcripts: 8 have no knowledge_items, 37 have no entity resolutions
- FSRS maximum_interval=365 caps known items at 274 days
- Alif comparison: desired_retention=0.95 (calibrated from 21k reviews), sentence-based multi-signal, leech detection, 11-factor selector

### 8 experiments defined
See design doc § Experiments & Hypotheses: aspect decomposition quality, binary vs ternary grading, collateral exposure effect, structural vs plain quizzes, synchronic cross-domain recall, session rhythm engagement, voice priority retention, mnemonic type effectiveness.

### Implementation: 8 phases
0=Foundation (done), 1=Review-first shell, 2=Aspect cards, 3=Quick quizzes, 4=Sequences, 5=Synchronic, 6=Cast/Causal, 7=Analytics, 8=Voice enhancements

### Pending
- Rollo transcript (vt_1776097010_8381) needs reprocessing through full pipeline
- 37/38 transcripts need entity resolution reprocessing
- PR #2 (Wikidata backfill) needs merging
- Another branch has "more flexible questions" work in progress

## Session 70b: Production Backfill + Voice Capture Integration (April 14, 2026)

### What
Deployed the full Wikidata entity resolution stack to production and wired it into the live voice capture pipeline.

### Production backfill
- Merged [PR #2](https://github.com/houshuang/petrarca/pull/2) (backfill + admin UI + merge tool)
- Ran 4-pass backfill on live alif DB: **509/570 entities resolved (89.3%)**, 1906 external IDs
- Applied 21 safe dedup merges (augustus↔octavian, homer↔homer_person, etc.)
- 61 unresolved — mostly curriculum-internal period labels, not real entities

### Voice capture integration ([PR #3](https://github.com/houshuang/petrarca/pull/3))
Two additions to `process_voice_capture()` in `review_engine.py`:
1. **Domain routing** (foreground): When entity matching finds <5 nodes, Gemini Flash picks top-3 domains → all nodes become candidates. Fixes the novel-entity problem.
2. **Background entity resolution**: Daemon thread resolves `entities_mentioned` to Wikidata QIDs (deterministic + Gemini disambiguation). Auto-creates `shared_entities` rows for novel entities.

### Validation
Ran `reprocess_voice_with_qids.py` on the canonical Rollo transcript (`vt_1776097010_8381`): 11/13 entities resolved correctly — Rollo→Q273773, Richard I→Q333359 (of Normandy), Gunnor→Q270777, Æthelred→Q183499.

### Environment notes
- `GEMINI_KEY` must be exported for SSH-invoked scripts: `export GEMINI_KEY=$(grep GEMINI_KEY /opt/petrarca/.env | cut -d= -f2)`
- limbic synced to server via rsync (not git): `rsync -av ~/src/limbic/limbic/ alif:/opt/limbic/limbic/`
- systemd unit is `petrarca-research.service`

---

## Session 70: Wikidata Entity Resolution Backfill (April 13-14, 2026)

### What
Built PR 3 of the Wikidata entity resolution rollout: Petrarca schema migration + backfill script + minimal review UI. Drove the local copy of the production DB from **0% → 90.5% canonical QID coverage** (517 of 571 entities after auto-merges and an improved rescue prompt) in ~10 minutes at ~$0.05 total cost.

See `research/wikidata-entity-resolution-plan.md` for the full architectural plan. PRs 0-2 are already merged on limbic main (`PayloadCache`/`temporal`, `WikidataClient`, `WikidataResolver`).

### Coverage journey
| Pass | Mechanism | Resolved | Coverage | Cost |
|---|---|---|---|---|
| Start | — | 0 | 0% | — |
| Pass 1 | Deterministic, independent | 219 | 37.1% | $0 |
| Pass 2 | Deterministic, pass-1 anchors | 219 | 37.1%* | $0 |
| LLM disambiguation | Gemini Flash picks top-K | 489 | 82.7% | ~$0.03 |
| No-match rescue | LLM alt-queries + resolver | 510 | 86.3% | ~$0.01 |
| LLM pass 2 + disambig rescue | Rescue caught disambig-page-only cases (Council of Nicaea) | 513 | 86.8% | ~$0.01 |
| Merge safe dupes | merge_entity_dupes.py | 513 | 89.8%† | $0 |

\* pass 2 sharpened confidences but didn't cross the commit threshold (those items moved through LLM pass)
† denominator shrank as 20 duplicates were merged

### Architecture
Four-pass pipeline in `scripts/backfill_wikidata.py`:

1. **Pass 1 (deterministic, independent)**: each entity resolved in isolation via the limbic resolver's 5 heuristics (type, date, description-embedding, coherence, rank). Produces initial commits for unambiguous cases.
2. **Pass 2 (deterministic, with anchors)**: re-runs non-done items with pass-1 QIDs as `already_resolved` coherence anchors. Sharpens confidences for graph-connected entities (Constantinople 0.77 → 0.98 once Justinian I is an anchor).
3. **LLM disambiguation**: Gemini Flash picks from the top-K candidates with full mention context. Guarded by `limbic.hippocampus.wikidata_resolve.validate_chosen_qid` — any QID not in the candidate set is rejected.
4. **No-match rescue**: LLM proposes 2-3 alternate search queries (for cases like "British Palladianism" → "Palladian architecture"), deterministic resolver runs on each. QIDs still come from the API, so no hallucination path. Also catches `ambiguous` cases where every candidate is a Wikimedia disambiguation page (Council of Nicaea pattern).

### Files (all under `scripts/`)
- `db.py` — `shared_entities.wikidata_qid` + `entity_resolutions` audit + `entity_external_ids` fan-out
- `migrate_wikidata_schema.py` — idempotent live-DB migration
- `backfill_wikidata.py` — the full pipeline (1,100+ LOC)
- `merge_entity_dupes.py` — dedup merger with safety classifier (SAFE/REVIEW)
- `research-server.py` — three admin endpoints: `/admin/entity-queue[-data]`, `/admin/entity/<qid>`, `POST /admin/entity/resolve`
- `entity_review.html` — single-page review UI in Annotated-Folio design tokens
- `tests/test_backfill_wikidata.py` (21 tests), `tests/test_admin_entity_review.py` (9 tests), `tests/test_merge_entity_dupes.py` (15 tests)

### Dedup catches (21 pairs on the corpus)
Auto-merged via `merge_entity_dupes.py --safe-only` (20 safe, 2 REVIEW remaining for human):

**SAFE (merged)**: `augustus ↔ octavian` (Q1405), `ibn_sina ↔ avicenna` (Q8011), `byzantion ↔ istanbul` (Q406), `naples ↔ neapolis` (Q2634), `cappella_palatina ↔ palatine_chapel` (Q1034853), `sasanian_empire ↔ sasanian_persia` (Q83891), plus the `_person`/`_place`-suffix family (homer, horace, aeschylus, aristophanes, euripides, augustine_of_hippo, rome, italy, france, england), plus `empedocles ↔ empedocles_of_akragas`, `gelon ↔ gelon_of_syracuse`, `constantine ↔ constantine_i`.

**REVIEW**: `ancient_greece ↔ greece` (resolver conflation of modern vs ancient), `abbasid_caliphate ↔ arab_caliphates` (specific vs parent). These need human judgement — not true duplicates.

### External knowledge harvested
**1,908 external identifiers** fanned out at resolve time from the QID's P-properties: VIAF (P214), GND (P227), GeoNames (P1566), Pleiades (P1584), Getty TGN (P1667), MusicBrainz (P434), Getty ULAN (P245), BnF (P268), LCCN (P244). Downstream specialist-source enrichment becomes a cache lookup.

### Safeguards validated in the wild
- **QID hallucination caught**: validator rejected exactly 1/308 LLM picks where Gemini proposed `Q160538` (Gian Lorenzo Bernini) for "Council of Nicaea" because the candidate set contained only the disambiguation page. The subsequent rescue pass correctly recovered `Q133331` (First Council of Nicaea) via alt-query `"First Council of Nicaea"`.
- **Dedup protection**: writes that would violate the unique-QID constraint are rewritten to `needs_review` with `chosen_qid` preserved for the merge UI. Prevented 21 silent collisions.
- **Supersede chains**: every resolution writes update any prior non-superseded rows for the entity. The admin queue query uses `MAX(created_at)` as belt-and-suspenders.

### Deployed
- **Schema migration deployed to alif** (`/opt/petrarca/data/petrarca.db`). Additive + idempotent, verified with two invocations. 591 entities currently have `wikidata_qid IS NULL` — ready for backfill when user approves.

### Not done (for follow-up)
- Running the actual backfill against the live alif DB (deferred to user's explicit approval — backfill is reversible but involves real writes to production data).
- PR 4: wire resolver into `process_voice_capture` for live voice transcripts. The Rollo/Normandy capture `vt_1776097010_8381` is the smoke-test target — that transcript triggered this entire project and still has 0 knowledge_items.
- Merge admin endpoint (`POST /admin/entity/merge`) — CLI tool exists; could add a UI button later.
- Long-tail residuals: 81 entities still unresolved. Mostly `period`-type curriculum-internal labels ("Aragonese Rule", "Augustan Satire") that don't have corresponding Wikidata entities. ~30 of these could probably be rescued via better search strategies.

### Branch + PR
`sh/wikidata-backfill` with 4 commits, pushed to origin. PR: [petrarca#2](https://github.com/houshuang/petrarca/pull/2).

## Session 69: Insight Node Matching Overhaul (April 13, 2026)

### What
Reviewed two voice insights captured 2026-04-12 (one about a Frederick II podcast, one about medieval Sicily / Arabic translation culture). Both were transcribed and saved correctly but the primary curriculum node and the secondary candidates were poorly chosen. Built a four-signal composite scoring system to robustly pick the primary node from candidate matches.

### Bugs Found
1. **Arbitrary primary selection**: `primary_domain = next(iter(candidate_domains))` returned an arbitrary domain from a Python set; `primary_node = candidate_nodes[0]` took whatever sorted to position 0. The Frederick II podcast was primary-linked to "The Greek Dark Ages and Homeric World" because Western Philosophy had 16 direct nodes from generic entity matches (Aristotle, Latin, Christianity, Nietzsche).
2. **Wrong title display**: `node_title` was set to the first matched entity name in SQL order (often "Frederick II" even for a Sicily medieval podcast where Frederick II is mentioned only in passing).
3. **False-positive entity matches**: Generic period words like "ancient", "early", "christian", "ages", and demonyms ("greek", "german", "norman") created spurious matches via the 1/2-word and 60% overlap rules.

### Composite Scoring Solution
Four orthogonal signals combined in `_composite_score()`:

1. **TF-IDF specificity**: weight = 1 / entity_link_count. Rare entities outrank common ones.
2. **Length scaling**: weight × max(0.5, min(2.0, name_length / 10)). Proper nouns ("Frederick II", 12 chars) outrank short common words ("Latin", 5 chars).
3. **Title-entity match**: +2.0 boost (plus length bonus, scaled by entity specificity) when a node's title contains a matched entity name. "Frederick II Stupor Mundi" containing "Frederick II" is a near-guaranteed topic match.
4. **Opening position bonus**: +4.0 if entity name appears in first 200 chars; +3.0 if a distinctive word from the entity name does. Entities in the opening sentence ("I listened to a podcast about X") are far more likely to be the topic.

### Stop-List Filter
Added `_STOP_WORDS_FOR_MATCHING` to reject matches based purely on generic words. Categories: period descriptors (ancient, modern, medieval), demonyms (greek, roman, german, italian, persian, arab, byzantine, norman), generic nouns (history, period, ages, world, century), religious/cultural categories (church, christian), polity types (empire, kingdom, civilization), discipline names (literature, philosophy, theology). Multi-word entities like "Norman Conquest of Sicily" still match via their other distinctive words (conquest, sicily).

### Verification
All three test insights now pick the correct primary node:
- Frederick II podcast → "Frederick II Stupor Mundi" (Sicily)
- Sicily medieval translation podcast → "The Norman Conquest of Sicily"
- Caliphate/Mawali tweet → "The Rashidun Caliphate (632-661)"

### Files Changed
- `scripts/review_engine.py` — `process_voice_capture()` insight branch + `_entity_matches_transcript()`

### Note
This scoring only applies to insight mode. Analyze-mode voice captures still use the original LLM-based node assessment, which is more accurate but slower. The composite scoring is a heuristic alternative for the no-LLM insight path. If insight matching proves unreliable in practice, consider running a Gemini Flash classification at save time (Layer 2 in the historiographic-knowledge-design.md plan).

## Session 68: Entity Matching Fix (April 13, 2026)

### What
Fixed two bugs in `_entity_matches_transcript()` in `review_engine.py` that caused voice captures (including insights) to miss obvious entity matches when transcripts contained plurals or short variant spellings.

### Discovery
Verified the first insight from session 67 ("difference between the Rashidun Khalif and... was it the Umayyads") was saved correctly but linked to wrong nodes (`ag_reception_hellenism` "The Persians" as primary, mostly Sicily/Rome `[keyword]` matches, no Islamic Civilization direct entity matches). The relevant entities (Umayyad Caliphate, Rashidun Caliphate, Abbasid Caliphate) all exist in `shared_entities` with correct curriculum links, but the matcher rejected them.

### Bugs
1. **No prefix matching**: Entity word "umayyad" failed to match transcript word "umayyads". Word-set intersection requires identical strings.
2. **Strict 60% + 2-word threshold for 2-word entities**: "Rashidun Caliphate" matched "rashidun" (1/2 words = 50%) but threshold required 60% AND ≥2 matching words. Multi-word entities with one distinctive proper noun were systematically rejected.

### Fix
- Added prefix matching for words ≥ 5 chars (avoids "Rome"/"Romeo" false positives while catching "umayyad"/"umayyads" plurals)
- Relaxed 2-word entity threshold: accept 1/2 match if the matched word is ≥ 6 chars (distinctive proper noun)
- Single-word and 3+ word entity rules unchanged

### Verification
Reprocessed the existing insight: now matches Umayyad/Rashidun/Abbasid Caliphates and 16 Islamic Civilization curriculum nodes including "The Mawali Question and Social Hierarchies" — exactly the topic of the insight. Updated primary node from byzantine alphabetical-first to islamic_ci_the_rashidun_caliphate_632661 (best-match domain has 16 direct links vs 4 byzantine).

### Impact
This affects ALL voice captures (analyze + insight modes), not just historiographic insights. Past captures may have been under-matched; could optionally backfill by reprocessing `voice_transcripts` with the new logic.

### Files Changed
- `scripts/review_engine.py` — `_entity_matches_transcript()` in `process_voice_capture()`

## Session 67: Insight Capture Mode (April 11, 2026)

### What
Added a "Save Insight" mode to voice capture for recording unverified theories, hypotheses, and historiographic observations without triggering the full analysis pipeline. Motivated by the need to capture interpretive/historiographic knowledge (e.g. "early caliphates prioritized Arab identity, later ones moved toward universal Islam") that doesn't fit the existing factual knowledge model.

### Design Decision
The current knowledge system is optimized for factual knowledge with clear right/wrong answers. But as reading moves into historiographic territory, there's a class of input — theories, attributed claims, debates, personal hypotheses — that shouldn't be treated as facts or trigger quiz generation. The insight mode is a minimal first step: save the transcript linked to curriculum nodes, but don't process further. This preserves the input for a future historiographic knowledge layer.

### Changes
- **`review_engine.py`**: `process_voice_capture()` accepts `capture_type='analyze'|'insight'`. Insight mode reuses all 4 phases of curriculum node detection (entity links, sibling overlap, domain expansion, keyword fallback), then saves to `voice_transcripts` with `source='insight'` and returns — no LLM call, no knowledge_items, no microlearning.
- **`research-server.py`**: `/explore/capture` parses `capture_type` from both multipart form and JSON body.
- **`ExplorerCapture.tsx`**: Recording and text-input states show two buttons: "Analyze" (solid, full pipeline) and "Insight" (outlined, transcribe + link only). Done state shows "Insight saved → Node1, Node2 ✓".
- **`voice-capture.tsx`**: Updated hint text explaining both modes.

### Design Document
Wrote `research/historiographic-knowledge-design.md` — comprehensive design doc covering:
- Taxonomy of non-factual knowledge (seeds → attributed claims → debates → frameworks → historiographic evolution)
- Five concrete risks of muddying the factual scaffold (diluting review time, ambiguous knowledge states, premature exposure, false attribution, scope creep)
- 6-layer proposal from minimal (insight capture, done) through speculative (debate-structured review)
- Data model: no new tables for Layers 0-1, optional `insight_metadata` table for Layer 2+
- Interaction with all 11 design principles
- Research grounding (Matuschak, Fuzzy-Trace Theory, elaborative interrogation, interleaving)
- Next step: Layer 1 (insight surfacing during elicitation/reading/review) — zero new data model, pure read-only surfacing

## Session 66: Quiz Dedup, Prompt Quality, LLM Comparison (April 11, 2026)

### What
Fixed quiz suggestion duplicates, improved prompt quality across all LLM-generated content using BAD/GOOD examples, and ran a systematic comparison of Codex (gpt-5.4 xhigh) vs Claude Opus for curriculum generation, microlearning cards, and question generation.

### Bug Fix
- **Quiz suggestion duplicates**: `generate_review_stream()` in `curriculum_db.py` only checked `knowledge_items` when filtering quiz suggestions — missed quizzes already created in `microlearning_quizzes`. Fixed by moving the `existing_quizzes` query before the suggestion builder and merging into a unified exclusion set. Exact text match is correct here (suggestions come from key_facts verbatim; semantic dedup already happens at multi-cue generation time).

### Prompt Improvements
- **rich_answer BAD/GOOD examples**: Both `QUESTION_GEN_PROMPT_FACTUAL` and `QUESTION_GEN_PROMPT` now include concrete examples showing vivid narrative style (specific names, ages, ironic details, physical description) vs. encyclopedia summaries. Teaches the model what "vivid" means.
- **Curriculum TITLE RULES**: `CURRICULUM_GENERATION_PROMPT` now has BAD/GOOD examples for node titles ("Merchant Wealth and Banking Families" → "The Medici Bank and Florentine Politics") and descriptions (thematic summary → specific names/dates/works). Tested via Codex comparison — dramatically improved title specificity.
- **Microlearning opening narrative**: Added "write like a storyteller" guidance and surprising detail quality bar. Quiz questions left unchanged — factual scaffold priority preserved.

### LLM Comparison: Codex vs Opus
Tested curriculum generation, microlearning cards, and question generation with both models. Results:
- **Curricula**: Both produced ~90 nodes. Opus names specific people/works in titles naturally; Codex needed explicit BAD/GOOD examples but then matched quality. Codex had denser prerequisite graphs (91% vs 71%).
- **Microlearning**: Opus tells better stories (eternal lamp before Plato's bust, Plato birthday banquet). Codex more historiographically aware (notes absence of institutional records as evidence, gives street addresses). Both valid, Opus better for "hooks not facts."
- **Question gen**: Opus rich_answers clearly richer — names minor figures (Urbán the cannon engineer), gives specific dates (May 29), makes causal links. Codex correct but reads like textbook.
- **Decision**: Staying with Opus for all interactive content. Codex viable as backup.

### Files Changed
- `scripts/curriculum_db.py` — Quiz suggestion dedup against `microlearning_quizzes`
- `scripts/review_engine.py` — BAD/GOOD examples in both question gen prompts and microlearning prompt
- `scripts/curriculum.py` — TITLE RULES with BAD/GOOD examples in generation prompt

## Session 65: Multi-Cue Retrieval Quizzes (April 10, 2026)

### What
Added automatic multi-angle retrieval cue generation for key_facts. When grading a review card, a background Gemini Flash call generates 2-4 alternate quiz questions per fact (e.g., "Who conquered Dacia?" / "What did Trajan conquer?" / "When was Dacia conquered?" — all testing the same fact from different angles). All cues share a `fact_id` and `rich_answer` (shared detail card), with semantic dedup at 0.82 cosine.

### Features
- **Multi-cue generation**: `generate_multicue_quizzes()` in `review_engine.py` — triggered as background thread after `record_answer()` for knowledge_items. Only processes date/event/person/place/fact type key_facts. Uses Gemini Flash with pub-quiz style prompt.
- **Shared detail cards**: `fact_id` and `rich_answer` columns on `microlearning_quizzes`. All cue-questions for one fact point to the same rich_answer content when revealed.
- **"Not interested in this fact"**: `POST /review/suspend-fact` — suspends all quizzes sharing a fact_id. Accessible from ⋯ menu on quiz cards.
- **"Quizzes for this topic"**: Review cards now show a checklist of all existing quizzes for the node at the bottom, with score status icons (✓/○/✗/•).
- **Fire-and-forget quiz creation**: QuizSuggestions component no longer awaits server response — instant checkmark on tap, DB write in background.

### Files Changed
- `scripts/review_engine.py` — `generate_multicue_quizzes()`, `MULTICUE_PROMPT`, hook in `record_answer()`
- `scripts/curriculum_db.py` — `existing_quizzes` query in stream builder, `fact_id`/`rich_answer` in quiz card data
- `scripts/research-server.py` — `POST /review/suspend-fact` endpoint, `fact_id` param on create-factual-quiz
- `scripts/db.py` — Schema: `fact_id TEXT`, `rich_answer TEXT` columns + migration + index
- `app/app/(tabs)/review.tsx` — `QuizSuggestions` fire-and-forget, `MicrolearningQuizCard` menu with "Not interested", existing quizzes listing
- `app/lib/book-api.ts` — `suspendFact()`, `fact_id` param on `createFactualQuiz()`

## Session 64: Multi-Domain Expansion (April 10, 2026)

### What
Expanded Petrarca from history-only to multi-domain learning. Generated 4 new curricula (music, literature, architecture, philosophy), fixed two pipeline bugs that prevented new curricula from working, and added Craig Wright's Yale music history course.

### New Curricula
- **Western Music History** (102 nodes, 406 key_facts, 61 entities) — Antiquity → 20th century: Gregorian chant, polyphony, Baroque, Classical, Romantic, Modernism
- **Western Literature** (110 nodes, 450 key_facts, 69 entities) — Homer → Modernism: epic, drama, novel, poetry across all major movements
- **European Architecture** (82 nodes, 354 key_facts, 63 entities) — Classical → Modern: Greek orders, Gothic, Renaissance, Baroque, Bauhaus, contemporary
- **Western Philosophy** (106 nodes, 462 key_facts, 63 entities) — Presocratics → 20th century: epistemology, ethics, metaphysics, political philosophy

### Bug Fixes
- **`generate_curriculum()` → SQLite gap**: Function saved JSON but `load_curriculum()` reads SQLite. New curricula were invisible to the entire pipeline. Added SQLite insertion to generation.
- **Entity pipeline disconnected**: `tag_curriculum_entities()` wrote to JSON entity index, but voice capture reads `shared_entities` + `entity_curriculum_links` in SQLite. Added `bootstrap_entities.py` call to server's post-generation flow.

### Infrastructure
- `_call_opus()` timeout 300s → 1200s, switched from JSON to text output format
- Server endpoint POST `/curriculum/generate` now runs full pipeline: generate → SQLite → entity tag (JSON) → entity bootstrap (SQLite) → index rebuild
- Installed `google-genai` on server for entity tagging
- Yale MUSI 112 course added as book with 23 lectures mapped to music history curriculum

## Session 63: Knowledge Sweeps — Tier 2 (April 9, 2026)

### What
Built knowledge sweep system — periodic domain-wide voice recall assessments scored against the full curriculum. Sweeps measure spontaneous retrieval organization (what you can produce unprompted), fundamentally different from quiz-prompted recall. First sweep on Sicily revealed 32.5% spontaneous recall vs 100% system coverage — reading ≠ retrieval.

### Full-Domain Sweep Screen (`knowledge-sweep.tsx`)
- Standalone screen accessible from ✦ drawer ("Knowledge Sweep" in Explore section)
- Flow: domain select → 7-era recording sequence → parallel transcription → LLM scoring → results display
- Each era gets its own voice recording, transcribed in parallel via `/knowledge/sweep/transcribe`
- Scoring via Opus produces: coverage, accuracy, connectivity, organization metrics
- System-vs-self comparison: system knowledge (from reading) vs spontaneous recall

### Era-Level Sweeps in Voice Elicitation
- Full-domain sweeps proved too exhausting (5+ min per era). Pivoted to era-level sweeps mixed into regular voice elicitation queue.
- `_era_sweep_candidates()` surfaces eras not swept in 14+ days as candidates with `type: 'era_sweep'`
- Voice elicitation UI shows SWEEP badge for era sweep candidates
- `run_voice_elicitation()` handles era_sweep type — routes to `run_era_sweep()` instead of standard node elicitation

### Sweep Scoring
- `SWEEP_SCORING_PROMPT` / `ERA_SWEEP_SCORING_PROMPT` — LLM scores transcript against curriculum nodes and key_facts
- Produces structured metrics: coverage (nodes mentioned/total), accuracy (% facts correct), connectivity (causal/temporal connections detected), organization (narrative structure)
- Per-node depth assessment: mentioned, explained, or connected

### Feedback Loop
- **Correction ML cards**: Wrong facts detected in sweep → `source_type='sweep_correction'` microlearning cards
- **Knowledge state updates**: Per-node depth assessment feeds back into knowledge levels
- **Timeline ML cards**: New card type (`source_type='sweep_timeline'`) generated when sweeps detect fuzzy chronology — presents date/event key_facts to build sequencing ability

### Database
- **`knowledge_sweeps`** — Stores sweep results: domain_id, era (nullable for full-domain), transcript, scores JSON, node-level results, created_at

### Endpoints
- `GET /knowledge/sweep/domains` — Available domains for sweeping
- `GET /knowledge/sweep/plan/{id}` — Sweep plan for a domain (eras, node counts)
- `POST /knowledge/sweep/submit` — Submit full-domain sweep for scoring
- `GET /knowledge/sweep/gaps` — Gap analysis from sweep results
- `POST /knowledge/sweep/transcribe` — Transcribe sweep audio
- `GET /knowledge/sweep/history/{id}` — Sweep history for a domain

### Key Findings (Sicily, 2 of 7 eras)
- System coverage: 100% (all nodes engaged/anchored from reading)
- Spontaneous recall: 32.5% (13/40 nodes) — massive gap between reading and retrieval
- Accuracy: 95.3% — facts are usually correct when stated
- 8 causal/temporal connections detected
- 4 factual errors corrected (Pericles→Alcibiades, Hiero allied with Rome not Athens, etc.)
- Greek Sicily: situation-model depth (causal chronological narrative)
- Arab-Norman Sicily: scattered facts without causal linking

### Design Decisions
- Full-domain sweeps too exhausting → era-level sweeps mixed into voice elicitation flow
- Sweeps measure something fundamentally different from quizzes: spontaneous retrieval organization vs prompted recall. The gap between them is the key diagnostic.
- Timeline ML cards address the specific gap revealed: knowing facts but not their chronological sequence

### Files Changed
- `scripts/db.py` — `knowledge_sweeps` table
- `scripts/review_engine.py` — `SWEEP_SCORING_PROMPT`, `ERA_SWEEP_SCORING_PROMPT`, `run_era_sweep()`, `get_sweep_plan()`, `score_sweep()`, `get_sweep_gaps()`, `get_sweep_history()`, `_era_sweep_candidates()`, era sweep handling in `run_voice_elicitation()`
- `scripts/research-server.py` — 6 new endpoints
- `app/app/knowledge-sweep.tsx` — full standalone sweep screen
- `app/app/voice-elicitation.tsx` — SWEEP badge, era_sweep type handling
- `app/lib/review-api.ts` — sweep API types and functions, `era_sweep` type
- `app/components/PetrarcaDrawer.tsx` — "Knowledge Sweep" entry in Explore section

## Session 62: Passive Knowledge Growth Tracking (April 9, 2026)

### What
Implemented Tier 1 (passive tracking) from `research/knowledge-growth-measurement-proposal.html` — the system now tracks knowledge growth over time without any new user interaction. All data comes from existing knowledge state changes, review scores, and curriculum prerequisite edges.

### Database
- **`knowledge_transitions`** — Event log of every knowledge level change (unknown→mentioned→engaged→anchored) with domain, node, source, timestamp. `update_knowledge()` instrumented to log transitions on every actual level change. Backfilled 313 historical transitions from existing `knowledge_states`.
- **`network_metrics_log`** — Periodic snapshots of per-domain metrics: node_coverage, edge_overlap (Goldsmith C metric), density, raw edge/node counts. Populated via `POST /knowledge/snapshot-metrics`.

### Network Metrics (Goldsmith Edge Overlap)
- `compute_network_metrics(domain_id)` computes learner vs expert graph similarity using curriculum prerequisite edges. If a user knows both endpoints of a prerequisite edge, it counts as "active."
- Edge overlap is the primary structural growth signal — distinguishes scattered facts (novice) from connected understanding (expert).
- Initial metrics: Sicily 98.0% edge overlap, Rome 64.9%, Byzantium 14.6%, Greece 3.6%.

### Growth Visualization (`/knowledge/growth`)
D3.js standalone page with 4 chart panels:
1. **Summary cards** — total known, coverage %, edge overlap %, transitions logged
2. **Current state** — stacked domain bars (mentioned/engaged/anchored)
3. **Coverage timeline** — cumulative nodes per domain over time (step chart)
4. **Edge overlap trajectory** — Goldsmith C metric over snapshots with domain lines
5. **Review performance** — weekly stacked bars (knew/partly/missed)
6. **Stability growth** — avg FSRS stability per domain over weeks

### Endpoints
- `GET /knowledge/growth` — HTML page
- `GET /knowledge/growth-data` — JSON: transitions, network_history, review_performance, stability_trends, current metrics
- `POST /knowledge/snapshot-metrics` — compute + store network metrics for all domains (cron-ready)

### Files Changed
- `scripts/db.py` — `knowledge_transitions` + `network_metrics_log` tables
- `scripts/curriculum_db.py` — instrumented `update_knowledge()`, added `backfill_knowledge_transitions()`, `compute_network_metrics()`, `snapshot_network_metrics()`, `get_knowledge_growth_data()`
- `scripts/research-server.py` — 3 new endpoints
- `scripts/knowledge_growth.html` — new D3.js visualization page

## Session 61: Voice Quiz Coverage Overhaul (April 9, 2026)

### What
Analyzed all 39 voice captures and found that 424 extracted facts were not becoming quiz questions. Voice elicitations (29 sessions) never created knowledge_items. 135 ML cards were stuck pending/failed due to missing `sentence_transformers` and expired Claude auth on server.

### Five Pipeline Fixes
- **A. Sync guard removed**: `process_voice_capture()` had `if not sync:` before ML card creation — sync mode silently dropped wonderings. Removed the guard.
- **B. Elicitation → knowledge_items**: `run_voice_elicitation()` now creates knowledge_items for nodes where none exist, with 14-day initial stability (long-term memory), proper `fsrs_card_json`, and background question pre-generation.
- **C. Wrong facts → correction quizzes**: `confidence_tagged` field (already extracted by LLM, never used) now creates `source_type='correction'` ML cards for confidently-stated incorrect facts. Added `correction` to HIGH-priority ML interleaving (1:3).
- **D. Missed facts no longer quizzed**: Removed missed-fact → ML card creation from elicitation. User prefers filling gaps through reading, not quizzing on unread content.
- **E. 135 pending ML cards reprocessed**: Sequential reprocessing script, all completed successfully.

### Server Dependency Fixes
- **Embedding fallback**: `get_learner_context()` now catches `sentence_transformers` import errors and falls back to relational-only retrieval instead of crashing the entire ML card generation pipeline.
- **`sentence_transformers` installed**: `pip3 install --break-system-packages sentence-transformers` on Hetzner.
- **limbic synced**: rsync + `pip install -e /opt/limbic` — server was running stale copy.
- **Claude auth synced**: `sync_claude_auth.sh` — 401 errors on `claude -p`.

### Duplicate Voice Capture Cleanup
- Cleaned up 8 duplicate voice_transcripts (39 → 31) — same podcast transcript processed 3-5x against different curriculum domains.
- Added transcript dedup via SHA-256 hash in `process_voice_capture()` — checks for existing transcript before processing.

### Design Decisions (Three Scenarios)
- **Podcast/book voice notes** → always generate quiz questions (voice_capture pathway)
- **Knowledge elicitation** → create lightweight SR items for demonstrated facts (high stability), correction quizzes for wrong facts, but don't quiz missed facts
- **Gap identification** → OK to identify, prefer filling by reading. Gap-fill items already deprioritized (-5.0, 3/batch cap)

### Files Changed
- `scripts/review_engine.py` — knowledge_item creation from elicitation, confidence_tagged corrections, removed missed-fact ML, sync guard removal, embedding fallback, transcript dedup
- `scripts/curriculum_db.py` — `correction` in HIGH-priority ML interleaving
- `scripts/reprocess_pending_ml.py` — new utility for reprocessing stuck cards
- `scripts/voice-capture-analysis.html` — one-time diagnostic page (static)

## Session 60: Card Provenance Display + FSRS Scheduling Fix (April 8, 2026)

### What
Added full provenance tracking to review cards (origin badge, "About this card" modal, "Bad question" flag). Found and fixed critical scheduling drift where voice paths bypassed FSRS, causing 229/256 cards to show up days or weeks too early.

### Card Provenance
- **Server**: `generate_review_stream()` now attaches `provenance` dict to every card — origin (book_chapter/book_whole/gap_fill/voice_wondering/follow_up/entity_research/user_request), stream_score, schedule_reason, knowledge_weight, fact_type_adj, sources array, created_at, due_at, last_reviewed_at
- **Origin badge**: Subtle label in card header — "📖 ch.4", "🔗 Gap fill", "🎙 Voice", "🔍 Follow-up", etc.
- **⋯ menu expanded**: "About this card" (full detail modal), "Bad question" (logs `review_flag_bad_question` event), "Suspend this topic"
- **About modal**: Card ID, origin description, book sources with confidence/dates, scheduling status, review count/last score/last reviewed, stability, due date, knowledge state, stream ranking score breakdown with component weights
- ML cards and ML quiz cards also get origin badge and about access

### FSRS Scheduling Fix (Critical Bug)
- **Root cause**: `run_voice_elicitation()` and voice capture in `review_engine.py` used old multiplicative formula (`stability_days *= multiplier`) instead of FSRS, overwriting `due_at` without updating `fsrs_card_json`
- **Impact**: 229/256 knowledge_items and 670 microlearning_quizzes had `due_at` that didn't match FSRS — some off by 702 hours (29 days). Cards graded "knew" were showing up days later instead of weeks
- **Data fix**: Aligned all `due_at` with FSRS JSON `due` field
- **Code fix**: Created `_fsrs_reschedule()` helper that loads FSRS card, applies rating, writes both `due_at` and `fsrs_card_json` atomically. Replaced old SQL `stability_days * ?` in both voice paths
- **Rule**: All scheduling MUST go through `record_answer()` or `_fsrs_reschedule()` — never raw SQL arithmetic on stability_days/due_at

### Files Changed
- `scripts/curriculum_db.py` — provenance data in `generate_review_stream()` for review + ML cards
- `scripts/review_engine.py` — `_fsrs_reschedule()` helper, fixed voice elicitation + voice capture scheduling
- `app/app/(tabs)/review.tsx` — `AboutCardModal`, `getOriginBadge()`, expanded ⋯ menu, origin badges on all card types
- `app/data/types.ts` — `provenance` field on `ResurfacingItem`

## Session 59: Review Card UX — Succinct Answers, ML Buttons, Entity Spans, Quiz Suggestions (April 7–8, 2026)

### What
Improved review card readability and microlearning card controls. Fixed entity markup on section-based ML cards. Made quiz suggestions actually work.

### Succinct Answer Line
- Review cards now show `answer_guidance` (1-2 sentence factual answer) as a **bold summary line** above the `rich_answer` (4-5 sentence explanation)
- Data was already there — `answer_guidance` was stored in `cached_question` and sent as `answer` in stream, but the UI only displayed `rich_answer`
- Only shown when short answer is meaningfully different (not identical, not a prefix of rich_answer)

### Microlearning Card Skip/Suspend
- Added **Skip** and **Suspend** buttons to top of microlearning cards (replacing "Not interested")
- Skip = schedule for later (calls `handleSkip`, card stays in pool)
- Suspend = remove from circulation (calls `dismissMicrolearning`)
- Removed redundant "Dismiss card" link from bottom actions

### Entity Markup on Section Cards
- **Bug**: Section rendering path used plain `<Text>` instead of `<AnnotatedText>` — entity/date markup never appeared on ML cards with structured sections (SOURCES, STILL VISIBLE, etc.)
- **Server fix**: `_annotate_item_entities()` now annotates each section text independently, stored as `entity_spans.section_0`, `section_1`, etc.
- **Client fix**: Sections now render with `<AnnotatedText>` using per-section span keys

### Quiz Suggestions Fix
- `quiz_suggestions` was baked into `cached_question` at generation time — only 2/90 cards had it
- **Moved to stream-build time**: now computed live in `generate_review_stream()` from key_facts minus existing knowledge_items
- All review cards now get up to 3 factual quiz suggestions
- Deduplicated: `related_facts` ("Same topic") excludes questions already in `quiz_suggestions` ("Quick quiz")

### Files Changed
- `app/app/(tabs)/review.tsx` — shortAnswerBox, ML top actions (Skip/Suspend), AnnotatedText in sections
- `scripts/curriculum_db.py` — live quiz_suggestions, per-section entity annotation, dedup related_facts

## Session 58: Review System Overhaul — FSRS, Logging, Entities, Card Gen (April 7, 2026)

### What
Comprehensive overhaul of the review system: replaced simple multiplicative scheduling with FSRS-6 (py-fsrs), rebuilt broken interaction logging, enriched entity database (+85 entities), changed card generation (6 follow-ups + factual quiz suggestions), removed entity intro cards and generate-more button.

### FSRS-6 Scheduling
- **Replaced** simple `stability × 2.5` multiplier with `py-fsrs 6.3.0`
- Parameters: `desired_retention=0.80`, `learning_steps=()`, `relearning_steps=()`, `enable_fuzzing=True`, `maximum_interval=365`
- Grade mapping: `knew` → Rating.Easy (~28d first due), `partly` → Rating.Good (~8d), `missed` → Rating.Again (~1d)
- `learning_steps=()` critical — without it FSRS schedules "Again" for 1 minute later (wrong for daily review)
- Added `fsrs_card_json TEXT` column to knowledge_items, review_items, microlearning_cards, microlearning_quizzes
- Migrated all 1342 existing items with stability preserved
- Fixed 23 items with NULL `last_score` from session 57 voice bulk update (set to 'partly')
- New knowledge_items and voice_followup review_items now initialized with FSRS card state

### Interaction Logging Rebuild
- **Problem**: Separate `log_server.py` on port 8091 was hung/unresponsive. Zero review events logged from mobile.
- **Fix**: Added `/log/events` endpoint to research-server.py (port 8090). Dual-layer: SQLite `interaction_log` table + JSONL files.
- New `interaction_log` table with event, item_id, score, session_id, response_ms, card_type, domain, node_title, extra
- Client logger URL changed from `:8091/log` to `:8090/log/events`
- Server-side `log_interaction()` called in both grading endpoints (`/curriculum/review/result` AND `/review/answer`) + suspend
- `server_log.py` extended with `log_interaction()` and `log_client_events()`

### Entity Linking Improvements
- Added `content` to second-pass entity annotation field list (was only annotating rich_answer, memory_hook, question)
- Created `enrich_entities.py` batch script: Gemini Flash extraction from all card content
- **Result**: 85 new entities (261→346). Includes Diodorus Siculus, Plutarch, Herodotus, Polybius, Cappella Palatina, Battle of Himera, etc.
- Deduplication: case-insensitive name + alias matching, require 2+ references across cards

### Card Generation Changes
- Follow-up questions: 6 instead of 3 (FOLLOW_UP_PROMPT, MICROLEARNING_PROMPT, ENTITY_RESEARCH_PROMPT all updated)
- **Factual quiz suggestions**: `_build_quiz_suggestions()` deterministically finds key_facts not yet quizzed (up to 3 per card)
- **QuizSuggestions UI component**: Green-accented "Quick quiz" chips below follow-up links. One-tap creates microlearning_quiz.
- **`/review/create-factual-quiz`** endpoint + `createFactualQuiz()` client API
- **Removed** "Generate 3 more questions" button (was adding latency; 6 initial follow-ups is sufficient)
- **Removed** entity intro cards (`MAX_INTRO_CARDS = 0`; rich answer cards now cover entity context)
- **Disabled** nexus cards — detection works (`_insert_nexus_cards()`) but cards lack synthesized content; showed as empty CONCEPT cards because client had no renderer for `type: 'nexus'`

### Bug Fix: Write-Lock Violation in record_answer
- `record_answer()` called `update_knowledge()` without passing `conn`, causing second connection to deadlock on WAL write lock
- Fixed: all `update_knowledge()` calls now receive `conn` parameter

### Files Changed
- `scripts/review_engine.py` — FSRS-6 scheduler, record_answer(), follow-up prompts (6), quiz suggestions, FSRS card init
- `scripts/db.py` — fsrs_card_json columns, interaction_log table
- `scripts/research-server.py` — /log/events, /review/create-factual-quiz, instrumented grading endpoints
- `scripts/server_log.py` — dual-layer logging (log_interaction, log_client_events)
- `scripts/curriculum_db.py` — entity annotation field list (+content), MAX_INTRO_CARDS=0
- `scripts/enrich_entities.py` — NEW: entity enrichment batch script
- `app/data/logger.ts` — URL change to :8090/log/events
- `app/app/(tabs)/review.tsx` — QuizSuggestions component, removed generate-more button
- `app/lib/book-api.ts` — createFactualQuiz()

## Session 57: Voice Upload Reliability + Review Tuning (April 7, 2026)

### What
Fixed three interconnected bugs causing voice upload failures and review questions resurfacing for well-known topics.

### Voice Upload Fixes
- **HTTP status code fix**: Server returned 500 for validation errors (too_short, transcription_failed), causing infinite client retry loops. Now returns 422 for validation errors, 500 only for real server errors. Validation results cached to prevent re-processing.
- **pending.json race condition**: Both `voice-elicitation.tsx` and `voice-upload-service.ts` did read-modify-write on the same `pending.json`. New recordings would resurrect already-cleared entries (caused the Sicily 1693 zombie retries — 12+ cache hits over 4 hours). Fixed: background service now clears entries individually with fresh reads; `savePendingUpload` deduplicates by requestId.
- **Removed too_short quality gate**: All recordings now get full LLM analysis regardless of length. The downstream coverage scoring handles quality.
- **422 retention**: Validation-failed uploads keep audio on device with `failedAt`/`failReason` flags. Auto-retry skips them. Manual retry via pending uploads UI with fresh request_id. Exported `getFailedUploads()`, `retryFailedUpload()`, `retryAllFailed()` for menu integration.

### Review Stream Tuning
- **Knowledge weight inversion**: `engaged: 8.0` (actively learning, highest priority), `anchored: 3.0` (well-known, deprioritized). Previously anchored was 8.0, boosting mastered topics.
- **Anchored skip**: Items with `knowledge='anchored'` + `last_score='knew'` + `confidence >= 0.5` + not yet overdue are skipped entirely from the review river.
- **Voice stability multipliers doubled**: Elicitation/capture now 5.0x (knew) / 3.0x (partly), up from 2.5x/1.5x. Retroactively adjusted 21 recently voice-reviewed items.

### Pipeline Verification
- All 13 voice uploads from April 6 processed correctly — transcripts, LLM analysis, chunks, embeddings, knowledge state updates all present.
- 2 duplicate transcript pairs found (same node, 14s/35s apart — race condition in retry, mitigated by pending.json fix).

### Files Changed
- `scripts/research-server.py` — 422 status for validation errors, cache validation results
- `scripts/review_engine.py` — removed too_short gate, voice stability 5.0x/3.0x
- `scripts/curriculum_db.py` — review stream: anchored skip + weight inversion
- `app/lib/review-api.ts` — handle 422 response body, `error` field on ElicitationResult
- `app/lib/voice-upload-service.ts` — per-entry clearing, failedAt/failReason, manual retry exports
- `app/app/voice-elicitation.tsx` — dedup savePendingUpload, show fail reason, fresh request_id on retry

## Session 56: Knowledge Profile System (April 6, 2026)

### What
Built a complete "digital twin" knowledge profile from voice transcripts. Every voice elicitation is now chunked, embedded, and linked to curriculum nodes and entities. This data is injected into all LLM prompts and surfaced on dashboard, atlas, and entity cards.

### Infrastructure (Phase 1)
- 3 new tables: `transcript_chunks` (embedded pieces), `chunk_node_links` (many-to-many), `chunk_entity_links` (many-to-many)
- `create_transcript_chunks()` — chunks transcripts, batch-embeds with MiniLM 384d, links to nodes via entity cross-references
- `get_learner_context(node_id, domain_id, conn)` — dual retrieval: relational (chunk_node_links) + semantic (cosine similarity ≥ 0.35)
- `get_learner_context_for_entity(entity_name, conn)` — entity-scoped retrieval with fuzzy match fallback
- `reprocess_transcripts.py` — backfill script, processed all 28 existing transcripts → 786 chunks, 13,743 node links, 80 entities

### Prompt Injection (Phase 2)
- `{learner_context}` added to 6 prompt templates: QUESTION_GEN_PROMPT_FACTUAL, QUESTION_GEN_PROMPT, FOLLOW_UP_PROMPT, _ENRICH_PROMPT, MICROLEARNING_PROMPT, ENTITY_RESEARCH_PROMPT
- All call sites updated: `generate_question()`, `_key_fact_to_question()`, `_generate_follow_up_queries()`, `_run_microlearning_research()`, `_run_entity_research()`

### Candidate Selection Fix (Phase 3)
- `_elicitation_candidates_for_domain()` now checks `chunk_node_links` for cross-node coverage
- Partially-covered nodes penalized -0.5 (not excluded) — confirmed working for 2 Byzantine nodes
- "Don't know" flow returns `already_covered` hint if topic was discussed in adjacent elicitation

### Elicitation Enrichment (Phase 4)
- VOICE_ELICITATION_PROMPT now extracts: `entities_mentioned`, `confidence_tagged`, `organizing_framework`, `adjacent_nodes_covered`
- `create_transcript_chunks()` wired into live `run_voice_elicitation()` pipeline with stable `vt_id` shared between chunk creation and transcript logging
- VOICE_CAPTURE_ANALYSIS_PROMPT also got `confidence_tagged`

### Domain Summaries (Phase 5)
- `domain_knowledge_summaries` table — cached 300-500 word knowledge portraits per domain
- `generate_domain_summary()` — follows read→close→LLM→reopen→write discipline
- `get_domain_summary()` prepended to every `get_learner_context()` call
- API: `GET /knowledge/profile/{domain}`, `POST /knowledge/profile/regenerate/{domain}`
- Generated portraits for all 5 active domains (Sicily, Ancient Greece, Byzantine, Rome, Islamic Civ)

### Visibility
- **Dashboard** (`/stats/dashboard`): Knowledge Profile section with chunk counts, type breakdown, cross-node links, domain portrait metadata
- **Atlas** (`/knowledge/atlas`): Node detail shows "Your Voice Recall", domain detail shows full portrait, entity detail shows "What You've Said"
- **Entity cards** (mobile): `voice_context` array in API response, displayed under "What I know → From your voice recall"
- **Entity API** (`/entity/{id}`): Returns `voice_context` from transcript chunks

### Bug Fixes During Review
- `get_domain_summary()` missing try/except for nonexistent table — would have crashed all review question generation
- `generate_domain_summary()` write-lock violation — held conn during 5-15s LLM call. Fixed to read→close→LLM→reopen→write
- `vt_id` mismatch — chunk transcript_id and voice_transcripts.id now use same pre-generated ID
- `fonts.serif` → `fonts.body` in EntitySheet.tsx (TS error caught by push hook)

### Files Changed
- `scripts/db.py` — 3 new tables + 1 migration
- `scripts/review_engine.py` — ~630 lines: chunking, retrieval, prompt injection, domain summaries
- `scripts/research-server.py` — knowledge profile endpoints, entity voice context, candidate coverage hint
- `scripts/curriculum_db.py` — dashboard stats + atlas data with voice chunks/portraits
- `scripts/statistics_dashboard.html` — Knowledge Profile codex-page
- `scripts/knowledge_atlas.html` — voice chunks in detail panels
- `scripts/reprocess_transcripts.py` — new backfill script
- `app/components/EntitySheet.tsx` — voice context display
- `app/data/types.ts` — `voice_context` on EntityDetails

### Known Limitations
- NER regex fallback misses single-word entities ("Aristotle") — only fires when LLM `entities_mentioned` absent (old transcripts)
- Cross-node linking depends on `shared_entities` coverage — "Fourth Crusade" not linked from Constantinople because entity wasn't extracted from old transcript. Future elicitations use LLM extraction.
- Domain portraits require 10+ chunks. Portrait regeneration is synchronous (15-20s on first GET request).

## Session 55: Review Card Quality Overhaul (April 6, 2026)

### What
End-to-end audit and fix of the review card experience. Every card now has rich narrative answers, temporal memory hooks, and quality follow-up questions. Added suspend functionality and related-facts checklist.

### UX Fixes
- **Flash after grading**: Removed "also want to know" suggestions panel + 500ms delay. Cards stay rendered during fade-out, instant transition to next card
- **Cards re-appearing**: Added `gradedIdsRef` tracking graded/skipped/dismissed IDs in session. Stream only reloads if away >60s (was every focus event). Manual Refresh clears the set
- **Generic entity filtering**: `_GENERIC_ENTITIES` set excludes ~20 obvious places (Italy, Venice, Greece, Sicily, Spain, etc.) from entity span annotations
- **Suspend button**: ⋯ menu on review cards → "Suspend this topic" pushes `due_at` 1 year forward. `POST /curriculum/review/suspend` endpoint

### Quality Pipeline Fixes
- **Follow-up queries**: Switched from Haiku → Sonnet, increased context 200→500 chars, removed template fallback. Regenerated all 100 items — 0% template queries remaining
- **Answer enrichment**: `_key_fact_to_question()` now calls Sonnet for rich_answer (4-5 sentences) + memory_hook at generation time. Backfilled all 96 bare items
- **Related facts checklist**: "Same topic" section shows other key_facts from the same node — tested (✓/○) and untested (○). Informational peace-of-mind, not action buttons. Up to 5 facts shown per card

### Data Quality Before/After
| Metric | Before | After |
|--------|--------|-------|
| Good follow-up queries | 17% | 100% |
| Rich narrative answers | 4% | 100% |
| Memory hooks | 4% | 96% |
| Template follow-ups | 83% | 0% |

### Files Changed
- `app/app/(tabs)/review.tsx` — removed suggestions panel, added gradedIdsRef, suspend menu, related facts checklist
- `app/lib/book-api.ts` — added `suspendReviewItem()`
- `scripts/review_engine.py` — Sonnet for follow-ups + key_fact enrichment, `_ENRICH_PROMPT`
- `scripts/curriculum_db.py` — `_GENERIC_ENTITIES` filter, `related_facts` in stream, `question_history` tracking for tested/untested
- `scripts/research-server.py` — `POST /curriculum/review/suspend` endpoint

## Session 54: Curriculum Audit & Overlapping Curricula (April 5, 2026)

### What
Comprehensive audit of the curriculum system — investigated where curricula earn their keep and where they don't. Identified that the "overlapping" in overlapping-curricula was unrealized (single-domain book mapping). Implemented the key missing features to realize the vision.

### Investigation Findings
- Curriculum essential for: deduplication (one node per concept), progress visualization (bounded 60-80 nodes), voice elicitation, key_facts deterministic questions
- Biggest gap: `detect_curriculum()` returned ONE domain per book — Syracuse book only mapped to Sicily, not also to Rome and Greece
- `shared_entities` (261 entities, 511 links) existed but wasn't queried during review
- 3 of 9 curricula unused (AP European, AP World History, Ancient & Classical) — kept for future
- Gap-fill was too aggressive (siblings within 200 years) and low-quality (curriculum description only)

### Implementation
1. **Multi-domain chapter mapping**: `create_review_items_for_chapter()` now uses `suggest_curricula_for_book()` to map against top-2-3 curricula (score >= 0.40)
2. **Cross-curriculum context**: `_get_cross_curriculum_context()` queries `entity_curriculum_links` + `knowledge_states` across domains, injected into question generation prompts
3. **Temporal cross-references**: `_get_temporal_cross_references()` finds contemporaneous events from other curricula, adds "Meanwhile in..." context to questions
4. **Entity nexus cards**: `_insert_nexus_cards()` inserts cross-perspective cards in review stream for entities with nexus_score >= 3 (Carthage, Byzantine Empire currently qualify)
5. **Improved gap-fill**: Prerequisites only (removed sibling expansion), enriched with `book_curriculum_mappings` when available
6. **Book pre-scan**: `GET /book/prescan/{book_id}` — shows known/new nodes, missing prerequisites, cross-book overlaps

### Files Changed
- `scripts/review_engine.py` — multi-domain mapping, cross-curriculum/temporal helpers, gap-fill improvement
- `scripts/curriculum_db.py` — nexus cards, book prescan function
- `scripts/research-server.py` — prescan endpoint

## Session 53: Statistics Dashboard (April 5, 2026)

### What
Standalone statistics page at `/stats/dashboard` combining three design approaches: dense metrics (Folio), timeline narrative (Chronicle), and card-based sections (Codex). Designed via design-explorer with 4 mockups, user selected top 3 for synthesis.

### Implementation
1. **`get_dashboard_stats()`** in `curriculum_db.py` — aggregates data from knowledge_states, knowledge_items, microlearning_cards, microlearning_quizzes, voice_transcripts, physical_books, kindle_books, book_captures, review_items.
2. **`/stats/dashboard-data`** endpoint in research-server.py.
3. **`statistics_dashboard.html`** — standalone HTML page with Petrarca design tokens. Fetches JSON on load.

### Sections
- **Today** — reviewed/due/elicitations/scores (4-column grid)
- **Knowledge State** — stacked bars per curriculum, linked to coverage pages
- **Review & Quiz** — all-time/7d/30d counts, score distribution, follow-ups/pipeline/stability, per-curriculum breakdown
- **Reading** — physical + Kindle books with progress bars, linked to book pages
- **Voice Elicitation** — total sessions, audio minutes, recall distribution, cards triggered
- **Activity Timeline** — chronological feed grouped by day: reviews, voice, cards, book captures. All linked.

### Fixes
- Voice recall: uses `suggested_score` (knew/partly/missed), not `knowledge_demonstrated`
- Book dedup: Kindle books already in physical_books excluded

### Key Files
- `scripts/statistics_dashboard.html` (new)
- `scripts/curriculum_db.py` — `get_dashboard_stats()`
- `scripts/research-server.py` — `/stats/dashboard` + `/stats/dashboard-data` routes

## Session 52: Rich Voice Capture Pipeline (April 5, 2026)

### Problem
Voice recordings from the Explore tab (person detail pages + top-level) used a thin Gemini Flash pipeline that only saved entity notes and logged transcripts. No knowledge state updates, no quiz generation, no curriculum node mapping. Three Sicily recordings from April 4 demonstrated the gap: zero entities detected, one claim each, no knowledge graph impact.

### New `process_voice_capture()` Function (`review_engine.py`)
Full knowledge graph ingestion pipeline for voice captures:
1. **Entity detection**: Multi-word entity matching via word overlap (>60% significant words, handles "Arab Conquest of Sicily"). Word boundary checks for short names.
2. **Node routing**: 4-phase priority system — directly linked nodes (entity_curriculum_links) → title-overlap siblings → primary domain fill → keyword fallback. Prevents prompt bloat from irrelevant domains.
3. **Claude analysis**: Extracts facts, maps each to curriculum nodes, assesses knowledge level per node, extracts wonderings. Prompt explicitly rejects cross-era mappings.
4. **Knowledge graph updates**: Upserts `knowledge_items` with voice capture sources (same pattern as `create_review_items_for_chapter()`), updates `knowledge_states`, clears `cached_question` to trigger re-generation.
5. **Quiz generation**: Pre-generates questions in background thread (or synchronously via `sync=True`).
6. **Microlearning**: Creates research cards from wonderings (up to 5).

### `/explore/capture` Endpoint Upgrade
Replaced thin Gemini Flash analysis with call to `process_voice_capture()`. Backward-compatible response shape. Entity name resolution from `shared_entities` DB.

### Reprocessing Results (3 Sicily recordings from April 4)
- **Recording 1** (Arab conquest podcast): 30 facts → 8 nodes. Arab Conquest of Sicily: **anchored** (18 facts), Norman Conquest: **anchored** (11), Palermo: **engaged** (9).
- **Recording 2** (Linguistic evolution): 13 facts → 10 nodes across Sicily chronology. Frederick II, Norman Conquest, Sicilian School of Poetry: **engaged**.
- **Recording 3** (Barbero/Frederick II): 49 facts → 7 nodes. Frederick II Stupor Mundi: **anchored** (49 facts!), Knowledge Transmission to Medieval Europe: **engaged**.
- Total: 19 knowledge items with voice capture sources, 25+ quiz questions generated, 15 microlearning wonderings triggered.

### Fixes During Development
- **DB lock contention**: `sync=True` parameter runs question generation inline, skips background microlearning threads. Used by batch reprocessing to avoid deadlocks.
- **Bad node mappings**: Prompt tightening + algorithm fix (Phase 3 only expands primary domain). Cleanup script removed 10 spurious Roman Republic mappings.
- **Duplicate sources**: Dedup by source_text prefix from multiple test runs.

### Key Files Changed
- `scripts/review_engine.py`: `process_voice_capture()`, `VOICE_CAPTURE_ANALYSIS_PROMPT`
- `scripts/research-server.py`: `_handle_explore_capture()` rewritten
- `scripts/cleanup_voice_captures.py`: One-shot cleanup script
- `scripts/reprocess_voice_captures.py`: Batch reprocessing script

## Session 50: Kindle SQLite Migration + Amazon Scraper + Browse Screen (April 5, 2026)

### Kindle SQLite Migration
- Migrated `kindle_library.json` → `kindle_books` SQLite table (25 columns, key=ASIN/book_id/title hash)
- New `available_epubs` table for indexing server-side EPUB files
- Helper functions: `upsert_kindle_books()`, `get_kindle_books()` (full query with search/filter/sort/pagination), `get_kindle_book()`, `migrate_kindle_json_to_sqlite()`
- All 7 existing Kindle endpoints rewritten from JSON to SQLite, backward-compatible response shapes
- `process_kindle_books.py` updated to read from SQLite instead of JSON
- Auto-migration runs on server startup

### New API Endpoints
- `GET /kindle/browse` — Full-featured query with search, status/category/tracked filters, sort, pagination. Returns `{books: [...], total: N}`
- `POST /kindle/scan-epubs` — Scans `/opt/petrarca/data/epubs/*.epub`, extracts OPF metadata, fuzzy-matches against kindle_books by title

### Amazon Library Scraper
- `amazon_library_scraper.py` — Uses `agent-browser --auto-connect` to leverage running Chrome's Amazon login
- Navigates to Amazon Content & Devices, extracts books via JS DOM evaluation (two strategies: data-asin attributes + /dp/ link parsing)
- Handles pagination, deduplicates by ASIN, pushes to `POST /kindle/sync`
- `com.petrarca.amazon-sync.plist` — daily launchd job (86400s interval)

### Kindle Browse Screen (Expo)
- `kindle-browse.tsx` — Search bar (300ms debounce), status/tracked filter chips, sort pills (recent/title/author/progress)
- Virtualized FlatList with pagination (50 per page). Shows cover, title, author, category badge, EPUB badge, progress bar, tracked indicator
- "Include" button for untracked books (→ addPhysicalBook), tap tracked books → book-detail
- EPUB ingestion: when including a book with `epub_path`, triggers `ingest_book_petrarca.py` for full-text extraction instead of research agent
- Navigation: ✦ drawer "Kindle Library" item, Library tab "Browse full Kindle library" link

## Session 49: Microlearning Card Enrichment + Follow-Up Overhaul (April 4–5, 2026)

### Card Content Enrichment
- `MICROLEARNING_PROMPT` now requires primary sources, material evidence, "still visible" sections
- Output is structured `sections` array with headings, rendered with small-caps rubric subheadings
- Enriched cards (200-350 words) preferred 3/4 over baseline in calibration eval
- `_strip_markdown()` handles asterisks before entity span computation

### Follow-Up Query Overhaul
- Replaced template follow-ups with LLM-generated queries via Haiku (`FOLLOW_UP_PROMPT`)
- Emphasizes sideways angles: geography, counter-narratives, structural causes, transmission history
- "Generate 3 more" button for additional follow-ups
- Durable server-side tracking: `triggered_follow_ups` column on knowledge_items + microlearning_cards

### Card Titles
- New `title` field with dates (e.g., "The Catiline Conspiracy (63 BC)")
- Displayed at 20px displaySemiBold. New DB column + full pipeline threading

### Entity Notes + Capture
- `ExplorerCapture` component for voice/text entity notes
- `POST /entity/notes` endpoint, notes displayed in EntitySheet "What I know" section

## Session 45: Knowledge Explorer & Timeline (April 4, 2026)

### Knowledge Explorer
- `KnowledgeExplorer.tsx` — 3 subtabs: Timeline / Persons / Places
- Timeline: entity-focused, cross-domain, century grouping, era bands, knowledge dots
- Persons (450) and Places (384) lists with domain dots, date ranges, knowledge indicators
- Tappable entity tags → filters timeline (browsing loop)
- "Generate card" button on events → triggers microlearning

### 3-Tab Review Screen
- Review tab: **Cards / Voice / Explore** tabs (was Cards + Voice button)
- Explore tab embeds KnowledgeExplorer
- Tappable dates in review cards → switches to Explore tab at that century
- Entity→timeline linking: EntitySheet "✦ View in timeline" button

### 100% Date Coverage
- `backfill_node_dates.py` populated dates for all 758 curriculum nodes (was ~40%)
- Entity re-indexing: 450 persons, 384 places, 316 events (was 226/219)

## Session 48: Voice Elicitation Quality Analysis + Dedup Fixes (April 4, 2026)

### Analysis
Full audit of all 20 voice transcripts, extraction pipeline, and downstream effects. Findings:
- **Extraction quality is excellent**: LLM correctly identifies captured/missed/interesting/wonderings. Feedback summaries are personalized and pedagogically useful.
- **Recall patterns are rich**: Transcripts show associative hook-building (e.g., connecting Frederick II to Sicilian School of poetry, Al-Andalus to troubadour poetry).
- **Major duplication bug**: 7 of 20 transcript rows were duplicates — same audio re-uploaded by mobile retry service. Caused inflated stability_days, duplicate microlearning items, wasted API calls.

### Fixes
1. **Server-side audio dedup**: Before transcription/LLM, checks `voice_transcripts` for matching `node_id + audio_bytes`. Returns cached LLM result instantly.
2. **Minimum transcript quality gate**: Recordings under 15 words get "too short" response instead of full LLM processing. Catches interrupted recordings (e.g., 13-char "I'm assuming." and Chinese-interrupted 97-char transcript).
3. **Wondering dedup at DB layer**: Before inserting `voice_followup` items, checks for existing items with same `curriculum_node_id + source_text`.
4. **Prompt refinement**: MISSED now targets structurally important facts (dates, actors, causal relationships) over colorful details. Adjacent topic knowledge gets partial credit in coverage_pct.
5. **Data cleanup**: Removed 6 duplicate transcripts (20→15), 3 duplicate followup items (18→16), corrected inflated stability_days on 3 knowledge_items.

### Files
- `scripts/review_engine.py` — dedup check, quality gate, wondering dedup, prompt refinement
- `scripts/cleanup_voice_dupes.py` — one-time data cleanup script

---

## Session 47: Voice Elicitation UX + Book Recall (April 4, 2026)

### Changes

**1. "Know Nothing" button replaces ambiguous "Skip"**
- Voice prompt screen now shows two options: **Know nothing** (rubric-colored, records `knowledge=unknown` with confidence 0.8) and **Skip** (muted, no signal).
- New `POST /review/elicit-know-nothing` server endpoint. Fire-and-forget from client.
- Files: `voice-elicitation.tsx`, `review-api.ts`, `research-server.py`.

**2. Fix: chapter recall from book-detail was silently failing**
- `book-detail.tsx:634` always passed `domain_id: ''` due to broken ternary (`book.topics?.[0] ? '' : ''`).
- Server at `_handle_voice_elicitation` rejected empty `domain_id` with 400 — recordings saved to `pending.json` but never processed.
- Fix: server auto-detects domain from `knowledge_items WHERE sources LIKE '%{book_id}%'`. Both handler and `run_voice_elicitation` have fallback detection.
- Files: `research-server.py`, `review_engine.py`.

**3. Voice prompts now load more instead of ending**
- Previously: 10 candidates loaded, session ended at "done" when exhausted.
- Now: tracks `seenNodeIds`, pre-fetches when 2 from end, auto-resumes via `useEffect` on `candidates.length` if new batch arrives while on done screen.
- Files: `voice-elicitation.tsx`.

**4. Book-level "Record what I remember" button**
- Always-visible button on book-detail page, not tied to chapter selection. Uses `node_id: book:{book_id}`.
- Server gathers ALL source texts for the book (up to 8), updates all linked knowledge_items.
- Useful for Kindle-tracked books or loosely-chaptered reads.
- Files: `book-detail.tsx`, `voice-elicitation.tsx`, `review-api.ts`, `review_engine.py`.

---

## Session 46: Voice Upload Robustness (April 4, 2026)

### Problem
Voice elicitation uploads failing consistently. Two root causes identified from server logs:
- **Connection reset by peer** (today): Server completes 40-50s processing (Soniox transcription + Claude LLM analysis) but mobile connection drops before response delivery. 4 failures in 2 hours.
- **Database is locked** (yesterday): 38 errors in 24h — post-LLM DB writes blocked by concurrent pipeline or other voice-elicit requests exceeding 60s busy_timeout.
- Combined effect: recordings stuck in `pending.json`, retries re-process everything (wasting API calls), and may fail again the same way.

### Fix: 3-Layer Robustness

**1. Idempotent retry via request_id caching (server + client)**
- Client generates stable `request_id` per recording (`elicit_{timestamp}_{node_id}`).
- Server caches successful results to `voice_elicit_cache/{request_id}.json` *before* sending response.
- On retry: cache hit returns instantly (<1s) — no re-transcription, no re-LLM, no duplicate side effects.
- Cache expires after 24h. `ConnectionResetError` gracefully handled instead of crashing.
- Files: `research-server.py` (`_handle_voice_elicitation`), `review-api.ts` (`sendVoiceElicitation`), `voice-elicitation.tsx` (PendingUpload + requestId plumbing).

**2. DB write retry loop (server)**
- Post-LLM write section (knowledge updates, review items, wonderings) wrapped in 3-attempt retry with 5s/10s backoff.
- Even if all retries fail, LLM result still returned (and cached) — writes succeed on client's next retry.
- File: `review_engine.py` (`run_voice_elicitation`).

**3. Auto-retry on app foreground + toast (client)**
- New `voice-upload-service.ts`: listens for `AppState` "active" transitions, retries all pending uploads.
- Entries expire after 48h (was: never, required manual navigation to voice-elicitation screen).
- New `VoiceUploadToast.tsx`: global toast showing success/failure of background retries.
- Wired into `_layout.tsx` at app startup.

### Files Changed/Created
- `scripts/research-server.py` (idempotent cache, graceful ConnectionReset)
- `scripts/review_engine.py` (DB write retry loop)
- `app/lib/review-api.ts` (requestId parameter)
- `app/app/voice-elicitation.tsx` (requestId generation + plumbing)
- `app/lib/voice-upload-service.ts` (new — background retry service)
- `app/components/VoiceUploadToast.tsx` (new — global toast)
- `app/app/_layout.tsx` (wire service + toast)

## Session 44: Multi-Quiz Microlearning, Entity Research, Review Stream Fix (April 4, 2026)

### Review Stream Fix
- **Root cause**: ALL 253 knowledge_items had `cached_question = NULL` — zero regular review cards could be served. Only 5 microlearning cards showed before "no more cards."
- **Batch generation**: New `POST /review/batch-generate` endpoint populated questions for all 109 eligible items.
- **Dynamic ML limit**: When regular items are sparse (<3), ML cards fill the whole batch. Fixed `has_more` pagination to count ML cards.

### Multi-Quiz Microlearning Cards
- **`microlearning_quizzes` table**: Each quiz independently FSRS-scheduled. ML card = content container, quizzes = review atoms.
- **Prompt**: Updated to generate 3-5 specific factual questions per card (date, person, event, consequence, connection).
- **First encounter**: Content shown, then all quizzes stacked with per-quiz Show answer / Skip / Grade. "Complete →" button to advance.
- **Re-review**: Individual quiz shown first (`microlearning_quiz` card type), full content revealed as answer.
- **Dismiss**: Per-quiz "Skip", per-card "Not interested" (top) + "Dismiss card" (bottom).

### Quiz Dedup (limbic MiniLM)
- New quizzes checked against existing quizzes + curriculum key_facts using MiniLM 384d cosine at 0.82 threshold.
- All matches logged with similarity score for calibration review (~Apr 18).
- Verified: caught "When was Battle of Himera?" duplicate at 0.907, let through different-angle questions at 0.77-0.81.

### Entity Research System
- **"3 questions" button**: Claude Sonnet generates research queries informed by temporally/spatially related entities.
- **"Research this" button**: Triggers rich entity profile ML card with connections to same-period/same-region entities.
- **Entity markup**: LLM annotates people/places/events/concepts with canonical IDs in ML card content → tappable spans.
- **Backlinks**: Entity lookup shows "In your research" with ML cards mentioning that entity. Dynamic entities for IDs not in shared_entities.
- **Caching**: Entity research stored as ML cards, available on subsequent entity opens.

### Other
- Scroll to top on card transitions.
- Backfilled 37 legacy ML cards with quiz rows.
- Cleaned up 3 failed + 1 pending ML cards.

## Session 41: Review System Consolidation + Fractal Exploration (March 30 – April 1, 2026)

### Review Tab Rewrite — Infinite River + Knowledge Items
- **Data source changed**: Review now uses `knowledge_items` (253 items across 6 curricula) instead of `retrieval_questions` (19 Sicily-only). Knowledge items carry FSRS scheduling, curriculum context, and source provenance.
- **Cards/Voice sub-tabs**: Review tab split into two modes — card-based review and voice recall. Cards are the default.
- **Infinite river**: No session boundary. Cards stream continuously; user stops when they want. Replaces the old 10-card batch + "Continue" button pattern.
- **Skip button**: Every card has a skip action — logs `review_skip` and moves to next card without affecting scheduling.
- **Simplified grading**: Three grades — knew / partly / missed — feed directly into FSRS scheduling via `review_engine.record_answer()`.

### Fractal Exploration — Microlearning Research Pipeline
- **Follow-up queries**: Each review card gets 3 LLM-generated follow-up research queries (e.g., "How did X influence Y?").
- **Tap to research**: Tapping a query triggers background Gemini + Search. Result stored as a `microlearning_card` with content, an assessment question, and 3 new follow-up queries (recursive fractal).
- **Interleaved in stream**: Microlearning cards appear in the review river every ~5 items, mixing retrieval practice with discovery.
- **Text input**: Every card has a text input for custom research queries — user types a question, same pipeline runs.
- **New table**: `microlearning_cards` in petrarca.db (content, assessment Q, follow-ups, parent card reference).
- **New endpoint**: `POST /review/microlearning` — generates microlearning card from query via Gemini + Search.

### Voice Mode — Chapter Recall Prompts
- Voice elicitation now includes "What do you remember from Chapter X?" prompts for active books.
- Chapter recalls get high priority in candidate selection for voice elicitation sessions.

### Data Cleanup — Legacy Review Code Removed
- **Removed code paths**: `record_review_result()`, `get_review_status()`, `get_retrieval_questions()` — all replaced by knowledge_items + review_engine.
- **Archived tables**: `retrieval_questions` and `review_schedule` tables archived with data preserved (not dropped), but no code references them.
- **Still active**: `review_items` table remains (used for exploration items and voice follow-ups).
- **Scoring**: Exclusively through `review_engine.record_answer()` — single path for all review grading.

### Interaction Logging — Comprehensive Review Events
New events for algorithm tuning:
- `review_card_shown` — card presented to user
- `review_answer_revealed` — user taps to see answer
- `review_result` — grading result with `time_seconds` field for response latency
- `review_skip` — card skipped
- `review_entity_intro_continue` — entity introduction card continued
- `review_custom_query` — user typed a custom research query
- `review_research_triggered` — follow-up research query tapped

### Navigation Cleanup
- **Drawer**: "Voice Recall" and "Hamarquizen" entries removed from drawer navigation.
- **Book detail**: "Hamarquizen" renamed to "Book Review".
- **Book detail review badge**: Now navigates to the Review tab instead of inline Hamarquizen screen.

### Book archive/remove feature
- **Swipe-to-remove on mobile**: `Swipeable` from `react-native-gesture-handler` on book rows in Library tab — swipe left reveals rubric-red "Remove" action. Same pattern as ArticleRow feed dismiss.
- **Hover × on web**: Absolute-positioned remove button appears on hover, with `confirm()` dialog.
- **Soft-delete via `archived` status**: Books set to `reading_status: 'archived'` are hidden from all Library filter tabs (Reading, All, Finished). Status syncs to server, survives app restart. Data preserved (reversible).
- **Bug fix**: `archiveBook()` in `book-store.ts` was incorrectly setting `reading_status: 'finished'` instead of `'archived'` — archived books were appearing in the Finished tab.
- **GestureHandlerRootView**: Added to Library screen (required for `Swipeable` on native).
- Book-detail screen already had an "Archive" status pill that correctly sets `'archived'` and navigates back.

### Files changed
- `app/app/(tabs)/library.tsx` — `GestureHandlerRootView` wrapper, `Swipeable` on native, hover × on web, `archived` filtered from all views
- `app/data/book-store.ts` — `archiveBook()` fixed to set `'archived'`

## Sessions 39–40: Curriculum Review System + Multi-Curriculum Queue (March 27–29, 2026)

### Curriculum Visualization (Session 39)
- **`curriculum_graph.html`**: Force-directed D3 graph of all curricula — nexus entity nodes, domain color lanes, Graph↔Timeline tabs
- **`curriculum_timeline.html`**: Horizontal D3 timeline — 5 curriculum lanes, 220px collapsible entity filter panel (persons/places/events), hierarchical place expansion, D3 brush for zoom, "Undated" column, detail sidebar. Served at `/curriculum/timeline`.

### Review Question Quality (Session 39)
- **Root cause**: Questions tested source-text trivia ("Which city founded Naxos?") instead of curriculum concepts
- **Fix**: `QUESTION_GEN_PROMPT_FACTUAL` redesigned — node description IS the answer guide. Questions test conceptual understanding ("What drove Greek colonization of Sicily?"), not random facts. Examples updated to be curriculum-agnostic.
- **Curriculum scan**: Level 1 container nodes filtered out (never assessable). Queue ordering: history areas before culture areas, chronological by `date_start` within area.
- **Dedup guard**: `create_exploration_items()` checks for unexpired items before creating new ones.
- **Node rename**: "Architecture as Palimpsest" → "Sicily's Architecture: Layers of Conquest" in curriculum JSON.

### Multi-Curriculum Knowledge Items + Review Queue (Session 40)

#### Byzantine + Islamic self-assessments → review queue
- User completed curriculum-scan for Byzantine (49 nodes: 16 engaged, 33 unknown) and Islamic (40 nodes: 11 engaged, 29 unknown)
- **Bridge script**: Creates `knowledge_items` from `knowledge_*.json` state files. Stability based on assessed level: unknown=1d/due-now, engaged=14d, anchored=60d. Sources: `[{type: 'self_assessment', ...}]`.
- **Date enrichment**: LLM-assigned `date_start`/`date_end` to all 78 Level 2+ Byzantine/Islamic nodes (none had dates). Specific events: Nika Revolt 532–532, Justinian 527–565, Arab sieges 632–718, etc.
- **Questions pre-generated**: 89 concept-based questions, 0 failures.

#### Ancient Greece book mapping
- 4 Iggulden novels (Gates of Athens, Protector, The Lion, Falcon of Sparta) + Matyszak "A Year in the Life" mapped to Ancient Greece curriculum via LLM
- 47 knowledge_items created with actual book sources (chapter evidence + temporal hooks)
- 8 additional self-assessment gap items created for nodes not covered by books

#### Roman Republic + other gaps
- Roman Republic: 38 knowledge_items from self-assessment (curriculum already had dates 509 BC–476 AD)
- Ancient Greece: 8 self-assessment gap items filled
- Total: **206 knowledge_items across 5 curricula** (was 24 Sicily-only) → **253 across 6 curricula** by session 41

#### Review queue ordering
- Sort key: `(area_order, date_start, due_at)` — history areas before culture areas, chronological within area
- Result: All 5 curricula interleave historically (~800 BC polis → ~480 BC Persian Wars → ~330 AD Constantinople → ~570 AD Islam)

### Review UX: 10-Card Batches + Continue Button (superseded by session 41 infinite river)
- ~~Session already capped at 10 cards via `getReviewQueue(10)`~~.
- ~~**Done screen**: "✦ Continue · N more due" rubric button when items remain; reloads next batch.~~
- **Replaced in session 41**: Infinite river with no session boundary, skip button on every card, Cards/Voice sub-tabs.

### Article Reading → Review Queue (#9)
- `POST /review/article-read` endpoint: looks up `article_curriculum_nodes` for an article, bumps matching `knowledge_items` due in 1h (if currently far-future).
- Reader `handleDone` fires this fire-and-forget.
- **Effect**: reading an article that covers curriculum topics you don't know well will surface those review cards in your next session.

### Prompt + Code Fixes
- `MAP_CHAPTER_PROMPT`: Examples changed from Sicily-specific to curriculum-agnostic (Themistocles, Byzantine dynasty, Muhammad).
- `QUESTION_GEN_PROMPT_FACTUAL`: "Sicilian history" wording removed; examples now span all curricula.
- Hardcoded `domain_id = ... 'sicily_history_culture_and_legacy'` fallback changed to `or` pattern.
- Review card: now shows curriculum domain in rubric color above chapter title for orientation.

## Session 38: Feed Overview + Web Link Fix (March 27, 2026)

### Web Reader Links Fixed
- **Root cause**: React Native Web's `<Text onPress + href>` calls `preventDefault` on the anchor, then `Linking.openURL`/`window.open()` gets blocked as popup. Also, parent `<Pressable onLongPress>` on paragraphs captured pointer events.
- **Fix**: New `MarkdownLink` component (`app/components/MarkdownLink.tsx`) — web uses native `<a href target="_blank">`, native uses `onPress` + `Linking.openURL`. Paragraph wrappers use `View` on web instead of `Pressable`.
- **Cmd+click**: Opens ingestable links externally on web (skips ingestion)
- **CLAUDE.md**: Documented RNW link gotcha to prevent recurrence

### Feed Overview — Sidebar (Web) + Filter Pills (Mobile)
- **Web**: Grid layout with 180px sticky left sidebar containing topic list (clickable filters with counts), source filters with colored dots, and "Your Research" box showing AI-generated articles with original queries
- **Mobile**: Research section (rubric left border, queries grouped with article titles) + combined topic/source filter pills in one scrollable row above feed
- **Filter pills**: Topic pills (EB Garamond, ink active state) + source pills (DM Sans uppercase, separated by divider) — both filter the feed
- **Data layer** (`store.ts`): `getArticleSourceCategory()` (twitter/newsletter/research/exploration/other), `getResearchArticles()` (grouped by query), `getFeedDistribution()`, `sourceFilter` param added to `getArticlesByLens()`
- **Research queries**: Extracted from `sources[].type` prefix `research:` — e.g. `research:How does compound engineering...`
- **New components**: `FeedFilterPills.tsx`, `FeedSidebar.tsx`, `ResearchSection.tsx`

## Session 36: SQLite Migration — Phases 1–4 (March 22–25, 2026)

### SQLite as Canonical Store
- **`petrarca.db`** at `/opt/petrarca/data/petrarca.db` — stores articles, atomic_claims, knowledge_index, clusters, syntheses alongside existing books/projects/kindle tables
- **Phase 1**: Schema + `db.py` with sync helpers (`sync_articles()`, `sync_knowledge_index()`, `sync_clusters()`, `sync_syntheses()`), each in one transaction
- **Phase 2**: Pipeline scripts (`build_articles.py`, `build_knowledge_index.py`, `build_concept_clusters.py`, `generate_syntheses.py`) dual-write JSON + SQLite
- **Phase 3**: SQLite is canonical — `export_content_json.py` reconstructs served JSON from SQLite, replacing hand-written JSON
- **Phase 4**: 6 `/api/*` endpoints on research-server.py serve directly from SQLite: `manifest`, `articles-meta`, `articles/<id>/content`, `knowledge-index`, `syntheses`, `clusters`

### Client Lazy Content Loading
- **`ArticleMeta`** type (no `content_markdown`/`sections`) used for feed and store — reduces initial payload from 13.6 → 4.7 MB
- **`ArticleContent`** type loaded lazily in reader via `article-content.ts` — in-memory + disk cache, prefetch for offline
- **Fallback**: Client falls back to nginx JSON if API is down

### Bug Fixes
- **Reader content not displaying** (March 25): `fullContent` useMemo in reader.tsx depended only on `article?.id`, which doesn't change when lazy-loaded content arrives. Added `articleContent` to dependency array.
- **Optional JSON fields**: Store NULL when absent in SQLite, skip in export (don't emit `null` keys in JSON)

### Gotchas Documented
- `knowledge_index` claims are derived (topics normalized, only articles with embeddings included)
- Duplicate claim IDs: composite PK `(article_id, id)` in `atomic_claims`
- JSON formatting: `articles.json` uses `indent=2`, `knowledge_index.json` uses compact

### Phase 4c: Pipeline Cleanup (March 25)
- **Removed `export_content_json.py`** from `content-refresh.sh` pipeline cron — SQLite API serves content directly
- Pipeline scripts still dual-write JSON (for nginx fallback compatibility)
- `export_content_json.py` can still be run manually if needed

### Incremental Article Sync (March 25)
- **`content-sync.ts` rewritten** to use manifest-driven smart sync:
  - Fetches manifest first, compares hashes per resource (articles, knowledge_index, clusters, syntheses)
  - **Articles**: if changed and cached data exists, fetches `?since=<last_sync_time>` for only new articles, merges by ID. Falls back to full download on count mismatch.
  - **Knowledge index / clusters / syntheses**: skipped entirely when hash unchanged, loaded from cache
  - **First launch**: still does full download
- **Bandwidth**: typical refresh after 4h cron = manifest (~1 KB) + 0–10 new articles (~20 KB each) vs previous 4.7 MB full article list
- **Logging**: `sync_mode` field in `content_downloaded` event tracks which path was taken (`incremental`, `cached`, `full`, `full_after_mismatch`)

### Next Priorities
- ~~Knowledge model simplification (drop FSRS → binary seen/unseen)~~ — kept FSRS, now exclusively via `review_engine.record_answer()`
- ~~Cross-book review generation with temporal hooks~~ — done (session 40 Hamarquizen cross-book, session 41 Book Review rename)
- Map old books (Kindle → curriculum → Amygdala probes)

## Session 35: Claim Calibration + Article Similarity + Prompt Overhaul (March 21–22, 2026)

### Extraction Prompt Overhaul
- **Both prompts rewritten** in `build_articles.py`: article extraction + atomic claims now prioritize insights, patterns, comparisons over product feature lists
- **Calibration results**: V1 had 31% noise, 17% insight rate. V2: 0% noise, 91% insight rate
- **Model switch**: pipeline tests + defaults → `gemini-3.1-flash-lite-preview` (fastest, cheapest, 5% factual claim rate vs 60% before)
- **All 257 articles backfilled** with new prompt — claims went from 1,473 to 1,045 (fewer but insight-focused), novelty claims 156→368, entities/follow-ups now on 100%

### Article-Level Similarity (amygdala `document_similarity` module)
- **New amygdala module**: `Document`, `find_similar_documents()`, weighted multi-field embeddings
- **Best strategy**: 0.5×summary + 0.5×claims embedding = 94% accuracy, Spearman ρ=0.818 (18 human-rated pairs)
- **Validated**: 300 LLM-rated pairs (AUROC=0.930), 50 synthetic benchmark pairs (ρ=0.895)
- **Calibrated thresholds**: briefing card=0.52 (P=80%, R=78%), feed ranking=0.49, dedup=0.64
- **Integrated**: `build_knowledge_index.py` → `article_similarities` field (6,815 pairs), client `getSimilarArticles()` in knowledge-engine.ts
- **What didn't work**: LLM judge (78%), topic Jaccard (50%), two-stage embed→LLM (no improvement)

### Briefing Card in Reader
- **Verdict line**: "Almost entirely new" / "Extends what you know — N new, M deepening" / "Mostly familiar — N details worth scanning"
- **Similar articles**: top 3 read articles with similarity %, tappable to navigate
- **Skip nudge**: when >70% known, "Read N new claims only →" switches to new_only mode
- **Graceful degradation**: all features return empty when knowledge index not loaded

### Reader UI Additions
- **Follow Topics section**: 2-3 toggleable chips (entity + specific topics) below article, sends interest_chip signals
- **Copy link**: "Copy link" in ⋯ dropdown menu, copies source_url to clipboard

### 9-Agent Research Swarm
- **Datasets**: `scripts/ground-truth/` — 300 LLM-rated pairs, 50 synthetic benchmark, 11 embedding strategies, corpus cluster analysis, two-stage pipeline experiments, threshold config
- **Experiment report**: `scripts/ground-truth/experiment-report.html` — visual report of all experiments
- **Research docs**: `research/auto-research-patterns.md` (Karpathy loop), `research/cross-project-similarity-applications.md` (Petrarca/Alif/Hamarquizen)
- **Amygdala design doc**: `experiments/document_similarity_design.md`

### Corpus Analysis (257 articles)
- 26 natural clusters, 119 singletons (46% don't cluster)
- 70% of articles have 10+ neighbors at threshold 0.47 — briefing card useful for majority
- Sicily dominates overlap (clusters at 0.75-0.88 cohesion); AI/tech articles naturally isolated
- 5-10 near-duplicate pairs identified (>0.90 similarity)

### Otak Integration
- `scripts/dedup_check.py` — pre-ingestion duplicate screening against existing sources
- `scripts/readwise_triage.py` — clusters 11K+ Readwise docs for ingestion prioritization
- `canonical_synthesis.py` — replaced hand-rolled similarity with amygdala's `pairwise_cosine`

### Next Priorities (at time of session 35)
- ~~SQLite migration~~ → Done (session 36, Phases 1–4)
- Atomic claims re-extraction with new prompt (separate from article-level backfill already done)
- Knowledge index rebuild after atomic claims update

## Session 34: Overlapping Curricula + Article-Curriculum Bridge (March 21–22, 2026)

### Curriculum Enrichment (all 3 curricula)
- **Date ranges**: All 192 nodes now have `date_start`/`date_end` fields (negative for BCE)
- **Prerequisite densification**: Sicily 43→101 edges, Greece 59→84, Rome 41→57 (via Sonnet LLM pass)
- **Cross-curriculum entities**: 25 shared entities (Archimedes, Syracuse, Punic Wars, Plato, etc.) with 74 node links and curriculum-specific "lenses"
- **Files**: Enriched JSONs uploaded to `/opt/petrarca/data/curricula/`, `cross_curriculum_entities.json`

### Temporal Hook System
- **Hook generation**: 30 temporal hooks connecting Sicily to Greece/Rome, 4 types: known_anchor, same_moment, causal_chain, surprising_proximity
- **Human calibration**: 29/30 useful, 1 meh, 0 wrong — all hook types work equally well
- **Key finding**: Concrete dates + genuine historical connection + narrative framing = useful. Thematic stretches without factual grounding = meh.
- **Files**: `scripts/hook-calibration.html`, `scripts/hook-calibration-2026-03-22.json`

### Article ↔ Curriculum Bridge
- **`scripts/build_curriculum_embeddings.py`** (new): Embeds 192 curriculum nodes with MiniLM 384d (same model as article claims), maps article claims to curriculum nodes
- **Threshold**: 0.65 cosine (calibrated — 0.70 too strict, 0.45 too noisy)
- **Results**: 769 claim→node links across 98/258 articles and 70/192 curriculum nodes
- **Pipeline integration**: `build_knowledge_index.py` now includes `article_curriculum_nodes` in knowledge_index.json
- **Client**: `getArticleCurriculumNodes()` in knowledge-engine.ts exposes data

### Feed Ranking: Active Book Boost
- Articles matching topics of actively-read books get +0.15 score boost in `getRankedFeedArticles()`
- Topic cache with 60s TTL to avoid re-scanning books per article
- **File**: `app/data/store.ts` — `_getActiveBookTopicBoost()`

### "Connects to Your Reading" Badge
- 📖 badge in ArticleRow margin for articles whose curriculum nodes overlap with active book domains
- `getArticleBookConnections()` in store.ts matches article curriculum domains to book topic keywords
- **File**: `app/components/ArticleRow.tsx`

### Chapter-Complete Trigger
- Selecting a new chapter implies finishing the previous one
- Logs `book_chapter_completed` event with completed/next chapter
- Shows brief green "✦ Finished Ch X" banner (fades after 3s)
- **File**: `app/app/book-detail.tsx` — `handleChapterSelect()`

### Research Documents Created
- `research/overlapping-curricula-vision.md` — Bounded courses model, shared entities with lenses, nexus points
- `research/reading-companion-process-design.md` — 3 interaction moments (chapter complete, cross-book review, map old book), temporal hooks, chapter semantics
- `research/books-articles-connection-proposal.md` — Curriculum as bridge between books and articles, 5-phase plan

### Key Architecture Decisions
- **Curriculum nodes as bridge** between books and articles (not direct claim-to-claim matching — different granularity, different embedding models)
- **Bounded courses > fractal world history** — pedagogical perspective, natural stopping points, cross-references are the richest learning
- **Amygdala-first**: Improve amygdala for probing/mapping rather than building Petrarca-specific code
- **No breadth scan needed for Sicily**: Knowledge starts at zero, book mappings ARE the knowledge state

## Session 32: Reading Flow Fixes + Feed Quality (March 20, 2026)

### Reading Flow
- **Removed PostReadInterestCard** — topic +/- modal after Done was useless friction
- **Auto-advance after Done**: queue → next ranked feed article → back (no more losing scroll position)
- **Bug fix**: pre-compute next article BEFORE `markArticleRead()` (read articles get filtered from feed list)
- **Default reading mode → 'guided'** — known paragraphs dimmed at 0.55 opacity from start

### Feed Quality: Wikipedia Filters
- 146/237 articles were Wikipedia fragments from entity research chunking at H2 boundaries
- **Min word filter**: Wikipedia chunks <500w excluded (36 stubs removed)
- **Per-page cap**: Max 3 per Wikipedia page in feed (29 excess removed)
- **Implementation**: `_capPerSource()` and word count check in `getRankedFeedArticles()` in store.ts

### Research Article Tagging
- `run_ingest()` now passes real source tag to `import_url.py` (was always `--tag manual`)
- **'↗ AI' badge** on ArticleRow for `sources[].type.startsWith('research:')`
- `ArticleSource.type` widened from union literal to `string`

### Race Condition Fix (Critical)
- `build_articles.py` (cron) would overwrite research articles added by concurrent `import_url.py`
- Now acquires `.articles.lock`, re-reads from disk, merges in new articles before final save
- **Root cause of 16/21 lost research articles**

### Related Articles Cleanup
- Connected Reading filters out read articles
- Related Reading excludes read articles + articles already in Connected Reading (fixes duplicate bug)

## Session 30: Reader UX Overhaul + Projects System (March 19, 2026)

### Reader Link Clarity
- **Visual differentiation**: ingestable links show `⊕` suffix (solid underline), external links show `↗` (dashed underline)
- **LinkToast component**: bottom snackbar "Queued: [domain] ✓" with "View Queue" action, auto-dismiss 3s
- **Files**: `reader.tsx` (link rendering), `components/LinkToast.tsx`

### Voice Note Discoverability
- **Always-visible ● icon** in reader toolbar (between star and menu buttons)
- Pulsing red when recording, one tap to start — no menu navigation needed
- **File**: `reader.tsx` (toolbar area)

### Projects System (new feature)
- **Server**: `GET/POST /projects`, `POST /projects/note`, `GET /projects/{id}`, `POST /projects/{id}/update`
- **Data**: `/opt/petrarca/data/projects.json` (projects + notes), `/opt/petrarca/data/projects/` (audio files)
- **Client**: `projects-api.ts`, `ProjectPicker.tsx` (bottom-sheet), `projects.tsx` (list), `project-detail.tsx` (notes + add)
- **Integration**: FeedbackCapture → "Add to project?" after sending, drawer entry

### Voice Routing (auto-classify transcripts)
- `route_voice_input()` in research-server.py — Gemini Flash classifies intent (project_note, research_request, article_feedback, general_note)
- Fuzzy-matches project names, auto-creates project notes when matched
- Background enrichment via daemon threads after feedback/voice note transcription

### Queue Priority in Feed
- Queued articles boosted to top of 'best' feed lens, queue order preserved
- "✦ UP NEXT" section header before queued articles in feed
- ContinueBar falls back to next queued article with "UP NEXT" label when nothing in-progress
- Queue count badge in ✦ drawer

### Bug Fixes
- **Duplicate related articles**: replaced cascading dedup sets with single accumulating `usedIds` set
- **API endpoint mismatches**: fixed client-server contract for projects endpoints (response unwrapping, correct paths)

### Amygdala Migration (completed)
- `build_claim_embeddings.py`: Gemini API → `limbic.amygdala.EmbeddingModel` (local MiniLM)
- `build_knowledge_index.py`: Nomic → single `claim_embeddings.npz`, Gemini judge → `limbic.amygdala.nli_classify_batch`
- `experiment_claim_dedup.py`: manual complete-linkage → `limbic.amygdala.complete_linkage_cluster`

## Session 28: Capture Reliability Fixes (March 16, 2026)

- **Server threading**: Switched from `HTTPServer` to `ThreadingHTTPServer` — each request now gets its own thread. Fixes `ConnectionResetError` when multiple OCR/sync requests queued during rapid photo captures.
- **Photo retry queue**: Failed photo OCR captures now saved to AsyncStorage (`@petrarca/pending_book_photos`) and retried in parallel on screen focus. Mirrors existing voice note retry mechanism.
- **Retroactive queueing**: On focus, book-detail scans existing captures for failed photos with local URIs and auto-queues them for retry.
- **Data recovery**: Manually recovered 1 voice transcript + 1 photo OCR from server-side stored files where the server had completed processing but the client connection had dropped.

## Sessions 20–23 Summary (March 13–16, 2026)

### Session 20: Multi-Stage Synthesis Pipeline
- New `synthesis_pipeline.py` — multi-stage approach (local only, not yet deployed to server)

### Session 21: Physical Book Companion
- Library tab replaces Queue in 2-tab layout (Feed | Library)
- Book tracking: `add-book.tsx`, `book-detail.tsx`, `library.tsx`
- Server: `call_vision()`, book identification, cover lookup (Open Library/Google Books), TOC extraction
- Data: `book-store.ts`, `book-api.ts`, `physical_books.json` on server

### Session 22: Book Research Agent + Cross-Source Matching
- `book_research_agent.py` — Gemini+Search → thesis, chapter claims, key terms, article connections
- `build_book_claim_embeddings.py` — book claims embedded in same space as article claims
- 6 research documents on reading/annotation/knowledge retention
- 8 experiment protocols for book companion features
- Server: `/book/research`, `/book/chapter-insights`, `/book/story-so-far`

### Session 23: Kindle Integration + Media Capture (THIS SESSION)

#### Kindle Library (major feature)
- **Primary source**: Kindle Mac app SQLite (`BookData.sqlite`) — 2,778 books
  - NSKeyedArchiver plist decoding for author metadata (97% coverage)
  - Progress tracking via `ZRAWCURRENTPOSITION/ZRAWMAXPOSITION`
  - Sideloaded (PDOC) vs purchased (EBOK) detection
- **`kindle_sync.py`** — reads local DB, syncs to server. Modes: `--dump`, `--reading`, `--read`, `--resolve-titles`
- **Chrome extension** — 3 Kindle content scripts:
  - `kindle-content.js` — Cloud Reader ASINs from cover image IDs
  - `kindle-notebook.js` — incremental highlight scraping (tracks annotated dates)
  - `kindle-manage.js` — auto-paginates through 883 purchased books
- **Classification** — all 2,776 books classified via Gemini into 6 categories:
  - non-fiction (1,156), genre-fiction (1,097), literary-fiction (254), reference (130), language-learning (74), classical-literature (65)
- **Title resolution** — 349 sideloaded filenames resolved via LLM
- **Gmail attachment downloader** — `gmail_kindle_attachments.py`, 436 book files from `brightkindle@kindle.com`
- **EPUB finder** — `upload_epubs.py`, 190 local EPUBs (539MB)
- **Automation** — launchd plist (4h DB sync, not loaded), chrome.alarms highlight sync **disabled** (was opening kindle website every 12h; manual sync still available)
- **Server endpoints**: `/kindle/sync`, `/kindle/library`, `/kindle/highlights`, `/kindle/curate`, `/kindle/classify`, `/kindle/resolve-titles`, `/kindle/include`

#### YouTube Integration (deployed)
- `youtube-content.js` — "✦ Petrarca" button on YouTube watch pages
- Server: `/ingest-youtube` — fetches transcript via `youtube-transcript-api`, processes through article pipeline
- No API key needed, handles SPA navigation

#### Podcast Integration (partial — metadata only, no knowledge pipeline)

**What exists:**
- `podcast_sync.py` — Overcast export via `overcast-to-sqlite` (uvx). Auth, list podcasts, list played, sync to server. `INCLUDE_PODCASTS` filter (currently empty).
- Server: `POST /media/sync` → appends episodes to `/opt/petrarca/data/media_log.json` (flat JSON, deduped by ID)
- Episode records include: title, source (feed name), overcast URL, enclosure URL, duration

**What's missing to actually ingest episodes (e.g. Rest is History):**
1. **Overcast auth** — need to run `python3 podcast_sync.py --auth` once (interactive login)
2. **Transcript fetching** — `--transcript` flag declared in argparse but not implemented. Options: Whisper on `enclosureUrl` audio, Soniox API (already used for voice elicitation), or podcast RSS transcript tags
3. **Article pipeline integration** — transcripts need to become article records in SQLite so claim extraction, entity linking, curriculum matching, and the reading/review pipeline work on them. YouTube ingest (`/ingest-youtube`) is the model — it does this end-to-end
4. **SQLite storage** — episodes currently go to JSON file, invisible to the knowledge system. Need article records in `petrarca.db`
5. **Episode selection UX** — no way to pick specific episodes from the app; would need CLI or a browse UI

#### Server Data Files Added
- `/opt/petrarca/data/kindle_library.json` — 2,776 books with categories, progress, titles
- `/opt/petrarca/data/kindle_highlights.json` — highlights from notebook
- `/opt/petrarca/data/media_log.json` — YouTube, podcasts, TV consumption log

---

## Pre-Session-20 Status (original document below)
**Status**: Full corpus deployed with knowledge system, reader interactions, voice notes, AI chat, research agents, entity deep-dive, follow-up research, voice note browser + action extraction, activity log tab, scroll-aware encounter tracking, curated novelty card, hierarchical topic feedback, cross-article connections, LLM-verified topic normalization, automatic defragmentation, **unified single-screen feed with lens tabs**, **dynamic reranking**, **✦ drawer navigation**, **clipper auto-save countdown**, **tweet URL ingestion via twikit**, **auto-sync Twitter cookies**, **clipper immediate save via background worker**, **reader disregard + report bad scrape**, **feed ingest metadata**, **floating feedback capture with screenshots + server upload**, **expanded follow-up questions**, **queue auto-advance**, **hybrid topic signals**, **desktop web: 2-column feed grid**, **desktop web: 3-column reader with margin annotations**, **keyboard navigation with multi-key sequences**, **hover actions (archive + dismiss)**, **XML-first article extraction (paragraph merging fix)**, **mobile feed overlap fix**, **reader arrow-key scroll fix**, **LLM judge for ambiguous claims (G2)**, **web layouts for all secondary screens (Topics/Queue/Trails/Landscape/Voice Notes)**, **DoubleRule on all screens**, **drawer quick actions fixed**, **reader date format fix**, **user guide updated + linked from drawer**, **keyboard shortcuts on Queue + Topics screens**, **swipe hint tooltip (mobile)**, **"All topics" pill in feed**, **AnimatedHighlightWrap (reader paragraph highlights)**, **knowledge bar staggered animation**, **DoubleRule in reader**, **reader error boundary**, **cross-article synthesis pipeline (graph clustering → LLM synthesis → claim-level FSRS propagation)**, **26 syntheses with unique labels**, **synthesis reader 3-column web layout + keyboard shortcuts**, **junk article cleanup + pipeline guards**, **Gemini tool calling for structured output**, **"Restrained Folio" synthesis reader redesign (2-col CSS grid, inline chat, article popovers)**, **synthesis prompt overhaul (humanist scholar voice, article reference links, progressive disclosure)**, **feed filtering by synthesis coverage (≥80% excluded, ≥50% demoted)**
**Latest commits**: Session 19 — "Restrained Folio" synthesis reader redesign: complete rewrite of synthesis-reader.tsx (2-column CSS grid with 190px sidebar, Cormorant Garamond + Crimson Pro two-weight typography, local folio color palette, IntersectionObserver TOC tracking, TensionBlock/ExcerptBlock/DetailSection sub-components). New synthesis prompt in generate_syntheses.py (humanist scholar voice, Article Reference Key for `[Title](article:ID)` links, descriptive headings, inline tension blockquotes, progressive disclosure markers, structured tension objects). New components: SynthesisChat.tsx (inline chat modal), ArticlePopover.tsx (web hover popovers for article links). Feed filtering wired: ≥80% synthesis coverage → excluded from feed, ≥50% → score demotion.

---

## What Was Built

On March 8, 2026, the full knowledge-aware reading system was implemented end-to-end based on the design in `research/novelty-system-architecture.md` and validated by 11 experiments documented in `research/experiment-results-report.md`. Subsequently, the full 182-article corpus was restored with claims, embeddings, and knowledge index, and a cost auditing system was added. In session 4, the LLM infrastructure was migrated from litellm to the native `google.genai` SDK (fixing output truncation with newer Gemini models), topic research was rewritten from `claude -p` to Gemini search grounding (reducing latency from 60-120s to ~2.5s), and write contention was fixed with file locking. In session 5, four features were implemented via parallel agents: entity deep-dive (long-press entities in reader), follow-up research prompts (end-of-article questions), voice note browser (new screen), and voice note action extraction (LLM intent extraction from transcripts). In session 6, the Activity Log tab (G7) was implemented: a 4th tab showing a vertical timeline of reading sessions, system/pipeline events, research dispatches, and interest signals. The logger was enhanced with an AsyncStorage-backed offline queue for reliable event delivery, and the pipeline now writes structured JSONL events to the interaction log for server-side aggregation via `GET /activity/feed?days=N` on the research server.

### Architecture Overview

The system splits into **server-computed INDEX** (user-independent) and **client-side LEDGER** (user-specific):

```
Server Pipeline (cron every 4 hours):
  Twitter + Readwise → build_articles.py --claims → atomic claims + entities + follow-up questions
  → cleanup_articles.py → remove junk/duplicates
  → build_claim_embeddings.py → Gemini embedding-001 (batch 100)
  → build_knowledge_index.py → knowledge_index.json (parallel delta reports, 10 workers)
  → build_concept_clusters.py → graph clustering + two-pass contrastive labeling
  → generate_syntheses.py → structured synthesis per cluster (Gemini 3 Flash + tool calling)
  → All LLM calls via gemini_llm.py (google.genai SDK, call_llm/call_llm_tool)
  → All calls tracked by llm_audit.py → data/llm_audit.jsonl
  → research-server.py: ThreadingHTTPServer (concurrent request handling)

App (Expo SDK 54):
  content-sync.ts downloads knowledge_index.json + concept_clusters.json + syntheses.json
  → knowledge-engine.ts classifies claims against user's ledger
  → paragraph dimming, curiosity scoring, delta reports
  → synthesis-reader.tsx: read synthesis → markClaimsEncountered() → all source claims get FSRS entries
  → AsyncStorage persists knowledge ledger (@petrarca/knowledge_ledger)
  → All interactions logged via logger.ts → local + server (port 8091)
```

### Files Created/Modified

#### New Files

| File | Description |
|------|-------------|
| `app/data/knowledge-engine.ts` | Core knowledge engine — FSRS decay, claim classification, paragraph dimming, curiosity scoring, knowledge ledger persistence. Module-level state (singleton). |
| `app/data/queue.ts` | Reading queue with AsyncStorage persistence. Add/remove/list queued article IDs. |
| `app/app/(tabs)/topics.tsx` | Topics screen — articles grouped by broad topic, expandable clusters with delta report summaries and top claims. |
| `app/app/(tabs)/queue.tsx` | Queue screen — saved-for-later articles with swipe-to-remove. |
| `scripts/build_knowledge_index.py` | Server pipeline — loads articles + embeddings, computes cosine similarity matrix, extracts cross-article pairs, builds paragraph mappings, generates LLM delta reports (parallel, 10 workers). Outputs `data/knowledge_index.json`. |
| `scripts/deploy_knowledge_index.sh` | Deploys knowledge_index.json to nginx + updates manifest hash. Supports `--local` mode. |
| `scripts/llm_audit.py` | Thread-safe JSONL audit trail for all LLM calls. Tracks tokens, cost, cache hits per-call. CLI: `python3 scripts/llm_audit.py --days 7`. |
| `scripts/log_server.py` | HTTP server (port 8091) for collecting app interaction logs. Accepts POST /log with JSONL body, stores as daily files in `/opt/petrarca/data/logs/`. |
| `app/data/bookmarks.ts` | Article bookmarking with AsyncStorage persistence. Toggle, query, list bookmarked IDs. |
| `app/components/AskAI.tsx` | Bottom-sheet AI chat modal. Conversation threading, Gemini Flash via `/chat` server endpoint. Article context (title, summary, claims, topics, truncated text) passed as context. |
| `app/components/VoiceFeedback.tsx` | Compact voice note recording bar. Records audio via expo-av, uploads to server `/note` endpoint for async Soniox transcription. Auto-closes on send. |
| `app/lib/chat-api.ts` | API client for research server: `askAI()`, `uploadVoiceNote()`, `spawnTopicResearch()`, `fetchNotes()`, `ingestUrl()`, `getIngestStatus()`, `reportBadScrape()`. |
| `app/public/guide/index.html` | HTML user guide (Annotated Folio styled). Covers all 5 capture flows, 3 tabs, reader modes, knowledge system, usage patterns. Linked from Feed header. |
| `research/user-guide.md` | Markdown source for user guide. Describes all implemented features accurately. |
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). Functions: `call_llm()`, `call_chat()`, `call_with_search()`, `call_llm_tool()` (forced function calling). Default model: `gemini-3.1-flash-lite-preview` (via `PETRARCA_LLM_MODEL` env var). |
| `app/app/voice-notes.tsx` | Voice notes browser screen. Global notes view with date-grouped sections, ✦ markers, Cormorant Garamond header. Accessible from Feed header "Notes" link. |
| `app/components/VoiceNoteCard.tsx` | Reusable voice note card component. Shows timestamp, duration badge, transcript (3-line max), article link, action chips with type-colored borders. |
| `app/lib/voice-notes-api.ts` | Voice notes API module. `fetchAllNotes()`, `fetchArticleNotes()`, `executeNoteAction()`. TypeScript interfaces for `VoiceNote` and `NoteAction`. |

#### New Files (Session 6: Activity Log)

| File | Description |
|------|-------------|
| `app/app/(tabs)/log.tsx` | Activity Log tab — vertical timeline with reading/system/research/interest nodes. Filter toggles (All/Reading/System/Research). Paged fetch: loads last day first, then 7 days in background. Colored dots per event type, ✦ markers for interest signals, day separators. |

#### New Files (Session 17: Cross-Article Synthesis Pipeline)

| File | Description |
|------|-------------|
| `scripts/build_concept_clusters.py` | Graph-based article clustering from novelty matrix. Connected components → spectral bisection for large clusters → two-pass LLM labeling (specificity prompt + contrastive refinement for collisions). Outputs `data/concept_clusters.json`. |
| `scripts/generate_syntheses.py` | Complete rewrite. Structured synthesis per cluster via Gemini 3 Flash + tool calling (`call_llm_tool()`). Narrative + shared themes + unique contributions + tensions + follow-up questions + claim coverage map. Claim coverage expansion: article_coverage ≥ 0.6 → include all claims, then similarity cascade ≥ 0.78. Incremental (skips unchanged). |
| `scripts/cleanup_articles.py` | Detects/removes X.com JS error pages, duplicates, short junk. Conservative defaults (--report is dry-run). |
| `scripts/compare_synthesis_models.py` | Model comparison framework for synthesis generation. Tests multiple Gemini models across cluster subsets. |
| `research/synthesis-pipeline-design.md` | Full design doc: investigation findings, architecture, model comparison, prompt iteration, decisions. |

#### New Files (Session 19: "Restrained Folio" Synthesis Reader Redesign)

| File | Description |
|------|-------------|
| `app/components/SynthesisChat.tsx` | Inline chat modal for synthesis discussions. Context builder from synthesis data (title, narrative, tensions, article titles). Auto-sends initial question. Restrained Folio styling (Crimson Pro body, folio color palette). 307 lines. |
| `app/components/ArticlePopover.tsx` | Web-only hover popover for `article:ID` reference links. Smart edge-flipping positioning (flips left/right based on viewport edge). Shows article title, summary, topics, coverage bar. Quick actions: Queue / Seen / Disregard. 194 lines. |

#### Modified Files (Session 19: "Restrained Folio" Synthesis Reader Redesign)

| File | Changes |
|------|---------|
| `scripts/generate_syntheses.py` | Major prompt overhaul: "humanist scholar" system instruction (was "expert research synthesizer"). Article Reference Key section in prompt — ID→title lookup so LLM writes proper `[Title](article:ID)` links. Descriptive `##` headings instead of prescribed structure. Inline `> ⚡ **Tension label**` blockquotes for tensions. Inline `*Open question: ...*` research prompts. `<!-- detail -->` / `<!-- /detail -->` progressive disclosure markers. Structured tensions changed from `string[]` to `Array<{label, description, article_ids}>`. Tool schema updated. max_tokens 8192→12288. Tension normalization in post-processing (handles both old string and new object formats). |
| `app/app/synthesis-reader.tsx` | Complete "Restrained Folio" rewrite. 2-column CSS grid (1fr + 190px sidebar) on web, single column on mobile. Two visual weights only: Cormorant Garamond 30px title + Crimson Pro everything else. Local folio color palette (`fc` constant) replacing design token colors. New sub-components: SynthesisTopBar, enhanced MarkdownContent (renders article links, tension blocks, excerpt blocks, detail sections), TensionBlock (amber border), ExcerptBlock (green border), DetailSection (collapsible), SynthesisSidebar with IntersectionObserver TOC tracking. No uppercase letterspaced labels. |
| `app/data/store.ts` | Feed filtering wired: `getArticleSynthesisCoverage()` integrated into `getRankedFeedArticles()` and `getArticlesByLens()`. Articles with ≥80% synthesis coverage excluded from feed. Articles with ≥50% coverage get score demotion `(1 - coverage * 0.5)`. |
| `app/data/types.ts` | `tensions` type broadened from `string[]` to `Array<string \| { label, description, article_ids? }>` for backward compatibility with old string format. |

#### Modified Files (Session 17: Synthesis Pipeline + Reader)

| File | Changes |
|------|---------|
| `scripts/build_articles.py` | Added `_validate_content()` — rejects junk (empty, JS error pages, too short) before LLM processing. |
| `scripts/gemini_llm.py` | Added `call_llm_tool()` for forced function calling with FunctionDeclaration (`mode='ANY'`). Structured output without JSON parsing. |
| `scripts/content-refresh.sh` | Added steps 3b2 (cleanup), 4b (clustering), 4c (synthesis generation), 4d (manifest hash update for clusters + syntheses). |
| `app/data/types.ts` | Expanded `TopicSynthesis` with cluster_id, claims_covered, article_coverage, follow_up_questions, tensions. Added `SynthesisFollowUpQuestion`. |
| `app/data/content-sync.ts` | Downloads concept_clusters.json + syntheses.json alongside articles. |
| `app/data/store.ts` | Module-level syntheses/clusters, getters (getSynthesisForCluster, getSynthesesForArticle, getArticleSynthesisCoverage), completedSyntheses set with AsyncStorage. |
| `app/data/knowledge-engine.ts` | Added `markClaimsEncountered()` for bulk claim encounter tracking from synthesis reader. |
| `app/app/synthesis-reader.tsx` | Complete rewrite: 3-column CSS Grid web layout (220px/1fr/240px matching article reader). Left margin: metadata, claim coverage bar, actions, keyboard shortcuts. Right margin: source articles with per-article coverage bars, follow-up research questions. Keyboard: Escape/d/gi. Browser-native scroll fix. Mobile: single-column with coverage bars. |
| `app/app/_layout.tsx` | Added synthesis-reader route. |
| `app/app/(tabs)/topics.tsx` | Added SynthesisCard component linking to synthesis-reader. |
| `app/app/(tabs)/index.tsx` | Added synthesis coverage indicator in feed article cards. |

#### New Files (Session 9: Unified Feed Redesign)

| File | Description |
|------|-------------|
| `app/components/DoubleRule.tsx` | Reusable double rule separator (2px + 5px gap + 1px ink lines) using layout tokens. |
| `app/components/LensTabs.tsx` | Horizontal tab switcher for Latest/Best/Topics/Quick lenses. EB Garamond 13px, rubric underline active indicator, logs `lens_switch`. |
| `app/components/UpNextSection.tsx` | Pinned top section: shows in-progress article (with progress bar), next queued, or algorithmic pick. Contains ✦ drawer trigger button. Logs `up_next_tap` with type. |
| `app/components/RecommendedSection.tsx` | Hero card for algorithmically top-ranked article. Cormorant Garamond 20px title, claim preview (green left border), novelty badge, "See all" link. Logs `recommended_tap`. |
| `app/components/TopicPillsSection.tsx` | Horizontal scroll of topic pills from `getArticlesGroupedByTopic()`. First pill gets ink (dark) treatment. Logs `topic_pill_tap`. |
| `app/components/TopicsGroupedList.tsx` | Articles grouped by topic with tree-line indentation. Expand/collapse (shows 3, "+N more" to expand). Optional `topicFilter` prop. Logs `topic_group_article_tap`. |
| `app/components/PetrarcaDrawer.tsx` | Bottom sheet (ink background). Quick actions: Triage, Voice Note. Nav items: Voice Notes, Activity Log, Reading Progress, Queue. Logs `drawer_open/close`, `drawer_item_tap`. |
| `research/feed-redesign-plan.md` | Comprehensive plan: 3 rounds of mockup feedback, approved architecture, screen layout, 5-phase implementation order, component specs. |

#### Modified Files (Session 14: Parsing Fix + Mobile Feed Overlap)

| File | Changes |
|------|---------|
| `scripts/build_articles.py` | XML-first extraction: `_xml_to_markdown()` converts trafilatura XML preserving `<p>` boundaries with link/bold/italic handling. `_split_long_paragraphs()` splits prose >200w at sentence boundaries (Latin/Greek/Cyrillic). Tweet text `\n`→`\n\n` normalization in bookmark processing. `fetch_method` now persisted in article JSON. `from xml.etree import ElementTree` added. |
| `scripts/clean_existing_articles.py` | Auto-detects server (`/opt/petrarca/data/`) vs local path. `count_issues()` now reports `long_paragraphs` count. |
| `scripts/research-server.py` | Tweet paragraph normalization in `run_ingest_tweet()`: single `\n` → `\n\n` for non-threaded tweets. |
| `app/app/(tabs)/index.tsx` | Mobile feed overlap fix: header moved from `ListHeaderComponent` into data array as `data[0]`, `stickyHeaderIndices` [0]→[1], `onViewableItemsChanged`/`viewabilityConfig` stabilized via `useRef`, `removeClippedSubviews={false}`, `scrollToIndex` offset +1→+2. |
| `app/app/reader.tsx` | Arrow-key scroll fix: override `body { overflow: auto }` on mount (React Native Web sets `hidden`). Inject `outline: none` on `div:focus, body:focus`. Top bar: `top: 0` + `paddingTop: 4`. |

#### Modified Files (Session 12: Desktop Web Layouts)

| File | Changes |
|------|---------|
| `app/app/(tabs)/index.tsx` | Web layout: ScrollView replaces FlatList, CSS Grid 2-column article grid (1100px max), hover ✓ (archive) and ✕ (dismiss) buttons on cards, Up Next auto-focused on web (focusedIndex=-1), hero articles (Up Next + Recommended) excluded from grid, `gi` multi-key shortcut, `webArticles`/`effectiveFocusedArticleId` for filtered keyboard nav. |
| `app/app/reader.tsx` | Web: browser-native scroll (View replaces ScrollView in center column), `window.scroll` listener for progress tracking. 3-column CSS Grid: left margin (metadata, novelty, mode toggle, actions, full shortcut list), right margin (up next, connected, follow-up, related). Top bar: prev/next article links. `gi` shortcut. Container removes `flex:1` on web. |
| `app/hooks/useKeyboardShortcuts.ts` | Multi-key sequence support: buffers prefix key for 500ms, matches 2-char sequences (e.g. "gi"). Falls back to standalone handler if no second key. |
| `app/components/UpNextSection.tsx` | Added `isFocused` prop with rubric left border + subtle background visual indicator. |
| `app/components/LensTabs.tsx` | Changed maxWidth from `contentMaxWidth` to `webFeedMaxWidth` (1100px). |
| `app/components/KeyboardHintBar.tsx` | Changed inner maxWidth from 680 to 1100px. |
| `app/design/tokens/spacing.ts` | Added web layout tokens: `webFeedMaxWidth` (1100), `webReaderMaxWidth` (1120), `webReaderLeftMargin` (190), `webReaderRightMargin` (210), `sidebarNavWidth` (220), `contentMaxWidth` (960). |

#### New Files (Session 11b: Feedback Capture + More Questions + Auto-Advance + Topic Signals)

| File | Description |
|------|-------------|
| `app/components/FeedbackCapture.tsx` | Floating ✦ feedback button (bottom-right). Tap captures screenshot (react-native-view-shot) + opens voice/text overlay with auto-detected context (screen, article, lens, reading state). Uploads screenshot (PNG) + audio (m4a) + text + context JSON to `POST /feedback`. Falls back to local AsyncStorage. Long-press hides (persisted). Events: `feedback_capture_start/complete/dismiss`. |
| `app/lib/feedback-context.ts` | Module-level feedback context store. `setFeedbackContext()` merges partial updates, `getFeedbackContext()` returns snapshot. Screens call `setFeedbackContext()` on mount/state change to propagate current screen, article ID/title, active lens, reading mode, scroll progress. |

#### Modified Files (Session 11b: Feedback Capture + More Questions + Auto-Advance + Topic Signals)

| File | Changes |
|------|---------|
| `app/app/_layout.tsx` | Added `FeedbackCapture` component (global floating button). |
| `app/app/(tabs)/index.tsx` | Redesigned topic interest signals: `isTopicNew()` function, `KnownTopicDot` component (tap-to-cycle), new topics get left-bordered +/− rows, known topics get compact dot-list. Removed old `TopicLevelRow` and chip styles. Added `getInterestProfile` import. |
| `app/app/reader.tsx` | "More questions" button in FURTHER INQUIRY with pulsing ✦ animation. Queue auto-advance: `advanceOrGoBack()` replaces `router.back()`, "UP NEXT" toast with escape button. Topic signal redesign matching index.tsx changes. |
| `app/lib/chat-api.ts` | Added `generateMoreQuestions()`, `uploadFeedback()` (multipart FormData with web data-URI→Blob conversion for screenshots). |
| `app/components/KeyboardHintBar.tsx` | Modified (minor). |
| `app/components/LensTabs.tsx` | Modified (minor). |
| `scripts/build_articles.py` | Extraction prompt generates 4 follow-up questions (was 2-3), with broader/more divergent framing. |
| `scripts/research-server.py` | New `POST /generate-questions` endpoint. New `POST /feedback` endpoint — accepts multipart/form-data (screenshot PNG, audio m4a, text, context JSON), saves to `/opt/petrarca/data/feedback/`, background Soniox transcription for audio. |

#### Modified Files (Session 11: Clipper Immediate Save + Reader Actions + Feed Metadata)

| File | Changes |
|------|---------|
| `clipper/popup.js` | Save moved to background worker via `fireImmediateSave()`. `doSave()` simplified to send note (if any) and show saved state. Cancel/Escape send `cancelSave` message. |
| `clipper/popup.html` | PETRARCA wordmark changed to clickable `<a>` with `id="open-app"`. |
| `clipper/popup.css` | Wordmark hover style (opacity 0.7 transition). |
| `clipper/background.js` | Added `addNote` → `POST /ingest-note`, `cancelSave` → `POST /ingest-cancel` handlers. `saveClip` gets offline fallback via `storeLocally()`. |
| `app/app/(tabs)/index.tsx` | Added `formatRelativeDate()` (minute/hour/day precision from ISO timestamps), `formatSourceLabel()` (maps source types to display labels). `ArticleCard` gets `showIngestInfo` prop, shown only on Latest lens. |
| `app/app/reader.tsx` | Added "Report bad scrape" menu item (`reportBadScrape()` → `/report-scrape`). Added "Disregard" menu item (dismiss + navigate back). Imported `dismissArticle` from store. |
| `app/lib/chat-api.ts` | Added `reportBadScrape()` function. |
| `app/data/types.ts` | Added `ingested_at?: string` to Article interface. |
| `scripts/import_url.py` | Added `ingested_at` ISO timestamp to article dict. |
| `scripts/build_articles.py` | Added `ingested_at` ISO timestamp to article dict. |
| `scripts/research-server.py` | Added `SCRAPE_REPORTS_PATH`. New endpoints: `POST /ingest-note` (sidecar write), `POST /ingest-cancel` (remove from articles.json), `POST /report-scrape` (append to scrape queue), `GET /scrape-reports` (list pending). |

#### Modified Files (Session 10: Clipper + Tweet Ingestion)

| File | Changes |
|------|---------|
| `clipper/popup.html` | Header gets countdown number + timer overlays on double rule. Note field always visible (dashed placeholder). Note toggle button removed. Cancel button added. |
| `clipper/popup.css` | Timer overlay animation (rubric drains to gray), countdown number (Cormorant 22px), dashed→solid note field transition on focus, Cancel button, gold completion flash (#c9a84c). |
| `clipper/popup.js` | Complete rewrite of save flow. 10s countdown via `requestAnimationFrame` (smooth pause/resume). States: counting → paused (on typing) → saving → saved. Auto-save at 0, Cancel button + Esc. |
| `clipper/manifest.json` | Added `cookies` permission + `host_permissions` for `*.x.com` and `*.twitter.com`. |
| `clipper/background.js` | Added `maybeSyncTwitterCookies()`: extracts `auth_token` + `ct0` via `chrome.cookies.get()` on X.com visits, POSTs to `/twitter/cookies`. Throttled to 4h via `chrome.storage.local` timestamp. `tabs.onUpdated` listener triggers on page load complete. |
| `scripts/research-server.py` | Added tweet URL detection (`_is_tweet_url`), `run_ingest_tweet()` (twikit fetch → thread reconstruction → URL extraction → normal pipeline), `_fetch_tweet_via_twikit()` (async), `_check_twikit_cookies()`. New endpoints: `GET /twitter/status`, `POST /twitter/cookies`. `/ingest` now routes tweet URLs through twikit. |

#### Modified Files (Session 9: Unified Feed Redesign)

| File | Changes |
|------|---------|
| `app/app/(tabs)/index.tsx` | Complete rewrite. Single FlatList with ListHeaderComponent (UpNext → Recommended → Topics → DoubleRule). Lens tabs as sticky `data[0]` via `stickyHeaderIndices={[0]}`. Articles sorted/grouped by active lens. Swipe dismiss/queue preserved. `useFocusEffect` triggers rerank on return from reader. No header chrome (no app name, no date). ~320 lines (was 728). |
| `app/app/(tabs)/_layout.tsx` | Tab bar hidden (`display: 'none'`). Topics/Queue/Log routes preserved with `href: null` for drawer navigation access. ~40 lines (was 82). |
| `app/data/store.ts` | Added `FeedLens` type, `getTopRecommendedArticle()` (highest-scored not in queue/in-progress), `getArticlesByLens()` (filters+sorts by lens), `getArticlesGroupedByTopic()` (groups by broad topic), `getInProgressArticles()`, `getFeedVersion()`/`bumpFeedVersion()` (reactive counter). Integrated `isKnowledgeReady()` + `_getArticleNovelty()` into `getRankedFeedArticles()`: blended score = interest (60%) + curiosity (40%). Quick lens also uses blended scoring. |
| `app/data/queue.ts` | Added `getNextQueued()` (front of queue without removing), `peekQueue(n)` (first N items). |
| `research/README.md` | Added UX Redesign section linking to `feed-redesign-plan.md`. |
| `research/experiment-log.md` | Session 9 entry: design exploration (3 rounds), user interview findings, implementation details, 8 hypotheses to validate, events logged. |

#### New Files (Session 8: Swarm Build + Topic Normalization)

| File | Description |
|------|-------------|
| `app/components/RelatedArticles.tsx` | Related articles component at bottom of reader. Three relationship finders (same topic, shared concepts via knowledge index, same source). Deduped, max 3 per group. Design system tokens. |

#### New Files (Session 8: Topic Hierarchy + Cross-Article + Normalization)

| File | Description |
|------|-------------|
| `scripts/topic_registry.json` | Canonical topic registry — 12 broad categories, 21 specific topics, each with include/exclude descriptions for LLM disambiguation. Hard limits: `max_broad: 25`, `max_specific_per_broad: 15`. Inspired by Otak's `tree_balance.py` approach but avoids its unbounded growth. |
| `scripts/topic_normalizer.py` | Topic normalization + defragmentation. `normalize_article_topics()` validates against registry via LLM merge-or-create. `defragment_registry()` consolidates overpopulated categories. `registry_needs_defrag()` checks if limits exceeded. |

#### Modified Files (Session 8: Topic Hierarchy + Cross-Article + Normalization)

| File | Changes |
|------|---------|
| `app/app/reader.tsx` | Redesigned `PostReadInterestCard` with hierarchical topic display: `TopicGroup` interface, `groupTopicsByBroad()`, `TopicLevelRow` with tree lines + level badges (broad/topic/entity), smart expand (≤2 broad → expanded). Added `ConnectedReadingSection` (bottom section: shared claim counts, read status, queue buttons). Added `InlineCrossArticleAnnotation` (inline "Also in: [title]" below paragraphs). ~400 lines added. |
| `app/data/interest-model.ts` | Added `recordTopicSignalAtLevel()` — signals at exactly one hierarchy level without cascading. Updated `computeInterestMatch()` to include entity-level scores via `Math.max(specificScore, broadScore * 0.7, entityScore)`. |
| `app/data/queue.ts` | Added `addToQueueFront()` — LIFO queue insertion for cross-article connections (user wants "next article I see would be this one"). |
| `app/data/knowledge-engine.ts` | Added `CrossArticleConnection` interface and two new functions: `getCrossArticleConnections()` (groups similar claims by article, max 5 results), `getParagraphConnections()` (maps paragraph indices to connected articles via claim-to-paragraph mapping from knowledge index). |
| `app/data/store.ts` | Added export wrappers: `recordTopicInterestSignalAtLevel()`, `getCrossArticleConnections()`, `getParagraphConnections()`. |
| `scripts/build_articles.py` | Integrated topic normalizer: loads registry once, normalizes each article's `interest_topics` via `normalize_interest_topics()`. Added `_get_topic_hint()` — injects existing categories into LLM extraction prompt. Added `--normalize-topics` for batch re-normalization, `--defrag-topics` for automatic defragmentation. Extended `--enrich` to also backfill `interest_topics`. |
| `scripts/content-refresh.sh` | Added step 3c3: automatic topic defragmentation check after article processing. |

#### Modified Files (Session 6: Activity Log)

| File | Changes |
|------|---------|
| `app/data/logger.ts` | Added AsyncStorage-backed offline queue (`savePendingPayload`, `flushPendingLogs`). Failed server sends are persisted and retried on session start + piggybacked on successful flushes. |
| `app/app/(tabs)/_layout.tsx` | Added 4th "Log" tab to tab bar. |
| `app/design/tokens/colors.ts` | Added `research: '#6a3a8a'` color token for research event dots. |
| `scripts/research-server.py` | Added `GET /activity/feed?days=N` endpoint. Aggregates interaction logs, pipeline events, and research results into grouped timeline nodes (reading sessions, interest signals within 60s, pipeline runs within 15min). |
| `scripts/content-refresh.sh` | Added `pipeline_log()` function writing structured JSONL to interaction log dir. Logs pipeline_start, each major step, and pipeline_complete with elapsed time. |

#### Modified Files (Session 4+5: LLM migration + four features)

| File | Changes |
|------|---------|
| `scripts/build_articles.py` | Migrated from litellm to `gemini_llm.call_llm()`. Added `_locked_append_article()` with `fcntl.flock` for write contention safety. Extended prompt schema with `entities[]` and `follow_up_questions[]`. Fixed `normalize_topic()` to handle dict inputs. |
| `scripts/research-server.py` | Migrated chat from litellm to `gemini_llm.call_chat()`. Rewrote topic research from `claude -p` to `gemini_llm.call_with_search()` (Gemini search grounding). Added `extract_note_actions()` for LLM intent extraction from transcripts. Added `POST /notes/{note_id}/execute-action` endpoint. `/ingest` now returns `ingest_id` + deterministic `article_id`. Added `GET /ingest-status?id=` for polling. |
| `scripts/import_url.py` | Added import of `_locked_append_article` from `build_articles` for concurrent write safety. |
| `app/data/types.ts` | Added `ArticleEntity` interface (7 entity types), `FollowUpQuestion` interface, extended `Article` with `entities?` and `follow_up_questions?`. |
| `app/app/reader.tsx` | Added `EntityHighlightText` (dotted underline on entity mentions, long-press popup), `EntityPopup` (inline marginalia card with entity info + "Research more"), `FollowUpSection` ("✦ FURTHER INQUIRY" section after article with tappable research questions). ~320 lines added. |
| `app/app/(tabs)/index.tsx` | Added "Notes" link in feed header navigating to `/voice-notes`. |
| `app/app/_layout.tsx` | Added `voice-notes` screen to Stack navigator. |

#### Modified Files (Mar 8 session 2)

| File | Changes |
|------|---------|
| `app/app/reader.tsx` | Added ⋯ menu (article info, source, Ask AI, voice note, research topic), ☆ bookmark toggle, AI chat modal, voice feedback panel. `buildAIChatContext()` builds article context string for LLM. |
| `app/app/(tabs)/index.tsx` | Guide link in header, topic normalization for filter chips and tags, `minHeight: 44` on filter scroll. |
| `app/app/(tabs)/topics.tsx` | "↗ Find more on [Topic]" research button in expanded topic clusters. Topic normalization for grouping/display. |
| `app/data/interest-model.ts` | Added `bookmark_add` (weight 1.5) and `bookmark_remove` (weight 0.5) signal types. |
| `app/data/store.ts` | Loads bookmarks on init alongside queue. |
| `app/lib/display-utils.ts` | Added `normalizeTopic()` and `displayTopic()` shared utilities. |
| `scripts/research-server.py` | Added `/chat` (Gemini Flash chat), `/note` (audio upload + Soniox transcription), `/research/topic` (claude -p topic research + auto-ingest), `/notes` GET. |

#### Modified Files (original build)

| File | Changes |
|------|---------|
| `app/data/types.ts` | Added 9 types: `KnowledgeIndex`, `DeltaReport`, `NoveltyClassification`, `ClaimKnowledgeEntry`, `ClaimClassification`, `ParagraphDimming`, `ArticleNovelty` |
| `app/data/content-sync.ts` | Downloads `knowledge_index.json` alongside articles. Added `KNOWLEDGE_INDEX_URL`, `knowledge_index_hash` to manifest checking, graceful fallback if index doesn't exist. |
| `app/data/store.ts` | Imports and initializes knowledge engine + queue in `initStore()`. Exports wrapper functions. Added bundled fallback `require('./knowledge_index.json')`. |
| `app/app/reader.tsx` | 3 reading modes (Full/Guided/New Only), paragraph dimming via `blockDimming` map, collapsible familiar sections (`CollapsedBar` component), "What's new for you" claims card, `ReadingModeToggle` component, `buildParagraphToBlockMap()` for mapping pipeline paragraph indices to markdown block indices. Calls `markArticleEncountered()` on Done. |
| `app/app/(tabs)/index.tsx` | Curiosity-zone re-ranking (with 0.05 threshold for stability), topic filter chips (horizontal ScrollView), swipe-right-to-queue, novelty hints ("N new claims"), `ContinueReadingCard` component (limited to 2 most recent). Interaction logging for swipe-dismiss and swipe-queue. |
| `app/app/(tabs)/_layout.tsx` | Originally 3-tab layout → expanded to 4 tabs (session 6) → **session 9: tab bar hidden, single screen with drawer**. Routes preserved via `href: null`. |
| `app/data/logger.ts` | Dual-write logging: local (localStorage/filesystem) + server buffer (batched POST to port 8091 every 5s). AsyncStorage-backed offline queue retries failed sends on session start. |
| `scripts/content-refresh.sh` | Full 6-step pipeline: fetch sources → build articles → validate → extract entities → extract claims → embed claims → build knowledge index → copy to nginx. Writes structured JSONL pipeline events to interaction log for activity feed. |

### Data Generated

| File | Size | Contents |
|------|------|----------|
| `data/articles.json` | ~7 MB | 237 articles with `atomic_claims[]`, `entities[]`, `follow_up_questions[]` (36 junk removed) |
| `data/claim_embeddings.npz` | ~50 MB | 4,831 Gemini embedding-001 vectors |
| `data/knowledge_index.json` | ~8 MB | 4,831 claims, cross-article similarity pairs (≥0.68), article paragraph maps, article novelty matrix, LLM delta reports |
| `data/concept_clusters.json` | 214 KB | 29 clusters from graph-based article clustering, unique contrastive labels |
| `data/syntheses.json` | 350 KB | 26 structured syntheses (narrative + themes + tensions + follow-up questions + claim coverage maps) |
| `data/llm_audit.jsonl` | ~100 KB | Per-call LLM usage records (tokens, cost, model, purpose) |

### Algorithm Parameters (validated by experiments)

| Parameter | Value | Source |
|-----------|-------|--------|
| KNOWN threshold | ≥ 0.78 cosine | Nomic calibration experiment |
| EXTENDS threshold | ≥ 0.68 cosine | Nomic calibration experiment |
| FORGOTTEN threshold | R < 0.3 | FSRS standard |
| Stability (skim) | 9 days | FSRS experiment |
| Stability (read) | 30 days | FSRS experiment |
| Stability (highlight) | 60 days | FSRS experiment |
| Reinforcement factor | 2.5× | FSRS standard |
| Curiosity peak | 70% novelty | Curiosity zone experiment |
| Curiosity Gaussian σ | 0.15 | Curiosity zone experiment |
| Similarity index threshold | ≥ 0.68 | Pairs below this are always NEW |
| Feed re-rank threshold | 0.05 | Prevents unstable sorts when scores are close |

---

## Deployment Status

### Server (Hetzner: alifstian.duckdns.org)

| Component | Status | Notes |
|-----------|--------|-------|
| nginx content server (:8083) | ✅ Working | Serves articles.json, knowledge_index.json, manifest.json |
| Static web app (:8084) | ✅ Deployed | Session 19: "Restrained Folio" synthesis reader, inline chat, article popovers, feed filtering |
| Expo native (:8082) | ✅ Running | systemd `petrarca-expo` |
| Log server (:8091) | ✅ Running | systemd `petrarca-log`, collects app interaction logs |
| articles.json | ✅ 182 articles | Full corpus with atomic claims, entities, follow-up questions |
| knowledge_index.json | ✅ 4.3MB | 300 delta reports, novelty matrix, paragraph maps |
| claim_embeddings.npz | ✅ 33MB | Gemini embedding-001, 2,954 vectors |
| manifest.json | ✅ Updated | `articles_hash` + `knowledge_index_hash` |
| llm_audit.jsonl | ✅ Collecting | 330 records from pipeline run ($0.035 total) |
| Python deps | ✅ All installed | numpy, google-genai (native SDK) in `/opt/petrarca/.venv` |
| Cron pipeline | ✅ Working | `content-refresh.sh` runs full pipeline including claims + embeddings + knowledge index |
| GEMINI_KEY | ✅ Configured | In `/opt/petrarca/.env` (used by `gemini_llm.py`, also `GEMINI_API_KEY` alias) |
| Voice notes storage | ✅ Working | `/opt/petrarca/data/notes/` (JSON) + `/opt/petrarca/data/audio/` (m4a) |
| Chat conversations | ✅ Working | `/opt/petrarca/data/chats/` (JSON, per conversation_id) |
| Research server endpoints | ✅ Updated | `/chat`, `/note`, `/research/topic`, `/notes`, `/notes/{id}/execute-action`, `/research`, `/research/results`, `/twitter/status`, `/twitter/cookies`, `/ingest-note`, `/ingest-cancel`, `/report-scrape`, `/scrape-reports`, `/generate-questions`, `/review/microlearning` on port 8090 |
| Scrape reports queue | ✅ Working | `/opt/petrarca/data/scrape_reports.json` — user-reported bad scrapes, `GET /scrape-reports` lists pending. **Review periodically** to identify scraping failure patterns and strengthen the pipeline (e.g. site-specific extractors, better fallback logic). |

### SSH Access
- Use `ssh alif` (configured in `~/.ssh/config` → `root@46.225.75.29` via `~/.ssh/hetzner_ed25519`)

---

## Known Issues & Bugs

### UI Issues (from user screenshot, Mar 8)

1. **Filter chips row clipped** — **RESOLVED**: Changed `maxHeight: 40` to `flexGrow: 0`.
2. **Continue Reading section too large** — **RESOLVED**: Limited to 2 most recent.
3. **Continue Reading cards have card-like backgrounds** — **RESOLVED**: Removed parchmentDark background.
4. ~~**UI not visually tested**~~ — **RESOLVED**: Visual testing done with agent-browser. Confirmed all screens render correctly. Topics expansion works (Playwright click issue was a false positive — React Native Web Pressable needs DOM `.click()`, not Playwright's `click @ref`).

### Data Issues

5. ~~**Server has only 47 articles**~~ — **RESOLVED**: Full 171-article corpus restored with 2,954 atomic claims, embeddings, and knowledge index.
6. ~~**Duplicate topic variants**~~ — **RESOLVED**: Added client-side topic normalization in `app/lib/display-utils.ts` (`normalizeTopic()` + `displayTopic()`). Used across feed filter chips, topic tags, and Topics tab grouping. Reduced 67→58 topic groups.
7. ~~**google.generativeai deprecation warning**~~ — **RESOLVED**: Migrated all LLM calls to `google.genai` SDK via shared `gemini_llm.py` wrapper. litellm fully removed.
11. ~~**Twitter cookies expire**~~ — **RESOLVED**: Chrome extension auto-syncs cookies to server on X.com visits (4h throttle). Also available via `POST /twitter/cookies` API and `GET /twitter/status` health check.

### Server Issues

15. ~~**Single-threaded server causes capture failures**~~ — **RESOLVED** (session 28): `HTTPServer` → `ThreadingHTTPServer`. Rapid photo captures no longer cause `ConnectionResetError` from queued requests blocking behind slow Gemini Vision calls.
16. ~~**No retry for failed photo OCR**~~ — **RESOLVED** (session 28): Photo retry queue added (parallel to existing voice retry). Failed captures auto-retry on book-detail focus.

### Logic Issues

8. **Reading mode toggle shows even when no dimming** — Fixed: now checks `Array.from(blockDimming.values()).some(d => d.opacity < 1)`.
9. **Feed sort unstable with empty ledger** — Fixed: added 0.05 threshold + rank tiebreaker so interest model order is preserved until curiosity scores meaningfully diverge.
10. **Paragraph-to-block mapping is heuristic** — `buildParagraphToBlockMap()` uses text prefix matching (first 50 chars). May mismap in articles with repeated paragraph openings.
12. ~~**Synthesis markdown has raw hex claim IDs**~~ — **RESOLVED** (session 19): Synthesis prompt redesigned with Article Reference Key section. LLM now writes proper `[Title](article:ID)` links instead of raw hex claim IDs like `[3d282718e065]`.
13. ~~**Feed does not filter synthesis-covered articles**~~ — **RESOLVED** (session 19): `getArticleSynthesisCoverage()` wired into `getRankedFeedArticles()` and `getArticlesByLens()`. Articles with ≥80% coverage excluded, ≥50% demoted.
14. ~~**Synthesis reader missing claim classification / paragraph dimming**~~ — Partially addressed (session 19): Synthesis reader completely rewritten with "Restrained Folio" design including inline chat, article popovers, and progressive disclosure. Claim classification and paragraph dimming in synthesis context remain future work.

---

## How the Knowledge System Works (User Perspective)

### First Use (Empty Ledger)
1. All claims classify as NEW (no ledger entries to compare against)
2. Feed shows articles ranked by interest model (curiosity scoring has no effect yet)
3. Reader shows "What's new for you" card with novel claims from the knowledge index
4. Reading mode toggle does NOT appear (no familiar blocks to dim)
5. User reads article → Done → claims recorded in ledger with stability=30d

### After Reading Several Articles
1. Open an article on a related topic → knowledge engine finds similar claims via cosine similarity
2. Claims matching ledger entries at ≥0.78 → KNOWN, ≥0.68 → EXTENDS, <0.68 → NEW
3. Paragraph dimming computed: familiar paragraphs get opacity 0.55, novel get 1.0, mixed get blended
4. Reading mode toggle appears:
   - **Full** — all content at normal opacity
   - **Guided** — familiar paragraphs dimmed (opacity from dimming map)
   - **New Only** — familiar blocks collapsed into "N familiar sections" bars, tap to expand
5. Feed re-ranks: articles with ~70% novelty ratio score highest (curiosity zone)

### Knowledge Decay
- Claims fade over time: R = e^(-t/S) where S = stability_days
- Skim=9d, Read=30d, Highlight=60d
- Re-reading reinforces: stability × 2.5
- Forgotten when R < 0.3 → claim treated as unknown again

### Topics & Delta Reports
- Topics tab groups articles by broad topic from `interest_topics`
- Expanding a topic shows the LLM-generated delta report: "What's new in [topic]"
- Delta reports are pre-generated by `build_knowledge_index.py` using Gemini Flash
- Each report: summary paragraph + top 5 claims

---

## Next Steps (Priority Order)

### Completed
1. ~~**Visual testing**~~ — DONE
2. ~~**Topic normalization**~~ — DONE
10. ~~**Research agent button**~~ — DONE: "↗ Research [topic]" in reader menu and Topics tab, spawns `claude -p`, auto-ingests found articles
11. ~~**Voice notes**~~ — DONE: Record in reader → upload to server → async Soniox transcription → stored as notes linked to article + topics
12. ~~**Resourceful bookmark pipeline**~~ — DONE: `build_articles.py --entities` detects short tweets mentioning books/people/products, uses Gemini Flash to extract entities, synthesizes mini-articles. Runs as step 3c2 in cron pipeline. Tested: 5 entity articles ingested successfully.
13. ~~**Topic +/- buttons fixed**~~ — DONE: Per-topic signals (not all topics), visual feedback on votes
14. ~~**Feed refresh on return from reader**~~ — DONE: `useFocusEffect` triggers recalculation of feed, read articles, and continue reading lists
15. ~~**Robust voice recording**~~ — DONE: Saves locally first → uploads in background → retry queue for failures
16. ~~**Long-press entity research**~~ — DONE: Long-press paragraph → action menu (Highlight / Research / Ask AI). Research opens AI chat with passage context.
17. ~~**Feed "..." menu**~~ — DONE: Voice feedback + stats from main feed screen
18. ~~**Inline topic chips**~~ — DONE: +/- buttons at end of article content, not just post-read modal
19. ~~**AskAI initialQuestion**~~ — DONE: Pre-fill AI chat with questions from research context

### Completed (Session 4+5)
4. ~~**Voice note visibility**~~ — DONE: Voice notes browser screen (`voice-notes.tsx`), accessible from Feed header "Notes" link. Date-grouped notes with transcript, duration, article link, action chips.
5. ~~**Voice note action extraction**~~ — DONE: `extract_note_actions()` in research-server.py uses Gemini to extract research/tag/remember intents from transcripts. Actions shown as tappable chips in VoiceNoteCard. Execute via `POST /notes/{id}/execute-action`.
6. ~~**Claude CLI token expired**~~ — RESOLVED: Topic research completely rewritten from `claude -p` to Gemini search grounding (`call_with_search()`). No longer depends on Claude CLI.
7. ~~**Follow-up research prompts**~~ — DONE: Pipeline extracts 2-3 curiosity-driven questions per article. "✦ FURTHER INQUIRY" section in reader after claims. Tap to spawn topic research via `/research/topic`.
20. ~~**Entity deep-dive**~~ — DONE: Pipeline extracts entities (person/book/company/concept/event/place/technology). Reader highlights entity mentions with dotted underline. Long-press shows marginalia popup with synthesis + "Research more".
21. ~~**LLM migration**~~ — DONE: All LLM calls use `google.genai` SDK via `gemini_llm.py`. litellm removed. Default model: Gemini 3.1 Flash-Lite.

### Completed (Session 6)
22. ~~**Re-run pipeline for entities/questions**~~ — DONE: Added `--enrich` flag to `build_articles.py`. All 182 articles now have entities (1,062 total) and follow-up questions (499 total).
23. ~~**Resourceful bookmark pipeline enhancement**~~ — DONE: `research_entity()` now uses Gemini search grounding (`call_with_search()`) for real Google-grounded results instead of plain LLM synthesis.
24. ~~**Server robustness**~~ — DONE: Added `_read_json_body()` / `_send_json_response()` helpers to research server. All 8 POST endpoints now return clean 400 errors on malformed JSON instead of crashing. File read errors in `execute-action` also handled.
25. ~~**Voice notes error handling**~~ — DONE: `handleActionExecute` in `voice-notes.tsx` now catches errors instead of crashing on network failures.
11. ~~**Production bundle optimization**~~ — Already done: `knowledge_index.json` is gitignored, not bundled.

### Completed (Session 7)
26. ~~**Scroll-aware encounter tracking**~~ — DONE: `markArticleReadUpTo()` only marks claims in paragraphs the user scrolled past. Estimates furthest paragraph from `(maxScrollY + viewportHeight) / contentHeight`. Engagement: 'read' (>60s) or 'skim' (≤60s). "Done" button still marks all claims.
27. ~~**Curated "What's new" card**~~ — DONE: Prioritizes non-factual claim types (causal, evaluative, comparative, procedural) over plain factual. Capped at 3 items. Added `claim_type` to `ClaimClassification`.
28. ~~**G1 descoped**~~ — Per-claim feedback UI explored via 4 design mockups. Decided knowledge model should infer from behavioral signals, not explicit per-claim buttons.

### Completed (Session 8)
29. ~~**Hierarchical topic feedback (G9)**~~ — DONE: PostReadInterestCard redesigned with hierarchical display (broad → specific → entity). `recordTopicSignalAtLevel()` for level-specific signaling without cascade. Smart expand logic.
30. ~~**Cross-article connections (G10)**~~ — DONE: Inline "Also in: [title]" annotations below paragraphs + "✦ CONNECTED READING" bottom section with queue-first behavior (LIFO via `addToQueueFront()`). Max 2 annotations per paragraph, max 5 connected articles.
31. ~~**LLM-verified topic normalization**~~ — DONE: Canonical topic registry (`topic_registry.json`) with include/exclude descriptions. `topic_normalizer.py` validates new topics against registry via LLM merge-or-create decisions. Build pipeline injects existing categories into extraction prompt for consistency from the start. Lessons from Otak's `tree_balance.py` applied: include/exclude descriptions work, but avoid unbounded tree growth.
32. ~~**Automatic topic defragmentation**~~ — DONE: `defragment_registry()` consolidates when limits exceeded. Phase 1: merge similar specifics per overpopulated broad. Phase 2: minimal broad merges. Phase 3: update all articles. Auto-runs as pipeline step 3c3. First run: 28→25 broad, 263→172 specific. See `research/topic-normalization-spec.md` for full spec.
33. ~~**Backfill interest_topics**~~ — DONE: Extended `--enrich` to also generate `interest_topics`. All 185 articles now have hierarchical topics, normalized and defragmented.

### Completed (Session 9)
34. ~~**Entity-link merge**~~ — DONE: When text is both a markdown link and a pipeline entity, the entity popup wins. URL is passed as context: shown in popup, used for smart actions. Article-like URLs (containing `/blog/`, `/article/`, `/introducing/`) get "Save article" (auto-ingest). All others get "Research more" with URL as context for Gemini search grounding. Linked entity mentions get rubric-colored dotted underline.
35. ~~**Ingest auth fix**~~ — DONE: Reader-originated ingests (`source: reader_link`) skip auth token check on `/ingest` endpoint. Previously all ingests required `X-Petrarca-Token`, causing 401 failures from the app.
36. ~~**Entity tap (not just long-press)**~~ — DONE: Entity mentions respond to `onPress` instead of `onLongPress` for better discoverability.

### Completed (Session 19: "Restrained Folio" Synthesis Reader Redesign)
51. ~~**Synthesis prompt overhaul**~~ — DONE: `generate_syntheses.py` rewritten with "humanist scholar" system instruction. Article Reference Key section provides ID→title lookup so LLM writes proper `[Title](article:ID)` links. Descriptive `##` headings instead of prescribed structure. Inline tension blockquotes (`> ⚡ **label**`), inline research prompts (`*Open question: ...*`), `<!-- detail -->` progressive disclosure markers. Structured tensions changed from `string[]` to `Array<{label, description, article_ids}>`. max_tokens 8192→12288. Tested on Pirandello + AI orchestration clusters.
52. ~~**"Restrained Folio" synthesis reader**~~ — DONE: Complete rewrite of `synthesis-reader.tsx`. 2-column CSS grid (1fr + 190px sidebar) on web, single column on mobile. Two visual weights: Cormorant Garamond 30px title + Crimson Pro everything else. Local folio color palette. Sub-components: TensionBlock (amber border), ExcerptBlock (green border), DetailSection (collapsible), SynthesisSidebar with IntersectionObserver TOC tracking. No uppercase letterspaced labels.
53. ~~**SynthesisChat component**~~ — DONE: `app/components/SynthesisChat.tsx` (307 lines). Inline chat modal for synthesis discussions. Context builder from synthesis data. Auto-sends initial question. Restrained Folio styling.
54. ~~**ArticlePopover component**~~ — DONE: `app/components/ArticlePopover.tsx` (194 lines). Web-only hover popover for article reference links. Smart edge-flipping positioning. Coverage bar, quick actions (Queue/Seen/Disregard).
55. ~~**Feed synthesis coverage filtering**~~ — DONE: `getArticleSynthesisCoverage()` wired into `getRankedFeedArticles()` and `getArticlesByLens()`. Articles with ≥80% synthesis coverage excluded from feed. Articles with ≥50% coverage get score demotion `(1 - coverage * 0.5)`.

### Completed (Session 11b)
47. ~~**Floating feedback capture**~~ — DONE: `FeedbackCapture.tsx` — floating ✦ button on every screen. Tap opens voice/text overlay with auto-detected context (screen, article ID). Long-press hides (persisted to AsyncStorage). Saves locally to `@petrarca/feedback_items`. TODO: screenshot capture, server upload.
48. ~~**Expanded follow-up questions**~~ — DONE: Pipeline now generates 4 questions per article (was 2-3) with broader framing. "More questions" button in FURTHER INQUIRY section generates 3 more via `POST /generate-questions` (avoids duplicates). Pulsing ✦ animation while loading.
49. ~~**Queue auto-advance**~~ — DONE: After finishing article + closing interest card, auto-navigates to next queued article via `router.replace()`. "UP NEXT: {title}" toast with "← Feed" escape button. `advanceOrGoBack()` replaces all `router.back()` calls.
50. ~~**Hybrid topic interest signals**~~ — DONE: Replaced binary +/- chips with hybrid minimal design. Single signal model: interested/neutral/less. New topics (zero signals, ≤1 articles) get prominent left-bordered +/− rows. Known topics get compact flowing dot-list with tap-to-cycle `KnownTopicDot`.

### Completed (Session 11)
41. ~~**Clipper immediate save**~~ — DONE: Save fires immediately via background service worker on popup open (survives popup close). Cancel/Escape sends `POST /ingest-cancel` to undo. Notes sent separately via `POST /ingest-note`. Offline fallback queues to `chrome.storage.local`.
42. ~~**PETRARCA wordmark opens app**~~ — DONE: Clicking the wordmark in clipper popup cancels capture + opens web app in new tab.
43. ~~**Reader "Disregard" action**~~ — DONE: ⋯ menu gets "Disregard" (muted text, below divider). Calls `dismissArticle()` with reason `reader_disregard`, records interest signal, navigates back to feed.
44. ~~**Report bad scrape queue**~~ — DONE: ⋯ menu gets "Report bad scrape". Sends to `POST /report-scrape` → stored in `/opt/petrarca/data/scrape_reports.json`. `GET /scrape-reports` lists pending reports. Deduplicated by article_id.
45. ~~**Feed ingest metadata**~~ — DONE: Latest lens shows relative ingest time ("2h ago", "yesterday") + source label (Twitter, Readwise). Uses `ingested_at` ISO timestamp (new field) with fallback to `date`.
46. ~~**`ingested_at` timestamp**~~ — DONE: Both `import_url.py` and `build_articles.py` now write `ingested_at: datetime.now(UTC).isoformat()` on all new articles. Existing articles fall back to `date` (day-level precision only).

### Completed (Session 25: Unified Book Library + Kindle Include Fix + Instant Add Book)

56. ~~**Kindle Include button fix**~~ — DONE: Old flow called `POST /book/process-kindle` with `{ max: 1 }` which processed the first alphabetically matching book, not the clicked one. New `POST /kindle/include` endpoint takes `{ "key": "<asin>" }`, creates unified PhysicalBook immediately, converts highlights to captures, marks `added_to_petrarca: true`, starts research in background thread.
57. ~~**Server-side Kindle filtering**~~ — DONE: `GET /kindle/library?exclude_processed=true` filters already-included books server-side, reducing payload from 2,776 to just unprocessed books. Also returns `title_display` for resolved sideloaded titles.
58. ~~**Kindle curation screen renamed**~~ — DONE: "Kindle Library" → "Import from Kindle". Uses display titles, shows toast on include, removes book from list on success.
59. ~~**Unified Library**~~ — DONE: Library subtitle changed from "Physical books" to "Books & reading notes". `metadata_source` type includes `'kindle'`. Kindle-included books appear in Library alongside physical books.
60. ~~**Instant add-book from photo**~~ — DONE: Old flow blocked user 5-10s on "Identifying..." spinner with 3-step wizard (capture → identifying → confirm). New flow: photo → placeholder book created immediately (`processing_status: 'identifying'`) → navigate back to Library in ~100ms. Identification runs in background, updates book when done. Library shows spinner for identifying books.
61. ~~**Reactive book store**~~ — DONE: `onBookStoreChange()` listener system + `useBookStoreVersion()` React hook added to `book-store.ts`. All mutations call `notifyListeners()`. Library and book-detail screens auto-re-render when background processing updates a book.
62. ~~**Book detail voice recording**~~ — DONE: Voice capture with expo-av recording, stable local file copy, background upload with retry queue via AsyncStorage. Shows transcription status (processing/failed with retry button).

**Files changed**:
- `scripts/research-server.py` — new `POST /kindle/include` endpoint, `GET /kindle/library` supports `?exclude_processed=true` + `title_display`
- `app/app/kindle-curation.tsx` — calls `/kindle/include` per-book, filtered fetch, toast feedback, display titles
- `app/app/add-book.tsx` — instant return: placeholder → background identify → update
- `app/data/book-store.ts` — `onBookStoreChange()` listeners, `useBookStoreVersion()` hook, `notifyListeners()` on all mutations
- `app/data/types.ts` — `metadata_source: 'kindle'`, `processing_status: 'identifying' | 'ready'`
- `app/app/(tabs)/library.tsx` — reactive hook, spinner for identifying books, updated subtitle
- `app/app/book-detail.tsx` — reactive hook, voice recording with retry queue
- `app/lib/book-api.ts` — `includeKindleBook(key)` function

### Completed (Session 10)
37. ~~**Clipper auto-save countdown**~~ — DONE: Chrome clipper popup auto-saves after 10 seconds (fire-and-forget via Cmd+Shift+S). Signature double rule acts as countdown timer (rubric drains to gray). Typing in note field pauses countdown. Visible Cancel button + Esc. Gold completion flash (#c9a84c) on save. requestAnimationFrame for smooth 60fps timer.
38. ~~**Tweet URL ingestion via twikit**~~ — DONE: `/ingest` endpoint detects twitter.com/x.com URLs and routes through twikit instead of generic URL import. Fetches full tweet metadata, reconstructs threads (same-author reply chains), extracts + resolves t.co links. If tweet has URLs → ingests linked article with tweet context. If no URLs → uses tweet/thread text as article content. Falls back to normal import if twikit fails.
39. ~~**Auto-sync Twitter cookies**~~ — DONE: Chrome extension silently extracts `auth_token` + `ct0` cookies when user visits X.com and pushes to server via `POST /twitter/cookies`. Throttled to once per 4 hours. Eliminates manual SSH cookie refresh. New manifest permissions: `cookies` + `host_permissions` for x.com/twitter.com.
40. ~~**Cookie health endpoints**~~ — DONE: `GET /twitter/status` checks cookie validity + age. `POST /twitter/cookies` accepts `{auth_token, ct0}` for remote cookie refresh.

### Completed (Session 41: Review System Consolidation + Fractal Exploration)
63. ~~**Review tab rewrite — infinite river**~~ — DONE: Review now uses `knowledge_items` (253 items, 6 curricula) instead of `retrieval_questions` (19 Sicily-only). Cards/Voice sub-tabs. Infinite river with no session boundary. Skip button on every card. Simplified grading (knew/partly/missed) via `review_engine.record_answer()`.
64. ~~**Fractal exploration microlearning**~~ — DONE: Each review card gets 3 LLM-generated follow-up queries. Tap triggers Gemini + Search → stored as `microlearning_card` with content, assessment Q, and 3 new follow-ups. Interleaved every ~5 items. Text input for custom queries. New table: `microlearning_cards`. New endpoint: `POST /review/microlearning`.
65. ~~**Voice chapter recall prompts**~~ — DONE: Voice elicitation includes "What do you remember from Chapter X?" with high-priority candidate selection.
66. ~~**Legacy review code cleanup**~~ — DONE: `record_review_result()`, `get_review_status()`, `get_retrieval_questions()` removed. `retrieval_questions` and `review_schedule` tables archived. Scoring exclusively through `review_engine.record_answer()`.
67. ~~**Review interaction logging**~~ — DONE: 7 new event types for algorithm tuning: `review_card_shown`, `review_answer_revealed`, `review_result` (with `time_seconds`), `review_skip`, `review_entity_intro_continue`, `review_custom_query`, `review_research_triggered`.
68. ~~**Navigation cleanup**~~ — DONE: "Voice Recall" and "Hamarquizen" removed from drawer. "Hamarquizen" → "Book Review" in book-detail. Review badge navigates to Review tab.

### Gap Analysis: Built vs. Full Spec (updated end of session 8)

#### COMPLETED — Original Gaps Now Resolved

| # | Feature | Resolution |
|---|---------|-----------|
| G1 | Claim-level feedback UI | **Descoped** → behavioral inference via scroll-aware tracking + curated "What's new" card |
| G3 | Incremental embedding | **DONE** — only embeds new claims, prunes removed, `--force` for full rebuild |
| G4 | Related articles at reader bottom | **DONE** — 3 groups (same topic / shared concepts / same source) with "+ Queue" buttons |
| G5 | Reader "Up next" footer | **DONE** — footer bar with Done + next queued article title, `router.replace()` flow |
| G6 | Auto-ingest from links | **DONE** — tap link → POST `/ingest` → poll `/ingest-status` → inline badges |
| G7 | Activity Log tab | **DONE** — 4th tab, server aggregation via `/activity/feed`, offline log queue |
| G9 | Topic hierarchy feedback | **DONE** — hierarchical PostReadInterestCard, `recordTopicSignalAtLevel()`, entity scoring |
| G10 | Cross-article connections | **DONE** — inline "Also in: [title]" annotations + "✦ CONNECTED READING" bottom section |
| G12 | Novel section markers | **DONE** — 2px green left border on novel/mostly_novel paragraphs in Guided/New Only modes |
| G13 | Micro-delights (partial) | **DONE** — ✦ pull-to-refresh ornament, claim reveal stagger (80ms), completion flash. AnimatedHighlightWrap deferred. |

#### REMAINING GAPS

| # | Feature | Priority | Notes |
|---|---------|----------|-------|
| G2 | **LLM judge for ambiguous claims** | ~~Medium~~ | **DONE** — `judge_ambiguous_pairs()` in `build_knowledge_index.py`, verdicts in `knowledge_index.json`, client consults verdicts in 0.68–0.78 range. First run: 57% of 200 judged pairs reclassified (mostly EXTENDS→UNRELATED). |
| G8 | **Web split panel + keyboard shortcuts** | Medium | Desktop experience. Left pane article list + right pane reader, `j/k/d/x/q/Space/s` keys. |
| G11 | **Scrollbar novelty minimap** | Low | Colored dots on scrollbar showing novel content locations. |
| G14 | **Scrape report triage + pipeline hardening** | Low | Mostly resolved by session 14 fixes. 2 of 4 reports fixed (tweet normalization, paragraph merging). Remaining: `df64c81e` (Claude docs, JS-heavy) and `450e9396` (newsletter redirect URL). `clean_existing_articles.py` now serves as ongoing quality audit. |
| G13 | **AnimatedHighlightWrap** | Low | Amber long-press border animation. Deferred due to block rendering complexity. |
| G14 | **Entry row sidebar** | Low | 76px sidebar with large Cormorant numbers + depth dots. Design polish. |
| G15 | **Depth navigator** | Low | Summary / Claims / Sections / Full horizontal toggle in reader. |
| G16 | **Novelty badges** | Low | "Mostly new" / "72% new" / "Partly familiar" semantic badges. |
| G17 | **Dismissed articles archive** | Low | Archive view for swiped-left articles. |
| G18 | **Structured comparison** | Low | Elicit-style multi-article comparison matrix. |
| G19 | **Blindspot detection** | Low | Topics with many articles but few absorbed claims. |
| G20 | **Contradiction detection** | Deferred | Corpus too harmonious (86% compatible). |
| G21 | **Book reader** | Deferred | Section-based long-form reading. |
| G22 | **Nomic embeddings** | Low | Experiments preferred Nomic over Gemini embeddings. Works fine with Gemini. |

### User Feedback Summary (from voice notes, Mar 8)
- **Article `6e3cb28c19e1`** (NotebookLM learning compression): User wants to bookmark AND follow multiple topics (AI-assisted learning, learning strategies). Wants topic overview to surface recently-bookmarked articles prominently. Voice feedback should support actionable commands (add tags, research topics, express interest).
- **Article `0708161ff37b`**: 94-second voice note recorded but transcription was client-side (old code). Note may not have been stored server-side — check logs. This was the last interaction before the backend transcription refactor.

---

## Key Design Documents

| Document | Purpose |
|----------|---------|
| `research/system-state-of-the-art.md` | **START HERE** — Comprehensive reference covering all research, algorithms, data structures, experiments, UI mockups |
| `research/novelty-system-architecture.md` | Architecture design for the knowledge-aware system |
| `research/experiment-results-report.md` | Results from 11 validation experiments |
| `research/experiment-log.md` | Append-only chronological experiment log |
| `research/ux-redesign-spec.md` | 2 rounds of mockup feedback, approved interaction models |
| `design/DESIGN_GUIDE.md` | The Annotated Folio design system specification |
| `research/knowledge-diff-interfaces.md` | HCI research on adaptive presentation (dimming, stretchtext) |
| `research/knowledge-tracing-for-reading.md` | FSRS/BKT adaptation for reading knowledge |
| `research/knowledge-deduplication.md` | Embedding + dedup architecture |
| `research/topic-normalization-spec.md` | Topic normalization & defragmentation spec — registry design, LLM merge-or-create, defrag algorithm, Otak lessons |
| `research/user-guide.md` | User-facing guide (markdown source) — also at `app/public/guide/index.html` (HTML) |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). `call_llm()`, `call_chat()`, `call_with_search()`, `call_llm_tool()`. Model: `gemini-3.1-flash-lite-preview` |
| `scripts/build_articles.py --claims` | Extract atomic claims, entities, and follow-up questions (Gemini 3.1 Flash-Lite, 10 parallel workers) |
| `scripts/build_articles.py --claims-only` | Extract claims/entities/questions for articles that don't have them yet |
| `scripts/build_articles.py --enrich` | Backfill entities + follow-up questions for existing articles (10 parallel workers) |
| `scripts/build_claim_embeddings.py` | Generate Gemini embeddings for all claims (batch 100) |
| `scripts/build_knowledge_index.py` | Build knowledge_index.json from embeddings (parallel delta reports) |
| `scripts/build_knowledge_index.py --skip-delta` | Build without LLM delta reports (faster) |
| `scripts/llm_audit.py` | View LLM usage/cost audit. `--days 7`, `--since 2026-03-01`, `--json` |
| `scripts/log_server.py` | Interaction log collector (port 8091, systemd `petrarca-log`) |
| `scripts/deploy_knowledge_index.sh` | Deploy to nginx + update manifest |
| `scripts/content-refresh.sh` | Full cron pipeline (fetch → extract → claims → embed → index → deploy) |
| `scripts/topic_normalizer.py` | Topic normalization + defragmentation. Normalize, defrag, enforce limits |
| `scripts/topic_registry.json` | Canonical topic registry — 25 broad, 172 specific topics with include/exclude descriptions. Auto-updated by normalizer, consolidated by defrag |
| `scripts/experiment_*.py` | 11 experiment scripts (see experiment-results-report.md) |
