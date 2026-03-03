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

import json
import os
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

RESULTS_DIR = Path(os.environ.get('RESEARCH_RESULTS_DIR', '/opt/petrarca/research-results'))
PORT = int(os.environ.get('RESEARCH_PORT', '8090'))

RESULTS_DIR.mkdir(parents=True, exist_ok=True)


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


class ResearchHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/research':
            self.send_error(404)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))

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
