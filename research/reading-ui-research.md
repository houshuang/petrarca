# Reading UI Research: Novel and Experimental Interfaces for Mobile Reading, Triage, and Knowledge Modeling

*Deep research conducted 2026-03-02 for Petrarca read-later app*

---

## Table of Contents

1. [Overview and Design Context](#1-overview-and-design-context)
2. [CHI/HCI Research on Mobile Reading](#2-chihci-research-on-mobile-reading)
3. [Speed Reading Interfaces (RSVP, Spritz, Bionic Reading)](#3-speed-reading-interfaces)
4. [Novel Reading UI Prototypes](#4-novel-reading-ui-prototypes)
5. [Information Foraging and Sensemaking](#5-information-foraging-and-sensemaking)
6. [Progressive Summarization and Multi-Level Content](#6-progressive-summarization-and-multi-level-content)
7. [Existing App UIs Worth Studying](#7-existing-app-uis-worth-studying)
8. [Signal-Giving Interactions](#8-signal-giving-interactions)
9. [Time-Aware Reading](#9-time-aware-reading)
10. [Gesture and Annotation UX on Mobile](#10-gesture-and-annotation-ux-on-mobile)
11. [Knowledge Modeling While Reading](#11-knowledge-modeling-while-reading)
12. [Synthesis: Design Principles for Petrarca](#12-synthesis-design-principles-for-petrarca)

---

## 1. Overview and Design Context

Petrarca combines incremental reading with knowledge modeling. Users need to:
- **Quickly triage** many articles (e.g., 20 Claude Code articles from Twitter)
- **Go as deep as time allows** (30 seconds or 30 minutes)
- **Give rich signals** about what they know vs. want to learn
- **Not lose their place** across micro-reading sessions

This creates a unique design challenge at the intersection of read-later apps, spaced repetition systems, and sensemaking tools. No existing product fully addresses this combination.

---

## 2. CHI/HCI Research on Mobile Reading

### 2.1 Scrolling vs. Paging

A study on screen size and text movement found that students obtained **better integrated understanding when paging than when scrolling**, and those who paged displayed more strategic backtracking. This suggests that Petrarca should consider card/page-based navigation over infinite scroll for deeper reading modes.

- Source: [Is it the size, the movement, or both? (Springer, 2022)](https://link.springer.com/article/10.1007/s11145-022-10328-9)

### 2.2 Reading Comprehension and Interaction Modes

Different reading interaction modes lead to significant differences in cognitive load and system usability. The combination of reading interaction mode and annotation position significantly influences reading comprehension, vocabulary learning, and system usability.

- Source: [CHI 2022 - Helping Mobile Learners Know Unknown Words](https://dl.acm.org/doi/10.1145/3491101.3519620)

### 2.3 Content-Aware Scrolling

Content-aware scrolling (CAS) allows users to traverse documents based on the **flow of content** rather than pages. This means scrolling snaps to semantic boundaries (paragraphs, sections, key claims) rather than arbitrary pixel positions.

- Source: [Content-Aware Scrolling, Ishak & Feiner](http://www.cs.columbia.edu/~ishak/projects/CAS/tn123-ishak.pdf)

### 2.4 Structure-Aware Touch Scrolling (SATS)

SATS extends content-aware scrolling to touch interfaces, using document structure (headings, sections) to create "magnetic" scroll positions that naturally snap to meaningful boundaries.

- Source: [SATS: Structure-aware touch-based scrolling (ResearchGate)](https://www.researchgate.net/publication/311421067_SATS_Structure-aware_touch-based_scrolling)

**Takeaway for Petrarca:** Scrolling should be structure-aware. When a user flicks through content, the view should snap to paragraph or section boundaries. This is especially important for the "30-second triage" use case where the user needs to quickly assess article structure.

---

## 3. Speed Reading Interfaces

### 3.1 RSVP (Rapid Serial Visual Presentation)

RSVP presents words one at a time at a fixed position on screen, eliminating eye movement. Research shows:

- For **short texts**, RSVP increased reading speed by **33%** with no significant comprehension loss
- For **long texts**, no speed improvement was found, and RSVP significantly **increased task load**
- Comprehension drops rapidly beyond **500 wpm**, especially for texts longer than single sentences
- Individual calibration is important: a CHI 2020 paper used EEG to determine how processing varies with RSVP parameters

Sources:
- [One does not Simply RSVP (CHI 2020)](https://dl.acm.org/doi/10.1145/3313831.3376766)
- [Towards Improved Readability on Mobile Devices (Springer)](https://link.springer.com/chapter/10.1007/3-540-45756-9_18)
- [Sonified RSVP on Mobile (Springer)](https://link.springer.com/chapter/10.1007/3-540-36572-9_39)

### 3.2 Spritz and Bionic Reading

**Spritz** displays individual words using the "Optimal Recognition Point" (ORP) in a "Redicle" display. It claims speeds up to 1,000 wpm, but research is skeptical:

- Comprehension fell rapidly beyond 500 wpm for longer texts
- Works best for social media-length content, not deep reading

**Bionic Reading** bolds the first half of every word to guide fixation. A 2024 study in Acta Psychologica found it **does not facilitate reading** and in fact led to costs relative to regular unbolded reading.

Sources:
- [No, Bionic Reading does not work (ScienceDirect, 2024)](https://www.sciencedirect.com/science/article/pii/S0001691824001811)
- [Spritz research report (UCSB)](https://raley.english.ucsb.edu/wp-content/uploads/Student-work/Spritz.pdf)
- [Spritz and speed reading apps: pros and cons (The Conversation)](https://theconversation.com/spritz-and-other-speed-reading-apps-prose-and-cons-24467)

**Takeaway for Petrarca:** RSVP could be useful for short summaries and key claims (the 30-second mode), but not for deep reading. Speed reading features should be optional and positioned as "quick preview" tools, not primary reading modes. Avoid Bionic Reading -- the evidence is against it.

---

## 4. Novel Reading UI Prototypes

### 4.1 Fisheye Views for Text

Fisheye interfaces provide both local detail and global context. Research on mobile devices found:

- Users completed web navigation tasks **significantly faster** with fisheye views compared to panning
- Fisheye users spent more time gaining **overview** and less time on details
- Both fisheye and overview+detail interfaces were **faster than linear interfaces**

**DateLens** (Bederson et al., Microsoft Research) applied fisheye to calendars on PDAs. It showed 3 months of data with focus+context distortion, where tapping a day expanded it while neighboring days contracted. Non-PDA users performed complex tasks significantly faster with DateLens than with standard calendars.

Sources:
- [Fisheye Interfaces -- Research Problems (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-19641-6_6)
- [Interacting with Big Interfaces on Small Screens (ResearchGate)](https://www.researchgate.net/publication/221474859_Interacting_with_Big_Interfaces_on_Small_Screens_a_Comparison_of_Fisheye_Zoom_and_Panning_Techniques)
- [DateLens (ACM TOCHI)](https://dl.acm.org/doi/10.1145/972648.972652)

**Takeaway for Petrarca:** A fisheye view of article text could be powerful: the user sees the full article structure compressed, with the section they are reading expanded. This directly supports the "go as deep as time allows" requirement -- you always see where you are in the whole.

### 4.2 Zoomable Text / Semantic Zoom

Semantic zooming changes object appearance based on zoom level. For text:
- Zoomed out: only titles visible
- Slightly zoomed: short summary or outline appears
- More zoomed: key claims / highlighted sentences
- Fully zoomed: complete text

This is the canonical **overview+detail** pattern applied to reading.

Sources:
- [Cockburn, Karlson, Bederson: Review of Overview+Detail, Zooming, and Focus+Context (ACM Computing Surveys, 2008)](https://dl.acm.org/doi/10.1145/1456650.1456652)
- [Supporting Early Document Navigation with Semantic Zooming (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-13654-2_21)

**Takeaway for Petrarca:** Semantic zoom is perhaps the single most promising UI pattern for Petrarca. A pinch-to-zoom gesture could smoothly transition between: article title + metadata -> AI summary + key claims -> highlighted full text -> full text. This maps directly to Tiago Forte's progressive summarization layers and to the user's variable time budget.

### 4.3 Space-Filling Thumbnails (SFT)

SFT shows all pages as miniatures in a space-filling matrix with no scrolling. The page under the cursor is magnified. Tested at CHI 2006, SFT was **significantly faster** than scrolling methods for visual search tasks and was strongly preferred by participants.

- Source: [Faster Document Navigation with Space-Filling Thumbnails (CHI 2006)](https://dl.acm.org/doi/abs/10.1145/1124772.1124774)

**Takeaway for Petrarca:** For triage, showing all saved articles as a grid of compressed thumbnails (showing title + key image + topic color) could enable rapid visual scanning without scrolling through a list.

### 4.4 Overview Scrollbar / Minimap

Overview scrollbars display an overview of the entire document, using different compression methods. They are more usable than traditional scrollbars when searching for recognizable targets.

**Fishnet** added search term highlighting with "popouts" -- terms are made readable even at thumbnail scale, allowing visual scanning of results within the entire page without scrolling.

Sources:
- [Overview Scrollbar (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-40498-6_51)
- [Fishnet (ACM AVI)](https://dl.acm.org/doi/10.1145/989863.989883)

### 4.5 Scim: Faceted Highlights for Paper Skimming

Scim (Allen AI / Semantic Scholar) is an augmented reading interface that highlights passages with distinct colors for four facets: **Objective, Novelty, Method, and Result**. Key findings:

- Reduced time to complete short information-seeking tasks
- Readers believed it helped develop high-level understanding
- Helped determine which passages to skim or skip
- Scaled to 521,000+ papers via the Semantic Reader

Sources:
- [Scim: Intelligent Faceted Highlights (CHI 2023 demo)](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)
- [Accelerating Scientific Paper Skimming (ACM TIIS, 2024)](https://dl.acm.org/doi/10.1145/3665648)

**Takeaway for Petrarca:** Faceted highlighting is directly applicable. Instead of Objective/Novelty/Method/Result, Petrarca could highlight: **Key Claim, Supporting Evidence, New-to-User Concept, Already-Known Concept**. The color coding helps users rapidly assess an article's value relative to their existing knowledge.

### 4.6 The Semantic Reader Project

The Allen AI Semantic Reader Project explores augmented reading interfaces for research papers. Key features:
- **Citation augmentation**: citations visually augmented based on connections to user's library
- **Inline citation cards**: hover over a citation to see TLDR summary
- **AI-generated highlights**: Goal, Method, Result labels
- **Skimming support**: highlights capture key points
- Evaluated with **300+ participants**, showing improved reading experiences

Source: [The Semantic Reader Project (arXiv, 2023)](https://arxiv.org/abs/2303.14334)

### 4.7 Paper Forager

Paper Forager provides a visually-based browsing experience for large collections of research documents (tested with 5,055 CHI/UIST papers). It uses multi-resolution images, giving users immediate access from overview to individual pages. Key design: **reducing the transaction cost between finding, scanning, and reading**.

- Source: [Paper Forager (Graphics Interface 2021)](https://graphicsinterface.org/proceedings/gi2021/gi2021-27/)

### 4.8 Treemap Visualization for Document Collections

Treemaps display hierarchical data as nested rectangles whose areas correspond to quantitative attributes. For article collections:
- Tile area can encode topic importance
- Nested word clouds show topic details
- Term size and color reflect representativeness
- **StoryGem** (2025) combines word clouds with Voronoi treemaps for semantics-preserving text visualization

Sources:
- [Treemapping (Wikipedia)](https://en.wikipedia.org/wiki/Treemapping)
- [StoryGem (arXiv, 2025)](https://arxiv.org/html/2506.18793)

**Takeaway for Petrarca:** A treemap view of your reading queue could encode: tile size = article length, color = topic, fill pattern = reading progress. This gives an instant overview of what you have saved and what areas are over/under-represented.

---

## 5. Information Foraging and Sensemaking

### 5.1 Pirolli & Card's Information Foraging Theory (1999)

Core concepts directly applicable to Petrarca:

- **Information Scent**: Users judge sources by how likely they seem to contain what is needed. Reading queue items must emit strong "scent" -- title, summary, topic tags, relevance signals.
- **Information Patches**: Related information clusters. Articles on similar topics should be visually grouped.
- **Information Diet**: Users optimize gain per unit effort. The UI must minimize the cost of assessing whether an article is worth reading.

Source: [Information Foraging Theory (IxDF)](https://www.interaction-design.org/literature/book/the-glossary-of-human-computer-interaction/information-foraging-theory)

### 5.2 Pirolli & Card's Sensemaking Model (2005)

The model defines two loops:

**Foraging Loop** (finding and filtering):
1. External data sources
2. Search and filter
3. Shoebox (raw collection of possibly relevant items)
4. Read and extract
5. Evidence file (key extracted snippets)

**Sensemaking Loop** (building understanding):
6. Schema (organizing evidence into structures -- timelines, concept maps, etc.)
7. Hypothesis (tentative theories built from schemas)
8. Presentation (communicable output)

Both loops operate **bottom-up** (data to theory) and **top-down** (theory to data) in an opportunistic mix.

**Key leverage points for technology:**
- Reduce cost of scanning, assessing, and selecting items for further attention
- Use "pre-attentive codings" (highlighting, color) to surface important information
- Support "re-representing documents" via summaries
- Help externalize the sensemaking process

Sources:
- [The Sensemaking Process and Leverage Points (Pirolli & Card, 2005)](https://www.researchgate.net/publication/215439203_The_sensemaking_process_and_leverage_points_for_analyst_technology_as_identified_through_cognitive_task_analysis)
- [Information Foraging (NNGroup)](https://www.nngroup.com/articles/information-foraging/)

**Takeaway for Petrarca:** The app is fundamentally a sensemaking tool. The reading queue is the "shoebox." Highlights and extracts form the "evidence file." Tags and knowledge graph connections form the "schema." Petrarca should make these transitions fluid: from triage (foraging) to reading (extracting) to connecting (sensemaking), all in one mobile-native interface.

### 5.3 Jigsaw: Visual Analytics for Document Sensemaking

Jigsaw (Georgia Tech) supports investigative analysis through multiple coordinated views:
- **Document View**: shows one-sentence summaries above full text for triage
- **Graph View**: entities and their connections across documents
- **Document Cluster View**: spatial grouping by similarity
- **List View**: filterable entity lists

Key insight: Jigsaw **visually illustrates connections between entities across different documents**, letting analysts see patterns they would miss reading sequentially.

Sources:
- [Jigsaw (Information Visualization, 2008)](https://dl.acm.org/doi/10.1145/1466620.1466622)
- [Jigsaw evaluation (IEEE TVCG)](https://faculty.cc.gatech.edu/~stasko/papers/tvcg11-eval.pdf)

### 5.4 Entity Workspace

Entity Workspace supports collaboration through entity-centric exploration, acting as an "evidence file that aids memory, inference, and reading." It lets analysts find documents, organize information, and compare hypotheses.

- Source: [Entity-based collaboration tools for intelligence analysis (ResearchGate)](https://www.researchgate.net/publication/220726938_Entity-based_collaboration_tools_for_intelligence_analysis)

### 5.5 Steering LLM Summarization with Visual Workspaces (2024)

Recent work proposes an intermediate step: a **schematic visual workspace for human sensemaking** before LLM generation. Users create spatial layouts, and the LLM uses these workspaces to produce better-aligned summaries.

- Source: [Steering LLM Summarization (arXiv, 2024)](https://arxiv.org/abs/2409.17289)

**Takeaway for Petrarca:** The knowledge modeling component should directly inform AI features. When a user has built up a knowledge graph around topic X, the AI should use that schema to generate better summaries, highlight what is new vs. known, and suggest connections.

---

## 6. Progressive Summarization and Multi-Level Content

### 6.1 Tiago Forte's Progressive Summarization

Five layers of distillation:
- **Layer 0**: Original full-length source text
- **Layer 1**: Initial capture -- anything insightful, interesting, or useful
- **Layer 2**: Bold formatting on key phrases and essential ideas
- **Layer 3**: Highlighting to isolate "the best of the best"
- **Layer 4**: Executive summary in your own words
- **Layer 5**: Creative remix into new output

Key principle: "You cannot compress something without losing some of its context." The system preserves all layers so you can always zoom back out.

Source: [Progressive Summarization (Forte Labs)](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)

### 6.2 Mapping to a Reading Interface

For Petrarca, progressive summarization maps to UI zoom levels:

| Zoom Level | Content Shown | Time to Consume | User Action |
|---|---|---|---|
| 0 (Title) | Title + source + topic tag | 2 seconds | Swipe to triage |
| 1 (Summary) | AI-generated 2-3 sentence summary | 10 seconds | Tap to expand |
| 2 (Key Claims) | 5-10 extracted claims with highlights | 1-2 minutes | Tap claim to expand |
| 3 (Annotated) | Full text with AI/user highlights | 5-20 minutes | Read, annotate |
| 4 (Full) | Complete original text | Variable | Deep reading |

### 6.3 Focus+Context Techniques for Text

The seminal review by Cockburn, Karlson, and Bederson (2008) categorizes four approaches:
1. **Overview+detail**: Spatial separation (e.g., minimap alongside reading pane)
2. **Zooming**: Temporal separation (e.g., pinch to zoom between levels)
3. **Focus+context**: Minimize seam (e.g., fisheye text where focused paragraph is expanded)
4. **Cue-based**: Selective highlighting (e.g., color coding key sentences)

Source: [A Review of Overview+Detail, Zooming, and Focus+Context Interfaces (ACM Computing Surveys, 2008)](https://dl.acm.org/doi/10.1145/1456650.1456652)

### 6.4 Progressive Disclosure on Mobile

Key principles for mobile progressive disclosure:
- Save space by initially hiding non-essential content
- Present most important information upfront
- Let users access details on demand
- Limit nesting levels to avoid "lost in hierarchy" confusion
- Use clear expand/collapse affordances

Source: [Progressive Disclosure in UX (LogRocket)](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)

**Takeaway for Petrarca:** Combine semantic zoom with progressive summarization layers. The default view should be Layer 1 (AI summary), with smooth transitions to deeper layers. Each layer should be independently scrollable and navigable. The user should always be able to see "how deep they are" relative to the full article.

---

## 7. Existing App UIs Worth Studying

### 7.1 Readwise Reader

The most sophisticated read-later app as of 2025-2026. Key design decisions:

**Triage System:**
- Documents flow through: **Inbox -> Later -> Shortlist -> Archive**
- Inspired by Superhuman's game-like email triage
- Feed section with **Unseen/Seen** states for low-signal content (RSS, newsletters)

**Reading Experience:**
- Cross-platform (web, iOS, Android) with continuous sync
- **Double-tap-to-paragraph highlighting** on mobile -- "the 80/20 of highlights"
- Margin notes inspired by traditional marginalia
- **TikTok-inspired swipe** for Feed consumption
- Keyboard-first on web (read, navigate, highlight, tag without mouse)

**AI Integration (Ghostreader):**
- Context-aware AI assistant in sidebar
- Select text and "Chat about this"
- Contextual definitions, translations, summaries
- Custom prompt templates

**Content Handling:**
- Unified reader for articles, PDFs, EPUBs, newsletters, YouTube (with transcripts), Twitter threads
- Full-text search across all saved content
- Text-to-speech with natural voices

Sources:
- [The Next Chapter of Reader (Readwise Blog)](https://blog.readwise.io/the-next-chapter-of-reader-public-beta/)
- [Designing Readwise's read-it-later app (Lazer Technologies)](https://www.lazertechnologies.com/case-studies/readwise)

**What Petrarca can learn:** Double-tap paragraph highlighting is brilliant for mobile. The Inbox/Later/Archive triage is proven. But Readwise Reader lacks knowledge modeling -- it is about capturing, not connecting. Petrarca's differentiation is helping users build understanding, not just collect highlights.

### 7.2 Superhuman (Email Triage as Paradigm)

Superhuman's design principles are directly transferable to reading triage:

**Speed as Product:**
- Internal target: **50-60ms** for all interactions (public claim: 100ms)
- Optimistic UI: actions complete visually before server confirmation
- Undo (Z key) as safety net instead of confirmation dialogs

**Keyboard-First with Vim Navigation:**
- J/K for up/down, H/L for left/right
- E = archive, R = reply, C = compose
- Cmd+K = command palette
- One-key actions reduce common tasks to single keystrokes

**Game-Like Triage:**
- Each email requires a decision: star, snooze, archive, delegate
- Video games are built on triage mechanics
- Split Inbox (3-7 categories) reduces cognitive load
- Users report processing **150% faster** than Gmail

**Onboarding as Muscle Memory Training:**
- 30-minute 1:1 sessions drilling keyboard shortcuts on synthetic data
- Practice first, real data second
- 20% increase in shortcut usage, 67% increase in feature adoption

Source: [Superhuman: Speed as the Product (Blake Crosley)](https://blakecrosley.com/en/guides/design/superhuman)

**What Petrarca can learn:** The triage queue should feel like a game. Each article demands a decision. Speed must be perceptible -- sub-100ms response for all triage actions. Consider a "command palette" for power users. But on mobile, translate keyboard shortcuts into gestures.

### 7.3 Artifact (Defunct AI News App)

Built by Instagram co-founders (2023-2024). Key features:
- AI-powered recommendations that improved with use
- Clickbait headline rewriting via AI
- Article summarization
- Clean, modern, focused design

**Why it failed:** Loss of focus. It diluted its sharp AI news reading experience by adding Pinterest-like link posting, text posting (like Twitter), and place sharing. The lesson: **feature creep in reading apps is lethal**.

Sources:
- [Artifact shutdown (Medium)](https://medium.com/artifact-news/shutting-down-artifact-1e70de46d419)
- [Why Artifact Failed (TechCrunch)](https://techcrunch.com/2024/01/18/why-artifact-from-instagrams-founders-failed-shut-down/)

**What Petrarca can learn:** Stay focused on the core loop: triage -> read -> model knowledge. Do not add social features, posting features, or discovery features that dilute the core.

### 7.4 Matter

A clean, minimalist read-later app, favorite among Apple users:
- Beautiful native iOS design
- Card-based reading interface
- Text highlighting and audio narration
- Integrations with Notion and Readwise
- Follow individual writers

Source: [Matter on App Store](https://apps.apple.com/us/app/matter-reading-app/id1501592184)

### 7.5 Reeder (RSS Reader)

Key UX innovation in the 2024 redesign by Silvio Rizzi:
- **No unread counts** -- remembers and syncs scroll position instead
- Feels like scrolling a social media timeline, but with curated content
- Different viewers for different content types (articles, photos, videos, podcasts)
- Bionic reading mode (though evidence against its effectiveness)
- Widget support for iOS

Source: [The new Reeder app (TechCrunch)](https://techcrunch.com/2024/09/23/the-new-reeder-app-is-built-for-rss-youtube-reddit-mastodon-and-more/)

**What Petrarca can learn:** Removing unread counts and replacing with scroll position sync is psychologically healthier. Content-type-specific viewers are essential. The timeline/feed metaphor works for discovery; a separate mode is needed for deep reading.

### 7.6 Blinkist and Shortform

Two contrasting approaches to book summarization:

**Blinkist:** 15-minute "Blinks" -- extremely compressed, perfect for quick reads. Three tabs: Discover, Library, You. Audio + text switching.

**Shortform:** 45-minute detailed guides with exercises and references. Prioritizes depth and engagement.

Sources:
- [Blinkist vs Shortform comparison](https://entreresource.com/which-book-summary-app-wins-shortform-headway-or-blinkist/)
- [Blinkist vs Shortform (Blinkist)](https://www.blinkist.com/magazine/posts/blinkist-vs-shortform)

**What Petrarca can learn:** Both models exist because different users want different depths at different times. The same user wants Blinkist-depth during a 5-minute commute and Shortform-depth during a quiet evening. Petrarca should support both modes for the same content.

### 7.7 LiquidText

Annotation tool with spatial workspace, named most innovative iPad app by Apple in 2015:
- **Pinch-to-collapse**: Pinch a document to collapse pages between two sections, showing distant pages side by side
- **Infinite workspace**: Drag excerpts, group them, draw connections
- **Ink connections**: Draw lines between any elements -- notes, highlights, cross-document references
- Multi-document projects

Source: [LiquidText deeper dive](https://www.liquidtext.net/liquidtextadeeperdive)

**What Petrarca can learn:** The pinch-to-collapse gesture is remarkable for comparing distant parts of a text. The spatial workspace model is powerful for sensemaking but may be too complex for mobile-first. Consider a simplified version where users can spatially arrange extracted claims.

### 7.8 MarginNote

Combines reading with mind mapping and spaced repetition on iPad/iPhone:
- **Study Mode**: MindMap notebook associated with multiple documents
- Annotations automatically become mind map nodes
- **Concept diagrams**: Link cards with lines or gestures on infinite canvas
- **Outliner**: Edit and reorder text nodes in bulk
- Built-in spaced repetition flashcards
- 10 branch styles for mind maps

Source: [MarginNote features](https://www.marginnote.com/features)

**What Petrarca can learn:** MarginNote is the closest existing product to Petrarca's vision. The automatic connection between annotations and knowledge structure is key. However, MarginNote's UI is complex and overwhelming. Petrarca should aim for MarginNote's depth with Readwise Reader's polish.

### 7.9 Omnivore (Open Source, Now Self-Hosted)

Open-source read-later app (deprecated cloud in Nov 2024):
- Reader view strips ads and clutter
- Organization via tags, filters, rules, full-text search
- AI-powered text-to-speech
- Integration with Logseq, Obsidian, Notion
- Newsletter subscription via email aliases

Source: [Omnivore on GitHub](https://github.com/omnivore-app/omnivore)

---

## 8. Signal-Giving Interactions

### 8.1 The Signal Vocabulary Problem

Most reading apps offer only binary signals: save/unsave, like/dislike. Petrarca needs richer signals:

| Signal | Meaning | Gesture Candidate |
|---|---|---|
| "Already know this" | Not uninteresting, just familiar | Swipe down / two-finger tap |
| "New and interesting" | Priority for deeper reading | Swipe up / double-tap |
| "Save this part" | Extract to knowledge base | Long-press + drag |
| "Go deeper on this" | Find more on subtopic | Swipe right on a claim |
| "Not relevant" | Not in my area of interest | Swipe left |
| "Understood" | Mark section as comprehended | Tap checkmark |

### 8.2 Implicit Signals from Reading Behavior

Research shows behavioral signals can predict user interest:
- **Time spent reading**: good indicator but task-dependent; more useful for complex tasks
- **Scroll depth**: deeper scrolls correlate with engagement
- **Mouse/touch movement**: patterns differ for skimming vs. careful reading
- **Eye-tracking**: explains 49.93% of comprehensibility variance and 30.41% of interest variance (though eye-tracking isn't available on mobile)
- **Combining multiple signals** provides more accurate modeling than any single metric

Sources:
- [Revisiting Interest Indicators (arXiv, 2022)](https://arxiv.org/abs/2207.06837)
- [Reading Time, Scrolling and Interaction (ResearchGate)](https://www.researchgate.net/publication/221301285_Reading_Time_Scrolling_and_Interaction_Exploring_Implicit_Sources_of_User_Preferences_for_Relevant_Feedback)
- [Feedback beyond accuracy: eye-tracking for interest detection (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10084433/)
- [Segment-level display time as implicit feedback (ACM SIGIR)](https://dl.acm.org/doi/10.1145/1571941.1571955)

### 8.3 Intentional vs. Unintentional Implicit Feedback

Recent research (2025) challenges the binary explicit/implicit feedback categorization. Users **consciously employ** behaviors previously categorized as implicit:
- Clicking is sometimes deliberate feedback ("I want more like this"), sometimes navigation
- Scroll patterns can be intentional signals
- The system should distinguish between "the user read this section carefully" (intentional interest) and "the user scrolled past this" (possibly unintentional skip)

Source: [Beyond Explicit and Implicit (arXiv, 2025)](https://arxiv.org/html/2502.09869v1)

**Takeaway for Petrarca:** Combine explicit gestures with implicit tracking. Track which sections users spend time on, which claims they expand, which topics they follow. Use this to build a model of what they know and want to learn, but always let them override with explicit signals. Surface the model transparently: "We think you know about X -- is that right?"

### 8.4 Triage App Design Pattern (Triage Email App)

The Triage email app uses a "stack of cards" interface where you quickly archive, keep, or reply with a flick or tap. This binary (or ternary) forced-decision pattern is powerful for processing queues.

Source: [Triage app](https://triage.cc/)

---

## 9. Time-Aware Reading

### 9.1 Micro-Reading Research

A study on college students' micro-reading activities designed 6-week micro-reading experiments, finding that the type of micro-reading activity (short clips vs. full articles) significantly affects reading effectiveness. Short, focused activities were better for specific learning goals.

Source: [Micro-reading activities (Springer)](https://link.springer.com/article/10.1007/s10639-023-12138-0)

### 9.2 Time Pressure and Comprehension

Research on time pressure effects on reading:
- On screen: test scores were **lower under time pressure** vs. free regulation
- On paper: time pressure actually **improved study efficiency**
- The difference suggests digital reading interfaces should help users read more strategically, not just faster

Source: [Time Limitations Enhance Reading Comprehension (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0361476X98909924)

### 9.3 Designing for Variable Time Budgets

No single academic paper addresses "time-aware reading interfaces" directly, but we can synthesize from multiple sources:

**Proposed Time Modes for Petrarca:**

| Time Budget | Mode | What the User Sees |
|---|---|---|
| < 30 sec | **Triage** | Title + AI summary + topic tag. Swipe to decide. |
| 1-3 min | **Scan** | Key claims extracted, color-coded by facet. Tap to expand any claim. |
| 5-10 min | **Read** | Full text with AI highlights. Structure-aware scrolling. |
| 15-30 min | **Study** | Full text + annotation tools + knowledge graph connections. |
| 30+ min | **Deep** | Full text + linked sources + concept exploration + spaced repetition prompts. |

### 9.4 SuperMemo's Incremental Reading as a Scheduling Model

SuperMemo pioneered **incremental reading** -- reading thousands of articles in parallel using spaced repetition scheduling. Key concepts:

**The Knowledge Funnel:**
1. Web information -> personal selection
2. Selection -> key extracts
3. Extracts -> cloze deletions (active knowledge)
4. Active knowledge -> stabilized memory
5. Memory -> creative application

**Priority Queue:** Articles are scheduled based on:
- User-assigned priority
- Time since last review
- Spaced repetition algorithm (interval grows with successful recall)
- Amount of unprocessed material remaining

**Parallel Processing:** Users never "finish" an article in one sitting. They read a section, extract key points, and the system schedules the article for later. This prevents the "all or nothing" trap of traditional reading.

Sources:
- [Incremental reading (SuperMemo.guru)](https://supermemo.guru/wiki/Incremental_reading)
- [Incremental reading (SuperMemo Help)](https://help.supermemo.org/wiki/Incremental_reading)
- [SuperMemo's Incremental Reading Explained](https://www.masterhowtolearn.com/2019-08-06-supermemos-incremental-reading-explained/)

**Takeaway for Petrarca:** This is the core paradigm Petrarca should adopt, but with a modern mobile UX rather than SuperMemo's desktop-era interface. The spaced repetition algorithm should schedule both re-reading (of articles not yet fully processed) and review (of extracted knowledge). The priority queue should be transparent and user-adjustable.

### 9.5 FSRS (Free Spaced Repetition Scheduler)

The modern open-source FSRS algorithm improves on SM2 (Anki's algorithm):
- Targets a specific retention probability (default 90%)
- Users can balance retention vs. review load
- **20-30% fewer reviews** for same retention level
- Can be extended beyond flashcards to schedule article re-visits

Source: [FSRS on GitHub](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler)

### 9.6 Reading Position Restoration

For micro-reading sessions, saving and restoring exact position is critical:
- Store scroll position at paragraph level (not pixel level)
- Show visual indicator of where user left off
- Consider "previously read" dimming (like Kindle's furthest-read indicator)
- Progress bar showing % read and estimated remaining time

**Reeder's approach** (2024) is notable: instead of unread counts, it remembers and syncs scroll position, making the experience feel like resuming a social media timeline.

---

## 10. Gesture and Annotation UX on Mobile

### 10.1 Core Mobile Gestures for Reading

Standard gesture vocabulary from Material Design 3 and iOS HIG:

| Gesture | Standard Use | Reading App Adaptation |
|---|---|---|
| Tap | Activate, select | Expand section, open article |
| Double-tap | Select word, zoom | Highlight paragraph (Readwise pattern) |
| Long-press | Context menu, drag | Begin text selection, annotation menu |
| Swipe left/right | Navigate, dismiss | Triage decision, navigation |
| Swipe up/down | Scroll | Signal interest/familiarity |
| Pinch | Zoom | Semantic zoom between summary levels |
| Two-finger tap | Secondary action | Mark as "already known" |

Sources:
- [Material Design 3 Gestures](https://m3.material.io/foundations/interaction/gestures)
- [Guide to iOS and Android gestures (Medium)](https://medium.com/uxparadise/guide-to-app-interaction-and-gestures-for-ios-and-android-5567ad4be386)

### 10.2 Long-Press Design

Long-press is powerful but has discoverability problems:
- Typical threshold: 500ms to 2 seconds
- Should always provide haptic feedback at activation
- Best used for secondary/expert actions
- Combine with visual preview (e.g., peek-and-pop)

Source: [Mastering Long Press Gestures (NumberAnalytics)](https://www.numberanalytics.com/blog/ultimate-guide-long-press-gestures-interaction-design)

### 10.3 Haptic Feedback for Reading Micro-Interactions

Haptics "function like punctuation -- adding rhythm, reinforcing meaning, and guiding attention while keeping the interface clean." Applications for reading:
- Subtle vibration when bookmarking or saving
- Stronger haptic on triage decisions (confirmation)
- Gentle pulse when crossing section boundaries
- Haptics especially valuable during one-handed use, walking, commuting

Source: [Haptic Storytelling UX (Influencers Time)](https://www.influencers-time.com/haptic-storytelling-boosts-ux-and-conversion-in-mobile-apps/)

### 10.4 Readwise Reader's Mobile Annotation Pattern

Readwise Reader's **double-tap-to-paragraph** is the state of the art for mobile highlighting:
- One tap selects the whole paragraph (the most common highlight granularity)
- Avoids the fiddly text-selection handles
- For finer selection, long-press triggers standard text selection
- Tags can be added via swipe gesture on highlight

**Takeaway for Petrarca:** Adopt double-tap-to-paragraph as baseline. Extend with: triple-tap to highlight key claim within paragraph (AI-detected), long-press to enter precise selection mode. Add swipe-on-highlight gestures for adding to knowledge graph.

---

## 11. Knowledge Modeling While Reading

### 11.1 Andy Matuschak's Mnemonic Medium and Orbit

Matuschak and Nielsen developed the "mnemonic medium" -- embedding spaced repetition directly into narrative text. **Quantum Country** is the reference implementation.

Key design principles:
- Prompts are embedded contextually within the text, not created separately
- Spaced repetition gives structure to normally-atomized prompts
- The system programs attention: "Spaced repetition systems can be used to program attention"
- Orbit aspires to be an "OS-level" SRS where prompts are like files, readable across services

Sources:
- [Mnemonic medium (Matuschak notes)](https://notes.andymatuschak.org/Mnemonic_medium)
- [Orbit (GitHub)](https://github.com/andymatuschak/orbit)
- [Orbit (withorbit.com)](https://withorbit.com/)

**Takeaway for Petrarca:** Reading and knowledge retention should be a single activity, not separate tools. When a user encounters a key claim while reading, the interface should make it effortless to convert that claim into a reviewable knowledge item. The knowledge graph grows organically from reading activity.

### 11.2 Personal Knowledge Graphs

Personal knowledge graphs represent an individual's knowledge as nodes (concepts) and edges (relationships):
- Nodes: facts, ideas, terms with attributes (title, description, source)
- Edges: hierarchical, associative, causal, or other relationship types
- Should support free spatial positioning per user preference

Source: [Personal Knowledge Graphs (ACM SIGIR 2019)](https://dl.acm.org/doi/10.1145/3341981.3344241)

### 11.3 Concept Mapping While Reading

Research shows that reading annotations facilitate feedback during concept mapping. The process benefits from:
- Visual tools for organizing knowledge
- Spatial arrangement of information objects
- Free positioning according to user preference
- Bidirectional links between source text and concept map

Source: [Bridging reading and mapping (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0306437924001169)

### 11.4 Automated Knowledge Graph Extraction

Modern LLMs can extract knowledge graphs from text:
- Identify entities and relationships from unstructured text
- Build graph structures automatically
- Concepts mentioned in proximity are assumed related
- Can augment user-created knowledge with AI-detected connections

Sources:
- [KGGen: Extracting Knowledge Graphs (arXiv, 2025)](https://arxiv.org/html/2502.09956v1)
- [Convert any text to a knowledge graph (GitHub)](https://github.com/rahulnyk/knowledge_graph)

**Takeaway for Petrarca:** Use LLMs to pre-extract entities and potential connections from articles. Present these as suggestions in the UI ("This article mentions concepts X, Y, Z -- connect to your existing knowledge?"). Let users confirm, modify, or dismiss. Over time, the knowledge graph becomes a map of what the user knows and what they are learning.

---

## 12. Synthesis: Design Principles for Petrarca

### 12.1 Core Architecture: Three Modes

Based on this research, Petrarca should have three distinct but fluid modes:

**1. Triage Mode (Foraging Loop)**
- Card-based stack (Tinder/Superhuman pattern)
- Each card shows: title, source, AI summary (2-3 sentences), topic tags, estimated read time
- Swipe gestures for decisions: Keep / Later / Archive / Already Know
- Target: process one article per 3-5 seconds
- Space-filling thumbnail grid as alternative view

**2. Reading Mode (Extracting)**
- Semantic zoom: pinch between summary/claims/highlighted/full levels
- Structure-aware scrolling (snap to paragraphs/sections)
- Faceted highlights (Scim-style): Key Claim / New Concept / Supporting Evidence
- Double-tap paragraph highlighting
- Inline AI assistant (like Ghostreader)
- Implicit tracking: time per section, scroll behavior, expansion patterns

**3. Modeling Mode (Sensemaking Loop)**
- Knowledge graph visualization of extracted concepts
- Spatial workspace for arranging claims and connections
- Spaced repetition scheduling for review
- Visual overview of knowledge coverage (treemap of topics)
- "What's new for me" vs. "What I already know" distinction

### 12.2 Key Interaction Patterns

**Gesture Vocabulary:**
- Swipe left: dismiss/archive
- Swipe right: save/keep/go deeper
- Swipe up: "I know this" (familiarity signal)
- Swipe down: "This is new" (interest signal)
- Double-tap: highlight paragraph
- Long-press: precise selection + annotation menu
- Pinch: semantic zoom between content levels
- Two-finger swipe: navigate between articles in queue

**Speed Targets (following Superhuman):**
- All triage actions: < 100ms visual response
- Article loading: < 200ms to show summary, progressive loading of full text
- Semantic zoom transition: < 150ms animation
- Knowledge graph update: optimistic UI with background sync

### 12.3 The Progressive Depth Stack

The most novel UI concept for Petrarca, synthesized from this research:

```
Level 0: Title + Topic + Source (triage card)
   |
   v  [tap / expand]
Level 1: AI Summary (2-3 sentences)
   |
   v  [tap / expand]
Level 2: Key Claims (5-10 bullets, color-coded)
   |
   v  [tap any claim]
Level 3: Claim + Context (paragraph containing claim, with claim highlighted)
   |
   v  [scroll / expand]
Level 4: Full Article (with all highlights and annotations preserved)
```

At any level, the user can:
- Signal "I know this" or "This is new" on any claim
- Drag a claim to their knowledge graph
- Ask the AI to explain, expand, or find related content
- See how this connects to their existing knowledge

### 12.4 Time-Aware Scheduling

Combine SuperMemo's incremental reading with modern UX:

1. **Import articles** with automatic AI processing (summary, claim extraction, entity detection)
2. **Priority queue** considers: user-assigned importance, topic relevance to knowledge goals, time since last seen, amount of unprocessed content
3. **Session-aware presentation**: when user opens app, detect available time context (quick check vs. study session) and present appropriate mode
4. **Partial progress**: reading progress saved at claim level, not just scroll position. "You've processed 7 of 12 key claims in this article."
5. **Spaced review**: Extracted knowledge re-surfaced on FSRS schedule. Articles with unprocessed content re-surfaced with decreasing frequency.

### 12.5 The Knowledge Feedback Loop

The unique value proposition of Petrarca, not found in any existing app:

```
Read Article -> Extract Claims -> Claims enter Knowledge Graph
                                         |
                                         v
New Articles -> AI compares to Knowledge Graph -> Highlights "new to you" vs "already known"
                                         |
                                         v
                              Better Triage (skip familiar, prioritize novel)
                                         |
                                         v
                              Knowledge Graph grows -> Even better recommendations
```

This creates a virtuous cycle where the more you read, the better the app becomes at showing you what is genuinely new and worth your time.

### 12.6 Anti-Patterns to Avoid

Based on this research:

1. **Do not add social features** (Artifact's mistake)
2. **Do not force speed reading** (Bionic Reading/Spritz evidence is negative for comprehension)
3. **Do not show unread counts** (anxiety-inducing; follow Reeder's scroll-position model)
4. **Do not require complex onboarding** (but do train gestures through progressive disclosure)
5. **Do not make annotation heavyweight** (double-tap paragraph > text selection handles)
6. **Do not hide the knowledge graph** (make it visible as motivation and orientation)
7. **Do not conflate "not interested" with "already know"** -- these are fundamentally different signals

---

## References (Organized by Topic)

### Academic Papers and Books

- Cockburn, A., Karlson, A., & Bederson, B.B. (2008). A Review of Overview+Detail, Zooming, and Focus+Context Interfaces. *ACM Computing Surveys*, 41(1). [ACM DL](https://dl.acm.org/doi/10.1145/1456650.1456652)
- Pirolli, P. & Card, S. (1999). Information Foraging. *Psychological Review*, 106(4). [ResearchGate](https://www.researchgate.net/publication/229101074_Information_Foraging)
- Pirolli, P. & Card, S. (2005). The Sensemaking Process and Leverage Points for Analyst Technology. *Proc. International Conference on Intelligence Analysis*. [PDF](https://andymatuschak.org/files/papers/Pirolli,%20Card%20-%202005%20-%20The%20sensemaking%20process%20and%20leverage%20points%20for%20analyst%20technology%20as.pdf)
- Stasko, J., Gorg, C., & Liu, Z. (2008). Jigsaw: Supporting Investigative Analysis through Interactive Visualization. *Information Visualization*, 7(2). [ACM DL](https://dl.acm.org/doi/10.1145/1466620.1466622)
- Bederson, B.B. et al. (2004). DateLens: A Fisheye Calendar Interface for PDAs. *ACM TOCHI*, 11(1). [ACM DL](https://dl.acm.org/doi/10.1145/972648.972652)
- Alexander, J. et al. (2006). Faster Document Navigation with Space-Filling Thumbnails. *CHI 2006*. [ACM DL](https://dl.acm.org/doi/abs/10.1145/1124772.1124774)
- Fok, R. & Head, A. (2023). Scim: Intelligent Skimming Support for Scientific Papers. *CHI 2023 Demo*. [ACM DL](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)
- Fok, R. et al. (2024). Accelerating Scientific Paper Skimming with Augmented Intelligence. *ACM TIIS*. [ACM DL](https://dl.acm.org/doi/10.1145/3665648)
- Lo, K. et al. (2023). The Semantic Reader Project: Augmenting Scholarly Documents. *arXiv*. [arXiv](https://arxiv.org/abs/2303.14334)
- Tang, X. et al. (2024). Steering LLM Summarization with Visual Workspaces for Sensemaking. *arXiv*. [arXiv](https://arxiv.org/abs/2409.17289)
- Matejka, J. et al. (2021). Paper Forager: Supporting Rapid Exploration of Research Document Collections. *Graphics Interface*. [GI](https://graphicsinterface.org/proceedings/gi2021/gi2021-27/)
- Ishak, E. & Feiner, S. Content-Aware Scrolling. *UIST*. [PDF](http://www.cs.columbia.edu/~ishak/projects/CAS/tn123-ishak.pdf)
- Dingler, T. et al. (2020). One Does Not Simply RSVP. *CHI 2020*. [ACM DL](https://dl.acm.org/doi/10.1145/3313831.3376766)
- Kosch, T. et al. (2024). No, Bionic Reading Does Not Work. *Acta Psychologica*. [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0001691824001811)
- Baier, D. et al. (2022). Revisiting Interest Indicators Derived from Web Reading Behavior. *arXiv*. [arXiv](https://arxiv.org/abs/2207.06837)
- Hearst, M. (1997). TextTiling: Segmenting Text into Multi-paragraph Subtopic Passages. *Computational Linguistics*. [ACL Anthology](https://aclanthology.org/J97-1003.pdf)

### Products and Tools

- [Readwise Reader](https://readwise.io/read)
- [Superhuman](https://superhuman.com)
- [LiquidText](https://www.liquidtext.net/)
- [MarginNote](https://www.marginnote.com/features)
- [Orbit (Andy Matuschak)](https://withorbit.com/)
- [Semantic Reader (Semantic Scholar)](https://www.semanticscholar.org/product/semantic-reader)
- [Reeder](https://reederapp.com)
- [Matter](https://apps.apple.com/us/app/matter-reading-app/id1501592184)
- [Blinkist](https://www.blinkist.com/)
- [Shortform](https://www.shortform.com/)
- [Triage (email)](https://triage.cc/)
- [FSRS Algorithm](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler)
- [Omnivore (open source)](https://github.com/omnivore-app/omnivore)

### Blog Posts and Design Resources

- [Progressive Summarization (Forte Labs)](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)
- [Superhuman: Speed as the Product (Blake Crosley)](https://blakecrosley.com/en/guides/design/superhuman)
- [Information Foraging (NNGroup)](https://www.nngroup.com/articles/information-foraging/)
- [Mnemonic Medium (Andy Matuschak)](https://notes.andymatuschak.org/Mnemonic_medium)
- [SuperMemo Incremental Reading](https://supermemo.guru/wiki/Incremental_reading)
- [Material Design 3 Gestures](https://m3.material.io/foundations/interaction/gestures)
- [Progressive Disclosure in UX (LogRocket)](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)
- [Best Read-Later Apps 2026 (Readless)](https://www.readless.app/blog/best-read-later-apps-comparison)
