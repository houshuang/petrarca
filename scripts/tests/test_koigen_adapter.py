"""Focused tests for Petrarca's narrow Koigen HTTP bridge.

The full research server imports databases, LLM clients, and creates host directories
at module import time.  These tests exercise the standalone adapter with in-memory
streams and a fake Koigen module instead.

Run: cd scripts && python3 -m pytest tests/test_koigen_adapter.py -v
"""

import ast
import io
import json
import sys
from email.message import Message
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import koigen_adapter as adapter  # noqa: E402


def request_headers(*pairs: tuple[str, str]) -> Message:
    headers = Message()
    for name, value in pairs:
        headers.add_header(name, value)
    return headers


class FakeKoigen:
    def __init__(self):
        self.calls = []

    def handle_ingest(self, token, body):
        self.calls.append(("browser", token, body))
        if not token:
            return 401, {"error": "bad token"}
        return 202, {"status": "spooled"}

    def handle_ingest_email(
        self, token, body, x_from="", x_to="", x_authenticated=""
    ):
        self.calls.append((
            "email", token, body,
            {
                "x_from": x_from,
                "x_to": x_to,
                "x_authenticated": x_authenticated,
            },
        ))
        if not token:
            return 401, {"error": "bad token"}
        if not x_authenticated:
            return 403, {"error": "authenticated sender required"}
        return 202, {"status": "spooled", "kind": "email"}

    def handle_approve_post(self, body):
        self.calls.append(("approve-post", body))
        return 200, "text/html; charset=utf-8", b"post accepted"

    def handle_approve(self, path):
        self.calls.append(("approve-get", path))
        return 200, "text/html; charset=utf-8", b"confirm"


@pytest.mark.parametrize("value", ["", "-1", "+1", " 1", "1 ", "1, 1", "1.0"])
def test_invalid_content_length_is_rejected_without_reading(value):
    stream = io.BytesIO(b"payload")
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(
            request_headers(("Content-Length", value)), stream, 100
        )
    assert caught.value.status == 400
    assert stream.tell() == 0


def test_missing_content_length_is_411_without_reading():
    stream = io.BytesIO(b"payload")
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(request_headers(), stream, 100)
    assert caught.value.status == 411
    assert stream.tell() == 0


def test_duplicate_content_length_is_rejected_without_reading():
    stream = io.BytesIO(b"payload")
    headers = request_headers(("Content-Length", "7"), ("Content-Length", "7"))
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(headers, stream, 100)
    assert caught.value.status == 400
    assert stream.tell() == 0


def test_pathological_digit_only_content_length_is_rejected_without_int_conversion():
    stream = io.BytesIO(b"payload")
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(
            request_headers(("Content-Length", "9" * 5000)), stream, 100
        )
    assert caught.value.status == 400
    assert stream.tell() == 0


def test_short_leading_zero_content_length_remains_valid_decimal():
    body = adapter.read_bounded_body(
        request_headers(("Content-Length", "0003")), io.BytesIO(b"abc"), 3
    )
    assert body == b"abc"


@pytest.mark.parametrize("transfer_encoding", ["chunked", "identity", ""])
def test_any_transfer_encoding_is_rejected_without_reading(transfer_encoding):
    stream = io.BytesIO(b"payload")
    headers = request_headers(
        ("Transfer-Encoding", transfer_encoding), ("Content-Length", "7")
    )
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(headers, stream, 100)
    assert caught.value.status == 400
    assert stream.tell() == 0


def test_body_must_reach_declared_length():
    with pytest.raises(adapter.RequestBodyError) as caught:
        adapter.read_bounded_body(
            request_headers(("Content-Length", "8")), io.BytesIO(b"short"), 100
        )
    assert caught.value.status == 400


def test_exact_limit_is_accepted_and_reader_does_not_overread():
    stream = io.BytesIO(b"abcNEXT")
    body = adapter.read_bounded_body(
        request_headers(("Content-Length", "3")), stream, 3
    )
    assert body == b"abc"
    assert stream.read() == b"NEXT"


@pytest.mark.parametrize(
    ("path", "maximum"),
    [
        (adapter.BROWSER_INGEST_PATH, 1024 * 1024),
        (adapter.EMAIL_INGEST_PATH, 5 * 1024 * 1024),
        (adapter.APPROVE_PATH, 16 * 1024),
    ],
)
def test_each_route_rejects_its_limit_plus_one_without_reading(path, maximum):
    stream = io.BytesIO(b"not consumed")
    response = adapter.dispatch_post(
        path,
        request_headers(("Content-Length", str(maximum + 1))),
        stream,
        FakeKoigen(),
    )
    assert response.status == 413
    assert response.close_connection is True
    assert stream.tell() == 0


def test_browser_ingest_dispatches_bounded_bytes_and_token():
    fake = FakeKoigen()
    body = b'{"url":"https://example.test/event"}'
    response = adapter.dispatch_post(
        adapter.BROWSER_INGEST_PATH,
        request_headers(
            ("Content-Length", str(len(body))),
            ("X-Koigen-Token", "browser-secret"),
        ),
        io.BytesIO(body),
        fake,
    )
    assert fake.calls == [("browser", "browser-secret", body)]
    assert response.status == 202
    assert json.loads(response.body) == {"status": "spooled"}


