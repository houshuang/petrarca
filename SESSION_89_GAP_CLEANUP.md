# Session 89 — Pipeline gap cleanup surfaced by the Iran Revolution capture

**Status at start:** Session 87 fixed three silent drops in the voice-capture pipeline (pre-gen retry for 429s, rank-before-truncate for wonderings, `temporal_hook` added to enrichment prompt). Session 87's end-of-session analysis used the 2026-04-20 Iran Revolution capture (transcripts `vt_1776697230_4034` entity-path + `vt_1776697289_4034` curriculum-path, 3518 chars, 10 ML cards, 6 entities) as the empirical test case and surfaced four remaining gaps. This session addresses them.

The Session 87 regen of the 6 Iran entities' `cached_question` with the new `_ENRICH_PROMPT` achieved **100% temporal_hook fill rate** on real data, confirming P1.1 works. That result is in `/tmp/iran_bundle.json` on Stian's laptop if you need to re-inspect it.

**Parallel session warning:** SESSION_88_GEMINI_TO_CLAUDE.md is running in parallel and also touches `scripts/review_engine.py` + `scripts/research-server.py`. Spawn with `isolation: "worktree"` so the two don't conflict. Merge both branches at the end.

---

## Priority 0 — Stuck cards recovery

### P0.2 — ML cards stuck at `status=failed` forever (no retry path)

**Symptom:** 4 of 10 ML cards from the Iran capture are in `status=failed` with 0 quizzes:
- `ml_1776697189_6128` (follow_up): "Did Khomeini himself visit the embassy…"
- `ml_1776697289_6873` (voice_wondering): "How exactly was the transitional PM put in place…"
- `ml_1776697289_3992` (voice_wondering): "Why did the Americans misunderstand the demands…"
- `ml_1776697289_6626` (voice_wondering): "What specific forms of torture were used…"

The failures are almost certainly from the same Gemini 429 window that dropped Khomeini's `cached_question`. There is no background sweep to retry them — they stay `failed` forever.

**Implementation:**

Add a startup sweep in `scripts/research-server.py` (the main entry point). After all other init is done, spawn a background thread that:

```python
def _retry_failed_ml_cards():
    """Requeue ML cards that failed within the last 24h. Space them 30s apart
    to avoid re-triggering the same rate-limit that caused the original fail."""
    from db import get_connection
    from review_engine import _run_microlearning_research  # or whatever the function name is
    conn = get_connection(readonly=True)
    now_ms = int(time.time() * 1000)
    rows = conn.execute("""
        SELECT id FROM microlearning_cards
        WHERE status='failed' AND created_at > ?
    """, (now_ms - 86400000,)).fetchall()
    conn.close()
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(30)
        try:
            _requeue_ml_card(row['id'])
        except Exception as e:
            print(f'[ml-retry] {row["id"]} still failing: {e}', flush=True)

threading.Thread(target=_retry_failed_ml_cards, daemon=True).start()
```

**You need to figure out:**
1. The exact function that processes an ML card (grep for `_run_microlearning_research` or similar in `review_engine.py`). Whatever it is, call it.
2. Whether the function needs `conn` or constructs its own — respect the write-lock discipline.
3. Whether `status` should first be reset to `pending` so the regular processing pipeline picks it up, or whether the retry function writes directly.

**Testing:**
After deploy, verify the 4 Iran failed cards pick up and fill. Query:
```
ssh alif 'sqlite3 /opt/petrarca/data/petrarca.db "SELECT id, status, length(content) FROM microlearning_cards WHERE id IN (\"ml_1776697189_6128\", \"ml_1776697289_6873\", \"ml_1776697289_3992\", \"ml_1776697289_6626\")"'
```
Each should move from `failed`→`completed` with non-zero content length.

---

## Priority 1 — Cross-path wondering duplication

### P1.2 — Both voice-capture paths fire overlapping ML cards

The Iran capture produced duplicate ML cards because both `process_voice_capture` (curriculum path, `scripts/review_engine.py:5581`) AND `_process_voice_capture_entity_path` (entity path, `scripts/review_engine.py:5993`) triggered `create_microlearning_request` on overlapping wondering lists:

