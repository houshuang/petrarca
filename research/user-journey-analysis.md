# User Journey Analysis: Assumptions vs. Reality

*A critical examination of how Petrarca expects Stian to use the app over weeks and months, checked against the design vision, user interviews, and current implementation. March 3, 2026.*

---

## Overview

This document walks through the expected user journey from first launch through habitual use over several weeks. For each phase, it:
1. States the **assumed behavior** (what the design expects the user to do)
2. Checks against **interview evidence** (what the user actually said they want/do)
3. Identifies **implementation status** and **gaps**

---

## Phase 1: First Launch & Content Discovery (Day 1)

### Assumed Behavior
The user opens the app for the first time and sees 51 articles from their Twitter bookmarks and Readwise history. They need to quickly understand what's here and decide what to engage with.

### What the Design Expects
1. User sees the Feed tab with a list of articles
2. User switches between List / Topics / Triage views to find their preferred way in
3. User tries Triage mode — swiping through cards to quickly sort "read later" vs "skip"
4. User taps into 2-3 interesting articles and reads at summary/claims depth
5. Within 10-15 minutes, the user has triaged a batch and read a few summaries

### Interview Evidence
- *"Opens Twitter during breaks, sees interesting stuff, bookmarks it, never returns"* — the bookmark graveyard problem. The user has a pile of content they saved but never processed.
- *"Not in the mood for long reading during work"* — first session is likely during a work break, 2-5 minutes.
- *"Quick triage — is this worth my time?"* — the user's primary first-session need.
- *"Most Claude Code articles are fluff... occasionally there's a genuinely new tool or deep framework insight"* — user expects quality filtering, not just a list.

### Implementation Status: PARTIALLY MEETS EXPECTATIONS

**What works:**
- Three feed modes (List/Topics/Triage) are built
- Triage swipe cards with spring physics feel good
- Novelty badges show "Mostly new" / "X% new" / "Mostly known"
- Continue Reading section for partially-read articles
- 51 articles across diverse topics

**Gaps identified:**

1. **Cold start problem with novelty scores.** On first launch, every concept is "unknown," so every article shows "Mostly new" (~100%). The novelty badge is meaningless until the user has signaled on many claims. The design vision says *"Score incoming articles for genuine novelty. Surface only what's worth your time"* — but on day 1, the system can't distinguish novel from familiar content.
   - **Severity: HIGH** — the core value proposition (knowledge-aware filtering) is absent at the moment it matters most.
   - **Possible fix:** Use an onboarding survey ("What topics do you already know well?"), or pre-seed knowledge states from Readwise reading history (`reading_progress > 0` items imply familiarity with their topics).

2. **No quality/credibility signal.** Interview 1 explicitly mentions: *"Filter by novelty AND credibility. Credibility of author matters but is hard to assess."* There is no credibility indicator anywhere in the current app. All 51 articles appear equal.
   - **Severity: MEDIUM** — not blocking but a stated user need.

3. **Triage doesn't explain itself.** The user swipes right/left/up but there's no indication of what these decisions *do* downstream. The design vision says *"the system should be smarter about what to show, not demanding about what to do."* Triage feels like work without clear payoff.
   - **Severity: LOW** — will become clear with use, but a brief tutorial/explanation would help.

4. **51 articles may feel too curated / too small.** The user has 200 Twitter bookmarks and 11,598 Readwise items. 51 might feel like "someone already filtered for me" rather than "my bookmarks, made smarter."
   - **Severity: MEDIUM** — depends on whether user perceives this as a sample or the whole thing.

---

## Phase 2: First Deep Reading Session (Day 1-3)

### Assumed Behavior
The user opens an article from the feed and enters the fluid depth reader. They scroll from summary through claims into sections and possibly the full article.

### What the Design Expects
1. User sees the summary first (30 seconds)
2. Scrolls down to claims — taps on claims to signal "knew this" or "new to me" (2 minutes)
3. If interested, continues to section summaries and selectively reads sections (5-15 minutes)
4. If deeply interested, reads the full article
5. Depth indicator shows progress; reading state persists across sessions
6. Time guidance bar helps the user decide how deep to go

### Interview Evidence
- *"Never know how much time you have. Rabbit holes lose you."* — user needs to control reading depth.
- *"6 minutes waiting for someone = atomic reading. Fireplace with a book = deep reading."* — the same article might be engaged at different depths in different contexts.
- *"Whatever the interaction is, it must work well on mobile during quick sessions"*
- *"Reading itself IS the primary signal"* — friction must be minimal.

