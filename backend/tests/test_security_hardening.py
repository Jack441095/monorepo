"""
Regression tests for the Tier-0 security hardening batch (R1):

- possession proof on /v1/deactivate (licensing.py)
- Paddle webhook timestamp freshness + non-UTF-8 body handling (commerce.py)
- lazy signing-key load (D-3)
- rate limiter per-client keying behind proxies + bounded memory (D-5)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException


def _sign_paddle_payload(payload: dict, secret: str, ts: int | None = None) -> tuple[bytes, str]:
    raw_body = json.dumps(payload).encode("utf-8")
    ts = str(int(time.time())) if ts is None else str(ts)
    signed_payload = f"{ts}:{raw_body.decode('utf-8')}"
    h1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return raw_body, f"ts={ts};h1={h1}"


def _seed_entitlement_and_activation(db_session, license_key: str, device_id: str = "DEV-SEC-1"):
    from app import models

    db_session.merge(
        models.Product(
            id="security-hardening-test",
            name="Security Hardening Test",
            status="active",
            public=True,
            purchasable=True,
            platforms=["macos"],
            paddle_product_id="security-hardening-test",
        )
    )
    user = models.User(email="sec-hardening@example.com")
    db_session.add(user)
    db_session.flush()
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id="security-hardening-test",
        license_key=license_key,
        license_type="perpetual",
        max_activations=3,
        status="active",
    )
    db_session.add(entitlement)
    db_session.flush()
    db_session.add(models.Activation(entitlement_id=entitlement.id, machine_id=device_id))
    db_session.commit()
    return entitlement


def _activate(client, license_key: str, device_id: str) -> dict:
    resp = client.post("/v1/activate", json={"license_key": license_key, "device_id": device_id})
    assert resp.status_code == 200
    return resp.json()


# --- possession proof on /v1/deactivate -------------------------------------


def test_deactivate_without_possession_proof_is_rejected(client, db_session):
    license_key = "SEC-NO-PROOF-0001"
    _seed_entitlement_and_activation(db_session, license_key)

    # Proof fields omitted entirely -> schema rejection.
    resp = client.post("/v1/deactivate", json={"license_key": license_key, "device_id": "DEV-SEC-1"})
    assert resp.status_code == 422

    # Proof supplied but garbage -> explicit 403, never a silent success.
    resp = client.post(
        "/v1/deactivate",
        json={
            "license_key": license_key,
            "device_id": "DEV-SEC-1",
            "activation_token_json": "{}",
            "activation_signature": "AAAA",
        },
    )
    assert resp.status_code == 403


def test_deactivate_token_for_another_device_is_rejected(client, db_session):
    license_key = "SEC-DEV-SWAP-01"
    _seed_entitlement_and_activation(db_session, license_key, device_id="DEV-SEC-A")

    token = _activate(client, license_key, "DEV-SEC-B")

    resp = client.post(
        "/v1/deactivate",
        json={
            "license_key": license_key,
            "device_id": "DEV-SEC-A",
            "activation_token_json": token["token_json"],
            "activation_signature": token["signature"],
        },
    )
    assert resp.status_code == 403
    # DEV-SEC-A must still validate.
    validate = client.post("/v1/validate", json={"license_key": license_key, "device_id": "DEV-SEC-A"})
    assert validate.status_code == 200


def test_deactivate_with_valid_possession_proof_succeeds(client, db_session):
    license_key = "SEC-VALID-00001"
    _seed_entitlement_and_activation(db_session, license_key)

    token = _activate(client, license_key, "DEV-SEC-1")

    resp = client.post(
        "/v1/deactivate",
        json={
            "license_key": license_key,
            "device_id": "DEV-SEC-1",
            "activation_token_json": token["token_json"],
            "activation_signature": token["signature"],
        },
    )
    assert resp.status_code == 200
    validate = client.post("/v1/validate", json={"license_key": license_key, "device_id": "DEV-SEC-1"})
    assert validate.status_code == 403


# --- Paddle webhook hardening ------------------------------------------------


def _completed_payload() -> dict:
    return {
        "event_id": "evt_sec_001",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_sec_001",
            "customer": {"email": "sec-webhook@example.com"},
            "currency_code": "GBP",
            "details": {"totals": {"total": "5900"}},
            "items": [{"price": {"product_id": "security-hardening-test"}}],
        },
    }


def test_webhook_rejects_stale_timestamp(client, db_session):
    from test_e2e import _seed_product

    _seed_product(db_session)
    raw_body, _ = _sign_paddle_payload(_completed_payload(), "test-webhook-secret")
    # Re-sign the identical body with a timestamp 10 days in the past: the
    # signature is valid, but the replay window must reject it.
    stale_ts = int(time.time()) - 10 * 24 * 60 * 60
    signed_payload = f"{stale_ts}:{raw_body.decode('utf-8')}"
    h1 = hmac.new(b"test-webhook-secret", signed_payload.encode(), hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhooks/paddle",
        content=raw_body,
        headers={"Paddle-Signature": f"ts={stale_ts};h1={h1}"},
    )
    assert resp.status_code == 400
    assert "replay" in resp.json()["detail"].lower()


def test_webhook_rejects_non_utf8_body(client):
    bad_body = b"\xff\xfe\x00garbage"
    ts = str(int(time.time()))
    signed_payload = f"{ts}:{bad_body.decode('latin-1')}"
    h1 = hmac.new(b"test-webhook-secret", signed_payload.encode(), hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhooks/paddle",
        content=bad_body,
        headers={"Paddle-Signature": f"ts={ts};h1={h1}"},
    )
    assert resp.status_code == 400  # was an unhandled 500 before the fix


# --- D-3: signing key is lazy ------------------------------------------------


def test_signing_key_is_lazy_not_import_time():
    from app import licensing

    assert hasattr(licensing._get_signing_key, "cache_clear")
    key = licensing._get_signing_key()  # must not raise, key exists in test env
    licensing._get_signing_key.cache_clear()  # a later call reloads lazily
    assert licensing._get_signing_key() is not key  # re-created on demand


# --- D-5: rate limiter keying + bounded memory --------------------------------


class _FakeRequest:
    def __init__(self, headers: dict, host: str | None = "10.0.0.1"):
        self.headers = headers
        self.client = type("C", (), {"host": host})() if host else None


def test_rate_limit_keys_on_forwarded_for_not_shared_bucket():
    from app import rate_limit as rl

    rl.reset_all()
    dep = rl.rate_limit("sec-test-bucket", max_requests=2, window_seconds=60)

    proxied = _FakeRequest({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})
    dep(proxied)
    dep(proxied)
    with pytest.raises(HTTPException) as exc:
        dep(proxied)
    assert exc.value.status_code == 429

    # A different client behind the same proxy must not share the bucket.
    dep(_FakeRequest({"x-forwarded-for": "5.6.7.8"}))

    # No header at all -> falls back to socket peer.
    dep(_FakeRequest({}, host="9.9.9.9"))
    rl.reset_all()


def test_rate_limit_buckets_are_bounded_and_stale_ones_swept(monkeypatch):
    from app import rate_limit as rl

    rl.reset_all()
    monkeypatch.setattr(rl, "MAX_TRACKED_BUCKETS", 8)
    dep = rl.rate_limit("sec-flood", max_requests=5, window_seconds=1)

    # 1. Simulate a flood of distinct (spoofed) client keys.
    for i in range(50):
        dep(_FakeRequest({"x-forwarded-for": f"flood-{i}"}))
        assert len(rl._windows) <= 8, "bucket dict grew past its hard cap"

    # 2. Stale buckets are evicted, live ones are not: advance the clock.
    real_monotonic = time.monotonic
    monkeypatch.setattr(rl.time, "monotonic", lambda: real_monotonic() + 120)
    dep(_FakeRequest({"x-forwarded-for": "after-sweep"}))
    monkeypatch.setattr(rl.time, "monotonic", real_monotonic)
    assert ("sec-flood", "after-sweep") in rl._windows
    rl.reset_all()

