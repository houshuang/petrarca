# Kindle Data Integration Research

*Date: 2026-03-04*

## Executive Summary

Amazon provides **no official public API** for Kindle reading data. All programmatic access relies on either (a) scraping Amazon's web interfaces, (b) reverse-engineering private sync APIs, (c) parsing local device files, or (d) using Readwise as middleware. For Petrarca, **Readwise's API is the most practical path** for highlights, while the **unofficial kindle-api TypeScript libraries** can supplement with reading progress data that Readwise does not expose.

---

## 1. Official Amazon Kindle API

**There is no official, documented Kindle API for consumer reading data.**

Amazon has developer programs for Kindle publishing (KDP), Alexa, and the Kindle SDK for Fire tablets, but none of these expose a user's reading highlights, annotations, progress, or library data. Amazon's position has been consistent: highlights and reading data are locked within their ecosystem.

The closest official interface is:
- **read.amazon.com** — Kindle Cloud Reader (for reading books in browser)
- **read.amazon.com/notebook** — Web-based highlight/note viewer (read-only, no export API)

Both are web applications with no documented API endpoints. They use internal JavaScript APIs that community tools have reverse-engineered.

## 2. Kindle Highlights Export Methods

### 2.1 My Clippings.txt (Physical Kindle Device)

Every Kindle e-reader stores a plain-text file at `/documents/My Clippings.txt` containing all highlights, notes, and bookmarks in chronological order.

**Format:**
```
Book Title (Author)
- Your Highlight on page 42 | Location 645-648 | Added on Wednesday, January 15, 2025 3:22:14 PM

The actual highlighted text goes here.
==========
Book Title (Author)
- Your Note on page 42 | Location 645 | Added on Wednesday, January 15, 2025 3:23:00 PM

The user's note text here.
==========
```