### Implementation Status: MOSTLY MEETS EXPECTATIONS

**What works:**
- Fluid depth transitions work — single scrollable document with zone tracking
- Claim signals (knew_it / interesting / save) are inline and low-friction
- Implicit time tracking silently captures scroll velocity, pauses, revisits
- Time guidance bar shows estimated time per depth level
- FloatingDepthIndicator shows current zone
- Reading state persists to AsyncStorage
- Connection prompting shows related articles at the end

**Gaps identified:**

5. **The "full article" zone renders raw markdown poorly.** Known issue: *"Full article zone shows raw markdown syntax (######, broken links)"* and *"Section headings show as `[` in reader."* The moment the user scrolls into the deepest level — the moment they're most engaged — the experience breaks. This directly contradicts *"Reading is the interface, not a chore."*
   - **Severity: HIGH** — this is the core reading experience degrading at the crucial moment.

6. **No way to record a thought without breaking flow.** Voice notes exist (mic button in top bar) but they require stopping scrolling, tapping a small button, and waiting for recording to start. The interview says: *"quickly use audio to take comments as I'm reading"* and *"Low-friction capture (don't break reading flow)."* The current implementation breaks flow.
   - **Severity: MEDIUM** — voice recording exists but friction may prevent use.

7. **Claim signals feel disconnected from reading.** Claims appear as blue cards in the Claims zone AND as highlights in the full text — but the user might not understand why they should signal on claims. The design vision says the system uses this to model what you know, but there's no visible feedback loop ("you signaled 'knew this' on 5 AI claims → your AI knowledge score went up").
   - **Severity: MEDIUM** — users need to understand *why* they're signaling to stay motivated.

8. **No "I need more context" action.** Interview 2 describes a common reading scenario: *"Sometimes needs more background knowledge before continuing."* The design vision includes *"AI enhancement (pre-reads, background summaries)"* but there's no way to request this while reading. The "research this" button doesn't exist yet.
   - **Severity: MEDIUM** — a core vision feature that's missing.

9. **Reading session boundary is unclear.** When the user leaves the reader and comes back, the app remembers depth but not scroll position. The design vision emphasizes *"No losing your place"* and the interviews mention *"Forgets context between sessions (what was happening in that chapter?)."* Currently, re-entering an article starts at the top with the right depth unlocked, but no "here's where you were" indicator.
   - **Severity: MEDIUM** — important for the "pick up where I left off" use case.

---

## Phase 3: Building the Knowledge Model (Week 1)

### Assumed Behavior
Over the first week, the user reads 10-20 articles at various depths. Their claim signals accumulate, the knowledge model populates, and novelty scores become meaningful.

### What the Design Expects
1. User reads a few articles per day (2-5 min sessions on commute/breaks, occasional 15+ min session)
2. Claim signals ("knew this" / "new to me") update concept states
3. Concepts transition from unknown → encountered → known
4. Novelty badges on feed cards become accurate — articles the user would find familiar show "mostly known"
5. The Knowledge Dashboard in Progress tab shows topic coverage growing
6. Reviews start appearing (encountered concepts at 1-day intervals, known concepts at 7-day)

### Interview Evidence
- *"The system should be smarter about what to show, not demanding about what to do"* — the model should build passively.
- *"Reading itself IS the signal"* — minimal explicit effort required.
- *"I now feel like I have enough overview of Caesar that I can confidently read articles... and 'place them'"* — the goal is reaching a threshold of understanding per topic.

### Implementation Status: PARTIALLY MEETS EXPECTATIONS

**What works:**
- Concept extraction pipeline produces 69 concepts across 39 topics
- Claim-to-concept matching with content-word overlap (0.3 threshold)
- Three-state concept lifecycle (unknown → encountered → known)
- NoveltyBadge updates as concepts change state
- KnowledgeDashboard shows per-topic progress bars
- Auto-creation of review states when concepts transition

**Gaps identified:**

10. **The concept-claim matching is probably too coarse.** 69 concepts across 51 articles means ~1.4 concepts per article. Many articles will have 0-1 concepts matched. A user could read 10 articles and only update 5-10 concept states — not enough granularity to make novelty scores diverge meaningfully. The design vision envisions *"Extract key claims/insights from each article"* and *"Compare against your knowledge model: what's genuinely new?"* — but the model is too thin.
    - **Severity: HIGH** — the knowledge model needs more granular coverage to deliver its promise.
    - **Possible fix:** Extract more concepts per article (aim for 5-10 per article, 200-500 total). Or use claims directly as knowledge units alongside concepts.