def test_email_ingest_passes_authenticated_envelope_headers_verbatim():
    fake = FakeKoigen()
    body = b"From: sender@example.test\r\n\r\nhello"
    response = adapter.dispatch_post(
        adapter.EMAIL_INGEST_PATH,
        request_headers(
            ("Content-Length", str(len(body))),
            ("X-Koigen-Token", "mail-secret"),
            ("X-From", "sender@example.test"),
            ("X-To", "clip@example.test"),
            ("X-Koigen-Mail-Authenticated", "cloudflare-forwardable"),
        ),
        io.BytesIO(body),
        fake,
    )
    assert response.status == 202
    assert fake.calls == [(
        "email",
        "mail-secret",
        body,
        {
            "x_from": "sender@example.test",
            "x_to": "clip@example.test",
            "x_authenticated": "cloudflare-forwardable",
        },
    )]


def test_duplicate_security_headers_fail_closed_before_backend_authentication():
    fake = FakeKoigen()
    body = b"From: sender@example.test\r\n\r\nhello"
    response = adapter.dispatch_post(
        adapter.EMAIL_INGEST_PATH,
        request_headers(
            ("Content-Length", str(len(body))),
            ("X-Koigen-Token", "one"),
            ("X-Koigen-Token", "two"),
            ("X-From", "sender@example.test"),
            ("X-Koigen-Mail-Authenticated", "cloudflare-forwardable"),
            ("X-Koigen-Mail-Authenticated", "forged-second-value"),
        ),
        io.BytesIO(body),
        fake,
    )
    assert response.status == 401
    assert fake.calls[0][1] == ""
    assert fake.calls[0][3]["x_authenticated"] == ""


def test_approve_post_has_its_own_html_response_path():
    fake = FakeKoigen()
    body = b"id=capture-1&a=approve"
    response = adapter.dispatch_post(
        adapter.APPROVE_PATH,
        request_headers(("Content-Length", str(len(body)))),
        io.BytesIO(body),
        fake,
    )
    assert fake.calls == [("approve-post", body)]
    assert response.status == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert response.body == b"post accepted"


def test_approve_framing_error_is_html_and_closes_connection():
    response = adapter.dispatch_post(
        adapter.APPROVE_PATH, request_headers(), io.BytesIO(), FakeKoigen()
    )
    assert response.status == 411
    assert response.content_type == "text/html; charset=utf-8"
    assert response.close_connection is True


def test_approve_get_preserves_signed_query_string():
    fake = FakeKoigen()
    path = "/koigen/approve?id=capture-1&a=approve&t=signed"
    response = adapter.dispatch_get(path, fake)
    assert fake.calls == [("approve-get", path)]
    assert response.status == 200
    assert response.body == b"confirm"


@pytest.mark.parametrize(
    "path",
    [
        "/koigen/approve/extra",
        "/koigen/approve/",
        "/other",
        "/ingest-email",
        "http://example.test/koigen/approve",
        "//[malformed",
        "http://[",
        "/koigen/approve#fragment",
    ],
)
def test_unrelated_paths_are_not_claimed(path):
    assert adapter.post_route(path) is None
    assert adapter.is_approve_get(path) is False


def test_expected_routes_allow_query_strings_without_accepting_near_prefixes():
    assert adapter.post_route("/koigen/ingest?source=clipper") == adapter.BROWSER_INGEST_PATH
    assert adapter.is_approve_get("/koigen/approve?id=signed") is True
    assert adapter.post_route("/koigen/ingest-extra") is None


def test_adapter_response_headers_are_length_bound_uncacheable_and_unframeable():
    response = adapter.AdapterResponse(
        200, "text/html; charset=utf-8", b"confirm", close_connection=True
    )
    headers = dict(adapter.response_headers(response))
    assert headers["Content-Length"] == str(len(b"confirm"))
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Connection"] == "close"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 99, "content_type": "text/html; charset=utf-8", "body": b"x"},
        {"status": 200, "content_type": "text/html\r\nX-Evil: yes", "body": b"x"},
        {"status": 200, "content_type": "text/html; charset=utf-8", "body": "x"},
    ],
)
def test_adapter_response_rejects_invalid_backend_contract(kwargs):
    with pytest.raises((TypeError, ValueError)):
        adapter.AdapterResponse(**kwargs)


def _class_method_source(method_name: str) -> str:
    source = (SCRIPT_DIR / "research-server.py").read_text()
    tree = ast.parse(source)
    handler = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ResearchHandler"
    )
    method = next(
        node for node in handler.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )
    return ast.get_source_segment(source, method) or ""


def test_research_server_wiring_is_thin_and_does_not_revive_legacy_email_reroute():
    post = _class_method_source("do_POST")
    get = _class_method_source("do_GET")
    send = _class_method_source("_send_koigen_response")
    cors = _class_method_source("_send_cors_headers")
    legacy_email = _class_method_source("_handle_ingest_email")

    assert "koigen_adapter.post_route" in post
    assert "koigen_adapter.is_approve_get" in get
    assert "koigen_adapter.response_headers" in send
    assert "X-Koigen-Token" in cors
    assert "koigen" not in legacy_email.casefold()
