# Article Synthesis Prior Art: Products That Merge Multiple Articles Into Combined Views

Research into existing products, prototypes, and approaches that take multiple articles about the same topic and produce a combined topical report or synthesis view.

---

## 1. News Aggregation & Synthesis Products

### Google News — Full Coverage & Story Clusters

**What it does:** Google News clusters articles from thousands of sources by topic, using AI to group related stories. The "Full Coverage" feature lets you tap into a story cluster to see a diversity of perspectives, timelines, and opinion pieces around a single event or topic. Clusters can contain hundreds of articles (one documented example had 649 articles in a single cluster).

**How synthesis works:** Google does NOT generate a unified prose synthesis. Instead, it organizes coverage structurally: headline articles, opinion/analysis, local angles, timeline, and FAQ-style cards. The algorithm considers original reporting, timeliness, coverage of recent developments, and local relevancy when ranking within a cluster. As of late 2025, Google is testing AI-powered article overviews on select publications' pages and exploring LLM-based de-duplication to merge overlapping stories into dense, auto-updating narratives.

**What's good:**
- Clean card-based UI for browsing a story cluster without duplication
- Full Coverage gives genuine perspective diversity (different outlets, opinion vs. reporting)
- Massive scale — 30-day window, thousands of sources
- Structural organization (timeline, opinion, local) rather than just a list

**What's bad:**
- No actual prose synthesis — still a list of articles, just organized
- Heavy editorial bias in which outlets appear first
- No user control over synthesis depth or focus
- The "auto-updating story" concept is still experimental

**Petrarca lessons:** The structural clustering approach (timeline, perspectives, opinion vs. fact) is valuable even without generating prose. Consider organizing a topic view around facets rather than just generating a single summary.

---

### Particle News

**What it does:** Built by former Twitter engineers, Particle is arguably the closest existing product to "synthesize 20 articles into one view." Each Particle "story" is a cluster of articles about the same event, synthesized into a bulleted summary drawn from multiple sources. Launched November 2024, web version added May 2025.

