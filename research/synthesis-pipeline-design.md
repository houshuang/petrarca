# Cross-Article Synthesis Pipeline Design

**Date**: March 12, 2026 (Session 17)
**Status**: In progress — clustering + synthesis generation built, pipeline integration + client pending
**Coherence**: Extends `novelty-system-architecture.md` Phase 4 (Delta Reports → full Synthesis), implements patterns from `article-synthesis-prior-art.md` and `multi-article-synthesis-systems.md`

---

## Motivation

The user bookmarks 10+ tweets/articles about a topic (e.g., Karpathy's autoresearch, AI agent orchestration). Currently these appear as 10+ separate feed items across fragmented topics ("ai orchestration", "ai coding tools", "ai agents", "autonomous agents", etc.). The vision:

1. **Open Petrarca → see ONE synthesis** of the concept cluster, drawing from all related sources
2. **Dispatch researchers** from auto-suggested follow-up questions
3. **Reading the synthesis marks all source articles as "read"** (their claims populate the knowledge ledger)
4. **New bookmarks assessed against this knowledge** — automatically, via existing claim-level cosine similarity

## Investigation Findings (March 12)

### Article Quality Audit

Analyzed 273 articles, 24 AI/coding-related. Key findings:

| Issue | Count | Impact |
|-------|-------|--------|
| X.com JavaScript error pages | 26 | Junk articles polluting feed + embeddings |
| Exact duplicates | 5 pairs | Redundant LLM processing |
| Near-duplicates (>80% claim overlap) | 2 pairs | Cluttered feed |
| Missing entity extraction | 6/24 AI articles | Broken cross-referencing |
| Topic fragmentation | 11 different AI topics | Synthesis impossible via topic grouping |
| Missing referenced content | karpathy/autoresearch repo not ingested | Incomplete picture |

### What Already Existed

| Component | Status | Gap |
|-----------|--------|-----|
| Claim-level similarity (99,572 pairs) | ✅ Working | — |
| Article novelty matrix | ✅ Working | Not used for clustering |
| Delta reports (425 topics) | ✅ Working | Per-topic, not per-concept-cluster |
| `generate_syntheses.py` | ⚠️ Stale (2 outputs from Mar 3) | Uses old `topics[0]`, not in pipeline |
| `TopicSynthesis` TypeScript type | ⚠️ Defined but unused | Minimal fields |
| Cross-article connections in reader | ✅ Working | Individual article context only |
| Research dispatch | ✅ Working | Per-article, not per-synthesis |
| Knowledge ledger (FSRS) | ✅ Working | Only populated per-article reading |
| `experiment_cross_article_links.py` | ⚠️ Experimental | Not integrated |

### Specific Karpathy Content Analysis

- **AgentHub** (265493334801): 10 claims, well-extracted GitHub README. Karpathy entity detected.
- **autoresearch-anything** (c8ab96e1fd55): 10 claims, well-extracted. Karpathy entity detected.
- **Zero claim-level similarity between these two** — they describe different projects. But they connect through intermediate articles (Claude Code guides, agent orchestration) forming a natural cluster.
- **karpathy/autoresearch** (the original project both reference) is NOT ingested — a gap.

## Architecture: Concept Clusters → Syntheses → Knowledge Propagation

### Pipeline Flow (extends existing cron)

```
Existing pipeline:
  fetch bookmarks → build_articles → validate → extract entities → claims → embeddings → knowledge_index

New steps (after knowledge_index):
  → build_concept_clusters.py    # Graph-based article clustering
  → generate_syntheses.py        # LLM synthesis per cluster
  → cleanup_articles.py --fix    # Remove junk + merge duplicates
  → Deploy concept_clusters.json + syntheses.json via nginx
```

### Step 1: Concept Cluster Detection (`build_concept_clusters.py`) — BUILT

Algorithm:
1. Build undirected article graph from `article_novelty_matrix`
   - Edge weight = EXTENDS + KNOWN shared claims between article pair
   - Threshold: ≥ 3 shared claims for an edge
2. Find connected components (BFS)
3. Split large components (>15 articles) via spectral bisection (Fiedler vector of normalized Laplacian), with topic-based fallback
4. Detect near-duplicates (>80% claims KNOWN)
5. Generate LLM cluster labels via `gemini_llm.call_llm()`

Results on 273 articles:
- 30 clusters, 231 articles assigned
- AI/coding → 4 clusters: Orchestration+Tooling (11), Building+Coding Agents (10), Agentic Workflows (9), Architectural Foundations (6)
- 328 near-duplicate pairs detected

### Step 2: Synthesis Generation (`generate_syntheses.py`) — BUILT (rewrite)

For each cluster (2+ articles):
1. Collect all article summaries, key claims, atomic claims (with IDs), sections
2. Load cross-article similarities from knowledge index
3. Generate structured synthesis via `gemini-2.0-flash`:
   - Narrative overview (3-8 paragraphs)
   - Shared themes with source attribution
   - Unique contributions per article
   - Tensions/disagreements
   - 5 follow-up questions with research prompts
   - Claim coverage map (which claim IDs are covered)
   - Per-article value capture estimate (e.g., "85% of Article X's value is in this synthesis")

Output per synthesis:
```json
{
  "cluster_id": "cluster_3",
  "label": "AI Agent Orchestration",
  "synthesis_markdown": "## Overview\n\n...",
  "article_ids": ["abc", "def", ...],
  "article_coverage": {"abc": 0.85, ...},
  "claims_covered": ["claim_1", "claim_2", ...],
  "unique_per_article": {"abc": ["Only article discussing..."], ...},
  "follow_up_questions": [{"question": "...", "research_prompt": "...", "related_topics": [...]}],
  "tensions": ["Source A says X while B argues Y"],
  "total_articles": 11,
  "total_claims_covered": 85,
  "total_claims_in_cluster": 187
}
```

Incremental: only regenerates clusters with changed article sets.

### Step 3: Junk Cleanup (`cleanup_articles.py`) — BUILT

Detects and removes:
- X.com JavaScript error pages (regex patterns)
- Articles under 80 words
- Content-hash duplicates (keeps better version by quality score)
- Claim-overlap duplicates (>90% KNOWN)

Guards added to `build_articles.py`:
- `_validate_content()` rejects junk BEFORE LLM processing (saves API costs)
- Content hash dedup against existing articles

### Step 4: Client Integration — TODO

Required changes:
1. **Load syntheses**: `content-sync.ts` fetches `syntheses.json` alongside articles/knowledge_index
2. **TopicSynthesis type**: DONE — expanded with cluster_id, label, article_coverage, claims_covered, follow_up_questions, tensions
3. **Synthesis in feed**: Special "synthesis card" in Topics lens or as a first-class feed item when a cluster has 3+ articles
4. **Synthesis reader**: Either reuse reader.tsx (treat synthesis_markdown as article content) or new screen
5. **Bulk mark-read**: When user finishes reading a synthesis, iterate `claims_covered` and call `markClaimEncountered()` for each — same FSRS stability as 'read' engagement (30 days)
6. **Follow-up dispatch**: Render follow_up_questions as tappable prompts that call `/research/topic` with the research_prompt
7. **New bookmark assessment**: Already works automatically — once claims are in ledger, new articles' claims are compared via cosine similarity

### Step 5: Missing Content Ingestion — TODO

- Ingest `karpathy/autoresearch` GitHub repo (the original project)
- Re-ingest Claude Code best practices (current article has wrong content due to redirect)
- Consider auto-ingesting referenced GitHub repos from tweet-linked READMEs

## Relationship to Existing Architecture

This design fulfills several planned-but-unbuilt features from `novelty-system-architecture.md`:

| Planned Feature | Status | This Implementation |
|----------------|--------|-------------------|
| Delta Reports (G5) | ✅ Built (per-topic) | Extended to per-cluster syntheses |
| Structured Comparison (G18) | ❌ Not built | `unique_per_article` + `tensions` fields partially cover this |
| Blindspot Detection (G19) | ❌ Not built | `total_claims_covered / total_claims_in_cluster` ratio indicates coverage gaps |
| Sub-topic Splitting | ✅ In delta reports only | Clusters naturally split broad topics |
| Cross-article connections | ✅ In reader | Synthesis provides the unified view |
| Research agents | ✅ Topic research | Follow-up questions with research_prompts |

## Design Decisions

1. **Graph clustering over topic grouping**: Topics are too fragmented (11 AI topics). Graph-based clustering using claim similarity finds natural groupings that cross topic boundaries.

2. **Synthesis as a reading unit, not a summary**: The synthesis is meant to be READ, not just scanned. It should be 3-8 paragraphs of narrative, not bullet points. After reading, the user should feel they've absorbed the key insights from all source articles.

3. **Claim-level knowledge propagation**: Reading a synthesis populates the knowledge ledger with ALL covered claims from ALL source articles. This is the key mechanism that makes "mark as read" work — it's not marking articles as read, it's marking CLAIMS as encountered.

4. **Per-article coverage estimate**: Not all articles are fully captured by a synthesis. An article with 60% coverage still has unique value worth reading directly. The UI should indicate "You've absorbed 85% of this article's key insights from the synthesis."

5. **Incremental synthesis**: Only regenerate when cluster membership changes. This keeps the pipeline fast and avoids unnecessary LLM calls.

## Known Limitations

- Synthesis quality depends on LLM's ability to integrate 10+ articles coherently
- Very large clusters (>15 articles) need context truncation — peripheral articles may be under-represented
- Claim coverage estimates are LLM-generated, not verified
- No contradiction detection yet (deferred from novelty architecture)
- Clusters are recomputed from scratch each run (no incremental graph update)

## Validation Results (March 12)

### Before fix: LLM claim coverage was 5-10% (severely underpowered)
### After fix: Post-processing expanded coverage via article_coverage + similarity matrix

| Cluster | Articles | Claims Covered | Coverage |
|---------|----------|----------------|----------|
| ai-coding-tools (with Karpathy) | 11 | 151/157 | 96% |
| ai-orchestration | 10 | 135/150 | 90% |
| llm-applications | 9 | 98/112 | 88% |
| ai-coding-tools (smaller) | 6 | 69/69 | 100% |

**Total: 21 syntheses, 157 articles covered, 2,637 claims covered.**

The fix: if article_coverage >= 0.6, include ALL claims from that article. Then cascade via similarity matrix (claims with >= 0.78 cosine to any covered claim get included). This expanded LLM-tagged 28 claims → 151 claims for the main AI cluster.

### Data Cleanup Results
- Removed 36 articles (29 junk + 7 duplicates) → 237 remaining
- No more X.com JavaScript error pages
- Pipeline guards prevent future junk ingestion

## Model Comparison (March 12)

Tested 6 Gemini models on cluster 3 (Sicily, 11 articles, ~32K input tokens). Script: `scripts/compare_synthesis_models.py`.

### Results — Cluster 3 (Sicily)

| Model | Time | Cost | Sections | Claims Tagged | Avg Coverage | Title Refs | Claim Refs | Questions | Tensions |
|-------|------|------|----------|---------------|--------------|------------|------------|-----------|----------|
| 2.0 Flash | 17s | $0.004 | 5/5 | 20/237 | 45% | 11 | 0 | 5 | 2 |
| 2.5 Flash Lite | 20s | $0.007 | 5/5 | 138/237 | 74% | 1 | 0 | 5 | 2 |
| 3.1 Flash Lite | 11s | $0.011 | 5/5 | 14/237 | 78% | 0 | 0 | 5 | 3 |
| 2.5 Flash | 38s | — | — | — | — | — | — | — | — |
| 3 Flash | 30s | $0.024 | 5/5 | 27/237 | 81% | 4 | 10 | 5 | 5 |
| 2.5 Pro | 64s | $0.076 | 5/5 | 14/237 | 49% | 7 | 0 | 5 | 2 |

**Pricing** (per 1M tokens): 2.0 Flash ($0.10/$0.40), 2.5 Flash Lite ($0.15/$0.60), 3.1 Flash Lite ($0.25/$1.50), 2.5 Flash ($0.30/$2.50), 3 Flash ($0.50/$3.00), 2.5 Pro ($1.25/$10.00).

### Results — Cluster 4 (AI Coding Tools, 11 articles, ~23K tokens)

| Model | Time | Cost | Sections | Claims Tagged | Avg Coverage | Title Refs | Claim Refs | Questions | Tensions |
|-------|------|------|----------|---------------|--------------|------------|------------|-----------|----------|
| 2.0 Flash | 31s | $0.004 | 5/5 | 157/157 | 59% | 10 | 0 | 5 | 2 |
| 2.5 Flash Lite | 20s | $0.006 | 5/5 | 98/157 | 67% | 11 | 0 | 5 | 1 |
| 3.1 Flash Lite | 10s | $0.009 | 5/5 | 18/157 | 78% | 4 | 0 | 5 | 2 |
| 2.5 Flash | 34s | — | FAIL | — | — | — | — | — | — |
| 3 Flash | 27s | $0.020 | 5/5 | 24/157 | 81% | 0 | 0 | 5 | 4 |
| 2.5 Pro | 54s | — | FAIL | — | — | — | — | — | — |

### Results — Cluster 12 (AI Orchestration, 10 articles, ~25K tokens)

| Model | Time | Cost | Sections | Claims Tagged | Avg Coverage | Title Refs | Claim Refs | Questions | Tensions |
|-------|------|------|----------|---------------|--------------|------------|------------|-----------|----------|
| 2.0 Flash | 16s | $0.003 | 5/5 | 17/150 | 67% | 0 | 0 | 5 | 0 |
| 2.5 Flash Lite | 26s | $0.006 | 5/5 | 252/150 | 74% | 0 | 0 | 5 | 2 |
| 3.1 Flash Lite | 9s | $0.009 | 5/5 | 18/150 | 84% | 0 | 0 | 5 | 2 |
| 2.5 Flash | 33s | — | FAIL | — | — | — | — | — | — |
| 3 Flash | 26s | $0.019 | 5/5 | 21/150 | 83% | 0 | 11 | 5 | 4 |
| 2.5 Pro | 69s | — | FAIL | — | — | — | — | — | — |

### Cross-Cluster Analysis

**Reliability**: 2.5 Flash failed on ALL 3 clusters. 2.5 Pro failed on 2/3. Both eliminated.

**Per-model strengths** (consistent across clusters):
- **2.0 Flash**: Cheapest ($0.003-0.004), fast (15-31s), good title refs on some clusters. But wildly inconsistent — 157/157 claims on one cluster, 17/150 on another. 0 tensions on cluster 12.
- **2.5 Flash Lite**: Best at claim tagging (98-252), cheap ($0.006). But 0 title refs on AI clusters.
- **3.1 Flash Lite**: Fastest (9-11s), highest coverage estimates (78-84%). But generic output — 0 title/claim refs on AI clusters.
- **3 Flash**: Best at claim ID inline citations (10-11), tensions (4-5), richest formatting. But 5-6× costlier, 0 title refs on AI clusters.

### Conclusion: Single Model + Better Prompting

Multi-model not worth it because:
1. **Post-processing dominates claim coverage** — even 14 LLM-tagged claims expand to 88-100% via article_coverage + similarity cascade
2. **Narrative quality differences are prompt-addressable** — 2.0 Flash gets 10-11 title refs on some clusters, 0 on others → prompt consistency issue, not model capability
3. **Cost difference is negligible** — $0.09 total across 30 clusters
4. **2-model pipeline adds complexity** with marginal gain

**Decision: Switch to Gemini 3 Flash + tool calling + improved prompt.**

### Prompt Iteration (March 12 — Later)

The original prompt was the bottleneck, not the model. Two changes:

1. **Improved prompt**: Stronger instructions for title references ("Name source articles in EVERY paragraph"), claim ID citations ("cite IDs inline: [claim_id]"), and tension detection ("different emphases count, aim for 3-5"). Results: claim ID refs went from 0 to 10-20, tensions from 0-2 to 4-5.

2. **Tool calling instead of raw JSON**: Define a `submit_synthesis` FunctionDeclaration with the schema. The model fills in structured fields, the API handles serialization. No more JSON parsing failures — completely eliminates the "Expecting ',' delimiter" errors that plagued raw JSON. `response_mime_type="application/json"` was tried and made things *worse* (more models failed). Tool calling is strictly superior.

Dynamic objects (`article_coverage`, `unique_per_article`) converted from `{id: value}` dicts to arrays of `{article_id, coverage}` objects because Gemini schemas can't express dynamic keys. Normalize back to dicts in post-processing.

Final model: **gemini-3-flash-preview** with tool calling. Cost: ~$0.02/synthesis, $0.60 for all 30 clusters.

## Completed Steps

1. ✅ Build concept clustering — `build_concept_clusters.py`
2. ✅ Build enhanced synthesis generation — `generate_syntheses.py` (rewrite)
3. ✅ Build cleanup script + pipeline guards — `cleanup_articles.py` + `_validate_content()` in build_articles.py
4. ✅ Integrate into cron pipeline — content-refresh.sh updated
5. ✅ Client: load + display syntheses — store.ts, content-sync.ts, synthesis-reader.tsx
6. ✅ Client: bulk mark-read on synthesis completion — markClaimsEncountered() in knowledge-engine.ts
7. ✅ Client: follow-up question dispatch — spawnTopicResearch() from synthesis reader
8. ✅ Deploy to server — scripts, data, web build all deployed
9. ✅ Validate end-to-end — 21 syntheses generated, AI clusters verified

## Remaining TODO

1. **Ingest missing content** — karpathy/autoresearch repo, Claude Code best practices (wrong content due to redirect)
2. **Synthesis design polish** — the synthesis reader is functional but could benefit from design-explorer mockup review
3. **Article coverage indicator in feed** — implemented but needs real usage to verify visibility
4. **Duplicate cluster labels** — two clusters named "ai-coding-tools" (11 and 6 articles). Consider merging or differentiating labels.
