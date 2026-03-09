# Petrarca User Guide

*How to actually use this thing — flows, integrations, and what everything does. March 9, 2026.*

> **Web version**: This guide is also available as a styled HTML page at `/guide/` in the web app, or `app/public/guide/index.html` in the repo. There's a "Guide" link in the Feed tab header. When updating this guide, also update the HTML version to keep them in sync.

---

## The Big Picture

Petrarca is a read-later system that models what you know. Content flows in from multiple sources (Twitter bookmarks, Readwise Reader, Chrome web clipper, email forwarding, link ingest from the reader, topic research), gets processed by Gemini Flash on a server every 4 hours, and arrives in the app as structured articles with summaries, atomic claims, interest topics, novelty scores, entity annotations, and follow-up research questions. As you read, the system automatically tracks what you've encountered and uses FSRS-based memory decay to determine which claims are still "known" vs forgotten — shaping what gets highlighted as new in future articles.

The loop:

```
Capture (bookmark/clip/email/link ingest/topic research) → Pipeline processes (every 4h) →
Content appears in app → You browse, swipe, read →
Knowledge model updates automatically → Familiar paragraphs dim →
Feed re-ranks based on novelty and interest
```

---

## Part 1: Getting Content In

You have seven ways to feed Petrarca. They all end at the same place: `import_url.py` on the server, which fetches the article, extracts text, runs it through Gemini Flash for structuring (summary, claims, sections, topics, entities, follow-up questions), and adds it to the content pool.

### Twitter Bookmarks (Automatic)

**What to do**: Just bookmark tweets as you normally do. That's it.

**What happens**: Every 4 hours, a cron job on the Hetzner server fetches your recent Twitter bookmarks via the twikit library. If a bookmarked tweet contains a URL to an article, the pipeline fetches that article, processes it with Gemini Flash, and adds it to the content pool. Tweet threads are reconstructed by following `in_reply_to` chains. Next time you open the app, it syncs.

**Lag time**: Up to 4 hours from bookmark to appearance in your feed.

**Gotchas**:
- The Twitter cookie auth expires periodically. If new bookmarks stop appearing, SSH into the server and refresh the cookies.
- Not every bookmarked tweet has a fetchable article URL. Tweet-only bookmarks (no link) are silently skipped.
- Some URLs are paywalled or JS-heavy and won't extract well. The pipeline tries multiple extraction methods (trafilatura, requests with browser headers) but some sites resist.

### Readwise Reader (Automatic)

**What to do**: Save articles to Readwise Reader as you normally do (via their browser extension, share sheet, RSS feeds, etc.).

**What happens**: The same 4-hour cron fetches your Readwise items via their API. The pipeline processes them identically to Twitter bookmarks.

**Why both?** Twitter bookmarks catch spontaneous discoveries. Readwise catches your more deliberate saves and RSS reading. Together they cover your "accidental" and "intentional" reading inputs.

### Chrome Web Clipper (Immediate)

**What to do**: When you're reading something interesting in Chrome, either:
1. **Click the floating button** (bottom-right corner of every page), or
2. **Click the Petrarca icon** in the Chrome toolbar (or press **Cmd+Shift+S**), then click "Save to Petrarca"

**What happens**: The extension sends the URL (plus extracted page content and any selected text) to the server's `/api/clip` endpoint. The server runs `import_url.py` to process it. The article appears in your feed on next sync.

**Features**:
- **Selected text is captured**: If you select a passage before clipping, that selection is sent along as a highlight/annotation.
- **Topic detection**: The extension extracts topic tags from the page's meta tags, which appear in the popup.
- **Add a note**: Click the "Add note" toggle in the popup to attach a comment before saving.
- **Settings**: Click the gear icon to configure server URL and auth token.

**To install**: Go to `chrome://extensions`, enable Developer Mode, click "Load unpacked", and select the `clipper/` directory. No Chrome Web Store needed.

### Email Forwarding (Immediate)

**What to do**: Forward any email (newsletter, article link, interesting thread) to the configured Petrarca email address.