| Topic | curriculum path (`follow_up`) | entity path (`voice_wondering`) |
|-------|-------------------------------|--------------------------------|
| Chartered airplane | `ml_1776697189_7523` | `ml_1776697263_5906` |
| Prime minister | `ml_1776697189_8386` | `ml_1776697289_6873` (failed) |
| Iranian newspapers | `ml_1776697189_1664` | `ml_1776697289_7596` |

User grades one — the duplicate still sits in the review stream. That's 30% wasted review bandwidth.

**Implementation** (from Session 87 prompt P1.2):

In `_process_voice_capture_entity_path` (`scripts/review_engine.py:~5993`), before calling `create_microlearning_request`, check whether a card with a sufficiently-similar query was created in the last 5 minutes:

```python
# Cross-path dedup: the curriculum path may have already fired an ML card
# for this same wondering. Skip if any ML card in the last 5 minutes has
# ≥20 shared trigrams with this wondering.
existing_recent = conn.execute("""
    SELECT query FROM microlearning_cards
    WHERE created_at > ? AND status != 'deleted'
""", (int(time.time() * 1000) - 300000,)).fetchall()
existing_queries = [r['query'] for r in existing_recent]

kept = []
for w in _rank_wonderings(wonderings, top_k=5):
    if any(_shared_trigrams(w, eq) >= 20 for eq in existing_queries):
        print(f'[voice-capture-entity→ml] skip dup: {w[:60]}', flush=True)
        continue
    kept.append(w)
for w in kept:
    # existing create_microlearning_request call
```

Helper:
```python
def _shared_trigrams(a: str, b: str) -> int:
    def trigrams(s: str) -> set:
        s = ' ' + s.lower() + ' '
        return {s[i:i+3] for i in range(len(s)-2)}
    return len(trigrams(a) & trigrams(b))
```

Threshold of 20 trigrams ≈ 60 chars of overlap. Tune on the Iran duplicates: `"Who paid for Khomeini's chartered airplane"` should overlap ≥20 with `"Who paid for the chartered airplane that brought Khomeini back"`. Verify empirically.

**Order matters:** this must run AFTER `_rank_wonderings` (already in place from Session 87) so we dedup the ranked top-5, not the raw list.

**Why 5-minute window:** the two paths fire seconds apart on the same capture. A 5-minute window is generous enough to catch retries and slow paths, tight enough to avoid legit repeat-wonderings from a later capture.

---

## Priority 2 — Quality gaps

### P2.1 — Accuracy contradictions between sibling ML cards

Two sibling ML cards from the Iran capture contradict each other:
- `ml_1776697189_7523` says Khomeini was "78-year-old" when he boarded the flight back to Iran.
- `ml_1776697263_5906` says he was "76-year-old" on the same flight.

Khomeini was born May 1902, returned Feb 1 1979 → actually 76. One card is wrong.

This is the kind of error no deterministic check catches — the LLM confidently fabricates a specific number. Options:

- **Lightweight**: after multi-card generation on the same topic, run a Claude consistency-check pass on specific factual claims (dates, ages, counts). ~40 lines. May duplicate effort if there's only one card per topic most of the time.
- **Heavier**: add a post-generation validator that flags any ML card whose facts conflict with facts in the same user's existing knowledge_items for the same entity. Requires entity-linking ML cards to knowledge_entities — worth doing regardless for other reasons.
- **Lightest**: ignore for now, document as known limitation, add a user-facing "flag as inaccurate" button on ML cards.

Recommend the lightest option for this session. The heavier options belong in their own design session — note them in `research/session-changelog.md` as open questions.

### P2.2 — Uncertainty markers stripped from capture

The Iran transcript is dense with epistemic hedges:
- "I'm not sure who paid [for the airplane]"
- "Egypt, I think, Morocco or something"
- "I think maybe even Khomeini came himself"
- "maybe a year"

The Q/A format flattens these to confident statements. The user's epistemic map (what they know vs. what they guessed) is destroyed.

**Implementation options:**

1. **Extend `key_facts` schema**: add `confidence: "certain" | "guessed" | "unsure"` (or keep existing `confidence_tagged` field). Change the voice-capture prompt (`VOICE_CAPTURE_ENTITY_PROMPT` + `VOICE_CAPTURE_PROMPT`) to mark each fact's confidence based on the user's own hedges. Preserve through the pipeline. Surface in review cards as "You captured this as uncertain — here's what actually happened."
2. **Add a "corrections" layer**: when rich_answer corrects a user guess (e.g., Shah went to Egypt, not Morocco), flag it explicitly in the card so the correction is the learning moment, not hidden inside the rich answer.

