# Petrarca: Complete User Journey Over Four Weeks

*A detailed narrative of how Stian is expected to use Petrarca over the first month, grounded in interview evidence, design research, and the current implementation. March 3, 2026.*

---

## The User

One person: Stian. Reads widely across history, cultural theory, AI/technology, policy, literature. Multiple languages. Multiple devices and contexts. The core frustration, stated in four separate interviews:

> "I read a lot and it just goes out the other window."

The goal isn't recall. It's **placement** — building enough mental framework that new information has somewhere to attach. Stian calls these "hooks."

> "'Done' = able to PLACE new knowledge. Having enough framework that new information can be assimilated."

---

## Reading Contexts (All Must Be Served)

| Context | Duration | Mode | What Stian does today |
|---------|----------|------|----------------------|
| Work break | 2-5 min | Phone/browser | Opens Twitter, bookmarks things, never returns |
| Commute/waiting | 2-10 min | Phone | Quick reading, reviews, triage |
| Article reading | 5-30 min | Phone or web | Occasionally gets through an article |
| Deep reading | 30-90 min | Kindle/phone/book | History, cultural theory, multiple books simultaneously |

Petrarca currently serves the first three. Deep reading (Mode B: "Deep Shelf") is explicitly deferred.

---

## Week 0: Before First Launch

### What happens in the pipeline

Before Stian ever opens the app, content is processed:

1. **Twitter bookmarks** (200+ items) and **Readwise Reader** items (537 with meaningful engagement) are fed through `build_articles.py`
2. Articles are fetched via 3-tier extraction (trafilatura → requests → lxml fallback)
3. Each article is processed by `claude -p`: sections extracted, summary written, key claims identified, topics tagged
4. Concepts are extracted across articles in batches of 5, deduplicated by word overlap (>60% Jaccard similarity)
5. **Current output**: 47 articles with content, 176 concepts across 107 topics, 15 cross-article concepts

**Assumption**: The pipeline produces useful articles from Stian's actual reading sources.

**Evidence**: The first experiment (Twitter bookmarks → Claude Code briefing) validated this. Stian used it to prepare a presentation. But content quality varies — some articles are donation pages, bitcoin addresses, boilerplate.

**Current state**: `validate_articles.py` exists but content quality filtering is minimal. The LLM processing catches most garbage, but some low-quality articles slip through. This is acceptable for a prototype with 47 articles; it becomes a problem at 500+.

---

## Week 1, Day 1: First Launch

### What actually happens

**App initialization** (invisible to user, ~2 seconds):
1. `initStore()` loads bundled `articles.json` (47 articles) and `concepts.json` (176 concepts)
2. Checks for cached remote content (none on first launch)
3. Loads user state from AsyncStorage (empty on first launch)
4. **Pre-seed fires**: 61 of 176 concepts are set to "encountered" based on Readwise reading history — topics like education (37 matching items), AI-and-writing (19), translation (16), classical-literature (8)
5. Background check for content updates from Hetzner server
6. Logs: `store_initialized`, `knowledge_preseed`

**What Stian sees**: Feed tab with 47 articles. Three view modes available (list/topics/triage).

### The First Five Minutes

**Most likely path**: List view (default). Stian scrolls through articles.

**What's different from a normal read-later app**:
- **Novelty badges** appear on articles. Because 61 concepts were pre-seeded from Readwise, articles about topics Stian has read extensively (education, AI, translation) show "Partly familiar" or lower. Articles about topics outside his Readwise history show "Mostly new" (~100%). This differentiation is immediate — no cold start period.
- **Time guidance** on each card: read time estimate.

**Assumption**: Novelty badges are visible and meaningful enough to change triage behavior.

**Risk**: The pre-seeding is based on topic overlap between Readwise items and concept topics. If the topic taxonomy is incoherent (and the simulation found 262 article topics vs 107 concept topics with only 33 overlapping), some pre-seeded concepts may be wrong. An article about "Byzantine bureaucracy" might have concepts about "ottoman-empire" that don't match any Readwise topics, even though Stian has read extensively about related history.

