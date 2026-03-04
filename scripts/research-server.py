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

import email
import email.policy
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, unquote

RESULTS_DIR = Path(os.environ.get('RESEARCH_RESULTS_DIR', '/opt/petrarca/research-results'))
INGEST_DIR = Path(os.environ.get('INGEST_DIR', '/opt/petrarca/ingest'))
PORT = int(os.environ.get('RESEARCH_PORT', '8090'))
INGEST_TOKEN = os.environ.get('PETRARCA_INGEST_TOKEN', '')
BOOKS_OUTPUT_DIR = Path(os.environ.get('BOOKS_OUTPUT_DIR', '/opt/petrarca/data/books'))
CROSS_MATCH_DIR = Path(os.environ.get('CROSS_MATCH_DIR', '/opt/petrarca/data'))
SCRIPTS_DIR = Path(__file__).parent
VENV_PYTHON = '/opt/petrarca/.venv/bin/python3'

EMAILS_DIR = INGEST_DIR / 'emails'

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
INGEST_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)


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
    if re.search(r'unsub|opt-out|optout|manage.preferences|email-preferences', full):
        return -1
    if 'substack.com' in hostname and re.match(r'^/(sign-in|account|app-link|embed|profile)', pathname):
        return -1
    if pathname in ('/', '/subscribe', '/publish', ''):
        return -1
    if re.match(r'^/@[^/]+/?$', pathname):
        return -1
    if re.search(r'1x1|beacon|pixel|\.gif\?', full):
        return -1
    if hostname == 't.co':
        return -1
    if re.match(r'^https?://(www\.)?(twitter|x)\.com/[^/]+/?$', url, re.IGNORECASE):
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
    if re.search(r'substack\.com/redirect/', full): score -= 5

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
    """Try to decode Substack redirect URLs to get the real destination."""
    import base64
    m = re.search(r'substack\.com/redirect/\d+/([A-Za-z0-9_-]+)', url)
    if not m:
        return None
    try:
        b64 = m.group(1).replace('-', '+').replace('_', '/')
        while len(b64) % 4:
            b64 += '='
        decoded = base64.b64decode(b64).decode('utf-8', errors='replace')
        if decoded.startswith('http'):
            return decoded
        try:
            data = json.loads(decoded)
            return data.get('url') or data.get('r')
        except json.JSONDecodeError:
            return None
    except Exception:
        return None


