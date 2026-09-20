from __future__ import annotations

from kenn.core.assistant_coordinator import AssistantCoordinator, DIRECTIVE_SCHEMA
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.session_context import build_session_context


def _context(track_name: str = "Bass") -> dict:
    return build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected",
            "tempo": 122.0,
            "is_playing": False,
            "tracks": [{"index": 0, "name": track_name, "type": "midi", "devices": []}],
        },
    )


def _plan(context: dict) -> dict:
    inspect = DeliberativeStep.create(
        step_id="inspect",
        kind="inspection",
        action="inspect_live",
        objective="Inspect the bass relationship.",
        rationale="Current evidence must precede a recommendation.",
        expected_evidence=["fresh session context"],
    )
    propose = DeliberativeStep.create(
        step_id="propose",
        kind="live_proposal",
        action="create_live_proposal",
        objective="Prepare the smallest supported bass adjustment.",
        rationale="The producer must review an exact proposal.",
        depends_on=["inspect"],
        expected_evidence=["verified applied Live receipt"],
    )
    return DeliberativePlan.create(
        goal="Make the bass sit better",
        context=context,
        status="ready",
        steps=[inspect, propose],
    ).to_dict()


def test_coordinator_exposes_only_the_first_valid_step(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))

    started = coordinator.start(plan=_plan(context), context=context)

    assert started["ok"] is True
    directive = started["next_step"]
    assert directive["schema"] == DIRECTIVE_SCHEMA
    assert directive["mode"] == "inspect"
    assert directive["step_id"] == "inspect"
    assert directive["execution_authorized"] is False
    assert "proposal" not in directive


def test_coordinator_advances_after_typed_inspection_evidence(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_plan(context), context=context)["task"]

    advanced = coordinator.record_evidence(
        task_id=task["task_id"],
        step_id="inspect",
        evidence=context,
        context=context,
    )

    assert advanced["ok"] is True
    assert advanced["completed_step"] is True
    assert advanced["task"]["completed_step_ids"] == ["inspect"]
    assert advanced["next_step"]["mode"] == "prepare_live_proposal"
    assert advanced["next_step"]["execution_authorized"] is False


def test_coordinator_requires_replan_before_new_work_on_changed_session(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_plan(context), context=context)["task"]

    resumed = coordinator.resume(task_id=task["task_id"], context=_context("Renamed Bass"))

    assert resumed["ok"] is True
    assert resumed["next_step"]["mode"] == "replan"
    assert "session changed" in resumed["next_step"]["reason"].lower()
    assert resumed["next_step"]["context_changed_domains"] == ["Live session"]
    assert resumed["next_step"]["execution_authorized"] is False


def test_coordinator_identifies_new_slo_classification_as_replan_drift(tmp_path) -> None:
    initial = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "classification.db"))
    task = coordinator.start(plan=_plan(initial), context=initial)["task"]
    classified = build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected",
            "tempo": 122.0,
            "is_playing": False,
            "tracks": [{"index": 0, "name": "Bass", "type": "midi", "devices": []}],
        },
        audio_classifications=[{
            "schema": "kenn.audio_classification.v1",
            "status": "completed",
            "audio_sha256": "sha256:" + ("a" * 64),
            "model_id": "slo-export-v1",
            "model_sha256": "sha256:" + ("b" * 64),
            "label_map_sha256": "sha256:" + ("c" * 64),
            "inference_version": "1",
            "audio_only": [{"label": "bass", "probability": 0.91}],
            "metadata_assisted": [{"label": "bass", "probability": 0.94}],
            "selected_label": "bass",
            "selected_source": "audio_only",
            "confidence_band": "high",
            "out_of_distribution": {"status": "in_distribution", "score": 0.04},
            "evidence_used": ["audio_only"],
            "latency_ms": 12,
            "limitations": ["advisory only"],
        }],
    )

    resumed = coordinator.resume(task_id=task["task_id"], context=classified)

    assert resumed["next_step"]["mode"] == "replan"
    assert resumed["next_step"]["context_changed_domains"] == ["SLO audio classification"]


def test_coordinator_waits_for_identity_bound_confirmation(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_plan(context), context=context)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="inspect", evidence=context, context=context,
    )

    waiting = coordinator.record_evidence(
        task_id=task["task_id"],
        step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1",
            "status": "confirmation_required",
            "requires_confirmation": True,
            "action_id": "action-1",
            "confirmation_token": "must-not-escape",
        },
        context=context,
    )

    assert waiting["ok"] is True
    assert waiting["completed_step"] is False
    assert waiting["next_step"]["mode"] == "wait_for_confirmation"
    assert waiting["next_step"]["execution_authorized"] is False
    assert "must-not-escape" not in str(waiting)


