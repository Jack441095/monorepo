"""
Catalog mapping, checkout creation, and refund recording -- the pieces of
commerce.py that only exist once real Paddle product/price IDs are
configured (docs/PADDLE_INTEGRATION_AUDIT.md). Paddle itself is still
never called for real here (no sandbox account exists yet); httpx.post is
monkeypatched for the checkout test the same way tests/test_e2e.py
simulates webhook payloads instead of receiving real ones.
"""
from __future__ import annotations

from app import models
from tests.test_e2e import _seed_product, _sign_paddle_payload


def _post_webhook(client, payload):
    raw_body, sig = _sign_paddle_payload(payload, "test-webhook-secret")
    return client.post(
        "/webhooks/paddle", content=raw_body, headers={"Paddle-Signature": sig, "Content-Type": "application/json"}
    )


def _completed_payload(event_id, txn_id, product_id="smart-sample-manager", price_id=None, email="buyer@example.com"):
    price = {"product_id": product_id}
    if price_id is not None:
        price["id"] = price_id
    return {
        "event_id": event_id,
        "event_type": "transaction.completed",
        "data": {
            "id": txn_id,
            "customer": {"email": email},
            "currency_code": "GBP",
            "details": {"totals": {"total": "500"}},
            "items": [{"price": price}],
        },
    }


