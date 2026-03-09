# Claims, Topics & Feedback Interaction Design — Deep Exploration Context

**Date**: March 7, 2026
**Purpose**: Context document for a dedicated agent to explore the interaction design around claims, topic hierarchies, and user feedback signals. This is the most complex and least resolved part of the Petrarca reader.

---

## Background

Petrarca is a knowledge-aware read-later app. The pipeline extracts `interest_topics` and `novelty_claims` from each article. The app needs to:
1. **Show** what's new/known in an article as you read
2. **Capture** user feedback on claims and topics to improve the interest model
3. **Handle** topic specificity — the user cares about topics at different levels of granularity

This document collects all user feedback on these interactions from two rounds of mockup exploration, plus the underlying data model and design constraints.

---

## The Core Problem: Topic Specificity

From user feedback (verbatim):

> "If I'm reading an article about a specific tool for orchestrating Claude Code agents, there are multiple levels of specificity. It's like a topic tree, maybe. It's about AI coding. It's about Claude Code. It's about orchestration. Which can both be generic to AI coding and specific to Claude Code. And it's about a specific tool for orchestration. And then you could go even deeper. If it's mentioning five tools, I guess that's five topics. Five specific topics."

> "My point is that I could say I'm super interested in AI orchestration — give me more articles about that. I could say I'm really interested in AI orchestration in Claude — give me more articles about that. Or I'm actually really interested in this specific tool because maybe I'm using it or considering using it. And then I would like to see other articles about that tool, about tips and tricks or new releases."

> "But if I just say that I'm interested in AI orchestration, then any new article about this tool that doesn't add substantially to the general discussion on AI orchestration would not be prioritized."

### What this means for the system:

The user wants to signal interest at different levels of a topic hierarchy:
- **Broad**: "AI coding" → surface any article about AI in software development
- **Specific**: "AI orchestration" → surface articles about multi-agent coordination
- **Entity**: "Claude Code" → surface articles specifically about this tool
- **Very specific**: "Claude Code worktree feature" → surface articles about this exact feature

Signaling interest at the "entity" level should NOT automatically mean interest in every article mentioning that entity — only articles that ADD to the user's understanding of that entity.

### Current Data Model

```typescript
interface InterestTopic {
  broad: string;      // "artificial-intelligence"
  specific: string;   // "ai-orchestration"
  entity?: string;    // "Claude Code"
}
```

This is a 3-level hierarchy. The user's feedback suggests this may need:
- Deeper nesting (4+ levels)
- Or a more flexible tagging system
- Or a way to signal "more about X at THIS level of specificity"

### Open Questions for Exploration
1. How do we let the user signal interest at different specificity levels without making the UI complex?
2. Should the post-read interest card show the full topic tree, or just the most relevant level?
3. How does this affect feed ranking? If I'm interested in "AI orchestration" broadly, should a "Claude Code release notes" article rank high or low?
4. What does "tell me more about this" mean at different levels?

---

## Claim Interaction Approaches

Three mockup approaches were explored and all received positive feedback. The question is which to implement (or how to combine them).

### Approach A: Margin Annotations (Mockup 4)

Claims displayed alongside article text with margin icons:
- **N** (green circle) = New to you
- **K** (grey circle) = You've seen this (dimmed text)
- **★** (rubric circle) = Saved
- **·** (empty circle) = Unmarked

**Interaction**: Tap margin icon to cycle through states: N → K → ★ → clear

**Pros**:
- Minimal flow interruption
- Book-like annotation feel, matches design language
- Quick one-tap signal per claim

**Cons**:
- Margin space is tight on mobile (56px available)
- Not clear what N/K/★ mean without learning
- No "tell me more" option
- Cross-article connections (purple links) could become noisy

**User feedback**: "I'm not sure exactly what the N, K, and star in the sidebar are" — needs better affordance/onboarding. "I like the identification of information that's in another article. That could also become very noisy."

### Approach B: Interleaved Callouts (Mockup 12)

Claims appear as highlighted blocks between paragraphs:
- Green left border + "New to you" label
- Grey border + "You've seen this" label (dimmed)
- Action buttons below each: "I knew this" / "★ Save" / "Tell me more"

**Interaction**: Tap button to provide signal. "I knew this" corrects the model. "Tell me more" queues a research agent.

**Pros**:
- Contextually placed — claim appears where it's discussed
- Clear labels, no learning curve
- "Tell me more" enables research agent trigger
- Known claims can be visually dimmed to speed up scanning

**Cons**:
- Interrupts reading flow more than margin annotations
- Takes up significant vertical space
- Might feel heavy if article has many claims

**User feedback**: Thumbs up, no specific complaints.

### Approach C: Top-of-Article Card Only (Current Implementation)

Just the ✦ "What's new" card at the top with bullet list of novelty claims. No interaction on individual claims — just read them and proceed.

**Pros**: Simple, no learning curve, minimal UI
**Cons**: No per-claim feedback, no specificity signals, no "I knew this" correction

### User's Broader Feedback on Claims

> "I'm still not exactly sure if I want the claims on top or as part of the article. And I'm not exactly sure the best way to give feedback on the claims. Or see feedback, meaning seeing connections to existing things. I think we need to probably iterate here quite a bit."

