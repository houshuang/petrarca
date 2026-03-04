#!/usr/bin/env python3
"""Ingest an EPUB/PDF book into Petrarca as section-level JSON.

Chapters are split into sections (5-15 min reads) which become the reading unit,
analogous to articles. Each section gets LLM-extracted claims, summaries, key terms,
and cross-book/article connections.

Pipeline:
  1. Parse EPUB/PDF via pymupdf — extract TOC, metadata, chapter text
  2. Split chapters into sections at heading boundaries or via LLM breakpoints
  3. LLM extraction per section: summary, claims, key terms, briefing
  4. Cross-book/article claim matching via content-word overlap
  5. Output: books/{book_id}/meta.json + books/{book_id}/ch{N}_sections.json

Usage:
    python ingest_book_petrarca.py path/to/book.epub
    python ingest_book_petrarca.py path/to/book.pdf --chapter 3
    python ingest_book_petrarca.py path/to/book.epub --output-dir /opt/petrarca/data/books
    python ingest_book_petrarca.py path/to/book.epub --cross-match-dir /opt/petrarca/data
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "data" / "books"
DEFAULT_CROSS_MATCH_DIR = PROJECT_DIR / "data"

# ---------------------------------------------------------------------------
# Stop words — mirrors app/data/store.ts contentWords()
# ---------------------------------------------------------------------------

STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'must',
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
    'that', 'which', 'who', 'whom', 'this', 'these', 'those',
    'it', 'its', 'they', 'them', 'their', 'we', 'our', 'you', 'your',
    'than', 'more', 'most', 'very', 'also', 'just', 'about',
}


def content_words(text: str) -> set[str]:
    """Extract content words from text, matching store.ts contentWords()."""
    words = re.sub(r'[^\w\s]', '', text.lower()).split()
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


# ---------------------------------------------------------------------------
# LLM calling — same pattern as build_articles.py
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, json_mode: bool = False) -> str | None:
    """Call Gemini Flash. Returns raw text response."""
    api_key = os.environ.get("GEMINI_KEY", "")
    if not api_key:
        print("  GEMINI_KEY not set, falling back to claude -p", file=sys.stderr)
        return _call_claude_cli(prompt)
    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        config = {}
        if json_mode:
            config["response_mime_type"] = "application/json"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config if config else None,
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"  gemini error: {e}", file=sys.stderr)
        return None


def _call_claude_cli(prompt: str, timeout: int = 300) -> str | None:
    """Call claude -p as fallback for synthesis tasks."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.stderr:
            print(f"  claude -p stderr: {result.stderr[:200]}", file=sys.stderr)
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  claude -p error: {e}", file=sys.stderr)
        return None


def _call_llm(prompt: str, json_mode: bool = False) -> str | None:
    """Call LLM — Gemini Flash primary, claude -p fallback."""
    result = _call_gemini(prompt, json_mode=json_mode)
    if result:
        return result
    print("  Gemini failed, trying claude -p fallback...", file=sys.stderr)
    return _call_claude_cli(prompt)


def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Book parsing — adapted from otak/scripts/ingest_book.py
# ---------------------------------------------------------------------------

