import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))
from evaluation.listening_protocol import evaluate_manifest_readiness  # noqa: E402


def _manifest(**overrides):
    result = {
        "schema": "kenn.mix_review.listening_manifest.v1",
        "status": "awaiting_owner_approval",
        "source_root": None,
        "rights": {
            "rights_cleared": False,
            "owner_approved": False,
            "consent_reference": "",
        },
        "cases": [],
    }
    result.update(overrides)
    return result


def test_missing_authority_is_not_ready_and_does_not_open_audio(tmp_path):
    result = evaluate_manifest_readiness(_manifest(), product_root=tmp_path / "product")
    assert result["ready_for_execution"] is False
    assert result["audio_opened"] is False
    assert "rights_cleared must be true" in result["errors"]


def test_ready_manifest_requires_external_source_and_unique_cases(tmp_path):
    manifest = _manifest(
        status="ready_for_review",
        source_root=str(tmp_path / "approved-corpus"),
        rights={
            "rights_cleared": True,
            "owner_approved": True,
            "consent_reference": "approval-001",
            "approval_reference": "owner-approval-001",
            "approved_by": "owner@example.test",
            "reviewed_at": "2026-08-31T10:00:00Z",
        },
        protocol={"audio_opening_authorized": True, "plan_hash": "plan-sha-001"},
        cases=[{"case_id": "a"}, {"case_id": "a"}],
    )
    result = evaluate_manifest_readiness(manifest, product_root=tmp_path / "product")
    assert result["ready_for_execution"] is False
    assert "case_id values must be unique" in result["errors"]


def test_ready_manifest_is_metadata_only(tmp_path):
    manifest = _manifest(
        status="ready_for_review",
        source_root=str(tmp_path / "approved-corpus"),
        rights={
            "rights_cleared": True,
            "owner_approved": True,
            "consent_reference": "approval-001",
            "approval_reference": "owner-approval-001",
            "approved_by": "owner@example.test",
            "reviewed_at": "2026-08-31T10:00:00Z",
        },
        protocol={"audio_opening_authorized": True, "plan_hash": "plan-sha-001"},
        cases=[{"case_id": "a"}, {"case_id": "b"}],
    )
    result = evaluate_manifest_readiness(manifest, product_root=tmp_path / "product")
    assert result["ready_for_execution"] is True
    assert result["case_count"] == 2
    assert result["audio_opened"] is False


def test_ready_manifest_without_audio_authorization_is_blocked(tmp_path):
    manifest = _manifest(
        status="ready_for_review",
        source_root=str(tmp_path / "approved-corpus"),
        rights={
            "rights_cleared": True,
            "owner_approved": True,
            "consent_reference": "approval-001",
            "approval_reference": "owner-approval-001",
            "approved_by": "owner@example.test",
            "reviewed_at": "2026-08-31T10:00:00Z",
        },
        protocol={"audio_opening_authorized": False, "plan_hash": "plan-sha-001"},
        cases=[{"case_id": "a"}],
    )
    result = evaluate_manifest_readiness(manifest, product_root=tmp_path / "product")
    assert result["ready_for_execution"] is False
    assert "audio_opening_authorized must be true once review is ready" in result["errors"]


def test_ready_manifest_without_bound_approval_receipt_is_blocked(tmp_path):
    manifest = _manifest(
        status="ready_for_review",
        source_root=str(tmp_path / "approved-corpus"),
        rights={
            "rights_cleared": True,
            "owner_approved": True,
            "consent_reference": "approval-001",
        },
        protocol={"audio_opening_authorized": True},
        cases=[{"case_id": "a"}],
    )
    result = evaluate_manifest_readiness(manifest, product_root=tmp_path / "product")
    assert result["ready_for_execution"] is False
    assert "approval_reference is required once review is ready" in result["errors"]
    assert "approved_by is required once review is ready" in result["errors"]
    assert "reviewed_at is required once review is ready" in result["errors"]
    assert "plan_hash is required once review is ready" in result["errors"]


def test_ready_manifest_rejects_unparseable_or_timezone_less_review_timestamp(tmp_path):
    for reviewed_at in ("yesterday", "2026-08-31T10:00:00"):
        manifest = _manifest(
            status="ready_for_review",
            source_root=str(tmp_path / "approved-corpus"),
            rights={
                "rights_cleared": True,
                "owner_approved": True,
                "consent_reference": "approval-001",
                "approval_reference": "owner-approval-001",
                "approved_by": "owner@example.test",
                "reviewed_at": reviewed_at,
            },
            protocol={"audio_opening_authorized": True, "plan_hash": "plan-sha-001"},
            cases=[{"case_id": "a"}],
        )
        result = evaluate_manifest_readiness(manifest, product_root=tmp_path / "product")
        assert result["ready_for_execution"] is False
        assert "reviewed_at must be an ISO-8601 timestamp with timezone" in result["errors"]
