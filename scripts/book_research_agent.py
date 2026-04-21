"""Book Research Agent — autonomously researches books when added or progress updated.

Three modes:
  1. research_book() — full book research on add (thesis, chapters, connections, suggestions)
  2. get_chapter_insights() — research for a specific chapter + article connections
  3. generate_story_so_far() — personalized briefing for returning after a gap

Output: data/book_research/{book_id}.json

Uses call_with_search() for Gemini + Google Search grounding.
"""

import json
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
BOOK_RESEARCH_DIR = DATA_DIR / "book_research"
ARTICLES_PATH = DATA_DIR / "articles.json"

BOOK_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)


def _parse_json(text: str) -> dict | list | None:
    """Extract JSON from LLM response, handling markdown fences."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object/array in the text
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = cleaned.find(start_char)
            if start >= 0:
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == start_char:
                        depth += 1
                    elif cleaned[i] == end_char:
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:i + 1])
                        except json.JSONDecodeError:
                            break
        return None


def _load_articles() -> list[dict]:
    """Load articles.json for topic/claim matching."""
    if not ARTICLES_PATH.exists():
        return []
    with open(ARTICLES_PATH) as f:
        return json.load(f)


def _find_article_connections(book_topics: list[str], articles: list[dict],
                               max_connections: int = 15) -> list[dict]:
    """Find articles whose topics overlap with book topics."""
    book_topic_set = {t.lower().strip() for t in book_topics}
    if not book_topic_set:
        return []

    scored = []
    for article in articles:
        article_topics = {t.lower().strip() for t in article.get('topics', [])}
        overlap = book_topic_set & article_topics
        if overlap:
            scored.append({
                'article_id': article['id'],
                'article_title': article.get('title', ''),
                'matching_topics': sorted(overlap),
                'overlap_count': len(overlap),
            })

    scored.sort(key=lambda x: x['overlap_count'], reverse=True)
    return scored[:max_connections]


def research_book(book_id: str, title: str, author: str,
                  isbn: str | None, chapters: list[dict],
                  topics: list[str]) -> dict:
    """Full book research — thesis, chapter claims, article connections, suggested reading.

    Args:
        book_id: Physical book ID (pb_xxx)
        title: Book title
        author: Author name
        isbn: ISBN if known
        chapters: List of {number, title, start_page?}
        topics: Topic tags from book identification

    Returns:
        Research dict (also saved to data/book_research/{book_id}.json)
    """
    from claude_llm import call_claude_search, call_claude_json

    print(f'[book-research] Researching "{title}" by {author}...', flush=True)
    t0 = time.time()

    # Step 1: Book-level research (thesis, arguments, reception)
    book_prompt = f"""Research the book "{title}" by {author}.
{f'ISBN: {isbn}' if isbn else ''}

Provide:
1. The book's central thesis or argument (2-3 sentences)
2. The major debates or scholarly conversations this book participates in
3. Key terms or concepts the book introduces or develops
4. How the book was received — key praise and criticism

Return a JSON object:
{{
  "thesis": "The book's central argument in 2-3 sentences",
  "debates": ["debate 1", "debate 2"],
  "key_terms": [{{"term": "name", "definition": "brief definition"}}],
  "reception": "1-2 sentences on reception"
}}
Return ONLY valid JSON."""

    book_result = call_claude_search(book_prompt, timeout=300)
    book_data = _parse_json(book_result) if book_result else None
    if not book_data or not isinstance(book_data, dict):
        book_data = {'thesis': '', 'debates': [], 'key_terms': [], 'reception': ''}

    # Step 2: Chapter-level research
    chapter_research = {}
    if chapters:
        # Research chapters in batches to reduce API calls
        chapter_list = '\n'.join(
            f"  {ch.get('number', i+1)}. {ch.get('title', f'Chapter {i+1}')}"
            for i, ch in enumerate(chapters)
        )

        chapter_prompt = f"""For the book "{title}" by {author}, research each chapter and provide a summary and key claims.

Chapters:
{chapter_list}

For each chapter, provide:
- A 2-3 sentence summary of the chapter's argument
- 3-5 atomic claims (single declarative sentences stating what the chapter argues)
- 2-3 key terms introduced or discussed

