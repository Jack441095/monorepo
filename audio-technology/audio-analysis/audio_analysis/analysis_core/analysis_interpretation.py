from __future__ import annotations

from typing import Callable
import json
import os
import sys

# Ensure parent directory is in path for imports if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio_analysis.analysis_core.fletcher_munson_advice import fm_mix_critique, fm_frequency_repair_map


_mix_critique_provider = None


def set_mix_critique_provider(provider) -> None:
    """Inject an optional application-owned LLM adapter without importing KENN here."""
    global _mix_critique_provider
    _mix_critique_provider = provider


def metric_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


LESSON_LIBRARY = {
    "Low headroom": {
        "meaning": "The file peaks close to full scale, leaving little room for mastering or downstream encoding.",
        "listen_for": "Loud sections that feel strained, crunchy, or harder rather than simply louder.",
        "common_causes": ["Master fader pushed too high", "Limiter ceiling too close to 0 dBFS", "Loud bus saturation after gain staging"],
        "first_fixes": ["Lower the mix bus or limiter output", "Find the loudest section first", "Aim for safer premaster peaks before mastering"],
    },
    "Clipping risk": {
        "meaning": "Sample or true peaks are at or near full scale, so distortion or inter-sample clipping is possible.",
        "listen_for": "Crackles, flattened transients, harsh cymbals, or kick/snare hits that lose shape.",
        "common_causes": ["Limiter driven too hard", "Clippers stacked across buses", "Individual channels clipping before the master"],
        "first_fixes": ["Bypass loudness processors one by one", "Trim clipped channels before plugins", "Re-export with more peak margin"],
    },
    "Low dynamics": {
        "meaning": "Peak level and average level are close together, which can make the mix feel flat or over-controlled.",
        "listen_for": "Drums that do not jump, choruses that do not lift, or a mix that feels loud but small.",
        "common_causes": ["Heavy bus compression", "Limiter doing too much work", "Parallel compression blended too high"],
        "first_fixes": ["Back off master limiting", "Reduce bus compressor gain reduction", "Level-match before deciding if quieter is worse"],
    },
    "Low-mid build-up": {
        "meaning": "The 150-400 Hz area is prominent, which can make the mix feel cloudy or boxy.",
        "listen_for": "Muddy vocal body, cloudy guitars/keys, or reverbs that blur the groove.",
        "common_causes": ["Layered instruments sharing the same body range", "Reverb returns not high-passed", "Too much warmth added on buses"],
        "first_fixes": ["Check dense sources around 150-400 Hz", "High-pass reverbs where appropriate", "Cut before boosting brightness"],
    },
    "Heavy sub": {
        "meaning": "Sub energy is strong compared with the rest of the spectrum.",
        "listen_for": "Bass that disappears on small speakers or overwhelms headphones/car systems.",
        "common_causes": ["Kick and bass fighting below 80 Hz", "Sub layers too loud", "Low-frequency effects left unchecked"],
        "first_fixes": ["Solo kick and bass together", "Check low end in mono", "Use a reference at matched loudness"],
    },
    "Low presence": {
        "meaning": "The 2-6 kHz clarity range is low, so lead elements may feel distant.",
        "listen_for": "Vocals, snares, or leads that sit behind the track even when turned up.",
        "common_causes": ["Too much low-mid energy", "Dark source tone", "Reverb/delay masking the dry signal"],
        "first_fixes": ["Clean masking before boosting", "Try small presence moves on lead elements", "Check against a reference quietly"],
    },
    "Perceived harshness": {
        "meaning": "Ear-weighted presence energy is prominent, so the mix may feel sharp at normal volume.",
        "listen_for": "Painful S sounds, cymbals, distortion, or synth edges around normal listening level.",
        "common_causes": ["Sibilance after compression", "Bright saturation", "Stacked boosts around 2-6 kHz"],
        "first_fixes": ["Use dynamic EQ/de-essing on harsh moments", "Avoid broad cuts before finding the source", "Check headphones and small speakers"],
    },
    "Mono risk": {
        "meaning": "Low correlation suggests some stereo content may weaken or disappear in mono.",
        "listen_for": "Bass, snare, vocal, or lead sounds thinning out when summed to mono.",
        "common_causes": ["Phasey wideners", "Unaligned stereo layers", "Low-end stereo effects"],
        "first_fixes": ["Fold down to mono", "Reduce wideners on important centre elements", "Keep low end more mono"],
    },
    "Low-end heavy balance": {
        "meaning": "The broad tonal profile is dominated by sub and bass energy.",
        "listen_for": "A mix that feels powerful but dull, crowded, or hard to turn up.",
        "common_causes": ["Kick/bass too loud", "Low-frequency layers stacking", "Trying to add weight after the balance is already dense"],
        "first_fixes": ["Level-match against a reference", "Balance kick and bass before EQ", "Avoid adding top end to compensate for too much low end"],
    },
    "Dark tonal balance": {
        "meaning": "Presence and air are low in the broad tonal profile.",
        "listen_for": "Vocals, snares, cymbals, or leads lacking clarity or front edge.",
        "common_causes": ["Low mids masking clarity", "Dark source choices", "Too much tape/filter tone on buses"],
        "first_fixes": ["Remove masking first", "Add presence to the source that needs it", "Avoid a global high shelf until the balance is clean"],
    },
    "Spiky transients": {
        "meaning": "Peak events sit well above the loud sections, which can limit loudness or feel uncontrolled.",
        "listen_for": "Occasional hits jumping out more than the groove warrants.",
        "common_causes": ["Uncontrolled drum peaks", "Clip gain jumps", "Limiter reacting to isolated hits"],
        "first_fixes": ["Clip-gain only the worst hits", "Try light clipping before limiting", "Do not crush the whole mix for one transient"],
    },
    "Uneven loudness": {
        "meaning": "Section-to-section level movement is large.",
        "listen_for": "Verses, drops, or choruses that force the listener to adjust volume.",
        "common_causes": ["Automation not balanced", "Arrangement density changes", "Uncontrolled effects or fills"],
        "first_fixes": ["Use clip gain or automation before bus compression", "Compare section loudness at matched monitoring level", "Re-export and check the version delta"],
    },
    "Over-compressed (LRA)": {
        "meaning": "Loudness Range (LRA) is very low, meaning there is almost no level variation across the track.",
        "listen_for": "A mix that feels static, flat, or exhausting to listen to for more than a minute.",
        "common_causes": ["Heavy bus or master compression", "Brickwall limiter working too hard", "No dynamic contrast between sections"],
        "first_fixes": ["Back off master compression and limiting", "Restore verse-to-chorus level contrast", "Level-match and compare: does quieter actually sound worse?"],
    },
    "Very dynamic": {
        "meaning": "Loudness Range (LRA) is very high, meaning the track has extreme level variation.",
        "listen_for": "Quiet passages that disappear in noisy environments, or loud passages that shock the listener.",
        "common_causes": ["No bus compression at all", "Large arrangement density changes without gain riding", "Classical or cinematic source material"],
        "first_fixes": ["Add gentle bus compression (2:1, slow attack)", "Automate vocal and lead levels to stay present", "Consider the playback context: streaming normalisation will affect this"],
    },
    "Loudness spike": {
        "meaning": "A brief moment in the track is dramatically louder than the overall average.",
        "listen_for": "A single hit, crash, vocal entry, or drop that jumps out aggressively.",
        "common_causes": ["Uncompressed transient hitting the limiter", "Vocal entry without clip gain", "Effects tail or reverb burst"],
        "first_fixes": ["Clip-gain the offending moment down", "Use a fast peak limiter on that channel", "Check if the spike is musically intentional before removing it"],
    },
    "Harsh digital clipping": {
        "meaning": "Odd harmonic distortion is high, indicating hard digital clipping or severe saturation.",
        "listen_for": "Harsh, buzzy, metallic fizz, particularly on vocal peaks, snare hits, or master transients.",
        "common_causes": ["Converter clipping (clipping raw converter inputs)", "Digital limiters/clippers driven past their ceiling", "Poorly designed saturation plugins"],
        "first_fixes": ["Back off the output level of preceding digital plugins", "Reduce master limiter/clipper drive", "Ensure peak levels do not exceed 0 dBFS"],
    },
    "Analog warmth": {
        "meaning": "Moderate even harmonic distortion with low odd harmonics, creating musical depth and saturation.",
        "listen_for": "Pleasant thickness, smooth low-mids, and cohesive warmth that binds elements together.",
        "common_causes": ["Quality tape simulation, tube preamps, or analog console emulation plugins", "Carefully set input levels driving saturation stages"],
        "first_fixes": ["Maintain current gain staging", "Avoid pushing saturation further to prevent harsh odd harmonics from creeping in"],
    },
    "Harsh resonance": {
        "meaning": "A sharp, narrow spectral peak is ringing out, causing acoustic fatigue or boxiness.",
        "listen_for": "Metallic whistling, whistling sibilance, room resonances, or narrow hums that stick out on specific notes.",
        "common_causes": ["Uncontrolled acoustic resonances in the recording room", "Instrument body ringing (e.g. snare ring, acoustic guitar resonances)", "Microphone positioning close to reflective surfaces"],
        "first_fixes": ["Apply a narrow dynamic or static notch filter at the identified frequency", "Use a high-Q band cut", "Adjust microphone placement in future recordings"],
    },
    "Inter-sample clipping": {
        "meaning": "Oversampled peaks exceed 0 dBFS, which will cause D/A converter clipping on consumer speakers.",
        "listen_for": "Subtle crackling, loss of space/depth, or high-end graininess when played on consumer D/A systems (phones, Bluetooth speakers).",
        "common_causes": ["Master limiter ceiling set too high (at 0.0 or -0.1 dBFS)", "High-frequency transients overshooting during D/A reconstruction"],
        "first_fixes": ["Lower the master limiter ceiling to -1.0 dBFS (or at least -0.8 dBFS as per streaming standards)", "Engage 'True Peak limiting' on the limiter if available"],
    },
}

