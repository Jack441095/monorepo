from __future__ import annotations

from fastapi import Response

from app import main
from app.storage import StorageError


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        return None


class _HealthyEngine:
    def connect(self):
        return _Connection()


class _HealthyStorage:
    def readiness(self):
        return None


def test_ready_reports_database_and_storage(monkeypatch):
    monkeypatch.setattr(main, "engine", _HealthyEngine())
    monkeypatch.setattr(main, "get_storage", lambda: _HealthyStorage())
    response = Response()

    result = main.ready(response)

    assert response.status_code == 200
    assert result["status"] == "ok"
    assert result["database"] is True
    assert result["storage"] is True
    assert result["storage_backend"] == main.settings.storage_backend
    assert result["storage_durable"] is (main.settings.storage_backend == "s3")
    assert result["email_provider"] == main.settings.email_provider
    assert result["email_provider_configured"] is True
    assert result["email_deliverable"] is (main.settings.email_provider == "resend")
    assert result["checkout_enabled"] is main.settings.paddle_checkout_enabled
    assert result["staging_customer_rehearsal"] is main.settings.staging_customer_rehearsal
    assert result["staging_customer_rehearsal_ready"] is True


def test_ready_returns_503_when_storage_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "engine", _HealthyEngine())

    def unavailable_storage():
        raise StorageError("test-only storage failure")

    monkeypatch.setattr(main, "get_storage", unavailable_storage)
    response = Response()

    result = main.ready(response)

    assert response.status_code == 503
    assert result["status"] == "unavailable"
    assert result["database"] is True
    assert result["storage"] is False
    assert result["email_provider_configured"] is True


def test_ready_returns_503_when_customer_rehearsal_gate_is_not_ready(monkeypatch):
    monkeypatch.setattr(main, "engine", _HealthyEngine())
    monkeypatch.setattr(main, "get_storage", lambda: _HealthyStorage())
    monkeypatch.setattr(main.settings, "staging_customer_rehearsal", True)
    monkeypatch.setattr(main.settings, "storage_backend", "local")
    monkeypatch.setattr(main.settings, "email_provider", "console")
    monkeypatch.setattr(main.settings, "resend_api_key", "")
    response = Response()

    result = main.ready(response)

    assert response.status_code == 503
    assert result["status"] == "unavailable"
    assert result["storage"] is True
    assert result["storage_durable"] is False
    assert result["email_deliverable"] is False
    assert result["staging_customer_rehearsal"] is True
    assert result["staging_customer_rehearsal_ready"] is False
