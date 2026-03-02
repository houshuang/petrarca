# Incremental Reading: Comprehensive Research Survey

*Research compiled March 2026 for the Petrarca project*

---

## Table of Contents

1. [SuperMemo's Incremental Reading: The Original Concept](#1-supermemos-incremental-reading-the-original-concept)
2. [Theoretical Foundations](#2-theoretical-foundations)
3. [Criticisms and Limitations](#3-criticisms-and-limitations)
4. [Modern Implementations and Tools](#4-modern-implementations-and-tools)
5. [Academic Research](#5-academic-research)
6. [The Extract-Transform-Review Pipeline](#6-the-extract-transform-review-pipeline)
7. [What is Different About the Petrarca Vision](#7-what-is-different-about-the-petrarca-vision)
8. [Key Takeaways for Petrarca](#8-key-takeaways-for-petrarca)

---

## 1. SuperMemo's Incremental Reading: The Original Concept

### 1.1 History and Origin

Incremental reading (IR) was conceived by Piotr Wozniak and first implemented in **SuperMemo 9.5 (1999)**, with the formalized version arriving in **SuperMemo 10 (March 27, 2000)**. Wozniak traces the conceptual roots to childhood encyclopedia reading habits (1972) and university cramming techniques (1983), with theoretical groundwork laid in his PhD dissertation (1995).

The key insight was simple but radical: **reading should be scheduled the same way flashcard reviews are scheduled**. Instead of finishing an article in one sitting, you read a portion, then the software schedules you to return days or weeks later. This transforms reading from a single event into a process distributed across time.

Sources: [History of incremental reading](https://supermemo.guru/wiki/History_of_incremental_reading), [Incremental reading - supermemo.guru](https://supermemo.guru/wiki/Incremental_reading)

### 1.2 The Full Pipeline: Import, Extract, Cloze, Schedule

SuperMemo's incremental reading operates as a **knowledge funnel** with five stages:

**Stage 1 -- Import.** Articles are imported from electronic sources (web pages, PDFs, Wikipedia, YouTube transcripts). When importing from the web, references and metadata are added automatically. The most convenient method is direct browser import -- SuperMemo can import all articles from open tabs at once.

**Stage 2 -- Incremental Reading (Spaced Reading).** You read articles in small portions across multiple sessions. After reading part of an article, you move on to a portion of another article. SuperMemo automatically schedules when you will return to each article. For example:
- March 1st: Read chapter 1 (40%), create extracts
- March 2nd: Review those extracts
- April 5th: Review extracts again
- April 12th: Continue reading from 40% mark

Between these sessions, you are working on hundreds or thousands of other articles.

**Stage 3 -- Extract.** While reading, you highlight and extract the most important fragments (Alt+X in SuperMemo). Each extract becomes an independent element in the system, subject to its own scheduling. Extracts are like progressive highlighting -- you are distilling the article down to its essence.

**Stage 4 -- Cloze Deletion.** Extracts are converted into active recall items using cloze deletion (Alt+Z). A sentence like "The mitochondria is the powerhouse of the cell" becomes "The [...] is the powerhouse of the cell." This converts passive reading into active testing.

**Stage 5 -- Spaced Review.** All generated items enter the spaced repetition system with increasing intervals. The system claims ~95% long-term retention when the schedule is maintained.

The process is recursive: each extract can itself be further extracted and refined, creating a cascade from raw article to granular, testable knowledge.

Sources: [SuperMemo: Incremental reading](https://super-memory.com/help/read.htm), [Master How To Learn: SuperMemo's IR Explained](https://www.masterhowtolearn.com/2019-08-06-supermemos-incremental-reading-explained/), [Incremental learning - SuperMemo Help](https://help.supermemo.org/wiki/Incremental_learning)

### 1.3 Topics vs. Items: Two Scheduling Systems

SuperMemo maintains a critical distinction between **topics** (reading material) and **items** (flashcards), each with different scheduling mechanics:

**Topics** (articles, extracts, images, videos):
- Serve passive engagement -- reading, viewing, listening
- Use a **simple, user-controllable scheduling system**
- Each topic has an **A-Factor** (interval multiplier) that the user can manually adjust via Alt+P
- If A-Factor = 2, review intervals double each time (e.g., 1 day, 2 days, 4 days, 8 days...)
- If A-Factor = 1.5, intervals grow more slowly
- A-Factor = 1.01 is the lowest, corresponding to highest priority (near-daily review)
- Users can reschedule topics freely (Ctrl+J) or force repetitions (Shift+Ctrl+R)

**Items** (flashcards, cloze deletions, Q&A pairs):
- Demand active recall
- Use the **complex SuperMemo Algorithm** (SM-18 as of latest versions)
- A-Factors are automatically computed based on item difficulty
- Users **cannot** manually modify item A-Factors
- The algorithm optimizes for ~95% recall at review time
- Intervals are determined by the mathematical relationship between question complexity and optimal spacing

This dual system means reading material flows through a gentler, more flexible schedule, while knowledge items are rigorously optimized by the algorithm. The key insight is that **reading benefits from spacing but does not require the same precision as recall testing**.

Sources: [SuperMemo: Incremental learning](https://super-memory.com/help/il.htm), [Incremental reading and item intervals](https://supermemopedia.com/wiki/Incremental_reading_and_item_intervals)

### 1.4 The Priority Queue

Introduced in **SuperMemo 13 (2006)**, the priority queue was a major innovation for managing information overload:

- Every element (topic or item) receives a **priority from 0% to 100%**, where **0% = highest priority** (counterintuitive but deliberate)
- Priorities are set automatically based on text length, processing behavior, and other heuristics, but can be manually adjusted at any time

**How the queue operates:**
1. **Auto-postpone** runs before each learning day begins, pushing low-priority overdue material to future dates
2. Auto-postpone always preserves top-priority elements in the queue
3. **Auto-sort** then orders the remaining material from high to low priority
4. You begin your day with all of today's scheduled material plus top-priority overflow from previous days
5. Material you don't reach gets auto-postponed again tomorrow

**Priority bias:** Wozniak identified a cognitive bias he calls "priority bias" -- the tendency to always think newly found articles are extremely important. The priority queue system counteracts this by forcing relative ranking: adding a new high-priority item necessarily pushes something else down.

The priority queue transforms IR from "read everything eventually" to "always work on the most important thing, and let lower-priority material gracefully degrade." Even material that gets repeatedly postponed still benefits from the spacing effect.

Sources: [Priority queue - SuperMemo Help](https://help.supermemo.org/wiki/Priority), [Auto-postpone - supermemo.guru](https://supermemo.guru/wiki/Auto-postpone)

### 1.5 Knowledge Darwinism

One of Wozniak's more interesting theoretical concepts is **knowledge darwinism**: the competition between memories for survival in long-term memory.

The core idea: when you create multiple questions addressing the same concept from different angles, the strongest formulation -- the one most connected to your existing knowledge, emotional associations, and personal context -- will "win" and establish itself most firmly. Rather than being wasteful, this redundancy is a feature:

- **Coherence enhancement:** The strongest formulation takes root first, then helps consolidate related memories
- **Stability building:** Less stable elements get reinforced more often, creating stronger overall architecture
- **Comprehension development:** Multiple angles on the same concept promote generalization and abstract understanding

In incremental reading, knowledge darwinism manifests naturally: you extract the same concept from multiple articles, create multiple overlapping cloze deletions, and let the best-fitting representations survive while strengthening the entire semantic network.

Source: [Knowledge darwinism - supermemo.guru](https://supermemo.guru/wiki/Knowledge_darwinism)

### 1.6 Neural Creativity

Wozniak's concept of **neural creativity** (2015) extends IR into creative production. The idea is that reviewing a large collection of interleaved topics naturally generates novel connections between ideas. When closely related concepts show up in sequence during a review session -- an article about architecture followed by one about biology -- the juxtaposition can spark creative insights.

IR is thus framed not just as a reading optimization but as a **creativity engine**: the more diverse your reading and the more you interleave topics, the more unexpected connections your brain will make.

Source: [Neural creativity - SuperMemo Help](https://help.supermemo.org/wiki/Neural_creativity)

### 1.7 Key Innovations vs. "Just Reading + Anki"

The fundamental difference between SuperMemo's IR and a workflow of "read articles, then add flashcards to Anki" can be summarized as:

| Dimension | Reading + Anki | SuperMemo IR |
|---|---|---|
| **Reading scheduling** | Manual / ad hoc | Algorithmic, spaced |
| **Reading prioritization** | Manual | Priority queue with auto-postpone |
| **Source-to-card pipeline** | Separate tools, manual transfer | Unified, in-context extraction |
| **Reading progress tracking** | Manual bookmarks | Automatic read points, pagemarks |
| **Interleaving** | Accidental | Systematic, by design |
| **Processing depth** | Binary (read/not read) | Gradual (article -> extract -> cloze) |
| **Overload management** | Guilt-driven | Algorithmic (auto-postpone) |

As one comparison puts it: "SuperMemo/Anki = spacing your remembering; Incremental reading = spacing your reading." The key insight is that **reading itself benefits from spacing**, not just the recall of facts derived from reading.

Source: [Master How To Learn: Spacing Your Reading](https://masterhowtolearn.wordpress.com/2019/08/08/supermemo-anki-spacing-your-remembering-incremental-reading-spacing-your-reading/)


---

## 2. Theoretical Foundations

### 2.1 The Spacing Effect

The most fundamental cognitive principle underlying IR is the **spacing effect**: distributing learning over time produces superior long-term retention compared to massed practice (cramming). This is one of the most robust findings in cognitive psychology, demonstrated in hundreds of studies across diverse domains.

Key findings relevant to IR:
- Spacing benefits both factual recall and conceptual understanding
- Longer inter-study intervals (within limits) paradoxically produce better long-term retention, even though they feel harder in the moment
- The spacing effect applies not just to flashcard review but to **reading comprehension** -- spacing out reading of the same material across sessions improves understanding
- Incorporating tests into spaced practice amplifies the benefits

IR directly leverages this by scheduling reading material at expanding intervals, ensuring that you return to articles and extracts at progressively longer gaps.

Sources: [Evidence of the Spacing Effect - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8759977/), [Kang (2016) Spaced Repetition Promotes Efficient and Effective Learning](https://journals.sagepub.com/doi/abs/10.1177/2372732215624708)

### 2.2 The Testing Effect (Retrieval Practice)

The testing effect (or retrieval practice effect) demonstrates that actively retrieving information from memory is more effective for long-term learning than passively re-reading or re-studying material. Testing is not just an assessment tool -- it is a **learning event**.

Dunlosky et al. (2013) rated **practice testing** and **distributed practice** as the only two learning techniques with "high utility" in their comprehensive review of 10 common learning strategies. Both are central to IR.

IR leverages this through the cloze deletion stage: extracting information from text and converting it to active recall questions transforms passive reading into testing. The progression from reading to extracting to cloze creation represents increasing levels of active engagement.

Sources: [Dunlosky et al. (2013) - Improving Students' Learning With Effective Learning Techniques](https://journals.sagepub.com/doi/abs/10.1177/1529100612453266), [Spaced repetition and active recall improves academic performance](https://www.sciencedirect.com/science/article/abs/pii/S187712972500231X)

### 2.3 Interleaving

Interleaving -- mixing different topics during study rather than blocking by subject -- generally improves long-term learning and transfer, especially for inductive category learning. The typical finding is that interleaved practice feels harder but produces better results.

IR is inherently interleaving: in a single session, you might read a paragraph about neuroscience, review an extract about economics, answer a cloze about history, and import an article about programming. This constant switching is not a bug but a feature -- it forces the brain to engage discrimination processes ("What kind of problem is this? What knowledge applies here?") that strengthen learning.

Research confirms that interleaving and spacing effects, while often co-occurring, have **distinct theoretical bases**. Interleaving boosts category learning and transfer; spacing boosts memory consolidation. IR benefits from both.

Source: [Spacing and Interleaving Effects Require Distinct Theoretical Bases - Springer](https://link.springer.com/article/10.1007/s10648-021-09613-w)

### 2.4 Elaborative Interrogation

Elaborative interrogation involves generating explanations for **why** stated facts are true. Research shows this strategy improves reading comprehension and text memory, particularly when combined with prior background knowledge. Dunlosky et al. rated it as "moderate utility" -- effective but under-studied in real educational contexts.

The connection to IR: creating cloze deletions and extracting key passages forces a form of elaborative processing. You must decide what is important, why it matters, and how to formulate it as a question -- all of which require understanding the material, not just reading it.

However, elaborative interrogation works best when learners have background knowledge to draw on. For completely novel domains, the technique may be less effective -- a limitation that also applies to IR.

Sources: [Effective Use of Elaborative Interrogation - Reading Psychology](https://www.tandfonline.com/doi/full/10.1080/02702711.2025.2482627), [UW-La Crosse CATL Guide](https://www.uwlax.edu/catl/guides/teaching-improvement-guide/how-can-i-improve/elaborative-interrogation/)

### 2.5 Desirable Difficulties

Robert Bjork's concept of **desirable difficulties** (1994) provides the overarching framework: conditions that make learning feel harder in the short term but produce better long-term retention. The four key desirable difficulties are:

1. **Spacing** (vs. massing)
2. **Interleaving** (vs. blocking)
3. **Retrieval practice** (vs. re-reading)
4. **Varying practice conditions** (vs. constant conditions)

IR systematically introduces all four. Reading is spaced. Topics are interleaved. Extracts become retrieval practice items. And the constant context-switching between different articles provides varying conditions.

The critical caveat: a difficulty is only "desirable" if the learner can successfully engage with it. If material is too far beyond current understanding, the difficulty becomes undesirable. This connects to the criticism that IR may not work well for complex subjects requiring deep, sustained focus.

Sources: [Bjork & Bjork (2011) Creating Desirable Difficulties](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf), [Desirable Difficulties in Theory and Practice - ResearchGate](https://www.researchgate.net/publication/347931447_Desirable_Difficulties_in_Theory_and_Practice)

### 2.6 Knowledge Chunking and Expert Memory

Michael Nielsen draws on Herbert Simon and Adriaan de Groot's chess research to argue that expertise fundamentally depends on having large numbers of **chunks** -- complex conceptual units that experts recognize instantly. A chess grandmaster doesn't evaluate each piece individually; they recognize board patterns as single units.

Nielsen argues that spaced repetition and incremental reading build these chunks: "Having more chunks memorized in some domain is somewhat like an effective boost to a person's IQ in that domain." This reframes memory from rote memorization to the **foundation of fluid intelligence** within a domain.

Source: [Michael Nielsen - Augmenting Long-term Memory](https://augmentingcognition.com/ltm.html)

### 2.7 Knowledge Valuation Network

Wozniak's concept of the **knowledge valuation network** describes how the brain assigns value to information based on its connections to goals, emotions, and existing knowledge. The value of any piece of knowledge is determined by:

- Its proximity to personal goals in the semantic network
- The strength and number of connections to other valued knowledge
- Emotional associations

This provides a theoretical basis for why IR works: by processing many articles across time and creating connections between them, you are building a richer valuation network. Material that connects to more of what you already know and care about will naturally receive higher priority.

Source: [Knowledge valuation network - supermemo.guru](https://supermemo.guru/wiki/Knowledge_valuation_network)


---

## 3. Criticisms and Limitations

### 3.1 Steep Learning Curve

The most frequently cited criticism. Learning IR requires mastering:
- A complex software workflow (importing, extracting, cloze creation, priority management)
- New reading habits (stopping mid-article, trusting the system to bring you back)
- Priority calibration (learning what deserves high vs. low priority)
- Cloze crafting (writing good cloze deletions is a skill that takes months to develop)

Most beginners report months of frustration before achieving proficiency. The software itself (SuperMemo) is Windows-only with a dated interface, which compounds the difficulty.

Sources: [Disadvantages of incremental reading - supermemo.guru](https://supermemo.guru/wiki/Disadvantages_of_incremental_reading), [SuperMemo.wiki: Incremental reading](https://www.supermemo.wiki/en/learning/incremental-reading)

### 3.2 Fragmentation of Understanding

A fundamental critique: by reading articles in small portions with days or weeks between sessions, you may lose the **thread of an argument**. Complex subjects that require holding many ideas in working memory simultaneously -- mathematical proofs, philosophical arguments, intricate code architectures -- may be poorly served by IR.

As one critic puts it: "Students spend but a few seconds on a passage related to one subject, and then jump to another, completely unrelated subject, making it difficult, if not impossible, to engage in deeper thoughts and thus to discover deeper truths beyond superficial remembering of passages."

Specific material types identified as poor fits for IR:
- Research papers with heavy methodology and novel notation
- Mathematical proofs requiring sustained working memory
- Code that must be understood as a whole system
- Narrative texts where flow and momentum matter
- Material requiring extensive prerequisite context that hasn't been built yet

Source: [Incremental reading may hamper learning complex subjects - SuperMemopedia](https://supermemopedia.com/wiki/Incremental_reading_may_hamper_learning_complex_subjects)

### 3.3 The "Monster Cloze" Problem

Beginners often create cloze deletions that are too complex, ambiguous, or context-dependent. A cloze like "The key finding was [...]" could have dozens of valid answers. Poor cloze quality creates a negative feedback loop: bad cards lead to frustrating reviews, which lead to avoidance of the system.

Even experienced users must constantly edit and refine their cloze deletions, multiplying the time cost of processing material. This is the primary reason newcomers report negative experiences.

Source: [ABC of incremental reading - SuperMemopedia](https://supermemopedia.com/wiki/ABC_of_incremental_reading_for_any_user_of_spaced_repetition)

### 3.4 Time Inefficiency in Early Stages

For short or simple materials, the overhead of importing, extracting, and creating cloze deletions may exceed the benefit compared to just reading and taking notes. Traditional methods may outperform IR for the first 1-2 months of use. The payoff only materializes at scale, over months and years, when managing thousands of articles simultaneously.

### 3.5 Platform Lock-in

SuperMemo is Windows-only desktop software (though web and mobile versions exist, they lack IR features). There is no practical way to do IR on mobile devices, no cross-platform sync in the desktop version, and the proprietary database format creates lock-in concerns.

Source: [Full Mobile SuperMemo - SuperMemopedia](https://supermemopedia.com/wiki/Full_Mobile_SuperMemo)

### 3.6 The "Overrated" Argument

Some users argue that IR is overrated because:
- It optimizes for **breadth** at the expense of **depth**
- The creativity benefits Wozniak claims are difficult to verify empirically
- For many practical learning goals (passing exams, learning a skill), simpler approaches work fine
- The time spent managing the system could be spent actually reading and thinking
- It can create an illusion of productivity (processing articles feels like learning even when comprehension is shallow)

Source: [Incremental reading is overrated - SuperMemopedia](https://supermemopedia.com/wiki/Incremental_reading_is_overrated)

### 3.7 Requires Digital Source Material

IR fundamentally requires electronic text. Paper books, handwritten notes, and other analog sources must be digitized before they can enter the system, adding friction. While OCR and scanning exist, they add significant overhead.


---

## 4. Modern Implementations and Tools

### 4.1 SuperMemo (Windows Desktop)

The original and most complete implementation. Current version is SuperMemo 19 (released ~2023). Features include:
- Full IR pipeline (import, extract, cloze, schedule)
- Priority queue with auto-postpone
- SM-18 algorithm for items
- A-Factor scheduling for topics
- Neural creativity mode
- Incremental video, audio, image learning
- Web browser integration (Edge/Chrome)

**Limitations:** Windows-only, dated UI, steep learning curve, no mobile IR, proprietary format.

Source: [SuperMemo - Wikipedia](https://en.wikipedia.org/wiki/SuperMemo)

### 4.2 Polar Bookshelf

An open-source personal knowledge repository supporting PDF, EPUB, and web content with IR-inspired features.

**Key feature -- Pagemarks:** A concept inspired by IR that enables non-linear reading with suspend/resume. You can create multiple pagemarks per document, supporting jumping around in technical/research material.

**Additional features:**
- Annotation and highlighting
- Auto-flashcard creation from highlights using GPT-3
- Anki integration for spaced repetition export
- Built with Electron and PDF.js
- Cross-platform (Linux, macOS, Windows)

**Status:** The original project (getpolarized.io) appears to have slowed in development. Multiple forks exist on GitHub.

Source: [GitHub: polar-bookshelf](https://github.com/SilverHoodCorp/polar-bookshelf)

### 4.3 RemNote

A note-taking tool with built-in spaced repetition, positioned as a more modern alternative to SuperMemo.

**Native IR features:** Limited. RemNote does not have built-in incremental reading as a native feature.

**Plugin: "Incremental Everything"** by bjsi (James Brind):
- Interleave flashcard reviews with notes, paragraphs from books, websites, video snippets
- Tag PDFs, websites, and highlights with an "Incremental" tag
- Supports incremental reading, writing, video, tasks, and exercises
- SuperMemo-inspired priority and scheduling

RemNote's strength is the tight integration between notes and flashcards -- any text can become a flashcard with `::` syntax. But the IR workflow requires the third-party plugin.

Sources: [RemNote Incremental Everything - GitHub](https://github.com/bjsi/incremental-everything), [RemNote vs Anki, SuperMemo](https://help.remnote.com/en/articles/6025618-remnote-vs-anki-supermemo-and-other-spaced-repetition-tools)

### 4.4 Readwise / Readwise Reader

A two-part system: **Readwise** resurfaces highlights via spaced repetition; **Reader** is a read-it-later app with AI features.

**Readwise (Highlight Review):**
- Imports highlights from Kindle, Apple Books, Instapaper, Pocket, web, PDF, etc.
- Daily Review resurfaces highlights using lightweight spaced repetition
- Supports converting highlights into Q&A and cloze deletion for active recall ("Mastery" feature)
- Themed Reviews use AI to pull together highlights by topic
- Users can weight probability of specific books/articles being resurfaced

**Readwise Reader:**
- Full read-it-later app with RSS feed support
- **Ghostreader**: AI assistant for summarization, definition lookup, question-answering
- Auto-summarization of saved documents (with OpenAI API key, also for feed items)
- Highlighting and annotation
- Export to Obsidian, Notion, Logseq, Roam, etc.
- Latest models: GPT-4.1-mini included in subscription

**IR comparison:** Readwise implements a lightweight version of the extract-to-review pipeline but lacks the full scheduling and priority queue mechanics of SuperMemo. It excels at the "resurface highlights" step but doesn't manage the reading schedule itself.

Sources: [Readwise](https://readwise.io/), [Readwise Reader docs](https://docs.readwise.io/reader/docs), [Ghostreader](https://docs.readwise.io/reader/docs/faqs/ghostreader), [Adding Intention to Spaced Repetition - Readwise Blog](https://blog.readwise.io/adding-intention-to-spaced-repetition/)

### 4.5 Orbit (Andy Matuschak)

An experimental platform exploring the **mnemonic medium** -- embedding spaced repetition prompts directly into narrative prose.

**Core concept:** Instead of readers creating their own flashcards after reading, **authors embed expert-crafted prompts within the text itself**. Readers answer questions as they read, and Orbit schedules reviews across sessions.

**Key innovations:**
- Tight coupling between text and questions (contextual anchoring)
- Author-supplied prompts lower the barrier for readers
- Naturally supports "incremental reading" -- review sessions bring readers back to material
- First implemented in [Quantum Country](https://quantum.country), a textbook on quantum computing

**Philosophical difference from IR:** The mnemonic medium is author-driven (the writer designs the learning experience) rather than reader-driven (the reader extracts what matters). This makes it more accessible but less personalized.

**Status:** Experimental, research-oriented. Available at [withorbit.com](https://withorbit.com/).

Sources: [Mnemonic medium - Andy Matuschak](https://notes.andymatuschak.org/Mnemonic_medium), [Orbit GitHub](https://github.com/andymatuschak/orbit)

### 4.6 Mochi

A Markdown-based note-taking and flashcard app with spaced repetition (modified SM-2 algorithm).

**IR-adjacent features:**
- Notes in Markdown that can be converted to flashcards
- Users have adapted it for IR by creating reference notes and progressively extracting key concepts into linked question-and-answer cards
- Simple, clean interface compared to SuperMemo

**Limitations:** No dedicated IR pipeline, no reading scheduling, no priority queue. Users must manually implement IR workflows.

Source: [Mochi Cards](https://mochi.cards/)

### 4.7 Anki with IR Add-ons

Several add-ons bring IR features to Anki:

**Incremental Reading v4.10.3 (official):**
- Import articles as Anki notes
- Read within Anki, create extracts and cloze deletions
- Basic scheduling for reading material

**Incremental Reading v4.13.0 (unofficial clone):**
- Updated fork with compatibility fixes for newer Anki versions
- ID: 999215520

**Limitations:**
- Anki was designed for flashcards, not reading -- the IR experience is clunky
- Compatibility issues with newer Anki versions are common
- No priority queue or sophisticated topic scheduling
- Platform support is inconsistent across add-on versions

Sources: [Anki IR v4.10.3](https://ankiweb.net/shared/info/935264945), [Unofficial clone](https://ankiweb.net/shared/info/999215520), [GitHub: anki-ir](https://github.com/za3k/anki-ir)

### 4.8 Dendro

A web-based app specifically designed to make incremental reading accessible to non-SuperMemo users.

**Features:**
- Mobile-friendly (described as "the best option for a mobile incremental reading system" despite being in development)
- Simplified IR workflow
- Algorithmic scheduling for reading material
- Created by Ollie Lovell, who found introducing SuperMemo to others was "a painful process"

**Status:** Still in development but functional for basic IR.

Sources: [Dendro](https://dendro.cloud/), [Ollie Lovell on IR](https://www.ollielovell.com/spaced-repetition-incremental-reading-anki-dendro/)

### 4.9 ZKMemo

A free, offline-first note-taking and learning application combining FSRS-based spaced repetition with incremental reading.

**Features:**
- SuperMemo-like interface
- Tree-structured knowledge management
- AI integration
- Zettelkasten-style linking
- FSRS scheduling algorithm
- Free offline storage with optional cloud sync upgrade

Source: [ZKMemo](https://zkmemo.com)

### 4.10 Obsidian Plugins

Multiple plugins bring IR-adjacent features to Obsidian:

**Incremental Writing (bjsi):**
- Add notes and blocks to prioritized queues
- A-Factor-based or simple scheduling
- Multiple queues with manual priority editing
- Tag-based automation
- SuperMemo-inspired design

**Spaced Repetition Plugin (st3v3nmw):**
- Flashcards within Obsidian markdown files
- Note-level spaced repetition review scheduling
- 26+ SRS plugins available as of 2025

**Better Recall:**
- Anki-like experience inside Obsidian
- Built-in scheduler based on Anki algorithm

Sources: [Incremental Writing - GitHub](https://github.com/bjsi/incremental-writing), [Obsidian Spaced Repetition](https://github.com/st3v3nmw/obsidian-spaced-repetition), [Best SRS Plugins](https://www.obsidianstats.com/posts/2025-05-01-spaced-repetition-plugins)

### 4.11 Emacs / Org-mode

**Org-Drill:** Spaced repetition extension for Org mode supporting SM2, SM5, and Simple8 algorithms.

**Incremental reading support:** Org-mode provides infrastructure for IR via org-capture templates and org-protocol. You can capture web snippets, annotate them, and review using org-drill scheduling. The EmacsWiki has a dedicated [Incremental Reading](https://www.emacswiki.org/emacs/IncrementalReading) page.

**org-mode-incremental-reading (vascoferreira25):** A SuperMemo-inspired implementation that breaks articles into small parts for incremental processing, with Anki export.

Sources: [Org-Drill](https://orgmode.org/worg/org-contrib/org-drill.html), [GitHub: org-mode-incremental-reading](https://github.com/vascoferreira25/org-mode-incremental-reading)

### 4.12 Logseq

Logseq has built-in spaced repetition (using cljc-fsrs in its database version) but the SRS implementation has had issues:
- The algorithm was broken in the plain-text version
- Only fixed in the database version
- Scheduling intervals for new cards reported as too long

For IR, Logseq users typically rely on community plugins or manual workflows.

Source: [Logseq SRS issue #8890](https://github.com/logseq/logseq/issues/8890)

### 4.13 FSRS Ecosystem

The **Free Spaced Repetition Scheduler** (FSRS) is an open-source algorithm based on the DSR (Difficulty, Stability, Retrievability) model. It uses machine learning to create personalized review schedules and achieves 20-30% fewer reviews than Anki's default algorithm for the same retention level.

FSRS implementations exist in: JavaScript, Python, Rust, Go, and more. It powers scheduling in Anki (via fsrs4anki), RemNote (via fsrs4remnote), Obsidian, Logseq, and other tools.

While FSRS optimizes flashcard scheduling, it could theoretically be adapted for topic/reading scheduling -- an area of potential innovation.

Sources: [FSRS GitHub](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler), [Awesome FSRS](https://github.com/open-spaced-repetition/awesome-fsrs)

### 4.14 Other Notable Tools

- **Glasp:** Social web highlighter used by 1M+ users. Highlight text on web/PDF, organize highlights, build AI clone from highlights. Social sharing and discovery of others' highlights. Exports in TXT, CSV, HTML, MD. [glasp.co](https://glasp.co/)
- **Screvi:** Read-it-later app where highlights flow into a knowledge library and get resurfaced through spaced repetition.
- **NeuraCache:** Mobile app providing spaced repetition for highlights from Notion, Evernote, Obsidian, Bear. Visually appealing, user-friendly interface.
- **Heptabase:** Visual knowledge management with whiteboards and card-based organization. Readwise integration. Five-step learning method (highlight, dissect, map, group, integrate). No dedicated SRS.
- **Soki.ai:** Discusses AI-powered incremental reading workflows combining prioritization, active recall, and spaced repetition.
- **Wallabag:** Open-source self-hosted read-it-later app (alternative to the defunct Omnivore).
- **Omnivore:** Was an excellent open-source read-it-later app. Acquired by ElevenLabs in October 2024, cloud service shut down November 2024. Source code remains open for self-hosting.


---

## 5. Academic Research

### 5.1 Dunlosky et al. (2013) -- The Definitive Learning Techniques Review

The most comprehensive review of learning techniques relevant to IR:

| Technique | Utility Rating | IR Relevance |
|---|---|---|
| Practice testing | **High** | Cloze deletion / active recall stage |
| Distributed practice | **High** | Core mechanic of spaced reading |
| Elaborative interrogation | Moderate | Implicit in extract creation |
| Self-explanation | Moderate | Implicit in cloze crafting |
| Interleaved practice | Moderate | Natural consequence of IR workflow |
| Summarization | Low | Extraction is a form of summarization |
| Highlighting | **Low** | IR goes beyond highlighting to extraction |
| Keyword mnemonic | Low | Not used in IR |
| Imagery for text | Low | Not central to IR |
| Rereading | **Low** | IR replaces rereading with active recall |

Notably, the two highest-rated techniques (practice testing and distributed practice) are the two pillars of IR. The low-rated techniques (highlighting, rereading) are what IR explicitly replaces.

Source: [Dunlosky et al. (2013)](https://journals.sagepub.com/doi/abs/10.1177/1529100612453266)

### 5.2 Michael Nielsen -- Augmenting Long-term Memory (2018)

Nielsen's influential essay describes his Anki-based workflow for reading technical papers. Key findings:

- **Multi-pass reading:** Initial rapid skim, successive deeper passes, final detailed read
- **The AlphaGo experiment:** Several days of systematic reading with Anki established durable expertise in deep reinforcement learning
- **Syntopic reading:** Deep engagement with 5-10 foundational papers + shallow reads of dozens of supporting papers
- **Card construction as understanding:** "The process of constructing cards is itself a form of understanding"
- **Atomic questions:** Breaking compound questions into focused units improves retention
- **The 10-minute rule:** If memorizing something seems worth 10 minutes of future time, it merits an Anki entry
- **90% of value is simple:** Show prompts-and-responses on a variable schedule controlled by binary choices

Wozniak's response: Nielsen essentially "re-discovered incremental reading with Anki," arriving at many of the same conclusions independently.

Sources: [Augmenting Long-term Memory](https://augmentingcognition.com/ltm.html), [Michael Nielsen re-discovers IR - supermemo.guru](https://supermemo.guru/wiki/Michael_Nielsen_re-discovers_incremental_reading_with_Anki)

### 5.3 Matuschak & Nielsen -- The Mnemonic Medium

Research on Quantum Country demonstrated that embedding spaced repetition prompts in text can produce substantial retention without separate study sessions. Key findings:

- Readers who engaged with embedded prompts retained ~80% of material after months
- Author-written prompts can scaffold good prompt-writing habits
- The medium gives structure to normally-atomized SRS prompts by keeping them connected to their source context
- Contextual anchoring (answering questions near the relevant text) may improve initial encoding

This represents a different approach than IR: rather than the reader extracting and reformulating, the author pre-designs the learning experience. The two approaches could be complementary.

Sources: [Mnemonic medium - Andy Matuschak](https://notes.andymatuschak.org/Mnemonic_medium), [How to make memory systems widespread?](https://michaelnotebook.com/mmsw/)

### 5.4 Active Reading Research

Meta-analyses on active reading strategies show mixed results:

- **Annotation** (marginal notes while reading): Positive evidence for increasing memory and comprehension by changing reading from passive to active
- **Highlighting alone:** Considered one of the least effective learning strategies -- but only when done in isolation. Combined with subsequent active processing (as in IR), it becomes the first step in a productive pipeline
- **Digital vs. paper:** Students annotate significantly less on laptop than on paper, and neither highlighting nor annotations alone influence subsequent memory in either condition
- **Combined strategies:** Impact on learning is greater when strategies are combined, especially with active processing and retrieval practice

The implication for IR: highlighting/extracting by itself is insufficient. The power comes from the downstream processing -- converting extracts to questions and scheduling active review.

Sources: [Effects of Highlighting on Learning - ResearchGate](https://www.researchgate.net/publication/357668403_Effects_of_Learner-Generated_Highlighting_and_Instructor-Provided_Highlighting_on_Learning_from_Text_A_Meta-Analysis), [Meta-Analysis of Reading Strategies - ERIC](https://files.eric.ed.gov/fulltext/ED493483.pdf)

### 5.5 Knowledge Tracing and Learner Modeling

The academic field of **knowledge tracing** (KT) is directly relevant to the Petrarca vision. KT aims to model a learner's knowledge state by analyzing their interaction history, then predict future performance and adapt instruction accordingly.

Key approaches:
- **Bayesian Knowledge Tracing (BKT):** Models knowledge as binary (known/unknown) per skill
- **Deep Knowledge Tracing (DKT):** Uses deep neural networks to capture complex learning patterns
- **Dynamic learner modeling:** Tracks how learner features evolve over time, shifting from static profiling to dynamic perception
- **Knowledge graph-based approaches:** Model relationships between concepts to recommend learning paths

This research has primarily been applied in **intelligent tutoring systems** and **MOOCs**, not in reading/knowledge management tools. There is a gap between the KT research community and the IR/PKM community that represents an opportunity.

Sources: [Survey of Knowledge Tracing](https://arxiv.org/html/2105.15106v4), [Personalized Learning Path Recommendation - MDPI](https://www.mdpi.com/2079-9292/15/1/238)


---

## 6. The Extract-Transform-Review Pipeline

### 6.1 How Different Tools Handle the Pipeline

The progression from raw article to long-term knowledge follows a general pattern, but different tools emphasize different stages:

```
RAW SOURCE --> CAPTURE --> HIGHLIGHT/EXTRACT --> TRANSFORM --> SCHEDULE/REVIEW --> LONG-TERM KNOWLEDGE
```

**SuperMemo (full pipeline):**
```
Web article --> Import to collection --> Read & extract (Alt+X) --> Cloze deletion (Alt+Z) --> SM-18 algorithm schedules review --> 95% retention
```
All stages happen within one tool. Reading is scheduled. Extracts are scheduled. Items are scheduled. Priority queue manages everything.

**Readwise + Reader (highlight-centric):**
```
Article in Reader --> Highlight while reading --> Highlights sync to Readwise --> Daily Review resurfaces highlights --> Optional: convert to Q&A/cloze --> Spaced repetition review
```
Strong at capture and resurfacing. Weaker at the transform-to-active-recall step (optional, not pushed).

**Obsidian + Plugins (note-centric):**
```
Article --> Manual import/clip to Obsidian --> Take notes with wikilinks --> Tag for incremental review --> Plugin schedules note review --> Create flashcards from notes
```
Maximum flexibility but requires significant manual orchestration. The "glue" between stages is the user.

**Orbit (author-embedded):**
```
Author writes article with embedded prompts --> Reader answers prompts while reading --> Orbit schedules review sessions --> Reader returns to answer prompts at expanding intervals
```
Eliminates the extract/transform stages by having the author do this work. Accessible but not personalized.

**Progressive Summarization (Tiago Forte):**
```
Source --> Layer 1: Capture to notes app --> Layer 2: Bold key passages --> Layer 3: Highlight best of best --> Layer 4: Write executive summary --> Layer 5: Create original content
```
Not scheduled -- processing happens opportunistically when you revisit notes for projects. No spaced repetition. The insight is that summarization should be **lazy and incremental**, not upfront.

### 6.2 Progressive Summarization (Forte)

Tiago Forte's approach differs fundamentally from IR in that it is **project-driven** rather than **knowledge-driven**. You don't process notes because a scheduler tells you to; you process them when you need them for a specific project.

The five layers:
- **Layer 0:** Original source
- **Layer 1:** Captured passages (the raw highlight)
- **Layer 2:** Bold the most important parts (quick scanning)
- **Layer 3:** Highlight the "best of the best" (rapid identification)
- **Layer 4:** Executive summary in your own words
- **Layer 5:** Remixed into original content

Core philosophy: "The challenge is knowing which knowledge is worth acquiring... to the future situation or problem or challenge where it is most applicable." Since you cannot predict future use, summarization should preserve full context while creating progressively more discoverable layers.

**Comparison with IR:**
- IR processes everything proactively; PS processes on-demand
- IR uses algorithmic scheduling; PS uses project-triggered review
- IR aims for recall; PS aims for discoverability
- IR works within one tool; PS works across any tool
- IR is more effective for retention; PS is more practical for creative production

Source: [Progressive Summarization - Forte Labs](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)

### 6.3 The Key Bottleneck

Across all implementations, the bottleneck is the **transform** stage: converting passive highlights into active recall items. This requires:

1. Understanding the material well enough to identify what matters
2. Reformulating information as questions (a skill that takes practice)
3. Ensuring questions are atomic, unambiguous, and well-connected
4. Doing this for every piece of material you read (scaling problem)

AI is beginning to address this bottleneck. Tools like Readwise's Ghostreader, Glasp's AI features, and various flashcard generators can auto-generate questions from highlighted text. However, Nielsen's insight holds: "The process of constructing cards is itself a form of understanding" -- outsourcing this to AI may reduce the learning benefit.


---

## 7. What is Different About the Petrarca Vision

### 7.1 The Upstream Innovation

Traditional incremental reading starts **after** you have already decided to read something. The pipeline is:

```
[You find an article] --> Import --> Read --> Extract --> Cloze --> Review
```

The Petrarca innovation is to add a critical stage **before** import:

```
[Article arrives in feed] --> SCORE for novelty & relevance against user knowledge model --> Prioritize/filter --> Import --> Read --> Extract --> Review
```

This is a fundamentally different problem. IR optimizes **how** you read. Petrarca optimizes **what** you read.

### 7.2 Prior Art: Novelty Detection in Recommendations

Academic research on novelty-aware recommendation systems provides relevant foundations:

**Novelty scoring:** A novel item for a user is one that the user has none or little knowledge about. Systems compute novelty based on how different an item is from the user's known preferences and consumption history.

**User interest modeling:** Knowledge graphs capture relationships between concepts a user has engaged with. User-specific embeddings identify important knowledge graph relationships, creating personalized item representations.

**Content-based filtering with novelty:** Context-based user profiles can filter recommendations using novelty scores derived from the user's history, providing items that add genuinely new information rather than repeating what's already known.

**SHARE system:** A research paper recommendation system that considers "paper's novelty, relevancy, complexity, diversity, and user's intention at a particular time."

Key academic sources:
- [Personalized News Recommendation with Novelty](https://link.springer.com/article/10.1007/s11036-017-0842-9) -- Collaborative filtering with novelty using rough set theory
- [Taxonomy Based Personalized News Recommendation](https://link.springer.com/chapter/10.1007/978-3-642-41230-1_18) -- Novelty and diversity via taxonomic classification
- [Evaluating Content Novelty in Recommender Systems](https://link.springer.com/article/10.1007/s10844-019-00548-x) -- Metrics for evaluating novelty
- [Automated Novelty Evaluation of Academic Papers](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.70005) -- Using LLMs for novelty assessment (2025)

### 7.3 Prior Art: Knowledge State Modeling

**Knowledge tracing** from educational technology directly addresses modeling what a user knows:

- **Deep Knowledge Tracing (DKT):** Neural networks model latent knowledge states from interaction history
- **Personalized learning path recommendation:** Knowledge graphs guide learners based on current mastery
- **Real-time knowledge state updates:** Modern systems dynamically update learner models as new data arrives

The gap: these systems have been applied to structured educational content (exercises, quizzes, courses) but **not** to unstructured reading and knowledge management. Adapting KT to model a reader's knowledge state based on their reading history, highlights, and extracted notes is largely unexplored.

Sources: [Deep Knowledge Tracing - Nature](https://www.nature.com/articles/s41598-025-10497-x.pdf), [Knowledge Tracing Survey](https://arxiv.org/html/2105.15106v4)

### 7.4 Prior Art: Intentional Feed Curation

**BONSAI (2025):** A system enabling users to build personalized, intentional social media feeds. Users express intent in natural language, and a framework of Planning, Sourcing, Curating, and Ranking modules creates transparent, personalized feeds. Study with 15 Bluesky users found users successfully discovered new content and filtered irrelevant/toxic posts.

Key insight from BONSAI: "Instead of relying solely on engagement signals inferred from past behavior, recommender systems and feed algorithms can now incorporate direct user input about what they want to see." This aligns with Petrarca's vision of intentional, knowledge-state-aware content selection.

Source: [BONSAI - arXiv](https://arxiv.org/abs/2509.10776)

### 7.5 Prior Art: Information Diet and Content Filtering

- **Readwise Reader** approaches this with AI-powered feed summarization and themed reviews, but doesn't model the user's knowledge state
- **Pocket / Instapaper** save articles for later but provide no scoring or prioritization
- **RSS readers** (Feedly, etc.) offer topic-based filtering but no novelty scoring against what you already know
- **Academic paper recommenders** (Semantic Scholar, ResearchRabbit, Connected Papers) recommend related papers but don't model what the user already knows from their reading history
- **Readless** (2025-2026) focuses on content curation strategies for managing information overload

### 7.6 The Gap Petrarca Fills

No existing tool combines all three of these capabilities:

1. **Knowledge state modeling:** Building an embedding-based model of what the user knows and cares about, derived from their reading history, highlights, and notes
2. **Upstream novelty scoring:** Scoring incoming articles for how much genuinely new, relevant information they contain relative to the user's current knowledge
3. **Incremental reading pipeline:** Managing the downstream process of reading, extracting, and retaining knowledge from the selected articles

Existing tools address at most one or two of these. SuperMemo handles (3) excellently but has no (1) or (2). Readwise handles parts of (3) but not (1) or (2). Academic recommendation systems handle (2) for papers but not in the context of a personal knowledge management workflow.

The Petrarca vision is to close this loop: **your reading history informs your knowledge model, which scores incoming content, which determines what you read next, which updates your knowledge model.**

### 7.7 Related Concepts

**Wozniak's Knowledge Valuation Network:** Wozniak theorized about how the brain assigns value to information based on its connections to goals and existing knowledge. Petrarca's upstream scoring is essentially an externalized, computational version of this: scoring articles based on their information-theoretic value relative to the user's knowledge graph.

**SuperMemo's Priority Bias:** Wozniak identified that humans systematically over-prioritize new information. Petrarca's novelty scoring could help counteract this by providing an objective measure of how novel an article actually is, not just how novel it feels.

**Nielsen's Syntopic Reading:** Nielsen's approach of deep reading in a few key papers + shallow reads across many supporting papers could be computationally supported: the system identifies which papers are "foundational" (high novelty, high centrality) vs. "supporting" (overlap with known material, peripheral).


---

## 8. Key Takeaways for Petrarca

### 8.1 What to Learn from SuperMemo

- The priority queue with auto-postpone is a proven solution to information overload
- Separate scheduling for reading material (topics) vs. recall items (items) is important -- reading needs flexibility, recall needs precision
- The A-Factor system for reading material is simple and effective
- Knowledge darwinism suggests redundancy in knowledge representation is a feature, not a bug
- The full pipeline (import -> read -> extract -> cloze -> review) is powerful but the learning curve is the primary barrier to adoption

### 8.2 What to Learn from Modern Tools

- Readwise shows that lightweight spaced repetition of highlights can provide 80% of the value with 20% of the complexity
- Orbit shows that author-embedded prompts can dramatically lower the barrier to active recall
- FSRS shows that modern ML-based scheduling algorithms outperform classical SM-2/SM-5
- Progressive Summarization shows that lazy, incremental processing is more sustainable than upfront exhaustive processing
- Mobile access is essential -- SuperMemo's Windows-only limitation is a major adoption barrier

### 8.3 What to Learn from Research

- The spacing effect and testing effect are the two most validated learning techniques -- both should be central
- Interleaving helps but may hurt for complex, interconnected topics -- the system should allow "deep dive" modes
- Elaborative interrogation works best when learners have background knowledge -- novice users may need scaffolding
- Knowledge tracing provides the theoretical framework for modeling user knowledge state
- Novelty-aware recommendation is an active research area but has not been applied to personal knowledge management

### 8.4 The Petrarca Differentiator

The core insight that distinguishes Petrarca from everything else in this space:

**Traditional IR:** "Here are 10,000 articles. Let me help you process them efficiently."

**Petrarca:** "Before you even see these 10,000 articles, let me tell you which 200 will actually teach you something new and relevant -- and here's why."

This upstream filtering, based on a continuously updated model of the user's knowledge state, is the key innovation. Everything downstream (reading, extracting, reviewing) can build on existing approaches. But the upstream scoring is where the novel value lies.

---

*Last updated: March 2, 2026*