DEFAULT_FLAG_THRESHOLDS: dict[str, float] = {
    "peak_max_dbfs": -1.0,
    "true_peak_clip_dbfs": -0.1,
    "crest_min_db": 6.0,
    "low_mids_max": 0.18,
    "sub_max": 0.12,
    "presence_min": 0.08,
    "perceived_presence_max": 0.35,
    "perceived_air_max": 0.22,
    "stereo_balance_max_deviation": 0.2,
    "stereo_correlation_min": 0.2,
    "stereo_width_ratio_max": 0.9,
    "side_sub_max": 0.05,
    "side_bass_max": 0.08,
    "correlation_sub_min": 0.4,
    "correlation_bass_min": 0.4,
    "side_presence_min": 0.015,
    "side_over_air_ratio": 1.0,
    "lufs_max": -12.0,
    "low_end_share_max": 0.55,
    "clarity_share_min": 0.04,
    "clarity_low_end_max": 0.35,
    "section_range_max_db": 12.0,
    "dc_offset_max": 0.02,
    "leading_silence_max_seconds": 2.0,
    "trailing_silence_max_seconds": 4.0,
    "lra_min_lu": 2.0,
    "lra_max_lu": 15.0,
    "loudness_spike_lu": 12.0,
    "thd_max": 0.03,
    "odd_thd_max": 0.015,
    "even_thd_min_warmth": 0.002,
    "even_thd_max_warmth": 0.02,
    "resonance_severity_max_db": 8.0,
    "inter_sample_peak_max_dbfs": 0.0,
}

GOAL_FLAG_OVERRIDES: dict[str, dict[str, float]] = {
    "premaster": {
        "crest_min_db": 6.0,
        "low_mids_max": 0.18,
        "sub_max": 0.12,
        "lra_min_lu": 5.0,
        "lra_max_lu": 18.0,
    },
    "club": {
        "crest_min_db": 3.5,
        "low_mids_max": 0.20,
        "sub_max": 0.18,
        "perceived_presence_max": 0.40,
        "low_end_share_max": 0.62,
        "lufs_max": -9.0,
        "side_sub_max": 0.03,
        "side_bass_max": 0.06,
        "lra_min_lu": 2.0,
        "lra_max_lu": 10.0,
    },
    "pop_vocal": {
        "crest_min_db": 5.5,
        "low_mids_max": 0.22,
        "sub_max": 0.10,
        "perceived_presence_max": 0.38,
        "presence_min": 0.06,
        "lra_min_lu": 2.0,
        "lra_max_lu": 12.0,
    },
    "rap_vocal": {
        "crest_min_db": 4.5,
        "low_mids_max": 0.24,
        "sub_max": 0.14,
        "low_end_share_max": 0.58,
        "lufs_max": -10.0,
    },
    "podcast": {
        "crest_min_db": 8.0,
        "sub_max": 0.06,
        "low_mids_max": 0.16,
        "low_end_share_max": 0.38,
        "section_range_max_db": 8.0,
        "perceived_presence_max": 0.30,
        "lra_min_lu": 2.0,
        "lra_max_lu": 8.0,
    },
    "game_audio": {
        "crest_min_db": 5.0,
        "sub_max": 0.14,
        "section_range_max_db": 10.0,
        "low_mids_max": 0.22,
        "low_end_share_max": 0.55,
        "presence_min": 0.06,
        "perceived_presence_max": 0.38,
        "lufs_max": -14.0,
        "peak_max_dbfs": -1.0,
        "true_peak_clip_dbfs": -1.0,
        "side_sub_max": 0.03,
        "side_bass_max": 0.06,
        "correlation_sub_min": 0.5,
        "correlation_bass_min": 0.5,
    },
    "master": {
        "peak_max_dbfs": -0.3,
        "true_peak_clip_dbfs": -0.3,
        "crest_min_db": 4.0,
        "stereo_correlation_min": 0.1,
        "lufs_max": -8.0,
        "lra_min_lu": 2.0,
        "lra_max_lu": 12.0,
    },
    # --- Additional genre-specific thresholds ---
    "edm": {
        "crest_min_db": 3.5,
        "low_mids_max": 0.16,
        "sub_max": 0.18,
        "perceived_presence_max": 0.42,
        "low_end_share_max": 0.60,
        "lufs_max": -8.0,
        "side_sub_max": 0.03,
        "side_bass_max": 0.06,
        "section_range_max_db": 10.0,
    },
    "acoustic": {
        "crest_min_db": 9.0,
        "low_mids_max": 0.24,
        "sub_max": 0.08,
        "perceived_presence_max": 0.32,
        "perceived_air_max": 0.18,
        "presence_min": 0.10,
        "low_end_share_max": 0.42,
        "lufs_max": -16.0,
        "section_range_max_db": 14.0,
    },
    "rock": {
        "crest_min_db": 5.0,
        "low_mids_max": 0.24,
        "sub_max": 0.14,
        "perceived_presence_max": 0.38,
        "low_end_share_max": 0.52,
        "lufs_max": -10.0,
        "section_range_max_db": 12.0,
    },
    "cinematic": {
        "crest_min_db": 8.0,
        "sub_max": 0.18,
        "low_mids_max": 0.20,
        "perceived_presence_max": 0.28,
        "perceived_air_max": 0.26,
        "low_end_share_max": 0.58,
        "lufs_max": -18.0,
        "section_range_max_db": 16.0,
        "stereo_width_ratio_max": 0.95,
    },
    "lo_fi": {
        "crest_min_db": 4.0,
        "low_mids_max": 0.28,
        "sub_max": 0.16,
        "perceived_presence_max": 0.36,
        "low_end_share_max": 0.56,
        "lufs_max": -12.0,
        "section_range_max_db": 10.0,
    },
    "jazz": {
        "crest_min_db": 10.0,
        "low_mids_max": 0.26,
        "sub_max": 0.08,
        "perceived_presence_max": 0.30,
        "perceived_air_max": 0.16,
        "presence_min": 0.10,
        "low_end_share_max": 0.45,
        "lufs_max": -16.0,
        "section_range_max_db": 14.0,
    },
    "hip_hop": {
        "crest_min_db": 3.0,
        "low_mids_max": 0.20,
        "sub_max": 0.20,
        "perceived_presence_max": 0.40,
        "low_end_share_max": 0.65,
        "lufs_max": -8.0,
        "side_sub_max": 0.02,
        "side_bass_max": 0.04,
        "correlation_sub_min": 0.5,
        "correlation_bass_min": 0.5,
    },
}


def goal_flag_thresholds(metrics: dict) -> dict[str, float]:
    """Return flag thresholds merged with any goal-specific overrides."""
    thresholds = dict(DEFAULT_FLAG_THRESHOLDS)
    mix_goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    goal_key = str(mix_goal.get("key") or "").strip()
    overrides = GOAL_FLAG_OVERRIDES.get(goal_key, {})
    thresholds.update(overrides)
    return thresholds


