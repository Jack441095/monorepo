"""R-07 synthetic webhook robustness (no secrets, no live calls).

Exercises /webhooks/paddle with HMAC-signed synthetic payloads using the
conftest test secret. Covers: duplicate delivery idempotency, malformed
bodies, missing event_id, tampered signatures, unknown catalog items.
"""
from __future__ import annotations

import pytest

from test_e2e import _seed_product, _sign_paddle_payload  # noqa: F401  (re-use proven helpers)


def _completed(order_no: str, event_no: str, email: str = "r07-buyer@example.com") -> dict:
    return {
        "event_id": event_no,
        "event_type": "transaction.completed",
        "data": {
            "id": order_no,
            "customer": {"email": email},
            "currency_code": "GBP",
            "details": {"totals": {"total": "5900"}},
            "items": [{"price": {"product_id": "smart-sample-manager"}}],
        },
    }


def test_duplicate_delivery_creates_single_purchase(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_dup", "evt_r07_dup")
    raw, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    headers = {"Paddle-Signature": sig, "Content-Type": "application/json"}
    first = client.post("/webhooks/paddle", content=raw, headers=headers)
    second = client.post("/webhooks/paddle", content=raw, headers=headers)
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


@pytest.mark.xfail(reason="R-07 finding: signed-but-malformed JSON returns 500 (retry storm) instead of 400; fix prepared, dirty-tree gated")
def test_malformed_json_is_rejected_400_not_retried():
    from fastapi.testclient import TestClient

    from app.main import app

    raw = b"{not valid json"
    _, sig = _sign_paddle_payload({"ignored": True}, "test-webhook-secret")
    # NOTE: signature is over a different body on purpose is NOT what we do
    # here -- we sign the actual garbage bytes below via the same scheme.
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    h1 = hmac.new(b"test-webhook-secret", f"{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    resp = TestClient(app).post(
        "/webhooks/paddle",
        content=raw,
        headers={"Paddle-Signature": f"ts={ts};h1={h1}", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_missing_event_id_is_400(client):
    payload = _completed("txn_r07_noevt", "evt_r07_noevt")
    del payload["event_id"]
    raw, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/paddle", content=raw,
        headers={"Paddle-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_tampered_signature_is_rejected(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_tamper", "evt_r07_tamper")
    raw, _ = _sign_paddle_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/paddle", content=raw,
        headers={"Paddle-Signature": "ts=1;h1=deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code in (400, 401)


def test_unknown_catalog_item_rejected_without_retry(client, db_session):
    _seed_product(db_session)
    payload = _completed("txn_r07_unknown", "evt_r07_unknown")
    payload["data"]["items"] = [{"price": {"product_id": "no-such-product"}}]
    raw, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    resp = client.post(
        "/webhooks/paddle", content=raw,
        headers={"Paddle-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_unknown_catalog_item"
