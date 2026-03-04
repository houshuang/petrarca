# Innovative Reading Application Patterns: Research Report for Petrarca Book Reader

**Date**: 2026-03-04
**Scope**: Multi-book reading UX, context restoration, cross-text connections, progressive disclosure, argument tracking, experimental ideas
**Focus**: What works, what's novel, what Petrarca should build

---

## Table of Contents

1. [Multi-Book Reading UX](#1-multi-book-reading-ux)
2. [Context Restoration After Absence](#2-context-restoration-after-absence)
3. [Cross-Text Connection Visualization](#3-cross-text-connection-visualization)
4. [Progressive Disclosure in Long-Form Reading](#4-progressive-disclosure-in-long-form-reading)
5. [Argument Tracking Across Texts](#5-argument-tracking-across-texts)
6. [Innovative Experiments Worth Trying](#6-innovative-experiments-worth-trying)
7. [Concrete Recommendations for Petrarca](#7-concrete-recommendations-for-petrarca)

---

## 1. Multi-Book Reading UX

### Heptabase: The Best Current Approach

Heptabase's reading workflow (documented by founder Alan Chan) is the most developed model for multi-source reading. The five-step process:

1. **Highlight** all important paragraphs while reading
2. **Dissect** content into granular concept cards — one concept per card, one-sentence title summarizing the core idea
3. **Map** relationships between concepts on spatial whiteboards using arrows and proximity
4. **Group** related cards into named sections that serve as "memory anchors for future review"
5. **Integrate** with prior knowledge by reusing concept cards across multiple whiteboards

The crucial insight from Heptabase: "Real deep understanding doesn't come from the relationship between two books but from the relationship between all the concepts in these two books." This is exactly Petrarca's thesis — that connections live at the concept level, not the document level.

**Key UX patterns:**
- Split-panel editing: source document open alongside a whiteboard for seamless extraction
- Drag-to-create: select text blocks, drag onto whiteboard as new cards
- Reusable cards: the same concept card referenced across multiple whiteboards without duplication
- Link-backed references: replace source content with links to concept cards, displaying titles as summaries
- Spatial organization: physical positioning on whiteboards mirrors mental models

**Limitation for Petrarca:** Heptabase requires heavy manual work. Users create every card and draw every arrow themselves. Petrarca's pipeline already extracts concepts and claims automatically — the challenge is making the *output* as navigable as Heptabase's *input*.

### Obsidian/Logseq: Bidirectional Links as Cross-Text Glue

The PKM tools use Zettelkasten-derived workflows:
- Each source gets a "literature note" with highlights and metadata
- Atomic "permanent notes" contain one idea each
- Bidirectional links `[[concept]]` create implicit connections across sources
- Graph views show the emergent network

**Friction problem:** Users report that note-taking overhead deters reading. The tools optimize for note-taking power users, not for readers. Zotero-to-Obsidian workflows (via Zotero Integration plugin) reduce some friction but still require significant manual curation.

**What Petrarca can learn:** The graph view in Obsidian is mostly useless for discovery (too many nodes, no clear hierarchy). But the *inline backlinks panel* — showing every note that references the current concept — is extremely useful. Petrarca should show "everywhere this concept appears" inline while reading.

### Readwise Themed Review: Retroactive Cross-Source Discovery

Rather than requiring upfront organization, Readwise's Themed Review uses AI to pull together highlights across all sources by theme: "Just describe what you're looking for, like an author, topic, book, or mood." No tagging needed. Users can also "chat with their entire library of highlights" as a super-powered search.

**What's novel:** This inverts the traditional workflow. Instead of "organize while reading, discover later," it's "read freely, discover retroactively." The AI does the cross-referencing work.

**Limitation:** Themed Review requires an accumulated corpus of highlights. It doesn't help during the first reading — only after significant highlight accumulation. Also currently web-only.

**Petrarca opportunity:** Combine pipeline-generated concepts (no manual highlighting needed) with themed review-style discovery. The system already knows every concept across every article and book. A "find me everything I've read about X" feature could work immediately on the existing data.

### Roam Research: Block-Level References

Roam's unique contribution is block references — every bullet point has a unique ID and can be embedded or referenced from anywhere. When the original is updated, all references update automatically.

This enables a reading pattern where a claim from Book A can be *embedded* in notes about Book B, maintaining a live link. The reader builds a web of cross-references at the paragraph level, not just the page level.

**For Petrarca:** The `CrossBookConnection` model captures this at the claim level. The reader should allow tapping a connection to show the referenced claim inline, with a "go to source" option.

---

## 2. Context Restoration After Absence

### The Forgetting Problem (Research)

Ebbinghaus forgetting curve research shows:
- **50%** of new information forgotten within 1 hour
- **70%** forgotten within 24 hours
- Only **20%** retained after 1 month without review
- Without deliberate review, forgetting happens rapidly — but spaced repetition and active recall significantly slow the process

For book reading specifically, after a week away the reader retains a vague impression of the topic but has lost most specific arguments, names, and logical connections.

### Context-Dependent and State-Dependent Memory

Memory research identifies two retrieval advantages:

**Context-dependent memory:** Recall improves when the external environment matches the encoding context. For reading, this means seeing the same text layout, the same surrounding passages, and the same visual markers (highlights, annotations) acts as a powerful retrieval cue.

**State-dependent memory:** Internal physiological/psychological state during learning affects recall. This is harder to replicate, but the practical implication is that re-exposure to one's own *reactions* (highlights, annotations, voice notes) during previous reading sessions helps reinstate the mental state.

### What Existing Apps Do (and Don't)

**Kindle:** Reopens at last position. No context restoration beyond that. For a book untouched for weeks, the reader sees paragraph 347 of 1200 with zero context for where they are in the argument. This is the baseline — it's terrible.

**Audible:** Provides brief audio recaps of previous chapters when resuming. Closer to the right idea, but limited to fiction narratives.

**Kairos (Every.to):** Has a "catch up on previous sections" feature accessible via the AI button. The AI can summarize what came before, making it easier to resume. This is the best current implementation for non-fiction.

**SuperMemo:** Doesn't solve this problem directly — instead, it *avoids* it by scheduling re-readings. You don't return to a text after weeks of absence because the algorithm keeps presenting it at intervals. The downside: SuperMemo's scheduling is opaque and requires discipline.

**Language learning apps:**
- Duolingo: daily streaks and notifications (extrinsic motivation, doesn't help memory)
- Anki/FSRS: spaced repetition resurfaces information at optimal intervals (addresses memory directly, but for discrete items rather than narrative context)

**Key finding: No mainstream reading app solves context restoration well.** This is a genuine open problem and a real opportunity.

### Design Principles for Context Restoration

1. **Temporal context cues:** Show *when* the reader last read, what zone they were in, how long they spent. "You were here 8 days ago, reading the Claims section for 12 minutes."

2. **Argument recap:** Brief AI-generated summary of what the reader has already read, emphasizing the argument arc: "So far, the author has argued X, then pivoted to Y. You marked Z as interesting."

3. **Personal signal replay:** Show the reader's own highlights, "interesting" signals, and voice notes from previous sessions. This is the strongest retrieval cue — seeing one's own marginalia reinstates context-dependent memory.

4. **Progressive re-entry:** Don't dump the reader at exact scroll position. Offer a "catch-up" mode: recap of last section, then transition to new material.

5. **Spaced repetition bridge:** Key claims from previously-read sections should appear in concept reviews during the gap between reading sessions, creating a "reactivation loop" where review sessions maintain some reading context even during absence.

---

## 3. Cross-Text Connection Visualization

### Citation Network Tools

**Connected Papers** visualizes academic citation relationships using co-citation analysis and bibliographic coupling. Papers that share citations or references cluster together even without direct citations, revealing "conceptual neighborhoods." Node size represents citations, node color represents publication year (lighter = older, darker = recent), connecting lines show relationship strength.

**Key design insight:** Arranging papers by *conceptual similarity* (not just direct citation) reveals hidden clusters. Two papers that never cite each other but cite many of the same sources are likely related. This is applicable to Petrarca's concept model — articles sharing many concepts should be considered related even if they're from completely different sources.

**Litmaps** adds a timeline dimension: papers arranged left-to-right by publication date with citation flows as arrows. This reveals how ideas develop over time — foundational work on the left, derivative work on the right, with the citation arrows showing influence direction.

**For Petrarca:** A timeline visualization of when the reader engaged with different texts, with concept connections as links, would show the reader's intellectual journey over time.

### Scite.ai: Agreement/Disagreement Classification

Scite.ai is the most directly relevant model for Petrarca. It classifies every citation as:
- **Supporting:** presents evidence for the cited work
- **Contrasting:** presents evidence against or disagreeing
- **Mentioning:** neutral reference without evidential relationship

Over 880 million classified citation statements. Their finding: contrasting citations take ~113 days longer to appear than supporting ones, suggesting critical discussion develops more slowly in the literature.

**Petrarca already models this** via `CrossBookConnection.relationship` with values `agrees`, `disagrees`, `extends`, `provides_evidence`, `same_topic`. The gap is in visualization — making these relationships visible and navigable while reading.

### InfraNodus: Structural Gap Detection

InfraNodus converts text into word co-occurrence networks and identifies "structural gaps" — areas where clusters of ideas could be connected but aren't. These gaps represent "areas where there is great potential to discover something new."

The tool identifies:
- Main topical clusters (communities of frequently co-occurring words)
- The most influential concepts (highest betweenness centrality)
- Structural gaps between clusters (missing connections between idea groups)

And then suggests: "Asking research questions that can bridge those gaps will lead you to new ideas."

**For Petrarca:** Apply this not to individual texts but to the user's *entire reading history*. Build a concept co-occurrence graph from all highlighted passages, interesting-marked claims, and voice notes. Identify structural gaps — topic clusters in the reader's knowledge that have no cross-connections. These gaps become reading suggestions: "You've read extensively about X and Y but nothing connects them."

### TheBrain: Focus+Context Navigation

TheBrain uses three relationship types (parent, child, sibling) with a radial layout centered on the selected node. Selecting a new node rearranges the entire graph around it. This "focus + context" approach is far more usable than static graph views.

**Critical lesson:** Graph visualizations with 200+ nodes are always useless. They look impressive in screenshots but provide no actionable information. The only effective pattern is focus+context: select a node, see its local neighborhood (2-3 hops), navigate by selecting neighbors.

**For Petrarca:** If building a concept explorer, use TheBrain's pattern: show one concept at center, its immediate connections (other concepts, articles, book sections) around it, and allow "walking" the graph by tapping connections.

### LiquidText: Spatial Annotation Workspace

LiquidText splits the screen into a document pane and an infinite workspace. Notes, excerpts, and images are placed on the workspace and can be connected to anything — other notes, passages in the document, passages in other documents.

"You can connect anything to anything. Literally anything on and within the digital text itself, between multiple digital texts, and between the digital texts and your note-taking workspace."

**Key UX innovation:** Pulling excerpts from the document into the workspace is frictionless — just drag. This reduces the barrier between reading and note-taking to near zero.

**For Petrarca:** The split-panel pattern could work for the book reader — reading text on one side, with the reader's highlights, voice notes, and cross-book connections displayed spatially on the other side.

---

## 4. Progressive Disclosure in Long-Form Reading

### Cognitive Load Research

- **Working memory capacity:** 5-9 chunks of information simultaneously (Miller's law)
- **Optimal sentence length for comprehension:** 130-150 characters (Mikk 2008), with longer sentences causing working memory overload
- **Chunking effectiveness:** Students using reading chunking significantly improved in literal, inferential, and evaluative comprehension; they reported reduced cognitive load and anxiety
- **Longer passages under acceleration:** Reading acceleration is most beneficial with relatively longer passages, suggesting chunk size should vary with reading speed/mode

### SuperMemo's Incremental Reading Model

SuperMemo treats reading itself as a spaced repetition task:
- Import articles at priority levels (0% = highest priority, 100% = lowest)
- Extract passages with Alt+X, creating child elements at inherited priority
- The algorithm interleaves reading across ALL imported materials — you never finish one before starting another
- Priority of questions and answers is determined by parent extract priority
- Priorities can be modified while reading

The crucial innovation compared to Petrarca's current model: **reading is scheduled by the algorithm, not left to the user.** The system decides when to resurface a text, based on priority and spacing. Articles aren't "done" — they keep coming back until the reader has extracted everything they want.

**Trade-off:** SuperMemo's interface is notoriously complex. Users need significant training. The power comes at the cost of accessibility. Petrarca should extract the scheduling principle without the interface complexity.

### Kairos and Adler's Four Levels of Reading

Kairos structures AI assistance around Mortimer Adler's framework:
- **Elementary:** AI explains dense passages in plain language
- **Inspectional:** Chapter summaries and catch-up features for previewing
- **Analytical:** AI asks probing questions about arguments and assumptions
- **Syntopical:** Cross-text connections surface philosophical parallels across books

The innovation: each level is a different *mode of engagement*, not just different amounts of text. Elementary is about comprehension, inspectional about survey, analytical about critique, syntopical about synthesis.

**For Petrarca:** The current depth zones (briefing → claims → terms → full text) map roughly to inspectional → analytical. What's missing:
- **Elementary mode:** "Explain this passage to me" (AI on-demand in reader)
- **Syntopical mode:** cross-book concept connections as a reading surface

### Blinkist/Headway: Summary-to-Depth Funnel

Blinkist offers 15-minute "blinks" covering key takeaways. Headway provides flexible summary types (quick insights vs. detailed overviews). Both serve as funnels to deeper reading.

An interesting user behavior: summaries often motivate full book purchases because they create awareness of what was stripped away. The summary makes the reader conscious of the depth they're missing.

**For Petrarca:** The briefing zone already serves this function. The key is making the transition from briefing to full text feel like gaining access, not like switching modes. Each depth level should hint at what the next level reveals.

### Dynamic Chunking (2024-2025 AI Research)

Recent research introduces adaptive text segmentation:
- **Meta-Chunking** identifies optimal segmentation points using perplexity and margin sampling — chunks break at natural thought boundaries
- **Hierarchical text segmentation** creates multi-level chunks (sentence → paragraph → section → chapter)
- **Semantic chunking** preserves logical boundaries like complete arguments or examples

Applied to Petrarca: rather than showing section boundaries as defined by the author, AI could identify natural "thought units" within sections. A section about three different trade routes could be expandable/collapsible at the thought-unit level, not just shown as one monolithic block.

---

## 5. Argument Tracking Across Texts

### Kialo: Structured Argument Mapping

Kialo is the most sophisticated argument mapping platform:
- Tree structure with thesis at root, supporting/opposing arguments as branches
- Each claim can have supporting/opposing sub-arguments recursively
- Impact ratings on arguments
- Collaborative construction
- Used by 1M+ users for structured deliberation

**Key design pattern:** The tree structure makes argument relationships explicit and navigable. "I disagree because X" is a child node of the claim being opposed. You can trace any conclusion back through its reasoning chain.

**Limitation:** Entirely manual. No automatic extraction from text. Also focused on single debates, not cross-text argument networks.

### Scite.ai: Automated Argument Context at Scale

Scite classifies 880+ million citation statements as supporting, contrasting, or mentioning. No manual input — deep learning classifies citation intent automatically from surrounding text.

**Finding:** Contrasting citations take ~113 days longer to appear than supporting ones. Critical engagement is slower than confirmatory citation.

**For Petrarca:** The claim extraction pipeline already identifies claims. The next step is automated classification of claim relationships — does Claim A from Book X support, contradict, or extend Claim B from Book Y? The `CrossBookConnection` data model already has this; the pipeline needs to reliably populate it.

### ThinkerAnalytix / Harvard: Argument Mapping as Skill

ThinkerAnalytix teaches argument mapping as a transferable critical thinking skill. Arguments are represented as boxes connected by support/attack arrows, with every conclusion tracing back through explicit reasoning steps.

**Their research finding:** Students who learn to construct argument maps show improved critical thinking across domains, not just in the practiced domain. The act of making argument structure explicit improves reasoning in general.

**Implication for Petrarca:** Showing argument structure isn't just informational — it's pedagogical. The Argument Skeleton view (recommendation E below) isn't just a nice feature, it potentially improves the reader's thinking skills.

### AMQuestioner (ACM 2025): AI-Driven Argument Map Questions

Uses interactive argument maps in discussion, with AI-generated questions that challenge students to examine argument structure: "What assumption does this claim rely on?" "What evidence would weaken this argument?"

This is the bridge between argument mapping and Socratic tutoring — the AI doesn't just display the argument, it probes the reader's understanding of it.

### What No One Does Yet

No tool currently:
1. Automatically extracts arguments from long-form non-fiction text
2. Tracks how those arguments relate across multiple texts
3. Visualizes the result inline during reading
4. Questions the reader about the argument structure

This is the specific gap Petrarca's data model targets. The `BookClaim` with `supports_claim` and `is_main`, plus `CrossBookConnection` with relationship types, provides the data layer. The interface layer is the open problem.

---

## 6. Innovative Experiments Worth Trying

### A. AI as Socratic Reading Partner (Not Summarizer)

**Research backing:** A 2025 study in Frontiers in Education tested four AI-assisted reading approaches — summaries, outlines, Q&A tutor, and Socratic chatbot. The Socratic chatbot improved comprehension most for low-performing readers. Summaries actually *worsened* high-performing readers' scores.

**Why this matters:** Passive AI assistance (summarization) can reduce engagement. Active questioning increases it. Petrarca's audience (a power reader) is the demographic most likely to be *harmed* by summaries and most helped by Socratic questioning.

**Implementation idea:** After the reader engages with a claim zone, surface 1-2 questions:
- "The author claims X. What evidence from your own reading would support or challenge this?"
- "You marked this 'interesting' — what specifically was new to you?"
- "How does this connect to [concept the reader marked 'knew_it' in another text]?"

These questions should be personalized based on the reader's knowledge model, not generic.

### B. Devil's Advocate Mode

When reading a persuasive piece, automatically generate the strongest counterarguments — sourced from actual contrasting positions in other texts the user has read. Not generic "here are some counterpoints" but grounded in the reader's own reading history:

"Author A argues X. But in the article you read last Tuesday, Author B presented evidence that..."

This combines Scite.ai's citation intent classification with personal reading history.

### C. Structural Gap Detection for Personal Knowledge

Apply InfraNodus-style text network analysis to the user's entire reading history:

1. Build a concept co-occurrence graph from all highlighted passages, interesting-marked claims, and voice notes
2. Use community detection (Louvain or label propagation) to find concept clusters
3. Identify structural gaps — pairs of clusters with high within-cluster density but no cross-cluster edges
4. Surface gaps as reading suggestions: "You've been reading about Renaissance humanism and modern knowledge management, but nothing connects these interests. Here are three articles that bridge the gap."

This turns reading history into a generative system — the corpus itself suggests new reading directions.

### D. Temporal Reading / Texts That Unfold Over Time

Andy Matuschak's concept of "timeful texts" extended beyond flashcards:

- Chapters are scheduled, not binge-read: "Read 2 sections per day for 12 days"
- Between sessions, key claims appear in spaced review
- Each session opens with a Context Restoration panel connecting to previous sessions
- "Bridging questions" generated between sessions: "Before continuing, consider: how might Ch. 3's argument apply to a modern democratic context?"
- The book becomes a *designed learning experience* spread across time, not a static artifact to plow through

This is SuperMemo's scheduling principle without SuperMemo's complexity.

### E. Reading State Preservation and Replay

Context-dependent memory research suggests that reinstating encoding context helps retrieval. A reading app could:

- Capture the reader's "state" at each session: time of day, reading speed, highlights made, signals given, scroll patterns
- When resuming, replay a compressed version of the previous session: "Last Tuesday evening, you spent 18 minutes here. You highlighted 3 passages and marked this claim interesting. Your pace was slow, suggesting careful reading."
- Present the reader's own marginalia — not the text — as the re-entry point
- This is the strongest context-dependent memory cue available: the reader's own cognitive footprint

### F. Gamification That Respects Intelligence

Research (JITE 2023) shows gamification increases reading time by 30% and improves comprehension — but only when game elements are tied to meaningful achievement.

**Patterns that work for a power reader:**
- **Quests, not points:** "Read three perspectives on [topic]" is a meaningful quest; "Read for 20 minutes" is a treadmill
- **Progress as mastery:** Show concept knowledge growing, not reading streaks
- **Curiosity loops:** Surface a tantalizing connection or gap, then let the reader choose whether to pursue it
- **Challenge calibration:** Present arguments just beyond what the reader has encountered — a "zone of proximal development" for intellectual growth
- **Completion as understanding:** "You've encountered this concept in 4 texts and can now see how different authors treat it" — completion means understanding, not just reading

**What to avoid:**
- Streak counters (punish absence, create anxiety)
- Points for time spent (incentivize leaving the app open)
- Badges for article counts (incentivize shallow skimming)

### G. The "Mnemonic Book" — Orbit Applied to Book Sections

Andy Matuschak's Orbit embeds spaced repetition prompts directly within web text. Readers encounter questions interleaved with prose. Key findings:

- Readers report increased attention and comprehension-checking
- "Safety" feeling — confidence that important details will be reinforced
- Sustained contact with material over months
- Limitation: "implicitly authoritarian" — readers must accept author's judgment about what to remember
- Limitation: reader-authored prompts work better than expert-authored ones for transfer

**Petrarca opportunity:** Generate personalized Orbit-style prompts for book sections based on the reader's knowledge model. The system knows which concepts are new to the reader and can focus prompts on those, avoiding questions about concepts already marked "knew_it." This addresses Orbit's "authoritarian" limitation — prompts are personalized, not one-size-fits-all.

---

## 7. Concrete Recommendations for Petrarca

Ordered by impact and feasibility, with specific reference to Petrarca's existing data model.

### Priority 1: Context Restoration Panel

**When:** Reader opens a book section they haven't touched in 3+ days
**What:** A "Welcome Back" card before jumping to last position

```
┌─────────────────────────────────────┐
│  Welcome back to "The Prince"       │
│  Last read: 8 days ago (Ch.3, §2)   │
│                                     │
│  The argument so far:               │
│  Machiavelli argued that effective  │
│  rulers must learn "how not to be   │
│  good." You marked this ★          │
│                                     │
│  Your highlights (3):               │
│  • "Fortune is the arbiter of..."   │
│  • "Men judge more by the eye..."   │
│  • [voice note: 0:34]              │
│                                     │
│  Since last visit:                  │
│  2 concept reviews touched ideas    │
│  from this book                     │
│                                     │
│  [Resume reading]  [Review Ch.3]    │
└─────────────────────────────────────┘
```

**Data sources:** `BookReadingState.last_read_at`, `personal_thread` entries, highlights, claim signals, concept review history. Recap text generated via `claude -p` during idle time or on-demand.

**Why first:** No other reading app does this well. Immediate, noticeable improvement for the #1 friction point in long-form reading. Leverages data Petrarca already collects.

### Priority 2: Inline Tension/Connection Callouts

**When:** Reader encounters a claim that relates to a claim in another text they've read
**What:** Inline callout card at the relevant passage

```
┌─ ⚡ Tension ─────────────────────────┐
│ This contradicts what you read in    │
│ "Discourses on Livy" (Ch.4, §1):    │
│                                      │
│ HERE: "A prince must learn how not   │
│ to be good"                          │
│                                      │
│ THERE: "Republican virtue requires   │
│ moral consistency in leaders"        │
│                                      │
│ [Go to passage]  [Note this tension] │
└──────────────────────────────────────┘
```

Color-coded: green for agrees, red/amber for disagrees, blue for extends, gray for same_topic.

**Data sources:** `CrossBookConnection` already captures relationship type, target section, target claim text. The reader already has `ConnectionIndicator` components for article connections.

**Why second:** The cross-book connection data already exists. This makes it visible during reading instead of hidden in data structures. Directly addresses the "multi-book simultaneous reading" use case.

### Priority 3: Argument Skeleton View

**When:** Reader wants to see the logical structure of a chapter or section
**What:** A new depth zone (or toggle on Claims view) showing argument tree

```
THESIS: Effective rulers must prioritize
        results over moral virtue
  │
  ├── BECAUSE: Human nature is self-interested (§15)
  │     └── EVIDENCE: "Men judge by the eye..." (§18)
  │
  ├── BECAUSE: External threats require pragmatism (§19)
  │
  └── HOWEVER: Tension with republican ideals (§26)
        └── [→ "Discourses" §3.2]
```

**Data sources:** `BookClaim.supports_claim`, `BookClaim.is_main`, `CrossBookConnection`. Build tree from existing claim relationships and render as collapsible outline.

**Why third:** Novel — no reading app offers this. Directly uses existing data model features. The ThinkerAnalytix research suggests this is pedagogically valuable beyond just being informative.

### Priority 4: Socratic Mode

**When:** Toggled on in reader settings
**What:** AI questions based on current reading and knowledge model

After reading a claim section:
- "What evidence would change your mind about this?"
- "You marked this 'knew_it' — where did you first encounter this idea?"
- "How does this relate to [concept from different book]?"

After highlighting:
- "Why did this stand out? How does it connect to [recent concept review]?"

**Implementation:** Pre-generate questions per section via `claude -p` during content processing. Personalize at read-time by filtering/adapting based on the user's claim signals and concept states.

**Why fourth:** Research strongly supports Socratic over summary AI for power readers. But requires more infrastructure (question generation, personalization logic) than the first three recommendations.

### Priority 5: Knowledge Gap Finder

**When:** Periodic analysis, surfaced in Feed or Discovery view
**What:** Concept cluster analysis revealing reading gaps

```
You've been reading about:
  Cluster A: Renaissance political philosophy (12 concepts)
  Cluster B: Modern leadership theory (8 concepts)

These clusters share 0 connections in your reading.
  Bridging suggestion: "Machiavelli and Modern Management"
```

**Implementation:** Build concept co-occurrence matrix from `Concept.source_article_ids`. Community detection via Louvain or label propagation. Gaps = cluster pairs with no cross-connections. Run in content pipeline.

### Priority 6: Temporal Reading Schedules

**When:** User starts a new book, offered as optional mode
**What:** AI-suggested reading schedule with between-session integration

- "Read 2 sections per day for 12 days"
- Between sessions: key claims appear in concept review queue
- Each session opens with Context Restoration panel (Priority 1)
- "Bridging questions" between sessions connect just-read material to upcoming material
- Optional push notifications: "Before continuing Ch.4 today, consider how the argument in Ch.3 applies to..."

**Implementation:** Scheduling logic on top of `BookReadingState`. Bridging questions via `claude -p`. Integration with existing spaced review system for between-session reinforcement.

### Priority 7: Adaptive Depth Based on Knowledge Model

**When:** Reader opens any new section
**What:** System adjusts default depth based on concept familiarity

- 80%+ of section concepts already known → start at Claims, skip Briefing
- Mostly new concepts → recommend starting at Briefing
- Section connects to a previously-marked "interesting" claim → highlight connection before reading
- Personalized, automatic — no user configuration needed

**Data sources:** Concept knowledge states (`ConceptState.state`), claim signals from other sections, `CrossBookConnection` data.

---

## Key Takeaways

1. **Context restoration is the biggest unsolved problem** in long-form reading apps. Petrarca already collects the data needed to solve it. Building a good "Welcome Back" panel would be immediately differentiated.

2. **Cross-text connections at the claim level** are Petrarca's structural advantage. No other reading app models `agrees`/`disagrees`/`extends` relationships between specific claims across texts. Making these visible inline during reading would be genuinely novel.

3. **Socratic AI beats summary AI** for engaged readers. The research is clear: questioning improves comprehension while summarization can reduce it. Petrarca should ask questions, not provide answers.

4. **Gap detection in personal knowledge** is an untried idea with strong theoretical backing (InfraNodus, cognitive research on creative insight at structural gaps). No reading app does this.

5. **Temporal reading** — scheduling book reading across time with between-session reinforcement — combines SuperMemo's core insight with Matuschak's "timeful text" vision in a way nobody has shipped in a usable mobile app.

6. **Avoid graph views with many nodes.** Every knowledge graph visualization looks great in demos and is useless in practice. Use TheBrain's focus+context pattern: one concept at center, immediate neighbors around it, navigate by selection.

---

## Sources

- [Heptabase: Best Way to Acquire Knowledge from Readings](https://wiki.heptabase.com/the-best-way-to-acquire-knowledge-from-readings)
- [Heptabase: How the Founder Uses It](https://medium.com/heptabase/how-heptabases-founder-use-heptabase-for-learning-research-planning-and-writing-b11b1829ff79)
- [Andy Matuschak: Mnemonic Medium](https://notes.andymatuschak.org/Mnemonic_medium)
- [Andy Matuschak: Augmented Reading](https://notes.andymatuschak.org/z8DRL5y5vMuXA98uro9KeZ3)
- [Andy Matuschak: Orbit](https://github.com/andymatuschak/orbit)
- [Andy Matuschak: How to Write Good Prompts](https://andymatuschak.org/prompts/)
- [Andy Matuschak & Michael Nielsen: Quantum Country / Mnemonic Medium](https://notes.andymatuschak.org/Mnemonic_medium)
- [Kairos / Every.to: A New Way to Read](https://every.to/source-code/a-new-way-to-read)
- [Readwise: Themed Review](https://docs.readwise.io/readwise/guides/themed-reviews)
- [Readwise: Ghostreader](https://docs.readwise.io/reader/guides/ghostreader/overview)
- [Connected Papers](https://www.connectedpapers.com/about)
- [Litmaps](https://www.litmaps.com/)
- [Scite.ai: Smart Citation Index](https://direct.mit.edu/qss/article/2/3/882/102990)
- [Scite.ai: How Fast Does Disagreement Happen](https://scite.ai/blog/how-fast-does-scientific-disagreement-and-support-happen)
- [InfraNodus: Text Network Analysis](https://infranodus.com)
- [InfraNodus: Reading Features](https://noduslabs.com/features/reading/)
- [TheBrain: Non-Linear Visual Knowledge](https://www.thebrain.com/blog/enabling-ubiquitous-non-linear-visual-knowledge)
- [LiquidText](https://www.liquidtext.net/)
- [SuperMemo: Incremental Reading](https://help.supermemo.org/wiki/Incremental_reading)
- [SuperMemo: Incremental Reading Step by Step](https://supermemo.guru/wiki/Incremental_reading_step_by_step)
- [Kialo Edu: Argument Mapping Research](https://www.kialo-edu.com/research)
- [AMQuestioner: Interactive Argument Maps (ACM 2025)](https://dl.acm.org/doi/10.1145/3757551)
- [Frontiers: Argument Visualization Review (2025)](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1709300/abstract)
- [Frontiers: Socratic vs Summary AI for Comprehension (2025)](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1506752/full)
- [Ebbinghaus Forgetting Curve](https://nesslabs.com/ebbinghaus-forgetting-curve)
- [Context-Dependent Memory](https://www.simplypsychology.org/context-and-state-dependent-memory.html)
- [Dynamic Chunking for Reading (ACL 2025)](https://aclanthology.org/2025.acl-long.1538.pdf)
- [Meta-Chunking: Text Segmentation (2024)](https://arxiv.org/abs/2410.12788)
- [Gamification in Reading Instruction (JITE 2023)](https://www.jite.org/documents/Vol23/JITE-Rv23Art028Wang10900.pdf)
- [Yu-kai Chou: Beyond Points and Badges](https://yukaichou.com/gamification-study/points-badges-and-leaderboards-the-gamification-fallacy/)
- [Readever AI Reading Companion](https://www.funblocks.net/aitools/reviews/readever-2)
- [Roam Research Beginner's Guide](https://www.sitepoint.com/roam-research-beginners-guide/)
- [Obsidian/Logseq Comparison 2025](https://www.glukhov.org/post/2025/11/obsidian-vs-logseq-comparison/)
- [Zotero to Obsidian Research Workflow](https://gracehhchuang.com/2025/02/22/workflow-of-deepen-understanding-of-research-literature-transferring-highlights-and-metadata-from-zotero-to-obsidian/)
