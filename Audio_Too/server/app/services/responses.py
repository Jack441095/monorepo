"""Typed service-layer result objects.

Every route handler in Website returns one of these three types
instead of calling send_json / send_bytes / send_file directly.
This gives callers a typed boundary, version negotiation, and
centralised error serialisation without coupling to the HTTP handler.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ApiError:
    """Structured API error suitable for machine and human readers."""

    def __init__(self, code, message, details=None, *, status=400):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status


@dataclass
class Response:
    """JSON response body returned by a service function."""
    payload: dict
    status: int = 200
    cookie: str | None = None

    def json_bytes(self):
        return json.dumps(self.payload, indent=2).encode("utf-8")


@dataclass
class FileResponse:
    """Stream a file from disk."""
    file_path: Path
    content_type: str
    filename: str = ""
    status: int = 200


@dataclass
class BytesResponse:
    """Raw bytes with a content type."""
    body: bytes
    content_type: str
    filename: str = ""
    status: int = 200


def ok(payload, *, cookie=None):
    return Response(payload=payload, status=200, cookie=cookie)

def created(payload, *, cookie=None):
    return Response(payload=payload, status=201, cookie=cookie)

def not_found(error_message):
    return Response(payload={"error": error_message}, status=404)

def bad_request(error_message):
    return Response(payload={"error": error_message}, status=400)

def forbidden(error_message="Access denied."):
    return Response(payload={"error": error_message}, status=403)

def unauthorised(error_message="Authentication required."):
    return Response(payload={"error": error_message}, status=401)

def payload_too_large(max_mb):
    return Response(payload={"error": f"Request body exceeds {max_mb} MB limit."}, status=413)

def server_error(request_id=""):
    return Response(payload={"error": "The request could not be completed.", "error_id": request_id}, status=500)


class Services:
    """Callable wrapper that maps typed results onto an HTTP handler."""
    def __init__(self, handler):
        self._handler = handler

    def send(self, result):
        if isinstance(result, Response):
            self._handler.send_json(result.status, result.payload, cookie=result.cookie)
        elif isinstance(result, FileResponse):
            self._handler.send_file(result.file_path, result.content_type, filename=result.filename)
        elif isinstance(result, BytesResponse):
            self._handler.send_bytes(result.status, result.body, result.content_type, filename=result.filename)
        else:
            self._handler.send_json(500, {"error": "Internal server error (unexpected service result)."})
