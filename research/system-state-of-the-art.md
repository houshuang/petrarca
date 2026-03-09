# Petrarca — Complete System State & Architecture

**Date**: March 8, 2026
**Purpose**: Single consolidated reference for the entire novelty-aware reading system — research findings, validated algorithms, data structures, implementation status, UI work, and next steps.

---

## 1. Core Concept

Petrarca tracks **what you know** at the atomic claim level. When you read Article 7, the system extracts 20 atomic claims, embeds them, and compares against everything you've encountered before. The reader dims familiar paragraphs (opacity 0.55), highlights novel content, and generates "what's new in [topic]" delta reports across articles.

**Two independent axes:**
- **Interest** (what to show more of) → feeds feed ranking
- **Knowledge** (what's already known) → feeds novelty scoring, paragraph dimming, delta reports

**Fundamental unit**: the atomic claim, not the article. A reader who encounters a claim via Article 7, a delta report, or a conversation has the same knowledge state.

---

## 2. Research Foundation

### 2.1 Key Papers & Prior Art

| Paper/System | Contribution to Petrarca |
|---|---|
| **FActScore** (EMNLP 2023) | Atomic fact decomposition methodology |
| **Claimify** (Microsoft 2025) | Production claim extraction pipeline patterns |
| **"Do MDS Models Synthesize?"** (TACL 2024) | Extract-then-synthesize beats stuff-and-summarize |
| **AFaCTA** (ACL 2024) | Claim type taxonomy (7 types we use) |
| **Scim** (IUI 2023) | Faceted reading with scrollbar markers |
| **CiteSee** (CHI 2023) | Knowledge-aware citation highlighting |
| **Constrained Highlighting** (CHI 2024 Best Paper) | ~150 words highlighted > everything highlighted |
| **Loewenstein 1994** | Curiosity as information gap theory |
| **Brusilovsky taxonomy** | Adaptive presentation techniques (dimming, stretchtext) |
| **FSRS** | Free Spaced Repetition Scheduler — adapted for knowledge decay |
| **BKT/DKT** | Bayesian/Deep Knowledge Tracing from education |

### 2.2 Product Survey (20+ tools analyzed)

| Category | Key systems studied |
|---|---|
| News synthesis | Google Full Coverage, Particle, Ground News, Artifact, Semafor |
| Research tools | Elicit, Semantic Scholar, NotebookLM, Perplexity |
| Read-later | Readwise Reader, Matter, Pocket, Omnivore |
| Reading UX | ScholarPhi, Papeos, Allen AI Semantic Reader |

**Core differentiation**: No existing app models user knowledge at the claim level. Readwise does highlights. Elicit does claim extraction. Nobody combines them with a personal knowledge model that tracks what you've already absorbed.

### 2.3 Research Documents

All in `research/`. Key documents:

| Document | What it covers |
|---|---|
| `novelty-system-architecture.md` | **START HERE** — master architecture design |
| `knowledge-modeling.md` | Personal knowledge modeling approaches |
| `knowledge-representation-novelty.md` | Atomic decomposition, NLI entailment, 21 papers |
| `knowledge-deduplication.md` | Embedding models, sqlite-vec, cascade comparison |
| `knowledge-diff-interfaces.md` | Dimming, stretchtext, Scim, diff patterns |
| `knowledge-tracing-for-reading.md` | BKT/FSRS adapted for reading |
| `hci-reading-systems.md` | CHI/UIST survey of knowledge-aware reading tools |
| `article-synthesis-prior-art.md` | 20+ product survey for delta reports |
| `multi-article-synthesis-systems.md` | PRIMERA, GraphRAG, cross-document alignment |
| `design-vision.md` | "Hooks, not facts" — core reading philosophy |
| `ux-redesign-spec.md` | Approved UI screens from 2 rounds of mockup feedback |
| `claims-topics-feedback-spec.md` | Deep dive on topic specificity problem |
| `experiment-log.md` | Append-only log of all 13+ experiments |
| `experiment-results-report.md` | Consolidated experiment results |

---

## 3. Validated Algorithms (11 Experiments)

All experiments run against 47 articles / 858 claims corpus.

### 3.1 Embedding Model — Nomic-embed-text-v1.5

| Property | Nomic (chosen) | Gemini embedding-001 |
|---|---|---|
| Dimensions | 768 | 3072 |
| Speed | Local, instant | API call |
| Similarity range | 0.3 – 0.95 (wide) | 0.55 – 0.75 (narrow) |
| Discrimination | Clear thresholds | Hard to separate KNOWN from EXTENDS |
| Cost | Free | $0.0001/call |

**Decision**: Nomic is default. Scripts updated. Gemini embeddings archived in `data/claim_embeddings.npz`.

### 3.2 Similarity Thresholds (Nomic-calibrated)

| Classification | Cosine threshold | Meaning |
|---|---|---|
| **KNOWN** | ≥ 0.78 | Essentially the same information |
| **EXTENDS** | 0.68 – 0.78 | Elaborates on known information |
| **NEW** | < 0.68 | Genuinely novel |

### 3.3 LLM Judge (NLI Entailment)

- **When**: Only for pairs in the 0.68–0.78 ambiguous range (~5% of all comparisons)
- **Model**: Gemini 2.0 Flash
- **Agreement with cosine**: 75% overall; 25% disagreement in 0.65–0.80 range
- **Key finding**: Cosine overestimates similarity — LLM says UNRELATED where cosine says EXTENDS
- **Cost**: ~$0/month at current scale (50 articles/week, ~5% need judge)
- Script: `scripts/experiment_nli_entailment.py`

### 3.4 Knowledge Decay (FSRS-inspired)

Claims don't stay "known" forever. Retrievability R decays: `R = e^(-t/S)` where S = stability in days.

| Engagement level | Stability | Meaning |
|---|---|---|
| Skim | 9 days | Glanced at, will forget quickly |
| Read | 30 days | Read carefully, base retention |
| Highlight | 60 days | Marked important, stronger retention |
| Annotate | 120 days | Actively engaged, long-term retention |

Re-encountering a claim multiplies stability by 2.5× (natural spaced repetition).

**Classification with decay**:
| Retrievability | Status | UI treatment |
|---|---|---|
| R ≥ 0.5 | KNOWN | Dim (opacity 0.55) |
| 0.3 ≤ R < 0.5 | PARTIALLY_KNOWN | Slightly dim (opacity 0.75) |
| R < 0.3 | FORGOTTEN → treat as NEW | Full opacity |

Script: `scripts/experiment_knowledge_decay.py`

### 3.5 Curiosity Zone Scoring

Articles score highest when ~70% novel (the "zone of proximal development"):

```python
def curiosity_score(novelty_ratio, n_claims):
    novelty_peak = exp(-((novelty_ratio - 0.7) ** 2) / (2 * 0.15 ** 2))  # Gaussian at 70%
    context_bonus = min(1.0, (1 - novelty_ratio) * 3) * 0.3  # Reward some familiar context
    size_factor = min(1.0, n_claims / 15) * 0.2  # Prefer substantial articles
    return novelty_peak * 0.6 + context_bonus + size_factor
```

- **Correlation with naive "most novel" ranking**: 0.051 — fundamentally different
- Promotes articles adjacent to existing knowledge
- Demotes 100%-novel articles with no familiar context
- **Recommendation**: Replace `discovery_bonus` in feed ranking with curiosity zone
- Script: `scripts/experiment_curiosity_zone.py`

### 3.6 Claim Deduplication

Complete-linkage clustering (all pairs in a cluster must be ≥ 0.78):

| Metric | Value |
|---|---|
| Total claims | 858 |
| Duplicate clusters | 174 |
| Unique after dedup | 404 (47.1% remain) |
| Largest cluster | 26 claims (dcg articles, avg sim=0.853) |
| Cross-article clusters | 12 |
| Intra-article clusters | 162 |

**Critical learning**: Single-linkage (union-find) creates runaway transitive chains — one cluster reached 133 members with avg sim 0.660. Always use complete-linkage for claim dedup.

Script: `scripts/experiment_claim_dedup.py`

### 3.7 Topic Clustering (BERTopic-style)

- UMAP (5D, cosine) + HDBSCAN found 59 clusters from 858 claims
- 7.8% noise (unclustered claims)
- ~75 LLM-assigned topics map cleanly to clusters (purity > 0.6)
- Broad topics fragment naturally: "ai-agents" → 9 sub-clusters
- **No emergent topics found** — LLM topic assignment is comprehensive
- **Use case**: Sub-topic splitting for broad categories
- Script: `scripts/experiment_topic_clustering.py`

### 3.8 Reading Order Optimization

Simulated 4 strategies reading all 47 articles:

| Strategy | 50% coverage | 75% coverage | Waste % |
|---|---|---|---|
| **Curiosity Zone** | Article 24 | Article 34 | 11.4% |
| Most Novel First | Article 25 | Article 35 | 9.6% |
| Random (avg 5) | Article 23 | Article 36 | 10.7% |
| Chronological | Article 25 | Article 37 | 9.4% |

Curiosity Zone front-loads interconnected articles, reads isolated articles last.

Script: `scripts/experiment_reading_order.py`
Visualization: `data/reading_order_curves.html`

### 3.9 Other Validated Experiments

| Experiment | Key result | Script |
|---|---|---|
| **Paragraph dimming** | 70 paragraphs: 14 mostly_novel, 4 familiar, 51 neutral. Opacity range 0.55–0.95 | `experiment_paragraph_dimming.py` |
| **Cross-article links** | 2,033 links found, articles cluster by topic domain | `experiment_cross_article_links.py` |
| **Delta summaries** | Gemini Flash generates readable 3-5 sentence topic reports | `experiment_delta_summaries.py` |
| **Contradiction detection** | Corpus too harmonious — 86% compatible, 4% false-positive contradictions. Deprioritize CONTRADICTS. | `experiment_contradiction_detection.py` |
| **Combined scoring** | Integrates all approaches; 125 NLI calls out of ~306 classifications | `experiment_combined_scoring.py` |

---

## 4. Data Structures

### 4.1 Article (as stored in `data/articles.json`)

```typescript
interface Article {
  id: string;
  title: string;
  author: string;
  source_url: string;
  hostname: string;
  date: string;
  content_markdown: string;
  sections: Section[];
  one_line_summary: string;
  full_summary: string;
  key_claims: string[];
  topics: string[];
  estimated_read_minutes: number;
  content_type: string;
  word_count: number;
  sources: string[];
  atomic_claims: AtomicClaim[];  // 10-30 per article
}
```

### 4.2 Atomic Claim

```typescript
interface AtomicClaim {
  id: string;                    // SHA-256 hash of normalized_text, 12 chars
  normalized_text: string;       // decontextualized, self-contained
  original_text: string;         // as it appeared in article
  claim_type: 'factual' | 'causal' | 'comparative' | 'procedural'
            | 'evaluative' | 'predictive' | 'experiential';
  source_paragraphs: number[];   // paragraph indices for attribution
  topics: string[];              // e.g., ["ai-agents", "AGENTS.md"]
}
```

Currently stored inline in `articles.json`. Embeddings stored separately in `data/claim_embeddings_nomic.npz` (numpy compressed, 858 × 768).

### 4.3 Knowledge State (designed, not yet in app)

```typescript
interface KnowledgeState {
  claim_id: string;
  status: 'unknown' | 'encountered' | 'absorbed';
  encountered_via: string;       // article_id or delta_report_id
  encountered_at: string;        // ISO timestamp
  confidence: number;            // 0-1, decays over time (FSRS)
  stability: number;             // days (FSRS: 9-120 based on engagement)
  user_marked_known?: boolean;   // explicit "I knew this" signal
  user_marked_interesting?: boolean;
}
```

### 4.4 Delta Report (designed, not yet in app)

```typescript
interface DeltaReport {
  id: string;
  topic_cluster: string;
  generated_at: string;
  previous_report_id?: string;
  source_article_ids: string[];
  sections: {
    whats_new: ClaimGroup[];
    where_sources_disagree: ClaimPair[];
    blindspots: string[];
    structured_comparison?: ComparisonMatrix;
  };
}
```

### 4.5 Interest Model (implemented in app)

```typescript
interface TopicInterest {
  topic: string;
  positive_signals: number;
  negative_signals: number;
  last_signal_at: string;
  // Computed: score = (pos - neg * 0.5) * decay(days_since_last)
  // Bayesian smoothing: (pos + prior) / (pos + neg + 2*prior)
}
```

Signal weights: swipe_keep(1.0), swipe_dismiss(0.5), open(0.5), done(1.5), highlight(1.0), chip_+/-(2.0).

Feed ranking: interest_match(40%) + freshness(25%) + discovery_bonus(20%) + variety(15%).

### 4.6 Embedding Files

| File | Contents |
|---|---|
| `data/claim_embeddings_nomic.npz` | 858 × 768 float32, Nomic-embed-text-v1.5 (**current default**) |
| `data/claim_embeddings.npz` | 858 × 3072 float32, Gemini embedding-001 (archived) |

---

## 5. Implementation Status

### 5.1 Implemented & Working

| Component | Where | Status |
|---|---|---|
| Content ingestion pipeline | `scripts/build_articles.py` | Production, runs on Hetzner cron |
| Atomic claim extraction | `build_articles.py --claims` | Working, 858 claims from 47 articles |
| Nomic claim embeddings | `scripts/build_claim_embeddings.py` | Working locally (not yet on Hetzner) |
| Mobile app (Feed + Reader) | `app/` | Deployed at `exp://alifstian.duckdns.org:8082` |
| Interest model | `app/data/interest-model.ts` | In app, tracking topic signals |
| Content sync | `app/data/content-sync.ts` | Manifest-based sync from Hetzner |
| Event logging | `app/data/logger.ts` | JSONL daily files |
| Post-read interest card | `app/app/reader.tsx` | Topic +/- chips after Done |
| "What's new" card | `app/app/reader.tsx` | Shows novelty_claims in reader |
| Design system | `design/DESIGN_GUIDE.md` + `app/design/tokens/` | Fully specified + implemented |
| Pipeline testing | `scripts/pipeline-tests/` | 5 layers, 12 fixtures, all pass |
| Chrome extension | `clipper/` | "Save to Petrarca" web clipper |

### 5.2 Validated in Experiments (not yet in app)

| Component | Script | Ready for integration? |
|---|---|---|
| Claim similarity classification | `simulate_reading.py` | Yes — thresholds calibrated |
| Paragraph-level dimming | `experiment_paragraph_dimming.py` | Yes — opacity logic validated |
| Knowledge decay (FSRS) | `experiment_knowledge_decay.py` | Yes — parameters tuned |
| Curiosity zone scoring | `experiment_curiosity_zone.py` | Yes — replace discovery_bonus |
| Delta summary generation | `experiment_delta_summaries.py` | Yes — Gemini Flash synthesis works |
| Cross-article related reading | `experiment_cross_article_links.py` | Yes — reading graph validated |
| Claim deduplication | `experiment_claim_dedup.py` | Yes — complete-linkage works |
| NLI judge for ambiguous pairs | `experiment_nli_entailment.py` | Yes — needed for 0.68-0.78 range |
| Topic sub-clustering | `experiment_topic_clustering.py` | Nice-to-have |
| Reading order optimization | `experiment_reading_order.py` | Informs queue ordering |

### 5.3 Designed but Not Built

| Component | Design source | Notes |
|---|---|---|
| Knowledge-diff reader (dimming in app) | Mockups 6-10, `ux-redesign-spec.md` | Algorithm proven, needs app integration |
| Delta report UI | Mockups 1-5, `ux-redesign-spec.md` | Pipeline proven, needs screen |
| Topics tab | `ux-redesign-spec.md` | Designed, not implemented |
| Queue tab | `ux-redesign-spec.md` | Designed, not implemented |
| Activity log tab | `ux-redesign-spec.md` | Designed, not implemented |
| "I knew this" claim interaction | `novelty-system-architecture.md` | Designed, not implemented |
| sqlite-vec knowledge store | `knowledge-deduplication.md` | Prototyped with numpy |
| Research agent spawning | `types.ts` interface exists | Not built |
| Voice note transcription | `voice-processing.md` | Soniox researched |

---

## 6. UI Work — All Mockups & Visualizations

### 6.1 Design Explorer Mockups (`mockups/`)

**36 mockup files** across 7 batches. All follow the Annotated Folio design system.

#### Delta Report Variants (5 approaches)
| File | Name | Approach |
|---|---|---|
| `mockup-1.html` | Scholarly Scroll | Linear claim list with subtopic sections, source attribution |
| `mockup-2.html` | Source Columns | Article-tabbed view with novelty bars per source |
| `mockup-3.html` | Claim Matrix | Elicit-style structured comparison (articles × dimensions) |
| `mockup-4.html` | Timeline | Chronological by bookmark date, novelty nodes |
| `mockup-5.html` | Dialectic | Sources "argue with each other" in threaded conversation |

#### Knowledge-Diff Reader Variants (5 approaches)
| File | Name | Approach |
|---|---|---|
| `mockup-6.html` | Margin Annotations | Body text + margin column with claim annotations |
| `mockup-7.html` | Inline Dimming + Minimap | Familiar paragraphs dimmed, scrollbar with novelty dots |
| `mockup-8.html` | Split View | Left: new claims list. Right: full article. Click → scroll |
| `mockup-9.html` | Progressive Disclosure | Novel sections shown, familiar collapsed as "tap to expand" |
| `mockup-10.html` | Claim-First Reading | Claims as primary unit, source passages expand below |

#### Refined Reader Variants (5)
| File | Name |
|---|---|
| `reader-new-v1-manuscript.html` | Manuscript-style reader |
| `reader-new-v2-progressive.html` | Progressive disclosure reader |
| `reader-new-v3-claimfirst.html` | Claim-first reading |
| `reader-new-v4-dimming.html` | Dimming reader |
| `reader-new-v5-hybrid.html` | Hybrid approach |

#### Refined Delta Report Variants (5)
| File | Name |
|---|---|
| `delta-report-v1-linear.html` | Linear prose report |
| `delta-report-v2-newspaper.html` | Newspaper-style columns |
| `delta-report-v3-cards.html` | Card-based layout |
| `delta-report-v4-timeline.html` | Timeline view |
| `delta-report-v5-conversation.html` | Conversational format |

#### Feed Variants (6)
| File | Name |
|---|---|
| `feed-v1-editorial.html` | Editorial newspaper layout |
| `feed-v2-knowledge.html` | Knowledge-focused with novelty indicators |
| `feed-v3-clusters.html` | Clustered by topic |
| `feed-v4-triage.html` | Triage-focused with swipe hints |
| `feed-v5-magazine.html` | Magazine layout |
| `feed-v6-briefing.html` | Daily briefing format |

#### Topic Browser Variants (5)
| File | Name |
|---|---|
| `topic-v1-delta.html` | Delta-focused topic view |
| `topic-v2-dialectic.html` | Dialectic topic comparison |
| `topic-v3-matrix.html` | Matrix topic view |
| `topic-v4-knowledge-map.html` | Knowledge map topic view |
| `topic-v5-timeline.html` | Timeline topic view |

#### Standalone Reader Variants (5)
| File | Name |
|---|---|
| `reader-v1-margins.html` | Margin annotation reader |
| `reader-v2-dimming.html` | Dimming reader |
| `reader-v3-split.html` | Split-panel reader |
| `reader-v4-progressive.html` | Progressive disclosure reader |
| `reader-v5-minimap.html` | Minimap reader |

### 6.2 Older App Mockups (`app/mockups/`)
9 files from earlier design round (feed variants, concept patterns).

### 6.3 Landing Page Mockups (`app/preview-mockups/`)
10 files — marketing/landing page designs.

### 6.4 Generated Data Visualizations (`data/*.html`)

| File | What it shows |
|---|---|
| `knowledge_map.html` | **Interactive D3.js graph** — 47 article nodes, 393 edges (shared claims), zoom/pan/search/topic filter |
| `reading_order_curves.html` | Knowledge growth curves for 4 reading strategies |
| `delta_summaries.html` | Natural-language delta reports for 5 topics (Annotated Folio styled) |
| `reader_preview.html` | Paragraph dimming preview (article 24: "Best Practices for Agent Skills") |
| `reader_preview_10.html` | Paragraph dimming preview (article index 10) |
| `reader_preview_15.html` | Paragraph dimming preview (article index 15) |
| `reader_preview_20.html` | Paragraph dimming preview (article index 20) |
| `reading_simulation_report.html` | Full reading simulation report with charts |
| `experiment_report.html` | Consolidated experiment dashboard |

### 6.5 Approved UI Direction (`ux-redesign-spec.md`)

After 2 rounds of mockup feedback, converged on:

**4 tabs**: Feed | Topics | Queue | Log

**Feed**: Topic filter chips → article cards with one ✦ novelty claim preview → swipe right to queue, left to dismiss

**Reader**: Progress bar → title → "What's new for you" card → body with paragraph dimming → claim interaction (format TBD) → "Done" button → post-read interest chips → "Up next" footer

**Topics**: Expandable topic clusters ranked by interest → articles within each cluster → delta report access

**Queue**: Ordered reading list → drag to reorder → flows through "Up next" in reader

**Log**: Activity timeline — reading actions, system events, research agents, interest signals

---

## 7. Pipeline Architecture

### 7.1 Current Production Pipeline

```
Twitter bookmarks + Readwise Reader
    ↓
fetch_twitter_bookmarks.py / Readwise API
    ↓
build_articles.py
    ├── Collect candidates
    ├── Filter/deduplicate by URL
    ├── Fetch article content (trafilatura + lxml fallback)
    ├── clean_markdown() — strips nav, cookies, subscribe cruft
    ├── Gemini Flash: sections, summaries, topics, key_claims
    ├── [optional] --claims: atomic claim extraction (10-30/article)
    └── Output: articles.json
    ↓
extract_entity_concepts.py (cross-article concepts)
    ↓
nginx serves /content/ on port 8083
    ↓
App syncs via manifest hash comparison
```

Runs every 4 hours via cron on Hetzner.

### 7.2 Validated but Not Deployed

```
articles.json (with atomic_claims)
    ↓
build_claim_embeddings.py
    ├── Nomic-embed-text-v1.5 (local, 768 dim)
    └── Output: claim_embeddings_nomic.npz
    ↓
[At read time]
simulate_reading.py logic:
    ├── cosine similarity → KNOWN/EXTENDS/NEW classification
    ├── LLM judge for 0.68-0.78 range
    ├── FSRS knowledge decay
    ├── Paragraph dimming (opacity 0.55-1.0)
    └── Delta report generation (Gemini Flash synthesis)
```

### 7.3 Target Production Pipeline

```
articles.json (with atomic_claims)
    ↓
build_claim_embeddings.py → claim_embeddings_nomic.npz
    ↓
[Stored on Hetzner in sqlite-vec]
    ↓
[Served to app as additional JSON files]
    ├── claim_embeddings.json (or binary)
    ├── claim_similarity_index.json (precomputed)
    └── delta_reports.json (per topic)
    ↓
[App-side]
    ├── Knowledge ledger in AsyncStorage
    ├── Reader: paragraph dimming + claim interaction
    ├── Feed: curiosity zone ranking
    └── Topics tab: delta reports
```

---

## 8. Key Architectural Decisions (Settled)

| Decision | Choice | Why |
|---|---|---|
| Knowledge atom | Atomic claim | Matches BKT literature, enables cross-article tracking |
| Embedding model | Nomic-embed-text-v1.5 | Free, local, fast, wide similarity range |
| Similarity thresholds | 0.78 (KNOWN), 0.68 (EXTENDS) | Validated by NLI experiment |
| LLM for extraction | Gemini 2.0 Flash via litellm | Cost-effective, good quality |
| Knowledge decay | FSRS with 30-day base stability | Realistic for reading comprehension |
| Feed ranking | Curiosity zone (peak at 70% novelty) | Better than naive novelty |
| Familiar content | Dim (0.55 opacity), don't hide | Preserves context per CHI research |
| Delta reports | Delta-only (not full syntheses) | Avoid redundant regeneration |
| Dedup clustering | Complete-linkage | Single-linkage creates runaway chains |
| Contradiction detection | Deprioritized | Corpus too harmonious; revisit with diverse sources |
| Vector store (planned) | sqlite-vec | Embedded, zero-config, handles millions |
| Design system | Annotated Folio | Fully approved, implemented in design tokens |

---

## 9. Open Questions

1. **Claim interaction format in reader**: Margin annotations vs inline callouts vs "What's new" card only? Three approaches mocked up, not decided.
2. **Topic specificity**: "AI coding" vs "Claude Code" vs "AGENTS.md" — how granular should topic tags be? See `claims-topics-feedback-spec.md`.
3. **Where do pre-computed similarities live?** Options: serve as JSON (simple), sqlite-vec on server with API (flexible), compute client-side (slow).
4. **FSRS parameter tuning**: 30-day base stability is a guess validated on simulated data. Needs real user behavior data.
5. **Scale of dedup**: 52.9% reduction on 858 claims. Will this ratio hold at 10,000+ claims?

---

## 10. File Index

### Scripts
| Path | Purpose |
|---|---|
| `scripts/build_articles.py` | Main content pipeline (1,400+ lines) |
| `scripts/build_claim_embeddings.py` | Nomic/Gemini embedding generation |
| `scripts/simulate_reading.py` | Reading simulation + delta reports |
| `scripts/experiment_claim_extraction.py` | Experiment 0: claim quality validation |
| `scripts/experiment_nli_entailment.py` | LLM judge validation |
| `scripts/experiment_topic_clustering.py` | BERTopic clustering |
| `scripts/experiment_knowledge_decay.py` | FSRS decay simulation |
| `scripts/experiment_curiosity_zone.py` | Curiosity zone scoring |
| `scripts/experiment_combined_scoring.py` | All approaches combined |
| `scripts/experiment_paragraph_dimming.py` | Reader dimming logic |
| `scripts/experiment_cross_article_links.py` | Related reading detection |
| `scripts/experiment_delta_summaries.py` | Natural-language delta reports |
| `scripts/experiment_reading_order.py` | Reading strategy comparison |
| `scripts/experiment_claim_dedup.py` | Complete-linkage dedup |
| `scripts/experiment_knowledge_map.py` | D3.js article network |
| `scripts/experiment_contradiction_detection.py` | Contradiction detection |
| `scripts/generate_experiment_report.py` | Visual experiment dashboard |
| `scripts/pipeline-tests/run.py` | Pipeline testing framework |

### App
| Path | Purpose |
|---|---|
| `app/app/(tabs)/index.tsx` | Feed screen |
| `app/app/reader.tsx` | Reader screen (785 lines) |
| `app/data/store.ts` | Central state management |
| `app/data/types.ts` | TypeScript type definitions |
| `app/data/interest-model.ts` | Topic interest tracking |
| `app/data/content-sync.ts` | Content synchronization |
| `app/data/logger.ts` | Event logging |
| `app/design/tokens/` | Design system tokens |
| `clipper/` | Chrome extension |

### Data
| Path | Purpose |
|---|---|
| `data/articles.json` | 47 articles with atomic_claims |
| `data/claim_embeddings_nomic.npz` | 858 × 768 Nomic embeddings |
| `data/experiment_*.json` | 13 experiment result files |
| `data/*.html` | 9 visualization files |

### Design & Research
| Path | Purpose |
|---|---|
| `design/DESIGN_GUIDE.md` | 490-line Annotated Folio specification |
| `design/tokens/` | TypeScript design tokens |
| `mockups/` | 36 design mockup HTML files |
| `research/` | 41 research documents |
