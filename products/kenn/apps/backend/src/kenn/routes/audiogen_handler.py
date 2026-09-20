"""AudioGen generation, phrase rendering, history, and MIDI proposal routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from kenn.core.audio_analysis import MAX_INPUT_BYTES, analyze_wav
from kenn.paths import RUNTIME_ROOT

PORTFOLIO_AUDIO_ROOTS = [
    RUNTIME_ROOT / "portfolio" / "audio",
]


def _portfolio_audio_bytes(reference: Any) -> tuple[bytes, str] | None:
    path_str = str(reference or "").strip()
    if not path_str.startswith("/portfolio/audio/"):
        return None
    parts = path_str.split("/")
    if len(parts) != 4 or parts[1] != "portfolio" or parts[2] != "audio":
        return None
    filename = parts[3]
    if not filename or filename != Path(filename).name or filename in {".", ".."} or not filename.lower().endswith(".wav"):
        return None
    import kenn.server as server_module
    roots = getattr(server_module, "PORTFOLIO_AUDIO_ROOTS", PORTFOLIO_AUDIO_ROOTS)
    for root in roots:
        root = root.resolve()
        target = (root / filename).resolve()
        if not str(target).startswith(str(root)) or not target.is_file() or target.suffix.lower() != ".wav":
            continue
        if target.stat().st_size > MAX_INPUT_BYTES:
            return None
        return target.read_bytes(), filename
    return None


def handle_audiogen_status(handler: Any, audiogen_bridge: Any) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    try:
        handler.send_json(200, public_audiogen_status(audiogen_bridge.status()))
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen status failed: {exc}"})


def handle_audiogen_history(handler: Any, audiogen_bridge: Any, parsed: Any) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    try:
        query = parse_qs(parsed.query)
        limit = int(query.get("limit", ["8"])[0])
        handler.send_json(200, {"ok": True, "items": public_audiogen_history(audiogen_bridge.list_render_history(limit=limit))})
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen history failed: {exc}"})


def handle_audiogen_job(handler: Any, audiogen_bridge: Any, parsed: Any) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    try:
        query = parse_qs(parsed.query)
        job_id = query.get("id", [""])[0]
        result = audiogen_bridge.render_job(job_id)
        if result.get("job"):
            result = {**result, "job": public_audiogen_job(result.get("job"))}
        handler.send_json(200, result)
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen job lookup failed: {exc}"})


def handle_audiogen_generate(handler: Any, audiogen_bridge: Any, payload: dict) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    try:
        result = audiogen_bridge.generate_for_kenn(
            str(payload.get("prompt", "")),
            emotion=str(payload.get("emotion", "")),
            bars=int(payload.get("bars", 8) or 8),
            publish=True,
        )
        handler.send_json(200 if result.get("ok") else 500, public_audiogen_result(result) or {"ok": False, "error": "AudioGen generation failed."})
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen generation failed: {exc}"})


def handle_audiogen_midi_proposal(handler: Any, audiogen_bridge: Any, payload: dict) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    session_id = str(payload.get("session_id", "")).strip()
    track_name = str(payload.get("track_name", "")).strip()
    if not session_id or not track_name:
        handler.send_json(400, {"ok": False, "error": "session_id and track_name are required."})
        return
    try:
        track_index = int(payload.get("track_index"))
        clip_slot_index = int(payload.get("clip_slot_index"))
        bars = max(1, min(24, int(payload.get("bars", 4) or 4)))
    except (TypeError, ValueError):
        handler.send_json(400, {"ok": False, "error": "track, clip-slot, and bars must be numeric."})
        return
    if min(track_index, clip_slot_index) < 0:
        handler.send_json(400, {"ok": False, "error": "track and clip-slot indices must be non-negative."})
        return
    raw_seed = payload.get("seed", "")
    seed = ""
    if raw_seed not in (None, ""):
        try:
            seed = str(int(raw_seed))
        except (TypeError, ValueError):
            handler.send_json(400, {"ok": False, "error": "AudioGen seed must be an integer when provided."})
            return
    revision_brief = None
    if payload.get("revision_brief") is not None:
        revision_brief, revision_errors = validate_revision_brief(
            payload.get("revision_brief"),
            session_id=session_id,
            track_index=track_index,
            track_name=track_name,
            clip_slot_index=clip_slot_index,
        )
        if revision_errors:
            handler.send_json(409, {
                "ok": False,
                "error": "Revision brief does not match the exact AudioGen target.",
                "limitations": revision_errors,
            })
            return
    try:
        live_context_snapshot = LiveActionService().snapshot(include_mixer=True)
        if live_context_snapshot.get("status") != "connected":
            handler.send_json(503, {"ok": False, "error": "Ableton Live context is unavailable; no AudioGen MIDI proposal was created."})
            return
        generated = audiogen_bridge.phrase_command(
            emotion=str(payload.get("emotion", "joy")).strip() or "joy",
            bars=bars,
            seed=seed,
            include_events=True,
        )
        event_payload = generated.get("result") if isinstance(generated, dict) else None
        source_bpm = event_payload.get("bpm") if isinstance(event_payload, dict) else None
        source_key = event_payload.get("key") if isinstance(event_payload, dict) else None
        generation_context, context_error = build_live_generation_context(
            live_context_snapshot,
            track_index=track_index,
            track_name=track_name,
            source_bpm=source_bpm,
            source_key=source_key,
        )
        if context_error or generation_context is None:
            handler.send_json(409, {"ok": False, "error": context_error or "Live context could not be bound to this AudioGen proposal."})
            return
        if revision_brief is not None:
            generation_context["revision"] = revision_brief
        artifact_result = artifact_from_event_payload(event_payload, generation_context=generation_context)
        if not artifact_result.get("ok"):
            handler.send_json(409, {
                "ok": False,
                "error": "AudioGen did not return an import-ready MIDI event artifact.",
                "limitations": artifact_result.get("errors", []),
                "validation": artifact_result.get("validation"),
            })
            return
        artifact = artifact_result["artifact"]
        if revision_brief is not None:
            from kenn.ableton_osc_bridge import live_client

            current_clip = live_client.get_midi_clip_state(track_index, clip_slot_index)
            if not current_clip.get("success") or not current_clip.get("has_clip") or not current_clip.get("is_midi_clip"):
                handler.send_json(409, {
                    "ok": False,
                    "error": "Cannot revise slot without an existing MIDI clip to replace.",
                    "limitations": ["The auditioned clip was deleted or changed before the revision could be proposed."],
                })
                return
            proposal_result = MidiClipActionService().propose_replacement(
                artifact,
                session_id=session_id,
                track_index=track_index,
                track_name=track_name,
                clip_slot_index=clip_slot_index,
                slot_action="replace_clip",
            )
        else:
            proposal_result = MidiClipActionService().propose(
                artifact,
                session_id=session_id,
                track_index=track_index,
                track_name=track_name,
                clip_slot_index=clip_slot_index,
                slot_action="create_clip",
            )
        status_code = 200 if proposal_result.get("ok") else 409
        handler.send_json(status_code, {
            **proposal_result,
            "artifact": artifact,
            "provenance": artifact.get("provenance"),
            "audio_reference": artifact.get("audio_reference"),
        })
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen MIDI proposal failed: {exc}"})


def handle_audiogen_audio_compare(handler: Any, payload: dict) -> None:
    first = _portfolio_audio_bytes(payload.get("source_a"))
    second = _portfolio_audio_bytes(payload.get("source_b"))
    if first is None or second is None:
        handler.send_json(400, {
            "ok": False,
            "error": "source_a and source_b must be existing KENN /portfolio/audio/*.wav references.",
            "advisory_only": True,
        })
        return
    first_bytes, first_filename = first
    second_bytes, second_filename = second
    try:
        analysis_a = analyze_wav(first_bytes, filename=first_filename)
        analysis_b = analyze_wav(second_bytes, filename=second_filename)
    except Exception as exc:
        handler.send_json(400, {"ok": False, "error": f"Audio comparison failed: {exc}", "advisory_only": True})
        return
    if not analysis_a.get("ok") or not analysis_b.get("ok"):
        handler.send_json(400, {
            "ok": False,
            "error": "Both local WAV candidates must analyze successfully.",
            "analysis_a": analysis_a,
            "analysis_b": analysis_b,
            "advisory_only": True,
        })
        return
    metrics_a = analysis_a.get("metrics", {})
    metrics_b = analysis_b.get("metrics", {})
    deltas = {}
    for key in sorted(set(metrics_a) & set(metrics_b)):
        if isinstance(metrics_a[key], (int, float)) and isinstance(metrics_b[key], (int, float)):
            deltas[key] = {
                "a": metrics_a[key],
                "b": metrics_b[key],
                "delta_b_minus_a": round(float(metrics_b[key]) - float(metrics_a[key]), 6),
            }
    handler.send_json(200, {
        "schema": "kenn.audiogen_audio_comparison.v1",
        "ok": True,
        "source_a": {"reference": f"/portfolio/audio/{first_filename}", "filename": first_filename, "input_hash": analysis_a.get("input_hash")},
        "source_b": {"reference": f"/portfolio/audio/{second_filename}", "filename": second_filename, "input_hash": analysis_b.get("input_hash")},
        "analysis_a": analysis_a,
        "analysis_b": analysis_b,
        "metric_deltas": deltas,
        "advisory_only": True,
        "limitations": [
            "Measured deltas describe technical features only; they do not establish that either candidate is musically better.",
            "Only KENN-served portfolio WAV references are accepted; both files are analyzed in memory and are not retained by this endpoint.",
        ],
    })


def handle_audiogen_render_song(handler: Any, audiogen_bridge: Any, payload: dict) -> None:
    if not audiogen_bridge:
        handler.send_json(503, {"ok": False, "error": "AudioGen bridge is unavailable."})
        return
    try:
        result = audiogen_bridge.enqueue_full_song_render(
            emotion=str(payload.get("emotion", "")),
            bars=int(payload.get("bars", 4) or 4),
            k=int(payload.get("k", 1) or 1),
            publish=True,
        )
        if result.get("job"):
            result = {**result, "job": public_audiogen_job(result.get("job"))}
        handler.send_json(200 if result.get("ok") else 500, result)
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"AudioGen render queue failed: {exc}"})
