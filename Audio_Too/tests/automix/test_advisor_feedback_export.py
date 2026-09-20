"""Reviewed advisor feedback, privacy export, replay, and deletion tests."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for import_root in (ROOT / "server" / "app", ROOT / "studio" / "audio_analysis"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import advisor_feedback  # noqa: E402
import artifact_store  # noqa: E402
import db  # noqa: E402
import event_store  # noqa: E402
from audio_analysis.integration.kenn_advisor import (  # noqa: E402
    CONTRACT_SCHEMA,
    SHADOW_RECEIPT_SCHEMA,
    mix_plan_revision,
)
from audio_analysis.mixdown.mix_decision_engine import (  # noqa: E402
    BusMixConfig,
    MixPlan,
    StemMixConfig,
)
from scripts.eval.automix_advisor_replay import replay_cases  # noqa: E402
from scripts.eval.automix_advisor_reviewed_export import export_reviewed_cases  # noqa: E402
from app.api_schemas import (  # noqa: E402
    AutomixAdvisorFeedbackRequest,
    SchemaValidationError,
)
from app.routes.automix_routes import handle_automix_get, handle_automix_post  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    event_store.reset_connection_state()
    db.init_db()
    yield tmp_path
    artifact_store.reset_connection_state()
    event_store.reset_connection_state()


def _shadow_artifact(root: Path, *, project_id: str = "private-project") -> dict:
    plan = MixPlan(
        stems=[
            StemMixConfig(
                stem_name="Client Name - Lead Vocal.wav",
                instrument="vocal",
                compressor={"ratio": 3.5},
            )
        ],
        bus=BusMixConfig(),
        genre="pop",
        target_lufs=-14.0,
        decisions_log=["Private Client Name requested a brighter vocal."],
    )
    revision = mix_plan_revision(plan)
    proposal = {
        "schema": CONTRACT_SCHEMA,
        "source_plan_revision": revision,
        "model_version": "kenn-deterministic-advisor-v1",
        "prompt_version": "canonical-drift-policy-v1",
        "correlation_id": "automix-job:private-job",
        "operations": [
            {
                "stem_id": "Client Name - Lead Vocal.wav",
                "operation": "gain_delta",
                "value": -1.0,
                "unit": "dB",
                "evidence_source_ids": ["automix-gain-note@index:v-test"],
                "confidence": 0.95,
                "reason": "Private source name should not survive export.",
            }
        ],
    }
    receipt = {
        "schema": SHADOW_RECEIPT_SCHEMA,
        "correlation_id": "automix-job:private-job",
        "source_plan_revision": revision,
        "source_plan": asdict(plan),
        "status": "valid",
        "proposal": proposal,
        "operation_count": 1,
        "would_change": [],
        "rejection_reason": "",
        "latency_ms": 1.0,
    }
    path = root / "shadow.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return artifact_store.register_file(
        path,
        kind=advisor_feedback.SHADOW_KIND,
        media_type="application/json",
        producer="test",
        producer_version="1",
        project_id=project_id,
        external_key="automix-job:private-job:advisor-shadow",
        metadata={"job_id": "private-job", "source_plan_revision": revision},
    )


def _preview_artifact(root: Path, shadow: dict, *, project_id: str = "private-project") -> dict:
    path = root / "preview.wav"
    path.write_bytes(b"RIFF synthetic preview")
    return artifact_store.register_file(
        path,
        kind=advisor_feedback.PREVIEW_KIND,
        media_type="audio/wav",
        producer="test",
        producer_version="1",
        project_id=project_id,
        external_key="automix-job:private-job:advisor-preview:0",
        parent_ids=(shadow["id"],),
        metadata={
            "job_id": "private-job",
            "shadow_artifact_id": shadow["id"],
            "source_plan_revision": shadow["metadata"]["source_plan_revision"],
            "operation_index": 0,
        },
    )


def test_audible_rating_requires_lineaged_preview(env: Path) -> None:
    shadow = _shadow_artifact(env)
    with pytest.raises(
        advisor_feedback.AdvisorFeedbackError,
        match="requires an A/B preview artifact",
    ):
        advisor_feedback.record_feedback(
            job_id="private-job",
            shadow_artifact_id=shadow["id"],
            operation_index=0,
            decision="accepted",
            usefulness_rating=5,
            explanation_quality_rating=4,
            audible_improvement_rating=5,
        )
    preview = _preview_artifact(env, shadow)
    feedback = advisor_feedback.record_feedback(
        job_id="private-job",
        shadow_artifact_id=shadow["id"],
        operation_index=0,
        decision="accepted",
        usefulness_rating=5,
        explanation_quality_rating=4,
        audible_improvement_rating=5,
        preview_artifact_id=preview["id"],
        reason="Contains private reviewer prose.",
    )
    assert feedback["decision"] == "accepted"
    assert feedback["audible_improvement_rating"] == 5


def test_feedback_rejects_wrong_job_and_duplicate_operation(env: Path) -> None:
    shadow = _shadow_artifact(env)
    kwargs = {
        "shadow_artifact_id": shadow["id"],
        "operation_index": 0,
        "decision": "needs_work",
        "usefulness_rating": 3,
        "explanation_quality_rating": 4,
    }
    with pytest.raises(advisor_feedback.AdvisorFeedbackError, match="does not belong"):
        advisor_feedback.record_feedback(job_id="other-job", **kwargs)
    advisor_feedback.record_feedback(job_id="private-job", **kwargs)
    with pytest.raises(advisor_feedback.AdvisorFeedbackError, match="already has feedback"):
        advisor_feedback.record_feedback(job_id="private-job", **kwargs)


def test_export_removes_identifiers_replays_and_supports_deletion(env: Path) -> None:
    shadow = _shadow_artifact(env)
    feedback = advisor_feedback.record_feedback(
        job_id="private-job",
        shadow_artifact_id=shadow["id"],
        operation_index=0,
        decision="needs_work",
        usefulness_rating=3,
        explanation_quality_rating=4,
        reason="Contains private reviewer prose.",
    )
    with db.connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM automix_advisor_feedback")]
    exported = export_reviewed_cases(rows, salt=b"0123456789abcdef", minimum_cases=1)
    assert exported["summary"]["exported_cases"] == 1
    assert exported["readiness"]["ready"] is False
    assert exported["summary"]["preview_backed_audible_cases"] == 0
    encoded = json.dumps(exported)
    for private_value in (
        "private-job",
        "private-project",
        "Client Name",
        "brighter vocal",
        "private reviewer prose",
        shadow["id"],
        feedback["id"],
    ):
        assert private_value not in encoded
    replay = replay_cases(exported["cases"])
    assert replay["summary"]["expected_status_accuracy"] == 1.0
    assert replay["summary"]["human_rating_means"]["usefulness"] == 3.0
    assert replay["summary"]["human_rating_means"]["audible_improvement"] is None

    assert advisor_feedback.delete_feedback(feedback["id"], actor_id="privacy-test") is True
    assert advisor_feedback.get_feedback(feedback["id"]) is None
    assert advisor_feedback.delete_feedback(feedback["id"]) is False
    with db.connect() as conn:
        events = conn.execute(
            "SELECT event_type, payload_json FROM domain_events "
            "WHERE aggregate_id = ? ORDER BY occurred_at",
            (feedback["id"],),
        ).fetchall()
    assert [row["event_type"] for row in events] == [
        "automix.advisor_feedback_recorded",
        "automix.advisor_feedback_deleted",
    ]
    assert "private reviewer prose" not in "".join(row["payload_json"] for row in events)


def test_advisor_feedback_request_schema_is_strict() -> None:
    payload = {
        "job_id": "job-1",
        "shadow_artifact_id": "art_shadow_1",
        "operation_index": 0,
        "decision": "needs_work",
        "usefulness_rating": 3,
        "explanation_quality_rating": 4,
        "audible_improvement_rating": None,
        "preview_artifact_id": "",
        "reason": "Needs a smaller move.",
    }
    request = AutomixAdvisorFeedbackRequest.from_payload(payload)
    assert request.decision == "needs_work"
    with pytest.raises(SchemaValidationError, match="Unknown request field"):
        AutomixAdvisorFeedbackRequest.from_payload({**payload, "surprise": True})
    with pytest.raises(SchemaValidationError, match="integer from 1 to 5"):
        AutomixAdvisorFeedbackRequest.from_payload({**payload, "usefulness_rating": True})


class _RouteHandler:
    def __init__(self, payload: dict):
        self.payload = payload
        self.status = 0
        self.response = {}

    def read_json_body(self):
        return self.payload

    def send_json(self, status: int, payload: dict):
        self.status = status
        self.response = payload

    def send_file(self, path: Path, content_type: str, *, filename: str = ""):
        self.status = 200
        self.response = {
            "bytes": path.read_bytes(),
            "content_type": content_type,
            "filename": filename,
        }


def test_authenticated_route_records_minimal_response(monkeypatch) -> None:
    payload = {
        "job_id": "job-1",
        "shadow_artifact_id": "art_shadow_1",
        "operation_index": 0,
        "decision": "accepted",
        "usefulness_rating": 5,
        "explanation_quality_rating": 4,
    }
    monkeypatch.setattr(
        advisor_feedback,
        "record_feedback",
        lambda **_kwargs: {
            "id": "aaf_test",
            "decision": "accepted",
            "operation_index": 0,
            "audible_improvement_rating": None,
        },
    )
    handler = _RouteHandler(payload)
    assert handle_automix_post(handler, "/api/automix/advisor-feedback", "") is True
    assert handler.status == 201
    assert handler.response == {
        "ok": True,
        "feedback": {
            "id": "aaf_test",
            "decision": "accepted",
            "operation_index": 0,
            "has_audible_evidence": False,
        },
    }


def test_authenticated_delete_route_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(advisor_feedback, "delete_feedback", lambda _feedback_id: True)
    handler = _RouteHandler({"feedback_id": "aaf_test"})
    assert (
        handle_automix_post(
            handler,
            "/api/automix/advisor-feedback/delete",
            "",
        )
        is True
    )
    assert handler.status == 200
    assert handler.response == {"ok": True, "deleted": True}


def test_preview_playback_route_checks_kind_and_integrity(env: Path) -> None:
    shadow = _shadow_artifact(env)
    preview = _preview_artifact(env, shadow)
    handler = _RouteHandler({})
    assert (
        handle_automix_get(
            handler,
            f"/api/v1/automix/advisor-previews/{preview['id']}",
            "",
        )
        is True
    )
    assert handler.status == 200
    assert handler.response["content_type"] == "audio/wav"
    assert handler.response["bytes"].startswith(b"RIFF")

    artifact_store.resolve_path(preview["id"]).write_bytes(b"tampered")
    tampered = _RouteHandler({})
    handle_automix_get(
        tampered,
        f"/api/v1/automix/advisor-previews/{preview['id']}",
        "",
    )
    assert tampered.status == 409