**What research says**: Artifact (the Instagram founders' news app) found that reading time, not clicks, was the best engagement signal. Nuzzle showed that transparent algorithms build trust. The novelty badge is our transparency mechanism — Stian can see WHY the system thinks an article is new or familiar.

### First Triage Session

Stian switches to Triage mode. This is the interaction the design vision calls "30-second interactions on phone."

**The flow**:
1. Full-screen card appears: title, summary, topics, source, read time
2. Stian swipes: right = "Read Later", left = "Skip", up = "Read Now"
3. Spring physics give satisfying feedback. Action labels fade in as card tilts.
4. Behind: 2 more cards stacked with depth effect
5. After all 47 cards: "All caught up!" screen with counts

**Assumption**: Forced binary choices produce faster triage than list browsing.

**Evidence from interviews**: "Not in the mood for long reading during work" — triage mode is designed for exactly this. The hypothesis was >3x faster decisions than list-browse.

**Implementation check**: Triage state persists to AsyncStorage (`@petrarca/triage_states`). After triaging, list view shows only `read_later` + `untriaged` items. Reset button available.

**Gap**: Triage mode doesn't use novelty scores to ORDER the cards. Cards appear in date order. The design vision says "Score incoming articles for genuine novelty. Surface only what's worth your time" — but triage presents articles chronologically, not by predicted value. High-novelty articles should appear first to maximize the value of limited triage time.

### First Deep Read

Stian taps an article from the feed. The reader opens.

**What happens**:
1. `reader_open` logged with article_id, previous_depth (unread)
2. Reader shows: title, author, metadata, time guidance bar, topic pills, full summary
3. **Floating depth indicator** at top: `Summary · Claims · Sections · Full` — "Summary" highlighted
4. Stian scrolls down naturally through the summary

**The claims zone** (key innovation):
- Divider: "KEY CLAIMS"
- Claims appear as cards with "Knew this" / "New to me" buttons
- Progress counter: "0 of 5 claims reviewed"
- Below each claim: **connection indicator** — if this concept has been encountered in other articles (from pre-seeding or prior reading), a subtle purple pill appears: "education · seen in 2 other articles"
- Tapping the connection pill expands to show article titles

**Assumption**: In-context claim evaluation produces richer signals than isolated claim lists.

**Evidence from research**: CHI papers on sensemaking show that context matters for judgment. Claims in isolation are harder to evaluate because the reader lacks the framing that the article provides.

**What happens when Stian signals**:
- "Knew this" on a claim → `processClaimSignalForConcepts()` finds matching concepts (content-word overlap > 0.3) → matched concepts transition to "known" → review auto-created with 7-day initial interval
- "New to me" → matched concepts transition to "encountered" → review created with 1-day interval
- Connection indicator updates if the concept was just encountered

**The implicit signal** (key assumption being tested):
If Stian spends >60 seconds in the claims/sections/full zone without tapping any buttons, `processImplicitEncounter()` fires once per session. All unknown concepts for this article become "encountered." This means **a user who reads attentively but never taps buttons still builds their knowledge model**.

**Evidence for this design**: The interviews repeatedly say "reading itself IS the signal." Artifact measured reading time as primary engagement signal. The 60-second threshold is a conservative estimate of meaningful engagement — quick skimmers won't trigger it.

**Risk**: 60 seconds in a zone might be too long or too short. If Stian reads quickly, he might leave the claims zone in 45 seconds having read all 5 claims carefully. If he reads slowly, 60 seconds might catch him still on the first claim. We log `dwell_ms` so we can analyze and adjust.

### Continuing deeper

Stian scrolls past claims into the **sections zone**:
- Section cards with headings, summaries, expand/collapse
- Expanding a section shows full section content rendered as proper markdown (headings, lists, blockquotes, code fences — fixed today)
- Section enter/exit times tracked automatically

And potentially into the **full article zone**:
- Complete markdown content
- Claims highlighted inline (blue for unsignaled, green for "new to me", gray for "knew this")
- Tap highlighted paragraph → floating pill with signal options
- Related articles section at the bottom: "Related Reading" with shared concept connections

**Scroll position is saved** every 2 seconds. If Stian leaves mid-article and comes back later, the reader scrolls to where he left off with a brief "Continuing where you left off" indicator.

### Voice note while reading

Stian reads something thought-provoking. He taps the mic button in the top bar.

**The flow**:
1. Recording starts (expo-av, high quality). Button turns red with timer.
2. Stian speaks for 15 seconds: "This reminds me of something Pirenne argued about trade routes..."
3. Taps to stop. Recording saved as VoiceNote with article_id + depth context.
4. **Automatic transcription** starts (Soniox API, async model `stt-async-v4`, multilingual).
5. After transcription completes: transcript matched against article's concepts (0.2 threshold — lower than claims because spoken language is noisier)
6. **Research banner appears**: shows transcript text + "Research this?" button
7. If Stian taps "Research this?": POST to Hetzner server with query + article context → `claude -p` runs in background finding diverse perspectives → results will be waiting in Progress tab next time

**Assumption**: Voice notes are a rich, low-friction signal that the user will actually use while reading.

**Evidence**: Four interviews mention voice notes. "I have often missed the opportunity to take voice notes while reading." "Voice → transcription → linked to reading context → fed into knowledge model."

**Risk**: Recording while reading on a phone in public (commute) may not be socially comfortable. The interviews describe the ideal context as "fireplace with a book" — private, relaxed. Work breaks are another context where recording might feel awkward.

**What research says about voice input**: It's the richest signal available (articulated thoughts vs. binary taps) but the highest friction. Petrarca doesn't require voice — it's an optional enhancement. The critical question is whether the research agent payoff is compelling enough to motivate recording.

---

## Week 1, Days 2-5: Building Habits

### The daily rhythm

**Morning commute (5 min)**:
1. Open app → Review tab
2. 3-5 concepts due for review (the pre-seeded "encountered" concepts from Readwise start becoming due at 1-day intervals)
3. Review card shows: concept text, topic, related claims from articles, any voice transcripts
4. "How does this connect to what you've been reading?"
5. Rate: confused (1) → fuzzy (2) → solid (3) → could teach (4)
6. Session capped at 7. "Done for now — 3 more available whenever you're ready."
7. Switch to Feed → check for new articles (if content refresh is set up on Hetzner, new articles may have appeared overnight)

**Work break (2 min)**:
1. Triage mode: swipe through any new articles
2. Or: continue reading an article from Continue Reading section (shows partially-read articles sorted by recency)

**Lunch (10-15 min)**:
1. Read 1-2 articles at claims depth
2. Signal on claims: "knew this" / "new to me"
3. Maybe record a voice note on something interesting
4. Connection indicators show up more often as the knowledge model populates

**Evening (optional, 20+ min)**:
1. Deep read an article through sections and full text
2. Related articles at the bottom lead to another article — the "rabbit hole" that Stian described
3. But this time, the rabbit hole is productive: depth is tracked, reading state persists, voice notes captured, concepts updated

### Knowledge model evolution through Week 1

**Day 1**: 61 concepts pre-seeded as "encountered." All others "unknown." Novelty scores reflect pre-seeded knowledge.

**Day 2-3**: Stian has read maybe 5-8 articles, signaled on ~20 claims. Through claim signals:
- ~10-15 concepts updated to "known" (things he already knew)
- ~5-10 more updated to "encountered" (new things)
- Through implicit encounters (dwell time): additional concepts from articles he read deeply but didn't explicitly signal

**Day 4-5**: Novelty scores start differentiating meaningfully. Articles about topics Stian has engaged with deeply (say, AI agents) show "60% new" or "Partly familiar." Articles about unfamiliar topics (say, bronze-age trade networks) still show "Mostly new."

**Assumption**: The knowledge model's concept coverage is granular enough to produce useful differentiation.

**Evidence from simulation**: With 176 concepts (median 4 per article), every article has at least 2 concepts. After reading 9 articles, novelty scores should start diverging. The simulation predicted this threshold — previously with 69 concepts (many articles at zero), useful divergence never happened.

**Remaining risk**: 176 concepts across 107 topics means most topics have 1-2 concepts. A topic like "medieval-history" might have 1 concept — reading one article about it flips that concept to "encountered," making ALL medieval history articles show as "partly familiar." This is too coarse. Ideally, we'd have 5-10 concepts per topic.

### Review sessions in Week 1

**Days 1-3**: Pre-seeded concepts start becoming due. These are concepts Stian is probably familiar with (matched from Readwise reading history) but hasn't explicitly engaged with in Petrarca. The reviews feel somewhat abstract — "You encountered this concept: 'LLM code generation.' How does this connect to what you've been reading?" — because the user hasn't actually read about it in Petrarca yet.

**Assumption**: Pre-seeded reviews are still valuable because they activate prior knowledge.

**Risk**: Pre-seeded reviews may feel disconnected and confusing. "Why is the app asking me about something I didn't read here?" The review card shows source articles and matching claims as context, but for pre-seeded concepts, there's no user engagement history to draw on.

**Mitigation**: Pre-seeded concepts start at 1-day intervals but will quickly settle. If Stian rates them "easy" (4), the interval jumps to 3.5 days, then ~12 days, then ~42 days. After 3 reviews, comfortable concepts essentially disappear for a month.

**Days 4-7**: Concepts from actual reading start becoming due. These reviews feel more natural — "You read about 'context engineering' 3 days ago. How does this connect to what you've been reading?" — because there's real engagement history, matching claims, maybe a voice note transcript.

**What the design vision says**: "Not flashcards — engagement prompts. The question isn't 'what is X?' but 'how does X connect to what you've been reading?'" The review prompt is deliberately open-ended and generative, not recall-based.

**Evidence from research**: Matuschak's "spaced everything" concept — scheduling attention to ideas, not just facts. Haisfield's work on "scaling synthesis." The review system is designed around this principle: revisit to connect, not to recall.

---

## Week 2: The Content Refresh Test

### The critical transition

This is where every read-later app dies. Stian has triaged all 47 articles. The initial batch is processed. Without new content, the app becomes review-only.

**What should happen** (with content refresh deployed):
1. Pipeline runs daily at 7 AM UTC on Hetzner
2. Fetches new Twitter bookmarks and Readwise items
3. Processes up to 10 new articles per run
4. Generates manifest.json with content hashes
5. When Stian opens the app: `checkForUpdates()` detects new manifest hash → `downloadContent()` fetches new articles + concepts → `mergeNewContent()` integrates them

**What Stian sees**: New articles in the Feed tab. The triage mode has new cards to swipe. The "all caught up" state from week 1 is replaced with fresh material.

**Assumption**: 10 new articles per day is the right volume. Not so many that it overwhelms, not so few that it feels stale.

**Evidence from interviews**: "Too many articles, too many tabs" — volume overwhelms. But also "constant stream from Twitter/RSS" — dryness kills engagement. 10 per day seems like a reasonable middle ground, but this needs user testing.

**Risk**: The pipeline's content quality is uneven. Some fetched articles will be 404s, paywalls, donation pages. At 10/day, even 30% garbage means 3 bad articles per day cluttering the feed. The LLM processing catches some of this, but not all.

**What's NOT built**: There's no mechanism for the user to report a bad article or mark a source as unreliable. The design vision mentions "author credibility" as a filtering dimension — this is still completely absent.

### Knowledge model deepening

By mid-week 2, Stian has engaged with ~20-30 articles. Approximately:
- 50-70 concepts have been updated (via explicit signals + implicit encounters)
- Novelty scores are meaningfully diverse (range: 0.3 to 1.0 across articles)
- The Knowledge Dashboard shows some topics filling in: AI/tech topics (well-covered in initial articles) might show 40-60% known/encountered

**Connection prompts become useful**: As more concepts reach "encountered" or "known" state, the inline ConnectionIndicator fires more often. When Stian reads a new article about AI agents, a claim about "context window management" triggers: "context-engineering · seen in 3 other articles." This is the "hooks" effect — new information attaching to existing knowledge.

**Assumption**: Connection prompts at the claim level are granular enough to be useful.

**Risk**: The content-word matching (>0.3 overlap threshold) might be too noisy. A concept like "educational assessment" might match claims about "AI model assessment" because "assessment" is the overlapping word. False connections undermine trust.

### Review cadence stabilizes

**Expected review volume by end of week 2**:
- ~60-80 concepts have review states
- With expanding intervals, most are not due simultaneously
- Typical daily queue: 5-10 due concepts (well within the 7-item session cap)
- Mature concepts (reviewed 3+ times) are settling to weekly or biweekly intervals

**The review experience should be improving**:
- Cards now show matching claims (added today) — concrete context
- Voice transcripts appear for concepts where Stian recorded notes
- Previous notes accumulate, making each review richer
- The prompt "How does this connect?" becomes more answerable as the user's mental model grows

**What's NOT happening**: The design vision describes "revisit via synthesis, not source." Currently, reviews show the concept + claims + articles, but there's no synthesized view ("here's what you took away from 4 articles about AI agents"). The synthesis feature exists for topic clusters in the feed, but not integrated into reviews.

---

## Week 3: Deeper Engagement Patterns

### The research agent loop

By week 3, Stian should have triggered a few research requests via voice notes. When he opens the Progress tab, results may be waiting:

**What a research result looks like**:
- Original question: "This reminds me of something Pirenne argued about trade routes..."
- **Perspectives**: 3-5 diverse viewpoints the agent found
- **Recommendations**: Specific articles/books to read next
- **Connections**: Links to existing reading

**Assumption**: Research results are high-quality enough to be worth the effort of recording a voice note and waiting.

**Risk**: `claude -p` quality depends heavily on the prompt. The research prompt asks for diverse perspectives and recommendations, but without access to Stian's full reading history (it only gets the current article's summary), the recommendations may be generic. Also, the results arrive asynchronously — Stian has to remember to check the Progress tab, and there's no push notification.

