"""Resurfacing Engine — schedules and generates prompts for book knowledge revisiting.

Three modes:
  1. Resonance Resurfacing: resurface individual highlights/captures with reflective prompts
  2. Cross-Book Dialogues: present claim pairs from different books with tension prompts
  3. Curriculum Review: retrieval practice questions from curriculum nodes (dates, people, events, sequences)

Output: resurfacing sessions as JSON, served via API endpoints.

Usage:
    python3 resurfacing_engine.py generate              # generate next session
    python3 resurfacing_engine.py generate --dialogues   # include cross-book dialogues
    python3 resurfacing_engine.py review                 # curriculum retrieval practice session
    python3 resurfacing_engine.py review --domain sicily # specific domain
    python3 resurfacing_engine.py status                 # show resurfacing state
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
PHYSICAL_BOOKS_PATH = Path(os.environ.get('PHYSICAL_BOOKS_PATH', '/opt/petrarca/data/physical_books.json'))
BOOK_RESEARCH_DIR = DATA_DIR / "book_research"
RESURFACING_STATE_PATH = DATA_DIR / "resurfacing_state.json"
CROSS_MATCHES_PATH = DATA_DIR / "book_article_connections.json"
CURRICULA_DIR = Path(os.environ.get('CURRICULUM_DIR', '/opt/petrarca/data/curricula'))

# Scheduling parameters
HIGHLIGHTS_PER_SESSION = 3
DIALOGUES_PER_SESSION = 1
MIN_DAYS_BETWEEN_RESURFACE = 7
DORMANT_AFTER_SKIPS = 2

# Expanding intervals (days)
INTERVALS = [7, 14, 30, 60, 120, 180]


def log(msg: str):
    print(f"[resurfacing] {msg}", flush=True)


def load_state() -> dict:
    """Load resurfacing state: per-capture tracking."""
    if RESURFACING_STATE_PATH.exists():
        return json.loads(RESURFACING_STATE_PATH.read_text())
    return {'captures': {}, 'sessions': [], 'last_session': None}


def save_state(state: dict):
    RESURFACING_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_books_and_captures() -> tuple[list[dict], list[dict]]:
    try:
        from db import load_all_books_and_captures
        data = load_all_books_and_captures()
        return data.get('books', []), data.get('captures', [])
    except Exception:
        # Fallback to JSON if DB not available
        if not PHYSICAL_BOOKS_PATH.exists():
            return [], []
        data = json.loads(PHYSICAL_BOOKS_PATH.read_text())
        return data.get('books', []), data.get('captures', [])


def load_research(book_id: str) -> dict | None:
    path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    if path.exists():
        return json.loads(path.read_text())
    return None


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------

def score_book_for_resurfacing(book: dict, captures: list[dict],
                                current_books: list[dict]) -> float:
    """Score a finished book for resurfacing priority."""
    book_captures = [c for c in captures if c['book_id'] == book['id']]
    highlight_count = len(book_captures)

    if highlight_count == 0:
        return 0.0

    # Time since finish (months)
    finished_date = book.get('finished_date') or book.get('last_interaction_at', 0)
    if isinstance(finished_date, str):
        try:
            from datetime import datetime as dt
            finished_date = int(dt.fromisoformat(finished_date.replace('Z', '+00:00')).timestamp() * 1000)
        except (ValueError, AttributeError):
            finished_date = 0
    months_since = max(1, (time.time() * 1000 - finished_date) / (30 * 24 * 3600 * 1000))

    # Topic overlap with currently-reading books
    book_topics = set(t.lower() for t in book.get('topics', []))
    current_topics = set()
    for cb in current_books:
        if cb.get('reading_status') == 'reading':
            current_topics.update(t.lower() for t in cb.get('topics', []))
    topic_overlap = len(book_topics & current_topics)

    # Check cross-source connections
    research = load_research(book['id'])
    connection_count = len(research.get('article_connections', [])) if research else 0

    score = (
        highlight_count * 2.0
        + connection_count * 3.0
        + topic_overlap * 5.0
        + min(months_since, 24) * 0.5  # older books get slight boost, capped at 2 years
    )
    return score


def score_capture_for_resurfacing(capture: dict, state: dict,
                                   book: dict | None = None) -> float:
    """Score an individual capture for resurfacing priority."""
    cap_state = state.get('captures', {}).get(capture['id'], {})

    # Skip dormant
    if cap_state.get('dormant', False):
        return -1.0

    # Skip if resurfaced too recently
    last_resurfaced = cap_state.get('last_resurfaced_at', 0)
    days_since = (time.time() * 1000 - last_resurfaced) / (24 * 3600 * 1000)
    resurface_count = cap_state.get('resurface_count', 0)

    if resurface_count > 0:
        required_interval = INTERVALS[min(resurface_count - 1, len(INTERVALS) - 1)]
        if days_since < required_interval:
            return -1.0  # not due yet

    # Higher score for captures with text content
    has_text = bool(capture.get('text') or capture.get('ocr_text') or capture.get('transcript'))
    text_bonus = 2.0 if has_text else 0.0

    # Higher score for captures with user notes
    note_bonus = 3.0 if capture.get('user_note') else 0.0

    # Overdue bonus
    overdue_days = max(0, days_since - INTERVALS[min(resurface_count, len(INTERVALS) - 1)])
    overdue_bonus = min(overdue_days * 0.5, 10.0)

    return text_bonus + note_bonus + overdue_bonus + random.random() * 2.0


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def generate_resonance_prompt(capture: dict, book: dict,
                               resurface_count: int,
                               current_books: list[dict] | None = None) -> dict:
    """Generate a context-aware resonance prompt for a capture."""

    title = book.get('title', 'this book')
    text = capture.get('text') or capture.get('ocr_text') or capture.get('transcript') or ''
    text_preview = text[:150] + ('...' if len(text) > 150 else '')
    chapter = capture.get('chapter', '')

    # Time since capture
    created_at = capture.get('created_at', 0)
    months_since = max(1, int((time.time() * 1000 - created_at) / (30 * 24 * 3600 * 1000)))
    time_desc = f"{months_since} month{'s' if months_since != 1 else ''}" if months_since < 24 else f"{months_since // 12} year{'s' if months_since > 23 else ''}"

    # Find currently-reading books with topic overlap
    current_book = None
    if current_books:
        book_topics = set(t.lower() for t in book.get('topics', []))
        for cb in current_books:
            if cb.get('reading_status') == 'reading' and cb['id'] != book['id']:
                cb_topics = set(t.lower() for t in cb.get('topics', []))
                if book_topics & cb_topics:
                    current_book = cb
                    break

    # Select prompt based on count and context
    if current_book and resurface_count >= 1:
        prompt_type = 'connect_to_current'
        prompt_text = (
            f"You're currently reading \"{current_book['title']}\". "
            f"This highlight from \"{title}\" seems related. Do you see the connection?"
        )
    elif resurface_count == 0:
        prompt_type = 'reconnect'
        prompts = [
            f"You highlighted this in \"{title}\" {time_desc} ago. What do you remember about why it struck you?",
            f"From \"{title}\": what was the argument this passage was part of?",
        ]
        prompt_text = random.choice(prompts)
    elif resurface_count == 1:
        prompt_type = 'reflect'
        prompts = [
            f"Has your thinking about this changed since you read \"{title}\"?",
            f"Where have you encountered this idea since reading \"{title}\"?",
        ]
        prompt_text = random.choice(prompts)
    elif months_since >= 12:
        prompt_type = 'deep_reconnect'
        prompts = [
            f"It's been {time_desc} since you read \"{title}\". What's the single idea that has stuck with you?",
            f"If you had to explain \"{title}\" to someone in one sentence, what would you say now?",
        ]
        prompt_text = random.choice(prompts)
    else:
        prompt_type = 'evolve'
        prompts = [
            f"Looking back at this highlight from \"{title}\" — how does it connect to your current reading?",
            f"What would you add to this note now that you didn't think of at the time?",
        ]
        prompt_text = random.choice(prompts)

    return {
        'type': 'resonance',
        'prompt_type': prompt_type,
        'prompt_text': prompt_text,
        'capture_id': capture['id'],
        'book_id': book['id'],
        'book_title': title,
        'book_author': book.get('author', ''),
        'book_cover_url': book.get('cover_url'),
        'chapter': chapter,
        'highlight_text': text_preview,
        'full_text': text,
        'months_since_capture': months_since,
        'resurface_count': resurface_count,
    }


def generate_cross_book_dialogue(books: list[dict], captures: list[dict]) -> dict | None:
    """Find an interesting claim pair across two books and generate a dialogue prompt."""
    from claude_llm import call_claude

    # Collect all book research claims grouped by book
    book_claims = {}
    for book in books:
        if book.get('reading_status') not in ('finished', 'reading'):
            continue
        research = load_research(book['id'])
        if not research:
            continue
        claims = []
        for ch_num, ch_data in research.get('chapter_research', {}).items():
            if isinstance(ch_data, dict):
                for claim_text in ch_data.get('claims', []):
                    claims.append({
                        'text': claim_text,
                        'chapter': ch_num,
                        'book_id': book['id'],
                        'book_title': book.get('title', ''),
                        'book_author': book.get('author', ''),
                    })
        if claims:
            book_claims[book['id']] = claims

    if len(book_claims) < 2:
        return None

    # Pick two books with topic overlap
    book_ids = list(book_claims.keys())
    book_map = {b['id']: b for b in books}

    best_pair = None
    best_overlap = 0
    for i, bid_a in enumerate(book_ids):
        for bid_b in book_ids[i+1:]:
            topics_a = set(t.lower() for t in book_map.get(bid_a, {}).get('topics', []))
            topics_b = set(t.lower() for t in book_map.get(bid_b, {}).get('topics', []))
            overlap = len(topics_a & topics_b)
            if overlap > best_overlap:
                best_overlap = overlap
                best_pair = (bid_a, bid_b)

    if not best_pair:
        # Pick random pair
        bid_a, bid_b = random.sample(book_ids, 2)
        best_pair = (bid_a, bid_b)

    bid_a, bid_b = best_pair
    claims_a = book_claims[bid_a]
    claims_b = book_claims[bid_b]

    # Pick claims (random for now; with embeddings, would pick by similarity)
    claim_a = random.choice(claims_a)
    claim_b = random.choice(claims_b)

    # Generate tension prompt via LLM
    tension_prompt_request = f"""Two books the reader has read make related claims:

