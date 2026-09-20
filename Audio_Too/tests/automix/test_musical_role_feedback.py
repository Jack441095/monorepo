"""Durable MusicalRole correction lifecycle and privacy export tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import artifact_store
import db
import musical_role_feedback
from audio_analysis.mixdown.musical_roles import apply_role_corrections, infer_musical_role
from audio_analysis.mixdown.stem_classifier import StemProfile
from scripts.eval.musical_role_reviewed_export import export_reviewed_role_cases


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "roles.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    db.init_db()
    yield
    artifact_store.reset_connection_state()


def _roles():
    profile = StemProfile(
        name="Guitar 04.wav",
        instrument="guitar",
        classification_confidence=0.82,
        classification_method="combined",
    )
    inferred = infer_musical_role(profile)
    applied = apply_role_corrections([inferred], {
        "Guitar 04.wav": {"role": "focal_element", "priority": "foreground"}
    })[0]
    return inferred, applied


def test_record_is_retry_safe_lineaged_and_emits_one_event(env) -> None:
    inferred, applied = _roles()
    kwargs = {
        "job_id": "job-1",
        "project_id": "project-1",
        "source_plan_revision": "a" * 64,
        "inferred_roles": [inferred],
        "applied_roles": [applied],
    }

    first = musical_role_feedback.record_applied_corrections(**kwargs)
    replay = musical_role_feedback.record_applied_corrections(**kwargs)

    assert replay == first
    assert first[0]["inferred_ambiguous"] == 1
    assert first[0]["corrected_role"] == "focal_element"
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM automix_musical_role_corrections").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_events WHERE event_type = 'automix.musical_role_corrected'"
        ).fetchone()[0] == 1


def test_conflicting_retry_fails_closed(env) -> None:
    inferred, applied = _roles()
    musical_role_feedback.record_applied_corrections(
        job_id="job-1", project_id="project-1", source_plan_revision="a" * 64,
        inferred_roles=[inferred], applied_roles=[applied],
    )
    changed = apply_role_corrections([inferred], {
        "Guitar 04.wav": {"role": "accompaniment", "priority": "support"}
    })[0]
    with pytest.raises(musical_role_feedback.MusicalRoleFeedbackError, match="Conflicting"):
        musical_role_feedback.record_applied_corrections(
            job_id="job-1", project_id="project-1", source_plan_revision="b" * 64,
            inferred_roles=[inferred], applied_roles=[changed],
        )


def test_export_removes_identifiers_and_reports_honest_readiness(env) -> None:
    inferred, applied = _roles()
    musical_role_feedback.record_applied_corrections(
        job_id="secret-job", project_id="secret-project", source_plan_revision="a" * 64,
        inferred_roles=[inferred], applied_roles=[applied],
    )
    report = export_reviewed_role_cases(
        musical_role_feedback.list_corrections(), salt=b"0123456789abcdef", minimum_cases=20
    )
    rendered = str(report)

    assert report["readiness"]["ready"] is False
    assert report["summary"]["reviewed_corrections"] == 1
    assert "secret-job" not in rendered
    assert "secret-project" not in rendered
    assert "Guitar 04.wav" not in rendered


def test_project_privacy_deletion_removes_rows_and_keeps_receipt(env) -> None:
    inferred, applied = _roles()
    musical_role_feedback.record_applied_corrections(
        job_id="job-1", project_id="project-1", source_plan_revision="a" * 64,
        inferred_roles=[inferred], applied_roles=[applied],
    )

    assert musical_role_feedback.delete_corrections_for_project("project-1") == 1
    assert musical_role_feedback.list_corrections(project_id="project-1") == []
    with db.connect() as conn:
        receipt = conn.execute(
            "SELECT payload_json FROM domain_events "
            "WHERE event_type = 'automix.musical_role_corrections_deleted'"
        ).fetchone()
    assert receipt is not None
    assert "Guitar 04.wav" not in receipt["payload_json"]
