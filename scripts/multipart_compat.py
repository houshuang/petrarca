"""Multipart form-data parser (Python 3.13+ removed stdlib `cgi`). FieldStorage-like API."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass


@dataclass
class FormField:
    """Enough of cgi.FieldStorage for Petrarca handlers."""

    filename: str
    _data: bytes

    def __post_init__(self) -> None:
        self.file: io.BytesIO | None
        if self._data or self.filename:
            self.file = io.BytesIO(self._data)
        else:
            self.file = None


class MultipartForm:
    def __init__(self, fields: dict[str, FormField]) -> None:
        self._fields = fields

    def __contains__(self, name: str) -> bool:
        return name in self._fields

    def __getitem__(self, name: str) -> FormField:
        return self._fields[name]

    def getvalue(self, name: str, default: str = '') -> str:
        if name not in self._fields:
            return default
        f = self._fields[name]
        if f.file is None:
            return default
        f.file.seek(0)
        raw = f.file.read()
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1')


def parse_multipart(body: bytes, content_type: str) -> MultipartForm:
    m = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type, re.I)
    if not m:
        raise ValueError('multipart boundary missing')
    boundary = (m.group(1) or m.group(2) or '').encode('ascii')
    if not boundary:
        raise ValueError('multipart boundary empty')

    boundary_marker = b'--' + boundary
    # Drop optional preamble (e.g. leading CRLF) before first boundary — RN fetch polyfill
    idx = body.find(boundary_marker)
    if idx < 0:
        raise ValueError('multipart boundary not found in body')
    body = body[idx:]

    sep = boundary_marker + b'\r\n'
    sep_alt = boundary_marker + b'\n'
    end = boundary_marker + b'--'

    if body.startswith(sep):
        inner = body[len(sep) :]
    elif body.startswith(sep_alt):
        inner = body[len(sep_alt) :]
        sep = sep_alt
    else:
        raise ValueError('multipart: expected CRLF after opening boundary')

    if inner.endswith(end + b'\r\n'):
        inner = inner[: -len(end + b'\r\n')]
    elif inner.endswith(end + b'\n'):
        inner = inner[: -len(end + b'\n')]
    elif inner.endswith(end):
        inner = inner[: -len(end)]

    raw_parts = inner.split(sep)
    fields: dict[str, FormField] = {}

    for part in raw_parts:
        if not part.strip():
            continue
        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            header_end = part.find(b'\n\n')
            if header_end == -1:
                continue
            sep_len = 2
        else:
            sep_len = 4

        headers_blob = part[:header_end].decode('utf-8', errors='replace')
        payload = part[header_end + sep_len :]
        if payload.endswith(b'\r\n'):
            payload = payload[:-2]
        elif payload.endswith(b'\n'):
            payload = payload[:-1]

        name: str | None = None
        filename = ''
        for line in headers_blob.split('\r\n'):
            if not line.strip():
                continue
            low = line.lower()
            if not low.startswith('content-disposition:'):
                continue
            nm = re.search(r'\bname="([^"]+)"', line) or re.search(r'\bname=([^;\s]+)', line)
            fnm = re.search(r'\bfilename="([^"]*)"', line) or re.search(r'\bfilename=([^;\s]+)', line)
            if nm:
                name = nm.group(1)
            if fnm:
                filename = fnm.group(1) or ''

        if not name:
            continue
        fields[name] = FormField(filename=filename, _data=payload)

    return MultipartForm(fields)
