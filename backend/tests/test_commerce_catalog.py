"""Stripe checkout, catalogue fulfilment, refunds, and download access."""
from __future__ import annotations

import hashlib
import pytest

from app import models
from app.config import settings as app_settings
from tests.test_e2e import _seed_product, _sign_stripe_payload


def _post_webhook(client, payload):
    raw_body, sig = _sign_stripe_payload(payload, "test-webhook-secret")
    return client.post(
        "/webhooks/stripe", content=raw_body, headers={"Stripe-Signature": sig, "Content-Type": "application/json"}
    )


def _completed_payload(event_id, txn_id, product_id="smart-sample-manager", price_id=None, email="buyer@example.com"):
    metadata = {"product_id": product_id}
    if price_id is not None:
        metadata["price_id"] = price_id
    return {"id": event_id, "type": "checkout.session.completed", "data": {"object": {
        "id": txn_id, "payment_intent": "pi_" + txn_id, "payment_status": "paid",
        "customer_details": {"email": email}, "currency": "gbp", "amount_total": 500,
        "metadata": metadata,
    }}}



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


def test_unpaid_checkout_does_not_issue_a_licence(client, db_session):
    _seed_product(db_session)
    payload = _completed_payload("evt_unpaid", "cs_unpaid")
    payload["data"]["object"]["payment_status"] = "unpaid"
    assert _post_webhook(client, payload).json()["status"] == "awaiting_payment"
    assert db_session.query(models.Purchase).count() == 0
    assert db_session.query(models.Entitlement).count() == 0



def test_server_price_metadata_is_recorded(client, db_session):
    _seed_product(db_session)
    resp = _post_webhook(client, _completed_payload("evt_price", "cs_price", price_id="price_intro"))
    assert resp.status_code == 200
    assert db_session.query(models.Purchase).one().price_id == "price_intro"



