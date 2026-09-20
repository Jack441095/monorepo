"""Behavior tests for static and signed invoice delivery routes."""

from __future__ import annotations

from pathlib import Path

from app.routes import invoice_routes, static_routes
from app.invoice_tokens import make_invoice_token


class Handler:
    def __init__(self, *, authenticated: bool = False) -> None:
        self.authenticated = authenticated
        self.status = 0
        self.body = b""
        self.content_type = ""
        self.filename = ""
        self.file_path: Path | None = None
        self.cache_control = ""

    def authorized(self) -> bool:
        return self.authenticated

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        filename: str = "",
    ) -> None:
        self.status = status
        self.body = body
        self.content_type = content_type
        self.filename = filename

    def send_file(
        self,
        path: Path,
        content_type: str,
        *,
        filename: str = "",
        cache_control: str = "no-store",
    ) -> None:
        self.status = 200
        self.file_path = path
        self.content_type = content_type
        self.filename = filename
        self.cache_control = cache_control


def test_static_route_map_streams_file_and_rejects_traversal(tmp_path, monkeypatch) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    index = static_root / "index.html"
    index.write_text("public site", encoding="utf-8")
    monkeypatch.setattr(static_routes, "STATIC_ROOT", static_root)
    monkeypatch.setattr(static_routes, "PORTFOLIO_ROOT", tmp_path / "portfolio")

    handler = Handler()
    assert static_routes.handle_static_get(handler, "/")
    assert handler.status == 200
    assert handler.file_path == index
    assert handler.content_type == "text/html"
    assert handler.cache_control == "public, max-age=300"

    assert static_routes.static_target("/../../private.txt") is None


def test_invoice_html_requires_token_and_escapes_client_data(monkeypatch) -> None:
    invoice = {
        "id": "inv-1",
        "date": "2026-06-29",
        "client": "<script>alert(1)</script>",
        "service": "Mixing",
        "hours": 2,
        "rate": 50,
        "total": 100,
        "status": "Draft",
    }
    monkeypatch.setattr(invoice_routes, "list_records", lambda table: [invoice])

    unauthorized = Handler()
    assert invoice_routes.handle_invoice_get(unauthorized, "/invoice/inv-1")
    assert unauthorized.status == 401

    token = make_invoice_token("inv-1")
    authorized = Handler()
    assert invoice_routes.handle_invoice_get(
        authorized, f"/invoice/inv-1?token={token}"
    )
    assert authorized.status == 200
    assert authorized.content_type == "text/html; charset=utf-8"
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in authorized.body
    assert b"<script>alert(1)</script>" not in authorized.body
