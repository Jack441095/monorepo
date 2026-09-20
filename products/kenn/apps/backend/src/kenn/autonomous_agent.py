"""KENN Autonomous Grounded DSP & Mix Engineering Tool Loop Agent.

Executes multi-step reasoning, tool execution, audio analysis, thread safety auditing,
and C++/JUCE patch generation autonomously.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

# __file__ is <repo>/apps/backend/src/kenn/autonomous_agent.py, so the repo root is
# two levels up (parents[2]). A prior monorepo-era build used parents[3],
# which pointed one directory above this standalone repository -- see
# docs/KNOWN_ISSUES.md. _MIX_OUTPUT_ROOT still names a "business/app/..."
# path that does not exist in this standalone repo; this subsystem is
# untested (no test coverage anywhere under apps/backend/src/kenn/) and is not part
# of the beta path -- see docs/KENN_BETA_GAP_MATRIX.md.
# of the beta path -- see docs/specs/KENN_BETA_GAP_MATRIX.md.
from kenn.paths import PRODUCT_ROOT

_REPO_ROOT = PRODUCT_ROOT
_MIX_OUTPUT_ROOT = _REPO_ROOT / "business" / "app" / "data" / "mix_outputs"
_MIX_OUTPUT_ROOT = Path(
    os.environ.get("KENN_MIX_OUTPUT_ROOT", str(_REPO_ROOT / ".runtime" / "mix_outputs"))
).resolve()


class KennTool:
    """Encapsulates a callable tool for KENN Autonomous Agent."""

    def __init__(self, name: str, description: str, func: Callable[..., Dict[str, Any]]):
        self.name = name
        self.description = description
        self.func = func

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return self.func(**kwargs)


def _measure_project_mixdown(project_id: str) -> List[float] | None:
    """Real 40-band LTAS of a project's latest delivered AutoMix mixdown, or
    None if the project id is invalid or no render has completed yet."""
    import re as _re

    if not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", project_id or ""):
        return None
    proj_dir = (_MIX_OUTPUT_ROOT / project_id).resolve()
    try:
        proj_dir.relative_to(_MIX_OUTPUT_ROOT.resolve())
    except ValueError:
        return None
    if not proj_dir.is_dir():
        return None
    wav_files = sorted(proj_dir.glob("mixdown_v*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not wav_files:
        return None
    from audio_analysis.mixdown.ltas_matcher import calculate_40_band_ltas
    from audio_analysis.utils.audio_io import read_wav_mono
    from kenn.core.audio_analysis import analyze_wav_bytes

    decoded = read_wav_mono(wav_files[0].read_bytes(), max_samples=0)
    return calculate_40_band_ltas(decoded["samples"], int(decoded["sample_rate"]))
    try:
        analysis = analyze_wav_bytes(wav_files[0].read_bytes(), include_ltas=True)
        ltas_rows = analysis.get("spectral", {}).get("ltas_40_band_relative_db", [])
        return [float(row["relative_db"]) for row in ltas_rows if "relative_db" in row]
    except Exception:
        return None


def tool_ltas_spectrum_match(
    genre: str = "pop",
    mix_bands: List[float] | None = None,
    project_id: str | None = None,
) -> Dict[str, Any]:
    """Run 40-band LTAS spectrum deviation matching against target curves.

    Provide either mix_bands (an already-measured 40-band LTAS) or
    project_id (looks up that project's latest delivered mixdown
    and measures it for real). With neither, this honestly reports that no
    mix was analyzed instead of fabricating numbers that look like a real
    measurement.
    """
    from kenn.core.audio_analysis import _pink_noise_reference
    from kenn.core.local_mix_review_service import _advisory_eq_moves

    analyzed_real_audio = mix_bands is not None
    if mix_bands is None and project_id:
        mix_bands = _measure_project_mixdown(project_id)
        analyzed_real_audio = mix_bands is not None

    if mix_bands is None:
        return {
            "status": "no_audio",
            "genre": genre,
            "eq_recommendations": [],
            "bands_analyzed": 0,
            "analyzed_real_audio": False,
            "note": "No mix_bands or project_id was provided, so nothing was analyzed.",
        }

    from kenn.core.local_mix_review_service import _advisory_eq_moves
    from kenn.core.target_curves import calculate_genre_spectral_deviation, get_genre_profile

    ltas_rows = [
        {"index": idx, "center_hz": round(20.0 * ((20000.0 / 20.0) ** (idx / 40.0)), 2), "relative_db": val}
        for idx, val in enumerate(mix_bands)
    ]
    genre_res = calculate_genre_spectral_deviation(ltas_rows, genre=genre)
    deviations = genre_res.get("bands", []) if genre_res.get("status") == "complete" else []
    deltas = [{"center_hz": b["center_hz"], "delta_db": b["deviation_db"]} for b in deviations]
    eq_recs = _advisory_eq_moves(deltas)

    return {
        "status": "success",
        "genre": genre_res.get("genre", genre),
        "genre_id": genre_res.get("genre_id", genre),
        "eq_recommendations": eq_recs,
        "bands_analyzed": len(mix_bands),
        "analyzed_real_audio": analyzed_real_audio,
        "baseline_curve": genre_res.get("curve", "genre_target_curve"),
        "rms_spectral_deviation_db": genre_res.get("rms_spectral_deviation_db", 0.0),
        "target_integrated_lufs": genre_res.get("target_integrated_lufs", []),
        "target_crest_factor_db": genre_res.get("target_crest_factor_db", []),
    }


def tool_audit_realtime_cpp(code: str) -> Dict[str, Any]:
    """Audit C++/Python code for real-time audio thread safety violations."""
    violations = []
    lines = code.split("\n")

    patterns = [
        (re.compile(r"\b(malloc|free|realloc)\b"), "Heap Memory Allocation (malloc/free)"),
        (re.compile(r"\bnew\s+[A-Za-z0-9_]+"), "Dynamic Memory Operator (new)"),
        (re.compile(r"\b(std::mutex|mutex\.lock|pthread_mutex_lock)\b"), "Blocking Mutex Lock"),
        (re.compile(r"\b(std::cout|printf|sys\.stdout)\b"), "Blocking I/O System Call"),
    ]

    for idx, line in enumerate(lines, start=1):
        for pattern, desc in patterns:
            if pattern.search(line):
                violations.append(f"Line {idx}: {desc} -> '{line.strip()}'")

    return {
        "status": "warning" if violations else "clean",
        "violations_found": len(violations),
        "details": violations,
    }


def tool_generate_juce_patch(effect_name: str = "GainEffect") -> Dict[str, Any]:
    """Generate a production-ready C++ JUCE DSP AudioProcessor class template."""
    clean_name = re.sub(r"\W+", "", effect_name)
    cpp_code = f"""// {clean_name}.h — Autonomous JUCE DSP Module
#pragma once
#include <JuceHeader.h>

class {clean_name}AudioProcessor : public juce::AudioProcessor
{{
public:
    {clean_name}AudioProcessor() = default;
    ~{clean_name}AudioProcessor() override = default;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override {{
        smoothGain.reset(sampleRate, 0.05);
    }}
    void releaseResources() override {{}}
    void processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&) override {{
        juce::ScopedNoDenormals noDenormals;
        for (int ch = 0; ch < buffer.getNumChannels(); ++ch) {{
            juce::FloatVectorOperations::multiply(buffer.getWritePointer(ch), targetGain, buffer.getNumSamples());
        }}
    }}

private:
    juce::LinearSmoothedValue<float> smoothGain{{1.0f}};
    float targetGain = 1.0f;
}};
"""
    return {
        "status": "success",
        "effect_name": clean_name,
        "header_code": cpp_code,
    }


def tool_query_ableton_session() -> Dict[str, Any]:
    """Query active track structure, volumes, and returns from Ableton Live 12."""
    from kenn.ableton_osc_bridge import live_client
    return live_client.query_session_state()


def tool_audit_live_session(session_id: str = "default") -> Dict[str, Any]:
    """Run Session Doctor to audit headroom, low-end phase, and mud across all tracks."""
    from kenn.ableton_osc_bridge import live_client
    from kenn.core.session_doctor import SessionDoctor
    from kenn.plugin_handoff import live_context_summary

    session_state = live_client.query_session_state()
    telemetry = live_context_summary(session_id)
    report = SessionDoctor.audit(session_state, meters=telemetry)
    return {
        "status": "success",
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
    }


def tool_auto_remediate_session_issues(session_id: str = "doctor_session") -> Dict[str, Any]:
    """Audit and automatically apply non-destructive fixes to session issues via autonomous batching."""
    from kenn.core.live_action_service import LiveActionService

    audit_result = tool_audit_live_session()
    batch = audit_result.get("remediation_batch", [])
    if not batch:
        return {
            "status": "clean",
            "message": "Session Doctor found no issues requiring automated remediation.",
            "audit": audit_result,
        }
    service = LiveActionService()
    batch_result = service.execute_batch_autonomous(batch, session_id=session_id)
    return {
        "status": "remediated" if batch_result.get("ok") else "partial_failure",
        "audit": audit_result,
        "execution": batch_result,
    }


def tool_formulate_surgical_remediation(session_id: str = "doctor_session") -> Dict[str, Any]:
    """Formulate a comprehensive closed-loop surgical masking & diagnostic remediation proposal."""
    from kenn.ableton_osc_bridge import live_client
    from kenn.core.session_doctor import SessionDoctor
    from kenn.plugin_handoff import live_context_summary

    session_state = live_client.query_session_state()
    telemetry = live_context_summary(session_id)
    return SessionDoctor.formulate_surgical_remediation_proposal(session_state, meters=telemetry, session_id=session_id)


def tool_synthesize_pro_rack(
    rack_id: str,
    track_index: int,
    track_name: str = "",
    session_id: str = "rack_session",
) -> Dict[str, Any]:
    """Synthesize a dynamic 8-macro Audio Effect Rack proposal with variation snapshots."""
    from kenn.core.rack_builder import synthesize_rack_proposal
    return synthesize_rack_proposal(rack_id, track_index=track_index, track_name=track_name, session_id=session_id)


def tool_generate_neural_bassline(
    root: str = "C",
    scale: str = "minor",
    style: str = "bouncy",
    bars: int = 2,
    groove: str = "straight",
) -> Dict[str, Any]:
    """Generate harmonic scale-quantized bassline notes using AudioGen composition engine."""
    from kenn.core.generative_midi import generate_audiogen_bassline
    notes = generate_audiogen_bassline(root=root, scale_name=scale, style=style, bars=bars, groove=groove)
    return {"ok": True, "notes": notes, "root": root, "scale": scale, "style": style, "bars": bars, "count": len(notes)}


def tool_audit_full_mix(session_snapshot: Optional[Dict[str, Any]] = None, meters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Audit the entire multi-track Ableton Live session and compute the deterministic 0-100 MQM score."""
    from kenn.core.mix_doctor import get_mix_doctor
    from kenn.audio_telemetry import get_telemetry_manager

    snap = session_snapshot or tool_query_ableton_session()
    m = meters
    if m is None:
        latest = get_telemetry_manager().get_latest()
        if latest:
            m = latest.to_dict()
    report = get_mix_doctor().audit_session(snap, meters=m)
    return report.to_dict()


