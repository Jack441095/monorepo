"""Offline AudioGen and AutoMix jobs, including the tasks they are bound to.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kenn.core.audition_revision import build_audition_revision_brief
from kenn.core.audiogen_artifacts import midi_import_payload
from kenn.core.session_context import safe_audio_job

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def audiogen_artifact(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id", "")).strip()[:128]
    if not job_id:
        raise ValueError("job_id is required")
    response = facade.client.get("/api/audiogen/job", {"id": job_id})
    job = response.get("job") if isinstance(response, dict) else None
    if not isinstance(job, dict):
        return {
            "schema": "kenn.audiogen_artifact_inspection.v1",
            "job_id": job_id,
            "status": "unavailable",
            "artifact": None,
            "ready_for_review": False,
            "available_actions": [],
            "limitations": ["AudioGen job was not available."],
        }
    safe_job = safe_audio_job(job)
    artifact = safe_job.get("artifact") if isinstance(safe_job.get("artifact"), dict) else None
    validation = artifact.get("validation") if isinstance(artifact, dict) else None
    ready = bool(
        str(safe_job.get("status", "")).lower() in {"completed", "success", "complete"}
        and isinstance(validation, dict)
        and validation.get("ok") is True
    )
    limitations: list[str] = []
    if artifact is None:
        limitations.append("The job has no inspectable artifact metadata yet.")
    if not ready:
        limitations.append("Artifact is not ready for audition or Live import.")
    else:
        limitations.append("Use create_midi_clip_from_artifact to create a confirmation-only Live proposal; applying it still requires explicit confirmation and readback.")
    return {
        "schema": "kenn.audiogen_artifact_inspection.v1",
        "job_id": job_id,
        "status": safe_job.get("status", "unknown"),
        "artifact": artifact,
        "ready_for_review": ready,
        "available_actions": [],
        "limitations": limitations,
    }


def queue_assistant_audiogen_job(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not task_id or not step_id or not session_id:
        raise ValueError("task_id, step_id, and session_id are required")
    try:
        bars = int(args.get("bars", 4))
        candidates = int(args.get("candidates", 1))
    except (TypeError, ValueError):
        raise ValueError("bars and candidates must be integers") from None
    if not 1 <= bars <= 24 or not 1 <= candidates <= 4:
        raise ValueError("bars must be 1..24 and candidates must be 1..4")
    result = facade.client.post(
        "/api/audiogen/render-song",
        {
            "emotion": str(args.get("emotion", "")).strip()[:64],
            "bars": bars,
            "k": candidates,
        },
    )
    if result.get("changed") is True or result.get("receipt"):
        raise RuntimeError("KENN returned a Live mutation from an offline AudioGen queue call")
    job = result.get("job") if isinstance(result.get("job"), dict) else None
    if job is None:
        return {**result, "assistant_task": {"ok": False, "errors": ["AudioGen did not return a job identity."]}}
    evidence = facade._audiogen_job_evidence(job)
    binding = facade.coordinator.record_evidence(
        task_id=task_id,
        step_id=step_id,
        evidence=evidence,
        context=facade._assistant_context(session_id),
    )
    return {**result, "job_evidence": evidence, "assistant_task": binding}


def refresh_assistant_audiogen_job(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    job_id = str(args.get("job_id", "")).strip()[:128]
    if not task_id or not step_id or not session_id or not job_id:
        raise ValueError("task_id, step_id, session_id, and job_id are required")
    result = facade.client.get("/api/audiogen/job", {"id": job_id})
    job = result.get("job") if isinstance(result.get("job"), dict) else None
    if job is None:
        return {**result, "assistant_task": {"ok": False, "errors": ["AudioGen job was not found."]}}
    evidence = facade._audiogen_job_evidence(job)
    context = facade._assistant_context(session_id, audiogen_job_id=job_id)
    if evidence["status"] == "failed":
        binding = facade.coordinator.record_failure(
            task_id=task_id, step_id=step_id, evidence=evidence, context=context,
        )
    else:
        binding = facade.coordinator.record_evidence(
            task_id=task_id, step_id=step_id, evidence=evidence, context=context,
        )
    return {**result, "job_evidence": evidence, "assistant_task": binding}


def bind_assistant_automix_job(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()[:128]
    step_id = str(args.get("step_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    job_id = str(args.get("job_id", "")).strip()[:128]
    if not task_id or not step_id or not session_id or not job_id:
        raise ValueError("task_id, step_id, session_id, and job_id are required")
    result = facade.client.get("/api/automix-status", {"id": job_id})
    evidence = facade._automix_job_evidence(result, requested_job_id=job_id)
    if evidence["status"] == "unavailable":
        return {
            **result,
            "job_evidence": evidence,
            "assistant_task": {
                "ok": False,
                "errors": [evidence.get("error") or "AutoMix job status was not available."],
            },
        }
    context = facade._assistant_context(session_id, automix_job_id=job_id)
    if evidence["status"] == "failed":
        binding = facade.coordinator.record_failure(
            task_id=task_id, step_id=step_id, evidence=evidence, context=context,
        )
    else:
        binding = facade.coordinator.record_evidence(
            task_id=task_id, step_id=step_id, evidence=evidence, context=context,
        )
    return {**result, "job_evidence": evidence, "assistant_task": binding}


def generate_audiogen_audio_candidate(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    prompt = str(args.get("prompt", "")).strip()[:512]
    if not prompt:
        raise ValueError("prompt is required")
    result = facade.client.post(
        "/api/audiogen/generate",
        {
            "prompt": prompt,
            "emotion": str(args.get("emotion", ""))[:64],
            "bars": args.get("bars", 8),
        },
    )
    if result.get("changed") is True or result.get("receipt"):
        raise RuntimeError("KENN returned a Live mutation from an offline AudioGen candidate call")
    src = str(result.get("src", "")).strip()
    listen_url = ""
    if src.startswith("/"):
        listen_url = str(getattr(facade.client, "base_url", "")).rstrip("/") + src
    elif src.startswith("http://") or src.startswith("https://"):
        listen_url = src
    return {
        "schema": "kenn.audiogen_audio_candidate.v1",
        "ok": bool(result.get("ok")),
        "emotion": result.get("emotion", ""),
        "bars": result.get("bars", ""),
        "audio_url": listen_url,
        "artifact": result.get("artifact"),
        "portfolio_title": result.get("portfolio_title", ""),
        "audition": {
            "status": "ready" if listen_url else "unavailable",
            "audio_url": listen_url,
            "transport": "local_http",
            "live_mutation": False,
        },
        "limitations": [] if listen_url else ["AudioGen did not return a listenable local WAV URL."],
        "error": result.get("error", ""),
    }


def compare_audiogen_audio_candidates(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    source_a = str(args.get("source_a", "")).strip()[:512]
    source_b = str(args.get("source_b", "")).strip()[:512]
    if not source_a or not source_b:
        raise ValueError("source_a and source_b are required")
    result = facade.client.post(
        "/api/audiogen/audio-compare",
        {"source_a": source_a, "source_b": source_b},
    )
    if result.get("changed") is True or result.get("receipt"):
        raise RuntimeError("KENN returned a Live mutation from an offline audio comparison call")
    return result


def create_midi_clip_from_artifact(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id", "")).strip()[:128]
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not job_id or not session_id:
        raise ValueError("job_id and session_id are required")
    response = facade.client.get("/api/audiogen/job", {"id": job_id})
    job = response.get("job") if isinstance(response, dict) else None
    if not isinstance(job, dict):
        return {"ok": False, "error": "AudioGen job was not available.", "job_id": job_id}
    safe_job = safe_audio_job(job)
    if str(safe_job.get("status", "")).lower() not in {"completed", "success", "complete"}:
        return {"ok": False, "error": "AudioGen job is not complete; no Live proposal was created.", "job_id": job_id, "status": safe_job.get("status", "unknown")}
    artifact = safe_job.get("artifact") if isinstance(safe_job.get("artifact"), dict) else None
    imported = midi_import_payload(artifact)
    if not imported.get("ok"):
        return {
            "ok": False,
            "error": "AudioGen MIDI artifact is not import-ready; no Live proposal was created.",
            "job_id": job_id,
            "artifact": artifact,
            "validation": imported.get("validation"),
            "limitations": imported.get("errors", []),
        }
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "track_name": str(args.get("track_name", ""))[:256],
        "clip_slot_index": args.get("clip_slot_index"),
        "length": imported["length"],
        "notes": imported["notes"],
        "source_artifact_sha256": imported["source_artifact_sha256"],
        "source_artifact_id": imported.get("artifact_id", ""),
        "source_context": imported.get("generation_context"),
    }
    result = facade.client.post("/api/ableton/midi-clip/proposal", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from an artifact proposal-only MCP call")
    return {
        **result,
        "source": {
            "job_id": job_id,
            "artifact_id": imported.get("artifact_id", ""),
            "sha256": imported.get("source_artifact_sha256", ""),
        },
    }


def generate_audiogen_midi_revision_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    feedback_id = str(args.get("feedback_id", "")).strip()[:128]
    if not session_id or not feedback_id:
        raise ValueError("session_id and feedback_id are required")
    facade._assistant_binding_ids(args)
    try:
        seed = int(args["seed"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("seed must be an integer for a revision candidate") from None
    feedback_result = facade.client.get(
        "/api/ableton/audition-feedback",
        {"session_id": session_id, "limit": 100},
    )
    items = feedback_result.get("feedback", []) if isinstance(feedback_result, dict) else []
    feedback = next(
        (
            item for item in items
            if isinstance(item, dict) and str(item.get("feedback_id", "")) == feedback_id
        ),
        None,
    )
    if feedback is None:
        raise ValueError("feedback_id was not found in the requested session")
    brief = build_audition_revision_brief(feedback, comparison=args.get("comparison"))
    target = brief["target"]
    payload = {
        "session_id": session_id,
        "track_index": target["track_index"],
        "track_name": target["track_name"],
        "clip_slot_index": target["clip_slot_index"],
        "emotion": str(args.get("emotion", "joy"))[:64],
        "bars": args.get("bars", 4),
        "seed": str(seed),
        "revision_brief": brief,
    }
    result = facade.client.post("/api/audiogen/midi-proposal", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a revision proposal-only MCP call")
    result = {**result, "revision_brief": brief}
    binding = facade._bind_assistant_proposal(args=args, result=result, session_id=session_id)
    if binding is not None:
        result = {**result, "assistant_task": binding}
    return result


def generate_audiogen_midi_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    track_name = str(args.get("track_name", "")).strip()[:256]
    if not session_id or not track_name:
        raise ValueError("session_id and track_name are required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "track_name": track_name,
        "clip_slot_index": args.get("clip_slot_index"),
        "emotion": str(args.get("emotion", "joy"))[:64],
        "bars": args.get("bars", 4),
        "seed": str(args.get("seed", ""))[:128],
    }
    result = facade.client.post("/api/audiogen/midi-proposal", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from an AudioGen proposal-only MCP call")
    return result
