"""
Paraphrase router tests -- products/nite-paraphrase, Phase 2.

The router proxies a streaming engine service; these tests stub that
service with httpx.MockTransport so nothing depends on a live Ollama.
The shared `settings` instance (config.py) is mutated via monkeypatch
since the product is disabled by default in tests, exactly as it is in
every environment until the staging gate flips it on.
"""
from __future__ import annotations

import json

import httpx

ENGINE_SSE = (
    'data: {"type":"token","token":"This "}\n\n'
    'data: {"type":"token","token":"reads "}\n\n'
    'data: {"type":"done","stats":{"tokens":2,"seconds":0.1}}\n\n'
)


def _stub_engine(monkeypatch, body: str = ENGINE_SSE, status: int = 200, error: Exception | None = None):
    def _handler(request: httpx.Request) -> httpx.Response:
        if error is not None:
            raise error
        return httpx.Response(
            status,
            text=body,
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        "app.paraphrase._client_factory",
        lambda *args, **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
    )


def _enable(monkeypatch):
    import app.config

    monkeypatch.setattr(app.config.settings, "paraphrase_enabled", True)


def _post(client, **overrides):
    payload = {"voice": "essay", "text": "Some sample student prose."}
    payload.update(overrides)
    return client.post("/v1/paraphrase", json=payload)


def test_disabled_product_returns_404_without_touching_engine(client):
    response = _post(client)
    assert response.status_code == 404


def test_enabled_product_streams_tokens_and_stats(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch)
    response = _post(client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "This " in body
    assert "reads " in body
    assert '"type":"done"' in body


def test_free_tier_allows_three_then_429(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch)
    for _ in range(3):
        assert _post(client).status_code == 200
    assert _post(client).status_code == 429


def test_unlock_header_removes_limit(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch)
    import app.config

    monkeypatch.setattr(app.config.settings, "paraphrase_unlock_token", "paid-token")
    for _ in range(5):
        response = client.post(
            "/v1/paraphrase",
            json={"voice": "essay", "text": "unlocked prose"},
            headers={"X-Paraphrase-Token": "paid-token"},
        )
        assert response.status_code == 200


def test_engine_unreachable_returns_503(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch, error=httpx.ConnectError("connection refused"))
    response = _post(client)
    assert response.status_code == 503


def test_engine_nonzero_status_is_propagated(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch, status=500)
    response = _post(client)
    assert response.status_code == 500


def test_invalid_register_is_rejected(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch)
    response = _post(client, voice="podcast")
    assert response.status_code == 422


def test_overlong_text_is_rejected(client, monkeypatch):
    _enable(monkeypatch)
    _stub_engine(monkeypatch)
    response = _post(client, text="x" * 8001)
    assert response.status_code == 422


def test_engine_receives_body_and_bearer_token(client, monkeypatch):
    import app.config

    _enable(monkeypatch)
    monkeypatch.setattr(app.config.settings, "paraphrase_service_token", "srv-secret")
    received: dict = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        received["authorization"] = request.headers.get("Authorization", "")
        received["voice"] = json.loads(request.content)["voice"]
        return httpx.Response(200, text=ENGINE_SSE, headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(
        "app.paraphrase._client_factory",
        lambda *args, **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(_handler), **kwargs),
    )
    assert _post(client).status_code == 200
    assert received["authorization"] == "Bearer srv-secret"
    assert received["voice"] == "essay"


def test_success_closes_engine_client(client, monkeypatch):
    _enable(monkeypatch)
    clients = []

    def factory(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=ENGINE_SSE))
        engine_client = httpx.AsyncClient(transport=transport, **kwargs)
        clients.append(engine_client)
        return engine_client

    monkeypatch.setattr("app.paraphrase._client_factory", factory)
    assert _post(client).status_code == 200
    assert len(clients) == 1
    assert clients[0].is_closed


def test_forward_cleanup_on_disconnect_and_stream_error():
    import anyio
    from app.paraphrase import _forward

    class Response:
        closed = False

        async def aiter_lines(self):
            yield 'data: {"type":"token","token":"partial"}'
            raise httpx.ReadError("interrupted")

        async def aclose(self):
            await anyio.sleep(0)
            self.closed = True

    class Client:
        closed = False

        async def aclose(self):
            await anyio.sleep(0)
            self.closed = True

    async def check():
        import pytest

        response, engine_client = Response(), Client()
        stream = _forward(engine_client, response)
        await anext(stream)
        with anyio.CancelScope() as scope:
            scope.cancel()
            await stream.aclose()
        assert response.closed and engine_client.closed

        response, engine_client = Response(), Client()
        stream = _forward(engine_client, response)
        await anext(stream)
        with pytest.raises(httpx.ReadError):
            await anext(stream)
        assert response.closed and engine_client.closed

    anyio.run(check)
