# Petrarca User Guide

*How to actually use this thing — flows, integrations, and what everything does. March 8, 2026.*

> **Web version**: This guide is also available as a styled HTML page at `/guide/` in the web app, or `app/public/guide/index.html` in the repo. There's a "Guide" link in the Feed tab header. When updating this guide, also update the HTML version to keep them in sync.

---

## The Big Picture

Petrarca is a read-later system that models what you know. Content flows in from multiple sources (Twitter bookmarks, Readwise Reader, Chrome web clipper, email forwarding), gets processed by Gemini Flash on a server every 4 hours, and arrives in the app as structured articles with summaries, atomic claims, interest topics, and novelty scores. As you read, the system automatically tracks what you've encountered and uses FSRS-based memory decay to determine which claims are still "known" vs forgotten — shaping what gets highlighted as new in future articles.

The loop:

```
Capture (bookmark/clip/email) → Pipeline processes (every 4h) →
Content appears in app → You browse, swipe, read →
Knowledge model updates automatically → Familiar paragraphs dim →
Feed re-ranks based on novelty and interest
```

---

## Part 1: Getting Content In

You have five ways to feed Petrarca. They all end at the same place: `import_url.py` on the server, which fetches the article, extracts text, runs it through Gemini Flash for structuring (summary, claims, sections, topics), and adds it to the content pool.

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

---

## Part 2: The App — Three Tabs

On launch, the app checks the server for new content by comparing a manifest hash. If the hash changed (pipeline ran, new articles arrived), it downloads the updated content and merges it with your existing state. Your reading progress and signals are stored locally and never lost.

The app has three tabs: **Feed**, **Topics**, **Queue**.

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

### Queue Tab

Your explicit reading list. Articles you've swiped left to queue from the Feed show here in order. Swipe right to remove. The queue is persisted to AsyncStorage and survives app restarts.

---

## Part 3: The Reader

Tap any article to open the reader. The reader presents the full article with intelligent paragraph dimming based on the knowledge engine's assessment of what you already know.

### Three Reading Modes

A mode toggle at the top of the reader lets you switch between:

1. **Full**: The complete article, no filtering. All paragraphs at full opacity.
2. **Guided**: Familiar paragraphs are dimmed (reduced opacity) based on claim similarity to things you've already read. Novel content stays prominent. You see everything but your eye is drawn to what's new.
3. **New Only**: Familiar paragraphs are collapsed entirely, showing only a "skip" indicator. Only genuinely novel sections are expanded. The fastest way to extract new information from an article.

The dimming is automatic — it comes from the knowledge engine comparing the article's atomic claims against claims you've previously encountered, using embedding similarity and FSRS-based memory decay.

### Reader Structure

- **Header**: Title, author, source, date, and a link to the original article
- **Summary**: One-paragraph overview
- **Mode toggle**: Full / Guided / New Only
- **Article body**: Full markdown-rendered content with paragraph-level dimming
- **Highlighting**: Long-press any paragraph to highlight it (amber border, haptic feedback on mobile). Highlights are persisted and can be toggled off.
- **Post-read interest card**: After tapping "Done", a bottom sheet appears with topic chips (+/-) to shape your interest model

### What's Tracked Automatically

The reader logs without you doing anything:
- Scroll position (saved every 2 seconds — leave and come back to exactly where you were)
- Time spent reading
- Reading mode changes
- Which paragraphs were visible (for implicit encounter tracking)

When you finish an article (tap Done), `markArticleEncountered` runs — all claims in the article enter your knowledge ledger with FSRS stability values, so future articles covering the same ground will show as familiar.

### Signals You Can Give

| Signal | What it does |
|--------|-------------|
| Long-press highlight | Marks a paragraph as interesting, persisted |
| +/- on topic chips (post-read) | Adjusts interest model — affects feed ranking |
| Reading mode choice | Logged for analytics |
| Swipe to queue (from feed) | Explicit interest signal |
| Swipe to dismiss (from feed) | Negative interest signal |

---

## Part 4: The Knowledge System

This is the core of what makes Petrarca different from a plain read-later app.

### How It Works