Return a JSON object where keys are chapter numbers (as strings):
{{
  "1": {{
    "summary": "Chapter 1 argues that...",
    "claims": ["Claim 1", "Claim 2", "Claim 3"],
    "key_terms": ["term1", "term2"]
  }},
  "2": {{
    "summary": "Chapter 2 argues that...",
    "claims": ["Claim 1", "Claim 2"],
    "key_terms": ["term1"]
  }}
}}
Return ONLY valid JSON."""

        chapter_result = call_claude_search(chapter_prompt, timeout=600)
        parsed_chapters = _parse_json(chapter_result) if chapter_result else None
        if parsed_chapters and isinstance(parsed_chapters, dict):
            chapter_research = parsed_chapters

    # Step 3: Find article connections via topic overlap
    articles = _load_articles()
    all_topics = list(set(topics))
    # Also add topics from chapter research
    for ch_data in chapter_research.values():
        if isinstance(ch_data, dict):
            all_topics.extend(ch_data.get('key_terms', []))

    article_connections = _find_article_connections(all_topics, articles)

    # Enrich connections with connection type using LLM
    enriched_connections = []
    if article_connections and book_data.get('thesis'):
        connection_items = []
        for conn in article_connections[:10]:
            # Find article's one-line summary
            art = next((a for a in articles if a['id'] == conn['article_id']), None)
            if art:
                connection_items.append({
                    'article_id': conn['article_id'],
                    'article_title': conn['article_title'],
                    'article_summary': art.get('one_line_summary', ''),
                    'matching_topics': conn['matching_topics'],
                })

        if connection_items:
            classify_prompt = f"""Book: "{title}" by {author}
Thesis: {book_data['thesis']}

These articles from the reader's feed share topics with this book:
{json.dumps(connection_items, indent=2)}

For each article, classify the connection type and explain why it's relevant.
Return a JSON array:
[{{
  "article_id": "...",
  "article_title": "...",
  "connection_type": "extends|contradicts|complements",
  "reason": "1-sentence explanation of how this article connects to the book"
}}]
Return ONLY valid JSON."""

            parsed_connections = call_claude_json(classify_prompt, timeout=180, model='sonnet')
            if parsed_connections and isinstance(parsed_connections, list):
                enriched_connections = parsed_connections

    # Fallback: use raw connections if enrichment failed
    if not enriched_connections:
        enriched_connections = [{
            'article_id': c['article_id'],
            'article_title': c['article_title'],
            'connection_type': 'complements',
            'reason': f"Shares topics: {', '.join(c['matching_topics'])}",
        } for c in article_connections[:10]]

    # Step 4: Suggest complementary reading
    suggested_reading = []
    suggest_prompt = f"""Someone is reading "{title}" by {author}.
Topics: {', '.join(topics)}
Thesis: {book_data.get('thesis', 'unknown')}

Suggest 3-5 freely accessible articles, essays, or papers that would:
- Complement the book's arguments with additional evidence
- Present counterarguments or alternative perspectives
- Provide historical/cultural context the book assumes

For each suggestion, provide a working URL if possible (prefer stable URLs from academic sites, major publications, or well-known blogs).