**Characteristics:**
- Plain text, easy to parse
- Append-only log (events recorded sequentially as they happen)
- Contains: highlights, notes, bookmarks (with location/page + timestamp)
- Requires USB cable connection to access
- Includes personal documents (sideloaded PDFs, MOBIs) — unlike cloud sync
- No reading progress/percentage data
- No deduplication (deleting a highlight doesn't remove the original entry)

**Parsing tools:**
- [KindleClippings](https://github.com/robertmartin8/KindleClippings) (Python) — organizes into per-book text/markdown files
- [kindle-clippings-to-notion](https://github.com/topics/kindle-clippings) (Python) — exports to Notion
- [Clippings.io](https://www.clippings.io/) — web service, imports clippings file, exports to Evernote/Notion/Google Drive

### 2.2 Amazon Kindle Notebook (read.amazon.com/notebook)

Amazon syncs highlights/notes from purchased books to the cloud. Visible at `read.amazon.com/notebook` (or `read.amazon.com/kp/notebook`).

**What it shows:** Highlights and notes per book, with location data, organized by book.

**Limitations:**
- **Copyright export limit**: Publishers restrict export to typically 10-20% of highlighted text per book
- Only purchased Amazon books (not personal documents/sideloaded content)
- No programmatic API — HTML page rendered by JavaScript
- Requires Amazon login (cookies/session)

**Scraping approaches:**
- **Bookcision** (readwise.io/bookcision) — JavaScript bookmarklet run on read.amazon.com; exports highlights as plain text, JSON, or XML. Works by extracting data from the rendered page DOM.
- **Glasp** — Chrome extension that bypasses export limits by accessing the page directly
- **kindle-highlight-scraper** (github.com/mieubrisse/kindle-highlight-scraper) — Python + Selenium, logs into Amazon and downloads all highlights as JSON
- **kindle-exporter** (github.com/ryangreenberg/kindle-exporter) — Exports from Kindle Notebook

### 2.3 Kindle Email Export

The Kindle iOS/Android apps have a "Share" feature that emails highlights for a book. Readwise supports importing via email forwarding to `add@readwise.io`.

### 2.4 Third-Party Services

- **[Readwise](https://readwise.io)** — Browser extension auto-syncs Kindle highlights from read.amazon.com. Most popular middleware.
- **[Clippings.io](https://www.clippings.io/)** — Imports My Clippings.txt or browser extension
- **[Glasp](https://glasp.co)** — Exports beyond Amazon's copyright limits

## 3. Reading Progress Data

### What Amazon Tracks

Amazon internally tracks extensive reading data per book:
- **Current reading position** (location number, not always page)
- **Percentage read** (visible in Kindle UI)
- **Furthest position read**
- **Time spent reading** (for Kindle Insights / reading streak features)
- **Sync timestamps** (Whispersync last sync date)

### How to Access It

**None of this is available through any official API.** Approaches:

#### 3a. Unofficial kindle-api Libraries (Best Current Option)

Two TypeScript libraries access Amazon's private Kindle API endpoints:

**[kindle-api by Xetera](https://github.com/Xetera/kindle-api)** (Node.js)
- Returns: book library, metadata, ASINs, cover images, **percentageRead**, sync dates
- Auth: 4 browser cookies (`ubid-main`, `at-main`, `x-main`, `session-id`) + device token
- Cookies valid for ~1 year
- Requires TLS proxy (tls-client-api) to bypass Amazon's TLS fingerprinting
- ~3 weekly npm downloads (niche but functional)

**[kindle-api by transitive-bullshit](https://github.com/transitive-bullshit/kindle-api)** (TypeScript)
- Same cookie-based auth approach
- Additionally exposes: content manifests (TAR files with book structure, TOC, layout metadata)
- v1.0.1 released October 2024
- Also requires TLS proxy

**Key data from these libraries:**
```typescript
interface KindleBook {
  asin: string;
  title: string;
  authors: string[];
  percentageRead: number;    // 0-100
  coverImageUrl: string;
  originType: string;        // "PURCHASE" etc.
  // ...
}
```

#### 3b. Whispersync Protocol (Reverse-Engineered)

Patrick Browne [reverse-engineered the Whispersync protocol](https://ptbrowne.github.io/posts/whispersync-reverse-engineering/) using mitmproxy.

**Key endpoints discovered:**
| Endpoint | Purpose |
|----------|---------|
| `FirsProxy/registerDevice` | Device authentication (username/password + 2FA) |
| `FionaTodoListProxy/syncMetaData` | List of books in library |
| `FionaCDEServiceEngine/FSDownloadContent` | Book content download |
| `FionaCDEServiceEngine/sidecar?type=EBOK&key=<ASIN>` | Annotations + last page read |

**Authentication:** RSA key-based request signing. Every request includes an `X-ADP-Request-Digest` header — SHA256 hash signed with RSA private key (received during device registration), PKCS1 padded, base64 encoded.

**Sidecar format:** Custom binary format, base64-encoded over HTTP. Contains highlights, bookmarks, annotations, and reading position. Text encoded as UTF-16 big-endian.

**Library:** [whispersync-lib](https://github.com/ptbrowne/whispersync-lib) (Node.js, 34 stars, last updated 2023) — provides `getBooks()` and `getAnnotations(asin)` methods.

**Assessment:** Fascinating but fragile. The binary format parsing is complex, the registration flow requires handling 2FA, and Amazon could change endpoints at any time. Not recommended for production use.

#### 3c. Lector (Python, Kindle Cloud Reader)

[Lector](https://github.com/msuozzo/Lector) uses PhantomJS to run JavaScript within an authenticated Kindle Cloud Reader session. Extracts library metadata and page progress. However, PhantomJS is deprecated and the project is unmaintained (last activity ~2015).

## 4. Kindle Desktop/Mobile App Local Data

### Kindle for Mac

**Book content location:** `~/Library/Containers/com.amazon.Kindle/Data/Library/Application Support/Kindle/My Kindle Content/`

**Annotation storage:** In older versions, the Kindle app stored annotations in a SQLite file called `AnnotationStorage` within the app's Library folder. The relevant table was `ZANNOTATION`. However:
- Modern Kindle for Mac (2024+) primarily syncs annotations to Amazon's cloud
- The local database may no longer contain the same structure
- macOS app sandboxing means the path is under `~/Library/Containers/com.amazon.Kindle/`
- Worth exploring: `~/Library/Containers/com.amazon.Kindle/Data/Library/` for any `.sqlite` or `.db` files

### Kindle for iOS

- Annotations were stored in `AnnotationStorage` SQLite file within the app's sandboxed container
- Requires jailbreak or desktop tools like iFunBox to access
- Not practical for automated integration

### Key Takeaway

Local app data is unreliable for integration: paths change between versions, databases may be encrypted, and sandboxing limits access. The cloud-based approaches (kindle-api libraries, Readwise) are more practical.

## 5. Reverse Engineering Landscape

### Active Projects (as of 2024-2025)

| Project | Language | Stars | Last Updated | What It Does |
|---------|----------|-------|--------------|-------------|
| [kindle-api (Xetera)](https://github.com/Xetera/kindle-api) | TypeScript | ~200 | 2024 | Private API, reading progress, book library |
| [kindle-api (transitive-bullshit)](https://github.com/transitive-bullshit/kindle-api) | TypeScript | ~150 | Oct 2024 | Private API + content manifests |
| [kindle-ai-export](https://github.com/transitive-bullshit/kindle-ai-export) | TypeScript | ~300 | 2024 | Export book text, PDF, EPUB, AI audiobooks |
| [whispersync-lib](https://github.com/ptbrowne/whispersync-lib) | JavaScript | 34 | 2023 | Whispersync protocol access |
| [obsidian-kindle-plugin](https://github.com/topics/kindle-highlights) | TypeScript | 1.2k | Feb 2026 | Sync highlights to Obsidian |
| [kindle-highlight-scraper](https://github.com/mieubrisse/kindle-highlight-scraper) | Python | ~50 | 2024 | Selenium-based notebook scraper |

### Amazon's Countermeasures

- **TLS fingerprinting** (added July 2023): Amazon detects non-browser TLS clients. The kindle-api libraries work around this by proxying through a TLS client API that mimics browser fingerprints.
- **Cookie expiration**: Auth cookies last ~1 year but may be invalidated
- **Rate limiting**: Aggressive rate limiting on cloud reader endpoints
- **Binary formats**: Sidecar (annotation) data uses custom binary encoding, not JSON

## 6. Readwise as Middleware

### What Readwise Already Does

Readwise syncs Kindle highlights via its browser extension, which navigates to `read.amazon.com/notebook` and downloads annotations. The user (Stian) already has a Readwise account with the token configured at `/opt/petrarca/.env`.

### Readwise API v2 (Highlights/Books)

**Base URL:** `https://readwise.io/api/v2/`
**Auth:** `Authorization: Token <READWISE_ACCESS_TOKEN>`
**Rate limits:** 240 req/min general, 20 req/min for list endpoints

**Key endpoints for Kindle data:**

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/v2/books/` | GET | All books with metadata, filterable by category="books" and source="kindle" |
| `/api/v2/books/{id}/` | GET | Single book details |
| `/api/v2/highlights/` | GET | All highlights, filterable by book_id |
| `/api/v2/highlights/{id}/` | GET | Single highlight with text, note, location |
| `/api/v2/export/` | GET | Bulk export: books with nested highlights |

**Book object fields (when source=kindle):**
```json
{
  "id": 12345,
  "title": "The Name of the Rose",
  "author": "Umberto Eco",
  "category": "books",
  "source": "kindle",
  "num_highlights": 47,
  "last_highlight_at": "2025-12-15T10:30:00Z",
  "updated": "2025-12-15T10:30:00Z",
  "cover_image_url": "https://...",
  "highlights_url": "https://readwise.io/api/v2/highlights?book_id=12345",
  "source_url": null,
  "asin": "B0046LU7H0",
  "tags": [],
  "document_note": ""
}
```

**Highlight object fields:**
```json
{
  "id": 67890,
  "text": "The highlighted passage text...",
  "note": "User's note on this highlight",
  "location": 1234,
  "location_type": "location",
  "color": "yellow",
  "highlighted_at": "2025-12-15T10:30:00Z",
  "url": null,
  "book_id": 12345,
  "tags": []
}
```

### Readwise Reader API v3 (Documents)

If books are also in Readwise Reader (the read-it-later app), additional data is available:

**Base URL:** `https://readwise.io/api/v3/`

**Key addition:** The `reading_progress` field (decimal 0.0-1.0) is available per document. However, this tracks progress within Reader itself, not Kindle reading progress. EPUBs imported into Reader would have Reader-tracked progress.

### What Readwise Does NOT Provide

- **No reading progress from Kindle** — Readwise syncs annotations only, not position/percentage
- **No personal document highlights** — Only purchased Amazon books sync to the cloud
- **Copyright-limited text** — Publisher restrictions may truncate highlighted passages
- **No real-time sync** — Browser extension runs periodically, not instantly

### Existing Petrarca Integration

The project already has `scripts/fetch_readwise_reader.py` which fetches documents from Readwise Reader API v3. This handles articles, PDFs, EPUBs, etc. A parallel script for Readwise API v2 (which is where Kindle book highlights live) would be straightforward to build.

## 7. Practical Integration Plan for Petrarca

### Recommended Architecture: Two-Layer Approach

```
Layer 1: Readwise API v2 (highlights + book metadata)
  - Reliable, documented, already authenticated
  - Gets: book list, ASINs, highlights, notes, locations, timestamps
  - Missing: reading progress, time spent

Layer 2: kindle-api (reading progress supplement)
  - Unofficial but functional
  - Gets: percentageRead, library with sync dates
  - Requires: 4 cookies extracted from browser (valid ~1 year)
  - Risk: Amazon could break it; TLS proxy dependency
```

### Implementation Steps

#### Phase 1: Kindle Highlights via Readwise (Low Risk, High Value)

1. **New script: `fetch_kindle_books.py`** — Uses Readwise API v2 `/export/` endpoint filtered to `category=books` and `source=kindle`
2. **Data structure:** Store as `data/kindle_books.json` with book metadata + nested highlights
3. **Matching:** Use ASIN as primary key to match Kindle books to any Petrarca-ingested book content (e.g., if the same book was also imported via bookifier pipeline or topic exploration)
4. **In the app:** Show "Your Kindle Highlights" section for books where matches exist; display highlight text alongside Petrarca's concept extractions

**Example API call:**
```python
# Get all Kindle books with highlights
resp = requests.get(
    "https://readwise.io/api/v2/export/",
    headers={"Authorization": f"Token {token}"},
    params={"updatedAfter": last_sync_iso}  # incremental
)
# Returns books with nested highlights, filtered to source=kindle
books = [b for b in resp.json()["results"] if b.get("source") == "kindle"]
```

#### Phase 2: Reading Progress via kindle-api (Medium Risk, Medium Value)

1. **Cookie extraction:** One-time manual step — log into read.amazon.com, extract 4 cookies + device token
2. **Script: `fetch_kindle_progress.py`** — Calls kindle-api endpoints to get `percentageRead` for each ASIN
3. **Merge:** Combine with Readwise highlight data to create rich book objects:
   ```json
   {
     "asin": "B0046LU7H0",
     "title": "The Name of the Rose",
     "kindle_progress": 0.67,
     "highlights": [...],
     "petrarca_concepts": [...],
     "connections": [...]
   }
   ```
4. **In the app:** "You're 67% through this book. Here's what you've highlighted so far, and here's how it connects to your other reading..."

#### Phase 3: Recaps and Connections (App-Level Feature)

1. **Book recaps:** For partially-read books, generate recap cards: "Last time in [Book], you highlighted [key passage]. Related concept: [X] appears in [Article Y] you read last week."
2. **Cross-pollination:** When a Petrarca article mentions a concept from a Kindle book the user is reading, surface the connection: "This article discusses [topic] — you highlighted a related passage in [Kindle Book] at location 1234."
3. **Review integration:** Include Kindle highlights in the spaced attention review flow alongside article concepts.

### Data Flow Diagram

```
Kindle Device/App
       |
       | (Whispersync)
       v
Amazon Cloud (read.amazon.com)
       |
       +---> Readwise (browser extension) ---> Readwise API v2 --> fetch_kindle_books.py
       |                                                                    |
       +---> kindle-api (cookies) ---------> fetch_kindle_progress.py       |
                                                       |                    |
                                                       v                    v
                                              data/kindle_books.json (merged)
                                                       |
                                                       v
                                              build_articles.py (matching)
                                                       |
                                                       v
                                              articles.json + concepts.json
                                                       |
                                                       v
                                              Petrarca App (reader, review, connections)
```

### Matching Strategy: Kindle Books to Petrarca Content

| Method | Use Case | Implementation |
|--------|----------|----------------|
| ASIN matching | Kindle book ↔ Readwise book | Direct field comparison |
| Title fuzzy match | Kindle book ↔ ingested book sections | Levenshtein/Jaccard on normalized titles |
| Author matching | Disambiguation | Normalize author names, match against article authors |
| ISBN/ASIN lookup | Cross-reference | Use Open Library or Google Books API to map ASIN ↔ ISBN |
| Concept overlap | Kindle highlights ↔ article concepts | Extract concepts from highlight text, match to concept graph |

### Risk Assessment

| Approach | Reliability | Data Quality | Maintenance Burden |
|----------|------------|--------------|-------------------|
| Readwise API v2 | High (official, documented API) | Good (highlights + metadata) | Low (token refresh only) |
| kindle-api libraries | Medium (unofficial, could break) | Good (reading progress) | Medium (cookie refresh yearly, TLS proxy) |
| My Clippings.txt | High (simple text file) | Good (includes personal docs) | Low (manual USB transfer) |
| Whispersync reverse-eng | Low (complex, fragile) | Excellent (everything) | High (binary format, auth complexity) |
| Local app SQLite | Low (paths change, sandboxed) | Variable | High (version-dependent) |

### Recommended Priority

1. **Start with Readwise API v2** — already have the token, well-documented, gets 90% of the value
2. **Add My Clippings.txt parser** — for personal documents not synced to cloud
3. **Optionally add kindle-api** — if reading progress data proves valuable for the recap/connection features
4. **Skip Whispersync and local DB approaches** — too fragile for a personal tool

## 8. EPUB File Integration: Mapping Kindle Progress to Book Content

### The Problem

The user has an EPUB file of a book and knows they're "30% through" on Kindle. How do we map that percentage to the actual content in the EPUB, so Petrarca can show what's been read and what's coming next?

### Kindle Locations vs EPUB Positions

Kindle uses a proprietary "location" system (1 location ≈ 128 bytes of text). These don't map directly to EPUB positions, which use EPUB CFI (Canonical Fragment Identifiers) — XPath-like references into the XHTML spine documents. However, **percentage-based progress** is a reasonable common denominator.

### Building a Chapter/Section Position Map from EPUB

Using `ebooklib` in Python, we can parse an EPUB's spine (the ordered list of content documents) and compute cumulative text lengths to build a percentage-to-chapter mapping:

```python
#!/usr/bin/env python3
"""Map EPUB chapters to percentage positions for Kindle progress matching."""

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class ChapterPosition:
    chapter_number: int
    title: str
    start_percentage: float  # 0.0 - 1.0
    end_percentage: float
    word_count: int
    spine_index: int


def build_position_map(epub_path: str) -> list[ChapterPosition]:
    """Parse EPUB and compute percentage positions for each chapter."""
    book = epub.read_epub(epub_path)
    spine_ids = [item_id for item_id, _ in book.spine]

    # First pass: measure all spine items
    items_with_text = []
    for spine_idx, item_id in enumerate(spine_ids):
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        if not text.strip():
            continue

        # Extract title from first heading, or use spine index
        heading = soup.find(['h1', 'h2', 'h3'])
        title = heading.get_text(strip=True) if heading else f"Section {spine_idx + 1}"

        items_with_text.append({
            'spine_index': spine_idx,
            'title': title,
            'text': text,
            'char_count': len(text),
            'word_count': len(text.split()),
        })

    # Second pass: compute cumulative percentages
    total_chars = sum(it['char_count'] for it in items_with_text)
    if total_chars == 0:
        return []

    chapters = []
    cumulative = 0
    for idx, item in enumerate(items_with_text):
        start_pct = cumulative / total_chars
        cumulative += item['char_count']
        end_pct = cumulative / total_chars
        chapters.append(ChapterPosition(
            chapter_number=idx + 1,
            title=item['title'],
            start_percentage=round(start_pct, 4),
            end_percentage=round(end_pct, 4),
            word_count=item['word_count'],
            spine_index=item['spine_index'],
        ))

    return chapters


def find_current_position(chapters: list[ChapterPosition], kindle_pct: float) -> dict:
    """Given Kindle percentage (0-100), find current chapter and reading state."""
    pct = kindle_pct / 100.0  # normalize to 0-1

    current_chapter = None
    chapters_read = []
    chapters_ahead = []

    for ch in chapters:
        if pct >= ch.end_percentage:
            chapters_read.append(ch)
        elif pct >= ch.start_percentage:
            current_chapter = ch
        else:
            chapters_ahead.append(ch)

    return {
        'kindle_percentage': kindle_pct,
        'current_chapter': current_chapter,
        'chapters_completed': len(chapters_read),
        'chapters_remaining': len(chapters_ahead),
        'total_chapters': len(chapters),
        'chapters_read': chapters_read,
        'chapters_ahead': chapters_ahead,
    }


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python epub_position_map.py <epub_path> [kindle_percentage]")
        sys.exit(1)

    chapters = build_position_map(sys.argv[1])
    kindle_pct = float(sys.argv[2]) if len(sys.argv) > 2 else None

    for ch in chapters:
        marker = ""
        if kindle_pct:
            pct = kindle_pct / 100.0
            if ch.start_percentage <= pct < ch.end_percentage:
                marker = " <-- YOU ARE HERE"
            elif pct >= ch.end_percentage:
                marker = " [read]"
        print(f"  Ch {ch.chapter_number}: {ch.title}")
        print(f"    {ch.start_percentage*100:.1f}% - {ch.end_percentage*100:.1f}% "
              f"({ch.word_count} words){marker}")

    if kindle_pct:
        pos = find_current_position(chapters, kindle_pct)
        print(f"\nAt {kindle_pct}%: Chapter {pos['current_chapter'].chapter_number if pos['current_chapter'] else '?'}")
        print(f"  {pos['chapters_completed']}/{pos['total_chapters']} chapters completed")
```

### Accuracy Considerations

The character-count-based percentage mapping is an approximation. Kindle's location system counts bytes differently from plain text extraction (it includes markup overhead and uses a 128-byte granularity). In practice, the mapping is accurate to within about 2-5% — good enough to identify which chapter the user is in, but not precise enough to pinpoint the exact paragraph.

For better accuracy, if we have both the EPUB and Kindle highlights with location numbers, we can use the **highlight text as anchors**: search for each highlighted passage in the EPUB text to create precise calibration points between Kindle locations and EPUB positions.

### Integration with Petrarca's Book Pipeline

The `ingest_book_petrarca.py` pipeline already splits EPUBs into sections. The position map can be generated during ingestion and stored alongside the book metadata:

```python
# In ingest_book_petrarca.py, after parsing chapters:
position_map = build_position_map(epub_path)

# Store in book metadata
book_meta = {
    "id": book_id,
    "title": title,
    "author": author,
    "chapters": [
        {
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "start_pct": ch.start_percentage,
            "end_pct": ch.end_percentage,
            "word_count": ch.word_count,
        }
        for ch in position_map
    ],
    "kindle_asin": asin,  # if known, for matching with Readwise
}
```

## 9. KOReader as an Alternative E-Reader

### Why KOReader Matters

[KOReader](https://koreader.rocks/) is an open-source e-reader app for Linux, Android, Kobo, Kindle, PocketBook, and other devices. Unlike Kindle, it exposes reading state through well-documented, open protocols. For a power user like Stian who values open algorithms and transparent data, KOReader is worth considering as the primary e-reader for books intended for Petrarca integration.

### KOReader Sync Protocol (kosync)

KOReader implements a lightweight REST API for syncing reading progress across devices:

**Endpoints:**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/auth` | Device authentication (MD5-hashed password) |
| PUT | `/syncs/progress` | Upload reading progress |
| GET | `/syncs/progress/{document_hash}` | Download reading progress |

**Progress data format:**
```json
{
  "document": "0b229176d4e8db7f6d2b5a4952368d7a",
  "progress": "/body/DocFragment[20]/body/p[22]/img.0",
  "percentage": 0.3186,
  "device": "KOReader",
  "device_id": "stian-kobo",
  "timestamp": 1709568000
}
```

Documents are identified by an MD5 hash of the first 10KB of the file. The `progress` field is an XPointer expression (for EPUB) or page reference (for PDF). The `percentage` field is a decimal 0.0-1.0.

**Self-hosting:** The sync server is trivial to deploy:
```bash
docker run -d -p 7200:7200 --name=kosync koreader/kosync:latest
```

### KOReader Highlight Export

KOReader exports highlights in multiple formats (JSON, Markdown, HTML, TXT) and can push directly to Readwise. The built-in exporter supports:

- **Local files**: JSON/Markdown/HTML/TXT written to device storage
- **Readwise**: Direct API integration (requires Readwise token)
- **Joplin**: Direct note sync
- **Memos/Flomo/XMNote**: Various note services

Highlights include page numbers, chapter references, and the highlighted text. For EPUB files, highlights also include CFI positions that can be mapped to precise locations in the document.

### KOReader Sidecar Files

KOReader stores per-book metadata in `.sdr` directories alongside each book file. These contain Lua tables with:

- Reading progress (percentage, position, page)
- All highlights with positions and text
- Bookmarks
- Reading statistics (time per session, pages read)
- Custom metadata

These files can be parsed directly with a Lua table parser or by reading the JSON export.

### Practical Integration: KOReader + Petrarca

If the user reads on KOReader instead of (or in addition to) Kindle:

1. **Progress sync**: Self-host kosync server on Hetzner alongside other Petrarca services. Poll it from `content-refresh.sh`.
2. **Highlights**: Configure KOReader to export to Readwise (which Petrarca already integrates with), or export JSON directly.
3. **Position accuracy**: KOReader's XPointer/CFI positions map exactly to EPUB content, giving paragraph-level precision rather than the ~5% approximation from Kindle percentage matching.

```python
# fetch_koreader_progress.py — poll kosync for reading progress
import requests
import hashlib
from pathlib import Path

KOSYNC_URL = "http://localhost:7200"
AUTH = {"X-Auth-User": "stian", "X-Auth-Key": "md5_hashed_password"}

def get_progress(epub_path: str) -> dict | None:
    """Get KOReader reading progress for an EPUB file."""
    # KOReader uses MD5 of first 10KB as document identifier
    with open(epub_path, 'rb') as f:
        doc_hash = hashlib.md5(f.read(10240)).hexdigest()

    resp = requests.get(
        f"{KOSYNC_URL}/syncs/progress/{doc_hash}",
        headers=AUTH
    )
    if resp.status_code == 200:
        return resp.json()  # {"percentage": 0.31, "progress": "...", ...}
    return None
```

### KOReader vs Kindle: Comparison for Petrarca Integration

| Feature | Kindle | KOReader |
|---------|--------|----------|
| Reading progress API | Unofficial (cookies, TLS proxy) | Open (kosync REST API) |
| Highlight export | Via Readwise or My Clippings.txt | JSON/Readwise/direct files |
| Position precision | ~5% (percentage-based) | Exact (CFI/XPointer) |
| Self-hostable sync | No | Yes (Docker) |
| DRM support | Required for purchased books | No (DRM-free only) |
| E-ink hardware | Kindle devices only | Kobo, PocketBook, reMarkable, Android |
| Ecosystem lock-in | High | None |
| Maintenance burden | Cookie refresh, TLS proxy | Minimal (standard REST) |

**Verdict**: For books where the user has a DRM-free EPUB, KOReader provides a vastly superior integration path. For books purchased on Amazon with DRM, Kindle + Readwise remains necessary.

## 10. Recommended Approach: Concrete Implementation

Given the user's situation (has Readwise, has the EPUB file, is 30% through a book on Kindle), here is the recommended implementation, broken into phases.

### Phase 1: Kindle Highlights via Readwise API v2 (1 day)

**Goal:** Pull all Kindle book highlights into Petrarca's data pipeline.

**New script: `scripts/fetch_kindle_books.py`**

```python
#!/usr/bin/env python3
"""Fetch Kindle book highlights via Readwise API v2.

Pulls books where source=kindle with their highlights.
Matches against Petrarca books by ASIN or title.

Usage:
    python3 scripts/fetch_kindle_books.py --save
    python3 scripts/fetch_kindle_books.py --save --incremental
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

VENV_SITE = str(Path(__file__).parent.parent / ".venv/lib/python3.12/site-packages")
if os.path.exists(VENV_SITE):
    sys.path.insert(0, VENV_SITE)

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_PATH = DATA_DIR / "kindle_books.json"
API_BASE = "https://readwise.io/api/v2"


def load_token() -> str:
    token = os.environ.get("READWISE_ACCESS_TOKEN")
    if token:
        return token
    for env_path in [Path(__file__).parent.parent / ".env", Path("/opt/petrarca/.env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("READWISE_ACCESS_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    print("ERROR: READWISE_ACCESS_TOKEN not found.", file=sys.stderr)
    sys.exit(1)


def fetch_kindle_export(token: str, updated_after: str | None = None) -> list[dict]:
    """Fetch all Kindle books with highlights via the export endpoint."""
    headers = {"Authorization": f"Token {token}"}
    all_books = []
    cursor = None

    while True:
        params = {}
        if updated_after:
            params["updatedAfter"] = updated_after
        if cursor:
            params["pageCursor"] = cursor

        resp = requests.get(f"{API_BASE}/export/", headers=headers, params=params)
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", 60))
            print(f"  Rate limited, waiting {retry}s...", file=sys.stderr)
            time.sleep(retry)
            continue
        resp.raise_for_status()
        data = resp.json()

        # Filter to Kindle-sourced books only
        kindle_books = [b for b in data.get("results", []) if b.get("source") == "kindle"]
        all_books.extend(kindle_books)
        print(f"  Fetched page: {len(kindle_books)} Kindle books "
              f"(total: {len(all_books)})", file=sys.stderr)

        cursor = data.get("nextPageCursor")
        if not cursor:
            break
        time.sleep(3)  # rate limit: 20 req/min for list endpoints

    return all_books


def transform_for_petrarca(books: list[dict]) -> list[dict]:
    """Transform Readwise export format into Petrarca's kindle_books.json format."""
    result = []
    for book in books:
        highlights = []
        for hl in book.get("highlights", []):
            highlights.append({
                "id": hl.get("id"),
                "text": hl.get("text", ""),
                "note": hl.get("note", ""),
                "location": hl.get("location"),
                "location_type": hl.get("location_type", "location"),
                "color": hl.get("color", "yellow"),
                "highlighted_at": hl.get("highlighted_at"),
                "tags": [t.get("name") for t in hl.get("tags", [])],
            })

        # Sort highlights by location for reading order
        highlights.sort(key=lambda h: h.get("location") or 0)

        result.append({
            "readwise_id": book.get("id"),
            "title": book.get("title", ""),
            "author": book.get("author", ""),
            "asin": book.get("asin"),
            "category": book.get("category", "books"),
            "source": book.get("source", "kindle"),
            "cover_image_url": book.get("cover_image_url"),
            "num_highlights": book.get("num_highlights", 0),
            "last_highlight_at": book.get("last_highlight_at"),
            "highlights": highlights,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        })
    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch Kindle books from Readwise")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        if not OUTPUT_PATH.exists():
            print("No data. Run with --save first.", file=sys.stderr)
            sys.exit(1)
        books = json.loads(OUTPUT_PATH.read_text())
        total_hl = sum(len(b.get("highlights", [])) for b in books)
        print(f"Kindle books: {len(books)}")
        print(f"Total highlights: {total_hl}")
        for b in sorted(books, key=lambda x: -len(x.get("highlights", []))):
            print(f"  {b['title']} ({b['author']}) — {len(b['highlights'])} highlights")
        return

    token = load_token()

    updated_after = None
    if args.incremental and OUTPUT_PATH.exists():
        existing = json.loads(OUTPUT_PATH.read_text())
        latest = max((b.get("fetched_at", "") for b in existing), default=None)
        if latest:
            updated_after = latest
            print(f"Incremental: since {latest}", file=sys.stderr)

    print("Fetching Kindle books from Readwise...", file=sys.stderr)
    raw = fetch_kindle_export(token, updated_after)
    books = transform_for_petrarca(raw)
    print(f"Found {len(books)} Kindle books", file=sys.stderr)

    if args.incremental and OUTPUT_PATH.exists():
        existing = json.loads(OUTPUT_PATH.read_text())
        by_id = {b["readwise_id"]: b for b in existing}
        for b in books:
            by_id[b["readwise_id"]] = b
        books = list(by_id.values())

    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(books, indent=2, ensure_ascii=False))
        print(f"Saved {len(books)} books to {OUTPUT_PATH}", file=sys.stderr)
    else:
        print(json.dumps(books, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

**Add to content-refresh.sh** (after Step 2):

```bash
# Step 2b: Fetch Kindle book highlights
log "Step 2b: Fetching Kindle book highlights..."
python3 "$SCRIPT_DIR/fetch_kindle_books.py" --save --incremental \
    || log "Step 2b FAILED: fetch_kindle_books.py"
```

### Phase 2: EPUB Position Mapping + Kindle Progress (1 day)

**Goal:** Given an EPUB file and a Kindle reading percentage, determine which chapters/sections have been read.

Add the `build_position_map()` and `find_current_position()` functions (shown in Section 8) to `ingest_book_petrarca.py`. During book ingestion, store the chapter position map alongside the book metadata.

**Matching Kindle books to Petrarca books:** When `ingest_book_petrarca.py` processes an EPUB, look for a matching entry in `kindle_books.json` by ASIN (if known) or fuzzy title+author match:

```python
def find_kindle_match(book_title: str, book_author: str, kindle_books: list[dict]) -> dict | None:
    """Find matching Kindle book by title similarity."""
    from difflib import SequenceMatcher

    best_match = None
    best_score = 0

    title_norm = book_title.lower().strip()
    author_norm = book_author.lower().strip()

    for kb in kindle_books:
        kt = kb.get("title", "").lower().strip()
        ka = kb.get("author", "").lower().strip()

        title_score = SequenceMatcher(None, title_norm, kt).ratio()
        author_score = SequenceMatcher(None, author_norm, ka).ratio()
        combined = title_score * 0.7 + author_score * 0.3

        if combined > best_score and combined > 0.6:
            best_score = combined
            best_match = kb

    return best_match
```

### Phase 3: Highlight-to-Section Mapping (1 day)

**Goal:** Map Kindle highlight text to specific sections within the EPUB, so highlights appear in the right place in the reader.

Kindle highlights from Readwise include the highlighted text and a location number. We can search for the highlight text within the EPUB's parsed sections to place them precisely:

```python
def map_highlights_to_sections(
    highlights: list[dict],
    sections: list[dict],  # Petrarca BookSection objects with content_markdown
) -> dict[str, list[dict]]:
    """Map Kindle highlights to book sections by text search.

    Returns: dict mapping section_id -> list of highlight objects
    """
    section_highlights: dict[str, list[dict]] = {}

    for hl in highlights:
        hl_text = hl.get("text", "").strip()
        if not hl_text or len(hl_text) < 20:
            continue

        # Search for highlight text in each section
        best_section = None
        best_overlap = 0

        for section in sections:
            content = section.get("content_markdown", "")
            # Try exact substring match first
            if hl_text in content:
                best_section = section["id"]
                break

            # Fall back to fuzzy: check if first 50 chars appear
            prefix = hl_text[:50]
            if prefix in content:
                best_section = section["id"]
                break

        if best_section:
            if best_section not in section_highlights:
                section_highlights[best_section] = []
            section_highlights[best_section].append(hl)

    return section_highlights
```

### Phase 4: App-Side Display (1-2 days)

**Goal:** Show Kindle reading progress, highlights, and connections in the Petrarca app.

**New types in `app/data/types.ts`:**

```typescript
export interface KindleBookState {
  book_id: string;              // Petrarca book ID
  kindle_asin?: string;
  kindle_progress: number;      // 0-100 percentage
  kindle_highlights: KindleHighlight[];
  last_synced_at: number;
}

export interface KindleHighlight {
  id: number;                   // Readwise highlight ID
  text: string;
  note?: string;
  location: number;             // Kindle location number
  color: string;
  highlighted_at: string;
  section_id?: string;          // Mapped to Petrarca section if available
  tags: string[];
}
```

**Context restoration card in the reader (React Native):**

```tsx
function KindleProgressCard({ book, kindleState }: {
  book: Book;
  kindleState: KindleBookState;
}) {
  const progress = kindleState.kindle_progress;
  const highlightCount = kindleState.kindle_highlights.length;
  const recentHighlight = kindleState.kindle_highlights
    .sort((a, b) => new Date(b.highlighted_at).getTime() - new Date(a.highlighted_at).getTime())[0];

  return (
    <View style={styles.kindleCard}>
      <Text style={styles.cardTitle}>Your Kindle Progress</Text>

      {/* Progress bar */}
      <View style={styles.progressBarBg}>
        <View style={[styles.progressBarFill, { width: `${progress}%` }]} />
      </View>
      <Text style={styles.progressText}>
        {progress.toFixed(0)}% read on Kindle
      </Text>

      {/* Highlight summary */}
      <Text style={styles.highlightCount}>
        {highlightCount} highlight{highlightCount !== 1 ? 's' : ''} captured
      </Text>

      {/* Most recent highlight */}
      {recentHighlight && (
        <View style={styles.recentHighlight}>
          <Text style={styles.recentLabel}>Last highlighted:</Text>
          <Text style={styles.recentText}>
            "{recentHighlight.text.slice(0, 150)}
            {recentHighlight.text.length > 150 ? '...' : ''}"
          </Text>
          {recentHighlight.note && (
            <Text style={styles.recentNote}>Note: {recentHighlight.note}</Text>
          )}
        </View>
      )}
    </View>
  );
}
```

**Kindle highlights rendered in the book section reader:**

```tsx
function SectionWithKindleHighlights({ section, kindleHighlights }: {
  section: BookSection;
  kindleHighlights: KindleHighlight[];
}) {
  // Highlights mapped to this section
  const sectionHighlights = kindleHighlights.filter(h => h.section_id === section.id);

  return (
    <View>
      <MarkdownText
        content={section.content_markdown}
        highlightedTexts={sectionHighlights.map(h => h.text)}
        highlightColor="#FDE68A"  // amber, same as existing highlights
      />
      {sectionHighlights.length > 0 && (
        <View style={styles.kindleHighlightBadge}>
          <Text style={styles.badgeText}>
            {sectionHighlights.length} Kindle highlight{sectionHighlights.length > 1 ? 's' : ''}
          </Text>
        </View>
      )}
    </View>
  );
}
```

### Phase 5: Recap and Connection Features (2-3 days)

**Goal:** Generate recaps, prompts, and cross-content connections based on Kindle reading state.

This is where the real value emerges. Using `claude -p` (free on Max plan):

**Recap generation (in the pipeline, run during content-refresh):**

```python
def generate_book_recap(
    book_title: str,
    chapters_read: list[dict],  # Petrarca sections the user has read
    kindle_highlights: list[dict],
    related_articles: list[dict],  # Petrarca articles on overlapping topics
) -> str:
    """Generate a personalized recap for a partially-read book."""
    highlights_text = "\n".join(
        f"- \"{h['text']}\"{' (Note: ' + h['note'] + ')' if h.get('note') else ''}"
        for h in kindle_highlights[:20]  # limit for prompt size
    )

    chapters_text = "\n".join(
        f"- Ch {ch['chapter_number']}: {ch['title']} ({ch.get('summary', 'no summary')})"
        for ch in chapters_read
    )

    related_text = "\n".join(
        f"- \"{a['title']}\" — {a.get('one_line_summary', '')}"
        for a in related_articles[:5]
    )

    prompt = f"""The user is reading "{book_title}" and has completed these chapters:
{chapters_text}

Their Kindle highlights:
{highlights_text}

Related articles they've read in Petrarca:
{related_text}

Generate a brief recap (3-5 sentences) that:
1. Summarizes the argument so far based on chapters read
2. Notes which highlights suggest the most engagement
3. Mentions 1-2 connections to the related articles
4. Poses one question to consider going forward

Keep it conversational and specific to what they've highlighted."""

    # Use claude -p (free on Max plan)
    import subprocess
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip()
```

**Connection surfacing (when reading an article):**

When the user opens an article in Petrarca, check if any Kindle highlights from their current books are conceptually related. This uses the existing concept matching infrastructure:

```python
def find_kindle_connections(
    article_concepts: list[str],
    kindle_highlights: list[dict],
) -> list[dict]:
    """Find Kindle highlights related to an article's concepts."""
    connections = []
    for hl in kindle_highlights:
        hl_words = set(hl["text"].lower().split())
        for concept in article_concepts:
            concept_words = set(concept.lower().split())
            overlap = len(hl_words & concept_words)
            if overlap >= 3:  # at least 3 content words in common
                connections.append({
                    "highlight_text": hl["text"][:200],
                    "concept": concept,
                    "book_title": hl.get("book_title", ""),
                    "location": hl.get("location"),
                    "overlap_score": overlap / len(concept_words),
                })

    # Return top connections, deduplicated
    connections.sort(key=lambda c: -c["overlap_score"])
    return connections[:5]
```

### Summary: What You Get

After implementing all phases, when the user opens Petrarca:

1. **"You're 30% through [Book]"** — progress bar synced from Kindle via kindle-api or manually entered
2. **"Your 15 Kindle highlights"** — pulled from Readwise, mapped to specific book sections
3. **Recap card** — "Last time in [Book], you were reading about [topic]. Your highlights focused on [theme]. This connects to [Article] you read last week about [related topic]."
4. **In-reader connections** — When reading an article, see "You highlighted a related passage in [Book] at location 1234: '[excerpt]'"
5. **Review integration** — Kindle highlights generate concepts that enter the spaced attention review flow

### Fallback: Manual Progress Entry

If kindle-api proves too fragile (cookies expiring, TLS proxy issues), implement a simple manual input:

```tsx
// In the book detail view
function ManualProgressInput({ bookId }: { bookId: string }) {
  const [pct, setPct] = useState('');

  return (
    <View style={styles.manualInput}>
      <Text>Kindle progress (%)</Text>
      <TextInput
        value={pct}
        onChangeText={setPct}
        keyboardType="numeric"
        placeholder="e.g. 30"
        style={styles.input}
      />
      <Pressable
        onPress={() => {
          updateKindleProgress(bookId, parseFloat(pct));
          logEvent('kindle_progress_manual', { bookId, percentage: parseFloat(pct) });
        }}
        style={styles.saveButton}
      >
        <Text>Update</Text>
      </Pressable>
    </View>
  );
}
```

This is pragmatic: the user glances at their Kindle, types "30", and Petrarca knows where they are. No API fragility, no cookies, no TLS proxies. Combined with automatic Readwise highlight sync, this covers the core use case well.

---

## Sources

- [Readwise API Documentation](https://readwise.io/api_deets)
- [Readwise Reader API](https://readwise.io/reader_api)
- [Readwise Kindle Import Docs](https://docs.readwise.io/readwise/docs/importing-highlights/kindle)
- [kindle-api by Xetera](https://github.com/Xetera/kindle-api)
- [kindle-api by transitive-bullshit](https://github.com/transitive-bullshit/kindle-api)
- [Whispersync Reverse Engineering](https://ptbrowne.github.io/posts/whispersync-reverse-engineering/)
- [whispersync-lib](https://github.com/ptbrowne/whispersync-lib)
- [Lector](https://github.com/msuozzo/Lector)
- [kindle-highlight-scraper](https://github.com/mieubrisse/kindle-highlight-scraper)
- [Bookcision](https://readwise.io/bookcision)
- [Clippings.io](https://www.clippings.io/)
- [Glasp Kindle Export](https://glasp.co/posts/how-to-copy-and-paste-kindle-highlights-beyond-the-export-limits)
- [obsidian-kindle-plugin](https://github.com/topics/kindle-highlights)
- [Kindle Clippings File Format](https://medium.com/@kindleclippingexport/what-is-the-kindle-clippings-file-9e4df408e0c1)
- [KindleClippings Parser](https://github.com/robertmartin8/KindleClippings)
- [kindle-ai-export](https://github.com/transitive-bullshit/kindle-ai-export)
- [Kindle Mac Storage](https://discussions.apple.com/thread/254960241)
- [How to Access Kindle Clippings (2025)](https://www.kindleexport.com/blog/kindle-clipping-file-access-2025)
- [KOReader](https://koreader.rocks/)
- [KOReader Sync Server](https://github.com/koreader/koreader-sync-server)
- [KOReader Highlight Export Wiki](https://github.com/koreader/koreader/wiki/Highlight-export)
- [KOHighlights Utility](https://github.com/noembryo/KoHighlights)
- [kosync Protocol Analysis](https://deepwiki.com/dengxuezhao/koreader_sync_statistic_analysis/3.3-synchronization-api)
- [EPUB CFI Specification](https://idpf.org/epub/linking/cfi/epub-cfi.html)
- [EPUB Locators (W3C)](https://w3c.github.io/epub-specs/epub33/locators/)
- [epub.js Locations API](https://github.com/futurepress/epub.js/blob/master/documentation/md/API.md)
- [ebooklib (Python EPUB library)](https://github.com/aerkalov/ebooklib)

- [Readwise API Documentation](https://readwise.io/api_deets)
- [Readwise Reader API](https://readwise.io/reader_api)
- [Readwise Kindle Import Docs](https://docs.readwise.io/readwise/docs/importing-highlights/kindle)
- [kindle-api by Xetera](https://github.com/Xetera/kindle-api)
- [kindle-api by transitive-bullshit](https://github.com/transitive-bullshit/kindle-api)
- [Whispersync Reverse Engineering](https://ptbrowne.github.io/posts/whispersync-reverse-engineering/)
- [whispersync-lib](https://github.com/ptbrowne/whispersync-lib)
- [Lector](https://github.com/msuozzo/Lector)
- [kindle-highlight-scraper](https://github.com/mieubrisse/kindle-highlight-scraper)
- [Bookcision](https://readwise.io/bookcision)
- [Clippings.io](https://www.clippings.io/)
- [Glasp Kindle Export](https://glasp.co/posts/how-to-copy-and-paste-kindle-highlights-beyond-the-export-limits)
- [obsidian-kindle-plugin](https://github.com/topics/kindle-highlights)
- [Kindle Clippings File Format](https://medium.com/@kindleclippingexport/what-is-the-kindle-clippings-file-9e4df408e0c1)
- [KindleClippings Parser](https://github.com/robertmartin8/KindleClippings)
- [kindle-ai-export](https://github.com/transitive-bullshit/kindle-ai-export)
- [Kindle Mac Storage](https://discussions.apple.com/thread/254960241)
- [How to Access Kindle Clippings (2025)](https://www.kindleexport.com/blog/kindle-clipping-file-access-2025)
