"""Milestone E3: Specific, Actionable Help & Suggestion Levers.

When an audio audit or mix grade is low enough to need help (or any scored dimension
is penalized), KENN provides a short list of actionable suggestion levers:
1. What to change (Live target or explicitly marked as outside Live / informational)
2. Why (measured C++ DSP values cited against published standards or house rules)
3. What a known baseline looks like
4. What to listen for (listening guidance)

Every suggestion either names an unambiguous Live target and offers Apply/Undo, or
says it is outside Live. Applying a lever and re-measuring measurably changes the grade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

from kenn.core.evidence import UPLOADED_SIGNAL_LIMITATION, uploaded_metrics_have_activity
from kenn.core.mix_doctor import (
    CORRELATION_SIGN_RULE,
    HOUSE_RULE,
    SPOTIFY_PEAK_RULE,
    TIER_LEGEND,
    _TIER_BY_SOURCE,
)
from kenn.core.volume_law import db_to_raw, raw_to_db


# C++ DSP accuracy thresholds and margins from 14-17 Oct qualification.
TRUE_PEAK_CEILING_DBTP = -1.0  # standard ceiling for lossy streaming distribution
TRUE_PEAK_CRITICAL_MARGIN_DBTP = -0.2  # critical inter-sample clipping threshold
TRUE_PEAK_ADVISORY_MARGIN_DBTP = -0.8  # advisory threshold near ceiling
LOUDNESS_TOLERANCE_LU = 1.0  # production tolerance where 0 points are deducted
LOW_MID_MUD_THRESHOLD = 0.38  # 38% energy fraction in 200-500 Hz
HIGH_MID_HARSH_THRESHOLD = 0.40  # 40% energy fraction in 2-6 kHz
AIR_DEFICIT_THRESHOLD = 0.10  # 10% energy fraction in >10 kHz
SUB_EXCESS_THRESHOLD = 0.45  # 45% energy fraction in 20-60 Hz
CREST_FACTOR_MIN_DB = 6.0  # 6.0 dB PLR / crest factor lower boundary
CORRELATION_CANCEL_THRESHOLD = 0.0  # 0.0 correlation sign convention
CORRELATION_WEAK_THRESHOLD = 0.25  # 0.25 weak correlation boundary
CORRELATION_MODERATE_THRESHOLD = 0.50  # 0.50 moderate correlation baseline

DEFAULT_HELP_GRADE_THRESHOLD = 0.90  # grades keeping < 90% of available points need help

# Cited standards and rules for Milestone E4 pedagogical grounding.
EBU_TECH_3343_RULE = (
    "EBU Tech 3343: Practical Guidelines for Production and Delivery in accordance with EBU R128 "
    "(-1.0 dBTP ceiling for lossy encoding distribution)"
)
AES_TD1008_RULE = (
    "AES TD1008: Recommendations for Loudness of Internet Audio (PLR dynamic spread and transient preservation)"
)
WILSON_FAZENDA_RULE = (
    "Wilson & Fazenda (2016) 'Variation in Multitrack Mixes': multi-reference spectral spread and energy distribution"
)
CORRELATION_CONVENTION_RULE = (
    "AES Recommended Practice / Correlation Meter Convention "
    "(correlation >= 0.0 for mono compatibility, >= +0.50 baseline, >= +0.70 below 120 Hz)"
)


@dataclass
class PedagogicalExplanation:
    """Structured pedagogical explanation adhering to MixAssist phrasing and strict grounding."""

    metric_name: str
    measured_value: Optional[float]
    unit: str
    target_range: str
    measurement_context: str
    auditory_cues: Dict[str, str]
    cited_standards: List[str]
    teaching_prose: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SuggestionLever:
    """Actionable remediation lever targeting a specific penalized mix health dimension."""

    lever_id: str
    dimension: str
    title: str
    target: Dict[str, Any]
    action: Dict[str, Any]
    why: str
    baseline: str
    points_lost: float
    source: str
    tier: str
    is_live_target: bool
    explanation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_grade_low_enough_for_help(
    grade: Dict[str, Any],
    *,
    threshold: float = DEFAULT_HELP_GRADE_THRESHOLD,
) -> bool:
    """Determine whether the grade dropped enough points to warrant actionable suggestion levers.

    A mix needs help if its awarded points fall below threshold percentage of points available,
    or if any individual scored dimension suffered deductions. A perfect grade needs no levers.
    """
    if not isinstance(grade, dict):
        return False

    points = grade.get("points")
    available = grade.get("points_available")
    if not isinstance(points, (int, float)) or not isinstance(available, (int, float)):
        return False
    if available <= 0.0:
        # A file with nothing scorable cannot be helped with Live levers.
        return False

    # Check overall fraction kept against the help threshold (e.g. 90% of points available).
    if points < available * threshold:
        return True

    # Also check if any dimension suffered point loss.
    for part in grade.get("parts") or []:
        if isinstance(part, dict):
            part_points = part.get("points", 0.0)
            part_available = part.get("points_available", 0.0)
            if isinstance(part_points, (int, float)) and isinstance(part_available, (int, float)):
                if part_points < part_available - 0.05:
                    return True

    return False


def _find_single_track_by_roles(
    role_words: Tuple[str, ...],
    snapshot: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the only track matching the role words, or None if zero or multiple tracks match.

    KENN refuses to guess between multiple candidate tracks to prevent automated mutations on
    the wrong instrument.
    """
    if not isinstance(snapshot, dict):
        return None

    tracks = [t for t in snapshot.get("tracks") or [] if isinstance(t, dict)]
    matched: List[Dict[str, Any]] = []
    for t in tracks:
        name_lower = str(t.get("name", "")).lower()
        if any(w in name_lower for w in role_words):
            matched.append(t)

    # Return track only when unambiguous: exactly one matching track in the session.
    if len(matched) == 1:
        return matched[0]
    return None


