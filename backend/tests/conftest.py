"""
Test fixtures -- runs against a dedicated `nitedsp_test` Postgres database
(never `nitedsp_staging`, so tests never pollute or depend on staging data).
Migrations run via Alembic for real before each test session, exactly the
same way they'd run against staging/production -- this is not a sqlite/mock
substitute for the real schema.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

os.environ["DATABASE_URL"] = "postgresql+psycopg2://localhost/nitedsp_test"
os.environ["PADDLE_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["LICENSING_PRIVATE_KEY_PATH"] = str(
    Path(__file__).parent.parent / "staging_keys" / "licensing_signing_key.private"
)
os.environ["LICENSING_PUBLIC_KEY_PATH"] = str(
    Path(__file__).parent.parent / "staging_keys" / "licensing_signing_key.public"
)
os.environ["MOCK_STORAGE_DIR"] = str(Path(__file__).parent / "fixtures" / "mock_storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND_DIR = Path(__file__).parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    from app.database import engine

    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE users, products, purchases, entitlements, activations, "
                "trials, releases, downloads, webhook_events, magic_link_tokens, "
                "admin_audit_log RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def db_session():
    from app.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()
