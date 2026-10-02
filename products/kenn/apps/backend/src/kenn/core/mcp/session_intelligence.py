"""The canonical context read and the briefings derived from it.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from kenn.core.mcp.errors import KennTransportError
from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison
from kenn.core.session_context import build_session_context, refresh_session_context_fingerprint
from kenn.core.session_intelligence import (
    build_session_intelligence,
    explanation_sections,
    retrieval_sources_from_cache,
)
from kenn.core.session_world_model import SessionWorldModel

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def kenn_context(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    # Context is an explicit intelligence read, not a liveness probe:
    # request the richer, still read-only snapshot so tempo, meter,
    # key/scale, mixer observations, routing, sends, clip inventory,
    # and selected-object state are available to the LLM.  The fast
    # control/proposal path continues to use topology-only reads.
    snapshot = facade.client.get("/api/ableton/osc/session", {"detail": "understanding"})
    plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
    plugin_frames: list[dict[str, Any]] = []
    if plugin_session_id:
        plugin_result = facade.client.get(
            "/api/plugin-live-review", {"session_id": plugin_session_id}
        )
        plugin_context = plugin_result.get("live_context") if isinstance(plugin_result, dict) else None
        if isinstance(plugin_result, dict) and plugin_result.get("ok") is True and isinstance(plugin_context, dict):
            plugin_frames.append(plugin_context)
    include_device_matrix = args.get("include_device_matrix", True)
    include_device_parameters = args.get("include_device_parameters", False)
    if not isinstance(include_device_matrix, bool) or not isinstance(include_device_parameters, bool):
        raise ValueError("include_device_matrix and include_device_parameters must be boolean")
    device_matrix = None
    if include_device_matrix:
        device_matrix = facade.client.get(
            "/api/ableton/device-matrix",
            {"parameters": "1" if include_device_parameters else "0"},
        )
    audiogen_jobs: list[dict[str, Any]] = []
    try:
        audiogen_status = facade.client.get("/api/audiogen/status")
        queue = audiogen_status.get("render_queue") if isinstance(audiogen_status, dict) else {}
        if isinstance(queue, dict):
            for group in ("running", "queued", "recent"):
                items = queue.get(group) if isinstance(queue.get(group), list) else []
                audiogen_jobs.extend(item for item in items if isinstance(item, dict))
    except KennTransportError:
        # Context is still useful when an optional creative service is
        # unavailable; the limitation is made explicit below.
        audiogen_status = None
    audiogen_job_id = str(args.get("audiogen_job_id", "")).strip()[:128]
    if audiogen_job_id:
        exact_job_result = facade.client.get("/api/audiogen/job", {"id": audiogen_job_id})
        exact_job = exact_job_result.get("job") if isinstance(exact_job_result, dict) else None
        if isinstance(exact_job, dict):
            exact_identity = str(exact_job.get("job_id") or exact_job.get("id") or "")
            existing_identities = {
                str(item.get("job_id") or item.get("id") or "")
                for item in audiogen_jobs
            }
            if exact_identity not in existing_identities:
                audiogen_jobs.append(exact_job)

    mix_reviews: list[dict[str, Any]] = []
    mix_review_id = str(args.get("mix_review_id", "")).strip()[:128]
    if mix_review_id:
        mix_result = facade.client.get("/api/mix-review-status", {"id": mix_review_id})
        if isinstance(mix_result, dict):
            review = mix_result.get("review")
            mix_reviews.append(review if isinstance(review, dict) else mix_result)

    automix_receipts: list[dict[str, Any]] = []
    automix_job_id = str(args.get("automix_job_id", "")).strip()[:128]
    if automix_job_id:
        automix_result = facade.client.get("/api/automix-status", {"id": automix_job_id})
        if isinstance(automix_result, dict):
            automix_receipt = facade._automix_job_evidence(
                automix_result, requested_job_id=automix_job_id,
            )
            if automix_receipt.get("status") != "unavailable":
                automix_receipts.append(automix_receipt)

    feedback_items: list[dict[str, Any]] = []
    if session_id:
        try:
            feedback_result = facade.client.get(
                "/api/ableton/audition-feedback",
                {"session_id": session_id, "limit": 16},
            )
            if isinstance(feedback_result, dict):
                items = feedback_result.get("feedback")
                if isinstance(items, list):
                    feedback_items = [item for item in items if isinstance(item, dict)]
        except KennTransportError:
            feedback_result = None

    profile_memory = facade.profile_store.context_memory(session_id) if session_id else {
        "producer_preferences": [], "episodic_outcomes": [],
    }

    context = build_session_context(
        snapshot=snapshot,
        session_id=session_id,
        plugin_frames=plugin_frames,
        mix_review_receipts=mix_reviews,
        audiogen_jobs=audiogen_jobs,
        automix_receipts=automix_receipts,
        audition_feedback=feedback_items,
        device_matrix=device_matrix,
        audiogen_available=isinstance(audiogen_status, dict) and audiogen_status.get("ok") is True,
        producer_preferences=profile_memory["producer_preferences"],
        episodic_outcomes=profile_memory["episodic_outcomes"],
    )
    if mix_review_id and plugin_session_id and mix_reviews and plugin_frames:
        # Keep the comparison in the canonical context as a typed
        # measurement. This lets planners and later intelligence
        # layers consume the same scope-aware evidence without
        # re-querying either source or reconstructing it from prose.
        realtime_mix_comparison = build_realtime_mix_comparison(
            mix_reviews[0],
            plugin_frames[0],
            review_id=mix_review_id,
            plugin_session_id=plugin_session_id,
        )
        context["realtime_mix_comparison"] = realtime_mix_comparison
        context["measurements"].append({
            "kind": "realtime_mix_comparison",
            **realtime_mix_comparison,
        })
        context["sources"].append({
            "kind": "realtime_mix_comparison",
            "status": "observed" if realtime_mix_comparison.get("comparison_available") else "unavailable",
            "observed_at": time.time(),
            "schema": realtime_mix_comparison.get("schema", ""),
        })
    if plugin_frames:
        context["limitations"].append(
            "Realtime plug-in evidence is a validated bus observation; it does not identify a Live track or device and does not authorize a mutation."
        )
    elif plugin_session_id:
        context["limitations"].append(
            "No fresh realtime plug-in review was available for the supplied plugin_session_id."
        )
    else:
        context["limitations"].append(
            "No realtime plug-in session was supplied; this context does not invent meter data."
        )
    if not audiogen_jobs and not isinstance(audiogen_status, dict):
        context["limitations"].append("AudioGen status was unavailable for this context read.")
    if session_id and feedback_result is None:
        context["limitations"].append("Audition feedback was unavailable for this context read.")
    if not mix_review_id:
        context["limitations"].append("No Mix Review id was supplied; uploaded review receipts were not queried.")
    if not automix_job_id:
        context["limitations"].append("No AutoMix job id was supplied; offline render receipts were not queried.")
    refresh_session_context_fingerprint(context)
    return context


def kenn_context_delta(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    context_args = {
        key: args[key]
        for key in (
            "session_id", "plugin_session_id", "mix_review_id", "automix_job_id", "audiogen_job_id",
            "include_device_matrix", "include_device_parameters",
        )
        if key in args
    }
    context = facade._dispatch("kenn_context", context_args)
    model = facade._world_models.get(session_id)
    if model is None:
        if len(facade._world_models) >= facade._max_world_models:
            facade._world_models.pop(next(iter(facade._world_models)))
        model = SessionWorldModel(session_id=session_id)
        facade._world_models[session_id] = model
    observed = model.observe_context(context)
    return {
        "schema": "kenn.session_world_delta.v1",
        "session_id": session_id,
        "delta": observed["delta"],
        "snapshot_fingerprint": context.get("snapshot_fingerprint", ""),
        "read_only": True,
        "advisory_only": True,
        "live_mutation_authorized": False,
    }


def kenn_session_intelligence(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    # Reuse the established one-owner context read. The resulting
    # intelligence brief is advisory and cannot be sent to any Live
    # action endpoint.
    context_args = {
        key: args[key]
        for key in (
            "session_id", "plugin_session_id", "mix_review_id", "automix_job_id", "audiogen_job_id",
            "include_device_matrix", "include_device_parameters",
        )
        if key in args
    }
    context = facade._dispatch("kenn_context", context_args)
    # Retrieval provenance must come from KENN's own cache, never an
    # MCP caller. The cache is scoped by session id and this helper
    # emits source identifiers/classes only, not chunks or queries.
    retrieval_sources = []
    session_id = str(args.get("session_id", "")).strip()[:128]
    if session_id:
        try:
            from kenn.core.session_memory import load_session
            retrieval_sources = retrieval_sources_from_cache(
                load_session(session_id=session_id).get("last_retrieved_results")
            )
        except Exception:
            # Optional previous-turn provenance cannot make the fresh
            # Live briefing unsafe or unavailable.
            retrieval_sources = []
    brief = build_session_intelligence(
        context,
        project_intent={
            "genre": args.get("genre", ""),
            "goal": args.get("goal", ""),
            "references": args.get("references", []),
        },
        retrieval_sources=retrieval_sources,
    )
    brief["explanation_sections"] = explanation_sections(brief)
    return brief


def kenn_session_doctor(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    from kenn.core.session_doctor import SessionDoctor
    from kenn.plugin_handoff import live_context_summary
    session_id = str(args.get("session_id", "doctor_session"))
    session_state = facade.client.get("/api/ableton/osc/session", {"detail": "understanding"})
    telemetry = live_context_summary(session_id)
    report = SessionDoctor.audit(session_state if isinstance(session_state, dict) else {}, meters=telemetry)
    remediated = None
    if args.get("auto_remediate") and report.remediation_batch:
        remediated = facade.client.post("/api/kenn/autonomous-execute-batch", {
            "session_id": str(args.get("session_id", "doctor_session")),
            "batch": report.remediation_batch,
        })
    return {
        "ok": True,
        "track_count": report.track_count,
        "issues_found": report.issues_found,
        "summary": report.summary,
        "issues": [
            {
                "code": i.code,
                "severity": i.severity,
                "track_index": i.track_index,
                "track_name": i.track_name,
                "description": i.description,
                "suggested_action": i.suggested_action,
                "proposed_value": i.proposed_value,
            }
            for i in report.issues
        ],
        "remediation_batch": report.remediation_batch,
        "remediation_execution": remediated,
    }