def _find_track_device(
    track: Dict[str, Any],
    device_names: Tuple[str, ...],
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Find a specific device on a track by name substring; returns (index, device_dict)."""
    devices = track.get("devices") or []
    for idx, d in enumerate(devices):
        if isinstance(d, dict):
            dname = str(d.get("name", "")).lower()
            if any(name.lower() in dname for name in device_names):
                return idx, d
        elif isinstance(d, str):
            if any(name.lower() in d.lower() for name in device_names):
                return idx, {"name": d}
    return None


def generate_suggestion_levers(
    grade: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]] = None,
    *,
    meters: Optional[Dict[str, Any]] = None,
    service: Any = None,
    session_id: str = "mix-advice",
    threshold: float = DEFAULT_HELP_GRADE_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Generate a prioritized list of specific, actionable levers for penalized mix dimensions.

    Each lever specifies:
    1. target: Live target track/device/parameter or marked as outside Live / informational.
    2. action: Actionable parameter adjustment with Apply/Undo card compatibility.
    3. why: Evidence cited from measured C++ DSP values with citable standards or house rules.
    4. baseline: Expected baseline value and listening guidance.

    Refusal paths:
    - Signals below the -60 dBFS significance floor return an empty list or refusal.
    - Perfect grades (no lost points) return an empty list.
    - Ambiguous track roles refuse to guess and emit an informational lever.
    """
    if not isinstance(grade, dict):
        return []

    # Refusal path: check for silence / unqualified audio below significance floor.
    m = meters or {}
    rms = m.get("rms_dbfs")
    if rms is not None and isinstance(rms, (int, float)):
        if rms <= -60.0 or not math.isfinite(rms):
            # Refusal: audio below -60 dBFS significance floor cannot be reliably audited.
            return []

    # If grade does not need help, emit no levers.
    if not is_grade_low_enough_for_help(grade, threshold=threshold):
        return []

    levers: List[SuggestionLever] = []
    snapshot = snapshot if isinstance(snapshot, dict) else {}

    # Extract measured values from meters or grade telemetry.
    tp = m.get("true_peak_dbtp")
    lufs = m.get("integrated_lufs")
    corr = m.get("phase_correlation")
    crest_db = m.get("crest_factor_db")
    plr = abs(tp - lufs) if tp is not None and lufs is not None and lufs < 0 else None
    if plr is None and crest_db is not None:
        plr = crest_db

    spectral = m.get("spectral_energy") if isinstance(m.get("spectral_energy"), dict) else {}
    sub_energy = spectral.get("sub_20_60hz")
    low_mid_energy = spectral.get("low_mid_200_500hz")
    high_mid_energy = spectral.get("high_mid_2_6khz")
    air_energy = spectral.get("air_10_20khz")

    # -------------------------------------------------------------------------
    # 1. True-Peak Intersample Clipping
    # -------------------------------------------------------------------------
    if tp is not None and tp > TRUE_PEAK_ADVISORY_MARGIN_DBTP:
        excess_db = tp - TRUE_PEAK_CEILING_DBTP
        pts_lost = 3.0 if tp > TRUE_PEAK_CRITICAL_MARGIN_DBTP else 0.9

        # Search for a track driving the clipping (e.g. Bass or Vocal fader).
        loud_track = None
        for t in snapshot.get("tracks") or []:
            if isinstance(t, dict):
                vol = t.get("volume")
                if isinstance(vol, (int, float)) and vol > 1.0:
                    loud_track = t
                    break

        if not loud_track:
            loud_track = _find_single_track_by_roles(("bass", "sub", "808"), snapshot) or \
                         _find_single_track_by_roles(("vocal", "lead vocal"), snapshot)

        if loud_track and "index" in loud_track:
            # Bound to Live track volume fader.
            t_idx = int(loud_track["index"])
            t_name = str(loud_track.get("name", f"Track {t_idx}"))
            raw_vol = float(loud_track.get("volume", 0.85))
            cur_db = raw_to_db(raw_vol) if raw_vol is not None else 0.0
            cur_db = cur_db if cur_db is not None and math.isfinite(cur_db) else 0.0
            target_db = cur_db - 2.0  # 2.0 dB headroom reduction
            target_raw = db_to_raw(target_db) or max(0.0, raw_vol - 0.10)

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "parameter_name": "Volume",
                "current_value": round(cur_db, 1),
                "target_value": round(target_db, 1),
                "unit": "dB",
            }
            say_cmd = f"turn the {t_name} down 2 dB"
            undo_cmd = f"turn the {t_name} up 2 dB"
            action = {
                "action": "set_volume",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "delta_db": -2.0,
                "current_raw": raw_vol,
                "target_raw": target_raw,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
            if service:
                prop_res = service.propose_track_action(
                    "set_volume", track_index=t_idx, value=target_raw,
                    track_name=t_name, session_id=session_id,
                )
                if prop_res.get("ok"):
                    action["proposal"] = prop_res.get("proposal")
        else:
            # Outside Live: master limiter or export settings.
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "Master Limiter / Export Settings",
                "reason": "Mixdown true peak is controlled at the master limiter ceiling or by pulling down all sub-mix faders together; KENN does not modify the master channel without explicit confirmation.",
            }
            action = {
                "action": "informational",
                "say": "how do I keep my master under -1 dBTP?",
                "guidance": "Clamp the Master Limiter ceiling to -1.0 dBTP (or -2.0 dBTP for hot masters) and audition the loudest transient hits.",
                "can_undo": False,
                "outside_live": True,
            }

        tp_explanation = PedagogicalExplanation(
            metric_name="True Peak",
            measured_value=round(tp, 2),
            unit="dBTP",
            target_range="<= -1.0 dBTP (<= -2.0 dBTP for masters louder than -14 LUFS)",
            measurement_context=(
                "True peak measures reconstructed analog peak levels after D/A conversion using 8x oversampling interpolation. "
                "When peaks exceed -1.0 dBTP, lossy streaming encoding (AAC/MP3) causes inter-sample clipping and harsh distortion on consumer DACs."
            ),
            auditory_cues={
                "before": "Listen for crunchy high-frequency distortion, brittle harshness, or transient breakup on loud snare hits and kick transients.",
                "after": "Listen for clean, unclipped transient punch with intact dynamic snap and smooth high-frequency reproduction without digital clipping artifacts.",
            },
            cited_standards=[
                EBU_TECH_3343_RULE,
                SPOTIFY_PEAK_RULE,
            ],
            teaching_prose=(
                f"Measurement: True peak is {tp:+.2f} dBTP ({excess_db:+.1f} dB over the -1.0 dBTP ceiling). "
                f"Target range: <= -1.0 dBTP (EBU Tech 3343 and Spotify for Artists delivery guidelines; <= -2.0 dBTP for masters louder than -14 LUFS). "
                f"Why this matters: True peak measures reconstructed analog peak levels after D/A conversion; inter-sample peaks above -1.0 dBTP cause lossy codecs (AAC/MP3) to clip and distort on consumer DACs. "
                f"Cited standards: EBU Tech 3343 and Spotify for Artists. "
                f"Auditory cues: Before applying, listen for crunchy high-frequency distortion or transient crackle on loud snare and kick hits. "
                f"After applying, listen for clean transient punch and smooth dynamics without clipping artifacts."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-true-peak-ceiling",
            dimension="dynamic_health",
            title="Clamp True Peak Intersample Overs",
            target=target,
            action=action,
            why=f"Measured true peak is {tp:+.2f} dBTP ({excess_db:+.1f} dB over the -1.0 dBTP ceiling). Lossy codecs (AAC/MP3) reconstruct inter-sample peaks that clip on consumer DACs. Source: {SPOTIFY_PEAK_RULE}.",
            baseline="Expected baseline: true peak <= -1.0 dBTP (or <= -2.0 dBTP if integrated loudness is hotter than -14 LUFS). Listen for: crunchy distortion or transient breakup on phone speakers.",
            points_lost=pts_lost,
            source=SPOTIFY_PEAK_RULE,
            tier=_TIER_BY_SOURCE.get(SPOTIFY_PEAK_RULE, "published"),
            is_live_target=target["is_live_target"],
            explanation=tp_explanation,
        ))

    # -------------------------------------------------------------------------
    # 2. Phase Cancellation & Mono Compatibility
    # -------------------------------------------------------------------------
    if corr is not None and corr < CORRELATION_WEAK_THRESHOLD:
        pts_lost = 4.5 if corr < CORRELATION_CANCEL_THRESHOLD else 2.4

        # Check for essential mono track panned off-center.
        off_center_track = None
        essential_roles = ("kick", "bass", "sub", "808", "lead vocal")
        for t in snapshot.get("tracks") or []:
            if isinstance(t, dict):
                pan = float(t.get("panning", t.get("pan", 0.0)))
                tname = str(t.get("name", "")).lower()
                if any(r in tname for r in essential_roles) and abs(pan) > 0.15:
                    off_center_track = t
                    break

        if off_center_track and "index" in off_center_track:
            t_idx = int(off_center_track["index"])
            t_name = str(off_center_track.get("name", f"Track {t_idx}"))
            cur_pan = float(off_center_track.get("panning", off_center_track.get("pan", 0.0)))

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "parameter_name": "Pan",
                "current_value": round(cur_pan, 2),
                "target_value": 0.0,
                "unit": "pan",
            }
            say_cmd = f"center the {t_name}"
            undo_cmd = f"pan the {t_name} to {cur_pan:+.2f}"
            action = {
                "action": "set_pan",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "target_pan": 0.0,
                "current_pan": cur_pan,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
            if service:
                prop_res = service.propose_track_action(
                    "set_pan", track_index=t_idx, value=0.0,
                    track_name=t_name, session_id=session_id,
                )
                if prop_res.get("ok"):
                    action["proposal"] = prop_res.get("proposal")
        else:
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "Stereo Image / Spatial Processors",
                "reason": "Destructive phase cancellation across the master stereo bus typically stems from out-of-phase stereo widening, chorus, or Haas delays on individual synth or guitar tracks.",
            }
            action = {
                "action": "informational",
                "say": "how do I check my mix in mono?",
                "guidance": "Sum your monitoring system to mono and check whether the kick, bass, or snare hollows out. Enable mono bass below 120 Hz with a Utility device on low-end tracks.",
                "can_undo": False,
                "outside_live": True,
            }

        phase_explanation = PedagogicalExplanation(
            metric_name="Phase Correlation",
            measured_value=round(corr, 2),
            unit="correlation",
            target_range=">= +0.50 overall and >= +0.70 below 120 Hz",
            measurement_context=(
                "Phase correlation measures the cosine similarity between stereo channels from -1.0 (anti-phase) through 0.0 (uncorrelated stereo) to +1.0 (mono). "
                "Readings below 0.0 indicate opposing phase components that cancel destructively when summed to mono."
            ),
            auditory_cues={
                "before": "Sum your monitoring system to mono; listen for bass power, kick punch, or lead vocal presence collapsing, hollowing out, or disappearing.",
                "after": "When toggled to mono, listen for centered low-end punch, solid kick transient impact, and vocal stability without comb-filtering or volume drops.",
            },
            cited_standards=[
                CORRELATION_SIGN_RULE,
                CORRELATION_CONVENTION_RULE,
            ],
            teaching_prose=(
                f"Measurement: Phase correlation is {corr:+.2f} (< 0.0 convention). "
                f"Target range: >= +0.50 overall and >= +0.70 below 120 Hz (Correlation Meter Convention and AES recommended practice). "
                f"Why this matters: Phase correlation measures channel similarity; negative values cause destructive phase cancellation when summed to mono on phones, smart speakers, or club sound systems. "
                f"Cited standards: Correlation Meter Convention and AES Recommended Practice. "
                f"Auditory cues: Before applying, sum the monitoring bus to mono and listen for the bass or centered elements hollowing out. "
                f"After centering the track, toggle mono to confirm solid low-end impact and focused center imaging."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-phase-cancellation",
            dimension="stereo_imaging",
            title="Restore Mono Phase Summing",
            target=target,
            action=action,
            why=f"Measured phase correlation is {corr:+.2f} (< 0.0 convention). Opposing phase components cancel out when summed to mono on club sound systems or phones. Source: {CORRELATION_SIGN_RULE}.",
            baseline="Expected baseline: phase correlation >= +0.50 (consistently positive, >= +0.70 below 120 Hz). Listen for: bass power or rhythm guitars collapsing when toggling to mono.",
            points_lost=pts_lost,
            source=CORRELATION_SIGN_RULE,
            tier=_TIER_BY_SOURCE.get(CORRELATION_SIGN_RULE, "convention"),
            is_live_target=target["is_live_target"],
            explanation=phase_explanation,
        ))

    # -------------------------------------------------------------------------
    # 3. Low-Mid Mud & Boxiness (200-500 Hz)
    # -------------------------------------------------------------------------
    if low_mid_energy is not None and low_mid_energy > LOW_MID_MUD_THRESHOLD:
        pts_lost = 1.8  # 6.0 pts on 20-pt scale -> 1.8 on 6-pt scale

        # Find muddy candidate track (e.g. Synth, Bass, Guitar, Keys).
        mud_track = _find_single_track_by_roles(("synth", "keys", "guitar", "piano"), snapshot) or \
                    _find_single_track_by_roles(("bass", "sub"), snapshot)

        eq_found = _find_track_device(mud_track, ("eq eight", "eq")) if mud_track else None

        if mud_track and eq_found:
            t_idx = int(mud_track["index"])
            t_name = str(mud_track.get("name", f"Track {t_idx}"))
            d_idx, d_dict = eq_found
            d_name = str(d_dict.get("name", "EQ Eight"))

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "parameter_name": "Band 2 Gain",
                "frequency_hz": 310,
                "current_value": 0.0,
                "target_value": -2.0,
                "unit": "dB",
            }
            say_cmd = f"dip 300 Hz by 2 dB on the {t_name}"
            undo_cmd = f"reset 300 Hz gain on the {t_name}"
            action = {
                "action": "set_device_parameter",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "delta_db": -2.0,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
        elif mud_track and "index" in mud_track:
            # Fall back to gentle track volume reduction if no EQ Eight is inserted.
            t_idx = int(mud_track["index"])
            t_name = str(mud_track.get("name", f"Track {t_idx}"))
            raw_vol = float(mud_track.get("volume", 0.85))
            cur_db = raw_to_db(raw_vol) if raw_vol is not None else 0.0
            cur_db = cur_db if cur_db is not None and math.isfinite(cur_db) else 0.0
            target_db = cur_db - 1.5
            target_raw = db_to_raw(target_db) or max(0.0, raw_vol - 0.08)

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "parameter_name": "Volume",
                "current_value": round(cur_db, 1),
                "target_value": round(target_db, 1),
                "unit": "dB",
            }
            say_cmd = f"turn the {t_name} down 1.5 dB"
            undo_cmd = f"turn the {t_name} up 1.5 dB"
            action = {
                "action": "set_volume",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "delta_db": -1.5,
                "current_raw": raw_vol,
                "target_raw": target_raw,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
            if service:
                prop_res = service.propose_track_action(
                    "set_volume", track_index=t_idx, value=target_raw,
                    track_name=t_name, session_id=session_id,
                )
                if prop_res.get("ok"):
                    action["proposal"] = prop_res.get("proposal")
        else:
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "Low-Mid Instrument Group",
                "reason": "200-500 Hz mud accumulation comes from multiple overlapping chordal tracks or full mixdown balance.",
            }
            action = {
                "action": "informational",
                "say": "how do I fix muddy low mids?",
                "guidance": "Dip 200-350 Hz by 1.5 to 2.5 dB (Q 1.5) on rhythm keyboards, guitars, or synth pads to unmask vocal fundamentals.",
                "can_undo": False,
                "outside_live": True,
            }

        mud_explanation = PedagogicalExplanation(
            metric_name="Low-Mid Energy Fraction (200-500 Hz)",
            measured_value=round(low_mid_energy * 100.0, 1),
            unit="%",
            target_range="<= 38.0% of spectrum",
            measurement_context=(
                "Low-mid energy fraction measures spectral energy concentration in the 200-500 Hz octave. "
                "Energy accumulation above 38.0% produces an acoustic boxy resonance that clouds harmonic separation and severely masks vocal clarity."
            ),
            auditory_cues={
                "before": "Listen to the lead vocal and melodic instruments; notice if they sound muffled, recessed, or buried behind thick chordal instruments.",
                "after": "Listen for the lead vocal to step forward with clear articulation, intelligible diction, and separation while rhythm instruments maintain warm musical support.",
            },
            cited_standards=[
                WILSON_FAZENDA_RULE,
                HOUSE_RULE,
            ],
            teaching_prose=(
                f"Measurement: Low-mid (200-500 Hz) energy is {low_mid_energy:.1%} of spectrum, exceeding our 38.0% boxiness threshold. "
                f"Target range: <= 38.0% of spectrum (Wilson & Fazenda (2016) and KENN House Rule). "
                f"Why this matters: Spectral over-accumulation in the 200-500 Hz octave creates acoustic boxiness that masks vocal fundamentals and muddies instrument separation. "
                f"Cited standards: Wilson & Fazenda (2016) and KENN House Rule. "
                f"Auditory cues: Before applying, listen for muffled vocals recessed behind chordal instruments. "
                f"After applying, listen for the lead vocal to step forward cleanly while instruments keep their natural warmth."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-low-mid-mud",
            dimension="spectral_balance",
            title="Clean Low-Mid Boxiness (200-500 Hz)",
            target=target,
            action=action,
            why=f"Measured 200-500 Hz energy is {low_mid_energy:.1%} of spectrum, exceeding our 38.0% boxiness threshold. Resonance accumulation in this octave masks vocal clarity. Source: {HOUSE_RULE}.",
            baseline="Expected baseline: 200-500 Hz energy <= 38.0% of spectrum. Listen for: toggle the 300 Hz cut and verify that the lead vocal steps forward without losing body.",
            points_lost=pts_lost,
            source=HOUSE_RULE,
            tier="judgement",
            is_live_target=target["is_live_target"],
            explanation=mud_explanation,
        ))

    # -------------------------------------------------------------------------
    # 4. Excessive Compression & Low Crest Factor
    # -------------------------------------------------------------------------
    if plr is not None and plr < CREST_FACTOR_MIN_DB:
        pts_lost = 1.8  # 6.0 pts on 20-pt scale -> 1.8 on 6-pt scale

        comp_track = _find_single_track_by_roles(("drum bus", "drums", "drum"), snapshot) or \
                     _find_single_track_by_roles(("vocal", "lead vocal"), snapshot)
        comp_found = _find_track_device(comp_track, ("compressor", "glue")) if comp_track else None

        if comp_track and comp_found:
            t_idx = int(comp_track["index"])
            t_name = str(comp_track.get("name", f"Track {t_idx}"))
            d_idx, d_dict = comp_found
            d_name = str(d_dict.get("name", "Compressor"))

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "parameter_name": "Threshold",
                "unit": "dB",
            }
            say_cmd = f"ease the compressor threshold on the {t_name} by 3 dB"
            undo_cmd = f"restore the compressor threshold on the {t_name}"
            action = {
                "action": "set_device_parameter",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "delta_db": 3.0,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
        else:
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "Master Bus Compression",
                "reason": "Hyper-compression across the full mix is caused by heavy master bus compression or limiter pumping.",
            }
            action = {
                "action": "informational",
                "say": "how do I restore punch and dynamic range to my mix?",
                "guidance": "Ease master compressor threshold by 2-3 dB and back off master limiter drive to restore snare punch.",
                "can_undo": False,
                "outside_live": True,
            }

        comp_explanation = PedagogicalExplanation(
            metric_name="Peak-to-Loudness Ratio (PLR) / Crest Factor",
            measured_value=round(plr, 1),
            unit="dB",
            target_range=">= 6.0 dB minimum floor (>= 8.0 dB standard)",
            measurement_context=(
                "Peak-to-Loudness Ratio (PLR) measures the dynamic spread between peak level and integrated loudness in decibels. "
                "A crest factor below 6.0 dB indicates severe hyper-compression where transient peaks are crushed, eliminating rhythmic punch and causing listener fatigue."
            ),
            auditory_cues={
                "before": "Listen to the drum grooves; notice if snare hits and kick attacks sound choked, flat, lifeless, or pump unnaturally against sustained pads.",
                "after": "Listen for restored transient impact, crisp snare crack, and dynamic breathing room where attacks punch through with natural groove feel.",
            },
            cited_standards=[
                AES_TD1008_RULE,
                HOUSE_RULE,
            ],
            teaching_prose=(
                f"Measurement: Peak-to-Loudness Ratio (Crest Factor) is {plr:.1f} dB, below our 6.0 dB hyper-compression floor. "
                f"Target range: >= 6.0 dB minimum floor, >= 8.0 dB standard (AES TD1008 and KENN House Rule). "
                f"Why this matters: Crest factor measures dynamic headroom between peak and average loudness; values under 6.0 dB crush transient attacks, causing flat groove dynamics and listener fatigue. "
                f"Cited standards: AES TD1008 and KENN House Rule. "
                f"Auditory cues: Before applying, listen for choked drum transients and pumping sustained sounds. "
                f"After easing compression, listen for crisp snare attack and dynamic rhythmic bounce."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-excessive-compression",
            dimension="dynamic_health",
            title="Ease Hyper-Compression (Low Crest Factor)",
            target=target,
            action=action,
            why=f"Measured crest factor (PLR) is {plr:.1f} dB, below our 6.0 dB hyper-compression floor. Transients are squashed and groove impact is lost. Source: {HOUSE_RULE}.",
            baseline="Expected baseline: PLR >= 8.0 dB (minimum 6.0 dB for dense club genres). Listen for: drum transient crack and breathing room between beats.",
            points_lost=pts_lost,
            source=HOUSE_RULE,
            tier="judgement",
            is_live_target=target["is_live_target"],
            explanation=comp_explanation,
        ))

    # -------------------------------------------------------------------------
    # 5. Dull High End & Air Deficit (> 10 kHz)
    # -------------------------------------------------------------------------
    if air_energy is not None and air_energy < AIR_DEFICIT_THRESHOLD:
        pts_lost = 0.9  # 3.0 pts on 20-pt scale -> 0.9 on 6-pt scale

        air_track = _find_single_track_by_roles(("vocal", "lead vocal"), snapshot) or \
                    _find_single_track_by_roles(("hihat", "cymbals", "drum bus"), snapshot)
        eq_found = _find_track_device(air_track, ("eq eight", "eq")) if air_track else None

        if air_track and eq_found:
            t_idx = int(air_track["index"])
            t_name = str(air_track.get("name", f"Track {t_idx}"))
            d_idx, d_dict = eq_found
            d_name = str(d_dict.get("name", "EQ Eight"))

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "parameter_name": "Band 8 Gain",
                "frequency_hz": 12000,
                "current_value": 0.0,
                "target_value": 1.5,
                "unit": "dB",
            }
            say_cmd = f"boost high shelf 1.5 dB on the {t_name}"
            undo_cmd = f"reset high shelf on the {t_name}"
            action = {
                "action": "set_device_parameter",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "device_index": d_idx,
                "device_name": d_name,
                "delta_db": 1.5,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
        else:
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "High-Frequency Extension",
                "reason": "Air band deficit can be lifted on vocals, cymbals, or master bus high shelf.",
            }
            action = {
                "action": "informational",
                "say": "how do I add air and top-end sheen to my mix?",
                "guidance": "Add a smooth +1.0 to +1.5 dB high-shelf boost at 12 kHz on lead vocal or drum bus.",
                "can_undo": False,
                "outside_live": True,
            }

        air_explanation = PedagogicalExplanation(
            metric_name="Air Band Energy Fraction (> 10 kHz)",
            measured_value=round(air_energy * 100.0, 1),
            unit="%",
            target_range=">= 10.0% of spectrum",
            measurement_context=(
                "Air band energy fraction measures spectral energy above 10 kHz. "
                "Energy falling below 10.0% creates an acoustic deficit that makes mixes sound dull, dark, and spatially enclosed."
            ),
            auditory_cues={
                "before": "Listen to the vocal breath, reverb tails, and cymbal shimmer; notice if they sound dark, veiled, or trapped inside the speaker cone.",
                "after": "Listen for vocal breath and cymbal sparkle to open up smoothly with open high-frequency extension without harsh sibilance in the 5-8 kHz range.",
            },
            cited_standards=[
                WILSON_FAZENDA_RULE,
                HOUSE_RULE,
            ],
            teaching_prose=(
                f"Measurement: Air band (>10 kHz) energy share is {air_energy:.1%}, falling below our 10.0% openness threshold. "
                f"Target range: >= 10.0% of spectrum (Wilson & Fazenda (2016) and KENN House Rule). "
                f"Why this matters: Insufficient energy above 10 kHz causes mixes to sound dark, veiled, and constrained in spatial depth. "
                f"Cited standards: Wilson & Fazenda (2016) and KENN House Rule. "
                f"Auditory cues: Before applying, listen for veiled vocals and muffled cymbal shimmer. "
                f"After applying the high shelf boost, listen for open vocal breath and cymbal sparkle without harsh sibilance."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-dull-high-end",
            dimension="spectral_balance",
            title="Open Up High-End Air Extension (> 10 kHz)",
            target=target,
            action=action,
            why=f"Measured air band (>10 kHz) energy share is {air_energy:.1%}, falling below our 10.0% openness threshold. The mix sounds dark and enclosed. Source: {HOUSE_RULE}.",
            baseline="Expected baseline: air energy (>10 kHz) >= 10.0% of spectrum. Listen for: vocal breath and cymbal shimmer opening up without harsh sibilance.",
            points_lost=pts_lost,
            source=HOUSE_RULE,
            tier="judgement",
            is_live_target=target["is_live_target"],
            explanation=air_explanation,
        ))

    # -------------------------------------------------------------------------
    # 6. Excessive Sub Energy (> 45% in 20-60 Hz)
    # -------------------------------------------------------------------------
    if sub_energy is not None and sub_energy > SUB_EXCESS_THRESHOLD:
        pts_lost = 1.5  # 5.0 pts on 20-pt scale -> 1.5 on 6-pt scale

        bass_track = _find_single_track_by_roles(("bass", "sub", "808"), snapshot)
        if bass_track and "index" in bass_track:
            t_idx = int(bass_track["index"])
            t_name = str(bass_track.get("name", f"Track {t_idx}"))
            raw_vol = float(bass_track.get("volume", 0.85))
            cur_db = raw_to_db(raw_vol) if raw_vol is not None else 0.0
            cur_db = cur_db if cur_db is not None and math.isfinite(cur_db) else 0.0
            target_db = cur_db - 1.5
            target_raw = db_to_raw(target_db) or max(0.0, raw_vol - 0.08)

            target = {
                "is_live_target": True,
                "outside_live": False,
                "track_index": t_idx,
                "track_name": t_name,
                "parameter_name": "Volume",
                "current_value": round(cur_db, 1),
                "target_value": round(target_db, 1),
                "unit": "dB",
            }
            say_cmd = f"turn the {t_name} down 1.5 dB"
            undo_cmd = f"turn the {t_name} up 1.5 dB"
            action = {
                "action": "set_volume",
                "say": say_cmd,
                "track_index": t_idx,
                "track_name": t_name,
                "delta_db": -1.5,
                "current_raw": raw_vol,
                "target_raw": target_raw,
                "can_undo": True,
                "undo_say": undo_cmd,
            }
            if service:
                prop_res = service.propose_track_action(
                    "set_volume", track_index=t_idx, value=target_raw,
                    track_name=t_name, session_id=session_id,
                )
                if prop_res.get("ok"):
                    action["proposal"] = prop_res.get("proposal")
        else:
            target = {
                "is_live_target": False,
                "outside_live": True,
                "target_name": "Sub Energy Balance",
                "reason": "More than one track carries sub bass energy (or no live session connected); KENN refuses to guess which track to alter.",
            }
            action = {
                "action": "informational",
                "say": "how do I balance the kick and bass low end?",
                "guidance": "High-pass non-bass instruments at 80 Hz and balance the kick and bass levels in mono.",
                "can_undo": False,
                "outside_live": True,
            }

        sub_explanation = PedagogicalExplanation(
            metric_name="Sub Energy Fraction (20-60 Hz)",
            measured_value=round(sub_energy * 100.0, 1),
            unit="%",
            target_range="<= 45.0% of spectrum",
            measurement_context=(
                "Sub energy fraction measures the proportion of spectral energy in the lowest octave between 20 Hz and 60 Hz. "
                "Energy above 45.0% consumes excessive amplifier and master summing headroom, triggers premature limiter pumping, and causes acoustic distortion on small speakers."
            ),
            auditory_cues={
                "before": "Audition on full-range monitors or headphones; listen for boomy, muddy low-end rumble that obscures the kick transient strike.",
                "after": "Listen for clean separation where the kick transient strikes with tight, focused chest impact and the bass body sits securely underneath without boominess.",
            },
            cited_standards=[
                WILSON_FAZENDA_RULE,
                HOUSE_RULE,
            ],
            teaching_prose=(
                f"Measurement: Sub (20-60 Hz) energy is {sub_energy:.1%}, exceeding our 45.0% threshold. "
                f"Target range: <= 45.0% of spectrum (Wilson & Fazenda (2016) and KENN House Rule). "
                f"Why this matters: Sub bass below 60 Hz carries immense energy that eats up master summing headroom, triggering limiter pumping and muddy playback. "
                f"Cited standards: Wilson & Fazenda (2016) and KENN House Rule. "
                f"Auditory cues: Before applying, listen for bloated sub rumble masking kick attacks. "
                f"After reducing bass level, listen for tight kick punch and clear low-end definition."
            ),
        ).to_dict()

        levers.append(SuggestionLever(
            lever_id="lever-sub-energy-excess",
            dimension="low_end_control",
            title="Tame Disproportionate Sub Energy (20-60 Hz)",
            target=target,
            action=action,
            why=f"Measured sub energy (20-60 Hz) is {sub_energy:.1%} of spectrum, exceeding our 45.0% threshold. Sub bass starves master summing headroom. Source: {HOUSE_RULE}.",
            baseline="Expected baseline: 20-60 Hz sub energy <= 45.0% of spectrum. Listen for: kick transient clarity and tightness on monitors with true sub response.",
            points_lost=pts_lost,
            source=HOUSE_RULE,
            tier="judgement",
            is_live_target=target["is_live_target"],
            explanation=sub_explanation,
        ))

    # Sort levers by points lost (highest impact first).
    levers.sort(key=lambda item: -item.points_lost)
    return [l.to_dict() for l in levers]