**What happens**: A Cloudflare Email Worker receives the forwarded email, extracts URLs from the content, and posts them to the Hetzner server's `/ingest-email` endpoint. The server runs `import_url.py` on each extracted URL.

**Best use cases**:
- **Newsletters**: Forward a Substack or other newsletter. The "View in browser" link gets extracted and processed.
- **Someone emails you an article**: Forward it to Petrarca.
- **Quick capture from phone**: See something interesting in your email? Forward it.

**Gotchas**:
- The email parser filters out tracking URLs (mailchimp, sendgrid, etc.) and image links. It looks for the most "article-like" URLs.
- Maximum 3 URLs processed per email.

### Manual URL Import (Developer)

If you're at a terminal: `ssh alif` then `cd /opt/petrarca && .venv/bin/python3 scripts/import_url.py "https://example.com/article" --tag manual`

### Link Auto-Ingest from Reader (Immediate)

**What to do**: While reading an article, tap any link in the text.

**What happens**: The URL is sent to the server's `/ingest` endpoint and processed in the background. An inline badge shows the ingest status. The article will appear in your feed after processing — no need to leave the app or copy-paste URLs.

### Topic Research (On-Demand)

**What to do**: On the Topics tab, expand any topic and tap the "↗ Find more on [Topic]" button.

**What happens**: Gemini search grounding finds real articles on that topic from the open web — not hallucinated URLs, but actual Google-discovered pages. The top 3 results are auto-ingested into your pipeline and will appear in your feed after processing.

---

## Part 2: The App — Four Tabs

On launch, the app checks the server for new content by comparing a manifest hash. If the hash changed (pipeline ran, new articles arrived), it downloads the updated content and merges it with your existing state. Your reading progress and signals are stored locally and never lost.

The app has four tabs: **Feed**, **Topics**, **Queue**, **Log**.

### Feed Tab

A scrollable list of articles, ranked by a combination of interest match, freshness, discovery bonus, variety, and novelty (curiosity score from the knowledge engine). Each entry shows:

- **Title** and one-line summary
- **Best claim preview** (green left border) — the highest-specificity novelty claim, giving you a taste of what's new
- **Novelty hint**: "3 new claims" in green if the knowledge engine has scored the article
- **Topic tags** on the right
- **Metadata**: hostname, author, read time estimate

**Swipe gestures**:
- **Swipe left** → Queue (green, adds to your reading queue)
- **Swipe right** → Dismiss (rubric red, hides from feed)

**"Continue Reading" section** appears at the top when you have articles in progress, showing a progress bar based on time spent.

**Topic filter chips**: A horizontal scroll row of the most common topics in your feed. Tap to filter; tap again (or "All") to show everything.

### Topics Tab

Articles grouped by primary topic. Each topic is a collapsible cluster with article count. Useful when you want to explore a specific interest area. Topics show reading state with colored dots (grey = unread, rubric = reading, green = read) and a count breakdown.

When the knowledge engine is ready, topics can show delta reports — a summary of what's new across all articles in that topic.

Each expanded topic has a **"↗ Find more on [Topic]"** button that triggers topic research via Gemini search grounding, auto-ingesting the top 3 results.

### Queue Tab

Your explicit reading list. Articles you've swiped left to queue from the Feed show here in order. Swipe right to remove. The queue is persisted to AsyncStorage and survives app restarts.

### Log Tab (Activity Log)

A vertical timeline of everything happening in the system. Reading sessions, pipeline runs, research dispatches, interest signals — all in one chronological view.

**What you see**: Colored dots per event type, ✦ markers for interest signals, day separators grouping events. Each entry shows a timestamp, event description, and relevant context.

**Filter toggles**: All / Reading / System / Research — tap to narrow the timeline to what you care about.

**Paging**: Loads the last day of events first, then fetches the previous 7 days in the background. Keeps the initial load fast.

**File**: `app/app/(tabs)/log.tsx`

---

## Part 3: The Reader

Tap any article to open the reader. The reader presents the full article with intelligent paragraph dimming based on the knowledge engine's assessment of what you already know, entity annotations, cross-article connections, and follow-up research prompts.