Option 2 is cheaper and more educational. Scope for this session:
- Update the enrichment prompt (`_ENRICH_PROMPT` in `scripts/review_engine.py:1327`) to compare the user's short answer vs. the rich answer and emit a `correction` field when they differ in a verifiable way.
- Render the correction prominently in the review card (`app/app/review.tsx` or wherever ReviewCard lives).

May be too big for this session alongside P0.2 + P1.2. If so, scope only the prompt change and leave the UI for a follow-up — the field will be populated but unused.

---

## Priority 3 — Known false-alarm, do NOT chase

### P3.1 (already fixed forward) — "Richest wondering didn't create an ML card"

Session 87's analysis flagged that the transcript's 6th wondering (`"how did the revolution manage to be both conservative/backward-looking and inspired by modern protest movements like the French Revolution and student sit-ins?"`) did not appear in any ML card. This is **already fixed** in the code — Session 87 deployed `_rank_wonderings` which now scores this wondering as #1 (125 chars, 1 question mark → top rank).

**Why it was dropped for the Iran capture specifically:** the capture was processed at 15:01 UTC 2026-04-20, BEFORE Session 87's ranking fix was deployed. Old `wonderings[:5]` silently truncated it. The next real capture will keep it.

**Do not re-investigate.** If you find yourself looking into wondering ranking, you are in the wrong place.

---

## Recommended execution order

1. **P0.2 (ML retry sweep)** first — ~20 lines, recovers the 4 stuck Iran cards as a freebie, no conflict with P1.2.
2. **P1.2 (cross-path dedup)** — ~30 lines in review_engine.py. Uses the same `_rank_wonderings` path as Session 87 so changes are adjacent.
3. **P2.1 (accuracy / uncertainty)** if time allows — otherwise document + defer.
4. Commit, deploy, verify the 4 failed Iran cards recover, verify no new dupes on the next real capture.

---

## What NOT to do

- Do NOT backfill or regenerate the 6 Iran entities' `cached_question` again — Session 87 already did this and it's the user's manually-verified baseline.
- Do NOT POST synthetic text to `/explore/capture` or any ingest endpoint (CLAUDE.md § Production Data Discipline). Test via `scripts/pipeline-tests/run.py` or a unit test against in-memory SQLite.
- Do NOT mass-edit ML cards in the DB to "fix" their content — the generation pipeline is the thing to fix, not the outputs.
- Do NOT touch Gemini call sites — that's SESSION_88's job. If a fix here crosses a Gemini call, leave the Gemini import and note it in the PR description; SESSION_88 will clean it up.

---

## Deliverables

1. `scripts/research-server.py`: ML retry sweep on startup (P0.2).
2. `scripts/review_engine.py`: cross-path wondering dedup (P1.2), optionally prompt tweaks for P2.
3. Verification: the 4 named Iran ML cards transition from `failed` → `completed`.
4. Branch `sh/pipeline-gap-cleanup`, one commit per priority or one total if kept small.
5. Deploy via `bash ~/src/expo/scripts/deploy.sh petrarca`. The deploy script now checks server-side git cleanliness.

---

## Context pointers

- Session 87 changes: commit `024b7ec`. Changes: `_rank_wonderings` helper, temporal_hook in `_ENRICH_PROMPT`, pre-gen retry loop. Read these before adding new logic nearby.
- Deploy drift check: commit `efd3700` in `~/src/expo/scripts/deploy.sh`. Don't remove.
- Production data rule: CLAUDE.md § Production Data Discipline.
- Write-lock discipline: CLAUDE.md § SQLite Best Practices (global).
- Iran capture raw data: `ssh alif 'sqlite3 /opt/petrarca/data/petrarca.db "SELECT * FROM microlearning_cards WHERE created_at BETWEEN 1776697000000 AND 1776698000000"'`
- Session 87 analysis document: this is the sibling SESSION_87_PROMPT.md plus the end-of-conversation retention-diff analysis.
