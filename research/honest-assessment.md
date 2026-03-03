# Honest Assessment of Petrarca

Frank self-critique of the project state. What works, what doesn't, what's risky, and what experiments would actually move the needle.

## What's Actually Good

- **Progressive disclosure reader** (summary → claims → sections → full) is genuinely novel. No other read-later app structures articles this way. It respects the user's time by letting them decide how deep to go.
- **Voice notes linked to reading context** create a unique form of annotation. Speaking a reaction while reading is faster and more natural than typing, and the link to the specific reading context preserves meaning.
- **Triage swipe interface** is fun and appropriate for mobile. The physical gesture of swiping maps well to quick keep/skip decisions.
- **Content sync from server** means the pipeline can evolve independently of the app. Article processing, concept extraction, and content quality improvements don't require app updates.
- **Spaced attention scheduling for concepts** (not just flashcards) is creative. Reviewing concepts rather than facts is a meaningful twist on SRS.
- **Research agents triggered from reading context** is a compelling interaction. The idea of spawning background research while reading, with results waiting next time, is genuinely useful.

## Honest Critique

### Concept Matching is Word Overlap

The entire knowledge model — novelty scoring, connection indicators, concept state updates — uses simple content-word Jaccard overlap. This means:

- "Machine learning transforms healthcare" and "Healthcare needs better ML" might not match
- Concepts with common words get false-positive matches
- The 30% threshold was chosen arbitrarily, not validated
- No semantic understanding — word overlap ≠ concept overlap

This is the foundation the whole system rests on, and it's held together with string.

### No Data Analysis

51 articles and 69 concepts exist, but zero interaction logs have been analyzed. We don't know:

- Does anyone (even Stian) actually use the progressive depth?
- Do the novelty scores correlate with reading behavior?
- Are concept state transitions meaningful or noise?
- Which articles get read vs. ignored and why?

Building features without analyzing whether existing features work is a classic trap. The logging infrastructure exists — the analysis doesn't.

### Connection Moment is Buried

The "This connects to [concept] across [N] articles" indicator is the most intellectually exciting feature — it shows knowledge building across articles. But it's a small disclosure triangle at the bottom of claims, easy to miss. The connection moment should be prominent, surprising, delightful.

### Review is Generic

The review tab shows concept text + rating buttons, but there's no context about why this concept matters to the user's reading journey. No "you first encountered this in [article]" or "you signaled 'interesting' on a related claim." The review feels disconnected from the reading experience.

### Mode B is Missing

There are two distinct reading modes:

- **Mode A** (currently built): Process incoming bookmarks/RSS — triage, filter, read what's new
- **Mode B** (not built): "I want to learn about X" — guided exploration, not filtering

Mode B (the Sicily research use case) requires fundamentally different UX: topic seeding, breadth-first exploration, subtopic triage, research feedback loops. None of this exists yet.

### Content Quality Varies

Some articles are donation pages, bitcoin addresses, boilerplate. The validation script catches some but not all. Content quality directly impacts the credibility of the concept model.

## Key Assumptions Ranked by Risk

1. **Users will signal on claims** (HIGH RISK) — Claim signaling is core to knowledge model updates. If users skip past claims without signaling, the model stagnates. Implicit encounter (60s dwell) is a fallback but much coarser.

2. **Concepts (not claims) are the right knowledge unit** (MEDIUM RISK) — Claims are article-specific; concepts cross articles. But current concept extraction via LLM produces variable quality. Some concepts are too broad, others too specific.

3. **Progressive depth creates better comprehension** (MEDIUM RISK) — No evidence yet. Users might just skip to full article, making the intermediate levels dead code.

4. **Novelty scoring drives reading priority** (LOW-MEDIUM RISK) — The idea is sound (show new stuff first) but the word-overlap implementation may not capture real novelty.

5. **Spaced review of concepts improves retention** (LOW RISK) — Well-established in SRS literature, but our concept-level granularity (vs. flashcard facts) is less proven.

## Experiments That Would Actually Matter

1. **Depth usage patterns** — Do users progress through depth levels, or jump to a single level? Instrument time-per-zone and track transitions.

2. **Signal → Model accuracy** — When users signal "knew it" on a claim, do the matched concepts actually reflect their knowledge? Log the concept matches and let users verify.

3. **Connection moment impact** — Track when connection indicators are shown, tapped, and whether they lead to reading the connected article. The rate of "connection → read related article" is the key metric.

4. **Novelty score vs. engagement** — Correlate novelty scores with actual reading depth and time spent. If high-novelty articles don't get read deeper, the scoring is broken.

5. **Mode B user journey** — Give user a topic, observe the exploration pattern. What's the read/skip ratio across subtopics? Does guided exploration feel productive or overwhelming?

## The Deep Insight: Scaffolding vs. Counting

The current system *counts* knowledge (69 concepts, X% known, Y encountered). But what users actually want is *scaffolding* — the feeling that reading article N was enriched because of what they learned from articles 1 through N-1.

Counting tells you: "You know 42% of AI concepts"
Scaffolding tells you: "This article's argument about RLHF makes more sense because you already understand reward modeling from the Anthropic paper you read last week"

The connection indicator is a baby step toward scaffolding. The review system is pure counting. The challenge is making the app feel like a knowledgeable reading companion, not a progress tracker.

## Surprising Delights

Despite the critique, some things work better than expected:

- The feed with novelty badges does create a "what should I read?" answer
- Voice notes while reading capture genuine in-the-moment reactions
- The topic clustering view reveals reading patterns the user didn't notice
- Research agents returning diverse perspectives is genuinely useful when it works
- The whole system runs without a backend database — static JSON + AsyncStorage is surprisingly viable

---

*Written 2026-03-03 as pre-flight assessment before the first real testing week.*
