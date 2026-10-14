"""Full-Session Mix Doctor: the technical-health part (30 points) of the E2 grade.

Audits an entire multi-track Ableton Live session across 5 psychoacoustic dimensions:
1. Dynamic Health & Crest Factor (Peak-to-Loudness Ratio, squashed vs open dynamics, clipping)
2. Low-End Control & Sub Phase (< 120 Hz mono compatibility, sub rumble)
3. Spectral Balance & Resonance (200-500 Hz boxiness, 3-6 kHz harshness, pink noise slope)
4. Pairwise Stem Separation (Kick vs Bass, Vocal vs Instruments cross-spectral collisions)
5. Stereo Imaging & Mono Compatibility (phase correlation, cancellation detection)

Produces a typed MixAuditReport containing the technical-health score, a one-line meaning, prioritized
critical issues (each with the points it cost and where its threshold comes from), and a non-destructive,
bounded remediation DAG. There is no letter grade: a number and what it means is all we claim.
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
    # What this finding cost, in points of the final technical-health score, and where its threshold comes from.
    # Advice-only findings (name and fader guesses) cost 0 but still name their source, so a reader can see
    # why they carry no points.
    points_lost: float = 0.0
    source: str = ""
    # How much weight the source can bear, set from `source` in audit_session; see TIER_LEGEND.
    tier: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MixAuditReport:
    mqm_score: float  # points kept, out of points_available (at most 30)
    meaning: str  # one line saying what the number covers and how many deductions rest on a published source
    dimension_scores: Dict[str, Optional[float]]  # None = the dimension had no reading to score from
    critical_issues: List[MixIssue]
    all_issues: List[MixIssue]
    remediation_dag: List[Dict[str, Any]]
    loudness_telemetry: Dict[str, Optional[float]]  # None = the meter did not report this reading
    points_available: float = 30.0  # 6 per scored dimension; the score is never rescaled to 30
    unmeasured: List[str] = field(default_factory=list)  # telemetry readings that were missing
    legend: Dict[str, str] = field(default_factory=lambda: dict(TIER_LEGEND))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mqm_score": round(self.mqm_score, 1),
            "meaning": self.meaning,
            "dimension_scores": {k: None if v is None else round(v, 1) for k, v in self.dimension_scores.items()},
            "critical_issues": [i.to_dict() for i in self.critical_issues],
            "all_issues": [i.to_dict() for i in self.all_issues],
            "remediation_dag": self.remediation_dag,
            "loudness_telemetry": self.loudness_telemetry,
            "points_available": self.points_available,
            "unmeasured": self.unmeasured,
            "legend": self.legend,
            "timestamp": self.timestamp,
        }


# Technical health is 30 of the grade's 100 points (decided 14 Oct 2026), so each of the five dimensions is worth 6.
_POINTS_PER_DIMENSION = 6.0
# The audits below were tuned on a 20-point scale and their deductions are still written that way; audit_session
# converts them, so moving a threshold or a cost here does not mean redoing the arithmetic for the 30-point scale.
_WORKING_POINTS = 20.0

# Where a deduction's threshold comes from. Only the true-peak ceiling and the sign of the correlation meter rest on
# anything published; every other threshold is our own rule of thumb and says so, so the grade never implies more.
SPOTIFY_PEAK_RULE = (
    "Spotify for Artists, Loudness normalization: keep true peak below -1 dBTP (support.spotify.com, read 14 Oct 2026); "
    "the -0.2 and -0.8 dBTP steps are our own margin for meter error"
)
CORRELATION_SIGN_RULE = (
    "Correlation meter convention: a reading below 0 means the channels cancel when summed to mono; "
    "it is a convention, not a published standard, and the cost is our own"
)
HOUSE_RULE = "house rule: our own threshold with no published basis, to be checked against the owner's ears under E9"

# Three tiers so a reader can weigh a deduction at a glance. There is no corpus tier yet: nothing here was measured
# against reference tracks. When one is, it gets its own line, not a place among these.
TIER_LEGEND = {
    "published": "the threshold's main figure comes from a publisher's own guidance; our margins around it are named in the source",
    "convention": "a widely used meter convention with no published standard behind it",
    "judgement": "our own rule of thumb, not yet checked against the owner's ears or any reference",
}
_TIER_BY_SOURCE = {SPOTIFY_PEAK_RULE: "published", CORRELATION_SIGN_RULE: "convention"}


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

        telemetry = self._extract_telemetry(meters, tracks, master)

        # Each dimension reports a score, or None when none of the readings it judges came from a meter.
        # A missing meter must not look like a healthy mix (it used to: the old defaults scored 20/20),
        # so an unscored dimension is left out of the total instead of being filled in.
        s_dynamic, dynamic_issues, dynamic_recs = self._audit_dynamic_health(tracks, master, telemetry)
        s_low_end, low_end_issues, low_end_recs = self._audit_low_end_control(tracks, telemetry)
        s_spectral, spectral_issues, spectral_recs = self._audit_spectral_balance(tracks, telemetry)
        # Stem separation is never scored: its only checks guess from track names and fader positions, and they
        # are advice-only now, so a score here would be 6 points nobody could lose.
        s_unmasking, unmasking_issues, unmasking_recs = self._audit_stem_separation(tracks, telemetry)
        s_stereo, stereo_issues, stereo_recs = self._audit_stereo_imaging(tracks, telemetry)

        for issues, recs in (
            (dynamic_issues, dynamic_recs),
            (low_end_issues, low_end_recs),
            (spectral_issues, spectral_recs),
            (unmasking_issues, unmasking_recs),
            (stereo_issues, stereo_recs),
        ):
            all_issues.extend(issues)
            remediation_dag.extend(recs)

        dimension_scores = {
            "dynamic_health": s_dynamic,
            "low_end_control": s_low_end,
            "spectral_balance": s_spectral,
            "stem_separation": s_unmasking,
            "stereo_imaging": s_stereo,
        }
        # Move everything from the audits' working scale to report points, so a dimension's score and the points its
        # issues cost add up in the same units.
        to_points = _POINTS_PER_DIMENSION / _WORKING_POINTS
        dimension_scores = {k: None if v is None else v * to_points for k, v in dimension_scores.items()}
        for issue in all_issues:
            issue.points_lost = round(issue.points_lost * to_points, 2)
            # Anything without a recognised source is judgement; an unexplained threshold never reads as better.
            issue.tier = _TIER_BY_SOURCE.get(issue.source, "judgement")

        scored = [v for v in dimension_scores.values() if v is not None]
        points_available = _POINTS_PER_DIMENSION * len(scored)
        total_mqm = max(0.0, min(points_available, sum(scored)))
        # With fewer than five dimensions measured we report the points available and say so in `meaning`; the score
        # is never rescaled up (3 of 5 dimensions kept at 16.5 of 18 is not 27.5 of 30).
        meaning = self._meaning(total_mqm, points_available, len(scored), len(dimension_scores), all_issues)
        critical_issues = [i for i in all_issues if i.severity in ("CRITICAL", "WARNING")]

        report = MixAuditReport(
            mqm_score=total_mqm,
            meaning=meaning,
            dimension_scores=dimension_scores,
            critical_issues=critical_issues,
            all_issues=all_issues,
            remediation_dag=remediation_dag,
            loudness_telemetry=telemetry,
            points_available=points_available,
            unmeasured=sorted(k for k, v in telemetry.items() if v is None),
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
    ) -> Dict[str, Optional[float]]:
        """Normalise the meter readings; a reading the meter did not give stays None, never a stand-in value."""
        m = meters or {}

        def reading(source: Dict[str, Any], *keys: str) -> Optional[float]:
            for key in keys:
                value = source.get(key)
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    # Absent, null or not a number: treat it as not measured and try the next alias.
                    continue
                if math.isfinite(number):
                    return number
            return None

        spectral = m.get("spectral_energy")
        spectral = spectral if isinstance(spectral, dict) else {}

        return {
            "integrated_lufs": reading(m, "integrated_lufs", "lufs"),
            "true_peak_dbtp": reading(m, "true_peak_dbtp", "peak_dbfs"),
            "phase_correlation": reading(m, "phase_correlation", "correlation"),
            "crest_factor_db": reading(m, "crest_factor_db", "crest_db"),
            "sub_energy": reading(spectral, "sub_20_60hz"),
            "low_mid_energy": reading(spectral, "low_mid_200_500hz"),
            "high_mid_energy": reading(spectral, "high_mid_2_6khz"),
            "air_energy": reading(spectral, "air_10_20khz"),
        }

    def _audit_dynamic_health(
        self,
        tracks: List[Dict[str, Any]],
        master: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
    ) -> Tuple[Optional[float], List[MixIssue], List[Dict[str, Any]]]:
        """Audit Dynamic Health & Crest Factor (Max 20 pts). Scores None when there is no true-peak reading."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        tp = telemetry["true_peak_dbtp"]
        lufs = telemetry["integrated_lufs"]
        # Peak-to-loudness needs both readings. It used to fall back to 10 dB when LUFS was missing or
        # positive, which read as a healthy ratio; now we skip the check instead.
        plr = abs(tp - lufs) if tp is not None and lufs is not None and lufs < 0 else None

        # Check Intersample Peak (ISP) / True Peak clipping
        if tp is None:
            pass
        elif tp > -0.2:
            cost = 10.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=SPOTIFY_PEAK_RULE,
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
            cost = 3.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=SPOTIFY_PEAK_RULE,
                severity="ADVISORY",
                category="dynamic",
                message=f"True Peak is near threshold ({tp:+.1f} dBTP). Recommended ceiling is -1.0 dBTP for streaming delivery.",
            ))

        # Check Track Volume fader clipping
        for t in tracks:
            vol = _number(t.get("volume"))
            idx = int(t.get("index", 0))
            name = str(t.get("name", f"Track {idx}"))
            # No fader reading means no verdict on this track. The old 0.85 default also fed the kick/bass and
            # vocal/synth collision checks, so a snapshot without volumes could be docked for collisions.
            if vol is not None and vol > 1.0:
                # Advice only, no points: a fader above unity is a gain choice, and without a meter on that
                # track we cannot say it clips (summing headroom is what the master true-peak reading judges).
                excess_db = 20.0 * math.log10(vol) if vol > 0 else 0.0
                issues.append(MixIssue(
                    source=HOUSE_RULE,
                    severity="ADVISORY",
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
        if plr is None:
            pass
        elif plr < 6.0:
            cost = 6.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
                severity="WARNING",
                category="dynamic",
                message=f"Mix is hyper-compressed (PLR {plr:.1f} dB). Transients are squashed; consider easing master bus threshold or ratio.",
            ))
        elif plr > 16.0 and tp < -6.0:
            cost = 3.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
                severity="ADVISORY",
                category="dynamic",
                message=f"Mix has wide crest factor (PLR {plr:.1f} dB) with quiet master peak ({tp:+.1f} dBTP). Headroom is available for makeup gain.",
            ))

        # Only the true-peak check judges anything a meter measured; without it the faders alone are not a grade.
        return (max(0.0, score) if tp is not None else None), issues, recs

    def _audit_low_end_control(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
    ) -> Tuple[Optional[float], List[MixIssue], List[Dict[str, Any]]]:
        """Audit Low-End Control & Sub Phase (Max 20 pts). Scores None when there is no sub-band reading."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        sub_energy = telemetry["sub_energy"]
        # Excessive sub energy
        if sub_energy is not None and sub_energy > 0.45:
            cost = 5.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
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
            # Snapshots that omit the device list tell us nothing; the old code read that as "no EQ" and docked 1.5 pts.
            if not isinstance(t.get("devices"), list):
                continue
            devices = [str(d.get("name", "")).lower() for d in t["devices"] if isinstance(d, dict)]
            has_eq = any("eq" in d or "filter" in d for d in devices)

            if is_non_bass and not has_eq:
                # Advice only, no points: the verdict rests on a track name and a device name, and plenty of
                # tracks (a pad, a sub-heavy FX hit) are meant to carry low end. The low-end meter judges it.
                issues.append(MixIssue(
                    source=HOUSE_RULE,
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

        return (max(0.0, score) if sub_energy is not None else None), issues, recs

    def _audit_spectral_balance(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
    ) -> Tuple[Optional[float], List[MixIssue], List[Dict[str, Any]]]:
        """Audit Spectral Balance & Mud Accumulation (Max 20 pts). Scores None when no band was measured."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        low_mid = telemetry["low_mid_energy"]
        high_mid = telemetry["high_mid_energy"]
        air = telemetry["air_energy"]

        # 200-500 Hz Boxiness / Mud accumulation
        if low_mid is not None and low_mid > 0.38:
            cost = 6.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
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
        if high_mid is not None and high_mid > 0.40:
            cost = 5.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
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
        if air is not None and air < 0.10:
            cost = 3.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
                severity="ADVISORY",
                category="spectral",
                message=f"Air band (>10 kHz) is dark ({air:.0%}). Consider gentle high shelf boost (+1.5 dB at 12 kHz) on vocals or drum bus.",
            ))

        measured = any(band is not None for band in (low_mid, high_mid, air))
        return (max(0.0, score) if measured else None), issues, recs

    def _audit_stem_separation(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
    ) -> Tuple[Optional[float], List[MixIssue], List[Dict[str, Any]]]:
        """Flag likely stem collisions from names and faders. Advice only: always returns an unscored (None) dimension."""
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        # Find Kick and Bass tracks
        kick_track = next((t for t in tracks if "kick" in str(t.get("name", "")).lower()), None)
        bass_track = next((t for t in tracks if any(b in str(t.get("name", "")).lower() for b in ["bass", "sub", "808"])), None)

        if kick_track and bass_track:
            kick_vol = _number(kick_track.get("volume"))
            bass_vol = _number(bass_track.get("volume"))
            if kick_vol is not None and bass_vol is not None and kick_vol > 0.80 and bass_vol > 0.80:
                # Advice only, no points: two high faders say nothing about whether the kick and bass collide,
                # since the faders ignore each track's own level, EQ and sidechain. Names pick the tracks too.
                issues.append(MixIssue(
                    source=HOUSE_RULE,
                    severity="ADVISORY",
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
            v_vol = _number(vocal_track.get("volume"))
            m_vol = _number(mid_track.get("volume"))
            if v_vol is not None and m_vol is not None and v_vol > 0.80 and m_vol > 0.80:
                # Advice only, no points, for the same reason as the kick/bass check above.
                issues.append(MixIssue(
                    source=HOUSE_RULE,
                    severity="ADVISORY",
                    category="unmasking",
                    track_name=f"{vocal_track.get('name')} & {mid_track.get('name')}",
                    message=f"Midrange competition between '{vocal_track.get('name')}' and '{mid_track.get('name')}'. Consider a subtle 1-2 kHz pocket.",
                ))

        # None, not full marks: nothing above can cost points, and a dimension that cannot lose would hand out its 6
        # points for free. Measured masking (core/stem_unmasking.py) can score this dimension once it is wired in.
        return None, issues, recs

    def _audit_stereo_imaging(
        self,
        tracks: List[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
    ) -> Tuple[Optional[float], List[MixIssue], List[Dict[str, Any]]]:
        """Audit Stereo Imaging & Mono Compatibility (Max 20 pts). Scores None when there is no correlation reading."""
        score = 20.0
        issues: List[MixIssue] = []
        recs: List[Dict[str, Any]] = []

        corr = telemetry["phase_correlation"]

        if corr is None:
            pass
        elif corr < 0.0:
            cost = 15.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=CORRELATION_SIGN_RULE,
                severity="CRITICAL",
                category="stereo",
                message=f"Destructive out-of-phase audio detected on master bus (correlation {corr:+.2f} < 0.0). Mix will cancel out in mono.",
                remediation_proposal={
                    "action": "narrow_stereo_field",
                    "rationale": "Inspect stereo wideners and out-of-phase stereo delays; narrow sub and mid width to restore mono summing compatibility.",
                }
            ))
        elif corr < 0.25:
            cost = 8.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
                severity="WARNING",
                category="stereo",
                message=f"Weak phase correlation ({corr:+.2f}). Mix is at risk of comb-filtering when played on phones or club mono systems.",
            ))
        elif corr < 0.50:
            cost = 3.0
            score -= cost
            issues.append(MixIssue(
                points_lost=cost,
                source=HOUSE_RULE,
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
                # Advice only, no points: a hard-panned bass or vocal is sometimes the idea (double-tracked
                # parts, a wide sub layer), and we only know the track from its name.
                issues.append(MixIssue(
                    source=HOUSE_RULE,
                    severity="ADVISORY",
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

        return (max(0.0, score) if corr is not None else None), issues, recs

    @staticmethod
    def _meaning(points: float, available: float, scored: int, total: int, issues: List[MixIssue]) -> str:
        """One line on what the number covers, so a partial or house-rule-heavy score cannot read as a full one."""
        text = f"{points:.1f} of {available:.0f} technical-health points kept"
        if scored < total:
            text += f"; only {scored} of {total} checks had a meter reading, the rest are not counted"
        costly = [i for i in issues if i.points_lost > 0]
        if costly:
            published = sum(1 for i in costly if i.tier == "published")
            text += f"; {len(costly)} deductions, {published} resting on a published source"
        return text + "."


def _number(value: Any) -> Optional[float]:
    """A finite float, or None for anything a snapshot left out or filled with junk."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        # Missing or non-numeric fader value: the caller skips the check instead of assuming a level.
        return None
    return number if math.isfinite(number) else None


# Singleton instance
_mix_doctor = MixDoctor()


def get_mix_doctor() -> MixDoctor:
    """Return the global MixDoctor instance."""
    return _mix_doctor