11. **Passive signal collection may be too slow.** The user needs to actively tap claim signals for concept states to update. But the interview says *"reading itself IS the signal."* The implicit tracking (dwell time, pauses) is logged but never feeds back into the knowledge model. A user who reads an entire article without tapping any claim buttons generates zero concept updates.
    - **Severity: HIGH** — the gap between "reading is the signal" and "you must tap buttons" is the single biggest assumption mismatch.
    - **Possible fix:** Use implicit signals (reading past the claims zone, spending >30s on a section) to auto-update concept states at lower confidence.

12. **No feedback loop on model accuracy.** The user has no way to correct the model if it's wrong. If the system thinks you "know" a concept because you signaled "knew this" on one claim, but actually you only knew that specific fact, there's no correction mechanism. The design vision mentions *"open algorithms"* and *"transparent and configurable,"* but the knowledge model is opaque.
    - **Severity: MEDIUM** — becomes important as the model grows.

13. **Topic coverage is uneven.** 39 topics across 51 articles means some topics have 1 article and 1 concept. The Knowledge Dashboard will show mostly empty progress bars. The user's broad interests (history, literature, AI, policy) may not all be represented in the initial 51 articles.
    - **Severity: LOW** — will resolve with more content.

---

## Phase 4: Review Sessions Begin (Week 1-2)

### Assumed Behavior
After a few days of reading, the Review tab shows due concepts. The user does 5-10 minute review sessions.

### What the Design Expects
1. Concepts encountered during reading appear in the Review tab after their initial interval (1 day for encountered, 7 days for known)
2. User sees the concept, thinks about connections, optionally writes a note
3. User rates understanding (again / hard / good / easy)
4. Intervals expand or contract based on rating
5. Over time, stable concepts settle to monthly+ intervals; struggling ones stay frequent
6. Reviews feel like "gentle re-engagement" not "homework"

### Interview Evidence
- *"Spaced repetition on every single fact is going to be completely useless and unmotivating"* — fact drilling is explicitly rejected.
- *"A very soft touch... prompt me to make connections with previous material"* — the interaction should feel like a helpful nudge.
- *"Revisit via synthesis, not source: show what you took away, not the raw original"* — reviews should surface the user's own notes, not just the concept text.
- *"How does this connect to X?" rather than "What year was Y?"* — generative, not recall-based.
- *"Must NOT be another note-taking obligation"* — reviews should be genuinely optional.

### Implementation Status: PARTIALLY MEETS EXPECTATIONS

**What works:**
- Review cards prompt "How does this connect to what you've been reading?" — generative, not recall-based
- Optional note-taking (user can "just rate" without writing)
- 4-point understanding scale (confused / fuzzy / solid / could teach)
- Previous notes shown on review cards
- Voice transcripts linked to concepts shown during review
- Completion screen shows topic knowledge overview

**Gaps identified:**

14. **Reviews may feel too abstract.** The review card shows the concept text (e.g., "LLM code generation") and asks "How does this connect?" — but concepts are often generic labels. Without rich context (which articles discussed this? what specific claims? what were your notes?), the prompt may feel meaningless. Source articles are listed but not excerpted.
    - **Severity: HIGH** — this is the most experimental part of the app and the user explicitly worried about it: *"I am very unsure about this. Much easier to figure out in terms of language learning."*
    - **Possible fix:** Show 1-2 relevant claim excerpts from source articles alongside the concept. Show the user's own voice note transcripts more prominently.

15. **Review volume may overwhelm.** With 69 concepts, after a week of reading, many could become due simultaneously. Even if the user only encounters 20 concepts in week 1, that's 20 reviews due on day 2 (at 1-day intervals). The design vision says *"Soft touch over hard obligations — no streaks, no guilt, no 'you have 47 items due'"* — but the UI shows "1 of 10 concepts" progress, implying a queue to complete.
    - **Severity: MEDIUM** — need to cap review sessions and make it easy to skip/defer.
    - **Possible fix:** Limit review queue to 5-7 items per session. Add a "done for now" button early.

16. **No synthesis across concepts.** The design vision emphasizes *"Synthesis over source — when revisiting, show what you took away, not the raw original."* But reviews show individual concepts in isolation. There's no "here's what you've learned about Byzantine history across 4 articles" synthesis view.
    - **Severity: MEDIUM** — a promised but unbuilt feature.

