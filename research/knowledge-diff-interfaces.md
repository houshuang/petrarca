# Knowledge-Diff Reading Interfaces: Navigating to "The New Stuff"

*Research survey: HCI literature, adaptive hypermedia, and product patterns for reading interfaces that help users skip familiar content and focus on novel information.*

*Conducted 2026-03-07. Complements `hci-reading-systems.md` and `reading-ui-research.md` with a focused lens on the "knowledge diff" problem.*

---

## The Core Problem

A reader has a knowledge base from prior reading. When opening a new article, they want to:
1. Immediately see which parts contain information they already know
2. Navigate directly to the sections with genuinely new content
3. See the familiar parts dimmed/collapsed for context without distraction
4. Get a "diff view" showing what this article adds to their existing knowledge

This is analogous to a GitHub diff view, but instead of diffing two versions of the same file, we are diffing "what the article says" against "what the reader already knows."

No single system does exactly this. But the components exist across decades of HCI research and several modern products. This document maps those components.

---

## 1. Adaptive Hypermedia: The Academic Foundation

### 1.1 Brusilovsky's Taxonomy of Adaptive Presentation

Peter Brusilovsky's foundational work (1996, 2001, 2007) defines the canonical techniques for adapting text presentation to a user model. His taxonomy identifies five fragment-level techniques:

**a) Inserting/Removing Fragments**
Content is conditionally shown or hidden based on the user model. A beginner sees prerequisite explanations; an expert sees them omitted. The system literally inserts or removes paragraphs. Used in MetaDoc, Anatom-Tutor, AHA.

**b) Altering Fragments**
Different variants of the same content are shown based on user knowledge level. A concept explanation might have a "novice" version and an "expert" version. Used in C-Book.

**c) Stretchtext**
The most elegant technique for the knowledge-diff use case. Hidden text can be expanded inline by clicking a link or icon. Unlike removing fragments, the user retains the *ability* to see the hidden content --- they just have to opt in. The amount of context depends on the quality of the link anchor or icon to signal what is hidden.

Originally conceived by Ted Nelson in 1967, stretchtext inserts content directly into the reading flow when activated, allowing readers to expand anchor text to see definitions, explanations, or supplementary details without navigating away. Modern implementations are rare despite theoretical recognition. The key insight: "outlines and summaries are static --- they exist at a fixed depth. StretchText is dynamic" --- enabling variable-depth consumption rather than fixed summary layers.

**d) Sorting Fragments**
Paragraphs are reordered based on relevance to the user. More relevant fragments appear first. Less studied but conceptually interesting for knowledge-diff: put the novel content first.

**e) Dimming Fragments**
The most directly relevant technique. Parts of the document containing information that is "out of the user's focus" are visually shaded rather than hidden. The information remains visible and directly accessible, but the visual emphasis guides the reader's attention to what matters.

Key advantage over hiding: dimming preserves context. The reader can still see the familiar material if they want to, but their eye is naturally drawn to the non-dimmed (novel) parts. This is the closest academic precedent to a "knowledge diff" view.