**What research says**: The interviews describe this as the key differentiating feature. "Spawns a background agent on the Hetzner VM that researches a question, has answers ready next time user returns." The delight is in the surprise — opening the app and finding that your question was answered while you slept.

### Topic synthesis emerges

Currently, 2 topic syntheses exist (claude-code with 5 articles, ai-agents with 5 articles). As more articles accumulate, more topics will cross the 3-article threshold and get syntheses generated.

**The Topics view in week 3**: Stian opens Topics mode. Sees topic clusters with article counts. The top clusters (5+ articles each) have purple synthesis cards. Tapping "Synthesis across 5 articles" reveals a flowing narrative about where the articles agree, disagree, and what's missing.

**Assumption**: AI-generated synthesis is useful and accurate.

**Risk**: `claude -p` synthesis of article summaries is two levels of abstraction away from the source material. The synthesis prompt works from summaries and claims, not the original text. It might produce plausible-sounding synthesis that misrepresents the actual arguments. Stian, as an experienced reader, might find this frustrating rather than helpful.

**What research says**: Tiago Forte's "Progressive Summarization" argues that effective synthesis requires the reader's own highlighting and annotation, not just AI summarization. The current synthesis is purely AI-generated. The design vision acknowledges this: "User's own thoughts (voice notes, reactions) are more valuable than the source material." A future version could incorporate Stian's voice notes and claim signals into the synthesis.

