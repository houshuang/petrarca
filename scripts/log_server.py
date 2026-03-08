#!/usr/bin/env python3
"""Minimal HTTP server for collecting app interaction logs.

Listens on port 8091 and accepts POST /log with JSONL body.
Appends to /opt/petrarca/data/logs/interactions_YYYY-MM-DD.jsonl.

Usage:
    python3 scripts/log_server.py
"""

import json
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

LOG_DIR = Path("/opt/petrarca/data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class LogHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/log":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 1_000_000:  # 1MB max
            self.send_response(413)
            self.end_headers()
            return

        body = self.rfile.read(content_length).decode("utf-8", errors="replace")

        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = LOG_DIR / f"interactions_{today}.jsonl"

        # Append each line
        lines_written = 0
        with open(log_file, "a") as f:
            for line in body.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        json.loads(line)  # validate JSON
                        f.write(line + "\n")
                        lines_written += 1
                    except json.JSONDecodeError:
                        pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "lines": lines_written}).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logging


def main():
    port = int(os.environ.get("LOG_PORT", "8091"))
    server = HTTPServer(("0.0.0.0", port), LogHandler)
    print(f"Log server listening on :{port}", file=sys.stderr)
    print(f"Logs → {LOG_DIR}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
