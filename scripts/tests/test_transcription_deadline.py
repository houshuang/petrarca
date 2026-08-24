"""Focused wall-clock and cleanup checks for Soniox transcription."""

from __future__ import annotations

import ast
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SERVER = SCRIPTS_DIR / "research-server.py"
NGINX_TEMPLATE = SCRIPTS_DIR / "nginx-petrarca-companion.conf.template"


def _transcription_namespace(clock):
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    wanted_assignments = {
        "SONIOX_TRANSCRIPTION_DEADLINE_SECONDS",
        "SONIOX_CLEANUP_RESERVE_SECONDS",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted_assignments
            for target in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "_soniox_request_timeout",
            "transcribe_on_server",
        }:
            nodes.append(node)
    namespace = {
        "Path": Path,
        "SONIOX_API_KEY": "not-a-real-key",
        "SONIOX_BASE_URL": "https://soniox.invalid/v1",
        "time": clock,
    }
    exec(compile(ast.Module(nodes, type_ignores=[]), str(SERVER), "exec"), namespace)
    return namespace


class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TranscriptionDeadlineTests(unittest.TestCase):
    def test_total_budget_has_large_margin_below_nginx(self):
        namespace = _transcription_namespace(_Clock())
        template = NGINX_TEMPLATE.read_text(encoding="utf-8")
        nginx_timeout = float(re.search(r"proxy_read_timeout (\d+)s", template).group(1))
        transcription_timeout = namespace["SONIOX_TRANSCRIPTION_DEADLINE_SECONDS"]
        self.assertLessEqual(transcription_timeout, nginx_timeout - 30)

    def test_request_timeout_never_exceeds_remaining_monotonic_budget(self):
        clock = _Clock()
        namespace = _transcription_namespace(clock)
        timeout = namespace["_soniox_request_timeout"](
            8.0, connect_cap=10, read_cap=30
        )
        self.assertLess(sum(timeout), 8.0)
        clock.now = 7.6
        with self.assertRaises(TimeoutError):
            namespace["_soniox_request_timeout"](
                8.0, connect_cap=10, read_cap=30
            )

    def test_polling_timeout_still_attempts_both_provider_cleanups(self):
        clock = _Clock()
        namespace = _transcription_namespace(clock)
        requests = types.ModuleType("requests")
        commonplace_capture = types.ModuleType("commonplace_capture")
        commonplace_capture.audio_file_details = lambda _name: (".m4a", "audio/mp4")
        calls = {"post": 0, "deletes": []}

        def spend(timeout, maximum):
            self.assertIsInstance(timeout, tuple)
            self.assertEqual(len(timeout), 2)
            self.assertGreater(timeout[0], 0)
            self.assertGreater(timeout[1], 0)
            clock.now += min(maximum, sum(timeout))

        def post(_url, *, timeout, **_kwargs):
            calls["post"] += 1
            spend(timeout, 4.0)
            if calls["post"] == 1:
                return _Response({"id": "file-1"})
            return _Response({"id": "transcription-1"})

        def get(_url, *, timeout, **_kwargs):
            spend(timeout, 25.0)
            return _Response({"status": "processing"})

        def delete(url, *, timeout, **_kwargs):
            spend(timeout, 6.0)
            calls["deletes"].append(url.rsplit("/v1/", 1)[-1])
            return _Response({})

        requests.post = post
        requests.get = get
        requests.delete = delete

        with tempfile.NamedTemporaryFile(suffix=".m4a") as audio:
            audio.write(b"audio")
            audio.flush()
            with patch.dict(
                sys.modules,
                {"requests": requests, "commonplace_capture": commonplace_capture},
            ):
                with self.assertRaises(TimeoutError):
                    namespace["transcribe_on_server"](Path(audio.name))

        self.assertEqual(
            calls["deletes"],
            ["transcriptions/transcription-1", "files/file-1"],
        )
        self.assertLessEqual(
            clock.now,
            namespace["SONIOX_TRANSCRIPTION_DEADLINE_SECONDS"],
        )


if __name__ == "__main__":
    unittest.main()