17. **The "again" rating feels punitive.** Rating a concept "again" (confused) resets the interval to 1 day and increases difficulty. But the user might legitimately not remember a concept because they only briefly encountered it, not because it's hard. The SRS metaphor may not map well to open-ended concept engagement.
    - **Severity: LOW** — the 4-point scale is reasonable but might need tuning.

---

## Phase 5: Voice Notes in Context (Week 1-3)

### Assumed Behavior
While reading, the user occasionally records voice notes — reactions, questions, connections to other reading. These are transcribed and linked to the knowledge model.

### What the Design Expects
1. User reads something thought-provoking → taps mic → speaks 10-30 seconds → stops recording
2. Transcription happens asynchronously (Soniox API)
3. Transcript is matched against article's concepts
4. Matched concepts update to "encountered" state
5. Voice transcripts appear in Progress tab (with concept pills) and Review tab (linked to concepts)
6. Over time, the user's own voice notes become the primary material for review — *"The user's own thoughts are more valuable than the source material"*

### Interview Evidence
- *"I have often missed the opportunity to take voice notes while reading"*
- Voice notes have 4 purposes: feedback, research trigger, personal notes for review, cross-source synthesis
- *"Voice → transcription → linked to reading context → fed into knowledge model"*
- The interviews describe voice as a RICH signal — not just "I liked this" but actual articulated thoughts

### Implementation Status: PARTIALLY MEETS EXPECTATIONS

**What works:**
- Recording works (expo-av, high quality preset)
- Soniox transcription with multilingual support
- Transcript → concept matching (0.2 threshold)
- Concept pills shown under transcripts in Progress tab
- Voice transcripts shown in Review cards
- Measurement events for all voice interactions

**Gaps identified:**

18. **Voice notes as research triggers are completely unbuilt.** The interview describes the #1 voice note use case as: *"Launch a background agent on the Hetzner VM that researches a question."* This is the "quick research button" — speak a question, get diverse perspectives waiting next time you open the app. None of this exists. Voice notes are recorded and transcribed but never acted upon beyond concept matching.
    - **Severity: HIGH** — this was a key interview request and is unbuilt.

19. **Transcript quality is untested with real usage.** The Soniox integration polls for results but there's no handling of partial transcripts, language mixing (the user reads in 10+ languages), or ASR errors in concept matching. The 0.2 content-word threshold may produce false matches on noisy transcripts.
    - **Severity: MEDIUM** — needs real-world testing.

20. **Voice notes don't become review items themselves.** The interviews say: *"Notes that become part of incremental reading themselves"* and the design vision says *"User's own notes and voice reflections are the primary material for re-engagement."* Currently, voice transcripts can appear *alongside* concept reviews, but the transcripts themselves are never scheduled for revisiting. A powerful voice note from week 1 is just as likely to be forgotten as the article it was about.
    - **Severity: HIGH** — goes against the core design principle that user's own thoughts are most valuable.

---

## Phase 6: Habitual Use & Pattern Emergence (Week 2-4)

### Assumed Behavior
The app becomes part of the daily routine. The user opens it on commute/breaks for 2-5 minute sessions and occasionally does deeper reading.

### What the Design Expects
1. **Morning commute (5 min):** Check Review tab for 3-5 due concepts, rate them. Scan Feed for new articles.
2. **Work break (2 min):** Triage 5-10 new articles via swipe cards.
3. **Lunch (10 min):** Continue reading an article from where you left off.
4. **Evening (20+ min):** Deep read 1-2 articles, record voice notes, explore related articles.
5. Knowledge model becomes accurate enough that novelty scores are genuinely useful.
6. Topics the user has deeply engaged with show as "mostly known" — articles about those topics rank lower.
7. The user starts to feel the "hooks" effect — new articles about familiar topics feel more placeable.

### Interview Evidence
- *"Time-respectful — useful in 30 seconds, rewarding in 30 minutes"*
- *"Bidirectional: atomic CAN PREPARE for deep read, atomic CAN REINFORCE after deep read"*
- The user reads on commute, at work, at home — multi-context, multi-duration
- *"Core pattern: start reading → follow interesting threads → rabbit hole → never come back → lose place"* — the app should prevent this

### Implementation Status: PARTIALLY MEETS EXPECTATIONS

**What works:**
- Continue Reading section surfaces partially-read articles
- Review tab provides a natural "2-minute check" activity
- Topic clustering helps exploration across interests
- Knowledge dashboard shows growth over time

**Gaps identified:**