### Two modes, one system (still incomplete)

The design vision identifies two reading modes:

**Mode A (Firehose)**: Fast-moving tech/current content. This is what Petrarca currently serves. Twitter bookmarks, tech articles, policy updates. Quality uncertain, high volume, knowledge decays fast.

**Mode B (Deep Shelf)**: Enduring books and scholarship. History, cultural theory, literary criticism. The specific voice of the author matters. Knowledge should endure.

By week 3, Stian might be thinking: "This is useful for my tech reading, but I'm reading Huizinga's 'Waning of the Middle Ages' on Kindle and none of that is in Petrarca." The app serves half his reading life.

**What's NOT built**:
- No Kindle highlight import
- No chapter-level reading (only article-level)
- No context restoration for long-form works ("where was I in this chapter?")
- No way to manually add a book or chapter as content
- No AI pre-reading or background summaries for book chapters

**What the design vision says**: "Build later — overlapping infrastructure but different UX, more experimental." The shared infrastructure (knowledge model, review system, voice notes) exists. The Mode B UX does not.

---

## Week 4: The Sustainability Test

### Does the loop hold?

By week 4, Petrarca has been a daily habit (or hasn't). The question is whether the core loop sustains:

```
New content arrives → Triage (2 min) → Read interesting ones (5-30 min)
→ Knowledge model updates → Novelty scores improve → Better triage
→ Reviews maintain knowledge → Connections deepen → More engagement
```

**Positive indicators** (what we'd see in logs):
- Daily session count > 1 (multiple opens per day)
- Claim signals per article stable or increasing (not declining from "signal fatigue")
- Review ratings trending toward 3-4 ("solid" / "could teach") over time
- Voice notes being recorded occasionally (not zero)
- Research results being viewed (not ignored)
- Reading depth reaching "sections" or "full" on at least some articles

**Warning indicators**:
- Review queue growing faster than completion (reviews piling up)
- Triage becoming mechanical (all "skip" or all "read later" with no reading)
- Voice notes declining to zero
- Only summary-depth reading (never going deeper)
- App opens declining week over week

### The "hooks" test

The ultimate measure from the interviews: does Stian feel like he can **place** new knowledge?

When he reads a new article about AI agents in week 4, does the system help him recognize: "This relates to the context engineering concept I reviewed last week, and the agentic safety paper I read on day 3, and the voice note I recorded about orchestration patterns"?

**What we've built to enable this**:
- Connection indicators during reading (concept seen in N other articles)
- Related articles at end of reader
- Review prompts asking "How does this connect?"
- Topic synthesis showing what 5 articles collectively say

**What we haven't built**:
- Dynamic in-reading commentary ("You read about this concept in [article] last week. The author here disagrees with that perspective.")
- Personal knowledge timeline ("Your understanding of AI agents has evolved across these 8 articles over 3 weeks")
- Cross-reading synthesis incorporating the user's own notes

### What the knowledge model looks like at week 4

**Estimated state** (assuming 3-5 articles/day with daily reviews):
- ~120-140 articles read (47 initial + ~70-90 from content refresh)
- ~100-120 concepts with non-unknown state (of ~350-400 total with new articles)
- ~200-300 total reviews completed
- Review stability: most concepts at 7-30 day intervals
- Daily review queue: 5-15 items (manageable with 7-item cap)

**The Knowledge Dashboard** shows topic coverage. Some topics (AI/tech, education) are well-covered with 60-80% known/encountered. Others (history, literature) remain mostly unknown because Mode B content isn't in the system.

---

## Assumptions Inventory

### Validated by implementation

| # | Assumption | How we test it | Current state |
|---|-----------|---------------|---------------|
| 1 | Progressive depth (summary → claims → sections → full) reduces reading friction | Log `reader_scroll_depth` transitions, compare engagement at each level | Built. Fluid transitions work. No data yet. |
| 2 | Forced binary triage (swipe) is faster than list browsing | Compare `triage_swipe` speed vs `feed_item_tap` browsing patterns | Built. Needs usage data. |
| 3 | Novelty scores change triage behavior (users prioritize high-novelty articles) | Correlate `novelty` field in `feed_item_tap` with article selection | Built. Pre-seeding gives day-1 differentiation. |
| 4 | Implicit dwell time is a reliable interest signal | Correlate `implicit_concept_encounter` zones with explicit claim signals | Built. 60s threshold. Needs log analysis. |
| 5 | Concept-level review feels like re-engagement, not homework | Review completion rate, early-exit rate, note-writing frequency | Built. 7-item cap, "done for now" tone. |
| 6 | Voice notes are used and valued | `voice_note_added` frequency, `research_triggered` rate | Built. End-to-end flow works. Needs real usage. |

### Not yet validated

| # | Assumption | Risk | Mitigation |
|---|-----------|------|------------|
| 7 | Content refresh produces 10 useful articles per day | Pipeline quality is uneven. Some articles will be garbage. | Need quality scoring in pipeline. |
| 8 | Content-word matching (0.3 threshold) accurately maps claims to concepts | False positives connect unrelated ideas; false negatives miss real connections. | Embeddings would be more accurate. Current approach is "good enough" for prototype. |
| 9 | Pre-seeded knowledge from Readwise is accurate enough to not confuse the user | Topic-level matching is coarse. Some pre-seeded concepts will be wrong. | User can "override" by signaling differently on claims. |
| 10 | Research agent results are worth the latency | Results arrive hours later. Quality depends on prompt engineering. | Need to test with real voice notes and evaluate result quality. |
| 11 | Review prompts ("How does this connect?") produce genuine reflection, not rote dismissal | Users might just tap "good" without thinking to clear the queue. | Log whether notes are written (has_note field). A declining note rate suggests rote behavior. |
| 12 | The app will be opened daily without push notifications | Read-later apps die from abandonment. No notification system exists. | Consider adding gentle daily notifications for reviews + new content. |
| 13 | 47 → ~150 articles over 4 weeks is enough content for the knowledge model to be useful | Some topics will have 1-2 articles. Concepts will be sparse in many areas. | Content refresh + broader source ingestion needed. |

### Structural assumptions in the design

| # | Assumption | Interview evidence | Concern |
|---|-----------|-------------------|---------|
| 14 | Concepts (not claims) are the right unit of knowledge | "Not a fact. Not a whole book. Something in between." | Concepts are auto-extracted and may not correspond to the user's actual mental model. The user never confirms "yes, this is a meaningful concept to track." |
| 15 | Three-state knowledge (unknown/encountered/known) is sufficient granularity | "Having enough framework that new information can be assimilated." | The real spectrum is richer: unknown → heard of → vaguely understand → could explain → could teach → could apply creatively. Three states lose nuance. |
| 16 | Reading articles is the primary way to build knowledge | All four interviews focus on articles and books. | Stian also learns from conversations, talks, podcasts, writing. None of these feed the knowledge model. |
| 17 | A single user is enough to validate the system | "Personal, not social. Built for one power user." | One user's behavior may not generalize. But the goal is personal tool first, so this is acceptable. |
| 18 | The "soft touch" constraint is compatible with effective learning | "Must NOT be another note-taking obligation." "No streaks, no guilt." | Effective learning often requires deliberate effort. The system may be too passive to produce deep understanding. The tension between "effortless" and "effective" is the core design challenge. |

---

## The Unresolved Design Tensions

### 1. Passive vs. Active Knowledge Building

The interviews say: "Reading itself IS the signal." But the research (SuperMemo, Matuschak, Forte) all emphasize that **active processing** — extracting, connecting, re-stating — is what produces durable understanding.

Petrarca tries to split the difference: passive signals (dwell time, reading depth) build the model automatically, while optional active signals (claim buttons, voice notes, review notes) deepen it. But the passive signals are necessarily coarse. Knowing that someone spent 60 seconds in the claims zone tells you they engaged, but not what they thought about it.

**The tension**: Make it too passive and the knowledge model is shallow. Make it too active and it becomes "another note-taking obligation."

**What we've built**: Both paths work. A fully passive user (never taps claims, never records voice notes) still gets concepts updated via dwell time. An active user gets richer updates and triggers research agents. The question is whether the passive path produces enough value to keep the user opening the app.

### 2. Filtering vs. Serendipity

The knowledge model is designed to surface genuinely novel content and deprioritize familiar material. But Stian explicitly values serendipity:

> "Sometimes following interesting threads into rabbit holes is exciting."

And the research (Artifact) recommends an "exploration budget" — 10-20% of recommendations outside the user's comfort zone to prevent filter bubbles.

**What we've NOT built**: No exploration budget. No way to intentionally surface articles outside the user's known interests. The novelty score purely reflects the knowledge model, which might create a feedback loop: read about AI → AI articles look "partly familiar" → system shows non-AI articles → user reads about history → history articles become "partly familiar" → cycle continues. This could be desirable (breadth) or undesirable (the user wanted to go deeper on AI).

### 3. Synthesis Quality

The design vision promises: "When revisiting, show a synthesis + your notes, not the raw original." But AI-generated synthesis is only as good as the inputs.

Currently, topic synthesis uses article summaries (already one level of abstraction from the original). The user's own notes and voice reflections are NOT incorporated into synthesis. This means the synthesis represents what the articles say, not what the user took away from them.

**The ideal** (from interviews): "If the system knew everything I had read... it could prompt me to make connections with previous material." This implies personalized synthesis — not just "what do 5 articles say about AI agents" but "what YOU learned about AI agents from these 5 articles, based on what you signaled, noted, and reviewed."

### 4. Review Motivation

The review system asks "How does this connect?" — an open-ended, generative prompt. But there's no feedback on whether the user's answer is good. Unlike language learning (where you know if you got the word right), conceptual review has no clear success criterion.

**Risk**: Without feedback, reviews become a box-ticking exercise. Stian taps "good" on every concept to clear the queue. The system records "understanding: 3" but the user hasn't actually reflected.

**What might help**: Showing the user how their understanding has evolved ("You rated this 'fuzzy' 2 weeks ago, now you rate it 'solid'. Here's what changed in between."). Or generating a specific connection prompt: "Article X argues A. Article Y argues B. Do you think they're compatible?" This requires more sophisticated prompting than the current generic "How does this connect?"

---

## What's Working Well

1. **The fluid reader** — scrolling through depth levels is natural and low-friction. Zone tracking captures meaningful engagement data.

2. **Claim signals as knowledge model input** — the "knew this" / "new to me" binary is simple, fast, and directly updates the model. It maps to the core question: "Is this new to you?"

3. **The implicit encounter mechanism** — ensures passive readers still build their model. 60s threshold is conservative enough to avoid false positives.

4. **Pre-seeding from Readwise** — eliminates the cold start problem. Day-1 novelty scores are differentiated.

5. **Content refresh architecture** — the pipeline → manifest → app sync flow is clean and should work reliably.

6. **Review session caps** — "Done for now" framing and 7-item limit prevent obligation fatigue.

7. **Scroll position persistence** — "No losing your place" is genuinely solved.

## What Needs Attention

1. **Concept granularity** — 176 concepts across 107 topics is still coarse. Many topics have 1-2 concepts. Topic-level pre-seeding means one article can flip an entire topic from "unknown" to "encountered."

2. **No content quality filtering** — the pipeline ingests everything and the app shows everything. As volume grows, noise will increase.

3. **No push notifications** — the app relies entirely on the user remembering to open it. This is the #1 predictor of read-later app abandonment.

4. **Review cards lack personalization** — the prompt is always "How does this connect?" regardless of the concept's history. A concept reviewed 5 times should get a different prompt than one being reviewed for the first time.

5. **Synthesis doesn't incorporate user notes** — topic synthesis is purely from article content, not from the user's own engagement.

6. **Triage doesn't use novelty ordering** — cards appear chronologically, not by predicted value to the user.

7. **No Mode B** — half of Stian's reading life (books, scholarship, deep works) is unserved.

8. **Research results have no feedback loop** — if Stian finds a research result useful or useless, there's no way to tell the system. The research agent can't learn what kinds of questions produce valuable results.

---

## Measurement Plan

Every assumption above can be tested with the existing event logging. Key analyses:

| Question | Events to analyze | What would validate |
|----------|------------------|-------------------|
| Does novelty scoring change behavior? | `feed_item_tap` with `novelty` field | High-novelty articles selected disproportionately |
| Is triage faster than browsing? | Time between `triage_swipe` events vs. `feed_item_tap` events | <5 seconds per triage decision |
| Does implicit encounter correlate with explicit signals? | `implicit_concept_encounter` vs `reader_claim_signal_inline` | Articles with implicit encounter also have more explicit signals |
| Are reviews producing reflection or rote dismissal? | `concept_review` `has_note` field over time | Note rate stays >20% (not declining toward zero) |
| Are voice notes being used? | `voice_note_added` frequency | >1 per week sustained |
| Are research results being viewed? | `research_result_viewed` vs `research_triggered` | >50% of triggered results get viewed |
| Is reading depth increasing over time? | `reader_close` `final_depth` over weeks | More "sections"/"full" depth as user builds knowledge |
| Does the app retain daily usage? | `session_start` timestamps | >5 sessions per week sustained through week 4 |