def test_purchase_confirmation_uses_catalog_product_name(client, db_session, monkeypatch):
    db_session.add(
        models.Product(
            id="nite-submit",
            name="NITE Submit",
            status="active",
            public=False,
            purchasable=True,
            platforms=["macos"],
        )
    )
    db_session.commit()

    import app.stripe_commerce as commerce_module

    sent = []
    monkeypatch.setattr(commerce_module, "send_email", lambda **kwargs: sent.append(kwargs))

    resp = _post_webhook(
        client,
        _completed_payload(
            "evt_nite_submit_confirmation",
            "txn_nite_submit_confirmation",
            product_id="nite-submit",
            email="nite-submit-buyer@example.com",
        ),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    assert sent[0]["subject"] == "Your NITE Submit purchase is complete"
    assert "Thanks for purchasing NITE Submit!" in sent[0]["body"]


def _refund_payload(event_id, transaction_id, full_refund=True):
    return {"id": event_id, "type": "charge.refunded", "data": {"object": {
        "payment_intent": "pi_" + transaction_id, "refunded": full_refund,
    }}}



def _buy_something(client, event_id, txn_id):
    _post_webhook(client, _completed_payload(event_id, txn_id))


def test_partial_refund_keeps_purchase_completed(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_pending_src", "txn_pending")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_pending").one()

    resp = _post_webhook(client, _refund_payload("evt_adj_pending", "txn_pending", False))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    db_session.refresh(purchase)
    assert purchase.status == "completed"
    assert purchase.refunded_at is None


def test_full_refund_preserves_entitlement_for_admin_review(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_approved_src", "txn_approved")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_approved").one()
    entitlement = db_session.query(models.Entitlement).filter(models.Entitlement.purchase_id == purchase.id).one()
    assert purchase.status == "completed"
    assert entitlement.status == "active"

    # A partial refund arrives before the final full refund.
    _post_webhook(client, _refund_payload("evt_adj_created", "txn_approved", False))
    resp = _post_webhook(client, _refund_payload("evt_adj_updated", "txn_approved", True))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    db_session.refresh(purchase)
    db_session.refresh(entitlement)
    assert purchase.status == "refunded"
    assert purchase.refunded_at is not None
    assert entitlement.status == "active"  # revocation stays a manual admin decision


def test_second_partial_refund_keeps_purchase_completed(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_rejected_src", "txn_rejected")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_rejected").one()

    _post_webhook(client, _refund_payload("evt_adj_created2", "txn_rejected", False))
    resp = _post_webhook(client, _refund_payload("evt_adj_rejected", "txn_rejected", False))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "completed"
    assert purchase.refunded_at is None


def test_duplicate_full_refund_is_idempotent(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_dup_adj_src", "txn_dup_adj")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_dup_adj").one()

    _post_webhook(client, _refund_payload("evt_adj_dup_1", "txn_dup_adj", True))
    db_session.refresh(purchase)
    first_refunded_at = purchase.refunded_at
    assert purchase.status == "refunded"

    # A second, distinct delivery (different event_id -- not the WebhookEvent
    # dedup path) reporting the same full refund.
    resp = _post_webhook(client, _refund_payload("evt_adj_dup_2", "txn_dup_adj", True))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "refunded"
    assert purchase.refunded_at == first_refunded_at  # untouched by the duplicate


def test_stale_partial_refund_does_not_regress_full_refund(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_ooo_src", "txn_out_of_order")
    purchase = db_session.query(models.Purchase).filter(models.Purchase.provider_order_id == "txn_out_of_order").one()

    _post_webhook(client, _refund_payload("evt_adj_ooo_approved", "txn_out_of_order", True))
    db_session.refresh(purchase)
    assert purchase.status == "refunded"
    refunded_at = purchase.refunded_at

    # A stale partial-refund event arrives after the full refund.
    resp = _post_webhook(client, _refund_payload("evt_adj_ooo_pending", "txn_out_of_order", False))
    assert resp.status_code == 200

    db_session.refresh(purchase)
    assert purchase.status == "refunded"  # never regresses back to completed
    assert purchase.refunded_at == refunded_at


def test_refund_for_unknown_transaction_is_a_safe_no_op(client, db_session):
    resp = _post_webhook(client, _refund_payload("evt_refund_unknown", "txn_never_existed", True))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"


def test_checkout_requires_auth(client):
    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 401


def test_checkout_unconfigured_stripe_returns_503(client, db_session, monkeypatch):
    # The developer's local .env may contain sandbox credentials. Keep this
    # regression deterministic: it is specifically testing the fail-closed
    # behavior when the provider is not configured.
    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "stripe_secret_key", "")
    raw_token = _login_and_get_token(client, "checkout-buyer@example.com", db_session)
    verify_resp = client.post("/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 503


def test_checkout_disabled_returns_503_even_when_stripe_is_configured(client, db_session, monkeypatch):
    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "stripe_secret_key", "sandbox-key-for-test")
    monkeypatch.setattr(commerce_settings, "stripe_active_price_id", "pri_active_real")
    monkeypatch.setattr(commerce_settings, "stripe_checkout_enabled", False)
    raw_token = _login_and_get_token(client, "checkout-disabled@example.com", db_session)
    assert client.post("/auth/verify", json={"token": raw_token}).status_code == 200

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 503


def test_checkout_creates_url_when_configured(client, db_session, monkeypatch):
    _seed_product(db_session, "nite-submit")
    raw_token = _login_and_get_token(client, "checkout-buyer-2@example.com", db_session)
    verify_resp = client.post("/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200

    from app.commerce import settings as commerce_settings

    monkeypatch.setattr(commerce_settings, "stripe_secret_key", "sandbox-key-for-test")
    monkeypatch.setattr(commerce_settings, "stripe_active_price_id", "pri_active_real")
    monkeypatch.setattr(commerce_settings, "stripe_checkout_enabled", True)

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"url": "https://checkout.stripe.com/fake"}

    def _fake_post(url, headers=None, data=None, timeout=None):
        assert url == "https://api.stripe.com/v1/checkout/sessions"
        assert data["line_items[0][price]"] == "pri_active_real"
        assert data["metadata[product_id]"] == "nite-submit"
        assert data["customer_email"] == "checkout-buyer-2@example.com"
        assert data["success_url"].endswith("/account?purchase=pending")
        return _FakeResponse()

    import app.commerce as commerce_module

    monkeypatch.setattr(commerce_module.httpx, "post", _fake_post)

    resp = client.post("/commerce/checkout", json={"price": "active"})
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/fake"


@pytest.mark.parametrize("purchasable", [None, False])
def test_checkout_rejects_a_missing_or_closed_catalog_product(client, db_session, monkeypatch, purchasable):
    # A valid Stripe price must not charge for a product we cannot fulfil.
    from app.commerce import settings as commerce_settings

    if purchasable is not None:
        _seed_product(db_session, "nite-submit")
        product = db_session.get(models.Product, "nite-submit")
        product.purchasable = purchasable
        db_session.commit()
    monkeypatch.setattr(commerce_settings, "stripe_secret_key", "sk_test_fake_checkout")
    monkeypatch.setattr(commerce_settings, "stripe_active_price_id", "price_test_active")
    monkeypatch.setattr(commerce_settings, "stripe_checkout_enabled", True)
    import app.commerce as commerce_module

    def unexpected_checkout(*args, **kwargs):
        pytest.fail("Unavailable catalog products must not contact Stripe")

    monkeypatch.setattr(commerce_module.httpx, "post", unexpected_checkout)
    token = _login_and_get_token(client, "unavailable-product@example.com", db_session)
    assert client.post("/auth/verify", json={"token": token}).status_code == 200

    assert client.post("/commerce/checkout", json={"price": "active"}).status_code == 503


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


@pytest.mark.parametrize("previous_provider", ["beta", "paddle"])
def test_new_stripe_purchase_preserves_download_access_with_an_existing_licence(client, db_session, previous_provider):
    # Beta grants and historical paid licences coexist with a new Stripe purchase.
    _seed_product(db_session)
    email = "existing-license@example.com"
    token = _login_and_get_token(client, email, db_session)
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    user = db_session.query(models.User).filter_by(email=email).one()
    purchase_id = None
    if previous_provider != "beta":
        purchase = models.Purchase(
            user_id=user.id, product_id="smart-sample-manager", provider=previous_provider,
            provider_order_id="legacy_order", amount_cents=500, currency="GBP",
        )
        db_session.add(purchase)
        db_session.flush()
        purchase_id = purchase.id
    db_session.add(models.Entitlement(
        user_id=user.id, product_id="smart-sample-manager", purchase_id=purchase_id,
        license_type="beta" if previous_provider == "beta" else "perpetual",
        license_key="EXISTING-LICENCE", max_activations=3, status="active",
    ))
    db_session.commit()

    assert _post_webhook(client, _completed_payload("evt_upgrade", "cs_upgrade", email=email)).status_code == 200
    assert db_session.query(models.Entitlement).filter_by(user_id=user.id, status="active").count() == 2
    response = client.get("/downloads/latest", params={
        "product_id": "smart-sample-manager", "platform": "macos", "architecture": "arm64",
    })
    # Authentication succeeds and reaches release lookup; no release was seeded.
    assert response.status_code == 404
    assert response.json()["detail"] == "No matching release found"


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


def test_checkout_falls_back_to_customer_email(client, db_session):
    _seed_product(db_session)
    payload = _completed_payload("evt_customer_email", "cs_customer_email")
    session = payload["data"]["object"]
    del session["customer_details"]
    session["customer_email"] = "real-customer@example.com"
    assert _post_webhook(client, payload).status_code == 200
    purchase = db_session.query(models.Purchase).one()
    assert db_session.get(models.User, purchase.user_id).email == "real-customer@example.com"



def test_failed_first_delivery_is_not_poisoned_by_retry(client, db_session):
    # A failed attempt must remain retryable even after its receipt was committed.
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

    payload = _completed_payload("evt_retry_test", "txn_retry_test", email="retry-buyer@example.com")

    import app.stripe_commerce as commerce_module

    original_handler = commerce_module._handle_checkout_session_completed
    call_count = {"n": 0}

    def _flaky_handler(db, payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient failure on first delivery")
        return original_handler(db, payload)

    import unittest.mock as mock

    with mock.patch.object(commerce_module, "_handle_checkout_session_completed", side_effect=_flaky_handler):
        first_resp = _post_webhook(client, payload)
        assert first_resp.status_code == 500

        assert db_session.query(models.Purchase).count() == 0
        events = db_session.query(models.WebhookEvent).filter(
            models.WebhookEvent.provider_event_id == "evt_retry_test"
        ).all()
        assert len(events) == 1
        assert events[0].processed_at is None
        assert events[0].processing_error == "simulated transient failure on first delivery"

        # Stripe retries the identical event_id.
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
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert create_resp.status_code == 200

    list_resp = client.get("/admin/products", headers={"X-Admin-Key": "test-admin-key"})
    assert list_resp.status_code == 200
    products = list_resp.json()
    assert len(products) == 1
    assert products[0]["id"] == "smart-sample-manager"

    # Updating (same path id) doesn't create a second row.
    update_resp = client.put(
        "/admin/products/smart-sample-manager",
        json={
            "id": "smart-sample-manager",
            "name": "Smart Sample Manager",
            "purchasable": False,
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
    macos_path = (
        tmp_path
        / "releases"
        / "nite-submit"
        / "0.2.0"
        / "macos"
        / "arm64"
        / "Submit-0.2.0-macOS.zip"
    )
    assert macos_path.read_bytes() == payload

    # A same-named artifact for another platform/architecture gets a distinct
    # immutable object key rather than colliding with the macOS release.
    windows_resp = client.post(
        "/admin/releases/upload",
        data={
            "product_id": "nite-submit",
            "version": "0.2.0",
            "platform": "windows",
            "architecture": "x64",
        },
        files={"artifact": ("Submit-0.2.0-macOS.zip", payload, "application/zip")},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert windows_resp.status_code == 200
    windows_path = (
        tmp_path
        / "releases"
        / "nite-submit"
        / "0.2.0"
        / "windows"
        / "x64"
        / "Submit-0.2.0-macOS.zip"
    )
    assert windows_path.read_bytes() == payload
    assert windows_path != macos_path


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
            "storage_key": "releases/nite-submit/0.2.0/macos/arm64/test-release.txt",
            "signature": "ad_hoc;notarised=false",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["checksum_sha256"] == checksum

    release = db_session.query(models.Release).filter(models.Release.product_id == "nite-submit").one()
    assert release.architecture == "arm64"
    assert release.channel == "private-beta"
    assert release.storage_key == "releases/nite-submit/0.2.0/macos/arm64/test-release.txt"


def test_admin_release_upsert_rejects_storage_key_for_other_release_identity(client, db_session):
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
            "channel": "private-beta",
            "checksum_sha256": "7e63a26d7a94559c3f69273bcf850d352984d2e503b437f69c2876ed232ea3ea",
            "storage_key": "releases/nite-submit/0.2.0/windows/x64/test-release.txt",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 400
    assert "canonical" in resp.json()["detail"]
    assert db_session.query(models.Release).count() == 0


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
            "storage_key": "releases/nite-submit/0.2.0/macos/arm64/test-release.txt",
        },
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 409
    assert db_session.query(models.Release).count() == 0


def test_webhook_uses_internal_product_slug(client, db_session):
    _seed_product(db_session)
    assert _post_webhook(client, _completed_payload("evt_slug", "cs_slug")).status_code == 200
    assert db_session.query(models.Purchase).one().product_id == "smart-sample-manager"



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


def test_delayed_payment_fulfils_once_when_two_events_share_a_session(client, db_session):
    # Checkout completion can precede settlement; only settlement grants a licence.
    _seed_product(db_session)
    payload = _completed_payload("evt_delayed_start", "cs_delayed")
    payload["data"]["object"]["payment_status"] = "unpaid"
    assert _post_webhook(client, payload).json()["status"] == "awaiting_payment"
    payload["id"] = "evt_delayed_paid"
    payload["type"] = "checkout.session.async_payment_succeeded"
    payload["data"]["object"]["payment_status"] = "paid"
    assert _post_webhook(client, payload).json()["status"] == "processed"
    payload["id"] = "evt_delayed_duplicate"
    assert _post_webhook(client, payload).json()["status"] == "already_processed"
    assert db_session.query(models.Purchase).count() == 1
    assert db_session.query(models.Entitlement).count() == 1


def test_paraphrase_paid_session_records_minor_units_and_can_be_redeemed(client, db_session):
    from app import paraphrase_orders

    payload = _completed_payload("evt_paraphrase", "cs_paraphrase", product_id="nite-paraphrase")
    payload["data"]["object"]["metadata"]["paraphrase_hint"] = "browser-secret-hint"
    assert _post_webhook(client, payload).status_code == 200
    payload["id"] = "evt_paraphrase_duplicate"
    assert _post_webhook(client, payload).status_code == 200
    order = db_session.query(models.ParaphraseOrder).one()
    assert order.amount_cents == 500
    assert order.currency == "GBP"
    token, _ = paraphrase_orders.redeem(db_session, "browser-secret-hint")
    assert paraphrase_orders.verify_unlock_token(token)
    assert paraphrase_orders.redeem(db_session, "other-browser-hint") is None
    assert db_session.query(models.User).count() == 0
    assert db_session.query(models.Entitlement).count() == 0


def test_paraphrase_checkout_uses_stripe_metadata_and_success_hint(monkeypatch):
    from app import paraphrase_orders

    monkeypatch.setattr(app_settings, "paraphrase_price_gbp_3", "price_paraphrase_3")
    calls = []

    class Provider:
        def create_checkout_url(self, price_id, **kwargs):
            calls.append((price_id, kwargs))
            return "https://checkout.stripe.com/paraphrase"

    url, hint = paraphrase_orders.create_checkout(Provider(), "gbp-3")
    assert url == "https://checkout.stripe.com/paraphrase"
    assert calls[0][0] == "price_paraphrase_3"
    assert calls[0][1]["metadata"] == {"product_id": "nite-paraphrase", "paraphrase_hint": hint}
    assert calls[0][1]["success_url"].endswith("?paraphrase_hint=" + hint)


def test_failed_flush_rolls_back_purchase_before_retry(client, db_session, monkeypatch):
    # A SQL failure aborts the transaction; recording an error needs a fresh one.
    import app.stripe_commerce as module

    _seed_product(db_session)
    original = module._handle_checkout_session_completed
    calls = 0

    def fail_after_flush(db, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            original(db, payload)
            db.add(models.User(email="buyer@example.com"))
            db.flush()
            raise AssertionError("the duplicate email should fail at flush")
        return original(db, payload)

    monkeypatch.setattr(module, "_handle_checkout_session_completed", fail_after_flush)
    payload = _completed_payload("evt_flush_retry", "cs_flush_retry")
    assert _post_webhook(client, payload).status_code == 500
    assert db_session.query(models.Purchase).count() == 0
    receipt = db_session.query(models.WebhookEvent).one()
    assert receipt.processed_at is None
    assert "UniqueViolation" in receipt.processing_error
    assert _post_webhook(client, payload).status_code == 200
    assert db_session.query(models.Purchase).count() == 1


def test_dispute_records_status_without_revoking_a_licence(client, db_session):
    _seed_product(db_session)
    _buy_something(client, "evt_dispute_src", "cs_dispute")
    payload = {"id": "evt_dispute", "type": "charge.dispute.created", "data": {"object": {
        "payment_intent": "pi_cs_dispute",
    }}}
    assert _post_webhook(client, payload).status_code == 200
    assert db_session.query(models.Purchase).one().status == "disputed"
    assert db_session.query(models.Entitlement).one().status == "active"
