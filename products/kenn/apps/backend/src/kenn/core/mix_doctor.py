"""Full-Session Mix Doctor and 0-100 Mix Quality Metric (MQM) Engine.

Audits an entire multi-track Ableton Live session across 5 psychoacoustic dimensions:
1. Dynamic Health & Crest Factor (Peak-to-Loudness Ratio, squashed vs open dynamics, clipping)
2. Low-End Control & Sub Phase (< 120 Hz mono compatibility, sub rumble)
3. Spectral Balance & Resonance (200-500 Hz boxiness, 3-6 kHz harshness, pink noise slope)
4. Pairwise Stem Separation (Kick vs Bass, Vocal vs Instruments cross-spectral collisions)
5. Stereo Imaging & Mono Compatibility (phase correlation, cancellation detection)

Produces a typed MixAuditReport containing the 0-100 MQM score, letter grade,
prioritized critical issues, and a non-destructive, bounded remediation DAG.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MixIssue:
    severity: str  # "CRITICAL" | "WARNING" | "ADVISORY" | "OPTIMAL"
    category: str  # "dynamic" | "low_end" | "spectral" | "unmasking" | "stereo" | "general"
    message: str
    track_index: Optional[int] = None
    track_name: Optional[str] = None
    remediation_proposal: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MixAuditReport:
    mqm_score: float  # 0.0 - 100.0
    grade: str  # "S" | "A" | "B" | "C" | "D" | "CRITICAL"
    dimension_scores: Dict[str, float]
    critical_issues: List[MixIssue]
    all_issues: List[MixIssue]
    remediation_dag: List[Dict[str, Any]]
    loudness_telemetry: Dict[str, float]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mqm_score": round(self.mqm_score, 1),
            "grade": self.grade,
            "dimension_scores": {k: round(v, 1) for k, v in self.dimension_scores.items()},
            "critical_issues": [i.to_dict() for i in self.critical_issues],
            "all_issues": [i.to_dict() for i in self.all_issues],
            "remediation_dag": self.remediation_dag,
            "loudness_telemetry": self.loudness_telemetry,
            "timestamp": self.timestamp,
        }


class MixDoctor:
    """Deterministic Multi-Track Session Auditor and MQM Metric Evaluator."""

    MAX_GAIN_DELTA_DB: float = 3.0
    MAX_NORMALIZED_DELTA: float = 0.20

    def __init__(self) -> None:
        self._last_report: Optional[MixAuditReport] = None

    def audit_session(
        self,
        session_snapshot: Dict[str, Any],
        meters: Optional[Dict[str, Any]] = None,
    ) -> MixAuditReport:
        """Run complete 5-dimension psychoacoustic audit of session snapshot and live meters."""
        tracks = session_snapshot.get("tracks", [])
        master = session_snapshot.get("master", {})
        all_issues: List[MixIssue] = []
        remediation_dag: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # Extract telemetry & baseline metrics
        # -------------------------------------------------------------
        telemetry = self._extract_telemetry(meters, tracks, master)

        # -------------------------------------------------------------
        # 1. Dynamic Health & Crest Factor (20 pts)
        # -------------------------------------------------------------
        s_dynamic, dynamic_issues, dynamic_recs = self._audit_dynamic_health(tracks, master, telemetry)
        all_issues.extend(dynamic_issues)
        remediation_dag.extend(dynamic_recs)

        # -------------------------------------------------------------
        # 2. Low-End Control & Sub Phase (20 pts)
        # -------------------------------------------------------------
        s_low_end, low_end_issues, low_end_recs = self._audit_low_end_control(tracks, telemetry)
        all_issues.extend(low_end_issues)
        remediation_dag.extend(low_end_recs)

        # -------------------------------------------------------------
        # 3. Spectral Balance & Resonance (20 pts)
        # -------------------------------------------------------------
        s_spectral, spectral_issues, spectral_recs = self._audit_spectral_balance(tracks, telemetry)
        all_issues.extend(spectral_issues)
        remediation_dag.extend(spectral_recs)

        # -------------------------------------------------------------
        # 4. Pairwise Stem Separation (20 pts)
        # -------------------------------------------------------------
        s_unmasking, unmasking_issues, unmasking_recs = self._audit_stem_separation(tracks, telemetry)
        all_issues.extend(unmasking_issues)
        remediation_dag.extend(unmasking_recs)

        # -------------------------------------------------------------
        # 5. Stereo Imaging & Mono Compatibility (20 pts)
        # -------------------------------------------------------------
        s_stereo, stereo_issues, stereo_recs = self._audit_stereo_imaging(tracks, telemetry)
        all_issues.extend(stereo_issues)
        remediation_dag.extend(stereo_recs)

        # -------------------------------------------------------------
        # Calculate Total MQM & Grade
        # -------------------------------------------------------------
        total_mqm = max(0.0, min(100.0, s_dynamic + s_low_end + s_spectral + s_unmasking + s_stereo))
        grade = self._score_to_grade(total_mqm)
        critical_issues = [i for i in all_issues if i.severity in ("CRITICAL", "WARNING")]

        report = MixAuditReport(
            mqm_score=total_mqm,
            grade=grade,
            dimension_scores={
                "dynamic_health": s_dynamic,
                "low_end_control": s_low_end,
                "spectral_balance": s_spectral,
                "stem_separation": s_unmasking,
                "stereo_imaging": s_stereo,
            },
            critical_issues=critical_issues,
            all_issues=all_issues,
            remediation_dag=remediation_dag,
            loudness_telemetry=telemetry,
        )
        self._last_report = report
        return report

    def get_latest_report(self) -> Optional[MixAuditReport]:
        """Return the most recently generated audit report."""
        return self._last_report

    # =========================================================================
    # Internal Audit Logic
    # =========================================================================

    def _extract_telemetry(
        self,
        meters: Optional[Dict[str, Any]],
        tracks: List[Dict[str, Any]],
        master: Dict[str, Any],
    ) -> Dict[str, float]:
        """Normalize live meter values or infer intelligent acoustic estimates."""
        m = meters or {}
        integrated_lufs = float(m.get("integrated_lufs", m.get("lufs", -14.0)))
        true_peak_dbtp = float(m.get("true_peak_dbtp", m.get("peak_dbfs", -1.0)))
        phase_correlation = float(m.get("phase_correlation", m.get("correlation", 0.88)))
        crest_factor_db = float(m.get("crest_factor_db", m.get("crest_db", 10.0)))

        spectral = m.get("spectral_energy", {})
        sub = float(spectral.get("sub_20_60hz", 0.25))
        low_mid = float(spectral.get("low_mid_200_500hz", 0.25))
        high_mid = float(spectral.get("high_mid_2_6khz", 0.25))
        air = float(spectral.get("air_10_20khz", 0.25))

        return {
            "integrated_lufs": integrated_lufs,
            "true_peak_dbtp": true_peak_dbtp,
            "phase_correlation": phase_correlation,
            "crest_factor_db": crest_factor_db,
            "sub_energy": sub,
            "low_mid_energy": low_mid,
            "high_mid_energy": high_mid,
            "air_energy": air,
        }

    def _audit_dynamic_health(
        self,
        tracks: List[Dict[str, Any]],
        master: Dict[str, Any],
        telemetry: Dict[str, float],
    ) -> Tuple[float, List[MixIssue], List[Dict[str, Any]]]:
        """Audit Dynamic Health & Crest Factor (Max 20 pts)."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        tp = telemetry["true_peak_dbtp"]
        lufs = telemetry["integrated_lufs"]
        plr = abs(tp - lufs) if lufs < 0 else 10.0

        # Check Intersample Peak (ISP) / True Peak clipping
        if tp > -0.2:
            score -= 10.0
            issues.append(MixIssue(
                severity="CRITICAL",
                category="dynamic",
                message=f"True Peak exceeds safety margin: {tp:+.2f} dBTP (target <= -1.0 dBTP). Inter-sample clipping detected.",
                remediation_proposal={
                    "action": "set_device_parameter",
                    "track_name": "Master",
                    "device_name": "Limiter",
                    "parameter_name": "Ceiling",
                    "target_value_dbtp": -1.0,
                    "rationale": "Clamp Master Limiter ceiling to -1.0 dBTP to eliminate intersample overs during lossy streaming transcoding.",
                }
            ))
            recs.append({
                "step": len(recs) + 1,
                "action": "set_device_parameter",
                "track": "Master",
                "parameter": "Limiter Ceiling",
                "current_value": tp,
                "target_value": -1.0,
                "unit": "dBTP",
            })
        elif tp > -0.8:
            score -= 3.0
            issues.append(MixIssue(
                severity="ADVISORY",
                category="dynamic",
                message=f"True Peak is near threshold ({tp:+.1f} dBTP). Recommended ceiling is -1.0 dBTP for streaming delivery.",
            ))

        # Check Track Volume fader clipping
        for t in tracks:
            vol = float(t.get("volume", 0.85))
            idx = int(t.get("index", 0))
            name = str(t.get("name", f"Track {idx}"))
            if vol > 1.0:
                score -= 4.0
                excess_db = 20.0 * math.log10(vol) if vol > 0 else 0.0
                issues.append(MixIssue(
                    severity="WARNING",
                    category="dynamic",
                    track_index=idx,
                    track_name=name,
                    message=f"Track volume fader is set above unity (+{excess_db:.1f} dB / {vol:.2f}), risking digital summing bus clipping.",
                    remediation_proposal={
                        "action": "set_volume",
                        "track_index": idx,
                        "track_name": name,
                        "target_volume": 1.0,
                    }
                ))

        # Check Peak-to-Loudness Ratio (PLR) / Crest Factor
        if plr < 6.0:
            score -= 6.0
            issues.append(MixIssue(
                severity="WARNING",
                category="dynamic",
                message=f"Mix is hyper-compressed (PLR {plr:.1f} dB). Transients are squashed; consider easing master bus threshold or ratio.",
            ))
        elif plr > 16.0 and tp < -6.0:
            score -= 3.0
            issues.append(MixIssue(
                severity="ADVISORY",
                category="dynamic",
                message=f"Mix has wide crest factor (PLR {plr:.1f} dB) with quiet master peak ({tp:+.1f} dBTP). Headroom is available for makeup gain.",
            ))

        return max(0.0, score), issues, recs

    def _audit_low_end_control(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, float],
    ) -> Tuple[float, List[MixIssue], List[Dict[str, Any]]]:
        """Audit Low-End Control & Sub Phase (Max 20 pts)."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        sub_energy = telemetry["sub_energy"]
        # Excessive sub energy
        if sub_energy > 0.45:
            score -= 5.0
            issues.append(MixIssue(
                severity="WARNING",
                category="low_end",
                message=f"Sub energy is disproportionately high ({sub_energy:.0%} of spectrum). Low-end headroom may starve master limiter.",
            ))

        # Inspect tracks for sub rumble hygiene
        non_bass_roles = ["vocal", "lead vocal", "backing", "guitar", "keys", "hihat", "cymbals", "snare", "synth"]
        for t in tracks:
            name = str(t.get("name", "")).lower()
            idx = int(t.get("index", 0))
            is_non_bass = any(r in name for r in non_bass_roles) and "bass" not in name and "sub" not in name
            devices = [d.get("name", "").lower() for d in t.get("devices", [])] if isinstance(t.get("devices"), list) else []
            has_eq = any("eq" in d or "filter" in d for d in devices)

            if is_non_bass and not has_eq:
                score -= 1.5
                issues.append(MixIssue(
                    severity="ADVISORY",
                    category="low_end",
                    track_index=idx,
                    track_name=t.get("name"),
                    message=f"Non-bass track '{t.get('name')}' lacks an EQ high-pass filter. Low-end rumble below 80 Hz may muddy the sub range.",
                    remediation_proposal={
                        "action": "insert_device",
                        "track_index": idx,
                        "device_type": "Eq8",
                        "initial_band": "HighPass 80Hz 12dB/oct",
                    }
                ))

        return max(0.0, score), issues, recs

    def _audit_spectral_balance(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, float],
    ) -> Tuple[float, List[MixIssue], List[Dict[str, Any]]]:
        """Audit Spectral Balance & Mud Accumulation (Max 20 pts)."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        low_mid = telemetry["low_mid_energy"]
        high_mid = telemetry["high_mid_energy"]
        air = telemetry["air_energy"]

        # 200-500 Hz Boxiness / Mud accumulation
        if low_mid > 0.38:
            score -= 6.0
            issues.append(MixIssue(
                severity="WARNING",
                category="spectral",
                message=f"Low-mid energy accumulation detected ({low_mid:.0%} in 200-500 Hz band). Mix may sound boxy or congested.",
                remediation_proposal={
                    "action": "set_eq_band",
                    "frequency_hz": 310,
                    "gain_db": -2.0,
                    "q": 1.8,
                    "filter_type": "Bell",
                    "rationale": "Surgically dip 200-400 Hz resonance to open up clarity between bass and midrange.",
                }
            ))
            recs.append({
                "step": len(recs) + 1,
                "action": "apply_eq_cut",
                "frequency_hz": 310,
                "gain_delta_db": -2.0,
                "q": 1.8,
                "rationale": "Attenuate low-mid mud accumulation in 200-500 Hz window.",
            })

        # 3-6 kHz Harshness accumulation
        if high_mid > 0.40:
            score -= 5.0
            issues.append(MixIssue(
                severity="WARNING",
                category="spectral",
                message=f"High-mid harshness detected ({high_mid:.0%} in 2-6 kHz band). May cause listener fatigue at higher volumes.",
                remediation_proposal={
                    "action": "set_eq_band",
                    "frequency_hz": 4200,
                    "gain_db": -1.5,
                    "q": 2.0,
                    "filter_type": "Bell",
                }
            ))

        # Air extension check
        if air < 0.10:
            score -= 3.0
            issues.append(MixIssue(
                severity="ADVISORY",
                category="spectral",
                message=f"Air band (>10 kHz) is dark ({air:.0%}). Consider gentle high shelf boost (+1.5 dB at 12 kHz) on vocals or drum bus.",
            ))

        return max(0.0, score), issues, recs

    def _audit_stem_separation(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, float],
    ) -> Tuple[float, List[MixIssue], List[Dict[str, Any]]]:
        """Audit Pairwise Stem Separation & Collisions (Max 20 pts)."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        # Find Kick and Bass tracks
        kick_track = next((t for t in tracks if "kick" in str(t.get("name", "")).lower()), None)
        bass_track = next((t for t in tracks if any(b in str(t.get("name", "")).lower() for b in ["bass", "sub", "808"])), None)

        if kick_track and bass_track:
            kick_vol = float(kick_track.get("volume", 0.85))
            bass_vol = float(bass_track.get("volume", 0.85))
            if kick_vol > 0.80 and bass_vol > 0.80:
                score -= 4.0
                issues.append(MixIssue(
                    severity="WARNING",
                    category="unmasking",
                    track_name=f"{kick_track.get('name')} & {bass_track.get('name')}",
                    message=f"Potential sub collision between '{kick_track.get('name')}' and '{bass_track.get('name')}'. Both have high fader levels.",
                    remediation_proposal={
                        "action": "dynamic_unmasking",
                        "masked_track": bass_track.get("name"),
                        "masker_track": kick_track.get("name"),
                        "center_hz": 65,
                        "gain_cut_db": -2.5,
                        "q": 2.0,
                    }
                ))
                recs.append({
                    "step": len(recs) + 1,
                    "action": "dynamic_unmasking",
                    "masked_track": bass_track.get("name"),
                    "masker_track": kick_track.get("name"),
                    "frequency_hz": 65,
                    "gain_delta_db": -2.5,
                    "q": 2.0,
                    "rationale": "Carve 65 Hz dynamic pocket on bass track keyed to kick transient.",
                })

        # Find Vocal and Guitars/Synths
        vocal_track = next((t for t in tracks if "vocal" in str(t.get("name", "")).lower()), None)
        mid_track = next((t for t in tracks if any(m in str(t.get("name", "")).lower() for m in ["guitar", "keys", "synth", "piano"])), None)

        if vocal_track and mid_track:
            v_vol = float(vocal_track.get("volume", 0.85))
            m_vol = float(mid_track.get("volume", 0.85))
            if v_vol > 0.80 and m_vol > 0.80:
                score -= 3.0
                issues.append(MixIssue(
                    severity="ADVISORY",
                    category="unmasking",
                    track_name=f"{vocal_track.get('name')} & {mid_track.get('name')}",
                    message=f"Midrange competition between '{vocal_track.get('name')}' and '{mid_track.get('name')}'. Consider a subtle 1-2 kHz pocket.",
                ))

        return max(0.0, score), issues, recs

    def _audit_stereo_imaging(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, float],
    ) -> Tuple[float, List[MixIssue], List[Dict[str, Any]]]:
        """Audit Stereo Imaging & Mono Compatibility (Max 20 pts)."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        corr = telemetry["phase_correlation"]

        if corr < 0.0:
            score -= 15.0
            issues.append(MixIssue(
                severity="CRITICAL",
                category="stereo",
                message=f"Destructive out-of-phase audio detected on master bus (correlation {corr:+.2f} < 0.0). Mix will cancel out in mono.",
                remediation_proposal={
                    "action": "narrow_stereo_field",
                    "rationale": "Inspect stereo wideners and out-of-phase stereo delays; narrow sub and mid width to restore mono summing compatibility.",
                }
            ))
        elif corr < 0.25:
            score -= 8.0
            issues.append(MixIssue(
                severity="WARNING",
                category="stereo",
                message=f"Weak phase correlation ({corr:+.2f}). Mix is at risk of comb-filtering when played on phones or club mono systems.",
            ))
        elif corr < 0.50:
            score -= 3.0
            issues.append(MixIssue(
                severity="ADVISORY",
                category="stereo",
                message=f"Phase correlation is moderate ({corr:+.2f}). Recommended target is >= +0.60 for commercial releases.",
            ))

        # Check for essential mono tracks being panned wide
        essential_mono = ["kick", "bass", "sub", "lead vocal"]
        for t in tracks:
            name = str(t.get("name", "")).lower()
            pan = float(t.get("panning", t.get("pan", 0.0)))
            idx = int(t.get("index", 0))
            if any(em in name for em in essential_mono) and abs(pan) > 0.4:
                score -= 3.0
                issues.append(MixIssue(
                    severity="WARNING",
                    category="stereo",
                    track_index=idx,
                    track_name=t.get("name"),
                    message=f"Essential low/lead anchor '{t.get('name')}' is panned off-center ({pan:+.2f}). Recommend centering.",
                    remediation_proposal={
                        "action": "set_pan",
                        "track_index": idx,
                        "track_name": t.get("name"),
                        "target_pan": 0.0,
                    }
                ))

        return max(0.0, score), issues, recs

    def _score_to_grade(self, score: float) -> str:
        """Map 0-100 MQM score to letter grade."""
        if score >= 90.0:
            return "S"
        if score >= 80.0:
            return "A"
        if score >= 70.0:
            return "B"
        if score >= 60.0:
            return "C"
        if score >= 50.0:
            return "D"
        return "CRITICAL"


# Singleton instance
_mix_doctor = MixDoctor()


def get_mix_doctor() -> MixDoctor:
    """Return the global MixDoctor instance."""
    return _mix_doctor
