"""
Catalog mapping, checkout creation, and refund recording -- the pieces of
commerce.py that only exist once real Paddle product/price IDs are
configured (docs/PADDLE_INTEGRATION_AUDIT.md). Paddle itself is still
never called for real here (no sandbox account exists yet); httpx.post is
monkeypatched for the checkout test the same way tests/test_e2e.py
simulates webhook payloads instead of receiving real ones.
"""
from __future__ import annotations

import hashlib

from app import models
from app.config import settings as app_settings
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
            paddle_product_id="smart-sample-manager",  # found, but rejected on purchasable=False
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


def test_purchase_confirmation_uses_catalog_product_name(client, db_session, monkeypatch):
    db_session.add(
        models.Product(
            id="nite-submit",
            name="NITE Submit",
            status="active",
            public=False,
            purchasable=True,
            platforms=["macos"],
            paddle_product_id="pro_nite_submit_sandbox",
        )
    )
    db_session.commit()

    import app.commerce as commerce_module

    sent = []
    monkeypatch.setattr(commerce_module, "send_email", lambda **kwargs: sent.append(kwargs))

    resp = _post_webhook(
        client,
        _completed_payload(
            "evt_nite_submit_confirmation",
            "txn_nite_submit_confirmation",
            product_id="pro_nite_submit_sandbox",
            email="nite-submit-buyer@example.com",
        ),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    assert sent[0]["subject"] == "Your NITE Submit purchase is complete"
    assert "Thanks for purchasing NITE Submit!" in sent[0]["body"]


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


def test_checkout_unconfigured_paddle_returns_503(client, db_session, monkeypatch):
    # The developer's local .env may contain sandbox credentials. Keep this
    # regression deterministic: it is specifically testing the fail-closed
    # behavior when the provider is not configured.
    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "paddle_api_key", "")
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
        assert "customer" not in json
        return _FakeResponse()

    import app.commerce as commerce_module

    monkeypatch.setattr(commerce_module.httpx, "post", _fake_post)

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://sandbox-checkout.paddle.com/fake"


def test_download_rejects_unsupported_platform(client, db_session):
    _seed_product(db_session)
    raw_token = _login_and_get_token(client, "unsupported-platform@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200

    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "solaris", "architecture": "x64"},
    )
    assert resp.status_code == 400
    assert "Unsupported platform" in resp.json()["detail"]


def test_download_requires_active_entitlement(client, db_session):
    _seed_product(db_session)
    raw_token = _login_and_get_token(client, "no-entitlement@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200

    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "macos", "architecture": "universal"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "No active entitlement for this product"


def test_download_reports_missing_release(client, db_session):
    _seed_product(db_session)
    user = models.User(email="missing-release@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key="MISSING-RELEASE-0001-0001",
            license_type="perpetual",
            max_activations=3,
            status="active",
        )
    )
    db_session.commit()

    raw_token = _login_and_get_token(client, "missing-release@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200
    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "linux", "architecture": "x64"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No matching release found"


def test_download_returns_latest_platform_specific_release_and_checksum(client, db_session):
    import hashlib

    _seed_product(db_session)
    user = models.User(email="platform-download@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key="PLATFORM-TEST-0001-0001",
            license_type="perpetual",
            max_activations=3,
            status="active",
        )
    )
    db_session.add(
        models.Release(
            product_id="smart-sample-manager",
            version="1.2.3",
            platform="windows",
            architecture="x64",
            channel="stable",
            checksum_sha256=hashlib.sha256(b"windows zip").hexdigest(),
            storage_key="releases/windows-1.2.3.zip",
        )
    )
    db_session.commit()

    raw_token = _login_and_get_token(client, "platform-download@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200
    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "windows", "architecture": "x64"},
    )

    assert resp.status_code == 200
    assert resp.json()["version"] == "1.2.3"
    assert resp.json()["checksum_sha256"] == hashlib.sha256(b"windows zip").hexdigest()
    assert "token=" in resp.json()["download_url"]


