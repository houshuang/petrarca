# Synthesis Pipeline Redesign: From Monolithic to Multi-Stage

## Problem Statement

The current synthesis pipeline makes a single LLM call per cluster that simultaneously:
1. Writes narrative prose (the synthesis markdown)
2. Self-reports article coverage percentages
3. Tags individual claim IDs as covered
4. Identifies unique contributions per article
5. Extracts tensions between sources
6. Generates follow-up research questions

This creates several problems:
- **Competing objectives**: The LLM prioritizes prose quality and half-asses structured fields
- **Self-reported coverage is unverifiable**: No ground truth check on "I covered 90%"
- **Claims tracking is fake**: LLM returns all or none; expansion logic papers over this
- **Non-deterministic quality**: Same cluster produces different headings, coverage, tensions
- **No intermediate artifacts**: Can't tell which step failed
- **Ignores existing infrastructure**: The knowledge index already computes claim similarities, novelty matrices, and delta reports — but the synthesis prompt barely uses them

## Existing Infrastructure (Already Computed)

The pipeline ALREADY produces rich per-article and cross-article analysis that the synthesis should consume, not re-derive:

### Per-Article (from `build_articles.py`)
- `atomic_claims[]` — each with ID, normalized text, claim_type, source paragraphs
- `key_claims[]` — high-level claims
- `topics[]`, `interest_topics[]` — broad + specific
- `entities[]` — people, methods, concepts
- `one_line_summary`, `full_summary`, `sections[]`

### Knowledge Index (from `build_knowledge_index.py`)
- **`similarities`** — 80,017 claim pairs with cosine scores (≥0.68 EXTENDS, ≥0.78 KNOWN)
- **`llm_verdicts`** — 200 LLM-judged ambiguous pairs (overrides for cosine 0.68-0.78 zone)
- **`article_novelty_matrix`** — for every article pair: `{new: N, extends: N, known: N}` — exactly how much new information article A adds beyond article B
- **`delta_reports`** — per-topic summaries: what's known, what's new, top claims by cross-article frequency
- **`paragraph_map`** — which paragraphs contain which claims (for paragraph-level dimming)
- **`article_claims`** — article_id → list of claim_ids

### Concept Clusters (from `build_concept_clusters.py`)
- `key_shared_claims[]` — claims appearing across multiple articles, ranked by cross-links
- `core_article_ids` — most connected articles in the cluster
- `internal_edges`, `avg_edge_weight` — graph connectivity metrics
- Per-article: `internal_degree`, `internal_weight`, `is_core`

### What This Means

**The novelty detection system already answers the key question**: "given that you've read article A, what does article B add?" The `article_novelty_matrix` gives exact counts of new/extends/known claims between every pair. The `key_shared_claims` identifies the claims that tie the cluster together. The `delta_reports` provide topic-level summaries.

**The synthesis pipeline should be a consumer of these artifacts, not a re-inventor.** Stage 1 of the original design ("per-article position extraction") was redundant — we already have claims, summaries, entities, and cross-article novelty data. The LLM's job should be to *narrate* pre-computed structure, not *discover* it.

## Cluster Profile

| Size | Count | Articles | Claims | Words |
|---|---|---|---|---|
| Large | 10 | 10-13 | 137-295 | 9K-22K |
| Medium | 12 | 7-9 | 137-244 | 8K-20K |
| Small | 4 | 2-3 | 19-41 | 500-13K |

26 clusters total. Model: `gemini-3-flash-preview`, 12288 max output tokens.

## Proposed Multi-Stage Pipeline

### Stage 0: Deterministic Pre-Computation (no LLM)

**Build the "synthesis brief"** from existing knowledge index data. This is the key insight — most of the analytical work is already done.

**Input**: cluster data + knowledge_index.json + articles.json
**Output**: `synthesis-stages/{cluster_id}/brief.json`