Book A: "{claim_a['book_title']}" by {claim_a['book_author']}
Claim A: "{claim_a['text']}"

Book B: "{claim_b['book_title']}" by {claim_b['book_author']}
Claim B: "{claim_b['text']}"

Generate a brief (1-2 sentence) prompt that:
1. Acknowledges both perspectives
2. Asks the reader to articulate the tension, connection, or synthesis
3. Is open-ended — there's no right answer

Return ONLY the prompt text, nothing else."""

    tension_text = call_claude(tension_prompt_request, timeout=60, model='sonnet')
    if not tension_text:
        tension_text = (
            f"How do these two perspectives relate? "
            f"Where do {claim_a['book_author']} and {claim_b['book_author']} agree or differ?"
        )

    return {
        'type': 'dialogue',
        'claim_a': {
            'text': claim_a['text'],
            'book_id': claim_a['book_id'],
            'book_title': claim_a['book_title'],
            'book_author': claim_a['book_author'],
            'chapter': claim_a['chapter'],
        },
        'claim_b': {
            'text': claim_b['text'],
            'book_id': claim_b['book_id'],
            'book_title': claim_b['book_title'],
            'book_author': claim_b['book_author'],
            'chapter': claim_b['chapter'],
        },
        'tension_prompt': tension_text.strip(),
    }


# ---------------------------------------------------------------------------
# Session generation
# ---------------------------------------------------------------------------

def generate_session(include_dialogues: bool = True) -> dict:
    """Generate a resurfacing session: highlights + optional dialogue."""
    state = load_state()
    books, captures = load_books_and_captures()

    if not books or not captures:
        return {'items': [], 'generated_at': _now()}

    book_map = {b['id']: b for b in books}
    current_books = [b for b in books if b.get('reading_status') == 'reading']

    # Score and select captures for resonance
    scored_captures = []
    for cap in captures:
        book = book_map.get(cap.get('book_id'))
        if not book:
            continue
        # Only resurface from finished or reading books
        if book.get('reading_status') not in ('finished', 'reading'):
            continue
        # Need text content
        if not (cap.get('text') or cap.get('ocr_text') or cap.get('transcript')):
            continue

        score = score_capture_for_resurfacing(cap, state, book)
        if score > 0:
            scored_captures.append((score, cap, book))

    scored_captures.sort(key=lambda x: x[0], reverse=True)

    items = []

    # Add top N resonance items
    for score, cap, book in scored_captures[:HIGHLIGHTS_PER_SESSION]:
        cap_state = state.get('captures', {}).get(cap['id'], {})
        resurface_count = cap_state.get('resurface_count', 0)

        prompt = generate_resonance_prompt(cap, book, resurface_count, current_books)
        items.append(prompt)

        # Update state
        if cap['id'] not in state['captures']:
            state['captures'][cap['id']] = {}
        state['captures'][cap['id']]['last_resurfaced_at'] = int(time.time() * 1000)
        state['captures'][cap['id']]['resurface_count'] = resurface_count + 1

    # Add cross-book dialogue
    if include_dialogues and len(book_map) >= 2:
        dialogue = generate_cross_book_dialogue(books, captures)
        if dialogue:
            items.append(dialogue)

    session = {
        'id': f'rs_{int(time.time())}',
        'items': items,
        'generated_at': _now(),
        'resonance_count': len([i for i in items if i['type'] == 'resonance']),
        'dialogue_count': len([i for i in items if i['type'] == 'dialogue']),
    }

    state['sessions'].append({
        'id': session['id'],
        'generated_at': session['generated_at'],
        'item_count': len(items),
    })
    state['last_session'] = session['generated_at']

    save_state(state)
    log(f"Session {session['id']}: {session['resonance_count']} resonance + {session['dialogue_count']} dialogues")

    return session


def record_response(capture_id: str, response_text: str, response_type: str = 'text'):
    """Record a user's response to a resurfacing prompt."""
    state = load_state()

    if capture_id not in state['captures']:
        state['captures'][capture_id] = {}

    cap_state = state['captures'][capture_id]

    # Record response
    if 'responses' not in cap_state:
        cap_state['responses'] = []
    cap_state['responses'].append({
        'text': response_text,
        'type': response_type,
        'created_at': _now(),
    })

    # Reset skip counter
    cap_state['consecutive_skips'] = 0
    cap_state['dormant'] = False

    save_state(state)
    log(f"Response recorded for {capture_id} ({len(response_text)} chars)")


