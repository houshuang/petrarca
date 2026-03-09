# Petrarca Overnight System Report
**Date**: March 8, 2026

## Executive Summary

The novelty-aware reading system has been built end-to-end and validated against 47 real articles (858 atomic claims). The core pipeline works: articles are decomposed into atomic claims, claims are embedded, and knowledge tracking correctly identifies familiar vs novel content as a user reads sequentially. Delta reports accurately show what's new in a topic cluster. The system is ready for integration into the app.

## What Was Built

### 1. Atomic Claim Extraction Pipeline
**File**: `scripts/build_articles.py` (functions: `_build_atomic_decomposition_prompt`, `extract_atomic_claims`, `_fix_pronoun_starts`)

- Extracts 10-30 typed atomic claims per article via Gemini Flash
- 7 claim types: factual (60%), procedural (17%), evaluative (11%), causal (6%), experiential (2%), comparative (2%), predictive (1%)
- Post-processing fixes pronoun-started claims ("It is recommended..." → "Deploying X is recommended...")
- CLI flags: `--claims`, `--claims-only`, `--skip-claims`

**Quality**: Tested against 12 diverse fixtures (tech blogs, Wikipedia, academic papers, tweet threads, StackOverflow). All 12 pass 7/7 structural checks after prompt iteration.

### 2. Claim Embedding Pipeline
**File**: `scripts/build_claim_embeddings.py`

- Embeds all claims using `gemini-embedding-001` (3072 dimensions)
- Batched embedding (100 claims/batch, ~10 seconds total)
- Cosine similarity matrix for all 858×858 claim pairs
- Analysis: near-duplicate detection, EXTENDS candidate detection, topic clustering

**Key Finding**: Gemini embeddings produce lower cosine similarities than sentence-transformers. Related claims from overlapping articles peak at ~0.73 (vs ~0.90 with models like all-MiniLM). Thresholds calibrated: KNOWN ≥ 0.72, EXTENDS ≥ 0.62.

### 3. Reading Journey Simulator
**File**: `scripts/simulate_reading.py`

- Knowledge ledger tracking per-claim state (unknown → encountered → absorbed)
- Three reading scenarios: tech-focused, broad, sequential
- Delta report generator for topic clusters
- Paragraph dimming simulation for the reader UI
- HTML report generation following Annotated Folio design system

### 4. Pipeline Testing Framework Extension
**Files**: `scripts/pipeline-tests/lib/evaluator.py`, `scripts/pipeline-tests/lib/runner.py`, `scripts/pipeline-tests/run.py`

- Added `atomic_claims` test layer with 12 fixtures
- 7 deterministic structural checks: claim_count, required_fields, valid_claim_types, self_contained, no_empty_text, topics_present, no_compound_claims
- LLM-as-judge scoring (granularity, decontextualization, type_accuracy, coverage, topic_quality)

## Key Metrics

### Claim Extraction
| Metric | Value |
|--------|-------|
| Articles processed | 47 |
| Total claims | 858 |
| Avg claims/article | 18.3 |
| Min/Max claims | 7 / 34 |
| Test pass rate | 12/12 fixtures |
| Extraction time | ~10s/article |
| Cost | ~$0 (Gemini Flash free tier) |

### Embedding & Similarity
| Metric | Value |
|--------|-------|
| Embedding dimensions | 3072 |
| Cross-article pairs ≥ 0.90 | 1 (near-duplicate) |
| Cross-article pairs ≥ 0.75 | 195 (meaningful overlap) |
| Unique claim-level topics | 250 |
| Top topic (ai-agents) | 110 claims |

### Knowledge Tracking (Sequential Scenario — 15 articles)
| Metric | Value |
|--------|-------|
| First article novelty | 100% (all new) |
| Average novelty | 80.8% |
| Lowest novelty | 23.1% (article 10 — heavy overlap) |
| Final knowledge size | 254 claims |
| AI-agents coverage | 85.5% after 15 articles |
| Claude-code coverage | 91.7% after 15 articles |

## What Works Well

1. **Knowledge tracking is directionally correct**. After reading 3 Claude Code articles, the 4th (Ralph Wiggum) correctly shows 78.6% novelty. After 9 articles, the 10th (Research Toggle) shows 23.1% — it's almost all review.

2. **Delta reports are useful**. After tech-focused reading, the system correctly identifies:
   - `knowledge-management` at 17.1% coverage → "You should explore this topic more"
   - `claude-code` at 91.7% coverage → "You've mostly covered this"
   - Specific new claims per article for unread topics

3. **Claim extraction quality is high**. The prompt + post-processing produces well-typed, self-contained, atomic claims across diverse content types.

4. **Cross-article similarity detection works**. The DCG articles correctly show high overlap (0.83-0.87). The two Codified Context articles are detected as near-duplicates (0.90).

5. **Different reading paths produce different knowledge profiles**. The broad scenario leaves ai-agents at 31.8% covered (read fewer agent articles), while the tech scenario reaches 90.9%.

