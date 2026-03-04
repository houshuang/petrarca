# Innovative Reading UX for Multi-Book Deep Reading

*Research conducted 2026-03-04 for Petrarca's book reader feature*

This document focuses on UX patterns specifically relevant to Petrarca's multi-book reading experience, where books are broken into section-sized passages (5-15 min reads) and the system tracks cross-book connections, argument development, and reader knowledge state. It complements `reading-ui-research.md` (general reading UX) and `book-reader-design.md` (implementation plan) with deeper research into six areas that could differentiate Petrarca from existing reading apps.

---

## Table of Contents

1. [Cross-Text Connection Visualization](#1-cross-text-connection-visualization)
2. [Context Restoration and Re-Engagement](#2-context-restoration-and-re-engagement)
3. [Argument Tracking and Thesis Mapping](#3-argument-tracking-and-thesis-mapping)
4. [Progressive Disclosure for Book-Length Content](#4-progressive-disclosure-for-book-length-content)
5. [The Interleaved Reading Pattern](#5-the-interleaved-reading-pattern)
6. [Innovative Mobile UX Patterns](#6-innovative-mobile-ux-patterns)
7. [Synthesis: Design Recommendations for Petrarca](#7-synthesis-design-recommendations-for-petrarca)

---

## 1. Cross-Text Connection Visualization

How do existing tools make connections between passages from different sources visible, navigable, and useful?

### 1.1 LiquidText: The Collapsible Workspace

LiquidText (CHI 2011, Apple "Most Innovative App") pioneered a two-pane interface: the document on one side, a freeform workspace on the other. Its key innovations:

- **Pinch-to-collapse**: A vertical pinch gesture on the document collapses intervening pages, bringing two distant passages into proximity for comparison. The degree of finger movement controls how much text collapses, giving continuous rather than binary control. This is a physical metaphor -- squeezing pages together like compressing a physical book.
- **Cross-pane links**: Excerpts dragged to the workspace maintain live bidirectional links back to the source document. Tapping an excerpt jumps to the original context. Tapping the link indicator on a source passage shows all workspace excerpts derived from it.
- **Multi-document workspaces**: Up to 3-5 documents displayed simultaneously in the document pane, with workspace excerpts from different documents coexisting and connectable.
- **Ink connections**: Freehand lines drawn between workspace excerpts create visual connections. These are spatial and informal, not typed relationships.

**What works**: The spatial freeform workspace makes connections tangible. Researchers report that the ability to see source and synthesis simultaneously reduces the cognitive cost of cross-referencing.

**What doesn't work**: The workspace is proprietary and non-exportable. Connections are spatial, not semantic -- they don't know *what kind* of connection they represent (agreement? contradiction? elaboration?). The pinch gesture requires an iPad-sized screen.

Sources: [LiquidText CHI 2011 paper](https://faculty.cc.gatech.edu/~keith/pubs/chi2011-liquidtext.pdf), [LiquidText website](https://www.liquidtext.net/)

### 1.2 MarginNote: Mind Maps from Annotations

MarginNote takes a different approach: annotations on documents automatically become nodes in a mind map or outline that grows alongside the reading.

- **Study Mode**: A split view with document(s) on one side and a growing mind map on the other. Highlights become nodes. Drag one node onto another to create a hierarchy.
- **Multi-document notebooks**: A single mind map can incorporate annotations from multiple PDFs and EPUBs. Nodes maintain links back to their source locations.
- **Cross-reference via hashtags**: Tagging annotations creates implicit connections across documents. The hashtag view shows all annotations with a given tag regardless of source.
- **Flashcard generation**: Any node can become a flashcard for spaced repetition review, combining reading with retention.

**Key insight for Petrarca**: MarginNote's "annotations become knowledge structure" pattern maps directly to how Petrarca's claim signals could build a cross-book concept map. The difference is that MarginNote requires the reader to manually organize the mind map, while Petrarca could automate the initial structure based on claim matching and let the reader refine it.

Source: [MarginNote features](https://www.marginnote.com/features), [MarginNote Study Mode manual](https://manual.marginnote.cn/en/study/)

### 1.3 Passages (CHI 2022): Reified Text Selections

The Passages research system (CHI 2022 Honorable Mention) introduces the concept of text selections as first-class persistent objects:

- A **passage** is a text selection enriched with metadata: source document, location, creation time, user tags, and comments.
- Passages can be **reused across tools** -- collected in one context, annotated in another, cited in a third.
- Passages maintain **provenance links**: you can always navigate back to the original context.
- The design is based on **reification** (making implicit actions into explicit objects) from the theory of instrumental interaction.

User studies with patent examiners and scientists showed that participants valued maintaining visibility of source material while working with excerpts and that transparent provenance links reduced confusion during document synthesis.

**Key insight for Petrarca**: Petrarca's cross-book connections are essentially passages with typed relationships. The CHI research validates that maintaining bidirectional provenance links (connection -> source passage) is critical for user trust and comprehension.

Source: [Passages: Interacting with Text Across Documents (CHI 2022)](https://dl.acm.org/doi/fullHtml/10.1145/3491102.3502052)

### 1.4 Roam Research: Block-Level Transclusion

Roam Research's key innovation is that every block (paragraph/bullet) has a unique identifier, enabling:

- **Block references**: Embedding a block from one page into another, with live updates. Edit the original, all references update.
- **Block embeds (transclusion)**: Full inline display of a block's content within another page.
- **Backlinks**: Every page shows all other pages that reference it, with surrounding context.

This creates a graph structure where ideas flow between documents without duplication. The overhead is that writers must think in blocks, not documents.

**Key insight for Petrarca**: When Petrarca shows a cross-book connection like "Runciman's claim about economics connects to Tuchman's claim about warfare," the connection card should be a *transclusion* -- showing the actual text of the connected claim inline, not just a link. The reader should be able to read both claims side by side without navigating away.

Source: [Roam Research](https://roamresearch.com/), [Block references discussion](https://www.zsolt.blog/2021/05/Addicted-to-block-references.html)

### 1.5 Obsidian and Spatial Canvas Tools

Obsidian's Graph View visualizes notes as nodes and links as edges, but users consistently report it's more aesthetically pleasing than practically useful. What does work:

- **Canvas**: A freeform spatial workspace where notes, images, and cards can be arranged and connected. Unlike the graph view, canvas relationships are intentionally created by the user.
- **InfraNodus plugin**: Uses 3D network visualization to show clusters of connected ideas and, critically, **gaps** between clusters -- areas where connections might exist but haven't been made.

Newer tools like **Heptabase** and **Scrintal** take the spatial canvas further:

- **Heptabase**: Whiteboards with cards (notes) that can be spatially arranged, grouped into sections, and connected. PDF annotations automatically create cards that live on whiteboards alongside other notes.
- **Scrintal**: "Floating tabs" allow working with multiple documents simultaneously. Creating a backlink automatically creates a visual arrow in the canvas, and vice versa -- the spatial and semantic representations stay in sync.

**Key insight for Petrarca**: A topic-level spatial view showing book sections as cards, with connection lines between related claims across books, could be a powerful synthesis tool. But the research consistently shows that automatically generated graphs (like Obsidian's) are less useful than user-curated spatial arrangements (like Canvas/Heptabase). Petrarca should seed the spatial layout with AI-detected connections but let the reader rearrange and prune.

Sources: [Obsidian Canvas Links](https://www.obsidianstats.com/plugins/canvas-links), [InfraNodus](https://infranodus.com/obsidian-plugin), [Heptabase](https://heptabase.com/), [Scrintal](https://scrintal.com/)

### 1.6 Social Annotation: Hypothesis and Perusall

Social annotation tools ground discussion at specific locations within documents:

- **Hypothesis**: An overlay that adds annotation sidebars to any web page. Annotations are "grounded" at a specific highlighted passage, reducing the need for explicit references.
- **Perusall**: Adds machine-learning-scored engagement metrics and automatic identification of "confusing" passages based on annotation density.

**Key insight for Petrarca**: While Petrarca is a single-user tool, the "grounding" principle applies to cross-book connections. Every connection should be grounded in a specific passage, not floating abstractly. The density of connections at a passage could serve as an implicit signal of conceptual importance (like Perusall's "confusion spotting" but for "connection density").

Sources: [Hypothesis vs Perusall comparison](https://web.hypothes.is/hypothesis-perusall-compared/), [Social annotation overview (Cornell)](https://teaching.cornell.edu/learning-technologies/collaboration-tools/social-annotation)

### 1.7 Gap Analysis: What Nobody Does Well

No existing tool does all of the following:

1. **Typed connections**: Most tools treat all connections as equivalent. LiquidText has lines, Roam has links, but neither distinguishes "agrees with" from "contradicts" from "provides evidence for."
2. **Automatic connection discovery**: Tools require manual linking. MarginNote's hashtags are the closest to automatic, but still require user tagging.
3. **Connection surfacing at reading time**: Even when connections exist, they're typically only visible in a separate workspace/graph view, not inline during reading.
4. **Mobile-first cross-document**: Most cross-document tools (LiquidText, MarginNote, Heptabase) are designed for iPad or desktop. Phone-sized cross-document reading is essentially unsolved.

**Petrarca's opportunity**: Combine automatic typed connection discovery (via claim matching in the pipeline) with inline surfacing during reading (connection callout cards already built) and a synthesis view for review. This combination doesn't exist in any current tool.

---

## 2. Context Restoration and Re-Engagement

When a reader returns after days or weeks, how can the app restore their mental context?

### 2.1 Current State of the Art

Most reading apps do the minimum:

- **Kindle**: Remembers page position, syncs across devices. Shows "% complete" and estimated time remaining. The "Before You Go" screen after finishing prompts for a rating and shows similar books.
- **Apple Books**: Page position sync. "Want to Read" and "Finished" collections. No context recap.
- **Kobo**: Reading statistics (time, pages per minute, sessions), badges/achievements for streaks. "Reading Life" gamification increased reading time by 50%+ after launch. But no content-level context restoration.
- **Libby**: Page sync, due date reminders. Annotations sync to Kindle on some titles.
- **Readwise Reader**: Ghostreader AI can summarize visible content, answer questions about the document. Context-aware chat that knows what's on screen. But no "here's what happened since you last read" summary.

**Gap**: None of these apps address the fundamental problem of *cognitive context restoration* -- helping the reader remember not just *where* they were, but *what they were thinking about* when they left.

### 2.2 Research on Task Resumption and Cognitive Load

Research on task resumption in multitasking contexts (Iqbal & Bailey, Brumby et al.) provides relevant findings:

- **Resumption lag**: The time between returning to an interrupted task and taking the first action. Context restoration (automatically showing task-relevant artifacts) significantly reduces resumption lag -- measured as reduced "edit lag" (time to first productive action).
- **Dedicated workspaces**: Research shows that having a workspace dedicated to each task (rather than a shared workspace) reduces cognitive load during resumption. This supports Petrarca's topic-based organization: returning to "History of Sicily" should show a dedicated view with all relevant reading state.
- **Cognitive resource theory**: Rest breaks between cognitively demanding tasks restore attentional resources. The implication is that context restoration should be gentle -- not overwhelming the reader with everything at once, but providing a graduated re-entry.

Source: [Dedicated workspaces and resumption times (ResearchGate)](https://www.researchgate.net/publication/301305771_Dedicated_workspaces_Faster_resumption_times_and_reduced_cognitive_load_in_sequential_multitasking)

### 2.3 The "Previously On..." Pattern

Television has solved this problem: the "Previously on..." recap before a new episode selectively replays key moments needed to understand what's coming next. This is a form of targeted context restoration. Some approaches to translating this to reading:

- **Series recap sites** (like Recaptains) provide book-by-book summaries for returning readers of long series. Authors themselves sometimes include "Previously" sections at the start of sequels.
- **Readwise's daily review**: Surfaces previously highlighted passages via spaced repetition, serving as ambient context maintenance rather than targeted restoration.
- **No reading app currently generates a "Previously on..." recap when the reader returns to a book after an absence.** This is an open design opportunity.

### 2.4 Recognition Over Recall

Nielsen's usability heuristic "recognition over recall" is directly applicable: returning readers should not have to recall what they read, but should be shown enough cues to recognize and rebuild their mental model. Effective cues include:

- Their own highlights and annotations (personal, distinctive, memorable)
- The last passage they read (with surrounding context)
- Key claims they engaged with (especially those they marked as surprising or disagreed with)
- Time-since-last-read as a signal for how much context to provide (2 days needs a sentence; 2 weeks needs a paragraph; 2 months needs a full recap)

### 2.5 Design Patterns for Petrarca

**The "Where Was I?" card** (already planned in book-reader-design.md) should be graduated:

| Absence | Context Level | Content |
|---------|--------------|---------|
| < 1 day | Minimal | Just the last section title and scroll position |
| 1-3 days | Light | Last section + your most recent highlight + next section preview |
| 3-14 days | Medium | "You were reading [topic] across [N] books. You last highlighted: [quote]. The argument so far: [1-2 sentences]. Your open questions: [from voice notes/text notes]" |
| 14+ days | Full | "Previously on [topic]..." with a generated narrative recap of the argument arc, your strongest reactions, and what's coming next. Include a mini-timeline showing your reading sessions. |

**Novel pattern: "Your Thread"** -- a chronological feed of the reader's own reactions, highlights, and voice notes, filtered to the current topic. This provides recognition cues that are deeply personal and memorable. The reader doesn't need to remember "what the author said" -- they need to remember "what *I* thought about what the author said."

**Novel pattern: "The Argument Bookmark"** -- instead of just marking a page position, the system saves a snapshot of the reader's current understanding: which claims they've engaged with, which they found surprising, what questions they had. On return, this snapshot is the basis for context restoration. This is fundamentally different from a page bookmark -- it's a *cognitive state* bookmark.

---

## 3. Argument Tracking and Thesis Mapping

### 3.1 The Problem

Books develop arguments across chapters. A claim in Chapter 2 may depend on evidence from Chapter 1 and be contradicted in Chapter 7. When reading multiple books on the same topic, argument threads interweave across books. No consumer reading app tracks this.

### 3.2 Argument Mapping Tools

Dedicated argument mapping tools exist but are designed for creating arguments, not tracking them while reading:

- **Kialo**: A tree-structured debate platform where every claim has pro and con arguments arranged hierarchically. The visual structure makes logical relationships explicit. As of 2020, it's the most widely adopted argumentation platform.
- **Rationale**: Web-based argument mapping for "structuring arguments, analyzing reasoning, identifying assumptions, and evaluating evidence." More academic than Kialo.
- **Argument maps** in general lay out premises and their relationships in a structured format, whereas texts present them linearly and "amid connecting grammar and prose" (Kialo research). The visual structure consistently improves comprehension of the logical relationships.

Source: [Kialo Edu research](https://www.kialo-edu.com/research), [Argument visualization survey (Frontiers in Education, 2025)](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1672105/full)

### 3.3 Argument Mining (NLP Research)

Computational argument mining is an active research field that could power Petrarca's argument tracking:

- **Argument components**: Claims (controversial statements) and premises (reasons/evidence). Each premise either supports or attacks a claim.
- **Argumentative relations**: Directed edges showing support or refutation between components, forming a hierarchical structure.
- **State of the art**: Models can parse argument structure in persuasive essays with reasonable accuracy. The challenge for books is that arguments span much longer texts and depend on implicit background knowledge.
- **Argument maps**: Pyramid-shaped hierarchical visualizations where propositions are connected by arrows showing logical relationships.

Source: [Argument Mining: A Survey (Computational Linguistics, MIT Press)](https://direct.mit.edu/coli/article/45/4/765/93362/Argument-Mining-A-Survey)

### 3.4 What Exists for Readers

Surprisingly little:

- **AI book summary tools** (Blinkist, Shortform, SuperSummary) provide chapter-by-chapter summaries but don't track argument development as a structure.
- **MarginNote's mind maps** can capture argument structure, but the reader must build it manually.
- **No tool tracks how an argument develops across chapters or across books.**

### 3.5 Design Patterns for Petrarca

**"The Argument So Far"**: After each chapter, the system generates a 2-3 sentence summary of how the argument has progressed. This is distinct from a chapter summary -- it's about the *development* of the argument, not a summary of *content*.

Example:
> "In Chapters 1-3, Runciman established that the Angevin administration was both extractive and culturally alien. Chapter 4 introduced the key counterargument: that Angevin Sicily was economically prosperous despite political grievances. You found this unconvincing (you marked the economic evidence as 'weak'). Chapter 5 begins the narrative of revolt, building on the tensions identified in Chapters 2-3."

**"The Argument Map"**: A simplified visual showing the book's main thesis, supporting arguments, and counterarguments as they've been introduced so far. Each node is linked to the section where it appears. Nodes the reader has engaged with are highlighted differently from nodes they haven't reached yet. This is like a Kialo tree, but generated from reading rather than from debate.

**"Cross-Book Argument View"**: When two books address the same topic, show their argument structures side by side:

```
Runciman's Argument          Tuchman's Argument

  Economic extraction -------- Economic prosperity
    (Ch 2, S3)                   (Ch 4, S1)
         |                          |
    Cultural alienation        Cultural exchange
    (Ch 3, S1)                   (Ch 4, S3)
         |                          |
    [Revolt was inevitable]    [Decline was gradual]
    (Ch 5, S1)                   (Ch 7, S2)
```

The connecting lines show where the arguments touch the same evidence or make competing claims. The reader's own position (from claim signals) colors the nodes.

**Novel pattern: "Argument Thread Notifications"**: When the reader encounters a claim in Book B that the system detects as contradicting or extending a claim from Book A that the reader engaged with, surface a notification-style card: "Tuchman disagrees with what Runciman said about trade routes [your highlight]. Want to compare?" This transforms passive cross-references into active reading prompts.

---

## 4. Progressive Disclosure for Book-Length Content

### 4.1 The Challenge

A typical non-fiction book is 60,000-100,000 words. A reading cluster of 4 books on the same topic approaches 300,000-400,000 words. How do you make this amount of content navigable without overwhelming the reader?

### 4.2 Shneiderman's Information-Seeking Mantra

"Overview first, zoom and filter, then details on demand" (Shneiderman, 1996) remains the foundational framework, with 8,000+ citations. Applied to multi-book reading:

1. **Overview**: Topic shelf showing all books, their progress, and key themes at a glance
2. **Zoom and filter**: Chapter/section view with argument summaries, filterable by topic or connection type
3. **Details on demand**: Individual section reader with full text, claims, annotations

Source: [The Eyes Have It (Shneiderman, 1996)](https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf)

### 4.3 Semantic Zoom

Semantic zoom changes what you see at each zoom level, not just the magnification:

- **Zoomed out**: Cards with titles and one-line summaries
- **Medium zoom**: Section previews with key claims visible
- **Zoomed in**: Full text with annotations

Unlike optical zoom (which just makes text bigger), semantic zoom shows qualitatively different representations at each level. Windows used this in its tile-based interface (zooming into a group changed from showing group names to showing individual items), and it maps directly to Petrarca's existing depth model (briefing -> claims -> sections -> full text).

**Key insight**: Petrarca already implements semantic zoom via its depth zones. The opportunity is to make the *navigation between depth levels* feel more like zooming than like switching modes. A pinch-to-zoom gesture that smoothly transitions between briefing and full text would make the depth model feel spatial and intuitive.

Source: [Semantic Zoom (InfoVis Wiki)](https://infovis-wiki.net/wiki/Semantic_Zoom), [Overview+Detail, Zooming, and Focus+Context review (Cockburn et al.)](https://dl.acm.org/doi/10.1145/1456650.1456652)

### 4.4 The Mnemonic Medium (Andy Matuschak)

Orbit/Quantum Country embeds spaced repetition prompts directly into narrative prose:

- As the reader progresses through text, they encounter review prompts at natural breakpoints.
- Author-provided prompts remove the burden of creating flashcards.
- Answering prompts provides immediate comprehension feedback.
- Prompts are later resurfaced via spaced repetition, maintaining long-term retention.

The mnemonic medium makes memory "programmable" -- the author can decide what readers should remember and embed that intention into the reading experience itself.

**Key insight for Petrarca**: The mnemonic medium validates embedding review/retention moments within the reading flow rather than separating them into a distinct "review" mode. Petrarca's claim cards with "I knew this" / "New to me" signals are already a lightweight version of this. The opportunity is to make the signals accumulate into a spaced repetition queue that resurfaces key claims at expanding intervals, as Petrarca already does for concepts but could do more explicitly for book claims.

Source: [Mnemonic medium (Matuschak)](https://notes.andymatuschak.org/Mnemonic_medium), [Orbit](https://withorbit.com/)

### 4.5 SuperMemo's Incremental Reading

SuperMemo's incremental reading system is the most mature implementation of progressive disclosure for reading:

- **Priority queue**: Articles/excerpts ranked by user-assigned priority. Most important material surfaces first.
- **A-Factor**: Controls how intervals between reviews increase (e.g., A-Factor of 2 means intervals double). This is simpler than full FSRS but effective for reading material.
- **Extract-condense workflow**: Read a section -> extract key passages -> condense extracts into cloze deletions -> review via spaced repetition. The material progressively shrinks from full text to atomic facts.
- **Knowledge tree**: Extracts maintain their position in a tree structure showing which article they came from, which section, etc.

**Key insight for Petrarca**: SuperMemo's extract-condense workflow is the original progressive disclosure for reading. Petrarca's depth model (briefing -> claims -> full text) inverts this: instead of the reader progressively extracting, the system progressively reveals. This inversion is more friendly but loses the active processing benefits of manual extraction. Consider a hybrid: system-generated progressive disclosure for the first encounter, but reader-directed extraction tools for deep engagement.

Source: [SuperMemo incremental reading](https://help.supermemo.org/wiki/Incremental_reading), [SuperMemo incremental learning](https://help.supermemo.org/wiki/Incremental_learning)

### 4.6 Polar Bookshelf: Pagemarks for Non-Linear Reading

Polar Bookshelf combines document management with incremental reading:

- **Pagemarks**: Visual indicators on the document showing which parts have been read, partially read, or unread. This enables non-linear reading -- you can mark sections as "read" even if you skipped earlier sections.
- **Annotation sidebar**: Highlights automatically appear in a sidebar that persists alongside the document.
- **Spaced repetition integration**: Any annotation can become a flashcard, synced to Anki.

**Key insight for Petrarca**: Pagemarks as a concept map well to Petrarca's section-based reading. Each section's reading state (unread -> briefing -> claims -> reading -> reflected) is effectively a multi-level pagemark. Visualizing these states across all sections of a book gives the reader an at-a-glance sense of their reading topology -- which parts they've engaged with deeply, which they've only skimmed, and which they haven't touched.

Source: [Polar Bookshelf incremental reading](https://getpolarized.io/docs/incremental-reading.html)

### 4.7 Readwise's Spaced Resurfacing

Readwise applies spaced repetition to highlights rather than facts:

- **Daily Review**: First half shows unprocessed highlights (random). Second half shows "Mastery" cards (spaced repetition, active recall format).
- **Probabilistic algorithm**: Uses a decay model with configurable half-lives (7/14/28 days) rather than date-based scheduling.
- **Per-book tuning**: Users can weight which books' highlights appear more frequently.

**Key insight for Petrarca**: Readwise validates that spaced repetition applied to highlights (not just facts) increases engagement. Petrarca could resurface not just concepts but entire claim-context pairs: "Two weeks ago, you highlighted this passage from Runciman. The connection to Tuchman's argument has since been strengthened by your reading of Chapter 7."

Source: [Readwise spaced repetition design](https://blog.readwise.io/hack-your-brain-with-spaced-repetition-and-active-recall/), [Readwise review FAQ](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights)

---

## 5. The Interleaved Reading Pattern

### 5.1 What Is Interleaving?

Interleaving means switching between topics/categories during learning rather than completing one topic before starting the next:

- **Blocked**: Read all of Book A, then all of Book B, then all of Book C (AAABBBCCC)
- **Interleaved**: Alternate between books by topic or chapter (ABCABCABC)

This is directly relevant to Petrarca's design of topic shelves where sections from different books on the same topic are interleaved in the reading queue.

### 5.2 The Evidence for Interleaving

The research evidence is strong and growing:

- **Memory benefit**: Effect sizes up to 0.65 for interleaved vs. blocked study.
- **Transfer benefit**: Effect sizes up to 0.66 -- interleaving helps apply knowledge to new problems.
- **Physics education**: Students who used interleaved practice recalled more relevant information and produced correct solutions 50% more often on Test 1 and 125% more often on Test 2.
- **Classroom studies**: Students answered 63% correctly on interleaved-concept quizzes vs. 54% on blocked-concept quizzes.
- **Meta-analysis**: A systematic review found interleaving benefits were greatest "when differences between items are subtle," extending to both art-based and science-based learning.

Sources: [Interleaved practice in physics (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8589969/), [Systematic review of interleaving (Firth, 2021)](https://bera-journals.onlinelibrary.wiley.com/doi/10.1002/rev3.3266), [Discriminative contrast hypothesis (Kang & Pashler, 2012)](https://link.springer.com/article/10.3758/s13421-012-0272-7)

### 5.3 Why It Works: Two Hypotheses

**The Discriminative Contrast Hypothesis**: When exemplars from different categories are juxtaposed, learners' attention is drawn to features that help *discriminate* between categories. In reading: when Runciman's claim about economics is followed by Tuchman's claim about economics, the reader naturally notices where they agree and disagree. Blocking (finishing one book before starting another) doesn't create these juxtapositions.

**The Retrieval Practice Hypothesis**: Distributed practice forces repeated retrieval from long-term memory, which strengthens the memory trace. Reading Book A section, then Book B section, then returning to Book A, requires the reader to *recall* what Book A said -- an act of retrieval that strengthens retention. Sequential reading of Book A never requires this recall.

### 5.4 Conditions and Caveats

Interleaving is not universally better:

- **High similarity required**: The benefit is greatest when the interleaved items are related but distinguishable. Random interleaving of unrelated topics does not help (and may hurt).
- **Desirable difficulty**: Interleaving feels harder than blocking. Learners often *prefer* blocked study and rate it as more effective, even when interleaving produces better outcomes. This is a UX challenge: the system must help users persist with a strategy that feels harder.
- **Spacing confound**: Interleaving across sessions also introduces spacing between encounters with the same material, which is independently beneficial. The benefits of interleaving and spacing are additive.

### 5.5 Application to Multi-Book Reading

No reading app currently supports deliberate interleaving of book sections. This is Petrarca's most distinctive design opportunity. The implementation in book-reader-design.md (topic shelves interleaving sections from multiple books) has strong pedagogical support:

1. **Topic-matched interleaving**: Only interleave sections that address overlapping topics. Random interleaving (switching from medieval history to quantum physics) provides no discriminative contrast benefit.
2. **Connection-bridged transitions**: When transitioning from Book A section to Book B section, show a brief bridge: "You just read Runciman on [X]. Tuchman addresses the same topic from a different angle." This makes the interleaving deliberate rather than disorienting.
3. **Explicit comparison prompts**: After reading related sections from two books, prompt the reader: "How does Runciman's evidence for economic decline compare to Tuchman's evidence for economic prosperity?" This leverages the discriminative contrast effect.
4. **Opt-in difficulty**: Since interleaving feels harder, let the reader choose: "Continue with Runciman (easier)" vs. "Switch to Tuchman's perspective (deeper learning)." Transparency about the learning benefit helps overcome resistance.

### 5.6 The "Interleaving Scheduler"

A novel feature for Petrarca: an algorithm that determines when to switch between books based on:

- **Topic overlap**: Switch when the next section of Book B addresses a topic just encountered in Book A.
- **Argument tension**: Switch when Book B contradicts or extends a claim from the section just read in Book A.
- **Reader signals**: If the reader marked a claim as "surprising," schedule the corresponding claim from Book B sooner.
- **Spacing interval**: Don't return to the same book too quickly (minimum 1-2 other sections in between) to get the retrieval practice benefit.
- **Reader override**: Always allow the reader to continue the current book sequentially if they prefer.

This scheduler would be transparent ("I'm suggesting Tuchman next because she discusses the same trade routes Runciman just mentioned") and configurable (the reader can adjust the interleaving aggressiveness).

---

## 6. Innovative Mobile UX Patterns

### 6.1 Gesture Vocabularies for Reading

**Facebook Paper (2014)**: Pioneered card-based gestural reading on mobile. Swiping up on a story "magically grows it into a full-screen summary card," and swiping up again "unfolds the story into a mobile web view." The double up-swipe is described as "oddly satisfying, like picking up a newspaper, then bringing it closer to your face." Paper proved that gesture-driven interfaces could replace traditional navigation, but its "gestural hell" (every action required learning a new gesture) also demonstrated the risk of overloading the gesture vocabulary.

Source: [Building Paper (Meta Engineering)](https://engineering.fb.com/2014/03/07/ios/building-paper/), [Facebook Paper's gestural hell (Scott Hurff)](https://www.scotthurff.com/posts/facebook-paper-gestures/)

**Material Design gesture principles**: Standard gesture vocabulary establishes swipe for navigation, pinch for zoom, tap for selection, long-press for options. Deviating from these conventions creates discoverability problems. The key constraint: "what makes some gestures easy and others confusing" comes down to physical metaphor coherence -- gestures must map to physical actions that make intuitive sense.

**Key takeaway**: Petrarca should use a *small* gesture vocabulary that maps to coherent physical metaphors:

| Gesture | Metaphor | Action |
|---------|----------|--------|
| Vertical scroll | Reading a page | Navigate within a section |
| Horizontal swipe | Turning a page | Move between sections |
| Pinch out/spread | Zooming in | Reveal more detail (deeper depth zone) |
| Pinch in | Zooming out | Show overview (shallower depth zone) |
| Long press | Highlighting with a pen | Create a highlight |
| Pull down | Pulling back to see the table | Show section map / argument overview |

The pinch-to-zoom metaphor for depth zones is the most novel gesture here: pinching in on the full text zooms out to the claims view, pinching further shows the briefing, and pinching all the way out shows the topic shelf. Spreading does the reverse. This makes Petrarca's progressive depth model feel like a spatial zoom rather than a mode switch.

### 6.2 Andy Matuschak's Stacked Notes

Matuschak's evergreen notes site (notes.andymatuschak.org) pioneered the "sliding panes" pattern: clicking a link opens the new note to the right while keeping the previous note visible. The result is a horizontal stack of notes showing the reader's exploration path.

This pattern has been widely adopted (Obsidian "Andy mode," Logseq, etc.) because it solves a fundamental problem of hypertext: click a link, lose your context. With stacked notes, context is preserved spatially.

**Application to Petrarca**: When following a cross-book connection, the connected passage should slide in from the right while the current passage remains visible on the left. The reader sees both passages simultaneously, maintaining context. On a phone, this could use a half-screen overlay: the connected passage covers the bottom half while the source passage remains visible in the top half.

Source: [Andy Matuschak on his notes browsing design](https://x.com/andy_matuschak/status/1568032773025431552)

### 6.3 Spatial Reading Metaphors

**The Bookshelf Metaphor**: Physical bookshelves communicate several things at once: what you own, what you've read (worn spines), where you are in a book (bookmark sticking out), and topical grouping (books clustered by subject). Digital reading apps rarely capture this richness.

**The Map Metaphor**: Representing a reading domain as a map where books are territories, sections are locations, and the reader's path is a route. This supports spatial memory: "I remember that claim was in the southeast corner of Runciman's territory." Research on spatial memory shows that location-based cues aid recall even in digital interfaces.

**The Timeline Metaphor**: A horizontal timeline showing reading sessions, with sections read stacked vertically. This gives a temporal view of the reading journey: when the reader engaged with which topics, how long sessions lasted, and where gaps occurred. This supports context restoration by showing "your reading journey so far."

### 6.4 The Depth Dial

A novel interaction pattern for Petrarca's multi-level content:

Instead of discrete tabs for Briefing / Claims / Sections / Full Text, implement a continuous "depth dial" -- a vertical slider on the edge of the screen that the reader can drag to smoothly transition between depth levels. At the top position, they see the briefing. As they drag down, claims fade in. Further down, full section text appears. This creates a feeling of *diving deeper* into the material.

The depth dial could also be controlled by scroll velocity: slow, deliberate scrolling shows full text; fast flicking collapses to claims and section headers. This maps to natural reading behavior -- when you skim a physical book, you see only headings and first sentences; when you slow down, you read every word.

### 6.5 The Connection Radar

A mobile-optimized visualization for cross-book connections:

A small radar-like widget in the corner of the reader that shows nearby connections from other books. As the reader scrolls, connections pulse when relevant passages come into view. Tapping the radar expands it to show a brief list of connections with inline previews. This is less intrusive than inline callout cards but provides persistent awareness of the connection landscape.

The radar metaphor communicates: "there are things nearby you should be aware of" -- appropriate for cross-book connections that are relevant but not required for the current reading.

---

## 7. Synthesis: Design Recommendations for Petrarca

Based on this research, here are the most impactful and differentiating features Petrarca could implement, ordered by novelty and expected value:

### 7.1 High Impact, Novel (No Existing Tool Does This)

**1. Interleaved Reading Scheduler**: An algorithm that interleaves sections from different books based on topic overlap, argument tension, and reader signals. Supported by strong pedagogical research (effect sizes 0.65+). Include connection-bridged transitions and explicit comparison prompts. Make the interleaving rationale transparent and overridable.

**2. "The Argument So Far" Tracker**: After each chapter, generate a 2-3 sentence summary of how the book's argument has *developed* (not what happened, but how the reasoning progressed). Show cross-book argument structures side by side when two books address the same topic. No existing reading app tracks argument development.

**3. Graduated Context Restoration**: Scale the re-engagement experience based on absence duration. Under 1 day: just scroll position. 1-3 days: last highlight + next section. 3-14 days: personal thread recap. 14+ days: full "Previously on..." narrative. No reading app adapts context restoration to absence length.

**4. Cognitive State Bookmarks**: Instead of saving a page position, save a snapshot of the reader's engagement state: which claims they found surprising, what questions they had, what connections they noticed. Use this state for context restoration and for personalizing future section briefings.

### 7.2 High Impact, Feasible (Builds on Existing Patterns)

**5. Pinch-to-Zoom Depth Navigation**: Use pinch/spread gestures to navigate between depth levels (briefing <-> claims <-> full text). This reframes Petrarca's existing depth model as spatial zoom rather than tab switching, leveraging the semantic zoom pattern.

**6. Inline Transclusion for Cross-Book Connections**: When showing a cross-book connection, display the connected claim's text inline (Roam-style transclusion) rather than requiring navigation. The reader should be able to compare two claims from different books without leaving the current section.

**7. Stacked Pane Navigation for Connections**: Following a cross-book connection opens the target passage in a half-screen overlay (Andy Matuschak stacked notes pattern adapted for mobile), maintaining the source passage as context.

**8. Reading Topology Visualization**: A visual map of all sections in a book/topic showing reading depth as color intensity. Sections read at full depth are vivid; briefings-only are faint; unread are hollow. This gives an at-a-glance sense of where the reader has gone deep vs. skimmed.

### 7.3 Worth Exploring (Speculative, Potentially Differentiating)

**9. Argument Thread Notifications**: When the reader encounters a claim that contradicts or extends a previously-engaged claim from another book, surface an interstitial prompt: "Tuchman disagrees with what you highlighted from Runciman. Compare?" This makes cross-book reading actively comparative rather than passively sequential.

**10. Connection Density as Importance Signal**: Track how many cross-book connections converge on a passage. High-connection-density passages are likely conceptually important. Use this to surface "key passages you haven't read yet" recommendations.

**11. The Depth Dial**: Replace discrete depth tabs with a continuous slider that smoothly transitions between depth levels. Or tie depth to scroll velocity: fast scroll shows headers/claims, slow scroll reveals full text.

**12. The Connection Radar**: A persistent small widget showing nearby cross-book connections that pulse as the reader scrolls past relevant passages.

**13. "Why Am I Reading This Next?" Explanations**: For every section the interleaving scheduler recommends, show a brief explanation: "This section addresses trade routes, which Runciman discussed in the section you read yesterday. Comparing perspectives strengthens retention (interleaving effect)."

### 7.4 What Not to Do

- **Don't build a general graph view**: Obsidian's experience shows that automatically generated graphs are more aesthetic than useful. Focus on *inline* connection surfacing during reading rather than a separate graph workspace.
- **Don't require manual linking**: MarginNote and LiquidText require significant manual effort to build connection maps. Petrarca's pipeline should discover connections automatically and let the reader confirm/dismiss them.
- **Don't gamify reading progress**: Kobo's badges and streaks increase reading time but may undermine intrinsic motivation for deep reading. Focus on intellectual satisfaction (connections discovered, arguments understood) rather than quantitative metrics (pages read, streaks maintained).
- **Don't overload the gesture vocabulary**: Facebook Paper's failure mode was requiring too many gestures. Stick to 5-6 gestures maximum, all mapping to coherent physical metaphors.
- **Don't separate review from reading**: The mnemonic medium research shows that embedding review moments in the reading flow is more effective than a separate review session. Petrarca's claim signals and concepts review should feel like extensions of reading, not a different mode.

---

## Sources

### Cross-Text Connection Visualization
- [LiquidText CHI 2011 Paper](https://faculty.cc.gatech.edu/~keith/pubs/chi2011-liquidtext.pdf)
- [LiquidText Website](https://www.liquidtext.net/)
- [MarginNote Features](https://www.marginnote.com/features)
- [Passages: Interacting with Text Across Documents (CHI 2022)](https://dl.acm.org/doi/fullHtml/10.1145/3491102.3502052)
- [Roam Research Block References](https://www.zsolt.blog/2021/05/Addicted-to-block-references.html)
- [Obsidian Canvas Links Plugin](https://www.obsidianstats.com/plugins/canvas-links)
- [InfraNodus Obsidian Plugin](https://infranodus.com/obsidian-plugin)
- [Heptabase](https://heptabase.com/)
- [Scrintal: Visual Note-Taking](https://scrintal.com/)
- [Hypothesis vs Perusall Comparison](https://web.hypothes.is/hypothesis-perusall-compared/)

### Context Restoration
- [Dedicated Workspaces and Resumption Times (ResearchGate)](https://www.researchgate.net/publication/301305771_Dedicated_workspaces_Faster_resumption_times_and_reduced_cognitive_load_in_sequential_multitasking)
- [Recognition Over Recall (UI Patterns)](https://ui-patterns.com/patterns/Recognition-over-recall)
- [Kobo Reading Life](https://www.kobo.com/readinglife)
- [Readwise Reader Ghostreader](https://docs.readwise.io/reader/guides/ghostreader/overview)

### Argument Tracking
- [Kialo Edu Research](https://www.kialo-edu.com/research)
- [Argument Visualization Survey (Frontiers in Education, 2025)](https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1672105/full)
- [Argument Mining Survey (Computational Linguistics, MIT Press)](https://direct.mit.edu/coli/article/45/4/765/93362/Argument-Mining-A-Survey)
- [Digital Tools for Written Argumentation (Springer)](https://link.springer.com/chapter/10.1007/978-3-031-36033-6_6)

### Progressive Disclosure
- [Shneiderman's Information-Seeking Mantra](https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf)
- [Semantic Zoom (InfoVis Wiki)](https://infovis-wiki.net/wiki/Semantic_Zoom)
- [Overview+Detail, Zooming, and Focus+Context (Cockburn et al.)](https://dl.acm.org/doi/10.1145/1456650.1456652)
- [Mnemonic Medium (Andy Matuschak)](https://notes.andymatuschak.org/Mnemonic_medium)
- [Orbit Platform](https://withorbit.com/)
- [SuperMemo Incremental Reading](https://help.supermemo.org/wiki/Incremental_reading)
- [Polar Bookshelf Incremental Reading](https://getpolarized.io/docs/incremental-reading.html)
- [Readwise Spaced Repetition Design](https://blog.readwise.io/hack-your-brain-with-spaced-repetition-and-active-recall/)

### Interleaved Reading
- [Interleaved Practice in Physics (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8589969/)
- [Systematic Review of Interleaving (Firth, 2021)](https://bera-journals.onlinelibrary.wiley.com/doi/10.1002/rev3.3266)
- [Discriminative Contrast Hypothesis (Kang & Pashler, 2012)](https://link.springer.com/article/10.3758/s13421-012-0272-7)
- [Spacing vs. Interleaving Effects (Educational Psychology Review)](https://link.springer.com/article/10.1007/s10648-021-09613-w)

### Mobile UX Patterns
- [Building Paper (Meta Engineering)](https://engineering.fb.com/2014/03/07/ios/building-paper/)
- [Facebook Paper Gestural Hell (Scott Hurff)](https://www.scotthurff.com/posts/facebook-paper-gestures/)
- [Material Design 3 Gestures](https://m3.material.io/foundations/interaction/gestures)
- [Andy Matuschak Stacked Notes Design](https://x.com/andy_matuschak/status/1568032773025431552)
- [Progressive Disclosure (NN/g)](https://www.nngroup.com/articles/progressive-disclosure/)