def find_article_urls(html: str, plain_text: str) -> list[dict]:
    """Extract and rank article URLs from email content. Returns list of {url, score}."""
    url_scores: dict[str, int] = {}

    # Extract from HTML href attributes
    if html:
        for m in re.finditer(r'href=["\']?(https?://[^"\'>\s]+)', html, re.IGNORECASE):
            url = clean_url(m.group(1))
            if url:
                url_scores[url] = max(url_scores.get(url, 0), score_url(url))

    # Extract from plain text
    if plain_text:
        for m in re.finditer(r'https?://[^\s<>"{}|\\^`\[\]()]+', plain_text):
            url = clean_url(m.group(0))
            if url:
                url_scores[url] = max(url_scores.get(url, 0), score_url(url))

    # Decode Substack redirect URLs
    for url in list(url_scores.keys()):
        if 'substack.com/redirect/' in url:
            real = decode_substack_redirect(url)
            if real:
                cleaned = clean_url(real)
                if cleaned:
                    s = score_url(cleaned)
                    if s > 0:
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
    """Process a raw email: save it, extract URLs or content, and ingest."""
    # Save raw email for replay
    ts = int(time.time())
    raw_path = EMAILS_DIR / f'email_{ts}.eml'
    raw_path.write_text(raw_text, encoding='utf-8')
    print(f'[email] Saved raw email to {raw_path.name}', flush=True)

    parsed = parse_email(raw_text)
    subject = parsed['subject']
    print(f'[email] Subject: "{subject}", from: {parsed["from"]}', flush=True)
    print(f'[email] HTML: {len(parsed["text_html"])} chars, Plain: {len(parsed["text_plain"])} chars', flush=True)

    # Strategy 1: Find article URLs
    candidates = find_article_urls(parsed['text_html'], parsed['text_plain'])
    top5 = candidates[:5]
    print(f'[email] Found {len(candidates)} candidate URLs', flush=True)
    for c in top5:
        print(f'  [{c["score"]:3d}] {c["url"][:100]}', flush=True)

    if candidates:
        top_score = candidates[0]['score']
        strong = [c for c in candidates if c['score'] >= top_score * 0.5]
        to_send = strong[:5]
        for c in to_send:
            print(f'[email] Ingesting URL: {c["url"][:100]}', flush=True)
            run_ingest(c['url'], subject, '', '', '', 'email')
        return

    # Strategy 2: Extract clean body text
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
        proc = subprocess.run(
            ['claude', '-p', prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            result['status'] = 'failed'
            result['error'] = f'claude exited with code {proc.returncode}: {proc.stderr[:500]}'
        else:
            output = proc.stdout.strip()
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

    except subprocess.TimeoutExpired:
        result['status'] = 'failed'
        result['error'] = 'Explore research timed out after 5 minutes'
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
        proc = subprocess.run(
            ['claude', '-p', prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            result['status'] = 'failed'
            result['error'] = f'claude exited with code {proc.returncode}: {proc.stderr[:500]}'
        else:
            output = proc.stdout.strip()
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

    except subprocess.TimeoutExpired:
        result['status'] = 'failed'
        result['error'] = 'Research timed out after 5 minutes'
    except json.JSONDecodeError as e:
        result['status'] = 'failed'
        result['error'] = f'JSON parse error: {e}'
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[research] {request_id} -> {result["status"]}')


def run_ingest(url: str, title: str, content: str, selected_text: str, comment: str, source: str):
    """Import a URL via import_url.py, optionally with pre-extracted content."""
    ingest_id = f'ingest_{int(time.time())}_{hash(url) % 10000:04d}'
    log_path = INGEST_DIR / f'{ingest_id}.json'

    log_entry = {
        'id': ingest_id,
        'status': 'processing',
        'url': url,
        'title': title,
        'source': source,
        'requested_at': int(time.time() * 1000),
    }
    log_path.write_text(json.dumps(log_entry, indent=2))

    content_file = None
    try:
        cmd = [VENV_PYTHON, str(SCRIPTS_DIR / 'import_url.py'), url, '--tag', 'manual']

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


class ResearchHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Petrarca-Token')

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

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

        thread = threading.Thread(target=process_email, args=(raw_email,), daemon=True)
        thread.start()

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'queued', 'source': 'email'}).encode())

    def _handle_ingest(self):
        # Verify auth token
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

        body = json.loads(self.rfile.read(content_length))

        url = body.get('url', '').strip()
        if not url:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing required field: url'}).encode())
            return

        title = body.get('title', '')
        content = body.get('content', '')
        selected_text = body.get('selected_text', '')
        comment = body.get('comment', '')
        source = body.get('source', 'unknown')

        thread = threading.Thread(
            target=run_ingest,
            args=(url, title, content, selected_text, comment, source),
            daemon=True,
        )
        thread.start()

        print(f'[ingest] Queued: {url[:80]} (source={source})')

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'queued', 'url': url}).encode())

    def _handle_ingest_book(self):
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

        body = json.loads(self.rfile.read(content_length))
        book_path = body.get('path', '').strip()
        if not book_path:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing required field: path'}).encode())
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

    def do_POST(self):
        if self.path == '/ingest':
            return self._handle_ingest()
        if self.path == '/ingest-email':
            return self._handle_ingest_email()
        if self.path == '/ingest-book':
            return self._handle_ingest_book()

        if self.path not in ('/research', '/research/explore'):
            self.send_error(404)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

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

    def do_GET(self):
        if self.path == '/research/results':
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

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(f'[http] {args[0]}')


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), ResearchHandler)
    print(f'Research server listening on port {PORT}')
    print(f'Results directory: {RESULTS_DIR}')
    server.serve_forever()
