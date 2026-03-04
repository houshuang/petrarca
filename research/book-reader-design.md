# Plan: Book Reader — "The Argument Unfolds"

## Context

Petrarca serves articles well (Mode A: "Firehose") but has no support for books (Mode B: "Deep Shelf"). The design-vision.md explicitly identifies this gap: books need context restoration, AI enhancement, voice notes linked to passages, and synthesis across time. The user reads widely across history, cultural theory, classical philology — books are where enduring knowledge lives.

**Two key user insights shape this design:**
1. **Chapters are too big as reading units.** A chapter can be 20-40 pages. The reading unit should be **sections within chapters** — 5-15 minute reads, like article sections. You might read 2-3 sections in a session, not a whole chapter.
2. **Multiple books on the same topic simultaneously.** Reading Pirenne, Huizinga, and Tuchman about the Middle Ages at the same time. The system should connect claims ACROSS books, not just within one book.

The innovation: **books are broken into section-sized passages that live alongside articles in one unified knowledge stream**. The system tracks argument arcs across chapters and across books on the same topic. A passage from Huizinga about medieval violence surfaces a connection to what Tuchman said about warfare — and to an article you clipped last week.

## Core Design: Sections as Reading Units

### The Section Model

A book chapter is split into **sections** (at H2/H3 boundaries, or by the LLM identifying logical breakpoints in chapters without headings). Each section becomes a **BookSection** — roughly equivalent to an article in the reading experience:

- Has its own claims, summary, key terms
- Has its own reading state (unread → briefing → reading → reflected)
- Appears in the feed alongside articles when relevant
- Can be read independently in 5-15 minutes

A chapter is just a grouping of sections. A book is a grouping of chapters.

### The Topic Shelf

Instead of organizing by book, the primary view is by **topic**. When reading about the history of Sicily, you see:

```
── History of Sicily ──────────────────────
📖 The Sicilian Vespers (Runciman)
   Ch 3, §2: "The Angevin Administration"    5 min
📖 A History of Sicily (Finley & Mack Smith)
   Ch 7, §1: "Norman Consolidation"          8 min
📰 "Modica's Baroque Heritage" (article)     3 min
📖 The Sicilian Vespers (Runciman)
   Ch 3, §3: "Seeds of Revolt"               6 min

[▸ The argument so far across these books...]
```

The system interleaves book sections with articles on the same topic. You read what's relevant to your current exploration, drawing from multiple books and articles. This is **incremental reading applied to books** — you don't finish one book before starting another; you weave through them by topic.

### Five Moments of Engagement

#### 1. The Briefing (before starting a book)

When a book is added, the system processes the TOC + introduction/preface. The user sees:

- "What you bring" — matches book topics against existing concepts
- Chapter list with estimated section counts
- Topic connections to other books and articles already in the system
- "Start with Chapter 1" or "Jump to a specific chapter"

#### 2. Reading a Section

Each section uses the same progressive depth model as articles:

| Zone | Content |
|------|---------|
| **Briefing** | Section summary + "where this fits" in the chapter's argument + connections to previous sections and other books |
| **Key Claims** | Claims with source passages. Cross-book connections: "Compare with Tuchman's claim in Ch 7..." |
| **Key Terms** | Author's definitions (with "I've seen this defined differently" when another book uses the same term differently) |
| **Full Text** | Section content with highlighting, voice notes, text notes |

The briefing zone shows **cross-book connections**: if Pirenne makes a claim about trade routes in section 3.2, and Tuchman makes a related claim in section 7.1, the briefing for Tuchman 7.1 says "Pirenne argued [X] about this — watch how Tuchman's evidence differs."

#### 3. The Pause (between sections, lightweight)

After completing a section, a small reflection prompt:
- System-generated one-sentence takeaway from your signals
- Optional: tap to refine, or record a voice note
- **No full-screen interruption** — just a card at the bottom, same weight as an article completion

Between chapters (not just sections), a slightly bigger pause:
- "The Argument So Far" for this chapter
- Connection to the book's developing thesis

#### 4. Where Was I? (context restoration)

On return after 2+ days, show per-topic:
- "You were reading about [topic] across [N books/articles]"
- Your personal thread entries, grouped by topic
- The section you were last in, with your last highlight
- Next recommended sections across all books on this topic

#### 5. Cross-Book Synthesis (the big payoff)

