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
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
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

CHAT_DIR = Path(os.environ.get('CHAT_DIR', '/opt/petrarca/data/chats'))
NOTES_DIR = Path(os.environ.get('NOTES_DIR', '/opt/petrarca/data/notes'))
AUDIO_DIR = Path(os.environ.get('AUDIO_DIR', '/opt/petrarca/data/audio'))
LOG_DIR = Path(os.environ.get('LOG_DIR', '/opt/petrarca/data/logs'))
ARTICLES_PATH = Path(os.environ.get('ARTICLES_PATH', '/opt/petrarca/data/articles.json'))
SCRAPE_REPORTS_PATH = Path(os.environ.get('SCRAPE_REPORTS_PATH', '/opt/petrarca/data/scrape_reports.json'))

SONIOX_API_KEY = os.environ.get('SONIOX_API_KEY', '557c7c5a86a2f5b8fa734ddbbe179f0f21fd342c762768c9af4f4ffff8c58e1f')
SONIOX_BASE_URL = 'https://api.soniox.com/v1'

TWIKIT_COOKIES_DIR = Path.home() / '.config' / 'twikit'
TWIKIT_COOKIES_PATH = TWIKIT_COOKIES_DIR / 'cookies.json'

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
INGEST_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)
CHAT_DIR.mkdir(parents=True, exist_ok=True)
NOTES_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


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

    except subprocess.TimeoutExpired:
        result['status'] = 'failed'
        result['error'] = 'Explore batch timed out after 5 minutes'
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
    """Use Gemini to extract actionable intents from a voice note transcript."""
    import uuid
    from gemini_llm import call_llm

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
        raw = call_llm(prompt, max_tokens=1000)
        if not raw:
            return []
        # Strip markdown code fences if present
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            if raw.endswith('```'):
                raw = raw[:-3].strip()

        json_start = raw.find('[')
        json_end = raw.rfind(']') + 1
        if json_start >= 0 and json_end > json_start:
            actions = json.loads(raw[json_start:json_end])
            for action in actions:
                action['id'] = f'act_{uuid.uuid4().hex[:8]}'
                action['status'] = 'pending'
            return actions
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
    except Exception as e:
        note['status'] = 'failed'
        note['error'] = str(e)
        note_path.write_text(json.dumps(note, indent=2))
        print(f'[note] {note_id} transcription failed: {e}', flush=True)


def run_topic_research(request_id: str, topic: str, context: str, article_titles: list[str]):
    """Background: use Gemini with search grounding to find articles on a topic, then ingest them."""
    from gemini_llm import call_with_search

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
        output = call_with_search(prompt)
        if not output:
            result['status'] = 'failed'
            result['error'] = 'No response from Gemini'
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
                result['error'] = 'Could not parse JSON from Gemini response'
                result['raw_output'] = output[:1000]
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    result_path.write_text(json.dumps(result, indent=2))
    print(f'[topic_research] {request_id} -> {result["status"]}', flush=True)


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


class ResearchHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Petrarca-Token')

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

        thread = threading.Thread(target=process_email, args=(raw_email,), daemon=True)
        thread.start()

        self.send_response(202)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'queued', 'source': 'email'}).encode())

    def _handle_note(self):
        """Receive audio file + metadata, transcribe in background, store note."""
        import cgi
        content_type = self.headers.get('Content-Type', '')

        if 'multipart/form-data' in content_type:
            # Parse multipart form data
            environ = {
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
                'CONTENT_LENGTH': self.headers.get('Content-Length', '0'),
            }
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ)

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

        self._send_json_response(202, {
            'status': 'queued',
            'url': url,
            'ingest_id': ingest_id,
            'article_id': article_id,
        })

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

    def do_POST(self):
        if self.path == '/chat':
            return self._handle_chat()
        if self.path == '/note':
            return self._handle_note()
        if self.path == '/research/topic':
            return self._handle_topic_research()
        if self.path == '/ingest':
            return self._handle_ingest()
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

        # --- Pipeline events ---
        pipeline_events = [e for e in raw_events if e.get('source') == 'pipeline']
        pipeline_events.sort(key=lambda e: e.get('ts', ''))
        pipeline_groups = []
        for ev in pipeline_events:
            ev_ts = ev.get('ts', '')
            merged = False
            for group in pipeline_groups:
                last_ts = group[-1].get('ts', '')
                try:
                    t1 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                    t2 = datetime.fromisoformat(ev_ts.replace('Z', '+00:00'))
                    if abs((t2 - t1).total_seconds()) <= 900:  # 15 min window
                        group.append(ev)
                        merged = True
                        break
                except (ValueError, TypeError):
                    pass
            if not merged:
                pipeline_groups.append([ev])

        for group in pipeline_groups:
            event_names = [e.get('event', '') for e in group]
            completed = 'pipeline_complete' in event_names

            # Collect any counts from meta
            meta = {}
            for ev in group:
                for k, v in ev.items():
                    if k not in ('ts', 'event', 'source', 'session_id'):
                        meta[k] = v

            # Build subtitle from events
            step_labels = []
            for name in event_names:
                label = name.replace('pipeline_', '').replace('_', ' ').title()
                if label not in step_labels:
                    step_labels.append(label)
            subtitle = ' · '.join(step_labels)

            subtype = 'processed' if completed else 'in_progress'
            timeline.append({
                'id': f'evt_{group[0]["ts"]}_pipeline',
                'type': 'system',
                'subtype': subtype,
                'ts': group[0].get('ts'),
                'title': 'Content refresh completed' if completed else 'Content refresh running',
                'subtitle': subtitle if subtitle else None,
                'meta': meta if meta else None,
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

    def do_GET(self):
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


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), ResearchHandler)
    print(f'Research server listening on port {PORT}')
    print(f'Results directory: {RESULTS_DIR}')
    server.serve_forever()
