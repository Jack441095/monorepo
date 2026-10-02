"""Session, plug-in, and Mix Review reads that build an advisory brief.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kenn.core.arrangement_analysis import analyze_arrangement_context
from kenn.core.mcp.errors import KennTransportError
from kenn.core.mcp.realtime import _realtime_context_is_current, _realtime_mix_recommendations
from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def live_snapshot(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    detail = str(args.get("detail", "topology"))
    if detail not in {"topology", "full", "understanding"}:
        raise ValueError("detail must be 'topology', 'full', or 'understanding'")
    return facade.client.get("/api/ableton/osc/session", {"detail": detail})


def live_plugin_review(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    result = facade.client.get("/api/plugin-live-review", {"session_id": session_id})
    if not isinstance(result, dict):
        raise ValueError("KENN returned an invalid plug-in review response")
    # Preserve the endpoint's explicit missing/expired distinction so
    # a reasoning client cannot mistake an unavailable frame for a
    # zero-valued measurement or stale session state.
    return result


def realtime_session_review(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
    focus = str(args.get("focus", "")).strip()[:512]
    query = {}
    if plugin_session_id:
        query["plugin_session_id"] = plugin_session_id
    if focus:
        query["focus"] = focus
    result = facade.client.get("/api/realtime-session-review", query)
    if not isinstance(result, dict):
        raise ValueError("KENN returned an invalid realtime session review response")
    return result


def live_arrangement_analysis(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    context = facade._dispatch(
        "kenn_context",
        {
            "session_id": session_id,
            "include_device_matrix": False,
            "include_device_parameters": False,
        },
    )
    return analyze_arrangement_context(context)


def realtime_mix_recommendations(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    result = facade.client.get("/api/plugin-live-review", {"session_id": session_id})
    if not isinstance(result, dict):
        raise ValueError("KENN returned an invalid plug-in review response")
    context = result.get("live_context")
    recommendations = _realtime_mix_recommendations(context) if isinstance(context, dict) else []
    limitations = [
        "Realtime findings are validated plug-in bus observations, not track-level diagnoses.",
        "No responsible Live track/device is inferred and no automatic master EQ or other mutation is authorized.",
    ]
    if isinstance(context, dict) and not _realtime_context_is_current(context):
        limitations.append("The retained plug-in context is stale_or_unknown for current diagnosis; recommendations are withheld.")
    if result.get("ok") is not True:
        return {
            "ok": False,
            "schema": "kenn.realtime_mix_recommendations.v1",
            "session_id": session_id,
            "recommendations": [],
            "recommendations_available": False,
            "advisory_only": True,
            "capture_requested": False,
            "error": result.get("error") or "No validated realtime plug-in review was available.",
            "limitations": limitations,
        }
    return {
        "ok": True,
        "schema": "kenn.realtime_mix_recommendations.v1",
        "session_id": session_id,
        "scope": "plugin_bus",
        "recommendations": [item.payload() for item in recommendations],
        "recommendations_available": bool(recommendations),
        "advisory_only": True,
        "capture_requested": False,
        "freshness": context.get("freshness") if isinstance(context, dict) else None,
        "live_context": context,
        "limitations": limitations,
    }


def compare_realtime_mix_review(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    review_id = str(args.get("review_id", "")).strip()[:128]
    plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
    if not review_id or not plugin_session_id:
        raise ValueError("review_id and plugin_session_id are required")
    review_result = facade.client.get("/api/mix-review-status", {"id": review_id})
    review = review_result.get("review") if isinstance(review_result, dict) else None
    plugin_result = facade.client.get("/api/plugin-live-review", {"session_id": plugin_session_id})
    live_context = plugin_result.get("live_context") if isinstance(plugin_result, dict) else None
    comparison = build_realtime_mix_comparison(
        review,
        live_context,
        review_id=review_id,
        plugin_session_id=plugin_session_id,
    )
    if not isinstance(review, dict):
        comparison.update({"ok": False, "error": review_result.get("error", "Mix Review was not found.")})
    elif not isinstance(live_context, dict):
        comparison.update({"ok": False, "error": plugin_result.get("error", "No realtime plug-in context was available.")})
    return comparison


def mix_review_recommendations(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    review_id = str(args.get("review_id", "")).strip()[:128]
    if not review_id:
        raise ValueError("review_id is required")
    result = facade.client.get("/api/mix-review-status", {"id": review_id})
    review = result.get("review") if isinstance(result, dict) else None
    if not isinstance(review, dict):
        return {
            "ok": False,
            "review_id": review_id,
            "recommendations": [],
            "error": "Mix Review did not return a review record.",
            "limitations": ["No measured review evidence was available; no Live target may be inferred."],
        }
    from kenn.project_analysis import (
        prioritize_recommendations,
        recommendations_from_mix_review,
        summarize_recommendations,
    )

    genre = str(args.get("genre", "")).strip() or None
    plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
    realtime_context = None
    realtime_error = ""
    realtime_recommendations: list[Any] = []
    if plugin_session_id:
        try:
            plugin_result = facade.client.get(
                "/api/plugin-live-review", {"session_id": plugin_session_id}
            )
        except KennTransportError as exc:
            plugin_result = None
            realtime_error = f"Realtime plug-in review was unavailable: {exc}"
        if isinstance(plugin_result, dict) and plugin_result.get("ok") is True:
            candidate_context = plugin_result.get("live_context")
            if isinstance(candidate_context, dict):
                realtime_context = candidate_context
                realtime_recommendations = _realtime_mix_recommendations(candidate_context)
            else:
                realtime_error = "No validated realtime plug-in bus context was available for this session."
        elif not realtime_error:
            realtime_error = "No fresh realtime plug-in review was available for this session."
    recommendation_inputs = recommendations_from_mix_review(review)
    recommendation_inputs.extend(realtime_recommendations)
    ranked = prioritize_recommendations(recommendation_inputs, genre=genre)
    from kenn.core.mixdown_coach import build_mixdown_coach
    mixdown_coach = build_mixdown_coach(review)
    realtime_mix_comparison = None
    if plugin_session_id and isinstance(realtime_context, dict):
        realtime_mix_comparison = build_realtime_mix_comparison(
            review,
            realtime_context,
            review_id=review_id,
            plugin_session_id=plugin_session_id,
        )
    recommendations = [item.payload() for item in ranked]
    for item in recommendations:
        if item.get("category") == "realtime_mix":
            item.update({
                "source_review_id": None,
                "source_scope": "plugin_bus_realtime",
                "plugin_session_id": plugin_session_id,
                "live_target_inference_allowed": False,
                "live_handoff": "Treat this as a bus-level listening check; KENN will not infer a responsible Live track/device or apply automatic master EQ.",
            })
        else:
            item.update({
                "source_review_id": review_id,
                "source_scope": "uploaded_or_rendered_audio",
                "live_target_inference_allowed": False,
                "live_handoff": "Supply an exact Live track/device/parameter separately; create a normal confirmation-only proposal and verify it by ear.",
            })
    response = {
        "ok": True,
        "schema": "kenn.mix_review_recommendations.v1",
        "review_id": review_id,
        "status": review.get("status", result.get("status", "unknown")),
        "recommendations": recommendations,
        "summary": summarize_recommendations(ranked),
        "mixdown_coach": mixdown_coach,
        "realtime_mix_comparison": realtime_mix_comparison,
        "limitations": [
            "Findings describe the uploaded/rendered audio review, not the current Live session.",
            "The review does not identify a responsible Live track or device; KENN will not infer one.",
            "Recommendations are advisory until an exact Live target, parameter, and user-confirmed proposal exist.",
        ],
    }
    if plugin_session_id:
        response["realtime_plugin_review"] = realtime_context
        response["realtime_recommendation_available"] = bool(realtime_recommendations)
        response["limitations"].append(
            "Realtime plug-in evidence is a validated bus observation; it does not identify a Live track/device or authorize a mutation."
        )
        if realtime_error:
            response["limitations"].append(realtime_error)
    return response
