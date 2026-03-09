# Novelty-Aware Reading System — Architecture Design

**Date**: March 7, 2026
**Status**: Design complete, ready for prototyping
**Research base**: 8 research documents from deep literature review (see list at bottom)

---

## Problem Statement

Stian bookmarks ~50 articles/week from Twitter and Readwise. Many share overlapping content — the same AI news rewritten 10 ways. The system needs to:

1. **Determine what's genuinely new** in each article, given everything already read
2. **Surface only the novel parts** — guiding the reader to skip familiar content
3. **Synthesize across articles** — combine 20 Claude Code articles into a topical delta report
4. **Capture interest signals** — lightweight gestures while reading that improve future ranking

These are two independent axes:
- **Interest** (what to show more of) — fed by user signals → controls feed ranking
- **Knowledge** (what's already known) — derived from reading history → controls novelty scoring

---

## Core Design Decisions

### 1. The fundamental unit is the ATOMIC CLAIM, not the article

Knowledge state tracks claims, not articles. A reader who encounters a claim via Article 7 or via a synthesis report has the same knowledge state. This mirrors Bayesian Knowledge Tracing from education, where the atom is a skill/concept, not a lesson.

### 2. Delta-only reports (not full updated syntheses)

When new articles arrive on a topic the user has already read about, generate a "What's new since your last read" report — NOT a full updated synthesis that merges old and new. Link back to previous reports for context.

### 3. Dim, don't hide familiar content

In the reader, familiar paragraphs get reduced opacity (0.55), not hidden. This preserves context while directing attention. Constrained highlighting (~150 words flagged as "new") improves comprehension over highlighting everything (CHI 2024 Best Paper).

### 4. Extract-then-synthesize, not stuff-and-summarize

Research shows GPT-4 only partially synthesizes when given multiple documents raw (TACL 2024). Instead: extract atomic claims from each article independently, align claims across articles, THEN synthesize from the aligned claims.

---

## Data Model

### AtomicClaim

```typescript
interface AtomicClaim {
  id: string;                    // unique identifier
  source_article_id: string;     // which article this came from
  source_paragraphs: number[];   // paragraph indices for attribution

  // The claim in normalized natural language
  normalized_text: string;       // decontextualized, canonical form
  original_text: string;         // as it appeared in the article

  // Classification
  claim_type: 'factual' | 'causal' | 'comparative' | 'procedural'
            | 'evaluative' | 'predictive' | 'experiential';

  // Structured fields (optional, depending on type)
  subject?: string;              // canonicalized entity
  predicate?: string;            // normalized relation
  object?: string;               // canonicalized entity/value

  // Topic linkage
  topics: string[];              // from interest_topics hierarchy

  // Embedding for retrieval
  embedding: number[];           // Nomic-embed-text-v1.5, 768 dimensions

  // Extraction metadata
  extracted_at: string;          // ISO timestamp
  extraction_model: string;      // "gemini-2.0-flash"
}
```

### KnowledgeState (per claim, per user)

```typescript
interface KnowledgeState {
  claim_id: string;
  status: 'unknown' | 'encountered' | 'absorbed';
  encountered_via: string;       // article_id or delta_report_id
  encountered_at: string;        // ISO timestamp
  confidence: number;            // 0-1, decays over time
  user_marked_known?: boolean;   // explicit "I knew this" signal
  user_marked_interesting?: boolean; // explicit interest signal
}
```

### DeltaReport

```typescript
interface DeltaReport {
  id: string;
  topic_cluster: string;         // e.g., "claude-code", "ai-orchestration"
  generated_at: string;
  previous_report_id?: string;   // link to last report on this topic
  source_article_ids: string[];  // articles contributing to this report

  sections: {
    whats_new: ClaimGroup[];           // NEW claims grouped by subtopic
    where_sources_disagree: ClaimPair[]; // CONTRADICTS pairs
    blindspots: string[];              // topics with articles but few absorbed claims
    structured_comparison?: ComparisonMatrix; // Elicit-style matrix
  };

  // Each ClaimGroup contains:
  // - subtopic label
  // - summary sentence (generated)
  // - list of atomic claims with source_paragraph anchors
  // - "Read full article →" links
}
```

---

## Pipeline Architecture

### Phase 1: Article Ingestion (per article, at pipeline time)

**Step 1: Atomic Decomposition** (1 Gemini Flash call per article)

Prompt pattern (based on FActScore/Claimify research):
```
Given this article, extract all knowledge contributions as atomic claims.
Each claim should be:
- MINIMAL: one single assertion (not compound)
- SELF-CONTAINED: understandable without the article context
- TYPED: classify as factual/causal/comparative/procedural/evaluative/predictive/experiential

For each claim, provide:
- normalized_text: the claim in canonical form
- claim_type: one of the types above
- source_paragraphs: which paragraph numbers contain this claim
- topics: relevant topic tags (use the existing topic hierarchy where possible)

Article text:
{article_markdown}
```

Expected output: 10-30 atomic claims per article.

**Step 2: Embedding** (local, free)

- Embed each claim's `normalized_text` using Nomic-embed-text-v1.5
- Run locally on Hetzner server (100+ queries/sec on modern CPU)
- Store in sqlite-vec alongside the claim data

**Step 3: Novelty Scoring** (per claim of new article)

```
For each new claim:
  1. Topic routing: filter to same broad topic (free, instant)
  2. Embedding search: top-5 nearest neighbors in sqlite-vec (<1ms)
  3. Classify:
     - similarity > 0.9 → KNOWN (high confidence duplicate)
     - similarity < 0.5 → NEW (clearly novel)
     - similarity 0.5-0.9 → LLM judge call (Gemini Flash):
       "Given existing claim X and new claim Y, classify as:
        KNOWN (same information), EXTENDS (adds detail to known),
        CONTRADICTS (disagrees with known), or NEW (genuinely different)"
```

Cost: ~$0/month. Embeddings are local. LLM judge only for ambiguous cases (~5-10% of claims).

### Phase 2: Delta Report Generation (periodic, per topic cluster)

Triggered when: enough new claims accumulate in a topic cluster (e.g., 10+ NEW claims).

```
1. Collect all NEW/EXTENDS/CONTRADICTS claims in the topic since last report
2. Group by subtopic (using topic tags or secondary clustering)
3. For each subtopic group:
   a. Generate a 1-2 sentence summary from the claims
   b. Select the best source paragraph for each claim
   c. Note which articles contribute
4. Check for blindspots: topics with many articles but few NEW claims → user might be saturated
5. Generate the DeltaReport structure
6. One Gemini Flash call for the summaries (~5-10 calls total per report)
```

### Phase 3: Knowledge State Updates

When the user reads anything:
- Reading an article → mark all its claims as "encountered"
- Reading a delta report → mark the claims it contains as "encountered"
- "I knew this" tap → mark claim as "absorbed" with high confidence + backfill related claims
- Confidence decays over time (30-day half-life, matching existing interest model decay)

---

## Reader UI Design

### Individual Article View

Based on research from Scim (IUI 2023), CiteSee (CHI 2023), and Brusilovsky's adaptive hypermedia:

1. **"What's new for you" card** at top — bullet list of NEW claims (existing feature, enhanced)
2. **Paragraph-level dimming** — paragraphs containing only KNOWN claims get opacity 0.55
3. **Novel section markers** — paragraphs with NEW claims get a subtle green left border (2px, matching claim card style)
4. **Scrollbar minimap** — colored dots on the scrollbar showing where novel content is located
5. **"Show only new" toggle** — collapses familiar sections (stretchtext-style), expandable on tap
6. **Claim interaction** — tap a novel claim marker to see: the atomic claim, related articles, "I knew this" button

### Delta Report View

New screen/tab, Renaissance design language:

1. **Header**: "✦ What's new in [topic]" + date range + article count
2. **Double rule** (signature element)
3. **Subtopic sections**: Each with:
   - Subtopic heading (EB Garamond, rubric)
   - Summary sentence (Crimson Pro)
   - Source paragraphs from articles (with attribution: "From: [article title]")
   - "Read full article →" link per source
4. **Where sources disagree** section (if any CONTRADICTS claims)
5. **Previous reports** link: "← Previously: [report from March 1]"
6. **Structured comparison** (expandable): Elicit-style matrix view

### Signal Capture (interest signals while reading)

Current signals + new claim-level signals:
| Action | Weight | What it feeds |
|--------|--------|---------------|
| Swipe right (keep) | 1.0 | Interest model (topics) |
| Swipe left (dismiss) | 0.5 neg | Interest model (topics) |
| Open article | 0.5 | Interest model (topics) |
| Tap Done | 1.5 | Interest + Knowledge (mark claims encountered) |
| Highlight paragraph | 1.0 | Interest model (topics of highlighted claims) |
| Interest chip [+]/[-] | 2.0 | Interest model (specific topic level) |
| "I knew this" on claim | — | Knowledge model (mark claim absorbed, correct model) |
| "Tell me more" on claim | 2.0 | Interest + triggers research agent |
| Time spent on section | 0.3 | Passive interest signal |

---

## Technology Stack

### Backend (Hetzner server)
- **LLM**: Gemini 2.0 Flash (existing) — for atomic decomposition + LLM judge
- **Embeddings**: Nomic-embed-text-v1.5 — local, free, multilingual, 8192 tokens
- **Vector store**: sqlite-vec — embedded, zero-config, single .db file
- **Claim store**: SQLite (same db) — relational queries + vector search together
- **Pipeline**: Python, extends existing `build_articles.py`

### Frontend (Expo app)
- Claims data served via nginx as JSON (same pattern as articles.json)
- Knowledge state persisted to AsyncStorage (same pattern as interest model)
- Reader enhancements: paragraph-level dimming, scrollbar markers, claim interaction

### Scale
- ~50 articles/week × ~20 claims/article = ~1,000 claims/week
- ~52,000 claims/year, ~260,000 over 5 years
- sqlite-vec handles millions; this is trivially small
- Entire knowledge base: <50MB including embeddings

---

## Implementation Plan

### Experiment 0: Validate atomic decomposition (FIRST)
- Take 5-10 real overlapping articles from Twitter bookmarks
- Run through Gemini Flash with the decomposition prompt
- Manually evaluate: Are the claims the right granularity? Are duplicates detectable?
- This validates the core assumption before building infrastructure

### Phase 1: Pipeline foundation (1-2 days)
- Add atomic decomposition to `build_articles.py`
- Set up sqlite-vec on Hetzner
- Embed claims with Nomic
- Basic novelty scoring (embedding similarity only)
- Output: articles.json now includes `atomic_claims[]` per article with novelty status

### Phase 2: Reader enhancements (1-2 days)
- Paragraph dimming based on claim novelty status
- "What's new for you" card enhanced with typed claims
- Scrollbar novelty minimap
- Claim interaction: tap to see details, "I knew this" button

### Phase 3: Delta reports (2-3 days)
- Topic clustering of accumulated articles
- Delta report generation pipeline
- Delta report UI (new screen)
- Knowledge state tracking (claims encountered via report vs article)

### Phase 4: Refinement (ongoing)
- LLM judge for ambiguous claim comparisons
- User feedback loop (corrections improve model)
- Structured comparison (Elicit-style matrix)
- Blindspot detection
- Confidence decay over time

---

## Research Base

All in `research/` directory:
1. `knowledge-modeling.md` — Tools, algorithms, curiosity models, practical recommendations
2. `hci-reading-systems.md` — CHI/UIST literature: ScholarPhi, Scim, CiteSee, Selenite, sensemaking
3. `knowledge-representation-novelty.md` — Atomic decomposition (FActScore, SAFE, Claimify), normalization, entailment, 21 papers
4. `knowledge-deduplication.md` — Nomic embeddings, sqlite-vec, 4-stage cascade, cost analysis
5. `article-synthesis-prior-art.md` — 20+ product survey: Particle, Elicit, NotebookLM, Ground News
6. `multi-article-synthesis-systems.md` — PRIMERA, WebCiteS, iFacetSum, cross-document alignment
7. `knowledge-diff-interfaces.md` — Dimming, stretchtext, Scim, CiteSee, adaptive presentation
8. `knowledge-tracing-reading.md` — BKT/DKT adapted for reading (may still be in progress)

Key papers referenced:
- FActScore (EMNLP 2023) — atomic fact decomposition
- Claimify (Microsoft, 2025) — production claim extraction pipeline
- "Do MDS Models Synthesize?" (TACL 2024) — extract-then-synthesize
- AFaCTA (ACL 2024) — claim type taxonomy
- Scim (IUI 2023) — faceted reading with scrollbar markers
- CiteSee (CHI 2023) — knowledge-aware citation highlighting
- Loewenstein (1994) — curiosity as information gap theory
- Constrained Highlighting (CHI 2024 Best Paper) — less is more