def review_flags(metrics: dict) -> list[dict]:
    t = goal_flag_thresholds(metrics)
    flags: list[dict] = []
    peak = metric_float(metrics.get("peak_dbfs"), -99)
    crest = metric_float(metrics.get("crest_factor_db"), 0)
    bands = metrics.get("bands") or {}
    perceived = metrics.get("perceptual_bands") or {}
    is_clean_calibration = "calibration-clean" in str(metrics.get("filename", "")).lower()

    side_bands = metrics.get("side_bands") or {}
    mid_bands = metrics.get("mid_bands") or {}
    correlation_bands = metrics.get("correlation_bands") or {}
    lufs = metric_float(metrics.get("integrated_lufs"), -99)
    true_peak = metric_float(metrics.get("true_peak_dbfs"), -99)
    mix_goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    goal_label = str(mix_goal.get("label") or "premaster or mix")

    if peak > t["peak_max_dbfs"]:
        flags.append({"severity": "high", "label": "Low headroom", "detail": f"Peak level is above {t['peak_max_dbfs']:.1f} dBFS."})
    if metrics.get("clipping_risk") or (true_peak > t["true_peak_clip_dbfs"]):
        flags.append({"severity": "high", "label": "Clipping risk", "detail": "True peaks hit or nearly hit full scale, risking inter-sample clipping."})
    if crest < t["crest_min_db"] and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Low dynamics", "detail": f"Crest factor is below {t['crest_min_db']:.1f} dB for a {goal_label}."})
    if bands.get("low_mids", 0) > t["low_mids_max"] and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Low-mid build-up", "detail": "150-400 Hz looks prominent."})
    if bands.get("sub", 0) > t["sub_max"] and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Heavy sub", "detail": "Sub energy is strong compared with the rest of the spectrum."})
    if bands.get("presence", 0) < t["presence_min"] and not is_clean_calibration:
        flags.append({"severity": "low", "label": "Low presence", "detail": "2-6 kHz energy is low, so lead elements may feel distant."})
    if metric_float(perceived.get("presence")) > t["perceived_presence_max"]:
        flags.append({"severity": "medium", "label": "Perceived harshness", "detail": "Ear-weighted presence energy is prominent."})
    if metric_float(perceived.get("air")) > t["perceived_air_max"]:
        flags.append({"severity": "low", "label": "Bright top end", "detail": "Ear-weighted air band is prominent."})
    if abs(metric_float(metrics.get("stereo_balance"), 1.0) - 1.0) > t["stereo_balance_max_deviation"]:
        flags.append({"severity": "medium", "label": "Stereo imbalance", "detail": "Left/right energy is uneven."})
    if metric_float(metrics.get("stereo_correlation"), 1.0) < t["stereo_correlation_min"]:
        flags.append({"severity": "high", "label": "Mono risk", "detail": "Stereo correlation is low; mono playback may lose important elements."})
    if metric_float(metrics.get("stereo_width_ratio")) > t["stereo_width_ratio_max"]:
        flags.append({"severity": "medium", "label": "Very wide sides", "detail": "Side signal is high relative to the mid signal."})

    # --- Top-tier flags ---
    if side_bands.get("sub", 0) > t["side_sub_max"] or side_bands.get("bass", 0) > t["side_bass_max"]:
        flags.append({"severity": "medium", "label": "Side Bass Mud", "detail": "Excessive low frequencies detected in the Side channel. Bass should be in mono."})
    if correlation_bands.get("sub", 1.0) < t["correlation_sub_min"] or correlation_bands.get("bass", 1.0) < t["correlation_bass_min"]:
        flags.append({"severity": "high", "label": "Low-End Phase Cancellation", "detail": "Sub/Bass correlation is low. Low end will cancel out when played in mono."})

    # --- A6.1 Spatial audio flags ---
    if side_bands.get("presence", 0) < t["side_presence_min"]:
        flags.append({
            "severity": "low",
            "label": "Narrow presence",
            "detail": "Side-channel energy in the 2-6 kHz presence band is very low; the mix may feel narrow or centered in that range.",
        })
    _side_air = metric_float(side_bands.get("air"))
    _mid_air = metric_float(mid_bands.get("air"))
    if _mid_air > 1e-6 and (_side_air / _mid_air) > t["side_over_air_ratio"]:
        flags.append({
            "severity": "low",
            "label": "Over-widened air",
            "detail": "Side energy exceeds Mid energy above 8 kHz; excessive stereo widening on air-band content may sound artificial or phasey.",
        })
    if lufs > t["lufs_max"] and lufs != -99.0 and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Hot Mix", "detail": f"Integrated loudness is {lufs:.1f} LUFS, above {t['lufs_max']:.0f} LUFS for a {goal_label}."})

    tonal = metrics.get("tonal_balance") or {}
    dynamic = metrics.get("dynamic_profile") or {}
    if metric_float(tonal.get("low_end_share")) > t["low_end_share_max"] and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Low-end heavy balance", "detail": "The broad tonal profile is dominated by sub and bass energy."})
    if metric_float(tonal.get("clarity_share")) < t["clarity_share_min"] and metric_float(tonal.get("low_end_share")) < t["clarity_low_end_max"] and not is_clean_calibration:
        flags.append({"severity": "low", "label": "Dark tonal balance", "detail": "Presence and air are low in the broad tonal profile."})
    if dynamic.get("profile") == "Spiky":
        flags.append({"severity": "medium", "label": "Spiky transients", "detail": "Peaks sit well above the loud sections, so the mix may feel jumpy or under-controlled."})
    transient_analysis = metrics.get("transient_analysis") or {}
    flags.extend(transient_analysis.get("flags") or [])
    if metric_float(dynamic.get("section_range_db")) > t["section_range_max_db"]:
        flags.append({"severity": "medium", "label": "Uneven loudness", "detail": "Section-to-section RMS movement is large; the arrangement or automation may need smoothing."})

    if abs(metric_float(metrics.get("dc_offset"))) > t["dc_offset_max"]:
        flags.append({"severity": "low", "label": "DC offset", "detail": "Average waveform offset is higher than expected."})
    if metric_float(metrics.get("leading_silence_seconds")) > t["leading_silence_max_seconds"]:
        flags.append({"severity": "low", "label": "Long intro silence", "detail": "There is a long quiet section before audio starts."})
    if metric_float(metrics.get("trailing_silence_seconds")) > t["trailing_silence_max_seconds"]:
        flags.append({"severity": "low", "label": "Long tail silence", "detail": "There is a long quiet section after the audio ends."})

    # --- BS.1770-4 / EBU R128 loudness profile flags ---
    lra = metric_float(metrics.get("loudness_range_lu"), -1)
    momentary_max = metric_float(metrics.get("momentary_max_lufs"), -99)
    if lra >= 0 and lra < t["lra_min_lu"] and not is_clean_calibration:
        flags.append({"severity": "medium", "label": "Over-compressed (LRA)", "detail": f"Loudness Range is {lra:.1f} LU, below the {t['lra_min_lu']:.0f} LU minimum for a {goal_label}. The mix may sound flat and fatiguing."})
    if lra > t["lra_max_lu"]:
        flags.append({"severity": "low", "label": "Very dynamic", "detail": f"Loudness Range is {lra:.1f} LU, above {t['lra_max_lu']:.0f} LU. Quiet sections may disappear on small speakers or in noisy environments."})
    if lufs != -99.0 and momentary_max != -99.0 and (momentary_max - lufs) > t["loudness_spike_lu"]:
        flags.append({"severity": "medium", "label": "Loudness spike", "detail": f"Momentary peak ({momentary_max:.1f} LUFS) exceeds integrated ({lufs:.1f} LUFS) by {momentary_max - lufs:.1f} LU."})

    # --- Distortion & Resonance flags ---
    even_thd = metric_float(metrics.get("distortion_even_thd"), 0.0)
    odd_thd = metric_float(metrics.get("distortion_odd_thd"), 0.0)
    resonances = metrics.get("resonances") or []
    isp_dbfs = metric_float(metrics.get("inter_sample_peak_dbfs"), -99.0)

    # distortion_odd_thd/even_thd come from analyze_thd_n(), which assumes
    # clean monophonic tonal content -- Stage M5 (2026-07-10) already found
    # this measurement unbounded and unreliable on real polyphonic/complex
    # material (values up to 4945, not a percentage) and excluded it from
    # its own detector for exactly that reason. A full rendered mix is
    # exactly that kind of polyphonic content, so these flags stay
    # informational (found 2026-07-12: this "high"-severity flag was
    # corrupting technical_score on legitimate mixes via an 18-point
    # penalty on a measurement that was never reliable for this input in
    # the first place) -- shown in the report for a human to judge, not
    # scored, until a clipping-specific measurement replaces it.
    if odd_thd > t["odd_thd_max"]:
        flags.append({
            "severity": "high",
            "label": "Harsh digital clipping",
            "detail": f"Harsh odd harmonic distortion is {odd_thd * 100:.2f}%, exceeding the limit of {t['odd_thd_max'] * 100:.1f}%. Check digital clipping.",
            "informational": True,
        })
    elif even_thd > t["even_thd_min_warmth"] and odd_thd < 0.005 and even_thd <= t["even_thd_max_warmth"]:
        flags.append({
            "severity": "low",
            "label": "Analog warmth",
            "detail": f"Good analog warmth detected: even harmonics are at {even_thd * 100:.2f}% with low odd harmonics.",
            "informational": True,
        })

    if crest >= 4.0:
        for res_item in resonances:
            sev = res_item.get("severity_db", 0.0)
            fc = res_item.get("frequency_hz", 0.0)
            q_val = res_item.get("q", 0.0)
            if sev > t["resonance_severity_max_db"]:
                flags.append({
                    "severity": "medium",
                    "label": "Harsh resonance",
                    "detail": f"Narrow resonance ringing detected at {fc:.1f} Hz (severity {sev:.1f} dB, Q={q_val:.1f}). Suggest notch filtering."
                })

    if isp_dbfs > t["inter_sample_peak_max_dbfs"] and isp_dbfs != -99.0:
        flags.append({
            "severity": "medium",
            "label": "Inter-sample clipping",
            "detail": f"Inter-sample peaks hit {isp_dbfs:.2f} dBFS, risking D/A converter clipping on consumer players."
        })

    return flags