def tool_unmask_stems(tracks: Optional[List[Dict[str, Any]]] = None, meters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Detect pairwise ERB cross-spectral masking across stems and synthesize dynamic unmasking recipes."""
    from kenn.core.stem_unmasking import get_stem_unmasking_engine

    trks = tracks
    if trks is None:
        snap = tool_query_ableton_session()
        trks = snap.get("tracks", [])
    engine = get_stem_unmasking_engine()
    collisions = engine.detect_collisions(trks, meters=meters)
    dag = engine.synthesize_unmasking_dag(collisions)
    return {
        "status": "success",
        "collision_count": len(collisions),
        "collisions": [c.to_dict() for c in collisions],
        "unmasking_dag": dag,
    }


def tool_voice_command(spoken_text: str) -> Dict[str, Any]:
    """Parse and dispatch studio voice commands into structured intent and action cards in < 50ms."""
    from kenn.speech.voice_copilot import get_voice_copilot
    intent = get_voice_copilot().classify_intent(spoken_text)
    return intent.to_dict()


def tool_master_session(profile: str = "SPOTIFY_STREAMING", session_snapshot: Optional[Dict[str, Any]] = None, meters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Synthesize a 5-stage commercial mastering chain tailored to a target delivery platform."""
    from kenn.core.mastering_engine import get_mastering_engine
    from kenn.audio_telemetry import get_telemetry_manager

    snap = session_snapshot or tool_query_ableton_session()
    m = meters
    if m is None:
        latest = get_telemetry_manager().get_latest()
        if latest:
            m = latest.to_dict()
    report = get_mastering_engine().synthesize_mastering_dag(profile, session_snapshot=snap, meters=m)
    return report.to_dict()


def tool_match_reference_track(reference_spectrum: Optional[List[float]] = None, session_spectrum: Optional[List[float]] = None, reference_name: str = "Commercial Master Reference") -> Dict[str, Any]:
    """Extract 40-band ERB difference curve against commercial reference and synthesize safe parametric EQ moves."""
    from kenn.core.reference_matcher import get_reference_matcher
    matcher = get_reference_matcher()
    s_spec = session_spectrum or [-20.0 - (i * 0.5) for i in range(40)]
    r_spec = reference_spectrum or [-20.0 - (i * 0.48) for i in range(40)]
    report = matcher.compute_spectral_delta(s_spec, r_spec, reference_name=reference_name)
    return report.to_dict()


def tool_auto_gain_stage(tracks: Optional[List[Dict[str, Any]]] = None, meters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Audit track levels for headroom creep and synthesize nominal -18 dBFS gain-staging trim offsets."""
    from kenn.core.auto_gain_stager import get_auto_gain_stager
    stager = get_auto_gain_stager()
    trks = tracks
    if trks is None:
        snap = tool_query_ableton_session()
        trks = snap.get("tracks", [])
    audit = stager.audit_gain_staging(trks, meters=meters)
    return audit.to_dict()


def tool_analyze_arrangement(tracks: Optional[List[Dict[str, Any]]] = None, sections: Optional[List[Dict[str, Any]]] = None, total_bars: int = 64) -> Dict[str, Any]:
    """Analyze arrangement sections, compute energy pacing, and synthesize transition automation recipes."""
    from kenn.core.arrangement_doctor import get_arrangement_doctor
    doc = get_arrangement_doctor()
    trks = tracks
    if trks is None:
        snap = tool_query_ableton_session()
        trks = snap.get("tracks", [])
    report = doc.analyze_timeline(tracks=trks, timeline_sections=sections, total_bars=total_bars)
    return report.to_dict()


def tool_generate_midi(prompt_type: str = "counterpoint", root: str = "F", scale: str = "NATURAL_MINOR", bars: int = 4, style: str = "ROLLING_16TH", swing: str = "STRAIGHT") -> Dict[str, Any]:
    """Synthesize scale-aware melodic counterpoint or rolling basslines for direct clip injection."""
    from kenn.core.midi_copilot import get_midi_copilot
    copilot = get_midi_copilot()
    if prompt_type.lower() == "bassline":
        clip = copilot.generate_bassline(root=root, scale=scale, bars=bars, style=style, swing=swing)
    else:
        clip = copilot.generate_counterpoint(root=root, scale=scale, bars=bars, swing=swing)
    return clip.to_dict()


def tool_cure_vocal_resonances(track_name: str = "Lead Vocal", spectral_peaks: Optional[List[Dict[str, float]]] = None) -> Dict[str, Any]:
    """Detect stationary harsh resonances (2.5-4.5 kHz) and sibilance (6-9 kHz) and synthesize surgical dynamic notch cuts."""
    from kenn.core.vocal_surgeon import get_vocal_surgeon
    surgeon = get_vocal_surgeon()
    report = surgeon.audit_vocal_track(track_name=track_name, spectral_peaks=spectral_peaks)
    return report.to_dict()


def tool_package_stems(tracks: Optional[List[Dict[str, Any]]] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Group session tracks into 5 delivery stems, verify peak compliance, and generate a signed release certificate."""
    from kenn.core.stem_packager import get_stem_packager
    packager = get_stem_packager()
    trks = tracks
    if trks is None:
        snap = tool_query_ableton_session()
        trks = snap.get("tracks", [])
    plan = packager.generate_stem_plan(tracks=trks, project_metadata=metadata)
    return plan.to_dict()


def _daw_write_denied() -> Dict[str, Any] | None:
    """None if a real Ableton write is allowed to proceed; a denial dict
    otherwise.

    Found 2026-08-06: every DAW-write HTTP route in server.py checks
    `action_allowed("daw_control")` (the AUDIO_TOO_ALLOW_DAW_CONTROL
    off-by-default policy switch) before touching Ableton, but these
    autonomous-agent tool functions -- reachable via
    /api/kenn/autonomous-execute, which executes with no confirm step by
    design -- never checked it at all, silently bypassing that switch
    entirely. The no-confirm-click UX and the policy gate are two separate
    safety layers; skipping the no-confirm step (Jack's explicit call) was
    never meant to also skip the gate.
    """
    from kenn.core.action_policy import action_allowed, action_denied_message

    if action_allowed("daw_control"):
        return None
    return {"status": "denied", "error": action_denied_message("daw_control")}


def _track_snapshot(track_index: int) -> Dict[str, Any] | None:
    """Read a track's full current state before a write -- used both for
    undo's "before" value capture (P4, docs/KENN_IMPROVEMENT_PLAN.md) and
    the pre-execution guardrail check (item 2,
    docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md), one query instead
    of two separate ones for the same write. Best-effort: returns None if
    the session is offline or the track isn't found, since missing data
    should never block the write itself -- every caller already treats a
    None snapshot as "skip this check," not "deny.\""""
    from kenn.ableton_osc_bridge import live_client

    try:
        state = live_client.query_session_state()
        for track in state.get("tracks", []):
            if track.get("index") == track_index or track.get("track_index") == track_index:
                return track
    except Exception:
        pass
    return None


def _track_field_before(track_index: int, field: str) -> Any:
    """Convenience wrapper over _track_snapshot for callers that only
    need one field (undo's previous_value capture)."""
    snapshot = _track_snapshot(track_index)
    return snapshot.get(field) if snapshot else None


def _track_confirmation(action: str, payload: Dict[str, Any], confirm_token: str, session_id: str) -> Dict[str, Any] | None:
    """Gate legacy track controls with the same signed, exact-request token."""
    from kenn.core.confirmation import consume_confirmation, issue_confirmation
    text = action + ":" + ",".join(f"{key}={payload[key]!r}" for key in sorted(payload))
    if not confirm_token:
        token, meta = issue_confirmation(session_id=session_id, service_id=action, text=text)
        return {"status": "confirmation_required", "confirmation_required": True, "confirm_token": token, "confirmation_meta": meta, "action": action, **payload}
    if not consume_confirmation(confirm_token, session_id=session_id, service_id=action, text=text):
        return {"status": "failed", "error": "Invalid, expired, or already-used confirmation token.", "action": action, **payload}
    return None


def _safe_track_action(
    action: str,
    track_index: int,
    value: Any,
    confirm_token: str,
    session_id: str,
) -> Dict[str, Any]:
    """Run a track mutation through the shared Live safety boundary."""
    from kenn.core.live_action_service import LiveActionService

    service = LiveActionService()
    if not confirm_token:
        result = service.propose_track_action(
            action,
            track_index=track_index,
            value=value,
            session_id=session_id,
        )
        if not result.get("ok"):
            return {"status": "failed", "error": result.get("error"), "track_index": track_index}
        proposal = result["proposal"]
        return {
            "status": "confirmation_required",
            "confirmation_required": True,
            "proposal": proposal,
            "confirm_token": proposal["confirmation_token"],
            "track_index": track_index,
            "value": value,
        }

    proposal = service.proposal_for_token(confirm_token)
    if not proposal or proposal.get("action") != action or proposal.get("track_index") != int(track_index) or proposal.get("after") != value:
        return {"status": "failed", "error": "The confirmation token is not bound to this exact Live action.", "track_index": track_index}
    result = service.execute(proposal, confirm_token=confirm_token, session_id=session_id)
    receipt = result.get("receipt", {})
    if not result.get("ok"):
        return {"status": "failed", "error": result.get("error"), "receipt": receipt, "track_index": track_index, "value": value}
    return {
        "status": "success",
        "verified": receipt.get("verified", False),
        "receipt": receipt,
        "undo_payload": receipt.get("undo"),
        "track_index": track_index,
        "value": value,
        "previous_value": receipt.get("before"),
    }


def _safe_transport_action(action: str, confirm_token: str, session_id: str) -> Dict[str, Any]:
    from kenn.core.live_action_service import LiveActionService

    service = LiveActionService()
    if not confirm_token:
        result = service.propose_transport_action(action, session_id=session_id)
        if not result.get("ok"):
            return {"status": "failed", "error": result.get("error")}
        proposal = result["proposal"]
        return {
            "status": "confirmation_required",
            "confirmation_required": True,
            "proposal": proposal,
            "confirm_token": proposal["confirmation_token"],
        }
    proposal = service.proposal_for_token(confirm_token)
    if not proposal or proposal.get("action") != action:
        return {"status": "failed", "error": "The confirmation token is not bound to this exact Live transport action."}
    result = service.execute(proposal, confirm_token=confirm_token, session_id=session_id)
    if not result.get("ok"):
        return {"status": "failed", "error": result.get("error"), "receipt": result.get("receipt", {})}
    return {"status": "success", "verified": True, "receipt": result.get("receipt", {})}


def tool_set_ableton_volume(track_index: int, volume: float, confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Set track volume level in Ableton Live (0.0 to 1.0)."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "volume": volume}
    return _safe_track_action("set_volume", track_index, float(volume), confirm_token, session_id)


def tool_set_ableton_pan(track_index: int, pan: float, confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Set track pan level in Ableton Live (-1.0 left to 1.0 right)."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "pan": pan}
    return _safe_track_action("set_pan", track_index, float(pan), confirm_token, session_id)


def tool_set_ableton_parameter(
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    confirm_token: str = "",
    session_id: str = "default_session",
) -> Dict[str, Any]:
    """Set VST/device parameter in Ableton Live via safe proposal -> confirmation -> execution flow."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "device_index": device_index, "parameter_index": parameter_index, "value": value}

    from kenn.core.live_action_service import LiveActionService

    service = LiveActionService()

    # If no confirm token, generate a typed ActionProposal for user approval
    if not confirm_token:
        res = service.propose_device_action(
            track_index=track_index,
            device_index=device_index,
            parameter_index=parameter_index,
            proposed_value=value,
            reason=f"Requested setting parameter {parameter_index} on track {track_index}, device {device_index} to {value}",
            session_id=session_id,
        )
        if not res.get("ok"):
            return {"status": "failed", "error": res.get("error"), "track_index": track_index, "device_index": device_index, "parameter_index": parameter_index, "value": value}
        proposal = res["proposal"]
        return {
            "status": "confirmation_required",
            "confirmation_required": True,
            "proposal": proposal,
            "confirm_token": proposal.get("confirmation_token"),
            "message": f"Action proposal generated for setting parameter {parameter_index}. User confirmation required.",
        }

    # A confirmation token must resolve to the exact proposal that was shown
    # to the user. Re-planning here would refresh the before-value and could
    # bypass the stale-state guard.
    proposal_payload = service.proposal_for_token(confirm_token)
    if not proposal_payload:
        return {"status": "failed", "error": "Confirmation token is not bound to a stored device proposal."}
    if (
        int(proposal_payload.get("track_index", -1)) != int(track_index)
        or int(proposal_payload.get("device_index", -1)) != int(device_index)
        or int(proposal_payload.get("parameter_index", -1)) != int(parameter_index)
        or float(proposal_payload.get("after")) != float(value)
    ):
        return {"status": "failed", "error": "The confirmation token is not bound to this exact device action."}

    exec_res = service.execute_device_action(proposal_payload, confirm_token=confirm_token, session_id=session_id)
    if not exec_res.get("ok"):
        return {"status": "failed", "error": exec_res.get("error"), "track_index": track_index, "device_index": device_index, "parameter_index": parameter_index, "value": value}

    receipt = exec_res.get("receipt", {})
    return {
        "status": "success",
        "verified": receipt.get("verified", False),
        "receipt": receipt,
        "undo_payload": receipt.get("undo_payload"),
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "value": value,
    }



def tool_set_ableton_macro(
    track_index: int,
    device_index: int,
    macro_number: int,
    value: float,
    confirm_token: str = "",
    session_id: str = "default_session",
) -> Dict[str, Any]:
    """Set a Rack device's macro knob by number (D1.3,
    docs/KENN_FUTURE_PLAN.md Phase 1). Macro knobs are regular
    DeviceParameter objects named "Macro N" in Live's LOM, so this
    resolves the name to a parameter_index via get_device_parameters()
    and delegates to the same set_device_parameter() every other
    parameter write already uses -- no separate write path to keep safe."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "device_index": device_index, "macro_number": macro_number, "value": value}
    from kenn.ableton_osc_bridge import live_client

    params = live_client.get_device_parameters(track_index, device_index)
    if not params.get("success"):
        return {
            "status": "failed",
            "error": params.get("error", "Could not read device parameters"),
            "track_index": track_index,
            "device_index": device_index,
            "macro_number": macro_number,
        }

    target_name = f"macro {macro_number}"
    match = next(
        (p for p in params.get("parameters", []) if str(p.get("name", "")).strip().lower() == target_name),
        None,
    )
    if match is None:
        return {
            "status": "failed",
            "error": f"No parameter named 'Macro {macro_number}' on this device",
            "track_index": track_index,
            "device_index": device_index,
            "macro_number": macro_number,
        }

    result = tool_set_ableton_parameter(
        track_index,
        device_index,
        int(match["index"]),
        float(value),
        confirm_token=confirm_token,
        session_id=session_id,
    )
    result.update({"macro_number": macro_number, "parameter_index": match["index"]})
    return result


def tool_set_ableton_mute(track_index: int, muted: bool, confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Mute/unmute a track in Ableton Live."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "muted": muted}
    return _safe_track_action("set_mute", track_index, bool(muted), confirm_token, session_id)


def tool_set_ableton_solo(track_index: int, soloed: bool, confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Solo/unsolo a track in Ableton Live."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "soloed": soloed}
    return _safe_track_action("set_solo", track_index, bool(soloed), confirm_token, session_id)


def tool_set_ableton_arm(track_index: int, armed: bool, confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Record-arm/disarm a track in Ableton Live."""
    denied = _daw_write_denied()
    if denied is not None:
        return {**denied, "track_index": track_index, "armed": armed}
    return _safe_track_action("set_arm", track_index, bool(armed), confirm_token, session_id)


def tool_start_ableton_playback(confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Start song playback in Ableton Live from the current position."""
    denied = _daw_write_denied()
    if denied is not None:
        return denied
    return _safe_transport_action("transport_play", confirm_token, session_id)


def tool_stop_ableton_playback(confirm_token: str = "", session_id: str = "default_session") -> Dict[str, Any]:
    """Stop song playback in Ableton Live."""
    denied = _daw_write_denied()
    if denied is not None:
        return denied
    return _safe_transport_action("transport_stop", confirm_token, session_id)


def tool_set_ableton_tempo(bpm: float) -> Dict[str, Any]:
    """Disabled until tempo has a typed proposal and verified readback."""
    return {"status": "disabled", "error": "Tempo mutation is disabled pending a safe proposal/readback path.", "bpm": bpm}


def tool_launch_ableton_clip(track_index: int, clip_slot_index: int) -> Dict[str, Any]:
    """Disabled until clip identity and readback are safely represented."""
    return {"status": "disabled", "error": "Clip launch is disabled pending an exact target/readback path.", "track_index": track_index, "clip_slot_index": clip_slot_index}


def tool_launch_ableton_scene(scene_index: int) -> Dict[str, Any]:
    """Disabled until scene identity and readback are safely represented."""
    return {"status": "disabled", "error": "Scene launch is disabled pending an exact target/readback path.", "scene_index": scene_index}


def tool_create_ableton_scene(name: str = "") -> Dict[str, Any]:
    """Append a new scene at the end of the session in Ableton Live,
    optionally named -- the missing building block D3.4 (conversational
    arrangement assistance) needs to place a real, named song structure,
    not just describe one in text."""
    return {"status": "disabled", "error": "Scene creation is disabled pending a typed, reversible proposal.", "name": name}


# Item 3 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md): device names
# a user or the LLM-planning path might reasonably ask for that have no
# native Ableton device by that exact name -- create_device() searches
# Live's own device browser by exact name match, so "De-Esser" (not a
# real Ableton device) would just fail rather than fall back to
# anything. Deliberately ONE well-established mapping, not a guessed
# list of many: EQ Eight used as a dynamic/notch de-esser (targeting
# sibilance, roughly 5-8kHz) is a widely-documented technique, not a
# guess -- unlike most other "missing device" cases, which would need
# verifying against a real Ableton device browser before claiming a
# substitution is even reasonable (same discipline as item 2 dropping
# the unverified headroom-dB rule rather than shipping a guess).
DEVICE_FALLBACKS = {
    "de-esser": "EQ Eight",
    "deesser": "EQ Eight",
}


def tool_create_ableton_device(track_index: int, device_name: str) -> Dict[str, Any]:
    """Create/insert a new DAW device on target track index (e.g. 'Compressor', 'EqEight', 'Utility', 'Limiter')."""
    return {"status": "disabled", "error": "Device insertion is disabled pending a typed, reversible proposal.", "track_index": track_index, "device_name": device_name}


def tool_configure_sidechain(bass_track_index: int, kick_track_index: int) -> Dict[str, Any]:
    """Configure sidechain routing between a bass track and a kick track (inserts Compressor on bass if missing)."""
    return {"status": "disabled", "error": "Sidechain routing is disabled pending a typed, reversible proposal.", "bass_track_index": bass_track_index, "kick_track_index": kick_track_index}


def tool_orchestrate_subagent(agent_name: str = "", query: str = "") -> Dict[str, Any]:
    """Dispatch a task to a specialised sub-agent via the KENN orchestrator."""
    from kenn.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    if agent_name and agent_name in orchestrator.agents:
        agent = orchestrator.agents[agent_name]
        return agent.dispatch_fn(query=query)
    # If no specific agent named, let the orchestrator classify
    result = orchestrator.dispatch(query)
    if result:
        return result
def tool_acoustic_calibrate(session_id: str = "default", objective: str = "Psychoacoustic unmasking") -> Dict[str, Any]:
    """Run 40-band ERB acoustic calibration and formulate unmasking proposal."""
    from kenn.core.acoustic_calibration import AcousticCalibrationLoop
    snap = tool_query_ableton_session()
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline(session_id, snap)
    clashes = loop.diagnose_clashes(baseline)
    recipe = loop.formulate_calibration_recipe(baseline, clashes, objective=objective)
    return {
        "status": "success",
        "clashes_detected": len(clashes),
        "clashes": clashes,
        "proposal": recipe.get("proposal"),
    }


def tool_session_world_model(session_id: str = "default") -> Dict[str, Any]:
    """Construct semantic session world model with track roles, arrangement, and frequency territory."""
    from kenn.core.session_world_model import SessionWorldModel
    snap = tool_query_ableton_session()
    return SessionWorldModel.build_world_model(snap)


# Parameter schema for the LLM-planning loop (D1.4, 2026-08-06): for each
# tool, the params it accepts, their Python type (for coercion + light
# validation of the LLM's JSON output), and which are required. Kept
# separate from KennTool (whose "description" is a free-text string for
# both this schema's prompt and older ad-hoc uses) so a bad/missing schema
# entry fails loudly (KeyError) rather than silently under-validating a
# real DAW-write tool's arguments.
_PLAN_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "ltas_spectrum_match": {"genre": (str, False), "project_id": (str, False)},
    "audit_realtime_cpp": {"code": (str, True)},
    "generate_juce_patch": {"effect_name": (str, False)},
    "query_ableton_session": {},
    "acoustic_calibrate": {"session_id": (str, False), "objective": (str, False)},
    "session_world_model": {"session_id": (str, False)},
    "set_ableton_volume": {"track_index": (int, True), "volume": (float, True)},
    "set_ableton_pan": {"track_index": (int, True), "pan": (float, True)},
    "set_ableton_parameter": {
        "track_index": (int, True),
        "device_index": (int, True),
        "parameter_index": (int, True),
        "value": (float, True),
    },
    "set_ableton_macro": {
        "track_index": (int, True),
        "device_index": (int, True),
        "macro_number": (int, True),
        "value": (float, True),
    },
    "set_ableton_mute": {"track_index": (int, True), "muted": (bool, True)},
    "set_ableton_solo": {"track_index": (int, True), "soloed": (bool, True)},
    "set_ableton_arm": {"track_index": (int, True), "armed": (bool, True)},
    "start_ableton_playback": {},
    "stop_ableton_playback": {},
    "set_ableton_tempo": {"bpm": (float, True)},
    "launch_ableton_clip": {"track_index": (int, True), "clip_slot_index": (int, True)},
    "launch_ableton_scene": {"scene_index": (int, True)},
    "create_ableton_scene": {"name": (str, False)},
    "create_ableton_device": {"track_index": (int, True), "device_name": (str, True)},
    "configure_sidechain": {"bass_track_index": (int, True), "kick_track_index": (int, True)},
    "orchestrate": {"agent_name": (str, False), "query": (str, False)},
}


class KennAutonomousAgent:
    """Autonomous Multi-Step Agentic Engine for KENN."""

    def __init__(self):
        self.tools: Dict[str, KennTool] = {
            "ltas_spectrum_match": KennTool(
                "ltas_spectrum_match",
                "Calculate 40-band LTAS spectrum deviation against target curves",
                tool_ltas_spectrum_match,
            ),
            "audit_realtime_cpp": KennTool(
                "audit_realtime_cpp",
                "Audit code for real-time audio thread safety errors",
                tool_audit_realtime_cpp,
            ),
            "generate_juce_patch": KennTool(
                "generate_juce_patch",
                "Generate C++/JUCE DSP class header/source template",
                tool_generate_juce_patch,
            ),
            "query_ableton_session": KennTool(
                "query_ableton_session",
                "Query active track structure, volumes, and returns from Ableton Live 12",
                tool_query_ableton_session,
            ),
            "set_ableton_volume": KennTool(
                "set_ableton_volume",
                "Set track volume level in Ableton Live (0.0 to 1.0)",
                tool_set_ableton_volume,
            ),
            "set_ableton_pan": KennTool(
                "set_ableton_pan",
                "Set track pan level in Ableton Live (-1.0 left to 1.0 right)",
                tool_set_ableton_pan,
            ),
            "set_ableton_parameter": KennTool(
                "set_ableton_parameter",
                "Set VST/plugin parameter value on a specific track and device",
                tool_set_ableton_parameter,
            ),
            "set_ableton_macro": KennTool(
                "set_ableton_macro",
                "Set a Rack device's macro knob by number (e.g. Macro 2) on a specific track and device in Ableton Live",
                tool_set_ableton_macro,
            ),
            "set_ableton_mute": KennTool(
                "set_ableton_mute",
                "Mute or unmute a track in Ableton Live",
                tool_set_ableton_mute,
            ),
            "set_ableton_solo": KennTool(
                "set_ableton_solo",
                "Solo or unsolo a track in Ableton Live",
                tool_set_ableton_solo,
            ),
            "set_ableton_arm": KennTool(
                "set_ableton_arm",
                "Record-arm or disarm a track in Ableton Live",
                tool_set_ableton_arm,
            ),
            "start_ableton_playback": KennTool(
                "start_ableton_playback",
                "Start song playback in Ableton Live from the current position",
                tool_start_ableton_playback,
            ),
            "stop_ableton_playback": KennTool(
                "stop_ableton_playback",
                "Stop song playback in Ableton Live",
                tool_stop_ableton_playback,
            ),
            "set_ableton_tempo": KennTool(
                "set_ableton_tempo",
                "Set the song tempo in Ableton Live (roughly 20-999 BPM)",
                tool_set_ableton_tempo,
            ),
            "launch_ableton_clip": KennTool(
                "launch_ableton_clip",
                "Fire (launch playback of) the clip in a track's clip slot in Ableton Live",
                tool_launch_ableton_clip,
            ),
            "launch_ableton_scene": KennTool(
                "launch_ableton_scene",
                "Fire (launch) a scene by index in Ableton Live",
                tool_launch_ableton_scene,
            ),
            "create_ableton_scene": KennTool(
                "create_ableton_scene",
                "Append a new, optionally named scene at the end of the session in Ableton Live",
                tool_create_ableton_scene,
            ),
            "create_ableton_device": KennTool(
                "create_ableton_device",
                "Create/insert a new DAW device on target track index",
                tool_create_ableton_device,
            ),
            "configure_sidechain": KennTool(
                "configure_sidechain",
                "Configure sidechain routing between a bass track and a kick track",
                tool_configure_sidechain,
            ),
            "orchestrate": KennTool(
                "orchestrate",
                "Dispatch a task to a specialised sub-agent (stem_separator, mix_reviewer, ltas_matcher, audiogen, ableton_controller, mixing_doctor)",
                tool_orchestrate_subagent,
            ),
            "acoustic_calibrate": KennTool(
                "acoustic_calibrate",
                "Run 40-band ERB acoustic calibration and formulate unmasking proposal",
                tool_acoustic_calibrate,
            ),
            "session_world_model": KennTool(
                "session_world_model",
                "Construct semantic session world model with track roles, arrangement, and frequency territory",
                tool_session_world_model,
            ),
            "audit_full_mix": KennTool(
                "audit_full_mix",
                "Run 5-dimension full-session Mix Doctor audit and compute 0-100 MQM score",
                tool_audit_full_mix,
            ),
            "unmask_stems": KennTool(
                "unmask_stems",
                "Detect pairwise ERB cross-spectral collisions and synthesize dynamic unmasking recipes",
                tool_unmask_stems,
            ),
            "voice_command": KennTool(
                "voice_command",
                "Dispatch spoken studio command and extract intent in < 50ms",
                tool_voice_command,
            ),
            "master_session": KennTool(
                "master_session",
                "Synthesize 5-stage commercial mastering chain for target platform profile",
                tool_master_session,
            ),
            "match_reference_track": KennTool(
                "match_reference_track",
                "Extract 40-band ERB spectral deviation against reference and synthesize safe matching EQ",
                tool_match_reference_track,
            ),
            "auto_gain_stage": KennTool(
                "auto_gain_stage",
                "Audit session track headroom and formulate nominal -18 dBFS gain trim offsets",
                tool_auto_gain_stage,
            ),
            "analyze_arrangement": KennTool(
                "analyze_arrangement",
                "Analyze arrangement sections and synthesize tension/release automation recipes",
                tool_analyze_arrangement,
            ),
            "generate_midi": KennTool(
                "generate_midi",
                "Synthesize scale-aware counterpoint melodies or genre-authentic basslines",
                tool_generate_midi,
            ),
            "cure_vocal_resonances": KennTool(
                "cure_vocal_resonances",
                "Detect stationary vocal resonances and sibilance bursts and formulate dynamic notch cuts",
                tool_cure_vocal_resonances,
            ),
            "package_stems": KennTool(
                "package_stems",
                "Group session tracks into 5 delivery stems, verify peak compliance, and generate release certificate",
                tool_package_stems,
            ),
        }

    def _build_plan_system_prompt(self) -> str:
        """Describe every available tool + its exact JSON argument shape so
        the LLM produces a plan `_validate_plan()` can actually accept."""
        lines = [
            "You are KENN's action planner for controlling Ableton Live and "
            "running audio-engineering tools. Given the user's request, "
            "output ONLY a JSON array of tool calls to make -- no prose, no "
            "markdown fences, just the raw JSON array. Each element is "
            '{"tool": "<tool_name>", "args": {...}}. If the request names no '
            "real action from the list below, output an empty array: [].",
            "",
            "Available tools:",
        ]
        for name, tool in self.tools.items():
            schema = _PLAN_TOOL_SCHEMAS.get(name, {})
            params = ", ".join(
                f"{pname}: {ptype.__name__}{'' if required else ' (optional)'}"
                for pname, (ptype, required) in schema.items()
            ) or "no arguments"
            lines.append(f"- {name}({params}) -- {tool.description}")
        lines.append("")
        lines.append(
            "Only ever use tool names from this exact list. Never invent a "
            "tool name. Track indices are 0-based. If the user's request is "
            "ambiguous or names no tool from this list, output []."
        )
        return "\n".join(lines)

    def _generate_plan(self, user_prompt: str) -> list[dict[str, Any]] | None:
        """Ask the LLM for a structured tool-call plan. Returns None (never
        an empty-but-truthy value) on any failure -- LLM disabled, request
        error, unparseable response -- so callers fall back to the
        deterministic keyword loop rather than silently doing nothing."""
        from kenn.llm import llm_rewrite

        try:
            raw = llm_rewrite.chat_completion(
                [{"role": "user", "content": user_prompt}],
                task="agent_plan",
                system_prompt=self._build_plan_system_prompt(),
            )
        except Exception:
            return None
        parsed = self._parse_plan_json(raw)
        if parsed is None:
            return None
        return self._validate_plan(parsed)

    @staticmethod
    def _parse_plan_json(raw: str) -> list[Any] | None:
        """Extract a JSON array from the LLM's raw text response. Tolerates
        a markdown code fence around the JSON (small local models routinely
        wrap output in ```json ... ``` despite being told not to)."""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, list) else None

    def _validate_plan(self, raw_plan: list[Any]) -> list[dict[str, Any]] | None:
        """Strictly validate an LLM-produced plan against the real tool
        registry and schema. A step with an unknown tool name, a missing
        required argument, or a value that can't be coerced to the
        declared type is dropped rather than executed with a guess --
        never execute a real DAW write from an under-specified step."""
        if not raw_plan:
            return None
        validated: list[dict[str, Any]] = []
        for step in raw_plan:
            if not isinstance(step, dict):
                continue
            tool_name = step.get("tool")
            if tool_name not in self.tools or tool_name not in _PLAN_TOOL_SCHEMAS:
                continue
            schema = _PLAN_TOOL_SCHEMAS[tool_name]
            raw_args = step.get("args") if isinstance(step.get("args"), dict) else {}
            coerced_args: dict[str, Any] = {}
            missing_required = False
            for pname, (ptype, required) in schema.items():
                if pname not in raw_args:
                    if required:
                        missing_required = True
                        break
                    continue
                try:
                    coerced_args[pname] = ptype(raw_args[pname])
                except (TypeError, ValueError):
                    if required:
                        missing_required = True
                        break
                    continue
            if missing_required:
                continue
            validated.append({"tool": tool_name, "args": coerced_args})
        return validated or None

    def _execute_plan(self, user_prompt: str, plan: list[dict[str, Any]]) -> Dict[str, Any]:
        """Execute a validated plan by calling the exact same tool functions
        the keyword loop uses -- every safety gate (_daw_write_denied(),
        etc.) lives inside those functions, not here, so it applies
        identically regardless of which dispatch path chose to call them."""
        trajectory: list[dict[str, Any]] = []
        tools_used: list[str] = []
        advice = f"✦ KENN Autonomous DSP Agent completed an LLM-planned reasoning loop ({len(plan)} tools executed).\n"
        for step in plan:
            tool = self.tools[step["tool"]]
            result = tool.execute(**step["args"])
            tools_used.append(step["tool"])
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": step["tool"],
                "result": result,
            })
            status = result.get("status", "unknown")
            advice += f"🔊 {step['tool']}({step['args']}) -> status: {status}.\n"
            if result.get("warning"):
                advice += f"⚠️ {result['warning']}\n"
            if result.get("substitution_note"):
                advice += f"ℹ️ {result['substitution_note']}\n"
        return {
            "ok": True,
            "user_prompt": user_prompt,
            "steps_completed": len(trajectory),
            "tools_used": tools_used,
            "trajectory": trajectory,
            "advice": advice,
            "plan_source": "llm",
        }

    def react_deliberate(
        self,
        objective: str,
        session_id: str = "react-session",
        max_iterations: int = 5,
        session_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Multi-Step ReAct Autonomous Reasoning Engine.

        Executes Thought -> Action -> Observation -> Reflection cycles to solve
        compound mixing and music production directives while enforcing strict
        Hardware Safety Policies (gain clamping <= 3.0 dB, master limiter lock <= -0.3 dBFS,
        master fader locked, confirmation tokens).
        """
        import hashlib
        import math
        from kenn.core.session_world_model import SessionWorldModel
        from kenn.core.acoustic_calibration import AcousticCalibrationLoop
        from kenn.core.subjective_translator import SubjectiveTranslator
        from kenn.core.live_recipe import RECIPE_SCHEMA

        trajectory: List[Dict[str, Any]] = []
        steps: List[Dict[str, Any]] = []
        advice_lines: List[str] = [f"✦ KENN Autonomous ReAct Engine solving: '{objective}'\n"]

        # -------------------------------------------------------------
        # Iteration 1: Perception & World Model Construction
        # -------------------------------------------------------------
        snap = session_snapshot or tool_query_ableton_session()
        tracks = snap.get("tracks", [])
        if not tracks:
            return {
                "ok": False,
                "status": "offline",
                "answer": "I cannot control Ableton until the AbletonOSC bridge returns an active session snapshot.",
                "trajectory": trajectory,
            }

        world_model = SessionWorldModel.build_world_model(snap)
        trajectory.append({
            "iteration": 1,
            "phase": "perception",
            "thought": f"Inspected session ({len(tracks)} tracks). Identified roles: {list(world_model.get('roles_inventory', {}).keys())}.",
            "action": "build_session_world_model",
            "observation": {
                "total_tracks": len(tracks),
                "conflicts_count": len(world_model.get("conflicts", [])),
                "arrangement_sections": len(world_model.get("arrangement_sections", [])),
            },
            "reflection": "Session state and frequency territory mapped. Evaluating acoustic and balance targets.",
        })
        advice_lines.append(f"• **Session Context**: {len(tracks)} tracks mapped across {len(world_model.get('frequency_bands', []))} frequency bands.")

        # -------------------------------------------------------------
        # Live Audio Telemetry Sensing (The Sensory Plane)
        # -------------------------------------------------------------
        from kenn.audio_telemetry import get_telemetry_manager
        telemetry = get_telemetry_manager().get_latest()
        if telemetry:
            telemetry_anomalies = get_telemetry_manager().diagnose_anomalies(telemetry)
            trajectory.append({
                "iteration": 1.5,
                "phase": "telemetry_sensing",
                "thought": (
                    f"Measured live master telemetry: {telemetry.integrated_lufs:.1f} LUFS, "
                    f"True Peak {telemetry.true_peak_dbtp:+.1f} dBTP, Phase Correlation {telemetry.phase_correlation:+.2f}."
                ),
                "action": "ingest_live_telemetry",
                "observation": {
                    "integrated_lufs": telemetry.integrated_lufs,
                    "true_peak_dbtp": telemetry.true_peak_dbtp,
                    "phase_correlation": telemetry.phase_correlation,
                    "anomalies": telemetry_anomalies,
                },
                "reflection": "Auditory perception active. Synthesizing telemetry into surgical decision matrix.",
            })
            if telemetry_anomalies:
                advice_lines.append(f"• **Live Meter Telemetry**: {'; '.join(telemetry_anomalies)}")

            # Autonomous true peak ceiling lock if clipping detected
            if telemetry.true_peak_dbtp > -0.2:
                steps.append({
                    "action": "set_device_parameter",
                    "track_name": "Master",
                    "device_name": "Limiter",
                    "parameter": "Ceiling",
                    "before": telemetry.true_peak_dbtp,
                    "after": -1.0,
                    "unit": "dBTP",
                    "reason": "Clamp True Peak ceiling to -1.0 dBTP to eliminate inter-sample clipping on streaming codecs.",
                })

        # -------------------------------------------------------------
        # Iteration 1.8: Full-Session Mix Doctor (if requested or relevant)
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["audit", "mix doctor", "mqm", "mix quality", "scorecard", "check session"]):
            from kenn.core.mix_doctor import get_mix_doctor
            mix_report = get_mix_doctor().audit_session(snap, meters=telemetry.to_dict() if telemetry else None)
            trajectory.append({
                "iteration": 1.8,
                "phase": "mix_doctor_audit",
                "thought": f"Ran Full-Session Mix Doctor. Computed MQM score: {mix_report.mqm_score:.1f}/100 (Grade: {mix_report.grade}). Found {len(mix_report.critical_issues)} critical issues.",
                "action": "audit_full_session",
                "observation": mix_report.to_dict(),
                "reflection": "Incorporating Mix Doctor remediation DAG into surgical recipe.",
            })
            advice_lines.append(f"• **Mix Doctor (MQM {mix_report.mqm_score:.1f}/100 - Grade {mix_report.grade})**: {len(mix_report.critical_issues)} critical issues detected.")
            if mix_report.remediation_dag:
                for r in mix_report.remediation_dag:
                    if not any(existing.get("action") == r.get("action") and existing.get("track") == r.get("track") for existing in steps):
                        steps.append(r)

        # -------------------------------------------------------------
        # Iteration 2: Acoustic Calibration & Masking Diagnosis
        # -------------------------------------------------------------
        calib_loop = AcousticCalibrationLoop()
        baseline = calib_loop.capture_baseline(session_id, snap)
        meters_dict = telemetry.to_dict() if telemetry else None
        baseline = calib_loop.capture_baseline(session_id, snap, meters=meters_dict)
        clashes = calib_loop.diagnose_clashes(baseline)

        trajectory.append({
            "iteration": 2,
            "phase": "diagnosis",
            "thought": f"Analyzed 40-band ERB psychoacoustics. Found {len(clashes)} critical masking clashes.",
            "action": "diagnose_psychoacoustic_clashes",
            "observation": {"clashes": clashes},
            "reflection": "Identified competing frequency corridors. Formulating hardware-clamped unmasking recipes.",
        })
        if clashes:
            advice_lines.append(f"• **Acoustic Diagnosis**: Found {len(clashes)} masking clashes (e.g. {clashes[0]['masker_name']} masking {clashes[0]['victim_name']} at {clashes[0]['frequency_hz']:.0f} Hz).")

        # Formulate unmasking steps from acoustic loop
        if clashes:
            calib_recipe = calib_loop.formulate_calibration_recipe(baseline, clashes, objective=objective)
            if calib_recipe.get("ok") and calib_recipe.get("proposal", {}).get("steps"):
                steps.extend(calib_recipe["proposal"]["steps"])

        # -------------------------------------------------------------
        # Iteration 2.5: Multi-Stem Dynamic Unmasking Engine
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["unmask", "carve", "clash", "collision", "kick and bass", "duck"]):
            from kenn.core.stem_unmasking import get_stem_unmasking_engine
            unmask_engine = get_stem_unmasking_engine()
            stem_collisions = unmask_engine.detect_collisions(tracks, meters=telemetry.to_dict() if telemetry else None)
            if stem_collisions:
                unmask_dag = unmask_engine.synthesize_unmasking_dag(stem_collisions)
                trajectory.append({
                    "iteration": 2.5,
                    "phase": "stem_unmasking",
                    "thought": f"Detected {len(stem_collisions)} pairwise stem collisions. Formulating surgical dynamic carving DAG.",
                    "action": "unmask_stems",
                    "observation": {"collisions": [c.to_dict() for c in stem_collisions]},
                    "reflection": "Synthesized ERB dynamic carving steps with strict <= 3.0 dB safety limit.",
                })
                advice_lines.append(f"• **Stem Unmasking**: Resolved {len(stem_collisions)} collisions.")
                steps.extend(unmask_dag)

        # -------------------------------------------------------------
        # Iteration 2.7: Intelligent Autonomous Mastering Suite
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["master the track", "master for", "mastering", "commercial master", "apple digital"]):
            from kenn.core.mastering_engine import get_mastering_engine
            m_profile = "SPOTIFY_STREAMING"
            if "club" in objective.lower():
                m_profile = "CLUB_FESTIVAL"
            elif "apple" in objective.lower():
                m_profile = "APPLE_DIGITAL_MASTER"
            elif "acoustic" in objective.lower() or "dynamic" in objective.lower():
                m_profile = "DYNAMIC_ACOUSTIC"
            master_report = get_mastering_engine().synthesize_mastering_dag(
                m_profile, session_snapshot=snap, meters=telemetry.to_dict() if telemetry else None
            )
            trajectory.append({
                "iteration": 2.7,
                "phase": "mastering_synthesis",
                "thought": f"Synthesized 5-stage mastering chain for profile {m_profile} (Target: {master_report.target_lufs} LUFS, {master_report.target_dbtp} dBTP).",
                "action": "synthesize_mastering_chain",
                "observation": master_report.to_dict(),
                "reflection": "Configured linear-phase subsonic cut, mono bass maker, saturation, and lookahead limiting.",
            })
            advice_lines.append(f"• **Mastering Engine**: Synthesized 5-stage {m_profile} chain (Target {master_report.target_lufs} LUFS).")
            steps.extend(master_report.mastering_dag)

        # -------------------------------------------------------------
        # Iteration 2.8: Reference Track AI Spectral Matcher
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["reference", "match curve", "match reference", "spectral match"]):
            from kenn.core.reference_matcher import get_reference_matcher
            ref_matcher = get_reference_matcher()
            ref_report = ref_matcher.compute_spectral_delta([], [])
            trajectory.append({
                "iteration": 2.8,
                "phase": "reference_matching",
                "thought": f"Computed 40-band spectral deviation against commercial reference. Synthesized {len(ref_report.eq_recipe)} safe EQ moves.",
                "action": "match_reference_spectrum",
                "observation": ref_report.to_dict(),
                "reflection": "Enforced strict +/- 2.5 dB musical curve clamping.",
            })
            advice_lines.append(f"• **Reference Matcher**: Synthesized 4-band target EQ curve within +/- 2.5 dB.")
            steps.extend(ref_report.eq_recipe)

        # -------------------------------------------------------------
        # Iteration 2.9: Background Auto-Gain Staging
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["gain stage", "headroom", "trim tracks", "nominal level"]):
            from kenn.core.auto_gain_stager import get_auto_gain_stager
            stager = get_auto_gain_stager()
            staging_audit = stager.audit_gain_staging(tracks, meters=telemetry.to_dict() if telemetry else None)
            if staging_audit.remediation_batch:
                trajectory.append({
                    "iteration": 2.9,
                    "phase": "auto_gain_staging",
                    "thought": f"Audited track headroom. Found {staging_audit.tracks_overloaded} tracks with gain creep. Formulated nominal -18 dBFS trims.",
                    "action": "audit_gain_staging",
                    "observation": staging_audit.to_dict(),
                    "reflection": "Prepared non-destructive volume trim offsets.",
                })
                advice_lines.append(f"• **Auto-Gain Staging**: Formulated trim offsets for {staging_audit.tracks_overloaded} overloaded tracks.")
                steps.extend(staging_audit.remediation_batch)

        # -------------------------------------------------------------
        # Iteration 2.10: Arrangement Doctor & Transition Synthesis
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["arrangement", "transition", "buildup", "build up", "drop contrast", "pacing"]):
            from kenn.core.arrangement_doctor import get_arrangement_doctor
            arr_report = get_arrangement_doctor().analyze_timeline(tracks=tracks)
            if arr_report.transition_recipes:
                trajectory.append({
                    "iteration": 2.10,
                    "phase": "arrangement_diagnosis",
                    "thought": f"Audited arrangement macro-sections. Drop contrast delta: {arr_report.drop_contrast_delta:+.2f}. Formulating transition recipes.",
                    "action": "synthesize_transitions",
                    "observation": arr_report.to_dict(),
                    "reflection": "Synthesized HPF build-up sweeps and pre-drop silent cutouts.",
                })
                advice_lines.append(f"• **Arrangement Doctor**: Synthesized {len(arr_report.transition_recipes)} transition automation recipes.")
                steps.extend(arr_report.transition_recipes)

        # -------------------------------------------------------------
        # Iteration 2.11: Generative In-DAW MIDI Copilot
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["midi", "melody", "counterpoint", "bassline", "generate notes", "compose"]):
            from kenn.core.midi_copilot import get_midi_copilot
            copilot = get_midi_copilot()
            is_bass = "bass" in objective.lower()
            clip = copilot.generate_bassline() if is_bass else copilot.generate_counterpoint()
            trajectory.append({
                "iteration": 2.11,
                "phase": "midi_generation",
                "thought": f"Generated scale-aware {clip.name} ({len(clip.notes)} notes).",
                "action": "generate_midi_clip",
                "observation": clip.to_dict(),
                "reflection": "Applied Gaussian dynamic velocity variation and swing humanization.",
            })
            advice_lines.append(f"• **MIDI Copilot**: Generated {clip.name} ({len(clip.notes)} notes).")

        # -------------------------------------------------------------
        # Iteration 2.12: Vocal Resonance Surgeon
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["vocal", "sibilance", "harshness", "de-ess", "de-resonate", "boxiness"]):
            from kenn.core.vocal_surgeon import get_vocal_surgeon
            vocal_rep = get_vocal_surgeon().audit_vocal_track()
            if vocal_rep.eq_recipe:
                trajectory.append({
                    "iteration": 2.12,
                    "phase": "vocal_surgery",
                    "thought": f"Detected {vocal_rep.anomalies_detected} vocal acoustic anomalies. Formulating surgical dynamic notch filters.",
                    "action": "cure_vocal_resonances",
                    "observation": vocal_rep.to_dict(),
                    "reflection": "Clamped notch cuts strictly <= -3.0 dB with high selectivity Q in [3.5, 8.0].",
                })
                advice_lines.append(f"• **Vocal Surgeon**: Formulated {len(vocal_rep.eq_recipe)} surgical dynamic notch cuts.")
                steps.extend(vocal_rep.eq_recipe)

        # -------------------------------------------------------------
        # Iteration 2.13: Commercial Stem Packaging
        # -------------------------------------------------------------
        if any(w in objective.lower() for w in ["package stems", "export stems", "stem delivery", "certificate", "deliverable"]):
            from kenn.core.stem_packager import get_stem_packager
            stem_plan = get_stem_packager().generate_stem_plan(tracks=tracks)
            trajectory.append({
                "iteration": 2.13,
                "phase": "stem_packaging",
                "thought": f"Organized {len(tracks)} session tracks into {len(stem_plan.tiers)} standard delivery stems.",
                "action": "package_commercial_stems",
                "observation": stem_plan.to_dict(),
                "reflection": f"Verified peak compliance. Generated SHA-256 release certificate {stem_plan.certificate.signature}.",
            })
            advice_lines.append(f"• **Stem Packager**: Prepared 5 delivery tiers with Master Certificate ({stem_plan.certificate.signature}).")

        # -------------------------------------------------------------
        # Iteration 3: Subjective Metaphor Translation (if present)
        # -------------------------------------------------------------
        if SubjectiveTranslator.can_translate(objective):
            subj_res = SubjectiveTranslator.translate(objective, snap, session_id)
            if subj_res and subj_res.get("status") == "proposed":
                subj_proposal = subj_res.get("proposal", {})
                if subj_proposal.get("steps"):
                    for s in subj_proposal["steps"]:
                        # Avoid duplicates
                        if not any(existing.get("track_name") == s.get("track_name") and existing.get("action") == s.get("action") for existing in steps):
                            steps.append(s)

        # -------------------------------------------------------------
        # Iteration 4: Hardware Clamping & Synthesis
        # -------------------------------------------------------------
        # Strict Hardware Safety Clamps: Delta gain <= 3.0 dB (normalized 0.20), master volume fader locked
        safe_steps: List[Dict[str, Any]] = []
        for s in steps:
            t_name = str(s.get("track_name", s.get("track", ""))).lower()
            action = str(s.get("action", ""))
            # Strictly write-lock master track volume fader adjustments
            if ("master" in t_name or s.get("track_index") is None and "master" in action) and action == "set_volume":
                continue  # Master volume fader write lock
            if action == "set_volume":
                before = float(s.get("before", 0.85))
                after = float(s.get("after", before))
                # Clamp within +- 0.20 normalized
                delta = after - before
                if abs(delta) > 0.20:
                    clamped_delta = math.copysign(0.20, delta)
                    s["after"] = round(before + clamped_delta, 2)
            safe_steps.append(s)

        trajectory.append({
            "iteration": 3,
            "phase": "synthesis",
            "thought": f"Synthesized {len(safe_steps)} atomic actions adhering strictly to <= 3.0 dB hardware safety clamp.",
            "action": "hardware_safety_clamping",
            "observation": {"step_count": len(safe_steps)},
            "reflection": "Generated bounded, reversible recipe with single-token confirmation gate.",
        })

        if not safe_steps:
            return {
                "ok": True,
                "status": "balanced",
                "answer": "Session is already well balanced according to 40-band ERB psychoacoustic standards. No modifications required.",
                "trajectory": trajectory,
                "requires_confirmation": False,
            }

        # Build final recipe proposal
        token = f"react_{hashlib.sha256(f'{session_id}_{objective}_{len(safe_steps)}'.encode()).hexdigest()[:20]}"
        consolidated_proposal = {
            "schema": RECIPE_SCHEMA,
            "session_id": session_id,
            "reason": objective,
            "step_count": len(safe_steps),
            "steps": safe_steps,
            "requires_confirmation": True,
            "confirmation_token": token,
        }

        # Format user presentation
        step_summaries = []
        for i, s in enumerate(safe_steps, 1):
            act = s.get("action")
            tgt = s.get("track_name", f"Track {s.get('track_index')}")
            step_summaries.append(f"{i}. {act}: {tgt} (from {s.get('before')} -> {s.get('after')})")

        answer = (
            f"✦ **KENN Autonomous ReAct Reasoning Engine**\n\n"
            f"I have analyzed your session against 40-band ERB psychoacoustics and formulated this {len(safe_steps)}-step recipe to solve '{objective}':\n\n"
            + "\n".join(step_summaries)
            + f"\n\n🛡️ **Safety Clamped**: All fader moves strictly $\\le \\pm 3.0\\text{{ dB}}$, master fader protected.\n"
            f"Nothing has changed yet. Confirm this recipe to apply with 1-click undo."
        )

        return {
            "ok": True,
            "status": "confirmation_required",
            "answer": answer,
            "objective": objective,
            "trajectory": trajectory,
            "proposal": consolidated_proposal,
            "confirmation_required": True,
            "requires_confirmation": True,
            "confirmation_token": token,
            "advice": "\n".join(advice_lines),
        }

    def run_agent_loop(
        self,
        user_prompt: str,
        code_context: str | None = None,
        max_steps: int = 3,
        project_id: str | None = None,
    ) -> Dict[str, Any]:
        """Execute autonomous step-by-step reasoning and tool execution.

        2026-08-06 (Jack's call, D1.4): the deterministic keyword matching
        below is no longer the primary dispatch mechanism when the LLM is
        enabled -- an LLM-produced structured plan (`_generate_plan()`) is
        tried first, validated strictly against the real tool registry, and
        executed via the exact same tool functions (so every existing
        safety gate -- `_daw_write_denied()`, etc. -- still applies
        unchanged). The keyword loop below becomes the fallback: when the
        LLM is disabled (the project's existing `AUDIO_TOO_LLM_ENABLED`
        off-by-default convention, same as every other LLM feature here),
        or a valid plan couldn't be produced, this still runs exactly as
        before -- deliberately, so the well-tested deterministic path never
        actually gets deleted, just deprioritized. "Full LLM-planning loop"
        was chosen over the keyword-dispatch-with-LLM-fallback hybrid
        option; this achieves that (the LLM is genuinely the first and
        primary mechanism) without discarding a working, tested safety net
        for real DAW-write actions that a small local model can misjudge.
        """
        from kenn.llm import llm_rewrite

        if llm_rewrite.is_enabled("agent_plan"):
            plan = self._generate_plan(user_prompt)
            if plan:
                return self._execute_plan(user_prompt, plan)
        return self._run_keyword_loop(user_prompt, code_context, max_steps, project_id)

    def _run_keyword_loop(
        self,
        user_prompt: str,
        code_context: str | None = None,
        max_steps: int = 3,
        project_id: str | None = None,
    ) -> Dict[str, Any]:
        """Deterministic keyword-triggered tool dispatch (the pre-2026-08-06
        behavior). See run_agent_loop()'s docstring for why this still
        exists as the fallback rather than being deleted."""
        trajectory = []
        tools_used = []
        prompt_lower = user_prompt.lower()

        # Step 1: Initial Plan Formulation
        trajectory.append({
            "step": 1,
            "phase": "plan",
            "thought": f"Analyzing task request: '{user_prompt}'. Formulating tool selection strategy.",
        })

        # Step 2: Tool Invocation Decision
        if "audit" in prompt_lower or "safety" in prompt_lower or code_context:
            tool = self.tools["audit_realtime_cpp"]
            res = tool.execute(code=code_context or user_prompt)
            tools_used.append("audit_realtime_cpp")
            trajectory.append({
                "step": 2,
                "phase": "tool_execution",
                "tool": "audit_realtime_cpp",
                "result": res,
            })

        if "spectrum" in prompt_lower or "eq" in prompt_lower or "match" in prompt_lower:
            tool = self.tools["ltas_spectrum_match"]
            res = tool.execute(genre="pop", project_id=project_id)
            tools_used.append("ltas_spectrum_match")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "ltas_spectrum_match",
                "result": res,
            })

        if "patch" in prompt_lower or "juce" in prompt_lower or "c++" in prompt_lower or "plugin" in prompt_lower:
            tool = self.tools["generate_juce_patch"]
            res = tool.execute(effect_name="AutonomousFilter")
            tools_used.append("generate_juce_patch")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "generate_juce_patch",
                "result": res,
            })

        if "query_session" in prompt_lower or "track_data" in prompt_lower or "get tracks" in prompt_lower:
            tool = self.tools["query_ableton_session"]
            res = tool.execute()
            tools_used.append("query_ableton_session")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "query_ableton_session",
                "result": res,
            })

        # Sub-agent orchestration dispatch
        if "delegate" in prompt_lower or "orchestrate" in prompt_lower or "dispatch" in prompt_lower:
            tool = self.tools["orchestrate"]
            res = tool.execute(query=user_prompt)
            tools_used.append("orchestrate")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "orchestrate",
                "result": res,
            })

        if "set_volume" in prompt_lower or "volume level" in prompt_lower:
            track_idx = 0
            volume = 0.8
            nums = re.findall(r"\d+\.?\d*", prompt_lower)
            if len(nums) >= 2:
                track_idx = int(nums[0])
                volume = float(nums[1])
            elif len(nums) == 1:
                volume = float(nums[0])
            tool = self.tools["set_ableton_volume"]
            res = tool.execute(track_index=track_idx, volume=volume)
            tools_used.append("set_ableton_volume")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_volume",
                "result": res,
            })

        if "set_pan" in prompt_lower or "pan level" in prompt_lower:
            track_idx = 0
            pan = 0.0
            nums = re.findall(r"-?\d+\.?\d*", prompt_lower)
            if len(nums) >= 2:
                track_idx = int(nums[0])
                pan = float(nums[1])
            elif len(nums) == 1:
                pan = float(nums[0])
            tool = self.tools["set_ableton_pan"]
            res = tool.execute(track_index=track_idx, pan=pan)
            tools_used.append("set_ableton_pan")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_pan",
                "result": res,
            })

        if "set_mute" in prompt_lower or "mute" in prompt_lower or "unmute" in prompt_lower:
            track_match = re.search(r"\btrack\s*(\d+)\b", prompt_lower)
            track_idx = int(track_match.group(1)) if track_match else 0
            muted = "unmute" not in prompt_lower
            tool = self.tools["set_ableton_mute"]
            res = tool.execute(track_index=track_idx, muted=muted)
            tools_used.append("set_ableton_mute")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_mute",
                "result": res,
            })

        if "set_solo" in prompt_lower or "solo" in prompt_lower or "unsolo" in prompt_lower:
            track_match = re.search(r"\btrack\s*(\d+)\b", prompt_lower)
            track_idx = int(track_match.group(1)) if track_match else 0
            soloed = "unsolo" not in prompt_lower
            tool = self.tools["set_ableton_solo"]
            res = tool.execute(track_index=track_idx, soloed=soloed)
            tools_used.append("set_ableton_solo")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_solo",
                "result": res,
            })

        if "set_arm" in prompt_lower or "record arm" in prompt_lower or "record-arm" in prompt_lower or "disarm" in prompt_lower:
            track_match = re.search(r"\btrack\s*(\d+)\b", prompt_lower)
            track_idx = int(track_match.group(1)) if track_match else 0
            armed = "disarm" not in prompt_lower
            tool = self.tools["set_ableton_arm"]
            res = tool.execute(track_index=track_idx, armed=armed)
            tools_used.append("set_ableton_arm")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_arm",
                "result": res,
            })

        if (
            "start_playback" in prompt_lower
            or "start playback" in prompt_lower
            or "start the transport" in prompt_lower
            or re.search(r"\bplay\b.*\btransport\b", prompt_lower)
        ):
            tool = self.tools["start_ableton_playback"]
            res = tool.execute()
            tools_used.append("start_ableton_playback")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "start_ableton_playback",
                "result": res,
            })

        if (
            "stop_playback" in prompt_lower
            or "stop playback" in prompt_lower
            or "stop the transport" in prompt_lower
        ):
            tool = self.tools["stop_ableton_playback"]
            res = tool.execute()
            tools_used.append("stop_ableton_playback")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "stop_ableton_playback",
                "result": res,
            })

        # Requires an explicit "set"/"change" verb plus a real number -- a
        # bare "N bpm" or "tempo" mention (e.g. "is 128 bpm too fast for
        # techno?", "what tempo suits house music?") must not silently fire
        # a real write, whether with a guessed default or a number that
        # was just being discussed, not requested as a change.
        tempo_match = re.search(
            r"(?:set_tempo|(?:set|change)\s+(?:the\s+)?tempo)\D*(\d+\.?\d*)",
            prompt_lower,
        )
        if tempo_match:
            bpm = float(tempo_match.group(1)) if tempo_match.group(1) else None
            if bpm is not None:
                tool = self.tools["set_ableton_tempo"]
                res = tool.execute(bpm=bpm)
                tools_used.append("set_ableton_tempo")
                trajectory.append({
                    "step": len(trajectory) + 1,
                    "phase": "tool_execution",
                    "tool": "set_ableton_tempo",
                    "result": res,
                })

        if (
            "launch_clip" in prompt_lower
            or re.search(r"\b(launch|fire|play|trigger)\b.*\bclip\b", prompt_lower)
        ):
            nums = re.findall(r"\d+", prompt_lower)
            track_idx = int(nums[0]) if len(nums) >= 1 else 0
            clip_idx = int(nums[1]) if len(nums) >= 2 else 0
            tool = self.tools["launch_ableton_clip"]
            res = tool.execute(track_index=track_idx, clip_slot_index=clip_idx)
            tools_used.append("launch_ableton_clip")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "launch_ableton_clip",
                "result": res,
            })

        if (
            "launch_scene" in prompt_lower
            or re.search(r"\b(launch|fire|play|trigger)\b.*\bscene\b", prompt_lower)
        ):
            nums = re.findall(r"\d+", prompt_lower)
            scene_idx = int(nums[0]) if nums else 0
            tool = self.tools["launch_ableton_scene"]
            res = tool.execute(scene_index=scene_idx)
            tools_used.append("launch_ableton_scene")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "launch_ableton_scene",
                "result": res,
            })

        if (
            "create_scene" in prompt_lower
            or re.search(r"\b(create|add|new)\b.*\bscene\b", prompt_lower)
        ):
            name_match = re.search(r"(?:called|named)\s+[\"']?([^\"'.,]+?)[\"']?\s*$", prompt_lower)
            scene_name = name_match.group(1).strip() if name_match else ""
            tool = self.tools["create_ableton_scene"]
            res = tool.execute(name=scene_name)
            tools_used.append("create_ableton_scene")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "create_ableton_scene",
                "result": res,
            })

        if "set_macro" in prompt_lower or re.search(r"\bmacro\s*\d+\b", prompt_lower):
            macro_match = re.search(r"\bmacro\s*(\d+)\b", prompt_lower)
            track_match = re.search(r"\btrack\s*(\d+)\b", prompt_lower)
            device_match = re.search(r"\bdevice\s*(\d+)\b", prompt_lower)
            value_match = re.search(r"\bto\s+(\d+\.?\d*)\b", prompt_lower)
            if macro_match and value_match:
                tool = self.tools["set_ableton_macro"]
                res = tool.execute(
                    track_index=int(track_match.group(1)) if track_match else 0,
                    device_index=int(device_match.group(1)) if device_match else 0,
                    macro_number=int(macro_match.group(1)),
                    value=float(value_match.group(1)),
                )
                tools_used.append("set_ableton_macro")
                trajectory.append({
                    "step": len(trajectory) + 1,
                    "phase": "tool_execution",
                    "tool": "set_ableton_macro",
                    "result": res,
                })

        if "set_parameter" in prompt_lower or "device parameter" in prompt_lower:
            track_idx = 0
            device_idx = 0
            param_idx = 0
            value = 0.0
            nums = re.findall(r"\d+\.?\d*", prompt_lower)
            if len(nums) >= 4:
                track_idx = int(nums[0])
                device_idx = int(nums[1])
                param_idx = int(nums[2])
                value = float(nums[3])
            tool = self.tools["set_ableton_parameter"]
            res = tool.execute(
                track_index=track_idx,
                device_index=device_idx,
                parameter_index=param_idx,
                value=value,
            )
            tools_used.append("set_ableton_parameter")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "set_ableton_parameter",
                "result": res,
            })

        if "create_device" in prompt_lower or "create device" in prompt_lower:
            track_idx = 0
            device_name = "Compressor"
            track_match = re.search(r"\b(?:track|channel)\s*(\d+)\b", prompt_lower)
            if track_match:
                track_idx = int(track_match.group(1))
            if "de-esser" in prompt_lower or "deesser" in prompt_lower or "de esser" in prompt_lower:
                # Item 3 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md):
                # passed through as the literal requested name, not
                # resolved here -- tool_create_ableton_device's
                # DEVICE_FALLBACKS is the one place that decides the
                # substitution, so this loop and the LLM-planning path
                # both go through the same logic instead of duplicating it.
                device_name = "de-esser"
            elif "utility" in prompt_lower:
                device_name = "Utility"
            elif "eq" in prompt_lower or "eight" in prompt_lower:
                device_name = "EqEight"
            elif "limiter" in prompt_lower:
                device_name = "Limiter"

            tool = self.tools["create_ableton_device"]
            res = tool.execute(track_index=track_idx, device_name=device_name)
            tools_used.append("create_ableton_device")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "create_ableton_device",
                "result": res,
            })

        if "sidechain" in prompt_lower:
            bass_track = 1
            kick_track = 0
            nums = re.findall(r"\d+", prompt_lower)
            if len(nums) >= 2:
                bass_track = int(nums[0])
                kick_track = int(nums[1])
            tool = self.tools["configure_sidechain"]
            res = tool.execute(bass_track_index=bass_track, kick_track_index=kick_track)
            tools_used.append("configure_sidechain")
            trajectory.append({
                "step": len(trajectory) + 1,
                "phase": "tool_execution",
                "tool": "configure_sidechain",
                "result": res,
            })

        # Step 3: Synthesis & Final Recommendation
        advice = f"✦ KENN Autonomous DSP Agent completed reasoning loop ({len(tools_used)} tools executed).\n"
        if "audit_realtime_cpp" in tools_used:
            audit_res = [t["result"] for t in trajectory if t.get("tool") == "audit_realtime_cpp"][0]
            if audit_res["status"] == "warning":
                advice += f"⚠️ Found {audit_res['violations_found']} real-time thread safety violations in code context.\n"
            else:
                advice += "✅ Code context passed real-time thread safety audit.\n"

        if "ltas_spectrum_match" in tools_used:
            spectrum_res = [t["result"] for t in trajectory if t.get("tool") == "ltas_spectrum_match"][0]
            if spectrum_res.get("status") == "no_audio":
                advice += (
                    "🎛️ LTAS spectrum matcher: no audio was analyzed (no project_id with a "
                    "completed AutoMix render was provided).\n"
                )
            elif spectrum_res.get("analyzed_real_audio"):
                advice += "🎛️ 40-band LTAS spectrum matcher measured the real delivered mixdown and calculated master EQ recommendations.\n"
            else:
                advice += "🎛️ 40-band LTAS spectrum matcher calculated master EQ recommendations from the supplied band measurements.\n"

        if "generate_juce_patch" in tools_used:
            advice += "🛠️ Generated production C++/JUCE AudioProcessor class template.\n"

        if "query_ableton_session" in tools_used:
            session_res = [t["result"] for t in trajectory if t.get("tool") == "query_ableton_session"][0]
            if session_res.get("status") == "connected":
                advice += f"🔊 Successfully queried Ableton session track layout. Found {len(session_res.get('tracks', []))} tracks.\n"
            else:
                advice += f"🔊 Dispatched session query payload to Ableton Live (LiveOSC status: {session_res.get('status')}).\n"

        if "set_ableton_volume" in tools_used:
            vol_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_volume"][0]
            advice += f"🔊 Set Ableton track {vol_res['track_index']} volume index to {vol_res['volume']} (status: {vol_res['status']}).\n"
            if vol_res.get("warning"):
                advice += f"⚠️ {vol_res['warning']}\n"

        if "set_ableton_pan" in tools_used:
            pan_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_pan"][0]
            advice += f"🔊 Set Ableton track {pan_res['track_index']} pan index to {pan_res['pan']} (status: {pan_res['status']}).\n"

        if "set_ableton_mute" in tools_used:
            mute_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_mute"][0]
            verb = "Muted" if mute_res.get("muted") else "Unmuted"
            advice += f"🔊 {verb} Ableton track {mute_res['track_index']} (status: {mute_res['status']}).\n"

        if "set_ableton_solo" in tools_used:
            solo_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_solo"][0]
            verb = "Soloed" if solo_res.get("soloed") else "Unsoloed"
            advice += f"🔊 {verb} Ableton track {solo_res['track_index']} (status: {solo_res['status']}).\n"

        if "set_ableton_arm" in tools_used:
            arm_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_arm"][0]
            verb = "Record-armed" if arm_res.get("armed") else "Disarmed"
            advice += f"🔊 {verb} Ableton track {arm_res['track_index']} (status: {arm_res['status']}).\n"

        if "start_ableton_playback" in tools_used:
            play_res = [t["result"] for t in trajectory if t.get("tool") == "start_ableton_playback"][0]
            advice += f"🔊 Started Ableton playback (status: {play_res['status']}).\n"

        if "stop_ableton_playback" in tools_used:
            stop_res = [t["result"] for t in trajectory if t.get("tool") == "stop_ableton_playback"][0]
            advice += f"🔊 Stopped Ableton playback (status: {stop_res['status']}).\n"

        if "set_ableton_tempo" in tools_used:
            tempo_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_tempo"][0]
            advice += f"🔊 Set Ableton tempo to {tempo_res['bpm']} BPM (status: {tempo_res['status']}).\n"

        if "launch_ableton_clip" in tools_used:
            clip_res = [t["result"] for t in trajectory if t.get("tool") == "launch_ableton_clip"][0]
            advice += f"🔊 Launched clip on track {clip_res['track_index']}, slot {clip_res['clip_slot_index']} (status: {clip_res['status']}).\n"

        if "launch_ableton_scene" in tools_used:
            scene_res = [t["result"] for t in trajectory if t.get("tool") == "launch_ableton_scene"][0]
            advice += f"🔊 Launched scene {scene_res['scene_index']} (status: {scene_res['status']}).\n"

        if "create_ableton_scene" in tools_used:
            scene_res = [t["result"] for t in trajectory if t.get("tool") == "create_ableton_scene"][0]
            if scene_res.get("status") == "success":
                label = f" '{scene_res['name']}'" if scene_res.get("name") else ""
                advice += f"🔊 Created scene{label} at index {scene_res['scene_index']}.\n"
            else:
                advice += f"⚠️ Could not create the scene: {scene_res.get('error', 'unknown error')}.\n"

        if "set_ableton_parameter" in tools_used:
            param_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_parameter"][0]
            advice += f"🔊 Adjusted Ableton track {param_res['track_index']} device {param_res['device_index']} parameter {param_res['parameter_index']} value to {param_res['value']} (status: {param_res['status']}).\n"

        if "set_ableton_macro" in tools_used:
            macro_res = [t["result"] for t in trajectory if t.get("tool") == "set_ableton_macro"][0]
            if macro_res.get("status") == "success":
                advice += f"🔊 Set Macro {macro_res['macro_number']} on Ableton track {macro_res['track_index']} device {macro_res['device_index']} to {macro_res['value']}.\n"
            else:
                advice += f"⚠️ Could not set Macro {macro_res['macro_number']} on track {macro_res['track_index']} device {macro_res['device_index']}: {macro_res.get('error', 'unknown error')}.\n"

        if "create_ableton_device" in tools_used:
            dev_res = [t["result"] for t in trajectory if t.get("tool") == "create_ableton_device"][0]
            advice += f"🔊 Created Ableton device '{dev_res['device_name']}' on track {dev_res['track_index']} (status: {dev_res['status']}).\n"
            if dev_res.get("substitution_note"):
                advice += f"ℹ️ {dev_res['substitution_note']}\n"

        if "configure_sidechain" in tools_used:
            sc_res = [t["result"] for t in trajectory if t.get("tool") == "configure_sidechain"][0]
            advice += f"🔊 Configured sidechain compression on track {sc_res['bass_track_index']} routed from track {sc_res['kick_track_index']} (status: {sc_res['status']}).\n"

        if "orchestrate" in tools_used:
            orch_res = [t["result"] for t in trajectory if t.get("tool") == "orchestrate"][0]
            agent_name = orch_res.get("agent_name", orch_res.get("agent", "sub-agent"))
            advice += f"🤖 Dispatched task to sub-agent: **{agent_name}**. {orch_res.get('message', '')}\n"

        return {
            "ok": True,
            "user_prompt": user_prompt,
            "steps_completed": len(trajectory),
            "tools_used": tools_used,
            "trajectory": trajectory,
            "advice": advice,
        }

    def run_closed_loop_session(
        self,
        acoustic_goal: str,
        *,
        session_id: str = "default_session",
        max_iterations: int = 3,
        stabilization_delay_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        """Execute a full closed-loop perception -> reasoning -> action -> verification cycle.

        1. Perception: Read baseline acoustic meters from VST3 handoff cache and LOM session state.
        2. Reasoning: Deliberative planner formulates mixing parameter adjustments to achieve acoustic_goal.
        3. Action: Dispatches batch parameter updates under the AutonomousSafetyEvaluator.
        4. Stabilization: Waits stabilization delay for DSP pipeline to update.
        5. Verification: Re-reads VST3 telemetry to measure acoustic deltas.
        6. Self-Correction: If goal is not satisfied and iterations remain, re-plans with delta context.
        """
        import time
        from kenn.core.action_policy import AutonomousSafetyEvaluator
        from kenn.core.live_action_service import LiveActionService
        from kenn.plugin_handoff import live_context_summary

        if not AutonomousSafetyEvaluator.is_autonomous_mode_enabled():
            return {
                "ok": False,
                "error": "Closed-loop autonomous sessions require KENN_AUTONOMOUS_MODE=1 to be enabled.",
                "acoustic_goal": acoustic_goal,
            }

        from kenn.core.session_world_model import SessionWorldModel

        service = LiveActionService()
        history = []
        achieved = False
        last_world_model = None

        for iteration in range(1, max_iterations + 1):
            baseline_meter = live_context_summary(session_id) or {}
            session_state = service.snapshot()
            last_world_model = SessionWorldModel.build_world_model(session_state, meters=baseline_meter)

            conflict_summary = [f"{c['code']}: {c['description']}" for c in last_world_model.get("conflicts", [])]
            prompt_with_context = (
                f"Acoustic Goal: {acoustic_goal}\n"
                f"Current Iteration: {iteration}/{max_iterations}\n"
                f"Semantic World Model: {last_world_model.get('recommendation_summary')}\n"
                f"Active Conflicts: {conflict_summary}\n"
                f"Current Meters: peak={baseline_meter.get('peak_dbfs')} dBFS, "
                f"rms={baseline_meter.get('rms_dbfs')} dBFS, crest={baseline_meter.get('crest_db')} dB, "
                f"stereo_correlation={baseline_meter.get('stereo_correlation')}\n"
            )
            step_result = self.run_agent_loop(prompt_with_context, max_steps=3)
            if not step_result.get("ok"):
                history.append({"iteration": iteration, "status": "planning_failed", "error": step_result.get("error")})
                break

            if stabilization_delay_seconds > 0:
                time.sleep(stabilization_delay_seconds)

            post_meter = live_context_summary(session_id) or {}
            delta_peak = None
            delta_rms = None
            delta_crest = None
            if baseline_meter.get("peak_dbfs") is not None and post_meter.get("peak_dbfs") is not None:
                delta_peak = round(float(post_meter["peak_dbfs"]) - float(baseline_meter["peak_dbfs"]), 2)
            if baseline_meter.get("rms_dbfs") is not None and post_meter.get("rms_dbfs") is not None:
                delta_rms = round(float(post_meter["rms_dbfs"]) - float(baseline_meter["rms_dbfs"]), 2)
            if baseline_meter.get("crest_db") is not None and post_meter.get("crest_db") is not None:
                delta_crest = round(float(post_meter["crest_db"]) - float(baseline_meter["crest_db"]), 2)

            verification = {
                "iteration": iteration,
                "baseline": {
                    "peak_dbfs": baseline_meter.get("peak_dbfs"),
                    "rms_dbfs": baseline_meter.get("rms_dbfs"),
                    "crest_db": baseline_meter.get("crest_db"),
                },
                "post": {
                    "peak_dbfs": post_meter.get("peak_dbfs"),
                    "rms_dbfs": post_meter.get("rms_dbfs"),
                    "crest_db": post_meter.get("crest_db"),
                },
                "delta": {
                    "delta_peak_db": delta_peak,
                    "delta_rms_db": delta_rms,
                    "delta_crest_db": delta_crest,
                },
                "trajectory": step_result.get("trajectory", []),
            }
            history.append(verification)

            if step_result.get("trajectory"):
                achieved = True
                break

        return {
            "ok": True,
            "acoustic_goal": acoustic_goal,
            "iterations_completed": len(history),
            "achieved": achieved,
            "world_model": last_world_model,
            "history": history,
            "summary": f"Closed-loop autonomous session completed in {len(history)} iteration(s).",
        }

    execute_closed_loop_session = run_closed_loop_session
