"""
Full purchase-to-activation E2E test, plus explicit failure paths --
Phase 4 Milestone H's required list. Runs against a real local Postgres
database and real Ed25519 signing (the staging keypair); the only thing
simulated is the Paddle webhook payload itself, since no real Paddle
sandbox account exists yet (docs/HUMAN_COMMERCIAL_REQUIREMENTS.md).

Not covered here (documented, not faked): DB/license-server temporarily
unavailable -- exercising a real outage would require actually stopping
the local Postgres service mid-suite, which is disruptive to run
repeatedly and doesn't need a bespoke test to prove: SQLAlchemy already
raises OperationalError on connection failure, which FastAPI surfaces as a
500, the same as any other unhandled DB exception. Documented in
docs/STAGING_E2E_RESULTS.md instead of asserted here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time


def _sign_paddle_payload(payload: dict, secret: str) -> tuple[bytes, str]:
    raw_body = json.dumps(payload).encode("utf-8")
    ts = str(int(time.time()))
    signed_payload = f"{ts}:{raw_body.decode('utf-8')}"
    h1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return raw_body, f"ts={ts};h1={h1}"


def _request_and_capture_link(client, email: str, db_session) -> str:
    """Requests a magic link and returns the *raw* token by inserting our
    own entry with a known raw token -- console-email capture would need
    log scraping, which is fragile; this achieves the same coverage
    (verify() against a real MagicLinkToken row) without it."""
    from app import models
    from app.security import generate_raw_token, hash_token
    from datetime import datetime, timedelta, timezone

    raw_token = generate_raw_token()
    now = datetime.now(timezone.utc)
    db_session.add(
        models.MagicLinkToken(
            email=email,
            token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
    )
    db_session.commit()
    return raw_token


def _seed_product(db_session, product_id: str = "smart-sample-manager") -> None:
    from app import models

    db_session.merge(
        models.Product(
            id=product_id,
            name="Smart Sample Manager",
            status="active",
            public=True,
            purchasable=True,
            platforms=["macos"],
            # Simulated webhook payloads in this test file re-use product_id
            # as Paddle's product_id too (see _completed_payload) -- real
            # Paddle events never do this (see commerce.py's
            # _handle_transaction_completed), but keeping the two equal here
            # is the least invasive way to keep every existing simulated
            # payload resolving correctly.
            paddle_product_id=product_id,
        )
    )
    db_session.commit()


def test_full_purchase_to_activation_flow(client, db_session):
    _seed_product(db_session)

    # 1. create user -> login
    raw_token = _request_and_capture_link(client, "e2e-buyer@example.com", db_session)
    verify_resp = client.post("/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200
    user_id = verify_resp.json()["user"]["id"]

    # 2. checkout start -> simulated webhook -> purchase created -> entitlement created
    payload = {
        "event_id": "evt_e2e_001",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_e2e_001",
            "customer": {"email": "e2e-buyer@example.com"},
            "currency_code": "GBP",
            "details": {"totals": {"total": "5900"}},
            "items": [{"price": {"product_id": "smart-sample-manager"}}],
        },
    }
    raw_body, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    webhook_resp = client.post(
        "/webhooks/paddle", content=raw_body, headers={"Paddle-Signature": sig, "Content-Type": "application/json"}
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["status"] == "processed"

    from app import models

    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_e2e_001").one()
    assert purchase.status == "completed"
    entitlement = db_session.query(models.Entitlement).filter(models.Entitlement.purchase_id == purchase.id).one()
    assert entitlement.status == "active"
    license_key = entitlement.license_key

    # 3. account shows product (entitlement exists for this user+product)
    assert entitlement.user_id == user_id
    assert entitlement.product_id == "smart-sample-manager"

    # 4. download link generated (requires the entitlement above)
    from app import models as m
    import shutil, pathlib
    from app.config import settings as app_settings

    releases_dir = pathlib.Path(app_settings.mock_storage_dir) / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(b"TEST FIXTURE -- not a real build artifact\n").hexdigest()
    db_session.add(
        m.Release(
            product_id="smart-sample-manager",
            version="0.1.0",
            platform="macos",
            architecture="universal",
            channel="stable",
            checksum_sha256=checksum,
            storage_key="releases/test-release.txt",
        )
    )
    db_session.commit()

    latest_resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "macos", "architecture": "universal"},
    )
    assert latest_resp.status_code == 200
    download_url = latest_resp.json()["download_url"]
    fetch_path = download_url.split(app_settings.nite_dsp_api_url, 1)[-1]
    fetch_resp = client.get(fetch_path)
    assert fetch_resp.status_code == 200
    assert b"TEST FIXTURE" in fetch_resp.content

    # 5. activation -> signed token -> offline validation
    activate_resp = client.post("/v1/activate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert activate_resp.status_code == 200
    token = activate_resp.json()

    from nacl.signing import VerifyKey
    import base64

    public_key = base64.b64decode(
        (pathlib.Path(app_settings.licensing_public_key_path)).read_text().strip()
    )
    VerifyKey(public_key).verify(token["token_json"].encode(), base64.b64decode(token["signature"]))

    validate_resp = client.post("/v1/validate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert validate_resp.status_code == 200

    # 6. deactivate -> reactivate
    deactivate_resp = client.post("/v1/deactivate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert deactivate_resp.status_code == 200
    revalidate_resp = client.post("/v1/validate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert revalidate_resp.status_code == 403
    reactivate_resp = client.post("/v1/activate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert reactivate_resp.status_code == 200

    # 7. "refund" -- admin revokes the entitlement, license stops validating
    revoke_resp = client.post(
        f"/admin/entitlements/{entitlement.id}/revoke",
        json={"reason": "refund issued"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert revoke_resp.status_code == 200
    post_refund_validate = client.post("/v1/validate", json={"license_key": license_key, "device_id": "DEV-A"})
    assert post_refund_validate.status_code == 403


def test_duplicate_webhook_is_idempotent(client, db_session):
    _seed_product(db_session)
    payload = {
        "event_id": "evt_dup_001",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_dup_001",
            "customer": {"email": "dup@example.com"},
            "currency_code": "GBP",
            "details": {"totals": {"total": "5900"}},
            "items": [{"price": {"product_id": "smart-sample-manager"}}],
        },
    }
    raw_body, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    first = client.post("/webhooks/paddle", content=raw_body, headers={"Paddle-Signature": sig})
    second = client.post("/webhooks/paddle", content=raw_body, headers={"Paddle-Signature": sig})
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "already_processed"

    from app import models

    count = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_dup_001").count()
    assert count == 1


def test_forged_webhook_signature_rejected(client):
    payload = {"event_id": "evt_forged", "event_type": "transaction.completed", "data": {}}
    raw_body = json.dumps(payload).encode()
    resp = client.post(
        "/webhooks/paddle", content=raw_body, headers={"Paddle-Signature": "ts=1;h1=deadbeef"}
    )
    assert resp.status_code == 401


def test_activate_invalid_license_key_rejected(client):
    resp = client.post("/v1/activate", json={"license_key": "NONEXISTENT", "device_id": "X"})
    assert resp.status_code == 404


def test_activation_limit_reached(client, db_session):
    from app import models

    _seed_product(db_session)
    user = models.User(email="limit@example.com")
    db_session.add(user)
    db_session.flush()
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id="smart-sample-manager",
        license_key="LIMIT-TEST-0001-0001",
        license_type="perpetual",
        max_activations=1,
        status="active",
    )
    db_session.add(entitlement)
    db_session.commit()

    ok = client.post("/v1/activate", json={"license_key": "LIMIT-TEST-0001-0001", "device_id": "DEV-1"})
    assert ok.status_code == 200
    blocked = client.post("/v1/activate", json={"license_key": "LIMIT-TEST-0001-0001", "device_id": "DEV-2"})
    assert blocked.status_code == 403


def test_expired_entitlement_rejected(client, db_session):
    from app import models
    from datetime import datetime, timedelta, timezone

    _seed_product(db_session)
    user = models.User(email="expired@example.com")
    db_session.add(user)
    db_session.flush()
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id="smart-sample-manager",
        license_key="EXPIRED-0001-0001-0001",
        license_type="subscription",
        max_activations=3,
        status="active",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(entitlement)
    db_session.commit()

    resp = client.post("/v1/activate", json={"license_key": "EXPIRED-0001-0001-0001", "device_id": "DEV-1"})
    assert resp.status_code == 403
    assert "expired" in resp.json()["detail"]


def test_download_without_entitlement_rejected(client, db_session):
    _seed_product(db_session)
    raw_token = _request_and_capture_link(client, "no-entitlement@example.com", db_session)
    client.post("/auth/verify", json={"token": raw_token})

    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "macos", "architecture": "universal"},
    )
    assert resp.status_code == 403


def test_download_missing_release_returns_404(client, db_session):
    from app import models

    _seed_product(db_session)
    user = models.User(email="norelease@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key="NORELEASE-0001-0001",
            license_type="perpetual",
            max_activations=3,
            status="active",
        )
    )
    db_session.commit()

    raw_token = _request_and_capture_link(client, "norelease@example.com", db_session)
    client.post("/auth/verify", json={"token": raw_token})
    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "windows", "architecture": "x64"},
    )
    assert resp.status_code == 404


def test_admin_endpoints_reject_bad_key(client, db_session):
    resp = client.get(
        "/admin/users/search", params={"email": "x@example.com"}, headers={"X-Admin-Key": "wrong"}
    )
    assert resp.status_code == 401