21. **No new content pipeline.** The 51 articles are static — bundled as JSON, requiring a developer to run the Python pipeline and redeploy. After week 1, the user has triaged all articles. There's nothing new. The app becomes a review-only tool with no fresh material.
    - **Severity: CRITICAL** — this is the single biggest structural gap. The design vision describes *"constant stream from Twitter/RSS/newsletters"* but the app is a static bundle. Without new content, the app dies after the initial batch is processed.
    - **Possible fix:** Add an in-app "refresh" that fetches and processes new bookmarks. Or run the pipeline on a schedule on the Hetzner VM with the app pulling new content.

22. **No notification or pull to return.** The review system creates due items, but there's no push notification or indicator that reviews are waiting. The user has to remember to open the app. Most read-later apps die from abandonment — the app needs a reason to come back.
    - **Severity: HIGH** — passive apps get forgotten.
    - **Possible fix:** Daily push notification: "3 concepts to review + 2 new articles matching your interests."

23. **The "two modes" distinction is absent.** The design vision identifies Mode A (Firehose — fast tech/current content) and Mode B (Deep Shelf — books, enduring scholarship). The current app only serves Mode A. There's no way to add a book, no chapter-level reading, no context restoration for long-form works. The user's history/literature interests (Pirenne, Huizinga, Mimesis) are entirely unserved.
    - **Severity: MEDIUM** for now — Mode B was explicitly planned as "build later." But it means the app only addresses half the user's reading life.

24. **No cross-session synthesis.** The user reads 4 articles about AI agents across 2 weeks. The design vision promises: *"When multiple articles cover the same topic, generate a synthesis view."* This doesn't exist. Each article remains siloed. The Related Articles feature shows connections at the concept level, but there's no "here's what 4 articles collectively say about AI agents."
    - **Severity: MEDIUM** — a core promised feature, especially important for the "hooks" goal.

---

## Phase 7: Long-Term Value & Knowledge Growth (Month 1-3)

### Assumed Behavior
After several weeks, the user has engaged with 100+ articles across many topics. The knowledge model is rich enough to genuinely filter content and surface connections.

### What the Design Expects
1. New articles are scored accurately — the user trusts the novelty indicators
2. Reviews have settled into a sustainable cadence (5-10 per week for mature concepts)
3. The user has a visible, growing map of what they know across topics
4. When reading something new, the system prompts connections to past reading
5. Voice notes have accumulated into a personal commentary layer
6. The system has enough data to suggest research directions

### Interview Evidence
- *"'Done' = able to PLACE new knowledge"* — the ultimate success criterion
- *"If the system knew everything I had read in the past few years... it could help me prompt me to make connections"*
- *"Synthesis + my notes/thoughts"* when revisiting past material
- *"I read 4 books about Caesar, natural repetition at high level. But knowledge fades as you move away"* — the system should prevent this fade

### Implementation Status: DOES NOT MEET EXPECTATIONS

**Gaps identified:**

25. **No reading history import.** The user has 4 years of Readwise data (11,598 items), years of Kindle highlights, and Roam/Logseq notes. None of this feeds the knowledge model. The system starts from zero despite the user having a rich reading history. The design vision says *"Model what you know"* — but the model ignores years of prior reading.
    - **Severity: HIGH** — the system could be pre-seeded with existing reading data to bypass the cold start.

26. **No growth trajectory visualization.** The Knowledge Dashboard shows current state but not change over time. The user can't see whether their knowledge is growing, stagnating, or developing blind spots. The experiment plan mentions *"Growth over time chart"* as planned but unbuilt.
    - **Severity: LOW** — nice to have, not blocking.

27. **Connection prompting only works at article boundaries.** The "Related Reading" section appears at the end of the full article — but the interview describes wanting connections *during* reading: *"When I read something new it could prompt me to make connections with previous material."* A concept mentioned mid-article should trigger a subtle indicator: "You've seen this concept in 3 other articles."
    - **Severity: MEDIUM** — the right idea is implemented but in the wrong place.