*Source: [Methods and Techniques of Adaptive Hypermedia](https://sites.pitt.edu/~peterb/papers/UMUAI96.pdf) (Brusilovsky, 1996)*
*Source: [Adaptive Content Presentation for the Web](https://www.cs.ubc.ca/~carenini/PAPERS/adaptiveWeb07.pdf) (Bunt, Carenini, Conati, 2007)*

### 1.2 The Overlay User Model

All adaptive hypermedia systems rely on an "overlay model" of user knowledge. For each concept in the domain, the system tracks how much the user knows about it (typically 0.0--1.0). When presenting content, the system checks which concepts each fragment covers and compares against the user's overlay model.

InterBook (Brusilovsky, Eklund, Schwarz, 1998) is the canonical implementation:
- Domain is modeled as a concept network (each concept = elementary knowledge unit)
- Each content page has **prerequisite concepts** and **outcome concepts**
- The system monitors student progress per concept
- Links are annotated with traffic-light colors: green = "ready, contains new knowledge," red = "not ready (prerequisites unmet)," white = "no new knowledge"

This is strikingly close to what Petrarca already does with `interest_topics` and `novelty_claims`. The key design decision: InterBook uses link annotation (color-coded navigation) rather than content adaptation (dimming/hiding within the page).

*Source: [Adaptive Navigation Support in Educational Hypermedia](https://sites.pitt.edu/~peterb/papers/BJET03.pdf) (Brusilovsky, 2003)*

### 1.3 AHA! System: Dimming + Traffic Lights

The AHA! (Adaptive Hypermedia for All) system by De Bra at TU Eindhoven combines several techniques:
- Link anchors colored blue (ready, new information), purple (ready, not new), or black (not ready)
- Conditional fragment insertion/removal for prerequisite explanations
- Fragment shading to reduce cognitive overload from too many highlighted links

Key finding: "annotation is a more powerful technology than hiding: hiding can distinguish only two states (relevant/non-relevant) while annotation can identify up to six states." Dimming technology can well simulate hiding through visual de-emphasis.

*Source: [AHA! Adaptive Hypermedia for All](https://dl.acm.org/doi/fullHtml/10.1145/506218.506247) (De Bra, 2002)*

### 1.4 Adaptive Presentation Supporting Focus and Context

A 2003 workshop paper specifically explored the combination of dimming with focus+context techniques. Rather than binary show/hide, the system uses a gradient of visual emphasis: fully visible (novel/important), dimmed (familiar but contextual), and hidden (completely irrelevant). This three-level approach maps well to a knowledge-diff: bright = new, dim = known, hidden = not relevant at all.

*Source: [Adaptive Presentation Supporting Focus and Context](https://wwwis.win.tue.nl/ah2003/proceedings/ht-5/) (AH2003 Workshop)*

---

## 2. Fisheye Views and Focus+Context for Text

### 2.1 Furnas's Degree of Interest Function

George Furnas's foundational fisheye view work (CHI 1986) provides the mathematical framework for showing detail where it matters and compressing elsewhere. His Degree of Interest (DOI) function:

**DOI(x, f) = API(x) - D(x, f)**

Where:
- **API(x)** = A Priori Importance of node x (independent of current focus)
- **D(x, f)** = Distance from node x to current focus f

For a knowledge-diff reading interface, this maps naturally:
- **API** = novelty score of each paragraph (how much new information it contains relative to the user's knowledge)
- **D** = structural distance from the current reading position
- **DOI** determines visual treatment: high DOI = full size, medium DOI = visible but reduced, low DOI = compressed or hidden

The fisheye view then shows novel sections at full size, familiar-but-nearby sections at reduced size, and distant familiar sections compressed to single lines.

*Source: [Generalized Fisheye Views](https://dl.acm.org/doi/10.1145/22627.22342) (Furnas, 1986)*

### 2.2 Fisheye Views Applied to Text Documents

Hornbaek and Frokjaer (2001, 2003) conducted the definitive usability study comparing three document reading interfaces:

- **Linear** (standard scrolling reader)
- **Fisheye** (focus area at readable size, context areas above/below compressed)
- **Overview+Detail** (full document minimap alongside readable detail view)

Key results:
- Fisheye interface: readers were **faster** at answering questions
- Overview+Detail: readers wrote **higher quality** essays (deeper comprehension)
- Linear interface: "inferior to both fisheye and overview+detail regarding most aspects of usability"
- The fisheye interface led to "shallow understanding" -- readers answered fewer incidental-learning questions correctly

**Design implication for Petrarca**: A pure fisheye (collapsing familiar content) would make reading faster but might sacrifice comprehension. The recommendation is overview+detail for deep reading, fisheye for time-critical tasks like triage. Both could be modes in Petrarca.

*Source: [Reading of Electronic Documents: Linear, Fisheye, and Overview+Detail Interfaces](https://www.researchgate.net/publication/221514617_Reading_of_electronic_documents_The_usability_of_linear_fisheye_and_overviewdetail_interfaces) (Hornbaek & Frokjaer, 2003)*

### 2.3 Shneiderman's Visual Information-Seeking Mantra

Ben Shneiderman's mantra --- "Overview first, zoom and filter, then details on demand" --- provides the high-level interaction pattern:

1. **Overview first**: Show the full article with novelty annotations (a heat map of what's new vs. known)
2. **Zoom and filter**: Let the user focus on novel sections, filtering out familiar content
3. **Details on demand**: Expand any collapsed familiar section for full context

This three-phase interaction is a robust framework for the knowledge-diff reading flow.

*Source: [The Eyes Have It](https://ieeexplore.ieee.org/document/545307/) (Shneiderman, 1996)*

---

## 3. Skimming and Selective Highlighting Interfaces

### 3.1 Scim: Faceted Highlights for Paper Skimming

Scim (IUI 2023, later ACM TIIS 2024) is the most directly applicable modern system for "skip to the important parts" reading. Developed as part of the Semantic Reader Project at AI2.

**Core design:**
- NLP automatically identifies salient sentences in a paper
- Sentences are classified into four rhetorical facets: **objectives**, **novelty**, **methods**, **results**
- Each facet gets a distinct color
- Highlights are **evenly distributed** throughout the paper (not just clustered at the start)
- Density is configurable at both paper-wide and paragraph-local levels

**Interaction patterns:**
- **Facet toggles**: Readers can turn on/off specific facets (e.g., show only "novelty" highlights)
- **Scrollbar markers**: Colored markers in the scrollbar show where highlighted passages are located, enabling rapid navigation
- **Sidebar highlight browser**: A panel collects all highlighted passages for sequential review without scrolling through the full paper
- **Paragraph-level density controls**: "More" / "Less" buttons per paragraph
- **Paper-wide density slider**: Global control over highlighting density

**User study findings:**
- Researchers used Scim in multiple strategies: some read primarily in the sidebar highlight browser, others made multiple passes with different facets active (e.g., objectives+novelty first pass, methods+results second pass)
- Highlights reduced the time it takes to find specific information
- Particularly useful for papers outside the reader's area of expertise

**Petrarca relevance**: Scim's faceted approach could be directly adapted. Instead of rhetorical facets (objective/novelty/methods/results), Petrarca could use knowledge-state facets: "new to you" / "relates to your interests" / "known to you" / "background context". The scrollbar markers and sidebar browser patterns are immediately applicable.

*Source: [Scim: Intelligent Skimming Support for Scientific Papers](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034) (Fok et al., IUI 2023)*
*Source: [Accelerating Scientific Paper Skimming](https://dl.acm.org/doi/10.1145/3665648) (ACM TIIS 2024)*

### 3.2 The Semantic Reader Project: A Library of Augmentation Patterns

The broader Semantic Reader Project (AI2, UC Berkeley, UW) has produced over a dozen reading interface prototypes, each contributing relevant patterns:

**ScholarPhi** (CHI 2021): Just-in-time definition tooltips. Click a term, get its definition from elsewhere in the paper without leaving your reading position. Key pattern: *inline augmentation at the point of reading*.

**CiteSee** (CHI 2023): Visually augments inline citations based on the reader's library. Citations to papers the reader has already read are colored differently from unfamiliar citations. Clicking "Expand" surfaces additional context from recently read papers. Key pattern: *personalizing visual treatment based on what the reader already knows*.

**CiteRead** (IUI 2022): Adds margin annotations showing how subsequent papers have discussed, extended, or contradicted specific passages. Key pattern: *cross-document context localized to the reading position*.

**Paper Plain** (CHI 2023): Plain-language summaries accessible via flags next to section headers. A sidebar provides questions readers may have, with links to answering passages and associated plain language summaries. Key pattern: *progressive disclosure from simplified to detailed*.

*Source: [The Semantic Reader Project](https://ar5iv.labs.arxiv.org/html/2303.14334) (Lo et al., 2023)*

### 3.3 Constrained Highlighting (CHI 2024 Best Paper)

Joshi and Vogel at University of Waterloo demonstrated that *limiting* how much users can highlight improves comprehension. Their system enforces a 150-word highlight limit:

- When the limit is reached, the system refuses additional highlights
- Users must revise existing highlights to add new ones
- This forces active evaluation: "Is this truly the most important part?"

Key finding: The constrained group scored 11% higher than unlimited highlighting and 19% higher than no highlighting on next-day comprehension tests. One participant explained: "It forced me to highlight only the parts I thought were more important. In turn, this forced me to understand the story and main themes more."

**Petrarca relevance**: If Petrarca automatically highlights "what's new," it should limit the amount of highlighting to maintain the signal-to-noise ratio. Excessive "everything is new" highlighting would be as useless as no highlighting. The system should be selective --- highlighting only the most novel claims, not every unfamiliar sentence.

*Source: [Constrained Highlighting in a Document Reader](https://dl.acm.org/doi/10.1145/3613904.3642314) (Joshi & Vogel, CHI 2024)*

---

## 4. Document Diff Interfaces: Lessons from Change Tracking

### 4.1 Wikipedia Visual Diffs

Wikipedia's 2018 visual diff system redesigned how editing changes are presented:

- **Unchanged text**: Dark grey on light grey (dimmed)
- **Changed paragraphs**: Black on white with colored borders (orange = old version, blue = new version)
- **Inserted/removed text**: Highlighted with the border color and bolded

Key design decisions:
- The dimming of unchanged text creates a natural focus on changes
- Border colors rather than background colors preserve readability
- The system remembers user preference for visual vs. wikitext diff

**Petrarca adaptation**: The "unchanged = grey on light grey" pattern maps directly to "familiar content = dimmed." The "changed = black on white with colored border" maps to "novel content = full contrast with accent marking."

*Source: [Visual Diffs Make It Easier to See Editing Changes](https://wikimediafoundation.org/news/2018/02/20/visual-diffs/) (Wikimedia, 2018)*

### 4.2 Code Editor Minimaps (VS Code Pattern)

VS Code's minimap provides a high-level overview of the entire document with colored markers:
- The minimap shows a compressed rendering of the full file
- Search results, errors, and changes are marked with colored indicators
- A highlighted viewport rectangle shows the currently visible portion
- Clicking the minimap navigates directly to that position

**Petrarca adaptation**: A scrollbar minimap showing novelty distribution --- green markers where novel content appears, grey where familiar content lives --- would let users jump directly to the new parts. This is essentially what Scim does with its scrollbar markers.

### 4.3 The "Track Changes" Interaction Model

Microsoft Word's Track Changes and Google Docs' Suggestion Mode share a common pattern:
- Insertions are shown in a distinct color (typically green or blue)
- Deletions are shown struck-through in another color (typically red)
- Comments appear in margin balloons
- The user can accept/reject individual changes

For a knowledge-diff, the analogous interactions would be:
- Novel information is visually marked (color/highlight)
- Familiar information is visually de-emphasized (dimmed/collapsed)
- The user can mark novel information as "I know this now" (accept) or "tell me more" (expand)
- Margin annotations show connections to prior knowledge

---

## 5. Progressive Disclosure and Layered Reading

### 5.1 Tiago Forte's Progressive Summarization

While not an HCI research system, Forte's Progressive Summarization technique provides a concrete mental model for layered reading:

- **Layer 0**: Full original text
- **Layer 1**: Captured excerpts (broad selection)
- **Layer 2**: Bolded passages (key phrases and core ideas)
- **Layer 3**: Highlighted passages (the "best of the best")
- **Layer 4**: Executive summary in your own words
- **Layer 5**: Remixed creative output

The key insight: each layer is a *compression* of the previous layer, and the visual treatment (normal -> bold -> highlighted -> summary) creates instant navigability. A reader returning to a note can read just the highlighted parts (Layer 3) in seconds, or drill down to the full text (Layer 0) for context.

**Petrarca adaptation**: The article could be presented with automatically generated layers based on the knowledge model:
- Layer 0: Full article text (dimmed for familiar sections)
- Layer 1: AI-extracted key claims (always visible)
- Layer 2: Novel claims highlighted (the knowledge diff)
- Layer 3: One-sentence "what's new for you" summary at the top

The user navigates between layers, spending most time in Layer 2 (the diff view).

*Source: [Progressive Summarization](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/) (Forte Labs)*

### 5.2 Axios Smart Brevity Format

Axios developed the "Smart Brevity" format specifically for scannable news. Every story follows a rigid structure:
- **Tease**: Snappy headline
- **Lede**: One strong first sentence
- **Why it matters**: Bold-labeled context block
- **Go Deeper**: Expandable additional detail

The format tells readers "What's new" and "Why it matters" first, always. Formatting uses strategic bolding, white space, bullets, and labeled sections.

**Petrarca adaptation**: The knowledge-diff reader could adopt a similar rigid structure:
- **What's new for you**: Bold summary of novel claims
- **Why it matters**: Connection to your interests
- **Full article**: The complete text with familiar sections collapsed
- **Go Deeper**: Related articles, research threads

*Source: [Smart Brevity](https://www.axioshq.com/smart-brevity) (Axios HQ)*

### 5.3 StretchText as Dynamic Progressive Disclosure

As described in Section 1.1c, stretchtext enables variable-depth reading where familiar sections are collapsed to single lines and can be expanded on demand. Unlike static summaries, stretchtext is dynamic --- the depth adjusts per-reader based on their knowledge model.

Modern NLP makes stretchtext practical: an LLM can generate multiple levels of summary for each section, enabling a true fractal reading experience where the reader zooms into the unfamiliar and skims the familiar.

---

## 6. Knowledge-Adaptive Systems (Beyond Education)

### 6.1 GLOSSER: Vocabulary-Aware Reading

GLOSSER is a reading assistant for foreign language texts that highlights words the reader doesn't know and provides definitions. It maintains an overlay model of the reader's vocabulary and adapts its highlighting over time as the reader learns new words.

**Petrarca analogy**: Replace "vocabulary words" with "knowledge claims." As the reader reads more articles, their knowledge model grows, and previously highlighted (novel) claims become familiar (dimmed) in future articles.

### 6.2 NLP Novelty Detection

Academic NLP research on novelty detection is directly relevant. A comprehensive survey (Computational Linguistics, 2022) defines novelty detection as "finding text that has some new information to offer with respect to whatever is earlier seen or known."

Key approaches:
- **Document-level**: Is the whole article redundant given what the user has read?
- **Sentence-level**: Which specific sentences contain novel information?
- **Knowledge-base comparison**: Check extracted claims against a background KB of known facts. Triples where two parts exist in the KB but one part is unknown are considered novel.

The semantic approach (checking meaning rather than word overlap) is critical: non-novel information may have completely different surface text but convey the same meaning. Semantic methods detect up to 90% of redundancy vs. only 19% for lexical methods.

**Petrarca relevance**: The pipeline already extracts `novelty_claims` and `interest_topics`. The next step is comparing these against the user's accumulated knowledge model (their "personal KB") to produce per-sentence novelty scores that drive the visual treatment.

*Source: [Novelty Detection: A Perspective from NLP](https://direct.mit.edu/coli/article/48/1/77/108847/) (Computational Linguistics, 2022)*

### 6.3 Update Summarization

In the clinical NLP domain, "update summarization" focuses on summarizing only novel content not already captured in previous summaries. The CLIN-SUMM system generates a "Changes over time" section that explicitly identifies what is new since the last update.

The challenge: over 50% of text in longitudinal clinical notes is duplicated due to copy-paste. The same pattern exists in news articles and blog posts --- much of any article recaps what the reader may already know from prior reading.

**Petrarca relevance**: When displaying an article, the system could generate an "update summary" --- a section showing only what this article adds beyond the user's existing knowledge. This is the textual equivalent of the knowledge diff.

---

## 7. Spatial and Annotation-Based Reading

### 7.1 LiquidText: Collapsible Document + Spatial Workspace

LiquidText's core innovation is treating the document as a malleable object:
- The document pane shows the full text with user annotations
- Users can "pull out" excerpts and place them on an infinite workspace
- Excerpts maintain live links back to their source location
- The workspace supports both list and mind-map organization
- The key interaction: pinch-to-collapse sections of a document, physically compressing familiar sections while keeping novel sections expanded

**Petrarca adaptation**: The pinch-to-collapse gesture could work in a mobile knowledge-diff reader. The user pinches familiar sections to collapse them, or the system auto-collapses sections scored as "known" by the knowledge model. Collapsed sections show a one-line summary that can be tapped to expand.

*Source: [LiquidText: A Flexible, Multitouch Environment to Support Active Reading](https://faculty.cc.gatech.edu/~keith/pubs/chi2011-liquidtext.pdf) (Tashman & Edwards, CHI 2011)*

### 7.2 Hypothesis: Social Annotation Layer

Hypothesis adds a collapsible annotation sidebar to any web page or PDF. Key UI patterns:
- Right-side panel overlays the document
- Annotations are anchored to specific text selections
- Four annotation types: highlights, margin notes, page notes, replies
- Tags enable filtering and search across annotations
- The panel collapses when not needed, preserving the reading experience

**Petrarca adaptation**: Knowledge-diff annotations ("you know this," "this is new," "relates to Article X") could use a similar right-margin pattern. On mobile, these could appear as subtle left-border colors (matching the existing claim card design) or as a swipeable annotation layer.

*Source: [Hypothesis](https://web.hypothes.is/)*

### 7.3 Readwise Reader: Ghost Reader AI

Readwise Reader's Ghostreader feature provides AI-augmented reading with:
- Document-level summaries generated on demand
- Term definitions from context
- Inline highlights that carry over to a note-taking system
- Keyboard-driven reading (H to highlight, T to tag, N to note)
- Wide-screen margin annotations

The most relevant feature: Ghostreader can answer questions about the document, enabling a "what's new here?" query that effectively produces a knowledge diff.

*Source: [Readwise Reader](https://readwise.io/read)*

---

## 8. Multi-Source Synthesis Interfaces

### 8.1 Cross-Document Reading Patterns

When a reader has consumed multiple articles on a topic, the knowledge-diff challenge becomes a multi-document synthesis problem. Several systems address this:

**CiteSee** personalizes citation display based on the reader's library. Citations to familiar papers are visually distinguished from unfamiliar ones, helping the reader navigate the novelty landscape of a new paper relative to their prior reading.

**CiteRead** shows marginal annotations from citing papers, providing "what happened next" context that helps readers understand a paper's impact relative to their existing knowledge.

**Andy Matuschak's Stacked Notes**: The note-taking interface displays linked notes in a horizontal stack, allowing readers to see multiple related notes simultaneously while maintaining context. This pattern could display multiple articles' takes on the same topic side-by-side.

*Source: [Andy Matuschak's Notes](https://notes.andymatuschak.org/)*

### 8.2 Roam Research and Transclusion

Roam Research's bidirectional linking and block references enable a form of automatic synthesis: when you view a page about a concept, you automatically see every other note that references it. This is a simple but powerful form of knowledge-diff: "here's everything you've encountered about this concept before."

Transclusion (embedding a block from one note inside another) allows reuse without duplication. Edits propagate automatically. This pattern could inform how Petrarca shows "you encountered this claim before in Article X" --- by transcluding the original context.

---

## 9. Synthesis: Design Patterns for Petrarca's Knowledge-Diff Reader

### 9.1 The Interaction Model

Drawing from all the above research, here is a proposed interaction model:

**Entry: The Knowledge-Diff Overview**
When opening an article, the reader first sees a "diff summary" (inspired by Axios Smart Brevity + Update Summarization):
- "3 claims new to you" / "2 claims extend what you know" / "5 claims you already know"
- A scrollbar minimap (VS Code + Scim pattern) with green markers at novel sections
- A one-paragraph "what's new for you" summary

**Reading: Dimmed + Highlighted Text**
The full article text is displayed with visual treatment driven by the knowledge model (Brusilovsky dimming + Wikipedia visual diff):
- **Novel claims**: Full contrast, left border in green (`#2a7a4a`, the existing `claimNew` color), optionally with a subtle background tint
- **Familiar claims**: Reduced opacity (0.55), left border in muted color (`#d0ccc0`, the existing `claimKnown` color)
- **Background/context**: Normal opacity, no border marking
- **Section headers**: Always visible, with a novelty indicator (e.g., "3 new claims" badge)

**Navigation: Fisheye + Stretchtext**
- Familiar sections can be collapsed to one-line summaries (stretchtext pattern)
- Tapping a collapsed section expands it (progressive disclosure)
- A "Show only new" toggle collapses all familiar sections at once
- A "Show all" toggle restores the full article
- The scrollbar minimap enables jumping directly to novel sections (Scim pattern)

**Feedback: Accept/Reject + Annotation**
- Swipe or tap on a novel claim to mark "I know this now" (accept, like Track Changes)
- Long-press on any passage to add a note or connect to another article
- "Tell me more" action on a novel claim triggers research agent or surfaces related articles

### 9.2 Visual Language (Mapped to Petrarca Design System)

| Element | Novel Content | Familiar Content | Context |
|---------|--------------|------------------|---------|
| Text opacity | 1.0 | 0.55 | 0.85 |
| Left border | 2px `claimNew` (#2a7a4a) | 2px `claimKnown` (#d0ccc0) | none |
| Section header | Full contrast + "N new" badge | Dimmed + collapsible | Normal |
| Scrollbar marker | Green dot | Grey dot | none |
| Background | subtle warm tint | none | none |

### 9.3 The DOI Function for Petrarca

Adapting Furnas's Degree of Interest function:

```
DOI(paragraph, focus) = NoveltyScore(paragraph) - Distance(paragraph, focus)
```

Where:
- `NoveltyScore` = 1.0 - max_similarity(paragraph_claims, user_knowledge_base)
- `Distance` = structural distance in sections from current reading position

Paragraphs with DOI > threshold_high: full display
Paragraphs with DOI > threshold_low: dimmed display
Paragraphs with DOI < threshold_low: collapsed to one-line summary

### 9.4 Implementation Phases

**Phase 1: Static Knowledge Diff (achievable now)**
- Use existing `novelty_claims` from the pipeline
- Compare against user's accumulated "known claims" (from reading history + explicit "I know this" signals)
- Apply dimming (opacity 0.55) to paragraphs whose claims are all in the user's knowledge base
- Add scrollbar markers showing novelty distribution
- Add "what's new for you" summary at top

**Phase 2: Interactive Diff (next iteration)**
- Collapsible familiar sections (stretchtext)
- "Show only new" toggle
- Swipe-to-mark-known on individual claims
- Sidebar claim browser (like Scim's highlight browser)

**Phase 3: Cross-Document Diff (future)**
- When a claim matches a prior article's claim, show the connection: "Also discussed in [Article X]"
- Transclusion of original context from the earlier article
- Multi-article synthesis view: "Here's what you've learned about Topic Y across 5 articles"

---

## 10. Open Questions

1. **Granularity**: Should novelty scoring operate at paragraph level, sentence level, or claim level? Claim-level is most semantically meaningful but requires high-quality claim extraction. Paragraph-level is simplest to implement.

2. **Cold start**: What happens before the user has a knowledge model? The system should probably start with no dimming and build the model from reading behavior + explicit signals.

3. **Calibration**: How dim is "dim enough"? The Wikipedia visual diff uses grey-on-light-grey for unchanged content. Brusilovsky's research suggests dimming should preserve readability while directing attention. Need to test opacity values with real users.

4. **Confidence**: How should the system communicate uncertainty? If the NLP is only 70% confident a claim is "known," should it show a partial dim? Or should there be a confidence threshold below which no dimming is applied?

5. **Decay**: Knowledge decays over time. A claim the user "knew" 6 months ago might need re-highlighting. The existing interest model's 30-day decay could apply to claim knowledge as well.

6. **User control**: All adaptive hypermedia research emphasizes user control. The reader should be able to:
   - Override any dimming decision ("I don't know this")
   - Adjust the aggressiveness of dimming (conservative = dim less, aggressive = dim more)
   - Turn off the knowledge-diff view entirely

7. **Multi-source conflicts**: What if two articles make contradictory claims about a topic the user already knows about? This requires not just "new vs. known" but "agrees vs. contradicts vs. extends."

---

## References

### Academic Papers
- Brusilovsky, P. (1996). Methods and Techniques of Adaptive Hypermedia. *UMUAI*. [PDF](https://sites.pitt.edu/~peterb/papers/UMUAI96.pdf)
- Brusilovsky, P. (2003). Adaptive Navigation Support in Educational Hypermedia. *BJET*. [PDF](https://sites.pitt.edu/~peterb/papers/BJET03.pdf)
- Bunt, A., Carenini, G., Conati, C. (2007). Adaptive Content Presentation for the Web. *Springer*. [PDF](https://www.cs.ubc.ca/~carenini/PAPERS/adaptiveWeb07.pdf)
- De Bra, P. (2002). AHA! Adaptive Hypermedia for All. [ACM](https://dl.acm.org/doi/fullHtml/10.1145/506218.506247)
- Fok, R. et al. (2023). Scim: Intelligent Skimming Support for Scientific Papers. *IUI*. [ACM](https://dl.acm.org/doi/fullHtml/10.1145/3581641.3584034)
- Fok, R. et al. (2024). Accelerating Scientific Paper Skimming. *ACM TIIS*. [ACM](https://dl.acm.org/doi/10.1145/3665648)
- Furnas, G. W. (1986). Generalized Fisheye Views. *CHI*. [ACM](https://dl.acm.org/doi/10.1145/22627.22342)
- Head, A. et al. (2021). Augmenting Scientific Papers with Just-in-Time Definitions. *CHI*. [ACM](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648)
- Hornbaek, K. & Frokjaer, E. (2003). Reading of Electronic Documents: Fisheye and Overview+Detail. [ResearchGate](https://www.researchgate.net/publication/221514617)
- Joshi, N. & Vogel, D. (2024). Constrained Highlighting in a Document Reader. *CHI Best Paper*. [ACM](https://dl.acm.org/doi/10.1145/3613904.3642314)
- Lo, K. et al. (2023). The Semantic Reader Project. [arXiv](https://arxiv.org/abs/2303.14334)
- Shneiderman, B. (1996). The Eyes Have It. *IEEE VL*. [IEEE](https://ieeexplore.ieee.org/document/545307/)
- Tashman, C. & Edwards, W. K. (2011). LiquidText. *CHI*. [PDF](https://faculty.cc.gatech.edu/~keith/pubs/chi2011-liquidtext.pdf)
- Ghosal, T. et al. (2022). Novelty Detection: A Perspective from NLP. *Computational Linguistics*. [MIT Press](https://direct.mit.edu/coli/article/48/1/77/108847/)

### Industry Products and Design Systems
- [Readwise Reader](https://readwise.io/read) --- AI-augmented read-later with Ghostreader
- [Hypothesis](https://web.hypothes.is/) --- Open-source social annotation
- [Semantic Scholar Semantic Reader](https://www.semanticscholar.org/product/semantic-reader) --- AI-augmented PDF reader
- [LiquidText](https://www.liquidtext.net/) --- Spatial reading workspace
- [Axios Smart Brevity](https://www.axioshq.com/smart-brevity) --- Scannable news format
- [VS Code Minimap](https://code.visualstudio.com/docs/getstarted/userinterface) --- Document overview with markers

### Design Techniques
- [Progressive Summarization](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/) --- Tiago Forte
- [StretchText](https://eclecticlight.co/2016/09/03/stretchtext-a-hidden-gem-in-real-hypertext/) --- Ted Nelson's expandable text concept
- [StretchText: Expandable Information](https://www.bradypramberg.com/posts/2020/09/stretchtext-expandable-information) --- Modern analysis
- [Wikipedia Visual Diffs](https://wikimediafoundation.org/news/2018/02/20/visual-diffs/) --- Change highlighting design
- [NN/g Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/) --- Usability guidelines
