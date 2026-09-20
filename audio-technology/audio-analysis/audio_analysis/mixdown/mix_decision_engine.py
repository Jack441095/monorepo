"""Mix Decision Engine module for automated mixdown system.

Translates stem classification profiles, psychoacoustic analysis results, and target genre
rules into concrete DSP mixing parameters for every stem and the master bus.
Generates a complete MixPlan with a human-readable decision log explaining every choice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from .stem_classifier import StemProfile
from .mix_rules import get_rule_for_instrument, INSTRUMENT_PRIORITY, GENRE_MODIFIERS
from ..analysis_core.target_config import GOAL_TARGETS, mix_goal_info
from ..dsp_engine.dsp_necessity import needs_deesser, needs_highpass, needs_mid_carve, needs_resonance_scan


GENRE_TO_MIX_GOAL = {
    "hip_hop": "rap_vocal",
    "rock": "premaster",
    "pop": "pop_vocal",
    "edm": "club",
    "acoustic": "premaster",
    "jazz": "premaster",
    "cinematic": "premaster",
    "podcast": "podcast",
}

# Common genre synonyms that map unambiguously onto a supported profile, so a
# request for e.g. "electronic" or "rap" gets the right treatment instead of
# silently falling back to "pop". Only unambiguous mappings live here; anything
# genuinely unsupported (e.g. "latin", "reggae") falls back to pop *with a
# logged note*, never silently. Targets must be keys of GENRE_MODIFIERS.
GENRE_ALIASES = {
    "electronic": "edm", "electronica": "edm", "house": "edm", "techno": "edm",
    "trance": "edm", "dubstep": "edm", "dnb": "edm", "drum and bass": "edm",
    "rap": "hip_hop", "hiphop": "hip_hop", "hip hop": "hip_hop", "hip-hop": "hip_hop",
    "trap": "hip_hop", "urban": "hip_hop", "urbano": "hip_hop", "reggaeton": "hip_hop", "latin": "pop",
    "rnb": "pop", "r&b": "pop", "soul": "acoustic", "lofi": "acoustic", "lo-fi": "acoustic",
    "classical": "cinematic", "orchestral": "cinematic", "score": "cinematic", "film": "cinematic",
    "folk": "acoustic", "singer-songwriter": "acoustic", "unplugged": "acoustic",
    "metal": "rock", "punk": "rock", "indie": "rock", "indie rock": "rock", "alt rock": "rock",
    "spoken": "podcast", "spoken word": "podcast", "voiceover": "podcast", "talk": "podcast",
}


def resolve_genre(genre: str) -> tuple[str, str]:
    """Resolve a requested genre to a supported profile.

    Returns ``(resolved_genre, note)`` where ``note`` is empty for an exact
    match, or a human-readable explanation when an alias or the pop fallback was
    used — so the caller can record it in the decision log rather than changing
    the render silently.
    """
    raw = (genre or "").strip().lower()
    if raw in GENRE_MODIFIERS:
        return raw, ""
    if raw in GENRE_ALIASES:
        target = GENRE_ALIASES[raw]
        return target, f"Genre '{raw}' mapped to the '{target}' profile."
    return "pop", f"Genre '{raw or '(unset)'}' not recognized; using the 'pop' profile (results may not match genre)."

# Preserve the producer's rough static balance while still allowing the rule
# engine to make useful role-based corrections. Full-song RMS is deliberately
# not trusted as an unconstrained gain target because sparse stems contain long
# silences and can otherwise receive extreme boosts.
ROUGH_INTENT_MAX_GAIN_DEVIATION_DB = 6.0


def bound_gain_to_rough_intent(proposed_gain_db: float, anchor_gain_db: float) -> float:
    """Clamp a role-based stem gain around the mix's shared anchor gain."""
    deviation = ROUGH_INTENT_MAX_GAIN_DEVIATION_DB
    return max(
        anchor_gain_db - deviation,
        min(anchor_gain_db + deviation, proposed_gain_db),
    )


@dataclass
class StemMixConfig:
    """DSP configurations for a single stem."""
    stem_name: str
    instrument: str
    gain_db: float = 0.0
    pan: float = 0.0
    eq_bands: list[dict] = field(default_factory=list)
    compressor: dict | None = None
    gate: dict | None = None
    reverb_send: float = 0.0
    reverb_type: str = "room"
    reverb_decay_s: float = 1.2
    delay_send: float = 0.0
    stereo_width: float = 1.0
    mono_below_hz: float = 120.0
    saturation_drive_db: float = 0.0
    saturation_mix: float = 0.0
    deesser: dict | None = None
    transient_shaper: dict | None = None
    # DSP-necessity gate (dsp_engine/dsp_necessity.py) — decided once here from
    # the already-computed StemProfile, so mix_renderer.py's per-stem loop can
    # skip stages that would be a no-op on this particular stem instead of
    # running them open-loop on every stem regardless of content.
    needs_resonance_scan: bool = True
    needs_deesser: bool = False
    needs_mid_carve: bool = True


