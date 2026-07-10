"""Small, testable HTTP boundary for Koigen capture routes.

Petrarca hosts Koigen's capture handler, but Koigen owns parsing, authentication,
and durable spooling.  This module deliberately does only three things:

* reject ambiguous HTTP request framing before reading a body;
* enforce a fixed byte ceiling for each public route; and
* translate the accepted request into one call on ``koigen_ingest``.

It has no Petrarca imports or startup side effects, so the boundary can be tested
without importing the full research server or touching either project's state.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit


BROWSER_INGEST_PATH = "/koigen/ingest"
EMAIL_INGEST_PATH = "/koigen/ingest-email"
APPROVE_PATH = "/koigen/approve"

BROWSER_MAX_BYTES = 1024 * 1024
EMAIL_MAX_BYTES = 5 * 1024 * 1024
APPROVE_MAX_BYTES = 16 * 1024

_POST_LIMITS = {
    BROWSER_INGEST_PATH: BROWSER_MAX_BYTES,
    EMAIL_INGEST_PATH: EMAIL_MAX_BYTES,
    APPROVE_PATH: APPROVE_MAX_BYTES,
}
_DECIMAL = re.compile(r"[0-9]+\Z")
_MAX_CONTENT_LENGTH_DIGITS = 20


@dataclass(frozen=True)
class AdapterResponse:
    status: int
    content_type: str
    body: bytes
    close_connection: bool = False

    def __post_init__(self):
        if (
            isinstance(self.status, bool)
            or not isinstance(self.status, int)
            or not 100 <= self.status <= 599
        ):
            raise ValueError("adapter response status is invalid")
        if self.content_type not in {
            "application/json; charset=utf-8",
            "text/html; charset=utf-8",
        }:
            raise ValueError("adapter response content type is invalid")
        if not isinstance(self.body, bytes):
            raise TypeError("adapter response body must be bytes")


class RequestBodyError(ValueError):
    """A client framing error detected before Koigen sees the request."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _header_values(headers, name: str) -> list[str]:
    """Return every value for ``name`` from HTTPMessage or a mapping.

    ``BaseHTTPRequestHandler.headers`` preserves duplicate fields through
    ``get_all``.  Tests and other callers may use a plain mapping, so retain a
    case-insensitive fallback without silently merging duplicate list values.
    """

    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all(name)
        return [] if values is None else [str(value) for value in values]

    values: list[str] = []
    for key, value in getattr(headers, "items", lambda: ())():
        if str(key).casefold() != name.casefold():
            continue
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def header(headers, name: str) -> str:
    """Return one request header, or an empty string when absent/duplicated."""

    values = _header_values(headers, name)
    return values[0] if len(values) == 1 else ""


def read_bounded_body(headers, stream: BinaryIO, maximum: int) -> bytes:
    """Read exactly one strictly framed body of at most ``maximum`` bytes.

    Transfer coding and duplicate/ambiguous Content-Length values are rejected.
    This server does not implement chunk decoding, and accepting both mechanisms
    would create request-smuggling ambiguity between a proxy and the Python HTTP
    parser.  Framing failures must cause the caller to close the connection because
    unread client bytes remain on the socket.
    """

    if _header_values(headers, "Transfer-Encoding"):
        raise RequestBodyError(400, "Transfer-Encoding is not supported")

    lengths = _header_values(headers, "Content-Length")
    if not lengths:
        raise RequestBodyError(411, "Content-Length is required")
    if (
        len(lengths) != 1
        or len(lengths[0]) > _MAX_CONTENT_LENGTH_DIGITS
        or not _DECIMAL.fullmatch(lengths[0])
    ):
        raise RequestBodyError(400, "Content-Length is invalid")

    length = int(lengths[0])
    if length > maximum:
        raise RequestBodyError(413, "Request body is too large")

    try:
        body = stream.read(length)
    except Exception as exc:  # the socket may disappear mid-request
        raise RequestBodyError(400, "Request body could not be read") from exc
    if not isinstance(body, bytes) or len(body) != length:
        raise RequestBodyError(400, "Request body ended before Content-Length")
    return body