### Three Reading Modes

A mode toggle at the top of the reader lets you switch between:

1. **Full**: The complete article, no filtering. All paragraphs at full opacity.
2. **Guided**: Familiar paragraphs are dimmed (reduced opacity) based on claim similarity to things you've already read. Novel content stays prominent. Novel and mostly-novel paragraphs get a 2px green left border to draw the eye. You see everything but your eye is drawn to what's new.
3. **New Only**: Familiar paragraphs are collapsed entirely, showing only a "skip" indicator. Only genuinely novel sections are expanded. Novel paragraphs get the same green left border. The fastest way to extract new information from an article.

The dimming is automatic — it comes from the knowledge engine comparing the article's atomic claims against claims you've previously encountered, using embedding similarity and FSRS-based memory decay.

### Reader Structure

- **Header**: Title, author, source, date, ☆ bookmark toggle, and ⋯ menu
- **Summary**: One-paragraph overview
- **Mode toggle**: Full / Guided / New Only
- **Article body**: Full markdown-rendered content with paragraph-level dimming and entity underlines
- **Highlighting**: Long-press any paragraph to highlight it (amber border, haptic feedback on mobile). Highlights are persisted and can be toggled off.
- **Claims card**: Atomic claims extracted from the article
- **✦ FURTHER INQUIRY**: Follow-up research questions generated by the pipeline
- **✦ CONNECTED READING**: Cross-article connections based on shared claims
- **Related articles**: Same Topic / Shared Concepts / Same Source
- **Footer bar**: Done button + "UP NEXT" showing next queued article title (tap to go directly), or "← Back to feed" if queue is empty
- **Post-read interest card**: After tapping "Done", a bottom sheet appears with hierarchical topic feedback

### ☆ Bookmark and ⋯ Menu

The reader header has two action elements alongside the title:

**☆ Bookmark**: Tap to toggle bookmark status. Persisted across sessions.

**⋯ Menu**: Opens a dropdown with:
- **Article info** — metadata, word count, source
- **Open source** — opens the original URL
- **Ask AI** — opens a bottom-sheet chat modal (see below)
- **Voice note** — starts recording a voice memo (see below)
- **Research topic** — spawns background research on the article's topic

### Entity Deep-Dive

The pipeline extracts 3-8 entities per article — people, books, concepts, companies, events, places, technologies. In the reader, entity mentions appear with **dotted underlines**. If the entity was also a hyperlink in the original article, the underline is rubric-colored.

**What to do**: Tap an underlined entity name.

**What happens**: A marginalia popup appears alongside the text with a synthesis of what the pipeline knows about that entity — a compact description drawn from the article context. If the entity was also a link in the original article, the URL appears in the popup as a tappable link, and the popup offers smart actions:

- **"Save article"** — appears for article-like URLs (blog posts, announcements). Auto-ingests the linked page into your feed.
- **"Research more"** — always available. Spawns background research via Gemini search grounding, passing the URL as context. Better than raw page scraping for product pages, landing pages, and other thin content.

This means entity mentions always win over plain links. If "SWE-bench" is both a link to `swebench.com` and a pipeline-extracted concept, tapping it shows you the entity synthesis with the URL as context — not a raw redirect.

### Follow-Up Research Prompts

The pipeline generates 2-3 curiosity questions per article — things a curious reader might want to explore next.

**Where**: The **"✦ FURTHER INQUIRY"** section appears at the end of the reader, after the claims card.

**What to do**: Tap any question.

**What happens**: The question spawns topic research via Gemini search grounding — finding real articles on the web and auto-ingesting them. The results appear in your feed after processing.

### AI Chat

**What to do**: Tap "Ask AI" from the ⋯ menu, or tap "Research more" from an entity popup.

**What happens**: A bottom-sheet chat modal opens. The AI (Gemini Flash on the server) has full article context — title, summary, claims, topics, and truncated article text. You can ask follow-up questions, request explanations, or explore tangents. Supports threaded conversation. When opened from an entity popup, the question is pre-filled with entity context.