> "For triage, it's a bit more complicated than what do I know something."

This suggests the agent should explore:
1. A hybrid approach (top card for overview + inline signals for specific claims)
2. Different feedback granularity (not just know/don't-know, but specificity-aware)
3. How to surface cross-article connections without noise

---

## Cross-Article Connections

When a claim in Article A relates to something in Article B:
- If Article B is already read: show "✓ read 2 weeks ago"
- If Article B is in the library but unread: show "+ Queue" button
- If Article B is not in the system: potentially trigger auto-ingest

**User feedback**:
> "I like the identification of information that's in another article. That could also become very noisy."
> "Maybe we should also indicate whether that article has been read before or not."
> "Instead of clicking into that article, clicking it to add it to the top of the inbox so that the next article I see would be this one."

**Key insight**: Cross-references should default to QUEUING, not navigating. A tap should add to queue (with visual feedback), a long-press should open directly.

---

## Post-Read Interest Card (Current Implementation)

After tapping "Done" in the reader, a bottom sheet appears with:
- 2-4 topic chips from `interest_topics`
- [+] / [-] per chip (weight 2.0, strongest signal)
- Close button (no forced interaction)

### What Needs to Change

The current card shows topics at the `specific` level only. Based on feedback about topic specificity, it should probably:
- Show the topic hierarchy (broad → specific → entity)
- Let the user signal interest at different levels
- Maybe: "More about AI orchestration" vs "More about Claude Code specifically"

---

## Signal Capture Summary

Current signal weights (from interest model):
| Action | Weight | Context |
|--------|--------|---------|
| Swipe right (keep) | 1.0 | Feed |
| Swipe left (dismiss) | 0.5 | Feed (negative) |
| Open article | 0.5 | Feed tap |
| Tap Done | 1.5 | Reader completion |
| Highlight paragraph | 1.0 | Long-press |
| Interest chip [+]/[-] | 2.0 | Post-Read card |

### New Signals to Explore
- **Claim: "I knew this"** — negative novelty signal for that claim's topics (model overestimated novelty)
- **Claim: "Save"** — strong positive signal, claim is worth remembering
- **Claim: "Tell me more"** — triggers research agent, strong interest signal at claim's specificity level
- **Claim: "Actually new"** — corrects model when it marked something as known (positive novelty signal)
- **Cross-reference: queued** — moderate interest signal for the linked topic
- **Topic chip at specific level** — signals interest at THAT level of the hierarchy
- **Time spent on claim** — passive signal, more time = more engagement

---

## Existing Data Model (For Reference)

### Article Fields
```typescript
interface Article {
  // ... standard fields ...
  interest_topics?: InterestTopic[];  // hierarchical: broad/specific/entity
  novelty_claims?: NoveltyClaim[];    // claim text + specificity level
  key_claims: string[];               // flat list from pipeline
  sections: ArticleSection[];         // each section has key_claims[]
}

interface InterestTopic {
  broad: string;      // "artificial-intelligence"
  specific: string;   // "ai-orchestration"
  entity?: string;    // "Claude Code"
}

interface NoveltyClaim {
  claim: string;
  specificity: 'high' | 'medium' | 'low';
}
```

### Legacy Signal Types (may need extension)
```typescript
interface UserSignal {
  article_id: string;
  signal: 'interesting' | 'knew_it' | 'deep_dive' | 'not_relevant' | 'save';
  timestamp: number;
  section_index?: number;
}
```

### Interest Model (in-app)
- Per-topic tracking with Bayesian smoothing
- 30-day decay half-life
- Currently tracks at the `specific` topic level only
- Feed ranking: interest_match(40%) + freshness(25%) + discovery_bonus(20%) + variety(15%)

---

## Design Constraints

1. **Must use the Annotated Folio design system** — see `design/DESIGN_GUIDE.md`
2. **Touch targets ≥ 44×44pt** — claim interaction buttons must be tappable
3. **Reading flow is sacred** — minimize interruption to the reading experience
4. **All signals must be logged** — `logEvent()` for every interaction
5. **Mobile-first** — design for 420px width, adapt to web later
6. **No visible scores** — don't show numerical interest/novelty values to the user

---

## Implementation Decisions (Session 8, Mar 9 2026)

### G9: Topic Hierarchy Feedback — IMPLEMENTED

**Approach chosen**: Hierarchical expand/collapse PostReadInterestCard.

**Signal propagation**: Signals stay at the specific level tapped (no cascade). `recordTopicSignalAtLevel(action, topicKey, level, parent)` records at exactly one level. The scoring algorithm (`computeInterestMatch`) traverses all levels: `Math.max(specificScore, broadScore * 0.7, entityScore)`. This means signaling interest in "Claude Code" (entity) also benefits articles about "AI orchestration" (specific) and "artificial-intelligence" (broad) — but only through the scoring traversal, not by inflating those topics' stored interest scores.

**UI**: `TopicLevelRow` with tree lines (└), level badges (broad/topic/entity), +/- buttons. `groupTopicsByBroad()` organizes topics hierarchically. Smart expand: ≤2 broad categories → all expanded, 3+ → all collapsed with expand toggle.

### G10: Cross-Article Connections — IMPLEMENTED

**Approach chosen**: Two surfaces — inline annotations + bottom section.

1. **InlineCrossArticleAnnotation**: "Also in: [title]" annotations below paragraphs with cross-article connections. Max 2 per paragraph. Tap → queue to front. Long-press → navigate directly.
2. **ConnectedReadingSection**: Bottom section ("✦ CONNECTED READING") showing up to 5 connected articles. Each shows shared claim count, read/unread status, "+ Queue" button. Muted styling for already-read articles.

**Queue behavior**: LIFO via `addToQueueFront()`. User's rationale: "once I finish reading the article, the things I just read are the things I want to see right away."

**Threshold**: ≥0.78 cosine similarity (conservative, matches KNOWN threshold).

### Topic Consistency — SOLVED via LLM-Verified Normalization

**Problem**: Pipeline generated topics independently per article with no canonicalization. Found 2.9% hierarchy inconsistency even on 15 synthetic articles (e.g., "reading-tools" under both "knowledge-management" and "personal-tools").

**Solution**: Two-layer approach:
1. **Prompt-level guidance**: `_get_topic_hint()` injects existing categories into the extraction prompt so the LLM generates consistent topics from the start.
2. **Post-extraction normalization**: `topic_normalizer.py` validates against `topic_registry.json`. New topics get LLM merge-or-create decisions with full registry context (including include/exclude descriptions).

**Otak lessons applied**: Include/exclude descriptions are the key to LLM disambiguation (from `tree_balance.py`). Hard limits prevent unbounded growth. Shallow hierarchy (max 2 levels) avoids Otak's 315-domain proliferation from 8 intended categories.

**Otak mistakes avoided**: No recursive splitting, no organic tree growth, no unbounded depth, no self-balancing complexity.

---

## Exploration Directions for the Agent

### Priority 1: Claim Presentation in Reader
- Should claims be margin annotations, interleaved callouts, or hybrid?
- How to handle articles with 2 claims vs 15 claims?
- Should "known" claims be collapsed/hidden or just dimmed?
- Can claims be anchored to specific paragraphs in the article text?

### Priority 2: Topic Hierarchy Feedback
- How to let user signal interest at broad vs specific vs entity level?
- What should the post-read interest card look like with hierarchical topics?
- Should the feed show which LEVEL of a topic matched? (e.g., "matched because: AI orchestration" vs "matched because: Claude Code")
- How to prevent "interested in Claude Code" from flooding feed with every Claude Code mention?

### Priority 3: Claim-Level Feedback UI
- Best gesture/button for "I knew this" / "Save" / "Tell me more"?
- Should "Tell me more" immediately trigger a research agent?
- How to handle "Tell me more" at different specificity levels?
- What feedback does the model need vs what does the user want to express?

### Priority 4: Cross-Article Connections
- When and how to show that a claim appears in other articles?
- Queue vs navigate for cross-references?
- How to avoid noise when many articles share common claims?
- Should connections be shown in claims view, full text view, or both?

---

## Mockup Files for Reference

All mockups are in `/Users/stian/src/petrarca/mockups/`:
- `mockup-1.html` — Feed with swipe + topic drill-down
- `mockup-4.html` — Reader with margin annotations + queue
- `mockup-11.html` — Reader with queue + related articles + link auto-ingest
- `mockup-12.html` — Reader with interleaved claim callouts
- `mockup-13.html` — Activity log
- `mockup-14.html` — Web split panel + keyboard
- `mockup-15.html` — Topic browser

Previous design round mockups in `/Users/stian/src/petrarca/app/mockups/`:
- `mockup-5.html` — Earlier reader with margin annotations (pre-queue concept)

Synthetic test data: `/Users/stian/src/petrarca/app/data/synthetic-articles.json`

---

## Key User Quotes (Full Context)

On topic specificity:
> "For triage, it's a bit more complicated than what do I know something. [...] It's like a topic tree, maybe. It's about AI coding. It's about Claude Code. It's about orchestration. Which can both be generic to AI coding and specific to Claude Code."

On claims:
> "I'm still not exactly sure if I want the claims on top or as part of the article. And I'm not exactly sure the best way to give feedback on the claims. Or see feedback, meaning seeing connections to existing things. I think we need to probably iterate here quite a bit."

On cross-references:
> "Instead of clicking into that article, clicking it to add it to the top of the inbox so that the next article I see would be this one."

On learning paths:
> "The suggested learning paths are interesting as a concept, but I don't know enough about it or how we would implement it in the app."

On scores:
> "I don't like the knowledge coverage at all. Ranked by novelty should be the default, but it doesn't have to be a headline."

On related articles:
> "While reading an article, I might also want to see related articles at the bottom in different dimensions so that I can kind of branch out."

On auto-ingest:
> "Clicking on a link in an article should immediately trigger downloading and processing and putting it on the top of my feed without distracting my current reading. And if we want to be really fancy about it, maybe we even want to show some indicator by the link showing that it's processing."
