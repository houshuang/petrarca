# Session 88 — Migrate all LLM calls from Gemini to Claude

**Status at start:** User has declared (2026-04-20) that the project can no longer use Gemini — "i can't afford gemini." Claude via `claude -p` (Max plan) is effectively free within rate limits. This is a durable preference saved as `memory/feedback_claude_only_never_gemini.md` and overrides the "Gemini for user-facing interactive paths" rule-of-thumb in CLAUDE.md.

The directive was triggered by a concrete failure: during the 2026-04-20 Iran Revolution voice capture, a Gemini 429 RESOURCE_EXHAUSTED silently dropped Khomeini's `cached_question` (Session 87 Priority 0.1). Retry logic alone isn't sufficient — the user wants to eliminate the class of failure.

**Parallel session warning:** a sibling session (SESSION_89_GAP_CLEANUP.md) is also touching `scripts/review_engine.py` and `scripts/research-server.py`. Spawn this agent with `isolation: "worktree"` so the two don't step on each other. Merge both branches at the end.

---

## The scope

32 files import `gemini_llm`, ~60 call sites. Categorized:

### Tier 1 — Active live paths (MUST migrate)

Every site here runs during a real user interaction or review-stream fetch. These are the cost drivers.

- `scripts/review_engine.py` — 5 sites at lines 1283, 2349, 3438, 5103, 6106. Each is a `from gemini_llm import call_llm`. Uses: multi-cue quiz generation, follow-up query generation for chips, voice-capture domain routing, entity confidence tagging.
- `scripts/research-server.py` — ~14 sites (see `grep -n 'from gemini_llm' scripts/research-server.py`). Covers: chat endpoints, explore capture routing, image/vision endpoints (`call_vision`), grounded search endpoints (`call_with_search`).
- `scripts/curriculum.py` — line 20, uses Gemini Flash for curriculum node generation. **Exception per CLAUDE.md**: curriculum generation is already Opus-only; the Gemini import here may be a fallback or test path — verify whether it's actually reached. If it is, migrate.
- `scripts/resurfacing_engine.py` — line 243. Used for resurfacing cards.
- `scripts/claude_llm.py` — lines 83, 164. **This is the damning one**: `claude_llm.py` itself falls back to Gemini when the Claude CLI fails. This cascade is exactly what the user wants to stop. Remove the fallback entirely and raise the original Claude error instead, OR retry Claude once with a backoff.

### Tier 2 — Batch generation scripts (migrate, lower urgency)

Run manually or on cron. Don't cost per-user-interaction but still cost per-run.

- `scripts/generate_aspect_cards.py`, `generate_sequence_cards.py`, `generate_synchronic_cards.py`, `generate_cast_cards.py`, `generate_causal_cards.py` — structural card generation. All import `call_llm` from gemini_llm at line ~18-21.
- `scripts/generate_scale_annotations.py`, `generate_aspect_mnemonics.py` — structural card enrichment batches.
- `scripts/generate_quick_quizzes.py` — batch quick-quiz generation.
- `scripts/generate_from_suggestions.py` — suggestion → structural card pipeline.
- `scripts/bootstrap_entities.py`, `enrich_entities.py` — entity tooling.
- `scripts/backfill_wikidata.py` — lines 413, 643. Wikidata resolution backfill.
- `scripts/reprocess_voice_with_qids.py` — lines 120, 222. Voice transcript reprocessing.

### Tier 3 — DO NOT MIGRATE (disabled subsystems)

CLAUDE.md § DISABLED SUBSYSTEMS (Session 71) explicitly marks these as preserved-but-disabled. Skip unless the user asks.

