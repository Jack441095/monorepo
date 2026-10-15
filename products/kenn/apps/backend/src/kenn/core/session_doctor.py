"""Audit Live track settings and report informational insert-meter observations.

Meter observations carry no verified Live target. Recipe steps come from
track-specific heuristics; their estimates are not measured repair outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional

from kenn.core.evidence import live_context_has_activity


BASS_KEYWORDS = frozenset({"bass", "sub", "808", "kick", "low"})
HIGH_PASS_DEVICES = frozenset({"eq eight", "channel eq", "auto filter", "eq three", "filter delay"})


def _finite_meter(value: Any) -> float | None:
    """Return a finite numeric meter value, leaving invalid observations unavailable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # Missing or malformed meters are not zero-valued observations.
        return None
    try:
        number = float(value)
    except OverflowError:
        # An unrepresentable integer cannot ground a meter finding.
        return None
    # NaN and infinity do not describe an observed signal level.
    return number if math.isfinite(number) else None


@dataclass
class Issue:
    code: str
    severity: str  # "critical", "warning", "advisory"
    track_index: int
    track_name: str
    description: str
    suggested_action: str
    target_param: str
    proposed_value: Any


@dataclass
class SessionAuditReport:
    ok: bool
    track_count: int
    issues_found: int
    issues: List[Issue] = field(default_factory=list)
    summary: str = ""
    remediation_batch: List[Dict[str, Any]] = field(default_factory=list)


