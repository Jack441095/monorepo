"""Purchase confirmation email durability (release blocker fix).

Before this fix the webhook sent the confirmation email inside the fulfilment
transaction: a commit failure mailed an unusable licence key, and a send
failure rolled back a paid licence. Fulfilment now commits first and the
email follows in a second transaction, so these tests pin both halves: a dead
mail provider must leave a usable licence plus an unsent row, and any later
delivery (Stripe retry or admin resend) must complete the email exactly once.
"""
from __future__ import annotations

from app import models
from tests.test_commerce_catalog import _completed_payload, _post_webhook
from tests.test_e2e import _seed_product


def _buy_with_broken_mail(client, db_session, monkeypatch, event_id, txn_id, email="durable-buyer@example.com"):
    import app.stripe_commerce as commerce_module

    def _dead_provider(**kwargs):
        raise RuntimeError("simulated mail provider outage")

    monkeypatch.setattr(commerce_module, "send_email", _dead_provider)
    return _post_webhook(client, _completed_payload(event_id, txn_id, email=email))


def test_send_failure_leaves_licence_durable_and_email_pending(client, db_session, monkeypatch):
    _seed_product(db_session)
    resp = _buy_with_broken_mail(client, db_session, monkeypatch, "evt_mail_down", "txn_mail_down")

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    purchase = db_session.query(models.Purchase).filter(
        models.Purchase.provider_order_id == "txn_mail_down"
    ).one()
    assert purchase.status == "completed"
    assert purchase.confirmation_email_sent_at is None
    entitlement = db_session.query(models.Entitlement).filter(
        models.Entitlement.purchase_id == purchase.id
    ).one()
    assert entitlement.status == "active"
    assert entitlement.license_key
    event = db_session.query(models.WebhookEvent).filter(
        models.WebhookEvent.provider_event_id == "evt_mail_down"
    ).one()
    assert event.processed_at is not None
    assert event.processing_error is None


def test_duplicate_delivery_resends_pending_confirmation_once(client, db_session, monkeypatch):
    import app.stripe_commerce as commerce_module

    _seed_product(db_session)
    _buy_with_broken_mail(client, db_session, monkeypatch, "evt_mail_down_2", "txn_mail_retry")

    sent = []
    monkeypatch.setattr(commerce_module, "send_email", lambda **kwargs: sent.append(kwargs))
    retry = _post_webhook(client, _completed_payload("evt_mail_retry", "txn_mail_retry"))

    assert retry.status_code == 200
    assert retry.json()["status"] == "already_processed"
    assert len(sent) == 1
    purchase = db_session.query(models.Purchase).filter(
        models.Purchase.provider_order_id == "txn_mail_retry"
    ).one()
    db_session.refresh(purchase)
    assert purchase.confirmation_email_sent_at is not None
    entitlement = db_session.query(models.Entitlement).filter(
        models.Entitlement.purchase_id == purchase.id
    ).one()
    assert entitlement.license_key in sent[0]["body"]
    assert db_session.query(models.Purchase).count() == 1
    assert db_session.query(models.Entitlement).count() == 1


def test_same_event_replay_resends_pending_confirmation(client, db_session, monkeypatch):
    import app.stripe_commerce as commerce_module

    _seed_product(db_session)
    payload = _completed_payload("evt_mail_replay", "txn_mail_replay")
    _buy_with_broken_mail(client, db_session, monkeypatch, "evt_mail_replay", "txn_mail_replay")

    sent = []
    monkeypatch.setattr(commerce_module, "send_email", lambda **kwargs: sent.append(kwargs))
    replay = _post_webhook(client, payload)

    assert replay.status_code == 200
    assert replay.json()["status"] == "already_processed"
    assert len(sent) == 1
    purchase = db_session.query(models.Purchase).filter(
        models.Purchase.provider_order_id == "txn_mail_replay"
    ).one()
    db_session.refresh(purchase)
    assert purchase.confirmation_email_sent_at is not None


def test_admin_resend_delivers_unsent_confirmation(client, db_session, monkeypatch):
    import app.stripe_commerce as commerce_module

    _seed_product(db_session)
    _buy_with_broken_mail(client, db_session, monkeypatch, "evt_mail_admin", "txn_mail_admin")
    purchase = db_session.query(models.Purchase).filter(
        models.Purchase.provider_order_id == "txn_mail_admin"
    ).one()

    pending = client.get("/admin/purchases/unsent-confirmations", headers={"X-Admin-Key": "test-admin-key"})
    assert pending.status_code == 200
    assert [row["provider_order_id"] for row in pending.json()] == ["txn_mail_admin"]

    sent = []
    monkeypatch.setattr(commerce_module, "send_email", lambda **kwargs: sent.append(kwargs))
    resend = client.post(
        f"/admin/purchases/{purchase.id}/resend-confirmation",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resend.status_code == 200
    assert resend.json() == {"purchase_id": purchase.id, "sent": True}
    assert len(sent) == 1

    db_session.refresh(purchase)
    assert purchase.confirmation_email_sent_at is not None
    assert client.get("/admin/purchases/unsent-confirmations",
                       headers={"X-Admin-Key": "test-admin-key"}).json() == []

    repeat = client.post(
        f"/admin/purchases/{purchase.id}/resend-confirmation",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert repeat.json() == {"purchase_id": purchase.id, "sent": False}
    assert len(sent) == 1


def test_admin_resend_unknown_purchase_is_404(client):
    resp = client.post(
        "/admin/purchases/does-not-exist/resend-confirmation",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 404


def test_admin_issue_reports_email_failure_without_losing_entitlement(client, db_session, monkeypatch):
    import app.admin as admin_module

    db_session.merge(models.Product(
        id="nite-submit", name="NITE Submit", status="active",
        public=False, purchasable=False, platforms=["macos"],
    ))
    db_session.commit()

    def _dead_provider(**kwargs):
        raise RuntimeError("simulated mail provider outage")

    monkeypatch.setattr(admin_module, "send_email", _dead_provider)
    resp = client.post(
        "/admin/entitlements/issue",
        json={"email": "beta-no-mail@example.com", "product_id": "nite-submit"},
        headers={"X-Admin-Key": "test-admin-key"},
    )

    assert resp.status_code == 200
    assert resp.json()["email_sent"] is False
    entitlement = db_session.query(models.Entitlement).filter(
        models.Entitlement.license_key == resp.json()["license_key"]
    ).one()
    assert entitlement.status == "active"