- `scripts/build_articles.py` (many sites) — article ingestion disabled
- `scripts/synthesis_pipeline.py`, `generate_syntheses.py` — depends on article pipeline
- `scripts/build_concept_clusters.py` — verify this is still live; grep for callers in research-server.py
- `scripts/build_book_claim_embeddings.py` — book pipeline, verify live
- `scripts/ingest_book_petrarca.py` — verify live
- `scripts/book_research_agent.py` — uses `call_with_search` (Gemini's grounded search); this IS in the live book research path. Special case — see Tier 4.

### Tier 4 — Special-case functions

Not every Gemini call has a 1:1 Claude equivalent. Handle these carefully:

1. **`call_with_search` (Gemini grounded search)** — used in `build_articles.py:335`, `research-server.py:1537, 1907, 1724`, `book_research_agent.py:103, 293`. Gemini's Google-grounded search returns web-cited answers.
   - **Claude equivalent**: the Anthropic API supports a `web_search` tool (Claude API, not available in `claude -p` CLI). Two migration options:
     - Switch to direct Anthropic API via `anthropic` SDK with `web_search_20250305` tool.
     - Replace with a cheaper pattern: Claude + a separate search tool (SerpAPI, Brave) + synthesize results.
   - Decide with the user which approach before migrating. Book-research paths depend heavily on grounded search; naive swap will regress quality.

2. **`call_vision`** — used in `research-server.py:1724, 1941, 1980`. Gemini vision for image analysis.
   - **Claude equivalent**: Claude API supports image blocks in messages. Use `claude_llm.py` (or add a `call_vision` there) that sends base64-encoded images to the Anthropic SDK.
   - Straightforward migration, ~30 lines in a new `claude_llm.call_vision` helper.

3. **`call_chat`** — `research-server.py:1670`. Streaming chat?
   - Check what it actually does. If it's SSE streaming, use the Anthropic SDK streaming interface.

4. **`claude_llm.py` Gemini fallback (lines 83, 164)** — the fallback that started this mess. **Highest priority.** Remove entirely. If Claude CLI fails (timeout, auth), surface the error; don't silently hand off to a paid service.

### Tier 5 — Research/experiments (lowest priority)

Won't run in production. Migrate only if easy, otherwise leave with a TODO.

- `scripts/experiments/autoresearch_question_gen_eval.py`
- `scripts/ground-truth/two_stage_pipeline_experiment.py`
- `scripts/compare_synthesis_models.py`
- `scripts/generate_benchmark.py`
- `scripts/generate_similarity_ground_truth.py`

---

## How to migrate a single call site

Gemini's `gemini_llm.call_llm(prompt, model='gemini-2.5-flash')` returns a string (or structured JSON if `response_mime_type='application/json'`).

Claude's `claude_llm.call_claude` / `call_claude_json` (see `scripts/claude_llm.py`) returns the same. Drop-in replacement in most cases:

```python
# Before
from gemini_llm import call_llm
result = call_llm(prompt, model='gemini-2.5-flash', response_mime_type='application/json')

# After
from claude_llm import call_claude_json
result = call_claude_json(prompt, timeout=90, model='sonnet')
```

For non-JSON:
```python
# Before
text = call_llm(prompt, model='gemini-2.5-flash')

# After
from claude_llm import call_claude
text = call_claude(prompt, timeout=90, model='sonnet')
```

**Model selection:**
- `gemini-2.5-flash` / `flash-lite` → `sonnet` (Claude Sonnet 4.6)
- Heavy reasoning / curriculum gen → `opus` (stays Opus)
- Interactive chat → `haiku` (Claude Haiku 4.5 — fastest, cheapest within the Max plan)

**Latency warning:** `claude -p` subprocess startup is 5-15s per call. This is fine for batch work; painful for interactive. Measure each migrated interactive endpoint and flag any that exceeded ~8s before migration — they'll feel slower.

---

## Recommended execution order

1. **First**: migrate `scripts/claude_llm.py` itself (remove the Gemini fallback at 83, 164). Until this is done, every other migration is fragile — a Claude timeout silently falls back to Gemini.

2. **Then Tier 1 in order of call frequency**:
   - `review_engine.py:5103` (voice-capture domain routing — fires on every capture)
   - `review_engine.py:2349` (multi-cue quiz generation — fires on every grade)
   - `review_engine.py:1283, 3438, 6106` (follow-up chips, entity confidence, other)
   - `research-server.py` live endpoints

3. **Then Tier 4 special cases** (`call_with_search`, `call_vision`) — consult user first on approach.

4. **Then Tier 2 batch scripts** — migrate in one pass.

5. **Tier 5** — optional, leave TODOs.

---

## How to verify

1. Syntax: `python3 -c "import ast; ast.parse(open('scripts/review_engine.py').read())"` after each file.
2. Grep: `grep -rn "from gemini_llm" scripts/ | grep -v experiments/` should shrink monotonically.
3. End-to-end on the entity-question pipeline (the one that broke for Khomeini):
   ```
   ssh alif "cd /opt/petrarca && python3 -c '
   import sys; sys.path.insert(0, \"scripts\")
   from db import get_connection
   from review_engine import generate_entity_question
   c = get_connection(readonly=True)
   q = generate_entity_question(\"ent:ruhollah_khomeini\", c)
   print(bool(q), list((q or {}).keys()))
   '"
   ```
   Should print `True` + keys including `temporal_hook`. No Gemini import in the stack trace of any error.

4. Spot-check that the research server still returns 200 on `/voice/calibration?limit=1` after deploy.

---

## What NOT to do

- Don't migrate Tier 3 (disabled subsystems) — dead code, waste of time.
- Don't remove `scripts/gemini_llm.py` itself yet — some Tier 5 experiments still need it, and a full removal risks breaking research code we don't need to touch.
- Don't change the shape of the data returned from any function. Callers expect `dict` / `str` — if Claude returns markdown-fenced JSON, strip fences in the migration, not in every caller.
- Don't add a Claude→Claude retry loop as a replacement for the Gemini fallback unless you measured Claude failure rates first. One retry with 10s backoff is fine; more is masking a different problem.

---

## Deliverables

1. Updated files in scope — each file's import line changed + any shape adjustments.
2. New `scripts/claude_llm.py` functions if needed: `call_vision`, `call_chat`, optionally `call_with_search`.
3. A short report: file, old call sites count, new call sites count, any behavior changes noted.
4. One commit per tier (or one commit total if kept small). Branch `sh/gemini-to-claude`.
5. Deploy via `bash ~/src/expo/scripts/deploy.sh petrarca` — the deploy.sh now checks server-side git cleanliness (added this session), so pre-existing server edits will abort cleanly.

---

## Context pointers

- Directive memory: `/Users/stian/.claude/projects/-Users-stian-src-petrarca/memory/feedback_claude_only_never_gemini.md`
- Claude wrapper: `scripts/claude_llm.py` (already has `call_claude`, `call_claude_json`, caching, etc.)
- The incident that triggered this: Session 86→87 Iran Revolution capture, Khomeini `cached_question=NULL` due to Gemini 429 at 15:01:43 UTC 2026-04-20.
- CLAUDE.md § "LLM Calling Discipline" — note the old "Gemini for interactive, claude -p for batch" rule is now superseded.
