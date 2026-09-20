"""Tests for the KENN HTTP server index hot-reload endpoint."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn" / "kenn"))

import server  # noqa: E402


class FakeHandler:
    def __init__(self, path: str) -> None:
        self.path = path
        self.status = 0
        self.payload = {}
        self.headers = {}

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def enforce_rate_limit(self, _scope: str) -> bool:
        return True


@patch("kenn.core.chat_retrieval.warm_index")
@patch("kenn.retrieval.retrieval.unload_embedding_index")
@patch("kenn.core.chat_retrieval.load_terms")
@patch("kenn.core.chat_retrieval.load_chunks")
def test_reload_index_endpoint_clears_cache_and_warms(
    mock_load_chunks, mock_load_terms, mock_unload_embedding, mock_warm_index
) -> None:
    # Set up cache_clear mocks on the lru_cache decorated functions
    mock_load_chunks.cache_clear = MagicMock()
    mock_load_terms.cache_clear = MagicMock()

    handler = FakeHandler("/api/admin/reload-index")
    server.Handler.do_GET(handler)

    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert "Index hot-reloaded successfully" in handler.payload["message"]

    # Verify reload steps executed in order
    mock_unload_embedding.assert_called_once()
    mock_load_chunks.cache_clear.assert_called_once()
    mock_load_terms.cache_clear.assert_called_once()
    mock_warm_index.assert_called_once()