def _request_path(raw_path: str) -> str | None:
    """Return a safe origin-form path, rejecting malformed/absolute targets."""

    if not isinstance(raw_path, str) or not raw_path.startswith("/"):
        return None
    try:
        parsed = urlsplit(raw_path)
    except (TypeError, ValueError):
        return None
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    return parsed.path


def post_route(raw_path: str) -> str | None:
    path = _request_path(raw_path)
    return path if path in _POST_LIMITS else None


def is_approve_get(raw_path: str) -> bool:
    return _request_path(raw_path) == APPROVE_PATH


def _json_response(status: int, data: dict, *, close: bool = False) -> AdapterResponse:
    return AdapterResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode(),
        close_connection=close,
    )


def _html_error(status: int, message: str, *, close: bool = False) -> AdapterResponse:
    # Message strings are adapter-owned constants, never reflected client input.
    body = (
        "<!doctype html><meta charset=utf-8><title>Koigen</title>"
        f"<h1>Forespørselen ble avvist</h1><p>{message}</p>"
    ).encode()
    return AdapterResponse(status, "text/html; charset=utf-8", body, close)


def _framing_error(route: str, error: RequestBodyError) -> AdapterResponse:
    if route == APPROVE_PATH:
        return _html_error(error.status, error.message, close=True)
    return _json_response(error.status, {"error": error.message}, close=True)


def unavailable_response(raw_path: str, *, close: bool = False) -> AdapterResponse:
    if _request_path(raw_path) == APPROVE_PATH:
        return _html_error(503, "Tjenesten er midlertidig utilgjengelig.", close=close)
    return _json_response(503, {"error": "capture service unavailable"}, close=close)


def response_headers(response: AdapterResponse) -> tuple[tuple[str, str], ...]:
    """Security and framing headers shared by every Koigen adapter response."""

    values = [
        ("Content-Type", response.content_type),
        ("Content-Length", str(len(response.body))),
        ("Cache-Control", "no-store"),
        ("Pragma", "no-cache"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("X-Frame-Options", "DENY"),
        (
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        ),
    ]
    if response.close_connection:
        values.append(("Connection", "close"))
    return tuple(values)


def load_koigen_ingest():
    """Load the separately deployed Koigen handler from its explicit directory."""

    deploy_dir = Path(os.environ.get("KOIGEN_DEPLOY_DIR", "/opt/hvaskjer/deploy"))
    if not deploy_dir.is_dir():
        raise ImportError(f"Koigen deploy directory does not exist: {deploy_dir}")
    raw = str(deploy_dir)
    if raw not in sys.path:
        sys.path.insert(0, raw)
    return importlib.import_module("koigen_ingest")


def dispatch_post(
    raw_path: str, headers, stream: BinaryIO, koigen_ingest=None
) -> AdapterResponse | None:
    """Dispatch one Koigen POST, returning ``None`` for an unrelated path."""

    route = post_route(raw_path)
    if route is None:
        return None
    try:
        body = read_bounded_body(headers, stream, _POST_LIMITS[route])
    except RequestBodyError as exc:
        return _framing_error(route, exc)

    # Import the separately deployed application only after the host has validated
    # framing and bounded the allocation. Tests inject a lightweight fake here.
    if koigen_ingest is None:
        koigen_ingest = load_koigen_ingest()

    if route == BROWSER_INGEST_PATH:
        status, data = koigen_ingest.handle_ingest(
            header(headers, "X-Koigen-Token"), body
        )
        return _json_response(status, data)

    if route == EMAIL_INGEST_PATH:
        status, data = koigen_ingest.handle_ingest_email(
            header(headers, "X-Koigen-Token"),
            body,
            x_from=header(headers, "X-From"),
            x_to=header(headers, "X-To"),
            x_authenticated=header(headers, "X-Koigen-Mail-Authenticated"),
        )
        return _json_response(status, data)

    status, content_type, response_body = koigen_ingest.handle_approve_post(body)
    return AdapterResponse(status, content_type, response_body)


def dispatch_get(raw_path: str, koigen_ingest=None) -> AdapterResponse | None:
    """Dispatch the non-mutating approval confirmation GET."""

    if not is_approve_get(raw_path):
        return None
    if koigen_ingest is None:
        koigen_ingest = load_koigen_ingest()
    status, content_type, body = koigen_ingest.handle_approve(raw_path)
    return AdapterResponse(status, content_type, body)