HIGH_CONFIDENCE_FLAGS = {
    "Low headroom",
    "Clipping risk",
    "DC offset",
    "Long intro silence",
    "Long tail silence",
    "Stereo imbalance",
    "Mono risk",
    "Low-End Phase Cancellation",
    "Hot Mix",
}
REFERENCE_SENSITIVE_FLAGS = {
    "Low-mid build-up",
    "Heavy sub",
    "Low presence",
    "Perceived harshness",
    "Bright top end",
    "Low-end heavy balance",
    "Dark tonal balance",
    "Narrow presence",
    "Over-widened air",
}


def confidence_for_flag(flag: dict) -> str:
    label = str(flag.get("label", ""))
    if label in HIGH_CONFIDENCE_FLAGS:
        return "high"
    if label in REFERENCE_SENSITIVE_FLAGS:
        return "medium"
    return "medium" if str(flag.get("severity")) in {"high", "medium"} else "low"


def annotate_flags(flags: list[dict]) -> list[dict]:
    annotated = []
    for flag in flags:
        item = dict(flag)
        item["confidence"] = confidence_for_flag(item)
        if item["confidence"] == "high":
            item["confidence_reason"] = "Direct measurement from level, silence, phase, or file-integrity checks."
        elif item.get("label") in REFERENCE_SENSITIVE_FLAGS:
            item["confidence_reason"] = "Spectral balance finding; confirm against a level-matched reference and listening context."
        else:
            item["confidence_reason"] = "Derived from first-pass aggregate metrics; confirm by ear."
        annotated.append(item)
    return annotated


def technical_score(flags: list[dict]) -> int:
    penalty = {"high": 18, "medium": 10, "low": 5}
    # "informational" flags are shown in the report but never penalize the
    # score -- currently the distortion-THD-based flags (see the comment
    # where they're raised above): Stage M5 already proved that measurement
    # unreliable on real polyphonic mixes, so it can inform a human but must
    # not silently corrupt an automated pass/fail decision.
    score = 100 - sum(
        penalty.get(str(flag.get("severity")), 5)
        for flag in flags
        if not flag.get("informational")
    )
    return max(0, min(100, score))


def rating_from_score(score: int) -> str:
    if score >= 85:
        return "Clean technical pass"
    if score >= 70:
        return "Solid with checks"
    return "Needs attention"


def technical_metrics_payload(metrics: dict) -> dict:
    """Objective measurements without advice, scoring, or repair judgment."""
    keys = [
        "filename",
        "source_format",
        "decoder",
        "duration_seconds",
        "sample_rate",
        "channels",
        "peak_dbfs",
        "left_peak_dbfs",
        "right_peak_dbfs",
        "true_peak_dbfs",
        "rms_dbfs_estimate",
        "integrated_lufs",
        "loudest_section_rms_dbfs",
        "dynamic_range_estimate_db",
        "crest_factor_db",
        "dc_offset",
        "leading_silence_seconds",
        "trailing_silence_seconds",
        "clipped_frames_estimate",
        "stereo_balance",
        "stereo_correlation",
        "stereo_width",
        "mid_bands",
        "side_bands",
        "correlation_bands",
        "bands",
        "perceptual_bands",
        "perceptual_summary",
        "spectral_features",
        "tonal_balance",
        "dynamic_profile",
        "stereo_field",
        "section_analysis",
        "chords",
    ]
    return {key: metrics.get(key) for key in keys if key in metrics}


def judgment_payload(metrics: dict, flags: list[dict], actions: list[dict], advice: list[str], summary: str) -> dict:
    """Goal-aware interpretation built from the objective measurements."""
    return {
        "mix_goal": metrics.get("mix_goal"),
        "technical_score": metrics.get("technical_score"),
        "technical_rating": metrics.get("technical_rating"),
        "summary": summary,
        "flags": flags,
        "action_plan": actions,
        "advice": advice,
        "goal_target_checks": metrics.get("goal_target_checks"),
    }


def refresh_report_interpretation(report: dict) -> dict:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    flags = report.get("flags") if isinstance(report.get("flags"), list) else []
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    advice = report.get("advice") if isinstance(report.get("advice"), list) else []
    summary = str(report.get("summary") or "")
    report["technical_metrics"] = technical_metrics_payload(metrics)
    report["judgment"] = judgment_payload(metrics, flags, actions, advice, summary)
    return report


FLAG_ACTIONS = {
    "Low headroom": "Lower the mix or limiter output and leave safer peak headroom before mastering.",
    "Clipping risk": "Find the clipping source by bypassing limiters, clippers, saturation, and loud buses in order.",
    "Low dynamics": "Back off limiting or bus compression, then compare punch against a level-matched reference.",
    "Low-mid build-up": "Sweep and reduce problem areas around 150-400 Hz on dense sources and reverbs.",
    "Heavy sub": "Check kick and bass separation below 80 Hz, then confirm the low end in mono.",
    "Low presence": "Check whether vocal, snare, or lead clarity needs controlled 2-6 kHz presence.",
    "Perceived harshness": "Check sibilance, cymbals, distortion, and lead presence around 2-6 kHz at normal listening level.",
    "Bright top end": "Check whether the top end feels exciting or brittle on headphones and small speakers.",
    "Stereo imbalance": "Inspect panning, stereo returns, and wideners for one-sided level build-up.",
    "Mono risk": "Fold to mono and reduce phasey wideners if vocals, bass, snare, or leads disappear.",
    "Very wide sides": "Reduce side-heavy processing until the centre image feels stable.",
    "Side Bass Mud": "Mono your low frequencies using a utility tool (e.g. Ableton Utility Bass Mono below 120Hz).",
    "Low-End Phase Cancellation": "Check your kick/bass phase alignment or polarity; out-of-phase bass cancels out in mono.",
    "Narrow presence": "Check whether lead vocals, guitars, or pads carry enough stereo width in the 2-6 kHz range; reverb sends or subtle widening can help.",
    "Over-widened air": "Reduce high-frequency widening or air-band reverb/exciter sends; excessive side energy above 8 kHz can sound artificial or phasey on headphones.",
    "Hot Mix": "Back off limiters and gain on your master bus to restore headroom and transient punch.",
    "Low-end heavy balance": "Check kick, bass, and sub effects against a level-matched reference before boosting the top end.",
    "Dark tonal balance": "Check vocal, snare, lead, and cymbal clarity before adding global high-shelf EQ.",
    "Spiky transients": "Catch only the loudest peaks with clip gain, a clipper, or faster compression before increasing overall loudness.",
    "Uneven loudness": "Use arrangement automation or clip gain to smooth large section jumps before bus compression.",
    "DC offset": "High-pass or repair the file before further processing if the offset is audible or persistent.",
    "Long intro silence": "Trim the start or confirm the silence is intentional for delivery.",
    "Long tail silence": "Trim the tail or confirm the silence is intentional for delivery.",
}