def parse_book(path: str) -> dict:
    """Parse an EPUB or PDF into chapters with metadata.

    Returns:
        {
            "title": str,
            "author": str,
            "chapters": [
                {"number": int, "title": str, "text": str,
                 "start_page": int, "end_page": int}
            ],
        }
    """
    doc = pymupdf.open(path)
    toc = doc.get_toc()

    meta = doc.metadata or {}
    book_title = meta.get("title", "") or Path(path).stem
    book_author = meta.get("author", "") or ""

    if not toc:
        # No TOC — treat entire document as one chapter
        print("  WARNING: No TOC found, treating entire document as one chapter", file=sys.stderr)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()
        return {
            "title": book_title,
            "author": book_author,
            "chapters": [{
                "number": 1,
                "title": book_title,
                "text": full_text.strip(),
                "start_page": 1,
                "end_page": doc.page_count,
            }],
        }

    # Build chapter list from TOC level-1 entries
    l1_entries = [(title, page) for level, title, page in toc if level == 1]
    raw_chapters = []
    for i, (title, start_page) in enumerate(l1_entries):
        end_page = l1_entries[i + 1][1] if i + 1 < len(l1_entries) else doc.page_count + 1
        raw_chapters.append({
            "title": title,
            "start_page": start_page,
            "end_page": end_page,
        })

    # Extract text for each chapter
    for ch in raw_chapters:
        text = ""
        for pg_num in range(ch["start_page"] - 1, ch["end_page"] - 1):
            if 0 <= pg_num < doc.page_count:
                text += doc[pg_num].get_text()
        ch["text"] = text.strip()

    doc.close()

    # Filter out empty/front-matter chapters and assign numbers
    chapters = []
    ch_num = 0
    skip_titles = {"cover", "title page", "copyright", "table of contents",
                   "contents", "dedication", "epigraph", "also by"}
    for ch in raw_chapters:
        title_lower = ch["title"].strip().lower()
        if title_lower in skip_titles:
            continue
        if len(ch["text"]) < 200:
            continue
        ch_num += 1
        chapters.append({
            "number": ch_num,
            "title": ch["title"].strip(),
            "text": ch["text"],
            "start_page": ch["start_page"],
            "end_page": ch["end_page"],
        })

    print(f"  Parsed {len(chapters)} chapters from '{book_title}'", file=sys.stderr)
    for ch in chapters:
        wc = len(ch["text"].split())
        print(f"    Ch {ch['number']}: {ch['title'][:60]} ({wc} words)", file=sys.stderr)

    return {
        "title": book_title,
        "author": book_author,
        "chapters": chapters,
    }


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _split_at_headings(text: str, min_words: int = 300) -> list[dict] | None:
    """Try to split chapter text at H2/H3 markdown headings.

    Returns list of {"title": str, "content": str} or None if no headings found.
    """
    heading_pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    matches = list(heading_pattern.finditer(text))

    if len(matches) < 2:
        return None

    sections = []

    # Content before first heading (if substantial)
    preamble = text[:matches[0].start()].strip()
    if len(preamble.split()) >= min_words:
        sections.append({
            "title": "Introduction",
            "content": preamble,
        })

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if len(content.split()) < min_words and sections:
            # Merge short section into previous
            sections[-1]["content"] += f"\n\n## {heading}\n\n{content}"
        else:
            sections.append({
                "title": heading,
                "content": content,
            })

    return sections if len(sections) >= 2 else None