When you've read sections from multiple books on the same topic, the system generates **topic-level synthesis** that weaves across books:

- "Runciman emphasizes the economic causes of the Vespers, while Finley focuses on cultural identity. Your highlights suggest you found the economic argument more convincing."
- Shows where authors agree, disagree, or talk past each other
- Shows which claims you found new vs. already knew — across all books

## How Cross-Book Connections Work

The concept model already handles cross-article connections. Books extend this:

1. **Claim matching across books**: When processing Book B section 4.2, match claims against ALL existing claims (from books AND articles). Flag high-similarity pairs as connections.
2. **Shared key terms**: When two books define the same term differently, create a "definitional tension" concept note automatically.
3. **Topic clustering**: Books are tagged with topics at the chapter/section level. Sections from different books with overlapping topics surface together.
4. **The argument graph spans books**: If Pirenne's claim M3 in Ch 2 contradicts Tuchman's claim M1 in Ch 5, the system knows and shows this relationship.

Book concepts get longer initial review intervals (14 days vs 1-7 for articles). Connection indicators in the article reader show "Also explored in [Book], Ch 3, §2".

## Data Structures

### New types in `app/data/types.ts`

```typescript
interface Book {
  id: string;
  title: string;
  author: string;
  cover_url?: string;
  chapters: BookChapterMeta[];  // lightweight chapter list
  topics: string[];
  thesis_statement?: string;
  running_argument: string[];   // one sentence per chapter processed
  language: string;
  added_at: number;
}

interface BookChapterMeta {
  chapter_number: number;
  title: string;
  section_count: number;
  processing_status: 'pending' | 'completed';
}

// A section is the reading unit — equivalent to an article
interface BookSection {
  id: string;                  // book_id:ch{N}:s{M}
  book_id: string;
  chapter_number: number;
  section_number: number;
  title: string;               // section heading
  chapter_title: string;       // parent chapter title
  content_markdown: string;
  summary: string;
  briefing: string;            // personalized: argument context + cross-book connections
  claims: BookClaim[];
  key_terms: KeyTerm[];
  cross_book_connections: CrossBookConnection[];
  word_count: number;
  estimated_read_minutes: number;
}

interface BookClaim {
  claim_id: string;            // M1, S1, etc. (scoped to section)
  text: string;
  claim_type: string;
  confidence: number;
  source_passage?: string;     // verbatim quote
  supports_claim?: string;     // for subclaims
  is_main: boolean;
}

interface KeyTerm {
  term: string;
  definition: string;          // as the author uses it
  conflicts_with?: string;     // if another book defines it differently
}

interface CrossBookConnection {
  target_section_id: string;   // section in another book
  target_book_title: string;
  target_claim_text: string;
  relationship: 'agrees' | 'disagrees' | 'extends' | 'provides_evidence' | 'same_topic';
}

// Reading state — per section, like articles
interface BookReadingState {
  book_id: string;
  section_states: Record<string, SectionReadingState>;  // keyed by section_id
  total_time_spent_ms: number;
  last_read_at: number;
  personal_thread: PersonalThreadEntry[];
}

interface SectionReadingState {
  depth: 'unread' | 'briefing' | 'claims' | 'reading' | 'reflected';
  scroll_position_y: number;
  time_spent_ms: number;
  last_read_at: number;
  claim_signals: Record<string, ClaimSignalType>;
}

interface PersonalThreadEntry {
  id: string;
  book_id: string;
  section_id: string;
  created_at: number;
  type: 'reflection' | 'voice_note' | 'claim_reaction' | 'connection';
  text: string;
  voice_note_id?: string;
  claim_id?: string;
  linked_concept_ids?: string[];
}
```

## Server Pipeline

### `scripts/ingest_book_petrarca.py` (new, adapted from `otak/ingest_book.py`)

