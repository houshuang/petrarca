# Scalable Knowledge Deduplication Research

**Date**: 2026-03-07
**Problem**: Given ~13,000 knowledge contributions/year (50 articles/week x 5 contributions each), efficiently determine which contributions in a new article are genuinely novel vs. already covered by existing ones.

---

## Table of Contents
1. [Scale Analysis & Cost Estimates](#1-scale-analysis--cost-estimates)
2. [Embedding Models for Knowledge Claims](#2-embedding-models-for-knowledge-claims)
3. [Vector Storage for Our Scale](#3-vector-storage-for-our-scale)
4. [Semantic Deduplication Approaches](#4-semantic-deduplication-approaches)
5. [Hierarchical Comparison Strategy](#5-hierarchical-comparison-strategy)
6. [Claim Matching & Verification Systems](#6-claim-matching--verification-systems)
7. [Incremental Knowledge Base Updates](#7-incremental-knowledge-base-updates)
8. [Recommended Architecture](#8-recommended-architecture)
9. [Implementation Plan](#9-implementation-plan)

---

## 1. Scale Analysis & Cost Estimates

### Our numbers
- **Year 1**: ~13,000 knowledge contributions (250 claims/week)
- **Year 3**: ~40,000 contributions (cumulative)
- **Year 5**: ~65,000 contributions (cumulative)
- **Average claim length**: ~15-30 tokens (a sentence or two)
- **Total tokens for full corpus at Year 3**: ~800K tokens (40K claims x 20 tokens avg)

This is a **small** problem by vector search standards. FAISS handles billions of vectors; we have tens of thousands. The entire corpus fits in memory trivially. This means we can afford higher-quality approaches that wouldn't scale to millions.

### Cost to embed the full corpus

| Provider | Model | Cost per 1M tokens | Year 1 cost | Year 3 cost |
|----------|-------|-------------------|-------------|-------------|
| OpenAI | text-embedding-3-small | $0.02/1M | $0.005 | $0.016 |
| OpenAI | text-embedding-3-large | $0.13/1M | $0.034 | $0.104 |
| Cohere | embed-v4 | $0.50/1M | $0.130 | $0.400 |
| Google | gemini-embedding-001 | Free tier / $0.15/1M | Free | Free-$0.12 |
| Nomic | nomic-embed-text-v1.5 | Free (local) / $0.01/1M (API) | ~$0 | ~$0 |
| Local | all-MiniLM-L6-v2 | Free | $0 | $0 |
| Local | BGE-large-en-v1.5 | Free | $0 | $0 |

**Key insight**: At our scale, embedding cost is essentially zero. Even the most expensive provider (Cohere) costs under $0.50/year. This means we should optimize for **quality**, not cost.

### Cost to compare a new article (5 claims against full corpus)

For each new article, we embed 5 new claims and search against the full index. This is:
- 5 embedding calls (~100 tokens) = negligible cost
- 5 ANN searches against 13K-65K vectors = sub-millisecond with any index

The real cost question is whether we also use an LLM for verification (see Section 5).

---

## 2. Embedding Models for Knowledge Claims

### What makes claim embeddings different from document embeddings

Knowledge claims are short, factual, and meaning-dense: *"Claude Code now supports background agents that run on remote servers"*. This is different from typical document retrieval where you're matching a query against long passages. We need:

1. **High semantic sensitivity**: "X supports Y" vs "X does not support Y" must be distant
2. **Entity awareness**: "Claude" and "GPT-4" should not be confused despite both being "AI models"
3. **Specificity preservation**: "LLMs can now run on phones" vs "Gemma 3 runs on Pixel 9 at 30 tok/s" are related but NOT duplicates
4. **Multilingual awareness**: Stian reads in many languages; the same claim in English and Norwegian should match

### Model comparison for claim similarity

**Tier 1: Best quality (recommended for our scale)**

| Model | Dims | MTEB STS | Multilingual | Notes |
|-------|------|----------|-------------|-------|
| Cohere embed-v4 | 1024 | 65.2 | 100+ langs | Best overall MTEB, 15-20% better on non-Latin scripts |
| OpenAI text-embedding-3-large | 3072 (truncatable) | 64.6 | Good | Matryoshka support, truncate to 256/512/1024 |
| BGE-large-en-v1.5 | 1024 | 63.5 (83.1 STS) | English-focused | Best open-source for STS specifically |
| E5-large-v2 / E5-instruct | 1024 | ~63 | Good | Instruction-tuned variant is very strong |

**Tier 2: Good quality, runs locally**

| Model | Dims | Speed | Notes |
|-------|------|-------|-------|
| Nomic-embed-text-v1.5 | 768 (Matryoshka: 64-768) | 100+ qps on M2 Mac | Fully open, auditable, Matryoshka support |
| BGE-M3 | 1024 | Moderate | Best multilingual open model, hybrid dense+sparse |
| GTE-large-en-v1.5 | 1024 | Moderate | Strong competitor to BGE |
| Qwen3-Embedding-0.6B | Variable | Fast | New, multilingual, instruction-aware |

**Tier 3: Fast but lower quality**

| Model | Dims | Speed | Notes |
|-------|------|-------|-------|
| all-MiniLM-L6-v2 | 384 | 14.7ms/1K tokens | Legacy, 56% Top-5 accuracy. DO NOT use for new projects |
| EmbeddingGemma-300M | Variable | <22ms on EdgeTPU | Compact but surprisingly capable |

### Recommendation for Petrarca

**Primary: Nomic-embed-text-v1.5** running locally on the Hetzner server.

Rationale:
- Fully open source (weights, code, training data)
- Matryoshka support lets us do cheap 64-dim pre-filtering, then full 768-dim comparison
- Runs fast on CPU (100+ qps on M2, similar on modern Intel/AMD)
- Outperforms OpenAI text-embedding-3-small on MTEB
- Multilingual support matches Stian's reading languages
- Zero marginal cost
- 8,192 token context window (more than enough for claims)

**Fallback/upgrade**: If multilingual quality isn't sufficient, switch to BGE-M3 (best multilingual open model) or use Gemini gemini-embedding-001 (free tier, 100+ languages).

---

## 3. Vector Storage for Our Scale

### The options

At 13K-65K vectors, we do NOT need a production vector database. Here's what fits:

| Solution | Type | Best for | Overhead |
|----------|------|----------|----------|
| **FAISS (Flat)** | In-memory library | <100K vectors, exact search | Zero — just numpy + faiss |
| **sqlite-vec** | SQLite extension | Embedded, persistent, relational queries | Near-zero — single .db file |
| **LanceDB** | Embedded DB | Larger scale, columnar storage | Low — file-based, no server |
| **ChromaDB** | Embedded/client-server | Prototyping, Python-native | Low-medium |
| **Qdrant** | Client-server | >1M vectors, production | Medium — separate process |
| **Pinecone** | Managed cloud | No-ops, massive scale | High — cloud dependency, cost |

### Recommendation for Petrarca

**Primary: sqlite-vec** (or raw numpy + FAISS Flat index)

Rationale for sqlite-vec:
- Our claim metadata (article_id, topic, date, specificity) needs relational queries too
- Single `.db` file, no server process, survives restarts
- SQLite is already the gold standard for embedded data
- KNN search at 65K vectors is instant (<1ms)
- Can store embeddings alongside claim text and metadata in one place
- Python integration via standard sqlite3 + extension loading

Rationale for FAISS Flat (alternative):
- At <100K vectors, brute-force exact search is faster than ANN approximations
- No index building, no training step, no approximation error
- `faiss.IndexFlatIP` (inner product) or `faiss.IndexFlatL2` on 65K x 768 = 200MB RAM
- Save/load with `faiss.write_index()` / `faiss.read_index()`
- Pair with a simple JSON or SQLite file for metadata

**Why NOT a managed database**: Our scale is 1000x too small to justify managed infrastructure. A FAISS flat index on 65K vectors of 768 dimensions uses ~200MB RAM and answers queries in <1ms. Pinecone's free tier would work but adds unnecessary network dependency.

---

## 4. Semantic Deduplication Approaches

### Levels of deduplication

For knowledge claims, we need to distinguish between:

1. **Exact duplicates**: Same claim extracted from different articles ("GPT-4o costs $5/M input tokens")
2. **Paraphrases**: Same fact, different wording ("GPT-4o's input pricing is $5 per million tokens")
3. **Subsumption**: One claim contains another ("GPT-4o costs $5/M input, $15/M output" subsumes "GPT-4o costs $5/M input")
4. **Related but distinct**: Same topic, different facts ("GPT-4o costs $5/M" vs "Claude 3.5 costs $3/M")
5. **Contradictions**: Opposite claims ("X improves performance" vs "X degrades performance")

### Approach 1: Pure embedding similarity

Embed all claims, find nearest neighbors, threshold at similarity > 0.85 for "likely duplicate".

**Pros**: Simple, fast, works well for paraphrases
**Cons**: Can't distinguish subsumption from exact match; threshold is fragile; entity confusion

### Approach 2: SemHash (recommended for initial implementation)

[SemHash](https://github.com/MinishLab/semhash) is purpose-built for semantic deduplication:
- Uses Model2Vec embeddings (distilled, very fast) + Vicinity ANN search
- Deduplicates 1.8M records in 83 seconds on CPU
- Supports within-dataset and cross-dataset deduplication
- Configurable similarity threshold
- Python library, pip-installable

```python
from semhash import SemHash

# Initialize with existing claims
existing_claims = [{"text": c["claim"]} for c in knowledge_base]
semhash = SemHash.from_records(existing_claims, columns=["text"])

# Check new claims against existing
new_claims = [{"text": c["claim"]} for c in article_claims]
results = semhash.self_deduplicate(new_claims, threshold=0.85)
# or: results = semhash.deduplicate(new_claims, threshold=0.85)  # cross-dataset
```

**Limitation**: SemHash uses Model2Vec which is a distilled model — may miss nuanced semantic differences. Good for a fast first pass, but may need LLM verification for edge cases.

### Approach 3: Two-stage (embedding filter + LLM judge)

This is the best approach for quality and is practical at our scale:

1. **Stage 1**: Embed new claim, find top-5 nearest neighbors from knowledge base (fast, <1ms)
2. **Stage 2**: Ask LLM to judge: "Is claim A genuinely novel given these existing claims B1-B5?"

```python
# Stage 1: Fast retrieval
query_embedding = embed(new_claim)
candidates = index.search(query_embedding, k=5)  # top 5 nearest

# Stage 2: LLM verification (only if top similarity > 0.7)
if candidates[0].similarity > 0.7:
    prompt = f"""Compare this new claim against existing knowledge:

    NEW: {new_claim}

    EXISTING:
    1. {candidates[0].text} (similarity: {candidates[0].similarity:.2f})
    2. {candidates[1].text} (similarity: {candidates[1].similarity:.2f})
    ...

    Is the new claim:
    A) DUPLICATE - same information as an existing claim
    B) REFINEMENT - adds specificity to an existing claim (merge)
    C) NOVEL - genuinely new information
    D) CONTRADICTION - conflicts with existing claims

    Respond with the letter and a brief explanation."""

    result = llm_judge(prompt)  # Gemini Flash — cheap, fast
```

**Cost of LLM verification**: At ~5 claims/article, ~50 articles/week, and ~50% needing verification (similarity > 0.7), that's ~125 LLM calls/week. With Gemini Flash at ~$0.075/1M tokens and ~200 tokens/call, this is ~$0.002/week. Essentially free.

### Approach 4: Claim normalization before comparison

Convert claims to a canonical form before embedding/comparison:

```
Raw: "According to a March 2025 Nature paper, transformer attention scales quadratically"
Normalized: "transformer attention computational complexity: O(n^2) quadratic scaling"
```

This is done by the LLM during extraction (add a `normalized_claim` field to the pipeline prompt). Normalized claims embed more consistently and compare more reliably.

### Approach 5: MinHash/SimHash for surface-level pre-filtering

[text-dedup](https://github.com/ChenghaoMou/text-dedup) provides MinHash + LSH, SimHash, and exact deduplication. These work on surface text and catch:
- Copy-paste duplicates across articles
- Slightly reworded versions of the same sentence
- Boilerplate text that appears in many articles

**Not sufficient alone** for semantic deduplication (won't catch paraphrases) but useful as a cheap first filter to avoid embedding identical text.

---

## 5. Hierarchical Comparison Strategy

### The problem with flat comparison

Comparing every new claim against every existing claim is O(n) per claim. At 65K claims, this is still fast with FAISS Flat (<1ms). But the comparison is "dumb" — an AI claim will match against politics claims if they share common words.

### Recommended: Topic-partitioned index

Since our pipeline already extracts `interest_topics` with `broad` and `specific` fields, we can partition:

```
knowledge_base/
  artificial-intelligence/
    ai-orchestration/  -> [claims about Claude Code, agent frameworks, ...]
    llm-training/      -> [claims about RLHF, scaling laws, ...]
    ai-safety/         -> [claims about alignment, interpretability, ...]
  history/
    medieval/          -> [claims about Arabic-Latin transmission, ...]
    classical/         -> [claims about Roman republic, ...]
  ...
```

**Implementation**: One FAISS index per `broad` topic. When a new article arrives:

1. Route to the correct topic index(es) based on its `interest_topics`
2. Search only within that topic's claims
3. Cross-topic search only for high-level "meta" claims

**Benefit**: Reduces false matches (an AI claim won't accidentally match a history claim about "models") and makes the comparison semantically tighter.

**At our scale, this is an optimization, not a necessity.** Even flat search over 65K vectors is <1ms. But it improves match quality by reducing false positives from unrelated domains.

### Multi-stage cascade

For maximum quality with minimum cost:

```
Stage 0: MinHash surface check        — catches exact/near-exact text duplicates (free, instant)
Stage 1: Topic routing                — filter to same broad topic (free, instant)
Stage 2: Embedding similarity search  — top-5 nearest neighbors in topic index (<1ms)
Stage 3: LLM judge (if sim > 0.7)    — classify as duplicate/refinement/novel (~$0.00002/call)
```

This cascade means the expensive LLM step only fires for ambiguous cases, which in practice is ~30-50% of claims.

---

## 6. Claim Matching & Verification Systems

### Relevant systems from fact-checking

**ClaimBuster** (UT Arlington): End-to-end fact-checking system that:
- Identifies "check-worthy" claims in text
- Matches claims against a repository of existing fact-checks
- Translates claims into knowledge base queries

The claim matching component is directly relevant: it finds semantically equivalent claims across different phrasings. Their approach uses supervised classifiers trained on claim pairs.

**Google Fact Check Tools API**: Programmatic search through fact-checked claims. Free with API key. Could be used as an external signal — if a claim matches a fact-check, note it. But the coverage is narrow (news/political claims only).

**ClaimReview schema**: A structured data format (Schema.org) for fact-checks. The normalization patterns are useful: each claim has a `claimReviewed` text, a `reviewRating`, and supporting evidence. We could adopt a similar structure for our knowledge contributions.

### Adapting fact-checking patterns for novelty detection

The fact-checking pipeline has close parallels to our problem:

| Fact-checking | Petrarca knowledge dedup |
|--------------|-------------------------|
| "Is this claim true?" | "Is this claim new to the user?" |
| Claim extraction from speeches | Claim extraction from articles (we already do this) |
| Match against fact-check DB | Match against knowledge base |
| Verdict: true/false/mixed | Verdict: novel/duplicate/refinement |
| Evidence retrieval | Existing claim retrieval |

### NLI-based claim comparison

Natural Language Inference models can directly judge claim relationships:
- **Entailment**: Existing claim entails new claim (new claim is already known)
- **Contradiction**: Claims conflict (flag for attention)
- **Neutral**: Claims are unrelated (new claim is novel in this dimension)

Models like `cross-encoder/nli-deberta-v3-base` can classify claim pairs with high accuracy. This is more precise than cosine similarity but slower (requires pairwise inference). At our scale (5 new claims x 5 top candidates = 25 NLI calls per article), this is fast enough.

```python
from sentence_transformers import CrossEncoder

nli_model = CrossEncoder('cross-encoder/nli-deberta-v3-base')
pairs = [(new_claim, existing_claim) for existing_claim in top_candidates]
scores = nli_model.predict(pairs)
# Returns [entailment, contradiction, neutral] probabilities per pair
```

---

## 7. Incremental Knowledge Base Updates

### Adding new claims

The knowledge base grows by ~250 claims/week. Updates must be:
1. **Append-only** for the claim store (never lose data)
2. **Index-updatable** without full rebuild

**FAISS**: Supports `index.add(new_vectors)` for flat and IVF indexes. No retraining needed for Flat index. For IVF, you train once on an initial batch, then add incrementally — centroid quality degrades slowly but at our scale this doesn't matter.

**sqlite-vec**: Just INSERT new rows. The index updates automatically.

**LanceDB**: Append new rows to the table. Index updates are automatic.

### Merging/consolidating duplicate claims

When the LLM judge identifies a "refinement" (new claim adds specificity to existing):

```python
# Example: existing claim gets enriched
existing = "LLMs can run on mobile devices"
new_refined = "Gemma 3 1B runs at 30 tokens/sec on Pixel 9 with 4-bit quantization"

# Don't delete the old claim — mark the relationship
knowledge_base.add({
    "claim": new_refined,
    "refines": existing_claim_id,
    "article_id": new_article_id,
    "date": "2026-03-07"
})

# Update the existing claim's metadata
knowledge_base.update(existing_claim_id, {
    "refined_by": [new_claim_id],
    "last_refined": "2026-03-07"
})
```

### Knowledge decay

Some claims become outdated: "GPT-4 is the best model" was true in 2023, not in 2026. Options:
- **Time-decay weighting**: Older claims get lower similarity weight, so a new article making the same claim about a newer model is still "novel"
- **Contradiction tracking**: When a new claim contradicts an old one, mark the old one as superseded
- **Manual override**: User marks claims as "outdated" during reading

### Proposed schema for knowledge contributions

```json
{
    "id": "kc_abc123",
    "claim": "Claude Code now supports background agents running on remote servers",
    "normalized_claim": "Claude Code: background agent support, remote server execution",
    "embedding": [0.12, -0.34, ...],  // 768-dim float32
    "article_id": "art_xyz789",
    "article_title": "Anthropic Launches Background Agents",
    "broad_topic": "artificial-intelligence",
    "specific_topic": "ai-orchestration",
    "entity": "Claude Code",
    "specificity": "high",
    "date_added": "2026-03-07",
    "status": "active",  // active | superseded | merged
    "refined_by": [],
    "superseded_by": null,
    "user_signals": {
        "marked_known": false,
        "marked_interesting": false
    }
}
```

---

## 8. Recommended Architecture

### Overview

```
                  New Article
                      |
                      v
            ┌─────────────────┐
            │  Pipeline (LLM) │  Extract claims + interest_topics
            │  (Gemini Flash) │  + normalized_claim field
            └────────┬────────┘
                     |
                     v
          ┌──────────────────────┐
          │  Stage 0: MinHash    │  Exact/near-exact text dedup
          │  (text surface)      │  → catches copy-paste duplicates
          └──────────┬───────────┘
                     |
                     v
          ┌──────────────────────┐
          │  Stage 1: Topic      │  Route to topic partition
          │  Routing             │  based on interest_topics.broad
          └──────────┬───────────┘
                     |
                     v
          ┌──────────────────────┐
          │  Stage 2: Embedding  │  Nomic-embed-text-v1.5
          │  Similarity Search   │  Top-5 nearest in topic index
          │  (sqlite-vec / FAISS)│  Threshold: sim > 0.7
          └──────────┬───────────┘
                     |
              ┌──────┴──────┐
              |             |
         sim < 0.7     sim >= 0.7
              |             |
              v             v
         NOVEL         ┌────────────────┐
         (add to KB)   │ Stage 3: LLM   │  Gemini Flash judge
                       │ Verification   │  duplicate/refinement/
                       │                │  novel/contradiction
                       └───────┬────────┘
                               |
                    ┌──────────┼──────────┐
                    v          v          v
               DUPLICATE   REFINEMENT   NOVEL
               (skip)      (link to     (add to KB)
                           existing)
```

### What runs where

- **Embedding model** (Nomic-embed-text-v1.5): Runs on Hetzner server via `sentence-transformers` or `nomic` Python package. First-time model download ~300MB, then runs from cache. CPU inference at 100+ qps is more than sufficient.
- **Vector index** (sqlite-vec or FAISS): On Hetzner server, persisted to disk. sqlite-vec as a single `.db` file in `/opt/petrarca/data/knowledge.db`.
- **LLM judge** (Gemini Flash): API call, same as existing pipeline. ~125 calls/week, cost ~$0.01/month.
- **MinHash** (optional): `text-dedup` or `datasketch` library, runs in-process.

### Integration with existing pipeline

The deduplication step plugs into `build_articles.py` after LLM extraction:

```python
# In build_articles.py, after LLM processing returns novelty_claims:

from knowledge_dedup import check_novelty

for claim in article["novelty_claims"]:
    result = check_novelty(claim, knowledge_base)
    claim["novelty_status"] = result.status  # "novel", "duplicate", "refinement"
    claim["similar_existing"] = result.similar_claims  # for UI display
    if result.status == "novel":
        knowledge_base.add(claim, article_id=article["id"])
    elif result.status == "refinement":
        knowledge_base.link(claim, refines=result.existing_claim_id)
```

### What the app gets

Each article served to the app now has enriched claims:

```json
{
    "novelty_claims": [
        {
            "claim": "Claude Code supports background agents",
            "specificity": "high",
            "novelty_status": "novel",
            "similar_existing": []
        },
        {
            "claim": "Background agents can run for up to 24 hours",
            "specificity": "medium",
            "novelty_status": "refinement",
            "similar_existing": [
                {"claim": "Background agents can run autonomously", "article": "AI Weekly #42"}
            ]
        }
    ]
}
```

The app can then display: "3 new insights, 2 you've seen before" with the ability to tap and see what existing knowledge each claim relates to.

---

## 9. Implementation Plan

### Phase 1: Foundation (1-2 hours)

1. Install dependencies on Hetzner:
   ```bash
   pip install sentence-transformers nomic sqlite-vec semhash
   ```

2. Create `scripts/knowledge_dedup.py` with:
   - Embedding function using Nomic-embed-text-v1.5
   - sqlite-vec database for claims + embeddings
   - `check_novelty(claim, topic)` function
   - `add_claim(claim, article_id, topic)` function

3. Backfill: Embed all existing `novelty_claims` from current articles.json

### Phase 2: Pipeline integration (1 hour)

1. Add `normalized_claim` to the LLM extraction prompt in `build_articles.py`
2. After LLM extraction, run each claim through `check_novelty()`
3. Add `novelty_status` and `similar_existing` to article output
4. New claims automatically added to knowledge base

### Phase 3: LLM judge (1 hour)

1. Add Gemini Flash verification for ambiguous cases (similarity 0.7-0.9)
2. Classify as duplicate/refinement/novel/contradiction
3. Handle refinement linking and contradiction flagging

### Phase 4: App integration (later)

1. Display novelty status in reader claim cards
2. "3 new / 2 known" badge on article cards in feed
3. Tap claim to see related existing knowledge
4. User feedback: "I knew this" / "This is new" to correct the model

### What NOT to build (yet)

- Topic-partitioned indexes: Flat search is fast enough at our scale. Add partitioning only if false match rate is too high.
- MinHash pre-filtering: Only needed if we see lots of exact-text duplicates across articles.
- Cross-encoder NLI verification: The LLM judge approach is simpler and more flexible.
- Managed vector database: Massive overkill for our scale.

---

## Sources

### Vector Databases & Benchmarks
- [Vector Database Comparison 2025 (LiquidMetal AI)](https://liquidmetal.ai/casesAndBlogs/vector-comparison/)
- [Best Vector Databases in 2026 (Firecrawl)](https://www.firecrawl.dev/blog/best-vector-databases)
- [Top 5 Open Source Vector Databases for 2025 (Medium)](https://medium.com/@fendylike/top-5-open-source-vector-search-engines-a-comprehensive-comparison-guide-for-2025-e10110b47aa3)

### Embedding Models
- [Top Embedding Models 2026 (ArtSmart)](https://artsmart.ai/blog/top-embedding-models-in-2025/)
- [Best Open-Source Embedding Models 2026 (BentoML)](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [13 Best Embedding Models 2026 (Elephas)](https://elephas.app/blog/best-embedding-models)
- [Benchmark of 16 Open Source Embedding Models (AI Multiple)](https://research.aimultiple.com/open-source-embedding-models/)
- [Embedding Models: OpenAI vs Gemini vs Cohere (AI Multiple)](https://research.aimultiple.com/embedding-models/)
- [Best Embedding Models 2025: MTEB Scores & Leaderboard (Ailog)](https://app.ailog.fr/en/blog/guides/choosing-embedding-models)

### Semantic Deduplication
- [SemHash: Fast Semantic Deduplication (GitHub)](https://github.com/MinishLab/semhash)
- [SemDeDup: Data-efficient learning through semantic deduplication (arXiv)](https://arxiv.org/abs/2303.09540)
- [text-dedup: All-in-one text deduplication (GitHub)](https://github.com/ChenghaoMou/text-dedup)
- [Large-scale Near-deduplication Behind BigCode (HuggingFace)](https://huggingface.co/blog/dedup)

### Claim Matching & Fact-Checking
- [ClaimBuster: End-to-end Fact-checking System (VLDB)](https://vldb.org/pvldb/vol10/p1945-li.pdf)
- [Google Fact Check Tools API](https://developers.google.com/fact-check/tools/api)
- [ClaimBuster Platform](https://idir.uta.edu/claimbuster/)

### Matryoshka & Multi-granularity Embeddings
- [Matryoshka Representation Learning (NeurIPS 2022)](https://arxiv.org/abs/2205.13147)
- [Introduction to Matryoshka Embedding Models (HuggingFace)](https://huggingface.co/blog/matryoshka)
- [Matryoshka Embeddings: Detail at Multiple Scales (Milvus)](https://milvus.io/blog/matryoshka-embeddings-detail-at-multiple-scales.md)

### Nomic Embed
- [Nomic-embed-text-v1.5 (HuggingFace)](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [Run OpenAI Quality Embeddings Locally (Nomic Blog)](https://www.nomic.ai/blog/posts/local-nomic-embed)

### Vector Storage (Embedded)
- [sqlite-vec: Vector search for SQLite (GitHub)](https://github.com/asg017/sqlite-vec)
- [LanceDB: Embedded Vector Database](https://lancedb.com/)
- [FAISS: Incremental Vector Addition (GitHub Issue)](https://github.com/facebookresearch/faiss/issues/163)

### Retrieval & Ranking
- [Rerankers and Two-Stage Retrieval (Pinecone)](https://www.pinecone.io/learn/series/rag/rerankers/)
- [Retrieval Strategies (Anyscale)](https://docs.anyscale.com/rag/quality-improvement/retrieval-strategies)

### Embedding Pricing
- [OpenAI API Pricing](https://platform.openai.com/docs/pricing)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Embedding GA Announcement (Google Developers Blog)](https://developers.googleblog.com/gemini-embedding-available-gemini-api/)

### Paraphrase Detection & NLI
- [Transformer Models for Paraphrase Detection (MDPI 2025)](https://www.mdpi.com/2073-431X/14/9/385)

### News Deduplication
- [Google News System Design](https://www.systemdesignhandbook.com/guides/google-news-system-design/)
- [News Clustering and Deduplication (New Sloth)](https://newsloth.com/blog/news-clustering-and-deduplication)
