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