### Voice Feedback

**What to do**: Tap "Voice note" from the ⋯ menu while reading.

**What happens**: The app starts recording locally. When you stop, the audio is uploaded to the server, transcribed via Soniox, and then Gemini extracts structured actions from the transcript — things like "research this topic", "tag this article as X", "remember that Y". The extracted actions appear as tappable chips with status tracking.

**The flow**: Record locally → upload to server → Soniox transcription → Gemini action extraction → tappable action cards.

### Cross-Article Connections

Two surfaces show how the current article connects to others:

1. **Inline annotations**: Below paragraphs that share claims with other articles, you'll see "Also in: [article title]" links (max 2 per paragraph). These are based on cosine similarity ≥0.78 between claims.

2. **"✦ CONNECTED READING" section**: At the bottom of the reader, up to 5 related articles with shared claim counts and "+ Queue" buttons (LIFO insertion — the queued article goes to the top of your queue).

### Related Articles

Below cross-article connections, three groups of related articles appear:

- **Same Topic**: Other articles sharing the primary topic
- **Shared Concepts**: Articles connected via embedding similarity in the knowledge index — these might not share an explicit topic but cover related ground
- **Same Source**: Other articles from the same publication/domain

Max 3 per group, deduplicated across groups.

### Scroll-Aware Encounter Tracking

Reading progress is tracked by scroll depth, not just the "Done" button. If you scroll through 60% of an article, claims in the first 60% are marked as encountered in the knowledge ledger. Engagement level is determined by time: 'read' (>60s in the article) or 'skim' (≤60s). Tapping "Done" marks all claims regardless of scroll position.

### Hierarchical Topic Feedback (Post-Read)

After tapping Done, the PostReadInterestCard appears as a bottom sheet. It now shows a **tree display** of topics: broad → specific → entity levels. Each level has +/- buttons for independent feedback.

**Smart expand**: If there are ≤2 broad categories, they auto-expand so you see the specific topics immediately. Signals are level-specific — tapping + on a specific topic doesn't cascade up to the broad category or down to entities.

### Micro-Delights