def test_s3_download_validates_token_records_download_and_redirects(client, db_session, monkeypatch):
    import hashlib
    from urllib.parse import urlsplit

    _seed_product(db_session)
    user = models.User(email="s3-download@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key="S3-DOWNLOAD-0001-0001",
            license_type="perpetual",
            max_activations=3,
            status="active",
        )
    )
    db_session.add(
        models.Release(
            product_id="smart-sample-manager",
            version="2.0.0",
            platform="linux",
            architecture="x64",
            channel="stable",
            checksum_sha256=hashlib.sha256(b"linux zip").hexdigest(),
            storage_key="releases/linux-2.0.0.zip",
        )
    )
    db_session.commit()

    raw_token = _login_and_get_token(client, "s3-download@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200
    latest = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "linux", "architecture": "x64"},
    )
    assert latest.status_code == 200

    class FakeStorage:
        def exists(self, storage_key):
            assert storage_key == "releases/linux-2.0.0.zip"
            return True

        def local_path(self, storage_key):
            return None

        def presigned_get_url(self, storage_key, expires_in, filename):
            assert expires_in == 15 * 60
            assert filename == "linux-2.0.0.zip"
            return "https://objects.example/signed-linux.zip"

    import app.downloads as downloads_module

    monkeypatch.setattr(downloads_module, "get_storage", lambda: FakeStorage())
    parsed = urlsplit(latest.json()["download_url"])
    fetched = client.get(f"{parsed.path}?{parsed.query}", follow_redirects=False)

    assert fetched.status_code == 307
    assert fetched.headers["location"] == "https://objects.example/signed-linux.zip"
    assert db_session.query(models.Download).count() == 1


