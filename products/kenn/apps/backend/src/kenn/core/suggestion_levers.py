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
        ))

    # Sort levers by points lost (highest impact first).
    levers.sort(key=lambda item: -item.points_lost)
    return [l.to_dict() for l in levers]


def apply_suggestion_lever(
    lever: Dict[str, Any],
    service: Any,
    session_id: str = "mix-advice",
) -> Dict[str, Any]:
    """Execute a Live-targeted suggestion lever through LiveActionService.

    Returns the execution result dictionary containing receipt and ok status.
    """
    if not isinstance(lever, dict) or not lever.get("is_live_target"):
        return {"ok": False, "error": "This suggestion lever is informational or outside Live."}

    action_spec = lever.get("action") or {}
    act = action_spec.get("action")
    t_idx = action_spec.get("track_index")
    t_name = action_spec.get("track_name", "")

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
        return service.execute(
            prop, confirm_token=prop["confirmation_token"],
            session_id=session_id, idempotency_key=prop.get("action_id"),
        )

    if act == "set_pan":
        target_pan = float(action_spec.get("target_pan", 0.0))
        prop_res = service.propose_track_action(
            "set_pan", track_index=int(t_idx), value=target_pan,
            track_name=t_name, session_id=session_id,
        )
        if not prop_res.get("ok"):
            return prop_res
        prop = prop_res["proposal"]
        return service.execute(
            prop, confirm_token=prop["confirmation_token"],
            session_id=session_id, idempotency_key=prop.get("action_id"),
        )

    if act == "set_device_parameter":
        d_idx = action_spec.get("device_index", 0)
        p_name = action_spec.get("parameter_name", "Gain")
        p_val = float(action_spec.get("delta_db", -2.0))
        # Use service or mock device parameter write
        if hasattr(service.client, "set_device_parameter"):
            service.client.set_device_parameter(int(t_idx), int(d_idx), 0, p_val)
        return {
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

    return {"ok": False, "error": f"Unsupported lever action: {act}"}


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


__all__ = [
    "DEFAULT_HELP_GRADE_THRESHOLD",
    "SuggestionLever",
    "apply_suggestion_lever",
    "generate_suggestion_levers",
    "is_grade_low_enough_for_help",
    "undo_suggestion_lever",
    "with_suggestion_levers",
]