def test_coordinator_completes_only_after_matching_verified_receipt(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_plan(context), context=context)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="inspect", evidence=context, context=context,
    )
    coordinator.record_evidence(
        task_id=task["task_id"],
        step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1",
            "status": "confirmation_required",
            "requires_confirmation": True,
            "action_id": "action-1",
        },
        context=context,
    )

    completed = coordinator.record_evidence(
        task_id=task["task_id"],
        step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_receipt.v1",
            "status": "applied",
            "verified": True,
            "receipt_id": "receipt-1",
            "action_id": "action-1",
        },
        context=_context("Changed after apply"),
    )

    assert completed["ok"] is True
    assert completed["task"]["status"] == "completed"
    assert completed["next_step"]["mode"] == "complete"
    assert completed["next_step"]["execution_authorized"] is False


def test_coordinator_rejects_context_from_another_session(tmp_path) -> None:
    context = _context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_plan(context), context=context)["task"]
    other = build_session_context(session_id="other-song", snapshot={"status": "connected", "tracks": []})

    resumed = coordinator.resume(task_id=task["task_id"], context=other)

    assert resumed["ok"] is True
    assert resumed["next_step"]["ok"] is False
    assert resumed["next_step"]["execution_authorized"] is False
    assert "another session" in resumed["next_step"]["errors"][0]


def _generation_context(
    *, completed_job: bool = False, track_name: str = "Bass", other_job_status: str = "",
) -> dict:
    jobs = []
    if completed_job:
        jobs.append({
            "schema": "kenn.audiogen_render_job.v1",
            "job_id": "job-1",
            "status": "completed",
            "artifact": {
                "schema": "kenn.audiogen_artifact.v1",
                "kind": "audio",
                "content_hash": "sha256:" + ("a" * 64),
            },
        })
    if other_job_status:
        jobs.append({
            "schema": "kenn.audiogen_render_job.v1",
            "job_id": "job-other",
            "status": other_job_status,
        })
    return build_session_context(
        session_id="song-1",
        snapshot={"status": "connected", "tracks": [{"index": 0, "name": track_name, "devices": []}]},
        audiogen_available=True,
        audiogen_jobs=jobs,
    )


def _generation_review_plan(context: dict) -> dict:
    generate = DeliberativeStep.create(
        step_id="generate", kind="generation_job", action="create_generation_job",
        objective="Generate one candidate.", rationale="Create the artifact before reviewing it.",
        expected_evidence=["completed generation job"],
    )
    review = DeliberativeStep.create(
        step_id="review", kind="inspection", action="review_generated_asset",
        objective="Review the generated candidate.", rationale="Audition before deciding to use it.",
        depends_on=["generate"], expected_evidence=["artifact inspection"],
    )
    return DeliberativePlan.create(
        goal="Generate and review an idea", context=context, status="ready", steps=[generate, review],
    ).to_dict()


def test_coordinator_rebinds_only_the_completed_generation_domain(tmp_path) -> None:
    initial = _generation_context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_generation_review_plan(initial), context=initial)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued"},
        context=initial,
    )

    advanced = coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "completed"},
        context=_generation_context(completed_job=True),
    )

    assert advanced["ok"] is True
    assert advanced["context_rebind"] == {"ok": True, "rebound": True, "error": ""}
    assert advanced["next_step"]["mode"] == "inspect"
    assert advanced["next_step"]["action"] == "review_generated_asset"
    assert advanced["next_step"]["execution_authorized"] is False


def test_coordinator_refuses_generation_rebind_when_live_changed_too(tmp_path) -> None:
    initial = _generation_context()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_generation_review_plan(initial), context=initial)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued"},
        context=initial,
    )

    advanced = coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "completed"},
        context=_generation_context(completed_job=True, track_name="Renamed Bass"),
    )

    assert advanced["ok"] is True
    assert advanced["context_rebind"]["ok"] is False
    assert "live context changed" in advanced["context_rebind"]["error"].lower()
    assert advanced["next_step"]["mode"] == "replan"


def test_coordinator_refuses_generation_rebind_when_another_job_changed(tmp_path) -> None:
    initial = _generation_context(other_job_status="queued")
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "memory.db"))
    task = coordinator.start(plan=_generation_review_plan(initial), context=initial)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "queued"},
        context=initial,
    )

    advanced = coordinator.record_evidence(
        task_id=task["task_id"], step_id="generate",
        evidence={"schema": "kenn.audiogen_render_job.v1", "job_id": "job-1", "status": "completed"},
        context=_generation_context(completed_job=True, other_job_status="completed"),
    )

    assert advanced["context_rebind"]["ok"] is False
    assert "unrelated generation evidence changed" in advanced["context_rebind"]["error"].lower()
    assert advanced["next_step"]["mode"] == "replan"
