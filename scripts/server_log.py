"""Shared server-side event logger for Petrarca pipeline scripts."""
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path('/opt/petrarca/data/logs')


def log_server_event(event: str, **kwargs):
    """Append a server-side event to the daily interaction log."""
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