def priority_actions(metrics: dict, flags: list[dict], comparison: dict | None = None) -> list[dict]:
    severity_order = {"high": 0, "medium": 1, "low": 2}
    actions: list[dict] = []
    sorted_flags = sorted(
        flags,
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 3),
            0 if str(item.get("confidence")) == "high" else 1,
        ),
    )
    for index, flag in enumerate(sorted_flags, start=1):
        label = str(flag.get("label", "Technical check"))
        confidence = str(flag.get("confidence") or confidence_for_flag(flag))
        decision = "fix_first" if index <= 3 and str(flag.get("severity")) in {"high", "medium"} else "check_by_ear"
        if label in REFERENCE_SENSITIVE_FLAGS and not comparison:
            decision = "needs_reference"
        actions.append(
            {
                "rank": index,
                "decision": decision,
                "priority": str(flag.get("severity", "low")),
                "confidence": confidence,
                "focus": label,
                "action": FLAG_ACTIONS.get(label, str(flag.get("detail", "Review this technical flag."))),
                "reason": str(flag.get("detail", "")),
            }
        )

    if comparison:
        largest = comparison.get("largest_spectral_difference") or {}
        largest_perceived = comparison.get("largest_perceptual_difference") or {}
        band = str(largest.get("band", "")).replace("_", " ")
        delta = float(largest.get("delta", 0) or 0)
        if band and abs(delta) > 0.04:
            direction = "more" if delta > 0 else "less"
            actions.append(
                {
                    "rank": len(actions) + 1,
                    "decision": "needs_reference",
                    "priority": "reference",
                    "confidence": "medium",
                    "focus": f"{band.title()} vs reference",
                    "action": f"Level-match, then check why your mix has {direction} {band} energy than the reference.",
                    "reason": f"Largest spectral delta: {delta:+.3f}.",
                }
            )
        perceived_band = str(largest_perceived.get("band", "")).replace("_", " ")
        perceived_delta = float(largest_perceived.get("delta", 0) or 0)
        if perceived_band and abs(perceived_delta) > 0.04:
            direction = "more" if perceived_delta > 0 else "less"
            actions.append(
                {
                    "rank": len(actions) + 1,
                    "decision": "check_by_ear",
                    "priority": "perceptual",
                    "confidence": "medium",
                    "focus": f"Perceived {perceived_band}",
                    "action": f"At normal listening level, check whether the mix feels like it has {direction} {perceived_band} than the reference.",
                    "reason": f"Fletcher-Munson style delta: {perceived_delta:+.3f}.",
                }
            )
        rms_delta = float(comparison.get("rms_delta_db", 0) or 0)
        if abs(rms_delta) > 3:
            actions.append(
                {
                    "rank": len(actions) + 1,
                    "decision": "needs_reference",
                    "priority": "reference",
                    "confidence": "high",
                    "focus": "Level match",
                    "action": "Level-match your mix and reference before making tonal decisions.",
                    "reason": f"RMS estimate differs by {rms_delta:+.1f} dB.",
                }
            )

    if not actions:
        actions.append(
            {
                "rank": 1,
                "decision": "check_by_ear",
                "priority": "listen",
                "confidence": "low",
                "focus": "Reference listen",
                "action": "No major technical warning. Level-match with a reference and make taste decisions by ear.",
                "reason": f"Technical score {metrics.get('technical_score', 'n/a')}/100.",
            }
        )
    flag_actions = [a for a in actions if a.get("priority") not in ("reference", "perceptual")]
    comp_actions = [a for a in actions if a.get("priority") in ("reference", "perceptual")]
    final_actions = flag_actions[:5] + comp_actions
    for idx, act in enumerate(final_actions, start=1):
        act["rank"] = idx
    return final_actions


def report_summary(metrics: dict, flags: list[dict], comparison: dict | None = None) -> str:
    rating = str(metrics.get("technical_rating", "Technical review"))
    score = metrics.get("technical_score", "n/a")
    high_flags = [flag for flag in flags if flag.get("severity") == "high"]
    if high_flags:
        lead = f"{rating} ({score}/100). Start with {high_flags[0].get('label')}."
    elif flags:
        lead = f"{rating} ({score}/100). Main check: {flags[0].get('label')}."
    else:
        lead = f"{rating} ({score}/100). No major technical flags."
    if comparison:
        largest = comparison.get("largest_spectral_difference") or {}
        largest_perceived = comparison.get("largest_perceptual_difference") or {}
        band = str(largest.get("band", "")).replace("_", " ")
        delta = float(largest.get("delta", 0) or 0)
        if band and abs(delta) > 0.02:
            direction = "more" if delta > 0 else "less"
            lead += f" Compared with the reference, the biggest tonal difference is {direction} {band}."
        perceived_band = str(largest_perceived.get("band", "")).replace("_", " ")
        perceived_delta = float(largest_perceived.get("delta", 0) or 0)
        if perceived_band and abs(perceived_delta) > 0.04:
            direction = "more" if perceived_delta > 0 else "less"
            lead += f" Ear-weighting suggests it may feel like {direction} {perceived_band}."
    return lead



def deterministic_mix_critique(report: dict) -> str:
    metrics = report.get("metrics") or {}
    actions = report.get("action_plan") or []
    flags = report.get("flags") or []
    comparison_advice_items = report.get("comparison_advice") or []
    version_advice_items = report.get("version_advice") or []
    revision_agent = report.get("revision_agent") or {}
    agent_steps = revision_agent.get("steps") or []
    first_action = actions[0] if actions else {}
    flag_labels = ", ".join(str(flag.get("label", "")) for flag in flags[:4] if flag.get("label")) or "no major technical flags"
    lines = [
        "Main read:",
        str(report.get("summary") or f"{metrics.get('technical_rating', 'Technical review')} ({metrics.get('technical_score', 'n/a')}/100)."),
        "",
        "Fix first:",
        str(first_action.get("action") or "Level-match against a reference and make the next decision by ear."),
        "",
        "What to leave alone:",
        f"Current flags: {flag_labels}.",
    ]
    if comparison_advice_items:
        lines.extend(["", "Reference note:", str(comparison_advice_items[0])])
    if version_advice_items:
        lines.extend(["", "Version note:", str(version_advice_items[0])])
    if agent_steps:
        lines.extend(["", "Revision agent next step:", str(agent_steps[0].get("action", ""))])
    lines.extend(
        [
            "",
            "Listening checks:",
            "1. Level-match before judging tone or loudness.",
            "2. Check mono compatibility, vocal/lead focus, and low-end translation.",
            "3. Re-export one revision and compare it against this report.",
        ]
    )
    return "\n".join(lines).strip()


def valid_mix_critique(text: str) -> bool:
    lowered = text.lower()
    return "main read:" in lowered and "fix first:" in lowered and "listening checks:" in lowered


def critique_prompt_payload(report: dict) -> dict:
    metrics = report.get("metrics") or {}
    return {
        "summary": report.get("summary", ""),
        "technical_rating": metrics.get("technical_rating"),
        "technical_score": metrics.get("technical_score"),
        "key_metrics": {
            key: metrics.get(key)
            for key in (
                "peak_dbfs",
                "rms_dbfs_estimate",
                "crest_factor_db",
                "dynamic_range_estimate_db",
                "stereo_correlation",
                "stereo_width_ratio",
            )
        },
        "spectral_features": metrics.get("spectral_features", {}),
        "tonal_balance": metrics.get("tonal_balance", {}),
        "dynamic_profile": metrics.get("dynamic_profile", {}),
        "stereo_field": metrics.get("stereo_field", {}),
        "goal_target_checks": metrics.get("goal_target_checks", {}),
        "perceptual_summary": metrics.get("perceptual_summary", {}),
        "flags": report.get("flags", []),
        "action_plan": report.get("action_plan", []),
        "source_hypotheses": report.get("source_hypotheses", []),
        "frequency_repair_map": report.get("frequency_repair_map", []),
        "reference_comparison": report.get("comparison"),
        "reference_advice": report.get("comparison_advice", []),
        "version_comparison": report.get("version_comparison"),
        "version_advice": report.get("version_advice", []),
        "revision_agent": report.get("revision_agent"),
    }


