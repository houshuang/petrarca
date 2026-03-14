# Synthesis Knowledge Tracking — System Design

## Problem
When the user reads a synthesis and marks it "done", the system should:
1. **Track what was seen** — which articles' content was covered
2. **Filter the feed** — articles well-covered by a read synthesis should disappear from the main feed
3. **Assess new content** — future ingestion should check against knowledge from read syntheses

## What Already Exists

### Infrastructure in Place
| Component | File | What it does |
|-----------|------|-------------|
| `completedSyntheses` Set | `store.ts:32` | Tracks cluster_ids of read syntheses (persisted to AsyncStorage) |
| `markSynthesisCompleted()` | `store.ts:455` | Adds cluster to completed set |
| `isSynthesisCompleted()` | `store.ts:451` | Checks if a synthesis was read |
| `getArticleSynthesisCoverage()` | `store.ts:460` | Returns max coverage % across all completed syntheses for an article |
| `markClaimsEncountered()` | `knowledge-engine.ts:399` | Creates FSRS entries (30-day stability) for all covered claims |
| `TopicSynthesis.article_coverage` | `types.ts:160` | Per-article coverage % (e.g., `{"abc123": 0.9}` = 90% of that article's claims covered) |
| `TopicSynthesis.claims_covered` | `types.ts:161` | List of all claim IDs covered by this synthesis |
| `dismissedArticles` | `store.ts:31` | Existing mechanism for hiding articles from feed |
| Knowledge similarity matrix | `knowledge-engine.ts` | Cosine similarity between all claims (KNOWN ≥ 0.78, EXTENDS ≥ 0.68) |

### The Gap
`getRankedFeedArticles()` (store.ts:216) filters by `dismissedArticles` and `readingStates` but **does not check synthesis coverage**. The coverage data exists — it's just not wired into the feed.

## Design

### 1. Feed Filtering — Hide Well-Covered Articles

**In `getRankedFeedArticles()`**, add a synthesis coverage check:

```typescript
const candidates = articles.filter(a => {
  if (dismissedArticles.has(a.id)) return false;
  const state = readingStates.get(a.id);
  if (state && state.status === 'read') return false;

  // NEW: Hide articles well-covered by a read synthesis
  const synthCoverage = getArticleSynthesisCoverage(a.id);
  if (synthCoverage !== null && synthCoverage >= SYNTHESIS_COVERAGE_THRESHOLD) return false;

  return true;
});
```

**Threshold**: `SYNTHESIS_COVERAGE_THRESHOLD = 0.80` (80%)
- At 80%+ coverage, the synthesis captured most of the article's insights
- Articles below 80% stay in the feed — they have significant uncovered content
- The remaining 20% might be installation details, tangential points, etc. that the synthesis deliberately omitted

**Edge case**: An article appears in multiple syntheses (different aspects). `getArticleSynthesisCoverage()` already returns the max across all completed syntheses. If only one synthesis is read, coverage might be 50% — the article stays in the feed because the other aspect hasn't been covered.

### 2. Partial Coverage — Demote Rather Than Hide

For articles between 50-80% coverage (partially covered by a read synthesis):

```typescript
// In the scoring section of getRankedFeedArticles():
const synthCoverage = getArticleSynthesisCoverage(a.id);
const coveragePenalty = synthCoverage ? synthCoverage * 0.5 : 0;
// An 80% covered article loses 40% of its score
return { article: a, score: (interestScore * 0.6 + curiosity * 0.4) * (1 - coveragePenalty) };
```

This means:
- 0% coverage (no synthesis read): full score
- 50% coverage: score × 0.75 (demoted but visible)
- 80%+ coverage: hidden from feed entirely

### 3. Visual Indicator for Partially-Covered Articles

Articles that remain in the feed but have partial synthesis coverage should show an indicator:
- "70% covered by AI Coding Tools synthesis" in muted text
- The novelty badge should reflect remaining uncovered content
- Existing `ArticleNovelty` system already handles this via FSRS claim entries

### 4. New Article Ingestion — Novelty Against Read Syntheses

This **already works** through the existing claim similarity pipeline:

1. User reads synthesis → `markClaimsEncountered(claims_covered, 'read')` → FSRS entries created
2. New article ingested → `build_knowledge_index.py` computes claim embeddings → similarity matrix
3. Client loads new knowledge index → `getArticleNovelty(articleId)` classifies each claim:
   - KNOWN (≥ 0.78 cosine to a seen claim) → familiar
   - EXTENDS (≥ 0.68) → builds on something known
   - NEW (< 0.68) → genuinely new
4. `curiosity_score` already peaks at 70% novelty (Gaussian σ=0.15)

**The key insight**: because `markClaimsEncountered()` writes FSRS entries at the *claim level*, not the *article level*, the novelty system automatically handles this. A new article about AI coding tools will have most of its claims classified as KNOWN (because they're similar to claims from the synthesis), and only genuinely new insights will register as NEW.

**No changes needed** for ingestion — the pipeline already does the right thing once claims are marked as encountered.

### 5. Synthesis Read State — What to Store

Currently: just a Set of cluster_ids. Should also track:

```typescript
interface SynthesisReadState {
  cluster_id: string;
  completed_at: number;          // When marked as read
  articles_covered: string[];    // Which article IDs were in the synthesis
  claims_encountered: number;    // How many claims were marked
  coverage_at_read: Record<string, number>;  // Snapshot of per-article coverage at time of reading
}
```

This enables:
- "You read this synthesis on Mar 12" in the UI
- Knowing which articles were covered (even if synthesis is later regenerated)
- Analytics: how much knowledge was gained per synthesis

### 6. Chat as Knowledge Artifact

When a chat conversation about a synthesis produces valuable insights:

```typescript
interface ChatKnowledgeArtifact {
  id: string;
  source_type: 'synthesis_chat' | 'article_chat';
  source_id: string;              // cluster_id or article_id
  conversation_id: string;        // From the chat system
  created_at: number;
  summary: string;                // LLM-generated summary of the conversation
  key_insights: string[];         // Extractable insights from the chat
  linked_article_ids: string[];   // Articles referenced in the conversation
  linked_topic: string;           // Topic/cluster label
}
```

The chat could have a "Save to knowledge" button that:
1. Summarizes the conversation
2. Extracts key insights as new claims
3. Links them to the synthesis/articles
4. These new insights then participate in the similarity/novelty system

### 7. Implementation Priority

1. **Feed filtering** (store.ts) — wire `getArticleSynthesisCoverage()` into `getRankedFeedArticles()`. Small change, high impact.
2. **Richer SynthesisReadState** — expand from Set to structured records. Moderate change.
3. **Partial coverage demotion** — add coverage penalty to feed scoring. Small change.
4. **Visual indicator** — show coverage status on feed articles. UI change.
5. **Chat knowledge artifacts** — requires inline chat first. Future work.

## Summary

The system is 80% built. The claim-level FSRS tracking means that ingestion novelty **already works correctly** once claims are marked as encountered. The main missing piece is wiring `getArticleSynthesisCoverage()` into the feed filter — a ~10 line change in `getRankedFeedArticles()`.