def test_unknown_product_rejected_no_entitlement(client, db_session):
    # No Product row seeded at all -- product_id in the payload doesn't exist.
    resp = _post_webhook(client, _completed_payload("evt_unknown_product", "txn_unknown_product"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_unknown_catalog_item"
    assert db_session.query(models.Purchase).count() == 0
    assert db_session.query(models.Entitlement).count() == 0


def test_non_purchasable_product_rejected(client, db_session):
    db_session.add(
        models.Product(
            id="smart-sample-manager",
            name="Smart Sample Manager",
            status="active",
            public=True,
            purchasable=False,  # e.g. private beta, not yet on sale
            platforms=["macos"],
        )
    )
    db_session.commit()

    resp = _post_webhook(client, _completed_payload("evt_not_purchasable", "txn_not_purchasable"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_unknown_catalog_item"
    assert db_session.query(models.Purchase).count() == 0


def test_unknown_price_id_rejected_when_mapping_configured(client, db_session, monkeypatch):
    _seed_product(db_session)
    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "paddle_product_id", "smart-sample-manager")
    monkeypatch.setattr(commerce_settings, "paddle_intro_price_id", "pri_intro_real")
    monkeypatch.setattr(commerce_settings, "paddle_regular_price_id", "pri_regular_real")

    resp = _post_webhook(
        client,
        _completed_payload("evt_wrong_price", "txn_wrong_price", price_id="pri_totally_unmapped"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected_unknown_catalog_item"
    assert db_session.query(models.Purchase).count() == 0


def test_known_price_id_accepted_when_mapping_configured(client, db_session, monkeypatch):
    _seed_product(db_session)
    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "paddle_product_id", "smart-sample-manager")
    monkeypatch.setattr(commerce_settings, "paddle_intro_price_id", "pri_intro_real")
    monkeypatch.setattr(commerce_settings, "paddle_regular_price_id", "pri_regular_real")

    resp = _post_webhook(
        client,
        _completed_payload("evt_right_price", "txn_right_price", price_id="pri_intro_real"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_right_price").one()
    assert purchase.price_id == "pri_intro_real"


def _adjustment_payload(event_id, transaction_id, status, action="refund"):
    return {
        "event_id": event_id,
        "event_type": "adjustment.created" if status == "pending_approval" else "adjustment.updated",
        "data": {"action": action, "status": status, "transaction_id": transaction_id},
    }


def _buy_something(client, event_id, txn_id):
    _post_webhook(client, _completed_payload(event_id, txn_id))


def test_pending_adjustment_does_not_mark_refunded(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_pending_src", "txn_pending")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_pending").one()

    resp = _post_webhook(client, _adjustment_payload("evt_adj_pending", "txn_pending", "pending_approval"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    db_session.refresh(purchase)
    assert purchase.status == "completed"
    assert purchase.refunded_at is None


def test_approved_adjustment_marks_refunded_without_touching_entitlement(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_approved_src", "txn_approved")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_approved").one()
    entitlement = db_session.query(models.Entitlement).filter(models.Entitlement.purchase_id == purchase.id).one()
    assert purchase.status == "completed"
    assert entitlement.status == "active"

    # Real lifecycle: pending first, then the approving update.
    _post_webhook(client, _adjustment_payload("evt_adj_created", "txn_approved", "pending_approval"))
    resp = _post_webhook(client, _adjustment_payload("evt_adj_updated", "txn_approved", "approved"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    db_session.refresh(purchase)
    db_session.refresh(entitlement)
    assert purchase.status == "refunded"
    assert purchase.refunded_at is not None
    assert entitlement.status == "active"  # revocation stays a manual admin decision


def test_rejected_adjustment_does_not_mark_refunded(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_rejected_src", "txn_rejected")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_rejected").one()

    _post_webhook(client, _adjustment_payload("evt_adj_created2", "txn_rejected", "pending_approval"))
    resp = _post_webhook(client, _adjustment_payload("evt_adj_rejected", "txn_rejected", "rejected"))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "completed"
    assert purchase.refunded_at is None


def test_duplicate_approved_adjustment_is_idempotent(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_dup_adj_src", "txn_dup_adj")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_dup_adj").one()

    _post_webhook(client, _adjustment_payload("evt_adj_dup_1", "txn_dup_adj", "approved"))
    db_session.refresh(purchase)
    first_refunded_at = purchase.refunded_at
    assert purchase.status == "refunded"

    # A second, distinct delivery (different event_id -- not the WebhookEvent
    # dedup path) reporting the same already-approved adjustment.
    resp = _post_webhook(client, _adjustment_payload("evt_adj_dup_2", "txn_dup_adj", "approved"))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "refunded"
    assert purchase.refunded_at == first_refunded_at  # untouched by the duplicate


def test_out_of_order_pending_after_approved_does_not_regress(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_ooo_src", "txn_out_of_order")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_out_of_order").one()

    _post_webhook(client, _adjustment_payload("evt_adj_ooo_approved", "txn_out_of_order", "approved"))
    db_session.refresh(purchase)
    assert purchase.status == "refunded"
    refunded_at = purchase.refunded_at

    # A stale pending_approval delivery for the same adjustment arrives late.
    resp = _post_webhook(client, _adjustment_payload("evt_adj_ooo_pending", "txn_out_of_order", "pending_approval"))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "refunded"  # never regresses back to completed
    assert purchase.refunded_at == refunded_at


def test_refund_for_unknown_transaction_is_a_safe_no_op(client, db_session):
    resp = _post_webhook(client, _adjustment_payload("evt_refund_unknown", "txn_never_existed", "approved"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"


def test_checkout_requires_auth(client):
    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 401


def test_checkout_unconfigured_paddle_returns_503(client, db_session):
    raw_token = _login_and_get_token(client, "checkout-buyer@example.com", db_session)
    verify_resp = client.post("/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 503


def test_checkout_creates_url_when_configured(client, db_session, monkeypatch):
    raw_token = _login_and_get_token(client, "checkout-buyer-2@example.com", db_session)
    verify_resp = client.post("/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200

    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "paddle_api_key", "sandbox-key-for-test")
    monkeypatch.setattr(commerce_settings, "paddle_active_price_id", "pri_active_real")

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"checkout": {"url": "https://sandbox-checkout.paddle.com/fake"}}}

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert json["items"][0]["price_id"] == "pri_active_real"
        return _FakeResponse()

    import app.commerce as commerce_module

    monkeypatch.setattr(commerce_module.httpx, "post", _fake_post)

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://sandbox-checkout.paddle.com/fake"


def test_transaction_completed_resolves_email_via_customer_id(client, db_session, monkeypatch):
    """A real Paddle Billing transaction.completed event carries only
    customer_id on data, never an embedded customer object (see
    commerce.py's _fetch_customer_email docstring -- found via a real
    sandbox webhook returning KeyError: 'customer', 2026-08-14). The
    handler must look the email up via the Customers API instead of
    assuming an embedded customer.email."""
    db_session.add(
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

    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "paddle_api_key", "sandbox-key-for-test")

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"email": "real-customer@example.com"}}

    def _fake_get(url, headers=None, timeout=None):
        assert url.endswith("/customers/ctm_real_customer")
        return _FakeResponse()

    import app.commerce as commerce_module

    monkeypatch.setattr(commerce_module.httpx, "get", _fake_get)

    payload = {
        "event_id": "evt_real_shape",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_real_shape",
            "customer_id": "ctm_real_customer",
            "currency_code": "GBP",
            "details": {"totals": {"total": "500"}},
            "items": [{"price": {"product_id": "smart-sample-manager"}}],
        },
    }
    resp = _post_webhook(client, payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    purchase = db_session.query(models.Purchase).one()
    user = db_session.get(models.User, purchase.user_id)
    assert user.email == "real-customer@example.com"
    assert db_session.query(models.Entitlement).count() == 1


def _login_and_get_token(client, email, db_session):
    from datetime import datetime, timedelta, timezone

    from app.security import generate_raw_token, hash_token

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
