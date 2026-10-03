"""R-07 synthetic webhook robustness (no secrets, no live calls).

Exercises /webhooks/stripe with HMAC-signed synthetic payloads using the
conftest test secret. Covers: duplicate delivery idempotency, malformed
bodies, missing event_id, tampered signatures, unknown catalog items.
"""
from __future__ import annotations

import time
import pytest

from test_e2e import _seed_product, _sign_stripe_payload  # noqa: F401  (re-use proven helpers)


def _completed(order_no: str, event_no: str, email: str = "r07-buyer@example.com") -> dict:
    from tests.test_commerce_catalog import _completed_payload
    return _completed_payload(event_no, order_no, email=email)


def test_duplicate_delivery_creates_single_purchase(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_dup", "evt_r07_dup")
    raw, sig = _sign_stripe_payload(payload, "test-webhook-secret")
    headers = {"Stripe-Signature": sig, "Content-Type": "application/json"}
    first = client.post("/webhooks/stripe", content=raw, headers=headers)
    second = client.post("/webhooks/stripe", content=raw, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "already_processed"

    from app import models

    assert (
        db_session.query(models.Purchase)
        .filter(models.Purchase.provider_order_id == "txn_r07_dup")
        .count()
    ) == 1
    assert (
        db_session.query(models.Entitlement)
        .join(models.Purchase, models.Entitlement.purchase_id == models.Purchase.id)
        .filter(models.Purchase.provider_order_id == "txn_r07_dup")
        .count()
    ) == 1


def test_malformed_json_is_rejected_400_not_retried():
    from fastapi.testclient import TestClient

    from app.main import app

    raw = b"{not valid json"
    # A valid signature must not turn malformed JSON into a retryable server error.
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    h1 = hmac.new(b"test-webhook-secret", f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    resp = TestClient(app).post(
        "/webhooks/stripe",
        content=raw,
        headers={"Stripe-Signature": f"t={ts},v1={h1}", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_missing_event_id_is_400(client):
    payload = _completed("txn_r07_noevt", "evt_r07_noevt")
    del payload["id"]
    raw, sig = _sign_stripe_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/stripe", content=raw,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_tampered_signature_is_rejected(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_tamper", "evt_r07_tamper")
    raw, _ = _sign_stripe_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/stripe", content=raw,
        headers={"Stripe-Signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code in (400, 401)


def test_unknown_catalog_item_rejected_without_retry(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_unknown", "evt_r07_unknown")
    payload["data"]["object"]["metadata"]["product_id"] = "no-such-product"
    raw, sig = _sign_stripe_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/stripe", content=raw,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_unknown_catalog_item"


def test_secret_rotation_accepts_any_valid_v1_signature(client, db_session):
    _seed_product(db_session)
    raw, signature = _sign_stripe_payload(_completed("cs_rotation", "evt_rotation"), "test-webhook-secret")
    response = client.post("/webhooks/stripe", content=raw, headers={
        "Stripe-Signature": signature + ",v1=" + "0" * 64,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "processed"


@pytest.mark.parametrize("signature", [
    "t=" + "9" * 310 + ",v1=" + "0" * 64,
    f"t={int(time.time())},v1=é",
])
def test_malformed_signature_values_are_verification_errors(signature):
    # Numeric overflow and non-ASCII signatures used to bypass the 400 path.
    from app.stripe_commerce import _verify_stripe_signature, StripeWebhookVerificationError

    with pytest.raises(StripeWebhookVerificationError):
        _verify_stripe_signature(b"{}", signature)