def record_skip(capture_id: str):
    """Record that user skipped a resurfacing prompt."""
    state = load_state()

    if capture_id not in state['captures']:
        state['captures'][capture_id] = {}

    cap_state = state['captures'][capture_id]
    skips = cap_state.get('consecutive_skips', 0) + 1
    cap_state['consecutive_skips'] = skips

    if skips >= DORMANT_AFTER_SKIPS:
        cap_state['dormant'] = True
        log(f"Capture {capture_id} → dormant (skipped {skips}x)")

    save_state(state)


def get_status() -> dict:
    """Get resurfacing status overview."""
    state = load_state()
    books, captures = load_books_and_captures()

    text_captures = [c for c in captures if c.get('text') or c.get('ocr_text') or c.get('transcript')]
    tracked = state.get('captures', {})
    dormant = sum(1 for cs in tracked.values() if cs.get('dormant', False))
    total_responses = sum(len(cs.get('responses', [])) for cs in tracked.values())
    total_resurfaces = sum(cs.get('resurface_count', 0) for cs in tracked.values())

    return {
        'total_books': len(books),
        'finished_books': len([b for b in books if b.get('reading_status') == 'finished']),
        'total_captures': len(captures),
        'resurfaceable_captures': len(text_captures),
        'tracked_captures': len(tracked),
        'dormant_captures': dormant,
        'total_resurfaces': total_resurfaces,
        'total_responses': total_responses,
        'sessions_generated': len(state.get('sessions', [])),
        'last_session': state.get('last_session'),
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Curriculum retrieval practice
# ---------------------------------------------------------------------------

REVIEW_STATE_PATH = DATA_DIR / "curriculum_review_state.json"
QUESTIONS_PER_REVIEW = 8
ORDERING_PER_REVIEW = 2

# Review intervals: same expanding schedule as captures
REVIEW_INTERVALS = [1, 3, 7, 14, 30, 60, 120]


def load_review_state() -> dict:
    """Load curriculum review state: per-question tracking."""
    if REVIEW_STATE_PATH.exists():
        return json.loads(REVIEW_STATE_PATH.read_text())
    return {'questions': {}, 'sessions': [], 'last_session': None}


def save_review_state(state: dict):
    REVIEW_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _find_curricula_with_questions() -> list[dict]:
    """Find all curricula that have retrieval question files."""
    results = []
    if not CURRICULA_DIR.exists():
        # Try local path for development
        local = Path(__file__).parent.parent / 'data' / 'curricula'
        if local.exists():
            search_dir = local
        else:
            return []
    else:
        search_dir = CURRICULA_DIR

    for path in search_dir.glob('*_retrieval_questions.json'):
        domain_slug = path.name.replace('_retrieval_questions.json', '')
        questions = json.loads(path.read_text())
        # Check for ordering questions too
        ordering_path = search_dir / f'{domain_slug}_ordering_questions.json'
        ordering = json.loads(ordering_path.read_text()) if ordering_path.exists() else []
        results.append({
            'domain': domain_slug,
            'questions': questions,
            'ordering_questions': ordering,
            'path': str(path),
        })
    return results


def generate_curriculum_review(domain_filter: str | None = None) -> dict:
    """Generate a curriculum retrieval practice session.

    Selects questions that are due for review using expanding intervals.
    Mixes question types: factual recall + temporal ordering.
    """
    state = load_review_state()
    curricula = _find_curricula_with_questions()

    if domain_filter:
        curricula = [c for c in curricula if domain_filter.lower() in c['domain'].lower()]

    if not curricula:
        return {'items': [], 'generated_at': _now(), 'domain': domain_filter or 'all',
                'message': 'No retrieval questions found. Generate them first.'}

    # Collect all questions across matching curricula
    all_questions = []
    all_ordering = []
    for curr in curricula:
        for q in curr['questions']:
            q_id = hashlib.md5(q['question'].encode()).hexdigest()[:12]
            q['_id'] = q_id
            q['_domain'] = curr['domain']
            all_questions.append(q)
        for o in curr['ordering_questions']:
            o_id = hashlib.md5(o['question'].encode()).hexdigest()[:12]
            o['_id'] = o_id
            o['_domain'] = curr['domain']
            all_ordering.append(o)

    # Score questions: due for review get positive scores, not-yet-due get negative
    now_ts = time.time() * 1000
    scored = []
    for q in all_questions:
        q_state = state['questions'].get(q['_id'], {})
        review_count = q_state.get('review_count', 0)
        last_reviewed = q_state.get('last_reviewed_at', 0)

        if review_count == 0:
            # Never reviewed — high priority for new questions
            score = 10.0 + random.random() * 2.0
        else:
            # Check if due
            interval_idx = min(review_count - 1, len(REVIEW_INTERVALS) - 1)
            required_days = REVIEW_INTERVALS[interval_idx]
            days_since = (now_ts - last_reviewed) / (24 * 3600 * 1000)
            if days_since < required_days:
                score = -1.0  # Not due
            else:
                overdue = days_since - required_days
                score = 5.0 + min(overdue * 0.3, 5.0) + random.random()

        # Boost questions the user got wrong last time
        if q_state.get('last_result') == 'wrong':
            score += 3.0

        scored.append((score, q))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [q for s, q in scored[:QUESTIONS_PER_REVIEW] if s > 0]

    # Add ordering questions (pick from due ones, or random if none due)
    ordering_scored = []
    for o in all_ordering:
        o_state = state['questions'].get(o['_id'], {})
        review_count = o_state.get('review_count', 0)
        last_reviewed = o_state.get('last_reviewed_at', 0)
        if review_count == 0:
            ordering_scored.append((10.0, o))
        else:
            interval_idx = min(review_count - 1, len(REVIEW_INTERVALS) - 1)
            required_days = REVIEW_INTERVALS[interval_idx]
            days_since = (now_ts - last_reviewed) / (24 * 3600 * 1000)
            if days_since >= required_days:
                ordering_scored.append((5.0 + random.random(), o))

    ordering_scored.sort(key=lambda x: x[0], reverse=True)
    selected_ordering = [o for s, o in ordering_scored[:ORDERING_PER_REVIEW] if s > 0]

    # Build session items
    items = []
    for q in selected:
        items.append({
            'type': 'retrieval',
            'question_id': q['_id'],
            'question': q['question'],
            'answer': q['answer'],
            'question_type': q.get('type', 'unknown'),
            'node_title': q.get('node_title', ''),
            'domain': q['_domain'],
        })
    for o in selected_ordering:
        items.append({
            'type': 'temporal_ordering',
            'question_id': o['_id'],
            'question': o['question'],
            'answer': o['answer'],
            'cluster_label': o.get('cluster_label', ''),
            'domain': o['_domain'],
        })

    # Shuffle to interleave types
    random.shuffle(items)

    session = {
        'id': f'cr_{int(time.time())}',
        'items': items,
        'generated_at': _now(),
        'domain': domain_filter or 'all',
        'retrieval_count': len(selected),
        'ordering_count': len(selected_ordering),
        'total_questions_in_pool': len(all_questions),
        'total_ordering_in_pool': len(all_ordering),
    }

    state['sessions'].append({
        'id': session['id'],
        'generated_at': session['generated_at'],
        'item_count': len(items),
    })
    state['last_session'] = session['generated_at']
    save_review_state(state)

    log(f"Review session {session['id']}: {len(selected)} retrieval + {len(selected_ordering)} ordering from {len(curricula)} curricula")
    return session


def record_review_result(question_id: str, result: str):
    """Record result for a curriculum review question.

    Args:
        question_id: The question's hash ID
        result: 'correct', 'partial', or 'wrong'
    """
    state = load_review_state()
    if question_id not in state['questions']:
        state['questions'][question_id] = {}

    q_state = state['questions'][question_id]
    q_state['review_count'] = q_state.get('review_count', 0) + 1
    q_state['last_reviewed_at'] = int(time.time() * 1000)
    q_state['last_result'] = result

    # Track history
    if 'history' not in q_state:
        q_state['history'] = []
    q_state['history'].append({
        'result': result,
        'at': _now(),
    })

    # If wrong, reset interval (drop back to short interval)
    if result == 'wrong':
        q_state['review_count'] = max(1, q_state.get('review_count', 1) - 2)

    save_review_state(state)
    log(f"Review result for {question_id}: {result} (count: {q_state['review_count']})")


def get_review_status() -> dict:
    """Get curriculum review status overview."""
    state = load_review_state()
    curricula = _find_curricula_with_questions()

    total_qs = sum(len(c['questions']) for c in curricula)
    total_ordering = sum(len(c['ordering_questions']) for c in curricula)
    tracked = state.get('questions', {})
    reviewed_at_least_once = sum(1 for q in tracked.values() if q.get('review_count', 0) > 0)
    correct_count = sum(1 for q in tracked.values() if q.get('last_result') == 'correct')
    wrong_count = sum(1 for q in tracked.values() if q.get('last_result') == 'wrong')

    return {
        'curricula_with_questions': len(curricula),
        'domains': [c['domain'] for c in curricula],
        'total_retrieval_questions': total_qs,
        'total_ordering_questions': total_ordering,
        'reviewed_at_least_once': reviewed_at_least_once,
        'last_correct': correct_count,
        'last_wrong': wrong_count,
        'sessions_generated': len(state.get('sessions', [])),
        'last_session': state.get('last_session'),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Resurfacing Engine")
    parser.add_argument("command", choices=['generate', 'status', 'review', 'review-status'],
                        help="generate: book resurfacing; review: curriculum retrieval practice; status/review-status: stats")
    parser.add_argument("--dialogues", action="store_true",
                        help="Include cross-book dialogues in session")
    parser.add_argument("--no-dialogues", action="store_true",
                        help="Skip cross-book dialogues")
    parser.add_argument("--domain", type=str, default=None,
                        help="Filter curriculum review to a specific domain (e.g. 'sicily')")
    args = parser.parse_args()

    if args.command == 'status':
        status = get_status()
        print(json.dumps(status, indent=2))
    elif args.command == 'generate':
        include_dialogues = not args.no_dialogues
        session = generate_session(include_dialogues=include_dialogues)
        print(json.dumps(session, indent=2))
    elif args.command == 'review':
        session = generate_curriculum_review(domain_filter=args.domain)
        print(json.dumps(session, indent=2))
    elif args.command == 'review-status':
        status = get_review_status()
        print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