## Issues & Limitations

### 1. Embedding Threshold Sensitivity
The Gemini embedding model produces a narrow similarity range (mean 0.53, meaningful overlap at 0.62-0.73). This makes threshold tuning critical and potentially fragile. Recommendation: test with Nomic-embed-text-v1.5 (local, free) which typically produces a wider distribution.

### 2. EXTENDS vs KNOWN Is Hard to Distinguish
With cosine similarity alone, it's difficult to distinguish "this is the same claim" from "this extends/elaborates on a known claim." The architecture doc's plan for an LLM judge at the 0.65-0.75 boundary would help.

### 3. No CONTRADICTS Detection
The current system detects NEW, KNOWN, and EXTENDS but not CONTRADICTS. This requires comparing claim semantics, not just embedding similarity. Implementing this needs the LLM judge step.

### 4. Paragraph-to-Claim Mapping Is Imperfect
The `source_paragraphs` field in claims relies on the LLM's paragraph indexing, which can be inaccurate. This affects reader dimming quality. Could be improved with post-hoc alignment (embed paragraphs + match to claims).

### 5. High EXTENDS Rate
Many articles show 80-100% "novel" because EXTENDS claims count as novel. This is arguably correct (extending knowledge IS novel), but the UI needs to distinguish "genuinely new" from "elaboration on something you know."

### 6. Corpus Bias
47 articles heavily weighted toward Claude Code / AI agents. Couldn't expand locally without Readwise/Twitter credentials. Should be expanded on Hetzner server.

## Architecture Validation

The architecture doc (`research/novelty-system-architecture.md`) proposed:
1. ✅ **Extract → Normalize → Embed → Compare → Score** pipeline
2. ✅ **Atomic claim decomposition** via Gemini Flash
3. ✅ **Embedding-based similarity** for fast comparison
4. ⬜ **LLM judge** for ambiguous cases (0.65-0.75 range) — not yet implemented
5. ✅ **Knowledge ledger** per-claim state tracking
6. ✅ **Delta reports** for topic-level "what's new"
7. ✅ **Paragraph dimming** logic (novel=1.0, familiar=0.55)
8. ⬜ **sqlite-vec** storage — prototyped with numpy, production should use sqlite-vec on Hetzner
9. ⬜ **Nomic embeddings** — used Gemini embedding-001 instead (works but narrower similarity range)

## Files Created/Modified

### New Scripts
- `scripts/build_claim_embeddings.py` — Embedding pipeline + similarity analysis
- `scripts/simulate_reading.py` — Reading journey simulator + delta reports + HTML report
- `scripts/experiment_claim_extraction.py` — Standalone experiment script (from previous session)

### Modified Scripts
- `scripts/build_articles.py` — Added atomic decomposition prompt, claim extraction, pronoun post-processing
- `scripts/pipeline-tests/run.py` — Added `claims` CLI subcommand
- `scripts/pipeline-tests/lib/runner.py` — Added `run_atomic_claims()`, increased max_tokens to 8192
- `scripts/pipeline-tests/lib/evaluator.py` — Added `evaluate_claims_structure()`, calibrated tolerances

### Data Files
- `data/claim_embeddings.npz` — 858×3072 embedding matrix (10MB)
- `data/claims_index.json` — Claim metadata index
- `data/claim_analysis.json` — Full similarity analysis results
- `data/simulation_results.json` — Three scenario simulation results
- `data/reading_simulation_report.html` — Visual report (Annotated Folio styled)

### Test Fixtures (12)
Located in `scripts/pipeline-tests/fixtures/atomic_claims/`:
arxiv-paper, codinghorror, first-servile-war, frederick-ii-long, history-article, huggingface-model, martinfowler, mission-control-tech, paulgraham, simonwillison-blog, stackoverflow, tweet-thread

## Recommended Next Steps

### Immediate (deploy to app)
1. **Integrate claims into the Expo reader** — implement paragraph dimming based on knowledge state
2. **Run claims extraction on Hetzner** as part of the 4-hour cron pipeline
3. **Store embeddings in sqlite-vec** on Hetzner for persistent knowledge tracking
4. **Add "I knew this" / "New to me" buttons** in the reader to correct the model

### Short-term (improve quality)
5. **Test Nomic-embed-text-v1.5** locally on Hetzner — likely produces better similarity distribution
6. **Add LLM judge** for the 0.62-0.72 similarity range (EXTENDS vs KNOWN disambiguation)
7. **Expand corpus** — run pipeline on Readwise Reader + Twitter bookmarks via Hetzner cron
8. **Implement delta report UI** — the data structure is ready, needs a reader screen

### Medium-term (features)
9. **CONTRADICTS detection** — compare claim pairs where one negates the other
10. **Confidence decay** — reduce certainty of old knowledge over time
11. **Interest × Knowledge interaction** — prioritize articles with high interest AND high novelty
12. **Research agent integration** — use delta reports to identify knowledge gaps, trigger research
