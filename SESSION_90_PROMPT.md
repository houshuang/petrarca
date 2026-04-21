# Session 90 — Epistemic Fidelity: Accuracy Flags + Uncertainty Preservation

**Status at start:** Session 89 shipped the ML retry sweep (P0.2) and cross-path wondering dedup (P1.2) — deployed at commit `0ef263d`. The two remaining gaps from Session 87's Iran retention analysis are **P2.1 accuracy contradictions** and **P2.2 uncertainty-marker preservation**. Both share a deeper theme: the pipeline loses the distinction between *what the user said/knows* and *what the LLM confidently asserts*. This session ships the minimum viable response to each, scoped so neither balloons into the design session it could become.

Session 88 (Gemini → Claude migration) should be merged before this runs; if not, coordinate or rebase. All LLM calls in `review_engine.py` should be assumed Claude by session start.

---

## Priority 0 — Surface the problem to the user (unblocks everything else)

### P0 — "Flag as inaccurate" button on ML cards

**Why first:** we currently have *zero* mechanism for the user to report that an ML card is wrong. Every subsequent design decision (consistency checks, validator against knowledge_items, training-data mining) needs a source of labeled bad cards. Ship this as the canonical error channel, then everything downstream has data to work with.

**Implementation:**

1. **Schema** (`scripts/db.py`):
   - Add columns to `microlearning_cards`:
     - `flagged_inaccurate INTEGER DEFAULT 0` (0/1 boolean)
     - `flagged_reason TEXT` (free-text from user)
     - `flagged_at INTEGER` (epoch ms)
   - Add migration in the `MIGRATIONS` list (don't rewrite the CREATE TABLE — this pattern is already established in db.py).

2. **Endpoint** (`scripts/research-server.py`):
   - New `POST /review/ml-flag-inaccurate` handler. Body: `{card_id: str, reason: str}`. Sets the three columns, returns `{ok: true}`.
   - Also log to `interaction_log` with `event_type='ml_flag_inaccurate'` so it shows up in the Stats timeline.
   - Side effect: set `due_at` to 0 + add a "suspended_flagged" bit (or just add a `WHERE flagged_inaccurate=0` filter to `generate_review_stream`'s ML selection in `curriculum_db.py`) so flagged cards drop out of the queue immediately.

3. **Client** (`app/app/review.tsx` or wherever `ReviewCard` lives for ML origin):
   - The existing `⋯` menu already has "Bad question" / "Suspend" — add a third item "Inaccurate fact".
   - Tap → prompt for 1-line reason (optional, default empty) → POST → fade the card, toast "Flagged".
   - For ML-origin cards only; not applicable to aspect/sequence/synchronic/cast/causal or to structural cards.

**Testing:** after deploy, flag one test card via the UI. Verify it disappears from the stream immediately, shows in `interaction_log`, and the three DB columns are set. Query:
```sql
SELECT id, flagged_inaccurate, flagged_reason, flagged_at FROM microlearning_cards WHERE flagged_inaccurate=1;
```

**Lines of code:** ~30 DB + endpoint, ~40 client. Small.

---

## Priority 1 — Preserve uncertainty through the pipeline

### P1.1 — `confidence` per-fact in extraction

Today, `VOICE_CAPTURE_ENTITY_PROMPT` (scripts/review_engine.py:516) outputs:
- `entity_facts[entity][i]` = `{id, question, answer, type, source_excerpt}` — **no confidence**
- `confidence_tagged[]` = `[{fact: "text", confidence: "certain|uncertain|wrong"}]` — separate sibling list, not keyed, fragile to match back to entity_facts

Result: by the time the pipeline writes `key_facts` to `knowledge_entities`, the confidence is severed. Downstream consumers (enrichment, review rendering) have no access to per-fact epistemic state.

**Implementation:**

1. **Prompt change** (`VOICE_CAPTURE_ENTITY_PROMPT` at `scripts/review_engine.py:516` AND `VOICE_CAPTURE_ANALYSIS_PROMPT` at `:482`):
   - Add `"confidence": "certain|uncertain|wrong"` as a required field on each entity_fact and on each fact in `facts[]`.
   - Add BAD/GOOD examples (follow the pattern from `_ENRICH_PROMPT` temporal_hook):
     - **certain**: "Khomeini returned to Iran on February 1, 1979" (stated as fact, specific date)
     - **uncertain**: "The Shah went to Egypt, I think — Morocco or somewhere" (explicit hedge, alternative offered)
     - **wrong**: "Khomeini was 78 when he returned" (stated confidently but verifiable as incorrect against Wikidata)
   - Keep `confidence_tagged` sibling field for backward compat — it's referenced elsewhere — but treat the per-fact `confidence` as authoritative.

2. **Store confidence on key_facts**:
   - `_process_voice_capture_entity_path` (`scripts/review_engine.py:5732`) currently copies `entity_facts[entity]` into `knowledge_entities.key_facts` as-is. With the prompt change, `confidence` rides along automatically.
   - Same for the curriculum path's `key_facts` writes — verify the shape flows through.

3. **Use in `_ENRICH_PROMPT`** (`scripts/review_engine.py:1359`):
   - When generating rich_answer for a fact with `confidence='uncertain'` or `'wrong'`, inject a new block above the output instructions:
     ```
     EPISTEMIC CONTEXT: The learner captured this fact with hedged confidence ("{original_excerpt}"). Frame the rich_answer to acknowledge their uncertainty and confirm or correct the claim gently. Do NOT condescend — the learner's hedge was epistemically sound.
     ```
   - The `{original_excerpt}` is the `source_excerpt` from the fact — give the LLM the user's own words so it can mirror the hedge.

4. **Render on review card**:
   - In `ReviewCard` / `AspectCard` / wherever facts render: if `fact.confidence === 'uncertain'`, show a small "⁓ you captured this with hedge" indicator near the question. If `'wrong'`, "⚠ captured as a guess" with the rich_answer acting as the correction.
   - Low-key UI — this is a learning moment, not an error.

**Why it matters:** the user's epistemic map is the product. Flattening "I think Morocco" to "Morocco ↦ definitely" destroys that. Re-surfacing the hedge preserves it and makes the rich_answer's correction a teachable moment.

### P1.2 — `correction` field on `_ENRICH_PROMPT` output

When the rich_answer disagrees with the short_answer in a specific, verifiable way (e.g. user said "Morocco", verified answer is "Egypt"), surface this explicitly rather than hiding it inside the 4-5-sentence prose.

**Implementation:**

1. **Prompt** (`_ENRICH_PROMPT`):
   - Add a 4th output field:
     ```
     4. correction: If the short_answer contradicts verified knowledge on a specific, checkable point
        (a name, date, number, place), output a {{"user_said": "<their claim>", "actually": "<verified>", "why_confused": "<1-sentence explanation>"}} object. Otherwise, output null.
     ```
   - Examples:
     - BAD: correction used for vibes ("user was uncertain"). The field is for verifiable, named contradictions only.
     - GOOD: `{"user_said": "Morocco", "actually": "Egypt (Anwar Sadat received him)", "why_confused": "Sadat's Egypt was the first refuge; the Shah later moved through Panama and eventually died in Egypt — Morocco was never a destination."}`
   - Schema update: `{"rich_answer": "...", "memory_hook": "...", "temporal_hook": "...", "correction": null | {...}}`.

2. **Store**:
   - `cached_question.correction` JSON field alongside rich_answer.

3. **Render**:
   - Review card shows correction block prominently when present — "You said X. Actually Y. Why it's easy to confuse: Z." in a bordered box above the rich_answer.
   - This IS the retention moment for that fact. Don't bury it.

**Lines of code:** ~15 prompt, ~10 store, ~40 client render.

---

## Priority 2 — Light accuracy-check on multi-card generation

### P2.1 — Pairwise consistency check on sibling ML cards from same capture

**The bug:** `ml_1776697189_7523` says Khomeini was 78 at the 1979 flight; `ml_1776697263_5906` says 76 on the same flight. Same transcript, two LLM calls, contradictory specific numbers.

**Ship:** after all ML cards from a single voice capture complete, run ONE Claude consistency-check pass over their titles + rich_answers + key quizzes. Return `contradictions: [{card_ids: [id1, id2], conflict: "disagreement on Khomeini age: 76 vs 78", verdict: "ml_1776697263_5906 correct"}]`. For each contradiction, auto-flag the loser (set `flagged_inaccurate=1`, `flagged_reason='consistency check: contradicts ml_XXX'`). User sees flagged cards drop out of queue; if they want to review, they can unflag manually.

**Why not a knowledge_items validator:** that requires entity-linking every ML card to a canonical entity, reconciling partial/hedged user knowledge, and tolerating the user's own wrong knowledge overruling the LLM. All design-session work, not worth blocking P2.1.

**Implementation:**

1. New function `_run_consistency_check(capture_id: str)` in `review_engine.py`.
2. Hook into the end of `process_voice_capture` / `_process_voice_capture_entity_path` — after all ML creation threads are spawned, kick off a background thread that polls microlearning_cards for this capture's cards until all reach `completed` or `failed` (timeout 5 min), then runs the consistency pass.
3. Claude call with all sibling cards as input → JSON output of contradictions → auto-flag losers.
4. Log in `interaction_log` with `event_type='ml_consistency_flag'`.

**Lines:** ~80. Non-trivial but bounded.

**Could defer if time runs short.** P0 (flag button) + P1 (uncertainty) are the spine; P2 is the cleanup that happens automatically once flag infrastructure exists.

---

## Non-goals for this session (explicit)

- **Do NOT** build the heavier validator against `knowledge_items` / `knowledge_entities` as a cross-check. That requires entity linkage for every ML card and is a session of its own — list it in session-changelog as a standalone follow-up.
- **Do NOT** re-process historical ML cards to backfill `confidence` or run consistency checks on them. Forward-only. The historical contradictions (Khomeini 76 vs 78) stay; user can flag them manually via P0 if they hit one in review.
- **Do NOT** POST synthetic text to `/explore/capture` for testing. Test via `scripts/pipeline-tests/run.py` fixtures or in-memory SQLite. CLAUDE.md § Production Data Discipline.
- **Do NOT** touch the SESSION_88 Gemini migration surfaces (if still in flight). If SESSION_88 landed before this, verify all LLM calls in the enrich/capture paths are Claude before prompt-tweaking.

---

## Deliverables

1. Schema migration: 3 columns on `microlearning_cards` for flagging.
2. Endpoint: `POST /review/ml-flag-inaccurate`.
3. UI: "Inaccurate fact" option in ML-card `⋯` menu.
4. Prompt change: `confidence` on per-fact in both voice capture prompts, `correction` field on `_ENRICH_PROMPT`.
5. Render: uncertainty indicator + correction block on review cards.
6. Consistency check (if time): background pass after each voice capture completes, auto-flag losers.

One commit per priority or bundled. Branch `sh/epistemic-fidelity`. Deploy + verify with a real voice capture — check that (a) the user can flag a card, (b) a capture with an explicit hedge ("I think X") preserves `confidence='uncertain'` through to the review card, (c) if time permits, the consistency pass catches the Khomeini-age-style contradiction when injected.

---

## Context pointers

- Session 89 changes: commit `0ef263d`. Changes: ML retry sweep in research-server.py, `_shared_trigrams` + dedup loop in review_engine.py.
- Session 87 retention-diff analysis (end of that session conversation) — the source of the two gaps P2.1 and P2.2 addressed.
- Voice capture prompts: `scripts/review_engine.py:479` (analysis), `:516` (entity), `:1359` (enrichment).
- Iran capture raw data: `ssh alif 'sqlite3 /opt/petrarca/data/petrarca.db "SELECT * FROM microlearning_cards WHERE created_at BETWEEN 1776697000000 AND 1776698000000"'` — includes the Khomeini 76/78 pair for consistency-check testing.
- Pre-push hook fix: Session 89 applied it locally; if running in a fresh worktree, the hook's `.git/hooks/pre-push` likely needs the same `unset GIT_DIR GIT_WORK_TREE` patch. Reapply before first push.
