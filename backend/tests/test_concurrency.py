"""
Concurrency tests -- Phase 5.5, Sections 50-51. Not synthetic load testing;
the goal is preserving commercial invariants (never exceed max_activations,
never double-process a webhook) under genuinely concurrent requests, each
using its own real database connection (FastAPI's `get_db` dependency opens
a fresh session per request, so parallel TestClient calls from separate
threads exercise real Postgres-level locking, not an in-process mock).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time

from app import models


def _seed_entitlement(db_session, license_key: str, max_activations: int, email: str) -> None:
    from app.database import Base  # noqa: F401 -- ensures metadata is loaded

    db_session.merge(
        models.Product(
            id="smart-sample-manager",
            name="Smart Sample Manager",
            status="active",
            public=True,
            purchasable=True,
            platforms=["macos"],
        )
    )
    db_session.commit()
    user = models.User(email=email)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key=license_key,
            license_type="perpetual",
            max_activations=max_activations,
            status="active",
        )
    )
    db_session.commit()


def test_concurrent_activation_never_exceeds_limit(client, db_session):
    _seed_entitlement(db_session, "RACE-TEST-0001-0001", max_activations=3, email="race@example.com")

    def activate(device_id: str):
        return client.post(
            "/v1/activate", json={"license_key": "RACE-TEST-0001-0001", "device_id": device_id}
        )

    device_ids = [f"DEVICE-{i}" for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(activate, device_ids))

    successes = [r for r in responses if r.status_code == 200]
    rejections = [r for r in responses if r.status_code == 403]

    assert len(successes) == 3, f"expected exactly 3 successful activations, got {len(successes)}"
    assert len(rejections) == 7

    from app.database import SessionLocal

    verify_db = SessionLocal()
    entitlement = (
        verify_db.query(models.Entitlement)
        .filter(models.Entitlement.license_key == "RACE-TEST-0001-0001")
        .one()
    )
    active_count = (
        verify_db.query(models.Activation)
        .filter(
            models.Activation.entitlement_id == entitlement.id,
            models.Activation.deactivated_at.is_(None),
        )
        .count()
    )
    verify_db.close()
    assert active_count == 3, f"database has {active_count} active activations for a 3-seat license"


def test_concurrent_duplicate_webhook_never_double_processes(client, db_session):
    import hashlib
    import hmac
    import json

    db_session.merge(
        models.Product(
            id="smart-sample-manager",
            name="Smart Sample Manager",
            status="active",
            public=True,
            purchasable=True,
            platforms=["macos"],
            paddle_product_id="smart-sample-manager",
        )
    )
    db_session.commit()

    payload = {
        "event_id": "evt_concurrent_001",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_concurrent_001",
            "customer": {"email": "concurrent-buyer@example.com"},
            "currency_code": "GBP",
            "details": {"totals": {"total": "5900"}},
            "items": [{"price": {"product_id": "smart-sample-manager"}}],
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    secret = "test-webhook-secret"
    # Timestamp must be inside the replay-protection window (commerce.py
    # rejects signed-but-stale deliveries); use the current wall clock.
    ts = str(int(time.time()))
    signed_payload = f"{ts}:{raw_body.decode('utf-8')}"
    h1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    headers = {"Paddle-Signature": f"ts={ts};h1={h1}", "Content-Type": "application/json"}

    def send_webhook(_):
        return client.post("/webhooks/paddle", content=raw_body, headers=headers)

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(send_webhook, range(5)))

    assert all(r.status_code == 200 for r in responses)

    from app.database import SessionLocal

    verify_db = SessionLocal()
    purchase_count = (
        verify_db.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_concurrent_001").count()
    )
    entitlement_count = (
        verify_db.query(models.Entitlement)
        .join(models.Purchase, models.Entitlement.purchase_id == models.Purchase.id)
        .filter(models.Purchase.provider_order_id == "txn_concurrent_001")
        .count()
    )
    verify_db.close()
    assert purchase_count == 1, f"expected exactly 1 purchase from 5 concurrent identical webhooks, got {purchase_count}"
    assert entitlement_count == 1
