"""Authenticated API contract discovery routes."""

from __future__ import annotations

from urllib.parse import urlparse

from app.api_contract import openapi_document


def handle_api_contract_get(handler, full_path: str) -> bool:
    if urlparse(full_path).path != "/api/v1/openapi.json":
        return False
    handler.send_json(200, openapi_document())
    return True
