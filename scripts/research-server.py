#!/usr/bin/env python3
"""
Petrarca Research Agent Server

Simple HTTP server that accepts research requests from the app,
spawns `claude -p` in the background to find diverse perspectives,
and serves completed results back to the app.

Run: python3 research-server.py
Port: 8090
Results stored in: /opt/petrarca/research-results/
"""

import asyncio
import email
import email.policy
import hashlib
import json
import os
import random
import re
import string
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, unquote

try:
    from limbic.cerebellum.claude_cli import log_cli_usage as _log_cli_usage
except ImportError:
    _log_cli_usage = None


def _run_claude_p(prompt: str, timeout: int, purpose: str) -> tuple[str | None, str | None]:
    """Run `claude -p` with --output-format json and log cost/usage to limbic.

    Returns (result_text, error_message). On success: (text, None). On failure:
    (None, "<human-readable error>"). Always logs usage when we get a parseable
    response, even on error.
    """
    # Strip CLAUDECODE (nested-session safety) + ANTHROPIC_* (force Max/OAuth auth
    # so the CLI doesn't silently bill an API key that may be set for the SDK path).
    _strip = ('CLAUDECODE', 'ANTHROPIC_API_KEY', 'ANTHROPIC_KEY', 'ANTHROPIC_AUTH_TOKEN')
    clean_env = {k: v for k, v in os.environ.items() if k not in _strip}
    try:
        proc = subprocess.run(
            ['claude', '-p', '--output-format', 'json', prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=clean_env,
        )
    except subprocess.TimeoutExpired:
        return None, f'claude timed out after {timeout}s'
    except FileNotFoundError:
        return None, 'claude CLI not found'

    try:
        response = json.loads(proc.stdout) if proc.stdout else None
    except json.JSONDecodeError:
        response = None

    if response is not None and _log_cli_usage is not None:
        try:
            _log_cli_usage(response, project='petrarca', purpose=purpose)
        except Exception:
            pass

    if proc.returncode != 0:
        return None, f'claude exited with code {proc.returncode}: {(proc.stderr or "")[:500]}'
    if response is None:
        return None, 'claude returned unparseable output'
    if response.get('is_error'):
        return None, f'claude error: {(response.get("result") or "unknown")[:300]}'
    return (response.get('result') or '').strip(), None


RESULTS_DIR = Path(os.environ.get('RESEARCH_RESULTS_DIR', '/opt/petrarca/research-results'))
INGEST_DIR = Path(os.environ.get('INGEST_DIR', '/opt/petrarca/ingest'))
PORT = int(os.environ.get('RESEARCH_PORT', '8090'))
INGEST_TOKEN = os.environ.get('PETRARCA_INGEST_TOKEN', '')
BOOKS_OUTPUT_DIR = Path(os.environ.get('BOOKS_OUTPUT_DIR', '/opt/petrarca/data/books'))
CROSS_MATCH_DIR = Path(os.environ.get('CROSS_MATCH_DIR', '/opt/petrarca/data'))
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import koigen_adapter
# Subprocess helper for import_url.py etc. Defaults to this server's interpreter.
VENV_PYTHON = os.environ.get('PETRARCA_PYTHON', sys.executable)

EMAILS_DIR = INGEST_DIR / 'emails'

CHAT_DIR = Path(os.environ.get('CHAT_DIR', '/opt/petrarca/data/chats'))
NOTES_DIR = Path(os.environ.get('NOTES_DIR', '/opt/petrarca/data/notes'))
AUDIO_DIR = Path(os.environ.get('AUDIO_DIR', '/opt/petrarca/data/audio'))
BOOK_UPLOADS_DIR = Path(os.environ.get('BOOK_UPLOADS_DIR', '/opt/petrarca/data/book-uploads'))
PHYSICAL_BOOKS_PATH = Path(os.environ.get('PHYSICAL_BOOKS_PATH', '/opt/petrarca/data/physical_books.json'))
LOG_DIR = Path(os.environ.get('LOG_DIR', '/opt/petrarca/data/logs'))
ARTICLES_PATH = Path(os.environ.get('ARTICLES_PATH', '/opt/petrarca/data/articles.json'))
SCRAPE_REPORTS_PATH = Path(os.environ.get('SCRAPE_REPORTS_PATH', '/opt/petrarca/data/scrape_reports.json'))
KINDLE_DATA_PATH = Path(os.environ.get('KINDLE_DATA_PATH', '/opt/petrarca/data/kindle_library.json'))
KINDLE_HIGHLIGHTS_PATH = Path(os.environ.get('KINDLE_HIGHLIGHTS_PATH', '/opt/petrarca/data/kindle_highlights.json'))
KINDLE_SYNC_LOG_PATH = Path(os.environ.get('KINDLE_SYNC_LOG_PATH', '/opt/petrarca/data/kindle_sync_log.jsonl'))
FEEDBACK_DIR = Path(os.environ.get('FEEDBACK_DIR', '/opt/petrarca/data/feedback'))
PROJECTS_PATH = Path(os.environ.get('PROJECTS_PATH', '/opt/petrarca/data/projects.json'))
PROJECTS_MEDIA_DIR = Path(os.environ.get('PROJECTS_MEDIA_DIR', '/opt/petrarca/data/projects'))
PHOTO_OCR_QUEUE_PATH = Path(os.environ.get('PHOTO_OCR_QUEUE_PATH', '/opt/petrarca/data/photo_ocr_queue.json'))
VOICE_ELICIT_CACHE_DIR = Path(os.environ.get('VOICE_ELICIT_CACHE_DIR', '/opt/petrarca/data/voice_elicit_cache'))
EXPLORE_CAPTURE_CACHE_DIR = Path(os.environ.get('EXPLORE_CAPTURE_CACHE_DIR', '/opt/petrarca/data/explore_capture_cache'))

from server_log import log_server_event
# Core curriculum functions from SQLite-backed module
from curriculum_db import (
    load_curriculum, list_curricula,
    load_knowledge_states, update_knowledge, get_coverage_report,
    map_book_to_curriculum, get_book_curriculum_context,
    import_assessment_answers,
    get_timeline,
    generate_review_stream,
    get_book_prescan,
)
# Functions not yet migrated to SQLite — still use JSON files
from curriculum import (
    generate_curriculum,
    start_elicitation, continue_elicitation,
    get_curriculum_graph_data, get_entity_index, build_entity_index,
    tag_curriculum_entities,
)
from bootstrap_entities import (
    build_extraction_prompt as _entity_extraction_prompt,
    parse_json_response as _entity_parse_json,
    insert_entities as _entity_insert,
)
from review_engine import (
    create_review_items_for_chapter, get_review_queue, generate_question,
    record_answer, get_review_stats, create_exploration_items, process_voice_memo,
    run_voice_elicitation, get_elicitation_candidates, generate_hamarquizen_session,
    generate_cross_book_hamarquizen, notify_article_read_curriculum,
)

SONIOX_API_KEY = os.environ.get('SONIOX_API_KEY', '557c7c5a86a2f5b8fa734ddbbe179f0f21fd342c762768c9af4f4ffff8c58e1f')
SONIOX_BASE_URL = 'https://api.soniox.com/v1'

TWIKIT_COOKIES_DIR = Path.home() / '.config' / 'twikit'
TWIKIT_COOKIES_PATH = TWIKIT_COOKIES_DIR / 'cookies.json'

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
INGEST_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job tracking for background curriculum generation
_curriculum_jobs: dict = {}  # job_id → {status, domain, domain_id?, node_count?, error?}
EMAILS_DIR.mkdir(parents=True, exist_ok=True)
CHAT_DIR.mkdir(parents=True, exist_ok=True)
NOTES_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
BOOK_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
VOICE_ELICIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
EXPLORE_CAPTURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Database + ID helpers
# ---------------------------------------------------------------------------

from db import get_connection, init_db, migrate_kindle_json_to_sqlite
from export_content_json import (
    export_articles_meta, export_article_content, compute_manifest,
    export_knowledge_index, export_clusters, export_syntheses,
)

def _gen_id(prefix: str) -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f'{prefix}_{int(time.time())}_{suffix}'


# ---------------------------------------------------------------------------
# Background photo OCR queue
# ---------------------------------------------------------------------------

_ocr_queue_lock = threading.Lock()
_ocr_results: dict[str, dict] = {}  # capture_id -> OCR result (kept in memory for polling)
_ocr_results_lock = threading.Lock()


def _load_ocr_queue() -> list[dict]:
    """Load pending OCR items from disk."""
    if not PHOTO_OCR_QUEUE_PATH.exists():
        return []
    try:
        return json.loads(PHOTO_OCR_QUEUE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_ocr_queue(queue: list[dict]):
    """Save OCR queue to disk."""
    PHOTO_OCR_QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def _enqueue_photo_ocr(item: dict):
    """Add a photo to the OCR processing queue."""
    with _ocr_queue_lock:
        queue = _load_ocr_queue()
        queue.append(item)
        _save_ocr_queue(queue)
    print(f'[ocr-queue] Enqueued {item["capture_id"]} ({len(queue)} in queue)', flush=True)


def _ocr_worker():
    """Background thread that processes the OCR queue."""
    while True:
        item = None
        with _ocr_queue_lock:
            queue = _load_ocr_queue()
            if queue:
                item = queue.pop(0)
                _save_ocr_queue(queue)

        if not item:
            time.sleep(2)
            continue

        capture_id = item['capture_id']
        photo_path = Path(item['photo_path'])
        print(f'[ocr-queue] Processing {capture_id}: {photo_path.name}', flush=True)

        try:
            result = process_book_ocr_page(
                photo_path,
                item.get('book_title', ''),
                item.get('page_number'),
                item.get('chapter'),
            )
            result['capture_id'] = capture_id
            result['status'] = 'completed'
            print(f'[ocr-queue] Completed {capture_id}', flush=True)
        except Exception as e:
            print(f'[ocr-queue] Error processing {capture_id}: {e}', flush=True)
            result = {
                'capture_id': capture_id,
                'status': 'failed',
                'error': str(e),
                'text': '', 'extracted_ideas': [], 'topics': [],
            }

        with _ocr_results_lock:
            _ocr_results[capture_id] = result

        # Also persist result to disk so it survives restarts
        results_path = BOOK_UPLOADS_DIR / f'ocr_result_{capture_id}.json'
        results_path.write_text(json.dumps(result))


# Start the OCR worker thread
_ocr_thread = threading.Thread(target=_ocr_worker, daemon=True)
_ocr_thread.start()


# ---------------------------------------------------------------------------
# Voice routing
# ---------------------------------------------------------------------------

def route_voice_input(transcript: str, source_context: dict) -> dict:
    """Classify voice input and route to appropriate handler.

    Returns: {"intent": "project_note|research_request|article_feedback|general_note",
              "project_id": str or None,
              "project_name": str or None,
              "confidence": 0.0-1.0,
              "cleaned_text": str}
    """
    conn = get_connection(readonly=True)
    active_projects = [dict(r) for r in conn.execute(
        "SELECT id, name FROM projects WHERE status = 'active'"
    ).fetchall()]
    conn.close()
    project_names_list = [p['name'] for p in active_projects]

    from claude_llm import call_claude_json

    prompt = f"""Classify this voice input. The user has these active projects: {json.dumps(project_names_list)}

Voice transcript: "{transcript}"

Source context: {json.dumps(source_context)}

Classify the intent as one of:
- "project_note": The user is adding a note to a specific project (mentions a project name or clearly refers to one)
- "research_request": The user is asking to research or investigate something
- "article_feedback": The user is giving feedback about the current article/content
- "general_note": A general thought or note not tied to a specific project

Return JSON only:
{{"intent": "...", "project_name": "..." or null, "confidence": 0.0-1.0, "cleaned_text": "the note text without the routing prefix"}}"""

    try:
        result = call_claude_json(prompt, timeout=60, model='sonnet')
        if not isinstance(result, dict):
            return {"intent": "general_note", "project_id": None, "project_name": None,
                    "confidence": 0.0, "cleaned_text": transcript}

        # Resolve project_name to project_id via fuzzy match
        matched_project = None
        if result.get('project_name'):
            target = result['project_name'].lower().strip()
            for p in active_projects:
                if target in p['name'].lower() or p['name'].lower() in target:
                    matched_project = p
                    break

        result['project_id'] = matched_project['id'] if matched_project else None
        if matched_project:
            result['project_name'] = matched_project['name']

        return result
    except Exception as e:
        print(f'[voice-routing] Classification failed: {e}', flush=True)
        return {"intent": "general_note", "project_id": None, "project_name": None,
                "confidence": 0.0, "cleaned_text": transcript}


def _route_and_enrich_feedback(feedback_id: str, transcript: str, context: dict):
    """Background: classify voice transcript and auto-create project note if matched."""
    try:
        routing = route_voice_input(transcript, context)
        print(f'[voice-routing] {feedback_id} → {routing["intent"]} '
              f'(project={routing.get("project_name")}, conf={routing.get("confidence")})', flush=True)

        # Update the feedback JSON with routing info
        meta_path = FEEDBACK_DIR / f'{feedback_id}.json'
        for _ in range(10):
            if meta_path.exists():
                break
            time.sleep(0.5)
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                meta['voice_routing'] = routing
                meta_path.write_text(json.dumps(meta, indent=2))
            except (json.JSONDecodeError, OSError) as e:
                print(f'[voice-routing] Failed to update feedback meta: {e}', flush=True)

        # Auto-create project note if matched
        if routing.get('intent') == 'project_note' and routing.get('project_id'):
            note_id = _gen_id('note')
            conn = get_connection()
            conn.execute(
                "INSERT INTO project_notes (id, project_id, text, audio_file, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, routing['project_id'], routing.get('cleaned_text', transcript),
                 None, json.dumps(context), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
            print(f'[voice-routing] Auto-created project note {note_id} for project {routing["project_id"]}', flush=True)

        # Auto-trigger microlearning for research requests
        if routing.get('intent') == 'research_request':
            try:
                from review_engine import create_microlearning_request
                query = routing.get('cleaned_text', transcript)
                source_domain = context.get('domain', '')
                source_node = context.get('node_id', '')
                card_id = create_microlearning_request(
                    query=query,
                    source_node_id=source_node or None,
                    source_domain=source_domain or None,
                    source_type='voice_wondering',
                )
                # Store reference in feedback meta
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        meta['microlearning_card_id'] = card_id
                        meta_path.write_text(json.dumps(meta, indent=2))
                    except Exception:
                        pass
                print(f'[voice→ml] feedback research → {card_id}: {query[:60]}', flush=True)
            except Exception as e:
                print(f'[voice→ml] feedback research trigger failed: {e}', flush=True)

    except Exception as e:
        print(f'[voice-routing] Background routing failed for {feedback_id}: {e}', flush=True)


def _route_and_enrich_note(note_id: str, transcript: str, article_id: str, article_title: str):
    """Background: classify voice note transcript and auto-create project note if matched."""
    try:
        context = {'type': 'article', 'id': article_id, 'title': article_title}
        routing = route_voice_input(transcript, context)
        print(f'[voice-routing] note {note_id} → {routing["intent"]} '
              f'(project={routing.get("project_name")}, conf={routing.get("confidence")})', flush=True)

        # Update the note JSON with routing info
        note_path = NOTES_DIR / f'{note_id}.json'
        if note_path.exists():
            try:
                note = json.loads(note_path.read_text())
                note['voice_routing'] = routing
                note_path.write_text(json.dumps(note, indent=2))
            except (json.JSONDecodeError, OSError) as e:
                print(f'[voice-routing] Failed to update note: {e}', flush=True)

        # Auto-create project note if matched
        if routing.get('intent') == 'project_note' and routing.get('project_id'):
            proj_note_id = _gen_id('note')
            conn = get_connection()
            conn.execute(
                "INSERT INTO project_notes (id, project_id, text, audio_file, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (proj_note_id, routing['project_id'], routing.get('cleaned_text', transcript),
                 None, json.dumps({'type': 'article', 'id': article_id, 'title': article_title}),
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
            print(f'[voice-routing] Auto-created project note {proj_note_id} from voice note {note_id}', flush=True)

    except Exception as e:
        print(f'[voice-routing] Background note routing failed for {note_id}: {e}', flush=True)


# ---------------------------------------------------------------------------
# Email processing (server-side)
# ---------------------------------------------------------------------------

def parse_email(raw_text: str) -> dict:
    """Parse raw email using Python email stdlib. Returns dict with subject, from, text_plain, text_html."""
    msg = email.message_from_string(raw_text, policy=email.policy.default)
    result = {
        'subject': str(msg.get('subject', '')).strip(),
        'from': str(msg.get('from', '')),
        'to': str(msg.get('to', '')),
        'date': str(msg.get('date', '')),
        'text_plain': '',
        'text_html': '',
    }

    # Strip Fwd:/Fw: prefixes
    result['subject'] = re.sub(r'^(Fwd?|Fw):\s*', '', result['subject'], flags=re.IGNORECASE).strip()

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain' and not result['text_plain']:
                result['text_plain'] = part.get_content() or ''
            elif ct == 'text/html' and not result['text_html']:
                result['text_html'] = part.get_content() or ''
    else:
        ct = msg.get_content_type()
        body = msg.get_content() or ''
        if ct == 'text/html':
            result['text_html'] = body
        else:
            result['text_plain'] = body

    return result


def score_url(url: str) -> int:
    """Score a URL for likelihood of being an article. Returns -1 for rejects, 0+ for candidates."""
    try:
        parsed = urlparse(url)
    except Exception:
        return -1

    hostname = (parsed.hostname or '').lower()
    pathname = (parsed.path or '').lower()
    full = url.lower()

    # --- Hard rejects ---
    if re.search(r'\.(png|jpg|jpeg|gif|svg|webp|ico|avif|mp3|mp4|css|js|woff2?|ttf|eot|zip|pdf)(\?|$)', pathname):
        return -1
    if 'substackcdn.com' in hostname:
        return -1
    if 'cdn.' in hostname and re.search(r'\.(png|jpg|jpeg|gif|svg|webp)', pathname):
        return -1
    reject_hosts = ['doubleclick.net', 'google-analytics.com', 'googleusercontent.com',
                    'mailchimp.com', 'sendgrid.net', 'list-manage.com', 'mandrillapp.com',
                    'mailgun.org', 'constantcontact.com', 'campaign-archive.com',
                    'apps.apple.com', 'play.google.com']
    if any(h in hostname for h in reject_hosts):
        return -1
    if re.match(r'^(click|track|open|pixel|beacon|email|links?)\.', hostname):
        return -1
    if re.search(r'unsub|opt-out|optout|manage.preferences|email-preferences|disable_email', full):
        return -1
    if 'substack.com' in hostname and re.match(r'^/(sign-in|account|app-link|embed|profile)', pathname):
        return -1
    if pathname in ('/', '/subscribe', '/publish', ''):
        return -1
    # Reject subscribe/share/action pages on any substack
    if re.search(r'\.substack\.com/(subscribe|action/|account)', full):
        return -1
    if re.match(r'^/@[^/]+/?$', pathname):
        return -1
    if re.search(r'1x1|beacon|pixel|\.gif\?', full):
        return -1
    if hostname == 't.co':
        return -1
    if re.match(r'^https?://(www\.)?(twitter|x)\.com/[^/]+/?$', url, re.IGNORECASE):
        return -1
    # Reject bare homepages (no meaningful path)
    if re.match(r'^/?(\?.*)?$', pathname):
        return -1
    # Reject unresolved redirect/tracking URLs — these should be resolved first
    if 'substack.com/redirect/' in full:
        return -1
    if re.search(r'/emails?/click/', full):
        return -1

    # --- Scoring ---
    score = 0
    segments = [s for s in pathname.split('/') if s]
    score += min(len(segments) * 2, 10)
    if len(pathname) > 20: score += 3
    if len(pathname) > 40: score += 2

    if re.search(r'substack\.com/p/', full): score += 15
    if re.search(r'open\.substack\.com/pub/[^/]+/p/', full): score += 20
    if re.search(r'medium\.com/.+/.+-[a-f0-9]{8,}', full): score += 15
    if re.search(r'/\d{4}/\d{2}/\d{2}/', pathname): score += 12
    if 'wordpress.com' in hostname and len(segments) >= 2: score += 10
    if re.search(r'/(article|post|blog|story|news|p)/', pathname, re.IGNORECASE): score += 8

    last_seg = segments[-1] if segments else ''
    if '-' in last_seg and len(last_seg) > 10: score += 5

    return score


def clean_url(url: str) -> str | None:
    """Clean tracking params and trailing punctuation from a URL."""
    cleaned = re.sub(r'[.,;:!?)\]}\'"]+$', '', url)
    cleaned = re.sub(r'#$', '', cleaned)
    try:
        parsed = urlparse(cleaned)
        qs = parse_qs(parsed.query, keep_blank_values=False)
        remove = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                  'mc_cid', 'mc_eid', 'ref', 'referer', 'fbclid', 'gclid'}
        filtered = {k: v for k, v in qs.items() if k not in remove}
        new_query = urlencode(filtered, doseq=True) if filtered else ''
        cleaned = parsed._replace(query=new_query).geturl()
        return cleaned
    except Exception:
        return None


def canonicalize_url(url: str) -> str:
    """Normalize URL for dedup: lowercase host, strip trailing slash and query."""
    try:
        parsed = urlparse(url)
        return f'{parsed.scheme}://{parsed.hostname.lower()}{parsed.path.rstrip("/")}'
    except Exception:
        return url


def decode_substack_redirect(url: str) -> str | None:
    """Decode Substack redirect URLs to extract the real destination.

    Current format (v2): substack.com/redirect/2/{payload}.{signature}
        Payload is base64url JSON with "e" field containing the destination URL.
        If "e" is a /subscribe page, the actual article may be in its "next" param.
    Legacy format: substack.com/redirect/{id}/{base64_url}
    """
    import base64

    m = re.search(r'substack\.com/redirect/\d+/([A-Za-z0-9_-]+)', url)
    if not m:
        return None

    # Extract the first base64url segment (before any dot separator)
    token_part = url.split('/redirect/')[1].split('/', 1)[-1]  # everything after /redirect/N/
    first_segment = token_part.split('.')[0]

    try:
        b64 = first_segment.replace('-', '+').replace('_', '/')
        while len(b64) % 4:
            b64 += '='
        decoded = base64.b64decode(b64).decode('utf-8', errors='replace')

        # If it decodes directly to a URL (legacy format)
        if decoded.startswith('http'):
            return decoded

        # Try parsing as JSON (v2 format with "e" field)
        data = json.loads(decoded)
        real_url = data.get('e') or data.get('url') or data.get('r')
        if not real_url or not real_url.startswith('http'):
            return None

        # If the "e" URL is a subscribe page, extract the actual article from "next" param
        if '/subscribe' in real_url:
            try:
                qs = parse_qs(urlparse(real_url).query)
                next_urls = qs.get('next', [])
                if next_urls and next_urls[0].startswith('http'):
                    return next_urls[0]
            except Exception:
                pass

        return real_url

    except Exception:
        return None


def resolve_redirect_url(url: str, timeout: float = 5.0) -> str:
    """Follow HTTP redirects to get the final destination URL.

    Handles Substack redirects, every.to click tracking, newsletter click tracking, etc.
    Falls back to the original URL if resolution fails.
    """
    import requests as req

    # Try client-side decode first for Substack (avoids HTTP roundtrip)
    if 'substack.com/redirect/' in url:
        decoded = decode_substack_redirect(url)
        if decoded:
            return decoded

    # For known redirect/tracking patterns, follow the HTTP redirect
    needs_resolve = any(p in url for p in [
        '/redirect/', '/emails/click/', '/email/click/', '/click?',
        '/track/', '/track?', 'email.mg.', 'links.',
        'click.', 'mailchi.mp/', 'elink.', 'post.spmailtechno',
    ])

    if not needs_resolve:
        return url

    try:
        resp = req.head(url, allow_redirects=True, timeout=timeout,
                        headers={'User-Agent': 'Mozilla/5.0 (compatible; Petrarca/1.0)'})
        final = resp.url
        if final and final != url:
            print(f'[email] Resolved redirect: {url[:60]}... → {final[:100]}', flush=True)
            return final
    except Exception as e:
        print(f'[email] Redirect resolve failed for {url[:60]}...: {e}', flush=True)

    return url


def find_article_urls(html: str, plain_text: str) -> list[dict]:
    """Extract and rank article URLs from email content. Returns list of {url, score}.

    Process: extract raw URLs → resolve redirects → clean → score → dedup.
    """
    raw_urls: set[str] = set()

    # Extract from HTML href attributes
    if html:
        for m in re.finditer(r'href=["\']?(https?://[^"\'>\s]+)', html, re.IGNORECASE):
            cleaned = clean_url(m.group(1))
            if cleaned:
                raw_urls.add(cleaned)

    # Extract from plain text
    if plain_text:
        for m in re.finditer(r'https?://[^\s<>"{}|\\^`\[\]()]+', plain_text):
            cleaned = clean_url(m.group(0))
            if cleaned:
                raw_urls.add(cleaned)

    print(f'[email] Extracted {len(raw_urls)} unique raw URLs', flush=True)

    # Resolve redirects for all URLs that look like tracking/redirect links
    resolved: dict[str, str] = {}  # raw → resolved
    for raw in raw_urls:
        resolved[raw] = resolve_redirect_url(raw)

    # Score the resolved URLs, dedup by canonical form
    url_scores: dict[str, int] = {}
    for raw, final_url in resolved.items():
        cleaned = clean_url(final_url)
        if cleaned:
            s = score_url(cleaned)
            url_scores[cleaned] = max(url_scores.get(cleaned, 0), s)

    # Filter, sort, dedup
    candidates = [{'url': u, 'score': s} for u, s in url_scores.items() if s > 0]
    candidates.sort(key=lambda c: c['score'], reverse=True)

    seen = set()
    deduped = []
    for c in candidates:
        canon = canonicalize_url(c['url'])
        if canon not in seen:
            seen.add(canon)
            deduped.append(c)

    return deduped


def strip_html(html: str) -> str:
    """Convert HTML to plain text."""
    text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
    text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|tr|li|blockquote|h[1-6])>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
                         ('&#39;', "'"), ('&nbsp;', ' '), ('&mdash;', '\u2014'),
                         ('&ndash;', '\u2013'), ('&hellip;', '\u2026')]:
        text = text.replace(entity, char)
    text = re.sub(r'&#x([0-9A-Fa-f]+);', lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_clean_content(html: str, plain_text: str) -> str:
    """Extract clean article content from email body."""
    text = strip_html(html) if html else plain_text
    if not text:
        return ''

    # Remove forwarded email headers
    text = re.sub(r'^[-\s]*(From|To|Cc|Bcc|Date|Sent|Subject|Reply-To):.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^[-=*\s]*(Forwarded|Original) (message|email|mail)[-=*\s]*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Begin forwarded message:$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Remove reply chains
    text = re.sub(r'^>+.*$', '', text, flags=re.MULTILINE)
    # Remove unsubscribe/footer lines
    text = re.sub(r'^.*\b(unsubscribe|manage\s+preferences|opt[- ]out|view\s+in\s+browser|view\s+online|email\s+preferences|privacy\s+policy)\b.*$',
                  '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Remove social media remnants
    text = re.sub(r'^\s*(Facebook|Twitter|Instagram|LinkedIn|YouTube|TikTok|Share|Like|Comment)\s*$',
                  '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Remove "powered by" footers
    text = re.sub(r'^.*\b(powered by|built with)\s+(substack|mailchimp|convertkit|ghost|buttondown|beehiiv)\b.*$',
                  '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Cut email signatures if in last 30%
    for pattern in [r'^--\s*$', r'^Sent from my ', r'^Sent from Mail for ', r'^Get Outlook for ']:
        m = re.search(pattern, text, re.MULTILINE)
        if m and m.start() > len(text) * 0.7:
            text = text[:m.start()]

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def process_email(raw_text: str) -> None:
    """Process a raw email: save it, extract URLs or content, and ingest.

    Strategy: resolve redirects first, score resolved URLs, prefer strong article URLs
    over many weak ones. For newsletters with one main article and supporting links,
    ingest only the primary article (score gap ≥ 2x).
    """
    # Save raw email for replay
    ts = int(time.time())
    raw_path = EMAILS_DIR / f'email_{ts}.eml'
    raw_path.write_text(raw_text, encoding='utf-8')
    print(f'[email] Saved raw email to {raw_path.name}', flush=True)

    parsed = parse_email(raw_text)
    subject = parsed['subject']
    print(f'[email] Subject: "{subject}", from: {parsed["from"]}', flush=True)
    print(f'[email] HTML: {len(parsed["text_html"])} chars, Plain: {len(parsed["text_plain"])} chars', flush=True)

    # Strategy 1: Find article URLs (resolves redirects, scores resolved URLs)
    candidates = find_article_urls(parsed['text_html'], parsed['text_plain'])

    # Boost URLs whose slug matches the email subject (the "main" article)
    if subject and candidates:
        subject_words = set(re.findall(r'[a-z]{3,}', subject.lower()))
        for c in candidates:
            slug = urlparse(c['url']).path.split('/')[-1].lower()
            slug_words = set(re.findall(r'[a-z]{3,}', slug))
            overlap = len(subject_words & slug_words)
            if overlap >= 3:
                c['score'] += 10
                print(f'[email] Subject match boost (+10): {c["url"][:80]}', flush=True)
        candidates.sort(key=lambda c: c['score'], reverse=True)

    print(f'[email] Found {len(candidates)} candidate URLs after resolve+dedup', flush=True)
    for c in candidates[:8]:
        print(f'  [{c["score"]:3d}] {c["url"][:100]}', flush=True)

    if candidates:
        top_score = candidates[0]['score']
        # If the top URL is 2x+ stronger than the second, it's clearly the main article
        # — just ingest that one. Otherwise take URLs scoring ≥ 60% of the top.
        if len(candidates) >= 2 and top_score >= candidates[1]['score'] * 2:
            to_send = [candidates[0]]
            print(f'[email] Clear primary article (score gap: {top_score} vs {candidates[1]["score"]})', flush=True)
        else:
            to_send = [c for c in candidates if c['score'] >= top_score * 0.6][:3]

        for c in to_send:
            print(f'[email] Ingesting URL: {c["url"][:100]}', flush=True)
            run_ingest(c['url'], subject, '', '', '', 'email')
        return

    # Strategy 2: Extract clean body text (email IS the content)
    clean = extract_clean_content(parsed['text_html'], parsed['text_plain'])
    print(f'[email] No strong URLs found. Clean content: {len(clean)} chars', flush=True)

    if len(clean) > 200:
        pseudo_url = f'mailto:{parsed["from"]}?subject={subject}'
        print(f'[email] Ingesting email body as content: "{subject}"', flush=True)
        run_ingest(pseudo_url, subject, clean, '', '', 'email-body')
    else:
        print(f'[email] No usable content found in email', flush=True)


def build_research_prompt(query: str, article_title: str, article_summary: str, concepts: list[str]) -> str:
    concept_str = ', '.join(concepts[:15]) if concepts else 'none provided'
    return f"""You are a research assistant for a reader who is exploring ideas while reading articles. They recorded a voice note with a question or thought, and want you to find diverse perspectives and connections.

CONTEXT:
- Article being read: "{article_title}"
- Article summary: {article_summary}
- Related concepts the reader is tracking: {concept_str}

READER'S QUESTION/THOUGHT:
{query}

Please provide your response as a JSON object with exactly these three arrays of strings:

1. "perspectives" - 3-5 diverse perspectives on this question or topic. Each should be a concise paragraph (2-3 sentences) presenting a distinct viewpoint, school of thought, or angle. Include perspectives the reader might not have considered.

2. "recommendations" - 3-5 specific article, book, or paper recommendations. Each should be a single string like "Title by Author - brief description of why it's relevant".

3. "connections" - 2-3 connections to the reader's existing reading context (the article and concepts listed above). Each should explain how this question connects to or extends what they're already reading about.

Respond ONLY with valid JSON, no other text."""


def build_explore_prompt(subtopic: str, exploration_tag: str, triage_signals: dict, existing_concepts: list[str]) -> str:
    concept_str = ', '.join(existing_concepts[:20]) if existing_concepts else 'none'
    liked = ', '.join(triage_signals.get('liked', [])) or 'none yet'
    skipped = ', '.join(triage_signals.get('skipped', [])) or 'none yet'
    return f"""You are a research assistant helping a reader explore "{exploration_tag}".

The reader has shown interest in the subtopic: "{subtopic}"

READER CONTEXT:
- Exploration topic: {exploration_tag}
- Subtopics they liked/read: {liked}
- Subtopics they skipped: {skipped}
- Concepts they already track: {concept_str}

Find 3-5 high-quality articles or sources about "{subtopic}" in the context of {exploration_tag}. Look for:
- Mix of overview and in-depth content
- Diverse perspectives (academic, journalistic, personal essays)
- Sources that connect to what the reader already knows

Respond ONLY with valid JSON:
{{
  "articles": [
    {{
      "title": "Article or source title",
      "url": "Full URL",
      "description": "1-2 sentence description of why this is worth reading",
      "depth": "overview|intermediate|deep"
    }}
  ],
  "connections": ["1-2 sentences connecting this subtopic to reader's existing knowledge"]
}}"""


def run_explore(request_id: str, subtopic: str, exploration_tag: str, triage_signals: dict, existing_concepts: list[str]):
    result_path = RESULTS_DIR / f'{request_id}.json'
    result = {
        'id': request_id,
        'type': 'explore',
        'status': 'processing',
        'subtopic': subtopic,
        'exploration_tag': exploration_tag,
    }

    try:
        prompt = build_explore_prompt(subtopic, exploration_tag, triage_signals, existing_concepts)
        output, err = _run_claude_p(prompt, timeout=300, purpose='explore')
        if err:
            result['status'] = 'failed'
            result['error'] = err
        else:
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(output[json_start:json_end])
                result['status'] = 'completed'
                result['completed_at'] = int(time.time() * 1000)
                result['articles'] = parsed.get('articles', [])
                result['connections'] = parsed.get('connections', [])
            else:
                result['status'] = 'failed'
                result['error'] = 'Could not parse JSON from claude output'

    except json.JSONDecodeError as e:
        result['status'] = 'failed'
        result['error'] = f'JSON parse error: {e}'
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[explore] {request_id} -> {result["status"]}')


def run_research(request_id: str, query: str, article_title: str, article_summary: str, concepts: list[str]):
    result_path = RESULTS_DIR / f'{request_id}.json'
    result = {
        'id': request_id,
        'status': 'processing',
        'query': query,
        'article_title': article_title,
    }

    try:
        prompt = build_research_prompt(query, article_title, article_summary, concepts)
        output, err = _run_claude_p(prompt, timeout=300, purpose='research')
        if err:
            result['status'] = 'failed'
            result['error'] = err
        else:
            # Extract JSON from the response (claude might wrap it in markdown)
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(output[json_start:json_end])
                result['status'] = 'completed'
                result['completed_at'] = int(time.time() * 1000)
                result['perspectives'] = parsed.get('perspectives', [])
                result['recommendations'] = parsed.get('recommendations', [])
                result['connections'] = parsed.get('connections', [])
            else:
                result['status'] = 'failed'
                result['error'] = 'Could not parse JSON from claude output'

    except json.JSONDecodeError as e:
        result['status'] = 'failed'
        result['error'] = f'JSON parse error: {e}'
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[research] {request_id} -> {result["status"]}')


# ---------------------------------------------------------------------------
# Twitter/X tweet ingestion via twikit
# ---------------------------------------------------------------------------

_TWEET_URL_RE = re.compile(r'https?://(?:twitter\.com|x\.com)/(\w+)/status/(\d+)')

def _is_tweet_url(url: str) -> bool:
    return bool(_TWEET_URL_RE.match(url))

def _extract_tweet_id(url: str) -> str | None:
    m = re.search(r'/status/(\d+)', url)
    return m.group(1) if m else None


async def _fetch_tweet_via_twikit(tweet_id: str) -> dict | None:
    """Fetch a single tweet by ID, reconstruct thread if applicable."""
    # Lazy imports — twikit may not be available in all environments
    sys.path.insert(0, str(SCRIPTS_DIR))
    from twikit import Client, Unauthorized
    from fetch_twitter_bookmarks import tweet_to_dict, reconstruct_thread

    if not TWIKIT_COOKIES_PATH.exists():
        print('[tweet] No twikit cookies found', flush=True)
        return None

    client = Client('en-US')
    client.load_cookies(str(TWIKIT_COOKIES_PATH))

    try:
        tweet = await client.get_tweet_by_id(tweet_id)
    except Unauthorized:
        print('[tweet] Cookies expired — cannot fetch tweet', flush=True)
        return None
    except Exception as e:
        print(f'[tweet] Failed to fetch tweet {tweet_id}: {e}', flush=True)
        return None

    if not tweet:
        return None

    tweet_dict = tweet_to_dict(tweet)

    # Reconstruct thread if this is a reply
    if tweet_dict.get('in_reply_to_tweet_id'):
        try:
            thread_texts = await reconstruct_thread(client, tweet_dict)
            if len(thread_texts) > 1:
                tweet_dict['thread_texts'] = thread_texts
                tweet_dict['thread_full_text'] = '\n\n---\n\n'.join(thread_texts)
                print(f'[tweet] Reconstructed thread: {len(thread_texts)} tweets', flush=True)
        except Exception as e:
            print(f'[tweet] Thread reconstruction failed: {e}', flush=True)

    return tweet_dict


def _extract_urls_from_tweet(tweet_dict: dict) -> list[str]:
    """Extract article-worthy URLs from a tweet, resolving t.co shortlinks."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from build_articles import _collect_urls_from_bookmark
    return _collect_urls_from_bookmark(tweet_dict)


def run_ingest_tweet(url: str, comment: str, ingest_id: str):
    """Fetch a tweet via twikit and ingest through the normal pipeline."""
    tweet_id = _extract_tweet_id(url)
    article_id = hashlib.sha256(url.encode()).hexdigest()[:12]
    log_path = INGEST_DIR / f'{ingest_id}.json'

    log_entry = {
        'id': ingest_id,
        'article_id': article_id,
        'status': 'processing',
        'url': url,
        'source': 'twitter_clip',
        'requested_at': int(time.time() * 1000),
    }
    log_path.write_text(json.dumps(log_entry, indent=2))

    if not tweet_id:
        log_entry['status'] = 'failed'
        log_entry['error'] = 'Could not extract tweet ID from URL'
        log_path.write_text(json.dumps(log_entry, indent=2))
        return

    # Fetch tweet (async → sync bridge)
    try:
        tweet_dict = asyncio.run(_fetch_tweet_via_twikit(tweet_id))
    except Exception as e:
        print(f'[tweet] twikit fetch error: {e}', flush=True)
        tweet_dict = None

    if not tweet_dict:
        # Fallback: try normal URL ingest (will likely fail for twitter.com but worth trying)
        print(f'[tweet] Falling back to normal URL ingest for {url[:60]}', flush=True)
        run_ingest(url, '', '', '', comment, 'twitter_clip', ingest_id)
        return

    author = tweet_dict.get('author_username', '')
    thread_text = tweet_dict.get('thread_full_text', tweet_dict.get('text', ''))
    # Normalize single newlines to paragraph breaks for non-thread tweets
    # (raw tweet text uses \n for visual breaks, but markdown needs \n\n)
    if not tweet_dict.get('thread_full_text') and '\n\n' not in thread_text:
        thread_text = '\n\n'.join(line for line in thread_text.split('\n') if line.strip())

    # Try to extract article URLs from the tweet
    try:
        article_urls = _extract_urls_from_tweet(tweet_dict)
    except Exception as e:
        print(f'[tweet] URL extraction failed: {e}', flush=True)
        article_urls = []

    if article_urls:
        # Ingest the linked article, with tweet context
        target_url = article_urls[0]
        tweet_context = f'Shared by @{author}: {tweet_dict["text"][:500]}'
        combined_comment = f'{tweet_context}\n\n{comment}' if comment else tweet_context
        print(f'[tweet] Found linked article: {target_url[:80]}', flush=True)
        run_ingest(target_url, '', '', '', combined_comment, 'twitter_clip', ingest_id)
    else:
        # Use tweet text/thread as article content
        title = f'Thread by @{author}' if tweet_dict.get('thread_full_text') else f'Tweet by @{author}'
        content = f'# {title}\n\n{thread_text}'
        print(f'[tweet] Using tweet text as content ({len(thread_text.split())} words)', flush=True)
        run_ingest(url, title, content, '', comment, 'twitter_clip', ingest_id)


async def _check_twikit_cookies() -> dict:
    """Check if twikit cookies are valid. Returns status dict."""
    if not TWIKIT_COOKIES_PATH.exists():
        return {'valid': False, 'error': 'No cookies file found'}

    try:
        cookies_mtime = TWIKIT_COOKIES_PATH.stat().st_mtime
        age_days = (time.time() - cookies_mtime) / 86400
    except Exception:
        age_days = -1

    sys.path.insert(0, str(SCRIPTS_DIR))
    from twikit import Client, Unauthorized

    client = Client('en-US')
    client.load_cookies(str(TWIKIT_COOKIES_PATH))

    try:
        await client.get_bookmarks(count=1)
        return {'valid': True, 'age_days': round(age_days, 1)}
    except Unauthorized:
        return {'valid': False, 'error': 'Cookies expired', 'age_days': round(age_days, 1)}
    except Exception as e:
        return {'valid': False, 'error': str(e), 'age_days': round(age_days, 1)}


# ---------------------------------------------------------------------------
# Standard URL ingestion
# ---------------------------------------------------------------------------

def _process_youtube_video(video_id, title, channel, url, description, chapters):
    """Background: fetch YouTube transcript, build article content, process through pipeline."""
    try:
        transcript_text = ''
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            ytt = YouTubeTranscriptApi()
            transcript_data = ytt.fetch(video_id)
            transcript_text = ' '.join(snippet.text for snippet in transcript_data)
            print(f'[youtube] Transcript: {len(transcript_text)} chars for {video_id}', flush=True)
        except Exception as e:
            print(f'[youtube] Transcript fetch failed for {video_id}: {e}', flush=True)
            transcript_text = description

        if not transcript_text:
            print(f'[youtube] No content for {video_id}', flush=True)
            return

        content = f'# {title}\n\n**Channel**: {channel}\n\n'
        if chapters:
            content += '**Chapters**:\n'
            for ch in chapters:
                content += f'- {ch.get("time", "")} {ch.get("title", "")}\n'
            content += '\n'
        content += '## Transcript\n\n' + transcript_text

        # Process through standard article pipeline
        from build_articles import process_single_article
        process_single_article(
            url=url,
            title=f'{title} — {channel} (YouTube)',
            content=content,
            source='youtube',
        )
        print(f'[youtube] Processed: "{title}" ({len(transcript_text)} chars)', flush=True)

        # Update media log status
        media_log_path = Path(os.environ.get('MEDIA_LOG_PATH', '/opt/petrarca/data/media_log.json'))
        try:
            media_log = json.loads(media_log_path.read_text())
            for item in media_log['items']:
                if item['id'] == f'yt_{video_id}':
                    item['transcript_status'] = 'available'
                    item['claims_extracted'] = True
                    break
            media_log_path.write_text(json.dumps(media_log, indent=2, ensure_ascii=False))
        except Exception:
            pass
    except Exception as e:
        print(f'[youtube] Error processing {video_id}: {e}', flush=True)
        import traceback
        traceback.print_exc()


def run_ingest(url: str, title: str, content: str, selected_text: str, comment: str, source: str, ingest_id: str | None = None):
    """Import a URL via import_url.py, optionally with pre-extracted content."""
    if not ingest_id:
        ingest_id = f'ingest_{int(time.time())}_{hash(url) % 10000:04d}'
    article_id = hashlib.sha256(url.encode()).hexdigest()[:12]
    log_path = INGEST_DIR / f'{ingest_id}.json'

    log_entry = {
        'id': ingest_id,
        'article_id': article_id,
        'status': 'processing',
        'url': url,
        'title': title,
        'source': source,
        'requested_at': int(time.time() * 1000),
    }
    log_path.write_text(json.dumps(log_entry, indent=2))

    content_file = None
    try:
        tag = source if source else 'manual'
        cmd = [VENV_PYTHON, str(SCRIPTS_DIR / 'import_url.py'), url, '--tag', tag]

        # If content was provided by the clipper, write it to a temp file
        if content and len(content.strip()) > 100:
            content_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', prefix='petrarca_clip_',
                dir=str(INGEST_DIR), delete=False
            )
            content_file.write(content)
            content_file.close()
            cmd.extend(['--content-file', content_file.name])

        print(f'[ingest] Running: {" ".join(cmd[:5])}...', flush=True)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(SCRIPTS_DIR),
        )

        if proc.returncode != 0:
            log_entry['status'] = 'failed'
            log_entry['error'] = proc.stderr[:1000]
            print(f'[ingest] {ingest_id} FAILED: {proc.stderr[:200]}', flush=True)
        else:
            log_entry['status'] = 'completed'
            log_entry['completed_at'] = int(time.time() * 1000)
            print(f'[ingest] {ingest_id} completed', flush=True)

        if proc.stdout:
            log_entry['stdout'] = proc.stdout[:2000]
        if proc.stderr:
            log_entry['stderr'] = proc.stderr[:2000]

    except subprocess.TimeoutExpired:
        log_entry['status'] = 'failed'
        log_entry['error'] = 'import_url.py timed out after 10 minutes'
        print(f'[ingest] {ingest_id} TIMEOUT', flush=True)
    except Exception as e:
        log_entry['status'] = 'failed'
        log_entry['error'] = str(e)
        print(f'[ingest] {ingest_id} ERROR: {e}', flush=True)
    finally:
        # Clean up temp content file
        if content_file and os.path.exists(content_file.name):
            os.unlink(content_file.name)

    # Save highlights and comments as sidecar data
    if selected_text or comment:
        sidecar = {
            'url': url,
            'title': title,
            'source': source,
            'created_at': int(time.time() * 1000),
        }
        if selected_text:
            sidecar['highlights'] = [{'text': selected_text, 'source': 'clipper'}]
        if comment:
            sidecar['notes'] = [{'text': comment, 'source': source}]
        sidecar_path = INGEST_DIR / f'{ingest_id}_sidecar.json'
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        log_entry['sidecar'] = str(sidecar_path)

    log_path.write_text(json.dumps(log_entry, indent=2))


def run_ingest_book(book_path: str, chapter: int | None, request_id: str):
    """Run ingest_book_petrarca.py to process a book."""
    result_path = RESULTS_DIR / f'{request_id}.json'
    result = {
        'id': request_id,
        'type': 'book_ingest',
        'status': 'processing',
        'book_path': book_path,
        'chapter': chapter,
        'requested_at': int(time.time() * 1000),
    }
    result_path.write_text(json.dumps(result, indent=2))

    try:
        cmd = [
            VENV_PYTHON,
            str(SCRIPTS_DIR / 'ingest_book_petrarca.py'),
            book_path,
            '--output-dir', str(BOOKS_OUTPUT_DIR),
            '--cross-match-dir', str(CROSS_MATCH_DIR),
        ]
        if chapter is not None:
            cmd.extend(['--chapter', str(chapter)])

        print(f'[book-ingest] Running: {" ".join(cmd[:6])}...', flush=True)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min for full book
            cwd=str(SCRIPTS_DIR),
        )

        if proc.returncode != 0:
            result['status'] = 'failed'
            result['error'] = proc.stderr[:2000]
            print(f'[book-ingest] {request_id} FAILED: {proc.stderr[:200]}', flush=True)
        else:
            result['status'] = 'completed'
            result['completed_at'] = int(time.time() * 1000)
            print(f'[book-ingest] {request_id} completed', flush=True)

        if proc.stdout:
            result['stdout'] = proc.stdout[:5000]
        if proc.stderr:
            result['stderr'] = proc.stderr[:2000]

    except subprocess.TimeoutExpired:
        result['status'] = 'failed'
        result['error'] = 'Book ingestion timed out after 30 minutes'
        print(f'[book-ingest] {request_id} TIMEOUT', flush=True)
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        print(f'[book-ingest] {request_id} ERROR: {e}', flush=True)

    result_path.write_text(json.dumps(result, indent=2))


def build_explore_batch_prompt(concepts: list[dict]) -> str:
    concept_lines = '\n'.join(
        f'- "{c["name"]}" (context: {c.get("context_article_title", "N/A")})'
        for c in concepts
    )
    return f"""You are a research assistant. A reader wants to explore these concepts further. For each concept, find 2-3 high-quality URLs from diverse sources (academic, journalism, essays, Wikipedia).

CONCEPTS TO EXPLORE:
{concept_lines}

For each concept, find articles that would help a curious reader understand it better. Look for diverse perspectives and reliable sources.

Return ONLY valid JSON:
{{
  "results": [
    {{
      "concept_name": "the concept name",
      "urls": [
        {{
          "url": "https://...",
          "title": "Article title",
          "description": "Why this is worth reading"
        }}
      ]
    }}
  ]
}}"""


def run_explore_batch(request_id: str, concepts: list[dict]):
    result_path = RESULTS_DIR / f'{request_id}.json'
    result = {
        'id': request_id,
        'type': 'explore_batch',
        'status': 'processing',
        'concept_count': len(concepts),
        'requested_at': int(time.time() * 1000),
    }
    result_path.write_text(json.dumps(result, indent=2))

    try:
        prompt = build_explore_batch_prompt(concepts)
        output, err = _run_claude_p(prompt, timeout=300, purpose='explore_batch')
        if err:
            result['status'] = 'failed'
            result['error'] = err
        else:
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(output[json_start:json_end])
                result['status'] = 'completed'
                result['completed_at'] = int(time.time() * 1000)
                result['results'] = parsed.get('results', [])

                # Auto-import top 2 URLs per concept
                for concept_result in result.get('results', []):
                    for url_entry in concept_result.get('urls', [])[:2]:
                        url = url_entry.get('url', '')
                        if url:
                            print(f'[explore-batch] Auto-importing: {url[:80]}', flush=True)
                            threading.Thread(
                                target=run_ingest,
                                args=(url, url_entry.get('title', ''), '', '', '', 'explore-batch'),
                                daemon=True,
                            ).start()
            else:
                result['status'] = 'failed'
                result['error'] = 'Could not parse JSON from claude output'

    except json.JSONDecodeError as e:
        result['status'] = 'failed'
        result['error'] = f'JSON parse error: {e}'
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[explore-batch] {request_id} -> {result["status"]} ({len(concepts)} concepts)', flush=True)


# --- Voice notes: backend transcription + storage ---

def transcribe_on_server(audio_path: Path) -> str:
    """Upload audio to Soniox, transcribe, return text."""
    import requests as req

    headers = {'Authorization': f'Bearer {SONIOX_API_KEY}'}

    # Upload file
    with open(audio_path, 'rb') as f:
        resp = req.post(f'{SONIOX_BASE_URL}/files', headers=headers,
                        files={'file': ('note.m4a', f, 'audio/m4a')})
    resp.raise_for_status()
    file_id = resp.json()['id']

    # Create transcription
    resp = req.post(f'{SONIOX_BASE_URL}/transcriptions', headers=headers,
                    json={'model': 'stt-async-v4', 'file_id': file_id,
                          'language_hints': ['en', 'no', 'sv', 'da', 'it', 'de', 'es', 'fr', 'zh', 'id']})
    resp.raise_for_status()
    txn_id = resp.json()['id']

    # Poll
    for _ in range(90):  # 3 min max
        time.sleep(2)
        resp = req.get(f'{SONIOX_BASE_URL}/transcriptions/{txn_id}', headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'completed':
            break
        if data['status'] == 'error':
            raise RuntimeError(f'Soniox error: {data.get("error_message", "unknown")}')

    # Get transcript
    resp = req.get(f'{SONIOX_BASE_URL}/transcriptions/{txn_id}/transcript', headers=headers)
    resp.raise_for_status()
    data = resp.json()
    text = ''
    if data.get('tokens'):
        text = ''.join(t['text'] for t in data['tokens']).strip()
    elif data.get('text'):
        text = data['text'].strip()

    # Cleanup
    try:
        req.delete(f'{SONIOX_BASE_URL}/transcriptions/{txn_id}', headers=headers)
        req.delete(f'{SONIOX_BASE_URL}/files/{file_id}', headers=headers)
    except Exception:
        pass

    return text


def extract_note_actions(transcript: str, article_title: str, topics: list[str]) -> list[dict]:
    """Extract actionable intents from a voice note transcript via Claude."""
    import uuid
    from claude_llm import call_claude_json

    prompt = f"""Analyze this voice note transcript and extract actionable intents.

Voice note transcript: "{transcript}"
Article being read: "{article_title}"
Article topics: {', '.join(topics[:5])}

Extract any of these intent types:
- "research": User wants to look up or explore a topic further
- "tag": User wants to tag or categorize something
- "remember": User wants to remember a specific insight or fact

Return a JSON array of actions. Each action has:
- "type": one of "research", "tag", "remember"
- "description": brief human-readable description
- "topic": (for research) the topic to research
- "tag": (for tag) the tag name
- "note_text": (for remember) the text to remember

If no clear actions are found, return an empty array.
Return ONLY the JSON array, no other text."""

    try:
        actions = call_claude_json(prompt, timeout=90, model='sonnet')
        if not isinstance(actions, list):
            return []
        for action in actions:
            if isinstance(action, dict):
                action['id'] = f'act_{uuid.uuid4().hex[:8]}'
                action['status'] = 'pending'
        return [a for a in actions if isinstance(a, dict)]
    except Exception as e:
        print(f'[note] Action extraction failed: {e}', flush=True)

    return []


def process_voice_note(note_id: str, audio_path: Path, article_id: str, topics: list[str],
                       article_title: str, article_context: str):
    """Background: transcribe audio, store note, extract actions."""
    note_path = NOTES_DIR / f'{note_id}.json'
    note = {
        'id': note_id,
        'article_id': article_id,
        'article_title': article_title,
        'topics': topics,
        'status': 'transcribing',
        'created_at': int(time.time()),
    }
    note_path.write_text(json.dumps(note, indent=2))

    try:
        transcript = transcribe_on_server(audio_path)
        note['transcript'] = transcript
        note['status'] = 'complete'
        note_path.write_text(json.dumps(note, indent=2))
        print(f'[note] {note_id} transcribed: {transcript[:80]}...', flush=True)

        # Extract actions from transcript
        actions = extract_note_actions(transcript, article_title, topics)
        if actions:
            note['actions'] = actions
            note_path.write_text(json.dumps(note, indent=2))
            print(f'[note] {note_id} extracted {len(actions)} actions', flush=True)

        # Voice routing (best-effort, non-blocking)
        threading.Thread(
            target=_route_and_enrich_note,
            args=(note_id, transcript, article_id, article_title),
            daemon=True,
        ).start()
    except Exception as e:
        note['status'] = 'failed'
        note['error'] = str(e)
        note_path.write_text(json.dumps(note, indent=2))
        print(f'[note] {note_id} transcription failed: {e}', flush=True)


def run_topic_research(request_id: str, topic: str, context: str, article_titles: list[str]):
    """Background: use Claude with web search to find articles on a topic, then ingest them."""
    from claude_llm import call_claude_search

    result_path = RESULTS_DIR / f'{request_id}.json'
    result = {
        'id': request_id,
        'type': 'topic_research',
        'status': 'processing',
        'topic': topic,
        'requested_at': int(time.time() * 1000),
    }
    result_path.write_text(json.dumps(result, indent=2))

    prompt = f"""You are a research assistant for Petrarca, a read-later app. The user is interested in the topic "{topic}".

Context about what they've been reading:
{context}

Articles they already have on this topic:
{chr(10).join(f'- {t}' for t in article_titles[:10])}

Search the web and find 3-5 high-quality articles, blog posts, or papers that would give the user genuinely NEW perspectives on this topic. Prioritize:
- Diverse viewpoints (not just the same take rehashed)
- Primary sources over aggregators
- Recent and substantive pieces
- Content that complements rather than duplicates what they already have

Return ONLY valid JSON (no markdown fences):
{{
  "articles": [
    {{"url": "https://...", "title": "...", "why": "One sentence on why this is valuable"}}
  ]
}}"""

    try:
        output = call_claude_search(prompt, timeout=300)
        if not output:
            result['status'] = 'failed'
            result['error'] = 'No response from Claude'
        else:
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(output[json_start:json_end])
                articles = parsed.get('articles', [])
                result['status'] = 'completed'
                result['completed_at'] = int(time.time() * 1000)
                result['found_articles'] = articles

                # Auto-ingest top articles sequentially (import_url.py uses file locking)
                for art in articles[:3]:
                    url = art.get('url', '')
                    if url:
                        print(f'[topic_research] Ingesting: {url}', flush=True)
                        run_ingest(url, art.get('title', ''), '', '', art.get('why', ''), f'research:{topic}')
            else:
                result['status'] = 'failed'
                result['error'] = 'Could not parse JSON from Claude response'
                result['raw_output'] = output[:1000]
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[topic_research] {request_id} -> {result["status"]}', flush=True)


# --- Generate more follow-up questions ---

def generate_more_questions(article_id: str, existing_questions: list[str]) -> list[dict]:
    """Generate additional follow-up questions for an article via Claude."""
    from claude_llm import call_claude_json

    # Load article data
    try:
        articles = json.loads(ARTICLES_PATH.read_text())
        article = next((a for a in articles if a.get('id') == article_id), None)
    except (OSError, json.JSONDecodeError):
        article = None

    if not article:
        return []

    title = article.get('title', 'Untitled')
    summary = article.get('one_line_summary', '') or article.get('full_summary', '')
    claims = article.get('key_claims', [])
    topics = article.get('topics', [])
    entities = [e.get('name', '') for e in article.get('entities', [])]

    existing_list = '\n'.join(f'- {q}' for q in existing_questions) if existing_questions else '(none)'

    prompt = f"""Given this article, generate 3 NEW follow-up questions that a curious, well-read person would want to explore.

Article: "{title}"
Summary: {summary}
Key claims: {json.dumps(claims[:6])}
Topics: {', '.join(topics[:8])}
Entities: {', '.join(entities[:8])}

Already-shown questions (do NOT repeat or rephrase these):
{existing_list}

Generate 3 diverse questions that:
- Connect to adjacent domains, historical parallels, or contrasting perspectives
- Are genuinely curiosity-driven — the kind that lead to interesting rabbit holes
- Span different angles: one might be comparative, one might be historical/contextual, one might challenge assumptions
- Each has a "connects_to" field naming the broader topic area it relates to

Return ONLY a JSON array:
[
  {{"question": "...", "connects_to": "..."}},
  {{"question": "...", "connects_to": "..."}},
  {{"question": "...", "connects_to": "..."}}
]"""

    questions = call_claude_json(prompt, timeout=90, model='sonnet')
    if not questions:
        return []
    if isinstance(questions, list):
        return [q for q in questions if isinstance(q, dict) and 'question' in q and 'connects_to' in q]
    print(f'[generate-questions] Unexpected response shape for article {article_id}', flush=True)

    return []


# --- Chat with article context ---

def handle_chat(question: str, context: str, conversation_id: str | None = None) -> dict:
    """Synchronous chat using Gemini via google.genai SDK."""
    import uuid
    from gemini_llm import call_chat

    if not conversation_id:
        conversation_id = str(uuid.uuid4())[:12]

    # Load conversation history
    chat_file = CHAT_DIR / f'{conversation_id}.json'
    history = []
    if chat_file.exists():
        try:
            history = json.loads(chat_file.read_text())
        except (json.JSONDecodeError, OSError):
            history = []

    # Build messages
    messages = [
        {'role': 'system', 'content': (
            'You are a helpful reading assistant for Petrarca, an intelligent read-later app. '
            'The user is reading an article and has a question. You have the article\'s metadata, '
            'summary, key claims, topics, and text as context. Answer concisely and helpfully. '
            'If the user asks about claims, topics, or connections to other knowledge, be specific.'
        )},
    ]

    # Add context as first user message if this is a new conversation
    if not history:
        messages.append({'role': 'user', 'content': f'[Article context]\n{context}'})
        messages.append({'role': 'assistant', 'content': 'I have the article context. What would you like to know?'})

    # Add conversation history
    for msg in history:
        messages.append({'role': msg['role'], 'content': msg['content']})

    # Add current question
    messages.append({'role': 'user', 'content': question})

    answer = call_chat(messages)
    if not answer:
        answer = 'Error: could not get response from Gemini'

    # Save to history
    history.append({'role': 'user', 'content': question, 'timestamp': int(time.time())})
    history.append({'role': 'assistant', 'content': answer, 'timestamp': int(time.time())})
    chat_file.write_text(json.dumps(history, indent=2))

    return {'answer': answer, 'conversation_id': conversation_id}


# ---------------------------------------------------------------------------
# Physical book endpoints — processing functions
# ---------------------------------------------------------------------------

def process_book_identify(image_path: Path) -> dict:
    """Identify a book from a cover/title page photo using Gemini Vision + Claude web search."""
    from gemini_llm import call_vision
    from claude_llm import call_claude_search

    image_data = image_path.read_bytes()
    mime_type = 'image/png' if str(image_path).endswith('.png') else 'image/jpeg'

    # Step 1: Extract title/author from photo
    vision_result = call_vision(
        image_data,
        """Identify this book from the cover or title page photo.
Return a JSON object with:
{
  "title": "exact book title",
  "author": "author name(s)",
  "isbn": "ISBN if visible, else null",
  "publisher": "publisher if visible, else null",
  "year": null
}
Return ONLY valid JSON.""",
        mime_type=mime_type,
        response_mime_type="application/json",
    )

    if not vision_result:
        return {'error': 'Could not identify book from image'}

    try:
        cleaned = vision_result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        book_info = json.loads(cleaned)
    except json.JSONDecodeError:
        return {'error': f'Failed to parse vision result: {vision_result[:200]}'}

    title = book_info.get('title', '')
    author = book_info.get('author', '')
    if not title:
        return {'error': 'Could not extract title from image'}

    # Step 2: Web search for metadata and cover
    search_result = call_claude_search(
        f"""Find metadata for this book:
Title: {title}
Author: {author}

Return a JSON object with:
{{
  "title": "full official title",
  "author": "full author name(s)",
  "cover_url": "URL to a high-quality cover image (Amazon, Google Books, or publisher)",
  "isbn": "ISBN-13 if available",
  "publisher": "publisher name",
  "year": publication year as integer,
  "page_count": total pages as integer,
  "topics": ["3-5 topic tags for this book"]
}}
Return ONLY valid JSON.""",
        timeout=180,
    )

    if search_result:
        try:
            cleaned = search_result.strip()
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
                cleaned = re.sub(r'\n?```$', '', cleaned)
            metadata = json.loads(cleaned)
            # Merge vision result with search metadata (search wins for richer data)
            for key in ('title', 'author', 'isbn', 'publisher', 'year', 'page_count', 'cover_url', 'topics'):
                if metadata.get(key) and not book_info.get(key):
                    book_info[key] = metadata[key]
                elif metadata.get(key):
                    book_info[key] = metadata[key]
        except json.JSONDecodeError:
            pass  # Use vision result as-is

    # Ensure topics is a list
    if not isinstance(book_info.get('topics'), list):
        book_info['topics'] = []

    # Step 3: Try to find table of contents via web search
    chapters = _find_toc_online(title, author)
    if chapters:
        book_info['chapters'] = chapters

    # Step 4: Find cover image via book APIs (much more reliable than LLM-generated URLs)
    cover_url = _find_cover_image(book_info.get('isbn'), title, author)
    if cover_url:
        book_info['cover_url'] = cover_url
    elif book_info.get('cover_url'):
        # Verify LLM-provided URL actually works before trusting it
        if not _url_returns_image(book_info['cover_url']):
            del book_info['cover_url']

    print(f'[book/identify] Identified: {book_info.get("title")} by {book_info.get("author")} (cover: {bool(book_info.get("cover_url"))})', flush=True)
    return book_info


def _find_cover_image(isbn: str | None, title: str, author: str) -> str | None:
    """Find a book cover image URL via Open Library (ISBN) then Google Books (title/author)."""
    import urllib.request
    import urllib.error

    # Try Open Library by ISBN first (direct image URL, no API key needed)
    if isbn:
        clean_isbn = re.sub(r'[^0-9X]', '', isbn.upper())
        if clean_isbn:
            ol_url = f'https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg?default=false'
            try:
                req = urllib.request.Request(ol_url, method='HEAD')
                req.add_header('User-Agent', 'Petrarca/1.0')
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status == 200 and 'image' in resp.headers.get('Content-Type', ''):
                    print(f'[cover] Found via Open Library ISBN: {clean_isbn}', flush=True)
                    return ol_url
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                pass

    # Try Google Books API (free, no key needed for low volume)
    try:
        query = urllib.parse.quote(f'intitle:{title} inauthor:{author}')
        gb_url = f'https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1'
        req = urllib.request.Request(gb_url)
        req.add_header('User-Agent', 'Petrarca/1.0')
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode())
        items = data.get('items', [])
        if items:
            image_links = items[0].get('volumeInfo', {}).get('imageLinks', {})
            # Prefer larger images, upgrade HTTP to HTTPS
            for key in ('extraLarge', 'large', 'medium', 'thumbnail', 'smallThumbnail'):
                if key in image_links:
                    url = image_links[key].replace('http://', 'https://')
                    # Remove edge=curl parameter for cleaner image
                    url = re.sub(r'&edge=curl', '', url)
                    print(f'[cover] Found via Google Books ({key})', flush=True)
                    return url
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f'[cover] Google Books lookup failed: {e}', flush=True)

    # Try Open Library by title search as last resort
    try:
        query = urllib.parse.quote(f'{title} {author}')
        ol_search = f'https://openlibrary.org/search.json?q={query}&limit=1&fields=isbn'
        req = urllib.request.Request(ol_search)
        req.add_header('User-Agent', 'Petrarca/1.0')
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode())
        docs = data.get('docs', [])
        if docs:
            isbns = docs[0].get('isbn', [])
            for found_isbn in isbns[:3]:
                ol_url = f'https://covers.openlibrary.org/b/isbn/{found_isbn}-L.jpg?default=false'
                try:
                    req2 = urllib.request.Request(ol_url, method='HEAD')
                    req2.add_header('User-Agent', 'Petrarca/1.0')
                    resp2 = urllib.request.urlopen(req2, timeout=5)
                    if resp2.status == 200 and 'image' in resp2.headers.get('Content-Type', ''):
                        print(f'[cover] Found via Open Library search → ISBN {found_isbn}', flush=True)
                        return ol_url
                except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                    continue
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f'[cover] Open Library search failed: {e}', flush=True)

    print(f'[cover] No cover found for "{title}" by {author}', flush=True)
    return None


def _url_returns_image(url: str) -> bool:
    """Check if a URL actually returns an image (HEAD request)."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'Petrarca/1.0')
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200 and 'image' in resp.headers.get('Content-Type', '')
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False


def _find_toc_online(title: str, author: str) -> list[dict] | None:
    """Try to find a book's table of contents via Claude + web search."""
    from claude_llm import call_claude_search

    result = call_claude_search(
        f"""Find the table of contents / chapter list for this book:
"{title}" by {author}

Return a JSON array of chapters:
[{{"number": 1, "title": "Chapter Title"}}, {{"number": 2, "title": "Chapter Title"}}]

Only include actual chapter titles, not preface/index/bibliography.
If you cannot find the chapter list, return an empty array [].
Return ONLY the JSON array.""",
        timeout=180,
    )

    if not result:
        return None

    try:
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        chapters = json.loads(cleaned)
        if isinstance(chapters, list) and len(chapters) >= 2:
            print(f'[toc] Found {len(chapters)} chapters online for "{title}"', flush=True)
            return chapters
    except json.JSONDecodeError:
        pass

    return None


def process_book_ocr_toc(image_path: Path) -> dict:
    """OCR a table of contents photo and parse chapter structure."""
    from gemini_llm import call_vision

    image_data = image_path.read_bytes()
    mime_type = 'image/png' if str(image_path).endswith('.png') else 'image/jpeg'

    result = call_vision(
        image_data,
        """Extract the table of contents from this image.
Return a JSON object:
{
  "chapters": [
    {"number": 1, "title": "Chapter Title", "start_page": 1},
    {"number": 2, "title": "Chapter Title", "start_page": 25}
  ]
}
Include chapter numbers, titles, and page numbers. If sections/parts have sub-chapters, include them.
Return ONLY valid JSON.""",
        mime_type=mime_type,
        response_mime_type="application/json",
    )

    if not result:
        return {'chapters': []}

    try:
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        parsed = json.loads(cleaned)
        return {'chapters': parsed.get('chapters', [])}
    except json.JSONDecodeError:
        return {'chapters': []}


def process_book_ocr_page(image_path: Path, book_title: str,
                          page_number: int | None = None,
                          chapter: str | None = None) -> dict:
    """OCR a page photo, extract page number and core ideas."""
    from gemini_llm import call_vision

    image_data = image_path.read_bytes()
    mime_type = 'image/png' if str(image_path).endswith('.png') else 'image/jpeg'

    context = f"Book: {book_title}"
    if chapter:
        context += f"\nChapter: {chapter}"
    if page_number:
        context += f"\nExpected page: {page_number}"

    result = call_vision(
        image_data,
        f"""{context}

OCR this book page and extract:
1. The full text on the page
2. The page number (from header/footer if visible)
3. 1-3 core ideas or claims from this page
4. Relevant topic tags
5. The single most important sentence on this page (key passage)
6. A thought-provoking "why" question about the content

Return a JSON object:
{{
  "text": "full OCR text of the page",
  "detected_page_number": page_number_or_null,
  "extracted_ideas": ["idea 1", "idea 2"],
  "topics": ["topic1", "topic2"],
  "key_passage": "the single most important sentence on this page",
  "elaborative_question": "a why/how question about the content that would deepen understanding"
}}
Return ONLY valid JSON.""",
        mime_type=mime_type,
        response_mime_type="application/json",
        max_tokens=8192,
    )

    if not result:
        return {'text': '', 'extracted_ideas': [], 'topics': []}

    try:
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        parsed = json.loads(cleaned)
        return {
            'text': parsed.get('text', ''),
            'detected_page_number': parsed.get('detected_page_number'),
            'extracted_ideas': parsed.get('extracted_ideas', []),
            'topics': parsed.get('topics', []),
            'key_passage': parsed.get('key_passage'),
            'elaborative_question': parsed.get('elaborative_question'),
        }
    except json.JSONDecodeError:
        return {'text': result, 'extracted_ideas': [], 'topics': []}


class ResearchHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header(
            'Access-Control-Allow-Headers',
            'Content-Type, X-Petrarca-Token, X-Koigen-Token',
        )

    def _send_koigen_response(self, response):
        """Send a capture response without caching capabilities or result bodies."""
        self.send_response(response.status)
        self._send_cors_headers()
        for name, value in koigen_adapter.response_headers(response):
            self.send_header(name, value)
        if response.close_connection:
            # A framing error leaves unread bytes in rfile. Never let the HTTP parser
            # reinterpret those bytes as a pipelined request.
            self.close_connection = True
        self.end_headers()
        self.wfile.write(response.body)

    def _handle_koigen_post(self):
        try:
            response = koigen_adapter.dispatch_post(
                self.path, self.headers, self.rfile,
            )
        except Exception as exc:
            print(f'[koigen] POST adapter failed: {exc}', flush=True)
            response = koigen_adapter.unavailable_response(self.path, close=True)
        if response is None:  # guarded by post_route(), but fail closed if changed
            return self._send_json_response(404, {'error': 'Unknown API endpoint'})
        return self._send_koigen_response(response)

    def _handle_koigen_get(self):
        try:
            response = koigen_adapter.dispatch_get(self.path)
        except Exception as exc:
            print(f'[koigen] GET adapter failed: {exc}', flush=True)
            response = koigen_adapter.unavailable_response(self.path)
        if response is None:  # guarded by is_approve_get(), but fail closed if changed
            return self._send_json_response(404, {'error': 'Unknown API endpoint'})
        return self._send_koigen_response(response)

    def _read_json_body(self) -> dict | None:
        """Read and parse JSON from request body. Sends 400 on failure, returns None."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Empty request body'})
            return None
        try:
            return json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json_response(400, {'error': f'Invalid JSON: {e}'})
            return None

    def _send_json_response(self, status: int, data: dict):
        self.send_response(status)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _handle_explore_batch(self):
        body = self._read_json_body()
        if body is None:
            return
        concepts = body.get('concepts', [])
        if not concepts:
            self._send_json_response(400, {'error': 'No concepts provided'})
            return

        request_id = f'expb_{int(time.time())}'
        print(f'[explore-batch] Received {len(concepts)} concepts', flush=True)

        thread = threading.Thread(
            target=run_explore_batch,
            args=(request_id, concepts),
            daemon=True,
        )
        thread.start()

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': request_id, 'status': 'processing', 'concept_count': len(concepts)}).encode())

    def _handle_ingest_email(self):
        """Accept raw email from Cloudflare Worker, process server-side."""
        if INGEST_TOKEN:
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self.send_response(401)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid or missing auth token'}).encode())
                return

        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Empty request body'}).encode())
            return

        raw_email = self.rfile.read(content_length).decode('utf-8', errors='replace')
        sender = self.headers.get('X-From', 'unknown')

        print(f'[ingest-email] Received {len(raw_email)} bytes from {sender}', flush=True)
        log_server_event('ingest_email', sender=sender)

        thread = threading.Thread(target=process_email, args=(raw_email,), daemon=True)
        thread.start()

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'queued', 'source': 'email'}).encode())

    def _handle_note(self):
        """Receive audio file + metadata, transcribe in background, store note."""
        content_type = self.headers.get('Content-Type', '')

        if 'multipart' in content_type.lower():
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b''
            try:
                form = self._multipart_parse_bytes(body, content_type)
            except Exception as e:
                print(f'[note] multipart parse: {e}', flush=True)
                self.send_response(400)
                self._send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
                return

            article_id = form.getvalue('article_id', '')
            topics_raw = form.getvalue('topics', '[]')
            article_title = form.getvalue('article_title', '')
            article_context = form.getvalue('article_context', '')

            try:
                topics = json.loads(topics_raw) if isinstance(topics_raw, str) else []
            except json.JSONDecodeError:
                topics = []

            # Save audio file
            note_id = f'note_{int(time.time())}_{article_id[:8]}'
            audio_path = AUDIO_DIR / f'{note_id}.m4a'

            file_item = form['audio']
            audio_path.write_bytes(file_item.file.read())
        else:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Expected multipart/form-data"}')
            return

        # Spawn background transcription
        thread = threading.Thread(
            target=process_voice_note,
            args=(note_id, audio_path, article_id, topics, article_title, article_context),
            daemon=True,
        )
        thread.start()

        print(f'[note] Started {note_id} for article {article_id}', flush=True)

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': note_id, 'status': 'transcribing'}).encode())

    def _handle_execute_action(self):
        """Execute an action extracted from a voice note."""
        parts = self.path.split('/')
        note_id = parts[2] if len(parts) >= 4 else ''

        note_path = NOTES_DIR / f'{note_id}.json'
        if not note_path.exists():
            self._send_json_response(404, {'error': 'Note not found'})
            return

        body = self._read_json_body()
        if body is None:
            return
        action_id = body.get('action_id', '')

        try:
            note = json.loads(note_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            self._send_json_response(500, {'error': f'Failed to read note: {e}'})
            return
        actions = note.get('actions', [])
        target_action = next((a for a in actions if a.get('id') == action_id), None)

        if not target_action:
            self._send_json_response(404, {'error': 'Action not found'})
            return

        if target_action['type'] == 'research':
            topic = target_action.get('topic', target_action.get('description', ''))
            request_id = f'topres_{int(time.time())}_{hash(topic) % 10000:04d}'
            thread = threading.Thread(
                target=run_topic_research,
                args=(request_id, topic, f'From voice note on: {note.get("article_title", "")}',
                      [note.get('article_title', '')]),
                daemon=True,
            )
            thread.start()
            target_action['status'] = 'running'
            print(f'[action] Spawned research for: {topic}', flush=True)
        else:
            target_action['status'] = 'done'

        note_path.write_text(json.dumps(note, indent=2))

        self.send_response(200)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'action_id': action_id, 'status': target_action['status']}).encode())

    def _handle_topic_research(self):
        body = self._read_json_body()
        if body is None:
            return
        topic = body.get('topic', '').strip()
        context = body.get('context', '')
        article_titles = body.get('article_titles', [])

        if not topic:
            self._send_json_response(400, {'error': 'Missing topic'})
            return

        request_id = f'topres_{int(time.time())}_{hash(topic) % 10000:04d}'

        thread = threading.Thread(
            target=run_topic_research,
            args=(request_id, topic, context, article_titles),
            daemon=True,
        )
        thread.start()

        print(f'[topic_research] Started {request_id}: {topic}', flush=True)

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': request_id, 'status': 'processing'}).encode())

    def _handle_generate_questions(self):
        body = self._read_json_body()
        if body is None:
            return
        article_id = body.get('article_id', '').strip()
        existing_questions = body.get('existing_questions', [])

        if not article_id:
            self._send_json_response(400, {'error': 'Missing article_id'})
            return

        print(f'[generate-questions] Generating for article {article_id}, {len(existing_questions)} existing', flush=True)
        questions = generate_more_questions(article_id, existing_questions)
        print(f'[generate-questions] Generated {len(questions)} new questions', flush=True)

        self._send_json_response(200, {'questions': questions})

    def _handle_chat(self):
        body = self._read_json_body()
        if body is None:
            return
        question = body.get('question', '').strip()
        context = body.get('context', '')
        conversation_id = body.get('conversation_id')

        if not question:
            self._send_json_response(400, {'error': 'Missing question'})
            return

        print(f'[chat] Q: {question[:80]}...', flush=True)
        result = handle_chat(question, context, conversation_id)
        print(f'[chat] A: {result["answer"][:80]}...', flush=True)

        self.send_response(200)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def _handle_ingest(self):
        body = self._read_json_body()
        if body is None:
            return

        source = body.get('source', 'unknown')

        # App-originated ingests (reader links) skip auth; external sources need a token
        if INGEST_TOKEN and source not in ('reader_link',):
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self._send_json_response(401, {'error': 'Invalid or missing auth token'})
                return

        url = body.get('url', '').strip()
        if not url:
            self._send_json_response(400, {'error': 'Missing required field: url'})
            return

        title = body.get('title', '')
        content = body.get('content', '')
        selected_text = body.get('selected_text', '')
        comment = body.get('comment', '')

        # Generate IDs before spawning thread so we can return them
        ingest_id = f'ingest_{int(time.time())}_{hash(url) % 10000:04d}'
        article_id = hashlib.sha256(url.encode()).hexdigest()[:12]

        # Route tweet URLs through twikit for full metadata + thread reconstruction
        if _is_tweet_url(url):
            thread = threading.Thread(
                target=run_ingest_tweet,
                args=(url, comment, ingest_id),
                daemon=True,
            )
            thread.start()
            print(f'[ingest] Tweet detected, fetching via twikit: {url[:80]} (id={ingest_id})')
        else:
            thread = threading.Thread(
                target=run_ingest,
                args=(url, title, content, selected_text, comment, source, ingest_id),
                daemon=True,
            )
            thread.start()
            print(f'[ingest] Queued: {url[:80]} (source={source}, id={ingest_id})')

        log_server_event('ingest_queued',
                         url=url[:200],
                         title=(title or url)[:100],
                         ingest_source=source,
                         article_id=article_id)

        self._send_json_response(202, {
            'status': 'queued',
            'url': url,
            'ingest_id': ingest_id,
            'article_id': article_id,
        })

    def _handle_media_sync(self):
        """POST /media/sync — sync media consumption records (podcasts, TV, etc.)."""
        body = self._read_json_body()
        if body is None:
            return

        media_log_path = Path(os.environ.get('MEDIA_LOG_PATH', '/opt/petrarca/data/media_log.json'))
        try:
            media_log = json.loads(media_log_path.read_text()) if media_log_path.exists() else {'items': []}
        except json.JSONDecodeError:
            media_log = {'items': []}

        existing_ids = {item['id'] for item in media_log['items']}
        new_items = body.get('items', [])
        added = 0

        for item in new_items:
            if item.get('id') and item['id'] not in existing_ids:
                media_log['items'].append(item)
                existing_ids.add(item['id'])
                added += 1

        media_log_path.write_text(json.dumps(media_log, indent=2, ensure_ascii=False))

        print(f'[media/sync] Added {added} items ({body.get("source", "unknown")}), total: {len(media_log["items"])}', flush=True)
        self._send_json_response(200, {'status': 'ok', 'added': added, 'total': len(media_log['items'])})

    def _handle_ingest_youtube(self):
        """POST /ingest-youtube — save YouTube video, fetch transcript, process as article."""
        body = self._read_json_body()
        if body is None:
            return
        video_id = body.get('video_id', '')
        if not video_id:
            self._send_json_response(400, {'error': 'Missing video_id'})
            return
        title = body.get('title', '')
        channel = body.get('channel', '')
        url = body.get('url', f'https://www.youtube.com/watch?v={video_id}')
        duration = body.get('duration', 0)
        description = body.get('description', '')
        keywords = body.get('keywords', [])
        chapters = body.get('chapters', [])

        # Save to media log
        media_log_path = Path(os.environ.get('MEDIA_LOG_PATH', '/opt/petrarca/data/media_log.json'))
        try:
            media_log = json.loads(media_log_path.read_text()) if media_log_path.exists() else {'items': []}
        except json.JSONDecodeError:
            media_log = {'items': []}
        existing_ids = {item['id'] for item in media_log['items']}
        article_id = f'yt_{video_id}'
        if article_id not in existing_ids:
            media_log['items'].append({
                'id': article_id, 'type': 'youtube', 'title': title,
                'source': channel, 'url': url,
                'date_consumed': datetime.now(timezone.utc).isoformat(),
                'duration': duration, 'description': description[:500],
                'keywords': keywords, 'chapters': chapters,
                'transcript_status': 'pending', 'claims_extracted': False,
            })
            media_log_path.write_text(json.dumps(media_log, indent=2, ensure_ascii=False))

        thread = threading.Thread(
            target=_process_youtube_video,
            args=(video_id, title, channel, url, description, chapters),
            daemon=True,
        )
        thread.start()
        print(f'[ingest-youtube] Queued: "{title}" by {channel} ({video_id})', flush=True)
        log_server_event('ingest_youtube', video_id=video_id, title=title[:100], channel=channel)
        self._send_json_response(202, {'status': 'queued', 'video_id': video_id})

    def _handle_ingest_note(self):
        """Add a note/comment to an already-ingested article (sidecar file)."""
        if INGEST_TOKEN:
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self._send_json_response(401, {'error': 'Invalid or missing auth token'})
                return

        body = self._read_json_body()
        if body is None:
            return

        url = body.get('url', '').strip()
        comment = body.get('comment', '').strip()
        if not url or not comment:
            self._send_json_response(400, {'error': 'Missing url or comment'})
            return

        sidecar = {
            'url': url,
            'title': body.get('title', ''),
            'source': body.get('source', 'clipper'),
            'created_at': int(time.time() * 1000),
            'notes': [{'text': comment, 'source': body.get('source', 'clipper')}],
        }
        sidecar_id = f'note_{int(time.time())}_{hash(url) % 10000:04d}'
        sidecar_path = INGEST_DIR / f'{sidecar_id}_sidecar.json'
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        print(f'[ingest-note] Saved note for {url[:60]}', flush=True)
        self._send_json_response(200, {'status': 'ok', 'sidecar_id': sidecar_id})

    def _handle_ingest_cancel(self):
        """Remove a recently-ingested article by URL (best-effort)."""
        if INGEST_TOKEN:
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self._send_json_response(401, {'error': 'Invalid or missing auth token'})
                return

        body = self._read_json_body()
        if body is None:
            return

        url = body.get('url', '').strip()
        if not url:
            self._send_json_response(400, {'error': 'Missing url'})
            return

        article_id = hashlib.sha256(url.encode()).hexdigest()[:12]
        removed = False

        try:
            articles = json.loads(ARTICLES_PATH.read_text())
            before = len(articles)
            articles = [a for a in articles if a.get('id') != article_id]
            if len(articles) < before:
                ARTICLES_PATH.write_text(json.dumps(articles, indent=2))
                removed = True
                print(f'[ingest-cancel] Removed {article_id} ({url[:60]})', flush=True)
            else:
                print(f'[ingest-cancel] Article {article_id} not found (may still be processing)', flush=True)
        except (json.JSONDecodeError, OSError) as e:
            print(f'[ingest-cancel] Error: {e}', flush=True)

        self._send_json_response(200, {
            'status': 'removed' if removed else 'not_found',
            'article_id': article_id,
        })

    def _handle_report_scrape(self):
        body = self._read_json_body()
        if body is None:
            return

        article_id = body.get('article_id', '')
        url = body.get('url', '')
        title = body.get('title', '')
        if not article_id:
            self._send_json_response(400, {'error': 'Missing article_id'})
            return

        try:
            reports = json.loads(SCRAPE_REPORTS_PATH.read_text()) if SCRAPE_REPORTS_PATH.exists() else []
        except (json.JSONDecodeError, OSError):
            reports = []

        # Skip if already reported
        if any(r['article_id'] == article_id for r in reports):
            self._send_json_response(200, {'status': 'already_reported'})
            return

        reports.append({
            'article_id': article_id,
            'url': url,
            'title': title,
            'reported_at': datetime.now(timezone.utc).isoformat(),
            'status': 'pending',
        })
        SCRAPE_REPORTS_PATH.write_text(json.dumps(reports, indent=2))
        print(f'[scrape-report] Reported {article_id}: {title[:60]}', flush=True)
        self._send_json_response(200, {'status': 'reported'})

    # --- Project handlers ---

    def _handle_projects_list(self):
        """GET /projects — list all projects with note counts."""
        conn = get_connection(readonly=True)
        rows = conn.execute("""
            SELECT p.id, p.name, p.description, p.status, p.created_at,
                   COUNT(n.id) as note_count,
                   COALESCE(MAX(n.created_at), p.created_at) as last_activity
            FROM projects p
            LEFT JOIN project_notes n ON n.project_id = p.id
            GROUP BY p.id
            ORDER BY last_activity DESC
        """).fetchall()
        conn.close()
        self._send_json_response(200, {'projects': [dict(r) for r in rows]})

    def _handle_project_detail(self):
        """GET /projects/{id} — get project with all its notes."""
        project_id = self.path.split('/')[2]
        conn = get_connection(readonly=True)
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            conn.close()
            self._send_json_response(404, {'error': 'Project not found'})
            return
        notes = conn.execute(
            "SELECT * FROM project_notes WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        conn.close()
        # Parse source JSON back to dict for each note
        note_list = []
        for n in notes:
            nd = dict(n)
            if nd.get('source'):
                try:
                    nd['source'] = json.loads(nd['source'])
                except (json.JSONDecodeError, TypeError):
                    pass
            note_list.append(nd)
        self._send_json_response(200, {'project': dict(row), 'notes': note_list})

    def _handle_project_create(self):
        """POST /projects — create a new project."""
        body = self._read_json_body()
        if body is None:
            return
        name = body.get('name', '').strip()
        if not name:
            self._send_json_response(400, {'error': 'Missing required field: name'})
            return
        project = {
            'id': _gen_id('proj'),
            'name': name,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active',
            'description': body.get('description', ''),
        }
        conn = get_connection()
        conn.execute(
            "INSERT INTO projects (id, name, description, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (project['id'], project['name'], project['description'], project['status'], project['created_at']),
        )
        conn.commit()
        conn.close()
        print(f'[projects] Created project {project["id"]}: {name}', flush=True)
        self._send_json_response(201, {'project': project})

    def _handle_project_note(self):
        """POST /projects/note — add a note to a project (multipart/form-data or JSON)."""
        content_type = self.headers.get('Content-Type', '')

        if 'multipart' in content_type.lower():
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b''
            try:
                form = self._multipart_parse_bytes(body, content_type)
            except Exception as e:
                self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
                return
            project_id = form.getvalue('project_id', '')
            text = form.getvalue('text', '')
            source_raw = form.getvalue('source', '')
            try:
                source = json.loads(source_raw) if source_raw else None
            except json.JSONDecodeError:
                source = None
            audio_file = None
            note_id = _gen_id('note')
            if 'audio' in form and form['audio'].file:
                audio_filename = f'{note_id}_audio.m4a'
                audio_path = PROJECTS_MEDIA_DIR / audio_filename
                audio_data = form['audio'].file.read()
                audio_path.write_bytes(audio_data if isinstance(audio_data, bytes) else audio_data.encode('latin-1'))
                audio_file = audio_filename
                print(f'[projects] Saved audio: {audio_filename}', flush=True)
        elif 'application/json' in content_type:
            body = self._read_json_body()
            if body is None:
                return
            project_id = body.get('project_id', '')
            text = body.get('text', '')
            source = body.get('source')
            audio_file = None
            note_id = _gen_id('note')
        else:
            self._send_json_response(400, {'error': 'Expected multipart/form-data or application/json'})
            return

        if not project_id:
            self._send_json_response(400, {'error': 'Missing required field: project_id'})
            return

        conn = get_connection()
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            conn.close()
            self._send_json_response(404, {'error': 'Project not found'})
            return

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO project_notes (id, project_id, text, audio_file, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, project_id, text, audio_file, json.dumps(source) if source else None, now),
        )
        conn.commit()
        conn.close()

        note = {'id': note_id, 'project_id': project_id, 'text': text,
                'audio_file': audio_file, 'source': source, 'created_at': now}
        print(f'[projects] Added note {note_id} to project {project_id}', flush=True)
        self._send_json_response(201, {'note': note})

    def _handle_project_update(self):
        """POST /projects/{id}/update — update project fields."""
        parts = self.path.split('/')
        project_id = parts[2] if len(parts) >= 4 else ''
        body = self._read_json_body()
        if body is None:
            return

        conn = get_connection()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            conn.close()
            self._send_json_response(404, {'error': 'Project not found'})
            return

        updates = {k: body[k] for k in ('name', 'status', 'description') if k in body}
        if updates:
            set_clause = ', '.join(f'{k} = ?' for k in updates)
            conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", (*updates.values(), project_id))
            conn.commit()

        updated = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        conn.close()
        print(f'[projects] Updated project {project_id}', flush=True)
        self._send_json_response(200, {'project': dict(updated)})

    def _handle_feedback(self):
        """Receive feedback with optional screenshot, audio, text, and context."""
        content_type = self.headers.get('Content-Type', '')

        if 'multipart' not in content_type.lower():
            self._send_json_response(400, {'error': 'Expected multipart/form-data'})
            return

        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b''
        try:
            form = self._multipart_parse_bytes(body, content_type)
        except Exception as e:
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return

        context_raw = form.getvalue('context', '')
        if not context_raw:
            self._send_json_response(400, {'error': 'Missing required field: context'})
            return

        try:
            context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        except json.JSONDecodeError:
            self._send_json_response(400, {'error': 'Invalid JSON in context field'})
            return

        text = form.getvalue('text', '')
        ts = datetime.now(timezone.utc)
        feedback_id = f'feedback_{ts.strftime("%Y%m%d_%H%M%S")}'

        saved_files = {}

        # Save screenshot if present
        if 'screenshot' in form and form['screenshot'].file:
            screenshot_path = FEEDBACK_DIR / f'{feedback_id}_screenshot.png'
            data = form['screenshot'].file.read()
            screenshot_path.write_bytes(data if isinstance(data, bytes) else data.encode('latin-1'))
            saved_files['screenshot'] = screenshot_path.name
            print(f'[feedback] Saved screenshot: {screenshot_path.name}', flush=True)

        # Save audio if present
        audio_path = None
        if 'audio' in form and form['audio'].file:
            audio_path = FEEDBACK_DIR / f'{feedback_id}_audio.m4a'
            data = form['audio'].file.read()
            audio_path.write_bytes(data if isinstance(data, bytes) else data.encode('latin-1'))
            saved_files['audio'] = audio_path.name
            print(f'[feedback] Saved audio: {audio_path.name}', flush=True)

        # Build metadata
        metadata = {
            'id': feedback_id,
            'timestamp': ts.isoformat(),
            'context': context,
            'text': text if isinstance(text, str) else '',
            'files': saved_files,
        }

        # Transcribe audio in background if present
        if audio_path:
            def _transcribe_and_update():
                transcript = None
                try:
                    transcript = transcribe_on_server(audio_path)
                    metadata['transcript'] = transcript
                    print(f'[feedback] {feedback_id} transcribed: {transcript[:80]}...', flush=True)
                except Exception as e:
                    metadata['transcript_error'] = str(e)
                    print(f'[feedback] {feedback_id} transcription failed: {e}', flush=True)
                finally:
                    meta_path = FEEDBACK_DIR / f'{feedback_id}.json'
                    meta_path.write_text(json.dumps(metadata, indent=2))
                # Voice routing (best-effort, non-blocking)
                if transcript:
                    threading.Thread(
                        target=_route_and_enrich_feedback,
                        args=(feedback_id, transcript, context),
                        daemon=True,
                    ).start()

            thread = threading.Thread(target=_transcribe_and_update, daemon=True)
            thread.start()
        else:
            # No audio — save metadata immediately
            meta_path = FEEDBACK_DIR / f'{feedback_id}.json'
            meta_path.write_text(json.dumps(metadata, indent=2))

        # Voice routing for text-only feedback
        effective_text = text if isinstance(text, str) else ''
        if effective_text and not audio_path:
            threading.Thread(
                target=_route_and_enrich_feedback,
                args=(feedback_id, effective_text, context),
                daemon=True,
            ).start()

        print(f'[feedback] Received {feedback_id} (text={bool(text)}, audio={bool(audio_path)}, screenshot={"screenshot" in saved_files})', flush=True)
        log_server_event('feedback_received', feedback_id=feedback_id)

        self._send_json_response(200, {'status': 'saved', 'id': feedback_id})

    # --- Physical book handlers ---

    @staticmethod
    def _multipart_parse_bytes(body: bytes, content_type: str):
        """Parse multipart body (stdlib `cgi` removed in Python 3.13+)."""
        from multipart_compat import parse_multipart

        return parse_multipart(body, content_type)

    def _parse_multipart_form(self):
        """Parse multipart form data, returning (form, error_response_sent)."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type.lower():
            self._send_json_response(400, {'error': 'Expected multipart/form-data'})
            return None, True
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b''
        try:
            form = self._multipart_parse_bytes(body, content_type)
        except Exception as e:
            print(f'[multipart] parse error: {e}', flush=True)
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return None, True
        return form, False

    def _save_upload_photo(self, form, field_name: str, prefix: str) -> Path | None:
        """Save an uploaded photo from multipart form to BOOK_UPLOADS_DIR."""
        if field_name not in form or not form[field_name].file:
            return None
        ext = 'jpg'
        if form[field_name].filename and form[field_name].filename.endswith('.png'):
            ext = 'png'
        photo_path = BOOK_UPLOADS_DIR / f'{prefix}_{int(time.time())}.{ext}'
        data = form[field_name].file.read()
        photo_path.write_bytes(data if isinstance(data, bytes) else data.encode('latin-1'))
        return photo_path

    def _handle_book_identify(self):
        """Identify a book from a cover/title page photo."""
        form, err = self._parse_multipart_form()
        if err:
            return

        photo_path = self._save_upload_photo(form, 'photo', 'cover')
        if not photo_path:
            self._send_json_response(400, {'error': 'Missing photo field'})
            return

        print(f'[book/identify] Received cover photo: {photo_path.name}', flush=True)

        try:
            result = process_book_identify(photo_path)
            if 'error' in result:
                self._send_json_response(422, result)
            else:
                self._send_json_response(200, result)
        except Exception as e:
            print(f'[book/identify] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_book_ocr_toc(self):
        """OCR a table of contents photo."""
        form, err = self._parse_multipart_form()
        if err:
            return

        photo_path = self._save_upload_photo(form, 'photo', 'toc')
        if not photo_path:
            self._send_json_response(400, {'error': 'Missing photo field'})
            return

        book_id = form.getvalue('book_id', '')
        print(f'[book/ocr-toc] Received TOC photo for book {book_id}: {photo_path.name}', flush=True)

        try:
            result = process_book_ocr_toc(photo_path)
            self._send_json_response(200, result)
        except Exception as e:
            print(f'[book/ocr-toc] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_book_ocr_page(self):
        """OCR a book page photo and extract core ideas."""
        form, err = self._parse_multipart_form()
        if err:
            return

        photo_path = self._save_upload_photo(form, 'photo', 'page')
        if not photo_path:
            self._send_json_response(400, {'error': 'Missing photo field'})
            return

        book_id = form.getvalue('book_id', '')
        book_title = form.getvalue('book_title', '')
        page_str = form.getvalue('page_number', '')
        chapter = form.getvalue('chapter', '')
        page_number = int(page_str) if page_str and page_str.isdigit() else None

        print(f'[book/ocr-page] Received page photo for {book_title}: {photo_path.name}', flush=True)

        try:
            result = process_book_ocr_page(photo_path, book_title, page_number, chapter)
            self._send_json_response(200, result)
        except Exception as e:
            print(f'[book/ocr-page] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_book_upload_photo(self):
        """Fast photo upload — save to disk and queue for async OCR processing."""
        form, err = self._parse_multipart_form()
        if err:
            return

        capture_id = form.getvalue('capture_id', '')
        if not capture_id:
            self._send_json_response(400, {'error': 'Missing capture_id'})
            return

        photo_path = self._save_upload_photo(form, 'photo', f'page_{capture_id}')
        if not photo_path:
            self._send_json_response(400, {'error': 'Missing photo field'})
            return

        book_id = form.getvalue('book_id', '')
        book_title = form.getvalue('book_title', '')
        page_str = form.getvalue('page_number', '')
        chapter = form.getvalue('chapter', '')
        page_number = int(page_str) if page_str and page_str.isdigit() else None

        print(f'[book/upload-photo] Saved {capture_id}: {photo_path.name} ({photo_path.stat().st_size} bytes)', flush=True)

        # Queue for background OCR processing
        _enqueue_photo_ocr({
            'capture_id': capture_id,
            'photo_path': str(photo_path),
            'book_id': book_id,
            'book_title': book_title,
            'page_number': page_number,
            'chapter': chapter,
        })

        self._send_json_response(200, {'status': 'queued', 'capture_id': capture_id})

    def _handle_book_photo_results(self):
        """Return completed OCR results for given capture_ids."""
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        capture_ids = body.get('capture_ids', [])
        results = {}

        with _ocr_results_lock:
            for cid in capture_ids:
                if cid in _ocr_results:
                    results[cid] = _ocr_results.pop(cid)

        # Also check disk for results (in case server restarted)
        for cid in capture_ids:
            if cid in results:
                continue
            result_path = BOOK_UPLOADS_DIR / f'ocr_result_{cid}.json'
            if result_path.exists():
                try:
                    results[cid] = json.loads(result_path.read_text())
                    result_path.unlink()  # Clean up after reading
                except (json.JSONDecodeError, OSError):
                    pass

        # Check how many are still pending in the queue
        with _ocr_queue_lock:
            queue = _load_ocr_queue()
            pending_ids = {item['capture_id'] for item in queue}

        pending = [cid for cid in capture_ids if cid not in results and cid in pending_ids]

        self._send_json_response(200, {
            'results': results,
            'pending': pending,
        })

    def _handle_book_voice_note(self):
        """Receive a voice note about a physical book, transcribe and extract ideas."""
        form, err = self._parse_multipart_form()
        if err:
            return

        if 'audio' not in form or not form['audio'].file:
            self._send_json_response(400, {'error': 'Missing audio field'})
            return

        book_id = form.getvalue('book_id', '')
        book_title = form.getvalue('book_title', '')
        chapter = form.getvalue('chapter', '')
        page_str = form.getvalue('page_number', '')
        page_number = int(page_str) if page_str and page_str.isdigit() else None

        note_id = f'bnote_{int(time.time())}_{book_id[:8]}'
        audio_path = AUDIO_DIR / f'{note_id}.m4a'
        data = form['audio'].file.read()
        audio_path.write_bytes(data if isinstance(data, bytes) else data.encode('latin-1'))

        print(f'[book/voice-note] Received note {note_id} for {book_title}', flush=True)

        from claude_llm import call_claude_json
        result = {'id': note_id, 'transcript': '', 'extracted_ideas': [], 'topics': []}
        try:
            transcript = transcribe_on_server(audio_path)
            result['transcript'] = transcript

            # Extract ideas from transcript
            if transcript.strip():
                parsed = call_claude_json(
                    f"""Extract key ideas from this voice note about the book "{book_title}".
{f'Chapter: {chapter}' if chapter else ''}
{f'Page: {page_number}' if page_number else ''}

Transcript: {transcript}

Return a JSON object:
{{"extracted_ideas": ["idea 1", "idea 2"], "topics": ["topic1", "topic2"]}}
Return ONLY valid JSON.""",
                    timeout=90,
                    model='sonnet',
                )
                if isinstance(parsed, dict):
                    result['extracted_ideas'] = parsed.get('extracted_ideas', [])
                    result['topics'] = parsed.get('topics', [])

            print(f'[book/voice-note] {note_id} processed: {len(result["extracted_ideas"])} ideas', flush=True)
        except Exception as e:
            print(f'[book/voice-note] {note_id} error: {e}', flush=True)

        # Save note result
        note_path = NOTES_DIR / f'{note_id}.json'
        note_path.write_text(json.dumps({
            **result,
            'book_id': book_id,
            'book_title': book_title,
            'chapter': chapter,
            'page_number': page_number,
            'audio_path': str(audio_path),
            'created_at': int(time.time() * 1000),
        }, indent=2))

        self._send_json_response(200, result)

    def _handle_book_research(self):
        """Trigger background research for a physical book."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing request body'})
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        book_id = body.get('book_id', '')
        title = body.get('title', '')
        author = body.get('author', '')
        if not title:
            self._send_json_response(400, {'error': 'Missing title'})
            return

        isbn = body.get('isbn')
        chapters = body.get('chapters', [])
        topics = body.get('topics', [])

        print(f'[book/research] Starting research for "{title}" by {author}', flush=True)

        def _do_research():
            try:
                from book_research_agent import research_book
                research_book(book_id, title, author, isbn, chapters, topics)
            except Exception as e:
                print(f'[book/research] Error: {e}', flush=True)

        thread = threading.Thread(target=_do_research, daemon=True)
        thread.start()

        self._send_json_response(202, {'status': 'researching', 'book_id': book_id})

    def _handle_book_chapter_insights(self):
        """Get research and connections for a specific chapter."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing request body'})
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        book_id = body.get('book_id', '')
        chapter_number = body.get('chapter_number', 1)
        chapter_title = body.get('chapter_title', '')
        captures = body.get('captures', [])

        print(f'[book/chapter-insights] Ch {chapter_number} of {book_id}', flush=True)

        try:
            from book_research_agent import get_chapter_insights
            result = get_chapter_insights(book_id, chapter_number, chapter_title, captures)
            self._send_json_response(200, result)
        except Exception as e:
            print(f'[book/chapter-insights] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_book_story_so_far(self):
        """Generate a 'Story So Far' briefing for returning to a book."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing request body'})
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        book_id = body.get('book_id', '')
        title = body.get('title', '')
        author = body.get('author', '')
        current_chapter = body.get('current_chapter')
        current_page = body.get('current_page')
        page_count = body.get('page_count')
        captures = body.get('captures', [])

        print(f'[book/story-so-far] Generating briefing for "{title}"', flush=True)

        try:
            from book_research_agent import generate_story_so_far
            result = generate_story_so_far(
                book_id, title, author,
                current_chapter, current_page, page_count,
                captures,
            )
            self._send_json_response(200, result)
        except Exception as e:
            print(f'[book/story-so-far] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_book_research_get(self):
        """GET /book/research/{book_id} — retrieve cached research."""
        book_id = self.path.split('/')[-1]
        from book_research_agent import load_book_research
        research = load_book_research(book_id)
        if research:
            self._send_json_response(200, research)
        else:
            self._send_json_response(404, {'error': 'No research found for this book'})

    # -----------------------------------------------------------------------
    # Kindle library sync
    # -----------------------------------------------------------------------

    def _handle_kindle_sync(self):
        """POST /kindle/sync — receive Kindle library data and store in SQLite."""
        body = self._read_json_body()
        if body is None:
            return

        data_type = body.get('data_type', 'library')
        now = datetime.now(timezone.utc).isoformat()

        # Log every sync event
        log_entry = json.dumps({
            'ts': now,
            'data_type': data_type,
            'source': body.get('source', 'unknown'),
            'url': body.get('url', ''),
            'book_count': len(body.get('books', [])),
        })
        with open(KINDLE_SYNC_LOG_PATH, 'a') as f:
            f.write(log_entry + '\n')

        if data_type == 'notebook':
            return self._handle_kindle_notebook_sync(body, now)

        # Library sync — merge books into SQLite
        from db import get_connection as _get_conn, get_kindle_book
        conn = _get_conn()

        new_count = 0
        updated_count = 0
        is_amazon = data_type == 'amazon_library'

        incoming_books = body.get('books', [])
        for book in incoming_books:
            asin = book.get('asin', '')
            title = book.get('title', '')
            book_id = book.get('book_id', '')
            if not asin and not title and not book_id:
                continue

            key = asin if asin else (book_id if book_id else f'title:{title[:80]}')
            existing = get_kindle_book(key, conn)

            if existing:
                # Update existing — keep curation fields, update progress
                updates = {'last_seen': now}
                if book.get('progress_text'):
                    updates['progress_text'] = book['progress_text']
                    updates['progress_updated'] = now
                if book.get('progress_pct') is not None and not is_amazon:
                    updates['progress_pct'] = book['progress_pct']
                    updates['current_position'] = book.get('current_position', 0)
                    updates['max_position'] = book.get('max_position', 0)
                    updates['progress_updated'] = now
                if book.get('cover_url') and not existing.get('cover_url'):
                    updates['cover_url'] = book['cover_url']
                if book.get('author') and not existing.get('author'):
                    updates['author'] = book['author']
                if book.get('last_read'):
                    updates['last_read'] = book['last_read']
                if book.get('status') and book['status'] != 'unread':
                    updates['status'] = book['status']
                if book.get('finished_date') and not existing.get('finished_date'):
                    updates['finished_date'] = book['finished_date']
                if book.get('purchase_date') and not existing.get('purchase_date'):
                    updates['purchase_date'] = book['purchase_date']
                if book.get('publisher') and not existing.get('publisher'):
                    updates['publisher'] = book['publisher']

                set_clause = ', '.join(f'{k}=?' for k in updates)
                conn.execute(
                    f'UPDATE kindle_books SET {set_clause} WHERE key=?',
                    list(updates.values()) + [key]
                )
                updated_count += 1
            else:
                # New book
                row = {
                    'key': key,
                    'asin': asin,
                    'book_id': book_id,
                    'title': title,
                    'author': book.get('author', ''),
                    'cover_url': book.get('cover_url', ''),
                    'progress_pct': book.get('progress_pct') or 0,
                    'current_position': book.get('current_position', 0),
                    'max_position': book.get('max_position', 0),
                    'progress_text': book.get('progress_text', ''),
                    'progress_updated': now,
                    'first_seen': now,
                    'last_seen': now,
                    'status': book.get('status', 'unreviewed'),
                    'finished_date': book.get('finished_date'),
                    'last_read': book.get('last_read'),
                    'purchase_date': book.get('purchase_date', ''),
                    'language': book.get('language', ''),
                    'publisher': book.get('publisher', ''),
                    'is_sideloaded': int(bool(book.get('is_sideloaded', False))),
                    'category': None,
                    'added_to_petrarca': 0,
                    'epub_path': None,
                    'source': 'amazon_library' if is_amazon else 'kindle_mac',
                }
                cols = ', '.join(row.keys())
                placeholders = ', '.join(['?'] * len(row))
                conn.execute(
                    f'INSERT OR IGNORE INTO kindle_books ({cols}) VALUES ({placeholders})',
                    list(row.values())
                )
                new_count += 1

        conn.commit()
        total = conn.execute('SELECT COUNT(*) FROM kindle_books').fetchone()[0]
        conn.close()

        print(f'[kindle/sync] Library: {new_count} new, {updated_count} updated, {total} total', flush=True)
        self._send_json_response(200, {
            'status': 'ok',
            'new_books': new_count,
            'updated_books': updated_count,
            'total_books': total,
        })

    def _handle_kindle_notebook_sync(self, body, now):
        """Handle notebook (highlights/notes) data."""
        existing = {'books': {}, 'last_sync': None}
        if KINDLE_HIGHLIGHTS_PATH.exists():
            try:
                existing = json.loads(KINDLE_HIGHLIGHTS_PATH.read_text())
            except json.JSONDecodeError:
                pass

        books_dict = existing.get('books', {})
        total_highlights = 0
        total_notes = 0

        for book in body.get('books', []):
            asin = book.get('asin', '')
            title = book.get('title', '')
            key = asin if asin else f'title:{title[:80]}'

            if not key:
                continue

            highlights = book.get('highlights', [])
            notes = book.get('notes', [])
            total_highlights += len(highlights)
            total_notes += len(notes)

            if key in books_dict:
                entry = books_dict[key]
                # Merge highlights (deduplicate by text)
                existing_texts = {h['text'] for h in entry.get('highlights', [])}
                for h in highlights:
                    if h.get('text') and h['text'] not in existing_texts:
                        entry.setdefault('highlights', []).append({**h, 'synced_at': now})
                        existing_texts.add(h['text'])
                # Merge notes
                existing_note_texts = {n['text'] for n in entry.get('notes', [])}
                for n in notes:
                    if n.get('text') and n['text'] not in existing_note_texts:
                        entry.setdefault('notes', []).append({**n, 'synced_at': now})
                        existing_note_texts.add(n['text'])
                entry['last_sync'] = now
            else:
                books_dict[key] = {
                    'asin': asin,
                    'title': title,
                    'author': book.get('author', ''),
                    'cover_url': book.get('cover_url', ''),
                    'highlights': [{**h, 'synced_at': now} for h in highlights],
                    'notes': [{**n, 'synced_at': now} for n in notes],
                    'first_sync': now,
                    'last_sync': now,
                }

        result = {
            'books': books_dict,
            'last_sync': now,
        }
        KINDLE_HIGHLIGHTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        print(f'[kindle/sync] Notebook: {total_highlights} highlights, {total_notes} notes across {len(body.get("books", []))} books', flush=True)
        self._send_json_response(200, {
            'status': 'ok',
            'highlights': total_highlights,
            'notes': total_notes,
        })

    def _handle_kindle_library_get(self):
        """GET /kindle/library — return Kindle library with curation status from SQLite."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        exclude_processed = params.get('exclude_processed', [''])[0] == 'true'

        from db import get_connection as _get_conn
        conn = _get_conn(readonly=True)
        try:
            where = 'WHERE added_to_petrarca = 0' if exclude_processed else ''
            rows = conn.execute(f'SELECT * FROM kindle_books {where} ORDER BY last_seen DESC').fetchall()
            total = conn.execute('SELECT COUNT(*) FROM kindle_books').fetchone()[0]

            books = {}
            for row in rows:
                book = dict(row)
                book['added_to_petrarca'] = bool(book.get('added_to_petrarca'))
                book['is_sideloaded'] = bool(book.get('is_sideloaded'))
                resolved = book.get('title_resolved')
                if resolved and resolved != book.get('title'):
                    book['title_display'] = resolved
                # Reconstruct progress object for backward compat
                book['progress'] = {
                    'pct': book.get('progress_pct', 0),
                    'text': book.get('progress_text', ''),
                    'current_position': book.get('current_position', 0),
                    'max_position': book.get('max_position', 0),
                    'updated': book.get('progress_updated', ''),
                }
                books[book['key']] = book

            self._send_json_response(200, {'books': books, 'sync_count': total})
        finally:
            conn.close()

    def _handle_kindle_highlights_get(self):
        """GET /kindle/highlights or /kindle/highlights?asin=X — return highlights."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        asin_filter = params.get('asin', [None])[0]

        if not KINDLE_HIGHLIGHTS_PATH.exists():
            self._send_json_response(200, {'books': {}})
            return
        try:
            data = json.loads(KINDLE_HIGHLIGHTS_PATH.read_text())
            if asin_filter:
                book = data.get('books', {}).get(asin_filter, {})
                self._send_json_response(200, {'book': book})
            else:
                self._send_json_response(200, data)
        except json.JSONDecodeError:
            self._send_json_response(200, {'books': {}})

    def _handle_kindle_recently_started(self):
        """GET /kindle/recently-started — books with reading progress, not yet tracked or dismissed."""
        from db import get_connection as _get_conn
        conn = _get_conn(readonly=True)
        try:
            rows = conn.execute('''
                SELECT key, title, title_resolved, author, cover_url,
                       progress_pct, status, category, last_seen, first_seen
                FROM kindle_books
                WHERE added_to_petrarca = 0
                  AND status NOT IN ('skipped', 'read')
                  AND progress_pct > 0 AND progress_pct < 95
                ORDER BY progress_pct DESC
            ''').fetchall()

            results = [{
                'key': r['key'],
                'title': r['title_resolved'] or r['title'],
                'author': r['author'] or '',
                'cover_url': r['cover_url'] or '',
                'progress_pct': r['progress_pct'],
                'status': r['status'],
                'category': r['category'],
                'last_seen': r['last_seen'] or '',
                'first_seen': r['first_seen'] or '',
            } for r in rows]

            self._send_json_response(200, {'books': results})
        finally:
            conn.close()

    def _handle_kindle_curate(self):
        """POST /kindle/curate — update curation fields for Kindle books."""
        body = self._read_json_body()
        if body is None:
            return

        from db import get_connection as _get_conn
        conn = _get_conn()

        ALLOWED_FIELDS = {'status', 'category', 'added_to_petrarca', 'epub_path', 'title_resolved', 'finished_date'}
        updates = body.get('updates', [])
        updated = 0

        for update in updates:
            key = update.get('key', '')
            if not key:
                continue

            fields = {}
            for f in ALLOWED_FIELDS:
                if f in update:
                    v = update[f]
                    if f == 'added_to_petrarca':
                        v = int(bool(v))
                    fields[f] = v

            if not fields:
                continue

            set_clause = ', '.join(f'{k}=?' for k in fields)
            result = conn.execute(
                f'UPDATE kindle_books SET {set_clause} WHERE key=?',
                list(fields.values()) + [key]
            )
            if result.rowcount > 0:
                updated += 1

        conn.commit()
        conn.close()

        print(f'[kindle/curate] Updated {updated} books', flush=True)
        self._send_json_response(200, {'status': 'ok', 'updated': updated})

    def _handle_kindle_include(self):
        """POST /kindle/include — include a Kindle book in the Library.

        Creates a unified PhysicalBook, converts highlights to captures,
        marks added_to_petrarca in SQLite, and starts research/ingestion in background.
        """
        body = self._read_json_body()
        if body is None:
            return

        key = body.get('key', '').strip()
        if not key:
            self._send_json_response(400, {'error': 'Missing required field: key'})
            return

        from db import get_connection as _get_conn, get_kindle_book, upsert_books, upsert_captures

        kindle_book = get_kindle_book(key)
        if not kindle_book:
            self._send_json_response(404, {'error': f'Book key not found: {key}'})
            return

        # Check if already unified
        conn = _get_conn(readonly=True)
        existing = conn.execute(
            "SELECT * FROM physical_books WHERE kindle_asin=? OR kindle_book_id=? OR id=?",
            (key, key, f'kindle_{key}')
        ).fetchone()
        conn.close()

        if existing:
            self._send_json_response(200, {'book': dict(existing), 'captures': [], 'already_existed': True})
            return

        # Convert to unified record
        from process_kindle_books import kindle_to_unified_book, highlights_to_captures, load_kindle_highlights
        unified = kindle_to_unified_book(key, kindle_book)

        # Convert highlights
        highlights_data = load_kindle_highlights()
        captures = highlights_to_captures(key, unified['id'], highlights_data)

        # Save to SQLite
        conn = _get_conn()
        upsert_books([unified], conn)
        if captures:
            upsert_captures(captures, conn)
        # Mark as added in kindle_books
        conn.execute(
            "UPDATE kindle_books SET added_to_petrarca=1, status='read' WHERE key=?",
            (key,)
        )
        conn.commit()
        conn.close()

        title = unified['title']
        epub_path = kindle_book.get('epub_path')
        print(f'[kindle/include] Included: {title} ({len(captures)} highlights, epub={epub_path is not None})', flush=True)

        # Start research/ingestion in background
        def _background():
            try:
                # If EPUB available, trigger full ingestion
                if epub_path and os.path.exists(epub_path):
                    print(f'[kindle/include] Starting EPUB ingestion for {title}', flush=True)
                    from ingest_book_petrarca import main as ingest_main
                    ingest_main([epub_path, '--output-dir', '/opt/petrarca/data/books',
                                 '--cross-match-dir', '/opt/petrarca/data'])
                    print(f'[kindle/include] EPUB ingestion done: {title}', flush=True)
                else:
                    # Fall back to research agent
                    from process_kindle_books import research_book_if_needed
                    topics = unified.get('topics', [])
                    if not topics:
                        cat = kindle_book.get('category', '')
                        if cat:
                            topics = [cat]
                    research_book_if_needed(
                        unified['id'], title, unified['author'],
                        unified.get('chapters', []), topics,
                    )
                    print(f'[kindle/include] Research done: {title}', flush=True)
            except Exception as e:
                print(f'[kindle/include] Background error for {title}: {e}', flush=True)
                import traceback; traceback.print_exc()

        thread = threading.Thread(target=_background, daemon=True)
        thread.start()

        self._send_json_response(200, {
            'book': unified,
            'captures': captures,
            'already_existed': False,
        })

    def _handle_kindle_classify(self):
        """POST /kindle/classify — use LLM to classify unreviewed books by category."""
        from db import get_connection as _get_conn
        conn = _get_conn(readonly=True)
        rows = conn.execute(
            "SELECT key, title, title_resolved, author FROM kindle_books WHERE category IS NULL"
        ).fetchall()
        conn.close()

        unclassified = [{'key': r['key'], 'title': r['title_resolved'] or r['title'], 'author': r['author']} for r in rows]

        if not unclassified:
            self._send_json_response(200, {'status': 'ok', 'message': 'All books already classified', 'classified': 0})
            return

        from claude_llm import call_claude_json
        classified_count = 0
        valid_cats = ('non-fiction', 'classical-literature', 'literary-fiction', 'genre-fiction', 'language-learning', 'reference')
        classified_pairs = []  # (key, category) tuples

        for i in range(0, len(unclassified), 50):
            batch = unclassified[i:i+50]
            book_list = '\n'.join(
                f'{j+1}. "{b["title"]}" by {b["author"] or "unknown"}'
                for j, b in enumerate(batch)
            )

            prompt = f"""Classify each of these books into exactly one category. Return ONLY a JSON array of objects with "index" (1-based) and "category" fields.

Categories (classify each book into EXACTLY ONE):
- "non-fiction" — history, science, philosophy, biography, essays, politics, technical, academic, etc.
- "classical-literature" — ancient/medieval/early-modern literature: Greek, Latin, Shakespeare, Dante, Cervantes, Goethe, etc. Also poetry collections from any era.
- "literary-fiction" — modern literary fiction, historical novels, and serious/ambitious fiction: Fowles, Eco, Marquez, Ibsen, Camus, etc.
- "genre-fiction" — crime, thriller, spy, romance, military fiction, sci-fi, fantasy — popular/commercial fiction
- "language-learning" — language textbooks, readers, bilingual editions, grammars, dictionaries
- "reference" — dictionaries, encyclopedias, collected works, anthologies, textbooks

Books:
{book_list}

Return JSON array only, no markdown fences:"""

            try:
                classifications = call_claude_json(prompt, timeout=180, model='sonnet')
                if not isinstance(classifications, list):
                    print(f'[kindle/classify] Batch {i//50}: unexpected shape', flush=True)
                    continue

                for item in classifications:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get('index', 0) - 1
                    category = item.get('category', '')
                    if 0 <= idx < len(batch) and category in valid_cats:
                        classified_pairs.append((batch[idx]['key'], category))
                        classified_count += 1
            except Exception as e:
                print(f'[kindle/classify] Batch {i//50} error: {e}', flush=True)

        # Batch update in SQLite
        if classified_pairs:
            conn = _get_conn()
            conn.executemany(
                'UPDATE kindle_books SET category=? WHERE key=?',
                [(cat, key) for key, cat in classified_pairs]
            )
            conn.commit()
            conn.close()

        # Category summary
        conn = _get_conn(readonly=True)
        cat_rows = conn.execute(
            "SELECT COALESCE(category, 'unclassified') as cat, COUNT(*) as cnt FROM kindle_books GROUP BY category"
        ).fetchall()
        conn.close()
        categories = {r['cat']: r['cnt'] for r in cat_rows}

        print(f'[kindle/classify] Classified {classified_count} books: {categories}', flush=True)
        self._send_json_response(200, {
            'status': 'ok',
            'classified': classified_count,
            'categories': categories,
        })

    def _handle_kindle_resolve_titles(self):
        """POST /kindle/resolve-titles — use LLM to identify real titles from filenames."""
        body = self._read_json_body()
        if body is None:
            return

        books_to_resolve = body.get('books', [])
        if not books_to_resolve:
            self._send_json_response(400, {'error': 'No books to resolve'})
            return

        from claude_llm import call_claude_json

        resolved = {}
        for i in range(0, len(books_to_resolve), 30):
            batch = books_to_resolve[i:i+30]
            book_list = '\n'.join(
                f'{j+1}. Filename: "{b["filename"]}" | Author: "{b.get("author", "unknown")}"'
                for j, b in enumerate(batch)
            )

            prompt = f"""Identify the real book title for each of these ebook files.
Clues: "pg*-images-3" = Project Gutenberg file. Use the author to find the specific work.
Other filenames may be abbreviations or slugs of the title.

Return ONLY a JSON array with "index" (1-based) and "title" (the canonical book title).
If unsure, set title to null.

{book_list}

JSON array only:"""

            try:
                titles = call_claude_json(prompt, timeout=180, model='sonnet')
                if not isinstance(titles, list):
                    print(f'[kindle/resolve-titles] Batch {i//30}: unexpected shape', flush=True)
                    continue

                for item in titles:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get('index', 0) - 1
                    title = item.get('title')
                    if 0 <= idx < len(batch) and title:
                        key = batch[idx].get('key', '')
                        resolved[key] = title
            except Exception as e:
                print(f'[kindle/resolve-titles] Batch {i//30} error: {e}', flush=True)

        # Update SQLite with resolved titles
        if resolved:
            from db import get_connection as _get_conn
            conn = _get_conn()
            matched = 0
            for key, title in resolved.items():
                # Try direct key match
                result = conn.execute(
                    'UPDATE kindle_books SET title_resolved=? WHERE key=?', (title, key)
                )
                if result.rowcount > 0:
                    matched += 1
                else:
                    # Try matching by book_id field
                    result = conn.execute(
                        'UPDATE kindle_books SET title_resolved=? WHERE book_id=?', (title, key)
                    )
                    if result.rowcount > 0:
                        matched += 1
            conn.commit()
            conn.close()
            print(f'[kindle/resolve-titles] Wrote {matched} resolved titles to SQLite', flush=True)

        print(f'[kindle/resolve-titles] Resolved {len(resolved)} of {len(books_to_resolve)} titles', flush=True)
        self._send_json_response(200, {'status': 'ok', 'resolved': resolved})

    def _handle_kindle_browse(self):
        """GET /kindle/browse — full-featured query endpoint for browse screen."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        from db import get_kindle_books
        books, total = get_kindle_books(
            search=params.get('search', [None])[0],
            status=params.get('status', [None])[0],
            category=params.get('category', [None])[0],
            tracked=params.get('tracked', [None])[0],
            sort=params.get('sort', ['recent'])[0],
            order=params.get('order', ['desc'])[0],
            limit=int(params.get('limit', [50])[0]),
            offset=int(params.get('offset', [0])[0]),
        )

        self._send_json_response(200, {
            'books': books,
            'total': total,
        })

    def _handle_kindle_scan_epubs(self):
        """POST /kindle/scan-epubs — scan server EPUB directory and match to kindle_books."""
        epub_dir = Path('/opt/petrarca/data/epubs')
        if not epub_dir.exists():
            self._send_json_response(200, {'scanned': 0, 'matched': 0, 'unmatched': []})
            return

        import re
        from zipfile import ZipFile
        from db import get_connection as _get_conn

        # Scan EPUB files and extract metadata
        epubs = []
        for epub_path in epub_dir.glob('*.epub'):
            title, author = '', ''
            try:
                with ZipFile(epub_path) as z:
                    for name in z.namelist():
                        if name.endswith('.opf'):
                            content = z.read(name).decode('utf-8', errors='replace')
                            m = re.search(r'<dc:title[^>]*>([^<]+)</dc:title>', content)
                            if m:
                                title = m.group(1).strip()
                            m = re.search(r'<dc:creator[^>]*>([^<]+)</dc:creator>', content)
                            if m:
                                author = m.group(1).strip()
                            break
            except Exception:
                pass

            epubs.append({
                'filename': epub_path.name,
                'server_path': str(epub_path),
                'title': title or epub_path.stem,
                'author': author,
                'size_bytes': epub_path.stat().st_size,
            })

        if not epubs:
            self._send_json_response(200, {'scanned': 0, 'matched': 0, 'unmatched': []})
            return

        conn = _get_conn()

        # Insert into available_epubs
        for e in epubs:
            conn.execute(
                'INSERT OR REPLACE INTO available_epubs (filename, server_path, title, author, size_bytes, uploaded_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (e['filename'], e['server_path'], e['title'], e['author'], e['size_bytes'],
                 datetime.now(timezone.utc).isoformat())
            )

        # Match against kindle_books by title (case-insensitive containment)
        matched = 0
        unmatched = []
        for e in epubs:
            if not e['title']:
                unmatched.append(e['filename'])
                continue

            # Try matching: kindle title contains epub title or vice versa
            row = conn.execute(
                'SELECT key FROM kindle_books '
                'WHERE epub_path IS NULL AND '
                '(LOWER(title) LIKE ? OR LOWER(title_resolved) LIKE ? '
                ' OR ? LIKE \'%\' || LOWER(title) || \'%\')',
                (f'%{e["title"].lower()}%', f'%{e["title"].lower()}%', e['title'].lower())
            ).fetchone()

            if row:
                conn.execute(
                    'UPDATE kindle_books SET epub_path=? WHERE key=?',
                    (e['server_path'], row['key'])
                )
                conn.execute(
                    'UPDATE available_epubs SET kindle_book_key=? WHERE server_path=?',
                    (row['key'], e['server_path'])
                )
                matched += 1
            else:
                unmatched.append(f"{e['title']} ({e['filename']})")

        conn.commit()
        conn.close()

        print(f'[kindle/scan-epubs] Scanned {len(epubs)}, matched {matched}', flush=True)
        self._send_json_response(200, {
            'scanned': len(epubs),
            'matched': matched,
            'unmatched': unmatched[:50],
        })

    def _handle_book_sync_save(self):
        """POST /book/sync — save books + captures to server (client → server).
        Writes directly to SQLite. Client wins for same ID (UPSERT).
        """
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing request body'})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        books = body.get('books', [])
        captures = body.get('captures', [])

        from db import get_connection, upsert_books, upsert_captures
        conn = get_connection()

        # Detect books transitioning to 'finished' — check pre-sync status
        newly_finished = []
        for book in books:
            if book.get('reading_status') == 'finished' and book.get('id'):
                row = conn.execute(
                    'SELECT reading_status FROM physical_books WHERE id=?', (book['id'],)
                ).fetchone()
                was_finished = row and row['reading_status'] == 'finished' if row else False
                if not was_finished:
                    newly_finished.append(book['id'])

        book_count = upsert_books(books, conn)
        cap_count = upsert_captures(captures, conn)
        conn.commit()
        conn.close()

        # Auto-map newly finished books to curricula in the background
        if newly_finished:
            import threading
            def _map_finished():
                from review_engine import map_whole_book
                from db import get_connection as _gc
                for bid in newly_finished:
                    try:
                        c = _gc()
                        result = map_whole_book(bid, c)
                        c.close()
                        print(f'[book/sync] Auto-mapped finished book {bid}: '
                              f'{result.get("total_items_created", 0)} items created', flush=True)
                    except Exception as e:
                        print(f'[book/sync] Auto-map failed for {bid}: {e}', flush=True)
            threading.Thread(target=_map_finished, daemon=True).start()
            print(f'[book/sync] {len(newly_finished)} newly finished books → mapping in background', flush=True)

        print(f'[book/sync] Saved {book_count} books, {cap_count} captures → SQLite', flush=True)
        self._send_json_response(200, {
            'status': 'ok',
            'books_count': book_count,
            'captures_count': cap_count,
        })

    def _handle_book_sync_load(self):
        """GET /book/sync — load books + captures from server (server → client).
        Reads from SQLite.
        """
        from db import load_all_books_and_captures
        data = load_all_books_and_captures()
        self._send_json_response(200, data)

    def _handle_resurfacing_generate(self):
        """POST /book/resurfacing/generate — generate a resurfacing session."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length:
            try:
                body = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, ValueError):
                pass
        include_dialogues = body.get('include_dialogues', True)
        try:
            from resurfacing_engine import generate_session
            session = generate_session(include_dialogues=include_dialogues)
            self._send_json_response(200, session)
        except Exception as e:
            print(f'[resurfacing/generate] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_resurfacing_respond(self):
        """POST /book/resurfacing/respond — record response to a resurfacing prompt."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing body'})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        capture_id = body.get('capture_id', '')
        response_text = body.get('response_text', '')
        response_type = body.get('response_type', 'text')
        if not capture_id or not response_text:
            self._send_json_response(400, {'error': 'Missing capture_id or response_text'})
            return

        from resurfacing_engine import record_response
        record_response(capture_id, response_text, response_type)
        self._send_json_response(200, {'status': 'ok'})

    def _handle_resurfacing_skip(self):
        """POST /book/resurfacing/skip — record skip for a resurfacing prompt."""
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            self._send_json_response(400, {'error': 'Missing body'})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return

        capture_id = body.get('capture_id', '')
        if not capture_id:
            self._send_json_response(400, {'error': 'Missing capture_id'})
            return

        from resurfacing_engine import record_skip
        record_skip(capture_id)
        self._send_json_response(200, {'status': 'ok'})

    def _handle_resurfacing_status(self):
        """GET /book/resurfacing/status — get resurfacing stats."""
        from resurfacing_engine import get_status
        self._send_json_response(200, get_status())

    def _handle_curriculum_review_generate(self):
        """POST /curriculum/review/generate — generate review stream from knowledge_items."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length:
            try:
                body = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, ValueError):
                pass
        domain = body.get('domain')
        limit = body.get('limit', 20)
        offset = body.get('offset', 0)
        try:
            result = generate_review_stream(
                domain_filter=domain, limit=limit, offset=offset)
            self._send_json_response(200, result)
        except Exception as e:
            print(f'[curriculum/review] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_curriculum_review_result(self):
        """POST /curriculum/review/result — record result for a review question."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        question_id = body.get('question_id')
        result = body.get('result')
        if not question_id or not result:
            self._send_json_response(400, {'error': 'question_id and result required'})
            return

        # Map any legacy grading terms
        RESULT_MAP = {
            'correct': 'knew', 'partial': 'partly', 'wrong': 'missed',
            'exact_year': 'knew', 'right_decade': 'partly', 'right_century': 'partly',
            'all_correct': 'knew', 'mostly_right': 'partly',
        }
        mapped_result = RESULT_MAP.get(result, result)

        from db import get_connection
        from review_engine import record_answer
        conn = get_connection()
        try:
            resp = record_answer(question_id, mapped_result, conn)
            if resp:
                from server_log import log_interaction
                log_interaction('review_answer', item_id=question_id, score=mapped_result,
                                card_type=body.get('card_type'),
                                new_stability=resp.get('new_stability_days'),
                                next_due=resp.get('next_due_at'),
                                response_time_ms=body.get('response_time_ms'))
                self._send_json_response(200, {'status': 'recorded', **resp})
            else:
                self._send_json_response(404, {'error': f'item {question_id} not found'})
        except Exception as e:
            print(f'[review/result] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_review_suspend(self):
        """POST /curriculum/review/suspend — suspend a knowledge_item for 1 year."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        item_id = body.get('item_id', '').strip()
        if not item_id:
            self._send_json_response(400, {'error': 'item_id required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            now_ms = int(time.time() * 1000)
            one_year = 365 * 24 * 60 * 60 * 1000
            conn.execute(
                'UPDATE knowledge_items SET due_at=?, last_score=? WHERE id=?',
                (now_ms + one_year, 'suspended', item_id))
            conn.commit()
            print(f'[review] suspended {item_id}', flush=True)
            from server_log import log_interaction
            log_interaction('review_suspend', item_id=item_id)
            self._send_json_response(200, {'status': 'suspended', 'item_id': item_id})
        except Exception as e:
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_suspend_fact(self):
        """POST /review/suspend-fact — suspend all quizzes sharing a fact_id."""
        body = self._read_json_body()
        if body is None:
            return
        fact_id = body.get('fact_id', '').strip()
        if not fact_id:
            self._send_json_response(400, {'error': 'fact_id required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            cursor = conn.execute(
                "UPDATE microlearning_quizzes SET status='dismissed' WHERE fact_id=? AND status='active'",
                (fact_id,))
            count = cursor.rowcount
            conn.commit()
            print(f'[suspend-fact] suspended {count} quizzes for fact_id={fact_id}', flush=True)
            from server_log import log_interaction
            log_interaction('suspend_fact', item_id=fact_id, extra=json.dumps({'count': count}))
            self._send_json_response(200, {'status': 'suspended', 'fact_id': fact_id, 'count': count})
        except Exception as e:
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_review_batch_generate(self):
        """POST /review/batch-generate — batch-generate cached_questions for knowledge_items."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length:
            try:
                body = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, ValueError):
                pass
        batch_limit = body.get('limit', 20)

        from db import get_connection
        from review_engine import generate_question
        conn = get_connection()
        try:
            # Find items with known knowledge state but no cached_question
            rows = conn.execute('''
                SELECT ki.id FROM knowledge_items ki
                LEFT JOIN knowledge_states ks
                  ON ks.domain_id = ki.curriculum_domain
                  AND ks.node_id = ki.curriculum_node_id
                WHERE ki.cached_question IS NULL
                  AND COALESCE(ks.knowledge, 'unknown') != 'unknown'
                LIMIT ?
            ''', (batch_limit,)).fetchall()
            item_ids = [r[0] for r in rows]
            conn.close()

            # Generate in background thread
            def _batch():
                from db import get_connection as _get_conn
                c = _get_conn()
                done = 0
                for iid in item_ids:
                    try:
                        q = generate_question(iid, c)
                        c.execute('UPDATE knowledge_items SET cached_question=? WHERE id=?',
                                  (json.dumps(q), iid))
                        c.commit()
                        done += 1
                        print(f'[batch-gen] {done}/{len(item_ids)} generated: {iid}', flush=True)
                    except Exception as e:
                        print(f'[batch-gen] failed for {iid}: {e}', flush=True)
                c.close()
                print(f'[batch-gen] Complete: {done}/{len(item_ids)}', flush=True)

            import threading
            threading.Thread(target=_batch, daemon=True).start()

            self._send_json_response(202, {
                'status': 'generating',
                'queued': len(item_ids),
                'message': f'Generating questions for {len(item_ids)} items in background',
            })
        except Exception as e:
            print(f'[batch-gen] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_microlearning_dismiss(self):
        """POST /review/microlearning/dismiss — dismiss a card or individual quiz."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        card_id = body.get('card_id', '').strip()
        quiz_id = body.get('quiz_id', '').strip()
        if not card_id and not quiz_id:
            self._send_json_response(400, {'error': 'card_id or quiz_id required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            if quiz_id:
                # Dismiss a single quiz
                conn.execute("UPDATE microlearning_quizzes SET status='dismissed' WHERE id=?",
                             (quiz_id,))
            if card_id:
                # Dismiss whole card + all its quizzes
                conn.execute("UPDATE microlearning_cards SET status='dismissed' WHERE id=?",
                             (card_id,))
                conn.execute("UPDATE microlearning_quizzes SET status='dismissed' WHERE card_id=?",
                             (card_id,))
            conn.commit()
            self._send_json_response(200, {'status': 'dismissed',
                                           'card_id': card_id, 'quiz_id': quiz_id})
        except Exception as e:
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_ml_flag_inaccurate(self):
        """POST /review/ml-flag-inaccurate — user reports a specific ML card as factually wrong.

        Sets flagged_inaccurate=1 on the card so it drops out of the review stream, and logs
        the reason for later triage / training-data mining. Session 90 P0: this is the canonical
        error channel for the epistemic-fidelity workstream — every downstream accuracy effort
        (validator, consistency checks) needs labeled bad cards as ground truth.
        """
        body = self._read_json_body()
        if body is None:
            return
        card_id = (body.get('card_id') or '').strip()
        reason = (body.get('reason') or '').strip()
        if not card_id:
            self._send_json_response(400, {'error': 'card_id required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            now_ms = int(time.time() * 1000)
            cursor = conn.execute(
                '''UPDATE microlearning_cards
                   SET flagged_inaccurate=1, flagged_reason=?, flagged_at=?
                   WHERE id=?''',
                (reason or None, now_ms, card_id))
            if cursor.rowcount == 0:
                self._send_json_response(404, {'error': f'card {card_id} not found'})
                return
            conn.commit()
            print(f'[ml-flag] inaccurate card_id={card_id} reason={reason!r}', flush=True)
            from server_log import log_interaction
            log_interaction('ml_flag_inaccurate', item_id=card_id,
                            extra=json.dumps({'reason': reason}))
            self._send_json_response(200, {'ok': True, 'card_id': card_id})
        except Exception as e:
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_microlearning_request(self):
        """POST /review/microlearning — trigger microlearning research for a query."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        query = body.get('query', '').strip()
        source_item_id = body.get('source_item_id')
        source_node_id = body.get('source_node_id')
        source_domain = body.get('source_domain')
        source_type = body.get('source_type', 'follow_up')
        if not query:
            self._send_json_response(400, {'error': 'query required'})
            return

        # Determine source_type and generation_depth from parent
        generation_depth = 0
        if source_item_id and source_item_id.startswith('ml_'):
            # Child of another ML card — follow_up unless explicitly overridden
            if source_type == 'follow_up':
                source_type = 'follow_up'
            try:
                from db import get_connection
                pconn = get_connection()
                parent = pconn.execute(
                    'SELECT generation_depth FROM microlearning_cards WHERE id=?',
                    (source_item_id,)).fetchone()
                pconn.close()
                if parent:
                    generation_depth = (parent[0] or 0) + 1
            except Exception:
                pass

        try:
            from review_engine import create_microlearning_request
            card_id = create_microlearning_request(
                query=query,
                source_item_id=source_item_id,
                source_node_id=source_node_id,
                source_domain=source_domain,
                source_type=source_type,
                generation_depth=generation_depth,
            )
            self._send_json_response(202, {
                'id': card_id,
                'status': 'processing',
                'query': query,
            })
        except Exception as e:
            print(f'[microlearning] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_follow_up_trigger(self):
        """POST /review/follow-up/trigger — durably record a follow-up query was triggered."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        item_id = body.get('item_id', '').strip()
        query = body.get('query', '').strip()
        if not item_id or not query:
            self._send_json_response(400, {'error': 'item_id and query required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            for table in ('knowledge_items', 'microlearning_cards'):
                row = conn.execute(f'SELECT triggered_follow_ups FROM {table} WHERE id=?',
                                   (item_id,)).fetchone()
                if row:
                    triggered = json.loads(row['triggered_follow_ups'] or '[]')
                    if query not in triggered:
                        triggered.append(query)
                    conn.execute(f'UPDATE {table} SET triggered_follow_ups=? WHERE id=?',
                                 (json.dumps(triggered), item_id))
                    conn.commit()
                    self._send_json_response(200, {'triggered': triggered})
                    return
            self._send_json_response(404, {'error': 'item not found'})
        except Exception as e:
            print(f'[follow-up-trigger] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_follow_up_generate(self):
        """POST /review/follow-up/generate — generate 3 new follow-up queries on demand."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        node_title = body.get('node_title', '').strip()
        node_description = body.get('node_description', '').strip()
        fact_context = body.get('fact_context', '').strip()
        exclude = body.get('exclude', [])
        if not node_title:
            self._send_json_response(400, {'error': 'node_title required'})
            return
        try:
            from review_engine import _generate_follow_up_queries
            extra = ''
            if exclude:
                extra = '\n\nDo NOT repeat or rephrase these already-asked questions:\n' + \
                    '\n'.join(f'- {q}' for q in exclude[:10])
            fqs = _generate_follow_up_queries(
                node_title, node_description,
                fact_context + extra if extra else fact_context,
            )
            self._send_json_response(200, {'follow_up_queries': fqs})
        except Exception as e:
            print(f'[follow-up-generate] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_create_factual_quiz(self):
        """POST /review/create-factual-quiz — create a quiz from a factual suggestion."""
        body = self._read_json_body()
        if body is None:
            return
        item_id = body.get('item_id', '').strip()
        question = body.get('question', '').strip()
        answer = body.get('answer', '').strip()
        fact_id = body.get('fact_id', '').strip()
        if not item_id or not question or not answer:
            self._send_json_response(400, {'error': 'item_id, question, and answer required'})
            return
        from db import get_connection
        import hashlib
        conn = get_connection()
        try:
            # Find the parent ML card for this knowledge_item (or create a virtual one)
            ki = conn.execute('SELECT * FROM knowledge_items WHERE id=?', (item_id,)).fetchone()
            if not ki:
                self._send_json_response(404, {'error': 'item not found'})
                return
            # Find or create a ML card to host this quiz
            mc = conn.execute(
                'SELECT id FROM microlearning_cards WHERE source_node_id=? AND source_domain=? LIMIT 1',
                (ki['curriculum_node_id'], ki['curriculum_domain'])).fetchone()
            if mc:
                card_id = mc['id']
            else:
                # Create a minimal ML card as quiz container
                card_id = hashlib.md5(f"{ki['curriculum_node_id']}:{ki['curriculum_domain']}:factual".encode()).hexdigest()[:12]
                now_ms = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR IGNORE INTO microlearning_cards
                    (id, query, source_node_id, source_domain, content, status, created_at, source_type)
                    VALUES (?,?,?,?,?,?,?,?)
                ''', (card_id, f"Factual quiz: {question[:60]}", ki['curriculum_node_id'],
                      ki['curriculum_domain'], '', 'completed', now_ms, 'follow_up'))
            # Look up rich_answer from key_facts if fact_id provided
            rich_answer = None
            if fact_id:
                node = conn.execute(
                    'SELECT key_facts FROM curriculum_nodes WHERE id=? AND domain_id=?',
                    (ki['curriculum_node_id'], ki['curriculum_domain'])).fetchone()
                if node and node['key_facts']:
                    for f in json.loads(node['key_facts']):
                        if f.get('id') == fact_id:
                            rich_answer = f.get('rich_answer') or f.get('answer', '')
                            break
            # Create the quiz
            quiz_id = hashlib.md5(f"{card_id}:{question}".encode()).hexdigest()[:12]
            now_ms = int(time.time() * 1000)
            conn.execute('''
                INSERT OR IGNORE INTO microlearning_quizzes
                (id, card_id, question, answer, fact_id, rich_answer,
                 status, stability_days, due_at, review_count, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', (quiz_id, card_id, question, answer, fact_id or None, rich_answer,
                  'active', 1.0, now_ms + 86400000, 0, now_ms))
            conn.commit()
            from server_log import log_interaction
            log_interaction('factual_quiz_created', item_id=quiz_id, node_title=question[:60],
                            domain=ki['curriculum_domain'])
            self._send_json_response(200, {'quiz_id': quiz_id, 'status': 'created'})
        except Exception as e:
            print(f'[factual-quiz] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_also_want_to_know(self):
        """POST /review/also-want-to-know — generate tappable suggestions after review."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        item_id = body.get('item_id', '')
        question_text = body.get('question', '')
        entities = body.get('entities', [])
        if not item_id:
            self._send_json_response(400, {'error': 'item_id required'})
            return
        try:
            from review_engine import generate_also_want_to_know
            suggestions = generate_also_want_to_know(item_id, question_text, entities)
            self._send_json_response(200, {'suggestions': suggestions})
        except Exception as e:
            print(f'[also-want-to-know] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_targeted_quiz(self):
        """POST /review/targeted-quiz — create a simple quiz for a specific fact gap."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        item_id = body.get('item_id', '')
        query = body.get('query', '').strip()
        query_type = body.get('type', 'simple_fact')
        if not item_id or not query:
            self._send_json_response(400, {'error': 'item_id and query required'})
            return
        try:
            if query_type == 'simple_fact':
                from review_engine import create_targeted_quiz
                result = create_targeted_quiz(item_id, query)
                self._send_json_response(200, result)
            else:
                # Complex/research → create ML card
                from review_engine import create_microlearning_request
                from db import get_connection
                conn = get_connection()
                ki = conn.execute(
                    'SELECT curriculum_node_id, curriculum_domain FROM knowledge_items WHERE id=?',
                    (item_id,)).fetchone()
                conn.close()
                card_id = create_microlearning_request(
                    query=query,
                    source_item_id=item_id,
                    source_node_id=ki[0] if ki else None,
                    source_domain=ki[1] if ki else None,
                    source_type='user_request',
                )
                self._send_json_response(202, {
                    'card_id': card_id, 'status': 'processing', 'query': query,
                })
        except Exception as e:
            print(f'[targeted-quiz] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})

    def _handle_entities_list(self):
        """GET /entities?type=place — list entities, optionally filtered by type."""
        from urllib.parse import urlparse, parse_qs
        from db import get_connection
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        entity_type = params.get('type', [None])[0]
        conn = get_connection(readonly=True)
        try:
            if entity_type:
                rows = conn.execute(
                    '''SELECT entity_id, name, description, entity_type, modern_name,
                              wikipedia_url, latitude, longitude, aliases, dates,
                              date_start, date_end, nexus_score
                       FROM shared_entities WHERE entity_type = ? ORDER BY name''',
                    (entity_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    '''SELECT entity_id, name, description, entity_type, modern_name,
                              wikipedia_url, latitude, longitude, aliases, dates,
                              date_start, date_end, nexus_score
                       FROM shared_entities ORDER BY name'''
                ).fetchall()
            entities = []
            for r in rows:
                e = dict(r)
                try:
                    e['aliases'] = json.loads(e.get('aliases') or '[]')
                except (json.JSONDecodeError, TypeError):
                    e['aliases'] = []
                # Map DB fields to what AncientMap expects
                e['curriculum_links'] = []
                entities.append(e)
            self._send_json_response(200, entities)
        finally:
            conn.close()

    def _handle_entity_lookup(self):
        """GET /entity/{entity_id} — get full entity details.

        If entity_id is not in shared_entities, fall back to searching
        microlearning cards for backlinks (dynamic entity from ML annotations).
        """
        entity_id = self.path.split('/entity/')[-1]
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            row = conn.execute(
                'SELECT * FROM shared_entities WHERE entity_id = ?', (entity_id,)
            ).fetchone()

            # Collect microlearning backlinks for this entity
            ml_backlinks = []
            eid_lower = entity_id.lower()
            try:
                ml_rows = conn.execute(
                    "SELECT id, query, content, entities, source_domain "
                    "FROM microlearning_cards WHERE status='completed' AND entities LIKE ?",
                    (f'%{entity_id}%',)
                ).fetchall()
                for ml in ml_rows:
                    entities_data = json.loads(ml['entities'] or '[]')
                    if any(e.get('canonical', '').lower() == eid_lower for e in entities_data):
                        ml_backlinks.append({
                            'card_id': ml['id'],
                            'query': ml['query'],
                            'snippet': (ml['content'] or '')[:150],
                            'domain': ml['source_domain'],
                        })
            except Exception:
                pass

            if row:
                links = conn.execute(
                    '''SELECT ecl.domain_id, ecl.node_id, ecl.lens_title, ecl.lens_emphasis,
                              cn.title as node_title, cn.description as node_description,
                              COALESCE(ks.knowledge, 'unknown') as knowledge
                       FROM entity_curriculum_links ecl
                       LEFT JOIN curriculum_nodes cn ON cn.id = ecl.node_id AND cn.domain_id = ecl.domain_id
                       LEFT JOIN knowledge_states ks ON ks.domain_id = ecl.domain_id AND ks.node_id = ecl.node_id
                       WHERE ecl.entity_id = ?''',
                    (entity_id,)
                ).fetchall()
                entity = dict(row)
                try:
                    entity['aliases'] = json.loads(entity.get('aliases') or '[]')
                except (json.JSONDecodeError, TypeError):
                    entity['aliases'] = []
                entity['curriculum_links'] = [dict(l) for l in links]
                entity['microlearning_backlinks'] = ml_backlinks
                # Include user notes
                try:
                    notes = conn.execute(
                        'SELECT id, note, created_at FROM entity_notes WHERE entity_id = ? ORDER BY created_at DESC',
                        (entity_id,)
                    ).fetchall()
                    entity['notes'] = [dict(n) for n in notes]
                except Exception:
                    entity['notes'] = []
                # Voice context from transcript chunks
                try:
                    voice_ctx_rows = conn.execute('''
                        SELECT tc.chunk_text, tc.chunk_type
                        FROM transcript_chunks tc
                        JOIN chunk_entity_links cel ON tc.id = cel.chunk_id
                        WHERE cel.entity_name = ?
                        AND tc.chunk_type != 'raw_speech'
                        ORDER BY cel.relevance DESC
                        LIMIT 8
                    ''', (entity.get('name', ''),)).fetchall()
                    entity['voice_context'] = [{'text': r['chunk_text'][:300], 'type': r['chunk_type']} for r in voice_ctx_rows]
                except Exception:
                    entity['voice_context'] = []
                self._send_json_response(200, entity)
            elif ml_backlinks:
                # Dynamic entity from microlearning annotations
                # Find the entity metadata from the first card that mentions it
                entity_meta = {}
                for ml in ml_rows:
                    entities_data = json.loads(ml['entities'] or '[]')
                    for e in entities_data:
                        if e.get('canonical', '').lower() == eid_lower:
                            entity_meta = e
                            break
                    if entity_meta:
                        break
                self._send_json_response(200, {
                    'entity_id': entity_id,
                    'name': entity_meta.get('name', entity_id.replace('_', ' ').title()),
                    'entity_type': entity_meta.get('type', 'concept'),
                    'description': None,
                    'aliases': [],
                    'curriculum_links': [],
                    'microlearning_backlinks': ml_backlinks,
                })
            else:
                self._send_json_response(404, {'error': 'Entity not found'})
        finally:
            conn.close()

    def _handle_entity_questions(self):
        """POST /entity/questions — generate 3 research questions about an entity."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        entity_id = body.get('entity_id', '').strip()
        entity_name = body.get('entity_name', '').strip()
        entity_type = body.get('entity_type', 'concept')
        description = body.get('description', '')
        if not entity_id or not entity_name:
            self._send_json_response(400, {'error': 'entity_id and entity_name required'})
            return
        try:
            from review_engine import generate_entity_questions
            questions = generate_entity_questions(
                entity_id, entity_name, entity_type, description)
            self._send_json_response(200, {
                'entity_id': entity_id,
                'questions': questions,
            })
        except Exception as e:
            print(f'[entity/questions] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_entity_research(self):
        """POST /entity/research — trigger a rich entity profile microlearning card."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        entity_id = body.get('entity_id', '').strip()
        entity_name = body.get('entity_name', '').strip()
        entity_type = body.get('entity_type', 'concept')
        description = body.get('description', '')
        if not entity_id or not entity_name:
            self._send_json_response(400, {'error': 'entity_id and entity_name required'})
            return
        try:
            from review_engine import create_entity_research
            card_id = create_entity_research(
                entity_id, entity_name, entity_type, description)
            self._send_json_response(202, {
                'card_id': card_id,
                'status': 'processing',
                'entity_id': entity_id,
            })
        except Exception as e:
            print(f'[entity/research] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})

    def _handle_explore_capture(self):
        """POST /explore/capture — voice or text capture, routed to entities + research.

        Accepts either:
          - multipart/form-data with 'audio' file + form fields (entity_id, entity_name, mode, request_id)
          - application/json with {text, entity_id, entity_name, mode}

        Supports idempotent retries via request_id (24h cache, same pattern as voice-elicit).
        Pipeline: transcribe (if audio) → analyze → save notes → trigger research → return results.
        """
        content_type = self.headers.get('Content-Type', '')

        entity_id = None
        entity_name = None
        mode = 'general'
        capture_type = 'analyze'
        input_text = None
        audio_path = None
        request_id = ''

        # Parse request — read body once, buffer for multipart (same as voice-elicit)
        if 'multipart' in content_type.lower():
            length = int(self.headers.get('Content-Length', 0))
            raw_data = self.rfile.read(length)
            try:
                form = self._multipart_parse_bytes(raw_data, content_type)
            except Exception as e:
                self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
                return
            entity_id = form.getvalue('entity_id', None)
            entity_name = form.getvalue('entity_name', None)
            mode = form.getvalue('mode', 'general')
            capture_type = form.getvalue('capture_type', 'analyze')
            request_id = form.getvalue('request_id', '')

            if 'audio' in form:
                capture_id = f'exc_{int(time.time())}'
                audio_path = AUDIO_DIR / f'{capture_id}.m4a'
                audio_path.write_bytes(form['audio'].file.read())
        elif 'application/json' in content_type:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
            entity_id = body.get('entity_id')
            entity_name = body.get('entity_name')
            mode = body.get('mode', 'general')
            capture_type = body.get('capture_type', 'analyze')
            input_text = body.get('text', '').strip()
        else:
            self._send_json_response(400, {'error': 'Expected multipart or JSON'})
            return

        if not audio_path and not input_text:
            self._send_json_response(400, {'error': 'No audio or text provided'})
            return

        # --- Idempotent cache check (24h TTL, same pattern as voice-elicit) ---
        cache_path = None
        if request_id:
            cache_path = EXPLORE_CAPTURE_CACHE_DIR / f'{request_id}.json'
            if cache_path.exists():
                age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
                if age_hours > 24:
                    cache_path.unlink(missing_ok=True)
                else:
                    try:
                        cached = json.loads(cache_path.read_text())
                        print(f'[explore/capture] Cache hit for {request_id}', flush=True)
                        if audio_path:
                            audio_path.unlink(missing_ok=True)
                        self._send_json_response(200, cached)
                        return
                    except Exception:
                        pass  # corrupted cache, re-process

        # --- Transcribe audio ---
        transcript = input_text or ''
        if audio_path:
            try:
                print(f'[explore/capture] Transcribing: {audio_path.stat().st_size} bytes, '
                      f'entity={entity_id}, mode={mode}, request_id={request_id}', flush=True)
                transcript = transcribe_on_server(audio_path)
            except Exception as e:
                print(f'[explore/capture] Transcription failed: {e}', flush=True)
                self._send_json_response(500, {'error': f'Transcription failed: {e}'})
                return
            finally:
                audio_path.unlink(missing_ok=True)

            if not transcript:
                empty_result = {
                    'status': 'completed', 'transcript': '',
                    'notes_saved': 0, 'research_triggered': [], 'entities_detected': [],
                }
                if cache_path:
                    try: cache_path.write_text(json.dumps(empty_result))
                    except Exception: pass
                self._send_json_response(200, empty_result)
                return

        # --- Rich knowledge graph processing via process_voice_capture ---
        from review_engine import process_voice_capture
        from db import get_connection

        # Resolve entity_name from DB if we have entity_id but no name
        if entity_id and not entity_name:
            conn = get_connection(readonly=True)
            row = conn.execute(
                'SELECT name FROM shared_entities WHERE entity_id = ?',
                (entity_id,)
            ).fetchone()
            if row:
                entity_name = row['name']
            conn.close()

        print(f'[explore/capture] Running {"insight save" if capture_type == "insight" else "rich pipeline"}: '
              f'entity={entity_id}, name={entity_name}, mode={mode}, transcript={len(transcript)} chars', flush=True)

        # input_mode records provenance: did this transcript come from a real
        # audio recording (Soniox) or from a text JSON payload (could be an
        # agent/test harness). Surfaces on the calibration page.
        input_mode = 'audio' if audio_path is not None else 'text_json'
        result = process_voice_capture(
            transcript=transcript,
            entity_id=entity_id,
            entity_name=entity_name,
            mode=mode,
            capture_type=capture_type,
            input_mode=input_mode,
        )

        # Ensure backward-compatible fields for client
        result.setdefault('notes_saved', result.get('items_created', 0) + result.get('items_updated', 0))
        result.setdefault('research_triggered', [
            {'card_id': m.get('id', ''), 'query': m.get('query', '')}
            for m in result.get('microlearning_triggered', [])
        ])
        result.setdefault('entities_detected', result.get('entities_mentioned', []))

        if cache_path:
            try:
                cache_path.write_text(json.dumps(result))
            except Exception:
                pass

        # --- Send response (handle mobile connection drops) ---
        try:
            self._send_json_response(200, result)
        except (ConnectionResetError, BrokenPipeError):
            if cache_path:
                print(f'[explore/capture] Client disconnected but result cached as {request_id}', flush=True)
            else:
                print(f'[explore/capture] Client disconnected, result lost (no request_id)', flush=True)

    def _handle_entity_notes_save(self):
        """POST /entity/notes — save a user note about an entity."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        entity_id = body.get('entity_id', '').strip()
        note = body.get('note', '').strip()
        if not entity_id or not note:
            self._send_json_response(400, {'error': 'entity_id and note required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            now_ms = int(time.time() * 1000)
            conn.execute(
                'INSERT INTO entity_notes (entity_id, note, created_at) VALUES (?, ?, ?)',
                (entity_id, note, now_ms))
            conn.commit()
            self._send_json_response(201, {
                'status': 'saved', 'entity_id': entity_id, 'created_at': now_ms,
            })
        except Exception as e:
            print(f'[entity/notes] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_entity_tap(self):
        """POST /entity/tap — record entity tap and auto-schedule review."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        entity_id = body.get('entity_id')
        action = body.get('action', 'tap')  # tap, unknown, interested, encountered
        if not entity_id:
            self._send_json_response(400, {'error': 'entity_id required'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            link = conn.execute(
                'SELECT domain_id, node_id FROM entity_curriculum_links WHERE entity_id = ? LIMIT 1',
                (entity_id,)
            ).fetchone()
            if not link:
                self._send_json_response(200, {'status': 'no_curriculum_link'})
                return
            domain_id, node_id = link['domain_id'], link['node_id']
            now_ms = int(time.time() * 1000)
            stability = 1.0 if action == 'unknown' else 3.0

            # "encountered" from intro cards — mark knowledge as mentioned if currently unknown
            if action == 'encountered':
                conn.execute('''
                    INSERT INTO knowledge_states (domain_id, node_id, knowledge, interest, confidence, highest_layer, last_updated)
                    VALUES (?, ?, 'mentioned', 0.5, 0.1, '', ?)
                    ON CONFLICT(domain_id, node_id) DO UPDATE SET
                        knowledge = CASE WHEN knowledge = 'unknown' THEN 'mentioned' ELSE knowledge END,
                        last_updated = ?
                ''', (domain_id, node_id, now_ms, now_ms))
                conn.commit()
                self._send_json_response(200, {
                    'status': 'encountered', 'entity_id': entity_id,
                })
                return

            # Create knowledge_item for review scheduling if missing
            item_id = f"{domain_id}:{node_id}"
            existing = conn.execute(
                'SELECT id FROM knowledge_items WHERE id = ?', (item_id,)
            ).fetchone()
            if not existing:
                node = conn.execute(
                    'SELECT title, description FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
                    (node_id, domain_id)
                ).fetchone()
                source = {
                    'book_id': None, 'chapter_number': None,
                    'chapter_title': f'Entity tap: {entity_id}',
                    'source_text': (node['description'] if node else '')[:400],
                    'lens': 'SIGNIFICANCE', 'temporal_hook': '', 'added_at': now_ms,
                }
                try:
                    conn.execute('''
                        INSERT INTO knowledge_items
                        (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                         sources, question_history, created_at)
                        VALUES (?,?,?,?,?,?,?,?)
                    ''', (item_id, node_id, domain_id, stability,
                          now_ms + int(stability * 24 * 3600 * 1000),
                          json.dumps([source]), '[]', now_ms))
                except Exception:
                    pass

            # "interested" — generate exploration prompts
            if action == 'interested':
                # Boost interest + schedule, then generate exploration in background
                conn.execute('''
                    INSERT INTO knowledge_states (domain_id, node_id, knowledge, interest, confidence, highest_layer, last_updated)
                    VALUES (?, ?, 'unknown', 0.9, 0.0, '', ?)
                    ON CONFLICT(domain_id, node_id) DO UPDATE SET
                        interest = MAX(interest, 0.9),
                        last_updated = ?
                ''', (domain_id, node_id, now_ms, now_ms))
                conn.commit()

                # Generate entity exploration prompts
                from review_engine import create_entity_exploration_items
                entity = conn.execute(
                    'SELECT entity_id, name, description, entity_type FROM shared_entities WHERE entity_id = ?',
                    (entity_id,)
                ).fetchone()
                if entity:
                    created = create_entity_exploration_items(
                        dict(entity), domain_id, node_id, conn
                    )
                    self._send_json_response(200, {
                        'status': 'exploration_queued',
                        'entity_id': entity_id,
                        'prompts_created': len(created),
                        'prompts': created,
                    })
                else:
                    self._send_json_response(200, {
                        'status': 'scheduled', 'entity_id': entity_id,
                    })
                return

            # Default tap/unknown — boost interest in knowledge_states
            conn.execute('''
                INSERT INTO knowledge_states (domain_id, node_id, knowledge, interest, confidence, highest_layer, last_updated)
                VALUES (?, ?, 'unknown', 0.8, 0.0, '', ?)
                ON CONFLICT(domain_id, node_id) DO UPDATE SET
                    interest = MAX(interest, 0.8),
                    last_updated = ?
            ''', (domain_id, node_id, now_ms, now_ms))
            conn.commit()
            self._send_json_response(200, {
                'status': 'scheduled', 'entity_id': entity_id,
                'domain_id': domain_id, 'node_id': node_id,
                'stability_days': stability,
            })
        except Exception as e:
            print(f'[entity/tap] Error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    # --------------------------------------------------------------------
    # Wikidata entity review (PR 3)
    #
    # These handlers surface the `entity_resolutions` audit table written by
    # scripts/backfill_wikidata.py and (later) process_voice_capture. They
    # are the trustability surface promised in the entity-resolution plan:
    # every ambiguous / no_match / merge-candidate resolution is queued here
    # for user triage.
    # --------------------------------------------------------------------

    def _handle_admin_suggested_cards(self):
        """GET /admin/suggested-cards — JSON list of voice-detected card suggestions."""
        from db import get_connection
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        status_filter = params.get('status', ['pending'])[0]

        conn = get_connection(readonly=True)
        query = "SELECT * FROM suggested_cards"
        args = []
        if status_filter != 'all':
            query += " WHERE status = ?"
            args.append(status_filter)
        query += " ORDER BY created_at DESC LIMIT 100"

        rows = conn.execute(query, args).fetchall()
        conn.close()

        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'card_type': r['card_type'],
                'source_transcript_ids': json.loads(r['source_transcript_ids']) if r['source_transcript_ids'] else [],
                'entities': json.loads(r['entities']) if r['entities'] else [],
                'domain_ids': json.loads(r['domain_ids']) if r['domain_ids'] else [],
                'rationale': r['rationale'],
                'status': r['status'],
                'created_at': r['created_at'],
            })

        return self._send_json_response(200, {'suggestions': result, 'count': len(result)})

    def _handle_admin_suggested_cards_update(self):
        """POST /admin/suggested-cards/approve or /reject — update suggestion status."""
        body = self._read_json_body()
        if body is None:
            return
        suggestion_id = body.get('id')
        if not suggestion_id:
            return self._send_json_response(400, {'error': 'Missing id'})

        new_status = 'approved' if '/approve' in self.path else 'rejected'

        from db import get_connection
        conn = get_connection()
        try:
            row = conn.execute('SELECT id, status FROM suggested_cards WHERE id = ?',
                               (suggestion_id,)).fetchone()
            if not row:
                return self._send_json_response(404, {'error': f'Suggestion {suggestion_id} not found'})

            conn.execute('UPDATE suggested_cards SET status = ? WHERE id = ?',
                         (new_status, suggestion_id))
            conn.commit()
            print(f'[suggested-cards] {suggestion_id}: {row["status"]} → {new_status}', flush=True)
            return self._send_json_response(200, {
                'id': suggestion_id, 'status': new_status,
                'message': f'Suggestion {new_status}',
            })
        except Exception as e:
            print(f'[suggested-cards] Error: {e}', flush=True)
            return self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_admin_entity_queue_data(self):
        """GET /admin/entity-queue-data — JSON list of resolutions needing review."""
        from db import get_connection
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        status_filter = params.get('status', ['needs_review,ambiguous,no_match'])[0]
        statuses = [s.strip() for s in status_filter.split(',') if s.strip()]
        limit = int(params.get('limit', ['200'])[0])

        conn = get_connection(readonly=True)
        try:
            placeholders = ','.join(['?'] * len(statuses))
            # Only the LATEST (non-superseded) resolution per entity. This
            # dedups any accidental re-runs of the backfill, and once PR 4's
            # LLM disambiguation is wired up, we'll only surface the most
            # recent verdict for a given entity.
            rows = conn.execute(
                f"""
                SELECT er.id, er.entity_id, er.mention_text, er.context_excerpt,
                       er.type_hint, er.status, er.chosen_qid, er.confidence,
                       er.candidate_qids, er.reasoning, er.created_at,
                       se.name AS entity_name, se.description AS entity_description,
                       se.nexus_score
                FROM entity_resolutions er
                LEFT JOIN shared_entities se ON se.entity_id = er.entity_id
                JOIN (
                    SELECT entity_id, MAX(created_at) AS latest
                    FROM entity_resolutions
                    WHERE superseded_by IS NULL AND entity_id IS NOT NULL
                    GROUP BY entity_id
                ) latest ON latest.entity_id = er.entity_id AND latest.latest = er.created_at
                WHERE er.status IN ({placeholders})
                  AND er.superseded_by IS NULL
                ORDER BY COALESCE(se.nexus_score, 0) DESC, er.confidence DESC
                LIMIT ?
                """,
                (*statuses, limit),
            ).fetchall()
            items = []
            for r in rows:
                row = dict(r)
                try:
                    row['candidates'] = json.loads(row.get('candidate_qids') or '[]')
                except (json.JSONDecodeError, TypeError):
                    row['candidates'] = []
                row.pop('candidate_qids', None)
                items.append(row)

            # Summary counts.
            counts = {}
            for s, n in conn.execute(
                "SELECT status, COUNT(*) FROM entity_resolutions "
                "WHERE superseded_by IS NULL GROUP BY status"
            ).fetchall():
                counts[s] = n
            self._send_json_response(200, {'items': items, 'counts': counts})
        finally:
            conn.close()

    def _handle_admin_entity_detail(self):
        """GET /admin/entity/<qid> — consolidated entity view for a QID."""
        qid = self.path.split('/admin/entity/')[-1].split('?')[0].strip()
        if not qid.startswith('Q'):
            self._send_json_response(400, {'error': 'qid must look like Q12345'})
            return
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            # All mentions resolved (or proposed) to this QID.
            resolutions = conn.execute(
                """
                SELECT id, entity_id, mention_text, status, confidence,
                       reasoning, created_at, superseded_by, capture_id
                FROM entity_resolutions
                WHERE chosen_qid = ?
                ORDER BY created_at DESC
                """,
                (qid,),
            ).fetchall()
            # The committed shared_entity (if any).
            committed = conn.execute(
                "SELECT entity_id, name, description, entity_type, nexus_score "
                "FROM shared_entities WHERE wikidata_qid = ?",
                (qid,),
            ).fetchone()
            # External IDs.
            ext_ids = []
            if committed:
                ext_ids = conn.execute(
                    "SELECT property_id, value, source FROM entity_external_ids "
                    "WHERE entity_id = ?",
                    (committed['entity_id'],),
                ).fetchall()
            # Curriculum links (if committed).
            links = []
            if committed:
                links = conn.execute(
                    """
                    SELECT ecl.domain_id, ecl.node_id, ecl.lens_title,
                           cn.title AS node_title
                    FROM entity_curriculum_links ecl
                    LEFT JOIN curriculum_nodes cn
                        ON cn.id = ecl.node_id AND cn.domain_id = ecl.domain_id
                    WHERE ecl.entity_id = ?
                    """,
                    (committed['entity_id'],),
                ).fetchall()
            self._send_json_response(200, {
                'qid': qid,
                'committed': dict(committed) if committed else None,
                'external_ids': [dict(x) for x in ext_ids],
                'curriculum_links': [dict(x) for x in links],
                'resolutions': [dict(x) for x in resolutions],
            })
        finally:
            conn.close()

    def _handle_admin_entity_resolve(self):
        """POST /admin/entity/resolve — manually commit a QID for an entity.

        Body: {entity_id, chosen_qid, source_resolution_id?, note?}.

        Writes a new entity_resolutions row with resolver_model='manual' +
        status='resolved', supersedes any prior resolution for the same
        entity_id, updates shared_entities.wikidata_qid.
        """
        body = self._read_json_body()
        if body is None:
            return
        entity_id = body.get('entity_id')
        chosen_qid = body.get('chosen_qid')
        source_rid = body.get('source_resolution_id')
        note = body.get('note') or ''
        if not entity_id or not chosen_qid:
            self._send_json_response(400, {'error': 'entity_id and chosen_qid required'})
            return
        if not chosen_qid.startswith('Q'):
            self._send_json_response(400, {'error': 'chosen_qid must look like Q12345'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            # Conflict: another entity already owns this QID.
            conflict = conn.execute(
                "SELECT entity_id FROM shared_entities "
                "WHERE wikidata_qid = ? AND entity_id != ?",
                (chosen_qid, entity_id),
            ).fetchone()
            if conflict:
                self._send_json_response(409, {
                    'error': 'qid already owned',
                    'owner_entity_id': conflict['entity_id'],
                    'hint': 'Merge entities via hippocampus.cascade before re-assigning.',
                })
                return

            rid = f"er_{uuid.uuid4().hex[:12]}"
            now_ts = int(time.time())
            reasoning = f"Manual resolution by admin. {note}".strip()

            conn.execute(
                """
                INSERT INTO entity_resolutions (
                    id, entity_id, capture_id, mention_text, context_excerpt,
                    type_hint, candidate_qids, chosen_qid, confidence, status,
                    resolver_model, reasoning, cost_usd, created_at
                )
                SELECT ?, ?, 'admin:manual', se.name, se.description, se.entity_type,
                       '[]', ?, 1.0, 'resolved', 'manual', ?, 0, ?
                FROM shared_entities se WHERE se.entity_id = ?
                """,
                (rid, entity_id, chosen_qid, reasoning, now_ts, entity_id),
            )

            # Supersede prior (still-active) resolutions for this entity.
            conn.execute(
                "UPDATE entity_resolutions SET superseded_by = ? "
                "WHERE entity_id = ? AND id != ? AND superseded_by IS NULL",
                (rid, entity_id, rid),
            )
            # Also mark the source resolution if provided.
            if source_rid:
                conn.execute(
                    "UPDATE entity_resolutions SET superseded_by = ? WHERE id = ?",
                    (rid, source_rid),
                )

            conn.execute(
                "UPDATE shared_entities SET wikidata_qid = ? WHERE entity_id = ?",
                (chosen_qid, entity_id),
            )
            conn.commit()
            self._send_json_response(200, {
                'ok': True,
                'resolution_id': rid,
                'entity_id': entity_id,
                'qid': chosen_qid,
            })
        except Exception as e:
            print(f'[admin/entity/resolve] error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_admin_entity_merge(self):
        """POST /admin/entity/merge — merge a duplicate entity into a canonical one.

        Body: {canonical, duplicate, qid}.

        Re-parents entity_curriculum_links + entity_external_ids + entity_notes
        + entity_resolutions from `duplicate` to `canonical`, handling
        composite-PK collisions via INSERT OR IGNORE. Deletes the duplicate
        shared_entities row. Writes a merge audit row on the canonical side
        and appends a line to the JSONL audit log.

        Safety: pre-check that `canonical` already owns `qid` and `duplicate`
        has `wikidata_qid IS NULL`. Returns 409 on safety failure, 200 with
        a summary on success.
        """
        body = self._read_json_body()
        if body is None:
            return
        canonical = body.get('canonical')
        duplicate = body.get('duplicate')
        qid = body.get('qid')
        if not canonical or not duplicate or not qid:
            self._send_json_response(400, {'error': 'canonical, duplicate, qid required'})
            return
        if canonical == duplicate:
            self._send_json_response(400, {'error': 'canonical and duplicate must differ'})
            return
        if not qid.startswith('Q'):
            self._send_json_response(400, {'error': 'qid must look like Q12345'})
            return

        # Import the merge helper lazily to avoid adding limbic deps to the
        # server's import path unless someone actually hits this endpoint.
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from merge_entity_dupes import merge_pair, find_dedup_pairs  # noqa: E402

        from db import get_connection
        conn = get_connection()
        try:
            # Sanity: the pair must be in the active dedup set.
            pairs = find_dedup_pairs(conn)
            match = next(
                (p for p in pairs
                 if p['canonical'] == canonical
                 and p['duplicate'] == duplicate
                 and p['qid'] == qid),
                None,
            )
            if match is None:
                self._send_json_response(409, {
                    'error': 'pair not in active dedup queue',
                    'hint': 'canonical must own the qid AND duplicate must have wikidata_qid=NULL',
                })
                return

            # Append the merge to the standard audit log path.
            db_dir = Path(os.environ.get('PETRARCA_DB_PATH',
                                         '/opt/petrarca/data/petrarca.db')).parent
            audit_path = db_dir / 'merge_audit.jsonl'
            with audit_path.open('a') as audit_log:
                summary = merge_pair(
                    conn,
                    canonical=canonical,
                    duplicate=duplicate,
                    qid=qid,
                    resolution_id=match['resolution_id'],
                    dry_run=False,
                    audit_log=audit_log,
                )
            self._send_json_response(200, {
                'ok': True,
                'canonical': canonical,
                'duplicate': duplicate,
                'qid': qid,
                'moves': summary['moves'],
                'dropped_dupes': summary['dropped_dupes'],
                'merge_resolution_id': summary.get('merge_resolution_id'),
            })
        except Exception as e:
            print(f'[admin/entity/merge] error: {e}', flush=True)
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_process_kindle(self):
        """POST /book/process-kindle — trigger Kindle book processing."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length:
            try:
                body = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, ValueError):
                pass

        max_books = body.get('max', 10)
        print(f'[process-kindle] Processing up to {max_books} books', flush=True)

        def _process():
            try:
                from process_kindle_books import process_all
                process_all(do_research=True, max_books=max_books)
            except Exception as e:
                print(f'[process-kindle] Error: {e}', flush=True)
                import traceback; traceback.print_exc()

        thread = threading.Thread(target=_process, daemon=True)
        thread.start()
        self._send_json_response(202, {'status': 'processing', 'max_books': max_books})

    def _handle_ingest_book(self):
        if INGEST_TOKEN:
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self._send_json_response(401, {'error': 'Invalid or missing auth token'})
                return

        body = self._read_json_body()
        if body is None:
            return
        book_path = body.get('path', '').strip()
        if not book_path:
            self._send_json_response(400, {'error': 'Missing required field: path'})
            return

        chapter = body.get('chapter')
        request_id = f'book_{int(time.time())}_{hash(book_path) % 10000:04d}'

        thread = threading.Thread(
            target=run_ingest_book,
            args=(book_path, chapter, request_id),
            daemon=True,
        )
        thread.start()

        print(f'[book-ingest] Queued: {book_path} (chapter={chapter})', flush=True)

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': request_id, 'status': 'processing', 'path': book_path}).encode())

    def _handle_twitter_cookies(self):
        """Update twikit cookies via API. Expects {auth_token, ct0}."""
        if INGEST_TOKEN:
            token = self.headers.get('X-Petrarca-Token', '')
            if token != INGEST_TOKEN:
                self._send_json_response(401, {'error': 'Invalid auth token'})
                return

        body = self._read_json_body()
        if body is None:
            return

        auth_token = body.get('auth_token', '').strip()
        ct0 = body.get('ct0', '').strip()

        if not auth_token or not ct0:
            self._send_json_response(400, {'error': 'Both auth_token and ct0 are required'})
            return

        TWIKIT_COOKIES_DIR.mkdir(parents=True, exist_ok=True)
        cookies = {'auth_token': auth_token, 'ct0': ct0}

        # twikit's save_cookies format is a dict of cookie dicts
        # but the simplest approach: use twikit Client to set and save
        try:
            sys.path.insert(0, str(SCRIPTS_DIR))
            from twikit import Client
            client = Client('en-US')
            client.set_cookies(cookies)
            client.save_cookies(str(TWIKIT_COOKIES_PATH))
            print(f'[twitter] Cookies updated via API', flush=True)
            self._send_json_response(200, {'status': 'ok', 'message': 'Cookies saved'})
        except Exception as e:
            self._send_json_response(500, {'error': f'Failed to save cookies: {e}'})

    # ── Curriculum endpoints ────────────────────────────────

    def _handle_curriculum_generate(self):
        """POST /curriculum/generate — Generate a curriculum for a domain (background).

        Accepts {domain, depth?, background?}.
        If background=true (default), returns immediately with a job_id and generates
        asynchronously. Poll GET /curriculum/generate/status?id=<job_id>.
        If background=false, blocks until complete (for local scripts).
        """
        body = self._read_json_body()
        if body is None:
            return
        domain = body.get('domain')
        if not domain:
            self._send_json_response(400, {'error': 'Missing domain field'})
            return
        depth = body.get('depth', 'introductory')
        run_background = body.get('background', True)

        if not run_background:
            print(f"[curriculum] Generating curriculum (sync): {domain}", flush=True)
            result = generate_curriculum(domain, depth)
            if result:
                self._send_json_response(200, result)
            else:
                self._send_json_response(500, {'error': 'Failed to generate curriculum'})
            return

        import uuid as _uuid
        job_id = _uuid.uuid4().hex[:12]
        _curriculum_jobs[job_id] = {'status': 'running', 'domain': domain, 'started_at': time.time()}

        def _gen():
            try:
                result = generate_curriculum(domain, depth)
                if result:
                    domain_id = result['id']
                    _curriculum_jobs[job_id] = {
                        'status': 'tagging', 'domain': domain,
                        'domain_id': domain_id, 'node_count': result['node_count'],
                    }
                    print(f"[curriculum] Generated '{domain}': {result['node_count']} nodes — tagging entities", flush=True)
                    tagged = tag_curriculum_entities(domain_id)
                    build_entity_index()

                    # Bootstrap SQLite entities (shared_entities + entity_curriculum_links)
                    _curriculum_jobs[job_id]['status'] = 'bootstrapping_entities'
                    try:
                        from claude_llm import call_claude
                        curriculum = load_curriculum(domain_id)
                        if curriculum:
                            prompt = _entity_extraction_prompt(curriculum)
                            raw = call_claude(prompt, timeout=300, model='sonnet')
                            entities = _entity_parse_json(raw) if raw else None
                            if entities:
                                from db import get_connection as _get_conn
                                conn = _get_conn()
                                created, links = _entity_insert(entities, domain_id, conn)
                                conn.commit()
                                conn.close()
                                print(f"[curriculum] Bootstrapped SQLite entities for '{domain}': {created} entities, {links} links", flush=True)
                    except Exception as ent_err:
                        print(f"[curriculum] Entity bootstrap failed (non-fatal): {ent_err}", flush=True)

                    _curriculum_jobs[job_id] = {
                        'status': 'done', 'domain': domain,
                        'domain_id': domain_id, 'node_count': result['node_count'],
                        'tagged': tagged,
                    }
                    print(f"[curriculum] Entity index rebuilt after '{domain}'", flush=True)
                else:
                    _curriculum_jobs[job_id] = {'status': 'failed', 'domain': domain}
            except Exception as e:
                _curriculum_jobs[job_id] = {'status': 'failed', 'domain': domain, 'error': str(e)}

        import threading as _threading
        _threading.Thread(target=_gen, daemon=True).start()
        self._send_json_response(202, {'job_id': job_id, 'status': 'running', 'domain': domain})

    def _handle_curriculum_map_book(self):
        """POST /curriculum/map-book — Map a book against a curriculum."""
        body = self._read_json_body()
        if body is None:
            return
        book_id = body.get('book_id')
        domain_id = body.get('domain_id')
        if not book_id or not domain_id:
            self._send_json_response(400, {'error': 'Missing book_id or domain_id'})
            return
        mappings = map_book_to_curriculum(book_id, domain_id)
        if mappings is not None:
            self._send_json_response(200, {'mappings': mappings, 'count': len(mappings)})
        else:
            self._send_json_response(500, {'error': 'Failed to map book'})

    def _handle_elicit_start(self):
        """POST /curriculum/elicit/start — Start a 20Q elicitation session."""
        body = self._read_json_body()
        if body is None:
            return
        domain_id = body.get('domain_id')
        if not domain_id:
            self._send_json_response(400, {'error': 'Missing domain_id'})
            return
        result = start_elicitation(domain_id)
        if result:
            self._send_json_response(200, result)
        else:
            self._send_json_response(404, {'error': 'Curriculum not found'})

    def _handle_elicit_respond(self):
        """POST /curriculum/elicit/respond — Respond to a 20Q question."""
        body = self._read_json_body()
        if body is None:
            return
        session_id = body.get('session_id')
        if not session_id:
            self._send_json_response(400, {'error': 'Missing session_id'})
            return
        result = continue_elicitation(session_id, body)
        if result:
            self._send_json_response(200, result)
        else:
            self._send_json_response(404, {'error': 'Session not found'})

    def _handle_knowledge_import_assessment(self):
        """POST /curriculum/knowledge/import-assessment — Batch import from HTML assessment UI."""
        body = self._read_json_body()
        if body is None:
            return
        domain_id = body.get('domain_id')
        answers = body.get('answers')
        if not domain_id or not answers:
            self._send_json_response(400, {'error': 'Missing domain_id or answers'})
            return
        result = import_assessment_answers(domain_id, answers)
        print(f"[curriculum] Imported {result['imported']} answers for {domain_id}: {result['by_level']}", flush=True)
        self._send_json_response(200, result)

    def _handle_knowledge_update(self):
        """POST /curriculum/knowledge/update — Manually update a knowledge state."""
        body = self._read_json_body()
        if body is None:
            return
        domain_id = body.get('domain_id')
        node_id = body.get('node_id')
        if not domain_id or not node_id:
            self._send_json_response(400, {'error': 'Missing domain_id or node_id'})
            return
        state = update_knowledge(
            domain_id, node_id,
            knowledge=body.get('knowledge'),
            interest=body.get('interest'),
            confidence=body.get('confidence'),
            source=body.get('source'),
        )
        self._send_json_response(200, {'state': state})

    # ── Review handlers ────────────────────────────────────────────────────────

    def _handle_review_book_complete(self):
        """POST /review/book-complete — map finished book to all relevant curricula."""
        body = self._read_json_body()
        if body is None:
            return
        book_id = body.get('book_id')
        if not book_id:
            self._send_json_response(400, {'error': 'Missing book_id'})
            return

        from db import get_connection
        from review_engine import map_whole_book
        conn = get_connection()
        try:
            result = map_whole_book(book_id, conn)
            if 'error' in result:
                self._send_json_response(404, result)
                return
            from review_engine import get_review_stats
            stats = get_review_stats(conn)
            result['due_today'] = stats['due_today']
            self._send_json_response(200, result)
        finally:
            conn.close()

    def _handle_review_chapter_complete(self):
        """POST /review/chapter-complete — map chapter to curriculum nodes, create review items."""
        body = self._read_json_body()
        if body is None:
            return
        book_id = body.get('book_id')
        chapter_number = body.get('chapter_number')
        chapter_title = body.get('chapter_title', '')
        if not book_id or chapter_number is None:
            self._send_json_response(400, {'error': 'Missing book_id or chapter_number'})
            return

        from db import get_connection
        conn = get_connection()
        try:
            row = conn.execute('SELECT title, topics FROM physical_books WHERE id=?', (book_id,)).fetchone()
            if not row:
                self._send_json_response(404, {'error': 'Book not found'})
                return
            book_title = row['title']
            book_topics = json.loads(row['topics'] or '[]')

            result = create_review_items_for_chapter(
                book_id, book_title, book_topics,
                chapter_number, chapter_title, conn,
            )
            stats = get_review_stats(conn)
            result['due_today'] = stats['due_today']
            self._send_json_response(200, result)
        finally:
            conn.close()

    def _handle_chapter_context(self):
        """POST /review/chapter-context — curriculum context for a chapter (preview or review)."""
        body = self._read_json_body()
        if body is None:
            return
        book_id = body.get('book_id', '')
        chapter_number = body.get('chapter_number', 0)
        chapter_title = body.get('chapter_title', '')
        mode = body.get('mode', 'review')

        if not book_id or not chapter_number:
            self._send_json_response(400, {'error': 'Missing book_id or chapter_number'})
            return

        from db import get_connection
        from review_engine import detect_curriculum, _generate_temporal_hook
        from curriculum_db import load_curriculum

        conn = get_connection(readonly=True)
        try:
            row = conn.execute('SELECT title, topics FROM physical_books WHERE id=?', (book_id,)).fetchone()
            if not row:
                self._send_json_response(404, {'error': 'Book not found'})
                return
            book_title = row['title']
            book_topics = json.loads(row['topics'] or '[]')

            domain_id = detect_curriculum(book_title, book_topics)
            curriculum = load_curriculum(domain_id, conn)
            if not curriculum or not curriculum.get('nodes'):
                self._send_json_response(200, {
                    'nodes': [], 'mode': mode,
                    'message': 'No curriculum mapping available for this chapter',
                })
                return

            nodes_by_id = {n['id']: n for n in curriculum.get('nodes', [])}

            # Get knowledge states for all nodes in this curriculum
            knowledge_rows = conn.execute(
                'SELECT node_id, knowledge, confidence FROM knowledge_states WHERE domain_id = ?',
                (domain_id,),
            ).fetchall()
            knowledge_map = {r['node_id']: {'knowledge': r['knowledge'], 'confidence': r['confidence']} for r in knowledge_rows}

            # Map chapter to nodes via LLM (same logic as chapter-complete)
            from review_engine import map_chapter_to_nodes
            mappings = map_chapter_to_nodes(book_id, book_title, book_topics, chapter_number, chapter_title)
            if not mappings:
                self._send_json_response(200, {
                    'nodes': [], 'mode': mode, 'domain_id': domain_id,
                    'message': 'No curriculum nodes mapped to this chapter',
                })
                return

            enriched_nodes = []
            for m in mappings:
                node_id = m.get('node_id', '')
                node = nodes_by_id.get(node_id, {})
                state = knowledge_map.get(node_id, {'knowledge': 'unknown', 'confidence': 0.0})

                enriched = {
                    'node_id': node_id,
                    'node_title': m.get('node_title', node.get('title', '')),
                    'description': node.get('description', ''),
                    'knowledge': state['knowledge'],
                    'confidence': state['confidence'],
                    'source_text': m.get('source_text', ''),
                    'lens': m.get('lens', ''),
                }

                if mode == 'preview':
                    prereqs = node.get('prerequisites', [])
                    shaky_prereqs = []
                    for pid in prereqs:
                        pstate = knowledge_map.get(pid, {'knowledge': 'unknown', 'confidence': 0.0})
                        if pstate['knowledge'] in ('unknown', 'mentioned') or pstate['confidence'] < 0.4:
                            pnode = nodes_by_id.get(pid, {})
                            shaky_prereqs.append({
                                'node_id': pid,
                                'node_title': pnode.get('title', pid),
                                'description': pnode.get('description', ''),
                                'knowledge': pstate['knowledge'],
                            })
                    enriched['shaky_prerequisites'] = shaky_prereqs
                    enriched['is_new'] = state['knowledge'] in ('unknown', 'mentioned')

                if mode == 'review' and node.get('date_start') is not None:
                    try:
                        hook = _generate_temporal_hook(node, domain_id, conn)
                        enriched['temporal_hook'] = hook
                    except Exception:
                        enriched['temporal_hook'] = ''

                enriched_nodes.append(enriched)

            # Generate a self-assessment question for review mode
            assessment_question = None
            if mode == 'review' and enriched_nodes:
                target = next(
                    (n for n in enriched_nodes if n.get('is_new', n['knowledge'] == 'unknown')),
                    enriched_nodes[0],
                )
                try:
                    from claude_llm import call_claude
                    q_prompt = (
                        f"Generate one short question (6-12 words) testing understanding of: {target['node_title']}\n"
                        f"Definition: {target['description'][:200]}\n"
                        f"Start with What/Why/How. Output just the question text, nothing else."
                    )
                    q_text = call_claude(q_prompt, timeout=60, model='sonnet')
                    if q_text:
                        assessment_question = {
                            'node_id': target['node_id'],
                            'node_title': target['node_title'],
                            'question': q_text.strip().strip('"'),
                        }
                except Exception:
                    pass

            known_count = sum(1 for n in enriched_nodes if n['knowledge'] in ('engaged', 'anchored'))
            new_count = sum(1 for n in enriched_nodes if n['knowledge'] in ('unknown', 'mentioned'))

            result = {
                'mode': mode,
                'domain_id': domain_id,
                'chapter_number': chapter_number,
                'chapter_title': chapter_title,
                'nodes': enriched_nodes,
                'assessment_question': assessment_question,
                'summary': {
                    'total': len(enriched_nodes),
                    'known': known_count,
                    'new': new_count,
                },
            }
            self._send_json_response(200, result)
        finally:
            conn.close()

    def _handle_review_generate_question(self):
        """POST /review/generate-question — personalized question for a review item."""
        body = self._read_json_body()
        if body is None:
            return
        item_id = body.get('item_id')
        if not item_id:
            self._send_json_response(400, {'error': 'Missing item_id'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            result = generate_question(item_id, conn)
            self._send_json_response(200, result)
        finally:
            conn.close()

    def _handle_review_answer(self):
        """POST /review/answer — record answer score, update FSRS."""
        body = self._read_json_body()
        if body is None:
            return
        item_id = body.get('item_id')
        score = body.get('score')
        if not item_id or score not in ('knew', 'partly', 'missed'):
            self._send_json_response(400, {'error': 'Missing item_id or invalid score'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            result = record_answer(item_id, score, conn)
            # Dual-layer interaction logging
            from server_log import log_interaction
            log_interaction('review_answer', item_id=item_id, score=score,
                            card_type=body.get('card_type'),
                            new_stability=result.get('new_stability_days'),
                            next_due=result.get('next_due_at'))
            self._send_json_response(200, result)
        finally:
            conn.close()

    def _handle_structural_grade(self):
        """POST /structural/grade — grade an aspect card's positions with FSRS."""
        body = self._read_json_body()
        if body is None:
            return
        card_id = body.get('card_id')
        results = body.get('results', [])
        if not card_id or not results:
            self._send_json_response(400, {'error': 'card_id and results required'})
            return
        from db import get_connection
        from review_engine import record_structural_answer
        conn = get_connection()
        try:
            resp = record_structural_answer(card_id, results, conn)
            from server_log import log_interaction
            log_interaction('structural_grade', card_id=card_id,
                            knew=resp.get('knew'), total=resp.get('total'))
            self._send_json_response(200, resp)
        except Exception as e:
            print(f'[structural/grade] Error: {e}', flush=True)
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_log_events(self):
        """POST /log/events — receive client-side interaction events.

        Replaces the broken separate log_server.py on port 8091.
        Accepts JSONL body (one JSON object per line).
        """
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 1_000_000:
            self.send_response(413)
            self.end_headers()
            return
        body = self.rfile.read(content_length).decode('utf-8', errors='replace')
        from server_log import log_client_events
        lines_written = log_client_events(body)
        self._send_json_response(200, {'ok': True, 'lines': lines_written})

    def _handle_review_explore(self):
        """POST /review/explore — generate follow-up exploration items."""
        body = self._read_json_body()
        if body is None:
            return
        item_id = body.get('item_id')
        if not item_id:
            self._send_json_response(400, {'error': 'Missing item_id'})
            return
        from db import get_connection
        conn = get_connection()
        try:
            created = create_exploration_items(item_id, conn)
            self._send_json_response(200, {'items_created': created})
        finally:
            conn.close()

    # ── Defender mode (prototype) ──────────────────────────────────────────
    def _handle_defender_start(self):
        """POST /defender/start — begin a debate session.
        Body: {thesis: str, domain_id?: str, node_id?: str, entity_name?: str}
        """
        body = self._read_json_body()
        if body is None:
            return
        thesis = (body.get('thesis') or '').strip()
        if not thesis:
            self._send_json_response(400, {'error': 'Missing thesis'})
            return
        from db import get_connection
        from defender_engine import start_session
        conn = get_connection()
        try:
            result = start_session(
                thesis=thesis,
                domain_id=body.get('domain_id'),
                node_id=body.get('node_id'),
                entity_name=body.get('entity_name'),
                conn=conn,
            )
            status = 400 if result.get('error') else 200
            self._send_json_response(status, result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_defender_respond(self):
        """POST /defender/respond — submit a defense, get grade + follow-up.
        Body: {session_id: str, response_text: str, objection_index?: int}
        """
        body = self._read_json_body()
        if body is None:
            return
        session_id = (body.get('session_id') or '').strip()
        response_text = (body.get('response_text') or '').strip()
        if not session_id or not response_text:
            self._send_json_response(400, {'error': 'Missing session_id or response_text'})
            return
        objection_index = int(body.get('objection_index') or 0)
        from db import get_connection
        from defender_engine import respond
        conn = get_connection()
        try:
            result = respond(session_id, response_text, objection_index, conn)
            status = 400 if result.get('error') else 200
            self._send_json_response(status, result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_defender_sessions_list(self):
        """GET /defender/sessions — list recent sessions."""
        from db import get_connection
        from defender_engine import list_sessions
        qs = parse_qs(urlparse(self.path).query)
        limit = int(qs.get('limit', ['20'])[0])
        conn = get_connection(readonly=True)
        try:
            sessions = list_sessions(conn, limit=limit)
            self._send_json_response(200, {'sessions': sessions})
        finally:
            conn.close()

    def _handle_defender_session_detail(self, session_id: str):
        """GET /defender/sessions/{id} — full session detail."""
        from db import get_connection
        from defender_engine import get_session
        conn = get_connection(readonly=True)
        try:
            sess = get_session(session_id, conn)
            if not sess:
                self._send_json_response(404, {'error': 'Session not found'})
                return
            self._send_json_response(200, sess)
        finally:
            conn.close()

    def _handle_defender_transcribe(self):
        """POST /defender/transcribe — multipart audio → transcript text.

        Generic transcription endpoint for the defender screen. The client
        records, posts the audio, gets back text, and lets the user edit it
        before submitting via /defender/start or /defender/respond.
        """
        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type:
            self._send_json_response(400, {'error': 'Expected multipart'})
            return
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = self.rfile.read(length)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f'[defender-transcribe] upload drop: {e}', flush=True)
            return
        try:
            fs = self._multipart_parse_bytes(data, content_type)
        except Exception as e:
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return
        audio_field = fs['audio'] if 'audio' in fs else None
        if not audio_field:
            self._send_json_response(400, {'error': 'Missing audio'})
            return
        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as tmp:
            tmp.write(audio_field.file.read())
            audio_path = Path(tmp.name)
        try:
            transcript = transcribe_on_server(audio_path)
            if not transcript or len(transcript.split()) < 2:
                self._send_json_response(422, {'error': 'too_short',
                                               'transcript': transcript or ''})
                return
            self._send_json_response(200, {'transcript': transcript})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            audio_path.unlink(missing_ok=True)

    # ── Commonplace-resurfacing (prototype) ────────────────────────────────
    def _handle_commonplace_resurface(self):
        """POST /commonplace/resurface — find old chunks that match query text.

        JSON body: {query_text: str, min_age_days?: int, threshold?: float,
                    max_results?: int, exclude_transcript_ids?: [str]}
        """
        body = self._read_json_body()
        if body is None:
            return
        query_text = (body.get('query_text') or '').strip()
        if not query_text:
            self._send_json_response(400, {'error': 'Missing query_text'})
            return
        from db import get_connection
        from commonplace_engine import find_resurface, log_event
        conn = get_connection()
        try:
            result = find_resurface(
                query_text=query_text,
                conn=conn,
                min_age_days=int(body.get('min_age_days', 30)),
                sim_threshold=float(body.get('threshold', 0.55)),
                max_results=int(body.get('max_results', 5)),
                exclude_transcript_ids=body.get('exclude_transcript_ids') or [],
            )
            event_id = log_event(query_text, result['echoes'], conn,
                                 query_source=body.get('source', 'manual'))
            result['event_id'] = event_id
            self._send_json_response(200, result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            conn.close()

    def _handle_commonplace_resurface_audio(self):
        """POST /commonplace/resurface-audio — multipart audio → transcribe → resurface.

        Convenience endpoint: lets the client record a thought, get back both
        the transcript AND the matching echoes in one round-trip.
        """
        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type:
            self._send_json_response(400, {'error': 'Expected multipart'})
            return
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = self.rfile.read(length)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f'[commonplace] upload drop: {e}', flush=True)
            return
        try:
            fs = self._multipart_parse_bytes(data, content_type)
        except Exception as e:
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return
        audio_field = fs['audio'] if 'audio' in fs else None
        if not audio_field:
            self._send_json_response(400, {'error': 'Missing audio'})
            return
        min_age_days = int(fs.getvalue('min_age_days', '30'))
        threshold = float(fs.getvalue('threshold', '0.55'))
        max_results = int(fs.getvalue('max_results', '5'))
        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as tmp:
            tmp.write(audio_field.file.read())
            audio_path = Path(tmp.name)
        audio_size = audio_path.stat().st_size
        try:
            transcript = transcribe_on_server(audio_path)
            if not transcript or len(transcript.split()) < 4:
                self._send_json_response(422, {'error': 'too_short',
                                               'transcript': transcript or ''})
                return
            from db import get_connection
            from commonplace_engine import find_resurface, log_event
            conn = get_connection()
            try:
                result = find_resurface(
                    query_text=transcript,
                    conn=conn,
                    min_age_days=min_age_days,
                    sim_threshold=threshold,
                    max_results=max_results,
                )
                event_id = log_event(transcript, result['echoes'], conn,
                                     query_source='audio',
                                     audio_bytes=audio_size)
                result['event_id'] = event_id
                result['transcript'] = transcript
                self._send_json_response(200, result)
            finally:
                conn.close()
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json_response(500, {'error': str(e)})
        finally:
            audio_path.unlink(missing_ok=True)

    def _handle_commonplace_events_list(self):
        """GET /commonplace/events — recent resurfacing events."""
        from db import get_connection
        from commonplace_engine import list_recent_events
        qs = parse_qs(urlparse(self.path).query)
        limit = int(qs.get('limit', ['30'])[0])
        conn = get_connection(readonly=True)
        try:
            events = list_recent_events(conn, limit=limit)
            self._send_json_response(200, {'events': events})
        finally:
            conn.close()

    def _handle_review_voice_memo(self):
        """POST /review/voice-memo — transcribe + extract signals."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type:
            self._send_json_response(400, {'error': 'Expected multipart'})
            return
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        try:
            fs = self._multipart_parse_bytes(data, content_type)
        except Exception as e:
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return
        item_id = fs.getvalue('item_id', '')
        audio_field = fs['audio'] if 'audio' in fs else None
        if not item_id or not audio_field:
            self._send_json_response(400, {'error': 'Missing item_id or audio'})
            return
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as tmp:
            tmp.write(audio_field.file.read())
            audio_path = Path(tmp.name)
        try:
            from db import get_connection
            conn = get_connection()
            try:
                result = process_voice_memo(item_id, audio_path, conn, transcribe_on_server)
                self._send_json_response(200, result)
            finally:
                conn.close()
        finally:
            audio_path.unlink(missing_ok=True)

    def _handle_voice_elicitation(self):
        """POST /review/voice-elicit — voice free-recall elicitation for a curriculum node.

        Accepts optional request_id for idempotent retries. If a result was already
        computed for this request_id, returns it from cache instantly (no re-processing).
        This handles mobile connections dropping during the 40-50s processing time.

        The request_id can be sent as X-Request-ID header (checked before reading body)
        or in the multipart form data. Header is preferred for retries since it allows
        the server to short-circuit without reading the full audio upload.
        """
        # Disk space pre-check — audio temp files + cache need ~10MB headroom
        try:
            st = os.statvfs('/opt/petrarca/data')
            free_mb = (st.f_bavail * st.f_frsize) / (1024 * 1024)
            if free_mb < 50:
                log_server_event('voice_elicit_disk_full', free_mb=round(free_mb, 1))
                print(f'[voice-elicit] DISK LOW: {free_mb:.0f}MB free — uploads may fail', flush=True)
                if free_mb < 10:
                    self._send_json_response(507, {'error': 'Server disk full'})
                    return
        except OSError:
            pass

        # Phase 2: Check header-based request_id BEFORE reading body
        header_request_id = self.headers.get('X-Request-ID', '')
        if header_request_id:
            cache_path = VOICE_ELICIT_CACHE_DIR / f'{header_request_id}.json'
            if cache_path.exists():
                age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
                if age_hours <= 24:
                    try:
                        cached = json.loads(cache_path.read_text())
                        # Return cached result (including validation errors like too_short)
                        if cached.get('captured') or cached.get('missed') or cached.get('feedback_summary'):
                            cache_status = 422 if cached.get('error') else 200
                            print(f'[voice-elicit] Header cache hit for {header_request_id}, skipping body read', flush=True)
                            self._send_json_response(cache_status, cached)
                            return
                        else:
                            print(f'[voice-elicit] Header cache for {header_request_id} is empty, re-processing', flush=True)
                            cache_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                else:
                    cache_path.unlink(missing_ok=True)

        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type:
            self._send_json_response(400, {'error': 'Expected multipart'})
            return
        length = int(self.headers.get('Content-Length', 0))
        # Phase 3: Catch connection drops during upload
        try:
            data = self.rfile.read(length)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            log_server_event('voice_elicit_upload_drop', error=str(e), content_length=length,
                             request_id=header_request_id or 'unknown')
            print(f'[voice-elicit] Client disconnected during upload ({e})', flush=True)
            return
        try:
            fs = self._multipart_parse_bytes(data, content_type)
        except Exception as e:
            self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
            return
        node_id = fs.getvalue('node_id', '')
        domain_id = fs.getvalue('domain_id', '')
        request_id = fs.getvalue('request_id', '') or header_request_id
        audio_field = fs['audio'] if 'audio' in fs else None
        if not node_id or audio_field is None:
            self._send_json_response(400, {'error': 'Missing node_id or audio'})
            return

        # Auto-detect domain_id for chapter/book recalls when not provided
        if not domain_id and (node_id.startswith('chapter:') or node_id.startswith('book:')):
            parts = node_id.split(':')
            book_id = parts[1] if len(parts) > 1 else ''
            if book_id:
                from db import get_connection
                tmp_conn = get_connection(readonly=True)
                try:
                    row = tmp_conn.execute(
                        "SELECT DISTINCT curriculum_domain FROM knowledge_items WHERE sources LIKE ? LIMIT 1",
                        (f'%{book_id}%',)
                    ).fetchone()
                    if row:
                        domain_id = row['curriculum_domain']
                        print(f'[voice-elicit] Auto-detected domain={domain_id} for {node_id}', flush=True)
                finally:
                    tmp_conn.close()
        if not domain_id and not node_id.startswith('chapter:') and not node_id.startswith('book:'):
            self._send_json_response(400, {'error': 'Missing domain_id'})
            return

        # Check cache for idempotent retry (expires after 24h)
        cache_path = None
        if request_id:
            cache_path = VOICE_ELICIT_CACHE_DIR / f'{request_id}.json'
            if cache_path.exists():
                age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
                if age_hours > 24:
                    cache_path.unlink(missing_ok=True)
                else:
                    try:
                        cached = json.loads(cache_path.read_text())
                        if cached.get('captured') or cached.get('missed') or cached.get('feedback_summary'):
                            cache_status = 422 if cached.get('error') else 200
                            print(f'[voice-elicit] Cache hit for {request_id}, returning cached result', flush=True)
                            self._send_json_response(cache_status, cached)
                            return
                        else:
                            print(f'[voice-elicit] Cached result for {request_id} is empty, re-processing', flush=True)
                            cache_path.unlink(missing_ok=True)
                    except Exception:
                        pass  # corrupted cache, re-process

        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as tmp:
                tmp.write(audio_field.file.read())
                audio_path = Path(tmp.name)
        except OSError as e:
            log_server_event('voice_elicit_tmpfile_fail', error=str(e), node_id=node_id, request_id=request_id)
            print(f'[voice-elicit] Failed to write temp file: {e}', flush=True)
            self._send_json_response(507, {'error': 'Server disk full — cannot write audio'})
            return
        audio_size = audio_path.stat().st_size
        result = None
        log_server_event('voice_elicit_start', node_id=node_id, domain_id=domain_id[:30],
                         audio_bytes=audio_size, request_id=request_id)
        try:
            print(f'[voice-elicit] Processing: node={node_id}, domain={domain_id[:30]}, audio={audio_size} bytes', flush=True)
            result = run_voice_elicitation(node_id, domain_id, audio_path, None, transcribe_on_server)
            print(f'[voice-elicit] Result: coverage={result.get("coverage_pct", "?")}%, captured={len(result.get("captured", []))}, ml_triggered={len(result.get("microlearning_triggered", []))}', flush=True)
            log_server_event('voice_elicit_done', node_id=node_id, request_id=request_id,
                             coverage_pct=result.get('coverage_pct'),
                             captured=len(result.get('captured', [])),
                             error=result.get('error'))
            if result.get('error'):
                print(f'[voice-elicit] Error in result: {result["error"]}', flush=True)
        except Exception as e:
            print(f'[voice-elicit] Exception: {e}', flush=True)
            log_server_event('voice_elicit_exception', node_id=node_id, request_id=request_id, error=str(e))
            import traceback; traceback.print_exc()
            result = {'error': str(e)}
        finally:
            audio_path.unlink(missing_ok=True)

        # Cache results before sending (connection may drop)
        # Cache both successful results AND validation errors (too_short, transcription_failed)
        # so retries don't re-upload and re-process the same audio
        VALIDATION_ERRORS = {'too_short', 'Transcription failed'}
        error_val = result.get('error', '') if result else ''
        is_validation_error = error_val in VALIDATION_ERRORS
        is_server_error = bool(error_val) and not is_validation_error

        has_analysis = (result and not is_server_error
                        and (result.get('captured') or result.get('missed') or result.get('feedback_summary')))
        if cache_path and (has_analysis or is_validation_error):
            try:
                cache_path.write_text(json.dumps(result))
            except Exception:
                pass

        # Send response (may fail with ConnectionReset on flaky mobile connections)
        # 200 = success, 422 = validation error (don't retry), 500 = server error (retry)
        try:
            if is_server_error:
                status = 500
            elif is_validation_error:
                status = 422
            else:
                status = 200
            self._send_json_response(status, result)
        except (ConnectionResetError, BrokenPipeError):
            if cache_path and not is_server_error:
                print(f'[voice-elicit] Client disconnected but result cached as {request_id}', flush=True)
            else:
                print(f'[voice-elicit] Client disconnected, result lost (no request_id)', flush=True)

    def _handle_voice_elicit_check(self):
        """GET /review/voice-elicit-check?request_id=X — check if a cached result exists.

        Returns the cached result (200) or 404 if not found. This allows clients
        to check before re-uploading the full audio file on retry.

        DELETE /review/voice-elicit-check?request_id=X — invalidate a cached result.
        Used when the cached result is incomplete/malformed and needs re-processing.
        """
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(self.path).query)
        request_id = params.get('request_id', [''])[0]
        if not request_id:
            self._send_json_response(400, {'error': 'Missing request_id'})
            return
        cache_path = VOICE_ELICIT_CACHE_DIR / f'{request_id}.json'
        if cache_path.exists():
            age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_hours > 24:
                cache_path.unlink(missing_ok=True)
                self._send_json_response(404, {'status': 'expired'})
                return
            try:
                cached = json.loads(cache_path.read_text())
                # Validate the cached result has actual analysis content
                if not (cached.get('captured') or cached.get('missed') or cached.get('feedback_summary')):
                    print(f'[voice-elicit] Cached result for {request_id} is empty, invalidating', flush=True)
                    cache_path.unlink(missing_ok=True)
                    self._send_json_response(404, {'status': 'invalid_cache'})
                    return
                print(f'[voice-elicit] Check cache hit for {request_id}', flush=True)
                self._send_json_response(200, cached)
                return
            except Exception:
                pass
        self._send_json_response(404, {'status': 'not_found'})

    def _handle_sweep_submit(self):
        """POST /knowledge/sweep/submit — submit and score a knowledge sweep.

        Body JSON: {domain_id, phase1_eras: [{era_id, transcript, duration_s}], phase2_transcript?}
        Transcripts come from client-side transcription (Soniox).
        Scoring uses Claude (Opus) — takes 30-60s.
        """
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        domain_id = data.get('domain_id', '')
        phase1_eras = data.get('phase1_eras', [])
        phase2_transcript = data.get('phase2_transcript')
        if not domain_id or not phase1_eras:
            return self._send_json_response(400, {'error': 'Missing domain_id or phase1_eras'})

        from review_engine import score_sweep
        log_server_event('sweep_submit_start', domain_id=domain_id, era_count=len(phase1_eras))
        print(f'[sweep] Scoring sweep for {domain_id}, {len(phase1_eras)} eras...', flush=True)
        result = score_sweep(domain_id, phase1_eras, phase2_transcript)
        if result.get('error'):
            log_server_event('sweep_submit_error', domain_id=domain_id, error=result['error'])
            print(f'[sweep] Error: {result["error"]}', flush=True)
            return self._send_json_response(500, result)
        log_server_event('sweep_submit_done', domain_id=domain_id,
                         coverage=result.get('total_coverage'), composite=result.get('composite_score'))
        print(f'[sweep] Done: coverage={result.get("total_coverage", 0):.1%}, '
              f'composite={result.get("composite_score", 0):.2f}', flush=True)
        return self._send_json_response(200, result)

    def _handle_sweep_transcribe(self):
        """POST /knowledge/sweep/transcribe — transcribe audio for a sweep era.

        Accepts multipart with 'audio' field. Returns {transcript, duration_s}.
        Lightweight wrapper around Soniox transcription.
        """
        content_type = self.headers.get('Content-Type', '')
        if 'multipart' not in content_type:
            return self._send_json_response(400, {'error': 'Expected multipart'})
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = self.rfile.read(length)
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            log_server_event('sweep_transcribe_upload_drop', error=str(e), content_length=length)
            print(f'[sweep-transcribe] Client disconnected: {e}', flush=True)
            return
        try:
            fs = self._multipart_parse_bytes(data, content_type)
        except Exception as e:
            return self._send_json_response(400, {'error': f'multipart parse failed: {e}'})
        audio_field = fs['audio'] if 'audio' in fs else None
        era_id = fs.getvalue('era_id', '')
        if audio_field is None:
            return self._send_json_response(400, {'error': 'Missing audio'})

        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as tmp:
                tmp.write(audio_field.file.read())
                audio_path = Path(tmp.name)
        except OSError as e:
            log_server_event('sweep_transcribe_tmpfile_fail', error=str(e), era_id=era_id)
            return self._send_json_response(507, {'error': 'Server disk full'})
        audio_size = audio_path.stat().st_size
        log_server_event('sweep_transcribe_start', era_id=era_id, audio_bytes=audio_size)
        try:
            print(f'[sweep-transcribe] Transcribing era={era_id}, size={audio_size}', flush=True)
            transcript = transcribe_on_server(audio_path)
            if not transcript or len(transcript.strip()) < 10:
                log_server_event('sweep_transcribe_too_short', era_id=era_id)
                return self._send_json_response(200, {'transcript': '', 'era_id': era_id, 'too_short': True})
            log_server_event('sweep_transcribe_done', era_id=era_id, chars=len(transcript))
            print(f'[sweep-transcribe] Done: {len(transcript)} chars', flush=True)
            return self._send_json_response(200, {'transcript': transcript, 'era_id': era_id})
        except Exception as e:
            log_server_event('sweep_transcribe_error', era_id=era_id, error=str(e))
            print(f'[sweep-transcribe] Error: {e}', flush=True)
            return self._send_json_response(500, {'error': str(e)})
        finally:
            audio_path.unlink(missing_ok=True)

    def _handle_sweep_gaps(self):
        """POST /knowledge/sweep/gaps — get gap probing prompts from Phase 1 results.

        Body JSON: {domain_id, scoring_result: {nodes: [...]}}
        Returns gap prompts for Phase 2.
        """
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        domain_id = data.get('domain_id', '')
        scoring_result = data.get('scoring_result', {})
        if not domain_id:
            return self._send_json_response(400, {'error': 'Missing domain_id'})

        from review_engine import get_sweep_gaps
        gaps = get_sweep_gaps(scoring_result, domain_id)
        return self._send_json_response(200, {'gaps': gaps, 'gap_count': len(gaps)})

    def _handle_elicit_candidates(self):
        """GET /review/elicit-candidates?domain_id=X&limit=5 — nodes suitable for voice elicitation.
        If domain_id is omitted, returns candidates from all domains.
        """
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(self.path).query)
        domain_id = params.get('domain_id', [''])[0] or None
        limit = int(params.get('limit', ['5'])[0])
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            candidates = get_elicitation_candidates(domain_id, limit=limit, conn=conn)
            self._send_json_response(200, {'candidates': candidates})
        finally:
            conn.close()

    def _handle_elicit_know_nothing(self):
        """POST /review/elicit-know-nothing — user explicitly knows nothing about a topic."""
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        node_id = body.get('node_id', '')
        domain_id = body.get('domain_id', '')
        if not node_id:
            self._send_json_response(400, {'error': 'Missing node_id'})
            return
        # Auto-detect domain_id for chapter/book node_ids
        if not domain_id and (node_id.startswith('chapter:') or node_id.startswith('book:')):
            parts = node_id.split(':')
            book_id = parts[1] if len(parts) > 1 else ''
            if book_id:
                from db import get_connection as gc
                tmp = gc(readonly=True)
                try:
                    row = tmp.execute(
                        "SELECT DISTINCT curriculum_domain FROM knowledge_items WHERE sources LIKE ? LIMIT 1",
                        (f'%{book_id}%',)
                    ).fetchone()
                    if row:
                        domain_id = row['curriculum_domain']
                finally:
                    tmp.close()
        # Check if the user already covered this topic via adjacent elicitations
        already_covered_hint = None
        if domain_id:
            try:
                from db import get_connection as gc2
                rconn = gc2(readonly=True)
                try:
                    link_row = rconn.execute("""
                        SELECT cnl.chunk_id, vt.node_id AS source_node_id
                        FROM chunk_node_links cnl
                        JOIN transcript_chunks tc ON tc.id = cnl.chunk_id
                        JOIN voice_transcripts vt ON vt.id = tc.transcript_id
                        WHERE cnl.node_id = ? AND cnl.domain_id = ?
                        LIMIT 1
                    """, (node_id, domain_id)).fetchone()
                    if link_row:
                        source_node = link_row['source_node_id'] or 'another topic'
                        already_covered_hint = f"You discussed this during your {source_node} recall"
                finally:
                    rconn.close()
            except Exception:
                pass  # chunk_node_links table might not exist yet

        from db import get_connection
        conn = get_connection()
        try:
            from curriculum_db import update_knowledge
            if domain_id:
                update_knowledge(domain_id, node_id, knowledge='unknown', confidence=0.8,
                                 source='voice_elicit_know_nothing', conn=conn)
            conn.commit()
            print(f'[voice-elicit] Know nothing: node={node_id}, domain={domain_id or "(none)"}', flush=True)
            response = {'ok': True}
            if already_covered_hint:
                response['already_covered'] = True
                response['hint'] = already_covered_hint
            self._send_json_response(200, response)
        finally:
            conn.close()

    def _handle_review_queue(self):
        """GET /review/queue — due items in dependency order."""
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(self.path).query)
        limit = int(params.get('limit', ['20'])[0])
        book_id = params.get('book_id', [None])[0]
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            items = get_review_queue(limit=limit, book_id=book_id, conn=conn)
            self._send_json_response(200, {'items': items, 'count': len(items)})
        finally:
            conn.close()

    def _handle_review_stats(self):
        """GET /review/stats — queue statistics."""
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            stats = get_review_stats(conn)
            self._send_json_response(200, stats)
        finally:
            conn.close()

    def _handle_review_article_read(self):
        """POST /review/article-read — record article reading, surface related curriculum nodes.

        Takes article_id, looks up which curriculum nodes the article covers, finds
        knowledge_items for those nodes, and bumps their due_at to now so they appear
        in the next review session (passive exposure → active recall).
        """
        body = self._read_json_body()
        article_id = (body or {}).get('article_id', '')
        if not article_id:
            self._send_json_response(400, {'error': 'article_id required'})
            return

        # Load article → curriculum node mappings
        mappings_file = Path('/opt/petrarca/data/curricula') / 'article_curriculum_mappings.json'
        article_nodes: list[str] = []
        if mappings_file.exists():
            with open(mappings_file) as f:
                all_mappings = json.load(f)
            entry = all_mappings.get('article_nodes', {}).get(article_id, [])
            article_nodes = [n if isinstance(n, str) else n.get('node_id', '') for n in entry]
            article_nodes = [n for n in article_nodes if n]

        if not article_nodes:
            self._send_json_response(200, {'nodes_found': 0, 'items_surfaced': 0, 'nodes': []})
            return

        from db import get_connection
        import time as time_mod
        now_ms = int(time_mod.time() * 1000)
        conn = get_connection()
        try:
            surfaced = []
            node_titles = []
            for node_id in article_nodes:
                # Find knowledge_item for this node
                row = conn.execute(
                    'SELECT id, stability_days, due_at FROM knowledge_items WHERE curriculum_node_id=?',
                    (node_id,)
                ).fetchone()
                if not row:
                    continue
                item_id = row['id']
                # item id is "{domain}:{node_id}" — extract readable label from node_id
                node_title = node_id.replace('_', ' ').title()
                node_titles.append(node_title)
                # Only surface items not recently reviewed (due far in future → bring to now + 1h)
                if row['due_at'] > now_ms + 24 * 60 * 60 * 1000:
                    conn.execute(
                        'UPDATE knowledge_items SET due_at=? WHERE id=?',
                        (now_ms + 60 * 60 * 1000, item_id)  # due in 1 hour
                    )
                    surfaced.append(item_id)
            conn.commit()

            # Also update curriculum knowledge states for mapped nodes
            curriculum_result = notify_article_read_curriculum(article_id, conn)

            self._send_json_response(200, {
                'nodes_found': len(article_nodes),
                'items_surfaced': len(surfaced),
                'nodes': node_titles[:5],
                'curriculum_nodes_updated': curriculum_result.get('nodes_updated', 0),
                'curriculum_node_details': curriculum_result.get('node_details', []),
            })
        finally:
            conn.close()

    def _handle_hamarquizen(self):
        """POST /review/hamarquizen — generate Hamarquizen PRIME->READ->TEST session for a book."""
        body = self._read_json_body()
        if body is None:
            return
        book_id = body.get('book_id', '')
        limit = body.get('limit', 5)
        if not book_id:
            self._send_json_response(400, {'error': 'Missing book_id'})
            return
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            cards = generate_hamarquizen_session(book_id, limit=limit, conn=conn)
            self._send_json_response(200, {'cards': cards, 'count': len(cards)})
        finally:
            conn.close()

    def _handle_hamarquizen_cross(self):
        """POST /review/hamarquizen-cross — cross-book comparison Hamarquizen cards."""
        body = self._read_json_body()
        if body is None:
            return
        limit = body.get('limit', 5)
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            cards = generate_cross_book_hamarquizen(limit=limit, conn=conn)
            self._send_json_response(200, {'cards': cards, 'count': len(cards)})
        finally:
            conn.close()

    def _handle_knowledge_profile_get(self):
        """GET /knowledge/profile/{domain_id} — return cached or regenerated domain portrait."""
        from datetime import datetime, timedelta
        from review_engine import generate_domain_summary, get_domain_summary
        domain_id = self.path.split('/knowledge/profile/')[1].split('?')[0]
        if not domain_id:
            return self._send_json_response(400, {'error': 'Missing domain_id'})

        conn = get_connection(readonly=True)
        try:
            row = conn.execute(
                'SELECT * FROM domain_knowledge_summaries WHERE domain_id = ?',
                (domain_id,)
            ).fetchone()
        finally:
            conn.close()

        # Check freshness: if updated within last 24h, return cached
        if row:
            try:
                updated = datetime.fromisoformat(row['updated_at'])
                if datetime.now() - updated < timedelta(hours=24):
                    return self._send_json_response(200, {
                        'domain_id': domain_id,
                        'portrait': row['summary'],
                        'version': row['version'],
                        'stats': {
                            'chunk_count': row['chunk_count'],
                            'node_count': row['node_count'],
                            'entity_count': row['entity_count'],
                        },
                        'updated_at': row['updated_at'],
                        'fresh': True,
                    })
            except (ValueError, TypeError):
                pass  # stale or unparseable — regenerate

        # Stale or missing — regenerate (manages its own connections)
        portrait = generate_domain_summary(domain_id)

        if not portrait:
            return self._send_json_response(404, {'error': 'Insufficient data for domain portrait'})

        # Re-read the stored row for stats
        conn = get_connection(readonly=True)
        try:
            row = conn.execute(
                'SELECT * FROM domain_knowledge_summaries WHERE domain_id = ?',
                (domain_id,)
            ).fetchone()
        finally:
            conn.close()

        return self._send_json_response(200, {
            'domain_id': domain_id,
            'portrait': portrait,
            'version': row['version'] if row else 1,
            'stats': {
                'chunk_count': row['chunk_count'] if row else 0,
                'node_count': row['node_count'] if row else 0,
                'entity_count': row['entity_count'] if row else 0,
            },
            'updated_at': row['updated_at'] if row else None,
            'fresh': False,
        })

    def _handle_knowledge_profile_regenerate(self):
        """POST /knowledge/profile/regenerate/{domain_id} — force regeneration."""
        from review_engine import generate_domain_summary
        domain_id = self.path.split('/knowledge/profile/regenerate/')[1].split('?')[0]
        if not domain_id:
            return self._send_json_response(400, {'error': 'Missing domain_id'})

        portrait = generate_domain_summary(domain_id)  # manages its own connections

        if not portrait:
            return self._send_json_response(404, {'error': 'Insufficient data for domain portrait'})

        conn = get_connection(readonly=True)
        try:
            row = conn.execute(
                'SELECT * FROM domain_knowledge_summaries WHERE domain_id = ?',
                (domain_id,)
            ).fetchone()
        finally:
            conn.close()

        return self._send_json_response(200, {
            'domain_id': domain_id,
            'portrait': portrait,
            'version': row['version'] if row else 1,
            'stats': {
                'chunk_count': row['chunk_count'] if row else 0,
                'node_count': row['node_count'] if row else 0,
                'entity_count': row['entity_count'] if row else 0,
            },
            'updated_at': row['updated_at'] if row else None,
        })

    def _handle_dashboard_stats(self):
        """GET /stats/dashboard-data — comprehensive dashboard statistics."""
        from curriculum_db import get_dashboard_stats
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            data = get_dashboard_stats(conn=conn)
            self._send_json_response(200, data)
        finally:
            conn.close()

    def _handle_native_stats(self):
        """GET /stats/native — statistics for the native Stats tab."""
        from curriculum_db import get_native_stats
        from db import get_connection
        conn = get_connection(readonly=True)
        try:
            data = get_native_stats(conn=conn)
            self._send_json_response(200, data)
        finally:
            conn.close()

    def _serve_html_file(self, filename: str):
        html_path = Path(__file__).parent / filename
        if not html_path.exists():
            self._send_json_response(404, {'error': f'{filename} not found'})
            return
        content = html_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_curriculum_graph_html(self):
        self._serve_html_file('curriculum_graph.html')

    def _serve_curriculum_timeline_html(self):
        self._serve_html_file('curriculum_timeline.html')

    def do_POST(self):
        if koigen_adapter.post_route(self.path):
            return self._handle_koigen_post()
        if self.path == '/admin/entity/resolve':
            return self._handle_admin_entity_resolve()
        if self.path == '/admin/entity/merge':
            return self._handle_admin_entity_merge()
        if self.path == '/chat':
            return self._handle_chat()
        if self.path == '/note':
            return self._handle_note()
        if self.path == '/research/topic':
            return self._handle_topic_research()
        if self.path == '/generate-questions':
            return self._handle_generate_questions()
        if self.path == '/ingest':
            return self._handle_ingest()
        if self.path == '/ingest-youtube':
            return self._handle_ingest_youtube()
        if self.path == '/media/sync':
            return self._handle_media_sync()
        if self.path == '/ingest-email':
            return self._handle_ingest_email()
        if self.path == '/ingest-book':
            return self._handle_ingest_book()
        if self.path == '/twitter/cookies':
            return self._handle_twitter_cookies()
        if self.path == '/ingest-note':
            return self._handle_ingest_note()
        if self.path == '/ingest-cancel':
            return self._handle_ingest_cancel()
        if self.path == '/report-scrape':
            return self._handle_report_scrape()
        if self.path == '/feedback':
            return self._handle_feedback()
        if self.path == '/book/identify':
            return self._handle_book_identify()
        if self.path == '/book/ocr-toc':
            return self._handle_book_ocr_toc()
        if self.path == '/book/ocr-page':
            return self._handle_book_ocr_page()
        if self.path == '/book/upload-photo':
            return self._handle_book_upload_photo()
        if self.path == '/book/photo-results':
            return self._handle_book_photo_results()
        if self.path == '/book/voice-note':
            return self._handle_book_voice_note()
        if self.path == '/book/research':
            return self._handle_book_research()
        if self.path == '/book/chapter-insights':
            return self._handle_book_chapter_insights()
        if self.path == '/book/story-so-far':
            return self._handle_book_story_so_far()
        if self.path == '/book/sync':
            return self._handle_book_sync_save()
        if self.path == '/book/resurfacing/generate':
            return self._handle_resurfacing_generate()
        if self.path == '/book/resurfacing/respond':
            return self._handle_resurfacing_respond()
        if self.path == '/book/resurfacing/skip':
            return self._handle_resurfacing_skip()
        if self.path == '/curriculum/review/generate':
            return self._handle_curriculum_review_generate()
        if self.path == '/curriculum/review/result':
            return self._handle_curriculum_review_result()
        if self.path == '/review/microlearning':
            return self._handle_microlearning_request()
        if self.path == '/curriculum/review/suspend':
            return self._handle_review_suspend()
        if self.path == '/review/microlearning/dismiss':
            return self._handle_microlearning_dismiss()
        if self.path == '/review/ml-flag-inaccurate':
            return self._handle_ml_flag_inaccurate()
        if self.path == '/review/follow-up/trigger':
            return self._handle_follow_up_trigger()
        if self.path == '/review/follow-up/generate':
            return self._handle_follow_up_generate()
        if self.path == '/review/also-want-to-know':
            return self._handle_also_want_to_know()
        if self.path == '/review/targeted-quiz':
            return self._handle_targeted_quiz()
        if self.path == '/review/create-factual-quiz':
            return self._handle_create_factual_quiz()
        if self.path == '/review/suspend-fact':
            return self._handle_suspend_fact()
        if self.path == '/review/batch-generate':
            return self._handle_review_batch_generate()
        if self.path == '/entity/tap':
            return self._handle_entity_tap()
        if self.path == '/entity/questions':
            return self._handle_entity_questions()
        if self.path == '/entity/research':
            return self._handle_entity_research()
        if self.path == '/entity/notes':
            return self._handle_entity_notes_save()
        if self.path == '/explore/capture':
            return self._handle_explore_capture()
        if self.path == '/book/process-kindle':
            return self._handle_process_kindle()
        if self.path == '/kindle/sync':
            return self._handle_kindle_sync()
        if self.path == '/kindle/curate':
            return self._handle_kindle_curate()
        if self.path == '/kindle/include':
            return self._handle_kindle_include()
        if self.path == '/kindle/classify':
            return self._handle_kindle_classify()
        if self.path == '/kindle/resolve-titles':
            return self._handle_kindle_resolve_titles()
        if self.path == '/kindle/scan-epubs':
            return self._handle_kindle_scan_epubs()

        # Project endpoints
        if self.path == '/projects':
            return self._handle_project_create()
        if self.path == '/projects/note':
            return self._handle_project_note()
        if self.path.endswith('/update') and self.path.startswith('/projects/'):
            return self._handle_project_update()

        # Curriculum endpoints
        if self.path == '/curriculum/generate':
            return self._handle_curriculum_generate()
        if self.path == '/curriculum/map-book':
            return self._handle_curriculum_map_book()
        if self.path == '/curriculum/elicit/start':
            return self._handle_elicit_start()
        if self.path == '/curriculum/elicit/respond':
            return self._handle_elicit_respond()
        if self.path == '/curriculum/knowledge/update':
            return self._handle_knowledge_update()
        if self.path == '/curriculum/knowledge/import-assessment':
            return self._handle_knowledge_import_assessment()
        if self.path.startswith('/knowledge/profile/regenerate/'):
            return self._handle_knowledge_profile_regenerate()
        if self.path == '/knowledge/sweep/submit':
            return self._handle_sweep_submit()
        if self.path == '/knowledge/sweep/gaps':
            return self._handle_sweep_gaps()
        if self.path == '/knowledge/sweep/transcribe':
            return self._handle_sweep_transcribe()
        if self.path == '/knowledge/snapshot-metrics':
            try:
                from curriculum_db import snapshot_network_metrics
            except ImportError:
                return self._send_json_response(501, {'error': 'not implemented'})
            conn = get_connection()
            try:
                results = snapshot_network_metrics(conn=conn)
                conn.commit()
            finally:
                conn.close()
            return self._send_json_response(200, {'snapshots': results, 'count': len(results)})

        # Client interaction logging (replaces broken log_server.py:8091)
        if self.path == '/log/events':
            return self._handle_log_events()

        # Review endpoints
        if self.path == '/review/book-complete':
            return self._handle_review_book_complete()
        if self.path == '/review/chapter-complete':
            return self._handle_review_chapter_complete()
        if self.path == '/review/chapter-context':
            return self._handle_chapter_context()
        if self.path == '/review/generate-question':
            return self._handle_review_generate_question()
        if self.path == '/review/answer':
            return self._handle_review_answer()
        if self.path == '/structural/grade':
            return self._handle_structural_grade()
        if self.path in ('/admin/suggested-cards/approve', '/admin/suggested-cards/reject'):
            return self._handle_admin_suggested_cards_update()
        if self.path == '/review/explore':
            return self._handle_review_explore()
        if self.path == '/defender/start':
            return self._handle_defender_start()
        if self.path == '/defender/respond':
            return self._handle_defender_respond()
        if self.path == '/defender/transcribe':
            return self._handle_defender_transcribe()
        if self.path == '/commonplace/resurface':
            return self._handle_commonplace_resurface()
        if self.path == '/commonplace/resurface-audio':
            return self._handle_commonplace_resurface_audio()
        if self.path == '/review/voice-memo':
            return self._handle_review_voice_memo()
        if self.path == '/review/voice-elicit':
            return self._handle_voice_elicitation()
        if self.path == '/review/elicit-know-nothing':
            return self._handle_elicit_know_nothing()
        if self.path == '/review/article-read':
            return self._handle_review_article_read()
        if self.path == '/review/hamarquizen':
            return self._handle_hamarquizen()
        if self.path == '/review/hamarquizen-cross':
            return self._handle_hamarquizen_cross()

        if self.path == '/research/explore-batch':
            return self._handle_explore_batch()

        # /notes/{note_id}/execute-action
        if self.path.startswith('/notes/') and self.path.endswith('/execute-action'):
            return self._handle_execute_action()

        if self.path not in ('/research', '/research/explore'):
            self.send_error(404)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            try:
                body = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, ValueError) as e:
                self._send_json_response(400, {'error': f'Invalid JSON: {e}'})
                return
        else:
            body = {}

        if self.path == '/research/explore':
            request_id = body.get('id', f'exp_{int(time.time())}')
            subtopic = body.get('subtopic', '')
            exploration_tag = body.get('exploration_tag', '')
            triage_signals = body.get('triage_signals', {})
            existing_concepts = body.get('concepts', [])

            if not subtopic or not exploration_tag:
                self.send_error(400, 'Missing subtopic or exploration_tag')
                return

            result_path = RESULTS_DIR / f'{request_id}.json'
            result_path.write_text(json.dumps({
                'id': request_id,
                'type': 'explore',
                'status': 'processing',
                'subtopic': subtopic,
                'exploration_tag': exploration_tag,
                'requested_at': int(time.time() * 1000),
            }, indent=2))

            thread = threading.Thread(
                target=run_explore,
                args=(request_id, subtopic, exploration_tag, triage_signals, existing_concepts),
                daemon=True,
            )
            thread.start()

            print(f'[explore] Started {request_id}: {subtopic[:80]}...')

            self.send_response(202)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'id': request_id, 'status': 'processing'}).encode())
            return

        request_id = body.get('id', f'res_{int(time.time())}')
        query = body.get('query', '')
        article_title = body.get('article_title', '')
        article_summary = body.get('article_summary', '')
        concepts = body.get('concepts', [])

        if not query:
            self.send_error(400, 'Missing query')
            return

        # Save initial pending state
        result_path = RESULTS_DIR / f'{request_id}.json'
        result_path.write_text(json.dumps({
            'id': request_id,
            'status': 'processing',
            'query': query,
            'article_title': article_title,
            'requested_at': int(time.time() * 1000),
        }, indent=2))

        # Spawn background thread
        thread = threading.Thread(
            target=run_research,
            args=(request_id, query, article_title, article_summary, concepts),
            daemon=True,
        )
        thread.start()

        print(f'[research] Started {request_id}: {query[:80]}...')

        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': request_id, 'status': 'processing'}).encode())

    def _load_articles_map(self) -> dict:
        """Load articles.json and return {id: title} map."""
        try:
            articles = json.loads(ARTICLES_PATH.read_text())
            return {a['id']: a.get('title', 'Untitled') for a in articles}
        except (OSError, json.JSONDecodeError, KeyError):
            return {}

    def _load_log_events(self, days: int) -> list[dict]:
        """Load interaction log events for the last N days."""
        events = []
        today = datetime.now(timezone.utc).date()
        for i in range(days):
            d = today - timedelta(days=i)
            log_file = LOG_DIR / f'interactions_{d.isoformat()}.jsonl'
            if not log_file.exists():
                continue
            try:
                for line in log_file.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                continue
        return events

    def _load_research_results(self) -> list[dict]:
        """Load all research result files."""
        results = []
        if not RESULTS_DIR.exists():
            return results
        for f in RESULTS_DIR.glob('*.json'):
            try:
                results.append(json.loads(f.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        return results

    def _handle_activity_feed(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        days = int(params.get('days', ['1'])[0])

        articles_map = self._load_articles_map()
        raw_events = self._load_log_events(days)
        research_results = self._load_research_results()

        # Build lookup: research_id -> result
        research_by_id = {r['id']: r for r in research_results if 'id' in r}

        timeline = []

        # --- Group reading sessions ---
        # Collect reader_* events by (session_id, article_id)
        reading_sessions = {}  # (session_id, article_id) -> list of events
        for ev in raw_events:
            event_name = ev.get('event', '')
            if event_name.startswith('reader_') and ev.get('article_id'):
                key = (ev.get('session_id', ''), ev['article_id'])
                reading_sessions.setdefault(key, []).append(ev)

        for (session_id, article_id), evts in reading_sessions.items():
            evts.sort(key=lambda e: e.get('ts', ''))
            anchor = next((e for e in evts if e['event'] == 'reader_open'), evts[0])

            finished = any(e['event'] == 'reader_done' for e in evts)
            highlights = sum(1 for e in evts if e['event'] == 'reader_highlight_add')
            close_evt = next((e for e in evts if e['event'] == 'reader_close'), None)
            time_spent_ms = close_evt.get('time_spent_ms', 0) if close_evt else 0
            scroll_pct = 0
            for e in evts:
                if e['event'] == 'reader_scroll_milestone':
                    scroll_pct = max(scroll_pct, e.get('pct', 0))

            title = articles_map.get(article_id, anchor.get('title', article_id[:12]))
            subtype = 'finished' if finished else 'in_progress'

            # Build subtitle
            parts = []
            if time_spent_ms > 0:
                mins = round(time_spent_ms / 60000)
                parts.append(f'{mins} min' if mins > 0 else '<1 min')
            if highlights:
                parts.append(f'{highlights} highlight{"s" if highlights != 1 else ""}')
            subtitle = ' · '.join(parts) if parts else None

            prefix = 'Finished reading' if finished else 'Reading'
            timeline.append({
                'id': f'evt_{anchor["ts"]}_{article_id[:8]}',
                'type': 'reading',
                'subtype': subtype,
                'ts': anchor.get('ts'),
                'title': f'{prefix}: {title}',
                'subtitle': subtitle,
                'article_id': article_id,
                'meta': {
                    'time_spent_ms': time_spent_ms,
                    'highlights': highlights,
                    'scroll_pct': scroll_pct,
                },
            })

        # --- Dismissals ---
        for ev in raw_events:
            if ev.get('event') == 'article_dismissed' and ev.get('article_id'):
                aid = ev['article_id']
                title = articles_map.get(aid, aid[:12])
                reason = ev.get('reason', '')
                timeline.append({
                    'id': f'evt_{ev["ts"]}_{aid[:8]}',
                    'type': 'reading',
                    'subtype': 'dismissed',
                    'ts': ev.get('ts'),
                    'title': f'Dismissed: {title}',
                    'subtitle': reason if reason else None,
                    'article_id': aid,
                })

        # --- Interest signals ---
        # Group interest_chip_tap events within 60s of each other for same article
        interest_events = [e for e in raw_events if e.get('event') == 'interest_chip_tap']
        interest_events.sort(key=lambda e: e.get('ts', ''))
        interest_groups = []
        for ev in interest_events:
            ev_ts = ev.get('ts', '')
            merged = False
            for group in interest_groups:
                last_ts = group[-1].get('ts', '')
                # Check same article or within 60s
                try:
                    t1 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                    t2 = datetime.fromisoformat(ev_ts.replace('Z', '+00:00'))
                    if abs((t2 - t1).total_seconds()) <= 60:
                        group.append(ev)
                        merged = True
                        break
                except (ValueError, TypeError):
                    pass
            if not merged:
                interest_groups.append([ev])

        for group in interest_groups:
            positive = []
            negative = []
            for ev in group:
                topic = ev.get('topic', '')
                if ev.get('positive', True):
                    positive.append(topic)
                else:
                    negative.append(topic)

            parts = []
            for t in positive:
                parts.append(f'+{t}')
            for t in negative:
                parts.append(f'-{t}')

            timeline.append({
                'id': f'evt_{group[0]["ts"]}_interest',
                'type': 'interest',
                'subtype': 'signal',
                'ts': group[0].get('ts'),
                'title': 'Signaled interest',
                'subtitle': ' '.join(parts) if parts else None,
                'topics_positive': positive,
                'topics_negative': negative,
            })

        # --- Pipeline runs ---
        pipeline_events = [e for e in raw_events if e.get('source') == 'pipeline']
        pipeline_events.sort(key=lambda e: e.get('ts', ''))
        pipeline_runs = []
        for ev in pipeline_events:
            ev_ts = ev.get('ts', '')
            merged = False
            for run in pipeline_runs:
                last_ts = run[-1].get('ts', '')
                try:
                    t1 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                    t2 = datetime.fromisoformat(ev_ts.replace('Z', '+00:00'))
                    if abs((t2 - t1).total_seconds()) <= 900:
                        run.append(ev)
                        merged = True
                        break
                except (ValueError, TypeError):
                    pass
            if not merged:
                pipeline_runs.append([ev])

        STEP_LABELS = {
            'pipeline_fetch_twitter': 'Fetched Twitter bookmarks',
            'pipeline_fetch_readwise': 'Fetched Readwise articles',
            'pipeline_build_articles': 'Built articles',
            'pipeline_defrag_topics': 'Defragmented topics',
            'pipeline_extract_claims': 'Extracted claims',
            'pipeline_build_index': 'Built knowledge index',
        }

        for run in pipeline_runs:
            event_names = [e.get('event', '') for e in run]
            completed = 'pipeline_complete' in event_names
            complete_ev = next((e for e in run if e.get('event') == 'pipeline_complete'), None)
            elapsed = complete_ev.get('elapsed_seconds') if complete_ev else None

            if completed and elapsed:
                mins, secs = divmod(int(elapsed), 60)
                run_title = f'Content refresh ({mins}m {secs}s)' if mins else f'Content refresh ({secs}s)'
            elif completed:
                run_title = 'Content refresh complete'
            else:
                run_title = 'Content refresh running'

            steps = len([n for n in event_names if n in STEP_LABELS])
            timeline.append({
                'id': f'evt_{run[0]["ts"]}_pipeline',
                'type': 'system',
                'subtype': 'pipeline',
                'ts': run[-1].get('ts') if completed else run[0].get('ts'),
                'title': run_title,
                'subtitle': f'{steps} steps' if steps else None,
            })

            # Also emit individual step events for granular view
            for ev in run:
                name = ev.get('event', '')
                if name in STEP_LABELS:
                    timeline.append({
                        'id': f'evt_{ev["ts"]}_{name}',
                        'type': 'system',
                        'subtype': 'pipeline_step',
                        'ts': ev.get('ts'),
                        'title': STEP_LABELS[name],
                    })

        # --- Server-side events (ingestion, article processing) ---
        INGEST_LABELS = {
            'clipper': 'Clipped',
            'reader_link': 'From reader',
        }
        for ev in raw_events:
            if ev.get('source') != 'server':
                continue
            event_name = ev.get('event', '')

            if event_name == 'ingest_queued':
                title = ev.get('title') or ev.get('url', 'Unknown')[:60]
                src = ev.get('ingest_source', 'unknown')
                label = INGEST_LABELS.get(src, 'Ingested')
                timeline.append({
                    'id': f'evt_{ev["ts"]}_ingest',
                    'type': 'system',
                    'subtype': 'ingest',
                    'ts': ev.get('ts'),
                    'title': f'{label}: {title}',
                    'article_id': ev.get('article_id'),
                })

            elif event_name == 'ingest_email':
                timeline.append({
                    'id': f'evt_{ev["ts"]}_email',
                    'type': 'system',
                    'subtype': 'ingest',
                    'ts': ev.get('ts'),
                    'title': f'Email from {ev.get("sender", "unknown")}',
                })

            elif event_name == 'article_processed':
                title = ev.get('title', 'Unknown')
                wc = ev.get('word_count', 0)
                wc_str = f' ({wc} words)' if wc else ''
                timeline.append({
                    'id': f'evt_{ev["ts"]}_processed',
                    'type': 'system',
                    'subtype': 'processed',
                    'ts': ev.get('ts'),
                    'title': f'Processed: {title}{wc_str}',
                    'article_id': ev.get('article_id'),
                })

            elif event_name == 'bookmarks_fetched':
                count = ev.get('count', 0)
                if count > 0:
                    timeline.append({
                        'id': f'evt_{ev["ts"]}_twitter',
                        'type': 'system',
                        'subtype': 'fetch',
                        'ts': ev.get('ts'),
                        'title': f'Fetched {count} Twitter bookmarks',
                    })

            elif event_name == 'readwise_fetched':
                count = ev.get('count', 0)
                docs = ev.get('documents', count)
                if count > 0:
                    timeline.append({
                        'id': f'evt_{ev["ts"]}_readwise',
                        'type': 'system',
                        'subtype': 'fetch',
                        'ts': ev.get('ts'),
                        'title': f'Fetched {count} Readwise items → {docs} docs',
                    })

        # --- Research events ---
        for ev in raw_events:
            event_name = ev.get('event', '')
            if event_name in ('research_spawned', 'topic_research_spawned'):
                topic = ev.get('topic', '')
                aid = ev.get('article_id')

                # Try to match with a completed result
                matched_result = None
                for rid, res in research_by_id.items():
                    if res.get('query') == topic or res.get('article_title') == articles_map.get(aid, ''):
                        matched_result = res
                        break

                if event_name == 'topic_research_spawned':
                    title_text = f'Research: {topic}'
                else:
                    article_title = articles_map.get(aid, '') if aid else ''
                    title_text = f'Research: {topic}' if topic else f'Research on {article_title}'

                subtype = 'dispatched'
                subtitle = 'Pending'
                if matched_result:
                    if matched_result.get('status') == 'completed':
                        subtype = 'completed'
                        subtitle = 'Results ready'
                    elif matched_result.get('status') == 'failed':
                        subtype = 'completed'
                        subtitle = 'Failed'

                node = {
                    'id': f'evt_{ev["ts"]}_research',
                    'type': 'research',
                    'subtype': subtype,
                    'ts': ev.get('ts'),
                    'title': title_text,
                    'subtitle': subtitle,
                }
                if aid:
                    node['article_id'] = aid
                timeline.append(node)

        # --- Queue actions ---
        for ev in raw_events:
            if ev.get('event') == 'queue_add' and ev.get('article_id'):
                aid = ev['article_id']
                title = articles_map.get(aid, aid[:12])
                timeline.append({
                    'id': f'evt_{ev["ts"]}_{aid[:8]}',
                    'type': 'reading',
                    'subtype': 'queued',
                    'ts': ev.get('ts'),
                    'title': f'Queued: {title}',
                    'article_id': aid,
                })

        # Sort newest-first
        timeline.sort(key=lambda e: e.get('ts', ''), reverse=True)

        self._send_json_response(200, {'events': timeline})

    # ------------------------------------------------------------------
    # Content API endpoints (SQLite Phase 4)
    # ------------------------------------------------------------------

    def _handle_content_api(self):
        """Dispatch /api/* routes to SQLite-backed content endpoints."""
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == '/api/manifest':
            conn = get_connection(readonly=True)
            try:
                data = compute_manifest(conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)

        if path == '/api/articles-meta':
            since = qs.get('since', [None])[0]
            conn = get_connection(readonly=True)
            try:
                articles = export_articles_meta(conn, since=since)
            finally:
                conn.close()
            return self._send_json_response(200, {'articles': articles})

        # /api/articles/<id>/content
        if path.startswith('/api/articles/') and path.endswith('/content'):
            article_id = path.split('/api/articles/')[1].rsplit('/content', 1)[0]
            article_id = unquote(article_id)
            conn = get_connection(readonly=True)
            try:
                data = export_article_content(conn, article_id)
            finally:
                conn.close()
            if data is None:
                return self._send_json_response(404, {'error': 'Article not found'})
            return self._send_json_response(200, data)

        if path == '/api/knowledge-index':
            conn = get_connection(readonly=True)
            try:
                data = export_knowledge_index(conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)

        if path == '/api/syntheses':
            conn = get_connection(readonly=True)
            try:
                data = export_syntheses(conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)

        if path == '/api/clusters':
            conn = get_connection(readonly=True)
            try:
                data = export_clusters(conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)

        return self._send_json_response(404, {'error': 'Unknown API endpoint'})

    def do_GET(self):
        if koigen_adapter.is_approve_get(self.path):
            return self._handle_koigen_get()
        # Content API endpoints (SQLite Phase 4)
        if self.path.startswith('/api/'):
            return self._handle_content_api()

        if self.path.startswith('/book/research/'):
            return self._handle_book_research_get()
        if self.path == '/book/sync':
            return self._handle_book_sync_load()
        if self.path.startswith('/review/queue'):
            return self._handle_review_queue()
        if self.path == '/review/stats':
            return self._handle_review_stats()
        if self.path.startswith('/review/elicit-candidates'):
            return self._handle_elicit_candidates()
        if self.path.startswith('/review/voice-elicit-check'):
            return self._handle_voice_elicit_check()
        if self.path == '/defender/sessions' or self.path.startswith('/defender/sessions?'):
            return self._handle_defender_sessions_list()
        if self.path.startswith('/defender/sessions/'):
            session_id = self.path.split('/defender/sessions/')[1].split('?')[0]
            return self._handle_defender_session_detail(session_id)
        if self.path == '/commonplace/events' or self.path.startswith('/commonplace/events?'):
            return self._handle_commonplace_events_list()
        if self.path == '/media/log':
            media_log_path = Path(os.environ.get('MEDIA_LOG_PATH', '/opt/petrarca/data/media_log.json'))
            try:
                data = json.loads(media_log_path.read_text()) if media_log_path.exists() else {'items': []}
            except json.JSONDecodeError:
                data = {'items': []}
            self._send_json_response(200, data)
            return
        if self.path == '/book/resurfacing/status':
            return self._handle_resurfacing_status()
        if self.path == '/entities' or self.path.startswith('/entities?'):
            return self._handle_entities_list()
        if self.path.startswith('/entity/') and not self.path.startswith('/entity/tap') and not self.path.startswith('/entity/notes'):
            return self._handle_entity_lookup()
        # Wikidata entity review UI (PR 3)
        if self.path == '/admin/entity-queue':
            return self._serve_html_file('entity_review.html')
        if self.path.startswith('/admin/entity-queue-data'):
            return self._handle_admin_entity_queue_data()
        if self.path.startswith('/admin/entity/Q'):
            return self._handle_admin_entity_detail()
        if self.path.startswith('/admin/suggested-cards'):
            return self._handle_admin_suggested_cards()
        if self.path.startswith('/curriculum/review/timeline/'):
            domain_id = self.path.split('/curriculum/review/timeline/')[1].split('?')[0]
            return self._send_json_response(200, {'timeline': get_timeline(domain_id)})
        # /curriculum/review/questions/ endpoint retired (retrieval_questions table archived)
        if self.path == '/kindle/recently-started':
            return self._handle_kindle_recently_started()
        if self.path.startswith('/kindle/browse'):
            return self._handle_kindle_browse()
        if self.path.startswith('/kindle/library'):
            return self._handle_kindle_library_get()
        if self.path.startswith('/kindle/highlights'):
            return self._handle_kindle_highlights_get()

        # Project GET endpoints
        if self.path == '/projects':
            return self._handle_projects_list()
        if self.path.startswith('/projects/') and self.path.count('/') == 2:
            return self._handle_project_detail()

        # Curriculum GET endpoints
        if self.path == '/curriculum/list':
            return self._send_json_response(200, {'curricula': list_curricula()})
        if self.path == '/curriculum/graph-data':
            conn = get_connection()
            data = get_curriculum_graph_data(conn)
            conn.close()
            return self._send_json_response(200, data)
        if self.path == '/curriculum/graph':
            return self._serve_curriculum_graph_html()
        if self.path == '/curriculum/timeline':
            return self._serve_curriculum_timeline_html()
        if self.path == '/curriculum/entity-index':
            return self._send_json_response(200, get_entity_index())
        if self.path.startswith('/book/prescan/'):
            book_id = self.path.split('/book/prescan/')[1].split('?')[0]
            conn = get_connection(readonly=True)
            try:
                data = get_book_prescan(book_id, conn=conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)
        if self.path == '/stats/dashboard':
            return self._serve_html_file('statistics_dashboard.html')
        if self.path == '/stats/dashboard-data':
            return self._handle_dashboard_stats()
        if self.path == '/stats/native':
            return self._handle_native_stats()
        if self.path == '/research/elicitation-analysis':
            return self._serve_html_file('knowledge_elicitation_analysis.html')
        if self.path == '/knowledge/growth':
            return self._serve_html_file('knowledge_growth.html')
        # Knowledge sweep endpoints
        if self.path.startswith('/knowledge/sweep/plan/'):
            domain_id = self.path.split('/knowledge/sweep/plan/')[1].split('?')[0]
            from review_engine import get_sweep_plan
            plan = get_sweep_plan(domain_id)
            if not plan:
                return self._send_json_response(404, {'error': f'Curriculum {domain_id} not found'})
            return self._send_json_response(200, plan)
        if self.path.startswith('/knowledge/sweep/history/'):
            domain_id = self.path.split('/knowledge/sweep/history/')[1].split('?')[0]
            from review_engine import get_sweep_history
            history = get_sweep_history(domain_id)
            return self._send_json_response(200, {'sweeps': history, 'domain_id': domain_id})
        if self.path == '/knowledge/sweep/domains':
            # list_curricula imported at module top — do not re-import here (would shadow and break /curriculum/list).
            curricula = list_curricula()
            # Add last sweep info for each domain
            conn = get_connection(readonly=True)
            try:
                domains = []
                for c in curricula:
                    last = conn.execute(
                        'SELECT id, total_coverage, composite_score, created_at '
                        'FROM knowledge_sweeps WHERE domain_id = ? ORDER BY created_at DESC LIMIT 1',
                        (c['id'],)
                    ).fetchone()
                    domains.append({
                        'id': c['id'],
                        'title': c['title'],
                        'node_count': c.get('node_count', 0),
                        'last_sweep': dict(last) if last else None,
                    })
            finally:
                conn.close()
            return self._send_json_response(200, {'domains': domains})
        if self.path == '/knowledge/growth-data':
            try:
                from curriculum_db import get_knowledge_growth_data
            except ImportError:
                return self._send_json_response(501, {'error': 'not implemented'})
            conn = get_connection(readonly=True)
            try:
                data = get_knowledge_growth_data(conn=conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)
        if self.path == '/voice/calibration' or self.path.startswith('/voice/calibration?'):
            return self._serve_html_file('voice_calibration.html')
        if self.path.startswith('/voice/calibration-data'):
            try:
                from voice_calibration import get_voice_calibration_data
            except ImportError as e:
                return self._send_json_response(500, {'error': f'voice_calibration import failed: {e}'})
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = int(q.get('limit', ['5'])[0])
            except ValueError:
                limit = 5
            limit = max(1, min(limit, 20))
            conn = get_connection(readonly=True)
            try:
                data = get_voice_calibration_data(conn, limit=limit)
            finally:
                conn.close()
            return self._send_json_response(200, data)
        if self.path == '/knowledge/atlas':
            return self._serve_html_file('knowledge_atlas.html')
        if self.path == '/knowledge/atlas-data':
            try:
                from curriculum_db import get_knowledge_atlas_data
            except ImportError:
                return self._send_json_response(501, {'error': 'get_knowledge_atlas_data not implemented yet'})
            conn = get_connection(readonly=True)
            try:
                data = get_knowledge_atlas_data(conn=conn)
            finally:
                conn.close()
            return self._send_json_response(200, data)
        if self.path.startswith('/knowledge/profile/'):
            return self._handle_knowledge_profile_get()
        if self.path.startswith('/curriculum/generate/status'):
            from urllib.parse import urlparse, parse_qs
            job_id = parse_qs(urlparse(self.path).query).get('id', [''])[0]
            job = _curriculum_jobs.get(job_id, {'status': 'not_found'})
            return self._send_json_response(200, job)
        if self.path.startswith('/curriculum/book-context/'):
            book_id = self.path.split('/curriculum/book-context/')[1].split('?')[0]
            context = get_book_curriculum_context(book_id)
            return self._send_json_response(200, context)
        if self.path.startswith('/curriculum/') and '/coverage' in self.path:
            domain_id = self.path.split('/curriculum/')[1].split('/coverage')[0]
            report = get_coverage_report(domain_id)
            if report:
                return self._send_json_response(200, report)
            return self._send_json_response(404, {'error': 'Curriculum not found'})
        if self.path.startswith('/curriculum/') and not self.path.startswith('/curriculum/elicit') and not self.path.startswith('/curriculum/knowledge') and not self.path.startswith('/curriculum/map') and not self.path.startswith('/curriculum/list') and not self.path.startswith('/curriculum/graph') and not self.path.startswith('/curriculum/timeline') and not self.path.startswith('/curriculum/entity') and not self.path.startswith('/curriculum/generate'):
            domain_id = self.path.split('/curriculum/')[1].split('?')[0]
            curriculum = load_curriculum(domain_id)
            if curriculum:
                states = load_knowledge_states(domain_id)
                # Annotate nodes with knowledge states
                for node in curriculum.get('nodes', []):
                    state = states.get(node['id'], {})
                    node['knowledge'] = state.get('knowledge', 'unknown')
                    node['interest'] = state.get('interest', 'none')
                    node['confidence'] = state.get('confidence', 0.0)
                    node['sources'] = state.get('sources', [])
                return self._send_json_response(200, curriculum)
            return self._send_json_response(404, {'error': 'Curriculum not found'})

        if self.path.startswith('/activity/feed'):
            return self._handle_activity_feed()

        elif self.path == '/research/results':
            results = []
            for f in sorted(RESULTS_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    data = json.loads(f.read_text())
                    if data.get('status') == 'completed':
                        results.append(data)
                except (json.JSONDecodeError, OSError):
                    continue

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())

        elif self.path.startswith('/notes'):
            # /notes?article_id=X or /notes (all)
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            article_filter = params.get('article_id', [None])[0]

            notes = []
            for f in sorted(NOTES_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    note = json.loads(f.read_text())
                    if article_filter and note.get('article_id') != article_filter:
                        continue
                    notes.append(note)
                except (json.JSONDecodeError, OSError):
                    continue

            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(notes).encode())

        elif self.path.startswith('/ingest-status'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            ingest_id = params.get('id', [None])[0]
            if not ingest_id:
                self._send_json_response(400, {'error': 'Missing id parameter'})
                return
            log_path = INGEST_DIR / f'{ingest_id}.json'
            if not log_path.exists():
                self._send_json_response(404, {'error': 'Ingest not found', 'id': ingest_id})
                return
            try:
                data = json.loads(log_path.read_text())
                self._send_json_response(200, {
                    'id': data.get('id'),
                    'status': data.get('status', 'unknown'),
                    'article_id': data.get('article_id'),
                    'url': data.get('url'),
                })
            except (json.JSONDecodeError, OSError) as e:
                self._send_json_response(500, {'error': str(e)})

        elif self.path == '/twitter/status':
            try:
                result = asyncio.run(_check_twikit_cookies())
            except Exception as e:
                result = {'valid': False, 'error': f'Check failed: {e}'}
            self._send_json_response(200, result)

        elif self.path == '/scrape-reports':
            try:
                reports = json.loads(SCRAPE_REPORTS_PATH.read_text()) if SCRAPE_REPORTS_PATH.exists() else []
                # Only show pending reports
                pending = [r for r in reports if r.get('status', 'pending') == 'pending']
                self._send_json_response(200, pending)
            except (json.JSONDecodeError, OSError):
                self._send_json_response(200, [])

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(f'[http] {args[0]}')


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _retry_failed_ml_cards():
    """Requeue ML cards that failed within the last 24h.

    Session 89: 4 Iran-capture ML cards sat at status='failed' forever because the
    original processing pipeline has no retry path — they failed during a Gemini
    429 window and were never revisited. Spacing retries 30s apart avoids
    re-triggering the same per-minute rate limit that caused the original fail.
    """
    from db import get_connection
    from review_engine import _run_microlearning_research

    conn = get_connection(readonly=True)
    now_ms = int(time.time() * 1000)
    try:
        rows = conn.execute(
            '''SELECT id, query, source_node_id, source_domain
               FROM microlearning_cards
               WHERE status='failed' AND created_at > ?
               ORDER BY created_at''',
            (now_ms - 86400000,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return
    print(f'[ml-retry] sweeping {len(rows)} failed cards from the last 24h',
          flush=True)
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(30)
        try:
            _run_microlearning_research(
                row['id'], row['query'],
                row['source_node_id'], row['source_domain'],
            )
        except Exception as e:
            print(f'[ml-retry] {row["id"]} still failing: {e}', flush=True)


if __name__ == '__main__':
    init_db()
    migrate_kindle_json_to_sqlite()
    threading.Thread(target=_retry_failed_ml_cards, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), ResearchHandler)
    print(f'Research server listening on port {PORT}')
    print(f'Results directory: {RESULTS_DIR}')
    server.serve_forever()