Return a JSON array:
[{{
  "title": "Article/essay title",
  "author": "Author if known",
  "url": "https://... (or null if unknown)",
  "reason": "1-sentence explanation of why this complements the book"
}}]
Return ONLY valid JSON."""

    suggest_result = call_with_search(suggest_prompt, max_tokens=4096)
    parsed_suggestions = _parse_json(suggest_result) if suggest_result else None
    if parsed_suggestions and isinstance(parsed_suggestions, list):
        suggested_reading = parsed_suggestions

    # Build and save result
    elapsed = time.time() - t0
    result = {
        'book_id': book_id,
        'title': title,
        'author': author,
        'isbn': isbn,
        'thesis': book_data.get('thesis', ''),
        'debates': book_data.get('debates', []),
        'key_terms': book_data.get('key_terms', []),
        'reception': book_data.get('reception', ''),
        'chapter_research': chapter_research,
        'article_connections': enriched_connections,
        'suggested_reading': suggested_reading,
        'topics': topics,
        'researched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'research_time_seconds': round(elapsed, 1),
    }

    output_path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f'[book-research] Done in {elapsed:.1f}s: '
          f'{len(chapter_research)} chapters, '
          f'{len(enriched_connections)} article connections, '
          f'{len(suggested_reading)} suggestions', flush=True)

    return result


def get_chapter_insights(book_id: str, chapter_number: int,
                         chapter_title: str,
                         captures: list[dict] | None = None) -> dict:
    """Get research and connections for a specific chapter.

    If research exists, returns cached chapter data + article connections.
    If not, researches just this chapter.
    """
    from claude_llm import call_claude_search

    research_path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    if research_path.exists():
        research = json.loads(research_path.read_text())
    else:
        research = {'chapter_research': {}, 'article_connections': [],
                     'title': '', 'author': '', 'thesis': ''}

    ch_key = str(chapter_number)
    ch_data = research.get('chapter_research', {}).get(ch_key)

    # If chapter not yet researched, research it now
    if not ch_data:
        title = research.get('title', 'Unknown')
        author = research.get('author', 'Unknown')

        prompt = f"""For chapter {chapter_number} ("{chapter_title}") of "{title}" by {author}:

Provide:
1. A 2-3 sentence summary of the chapter's argument
2. 3-5 atomic claims (single declarative sentences)
3. 2-3 key terms introduced or discussed

Return JSON:
{{
  "summary": "...",
  "claims": ["...", "..."],
  "key_terms": ["...", "..."]
}}
Return ONLY valid JSON."""

        result = call_claude_search(prompt, timeout=300)
        ch_data = _parse_json(result) if result else None
        if not ch_data or not isinstance(ch_data, dict):
            ch_data = {'summary': '', 'claims': [], 'key_terms': []}

        # Cache in research file
        if 'chapter_research' not in research:
            research['chapter_research'] = {}
        research['chapter_research'][ch_key] = ch_data
        research_path.write_text(json.dumps(research, indent=2, ensure_ascii=False))

    # Filter article connections relevant to this chapter's topics
    ch_topics = {t.lower() for t in ch_data.get('key_terms', [])}
    ch_connections = []
    for conn in research.get('article_connections', []):
        conn_topics = {t.lower() for t in conn.get('matching_topics', [])}
        if ch_topics & conn_topics or not ch_topics:
            ch_connections.append(conn)

    return {
        'chapter_number': chapter_number,
        'chapter_title': chapter_title,
        'summary': ch_data.get('summary', ''),
        'claims': ch_data.get('claims', []),
        'key_terms': ch_data.get('key_terms', []),
        'connections': ch_connections[:5],
        'captures_count': len(captures) if captures else 0,
    }


def generate_story_so_far(book_id: str, title: str, author: str,
                          current_chapter: str | None,
                          current_page: int | None,
                          page_count: int | None,
                          captures: list[dict] | None = None) -> dict:
    """Generate a personalized 'Story So Far' briefing for returning after a gap.

    Combines server research with user captures to create context restoration.
    """
    from claude_llm import call_claude_json

    research_path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    research = {}
    if research_path.exists():
        research = json.loads(research_path.read_text())

    # Build context from research
    thesis = research.get('thesis', '')
    chapter_summaries = []
    for ch_num, ch_data in sorted(research.get('chapter_research', {}).items()):
        if isinstance(ch_data, dict) and ch_data.get('summary'):
            chapter_summaries.append(f"Chapter {ch_num}: {ch_data['summary']}")

    # Build context from captures
    capture_texts = []
    if captures:
        for cap in captures[-10:]:  # last 10 captures
            parts = []
            if cap.get('chapter'):
                parts.append(f"[{cap['chapter']}]")
            if cap.get('page_number'):
                parts.append(f"[p.{cap['page_number']}]")
            content = cap.get('text') or cap.get('ocr_text') or cap.get('transcript') or ''
            if content:
                parts.append(content[:200])
            if cap.get('extracted_ideas'):
                parts.append(f"Ideas: {'; '.join(cap['extracted_ideas'][:3])}")
            if parts:
                capture_texts.append(' '.join(parts))

    progress_str = ''
    if current_page and page_count:
        progress_str = f"Currently on page {current_page} of {page_count} ({round(current_page / page_count * 100)}% through)."
    if current_chapter:
        progress_str += f" Current chapter: {current_chapter}."

    prompt = f"""The reader is returning to "{title}" by {author} after being away.
{progress_str}