def test_download_rejects_expired_entitlement(client, db_session):
    from datetime import datetime, timedelta, timezone

    _seed_product(db_session)
    user = models.User(email="expired-download@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        models.Entitlement(
            user_id=user.id,
            product_id="smart-sample-manager",
            license_key="EXPIRED-DL-0001-0001",
            license_type="subscription",
            max_activations=3,
            status="active",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    raw_token = _login_and_get_token(client, "expired-download@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200
    resp = client.get(
        "/downloads/latest",
        params={"product_id": "smart-sample-manager", "platform": "macos", "architecture": "universal"},
    )
    assert resp.status_code == 403


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
            paddle_product_id="smart-sample-manager",
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


def test_failed_first_delivery_is_not_poisoned_by_retry(client, db_session):
    """A delivery that raises on its first attempt must still be
    processable on a later retry of the same event_id. Before this fix,
    the insert-and-commit idempotency claim ran before processing, so a
    first-attempt failure left a WebhookEvent row with processed_at=None
    permanently in place -- every retry (including Paddle's own automatic
    one) matched that row and short-circuited to already_processed without
    ever calling _handle_transaction_completed. Paddle marks the
    notification "delivered" on that 200, so the event was lost forever.
    Real incident: txn_01kzzqmywn6h2waqzycw10f0me, 2026-08-14."""
    # No Product row seeded -- first delivery raises UnknownCatalogItemError,
    # which IS treated as a terminal rejection (by design, see paddle_webhook),
    # so instead simulate a genuinely transient failure: seed the product
    # but make the first delivery's price_id mapping momentarily wrong.
    db_session.add(
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

    payload = _completed_payload("evt_retry_test", "txn_retry_test", email="retry-buyer@example.com")

    import app.commerce as commerce_module

    original_handler = commerce_module._handle_transaction_completed
    call_count = {"n": 0}

    def _flaky_handler(db, payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient failure on first delivery")
        return original_handler(db, payload)

    import unittest.mock as mock

    with mock.patch.object(commerce_module, "_handle_transaction_completed", side_effect=_flaky_handler):
        first_resp = _post_webhook(client, payload)
        assert first_resp.status_code == 500

        assert db_session.query(models.Purchase).count() == 0
        events = db_session.query(models.WebhookEvent).filter(
            models.WebhookEvent.provider_event_id == "evt_retry_test"
        ).all()
        assert len(events) == 1
        assert events[0].processed_at is None
        assert events[0].processing_error == "simulated transient failure on first delivery"

        # Paddle retries the identical event_id.
        retry_resp = _post_webhook(client, payload)
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "processed"

    assert call_count["n"] == 2
    db_session.expire_all()  # the app processed this in a separate session/transaction
    assert db_session.query(models.Purchase).count() == 1
    assert db_session.query(models.Entitlement).count() == 1
    event = db_session.query(models.WebhookEvent).filter(
        models.WebhookEvent.provider_event_id == "evt_retry_test"
    ).one()
    assert event.processed_at is not None
    assert event.processing_error is None

    # A third, now-truly-duplicate delivery must not double-process.
    third_resp = _post_webhook(client, payload)
    assert third_resp.status_code == 200
    assert third_resp.json()["status"] == "already_processed"
    assert db_session.query(models.Purchase).count() == 1
    assert db_session.query(models.Entitlement).count() == 1


def test_admin_can_create_and_list_products(client, db_session):
    create_resp = client.put(
        "/admin/products/smart-sample-manager",
        json={
            "id": "smart-sample-manager",
            "name": "Smart Sample Manager",
            "purchasable": True,
            "public": True,
            "platforms": ["macos"],
            "paddle_product_id": "pro_real_catalog_item",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json() == {"id": "smart-sample-manager", "paddle_product_id": "pro_real_catalog_item"}

    list_resp = client.get("/admin/products", headers={"X-Admin-Key": "test-admin-key"})
    assert list_resp.status_code == 200
    products = list_resp.json()
    assert len(products) == 1
    assert products[0]["paddle_product_id"] == "pro_real_catalog_item"

    # Updating (same path id) doesn't create a second row.
    update_resp = client.put(
        "/admin/products/smart-sample-manager",
        json={
            "id": "smart-sample-manager",
            "name": "Smart Sample Manager",
            "purchasable": False,
            "paddle_product_id": "pro_real_catalog_item",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert update_resp.status_code == 200
    assert db_session.query(models.Product).count() == 1
    db_session.expire_all()
    assert db_session.get(models.Product, "smart-sample-manager").purchasable is False


def test_admin_products_requires_admin_key(client):
    resp = client.get("/admin/products", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 401


def test_staging_release_upload_is_checksum_bound(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "environment", "staging")
    monkeypatch.setattr(app_settings, "mock_storage_dir", str(tmp_path))
    db_session.add(
        models.Product(
            id="nite-submit",
            name="NITE Submit",
            status="active",
            public=False,
            purchasable=False,
            platforms=["macos"],
        )
    )
    db_session.commit()

    payload = b"staging release bytes"
    checksum = hashlib.sha256(payload).hexdigest()
    resp = client.post(
        "/admin/releases/upload",
        data={
            "product_id": "nite-submit",
            "version": "0.2.0",
            "platform": "macos",
            "architecture": "arm64",
        },
        files={"artifact": ("Submit-0.2.0-macOS.zip", payload, "application/zip")},
        headers={"X-Admin-Key": "test-admin-key"},
    )

    assert resp.status_code == 200
    assert resp.json()["checksum_sha256"] == checksum
    assert (tmp_path / "releases" / "nite-submit" / "0.2.0" / "Submit-0.2.0-macOS.zip").read_bytes() == payload


def test_admin_release_upsert_verifies_artifact_checksum(client, db_session):
    db_session.add(
        models.Product(
            id="nite-submit",
            name="NITE Submit",
            status="active",
            public=False,
            purchasable=False,
            platforms=["macos"],
        )
    )
    db_session.commit()

    checksum = "7e63a26d7a94559c3f69273bcf850d352984d2e503b437f69c2876ed232ea3ea"
    resp = client.put(
        "/admin/releases/nite-submit/0.2.0/macos/arm64",
        json={
            "product_id": "nite-submit",
            "version": "0.2.0",
            "platform": "macos",
            "architecture": "arm64",
            "channel": "private-beta",
            "checksum_sha256": checksum,
            "storage_key": "releases/test-release.txt",
            "signature": "ad_hoc;notarised=false",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["checksum_sha256"] == checksum

    release = db_session.query(models.Release).filter(models.Release.product_id == "nite-submit").one()
    assert release.architecture == "arm64"
    assert release.channel == "private-beta"
    assert release.storage_key == "releases/test-release.txt"


def test_admin_release_upsert_rejects_checksum_mismatch(client, db_session):
    db_session.add(
        models.Product(
            id="nite-submit",
            name="NITE Submit",
            status="active",
            public=False,
            purchasable=False,
            platforms=["macos"],
        )
    )
    db_session.commit()

    resp = client.put(
        "/admin/releases/nite-submit/0.2.0/macos/arm64",
        json={
            "product_id": "nite-submit",
            "version": "0.2.0",
            "platform": "macos",
            "architecture": "arm64",
            "checksum_sha256": "0" * 64,
            "storage_key": "releases/test-release.txt",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 409
    assert db_session.query(models.Release).count() == 0


def test_webhook_resolves_product_via_paddle_product_id_not_internal_slug(client, db_session):
    """The real bug this whole model exists to fix: a real Paddle
    transaction.completed event's product_id is Paddle's own id
    (pro_...), which is never equal to our internal slug. Seeding the
    Product with a *different* internal id than the Paddle product_id
    confirms resolution goes through paddle_product_id, not Product.id."""
    db_session.add(
        models.Product(
            id="smart-sample-manager",
            name="Smart Sample Manager",
            status="active",
            public=True,
            purchasable=True,
            platforms=["macos"],
            paddle_product_id="pro_01realcatalogitem",
        )
    )
    db_session.commit()

    payload = _completed_payload(
        "evt_real_product_shape", "txn_real_product_shape", product_id="pro_01realcatalogitem"
    )
    resp = _post_webhook(client, payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    purchase = db_session.query(models.Purchase).one()
    assert purchase.product_id == "smart-sample-manager"  # our internal slug, not Paddle's id


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
