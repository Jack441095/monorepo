"""
Test fixtures -- runs against a dedicated `nitedsp_test` Postgres database
(never `nitedsp_staging`, so tests never pollute or depend on staging data).
Migrations run via Alembic for real before each test session, exactly the
same way they'd run against staging/production -- this is not a sqlite/mock
substitute for the real schema.
"""
from __future__ import annotations

import os
import atexit
import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from nacl.signing import SigningKey

os.environ["DATABASE_URL"] = "postgresql+psycopg2://localhost/nitedsp_test"
os.environ["PADDLE_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["SESSION_SECRET"] = "test-session-secret"
# Test signing keys must be a matched pair, but must never be committed or
# borrowed from staging. Create them in an OS temporary directory before any
# application module imports Settings/licensing.py, then remove them on exit.
TEST_KEY_DIR = Path(tempfile.mkdtemp(prefix="nitedsp-test-keys-"))
test_signing_key = SigningKey.generate()
test_private_key = TEST_KEY_DIR / "licensing_signing_key.private"
test_public_key = TEST_KEY_DIR / "licensing_signing_key.public"
test_private_key.write_text(base64.b64encode(bytes(test_signing_key)).decode("ascii"))
test_private_key.chmod(0o600)
test_public_key.write_text(base64.b64encode(bytes(test_signing_key.verify_key)).decode("ascii"))
atexit.register(shutil.rmtree, TEST_KEY_DIR, ignore_errors=True)
os.environ["LICENSING_PRIVATE_KEY_PATH"] = str(test_private_key)
os.environ["LICENSING_PUBLIC_KEY_PATH"] = str(test_public_key)
os.environ["MOCK_STORAGE_DIR"] = str(Path(__file__).parent / "fixtures" / "mock_storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND_DIR = Path(__file__).parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    # Use the interpreter running pytest so a fresh virtualenv does not need
    # its Scripts/bin directory separately added to PATH.
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)
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


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Keep in-process request limits isolated between test cases.

    Production rate limiting remains unchanged. Without this test-only reset,
    the shared TestClient IP accumulates authentication calls across the
    suite and later tests can receive a limiter response instead of exercising
    their intended endpoint behavior.
    """
    from app.rate_limit import reset_all

    reset_all()
    yield
    reset_all()


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