Book thesis: {thesis or 'Not yet researched.'}

Chapter summaries from research:
{chr(10).join(chapter_summaries) if chapter_summaries else 'No chapter research available.'}

Reader's own captures (most recent):
{chr(10).join(capture_texts) if capture_texts else 'No captures yet.'}

Generate a "Story So Far" briefing. This should:
1. Summarize the book's argument up to where the reader stopped, emphasizing what THEY captured (if any captures exist). If no captures, use the research summaries.
2. Pick 1-2 interesting insights to highlight (from captures if available, otherwise from research).
3. Preview what's coming next in the book.

Return JSON:
{{
  "argument_summary": "2-3 sentences summarizing the argument so far, personalized to the reader's captures",
  "highlights": [
    {{"text": "An interesting insight or capture", "why_it_matters": "Why this matters to the book's argument"}}
  ],
  "preview": "1 sentence about what's coming next",
  "articles_since": 0
}}
Return ONLY valid JSON."""

    parsed = call_claude_json(prompt, timeout=120, model='sonnet')
    if not parsed or not isinstance(parsed, dict):
        # Fallback: construct basic briefing from research
        parsed = {
            'argument_summary': thesis or f'You are reading "{title}" by {author}.',
            'highlights': [],
            'preview': 'Continue reading to discover what comes next.',
            'articles_since': 0,
        }

    # Add suggested reading from research
    parsed['suggested_reading'] = research.get('suggested_reading', [])[:3]

    return parsed


def load_book_research(book_id: str) -> dict | None:
    """Load existing research for a book."""
    research_path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    if research_path.exists():
        return json.loads(research_path.read_text())
    return None


def get_all_book_claims() -> list[dict]:
    """Collect all claims across all researched books for embedding.

    Returns list of {id, text, book_id, chapter_number, source} dicts.
    """
    all_claims = []
    for research_path in BOOK_RESEARCH_DIR.glob('*.json'):
        try:
            research = json.loads(research_path.read_text())
        except json.JSONDecodeError:
            continue

        book_id = research.get('book_id', research_path.stem)
        title = research.get('title', '')

        for ch_num, ch_data in research.get('chapter_research', {}).items():
            if not isinstance(ch_data, dict):
                continue
            for i, claim_text in enumerate(ch_data.get('claims', [])):
                claim_id = f'bk_{book_id}_{ch_num}_{i}'
                all_claims.append({
                    'id': claim_id,
                    'text': claim_text,
                    'book_id': book_id,
                    'book_title': title,
                    'chapter_number': ch_num,
                    'source': 'research',
                })

    return all_claims


# CLI for testing
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python book_research_agent.py <command> [args]")
        print("Commands:")
        print("  research <book_id> <title> <author> [topics...]")
        print("  chapter <book_id> <chapter_num> <chapter_title>")
        print("  story <book_id> <title> <author> [current_chapter]")
        print("  claims  -- list all book claims for embedding")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'research':
        book_id = sys.argv[2]
        title = sys.argv[3]
        author = sys.argv[4]
        topics = sys.argv[5:] if len(sys.argv) > 5 else []
        result = research_book(book_id, title, author, None, [], topics)
        print(json.dumps(result, indent=2))

    elif cmd == 'chapter':
        book_id = sys.argv[2]
        ch_num = int(sys.argv[3])
        ch_title = sys.argv[4]
        result = get_chapter_insights(book_id, ch_num, ch_title)
        print(json.dumps(result, indent=2))

    elif cmd == 'story':
        book_id = sys.argv[2]
        title = sys.argv[3]
        author = sys.argv[4]
        chapter = sys.argv[5] if len(sys.argv) > 5 else None
        result = generate_story_so_far(book_id, title, author, chapter, None, None)
        print(json.dumps(result, indent=2))

    elif cmd == 'claims':
        claims = get_all_book_claims()
        print(f'{len(claims)} book claims found:')
        for c in claims[:10]:
            print(f'  [{c["id"]}] {c["text"][:80]}...')

    else:
        print(f'Unknown command: {cmd}')
        sys.exit(1)