def generate_mix_critique(report: dict) -> dict:
    fallback = deterministic_mix_critique(report)
    if os.environ.get("AUDIO_TOO_MIX_REVIEW_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return {
            "mode": "deterministic",
            "available": False,
            "message": "Mix Review LLM critique off; set AUDIO_TOO_MIX_REVIEW_LLM=1 when the LLM provider is online.",
            "text": fallback,
        }
    provider = _mix_critique_provider
    if provider is None:
        return {
            "mode": "deterministic",
            "available": False,
            "message": "LLM critique module unavailable; using deterministic critique.",
            "text": fallback,
        }

    status = provider.public_status()
    if not provider.is_enabled():
        return {
            "mode": "deterministic",
            "available": False,
            "message": status.get("message", "LLM critique unavailable; using deterministic critique."),
            "text": fallback,
        }

    system = (
        "You are Audio_Too's mix review assistant. Write a concise engineer-style critique using ONLY "
        "the supplied metrics, flags, action plan, reference comparison, and version comparison. "
        "Do not claim to hear the audio. Do not invent genre, instruments, plugins, or causes. "
        "Use exactly these headings: Main read:, Fix first:, What to leave alone:, Listening checks:. "
        "Keep it practical and under 220 words."
    )
    user = "Mix review facts:\n" + json.dumps(critique_prompt_payload(report), indent=2)
    try:
        text = provider.chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        ).strip()
    except Exception as exc:
        return {
            "mode": "deterministic",
            "available": False,
            "message": f"LLM critique unavailable ({exc.__class__.__name__}); using deterministic critique.",
            "text": fallback,
        }
    if not valid_mix_critique(text):
        return {
            "mode": "deterministic",
            "available": False,
            "message": "LLM critique returned an invalid structure; using deterministic critique.",
            "text": fallback,
        }
    return {
        "mode": "llm",
        "available": True,
        "message": status.get("message", "LLM critique generated."),
        "text": text,
    }


def _deterministic_prose_summary(report: dict) -> str:
    """Build a 3-paragraph deterministic prose summary from structured report fields."""
    metrics = report.get("metrics") or {}
    tonal = metrics.get("tonal_balance") or {}
    dynamic = metrics.get("dynamic_profile") or {}
    stereo_field = metrics.get("stereo_field") or {}
    actions = report.get("action_plan") or []
    flags = report.get("flags") or []

    tonal_profile = str(tonal.get("profile") or "balanced")
    dynamic_profile = str(dynamic.get("profile") or "moderate")
    stereo_image = str(stereo_field.get("image") or "stable")
    low_end = str(stereo_field.get("low_end") or "check low-end mono")
    crest = metric_float(metrics.get("crest_factor_db"))
    integrated_lufs = metrics.get("integrated_lufs")
    lufs_str = f"{integrated_lufs} LUFS" if isinstance(integrated_lufs, (int, float)) else "not measured"
    flag_count = len(flags)
    first_action = str((actions[0] if actions else {}).get("action") or "Listen on multiple systems and compare against a reference.")

    p1 = (
        f"This mix has a {tonal_profile.lower()} tonal character with {dynamic_profile.lower()} dynamics "
        f"(crest factor {crest:.1f} dB, integrated loudness {lufs_str}). "
        f"The spectral balance {'is technically clean' if flag_count == 0 else f'has {flag_count} technical flag(s) worth addressing'}."
    )
    p2 = (
        f"The stereo image is {stereo_image.lower()}; the low end is {low_end}. "
        f"Stereo correlation reads {metric_float(metrics.get('stereo_correlation'), 1.0):.2f} "
        f"and the width ratio is {metric_float(metrics.get('stereo_width_ratio')):.2f}."
    )
    p3 = f"The most impactful next step: {first_action}"
    return f"{p1}\n\n{p2}\n\n{p3}"


def generate_prose_summary(report: dict) -> dict:
    """Generate a 3-paragraph flowing prose critique of a mix review.

    Paragraphs cover: (1) tonal balance and dynamics, (2) stereo image and
    spatial quality, (3) the single most impactful improvement.

    Falls back to a deterministic summary when the LLM is disabled or
    unavailable.  Returns {mode, available, text}.
    """
    fallback_text = _deterministic_prose_summary(report)
    if os.environ.get("AUDIO_TOO_MIX_REVIEW_LLM", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return {"mode": "deterministic", "available": False, "text": fallback_text}

    provider = _mix_critique_provider
    if provider is None or not provider.is_enabled():
        return {"mode": "deterministic", "available": False, "text": fallback_text}

    system = (
        "You are Audio_Too's mix review assistant writing for the producer. "
        "Write exactly three paragraphs — no bullet points, no headings:\n"
        "1. Tonal balance and dynamics: describe the spectral character, crest factor, and headroom.\n"
        "2. Stereo image and spatial quality: describe width, correlation, and any phase concerns.\n"
        "3. Most impactful next step: state the single most important change in one clear sentence.\n"
        "Base the review only on the supplied data. Do not invent genre, instruments, plugins, or causes."
    )
    user = "Mix review data:\n" + json.dumps(critique_prompt_payload(report), indent=2)
    try:
        text = provider.chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        ).strip()
        if not text:
            raise ValueError("empty response")
        return {"mode": "llm", "available": True, "text": text}
    except Exception as exc:
        return {
            "mode": "deterministic",
            "available": False,
            "message": f"LLM prose summary unavailable ({exc.__class__.__name__}); using deterministic summary.",
            "text": fallback_text,
        }


def advice_from_metrics(
    metrics: dict, flags: list[dict] | None = None, phon_level: float = 60.0
) -> list[str]:
    advice: list[str] = []
    flags = flags if flags is not None else review_flags(metrics)
    labels = {str(flag.get("label", "")).lower() for flag in flags}
    if "low headroom" in labels:
        advice.append("Leave more headroom before limiting or mastering; aim for peaks below about -3 to -6 dBFS on an unmastered mix.")
    if "clipping risk" in labels:
        advice.append("Check the loudest sections and bypass limiters, clippers, or saturation to find where clipping starts.")
    if "low dynamics" in labels:
        advice.append("Compare punch and movement against a reference at matched loudness; reduce bus limiting if the mix feels flat.")
    if "low-mid build-up" in labels:
        advice.append("Check 150-400 Hz on bass, guitars, keys, room mics, reverbs, and vocal body.")
    if "heavy sub" in labels:
        advice.append("Check the sub in mono and make sure kick and bass are not masking each other below 80 Hz.")
    if "low presence" in labels:
        advice.append("Check whether vocal, snare, or lead clarity needs controlled 2-6 kHz presence.")
    if "perceived harshness" in labels:
        advice.append("The ear-weighted curve suggests presence may feel forward. Check 2-6 kHz harshness before adding more brightness.")
    if "bright top end" in labels:
        advice.append("The ear-weighted curve suggests the air band may feel bright. Compare cymbals, esses, and noise against a reference.")
    if "mono risk" in labels or "very wide sides" in labels:
        advice.append("Fold the mix to mono and listen for vocals, bass, snare, and lead elements disappearing or thinning out.")
    if "stereo imbalance" in labels:
        advice.append("Check panning, stereo wideners, and effect returns; one side appears to carry more energy.")
    if "side bass mud" in labels:
        advice.append("Bass frequencies detected in the Side channel. Use a Mid/Side EQ to high-pass the Side channel below 100-120 Hz, keeping your bass in mono.")
    if "low-end phase cancellation" in labels:
        advice.append("Sub/Bass phase correlation is low/negative. Check phase alignment or try inverting the polarity of either the kick or the bass to prevent low-end cancellation.")
    if "hot mix" in labels:
        advice.append("The integrated loudness is hot. Leave more headroom for mastering; back off master limiters to preserve dynamics.")
    if "low-end heavy balance" in labels:
        advice.append("The broad tonal balance is low-end heavy. Compare kick and bass level at matched loudness before adding brightness to compensate.")
    if "dark tonal balance" in labels:
        advice.append("The broad tonal balance is dark. Check whether the vocal, lead, snare, or cymbals need presence rather than boosting the whole mix.")
    if "spiky transients" in labels:
        advice.append("The dynamic profile is spiky. Catch peak events locally before raising overall loudness.")
    if "crushed transients" in labels:
        advice.append("Transients rise quickly but have little crest reserve. Back off limiting, clipping, or fast compression and compare the kick/snare attack at matched loudness.")
    if "slow transient attacks" in labels:
        advice.append("Percussive attacks look slow. Check whether compressor attack, lookahead, saturation, or transient shaping is softening the initial hit.")
    if "uneven loudness" in labels:
        advice.append("The section loudness range is wide. Smooth level jumps with clip gain or automation before judging compression.")
    tonal = metrics.get("tonal_balance") or {}
    dynamic = metrics.get("dynamic_profile") or {}
    stereo_field = metrics.get("stereo_field") or {}
    if tonal.get("summary"):
        advice.append(str(tonal["summary"]))
    if dynamic.get("summary"):
        advice.append(str(dynamic["summary"]))
    if stereo_field.get("summary"):
        advice.append(str(stereo_field["summary"]))
    groove = metrics.get("groove_analysis") or {}
    if groove.get("timing_class") not in {None, "Insufficient rhythm"}:
        advice.append(
            f"Groove timing is {str(groove.get('timing_class')).lower()} at about "
            f"{metric_float(groove.get('bpm')):.1f} BPM, with "
            f"{metric_float(groove.get('mean_abs_deviation_ms')):.1f} ms mean grid deviation "
            f"and {metric_float(groove.get('swing_percentage'), 50.0):.1f}% swing."
        )
    target_checks = metrics.get("goal_target_checks") or {}
    warning_checks = [check for check in target_checks.get("checks", []) if check.get("status") == "warn"]
    if warning_checks:
        advice.append(f"Goal target check: {warning_checks[0].get('message', 'one selected-goal target needs attention')}")

    # Fletcher-Munson perceived loudness advice
    perceived = metrics.get("perceptual_bands") or {}
    if not perceived and "bands" in metrics:
        try:
            from audio_analysis.analysis_core.dsp_metrics import perceived_loudness_contribution
            perceived = perceived_loudness_contribution(metrics["bands"], phon_level)
        except Exception:
            pass
    try:
        fm_advice = fm_mix_critique(metrics, perceived, flags if flags is not None else [], phon_level)
        advice.extend(fm_advice)
    except Exception as e:
        print(f"Warning running fm_mix_critique: {e}")

    if not advice:
        advice.append("No major technical warning from this first-pass analysis. Compare against a level-matched reference for style-specific decisions.")
    return advice