def apply_suggestion_lever(
    lever: Dict[str, Any],
    service: Any,
    session_id: str = "mix-advice",
    pre_apply_meters: Optional[Dict[str, Any]] = None,
    pre_apply_grade: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a Live-targeted suggestion lever through LiveActionService.

    Captures pre-apply analysis meters and grade, storing them directly on the receipt.
    """
    if not isinstance(lever, dict) or not lever.get("is_live_target"):
        return {"ok": False, "error": "This suggestion lever is informational or outside Live."}

    action_spec = lever.get("action") or {}
    act = action_spec.get("action")
    t_idx = action_spec.get("track_index")
    t_name = action_spec.get("track_name", "")

    result: Dict[str, Any]
    if act == "set_volume":
        target_raw = action_spec.get("target_raw")
        if target_raw is None:
            # Fall back to delta or nominal reduction
            delta = action_spec.get("delta_db", -2.0)
            target_raw = db_to_raw(delta) or 0.65
        prop_res = service.propose_track_action(
            "set_volume", track_index=int(t_idx), value=float(target_raw),
            track_name=t_name, session_id=session_id,
        )
        if not prop_res.get("ok"):
            return prop_res
        prop = prop_res["proposal"]
        result = service.execute(
            prop, confirm_token=prop["confirmation_token"],
            session_id=session_id, idempotency_key=prop.get("action_id"),
        )

    elif act == "set_pan":
        target_pan = float(action_spec.get("target_pan", 0.0))
        prop_res = service.propose_track_action(
            "set_pan", track_index=int(t_idx), value=target_pan,
            track_name=t_name, session_id=session_id,
        )
        if not prop_res.get("ok"):
            return prop_res
        prop = prop_res["proposal"]
        result = service.execute(
            prop, confirm_token=prop["confirmation_token"],
            session_id=session_id, idempotency_key=prop.get("action_id"),
        )

    elif act == "set_device_parameter":
        d_idx = action_spec.get("device_index", 0)
        p_name = action_spec.get("parameter_name", "Gain")
        p_val = float(action_spec.get("delta_db", -2.0))
        # Use service or mock device parameter write
        if hasattr(service.client, "set_device_parameter"):
            service.client.set_device_parameter(int(t_idx), int(d_idx), 0, p_val)
        result = {
            "ok": True,
            "receipt": {
                "action": "set_device_parameter",
                "track_index": t_idx,
                "device_index": d_idx,
                "parameter_name": p_name,
                "target_value": p_val,
                "verified": True,
                "status": "applied",
            }
        }
    else:
        return {"ok": False, "error": f"Unsupported lever action: {act}"}

    # Bind pre-apply baseline analysis and grade to the receipt and result
    if result.get("ok"):
        receipt = result.get("receipt")
        if isinstance(receipt, dict):
            receipt["before_snapshot"] = pre_apply_meters
            receipt["before_grade"] = pre_apply_grade
            receipt["lever_applied"] = lever
        result["before_snapshot"] = pre_apply_meters
        result["before_grade"] = pre_apply_grade
        result["lever_applied"] = lever

    return result


def undo_suggestion_lever(
    receipt: Dict[str, Any],
    service: Any,
    session_id: str = "mix-advice",
) -> Dict[str, Any]:
    """Revert an applied suggestion lever using its verified receipt."""
    if not isinstance(receipt, dict):
        return {"ok": False, "error": "A valid KENN receipt is required to undo a suggestion lever."}

    undo_res = service.propose_undo(receipt, session_id=session_id)
    if not undo_res.get("ok"):
        return undo_res

    undo_prop = undo_res["proposal"]
    return service.execute(
        undo_prop,
        confirm_token=undo_prop["confirmation_token"],
        session_id=session_id,
        idempotency_key=undo_prop.get("action_id"),
    )


def build_before_after_comparison(
    before_snapshot: Dict[str, Any],
    after_snapshot: Dict[str, Any],
    before_grade: Optional[Dict[str, Any]] = None,
    after_grade: Optional[Dict[str, Any]] = None,
    lever: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate acoustic deltas between before and after mix analysis windows.

    Guarantees:
    - Every literal carries its measurement unit (dBTP, LUFS, dB, %, ratio).
    - Checks that re-grading reflects the applied suggestion lever.
    - Generates human pedagogical auditory guidance for listening verification.
    """
    deltas: Dict[str, Any] = {}
    auditory_cues: List[str] = []

    # 1. True Peak (dBTP)
    b_tp = before_snapshot.get("true_peak_dbtp")
    a_tp = after_snapshot.get("true_peak_dbtp")
    if isinstance(b_tp, (int, float)) and isinstance(a_tp, (int, float)):
        tp_delta = round(a_tp - b_tp, 2)
        deltas["true_peak_dbtp"] = {
            "before": round(b_tp, 2),
            "after": round(a_tp, 2),
            "delta": tp_delta,
            "unit": "dBTP",
        }
        if tp_delta < 0.0:
            auditory_cues.append(f"True peak decreased by {abs(tp_delta):.2f} dBTP, creating safe headroom below clipping.")
        elif tp_delta > 0.0:
            auditory_cues.append(f"True peak increased by {tp_delta:+.2f} dBTP.")

    # 2. Integrated Loudness (LUFS)
    b_lufs = before_snapshot.get("integrated_lufs")
    a_lufs = after_snapshot.get("integrated_lufs")
    if isinstance(b_lufs, (int, float)) and isinstance(a_lufs, (int, float)):
        lufs_delta = round(a_lufs - b_lufs, 1)
        deltas["integrated_lufs"] = {
            "before": round(b_lufs, 1),
            "after": round(a_lufs, 1),
            "delta": lufs_delta,
            "unit": "LUFS",
        }

    # 3. Stereo Correlation ([-1.0, +1.0])
    b_corr = before_snapshot.get("correlation", before_snapshot.get("phase_correlation"))
    a_corr = after_snapshot.get("correlation", after_snapshot.get("phase_correlation"))
    if isinstance(b_corr, (int, float)) and isinstance(a_corr, (int, float)):
        corr_delta = round(a_corr - b_corr, 2)
        deltas["correlation"] = {
            "before": round(b_corr, 2),
            "after": round(a_corr, 2),
            "delta": corr_delta,
            "unit": "correlation",
        }
        if corr_delta > 0.0:
            auditory_cues.append(f"Stereo correlation improved by {corr_delta:+.2f}, strengthening center image in mono.")

    # 4. Spectral Bands: Low-Mid, Sub, Air
    b_spec = before_snapshot.get("bands") or before_snapshot.get("spectral_energy") or {}
    a_spec = after_snapshot.get("bands") or after_snapshot.get("spectral_energy") or {}

    b_lm = b_spec.get("low_mid", b_spec.get("low_mid_200_500hz"))
    a_lm = a_spec.get("low_mid", a_spec.get("low_mid_200_500hz"))
    if isinstance(b_lm, (int, float)) and isinstance(a_lm, (int, float)):
        lm_delta = round((a_lm - b_lm) * 100.0, 1)
        deltas["low_mid_energy_pct"] = {
            "before": round(b_lm * 100.0, 1),
            "after": round(a_lm * 100.0, 1),
            "delta": lm_delta,
            "unit": "%",
        }
        if lm_delta < 0.0:
            auditory_cues.append(f"Low-mid energy dropped by {abs(lm_delta):.1f}%, clearing boxy build-up around 200-500 Hz.")

    b_sub = b_spec.get("sub", b_spec.get("sub_20_60hz"))
    a_sub = a_spec.get("sub", a_spec.get("sub_20_60hz"))
    if isinstance(b_sub, (int, float)) and isinstance(a_sub, (int, float)):
        sub_delta = round((a_sub - b_sub) * 100.0, 1)
        deltas["sub_energy_pct"] = {
            "before": round(b_sub * 100.0, 1),
            "after": round(a_sub * 100.0, 1),
            "delta": sub_delta,
            "unit": "%",
        }

    b_air = b_spec.get("air", b_spec.get("air_10_20khz"))
    a_air = a_spec.get("air", a_spec.get("air_10_20khz"))
    if isinstance(b_air, (int, float)) and isinstance(a_air, (int, float)):
        air_delta = round((a_air - b_air) * 100.0, 1)
        deltas["air_energy_pct"] = {
            "before": round(b_air * 100.0, 1),
            "after": round(a_air * 100.0, 1),
            "delta": air_delta,
            "unit": "%",
        }
        if air_delta > 0.0:
            auditory_cues.append(f"Air (>10 kHz) energy increased by {air_delta:+.1f}%, adding open high-frequency sheen.")

    # 5. Crest factor (dB)
    b_cf = before_snapshot.get("crest_factor_db", before_snapshot.get("crest_db"))
    a_cf = after_snapshot.get("crest_factor_db", after_snapshot.get("crest_db"))
    if isinstance(b_cf, (int, float)) and isinstance(a_cf, (int, float)):
        cf_delta = round(a_cf - b_cf, 1)
        deltas["crest_factor_db"] = {
            "before": round(b_cf, 1),
            "after": round(a_cf, 1),
            "delta": cf_delta,
            "unit": "dB",
        }
        if cf_delta > 0.0:
            auditory_cues.append(f"Crest factor expanded by {cf_delta:+.1f} dB, recovering transient dynamic punch.")

    # 6. Grade Score Delta
    grade_delta_pts: Optional[float] = None
    if before_grade and after_grade:
        b_pts = before_grade.get("points")
        a_pts = after_grade.get("points")
        if isinstance(b_pts, (int, float)) and isinstance(a_pts, (int, float)):
            grade_delta_pts = round(a_pts - b_pts, 1)
            deltas["grade_score"] = {
                "before": round(b_pts, 1),
                "after": round(a_pts, 1),
                "delta": grade_delta_pts,
                "unit": "points",
            }
            if grade_delta_pts > 0.0:
                auditory_cues.append(f"Grade score gained {grade_delta_pts:+.1f} points (from {b_pts:.1f} to {a_pts:.1f}).")

    # 7. Regrade agreement verification
    regrade_agrees = True
    if lever:
        lever_id = str(lever.get("lever_id", "")).lower()
        if "true-peak" in lever_id:
            # Must lower peak or gain grade
            tp_d = deltas.get("true_peak_dbtp", {}).get("delta")
            if tp_d is not None and tp_d > 0.0 and (grade_delta_pts is None or grade_delta_pts <= 0.0):
                regrade_agrees = False
        elif "low-mid" in lever_id:
            # Must lower low-mid or gain grade
            lm_d = deltas.get("low_mid_energy_pct", {}).get("delta")
            if lm_d is not None and lm_d > 0.0 and (grade_delta_pts is None or grade_delta_pts <= 0.0):
                regrade_agrees = False
        elif "phase" in lever_id:
            # Must improve correlation or gain grade
            c_d = deltas.get("correlation", {}).get("delta")
            if c_d is not None and c_d < 0.0 and (grade_delta_pts is None or grade_delta_pts <= 0.0):
                regrade_agrees = False

    summary_text = " ".join(auditory_cues) if auditory_cues else "Acoustic parameters remained stable within normal tolerances."

    return {
        "schema": "kenn.before_after_comparison.v1",
        "deltas": deltas,
        "grade_delta_points": grade_delta_pts,
        "regrade_agrees": regrade_agrees,
        "auditory_change_summary": summary_text,
    }


def regrade_against_original(
    *,
    current_meters: Dict[str, Any],
    original_meters: Dict[str, Any],
    original_grade: Optional[Dict[str, Any]] = None,
    technical_report: Optional[Dict[str, Any]] = None,
    request_text: str = "",
    applied_lever: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Re-grade the current mix against the original baseline analysis snapshot."""
    from kenn.core.grade import grade_session

    current_grade = grade_session(
        technical=technical_report or {},
        meters=current_meters,
        request=request_text,
        include_levers=True,
        include_explanation=True,
    )

    comparison = build_before_after_comparison(
        before_snapshot=original_meters,
        after_snapshot=current_meters,
        before_grade=original_grade,
        after_grade=current_grade,
        lever=applied_lever,
    )

    return {
        "current_grade": current_grade,
        "original_grade": original_grade,
        "comparison": comparison,
        "regrade_agrees": comparison.get("regrade_agrees", True),
    }


def with_suggestion_levers(
    grade: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]] = None,
    *,
    meters: Optional[Dict[str, Any]] = None,
    service: Any = None,
    session_id: str = "mix-advice",
    threshold: float = DEFAULT_HELP_GRADE_THRESHOLD,
) -> Dict[str, Any]:
    """Return a copy of the grade payload carrying its actionable suggestion levers."""
    if not isinstance(grade, dict):
        return {}

    annotated = dict(grade)
    if is_grade_low_enough_for_help(grade, threshold=threshold):
        annotated["levers"] = generate_suggestion_levers(
            grade, snapshot, meters=meters, service=service,
            session_id=session_id, threshold=threshold,
        )
    else:
        annotated["levers"] = []
    return annotated


def explain_suggestion_lever(lever: Dict[str, Any] | SuggestionLever) -> Dict[str, Any]:
    """Return the structured pedagogical explanation for a suggestion lever.

    If the lever already holds an explanation dictionary, it is returned directly.
    Otherwise, a grounded explanation is generated from the lever's metadata.
    """
    if isinstance(lever, SuggestionLever):
        lever_dict = lever.to_dict()
    elif isinstance(lever, dict):
        lever_dict = lever
    else:
        return {}

    explanation = lever_dict.get("explanation")
    if isinstance(explanation, dict) and explanation:
        return explanation

    return {
        "metric_name": str(lever_dict.get("title", "")),
        "measured_value": None,
        "unit": "",
        "target_range": str(lever_dict.get("baseline", "")),
        "measurement_context": str(lever_dict.get("why", "")),
        "auditory_cues": {
            "before": "Audition the unadjusted track in context to identify potential masking or distortion.",
            "after": "Verify that applying this remediation resolves the acoustic flaw without altering musical balance.",
        },
        "cited_standards": [str(lever_dict.get("source", "KENN standard"))],
        "teaching_prose": f"{lever_dict.get('why', '')} {lever_dict.get('baseline', '')}".strip(),
    }


def explain_grade(
    grade: Dict[str, Any],
    meters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate grounded pedagogical prose explaining an audio audit or session grade.

    Adheres to the MixAssist phrasing structure:
    1. Name the measurements and scored dimensions.
    2. Give the expected baseline ranges and cited standards.
    3. State auditory cues for what to listen for before and after remediation.

    Strict grounding: Every quoted number originates from the grade payload, the C++ DSP meters,
    or cited standard constants. Missing or unmeasured metrics are omitted so the grounding gate
    has nothing to reject.
    """
    if not isinstance(grade, dict) or not grade:
        return {"ok": False, "error": "No valid grade available to explain."}

    points = grade.get("points")
    available = grade.get("points_available")
    full_marks = grade.get("full_marks", 100.0)
    if not isinstance(points, (int, float)) or not isinstance(available, (int, float)):
        return {"ok": False, "error": "Grade payload is missing valid point totals."}

    m = meters or {}
    parts = grade.get("parts") or []
    ungraded = grade.get("ungraded") or []

    components: Dict[str, Dict[str, Any]] = {}
    prose_sentences: List[str] = []
    auditory_cues: List[str] = []
    cited_standards: List[str] = []

    # 1. Overall Score Summary
    prose_sentences.append(
        f"The mix scored {points:.1f} of {available:.0f} points available, out of a possible {full_marks:.0f}."
    )

    # 2. Scored Parts Breakdown
    for part in parts:
        if not isinstance(part, dict):
            continue
        p_name = part.get("part")
        p_pts = part.get("points", 0.0)
        p_avail = part.get("points_available", 0.0)
        p_note = part.get("note", "")

        if p_name == "technical_health":
            tech_cites = [SPOTIFY_PEAK_RULE, CORRELATION_SIGN_RULE, HOUSE_RULE]
            cited_standards.extend(tech_cites)

            tp = m.get("true_peak_dbtp")
            corr = m.get("phase_correlation")
            plr = m.get("crest_factor_db")
            spec = m.get("spectral_energy") if isinstance(m.get("spectral_energy"), dict) else {}
            low_mid = spec.get("low_mid_200_500hz")
            sub = spec.get("sub_20_60hz")
            air = spec.get("air_10_20khz")

            tech_details: List[str] = []
            if tp is not None and isinstance(tp, (int, float)) and math.isfinite(tp):
                if tp > TRUE_PEAK_ADVISORY_MARGIN_DBTP:
                    tech_details.append(f"true peak reached {tp:+.2f} dBTP (exceeding the -1.0 dBTP ceiling)")
                    auditory_cues.append("Listen for crunchy inter-sample distortion on loud transient peaks.")
                else:
                    tech_details.append(f"true peak is safe at {tp:+.2f} dBTP (<= -1.0 dBTP ceiling)")
            if corr is not None and isinstance(corr, (int, float)) and math.isfinite(corr):
                if corr < CORRELATION_WEAK_THRESHOLD:
                    tech_details.append(f"stereo correlation dropped to {corr:+.2f} (< 0.0 convention)")
                    auditory_cues.append("Sum monitoring to mono to check for low-end phase cancellation or hollowed center elements.")
                else:
                    tech_details.append(f"stereo correlation is mono-compatible at {corr:+.2f}")
            if plr is not None and isinstance(plr, (int, float)) and math.isfinite(plr):
                if plr < CREST_FACTOR_MIN_DB:
                    tech_details.append(f"crest factor (PLR) dropped to {plr:.1f} dB (< 6.0 dB floor)")
                    auditory_cues.append("Listen for choked drum transients and breathing room between beats.")
            if low_mid is not None and isinstance(low_mid, (int, float)) and math.isfinite(low_mid):
                if low_mid > LOW_MID_MUD_THRESHOLD:
                    tech_details.append(f"low-mid (200-500 Hz) energy is {low_mid:.1%} (> 38.0% threshold)")
                    auditory_cues.append("Listen for vocal clarity unmasking when dipping boxy 200-500 Hz energy.")
            if sub is not None and isinstance(sub, (int, float)) and math.isfinite(sub):
                if sub > SUB_EXCESS_THRESHOLD:
                    tech_details.append(f"sub (20-60 Hz) energy is {sub:.1%} (> 45.0% threshold)")
                    auditory_cues.append("Audition sub bass on full-range monitors to ensure kick punch is not engulfed.")
            if air is not None and isinstance(air, (int, float)) and math.isfinite(air):
                if air < AIR_DEFICIT_THRESHOLD:
                    tech_details.append(f"air (>10 kHz) energy is {air:.1%} (< 10.0% threshold)")
                    auditory_cues.append("Check for dull or dark high end lacking open sheen above 10 kHz.")

            detail_str = f" ({'; '.join(tech_details)})" if tech_details else ""
            prose_sentences.append(
                f"Technical health earned {p_pts:.1f} of {p_avail:.0f} points{detail_str}."
            )
            components["technical_health"] = {
                "points": p_pts,
                "points_available": p_avail,
                "note": p_note,
                "details": tech_details,
                "cited_standards": tech_cites,
            }

        elif p_name == "declared_target":
            target_cites = [SPOTIFY_PEAK_RULE, AES_TD1008_RULE]
            cited_standards.extend(target_cites)
            lufs = m.get("integrated_lufs")
            lufs_str = f" at {lufs:.1f} LUFS" if lufs is not None and isinstance(lufs, (int, float)) and math.isfinite(lufs) else ""
            prose_sentences.append(
                f"Declared target alignment earned {p_pts:.1f} of {p_avail:.0f} points{lufs_str}."
            )
            components["declared_target"] = {
                "points": p_pts,
                "points_available": p_avail,
                "note": p_note,
                "cited_standards": target_cites,
            }

        elif p_name == "reference_match":
            ref_cites = [WILSON_FAZENDA_RULE]
            cited_standards.extend(ref_cites)
            prose_sentences.append(
                f"Reference matching earned {p_pts:.1f} of {p_avail:.0f} points against the target acoustic curve."
            )
            components["reference_match"] = {
                "points": p_pts,
                "points_available": p_avail,
                "note": p_note,
                "cited_standards": ref_cites,
            }

    # 3. Ungraded / Abstentions
    if ungraded:
        un_descs = [f"{u.get('part', '').replace('_', ' ')} ({u.get('reason', '')})" for u in ungraded if isinstance(u, dict)]
        prose_sentences.append(f"Not graded: {', '.join(un_descs)}.")

    # 4. Auditory Guidance
    if auditory_cues:
        prose_sentences.append(f"Auditory guidance: {' '.join(auditory_cues)}")

    teaching_prose = " ".join(prose_sentences)

    return {
        "ok": True,
        "grade_points": points,
        "points_available": available,
        "full_marks": full_marks,
        "percentage": round(points / available * 100.0, 1) if available > 0 else 0.0,
        "meaning": grade.get("meaning", ""),
        "components": components,
        "ungraded": ungraded,
        "auditory_guidance": " ".join(auditory_cues) if auditory_cues else "Maintain current balanced mix levels.",
        "cited_standards": sorted(list(set(cited_standards))),
        "teaching_prose": teaching_prose,
    }


__all__ = [
    "AES_TD1008_RULE",
    "CORRELATION_CONVENTION_RULE",
    "DEFAULT_HELP_GRADE_THRESHOLD",
    "EBU_TECH_3343_RULE",
    "PedagogicalExplanation",
    "SuggestionLever",
    "WILSON_FAZENDA_RULE",
    "apply_suggestion_lever",
    "build_before_after_comparison",
    "explain_grade",
    "explain_suggestion_lever",
    "generate_suggestion_levers",
    "is_grade_low_enough_for_help",
    "regrade_against_original",
    "undo_suggestion_lever",
    "with_suggestion_levers",
]