```json
{
  "cluster_id": "cluster_1",
  "label": "...",
  "article_count": 13,

  "novelty_graph": {
    "article_id_a": {
      "article_id_b": {"new": 11, "extends": 2, "known": 3}
    }
  },

  "shared_claims": [
    {
      "claim_id": "...",
      "text": "...",
      "article_ids": ["id1", "id2", "id3"],
      "cross_links": 28
    }
  ],

  "unique_claims_per_article": {
    "article_id": [
      {"claim_id": "...", "text": "...", "similarity_to_nearest": 0.45}
    ]
  },

  "high_tension_pairs": [
    {
      "claim_a": {"id": "...", "text": "...", "article_id": "..."},
      "claim_b": {"id": "...", "text": "...", "article_id": "..."},
      "similarity": 0.73,
      "llm_verdict": "EXTENDS"
    }
  ],

  "coverage_if_read_in_order": [
    {"article_id": "core_1", "marginal_new_claims": 29},
    {"article_id": "core_2", "marginal_new_claims": 18},
    {"article_id": "peripheral_3", "marginal_new_claims": 5}
  ]
}
```

**Key computations (all deterministic)**:
1. Extract novelty graph subset for this cluster from `article_novelty_matrix`
2. Identify shared claims (from `key_shared_claims` + similarity matrix within cluster)
3. Identify unique claims per article: claims with no similarity ≥0.68 to any other article's claims in the cluster
4. Find "high tension" pairs: claims with moderate similarity (0.68-0.78) between articles, especially where LLM verdicts disagree with cosine
5. Compute reading order by marginal information gain (greedy: pick article adding most new claims at each step)

**This stage is fast, deterministic, and produces the core analytical artifact that everything else builds on.**

### Stage 1: Tension Narration (LLM, parallel)

**Input**: High-tension claim pairs from Stage 0, plus relevant article excerpts
**Output**: Structured tension descriptions

For each high-tension pair (or group of related pairs):
```json
{
  "label": "Efficiency vs. Time Consumption",
  "description": "Article A argues X while Article B contends Y...",
  "side_a": {"article_ids": [...], "claim_ids": [...]},
  "side_b": {"article_ids": [...], "claim_ids": [...]},
  "type": "disagreement|emphasis|methodology|scope"
}
```

**Why LLM**: The knowledge index identifies *which* claims are in tension (moderate similarity, different articles) but can't articulate *what the tension is about* in human-readable terms. This is a focused task: "here are two claims that seem related but different — describe the tension."

**Can parallelize**: Each tension pair/group is independent.

**Model**: Flash Lite (small focused prompt, structured output)

### Stage 2: Outline & Theme Organization (LLM, sequential)

**Input**: Synthesis brief (Stage 0) + narrated tensions (Stage 1) + article summaries
**Output**: `synthesis-stages/{cluster_id}/outline.json`

```json
{
  "title": "Descriptive synthesis title",
  "sections": [
    {
      "heading": "Descriptive heading (not 'Overview' or 'Shared Themes')",
      "theme_summary": "What this section argues",
      "primary_articles": ["id1", "id2"],
      "supporting_articles": ["id3"],
      "shared_claims_to_weave": ["claim_id_1", "claim_id_2"],
      "unique_claims_to_highlight": ["claim_id_5"],
      "tensions_to_embed": [0],
      "suggested_research_question": "..."
    }
  ]
}
```

**Deterministic validation after this stage**:
- Every article appears in at least one section
- Every high-cross-link shared claim is assigned to a section
- Tensions are distributed (not all in one section)
- No banned heading names ("Overview", "Shared Themes", "Unique Contributions")

**Model**: Flash

### Stage 3: Prose Generation (LLM, parallel by section)

**Input**: One section from outline + relevant article excerpts + specific claims to reference + tensions to embed
**Output**: 2-3 paragraphs with `[Title](article:ID)` links

Each section call gets a focused brief:
- "Write about [theme]. Your primary sources are [articles]. Weave in these shared insights: [claims]. Embed this tension: [narrated tension from Stage 1]. Reference articles using these exact links: [reference key]."

