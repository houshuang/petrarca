# Spaced Attention: Beyond Flashcards to Concept-Level Engagement

*Research compiled March 2026 for the Petrarca project*

---

## Table of Contents

1. [The Core Problem](#1-the-core-problem)
2. [Andy Matuschak's Framework](#2-andy-matuschaks-framework)
3. [Rob Haisfield and Scaling Synthesis](#3-rob-haisfield-and-scaling-synthesis)
4. [Piotr Wozniak's Incremental Reading](#4-piotr-wozniaks-incremental-reading)
5. [Readwise: Practical Spaced Resurfacing](#5-readwise-practical-spaced-resurfacing)
6. [Academic Foundations](#6-academic-foundations)
7. [The Concept Card: What It Looks Like](#7-the-concept-card-what-it-looks-like)
8. [Design Principles for Petrarca](#8-design-principles-for-petrarca)
9. [Open Questions](#9-open-questions)
10. [Sources](#10-sources)

---

## 1. The Core Problem

Traditional spaced repetition systems (Anki, SuperMemo flashcards) work brilliantly for discrete facts: vocabulary words, dates, formulas. But for the kind of reading Petrarca targets -- history, cultural theory, technical topics -- the user's own experience is clear: **SRS on individual facts from reading is "completely useless and unmotivating."**

Why? Several compounding reasons:

**Facts without frameworks are inert.** Knowing that the Pirenne thesis was published in 1922-23 is meaningless without understanding why it mattered, what it challenged, and how it reshaped medieval historiography. A flashcard testing the date teaches nothing.

**Understanding is relational, not atomic.** Grasping the Pirenne thesis means connecting it to: the fall of Rome, Islamic expansion, Carolingian economics, the Annales school, Bloch's social history. These connections cannot be tested with cloze deletions.

**Motivation comes from growth, not recall.** The experience of "I understand this better now than I did a month ago" is deeply motivating. The experience of "I remembered the date" is not. Reading engagement depends on the feeling of conceptual progress.

**Reading is generative, not receptive.** Deep reading produces new thoughts, questions, and connections. A system that only asks "do you remember X?" ignores the most valuable part of the reading process -- what the reader *thinks* about X.

The question becomes: can we apply the spacing principle (distributed re-engagement over time) to **ideas, frameworks, and evolving understanding** rather than to factual recall?

---

## 2. Andy Matuschak's Framework

Andy Matuschak's work provides the most developed theoretical foundation for this problem. His key contributions span several interconnected concepts.

### 2.1 Programmable Attention

Matuschak reframes spaced repetition as fundamentally about **programming attention**, not memorizing facts:

> "The efficacy of a spaced repetition memory system comes from its power to program your attention."

He calls it "a cron for your mind." You make a coarse decision ("I'll do 10 minutes of review"), then the system directs your attention to high-priority items within that block. The core mechanism generalizes to three components:

- A priority queue of microtasks
- An interactive interface presenting high-priority items
- Feedback mechanisms modifying task priority

This abstraction immediately breaks free of the flashcard paradigm. The "microtask" need not be "recall this fact." It could be "reflect on this idea," "connect this framework to something you read yesterday," or "has your understanding of this concept changed?"

Source: [Spaced repetition systems can be used to program attention](https://notes.andymatuschak.org/Spaced_repetition_systems_can_be_used_to_program_attention)

### 2.2 "Spaced Everything"

Matuschak's concept of "spaced everything" generalizes the expanding-interval principle across domains far beyond flashcards:

- **Habit development**: Cards prompting reflection on new behaviors at strategic intervals
- **Incremental reading**: Scheduling re-engagement with texts over time
- **Creative development**: Scheduling fine-grained activities like "reach out to interesting people in a new field"
- **Practice routines**: His piano example -- tracking exercises, prioritizing based on recency and performance, presenting a queue of practice work
- **Inbox management**: Applying spacing to email, to-do lists, reading lists

The unifying principle: **any domain where distributed engagement over time improves outcomes** can benefit from automated spacing.

For Petrarca, this means the system need not be limited to "review this highlight." It could schedule: re-read this section, revisit this argument, connect this idea to your notes on X, or simply "think about the Pirenne thesis for 2 minutes."

Source: [Spaced everything](https://notes.andymatuschak.org/z9hscgkG2TeqgUtu3vAEW3U)

### 2.3 Salience Prompts

One of Matuschak's most relevant ideas for Petrarca is **salience prompts** -- spaced repetition prompts designed not to test recall but to keep ideas top-of-mind:

> "One valuable use for spaced repetition prompts is to keep ideas salient, top of mind, over longer periods of time."

Salience is about **what you notice**. When something is fresh in your mind, you spot related phenomena in daily life. Matuschak describes this as extending the Baader-Meinhof phenomenon deliberately. The goal is to keep certain lenses active so that when you encounter relevant material, you recognize it.

He recommends phrasing salience prompts around contexts where ideas might be meaningful: "When designing a distributed system, what principle from X should I consider?" rather than "What did X say about distributed systems?"

The scheduling for salience prompts is acknowledged to be "probably all wrong" in standard SRS -- they need different algorithms than recall prompts, because the goal is sustained awareness rather than retrievability.

**For Petrarca**: A user reading about medieval trade routes who has previously engaged with the Pirenne thesis should have that framework kept salient. Not "what year was the Pirenne thesis published?" but rather "as you read about Mediterranean trade, consider how this relates to Pirenne's argument about Islamic commerce." The system prompts *application of frameworks*, not recall of facts.

Source: [Salience prompts](https://notes.andymatuschak.org/zF8pCkzLVarNsaFyBxF9Aib)

### 2.4 Developing Inklings Through Spacing

Matuschak proposes using spaced repetition to **incrementally develop nascent ideas** -- thoughts that are not yet ready for full exploration:

> "I'm often struck by an interesting question or notion in conversation or on a walk. In many cases, I can't write anything terribly insightful on that topic in that moment."

His proposed workflow:

1. **Capture** inchoate ideas in a writing inbox
2. **Regular review**: Present a small selection of prompts during daily writing sessions
3. **Graduated feedback**: Mark prompts "fruitful" (schedule sooner), "unfruitful" (delay substantially), or ignore (moderate delay)
4. **Conversion**: Transform developed prompts into formal evergreen notes when ready
5. **Scale**: "By taking advantage of the exponential nature of spaced repetition intervals, one could make incremental progress on potentially hundreds of prompts, while considering only a few on any given day."

This is directly relevant to Petrarca's vision of voice notes and personal annotations becoming part of the review cycle. A half-formed thought about the Pirenne thesis, captured as a voice note while reading, could resurface weeks later when the user has read more relevant material -- and the thought may have crystallized.

Source: [Spaced repetition may be a helpful tool to incrementally develop inklings](https://notes.andymatuschak.org/Spaced_repetition_may_be_a_helpful_tool_to_incrementally_develop_inklings)

### 2.5 Timeful Texts

Matuschak and Nielsen's concept of **timeful texts** addresses the temporal poverty of traditional reading:

> "Books lack mechanisms to engage readers beyond initial reading. To be transformed by a book, readers must bathe in the book's ideas, relate those ideas to experiences in their lives over weeks and months... Unfortunately, readers must drive that process for themselves."

Their proposed alternative: "texts with affordances extending the authored experience over weeks and months, texts which continue the conversation with the reader as they slowly integrate those ideas into their lives."

Key findings from Quantum Country:

- Review sessions "didn't just build detailed retention: the ongoing practice also changed readers' relationship to the material by maintaining their contact with it over time"
- Less than 50% additional time investment yields months or years of detailed retention
- The medium changed **identity** -- regular review caused readers to think of themselves as "doing quantum computing" in a more serious way

The identity transformation finding is particularly significant for Petrarca. A system that keeps the user in contact with, say, medieval history frameworks over months could shift their self-concept from "someone who read a book about medieval history" to "someone who is developing expertise in medieval history."

Source: [Timeful Texts](https://numinous.productions/timeful/)

### 2.6 Prompts for Application, Synthesis, and Creation

Matuschak explicitly addresses using SRS prompts beyond memorization:

> "The same mechanisms can be used to create relatively unorthodox cards which prompt application, synthesis, and creation."

A critical limitation emerges with self-authored application prompts: **vagueness becomes necessary**. He contrasts "apply utilitarianism to a recent decision" (vague but reusable) vs. "apply utilitarianism to the death penalty" (specific but becomes mere recall after first use). For self-authored prompts, the specific version fails because the user has already processed the answer.

The solution he proposes: **embedding application prompts within educational content**, where an external author can ask readers to apply concepts "in combination, in a novel situation" without predetermined answers.

For Petrarca, this suggests that **the system itself should generate novel application prompts** using the user's current reading context. "You're reading about Viking trade routes. How does this connect to the Pirenne thesis you engaged with last month?" -- a prompt that could only be generated by knowing the user's reading history.

Source: [Spaced repetition memory systems can be used to prompt application, synthesis, and creation](https://notes.andymatuschak.org/Spaced_repetition_memory_systems_can_be_used_to_prompt_application,_synthesis,_and_creation)

### 2.7 Conceptual Understanding Through SRS

Matuschak argues that SRS can develop genuine understanding, not just recall, through specific techniques:

- **Multi-angle encoding**: "Spaced repetition memory prompts should encode ideas from multiple angles"
- **Relationship-focused questions**: Testing connections, implications, causes, and consequences
- **Sustained engagement**: Regular interaction keeps learners "in contact with the topic and help you internalize it more deeply"

Research by Butler (2010) and Karpicke & Blunt (2011) demonstrates the testing effect works for conceptual questions. Building intuition requires minimizing inferential distance on each card -- "each flashcard should only have one inferential step on it" -- but those steps can be about logical deduction, visualization, or connection-making, not just fact retrieval.

Source: [Spaced repetition memory systems can be used to develop conceptual understanding](https://notes.andymatuschak.org/z9Vi7YVx7NzxU2wawNgsJbk)

### 2.8 The "Why Books Don't Work" Argument

Matuschak's argument that books are built on **transmissionism** -- the false assumption that "people absorb knowledge by reading sentences" -- is foundational for Petrarca. Books leave readers responsible for self-monitoring, question-formulation, and feedback generation, all "quite taxing" cognitive tasks. Most readers experience an **illusion of understanding** while retaining minimal information.

His proposed solution: design mediums where "default actions and patterns of thought" align with "what's necessary to understand." Comprehension should be the inevitable outcome of engagement, not an optional add-on.

Source: [Why books don't work](https://andymatuschak.org/books/)

### 2.9 Implicit Practice and the Sight Reading Parable

In "Implicit practice: a sight reading parable," Matuschak challenges the assumption that knowledge workers develop skills implicitly through daily work. Despite thousands of hours at the piano, his sight-reading remained at beginner level because he never practiced it deliberately -- he always memorized pieces instead.

The parallel for reading: we may read thousands of articles without improving our ability to **synthesize, connect, or retain** what we read, because passive reading does not develop those skills. A system like Petrarca could provide the structured practice that transforms reading from passive consumption into active skill development.

Source: [Implicit practice: a sight reading parable](https://andymatuschak.org/sight-reading/)

### 2.10 "How Might We Learn?" -- Enabling Environments

In his 2024 UCSD talk, Matuschak argues that the most transformative learning happens when "learning wasn't the point" -- people were immersed in meaningful pursuits and learned what they needed along the way. He proposes four design principles:

1. **Contextual guidance**: Bring instructional support directly into authentic work, not separated
2. **Infused authenticity**: Ground all study activities in learners' actual aims and projects
3. **Community connection**: Help learners access legitimate peripheral participation
4. **Dynamic reinforcement**: Practice should vary over time, transfer to real situations, deepen progressively

For Petrarca: the system should support the user's actual intellectual projects (understanding medieval history, grasping cultural theory), not create artificial learning tasks. Re-engagement should feel like continuing a conversation with the material, not doing homework.

Source: [How Might We Learn?](https://andymatuschak.org/hmwl/)

### 2.11 Evergreen Note Maintenance as Organic Spaced Repetition

Matuschak observes that maintaining a densely-linked note system creates a natural spacing effect:

> "We learn something not only when we connect it to prior knowledge and try to understand its broader implications (elaboration), but also when we try to retrieve it at different times (spacing)" -- Ahrens

When you actively work on related topics, you naturally encounter and revise earlier notes. The spacing follows your authentic interests rather than an artificial schedule. This approach leverages the **generation effect** (revising requires effort and produces meaningful updates) rather than the testing effect.

For Petrarca: the user's own notes and voice recordings should re-enter the system as review items. When the user returns to a topic area, their earlier thoughts on related material should surface naturally, creating organic spacing driven by genuine intellectual interest.

Source: [Evergreen note maintenance approximates spaced repetition](https://notes.andymatuschak.org/Evergreen_note_maintenance_approximates_spaced_repetition)

---

## 3. Rob Haisfield and Scaling Synthesis

### 3.1 Background

Rob Haisfield is a behavioral product strategist and gamification designer. His research home is [Scaling Synthesis](https://scalingsynthesis.com), a living hypertext notebook co-authored with Joel Chan and Brendan Langen, exploring "data structures and interfaces that support synthesis and innovation in a decentralized discourse graph."

### 3.2 Contextual Knowledge Re-engagement

Haisfield's key contribution relevant to Petrarca is not a specific "spaced attention" tool but rather a framework for **how ideas gain value through re-contextualization**. His hypertext notebook operates on the principle that "pages that you've already read may take on new meaning when placed into new contexts." This is a design principle, not an algorithm, but it directly addresses the limitation of standard SRS.

His stated aim: "express ideas in a way that each idea is placed into its broader context whenever I add something new." Knowledge management becomes an iterative, contextualized process -- each time you revisit an idea, it exists in a richer context than before.

Source: [Rob's Hypertext Notebook](https://robhaisfield.com/about)

### 3.3 Behavioral Design for Knowledge Work

Haisfield's background in behavioral economics and gamification brings a practical lens to knowledge engagement:

- **The "cream rises to the top" principle**: People who capture fleeting thoughts need mechanisms for the best ideas to surface repeatedly. This is essentially spaced attention without the SRS machinery -- using behavioral design to ensure important ideas get revisited.
- **Continuous onboarding**: His framework from product design applies to knowledge systems -- the user should never stop discovering new capabilities and connections in their own knowledge base.
- **Feedback loops and portfolio effects**: Learning through diverse applications of the same ideas, where each application deepens understanding.

Source: [Scaling Synthesis](https://scalingsynthesis.com/), [ClearerThinking Podcast](https://podcast.clearerthinking.org/episode/049/rob-haisfield-user-engagement-and-expert-intuition)

### 3.4 Voiceliner and Voice-Based Capture

The Scaling Synthesis project includes analysis of **Voiceliner**, an app for voice-based thought capture that is directly relevant to Petrarca's voice-note integration. Voiceliner uses a "hold to record" interaction with hierarchical organization, automatic transcription, and location tagging. The design philosophy: capture is fast and frictionless, with review and organization happening separately.

The connection to spaced attention: captured voice thoughts could enter a spaced review queue where they are revisited and refined over time -- exactly Matuschak's "developing inklings" pattern applied to spoken rather than written thoughts.

Source: [Voiceliner on Scaling Synthesis](https://scalingsynthesis.com/voiceliner/)

---

## 4. Piotr Wozniak's Incremental Reading

*(Covered in depth in incremental-reading.md; summary of concepts relevant to spaced attention here.)*

### 4.1 Reading as a Scheduled Activity

Wozniak's core insight: **reading should be scheduled the same way flashcard reviews are scheduled.** Instead of finishing an article in one sitting, you read a portion, then the software schedules you to return days or weeks later. This is "spaced reading" at the most literal level.

The dual scheduling system is key: **topics** (reading material) use a simpler, user-controllable schedule with A-Factors, while **items** (flashcards) use the complex SM algorithm. Reading benefits from spacing but does not require the same precision as recall testing.

### 4.2 Incremental Writing

Wozniak extended the concept to **incremental writing** -- composing text in small bursts scheduled by the system. You work on a piece for a few minutes, then it re-enters the queue. The spacing provides time for unconscious processing and the accumulation of new relevant knowledge between sessions.

This maps directly to Petrarca's vision of voice notes that develop over time. A note about the Pirenne thesis, captured on day 1, could be extended on day 15 after reading more about Mediterranean trade, and again on day 45 after encountering a critique of the thesis.

### 4.3 The Knowledge Funnel

SuperMemo's pipeline -- Import, Read, Extract, Cloze, Review -- is a progressive distillation process. But critically, the intermediate stages (extracts, incomplete thoughts) remain in the system and continue to be scheduled. The entire funnel is spaced, not just the final flashcards.

For Petrarca, this suggests that **every artifact in the reading process** should be schedulable: the article itself, highlights, user annotations, voice notes, questions, connections to other material. The system manages a heterogeneous queue of intellectual engagement tasks at various levels of development.

---

## 5. Readwise: Practical Spaced Resurfacing

Readwise provides the most commercially successful implementation of spaced idea resurfacing (as opposed to fact testing).

### 5.1 Daily Review

Readwise resurfaces highlights using a **decaying algorithm based on recall probability half-life**. Once a highlight's recall probability drops to 50% or lower, it becomes a candidate for resurfacing. This is SRS applied to exposure rather than testing -- the user sees the highlight again, which is sufficient to refresh the connection.

### 5.2 Themed Reviews

Readwise moves beyond random resurfacing through **Themed Reviews** -- curated subsets organized by specific purposes:

- **Topic mastery**: Single-book themes for theoretical integration
- **Workflow-based learning**: Project-specific reviews
- **Creative synthesis**: Priming awareness with "inchoate thoughts, slow hunches, and unanswered questions"

Users can up-weight or down-weight the probability of specific books or articles being resurfaced, and bias toward newer or older content.

### 5.3 Intentional Spaced Repetition

Readwise explicitly frames their approach as "spaced repetition has applications far beyond rote schooling." Their writing workflow demonstrates concept-building: progressively editing non-linear thoughts across multiple review cycles, separating drafting from editing. The core innovation: transforming spaced repetition from knowledge *retention* into knowledge *application* and *synthesis*.

### 5.4 Ghostreader

The Ghostreader AI assistant can generate questions, define terms, simplify language, and automate flashcard formatting. This is an early implementation of AI-assisted prompt generation -- but still primarily oriented toward individual highlights rather than conceptual frameworks.

### 5.5 Limitations for Petrarca

Readwise resurfaces **author-written highlights**, not the user's own developing thoughts. It does not model the user's understanding or generate prompts that connect across sources. The resurfacing is essentially random (within themed constraints) rather than responsive to the user's evolving knowledge state. Petrarca can go significantly further.

Source: [Readwise](https://readwise.io/), [Adding Intention to Spaced Repetition](https://blog.readwise.io/adding-intention-to-spaced-repetition/)

---

## 6. Academic Foundations

### 6.1 Schema Theory and Repeated Exposure

Schema theory (Bartlett, 1932; Piaget; Rumelhart, 1980) explains how understanding develops through repeated exposure:

- Learners **actively build schemata** and revise them through repeated encounters with new information
- **Default values emerge naturally** through repeated experiences with specific instances
- Changing schemas requires **multiple exposures** to correct information, explicit comparison with misconceptions, and opportunities to apply understanding in various contexts
- Schema-congruent information is easier to learn than schema-incongruent information, but incongruent information -- when successfully integrated -- produces deeper structural change

For reading: each re-engagement with a text or concept activates and potentially modifies the relevant schema. The first reading creates a rough scaffold; subsequent readings refine, correct, and elaborate the schema. This is why re-reading at spaced intervals can produce understanding that single close reading cannot -- each pass occurs with a richer schema context.

### 6.2 Expert vs. Novice Knowledge Organization

Research on expert-novice differences (Chi, Feltovich, & Glaser, 1981; de Groot, 1965; Gobet & Simon, 2000) reveals fundamental differences in how knowledge is organized:

- **Experts organize by deep principles**: Physics experts group problems by Newton's laws; novices group by surface features (problems about inclined planes)
- **Experts have larger, fewer chunks**: Complex situations are encoded into a small number of "large" chunks vs. many "small" chunks for novices
- **Expert schemas include procedures**: Not just "what" but "how" and "when to apply"
- **Template theory**: Frequently-used chunks become templates with a constant core and variable slots, dramatically expanding memory capability

For Petrarca: the system should support the transition from novice-style organization (facts about medieval history) to expert-style organization (frameworks like the Pirenne thesis that organize many facts). **Concept cards should model frameworks, not facts.** The spacing should support schema enrichment -- each re-engagement adds detail, connections, and application contexts to the framework.

Source: [How People Learn, Ch. 2](http://www.csun.edu/science/ref/reasoning/how-students-learn/2.html), [Gobet (2005)](https://onlinelibrary.wiley.com/doi/abs/10.1002/acp.1110)

### 6.3 Desirable Difficulties (Bjork & Bjork)

The Bjork lab's research on **desirable difficulties** provides the learning-science foundation for spaced attention:

- **Spacing effect**: Distributing practice over time produces better long-term retention than massing, even though massed practice *feels* more effective
- **Interleaving**: Mixing topics during study outperforms blocked study on long-term tests, even though blocked study produces better immediate performance
- **Testing effect**: Retrieval practice strengthens memory more than re-study, but critically, this extends to **conceptual questions**, not just factual ones
- **Illusion of understanding**: Re-reading creates perceptual fluency that is mistaken for comprehension. "Good performance during learning episodes tends to be mistaken for good learning."

The key insight for Petrarca: conditions that feel harder (spacing, interleaving, testing) produce better learning. A system that brings back ideas from weeks ago, interleaves them with current reading, and asks the user to actively engage (not just re-read) will produce deeper understanding -- even if it initially feels less smooth than simply reading forward.

Source: [Bjork & Bjork (2011) Creating Desirable Difficulties](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf)

### 6.4 Elaborative Interrogation and Self-Explanation

Two well-researched techniques map directly to Petrarca's design:

**Elaborative interrogation**: Asking "why is this true?" about stated facts. Rated "moderate utility" in Dunlosky et al.'s (2013) comprehensive review of learning techniques. Works by forcing integration of new information with prior knowledge. For reading engagement, the system could generate "why" questions about key claims in articles.

**Self-explanation**: Prompting learners to explain material as they work with it. Chi et al. showed that students who self-explained performed significantly better on concept tests. The mechanism: self-explanation forces the learner to identify gaps in understanding and fill them.

For Petrarca: rather than asking "what does the Pirenne thesis state?" (recall), the system should prompt "why did Pirenne's argument about Islamic commerce challenge the existing narrative?" (elaborative interrogation) or "explain in your own words how the Pirenne thesis connects trade routes to the fall of Rome" (self-explanation). Voice notes are a natural medium for self-explanation.

Source: [Dunlosky et al. (2013)](https://www.whz.de/fileadmin/lehre/hochschuldidaktik/docs/dunloskiimprovingstudentlearning.pdf), [The Power of Self-Explanation](https://learning.northeastern.edu/the-power-of-self-explanation/)

### 6.5 The Testing Effect for Conceptual Transfer

The testing effect extends beyond simple recall:

- **Transfer**: Retrieval practice effects are smaller but still present when transfer to new contexts is required (applying learned principles to novel problems)
- **Mental model integration**: Online quizzing promotes "a more integrated mental model of target knowledge"
- **Concept mapping + retrieval**: Linking retrieval practice to concept mapping supports organized mental models
- **Meaningful learning**: The testing effect works for conceptual questions when prompts target relationships and implications, not just surface features

However, the transfer-appropriate processing framework suggests that **the type of retrieval practice matters**: if the goal is application and connection-making (not just recall), then the practice tasks should involve application and connection-making.

Source: [PMC4513285](https://pmc.ncbi.nlm.nih.gov/articles/PMC4513285/)

### 6.6 Knowledge Building (Scardamalia & Bereiter)

Scardamalia and Bereiter's Knowledge Building framework (1990s onward) centers on the **collective creation of new cognitive artifacts**:

- Knowledge is "the product of purposeful acts of creation"
- **Idea improvement** is an explicit principle that guides effort
- The direct pursuit of idea improvement "brings schooling into much closer alignment with creative knowledge work"
- Students are tasked with "continually contributing, refining and building on collective knowledge"

This maps to Petrarca's vision of notes and annotations that develop over time. The user is not just remembering what they read -- they are building new understanding through iterative engagement with the material.

Source: [Scardamalia & Bereiter (2014)](https://ikit.org/fulltext/2014-KBandKC-Published.pdf)

### 6.7 Re-reading Research

Research on re-reading shows mixed results that inform Petrarca's design:

- **Guided re-reading works**: "Rereading consists of on-going and repeated encounters with a text, guided by a particular task so that segments of the text get revisited and rethought" -- this produces genuine understanding gains
- **Passive re-reading does not**: Callender & McDaniel (2009) found "a consistent absence of effects of rereading" when using educationally relevant materials with summative assessments
- **The key differentiator is active engagement**: Re-reading with a new question, a new lens, or a new connection task produces learning; re-reading with no specific purpose does not

For Petrarca: spaced re-engagement must be **task-directed**. The system should not simply re-present a highlight -- it should present it with a specific cognitive task (connect, explain, question, apply).

---

## 7. The Concept Card: What It Looks Like

Based on the research above, here is a concrete proposal for what a "concept card" in Petrarca looks like, contrasted with a traditional flashcard.

### 7.1 Traditional Flashcard (What We Are NOT Building)

```
Front: What is the Pirenne thesis?
Back: Henri Pirenne argued that the fall of Rome did not end
      classical civilization; rather, Islamic expansion in the
      7th-8th centuries disrupted Mediterranean trade and caused
      the economic transformation that created medieval Europe.
```

This tests recall of a definition. After a few repetitions, the user can recite the answer without engaging with the idea at all.

### 7.2 Concept Card: Framework Level

A concept card in Petrarca would be a rich, evolving object:

```
CONCEPT: The Pirenne Thesis
TYPE: Historical framework / interpretive lens
STATUS: Developing (engaged 3 times over 6 weeks)

CORE IDEA (user's own words, v3):
Pirenne challenged the "barbarian invasions ended Rome" narrative.
He argued continuity persisted until Islamic expansion cut
Mediterranean trade, making the 8th century the real break point.
This reframed the entire question of "when did antiquity end."

CONNECTIONS (growing over time):
- Links to: Mediterranean trade routes [from article on Viking commerce]
- Links to: Annales school methodology [from Bloch reading]
- Tension with: Archaeological evidence of 5th-century decline
- Relates to: Current reading on Byzantine trade networks

USER NOTES (voice + text, chronological):
- Week 1: "Interesting inversion - not the fall but the cut-off"
- Week 3: "Reading about Carolingian economics makes this more
  concrete - the shift to a land-based economy"
- Week 6: [voice note] "Wait, the Viking trade routes partially
  restore Mediterranean connectivity. Does that weaken Pirenne?"

NEXT ENGAGEMENT PROMPT (system-generated):
"You're currently reading about Byzantine trade networks. How does
the persistence of Eastern Mediterranean commerce affect Pirenne's
argument about the Islamic disruption of trade?"
```

### 7.3 Key Differences

| Dimension | Flashcard | Concept Card |
|-----------|-----------|--------------|
| **Unit** | Single fact | Framework / interpretive lens |
| **Content** | Fixed Q&A pair | Evolving user-authored understanding |
| **Engagement** | Recall (binary: remembered/forgot) | Reflection, connection, application |
| **Growth** | None (same card forever) | Accumulates connections, notes, context |
| **Prompt type** | "What is X?" | "How does X relate to what you're reading now?" |
| **User voice** | None | Central -- notes, voice memos, evolving summaries |
| **Success metric** | Recall accuracy | Richness of connections, depth of explanation |
| **Scheduling** | Based on recall probability | Based on relevance to current reading + time since last engagement |

### 7.4 A Spectrum of Engagement Tasks

The concept card can present different types of tasks based on maturity and context:

**Early stage** (first encounters):
- "Summarize this idea in your own words"
- "What surprised you about this?"
- "What questions does this raise?"

**Developing stage** (multiple encounters):
- "How does this connect to [related concept you've engaged with]?"
- "Has your understanding changed since you last thought about this?"
- "Can you think of an example or counter-example?"

**Mature stage** (well-developed understanding):
- "You're reading about [new topic]. Does [this framework] apply?"
- "How would you explain this to someone unfamiliar with the field?"
- "What are the strongest objections to this idea?"

**Cross-pollination** (connecting across domains):
- "This concept from history resembles [concept from another domain]. What's the structural similarity?"
- "Can you use this framework to analyze [something from current reading]?"

---

## 8. Design Principles for Petrarca

### 8.1 Schedule Re-engagement with IDEAS, Not Facts

The fundamental scheduling unit should be a **concept/framework**, not a highlight or fact. The system maintains a priority queue of concepts the user is developing understanding of, and schedules re-engagement based on:

- Time since last engagement (basic spacing)
- Relevance to current reading (Matuschak's salience principle)
- Maturity of understanding (less developed concepts need more frequent engagement)
- User-expressed interest level
- Availability of new connections (the system has found new material related to this concept)

### 8.2 Prompt Reflection, Not Recall

Every re-engagement should involve a **generative task**, not a recognition/recall task. Drawing on elaborative interrogation and self-explanation research:

- "Explain in your own words..." (self-explanation)
- "Why do you think...?" (elaborative interrogation)
- "How does this connect to...?" (connection-making)
- "What has changed in your understanding since...?" (metacognitive reflection)
- "Record a voice note about what you think now..." (generation effect)

Voice notes are ideal for this: they lower the friction of generating explanations and capture the user's evolving thinking.

### 8.3 Make User Notes Central to the Review Cycle

Following Matuschak's "developing inklings" pattern:

- User annotations (text and voice) re-enter the review queue
- Earlier notes are presented alongside current reading for comparison
- The system tracks how the user's language about a concept changes over time
- Notes from different sources on related topics are presented together

This creates a **personal intellectual history** for each concept -- the user can see their own understanding developing.

### 8.4 Connect Across Sources

Following Matuschak's concept-oriented organization principle: knowledge should be organized by concept, not by source. When the user engages with the Pirenne thesis, they should see:

- Their highlights from the original Pirenne reading
- Their highlights from related readings (medieval trade, Carolingian economics)
- Their own notes and voice recordings
- System-identified connections to current reading

This cross-source synthesis is where Petrarca goes beyond Readwise (which resurfaces highlights from individual sources).

### 8.5 Track Understanding, Not Recall

The system needs a model of the user's understanding of each concept, not just whether they remember a fact. Possible signals:

- **Richness of explanation**: Are the user's voice notes about this concept getting more detailed and nuanced?
- **Connection density**: How many other concepts has the user connected this to?
- **Application frequency**: Has the user applied this framework to new material?
- **Question evolution**: Have the user's questions about this concept become more sophisticated?
- **Confidence self-report**: Simple "how well do I understand this?" rating

This is qualitatively different from FSRS-style recall tracking. It is closer to the "open learner modeling" literature identified in the incremental-reading research.

### 8.6 Leverage the Interleaving Effect

Drawing on Bjork's research: interleave concepts during review sessions. Don't present all medieval history concepts together -- mix them with concepts from technology reading, cultural theory, etc. This forces the user to switch contexts, which is harder in the moment but produces better long-term learning and transfer.

### 8.7 Support the Novice-to-Expert Transition

The system should help the user develop **expert-style knowledge organization**:

- Early on, the user may capture many isolated facts about medieval history
- Over time, the system should help these facts cluster around frameworks (the Pirenne thesis, feudalism as a system, the Annales school methodology)
- Concept cards should gradually become "higher-level API notes" (Matuschak's term) that organize many lower-level observations
- The system could prompt: "You have 12 notes about medieval trade. Can you identify a framework that organizes them?"

### 8.8 Make It Feel Like Continuing a Conversation

The re-engagement experience should feel like **picking up a conversation where you left off**, not like taking a test. Design cues:

- Show the user's most recent note on this concept as the entry point
- Present new related material the system has found
- Ask an open-ended question, not a closed recall question
- Allow the user to respond with voice, text, or simply "not now"
- Track time spent engaging (not accuracy of recall) as the primary metric

---

## 9. Open Questions

### 9.1 Scheduling Algorithm

Standard SRS algorithms (SM-2, FSRS) are designed for binary recall outcomes. What algorithm works for concept-level engagement where:
- There is no "correct answer" to check against
- The goal is deepening understanding, not maintaining recall
- Engagement quality varies (quick dismissal vs. 5-minute voice note)
- Relevance to current reading matters as much as time-since-review

Possible approach: a hybrid of time-based spacing (basic expanding intervals) and relevance-based surfacing (boost priority when current reading connects to this concept). User feedback (fruitful/unfruitful, as in Matuschak's inkling system) modulates intervals.

### 9.2 Cold Start Problem

How does the system identify concepts worth tracking before the user has built up a reading history? Options:
- Let the user explicitly flag "this is a framework I want to develop" (high friction but high signal)
- Use LLM analysis to identify frameworks and arguments in articles (automatic but potentially noisy)
- Start with simple highlight resurfacing (Readwise-style) and gradually upgrade to concept-level engagement as the user builds connections

### 9.3 When Does a Concept Card "Graduate"?

In traditional SRS, a card is never truly done. For concept cards, there should be a sense of maturity:
- The user feels confident explaining the concept and its connections
- The framework has been applied to multiple contexts
- New reading no longer significantly changes the user's understanding

Graduated concepts could move to a "reference" state -- available for cross-referencing but no longer actively scheduled. They re-activate if the system detects relevant new material.

### 9.4 Balancing Active and Passive Engagement

Not every re-engagement needs to be effortful. Sometimes a brief reminder is enough to maintain salience. The system needs multiple engagement modes:
- **Passive**: Brief reminder ("You've been thinking about the Pirenne thesis. Here's a related article you saved.")
- **Light active**: Rate your current understanding, or answer a quick connection question
- **Deep active**: Record a voice note explaining your current understanding, or write a synthesis

### 9.5 Role of AI in Prompt Generation

AI (LLM) could play a powerful role in generating contextual prompts:
- Identify when current reading connects to previously engaged concepts
- Generate novel application questions based on the user's reading history
- Detect when the user's understanding seems to have gaps (based on their notes)
- Suggest connections the user hasn't made

But there is a risk: if the AI does the thinking, the user doesn't get the generation effect. The AI should prompt thinking, not replace it.

### 9.6 Voice Notes as First-Class Objects

The user-requirements interviews emphasize voice notes heavily. Research questions:
- How should voice notes be indexed and made searchable? (Transcription + semantic search?)
- Should the system play back earlier voice notes during review, or present transcriptions?
- Can the system detect evolution in the user's thinking by comparing voice notes over time?
- How do voice notes interact with text highlights from reading?

---

## 10. Sources

### Andy Matuschak -- Primary

- [Spaced repetition systems can be used to program attention](https://notes.andymatuschak.org/Spaced_repetition_systems_can_be_used_to_program_attention)
- [Spaced everything](https://notes.andymatuschak.org/z9hscgkG2TeqgUtu3vAEW3U)
- [Spaced repetition memory systems can be used to prompt application, synthesis, and creation](https://notes.andymatuschak.org/Spaced_repetition_memory_systems_can_be_used_to_prompt_application,_synthesis,_and_creation)
- [Spaced repetition memory systems can be used to develop conceptual understanding](https://notes.andymatuschak.org/z9Vi7YVx7NzxU2wawNgsJbk)
- [Spaced repetition may be a helpful tool to incrementally develop inklings](https://notes.andymatuschak.org/Spaced_repetition_may_be_a_helpful_tool_to_incrementally_develop_inklings)
- [Salience prompts](https://notes.andymatuschak.org/zF8pCkzLVarNsaFyBxF9Aib)
- [Evergreen note maintenance approximates spaced repetition](https://notes.andymatuschak.org/Evergreen_note_maintenance_approximates_spaced_repetition)
- [How to write good prompts](https://andymatuschak.org/prompts/)
- [Why books don't work](https://andymatuschak.org/books/)
- [Implicit practice: a sight reading parable](https://andymatuschak.org/sight-reading/)
- [How Might We Learn?](https://andymatuschak.org/hmwl/)

### Matuschak & Nielsen -- Joint Work

- [How can we develop transformative tools for thought?](https://numinous.productions/ttft/)
- [Timeful Texts](https://numinous.productions/timeful/)
- [Quantum Country](https://quantum.country/)
- [Orbit](https://withorbit.com/) / [GitHub](https://github.com/andymatuschak/orbit)

### Matuschak -- Talks & Updates

- [Dwarkesh Podcast: Self-Teaching, Spaced Repetition, & Why Books Don't Work](https://www.dwarkesh.com/p/andy-matuschak)
- [Cultivating depth and stillness in research](https://andymatuschak.org/stillness/)
- [Towards impact through intimacy in my memory system research](https://andymatuschak.org/impact-through-intimacy/)
- [Exorcising us of the Primer](https://andymatuschak.org/primer/)

### Rob Haisfield & Scaling Synthesis

- [Scaling Synthesis](https://scalingsynthesis.com/)
- [Rob's Hypertext Notebook](https://robhaisfield.com/about)
- [Voiceliner](https://scalingsynthesis.com/voiceliner/) / [App](https://a9.io/voiceliner/)
- [ClearerThinking Podcast: User Engagement and Expert Intuition](https://podcast.clearerthinking.org/episode/049/rob-haisfield-user-engagement-and-expert-intuition)
- [Futurati Podcast: Scaling Synthesis and Tools for Thought](https://futuratipodcast.com/scaling-synthesis-and-tools-for-thought/)

### SuperMemo / Wozniak

- [Incremental reading - supermemo.guru](https://supermemo.guru/wiki/Incremental_reading)
- [History of incremental reading](https://supermemo.guru/wiki/History_of_incremental_reading)
- [Inevitability of incremental reading](https://supermemo.guru/wiki/Inevitability_of_incremental_reading)

### Readwise

- [Readwise](https://readwise.io/)
- [Adding Intention to Spaced Repetition](https://blog.readwise.io/adding-intention-to-spaced-repetition/)
- [Readwise Reader](https://readwise.io/read)

### Academic / Learning Science

- Bjork, E.L. & Bjork, R.A. (2011). [Creating Desirable Difficulties to Enhance Learning](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf)
- Dunlosky, J. et al. (2013). [Improving Students' Learning With Effective Learning Techniques](https://www.whz.de/fileadmin/lehre/hochschuldidaktik/docs/dunloskiimprovingstudentlearning.pdf). Psychological Science in the Public Interest, 14(1), 4-58.
- Chi, M.T.H., Feltovich, P.J., & Glaser, R. (1981). Categorization and Representation of Physics Problems by Experts and Novices. Cognitive Science, 5(2), 121-152.
- Gobet, F. (2005). [Chunking models of expertise](https://onlinelibrary.wiley.com/doi/abs/10.1002/acp.1110). Applied Cognitive Psychology, 19(2), 183-204.
- Scardamalia, M. & Bereiter, C. (2014). [Knowledge Building and Knowledge Creation](https://ikit.org/fulltext/2014-KBandKC-Published.pdf).
- Butler, A.C. (2010). Repeated testing produces superior transfer of learning. Journal of Experimental Psychology: Learning, Memory, and Cognition, 36(5), 1118-1133.
- Karpicke, J.D. & Blunt, J.R. (2011). Retrieval Practice Produces More Learning than Elaborative Studying. Science, 331(6018), 772-775.
- Callender, A.A. & McDaniel, M.A. (2009). [The limited benefits of rereading educational texts](https://www.sciencedirect.com/science/article/abs/pii/S0361476X08000477). Contemporary Educational Psychology, 34(1), 30-41.

### Related Tools

- [Building intuition with spaced repetition systems](https://jacobgw.com/blog/tft/2024/05/12/srs-intuit.html) (Jacob GW)
- [Building intuition with SRS - LessWrong](https://www.lesswrong.com/posts/gwavKiKXf97NLNC2n/building-intuition-with-spaced-repetition-systems)
- [Nielsen (2018). Augmenting Long-term Memory](https://augmentingcognition.com/ltm.html)
- [Nielsen (2016). Thought as a Technology](https://cognitivemedium.com/tat/)

### Existing Otak Research

- `/Users/stian/src/otak/research/deep-research-2026-02-23/deep_matuschak.md` -- Comprehensive Matuschak research with design implications (written for Otak but highly relevant)