1. **Parse EPUB/PDF** via pymupdf (reuse otak's `parse_book()`)
2. **Split chapters into sections** at H2/H3 boundaries (reuse bookifier's `_chunk_at_h2` pattern). For chapters without headings, use Gemini Flash to identify logical breakpoints (~1500-3000 words per section
3. **Process sections with deep extraction** (adapted from otak's `BOOK_EXTRACTION_SCHEMA`): claims, key terms per section; argument links at chapter level
4. **Cross-book matching**: when processing Book B, match its claims against ALL existing book claims and article claims to find connections
5. **Generate briefings** per section, incorporating cross-book connections and user's concept state
6. **Output**: `books/{book_id}/meta.json` + `books/{book_id}/ch{N}_sections.json` — served via nginx

### Processing strategy
- On book add: process TOC + Chapter 1 sections
- On Chapter N completion: process Chapter N+1 sections in background
- Gemini Flash for section extraction (cheap, fast — ~$0.01/chapter)
- Anthropic for book completion synthesis (once per book, worth the quality)

### Cross-book claim matching
After extracting claims from a section, run a lightweight similarity pass:
- For each claim, compare against all claims from other books/articles on overlapping topics
- Use content-word overlap (same as existing concept matching) — no embeddings needed for MVP
- Store matches as `CrossBookConnection` on the section

## Files to Modify/Create

| File | Action |
|------|--------|
| `app/data/types.ts` | Add Book, BookSection, BookClaim, BookReadingState, PersonalThreadEntry, CrossBookConnection, KeyTerm |
| `app/data/store.ts` | Add book/section state management (following existing module-level pattern) |
| `app/data/content-sync.ts` | Extend sync for books (per-book JSON, chapter-level fetching) |
| `app/app/book-reader.tsx` | **New** — section reader, reusing MarkdownText/highlighting/voice from reader.tsx |
| `app/app/library.tsx` | Add "Shelf" view with topic-grouped book sections + progress |
| `app/app/_layout.tsx` | Add book-reader route |
| `scripts/ingest_book_petrarca.py` | **New** — adapted from `otak/ingest_book.py` with section splitting |
| `scripts/research-server.py` | Add `/ingest-book` endpoint |

### Key code to reuse
- `otak/scripts/ingest_book.py`: `parse_book()`, `BOOK_EXTRACTION_SCHEMA`, `BOOK_SYSTEM_PROMPT`, endnote parsing
- `app/app/reader.tsx`: MarkdownText, VoiceRecordButton/TextNoteInput, highlight system, claim signal cards, FloatingDepthIndicator, scroll tracking, ConnectionIndicator
- `app/data/store.ts`: concept matching logic (`processClaimSignalForConcepts`), AsyncStorage persistence pattern
- `scripts/build_articles.py`: `_call_llm()` (Gemini/Anthropic)

## Implementation Phases

### Phase 1: Pipeline + Data (2 days)
- Add types to types.ts
- Create `ingest_book_petrarca.py`: pymupdf parsing → section splitting → Gemini extraction → cross-book matching
- Test with an EPUB from Calibre Library or a Sicily history book
- Serve section JSON via nginx

### Phase 2: Section Reader MVP (2 days)
- `book-reader.tsx` with briefing → claims → key terms → full text zones
- Reuse MarkdownText, highlighting, voice notes from reader.tsx
- Section completion with lightweight reflection prompt
- Cross-book connection indicators ("Tuchman argues differently in Ch 7...")

### Phase 3: Topic Shelf + Navigation (1 day)
- "Shelf" view in library.tsx, grouped by topic
- Interleaved book sections + articles on same topic
- Book landing page with chapter/section map
- Context restoration on return (>2 days)

### Phase 4: Knowledge Integration (1-2 days)
- Book claims → concept model (same matching as articles)
- Cross-references between books/articles in connection indicators
- Book concepts in review queue with 14-day initial intervals
- "Argument So Far" per chapter and per book

### Phase 5: Multi-Book Synthesis (1-2 days)
- Cross-book topic synthesis: "Runciman emphasizes economics, Finley emphasizes culture"
- Book completion synthesis (Anthropic, once per book)
- "What to Read Next" from research agents

## Verification

1. Get a Sicily history EPUB (e.g., from Dropbox, Calibre, or download one)
2. Run `ingest_book_petrarca.py path/to/book.epub` — verify sections extracted with claims, key terms
3. Add a second book on overlapping topic → verify cross-book connections generated
4. Open app on web → Library Shelf shows topic-grouped sections from both books + existing Sicily articles
5. Open a section → see briefing with cross-book context → claim cards with source passages
6. Mark some claims → complete section → reflection prompt appears
7. Check that book claims created concepts appearing in article reader connections
8. Close app, reopen after 2+ days → context restoration shows personal thread
9. `npx tsc --noEmit` — no type errors
10. `npx expo export --platform web` — builds cleanly