@dataclass
class BusMixConfig:
    """DSP configurations for the master summing bus."""
    bus_compressor: dict | None = None
    bus_eq_bands: list[dict] = field(default_factory=list)
    reference_width_factor: float = 1.0
    limiter_ceiling_db: float = -1.0
    limiter_threshold_db: float = 0.0  # Threshold of limiting (negative is boost/makeup)
    saturation_drive_db: float = 0.0
    saturation_mix: float = 0.0


@dataclass
class MixPlan:
    """Complete, end-to-end automated mixing plan."""
    stems: list[StemMixConfig]
    bus: BusMixConfig
    genre: str
    target_lufs: float
    mix_goal: str = "premaster"
    decisions_log: list[str] = field(default_factory=list)
    musical_roles: list[dict] = field(default_factory=list)
    arrangement: dict = field(default_factory=dict)
    relationships: list[dict] = field(default_factory=list)
    automation_preview: dict = field(default_factory=dict)
    mono_compatibility: dict = field(default_factory=dict)
    # Off by default until listening-validated (docs/PROJECT_ACTION_PLAN §6.2/§10.4
    # and docs/AUDIO_SOFTWARE_IMPROVEMENT_PLAN_2026-07-20.md §2). A 2026-07-20 change
    # flipped this (and crest reduction) on by default with no blind A/B; reverted,
    # because a perceptual DSP change must not be a default without blind evidence
    # (the "boost-don't-cut" lesson in docs/audits/2026-07-17-reference-track-comparison.md).
    # When True, the renderer applies the relationship engine's actionable
    # dynamic-EQ candidates to the lower-priority (target) stem to de-mask it —
    # closing the "detected masking but rendered zero corrections" funnel.
    apply_masking_corrections: bool = False
    # Off by default, same rationale. When True, the renderer applies a bounded
    # additional stereo-narrowing pass to any stem the mono-compatibility
    # detector flagged warning/critical — closes the same "detected but never
    # corrected" gap for phase/fold-down issues (see
    # docs/audits/2026-07-17-stranger-v6-listening-findings.md — ear-confirmed
    # on real material, root cause traced to source-recording decorrelation).
    apply_mono_compat_correction: bool = False
    # Off by default until listening-validated (reverted from the same 2026-07-20
    # unvalidated default-on flip). When True, the renderer applies proactive
    # crest-factor reduction before the final LUFS gain solve when the measured
    # crest factor is unusually wide -- closes the "reference tracks sound denser
    # at the same integrated loudness" gap that fixed-LUFS normalization alone
    # can't fix (it only controls average level, not peak-to-average ratio).
    # Distinct from the always-on, reachability-gated crest reduction in
    # mix_renderer.py, which only engages when the target loudness is literally
    # unreachable -- this engages on measured density regardless of reachability.
    apply_proactive_crest_reduction: bool = False
    apply_deesser: bool = False
    apply_spectral_matching: bool = False



def _target_ceiling_for_goal(goal: str, fallback: float = -1.0) -> float:
    """Return the strictest peak ceiling declared by the canonical goal target."""
    ceilings = []
    for check in GOAL_TARGETS.get(goal, {}).get("checks", []):
        if check.get("metric") in {"peak_dbfs", "true_peak_dbfs"} and "max" in check:
            ceilings.append(float(check["max"]))
    return min(ceilings) if ceilings else fallback


def analyze_reference_track(file_bytes: bytes) -> dict:
    """Analyze a reference track's integrated loudness and spectral band energy distribution."""
    from ..utils.audio_io import read_wav_mono
    from ..analysis_core.dsp_metrics import spectral_bands
    from ..analysis_core.loudness import calculate_loudness_profile
    from .stem_prep import read_wav_stereo

    # Read mono samples for spectral band ratios
    mono_data = read_wav_mono(file_bytes, max_samples=131072)
    samples = mono_data.get("samples", [])
    sr = mono_data.get("sample_rate", 44100)
    bands = spectral_bands(samples, sr)

    # Read full stereo channels for LUFS profile
    stereo_data = read_wav_stereo(file_bytes, max_samples=0)
    left = stereo_data.get("left", [])
    right = stereo_data.get("right", [])

    try:
        loudness_info = calculate_loudness_profile(left, right, sr)
        lufs = loudness_info.get("integrated_lufs", -14.0)
    except Exception:
        logger.warning("Reference track LUFS measurement failed; using -14.0 default", exc_info=True)
        lufs = -14.0

    return {
        "bands": bands,
        "loudness": lufs
    }