- **Pull-to-refresh**: A rotating ✦ ornament (rubric-colored, 1200ms loop) replaces the default spinner
- **Claim reveal**: Claims slide up with a staggered 80ms animation in the claims card
- **Completion flash**: A gold (#c9a84c) sweep runs across the progress bar when you tap Done (600ms duration)

### Footer Bar

The old floating "Done" button was replaced with a persistent footer bar:
- **Done button** on the left
- **"UP NEXT"** on the right, showing the title of the next queued article — tap to go directly to it
- If the queue is empty, shows **"← Back to feed"** instead

### What's Tracked Automatically

The reader logs without you doing anything:
- Scroll position (saved every 2 seconds — leave and come back to exactly where you were)
- Scroll depth for claim encounter tracking
- Time spent reading
- Reading mode changes
- Which paragraphs were visible (for implicit encounter tracking)

When you finish an article (tap Done), `markArticleEncountered` runs — all claims in the article enter your knowledge ledger with FSRS stability values, so future articles covering the same ground will show as familiar.

### Signals You Can Give

| Signal | Where | What it does |
|--------|-------|-------------|
| Long-press highlight | Reader body | Marks a paragraph as interesting, persisted |
| +/- on topic tree (post-read) | Post-read card | Adjusts interest model — level-specific, affects feed ranking |
| Reading mode choice | Reader toggle | Logged for analytics |
| Swipe to queue (from feed) | Feed | Explicit interest signal |
| Swipe to dismiss (from feed) | Feed | Negative interest signal |
| Entity long-press | Reader body | Opens entity info + research option |
| Voice note | Reader (⋯ menu) | Records thought, extracts actions |
| Ask AI | Reader (⋯ menu) | Opens contextual chat |
| Research question tap | Reader (FURTHER INQUIRY) | Spawns background research |
| Topic research | Topics tab | Finds and ingests real articles |
| Link ingest | Reader body | Auto-ingests linked URL |

---

## Part 4: The Knowledge System

This is the core of what makes Petrarca different from a plain read-later app.

### How It Works

1. **Atomic decomposition**: When an article enters the pipeline, Gemini Flash decomposes it into 10-30 atomic claims — single facts or assertions that stand alone.
2. **Embedding**: Claims are embedded using Nomic-embed-text-v1.5 and stored in a vector index.
3. **Similarity**: When you read an article, its claims are compared against all claims you've previously encountered. High similarity = "you know this." Moderate similarity = "this extends what you know."
4. **FSRS decay**: Knowledge doesn't last forever. Each claim in your ledger has a stability value (in days). Over time, retrievability decays exponentially. A claim you read 30 days ago with stability of 30 days has ~37% retrievability — the system treats it as partially forgotten, not fully known.
5. **Classification**: Each claim is classified as NEW, KNOWN, or EXTENDS based on similarity scores and your current retrievability.

### Cross-Article Connections

The knowledge index powers cross-article connections in the reader. When two articles share claims with cosine similarity ≥0.78, they're linked — surfaced as inline "Also in" annotations and in the "✦ CONNECTED READING" section at the bottom of the reader.

### Topic Normalization

Topics go through a canonical registry with LLM-verified merge-or-create for new topics. When the same concept appears under different names ("machine learning" vs "ML" vs "statistical learning"), the normalization step merges them. Automatic defragmentation runs when categories exceed limits, keeping the topic space clean.

### Stability Values

Different engagement levels produce different stability (how long before the knowledge "fades"):
- **Skim** (article opened, scrolled): 9 days stability
- **Read** (article completed): 30 days stability
- **Highlight** (paragraph highlighted): 60 days stability
- **Reinforcement**: Re-encountering a claim multiplies its stability by 2.5x

### What You See

- **Paragraph dimming** in Guided/New Only modes — familiar paragraphs fade
- **Novel paragraph markers** in Guided/New Only modes — 2px green left border on novel content
- **Novelty hints** in the feed — "3 new claims" tells you how much is genuinely new
- **Curiosity score** affects feed ranking — articles with more novel claims float higher
- **Delta reports** on the Topics tab — summaries of what's new in a topic area
- **Cross-article connections** — inline "Also in" links and "✦ CONNECTED READING" section

---

## Part 5: Usage Patterns

### The 30-Second Check
Open the app. Scan the feed. Swipe-dismiss anything stale. Swipe-queue anything promising. Close.

### The 5-Minute Read
Tap an article. Use Guided mode — your eye goes straight to the new stuff (green-bordered paragraphs). Skim the dimmed paragraphs for context. Tap Done. Rate the topics.

### The 15-Minute Deep Read
Open a queued article in Full mode. Read it all. Highlight interesting paragraphs. Long-press an interesting entity to learn more. When done, the interest card helps you tell the system what mattered. Follow topic links or connected reading to related articles.

### The New-Only Speedrun
Switch to New Only mode. Only novel paragraphs are shown. Get the delta in 2 minutes. Great for articles in a domain you know well.

### The Voice Note
While reading, open the ⋯ menu and tap "Voice note". Record a quick thought — "I should look into this more", "this contradicts what I read last week", "tag this as important for the green party paper". Stop recording. The audio uploads, gets transcribed by Soniox, and Gemini extracts actions: research topics, tags, things to remember. The extracted actions appear as tappable chips you can act on later.

### The Research Rabbit Hole
You're reading an article and notice an underlined entity you want to know more about. Long-press it — a marginalia popup shows what the pipeline knows. Tap "Research more" — AI chat opens with context pre-filled. Ask your questions. Then scroll down to the "✦ FURTHER INQUIRY" section and tap a question that caught your eye. Gemini search finds real articles on the web, auto-ingests the top 3 into your pipeline. Next time you open the app, those articles are waiting in your feed, processed and ready.

---

## Part 6: The Content Pipeline

Understanding this helps you understand timing and quality.

### Every 4 Hours on the Server:
1. Fetch new Twitter bookmarks (twikit, GraphQL API, thread reconstruction)
2. Fetch new Readwise Reader items (API)
3. For each new URL:
   - a. Fetch article HTML with multi-tier fallback (trafilatura, requests + browser headers)
   - b. Clean the markdown (strips nav menus, cookie banners, subscribe cruft, normalizes headings)
   - c. Send to Gemini Flash for structuring: summary, one-line summary, sections, key claims, interest topics
   - d. Extract atomic claims (10-30 per article)
   - e. Extract entities (3-8 per article: person, book, concept, company, event, place, technology)
   - f. Generate follow-up questions (2-3 curiosity questions per article)
   - g. Normalize topics against the canonical registry (LLM-verified merge-or-create)
   - h. Run automatic defragmentation when registry exceeds limits
4. Update `articles.json`, `manifest.json`
5. nginx serves updated files on port 8083

### When You Open the App:
1. App checks manifest hash against cached version
2. If different: downloads new articles + knowledge index
3. Merges with existing state (your signals, highlights, queue all preserved)
4. Knowledge engine initializes, builds similarity lookup
5. New articles appear in feed, ranked by interest + novelty

### Content Quality:
- Most articles process well, especially long-form journalism, blog posts, and technical writing
- Some articles are low quality (very short tweets, paywalled stubs, donation pages)
- The `clean_markdown` step removes navigation, cookie banners, and subscribe cruft
- Gemini Flash catches most garbage but not all
- Wide net with some noise is the deliberate trade-off

---

## Part 7: Non-Obvious Features

1. **Knowledge is automatic.** You don't need to tap "knew this" buttons. Just reading an article updates your knowledge ledger. The FSRS decay handles forgetting naturally.

2. **Paragraph dimming is per-claim.** A paragraph might contain 3 claims — 2 known, 1 new. The dimming reflects the aggregate, not a binary known/unknown.

3. **Swipe left = queue, swipe right = dismiss.** This is intentional — your thumb naturally reaches right for the common action (dismiss), left for the deliberate one (save to queue).

4. **Topic chips after reading shape your whole feed.** The +/- signals on the post-read interest card have the highest weight (2.0) in the interest model. A single "+" on a topic meaningfully boosts related articles.

5. **The knowledge engine needs a knowledge index.** Paragraph dimming and novelty scores only work after the pipeline generates a knowledge index with embeddings. Without it, the reader falls back to full mode and the feed uses interest-only ranking.

6. **Feed ranking is multi-factor.** Interest match (40%) + freshness (25%) + discovery bonus (20%) + variety (15%), then re-ranked by curiosity score from the knowledge engine.

7. **The web clipper captures selected text.** Select a passage before clicking the clipper — that selection is saved as a highlight on the article.

8. **Scroll position is saved.** Every 2 seconds while reading, your position is saved. Leave and come back to exactly where you were.

9. **Continue Reading cards have progress bars.** The progress is based on time spent relative to estimated read time, capped at 95%.

10. **All interactions are logged.** Every tap, swipe, scroll, and mode change is logged to daily JSONL files via `logEvent()`. Logs live at `{documentDirectory}/logs/interactions_YYYY-MM-DD.jsonl`.

11. **Entity underlines absorb links.** If text is both an entity and a hyperlink, the entity popup wins — you see the synthesis plus the URL, not a raw redirect. Article-like URLs get a "Save article" button; product pages get "Research more" with the URL as context. The dotted underline turns rubric-colored when the entity has a URL.

12. **Voice note actions are smart.** After transcription, the LLM identifies intents: "research X", "tag this article as Y", "remember Z". Actions appear as tappable chips with status tracking, not just raw transcript text.

13. **Cross-article connections use claim similarity.** The "Also in" annotations and "✦ CONNECTED READING" section are based on cosine similarity ≥0.78 between article claims, not just shared topics. Two articles about completely different topics can be connected if they reference the same facts.

14. **The Activity Log shows everything.** Pipeline runs, reading sessions, interest signals, research dispatches — all in a chronological timeline with filters. Useful for understanding what the system has been doing while you were away.

15. **Related articles at the reader bottom find connections three ways.** Same topic, shared concepts (via embedding similarity in the knowledge index), and same source. Three different lenses on "what to read next."

---

## Part 8: Known Issues and Workarounds

| Issue | Workaround |
|-------|-----------|
| Some articles are low quality (donation pages, boilerplate) | Swipe to dismiss. The pipeline casts a wide net. |
| Twitter cookie auth expires | SSH to server, refresh cookies at `/root/.config/twikit/cookies.json`. |
| Full article shows raw markdown in some cases | The markdown renderer handles most cases but edge cases exist. |
| Knowledge engine not active | If no knowledge index is loaded, dimming and novelty scores don't appear. The pipeline needs to generate the index. |
| No push notifications | Rely on habit — open the app when you have reading time. |
| Content sync requires network | The app works offline with cached content but won't get new articles until it can reach the server. |
| Entity underlines may miss some mentions | The pipeline matches entity names against article text via string matching — may miss variant spellings or abbreviations. |
| Voice notes require network for transcription | Recording is local-first, but upload + transcription need connectivity. Pending uploads retry automatically. |

---

## Part 9: Quick Reference

### Keyboard Shortcuts
- **Cmd+Shift+S**: Open web clipper (Chrome)
- **Enter**: Save in clipper popup
- **Escape**: Close clipper popup

### Where Things Live
- **App (native)**: `exp://alifstian.duckdns.org:8082`
- **App (web)**: `http://alifstian.duckdns.org:8084`
- **Content server**: `http://alifstian.duckdns.org:8083/content/`
- **Research server**: port 8090
- **Server access**: `ssh alif`
- **Pipeline cron**: `/etc/cron.d/petrarca-refresh` (every 4 hours)
- **Server data**: `/opt/petrarca/data/`
- **Voice Notes browser**: accessible from Feed header "Notes" link, or per-article in article info

### Capture Methods Summary
| Method | What to do | Lag time | Notes |
|--------|-----------|----------|-------|
| Twitter bookmark | Bookmark a tweet | Up to 4 hours | Automatic, thread reconstruction |
| Readwise | Save in Readwise | Up to 4 hours | Automatic |
| Web clipper | Click button or Cmd+Shift+S | Immediate | Manual, captures selected text |
| Email forward | Forward to petrarca address | Immediate | Cloudflare worker, max 3 URLs |
| Manual URL | Run `import_url.py` on server | Immediate | Developer-only |
| Link ingest | Tap a link in the reader | Immediate | Auto-ingests linked URL |
| Topic research | "↗ Find more" on Topics tab | Background | Gemini search, auto-ingests top 3 |

### Signal Actions Summary
| Signal | Where | What it does |
|--------|-------|-------------|
| Swipe left (queue) | Feed | Adds to reading queue, positive interest signal |
| Swipe right (dismiss) | Feed | Hides from feed, negative interest signal |
| Long-press highlight | Reader | Saves highlighted paragraph |
| Topic tree +/- | Post-read card | Adjusts interest model (weight 2.0), level-specific |
| Read article | Reader (Done) | All claims enter knowledge ledger with FSRS stability |
| Reading mode change | Reader | Logged for analytics |
| Open article | Feed/Topics/Queue | Interest signal (weight 0.5) |
| Entity long-press | Reader | Opens entity info + research option |
| Voice note | Reader (⋯ menu) | Records thought, extracts actions |
| Ask AI | Reader (⋯ menu) | Opens contextual chat |
| Research question tap | Reader (FURTHER INQUIRY) | Spawns background research |
| Topic research | Topics tab | Finds and ingests real articles |
| Link ingest | Reader | Auto-ingests linked URL |

### The Four Tabs
| Tab | What it shows |
|-----|--------------|
| Feed | Ranked article list, swipe gestures, topic filters, continue reading |
| Topics | Articles grouped by topic, delta reports, topic research |
| Queue | Your explicit reading list, ordered |
| Log | Activity timeline — reading, system, research events with filters |

---

*This guide reflects the system as of March 9, 2026. Petrarca is in active development — the knowledge system, entity deep-dive, and cross-article connections are the current focus.*