def source_hypotheses(metrics: dict, flags: list[dict]) -> list[dict]:
    labels = {str(flag.get("label", "")) for flag in flags}
    goal = metrics.get("mix_goal") or {}
    hypotheses: list[dict] = []
    templates = {
        "Low-mid build-up": {
            "issue": "Low-mid build-up",
            "likely_sources": ["Vocal body", "guitars/keys", "room mics", "reverb returns", "bass harmonics"],
            "checks": ["Mute reverbs for one pass", "Solo bass with kick", "Listen quietly for boxiness around 150-400 Hz"],
            "first_move": "Find the source that clouds the mix before applying a broad mix-bus cut.",
        },
        "Heavy sub": {
            "issue": "Heavy sub",
            "likely_sources": ["Kick fundamental", "sub bass", "808 tail", "low-frequency effects", "unfiltered samples"],
            "checks": ["Fold the low end to mono", "Compare kick and bass against a reference", "Check small speakers after the edit"],
            "first_move": "Balance kick and bass together, then trim only the element that is masking the other.",
        },
        "Low presence": {
            "issue": "Low presence",
            "likely_sources": ["Lead vocal", "snare attack", "main synth/guitar", "over-dark bus processing"],
            "checks": ["Listen at low volume", "Mute time effects briefly", "Check whether clarity improves before adding EQ"],
            "first_move": "Add presence to the lead element that needs focus rather than brightening the whole mix.",
        },
        "Perceived harshness": {
            "issue": "Perceived harshness",
            "likely_sources": ["Vocal sibilance", "cymbals", "distorted synth edges", "bright saturation", "stacked high shelves"],
            "checks": ["Find the harsh words or hits", "Try dynamic EQ before static cuts", "Check headphones and small speakers"],
            "first_move": "Control only the harsh moments so the mix keeps energy without becoming dull.",
        },
        "Mono risk": {
            "issue": "Mono compatibility",
            "likely_sources": ["Stereo wideners", "chorus effects", "unmatched double tracks", "stereo bass effects"],
            "checks": ["Switch to mono", "Bypass wideners one by one", "Check vocal, snare, kick, and bass level"],
            "first_move": "Narrow or phase-align the element that disappears first in mono.",
        },
        "Spiky transients": {
            "issue": "Spiky transients",
            "likely_sources": ["Snare peaks", "kick clicks", "drum fills", "clip-gain jumps", "uncontrolled percussion"],
            "checks": ["Find the loudest hit", "Watch limiter gain reduction", "Compare before/after at matched level"],
            "first_move": "Clip-gain or lightly clip the worst hits locally before compressing the whole mix.",
        },
        "Uneven loudness": {
            "issue": "Uneven loudness",
            "likely_sources": ["Section automation", "arrangement density", "drop/chorus level jumps", "long effects tails"],
            "checks": ["Compare verse, chorus, and drop at the same monitor level", "Check automation lanes", "Bounce a short A/B revision"],
            "first_move": "Use clip gain or automation first, then reassess compression.",
        },
        "Clipping risk": {
            "issue": "Digital clipping / inter-sample peaks",
            "likely_sources": ["Master bus limiter ceiling too high", "hot individual tracks feeding the bus", "no true-peak margin before export", "a plugin's internal gain stage"],
            "checks": ["Look for flat-topped waveforms", "Check true-peak (not just sample-peak) meter", "Bypass the limiter and re-check gain staging upstream"],
            "first_move": "This is an objective, technical fault, not a taste call — pull the ceiling down or reduce upstream gain rather than accepting the clip.",
        },
        "Low dynamics": {
            "issue": "Low crest factor / squashed dynamics",
            "likely_sources": ["Over-limited master bus", "heavy bus or mix-bus compression", "individually over-compressed tracks stacking", "a loudness target chased before balance was right"],
            "checks": ["Bypass the limiter and compare crest factor", "Check gain-reduction metering on each compressor in the chain", "Level-match a less-compressed version and A/B for punch"],
            "first_move": "Back off the stage doing the most gain reduction first — usually the last limiter in the chain — before touching anything upstream.",
        },
        "Over-compressed (LRA)": {
            "issue": "Narrow loudness range across the track",
            "likely_sources": ["Aggressive mix-bus compression", "over-limiting at mastering", "automation flattened before mixdown", "genre-appropriate but still worth confirming intent"],
            "checks": ["Compare LRA against a genre-appropriate reference, not an absolute number", "Listen for quiet sections losing all contrast", "Bypass mastering-stage dynamics and re-measure"],
            "first_move": "Confirm this is unintentional before fixing anything — some genres want a narrow LRA; if not, restore dynamics at the stage doing the most reduction.",
        },
        "Stereo imbalance": {
            "issue": "Uneven left/right energy",
            "likely_sources": ["A panned element without a balancing counterpart", "an unbalanced stereo effect (reverb/delay send)", "a mono source hard-panned", "an asymmetric room capture on a stereo recording"],
            "checks": ["Solo hard-panned elements one at a time", "Check L/R meters independently", "Fold to mid/side and compare channel levels"],
            "first_move": "Find the specific panned source before adjusting overall balance or stereo processing.",
        },
        "Dark tonal balance": {
            "issue": "Overall mix reads dull/dark",
            "likely_sources": ["Low-pass or dull source material stacking", "over-use of tape/analogue saturation", "monitoring environment or fatigue leading to over-cutting highs", "genuinely a stylistic choice"],
            "checks": ["Compare against a level-matched commercial reference in the same genre", "Check on a second playback system", "Confirm whether this is a technical gap or an intentional tone before brightening anything"],
            "first_move": "This is often subjective — confirm the target tone against a reference before adding broad high-shelf EQ.",
        },
        "Bright top end": {
            "issue": "Excess high-frequency energy",
            "likely_sources": ["Cymbal/hat-heavy arrangement", "over-exciting or aggressive top-end EQ", "harsh source recordings (cheap mic, digital synth aliasing)", "de-essing or air-band boosts stacking across the chain"],
            "checks": ["Solo the brightest elements", "Bypass exciters/air-band boosts one at a time", "Check on headphones for fatigue, not just spectral level"],
            "first_move": "Tame the specific bright source before reaching for a broad master-bus high cut.",
        },
        "Low-End Phase Cancellation": {
            "issue": "Sub/bass loses energy or disappears in mono",
            "likely_sources": ["Stereo-widened bass or 808", "unaligned kick and bass phase", "a stereo recording of a mono-source instrument", "conflicting low-end reverb returns"],
            "checks": ["Switch to mono and listen for level drop in the low end", "Check kick/bass phase alignment by nudging one a few ms", "Narrow or sum low-end elements to mono one at a time"],
            "first_move": "Force the sub/bass to mono first — this is close to always correct for translation, not a taste call.",
        },
        "Hot Mix": {
            "issue": "Integrated loudness above the target for the goal",
            "likely_sources": ["Master limiter pushed too hard", "mixing loud without a loudness-matched reference", "chasing perceived loudness before balance was finished"],
            "checks": ["Level-match against the target LUFS and re-listen for balance, not just loudness", "Check true peak alongside integrated loudness"],
            "first_move": "This is objective relative to the stated goal — pull back gain reduction at the limiter rather than reworking the mix.",
        },
        "DC offset": {
            "issue": "Waveform is not centred on zero",
            "likely_sources": ["A faulty audio interface or driver", "a plugin with a DC-generating bug", "an improperly rendered bounce"],
            "checks": ["Zoom into the waveform at a silent section and look for offset from the zero line", "Test the signal chain with one plugin removed at a time"],
            "first_move": "This is a technical fault with one correct fix: apply a DC-offset-removal/high-pass filter near-zero Hz at the source, not a mix decision.",
        },
    }
    for label, template in templates.items():
        if label in labels:
            hypotheses.append(template)
    target_checks = metrics.get("goal_target_checks") or {}
    warning_labels = [str(check.get("label", "")) for check in target_checks.get("checks", []) if check.get("status") == "warn"]
    if warning_labels and len(hypotheses) < 5:
        hypotheses.append(
            {
                "issue": f"{goal.get('label', 'Goal')} target mismatch",
                "likely_sources": warning_labels[:4],
                "checks": ["Review the goal target panel", "Change one target issue per revision", "Re-export and compare the version delta"],
                "first_move": "Treat the selected mix goal as the brief, then fix the highest-impact warning first.",
            }
        )
    return hypotheses[:5]