28. **No way to manage or curate the knowledge model.** As the model grows, there will be incorrect states (concept marked "known" when it was really just one claim), orphaned concepts (from articles the user didn't care about), or topics the user wants to deprioritize. There's no UI for editing concept states, merging duplicate concepts, or removing irrelevant ones.
    - **Severity: MEDIUM** — will become important as the model scales.

---

## The Biggest Assumption Mismatches

Ranked by impact on the core user journey:

### 1. Static Content (Gap #21) — CRITICAL
**Assumption:** Content flows continuously.
**Reality:** 51 articles, frozen at build time. No refresh mechanism.
The entire app is built around the concept of triaging and filtering a stream of content. Without the stream, it's a one-time demo. This must be solved for the app to be usable beyond week 1.

### 2. Passive Knowledge Building (Gap #11) — HIGH
**Assumption:** Reading itself builds the knowledge model.
**Reality:** Only explicit claim taps update concept states.
The user was very clear: *"Reading itself IS the primary signal."* But the system requires deliberate button-tapping on every claim. The implicit signals (dwell time, scroll patterns, pauses) are collected but never used. This creates a gap between the stated philosophy and the actual mechanism.

### 3. Cold Start (Gap #10 + #1) — HIGH
**Assumption:** The knowledge model will become accurate over time.
**Reality:** With 69 concepts and coarse matching, the model may never reach useful granularity with the current article set. And on day 1, everything looks the same.
The system needs either more granular concepts (200-500), or a way to pre-seed knowledge from external data (Readwise history, explicit user input), or both.

### 4. Background Research (Gap #18) — HIGH
**Assumption:** Voice notes trigger research agents.
**Reality:** Voice notes are transcribed and matched to concepts but never acted upon.
This was the user's most distinctive feature request — *"spawns a background agent that finds diverse perspectives"* — and it's entirely absent.

### 5. Content Quality (Gap #5) — HIGH
**Assumption:** The reader renders content beautifully at all depths.
**Reality:** The full article zone shows raw markdown with broken formatting.
The reading experience — the core interface — degrades at exactly the depth level that indicates highest engagement.

---

## User Journey Summary: What Actually Happens Today

Here's the realistic week-by-week user journey with the current implementation:

**Day 1:** User opens app. Sees 51 articles. Tries triage — swiping is fun. All articles show "Mostly new" (unhelpful). Reads 2-3 articles at summary/claims depth. Marks a few claims. Feels promising.

**Day 2-3:** Opens app again. Reads a few more articles. Taps some claim signals. Notices the novelty badges haven't changed much (too few concepts updated). Tries the Topics view. Maybe records a voice note.

**Day 4-7:** Reviews start appearing in the Review tab. First few reviews feel interesting ("How does this connect?"). But the concepts are generic and context-thin. The user writes a note or two, rates a few. Starts to feel like homework.

**Week 2:** User has read maybe 15-20 of the 51 articles. Feed is getting stale — no new content. Triage mode is empty ("All caught up!"). Reviews are the main reason to open the app. But without new reading material, reviews feel disconnected from active learning.

**Week 3+:** Without new content, the app becomes a pure review tool. The user opens it less frequently. Reviews pile up but feel less relevant because there's no new reading to connect them to. The app goes dormant — exactly the fate of every read-later tool the user has tried.

### What Would Break This Cycle

The critical path to a sustainably useful app requires three things:

1. **Continuous content flow** — new articles arriving regularly, either through scheduled pipeline runs, in-app refresh, or background processing on Hetzner
2. **Richer passive knowledge building** — reading behavior (time, depth, scroll patterns) should update concept states without requiring explicit taps
3. **Active follow-up on voice notes** — the "research this" loop that gives the user a reason to return and find something new waiting

These three changes would create the virtuous cycle the design envisions: new content → reading → knowledge growth → better filtering → more relevant content → deeper engagement.

---

## Recommendations by Priority

### Must-fix for viability
1. **Content refresh mechanism** — run pipeline on schedule, or add in-app refresh
2. **Implicit signal → knowledge model** — reading an article's claims zone or spending >60s in a section should auto-update relevant concepts
3. **Fix full-article markdown rendering** — the reader must work well at all depths

### Important for engagement
4. **Pre-seed knowledge model** — import topics from Readwise reading history (articles with reading_progress > 0.5 imply topic familiarity)
5. **More granular concepts** — aim for 5-10 per article, 200-500 total
6. **Cap review sessions** — max 5-7 items, with "done for now" option prominent
7. **Richer review context** — show claim excerpts and voice transcripts on review cards

### Important for the vision
8. **Background research agents** — the voice note → research → results pipeline
9. **Cross-article synthesis** — "What 4 articles say about X"
10. **In-reading connection prompts** — highlight concepts that appear in previously-read articles

### Nice to have
11. **Return-to-position in reader** — scroll to where user left off
12. **Growth trajectory** — knowledge map over time
13. **Knowledge model curation** — edit/merge/remove concepts
14. **Push notifications** — gentle reminders for reviews + new content