def generate_mix_plan(
    stems_profiles: list[StemProfile],
    masking_results: dict | None = None,
    genre: str = "pop",
    target_lufs: float | None = None,
    reference_profile: dict | None = None,
    connect_func=None,
    dynamics_flags: dict[str, dict] | None = None,
) -> MixPlan:
    """Generate a MixPlan based on stem profiles, genre requirements, and masking analysis.

    Parameters
    ----------
    stems_profiles : list[StemProfile]
        Profiles of the input stems containing classified instruments, levels, etc.
    masking_results : dict, optional
        Results of simultaneous masking analysis (from analyze_stems_masking).
    genre : str
        Target genre modifier. Defaults to "pop".
    target_lufs : float
        Target loudness for the master output.
    dynamics_flags : dict[str, dict], optional
        Stage K pre-analysis output (from
        ``analysis_core.sidechain_detection.analyze_stems_for_dynamics``),
        keyed by stem name. A stem flagged with ``"sidechain_detected":
        True`` gets its own rule-table compressor backed off (skipped
        entirely) rather than applied on top of an already-shaped envelope
        -- AutoMix's compressor stage would otherwise fight or double-
        process a dynamics treatment the original producer already applied
        intentionally. ``None``/omitted is fully backward compatible: no
        stem is ever backed off unless a caller explicitly opts in by
        passing real detection results.
    """
    genre, _genre_note = resolve_genre(genre)

    master_defaults = GENRE_MODIFIERS[genre].get("master_bus", {})
    if target_lufs is None:
        target_lufs = float(master_defaults.get("target_lufs", -14.0))
    mix_goal = GENRE_TO_MIX_GOAL[genre]
    goal_info = mix_goal_info(mix_goal)

    # M8.3 — load feedback-derived corrections when a DB connection is available
    _feedback_corrections: dict = {}
    if connect_func is not None:
        try:
            from audio_analysis.integration.quality_predictor import load_mix_modifiers
            _feedback_corrections = load_mix_modifiers(genre, connect_func=connect_func) or {}
        except Exception:
            pass

    decisions: list[str] = []
    if _genre_note:
        decisions.append(_genre_note)
    decisions.append(f"Starting automated mix generation for genre: '{genre}' targeting {target_lufs} LUFS.")
    if _feedback_corrections:
        decisions.append(
            f"Applying {len(_feedback_corrections)} feedback-learned correction(s) from prior accepted/rejected mixes."
        )
    decisions.append(
        f"Canonical target profile: {goal_info['label']} ({goal_info['key']}) — {goal_info['target']}"
    )

    # 1. Map stems to rules and identify anchor
    stem_configs: dict[str, StemMixConfig] = {}
    
    # We want to identify the anchor stem (typically kick, drum bus, or loudest stem)
    anchor_profile: StemProfile | None = None
    for p in stems_profiles:
        rule = get_rule_for_instrument(p.instrument, genre)
        if rule.get("gain_anchor", False):
            anchor_profile = p
            decisions.append(f"Anchor stem identified: '{p.name}' (classified as '{p.instrument}').")
            break

    if anchor_profile is None:
        # If no explicit anchor, choose the loudest stem by peak level
        valid_stems = [p for p in stems_profiles if p.peak_dbfs > -60.0]
        if valid_stems:
            anchor_profile = max(valid_stems, key=lambda p: p.peak_dbfs)
            decisions.append(
                f"No explicit anchor instrument found. Selected loudest stem as fallback anchor: "
                f"'{anchor_profile.name}' (classified as '{anchor_profile.instrument}', peak {anchor_profile.peak_dbfs:.1f} dBFS)."
            )
        else:
            # Absolute fallback
            anchor_profile = stems_profiles[0] if stems_profiles else None

    # Calculate anchor gain adjustment
    anchor_gain = 0.0
    anchor_target_peak = -6.0
    if anchor_profile:
        anchor_rule = get_rule_for_instrument(anchor_profile.instrument, genre)
        anchor_target_peak = anchor_rule.get("target_peak_dbfs", -6.0)
        anchor_gain = anchor_target_peak - anchor_profile.peak_dbfs
        # Reference RMS level of the anchor track once gain is applied
        ref_rms_dbfs = anchor_profile.rms_dbfs + anchor_gain
        decisions.append(
            f"Anchor gain set to {anchor_gain:+.1f} dB (targeting peak level of {anchor_target_peak:.1f} dBFS)."
        )
    else:
        ref_rms_dbfs = -18.0  # Arbitrary fallback reference
        decisions.append("No stems available to anchor gain staging. Using fallback reference level.")

    # 2. Compute Level Gains, Panning, High-pass, and Default EQ
    for p in stems_profiles:
        rule = get_rule_for_instrument(p.instrument, genre)
        config = StemMixConfig(stem_name=p.name, instrument=p.instrument)

        # A. Gain Staging
        if anchor_profile and p.name == anchor_profile.name:
            config.gain_db = anchor_gain
        else:
            # Check if this is a transient or continuous instrument
            is_transient = p.instrument in ("kick", "snare", "hihat", "percussion", "full_drum_bus")
            
            if is_transient:
                # Target based on peak relative to anchor peak
                rel_peak = rule.get("target_level_relative_to_anchor", -6.0)
                target_peak = anchor_target_peak + rel_peak
                proposed_gain = target_peak - p.peak_dbfs
                config.gain_db = bound_gain_to_rough_intent(proposed_gain, anchor_gain)
                decisions.append(
                    f"Gain for transient '{p.name}' ({p.instrument}) set to {config.gain_db:+.1f} dB "
                    f"(proposed {proposed_gain:+.1f} dB from target peak {target_peak:.1f} dBFS; "
                    f"rough-intent limit +/-{ROUGH_INTENT_MAX_GAIN_DEVIATION_DB:.1f} dB around anchor)."
                )
            else:
                # Target based on RMS relative to anchor RMS
                rel_rms = rule.get("target_level_relative_to_anchor", -8.0)
                target_rms = ref_rms_dbfs + rel_rms
                proposed_gain = target_rms - p.rms_dbfs
                config.gain_db = bound_gain_to_rough_intent(proposed_gain, anchor_gain)
                decisions.append(
                    f"Gain for continuous '{p.name}' ({p.instrument}) set to {config.gain_db:+.1f} dB "
                    f"(proposed {proposed_gain:+.1f} dB from target RMS {target_rms:.1f} dBFS; "
                    f"rough-intent limit +/-{ROUGH_INTENT_MAX_GAIN_DEVIATION_DB:.1f} dB around anchor)."
                )

        # A1. M8.3 — Apply feedback-learned gain correction (capped at ±2 dB)
        gain_correction = _feedback_corrections.get("crest_factor_db", 0.0)
        if gain_correction and abs(gain_correction) >= 0.1:
            config.gain_db = config.gain_db + max(-2.0, min(2.0, gain_correction))
            if not (anchor_profile and p.name == anchor_profile.name):
                config.gain_db = bound_gain_to_rough_intent(config.gain_db, anchor_gain)

        # B. Panning
        config.pan = rule.get("pan", 0.0)
        if abs(config.pan) > 1e-4:
            side = "left" if config.pan < 0 else "right"
            decisions.append(f"Panned '{p.name}' to the {side} ({abs(config.pan) * 100:.0f}%).")

        # C. High-pass filter
        hpf_freq = rule.get("highpass_hz", 0.0)
        if hpf_freq > 20.0:
            if needs_highpass(p.frequency_profile, hpf_freq):
                config.eq_bands.append({
                    "type": "highpass",
                    "frequency": hpf_freq,
                    "q": 0.707,
                    "reason": "Remove low-frequency rumble and mud",
                })
                decisions.append(f"Applied high-pass filter at {hpf_freq:.0f} Hz to '{p.name}'.")
            else:
                decisions.append(
                    f"Skipped high-pass filter on '{p.name}': already negligible energy below "
                    f"{hpf_freq:.0f} Hz -- the cut would be a no-op."
                )

        # DSP-necessity gate: decide once here (StemProfile is already
        # computed) whether the per-stem resonance scan, de-esser, and
        # vocal-lead mid-carve are worth running for THIS stem, so
        # mix_renderer.py's render loop can skip stages that would find/do
        # nothing instead of running them open-loop on every stem
        # regardless of content.
        config.needs_resonance_scan = needs_resonance_scan(p.frequency_profile)
        if not config.needs_resonance_scan:
            decisions.append(
                f"Skipped resonance scan on '{p.name}': negligible energy above 150 Hz "
                f"(nothing in the range the detector targets)."
            )
        config.needs_deesser = needs_deesser(p.frequency_profile, p.instrument)
        if config.needs_deesser:
            config.deesser = {
                "frequency_hz": 7000.0,
                "q": 2.0,
                "threshold_db": -24.0,
                "ratio": 4.0,
                "max_reduction_db": 4.0,
                "attack_ms": 2.0,
                "release_ms": 60.0,
            }
            decisions.append(f"Configured sibilance de-esser on '{p.name}' (7000 Hz, max 4.0 dB reduction).")
        config.needs_mid_carve = needs_mid_carve(p.frequency_profile)

        # Transient Shaper configuration for percussive / rhythm stems
        if p.instrument in ("drums", "snare", "kick", "percussion", "bass", "sub_bass"):
            config.transient_shaper = {
                "attack_boost_db": 2.5 if p.instrument in ("drums", "snare", "kick", "percussion") else 1.5,
                "sustain_trim_db": -0.5,
            }
            decisions.append(f"Transient shaper attack boost (+{config.transient_shaper['attack_boost_db']} dB) on '{p.name}'.")

        # D. Character EQ curves
        char_bands = rule.get("eq_character", [])
        for b in char_bands:
            config.eq_bands.append({
                "type": b["type"],
                "frequency": b["freq"],
                "gain_db": b.get("gain_db", 0.0),
                "q": b.get("q", 0.707),
                "reason": b.get("reason", "Tonal enhancement"),
            })
            if abs(b.get("gain_db", 0.0)) > 0.0:
                dir_word = "Boosted" if b["gain_db"] > 0 else "Cut"
                decisions.append(
                    f"Tonal EQ on '{p.name}': {dir_word} {abs(b['gain_db']):.1f} dB at {b['freq']:.0f} Hz "
                    f"({b.get('reason')})."
                )

        # E. Dynamics (Compressor)
        # Stage K: a stem with a real, detected existing dynamics treatment
        # (most commonly sidechain compression, e.g. bass ducking against
        # the kick) already has its envelope intentionally shaped upstream --
        # AutoMix's own rule-table compressor would fight or double-process
        # that rather than respect it. Skip the compressor stage entirely
        # for a flagged stem, matching the "measure before deciding,
        # transparent when nothing detected" discipline already used
        # elsewhere in this render chain (Stage C's dynamic EQ, Stage A's
        # probe-before-engaging crest reduction).
        stem_dynamics = (dynamics_flags or {}).get(p.name, {})
        if stem_dynamics.get("sidechain_detected"):
            comp_rule = None
            trigger = stem_dynamics.get("sidechain_trigger", "another stem")
            decisions.append(
                f"Skipped compressor on '{p.name}': existing sidechain ducking against "
                f"'{trigger}' detected (correlation {stem_dynamics.get('sidechain_correlation', 0.0):.2f}, "
                f"mean dip {stem_dynamics.get('sidechain_mean_dip_db', 0.0):.1f} dB) "
                f"-- respecting the existing treatment rather than double-processing it."
            )
        else:
            comp_rule = rule.get("compression", None)
        if comp_rule:
            # We modulate threshold based on measured crest factor to avoid over-compressing pre-compressed signals
            measured_crest = p.crest_factor_db
            target_thresh = comp_rule["threshold_db"]
            
            # If signal is already highly compressed (low crest factor < 10 dB), raise threshold
            if measured_crest < 10.0:
                adjusted_thresh = target_thresh + 6.0
                decisions.append(
                    f"Adjusted compressor threshold for '{p.name}' to {adjusted_thresh:.1f} dB (original {target_thresh} dB) "
                    f"because signal is already pre-compressed (crest factor {measured_crest:.1f} dB)."
                )
            elif measured_crest > 18.0:
                # If highly dynamic, drop threshold a bit to catch transients
                adjusted_thresh = target_thresh - 3.0
                decisions.append(
                    f"Adjusted compressor threshold for '{p.name}' to {adjusted_thresh:.1f} dB "
                    f"because signal is highly dynamic (crest factor {measured_crest:.1f} dB)."
                )
            else:
                adjusted_thresh = target_thresh

            config.compressor = {
                "ratio": comp_rule["ratio"],
                "attack_ms": comp_rule["attack_ms"],
                "release_ms": comp_rule["release_ms"],
                "threshold_db": adjusted_thresh,
                "makeup_gain_db": 0.0,
            }
            decisions.append(
                f"Configured compressor on '{p.name}': Ratio {config.compressor['ratio']}:1, "
                f"Thresh {config.compressor['threshold_db']:.1f} dB, Attack {config.compressor['attack_ms']:.0f}ms."
            )

        # F. Spatial Sends
        config.reverb_send = rule.get("reverb_send", 0.0)
        config.reverb_type = str(rule.get("reverb_type", "room"))
        config.reverb_decay_s = float(rule.get("reverb_decay_s", 1.2))
        config.delay_send = rule.get("delay_send", 0.0)
        if config.reverb_send > 0:
            decisions.append(
                f"Set {config.reverb_type} reverb on '{p.name}' to {config.reverb_send * 100:.0f}% "
                f"with {config.reverb_decay_s:.1f}s decay."
            )
        if config.delay_send > 0:
            decisions.append(f"Set delay send on '{p.name}' to {config.delay_send * 100:.0f}%.")

        # G. Stereo Width
        config.stereo_width = rule.get("stereo_width", 1.0)
        config.mono_below_hz = float(rule.get("mono_below_hz", 120.0))
        if abs(config.stereo_width - 1.0) > 1e-4:
            width_word = "widened" if config.stereo_width > 1.0 else "narrowed"
            decisions.append(f"Stereo image of '{p.name}' {width_word} to {config.stereo_width:.2f}.")

        decisions.append(
            f"Stem plan '{p.name}': gain {config.gain_db:+.1f} dB, pan {config.pan:+.2f}, "
            f"{len(config.eq_bands)} EQ band(s), compression "
            f"{'enabled' if config.compressor else 'disabled'}, reverb {config.reverb_send:.2f}, "
            f"delay {config.delay_send:.2f}, width {config.stereo_width:.2f}."
        )

        stem_configs[p.name] = config

    # 3. Apply Psychoacoustic EQ Carving based on Masking Analysis
    if masking_results and "erb_details" in masking_results:
        erb_details = masking_results["erb_details"]
        suggestions = erb_details.get("carving_suggestions", [])
        
        decisions.append(f"Analyzing {len(suggestions)} psychoacoustic masking carving suggestions.")

        for sug in suggestions:
            masker_name = sug.get("masker")
            masked_name = sug.get("masked")
            freq = sug.get("frequency_hz")

            if not masker_name or not masked_name or not freq:
                continue

            # Look up profiles of both stems
            masker_profile = next((p for p in stems_profiles if p.name.rsplit(".", 1)[0] == masker_name or p.name == masker_name), None)
            masked_profile = next((p for p in stems_profiles if p.name.rsplit(".", 1)[0] == masked_name or p.name == masked_name), None)

            if not masker_profile or not masked_profile:
                continue

            # Compare priorities
            masker_priority = INSTRUMENT_PRIORITY.get(masker_profile.instrument, 17)
            masked_priority = INSTRUMENT_PRIORITY.get(masked_profile.instrument, 17)

            # Determine who to cut (the lower priority instrument gets cut to clear room for the higher priority one)
            if masker_priority < masked_priority:
                # Masker is higher priority (e.g. Lead Vocal). We do NOT cut the masker.
                # Instead, we cut the masked instrument (e.g. Keyboard/Synth pad) to get it out of the way.
                cut_stem = masked_profile.name
                gain_reduction = -2.5
                reason = f"Avoid masking high-priority '{masker_profile.instrument}' ({masker_profile.name}) at {freq:.0f} Hz"
            else:
                # Masked instrument is higher priority. We cut the masker (lower priority) to clear room.
                cut_stem = masker_profile.name
                gain_reduction = -3.0
                reason = f"Clear room for high-priority '{masked_profile.instrument}' ({masked_profile.name}) at {freq:.0f} Hz"

            # Apply the EQ cut
            if cut_stem in stem_configs:
                # Prevent adding duplicate cuts at the exact same frequency
                dup = any(abs(b["frequency"] - freq) < 20.0 and b["type"] == "peaking" for b in stem_configs[cut_stem].eq_bands)
                if not dup:
                    stem_configs[cut_stem].eq_bands.append({
                        "type": "peaking",
                        "frequency": freq,
                        "gain_db": gain_reduction,
                        "q": 1.2,
                        "reason": reason,
                    })
                    decisions.append(
                        f"Psychoacoustic carve on '{cut_stem}': Cut {gain_reduction:.1f} dB at {freq:.0f} Hz ({reason})."
                    )

    # 4. Bus Configurations (Bus Compressor, Saturation, Limiter)
    genre_mod = GENRE_MODIFIERS.get(genre, {})
    master_mod = genre_mod.get("master_bus", {})

    bus_config = BusMixConfig()

    # A. Bus Saturation (Warmth)
    sat_db = master_mod.get("saturation_db", 0.5)
    if sat_db > 0.0:
        bus_config.saturation_drive_db = sat_db
        bus_config.saturation_mix = 0.4  # Moderate mix for master bus glue
        decisions.append(f"Master bus saturation enabled: {sat_db:.1f} dB tape-style drive (mix 40%).")

    # B. Bus Compressor (Glue compressor)
    bus_comp_ratio = master_mod.get("compression_ratio", 2.0)
    if bus_comp_ratio > 1.0:
        bus_config.bus_compressor = {
            "ratio": bus_comp_ratio,
            "attack_ms": 30.0,   # Slow attack to let transients pass
            "release_ms": 150.0, # Medium-fast release for natural pump
            "threshold_db": -12.0,
            "makeup_gain_db": 0.0,
        }
        decisions.append(
            f"Glue compressor on master bus: Ratio {bus_comp_ratio:.1f}:1, "
            f"Attack 30ms, Release 150ms, Threshold -12 dBFS."
        )

    # Multiband Compressor Crossovers (Genre-adaptive)
    low_cross = float(master_mod.get("multiband_low_hz", 200.0))
    high_cross = float(master_mod.get("multiband_high_hz", 5000.0))
    mid_rat = float(master_mod.get("multiband_mid_ratio", 1.8))
    bus_config.multiband_compressor = {
        "low_crossover_hz": low_cross,
        "high_crossover_hz": high_cross,
        "mid_ratio": mid_rat,
    }

    # C. Limiter Settings
    genre_ceiling = float(master_mod.get("limit_ceiling_db", -1.0))
    bus_config.limiter_ceiling_db = _target_ceiling_for_goal(mix_goal, genre_ceiling)
    # Master brickwall limiter ceiling set
    bus_config.limiter_threshold_db = 0.0
    decisions.append(f"Master brickwall limiter ceiling set to {bus_config.limiter_ceiling_db:.1f} dBFS.")

    # Master low-end balance correction (+4.0 dB @ 300 Hz low shelf)
    bus_config.bus_eq_bands.append({
        "type": "lowshelf",
        "frequency": 300.0,
        "gain_db": 4.0,
        "q": 0.707,
        "reason": "Default low-end balance correction: +4 dB @ 300 Hz low shelf to match commercial reference warmth."
    })
    decisions.append("Master low-end balance correction applied (+4.0 dB @ 300 Hz low shelf).")

    # D. Reference EQ Matching
    if reference_profile and "bands" in reference_profile:
        decisions.append("Applying reference track matching EQ adjustments to the master bus:")
        total_weight = 0.0
        mix_bands = {b: 0.0 for b in ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"]}
        for profile in stems_profiles:
            weight = 10 ** (profile.rms_dbfs / 20.0) if profile.rms_dbfs > -90.0 else 0.0
            total_weight += weight
            for b in mix_bands:
                mix_bands[b] += profile.frequency_profile.get(b, 0.0) * weight

        if total_weight > 0.0:
            for b in mix_bands:
                mix_bands[b] /= total_weight

        import math
        for band, center_freq in [
            ("sub", 40.0),
            ("bass", 100.0),
            ("low_mids", 250.0),
            ("mids", 1000.0),
            ("presence", 4000.0),
            ("sibilance", 7000.0),
            ("air", 12000.0)
        ]:
            ref_val = reference_profile["bands"].get(band, 0.0)
            mix_val = mix_bands.get(band, 0.0)
            
            if mix_val > 0.0 and ref_val > 0.0:
                ratio = ref_val / mix_val
                gain_db = 20 * math.log10(ratio)
                gain_db = max(-5.0, min(5.0, gain_db))
                
                if abs(gain_db) >= 0.2:
                    bus_config.bus_eq_bands.append({
                        "type": "peaking",
                        "frequency": center_freq,
                        "gain_db": round(gain_db, 2),
                        "q": 1.0,
                        "reason": f"Reference EQ Match: {band} adjusted by {gain_db:+.1f} dB to match reference track profile.",
                    })
                    decisions.append(f"  - Boosted {band} ({center_freq} Hz) by {gain_db:+.2f} dB to match reference balance.")

    plan = MixPlan(
        stems=list(stem_configs.values()),
        bus=bus_config,
        genre=genre,
        target_lufs=target_lufs,
        mix_goal=mix_goal,
        decisions_log=decisions,
    )
    
    return plan


# Shared with the per-category checks below -- previously this exact
# 4-word up/down tuple pair was retyped inline 8 times in this function
# (a plain internal DRY violation, fixed here as its own constants).
#
# Note on the *other* keyword-based feedback parser, integration/mix_intent.py's
# parse_mix_intent()/apply_intent_to_plan(): docs/automix_deep_scan_2026-07-12.md
# §4.5 flagged both as doing "the same conceptual job" and suggested routing
# this function through that one. Investigated 2026-07-13 and deliberately did
# NOT do a full merge: the two have genuinely different semantics, not just
# different keyword lists -- this function corrects multiple independent
# topics (vocals AND bass AND brightness) from a single feedback string and
# can add master-bus EQ bands, while mix_intent.py's apply_intent_to_plan()
# is single-intent-per-call, stem-only (no master-bus path), and returns a
# new plan functionally rather than mutating in place. Forcing them into one
# shape risked silently dropping the master-bus brightness/warmth handling
# that mix_intent.py has no equivalent for. The genuinely-identical part (this
# up/down word list) is deduplicated; the topic-grouping and magnitude logic
# remain intentionally distinct.
_UP_KEYWORDS = ("up", "loud", "more", "boost")
_DOWN_KEYWORDS = ("down", "quiet", "less", "cut")

# Magnitude words scale every fixed dB/level step below by this factor --
# "a little more air" should move less than a bare "more air". Keyed the
# same way integration/mix_intent.py's _MAGNITUDE_DB thinks about magnitude
# (subtle/moderate/strong), applied here as a multiplier on this function's
# own existing fixed steps rather than importing a second, differently-
# shaped system (see the design-history comment above this function on why
# the two parsers were deliberately kept separate).
_SUBTLE_WORDS = ("a little", "a bit", "slightly", "a touch", "subtle")
_STRONG_WORDS = ("a lot", "way more", "much more", "way less", "much less", "significantly", "a ton")


def _magnitude_multiplier(text: str) -> float:
    if any(w in text for w in _STRONG_WORDS):
        return 2.0
    if any(w in text for w in _SUBTLE_WORDS):
        return 0.5
    return 1.0


def _describe_applied_intent(intent: dict, feedback_text: str) -> str:
    """Human-readable change-log line matching the original single-intent
    formatting/tests exactly (each category's own wording)."""
    sign = "+" if intent.get("direction") == "up" else "-"
    parameter = intent.get("parameter", "gain_db")
    magnitude = intent.get("magnitude", "moderate")
    direction = intent.get("direction", "up")
    target_stem = intent.get("target_stem", "all")

    magnitude_db = {"subtle": 0.5, "moderate": 1.5, "strong": 3.0}
    step = round(magnitude_db.get(magnitude, 1.5), 2)
    action = "boosted" if direction == "up" else "cut"

    if parameter == "gain_db" and target_stem in ("vocal", "synth_lead"):
        return f"Vocal gain {action} by {sign}{step} dB based on feedback: '{feedback_text}'"
    if parameter == "gain_db" and target_stem in ("bass", "sub_bass", "kick"):
        return f"Bass/kick gain {action} by {sign}{step} dB based on feedback: '{feedback_text}'"
    if parameter == "gain_db" and target_stem in ("snare", "hihat", "percussion", "full_drum_bus", "drums"):
        return f"Drums gain {action} by {sign}{step} dB based on feedback: '{feedback_text}'"
    if parameter == "reverb_level":
        reverb_step = round(0.08 * (0.33 if magnitude == "subtle" else 2.0 if magnitude == "strong" else 1.0), 3)
        scope = f"on {target_stem} stems" if target_stem != "all" else "on every stem"
        return f"Adjusted reverb send level: {sign}{reverb_step} {scope} based on feedback: '{feedback_text}'"
    if parameter == "width":
        width_step = round(0.1 * (0.33 if magnitude == "subtle" else 2.0 if magnitude == "strong" else 1.0), 2)
        scope = f"on {target_stem} stems" if target_stem != "all" else "on every stem"
        return f"Adjusted stereo width: {sign}{width_step} {scope} based on feedback: '{feedback_text}'"
    if parameter == "brightness":
        return f"Added master highshelf {action if direction == 'up' else 'cut'} ({sign}{step} dB) for brightness."
    if parameter == "warmth":
        return f"Added master low-mid {action if direction == 'up' else 'cut'} ({sign}{step} dB) for warmth."
    scope = f"on {target_stem} stems" if target_stem != "all" else "on every stem"
    return f"Adjusted {parameter.replace('_', ' ')}: {sign}{step} dB {scope} based on feedback: '{feedback_text}'"


def apply_revision_feedback(plan: MixPlan, feedback_text: str) -> list[str]:
    """Parse text revision comments and apply corrections directly to the
    MixPlan (mutated in place). Returns the list of human-readable changes
    applied, so a caller can echo back what happened.

    2026-08-06 (D1.5, docs/KENN_FUTURE_PLAN.md Phase 1): a compound comment
    ("vocals louder, bass louder too") now applies EVERY distinct change it
    names, not just the first. Previously only the first matched
    stem/parameter ever applied -- silently dropping the rest -- despite a
    docstring elsewhere in this codebase (business/app/ableton_bridge.py's
    _handle_mix_revision()) incorrectly claiming this already handled
    "multi-topic feedback"; it never did, confirmed by reading this
    function's own body, which called the single-intent parser exclusively.
    """
    from audio_analysis.integration.mix_intent import parse_mix_intents, apply_intents_to_plan

    intents = parse_mix_intents(feedback_text, {})

    if not intents:
        change_desc = f"Received feedback comment: '{feedback_text}' (no automatic heuristics matched)."
        plan.decisions_log.append(change_desc)
        return []

    new_plan = apply_intents_to_plan(intents, plan)

    # Safely mutate stems in-place to preserve object reference integrity
    for old_cfg, new_cfg in zip(plan.stems, new_plan.stems):
        old_cfg.gain_db = new_cfg.gain_db
        old_cfg.stereo_width = new_cfg.stereo_width
        old_cfg.reverb_send = new_cfg.reverb_send
        old_cfg.eq_bands = new_cfg.eq_bands
        old_cfg.compressor = new_cfg.compressor
        old_cfg.gate = new_cfg.gate
        old_cfg.deesser = new_cfg.deesser
        old_cfg.transient_shaper = new_cfg.transient_shaper

    # Copy bus configuration fields
    plan.bus.bus_eq_bands = new_plan.bus.bus_eq_bands
    plan.bus.bus_compressor = new_plan.bus.bus_compressor
    plan.bus.reference_width_factor = new_plan.bus.reference_width_factor
    plan.bus.limiter_ceiling_db = new_plan.bus.limiter_ceiling_db
    plan.bus.limiter_threshold_db = new_plan.bus.limiter_threshold_db
    plan.bus.saturation_drive_db = new_plan.bus.saturation_drive_db
    plan.bus.saturation_mix = new_plan.bus.saturation_mix

    applied = [_describe_applied_intent(intent, feedback_text) for intent in intents]
    plan.decisions_log.extend(applied)
    return applied
