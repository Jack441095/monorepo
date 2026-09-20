"""Body-limit tests for Thursday HTTP server (2026-09-18 audit fix).

Chunked bodies have no Content-Length: the old _read_json returned {}
and silently ignored the body (up to gigabytes). Slow senders could
hold a server thread forever on rfile.read(). Both now capped.
"""

from __future__ import annotations

import io
import socket
from unittest.mock import MagicMock

from thursday import server as srv


def _handler(headers: dict, body: bytes = b"", read_side_effect=None):
    handler = MagicMock()
    handler.headers = headers
    if read_side_effect is not None:
        rfile = MagicMock()
        rfile.read.side_effect = read_side_effect
    else:
        rfile = io.BytesIO(body)
    handler.rfile = rfile
    conn = MagicMock()
    conn.gettimeout.return_value = None
    handler.connection = conn
    errors: list = []
    handler._send_error.side_effect = lambda *a: errors.append(a)
    handler._errors = errors
    return handler


def _read(handler):
    return srv.Handler._read_json(handler)


def test_chunked_oversize_body_rejected_413():
    big = b"x" * (srv.MAX_REQUEST_BODY_BYTES + 1)
    h = _handler({"Transfer-Encoding": "chunked"}, body=big)
    assert _read(h) is None
    assert h._errors and h._errors[0][0] == 413


def test_chunked_small_json_body_parsed():
    h = _handler({"Transfer-Encoding": "chunked"}, body=b'{"question": "hi"}')
    assert _read(h) == {"question": "hi"}
    assert not h._errors


def test_content_length_oversize_rejected_413():
    h = _handler({"Content-Length": str(srv.MAX_REQUEST_BODY_BYTES + 1)})
    assert _read(h) is None
    assert h._errors and h._errors[0][0] == 413


def test_slow_body_returns_408():
    def slow(n):
        raise socket.timeout("timed out")

    h = _handler({"Content-Length": "100"}, read_side_effect=slow)
    assert _read(h) is None
    assert h._errors and h._errors[0][0] == 408


def test_empty_body_still_returns_empty_dict():
    h = _handler({})
    assert _read(h) == {}