class SessionDoctor:
    """Combine structural track advice with capture-scoped meter observations."""

    # Nominal headroom limits (normalized volume: 0.85 ~= 0 dB in Ableton's tapered fader)
    NOMINAL_FADER_LIMIT = 0.85
    HOT_FADER_LIMIT = 0.90
    REDUCTION_STEP = 0.08  # ~ -1.5 dB delta within autonomous safety envelope

    @classmethod
    def audit(
        cls,
        session_state: Dict[str, Any],
        meters: Optional[Dict[str, Any]] = None,
    ) -> SessionAuditReport:
        tracks = session_state.get("tracks", [])
        issues: List[Issue] = []

        # This is an insert capture, with no verified binding to a Live track or master.
        # Keep meter observations informational; a host track name is not a target identity.
        if isinstance(meters, dict) and live_context_has_activity(meters):
            peak = _finite_meter(meters.get("peak_dbfs"))
            corr = _finite_meter(meters.get("stereo_correlation"))
            # Preserve the existing -0.5 dBFS warning line; it is not a true-peak ceiling.
            if peak is not None and peak > -0.5:
                issues.append(Issue(
                    code="CAPTURE_SAMPLE_PEAK_RISK",
                    severity="advisory",
                    track_index=-1,
                    track_name="Captured insert",
                    description=f"Captured insert sample peak is near digital full scale ({peak:.1f} dBFS). This reading does not measure true peak or establish master-bus clipping.",
                    suggested_action="Check the captured insert's gain and downstream routing, then measure true peak separately before choosing an output ceiling.",
                    target_param="",
                    proposed_value=None,
                ))
            if corr is not None and corr < 0.0:
                issues.append(Issue(
                    code="CAPTURE_NEGATIVE_CORRELATION",
                    severity="advisory",
                    track_index=-1,
                    track_name="Captured insert",
                    description=f"Captured insert stereo correlation is negative ({corr:.2f}). Mono summing may reduce parts of this signal; this reading does not identify the affected frequencies or audible severity.",
                    suggested_action="Audition this capture in mono and inspect its stereo processing before choosing a change.",
                    target_param="",
                    proposed_value=None,
                ))

        # 2. Per-track audits
        for track in tracks:
            t_idx = track.get("index", track.get("track_index", 0))
            name = str(track.get("name", f"Track {t_idx}"))
            vol = float(track.get("volume", 0.85))
            lower_name = name.lower()

            # Skip master/return tracks for individual track fader checks
            if lower_name in {"master", "main"}:
                continue

            # Check A: Hot faders / Headroom risk
            if vol > cls.HOT_FADER_LIMIT:
                new_vol = max(0.0, vol - cls.REDUCTION_STEP)
                issues.append(Issue(
                    code="HEADROOM_CLIPPING_RISK",
                    severity="warning",
                    track_index=t_idx,
                    track_name=name,
                    description=f"Track fader is very hot ({vol:.2f} normalized). Lacks dynamic headroom for summing.",
                    suggested_action=f"Trim track volume from {vol:.2f} to {new_vol:.2f}.",
                    target_param="volume",
                    proposed_value=new_vol,
                ))

            # Check B: Low-End Mud (non-bass tracks without high-pass filter)
            is_bass = any(kw in lower_name for kw in BASS_KEYWORDS)
            devices = track.get("devices", [])
            has_hp_filter = False
            for dev in devices:
                dev_name = str(dev.get("name", "")).lower()
                dev_class = str(dev.get("class_name", "")).lower()
                if any(hpd in dev_name or hpd in dev_class for hpd in HIGH_PASS_DEVICES):
                    has_hp_filter = True
                    break

            if not is_bass and not has_hp_filter and len(devices) > 0:
                # If it's a vocal, guitar, pad, or synth without EQ/filter
                if any(kw in lower_name for kw in {"vocal", "vox", "pad", "synth", "lead", "guitar", "keys", "piano", "strings"}):
                    issues.append(Issue(
                        code="LOW_END_MUD_RISK",
                        severity="advisory",
                        track_index=t_idx,
                        track_name=name,
                        description=f"Non-bass track '{name}' has no high-pass filter. Low frequency rumble clutters mix headroom.",
                        suggested_action="Insert an EQ Eight or Channel EQ and apply a high-pass cut at 80-120 Hz.",
                        target_param="device_insert",
                        proposed_value="Channel EQ",
                    ))

            # Check C: Sub/Bass Stereo Width Check
            if is_bass and "sub" in lower_name:
                pan = float(track.get("panning", 0.0))
                if abs(pan) > 0.1:
                    issues.append(Issue(
                        code="SUB_BASS_OFF_CENTER",
                        severity="warning",
                        track_index=t_idx,
                        track_name=name,
                        description=f"Sub bass track '{name}' is panned off-center ({pan:+.2f}). Sub bass should be strictly mono centered.",
                        suggested_action="Center sub bass pan to 0.0.",
                        target_param="panning",
                        proposed_value=0.0,
                    ))

        # Check D: Empirical Psychoacoustic Masking Clashes
        track_profiles = [t for t in tracks if "erb_profile" in t]
        if len(track_profiles) >= 2:
            from kenn.core.psychoacoustics import compute_track_masking_matrix, generate_spectral_carving_proposals
            masking_res = compute_track_masking_matrix(track_profiles)
            carving_props = generate_spectral_carving_proposals(masking_res)
            for prop in carving_props:
                issues.append(Issue(
                    code="PSYCHOACOUSTIC_MASKING_CLASH",
                    severity="warning",
                    track_index=prop["masker_index"],
                    track_name=prop["masker_track"],
                    description=prop["reasoning"],
                    suggested_action=prop["action"],
                    target_param="device_eq_cut",
                    proposed_value=prop["suggested_cut_db"],
                ))

        # Check E: Dynamic Low-End Masking & Sidechain Ducking (Kick & 808 / Sub-Bass Carving)
        kick_tracks = [t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"kick", "bd"})]
        bass_tracks = [t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"808", "sub", "bass"}) and t not in kick_tracks]
        if kick_tracks and bass_tracks:
            from kenn.core.psychoacoustics import compute_dynamic_sidechain_ducking
            for kick in kick_tracks:
                k_idx = kick.get("index", kick.get("track_index", 0))
                k_name = str(kick.get("name", f"Kick {k_idx}"))
                k_vol = float(kick.get("volume", 0.85))
                for bass in bass_tracks:
                    b_idx = bass.get("index", bass.get("track_index", 0))
                    b_name = str(bass.get("name", f"Bass {b_idx}"))
                    b_vol = float(bass.get("volume", 0.85))
                    duck_res = compute_dynamic_sidechain_ducking(kick_energy=k_vol, bass_energy=b_vol)
                    if duck_res["ducking_required"]:
                        issues.append(Issue(
                            code="DYNAMIC_LOW_END_MASKING",
                            severity="warning",
                            track_index=b_idx,
                            track_name=b_name,
                            description=(
                                f"Kick '{k_name}' and Bass '{b_name}' collide in 40-90 Hz sub band "
                                f"(Collision Ratio: {duck_res['collision_ratio']*100:.1f}%). "
                                f"Dynamic masking causes transient smear and sub energy cancellation."
                            ),
                            suggested_action=(
                                f"Apply dynamic sidechain ducking of {abs(duck_res['gain_reduction_db']):.1f} dB "
                                f"on '{b_name}' keyed to '{k_name}' (Attack={duck_res['attack_ms']}ms, Release={duck_res['release_ms']}ms)."
                            ),
                            target_param="sidechain_ducking",
                            proposed_value=duck_res["gain_reduction_db"],
                        ))

        # Check F: Multi-Stem Headroom Balance (Sum of active track volumes exceeding safe bus limit)
        non_master_tracks = [t for t in tracks if str(t.get("name", "")).lower() not in {"master", "main"}]
        total_energy_sum = sum(float(t.get("volume", 0.85)) ** 2 for t in non_master_tracks)
        if len(non_master_tracks) >= 3 and total_energy_sum > (len(non_master_tracks) * 0.75):
            # Summed faders are uniformly pushed too hard; recommend calibrated multi-stem trim
            trim_amount = round(min(cls.REDUCTION_STEP, 0.05), 3)
            for trk in non_master_tracks:
                vol = float(trk.get("volume", 0.85))
                if vol >= 0.80:
                    t_idx = trk.get("index", trk.get("track_index", 0))
                    issues.append(Issue(
                        code="MULTI_STEM_SUMMING_OVERLOAD",
                        severity="advisory",
                        track_index=t_idx,
                        track_name=str(trk.get("name", f"Track {t_idx}")),
                        description="Multi-stem acoustic density exceeds safe master bus summing margin (> -3 dBFS inter-track headroom).",
                        suggested_action=f"Trim fader by -{trim_amount} normalized ({round(vol - trim_amount, 3)}) for summing headroom.",
                        target_param="volume",
                        proposed_value=max(0.0, round(vol - trim_amount, 3)),
                    ))

        # Generate atomic remediation batch for safe actions
        remediation_batch = []
        for issue in issues:
            if issue.proposed_value is not None and issue.track_index >= 0:
                if issue.target_param == "volume":
                    remediation_batch.append({
                        "action": "set_volume",
                        "track_index": issue.track_index,
                        "value": round(issue.proposed_value, 3),
                    })
                elif issue.target_param == "panning":
                    remediation_batch.append({
                        "action": "set_pan",
                        "track_index": issue.track_index,
                        "value": round(issue.proposed_value, 3),
                    })
                elif issue.target_param == "sidechain_ducking":
                    remediation_batch.append({
                        "action": "configure_sidechain",
                        "track_index": issue.track_index,
                        "value": round(issue.proposed_value, 3),
                    })

        summary = (
            f"Session Doctor Audit: {len(tracks)} tracks analyzed. "
            f"Found {len(issues)} issue(s) ({sum(1 for i in issues if i.severity == 'critical')} critical, "
            f"{sum(1 for i in issues if i.severity == 'warning')} warnings, "
            f"{sum(1 for i in issues if i.severity == 'advisory')} advisory). "
            f"Formulated {len(remediation_batch)} autonomous remediation action(s)."
        )

        return SessionAuditReport(
            ok=True,
            track_count=len(tracks),
            issues_found=len(issues),
            issues=issues,
            summary=summary,
            remediation_batch=remediation_batch,
        )

    @classmethod
    def formulate_surgical_remediation_proposal(
        cls,
        session_state: Dict[str, Any],
        meters: Optional[Dict[str, Any]] = None,
        session_id: str = "",
    ) -> Dict[str, Any]:
        """Synthesize an actionable, confirmation-gated recipe proposal for closed-loop acoustic remediation."""
        import hashlib
        from kenn.core.session_world_model import SessionWorldModel

        audit_report = cls.audit(session_state, meters=meters)
        world_model_res = SessionWorldModel.analyze(session_state)

        tracks = session_state.get("tracks", [])
        track_map = {t.get("index", t.get("track_index", i)): t for i, t in enumerate(tracks)}

        steps: List[Dict[str, Any]] = []
        resolved_conflict_count = 0
        # Informational capture observations cannot count as repairable conflicts or
        # trigger the recipe's existing baseline masking-improvement estimate.
        repair_issues = [issue for issue in audit_report.issues if issue.target_param]
        total_conflict_count = len(repair_issues) + len(world_model_res.get("conflicts", []))

        # Capture-only meter observations have no bound Live target or measured repair.
        # Only the existing track-specific rules below can contribute proposal steps.
        for issue in repair_issues:
            if issue.code in {"HEADROOM_CLIPPING_RISK", "MULTI_STEM_SUMMING_OVERLOAD"}:
                trim_val = round(issue.proposed_value, 3)
                steps.append({
                    "action": "set_volume",
                    "track_index": issue.track_index,
                    "track_name": issue.track_name,
                    "target_param": "volume",
                    "parameter": "Volume",
                    "value": trim_val,
                    "before_display": "current",
                    "after_display": f"{trim_val:.2f} fader",
                    "after_label": f"Trim {issue.track_name} fader",
                    "reason": issue.description,
                })
                resolved_conflict_count += 1
            elif issue.code == "SUB_BASS_OFF_CENTER":
                steps.append({
                    "action": "set_pan",
                    "track_index": issue.track_index,
                    "track_name": issue.track_name,
                    "target_param": "panning",
                    "parameter": "Pan",
                    "value": 0.0,
                    "before_display": "Off-center",
                    "after_display": "Center (C)",
                    "after_label": f"Center {issue.track_name} pan",
                    "reason": issue.description,
                })
                resolved_conflict_count += 1
            elif issue.code == "DYNAMIC_LOW_END_MASKING":
                duck_db = round(issue.proposed_value, 3)
                steps.append({
                    "action": "configure_sidechain",
                    "track_index": issue.track_index,
                    "track_name": issue.track_name,
                    "target_param": "compressor_sidechain",
                    "parameter": "Sidechain Ducking",
                    "value": duck_db,
                    "before_display": "Off",
                    "after_display": f"-{abs(duck_db):.1f} dB ducking",
                    "after_label": f"Sidechain ducking on {issue.track_name}",
                    "reason": issue.description,
                })
                resolved_conflict_count += 1

        # 2. Semantic Conflicts from World Model
        for conflict in world_model_res.get("conflicts", []):
            code = conflict.get("code")
            t_indices = conflict.get("track_indices", [])
            if code == "SUB_KICK_CLASH" and len(t_indices) >= 2:
                kick_idx, bass_idx = t_indices[0], t_indices[1]
                bass_name = str(track_map.get(bass_idx, {}).get("name", f"Track {bass_idx}"))
                steps.append({
                    "action": "device_eq_cut",
                    "track_index": bass_idx,
                    "track_name": bass_name,
                    "device_name": "EQ Eight",
                    "parameter": "EQ Eight 60 Hz Notch",
                    "parameters": {"band_index": 3, "frequency": 60.0, "gain_db": -2.5, "q": 3.0},
                    "before_display": "Flat",
                    "after_display": "-2.5 dB @ 60 Hz",
                    "after_label": f"Surgical 60 Hz notch on {bass_name}",
                    "reason": f"Surgical notch at 60 Hz on {bass_name} to give kick transient room.",
                })
                resolved_conflict_count += 1
            elif code == "LOW_MID_MUD_ACCUMULATION":
                for tidx in t_indices:
                    tname = str(track_map.get(tidx, {}).get("name", f"Track {tidx}"))
                    steps.append({
                        "action": "insert_device",
                        "track_index": tidx,
                        "track_name": tname,
                        "device_name": "EQ Eight",
                        "parameter": "EQ Eight 130 Hz HPF",
                        "parameters": {"band1_hp": 130.0, "band1_slope": 12},
                        "before_display": "Full range",
                        "after_display": "130 Hz High Pass",
                        "after_label": f"130 Hz HPF on {tname}",
                        "reason": f"Apply 130 Hz high-pass cut on {tname} to clean low-mid mud.",
                    })
                    resolved_conflict_count += 1
            elif code == "VOCAL_PRESENCE_MASKING" and len(t_indices) >= 2:
                vox_idx, synth_idx = t_indices[0], t_indices[1]
                synth_name = str(track_map.get(synth_idx, {}).get("name", f"Track {synth_idx}"))
                steps.append({
                    "action": "device_eq_cut",
                    "track_index": synth_idx,
                    "track_name": synth_name,
                    "device_name": "EQ Eight",
                    "parameter": "EQ Eight 3.2 kHz Cut",
                    "parameters": {"band_index": 5, "frequency": 3200.0, "gain_db": -2.0, "q": 2.5},
                    "before_display": "Flat",
                    "after_display": "-2.0 dB @ 3.2 kHz",
                    "after_label": f"3.2 kHz vocal pocket on {synth_name}",
                    "reason": f"Carve 3.2 kHz pocket on {synth_name} to grant lead vocal clarity corridor.",
                })
                resolved_conflict_count += 1

        # 3. Calculate predicted post-remediation acoustic deltas
        masking_reduction = round(
            min(1.0, (resolved_conflict_count / max(total_conflict_count, 1)) * 0.85 + 0.10) * 100, 1
        ) if total_conflict_count > 0 else 0.0

        headroom_reclaimed = 0.0
        for s in steps:
            if s.get("action") == "set_volume":
                headroom_reclaimed += 0.8
            elif s.get("action") == "insert_device" and "band1_hp" in s.get("parameters", {}):
                headroom_reclaimed += 0.3
        headroom_reclaimed = round(min(headroom_reclaimed, 3.0), 2)

        correlation_improvement = 0.0
        if any(s.get("action") == "set_pan" or s.get("parameters", {}).get("bass_mono") for s in steps):
            correlation_improvement = 0.45

        token_src = f"{session_id}_doctor_{len(steps)}_{total_conflict_count}"
        token = f"doctor_remedy_{hashlib.sha256(token_src.encode()).hexdigest()[:16]}"

        proposal = {
            "schema": "kenn.surgical_masking_remediation.v1",
            "action": "recipe",
            "session_id": session_id,
            "total_conflicts_analyzed": total_conflict_count,
            "resolved_conflict_count": resolved_conflict_count,
            "step_count": len(steps),
            "steps": steps,
            "predicted_metrics": {
                "masking_reduction_percent": masking_reduction,
                "headroom_reclaimed_db": headroom_reclaimed,
                "mono_correlation_delta": correlation_improvement,
            },
            "requires_confirmation": True,
            "confirmation_token": token,
            "is_doctor_remediation": True,
        }

        return {"ok": True, "audit_summary": audit_report.summary, "proposal": proposal}
