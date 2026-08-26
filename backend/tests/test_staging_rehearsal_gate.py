from scripts.check_staging_rehearsal import (
    validate_download_auth,
    validate_health,
    validate_ready,
)


HEALTHY_READY = {
    "status": "ok",
    "database": True,
    "storage": True,
    "storage_backend": "s3",
    "storage_durable": True,
    "email_provider": "resend",
    "email_provider_configured": True,
    "email_deliverable": True,
    "checkout_enabled": True,
    "staging_customer_rehearsal": True,
    "staging_customer_rehearsal_ready": True,
}


def test_health_gate_accepts_staging_liveness():
    assert validate_health(200, {"status": "ok", "environment": "staging"}) == []


def test_health_gate_rejects_non_staging_or_non_200_response():
    failures = validate_health(503, {"status": "unavailable", "environment": "production"})

    assert "GET /health returned HTTP 503, expected 200" in failures
    assert "GET /health did not report status=ok" in failures
    assert "GET /health did not report environment=staging" in failures


def test_ready_gate_accepts_durable_rehearsal():
    assert validate_ready(200, HEALTHY_READY) == []
    assert validate_ready(200, HEALTHY_READY, require_checkout=True) == []


def test_ready_gate_rejects_current_ephemeral_console_staging():
    lightweight = {
        **HEALTHY_READY,
        "storage_backend": "local",
        "storage_durable": False,
        "email_provider": "console",
        "email_deliverable": False,
        "staging_customer_rehearsal": False,
        "staging_customer_rehearsal_ready": True,
    }

    failures = validate_ready(503, lightweight)

    assert "GET /ready returned HTTP 503, expected 200" in failures
    assert "GET /ready field storage_durable=true is required" in failures
    assert "GET /ready field email_deliverable=true is required" in failures
    assert "GET /ready field staging_customer_rehearsal=true is required" in failures
    assert "GET /ready field storage_backend=s3 is required" in failures
    assert "GET /ready field email_provider=resend is required" in failures


def test_ready_gate_can_separate_infrastructure_from_checkout():
    infrastructure_only = {**HEALTHY_READY, "checkout_enabled": False}

    assert validate_ready(200, infrastructure_only) == []
    assert "GET /ready field checkout_enabled=true is required" in validate_ready(
        200, infrastructure_only, require_checkout=True
    )


def test_download_auth_gate_requires_unauthenticated_401():
    assert validate_download_auth(401) == []
    assert validate_download_auth(200) == [
        "GET /downloads/latest returned HTTP 200, expected 401"
    ]