def _split_via_llm(text: str, chapter_title: str) -> list[dict]:
    """Use Gemini Flash to identify logical breakpoints in text without headings."""
    word_count = len(text.split())
    target_sections = max(2, min(8, word_count // 2000))

    prompt = f"""Split this chapter into {target_sections} logical sections for progressive reading.
Each section should be 1500-3000 words and represent a coherent unit of argument.

Chapter: {chapter_title}
Word count: {word_count}

TEXT:
{text[:15000]}
{"[... truncated ...]" if len(text) > 15000 else ""}

Return a JSON array where each element has:
- "title": a descriptive heading for the section (5-10 words)
- "start_phrase": the first 8-12 words of where this section begins in the text (verbatim)

Example: [{{"title": "The Problem of Medieval Trade", "start_phrase": "The conventional view of medieval commerce"}}]

Return ONLY the JSON array."""

    response = _call_llm(prompt, json_mode=True)
    if not response:
        return [{"title": chapter_title, "content": text}]

    breakpoints = _parse_json_response(response)
    if not breakpoints or not isinstance(breakpoints, list) or len(breakpoints) < 2:
        return [{"title": chapter_title, "content": text}]

    # Match start_phrases to positions in text
    sections = []
    text_lower = text.lower()
    positions = []

    for bp in breakpoints:
        phrase = bp.get("start_phrase", "").lower().strip()
        if not phrase:
            continue
        # Find the phrase in text (fuzzy: try first 6 words if full match fails)
        idx = text_lower.find(phrase)
        if idx == -1:
            words = phrase.split()[:6]
            idx = text_lower.find(" ".join(words))
        if idx == -1:
            words = phrase.split()[:4]
            idx = text_lower.find(" ".join(words))
        positions.append((idx if idx >= 0 else -1, bp.get("title", "Section")))

    # Filter out unmatched and sort by position
    positions = [(pos, title) for pos, title in positions if pos >= 0]
    positions.sort(key=lambda x: x[0])

    if len(positions) < 2:
        return [{"title": chapter_title, "content": text}]

    for i, (pos, title) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        content = text[pos:end_pos].strip()
        sections.append({"title": title, "content": content})

    return sections


def split_chapter_into_sections(chapter: dict) -> list[dict]:
    """Split a chapter into reading-sized sections.

    Returns list of {"title": str, "content": str}.
    """
    text = chapter["text"]
    word_count = len(text.split())

    # Short chapter — keep as one section
    if word_count < 2000:
        return [{"title": chapter["title"], "content": text}]

    # Try heading-based splitting first
    heading_sections = _split_at_headings(text)
    if heading_sections:
        print(f"    Split at headings: {len(heading_sections)} sections", file=sys.stderr)
        return heading_sections

    # Fall back to LLM splitting
    print(f"    No headings found, using LLM to find breakpoints...", file=sys.stderr)
    llm_sections = _split_via_llm(text, chapter["title"])
    print(f"    LLM split: {len(llm_sections)} sections", file=sys.stderr)
    return llm_sections


# ---------------------------------------------------------------------------
# Section extraction prompt
# ---------------------------------------------------------------------------

SECTION_EXTRACTION_PROMPT = """You are extracting structured information from a book section for a progressive reading app.

The reader will see this section at multiple depth levels:
1. Briefing (30-second orientation: what this section covers, where it fits)
2. Key claims with source passages
3. Key terms with definitions
4. Full text reading

Book: {book_title}
Author: {book_author}
Chapter: {chapter_title}
Section: {section_title}
Section {section_number} of {total_sections} in this chapter

{context_note}

SECTION TEXT:
{section_text}

Return a JSON object:
{{
  "summary": "2-3 sentence summary of this section's content and argument",
  "briefing": "1-2 sentences placing this section in context: what came before, what argument this advances, what to watch for",
  "claims": [
    {{
      "claim_id": "M1",
      "text": "Clear propositional statement of the claim",
      "claim_type": "one of: historical_claim, empirical_claim, theoretical_claim, causal_claim, policy_claim, methodological_claim, interpretive_claim",
      "confidence": 0.8,
      "source_passage": "verbatim quote from the text supporting this claim",
      "supports_claim": null,
      "is_main": true
    }}
  ],
  "key_terms": [
    {{
      "term": "term as used by author",
      "definition": "how the author defines or uses this term in context"
    }}
  ]
}}

Guidelines:
- claims: Extract 3-8 claims per section. Main claims (is_main=true) are the section's core propositions. Supporting claims (is_main=false) use supports_claim to reference the main claim ID they support (e.g. "M1").
- claim_id: Use M1, M2 etc for main claims, S1, S2 etc for supporting claims
- source_passage: Must be VERBATIM from the text, not paraphrased
- confidence: 0.8-0.95 for well-evidenced claims, 0.5-0.7 for interpretive claims
- key_terms: 2-6 terms that the author defines or uses in a specific way
- briefing: Write as if addressing the reader directly, briefly

Return ONLY valid JSON."""


def extract_section(section: dict, book_info: dict, chapter: dict,
                    section_number: int, total_sections: int,
                    prev_summary: str = "") -> dict | None:
    """Run LLM extraction on a single section."""
    context_note = ""
    if prev_summary:
        context_note = f"Previous section summary: {prev_summary}"

    section_text = section["content"]
    if len(section_text) > 20000:
        section_text = section_text[:20000] + "\n\n[... truncated ...]"

    prompt = SECTION_EXTRACTION_PROMPT.format(
        book_title=book_info["title"],
        book_author=book_info["author"],
        chapter_title=chapter["title"],
        section_title=section["title"],
        section_number=section_number,
        total_sections=total_sections,
        context_note=context_note,
        section_text=section_text,
    )

    response = _call_llm(prompt, json_mode=True)
    if not response:
        return None

    return _parse_json_response(response)


# ---------------------------------------------------------------------------
# Chapter argument extraction
# ---------------------------------------------------------------------------

def extract_chapter_argument(chapter_title: str, section_summaries: list[str],
                             book_title: str) -> str:
    """Generate a one-sentence running argument for the chapter."""
    summaries_text = "\n".join(f"  Section {i+1}: {s}" for i, s in enumerate(section_summaries))

    prompt = f"""In ONE sentence, summarize the contribution of this chapter to the book's overall argument.

Book: {book_title}
Chapter: {chapter_title}
Section summaries:
{summaries_text}

Return ONLY the single sentence, no quotes or explanation."""

    response = _call_llm(prompt)
    if response:
        return response.strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# Cross-book/article claim matching
# ---------------------------------------------------------------------------

def load_existing_claims(cross_match_dir: Path) -> list[dict]:
    """Load all existing claims from articles and other books for cross-matching.

    Returns list of {"claim_text": str, "source_id": str, "source_title": str, "source_type": str}
    """
    claims = []

    # Load article claims
    articles_path = cross_match_dir / "articles.json"
    if articles_path.exists():
        try:
            articles = json.loads(articles_path.read_text())
            for article in articles:
                for claim_text in article.get("key_claims", []):
                    claims.append({
                        "claim_text": claim_text,
                        "source_id": article["id"],
                        "source_title": article.get("title", ""),
                        "source_type": "article",
                    })
        except (json.JSONDecodeError, KeyError):
            print(f"  Warning: could not parse {articles_path}", file=sys.stderr)

    # Load claims from other books
    books_dir = cross_match_dir / "books"
    if books_dir.exists():
        for book_dir in books_dir.iterdir():
            if not book_dir.is_dir():
                continue
            meta_path = book_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                book_meta = json.loads(meta_path.read_text())
                book_title = book_meta.get("title", book_dir.name)
            except (json.JSONDecodeError, KeyError):
                book_title = book_dir.name

            for ch_file in sorted(book_dir.glob("ch*_sections.json")):
                try:
                    sections = json.loads(ch_file.read_text())
                    for section in sections:
                        for claim in section.get("claims", []):
                            claims.append({
                                "claim_text": claim["text"],
                                "source_id": section["id"],
                                "source_title": book_title,
                                "source_type": "book",
                            })
                except (json.JSONDecodeError, KeyError):
                    continue

    print(f"  Loaded {len(claims)} existing claims for cross-matching", file=sys.stderr)
    return claims


def classify_connection_relationship(claim_a: str, claim_b: str, source_b: str) -> str:
    """Use LLM to classify the relationship between two claims.

    Returns one of: agrees, disagrees, extends, provides_evidence, same_topic
    """
    prompt = f"""Classify the relationship between these two claims from different sources.

Claim A (current book): {claim_a}

Claim B (from "{source_b}"): {claim_b}

Return ONLY one word — the relationship type:
- "agrees" if both claims support the same conclusion
- "disagrees" if they contradict or present opposing views
- "extends" if Claim B adds nuance, detail, or a new angle to Claim A's topic
- "provides_evidence" if one claim provides evidence for the other
- "same_topic" if they discuss the same subject but don't clearly agree/disagree/extend

Return ONLY the single word."""

    response = _call_llm(prompt)
    if response:
        word = response.strip().lower().strip('"').strip("'")
        if word in ("agrees", "disagrees", "extends", "provides_evidence", "same_topic"):
            return word
    return "same_topic"


def find_cross_connections(section_claims: list[dict], existing_claims: list[dict],
                           own_book_id: str, threshold: float = 0.3,
                           classify: bool = True) -> list[dict]:
    """Find cross-book/article connections for a section's claims.

    Uses content-word overlap matching (same algorithm as store.ts).
    When classify=True, uses LLM to determine relationship type for top matches.
    """
    connections = []
    seen_targets = set()

    for claim in section_claims:
        claim_cw = content_words(claim.get("text", ""))
        if len(claim_cw) < 3:
            continue

        for existing in existing_claims:
            # Skip claims from the same book
            if existing["source_id"].startswith(own_book_id):
                continue

            existing_cw = content_words(existing["claim_text"])
            if len(existing_cw) < 3:
                continue

            overlap = len(claim_cw & existing_cw)
            score = overlap / min(len(claim_cw), len(existing_cw))

            if score >= threshold:
                target_key = existing["source_id"]
                if target_key in seen_targets:
                    continue
                seen_targets.add(target_key)

                connections.append({
                    "target_section_id": existing["source_id"],
                    "target_book_title": existing["source_title"],
                    "target_claim_text": existing["claim_text"],
                    "claim_text": claim.get("text", ""),
                    "relationship": "same_topic",
                    "overlap_score": round(score, 3),
                })

    # Sort by overlap score and keep top 5
    connections.sort(key=lambda c: c["overlap_score"], reverse=True)
    connections = connections[:5]

    # Classify relationship type for top connections
    if classify and connections:
        for conn in connections:
            rel = classify_connection_relationship(
                conn["claim_text"], conn["target_claim_text"], conn["target_book_title"]
            )
            conn["relationship"] = rel
            time.sleep(0.5)  # Rate limiting

    return connections


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def generate_book_id(title: str, author: str) -> str:
    """Generate a stable book ID from title and author."""
    src = f"{title.lower().strip()}:{author.lower().strip()}"
    return hashlib.sha256(src.encode()).hexdigest()[:12]


def process_book(book_path: str, output_dir: Path, cross_match_dir: Path | None,
                 chapter_filter: int | None = None):
    """Main entry point: parse book, split into sections, extract, output."""

    t_start = time.time()
    total_llm_calls = 0

    # 1. Parse the book
    print(f"\n=== Parsing: {book_path} ===", file=sys.stderr)
    book = parse_book(book_path)
    book_id = generate_book_id(book["title"], book["author"])
    print(f"  Book ID: {book_id}", file=sys.stderr)
    print(f"  Title: {book['title']}", file=sys.stderr)
    print(f"  Author: {book['author']}", file=sys.stderr)

    # 2. Load existing claims for cross-matching
    existing_claims = []
    if cross_match_dir:
        existing_claims = load_existing_claims(cross_match_dir)

    # 3. Load or initialize book meta
    book_dir = output_dir / book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    meta_path = book_dir / "meta.json"

    if meta_path.exists():
        book_meta = json.loads(meta_path.read_text())
        print(f"  Loaded existing meta ({len(book_meta.get('chapters', []))} chapters)", file=sys.stderr)
    else:
        book_meta = {
            "id": book_id,
            "title": book["title"],
            "author": book["author"],
            "source_path": str(book_path),
            "chapters": [],
            "topics": [],
            "running_argument": [],
            "language": "en",
            "added_at": int(time.time() * 1000),
        }

    # 4. Process chapters
    chapters_to_process = book["chapters"]
    if chapter_filter is not None:
        chapters_to_process = [ch for ch in chapters_to_process if ch["number"] == chapter_filter]
        if not chapters_to_process:
            print(f"  ERROR: Chapter {chapter_filter} not found", file=sys.stderr)
            sys.exit(1)

    for chapter in chapters_to_process:
        ch_num = chapter["number"]
        print(f"\n--- Chapter {ch_num}: {chapter['title']} ---", file=sys.stderr)

        # Split into sections
        raw_sections = split_chapter_into_sections(chapter)

        # Process each section
        processed_sections = []
        prev_summary = ""

        for s_idx, raw_section in enumerate(raw_sections):
            s_num = s_idx + 1
            section_id = f"{book_id}:ch{ch_num}:s{s_num}"
            word_count = len(raw_section["content"].split())
            est_minutes = max(1, round(word_count / 250))

            print(f"  Section {s_num}/{len(raw_sections)}: {raw_section['title'][:50]} ({word_count} words)", file=sys.stderr)

            # LLM extraction
            extraction = extract_section(
                section=raw_section,
                book_info=book,
                chapter=chapter,
                section_number=s_num,
                total_sections=len(raw_sections),
                prev_summary=prev_summary,
            )
            total_llm_calls += 1

            if extraction:
                claims = extraction.get("claims", [])
                summary = extraction.get("summary", "")
                briefing = extraction.get("briefing", "")
                key_terms = extraction.get("key_terms", [])
                prev_summary = summary
                print(f"    Extracted: {len(claims)} claims, {len(key_terms)} terms", file=sys.stderr)
            else:
                print(f"    WARNING: extraction failed, using empty values", file=sys.stderr)
                claims = []
                summary = ""
                briefing = ""
                key_terms = []

            # Cross-book matching
            cross_connections = []
            if existing_claims and claims:
                cross_connections = find_cross_connections(claims, existing_claims, book_id)
                if cross_connections:
                    print(f"    Found {len(cross_connections)} cross-connections", file=sys.stderr)

            # Build section object
            section_obj = {
                "id": section_id,
                "book_id": book_id,
                "chapter_number": ch_num,
                "section_number": s_num,
                "title": raw_section["title"],
                "chapter_title": chapter["title"],
                "content_markdown": raw_section["content"],
                "summary": summary,
                "briefing": briefing,
                "claims": claims,
                "key_terms": key_terms,
                "cross_book_connections": [
                    {k: v for k, v in c.items() if k not in ("overlap_score", "claim_text")}
                    for c in cross_connections
                ],
                "word_count": word_count,
                "estimated_read_minutes": est_minutes,
            }
            processed_sections.append(section_obj)

            # Rate limiting
            time.sleep(1)

        # Track key terms across sections for conflict detection
        for section_obj in processed_sections:
            for term in section_obj.get("key_terms", []):
                term_key = term["term"].lower().strip()
                # Check if this term was defined differently in an earlier section
                for prev_section in processed_sections:
                    if prev_section["id"] == section_obj["id"]:
                        break
                    for prev_term in prev_section.get("key_terms", []):
                        if prev_term["term"].lower().strip() == term_key:
                            # Same term, check if definitions differ meaningfully
                            if prev_term["definition"] != term["definition"]:
                                term["conflicts_with"] = f"Ch {prev_section['chapter_number']}, §{prev_section['section_number']}: \"{prev_term['definition'][:80]}...\""

        # Generate chapter argument sentence
        section_summaries = [s["summary"] for s in processed_sections if s["summary"]]
        chapter_argument = ""
        if section_summaries:
            chapter_argument = extract_chapter_argument(
                chapter["title"], section_summaries, book["title"]
            )
            total_llm_calls += 1
            if chapter_argument:
                print(f"  Chapter argument: {chapter_argument[:80]}...", file=sys.stderr)

        # Save chapter sections
        ch_path = book_dir / f"ch{ch_num}_sections.json"
        ch_path.write_text(json.dumps(processed_sections, indent=2, ensure_ascii=False))
        print(f"  Saved: {ch_path} ({len(processed_sections)} sections)", file=sys.stderr)

        # Update meta
        ch_meta = {
            "chapter_number": ch_num,
            "title": chapter["title"],
            "section_count": len(processed_sections),
            "processing_status": "completed",
            "argument_sentence": chapter_argument,
        }

        # Replace or append chapter meta
        existing_ch_nums = [c["chapter_number"] for c in book_meta["chapters"]]
        if ch_num in existing_ch_nums:
            idx = existing_ch_nums.index(ch_num)
            book_meta["chapters"][idx] = ch_meta
        else:
            book_meta["chapters"].append(ch_meta)
            book_meta["chapters"].sort(key=lambda c: c["chapter_number"])

        # Update running argument
        while len(book_meta["running_argument"]) < ch_num:
            book_meta["running_argument"].append("")
        book_meta["running_argument"][ch_num - 1] = chapter_argument

    # Cross-chapter key term conflict detection
    all_chapter_terms: dict[str, list[dict]] = {}
    for ch in book_meta["chapters"]:
        if ch["processing_status"] != "completed":
            continue
        ch_file = book_dir / f"ch{ch['chapter_number']}_sections.json"
        if not ch_file.exists():
            continue
        sections = json.loads(ch_file.read_text())
        for sec in sections:
            for term in sec.get("key_terms", []):
                key = term["term"].lower().strip()
                if key not in all_chapter_terms:
                    all_chapter_terms[key] = []
                all_chapter_terms[key].append({
                    "term": term["term"],
                    "definition": term["definition"],
                    "chapter": sec["chapter_number"],
                    "section": sec["section_number"],
                    "section_id": sec["id"],
                })

    # For terms that appear in multiple chapters, annotate conflicts
    terms_with_evolution = {k: v for k, v in all_chapter_terms.items() if len(v) > 1}
    if terms_with_evolution:
        print(f"  Terms appearing across chapters: {len(terms_with_evolution)}", file=sys.stderr)
        for term_key, appearances in terms_with_evolution.items():
            # Check if definitions differ
            unique_defs = set(a["definition"] for a in appearances)
            if len(unique_defs) > 1:
                for i, app in enumerate(appearances[1:], 1):
                    first = appearances[0]
                    # Update the section file to add conflicts_with
                    ch_file = book_dir / f"ch{app['chapter']}_sections.json"
                    if ch_file.exists():
                        sections = json.loads(ch_file.read_text())
                        for sec in sections:
                            if sec["id"] == app["section_id"]:
                                for term in sec.get("key_terms", []):
                                    if term["term"].lower().strip() == term_key and not term.get("conflicts_with"):
                                        term["conflicts_with"] = f"Ch {first['chapter']}, §{first['section']}"
                        ch_file.write_text(json.dumps(sections, indent=2, ensure_ascii=False))

    # Extract thesis statement if not already set
    if not book_meta.get("thesis_statement") and book_meta["running_argument"]:
        thesis_prompt = f"""What is the central thesis of this book?

Book: {book["title"]} by {book["author"]}
Chapter arguments:
{chr(10).join(f'  Ch {i+1}: {arg}' for i, arg in enumerate(book_meta["running_argument"]) if arg)}

Return ONE sentence capturing the book's central thesis. Return ONLY the sentence."""

        thesis_response = _call_llm(thesis_prompt)
        if thesis_response:
            book_meta["thesis_statement"] = thesis_response.strip().strip('"').strip("'")
            print(f"  Thesis: {book_meta['thesis_statement'][:80]}...", file=sys.stderr)

    # Extract topics from the book if not already set
    if not book_meta.get("topics"):
        all_terms = set()
        all_claims_text = []
        for ch in book_meta["chapters"]:
            if ch["processing_status"] != "completed":
                continue
            ch_file = book_dir / f"ch{ch['chapter_number']}_sections.json"
            if ch_file.exists():
                sections = json.loads(ch_file.read_text())
                for sec in sections:
                    for term in sec.get("key_terms", []):
                        all_terms.add(term.get("term", "").lower())
                    for claim in sec.get("claims", []):
                        all_claims_text.append(claim.get("text", ""))

        if all_terms or all_claims_text:
            topic_prompt = f"""Given this book and its key terms and claims, identify 3-5 topic tags.

Book: {book["title"]} by {book["author"]}
Key terms: {', '.join(list(all_terms)[:30])}
Sample claims: {' | '.join(all_claims_text[:10])}

Return a JSON array of 3-5 short topic strings (2-4 words each), like ["Medieval Trade", "Islamic Scholarship", "Cultural Exchange"].
Return ONLY the JSON array."""

            topic_response = _call_llm(topic_prompt, json_mode=True)
            if topic_response:
                topics = _parse_json_response(topic_response)
                if isinstance(topics, list):
                    book_meta["topics"] = [t for t in topics if isinstance(t, str)]
                    print(f"  Topics: {book_meta['topics']}", file=sys.stderr)

    # Add pending entries for unprocessed chapters
    processed_nums = {c["chapter_number"] for c in book_meta["chapters"]}
    for ch in book["chapters"]:
        if ch["number"] not in processed_nums:
            book_meta["chapters"].append({
                "chapter_number": ch["number"],
                "title": ch["title"],
                "section_count": 0,
                "processing_status": "pending",
                "argument_sentence": "",
            })
    book_meta["chapters"].sort(key=lambda c: c["chapter_number"])

    # Save meta
    meta_path.write_text(json.dumps(book_meta, indent=2, ensure_ascii=False))

    elapsed = time.time() - t_start
    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  Output: {book_dir}", file=sys.stderr)
    print(f"  LLM calls: {total_llm_calls}", file=sys.stderr)
    print(f"  Time: {elapsed:.1f}s", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest an EPUB/PDF book into Petrarca as section-level JSON."
    )
    parser.add_argument("book_path", help="Path to EPUB or PDF file")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--chapter", type=int, default=None,
                        help="Process only this chapter number")
    parser.add_argument("--cross-match-dir", type=Path, default=DEFAULT_CROSS_MATCH_DIR,
                        help=f"Directory with articles.json and books/ for cross-matching (default: {DEFAULT_CROSS_MATCH_DIR})")

    args = parser.parse_args()

    if not Path(args.book_path).exists():
        print(f"ERROR: File not found: {args.book_path}", file=sys.stderr)
        sys.exit(1)

    process_book(
        book_path=args.book_path,
        output_dir=args.output_dir,
        cross_match_dir=args.cross_match_dir,
        chapter_filter=args.chapter,
    )


if __name__ == "__main__":
    main()