1. **Atomic decomposition**: When an article enters the pipeline, Gemini Flash decomposes it into 10-30 atomic claims — single facts or assertions that stand alone.
2. **Embedding**: Claims are embedded using Nomic-embed-text-v1.5 and stored in a vector index.
3. **Similarity**: When you read an article, its claims are compared against all claims you've previously encountered. High similarity = "you know this." Moderate similarity = "this extends what you know."
4. **FSRS decay**: Knowledge doesn't last forever. Each claim in your ledger has a stability value (in days). Over time, retrievability decays exponentially. A claim you read 30 days ago with stability of 30 days has ~37% retrievability — the system treats it as partially forgotten, not fully known.
5. **Classification**: Each claim is classified as NEW, KNOWN, or EXTENDS based on similarity scores and your current retrievability.

### Stability Values

Different engagement levels produce different stability (how long before the knowledge "fades"):
- **Skim** (article opened, scrolled): 9 days stability
- **Read** (article completed): 30 days stability
- **Highlight** (paragraph highlighted): 60 days stability
- **Reinforcement**: Re-encountering a claim multiplies its stability by 2.5x

### What You See

- **Paragraph dimming** in Guided/New Only modes — familiar paragraphs fade
- **Novelty hints** in the feed — "3 new claims" tells you how much is genuinely new
- **Curiosity score** affects feed ranking — articles with more novel claims float higher
- **Delta reports** on the Topics tab — summaries of what's new in a topic area

---

## Part 5: Usage Patterns

### The 30-Second Check
Open the app. Scan the feed. Swipe-dismiss anything stale. Swipe-queue anything promising. Close.

### The 5-Minute Read
Tap an article. Use Guided mode — your eye goes straight to the new stuff. Skim the dimmed paragraphs for context. Tap Done. Rate the topics.

### The 15-Minute Deep Read
Open a queued article in Full mode. Read it all. Highlight interesting paragraphs. When done, the interest card helps you tell the system what mattered. Follow topic links to related articles.

### The New-Only Speedrun
Switch to New Only mode. Only novel paragraphs are shown. Get the delta in 2 minutes. Great for articles in a domain you know well.

---

## Part 6: The Content Pipeline

Understanding this helps you understand timing and quality.

### Every 4 Hours on the Server:
1. Fetch new Twitter bookmarks (twikit, GraphQL API, thread reconstruction)
2. Fetch new Readwise Reader items (API)
3. For each new URL:
   - Fetch article HTML with multi-tier fallback (trafilatura, requests + browser headers)
   - Clean the markdown (strips nav menus, cookie banners, subscribe cruft, normalizes headings)
   - Send to Gemini Flash for structuring: summary, one-line summary, sections, key claims, interest topics
   - Optionally extract atomic claims (10-30 per article)
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

### Capture Methods Summary
| Method | What to do | Lag time | Notes |
|--------|-----------|----------|-------|
| Twitter bookmark | Bookmark a tweet | Up to 4 hours | Automatic, thread reconstruction |
| Readwise | Save in Readwise | Up to 4 hours | Automatic |
| Web clipper | Click button or Cmd+Shift+S | Immediate | Manual, captures selected text |
| Email forward | Forward to petrarca address | Immediate | Cloudflare worker, max 3 URLs |
| Manual URL | Run `import_url.py` on server | Immediate | Developer-only |

### Signal Actions Summary
| Signal | Where | What it does |
|--------|-------|-------------|
| Swipe left (queue) | Feed | Adds to reading queue, positive interest signal |
| Swipe right (dismiss) | Feed | Hides from feed, negative interest signal |
| Long-press highlight | Reader | Saves highlighted paragraph |
| Topic chip +/- | Post-read card | Adjusts interest model (weight 2.0) |
| Read article | Reader (Done) | All claims enter knowledge ledger with FSRS stability |
| Reading mode change | Reader | Logged for analytics |
| Open article | Feed/Topics/Queue | Interest signal (weight 0.5) |

---

*This guide reflects the system as of March 8, 2026. Petrarca is in active development — the knowledge system and reading modes are the current focus.*