**Why per-section**: Smaller context, more focused task, deterministic article references. Each section is independent → parallel.

**Model**: Flash. Could use Pro for the opening section of large clusters.

### Stage 4: Assembly & Verification (deterministic + LLM)

**Deterministic assembly**:
1. Concatenate section prose with headings
2. Verify all `[Title](article:ID)` links resolve to real articles
3. Check: tension blocks present, no banned headings, minimum paragraph count

**LLM verification** (separate "reader" call):
- Input: final synthesis + list of claims per article
- Output: which claims are actually discussed (even paraphrased)
- This is the *reader grading the writer's work*

**Coverage computation** (deterministic):
- For each article: what fraction of its claims are either directly referenced or within the claim similarity neighborhood of a referenced claim?
- Uses the same similarity matrix already in the knowledge index

**Follow-up questions** (LLM, parallel with verification):
- Input: synthesis + tensions + article metadata
- Output: research questions with search prompts

**Output**: Final `syntheses.json` entry with verified coverage, plus `synthesis-stages/{cluster_id}/report.json` with full diagnostics.

## Intermediate Artifacts

Each cluster gets a directory: `synthesis-stages/{cluster_id}/`

```
brief.json          — Stage 0: deterministic pre-computation
tensions.json       — Stage 1: narrated tension pairs
outline.json        — Stage 2: theme organization
sections/           — Stage 3: individual section prose
  section_0.md
  section_1.md
  ...
assembled.md        — Stage 4: stitched final synthesis
verification.json   — Stage 4: coverage check + format compliance
report.json         — Full pipeline report (timing, token usage, quality scores)
```

Every stage is independently inspectable and retriable.

## Comparison

| Aspect | Current (monolithic) | Proposed (multi-stage) |
|---|---|---|
| LLM calls per cluster | 1 | 4-8 (many parallel) |
| Deterministic work | Minimal | Stage 0 does heavy lifting |
| Uses knowledge index | Passes as context, LLM ignores | Pre-computes from it (Stage 0) |
| Coverage accuracy | Self-reported | Post-hoc verified by separate model + similarity matrix |
| Tension quality | Afterthought in prose | First-class artifact from claim pairs |
| Format consistency | Non-deterministic | Outline constrains prose, deterministic checks |
| Debuggability | Black box | 6 intermediate artifacts |
| Retry granularity | Redo everything | Retry just the failed stage |
| Cacheability | None | Stage 0-1 cached across prompt iterations |

## Implementation Plan

### Phase A: Stage 0 (deterministic brief builder)
- Extract novelty graph, shared claims, unique claims, tension pairs from knowledge index
- Compute marginal reading order
- Save brief.json per cluster
- **Validate**: inspect briefs for 3-4 clusters, check tension pairs make sense

### Phase B: Stages 1-2 (tensions + outline)
- Implement tension narration (parallel)
- Implement outline generation
- **Validate**: compare outlines against current synthesis headings
- Deterministic outline checks (article coverage, tension distribution)

### Phase C: Stages 3-4 (prose + assembly)
- Per-section prose generation (parallel)
- Assembly with verification
- Coverage computation using similarity matrix
- **Validate**: A/B compare against current monolithic output for 3-4 clusters

### Phase D: Full rollout
- `--pipeline` flag on generate_syntheses.py
- Run all 26 clusters through new pipeline
- Generate comparison report

## Open Questions

1. **Section-level vs. full-document prose**: Per-section is more deterministic but risks losing narrative flow. Mitigation: pass previous section summaries as context to each subsequent section?
2. **Caching strategy**: Stage 0 output is deterministic given knowledge index — cache it. Stage 1 tensions could also be cached. This means prompt iteration on Stages 2-3 is cheap.
3. **Model mixing**: Flash Lite for extraction (Stages 1, 4-questions), Flash for reasoning (Stages 2, 3), Pro for complex cluster prose?
4. **Claim-level vs article-level coverage for feed filtering**: Currently using article-level (80% threshold). Claim-level would be more precise but may not change behavior much.
