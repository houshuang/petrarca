# Topic Normalization & Defragmentation System

**Date**: March 9, 2026
**Status**: Implemented and deployed
**Files**: `scripts/topic_normalizer.py`, `scripts/topic_registry.json`, `scripts/build_articles.py`

---

## Problem

The pipeline generates `interest_topics` (broad/specific/entity hierarchies) independently per article. Without canonicalization:
- The same concept gets different slugs ("reading-tools" vs "read-later-apps")
- Topics get assigned to wrong broad categories ("reading-tools" under "personal-tools" vs "knowledge-management")
- The topic space proliferates unboundedly — Otak's experience showed 315 domains from 8 intended

A 2.9% hierarchy inconsistency rate was measured on just 15 synthetic articles.

## Architecture

The system operates in three layers:

### Layer 1: Prompt-Level Guidance

When extracting articles, `build_articles.py` injects existing categories into the LLM extraction prompt via `_get_topic_hint()`:

```
interest_topics: hierarchical topic tags with kebab-case broad/specific categories...
Prefer these existing categories when they fit (create new ones only if none match):
  artificial-intelligence: ai-coding-tools, ai-orchestration, llm-applications, model-architecture
  history: italian-history, medieval-mediterranean
  ...
```

This makes the LLM prefer existing categories, reducing the need for post-hoc normalization.

### Layer 2: Post-Extraction Normalization

After extraction, each article's topics pass through `normalize_article_topics()`:

1. **Slug normalization**: kebab-case, lowercase, no special chars
2. **Registry lookup**: Check if broad/specific slugs exist in the canonical registry
3. **LLM merge-or-create**: For new slugs, the LLM sees all existing topics (with include/exclude descriptions) and decides:
   - **Merge**: The new topic maps to an existing one (e.g., "ai-tools" → "ai-coding-tools")
   - **Create**: The topic is genuinely new, added to registry with include/exclude descriptions
4. **Canonical parent enforcement**: If a specific topic's canonical broad parent differs from the article's broad, the canonical parent wins

### Layer 3: Periodic Defragmentation

When the registry exceeds configured limits, `defragment_registry()` consolidates:

**Phase 1 — Specific topic consolidation**:
For each broad category with >15 specific topics:
- Present all specific topics (with descriptions) to LLM in a single batch call
- LLM returns merge groups (e.g., merge "drama", "opera", "bel-canto" → "performing-arts")
- Canonical slug gets a merged include/exclude description
- Absorbed slugs are removed from registry

**Phase 2 — Broad category consolidation**:
If >25 broad categories:
- Only merge the minimum number needed to reach the limit
- Prefer absorbing small/niche categories into larger ones
- Major categories (history, literature, AI, politics) are never merged
- Specific topics under absorbed broads are reassigned

**Phase 3 — Article update**:
- Apply the merge map to all articles' `interest_topics`
- When a specific topic is merged, its canonical broad parent is also adopted

## Canonical Topic Registry

`scripts/topic_registry.json` stores the ground truth:

```json
{
  "version": 1,
  "max_broad": 25,
  "max_specific_per_broad": 15,
  "broad": {
    "artificial-intelligence": {
      "includes": "AI, machine learning, LLMs, neural networks, ...",
      "excludes": "Software that merely uses AI as a minor feature ..."
    }
  },
  "specific": {
    "ai-coding-tools": {
      "broad": "artificial-intelligence",
      "includes": "AI coding assistants, code generation, ...",
      "excludes": "General LLM applications not focused on coding"
    }
  }
}
```

Key properties:
- **Include/exclude descriptions**: The critical disambiguation mechanism (learned from Otak)
- **Hard limits**: `max_broad` and `max_specific_per_broad` are soft warnings during normalization, hard triggers for defragmentation
- **Auto-updating**: New topics verified by LLM are automatically added
- **Shallow hierarchy**: Max 2 levels (broad → specific), no recursive nesting

## Triggering Defragmentation

Defrag runs automatically as step 3c3 in the cron pipeline (`content-refresh.sh`):

```bash
# Step 3c3: Defragment topic registry if limits exceeded
python3 scripts/build_articles.py --defrag-topics
```

The `registry_needs_defrag()` function returns True if:
- Broad count > `max_broad` (default 25)
- Any broad category has > `max_specific_per_broad` (default 15) specific topics

If within limits, the step is a no-op (<1ms).

## CLI Interface

```bash
# Normal pipeline — topics auto-normalized during extraction
python3 build_articles.py --limit 10

# Batch re-normalize all existing articles against registry
python3 build_articles.py --normalize-topics [--dry-run]

# Consolidate overpopulated categories via LLM
python3 build_articles.py --defrag-topics [--dry-run]

# Backfill interest_topics for articles that lack them
python3 build_articles.py --enrich [--dry-run]
```

## Lessons from Otak

Otak's `tree_balance.py` implemented a self-balancing topic tree with split/join operations. Key lessons applied:

**What worked (applied here)**:
- Include/exclude descriptions are essential for LLM disambiguation of topic boundaries
- Presenting existing categories when generating new ones dramatically reduces drift
- Batch consolidation (cluster-first, name-later) works better than per-item decisions

**What failed (avoided here)**:
- Recursive splitting → led to 315 domains from 8 intended. We use hard limits instead.
- Organic tree growth → depth spiraled out of control. We enforce max 2 levels.
- Self-balancing complexity → the split/join algorithm was fragile. We use simple LLM merge prompts.
- No convergence guarantee → trees could oscillate. Our defrag only runs when limits are exceeded, and the merge prompt targets exactly the limit.

## Current State (post-deployment)

After processing 185 articles + defragmentation:
- **25 broad categories** (at limit): history, culture, politics, literature, linguistics, software-engineering, artificial-intelligence, education, philosophy, art-architecture, geography, transportation, science, biology, mathematics, knowledge-management, economics, organized-crime, energy, sociology, productivity, engineering, entertainment, collaboration, cognitive-science
- **172 specific topics** across those categories
- All articles normalized and updated
- Registry deployed to server, included in cron pipeline

## Data Flow

```
New article ingested
  → build_articles.py extracts interest_topics (with prompt hint)
  → normalize_interest_topics() validates against registry
    → Known topic? → Use canonical slug
    → Unknown topic? → LLM merge-or-create
      → Merge → Use existing slug
      → Create → Add to registry with includes/excludes
  → Article saved with normalized topics

Every 4h cron pipeline:
  → Step 3c3: registry_needs_defrag()?
    → Yes → defragment_registry()
      → Phase 1: Consolidate specific topics per overpopulated broad
      → Phase 2: Consolidate broad categories (minimal merges)
      → Phase 3: Update all articles
    → No → Skip (no-op)
```