**How synthesis works:** When you open a story, you see an AI-generated bulleted summary pulling facts from across all sources in the cluster. You can switch between modes: "Just the Facts" (5W's summary), "Explain Like I'm 5" (simplified), and "Opposite Sides" (contrasting perspectives from left/right-leaning sources). A "story spectrum" shows how coverage distributes across the political spectrum. As of 2026, Particle also uses vector embeddings to clip relevant podcast segments and attach them to story clusters.

**What's good:**
- True multi-source synthesis (not just linking to articles)
- Multiple presentation modes for the same synthesis (facts vs. ELI5 vs. perspectives)
- Political spectrum visualization ("Opposite Sides" feature)
- Revenue-sharing with publishers rather than just scraping
- Podcast clip integration (2026) — multi-modal synthesis

**What's bad:**
- Primarily event-driven news, not long-running topic analysis
- Summary modes are preset — no user-defined synthesis angles
- Quality depends on cluster quality; if clustering is wrong, synthesis is wrong

**Petrarca lessons:** The multiple presentation modes idea is powerful. A synthesis could have different "lenses": just facts, what's new since last time, contrasting views, ELI5. The spectrum visualization is interesting for showing source diversity. Podcast clip attachment is a creative multi-modal extension.

---

### Ground News

**What it does:** Aggregates from 40,000+ outlets, clusters stories by event, then overlays bias analysis. Publishes ~30,000 AI-generated story summaries daily.

**How synthesis works:** For each story cluster, Ground News generates separate summaries of how Left, Center, and Right outlets cover the same story. The "Bias Comparison" feature (beta) highlights where coverage differs across the political spectrum. Stories show a visual breakdown of how many outlets from each political leaning are covering it, and which outlets are NOT covering it (the "blindspot" feature).

**What's good:**
- "Blindspot" feature — showing what's NOT being covered is as valuable as what is
- Bias-aware synthesis rather than bias-naive
- Per-perspective summaries rather than a single "neutral" synthesis
- Ownership transparency — shows who owns each outlet

**What's bad:**
- Bias classification is coarse (left/center/right) and US-centric
- AI synthesis "may gloss over nuance that trained reporters would catch" (CJR review)
- Primarily a news product — not suitable for longer-form topic synthesis

**Petrarca lessons:** The "blindspot" concept (what sources are NOT saying) is brilliant and underexplored. Per-perspective synthesis rather than "one true summary" respects the reader's agency. Could adapt: instead of political perspective, use "disciplinary perspective" or "time period."

---

### Artifact (Shutdown 2024, tech acquired by Yahoo News)

**What it does:** Instagram co-founders' AI news app. Summarized articles, rewrote clickbait headlines, personalized recommendations using a TikTok-style engagement model.

**How synthesis worked:** Artifact did per-article summarization (various styles like "Gen Z" or "Explain Like I'm Five") but NOT multi-article synthesis. The AI rewriting was applied to individual articles. The core value was personalization and discovery, not synthesis.

**What's good:**
- Clean, modern design that a core audience loved
- AI headline rewriting was genuinely useful (removing clickbait)
- Personalization engine worked well

**What's bad:**
- Lost focus by adding social features (link posting, text content, places)
- Market too small to justify investment
- Never attempted multi-article synthesis

**Petrarca lessons:** Focused execution matters. Artifact's best features (clickbait rewriting, personalization) were sharp and useful. The failure came from losing focus. Also: the technology survived the company — Yahoo News integrated the AI. For Petrarca, the per-article rewriting (stripping clickbait, normalizing tone) is a valuable preprocessing step before synthesis.

---

### SmartNews

**What it does:** Major news aggregation app (50M+ downloads). Strong in Japan and US. Uses "News from all sides" approach.

**Synthesis features:** Limited — primarily article-level summarization and topic clustering. No documented multi-article synthesis feature. The app's strength is algorithmic curation and speed, not synthesis.

**Petrarca lessons:** SmartNews demonstrates that curation and speed can be valuable even without synthesis. The "all sides" framing resonates with users tired of echo chambers.

---

### Semafor Signals

**What it does:** A human-curated, AI-assisted global news feed. Journalists identify central facts of a story, then curate analysis and insight from a global range of sources, including opposing views.

**How synthesis works:** This is a hybrid human-AI approach: journalists use Microsoft/OpenAI tools to identify and curate perspectives, then write the synthesis themselves. The format explicitly separates facts from analysis from opinion. The original "Semaform" article format was designed to make this separation visible.

**What's good:**
- Explicit separation of facts / analysis / opinion
- Global source range (not just US/UK outlets)
- Human editorial judgment guides what matters
- The format itself is a contribution to synthesis UX

**What's bad:**
- Doesn't scale (requires journalist labor)
- Not customizable to individual reader interests
- Limited topic coverage

**Petrarca lessons:** The facts / analysis / opinion separation is a powerful structural element for synthesis. Even AI-generated synthesis could benefit from this explicit layering. Consider a synthesis format that says: "Here are the agreed-upon facts. Here is where sources disagree. Here is the open analysis."

---

### ChatGPT Pulse (OpenAI, 2025)

**What it does:** Nightly briefing service for ChatGPT Pro mobile users. Delivers personalized daily summaries leveraging the user's conversation history and memory system.

**How synthesis works:** Uses the user's accumulated context (past conversations, stated interests) to select and synthesize daily news into a proactive briefing. Represents a shift from reactive chat to proactive synthesis.

**Petrarca lessons:** The proactive, scheduled synthesis based on a user model is directly relevant. Petrarca already has the interest model — a daily or per-topic synthesis generated from that model is a natural extension.

---

## 2. AI Research Synthesis Tools

### Google NotebookLM

**What it does:** Upload up to 50 sources (PDFs, Google Docs, URLs, YouTube transcripts). Ask questions across all sources. Generates summaries, study guides, audio overviews ("podcast-style" discussions), mind maps, data tables, infographics, slide decks, flashcards, and quizzes.

**How synthesis works:** NotebookLM treats uploaded sources as ground truth — it will not hallucinate beyond them. You can select specific sources to query against, or query across all. Inline citations link back to specific passages. The Audio Overview feature generates a two-host podcast discussion synthesizing the material. As of December 2025, Data Tables can extract structured data across sources and export to Google Sheets. Deep Research (November 2025) creates research plans and synthesizes reports.

**What's good:**
- Source-grounded (no hallucination from external knowledge)
- Multiple output modalities (text, audio, visual, structured data)
- Cross-reference engine that finds connections and discrepancies
- Clean, minimal interface — no feature bloat
- Users report it helps them "think more clearly"

**What's bad:**
- Citation depth issues — "Source 3" without page/paragraph numbers
- No cross-notebook synthesis (notebooks are isolated silos)
- No built-in export with live citations
- Accuracy degrades as you approach the 50-source limit
- "Context window anxiety" — early sources get ignored in favor of recent ones
- Outputs are not directly editable
- Text-only input (must transcribe audio/video first)

**Petrarca lessons:** The source-grounded approach is critical — synthesis should never introduce information not present in the source articles. The multiple output modalities idea is interesting (could Petrarca offer both a text synthesis and an audio summary?). The cross-notebook limitation reveals a key design question: should synthesis be per-topic or cross-topic? The citation-to-source-passage linking is essential for trust.

---

### Consensus.app

**What it does:** AI search engine specifically for scientific literature. Searches 200M+ academic papers, synthesizes findings across papers for a given question. Features a "Consensus Meter" that visualizes agreement/disagreement across the literature.

**How synthesis works:** Hybrid semantic + keyword search retrieves top 1,500 papers, which are re-ranked by relevance and research quality. AI then generates a cohesive synthesis with citations. The "Pro Analysis" feature synthesizes findings across multiple papers. The "Consensus Meter" uses fine-tuned models to classify papers as supporting, opposing, or neutral on yes/no questions. "Checker models" verify relevance before summarizing. If insufficient evidence exists, it says so rather than hallucinating.

**What's good:**
- Consensus Meter is a brilliant visualization of agreement/disagreement
- "Checker models" that verify before summarizing
- Explicit "I don't have enough evidence" responses
- Quality signals (research methodology, citation count) influence ranking
- Grounded in real papers, not general knowledge

**What's bad:**
- Limited to scientific literature
- Yes/no framing for Consensus Meter is constraining
- Individual paper analysis can still misinterpret nuance

**Petrarca lessons:** The Consensus Meter concept could translate to news: "Are sources in agreement or disagreement about this claim?" The checker-model approach (verify relevance before synthesizing) is a good safeguard. The explicit "insufficient evidence" response is better than a confident hallucination.

---

### Elicit

**What it does:** AI research assistant for systematic literature reviews. Finds papers, extracts data into a structured matrix, and generates synthesis reports.

**How synthesis works:** Papers are displayed in a table with customizable columns. Users add columns like "sample size," "methodology," "main findings" and Elicit extracts answers from full-text papers automatically. Clicking any extracted answer shows the supporting quote from the paper. Reports synthesize up to 80 papers with methods sections, mini-PRISMA diagrams, tables, and frequency counts. As of December 2025, "Research Agents" can conduct automated systematic reviews with 94-99% data extraction accuracy.

**What's good:**
- The structured matrix approach — extracting specific dimensions across many papers — is powerful
- Supporting quote verification (click to see source passage)
- Reports include methodology (how the synthesis was generated)
- High accuracy (94% screening, 94-99% extraction)
- "Strict Screening" mode for academic rigor

**What's bad:**
- Academic-focused, not general reading
- Matrix is researcher-driven (you must define the columns/questions)
- Export limited to CSV

**Petrarca lessons:** The structured matrix is the most promising synthesis UI pattern found in this research. Instead of generating a prose summary, present a table: Article | Key Claim | What's New | Agrees/Disagrees With. Let the user define dimensions they care about. The supporting-quote verification pattern is essential for trust. The "methods section" in reports (explaining how synthesis was generated) is a transparency practice worth adopting.

---

### Semantic Scholar (TLDR + Semantic Reader)

**What it does:** AI2's academic search engine. TLDR generates one-sentence summaries of papers. Semantic Reader provides an augmented PDF reading experience. Research Feeds learn from your library.

**How synthesis works:** TLDR is per-paper, not cross-paper. The value is in rapid triage — one sentence tells you whether to read the full paper. Available for ~60M papers in CS, biology, and medicine.

**What's good:**
- TLDR is genuinely useful for screening/triage
- Clean, fast, focused on one thing
- Research Feeds personalize based on your library

**What's bad:**
- No multi-document synthesis
- TLDR limited to CS and biomedical domains
- Not designed for non-academic content

**Petrarca lessons:** Per-article TLDR is a necessary building block before multi-article synthesis. Petrarca already extracts claims and topics — ensuring each article has a reliable one-line summary is prerequisite work. The Research Feeds personalization based on saved/read items mirrors Petrarca's interest model.

---

## 3. Newsletter & Digest Tools

### Feedly (Leo AI)

**What it does:** RSS reader with AI assistant "Leo" that prioritizes, deduplicates, summarizes, and filters articles. Feedly offers an "AI Overview" feature for cross-article synthesis.

**How synthesis works:** Leo summarizes individual articles. The AI Overview block "analyzes multiple articles together to identify patterns and connections" — this is cross-article synthesis for newsletter creation. Users can generate newsletter sections from multiple selected articles. Leo can also be trained with examples and feedback to refine recommendations.

**What's good:**
- AI Overview is genuine multi-article synthesis
- Integrated into the RSS reading workflow (not a separate tool)
- Trainable AI (feedback loop)
- Newsletter export — synthesis becomes a shareable artifact

**What's bad:**
- AI Overview quality is undocumented in reviews
- Primarily a professional/enterprise tool (pricing reflects this)
- Synthesis is oriented toward newsletter creation, not personal understanding

**Petrarca lessons:** The AI Overview concept — "analyze these 15 articles together and find patterns" — is exactly what Petrarca needs. The key insight is integrating synthesis into the reading workflow rather than making it a separate step. The newsletter export idea is interesting: could Petrarca generate a personal weekly synthesis that looks like a newsletter?

---

### Mailbrew

**What it does:** Creates automated personal email digests from RSS, Twitter, Reddit, Hacker News, YouTube, newsletters, and other sources. Delivers at a scheduled time.

**How synthesis works:** Aggregation rather than synthesis. Mailbrew pulls highlights from your configured sources and assembles them into a clean, ad-free email. It can tag and categorize newsletters. The value is curation and scheduling, not AI synthesis.

**What's good:**
- Clean, beautiful digest format
- Multi-source aggregation (RSS + social + newsletters)
- Scheduling — content arrives when you want it

**What's bad:**
- No AI synthesis across items
- No topic clustering
- No personalization beyond source selection

**Petrarca lessons:** The scheduled digest format is a good delivery mechanism. Even without synthesis, a well-organized daily email showing "here's what's new in your interest areas" has value. The multi-source aggregation (RSS + Twitter + newsletters) is already part of Petrarca's pipeline.

---

### TLDR Newsletter

**What it does:** Family of 16+ daily tech newsletters serving 1.6M+ subscribers. Human-curated with a team of domain-expert freelance curators who select from 3,000-4,000 sources. Each story is summarized in 1-2 sentences.

**How synthesis works:** This is human curation, not AI synthesis. The value is editorial judgment about what matters, combined with extreme brevity. Stories are grouped by topic (AI, security, crypto, web dev, etc.) within each edition.

**What's good:**
- 5-minute read time is a powerful constraint
- Topic grouping within editions
- Domain-expert curators ensure quality
- Consistent, reliable format

**What's bad:**
- Not personalized
- No multi-article synthesis (each item is independent)
- Human-curated, doesn't scale to individual preferences

**Petrarca lessons:** The "5-minute read" constraint is worth adopting. A synthesis should have a clear time-to-consume target. The topic grouping within a digest is simple but effective. The domain-expert curation highlights that quality matters more than automation.

---

### Kagi News

**What it does:** Daily AI-generated news briefing at 8am ET. Customizable topics and sections, collated from an open-source list of public RSS feeds. Powered by Kagi's proprietary summarization models (Cecil, Agnes, Muriel).

**How synthesis works:** AI generates daily topic-grouped summaries from RSS feeds. Customizable topics. Links to original sources for deeper reading.

**What's good:**
- Respectful of user attention (one briefing per day)
- Customizable topics
- Open-source feed list
- In-house models (not dependent on OpenAI)

**What's bad:**
- Limited documentation on synthesis quality
- Fixed daily cadence

**Petrarca lessons:** The "one briefing per day, respect attention" philosophy aligns with Petrarca's design principles. In-house or open-source models for synthesis reduce dependency on API providers.

---

### Readwise Reader (Ghostreader)

**What it does:** Read-later app with AI assistant "Ghostreader" that summarizes, defines terms, generates questions, and allows follow-up chat about any document. Daily Digest surfaces new and saved items.

**How synthesis works:** Ghostreader operates on individual documents, not across documents. You can chat with a document, but not across your entire library. The Daily Digest is a curated selection (new items + backlog items), not a synthesis.

**What's good:**
- AI integrated directly into the reading experience
- Chat interface allows follow-up questions
- Customizable prompts (bring your own AI patterns)
- BYO API key with model selection (GPT-5, o3, etc.)

**What's bad:**
- No cross-document synthesis
- No topic clustering of saved articles
- Daily Digest is selection, not synthesis

**Petrarca lessons:** Ghostreader's integration INTO the reading experience (not a separate mode) is the right UX pattern. The customizable prompt library is interesting — let users define their own synthesis patterns. The absence of cross-document synthesis in Readwise is a clear gap that Petrarca could fill.

---

## 4. Search & Report Tools

### Perplexity Deep Research + Pages

**What it does:** Deep Research conducts dozens of parallel web searches, reads hundreds of sources, and generates comprehensive research reports. Pages turns research into shareable, published content with sections, media, and citations.

**How synthesis works:** When activated, Deep Research interprets your query, formulates a research plan, conducts parallel searches, cross-references findings, and synthesizes into a report with executive summaries, key insights, timelines, and recommendations. Pages lets you edit sections, adjust audience level (beginner/advanced/anyone), add media, and publish. Export to PDF or shareable link.

**What's good:**
- End-to-end: question → research plan → search → synthesis → report
- Audience-level customization
- Editable output (add/remove/rewrite sections)
- Published Pages are searchable
- Source transparency throughout

**What's bad:**
- Pages feature was temporarily retired for redesign
- Quality varies — some reports are excellent, some are generic
- No integration with personal reading history or saved articles
- Synthesizes from the open web, not from YOUR curated sources

**Petrarca lessons:** The research plan transparency ("here's what I'll investigate") is a trust-building pattern. Audience-level customization is valuable. The critical difference for Petrarca: synthesis from your curated, read articles rather than the open web. This means the synthesis reflects YOUR reading, not the internet's general take.

---

### Arc Search ("Browse for Me")

**What it does:** Mobile browser feature. Type a query, tap "Browse for Me," and Arc searches the web, reads multiple pages, and generates a custom webpage with a synthesized answer.

**How synthesis works:** Uses OpenAI's API to search, read, and synthesize. The generated page includes: image/video gallery, title + bulleted summary, top 3-5 search results, sub-headings with detailed bullet points, and a "Dive Deeper" section with links.

**What's good:**
- One-tap synthesis — extremely low friction
- Generated page format is well-structured (summary → details → sources)
- "Dive Deeper" section maintains access to original sources

**What's bad:**
- No control over which sources are used
- No persistence — each "browse" is ephemeral
- Quality depends entirely on what web search returns
- No integration with personal reading/interests

**Petrarca lessons:** The structural format (summary → structured details → source links) is a good template for synthesis output. The "Dive Deeper" pattern (synthesis first, sources available on demand) respects reader flow. The one-tap friction is aspirational.

---

## 5. DIY / Open Source Approaches

### Fabric (Daniel Miessler)

**What it does:** Open-source framework of AI prompt patterns for augmenting daily workflows. Includes patterns for summarization, extraction, and analysis. Can be piped together for complex workflows.

**How synthesis works:** Fabric provides modular "patterns" (prompt templates) that can be chained. You could pipe multiple articles through `extract_wisdom` then through a `create_summary` pattern. The stitching feature enables multi-step workflows.

**What's good:**
- Fully customizable patterns
- Command-line composability (pipe multiple steps)
- Community-contributed patterns
- Model-agnostic

**What's bad:**
- CLI tool, not a product — requires technical skill
- No UI for synthesis output
- No built-in article clustering or topic detection
- Each pattern is independent — no persistent knowledge model

**Petrarca lessons:** The pattern/prompt library concept is worth adopting. Users could define synthesis "patterns" — "give me the contrarian takes," "what would I disagree with," "what's genuinely new." The composability (chain extraction → synthesis → formatting) maps well to a pipeline architecture.

---

### GitHub News Summarization Projects

**What exists:** Dozens of open-source projects (LazyNews, AI-News-Summariser, etc.) that fetch news via RSS/APIs and generate summaries. Most use GPT-3.5/4 for single-article summarization. Some categorize by topic. None do genuine multi-article synthesis.

**What's good:**
- Demonstrate the technical feasibility
- Often simple and well-documented
- Good starting points for experimentation

**What's bad:**
- Universally single-article summarization, not cross-article synthesis
- No topic clustering
- No quality control or hallucination detection
- No user model or personalization

**Petrarca lessons:** The gap is clear: single-article summarization is a solved problem. Cross-article synthesis (identifying what's shared, what's different, what's new) is the unsolved interesting problem.

---

### DIY "Daily Brief" Systems

**What exists:** Blog posts describing personal setups using Claude/GPT + RSS feeds + Make.com/Zapier to generate daily briefings. One documented system fetches from 40+ RSS feeds, filters by relevance, generates 1-2 sentence summaries organized by topic. Tools like Glean (self-hosted) offer AI-powered RSS reading with auto-tagging and topic clustering.

**What's good:**
- Highly customizable to individual needs
- Can integrate diverse sources (RSS, email, social)
- Often well-documented as blog posts

**What's bad:**
- Fragile (depends on API availability, rate limits)
- No shared infrastructure or community
- Quality varies enormously
- Still mostly summarization, not synthesis

**Petrarca lessons:** The personal, customized approach resonates with Petrarca's single-user philosophy. The integration of diverse sources (RSS + Twitter + email) is already in the pipeline. The key gap in these DIY systems is the same: aggregation without genuine synthesis.

---

## 6. What Works and What Doesn't

### Common Failure Modes

1. **Hallucination at scale:** A Columbia Journalism Review study found that nearly half of 3,000 AI news responses contained significant misrepresentations. ChatGPT falsely attributed 76% of quotes it was asked to identify. In research contexts, 91% hallucination rate was observed in literature synthesis tasks.

2. **Loss of nuance:** "Summaries, by their nature, do not contain context or nuance, which are crucial elements for accurate news reporting." AI struggles with idiomatic expressions, cultural references, emotional undertones, and the difference between editorial commentary and verified reporting.

3. **Source attribution failures:** AI chatbots frequently direct users to syndicated versions (Yahoo News, AOL) rather than original sources. Models "alter quotes or summarize without clear links and timestamps." Citation depth is insufficient ("Source 3" without page/paragraph).

4. **Context window degradation:** NotebookLM users report "forgetful" behavior where early sources are ignored. Accuracy drops as source count approaches limits.

5. **Consensus fabrication:** When synthesizing across sources, AI tends to smooth over genuine disagreements, creating false consensus. The opposite of what synthesis should do.

### What Users Actually Want

Based on patterns across all products reviewed:

1. **Source transparency** — Being able to trace every claim back to a specific source and passage
2. **Disagreement surfacing** — Not just "here's the consensus" but "here's where sources differ"
3. **Adjustable depth** — Summary first, details on demand, full sources available
4. **Trust calibration** — Knowing when the AI is confident vs. uncertain
5. **Personal relevance** — "What's new to ME" not "what's new in general"
6. **Structural organization** — Facts vs. analysis vs. opinion, timeline, perspectives
7. **Editability** — Ability to correct, annotate, or extend the synthesis

### What's Missing From Every Product

No existing product combines all of these:
- Synthesis from YOUR curated/read articles (not the open web)
- Knowledge-model-aware synthesis ("skip what I already know")
- Cross-article claim comparison (which articles agree/disagree on specific claims)
- Progressive synthesis that builds over time as you read more
- User-defined synthesis dimensions/angles
- Source-passage-level attribution (not just "Source 3")

---

## 7. Synthesis for Petrarca: Key Takeaways

### Most Promising Patterns to Adopt

1. **Elicit's structured matrix** — Extract specific dimensions across articles (claim, evidence, agreement, what's new) rather than generating prose. Let users add their own columns.

2. **Ground News' blindspot detection** — Show what's NOT being covered, not just what is. Adapt: "Your articles about X don't mention Y at all."

3. **Particle's multiple lenses** — Same synthesis, different presentations: just facts, what's new, contrasting views, ELI5.

4. **Semafor's fact/analysis/opinion separation** — Explicit structural layers in synthesis output.

5. **Consensus Meter's agreement visualization** — For each claim, show which articles agree, which disagree, which don't mention it.

6. **NotebookLM's source-grounding** — Synthesis should ONLY contain information from the source articles, never external knowledge.

7. **Perplexity's research plan transparency** — Show the user what the synthesis will cover before generating it.

8. **Feedly's integrated synthesis** — Synthesis should happen within the reading workflow, not as a separate mode.

### Unique Petrarca Advantage

Petrarca has something no other product has: a user knowledge model (interest topics with Bayesian scoring, novelty claims, reading history). This means synthesis can be:
- **Knowledge-aware**: "Skip the background on X, you already know it. Focus on what's genuinely new."
- **Interest-weighted**: "Emphasize the aspects related to your interest in Y."
- **Progressive**: "Since you last read about this topic, here's what has changed."
- **Claim-comparative**: "You read Article A's claim that Z. Articles B and C disagree."

This is the differentiator. Every other product synthesizes for a generic reader. Petrarca can synthesize for THIS reader, given what they've already read and what they care about.

### Recommended Synthesis Format

Based on this research, a Petrarca topic synthesis could follow this structure:

```
TOPIC: [Topic Name]
Based on [N] articles you've read/saved

1. WHAT'S NEW (since you last looked)
   - Claim-level bullets with source attribution
   - Marked as [agreed] [disputed] [unique to one source]

2. WHERE SOURCES DISAGREE
   - Specific claims where articles conflict
   - Side-by-side positions with source links

3. WHAT YOU HAVEN'T SEEN
   - Aspects of this topic not covered in your articles
   - Suggested directions for further reading

4. STRUCTURED COMPARISON (Elicit-style matrix)
   | Article | Key Claim | Evidence | Agrees With | New To You |
   |---------|-----------|----------|-------------|------------|

5. SOURCE PASSAGES
   - Expandable quotes linked to specific articles
```

---

## Sources

- [How AI Is Reshaping News Aggregation (Medium)](https://medium.com/@AhmedBn/how-ai-is-reshaping-news-aggregation-as-we-enter-2026-c8631839fa29)
- [Google News Full Coverage (Google Blog)](https://blog.google/products/news/get-full-news-story-full-coverage-search/)
- [Google testing AI article overviews (TechCrunch)](https://techcrunch.com/2025/12/10/google-is-testing-ai-powered-article-overviews-on-select-publications-google-news-pages/)
- [Particle launches AI news app (TechCrunch)](https://techcrunch.com/2024/11/12/particle-launches-an-ai-news-app-to-help-publishers-instead-of-just-stealing-their-work/)
- [Particle brings reader to web (TechCrunch)](https://techcrunch.com/2025/05/06/particle-brings-its-ai-powered-news-reader-to-the-web/)
- [Particle podcast clips (TechCrunch)](https://techcrunch.com/2026/02/23/particles-ai-news-app-listens-to-podcasts-for-interesting-clips-so-you-you-dont-have-to/)
- [Ground News bias comparison](https://help.ground.news/en/articles/3189505)
- [Ground News review (CJR)](https://www.cjr.org/analysis/the-business-of-balance-ground-news.php)
- [Artifact shutdown (TechCrunch)](https://techcrunch.com/2024/01/18/why-artifact-from-instagrams-founders-failed-shut-down/)
- [Why Artifact Failed (Failory)](https://newsletter.failory.com/p/why-artifact-failed)
- [Semafor Signals](https://www.semafor.com/article/02/05/2024/introducing-semafor-signals)
- [Perplexity Deep Research](https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research)
- [Perplexity Pages (TechCrunch)](https://techcrunch.com/2024/05/30/perplexity-ais-new-feature-will-turn-your-searches-into-sharable-pages/)
- [Arc Search Browse for Me](https://allthings.how/using-browse-for-me-in-arc-search/)
- [NotebookLM Data Tables (Google)](https://workspaceupdates.googleblog.com/2025/12/transform-sources-structured-data-tables-notebooklm.html)
- [NotebookLM Deep Research (TechCrunch)](https://techcrunch.com/2025/11/13/googles-notebooklm-adds-deep-research-tool-support-for-more-file-types/)
- [NotebookLM limitations (XDA)](https://www.xda-developers.com/notebooklm-limitations/)
- [NotebookLM source limit problem (XDA)](https://www.xda-developers.com/notebooklms-source-limit-is-its-biggest-problem/)
- [Consensus.app how it works](https://consensus.app/home/blog/how-consensus-works/)
- [Consensus app PMC review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12318603/)
- [Elicit systematic review features](https://scrollwell.com/guide/tools/elicit-ai-research-tool-review-new-features-2025/)
- [Elicit evaluation (Cochrane)](https://onlinelibrary.wiley.com/doi/full/10.1002/cesm.70050)
- [Semantic Scholar TLDR](https://www.semanticscholar.org/product/tldr)
- [Feedly AI features](https://feedly.com/ai)
- [Feedly AI-powered newsletters](https://feedly.com/new-features/posts/ai-powered-newsletters-faster-creation-greater-impact)
- [Mailbrew](https://mailbrew.com/)
- [TLDR Newsletter curation (Paved)](https://www.paved.com/blog/tldr-newsletter-curation/)
- [Kagi Summarizer](https://help.kagi.com/kagi/summarizer/)
- [Readwise Ghostreader](https://docs.readwise.io/reader/guides/ghostreader/overview)
- [Fabric (GitHub)](https://github.com/danielmiessler/Fabric)
- [Nuzzel shutdown](https://daringfireball.net/linked/2021/05/05/nuzzel)
- [AI search citation problems (CJR)](https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php)
- [AI hallucinations in literature synthesis (Springer)](https://link.springer.com/article/10.1007/s00146-025-02406-7)
- [AI news misrepresentation audit](https://windowsforum.com/threads/ai-news-summaries-under-scrutiny-45-misrepresentation-in-public-audits.385812/)
- [Multi-document summarization synthesis (MIT Press)](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00687/124262/Do-Multi-Document-Summarization-Models-Synthesize)
- [AI daily brief (Medium)](https://mark-mishaev.medium.com/how-i-built-an-ai-powered-daily-brief-that-saves-me-2-hours-every-day-2504a015f79f)
- [ChatGPT Pulse](https://ai2.work/news/ai-news-chatgpt-pulse-feature-launch-2025/)
- [Three newsrooms on AI summaries (Nieman Lab)](https://www.niemanlab.org/2025/06/lets-get-to-the-point-three-newsrooms-on-generating-ai-summaries-for-news/)