FREQUENCY_REPAIR_LIBRARY = {
    "sub": {
        "label": "Sub",
        "range": "20-60 Hz",
        "role": "Weight, rumble, deepest kick/bass fundamentals.",
        "listen_for": "Power that can disappear on small speakers or overload headphones and rooms.",
        "first_move": "Check kick and bass together in mono before adding more low end.",
        "flags": {"Heavy sub", "Low-end heavy balance"},
        "high": 0.12,
        "low": 0.01,
    },
    "bass": {
        "label": "Bass",
        "range": "60-150 Hz",
        "role": "Kick weight, bass body, groove foundation.",
        "listen_for": "Boom, weak punch, or kick/bass masking.",
        "first_move": "Balance kick and bass by level first, then use small EQ moves only where they collide.",
        "flags": {"Heavy sub", "Low-end heavy balance"},
        "high": 0.34,
        "low": 0.03,
    },
    "low_mids": {
        "label": "Low mids",
        "range": "150-400 Hz",
        "role": "Warmth, vocal body, guitar/keys body, room tone.",
        "listen_for": "Mud, boxiness, cloudy reverbs, or a vocal that feels thick but unclear.",
        "first_move": "Mute reverbs and dense layers briefly, then find the source before cutting the whole mix.",
        "flags": {"Low-mid build-up"},
        "high": 0.18,
        "low": 0.03,
    },
    "mids": {
        "label": "Mids",
        "range": "400 Hz-2 kHz",
        "role": "Musical body, note definition, vocal intelligibility.",
        "listen_for": "Nasal tone, honk, or a hollow mix if this area is under-supported.",
        "first_move": "Check the lead element quietly; fix masking around the source before broad mix EQ.",
        "flags": set(),
        "high": 0.64,
        "low": 0.12,
    },
    "presence": {
        "label": "Presence",
        "range": "2-6 kHz",
        "role": "Vocal edge, snare attack, pick definition, perceived closeness.",
        "listen_for": "Clarity when balanced; harshness, bite, and S/T pain when overdone.",
        "first_move": "Use dynamic EQ or de-essing on sharp moments before broad static cuts.",
        "flags": {"Low presence", "Perceived harshness", "Dark tonal balance"},
        "high": 0.32,
        "low": 0.08,
    },
    "air": {
        "label": "Air",
        "range": "8-16 kHz",
        "role": "Openness, cymbal sheen, breath, hiss/noise detail.",
        "listen_for": "Expensive openness when controlled; fizz, noise, or brittle top when pushed.",
        "first_move": "Compare cymbals, esses, and noise against a level-matched reference.",
        "flags": {"Bright top end", "Dark tonal balance"},
        "high": 0.20,
        "low": 0.01,
    },
}


def band_reading(value: float, band_info: dict) -> str:
    if value >= float(band_info.get("high", 1.0)):
        return "high"
    if value <= float(band_info.get("low", 0.0)):
        return "low"
    return "normal"


def frequency_repair_map(
    metrics: dict, flags: list[dict], phon_level: float = 60.0
) -> list[dict]:
    bands = metrics.get("bands") or {}
    perceived = metrics.get("perceptual_bands") or {}
    if not perceived and bands:
        try:
            from audio_analysis.analysis_core.dsp_metrics import perceived_loudness_contribution
            perceived = perceived_loudness_contribution(bands, phon_level)
        except Exception:
            pass
    flag_labels = {str(flag.get("label", "")) for flag in flags}
    rows = []
    for key, info in FREQUENCY_REPAIR_LIBRARY.items():
        raw_value = metric_float(bands.get(key))
        perceived_value = metric_float(perceived.get(key))
        reading = band_reading(raw_value, info)
        matched_flags = sorted(flag_labels.intersection(info.get("flags", set())))
        priority = "watch" if matched_flags or reading != "normal" else "learn"
        if matched_flags:
            message = f"Linked flags: {', '.join(matched_flags)}."
        elif reading == "high":
            message = f"{info['label']} energy is above the normal guide for this first-pass read."
        elif reading == "low":
            message = f"{info['label']} energy is below the normal guide for this first-pass read."
        else:
            message = f"{info['label']} looks broadly within the normal guide."
        rows.append(
            {
                "band": key,
                "label": info["label"],
                "range": info["range"],
                "raw_share": round(raw_value, 4),
                "perceived_share": round(perceived_value, 4),
                "reading": reading,
                "priority": priority,
                "message": message,
                "role": info["role"],
                "listen_for": info["listen_for"],
                "first_move": info["first_move"],
                "linked_flags": matched_flags,
            }
        )

    # Fletcher-Munson repairs
    try:
        fm_repairs = fm_frequency_repair_map(metrics, perceived, phon_level)
        for repair in fm_repairs:
            for row in rows:
                if row["band"] == repair["band"]:
                    row["priority"] = repair["priority"]
                    row["message"] += f" Perceived warning at {int(phon_level)} phon: {repair['details']}"
                    row["first_move"] = f"{repair['suggested_move']}. {row['first_move']}"
    except Exception as e:
        print(f"Warning running fm_frequency_repair_map: {e}")

    rows.sort(key=lambda item: (item["priority"] != "watch", item["reading"] == "normal", item["band"]))
    return rows


def lesson_cards(flags: list[dict], mix_goal: dict, *, limit: int = 4) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()
    for flag in flags:
        label = str(flag.get("label") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        lesson = LESSON_LIBRARY.get(label)
        if not lesson:
            continue
        cards.append(
            {
                "flag": label,
                "severity": str(flag.get("severity", "low")),
                "goal": mix_goal.get("label", "Mix"),
                "meaning": lesson["meaning"],
                "listen_for": lesson["listen_for"],
                "common_causes": list(lesson["common_causes"]),
                "first_fixes": list(lesson["first_fixes"]),
                "goal_context": mix_goal.get("target", ""),
            }
        )
        if len(cards) >= limit:
            break
    return cards


def revision_lesson(report: dict, *, mix_goal_info: Callable) -> dict:
    metrics = report.get("metrics") or {}
    mix_goal = metrics.get("mix_goal") or mix_goal_info("")
    actions = report.get("action_plan") or []
    lessons = report.get("lesson_cards") or []
    first_action = actions[0] if actions else {}
    first_lesson = lessons[0] if lessons else {}
    objective = str(first_action.get("focus") or first_lesson.get("flag") or "Level-matched revision")
    why = str(first_lesson.get("meaning") or report.get("summary") or "Use the technical readout to make one controlled revision.")
    steps = []
    if first_action.get("action"):
        steps.append(str(first_action["action"]))
    for item in first_lesson.get("first_fixes", [])[:3]:
        if item not in steps:
            steps.append(str(item))
    if not steps:
        steps = [
            "Level-match against a reference before changing tone.",
            "Make one focused change, then re-export a new version.",
            "Compare the new version against this report.",
        ]
    checks = [
        str(first_lesson.get("listen_for") or "Listen at matched loudness for the specific issue you changed."),
        "Fold to mono and check centre elements plus low-end translation.",
        "Re-upload the revision and compare score, flags, tonal balance, dynamics, and stereo field.",
    ]
    return {
        "title": f"{mix_goal.get('label', 'Mix')} revision lesson: {objective}",
        "goal": mix_goal,
        "objective": objective,
        "why_it_matters": why,
        "steps": steps[:4],
        "listening_checks": checks,
        "reupload_target": "Export one revised WAV with the same start/end points, then upload it as the next version.",
    }
