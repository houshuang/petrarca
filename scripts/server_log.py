"""Shared server-side event logger for Petrarca pipeline scripts.

Dual-layer logging (modeled on Alif's interaction_logger.py):
- JSONL files: /opt/petrarca/data/logs/interactions_YYYY-MM-DD.jsonl (audit trail)
- SQLite: interaction_log table (for queries/analytics)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get('LOG_DIR', '/opt/petrarca/data/logs'))


def log_server_event(event: str, **kwargs):
    """Append a server-side event to the daily JSONL interaction log."""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f'interactions_{today}.jsonl'
        entry = {'ts': ts, 'event': event, 'source': 'server', **kwargs}
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass


def log_interaction(event: str, item_id: str = None, item_type: str = None,
                    score: str = None, session_id: str = None,
                    response_ms: int = None, card_type: str = None,
                    domain: str = None, node_id: str = None,
                    node_title: str = None, **extra):
    """Dual-layer logging: SQLite interaction_log + JSONL audit trail.

    Never raises — logging must never fail the main request.
    """
    # Layer 1: JSONL (always)
    log_server_event(event, item_id=item_id, item_type=item_type,
                     score=score, session_id=session_id,
                     response_ms=response_ms, card_type=card_type,
                     domain=domain, node_id=node_id, node_title=node_title,
                     **extra)
    # Layer 2: SQLite (for queries)
    try:
        from db import get_connection
        conn = get_connection()
        conn.execute(
            '''INSERT INTO interaction_log
               (event, item_id, item_type, score, session_id, response_ms,
                card_type, domain, node_id, node_title, extra)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (event, item_id, item_type, score, session_id, response_ms,
             card_type, domain, node_id, node_title,
             json.dumps(extra) if extra else None))
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_client_events(body: str) -> int:
    """Process a batch of client-side JSONL events. Returns lines written."""
    lines_written = 0
    for line in body.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            event = entry.pop('event', 'unknown')
            session_id = entry.pop('session_id', None)
            item_id = entry.pop('question_id', None) or entry.pop('item_id', None)
            score = entry.pop('result', None) or entry.pop('score', None)
            response_ms = None
            if 'time_seconds' in entry:
                response_ms = int(entry.pop('time_seconds') * 1000)
            card_type = entry.pop('card_type', None) or entry.pop('type', None)
            domain = entry.pop('domain', None)
            node_title = entry.pop('node_title', None)
            node_id = entry.pop('node_id', None)
            # Remove ts — we use server time for consistency
            entry.pop('ts', None)
            log_interaction(
                event, item_id=item_id, item_type=entry.pop('item_type', None),
                score=score, session_id=session_id, response_ms=response_ms,
                card_type=card_type, domain=domain, node_id=node_id,
                node_title=node_title, **entry)
            lines_written += 1
        except (json.JSONDecodeError, Exception):
            pass
    return lines_written
