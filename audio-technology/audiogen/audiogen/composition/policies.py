from audiogen_core.config import resolve_config
# composition/policies.py
# Project module `policies` (composition).

from typing import Any, Dict, List, Tuple

from audiogen_core.composition_runtime_flags import stable_emotion_dynamics_enabled
from data.arp_curve_defaults import arp_mode_for_role
from data.arrangement_chord_change_params import CHORD_CHANGE_PARAMS
from data.arrangement_curves import BASE_CURVE, BOUNDARY_DEFAULTS, POP_EXT_OVERRIDES, global_curve, role_curve
from data.arrangement_forms import FORM_SEQUENCES
from data.audit import normalize_arrangement_curve
from data.emotion_anchors import anchor_curve_overrides
from data.melody_phrase_profiles import melody_phrase_contour_sequence_for_emotion
from data.emotion_profiles import arrangement_overrides_for_emotion
from data.emotion_section_role_profiles import apply_emotion_section_role_profile
from data.emotion_aliases import canonical_emotion_name
from data.music_data import EmotionProfile

from composition.section_planner.section_dynamics_stage import (
    apply_default_form_contrast_polish as _apply_default_form_contrast_polish,
    apply_final_tension_arc_dynamics,
)

# Emotion arrangement overrides are authored as "global temperament" scalars, but they were
# historically merged with dict.update(), which erased per-section role contrast (intro
# vs verse vs chorus). Multiply these onto the role curve so temperament and form both apply.
_EMOTION_ROLE_BLEND_KEYS: frozenset[str] = frozenset(
    {
        "melody_density_mult",
        "melody_total_notes_mult",
        "markov_rest_prob_mult",
        "chord_motion_mult",
        "chord_rhythm_mult",
        "arp_density_mult",
        "section_dynamic",
    }
)


_CHORUS_TEXTURE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # Chord/lead-led chorus: keep a restrained arp bed instead of removing the
    # project's core ch3 motion layer.
    "pad_hook": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.34,
        "arp_target_notes_per_bar": 4.8,
        "arp_velocity_scale": 0.72,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "chord_motion_mult": 0.94,
        "section_dynamic": 0.98,
    },
    "pad_hook_bloom": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.38,
        "arp_target_notes_per_bar": 5.2,
        "arp_velocity_scale": 0.74,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "chord_motion_mult": 0.90,
        "harmonic_color_mult": 1.06,
        "section_dynamic": 1.00,
    },
    "pad_hook_answer": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.48,
        "arp_target_notes_per_bar": 5.6,
        "arp_velocity_scale": 0.76,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "chord_motion_mult": 0.92,
        "section_dynamic": 0.99,
    },
    # Continuous motoric bed: energetic pop lift.
    "pulse_hook": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 1.18,
        "arp_target_notes_per_bar": 9.5,
        "arp_velocity_scale": 0.96,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "dialogue",
        "section_dynamic": 1.08,
    },
    "pulse_hook_lift": {
        "arp_enabled": 1.0,
        "arp_mode": "down",
        "arp_density_mult": 0.92,
        "arp_target_notes_per_bar": 6.5,
        "arp_velocity_scale": 0.88,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "dialogue",
        "section_dynamic": 1.10,
    },
    "pulse_hook_droplift": {
        "arp_enabled": 1.0,
        "arp_mode": "updown_excl",
        "arp_density_mult": 0.74,
        "arp_target_notes_per_bar": 5.0,
        "arp_velocity_scale": 0.82,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "dialogue",
        "section_dynamic": 1.12,
        "chord_motion_mult": 0.98,
    },
    # Brighter but still steady: moderate chorus bed without hard breaks.
    "steady_hook": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.78,
        "arp_target_notes_per_bar": 5.5,
        "arp_velocity_scale": 0.88,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "section_dynamic": 1.00,
    },
    "steady_hook_glide": {
        "arp_enabled": 1.0,
        "arp_mode": "down",
        "arp_density_mult": 0.62,
        "arp_target_notes_per_bar": 4.5,
        "arp_velocity_scale": 0.80,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "section_dynamic": 1.02,
        "harmonic_color_mult": 1.04,
    },
    "steady_hook_bloom": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.54,
        "arp_target_notes_per_bar": 5.6,
        "arp_velocity_scale": 0.78,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "unison",
        "section_dynamic": 1.03,
    },
    # Warm close-mic chorus: audible bed, but explicitly not a unison shadow
    # of the lead. This supports love/caring without recreating the old
    # lead/arp pitch masking issue.
    "intimate_hook_bed": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.62,
        "arp_target_notes_per_bar": 6.4,
        "arp_velocity_scale": 0.82,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "coexist",
        "chord_motion_mult": 0.94,
        "harmonic_color_mult": 1.04,
        "section_dynamic": 1.02,
    },
    "intimate_hook_answer": {
        "arp_enabled": 1.0,
        "arp_mode": "updown",
        "arp_density_mult": 0.68,
        "arp_target_notes_per_bar": 6.8,
        "arp_velocity_scale": 0.84,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "coexist",
        "chord_motion_mult": 0.96,
        "harmonic_color_mult": 1.06,
        "section_dynamic": 1.03,
    },
    # Tense answering bed: a more agitated chorus identity.
    "tense_hook": {
        "arp_enabled": 1.0,
        "arp_mode": "up",
        "arp_density_mult": 0.92,
        "arp_target_notes_per_bar": 6.5,
        "arp_velocity_scale": 0.94,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "fill",
        "section_dynamic": 1.02,
        "chord_motion_mult": 1.04,
    },
    "tense_hook_stab": {
        "arp_enabled": 1.0,
        "arp_mode": "down",
        "arp_density_mult": 0.82,
        "arp_target_notes_per_bar": 5.0,
        "arp_velocity_scale": 0.98,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "fill",
        "section_dynamic": 1.04,
        "chord_motion_mult": 1.08,
    },
    "tense_hook_lean": {
        "arp_enabled": 1.0,
        "arp_mode": "updown_excl",
        "arp_density_mult": 0.84,
        "arp_target_notes_per_bar": 5.5,
        "arp_velocity_scale": 0.86,
        "arp_mode_lock": True,
        "chorus_interaction_mode": "fill",
        "section_dynamic": 1.01,
        "chord_motion_mult": 1.06,
    },
}

_EMOTION_CHORUS_TEXTURES: Dict[str, Tuple[str, ...]] = {
    "grief": ("pad_hook", "pad_hook_bloom", "pad_hook_answer"),
    "sadness": ("pad_hook", "pad_hook_bloom", "pad_hook_answer"),
    "remorse": ("pad_hook", "pad_hook_bloom", "pad_hook_answer"),
    "relief": ("pad_hook", "pad_hook_bloom", "pad_hook_answer"),
    "disappointment": ("pad_hook", "pad_hook_bloom"),
    "love": ("intimate_hook_bed", "intimate_hook_answer", "intimate_hook_bed"),
    "caring": ("intimate_hook_bed", "intimate_hook_answer", "intimate_hook_bed"),
    "joy": ("pulse_hook", "pulse_hook_lift", "pulse_hook", "pulse_hook_lift"),
    "excitement": ("pulse_hook", "pulse_hook_lift", "pulse_hook_droplift"),
    "amusement": ("pulse_hook", "pulse_hook_lift", "pulse_hook_droplift"),
    "optimism": ("pulse_hook", "pulse_hook_lift", "pulse_hook", "pulse_hook_lift"),
    "approval": ("pulse_hook", "pulse_hook_lift", "pulse_hook", "pulse_hook_lift"),
    "pride": ("pulse_hook", "pulse_hook_lift", "pulse_hook_droplift"),
    "fear": ("tense_hook", "tense_hook_stab", "tense_hook_lean"),
    "nervousness": ("tense_hook", "tense_hook_stab", "tense_hook_lean"),
    "confusion": ("tense_hook", "tense_hook_stab", "tense_hook", "tense_hook_stab"),
    "disapproval": ("tense_hook", "tense_hook_stab", "tense_hook_lean"),
    "disgust": ("tense_hook", "tense_hook_stab", "tense_hook_lean"),
    "surprise": ("tense_hook", "tense_hook_stab", "tense_hook_lean"),
    "neutral": ("steady_hook", "steady_hook_glide", "steady_hook_bloom"),
    "admiration": ("steady_hook", "steady_hook_glide", "steady_hook_bloom"),
    "curiosity": ("steady_hook", "steady_hook_glide", "steady_hook_bloom"),
    "realization": ("steady_hook", "steady_hook_glide", "steady_hook_bloom"),
}


def _apply_chorus_texture_archetype(curve: Dict[str, Any], arch_key: str, *, authoritative: bool = False) -> None:
    spec = _CHORUS_TEXTURE_ARCHETYPES.get(str(arch_key or ""), {})
    if not spec:
        return
    curve["chorus_texture_archetype"] = str(arch_key)
    for key, val in spec.items():
        try:
            if authoritative:
                curve[key] = val
            elif key in _EMOTION_ROLE_BLEND_KEYS or key in {"arp_density_mult", "section_dynamic", "chord_motion_mult"}:
                curve[key] = float(curve.get(key, 1.0) or 1.0) * float(val)
            else:
                curve[key] = val
        except Exception:
            curve[key] = val


def _merge_emotion_arrangement_overrides(curve: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    """Layer ``overrides`` onto ``curve`` in place (role curve is already in ``curve``)."""
    for key, val in dict(overrides or {}).items():
        if key in _EMOTION_ROLE_BLEND_KEYS:
            try:
                base = float(curve.get(key, 1.0) or 1.0)
                curve[key] = base * float(val)
            except Exception:
                curve[key] = val
        else:
            curve[key] = val


def _stable_text_code(text: str) -> int:
    acc = 0
    for ch in str(text or ""):
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return int(acc)


def _apply_emotion_chorus_texture_identity(
    curve: Dict[str, Any],
    *,
    emotion_name: str,
    role: str,
    section_index: int = 0,
    role_occurrence: int = 0,
    song_seed: int = 0,
    form_mode: str = "",
) -> None:
    role_lc = str(role or "").strip().lower()
    if role_lc not in {"b", "chorus", "hook", "tag"}:
        return
    emo = canonical_emotion_name(emotion_name or "")
    options = tuple(_EMOTION_CHORUS_TEXTURES.get(emo, ()))
    if not options:
        return
    mix = (
        int(song_seed)
        ^ (_stable_text_code(emo) * 17)
        ^ (int(section_index) * 131)
        ^ (int(role_occurrence) * 977)
        ^ (_stable_text_code(str(form_mode or "")) * 53)
    ) & 0xFFFFFFFF
    option_count = max(1, len(options))
    idx = int(mix % option_count)
    if option_count > 1:
        form_offset = int(_stable_text_code(str(form_mode or "")) % option_count)
        idx = int((idx + ((mix >> 8) % option_count) + form_offset) % option_count)
    arch_key = str(options[idx])
    _apply_chorus_texture_archetype(curve, arch_key, authoritative=False)


_EMOTION_IDENTITY_LANES: Dict[str, str] = {
    "joy": "radiant_pulse",
    "excitement": "radiant_pulse",
    "amusement": "radiant_pulse",
    "optimism": "radiant_pulse",
    "approval": "radiant_pulse",
    "pride": "radiant_pulse",
    "sadness": "reflective_space",
    "grief": "reflective_space",
    "remorse": "reflective_space",
    "disappointment": "reflective_space",
    "relief": "reflective_space",
    "fear": "tense_fragment",
    "nervousness": "tense_fragment",
    "confusion": "tense_fragment",
    "disapproval": "tense_fragment",
    "disgust": "tense_fragment",
    "anger": "tense_fragment",
    "annoyance": "tense_fragment",
    "surprise": "tense_fragment",
    "love": "intimate_glow",
    "caring": "intimate_glow",
    "gratitude": "intimate_glow",
    "desire": "intimate_glow",
    "admiration": "noble_glide",
    "curiosity": "noble_glide",
    "realization": "noble_glide",
    "neutral": "noble_glide",
    "embarrassment": "guarded_pulse",
}


def _apply_default_form_emotion_identity(
    curve: Dict[str, Any],
    *,
    emotion_name: str,
    role: str,
    role_occurrence: int = 0,
    strength: float = 0.25,
) -> None:
    """Late emotion identity pass for default-form arrangement curves.

    This does not invent a new layer. It tags a production lane and nudges
    existing planner-facing knobs so emotions with similar energy no longer
    collapse into the same section texture.
    """

    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return
    emo = canonical_emotion_name(str(emotion_name or ""))
    lane = str(_EMOTION_IDENTITY_LANES.get(emo, "noble_glide"))
    role_lc = str(role or "").strip().lower()
    occ = max(1, int(role_occurrence or 1))
    curve["arrangement_emotion_identity"] = str(lane)
    curve["arrangement_emotion_identity_strength"] = float(s)

    def _f(key: str, default: float = 1.0) -> float:
        try:
            return float(curve.get(key, default) or default)
        except Exception:
            return float(default)

    def _mul(key: str, mult: float, *, lo: float | None = None, hi: float | None = None) -> None:
        val = _f(key) * (1.0 + (float(mult) - 1.0) * s)
        if lo is not None:
            val = max(float(lo), val)
        if hi is not None:
            val = min(float(hi), val)
        curve[key] = float(val)

    def _add(key: str, amount: float, *, lo: float | None = None, hi: float | None = None) -> None:
        val = _f(key, 0.0) + float(amount) * s
        if lo is not None:
            val = max(float(lo), val)
        if hi is not None:
            val = min(float(hi), val)
        curve[key] = float(val)

    def _offset(delta: float, *, lo: int = -8, hi: int = 8) -> None:
        try:
            cur = float(curve.get("melody_lane_center_offset", 0) or 0)
        except Exception:
            cur = 0.0
        curve["melody_lane_center_offset"] = int(max(int(lo), min(int(hi), round(cur + float(delta) * s))))

    chorusish = role_lc in {"b", "chorus", "hook", "tag"}
    verseish = role_lc in {"a", "verse"}

    if lane == "radiant_pulse":
        curve["arrangement_identity_texture"] = "bright_motor_hook"
        if verseish:
            _mul("melody_density_mult", 1.02, lo=0.94, hi=1.12)
            _mul("arp_density_mult", 1.05, lo=0.60, hi=1.30)
            _add("counter_melody_enabled_mult", 0.03 if occ > 1 else 0.0, hi=0.18)
        elif role_lc == "pre_chorus":
            _mul("chord_motion_mult", 1.025, lo=1.06, hi=1.22)
            _mul("arp_density_mult", 1.05, lo=0.92, hi=1.34)
        elif chorusish:
            _mul("section_dynamic", 1.012, lo=1.06, hi=1.12)
            _mul("motif_prob_mult", 1.025, lo=1.42, hi=1.76 + 0.06 * min(2.0, occ - 1))
            _mul("phrase_repeat_mult", 1.02, lo=0.82, hi=1.18 + 0.03 * min(2.0, occ - 1))
            _offset(0.5 if occ <= 1 else 1.0, hi=7)
            curve["chorus_interaction_mode"] = str(curve.get("chorus_interaction_mode", "") or "dialogue")
    elif lane == "reflective_space":
        curve["arrangement_identity_texture"] = "sparse_breath_hook"
        _mul("arrangement_variation_depth", 0.92, hi=0.24)
        if verseish:
            _mul("chord_motion_mult", 0.94, hi=0.98)
            _mul("chord_rhythm_mult", 0.96, hi=0.96)
            _mul("phrase_repeat_mult", 1.04, lo=0.70, hi=1.00)
            _add("counter_melody_enabled_mult", -0.20, hi=0.0)
        elif role_lc == "pre_chorus":
            _mul("chord_motion_mult", 0.98, hi=1.06)
            _mul("arp_density_mult", 0.97, hi=0.50)
        elif chorusish:
            _mul("melody_density_mult", 1.015, lo=0.90, hi=1.04)
            _mul("section_dynamic", 0.992, hi=1.08)
            _mul("phrase_repeat_mult", 1.04, lo=0.88, hi=1.10)
            _add("counter_melody_enabled_mult", -0.20, hi=0.02)
            if float(curve.get("arp_enabled", 0.0) or 0.0) >= 0.5:
                _mul("arp_density_mult", 0.95, hi=0.64)
                curve["arp_target_notes_per_bar"] = float(min(_f("arp_target_notes_per_bar", 5.2), 5.6))
    elif lane == "tense_fragment":
        curve["arrangement_identity_texture"] = "angular_tension_answer"
        if verseish:
            _mul("chord_motion_mult", 1.02, lo=1.00, hi=1.16)
            _mul("harmonic_color_mult", 1.025, lo=1.04, hi=1.22)
            _mul("melody_contour_variation_mult", 1.02, lo=0.92, hi=1.14)
            _add("counter_melody_enabled_mult", -0.05, hi=0.10)
        elif role_lc == "pre_chorus":
            _mul("chord_motion_mult", 1.03, lo=1.10, hi=1.24)
            _mul("harmonic_color_mult", 1.03, lo=1.08, hi=1.26)
            _mul("section_dynamic", 1.008, lo=1.04, hi=1.10)
        elif chorusish:
            _mul("motif_prob_mult", 1.015, lo=1.34, hi=1.66)
            _mul("harmonic_color_mult", 1.03, lo=1.08, hi=1.24)
            _mul("chord_motion_mult", 1.015, lo=1.00, hi=1.14)
            _mul("arp_density_mult", 0.98, hi=1.04)
            curve["chorus_interaction_mode"] = str(curve.get("chorus_interaction_mode", "") or "fill")
    elif lane == "intimate_glow":
        curve["arrangement_identity_texture"] = "warm_close_motif"
        if verseish:
            _mul("melody_density_mult", 1.015, lo=0.94, hi=1.08)
            _mul("phrase_repeat_mult", 1.035, lo=0.66, hi=1.02)
            _mul("arp_density_mult", 0.98, lo=0.50, hi=0.96)
            _add("counter_melody_enabled_mult", -0.10, hi=0.04)
        elif role_lc == "pre_chorus":
            _mul("harmonic_color_mult", 1.02, hi=1.14)
            _mul("chord_motion_mult", 1.01, hi=1.12)
        elif chorusish:
            _mul("motif_prob_mult", 1.03, lo=1.42, hi=1.72)
            _mul("phrase_repeat_mult", 1.035, lo=0.88, hi=1.12)
            _mul("melody_total_notes_mult", 0.98, hi=0.88)
            _offset(0.5, hi=6)
            if emo in {"love", "caring"}:
                # Warm emotions should reprise the hook, but not lock into
                # copy-paste final choruses. This was the main repeat outlier
                # in the seed audit, especially for caring.
                curve["phrase_repeat_mult"] = float(
                    min(_f("phrase_repeat_mult", 1.0), 0.98 if occ <= 1 else 1.10)
                )
                curve["melody_contour_variation_mult"] = float(
                    max(_f("melody_contour_variation_mult", 1.0), 0.98)
                )
                curve["chorus_interaction_mode"] = "coexist"
    elif lane == "guarded_pulse":
        curve["arrangement_identity_texture"] = "small_stutter_hook"
        _mul("section_dynamic", 0.99, hi=1.02)
        if verseish:
            _mul("melody_total_notes_mult", 0.98, hi=0.98)
            _mul("arp_density_mult", 0.96, hi=0.78)
            _add("counter_melody_enabled_mult", -0.18, hi=0.0)
        elif chorusish:
            _mul("arp_density_mult", 0.95, hi=0.78)
            curve["arp_target_notes_per_bar"] = float(min(_f("arp_target_notes_per_bar", 5.2), 5.4))
            curve["chorus_interaction_mode"] = "coexist"
    else:  # noble_glide
        curve["arrangement_identity_texture"] = "clear_gliding_form"
        if verseish:
            _mul("melody_contour_variation_mult", 1.015, lo=0.90, hi=1.08)
            _mul("arp_density_mult", 0.98, hi=1.02)
        elif role_lc == "pre_chorus":
            _mul("chord_motion_mult", 1.015, lo=1.02, hi=1.12)
        elif chorusish:
            _mul("motif_prob_mult", 1.02, lo=1.36, hi=1.66)
            _mul("phrase_repeat_mult", 1.015, lo=0.82, hi=1.08)
            _offset(0.5, hi=6)


class ArrangementPolicy:
    """Centralizes emotion-driven arrangement defaults used by the composition engine."""

    def chord_change_params(self, emotion_name: str, defaults: Dict[str, float]) -> Dict[str, float]:
        params = dict(defaults)
        params.update(CHORD_CHANGE_PARAMS.get(emotion_name.lower(), {}))
        return params

    def resolve_melody_style(self, style: str, _emotion: EmotionProfile) -> str:
        """Lead (melody channel) uses Markov lines; arpeggiated harmony is the arp bed, not ch2."""
        s = (style or "auto").strip().lower()
        if s in {"arp", "arpeggio", "arpeggiated", "chord_arp"}:
            return "markov"
        if s != "auto":
            return s
        return "markov"

    # ------------------------------------------------------------------
    # Section form & arrangement curves
    # ------------------------------------------------------------------

    _FORM_SEQUENCES: Dict[str, Tuple[str, ...]] = dict(FORM_SEQUENCES)

    def __init__(self) -> None:
        # Default arranged form used across tests and realtime defaults.
        # `default` is intentionally the simplified "layer automation" mode.
        self.form_mode: str = "default"
        self.song_identity_seed: int = 0
        self.song_primary_emotion_name: str = ""
        # Realtime override hook: allows the realtime scheduler to force a role for a specific
        # section index without mutating the global form sequence (best-effort, small map).
        self._realtime_role_overrides: Dict[int, str] = {}

    def set_realtime_role_override(self, section_index: int, role: str) -> None:
        """Best-effort: override `section_role(section_index)` for realtime scheduling."""
        try:
            i = int(section_index)
        except Exception:
            return
        r = str(role or "").strip()
        if not r:
            return
        try:
            self._realtime_role_overrides[i] = r
        except Exception:
            pass

    def set_song_identity_seed(self, seed: int | None) -> None:
        try:
            self.song_identity_seed = int(seed or 0)
        except Exception:
            self.song_identity_seed = 0

    def set_song_primary_emotion(self, emotion_name: str | None) -> None:
        try:
            from data.emotion_aliases import canonical_emotion_name

            self.song_primary_emotion_name = str(canonical_emotion_name(str(emotion_name or "")) or "")
        except Exception:
            self.song_primary_emotion_name = ""

    def clear_realtime_role_overrides_older_than(self, min_section_index: int) -> None:
        """Drop old override entries to keep the dict bounded."""
        try:
            m = int(min_section_index)
        except Exception:
            return
        try:
            keys = list(self._realtime_role_overrides.keys())
        except Exception:
            return
        for k in keys:
            try:
                if int(k) < m:
                    self._realtime_role_overrides.pop(k, None)
            except Exception:
                continue

    def section_role(self, section_index: int) -> str:
        try:
            ov = self._realtime_role_overrides.get(int(section_index))
        except Exception:
            ov = None
        if isinstance(ov, str) and ov.strip():
            return str(ov).strip()
        seq = self._FORM_SEQUENCES.get(self.form_mode) or self._FORM_SEQUENCES["default"]
        if section_index < 0:
            section_index = 0
        if section_index >= len(seq):
            return seq[-1]
        return seq[section_index]

    def _first_chorus_section_index(self) -> int:
        """Index of the first `b` role in the active form (verse/chorus lift). No `b` → 0 (bass always on)."""
        seq = self._FORM_SEQUENCES.get(self.form_mode) or self._FORM_SEQUENCES["default"]
        for i, role in enumerate(seq):
            if role == "b":
                return i
        return 0

    def chorus_occurrence_number(self, section_index: int) -> int:
        """1-based index among chorus (`b`) sections in the active form. Returns 0 if this section is not chorus."""
        seq = self._FORM_SEQUENCES.get(self.form_mode) or self._FORM_SEQUENCES["default"]
        if not seq:
            return 0
        try:
            si = max(0, int(section_index))
        except Exception:
            si = 0
        try:
            if str(self.section_role(si)).strip().lower() != "b":
                return 0
        except Exception:
            return 0
        n = 0
        try:
            for i in range(si + 1):
                if str(self.section_role(i)).strip().lower() == "b":
                    n += 1
        except Exception:
            return 0
        return int(n)

    def form_section_count(self) -> int:
        """Number of sections in the active arranged form (for harmony / cadence coupling)."""
        seq = self._FORM_SEQUENCES.get(self.form_mode) or self._FORM_SEQUENCES["default"]
        return max(1, len(seq))

    def _role_occurrence_index(self, section_index: int, role: str) -> int:
        """1-based occurrence count of `role` up to `section_index` in the active form."""
        seq = self._FORM_SEQUENCES.get(self.form_mode) or self._FORM_SEQUENCES["default"]
        role_lc = str(role or "").strip().lower()
        if not seq or not role_lc:
            return 0
        try:
            si = max(0, int(section_index))
        except Exception:
            si = 0
        n = 0
        for i in range(min(len(seq), si + 1)):
            if str(self.section_role(i)).strip().lower() == role_lc:
                n += 1
        return int(n)

    def arrangement_curve(self, section_index: int, emotion: EmotionProfile) -> Dict[str, Any]:
        """
        Returns arrangement controls for a section.

        Generation:
          - melody_density_mult, bass_enabled, drone_enabled,
            temperature_mult, motif_prob_mult, phrase_repeat_mult
          - bass_enabled: 1.0 = generate bass; 0.0 = omit bass line (intro + first verse
            until the first `b` section / chorus in the form sequence).
          - boundary_bar0_vel_mult: when set and a transition handoff exists, softens bar 0
            velocities (None = keep legacy 0.88 only on handoff).
          - boundary_first_phrase_note_mult: scales first phrase note budget after a handoff
            (1.0 = no change).
          - melody_total_notes_mult: scales Markov lead total note budget after density math.
          - melody_max_notes_per_phrase: if set, caps each phrase slice (intro/outro sparser,
            chorus/tag higher).
          - harmonic_color_mult: scales extension / interchange / secondary-dominant strength
            after role-based harmony nudges (build_section).
          - markov_rest_prob_mult: scales lead-line rest probability for phrase space.
          - chord_rhythm_mult: scales sus/half-bar chord-pad rhythm probabilities.
          - chord_motion_mult: >1 = faster harmonic rhythm (Markov + chord events); <1 = stickier pads.
            In `generate_chord_events`, combined with chord_rhythm_mult as crm * motion (same clamp
            as chord progression sampling) so pad splits track the section curve.
          - harmony_temperature_mult: scales chord Markov temperature for this section only.

        Mix (applied to MIDI velocities, 1.0 = neutral):
          - bass_vel_scale, chord_vel_scale, melody_vel_scale,
            drone_vel_scale

        Dynamics:
          - section_dynamic: multiplier for all layers after per-channel scales (fade arcs)
        """
        role = self.section_role(section_index)
        role_lc = str(role).strip().lower()
        form_sections = max(1, int(self.form_section_count()))
        try:
            section_progress = float(max(0.0, min(1.0, float(section_index) / float(max(1, form_sections - 1)))))
        except Exception:
            section_progress = 0.0
        role_occ = self._role_occurrence_index(int(section_index), role_lc)
        stable_dyn = stable_emotion_dynamics_enabled()
        # Normalize emotion scalars defensively (data/ can contain outliers).
        # This keeps "dynamic" emotions from thrashing the role curves and prevents
        # accidental data-entry mistakes from sounding like mid-song automation.
        try:
            from data.audit import normalize_emotion_scalars

            tempo_m, vel_raw, dens_m = normalize_emotion_scalars(emotion)
        except Exception:
            tempo_m = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
            vel_raw = float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)
            dens_m = float(getattr(emotion, "density", 0.5) or 0.5)

        vel_m = 1.0 if stable_dyn else float(vel_raw)
        energy = (float(tempo_m) + float(vel_m) + float(dens_m)) / 3.0

        curve = dict(BASE_CURVE)
        curve.update(global_curve(self.form_mode, energy=float(energy)))
        curve.update(role_curve(role, energy=float(energy)))

        # ------------------------------------------------------------------
        # Default pop arrangement: verse / pre / chorus contracts first.
        #
        # The form sequence is already pop-like, so the runtime curve should not
        # flatten it into generic layer automation. Keep a small whole-song build,
        # but make the section roles do the real work.
        # ------------------------------------------------------------------
        if str(self.form_mode or "").strip().lower() == "default":
            try:
                build = float(section_progress)
            except Exception:
                build = 0.0
            build = float(max(0.0, min(1.0, build)))
            emo_name = canonical_emotion_name(str(getattr(emotion, "name", "") or "neutral"))
            # ``pulse_lift``: default-form pop motion + audible verse arp/leads for most moods.
            # ``einaudi_ostinato`` only for sorrow/relief arcs (sparse ostinato is intentional).
            # neutral/gratitude/admiration/realization were starving on ~2–3 note arp caps.
            if emo_name in {
                "love",
                "caring",
                "neutral",
                "gratitude",
                "admiration",
                "realization",
                "joy",
                "optimism",
                "pride",
                "approval",
                "amusement",
                "excitement",
            }:
                song_profile = "pulse_lift"
            elif emo_name in {"sadness", "grief", "remorse", "relief"}:
                song_profile = "einaudi_ostinato"
            elif emo_name in {
                "fear", "nervousness", "confusion", "disapproval", "disgust", "surprise",
                "anger", "annoyance",
            }:
                song_profile = "tension_ladder"
            elif emo_name in {"desire", "curiosity", "embarrassment"}:
                song_profile = "glide_return"
            else:
                song_profile = "pop_flow"

            # Intro/outro keep their role signatures; automation applies primarily to song sections.
            if role_lc not in {"intro", "outro", "ending"}:
                curve["section_contrast_strength"] = 0.78
                curve["song_cohesion_strength"] = float(
                    max(0.84, min(0.97, float(curve.get("song_cohesion_strength", 0.86) or 0.86) + 0.03))
                )
                curve["theme_recall_strength"] = float(
                    max(0.84, min(0.97, float(curve.get("theme_recall_strength", 0.86) or 0.86) + 0.03))
                )
                curve["melody_contour_variation_mult"] = float(
                    min(float(curve.get("melody_contour_variation_mult", 1.0) or 1.0), 0.96 + 0.05 * build)
                )
                curve["arrangement_variation_depth"] = float(
                    min(float(curve.get("arrangement_variation_depth", 0.3) or 0.3), 0.24 + 0.06 * build)
                )

                if role_lc in {"a", "verse"}:
                    later_verse_count = max(0.0, float(role_occ - 1))
                    verse_growth = max(0.0, min(1.0, 0.14 + 0.34 * build + 0.20 * later_verse_count))
                    # Role curve ``a`` ships with ``arp_enabled=0``; gating verse arp behind
                    # near-max energy/starved nearly every emotion's **first verse** once
                    # downstream profiles (e.g. ``pop_flow``) forgot to flip the bed back on.
                    allow_verse_pulse = True
                    curve["verse_sentence_pattern"] = "statement-answer-restate-turn"
                    curve["verse_development_mode"] = "return_lift" if later_verse_count > 0.0 else "statement"
                    contour_cap = 0.90 if role_occ <= 1 else 0.84
                    curve["melody_contour_variation_mult"] = float(
                        min(float(curve.get("melody_contour_variation_mult", 1.0) or 1.0), contour_cap + 0.03 * build)
                    )
                    curve["melody_lane_center_offset"] = int(
                        round(float(curve.get("melody_lane_center_offset", 0) or 0) + min(3.0, 1.5 * later_verse_count))
                    )
                    curve["melody_density_mult"] = float(max(0.88, min(1.00, 0.92 + 0.04 * build)))
                    curve["melody_total_notes_mult"] = float(max(0.84, min(0.96, 0.88 + 0.04 * build)))
                    curve["markov_rest_prob_mult"] = float(max(0.94, min(1.06, 1.00 - 0.03 * build)))
                    curve["chord_rhythm_mult"] = float(max(0.92, min(1.02, 0.96 + 0.01 * build)))
                    curve["chord_motion_mult"] = float(max(0.90, min(1.02, 0.95 + 0.02 * build)))
                    curve["phrase_repeat_mult"] = float(
                        max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.60 + 0.10 * later_verse_count)
                    )
                    curve["motif_prob_mult"] = float(
                        max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.18 + 0.10 * later_verse_count)
                    )
                    if allow_verse_pulse:
                        curve["arp_enabled"] = 1.0
                        curve["arp_density_mult"] = float(
                            max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.52 + 0.18 * verse_growth + 0.04 * later_verse_count)
                        )
                        curve["arp_target_notes_per_bar"] = float(
                            max(float(curve.get("arp_target_notes_per_bar", 0.0) or 0.0), 3.5 + 1.6 * verse_growth + 0.35 * later_verse_count)
                        )
                        curve["arp_grid"] = float(max(float(curve.get("arp_grid", 0.5) or 0.5), 0.5))
                        curve["arp_mode_variation_prob"] = float(
                            min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.06 if role_occ <= 1 else 0.04)
                        )
                    else:
                        curve["arp_enabled"] = 0.0
                        curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.0))
                    curve["counter_melody_enabled_mult"] = 0.0 if role_occ <= 1 else float(0.08 + 0.06 * min(2.0, later_verse_count))
                    curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.00 + 0.02 * verse_growth + 0.01 * later_verse_count))
                elif role_lc == "pre_chorus":
                    curve["melody_density_mult"] = float(max(0.84, min(1.02, 0.92 + 0.04 * build)))
                    curve["melody_total_notes_mult"] = float(max(0.80, min(0.96, 0.88 + 0.04 * build)))
                    curve["markov_rest_prob_mult"] = float(max(0.90, min(1.06, 0.98 - 0.03 * build)))
                    curve["chord_rhythm_mult"] = float(max(1.00, min(1.12, 1.04 + 0.03 * build)))
                    curve["chord_motion_mult"] = float(max(1.04, min(1.18, 1.10 + 0.04 * build)))
                    curve["arp_enabled"] = 1.0
                    curve["arp_density_mult"] = float(max(0.86, min(1.06, 0.92 + 0.06 * build)))
                    curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.42))
                    curve["counter_melody_enabled_mult"] = 0.0
                    curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.05))
                elif role_lc in {"b", "chorus", "hook", "tag"}:
                    chorus_growth = max(0.0, float(role_occ - 1))
                    curve["melody_density_mult"] = float(max(0.82, min(1.00, 0.88 + 0.03 * build)))
                    curve["melody_total_notes_mult"] = float(max(0.64, min(0.82, 0.72 + 0.03 * build)))
                    curve["markov_rest_prob_mult"] = float(max(0.92, min(1.06, 0.98 - 0.02 * build)))
                    curve["chord_rhythm_mult"] = float(max(0.92, min(1.04, 0.96 + 0.02 * build)))
                    curve["chord_motion_mult"] = float(max(0.96, min(1.08, 1.00 + 0.03 * build)))
                    curve["arp_enabled"] = 1.0
                    curve["arp_density_mult"] = float(max(0.94, min(1.08, 0.98 + 0.04 * build + 0.02 * min(2.0, chorus_growth))))
                    curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.78 + 0.04 * min(2.0, chorus_growth)))
                    curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.40 + 0.04 * min(2.0, chorus_growth)))
                    curve["counter_melody_enabled_mult"] = 0.0 if role_occ <= 1 else float(0.16 + 0.06 * min(2.0, chorus_growth))
                    curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.06))
                else:
                    curve["melody_density_mult"] = float(max(0.68, min(0.98, 0.78 + 0.08 * build)))
                    curve["melody_total_notes_mult"] = float(max(0.66, min(0.94, 0.78 + 0.08 * build)))
                    curve["markov_rest_prob_mult"] = float(max(0.94, min(1.16, 1.04 - 0.04 * build)))
                    curve["chord_rhythm_mult"] = float(max(0.90, min(1.08, 0.96 + 0.04 * build)))
                    curve["chord_motion_mult"] = float(max(0.92, min(1.10, 0.98 + 0.04 * build)))

                # Counter-melody is a late layer, and only after the song shape is clear.
                late = max(0.0, min(1.0, (build - 0.62) / 0.38))
                if float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0) > 0.0:
                    curve["counter_melody_enabled_mult"] = float(
                        min(0.34, float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0) + 0.12 * late)
                    )

                # Emotion-level arrangement journeys: same form, but different song-writing behavior.
                curve["arrangement_song_profile"] = str(song_profile)
                if song_profile == "einaudi_ostinato":
                    if role_lc in {"a", "verse"}:
                        curve["arp_enabled"] = 1.0
                        curve["arp_mode"] = "up"
                        curve["arp_grid"] = float(max(float(curve.get("arp_grid", 1.0) or 1.0), 1.0))
                        curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 0.30) or 0.30), 0.34 + 0.04 * min(1.0, build)))
                        curve["arp_target_notes_per_bar"] = float(min(float(curve.get("arp_target_notes_per_bar", 2.2) or 2.2), 2.6))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.0) or 0.0), 0.02))
                        curve["chord_motion_mult"] = float(min(float(curve.get("chord_motion_mult", 1.0) or 1.0), 0.96))
                        curve["chord_rhythm_mult"] = float(min(float(curve.get("chord_rhythm_mult", 1.0) or 1.0), 0.94))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.72 + 0.08 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.34))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.94))
                        curve["melody_total_notes_mult"] = float(max(float(curve.get("melody_total_notes_mult", 0.0) or 0.0), 0.90))
                        curve["markov_rest_prob_mult"] = float(min(float(curve.get("markov_rest_prob_mult", 1.0) or 1.0), 1.00))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 1.0))
                        curve["arrangement_variation_depth"] = float(min(float(curve.get("arrangement_variation_depth", 0.3) or 0.3), 0.20))
                        curve["counter_melody_enabled_mult"] = 0.0
                    elif role_lc == "pre_chorus":
                        curve["arp_enabled"] = 1.0
                        curve["arp_mode"] = "up"
                        curve["arp_grid"] = float(max(float(curve.get("arp_grid", 0.5) or 0.5), 0.5))
                        curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.44))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.0) or 0.0), 0.03))
                        curve["chord_motion_mult"] = float(min(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.02))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.56))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.22))
                    elif role_lc in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.0) or 0.0), 0.02))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.90 + 0.04 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.52))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 2.0))
                        curve["arrangement_variation_depth"] = float(min(float(curve.get("arrangement_variation_depth", 0.3) or 0.3), 0.18))
                elif song_profile == "pulse_lift":
                    if role_lc in {"a", "verse"}:
                        curve["arp_enabled"] = 1.0
                        curve["arp_mode"] = "up"
                        curve["arp_grid"] = float(max(float(curve.get("arp_grid", 0.5) or 0.5), 0.5))
                        curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.62 + 0.08 * max(0.0, role_occ - 1)))
                        curve["arp_target_notes_per_bar"] = float(max(float(curve.get("arp_target_notes_per_bar", 0.0) or 0.0), 4.2 + 0.4 * max(0.0, role_occ - 1)))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.08))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.64 + 0.10 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.30))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.96))
                        curve["melody_total_notes_mult"] = float(max(float(curve.get("melody_total_notes_mult", 0.0) or 0.0), 0.90))
                        curve["markov_rest_prob_mult"] = float(min(float(curve.get("markov_rest_prob_mult", 1.0) or 1.0), 0.98))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 1.0 * max(0.0, role_occ - 1)))
                    elif role_lc == "pre_chorus":
                        curve["chord_motion_mult"] = float(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.14))
                        curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.98))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.10))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.18))
                    elif role_lc in {"b", "chorus", "hook", "tag"}:
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.88 + 0.06 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.56 + 0.04 * max(0.0, role_occ - 1)))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.06 if role_occ <= 1 else 0.03))
                        curve["harmonic_color_mult"] = float(min(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.06))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.94))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 2.0))
                elif song_profile == "tension_ladder":
                    if role_lc in {"a", "verse"}:
                        curve["arp_enabled"] = 1.0
                        curve["arp_mode"] = "up"
                        curve["arp_grid"] = float(max(float(curve.get("arp_grid", 0.5) or 0.5), 0.5))
                        curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.56))
                        curve["chord_motion_mult"] = float(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.02))
                        curve["harmonic_color_mult"] = float(max(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.08))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.54 + 0.06 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.18))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                    elif role_lc == "pre_chorus":
                        curve["arp_mode"] = "updown_excl"
                        curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 1.02))
                        curve["chord_motion_mult"] = float(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.16))
                        curve["harmonic_color_mult"] = float(max(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.12))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.20))
                    elif role_lc in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.07 if role_occ <= 1 else 0.04))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.82 + 0.04 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.42))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 1.0))
                elif song_profile == "glide_return":
                    if role_lc in {"a", "verse"}:
                        curve["arp_enabled"] = 1.0
                        curve["arp_mode"] = "up"
                        curve["arp_density_mult"] = float(min(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.42), 0.60))
                        curve["chord_motion_mult"] = float(min(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 0.96), 1.04))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.66))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.26))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.05))
                    elif role_lc == "pre_chorus":
                        curve["chord_motion_mult"] = float(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.08))
                        curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.76))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.18))
                    elif role_lc in {"b", "chorus", "hook", "tag"}:
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.86 + 0.04 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.46))
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.05 if role_occ <= 1 else 0.03))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 1.0))
                else:  # pop_flow
                    if role_lc in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 0.18) or 0.18), 0.06 if role_occ <= 1 else 0.03))
                        curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 0.0) or 0.0), 0.86 + 0.04 * max(0.0, role_occ - 1)))
                        curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 0.0) or 0.0), 1.48))
                        curve["melody_density_mult"] = float(max(float(curve.get("melody_density_mult", 0.0) or 0.0), 0.92))
                        curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + 1.0))
            else:
                # Outro strip-back (simple automation): reduce density/motion; arp/counter already gated off below.
                if role_lc in {"outro", "ending"}:
                    try:
                        curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0) or 1.0) * 0.72
                    except Exception:
                        curve["melody_density_mult"] = 0.72
                    try:
                        curve["melody_total_notes_mult"] = float(curve.get("melody_total_notes_mult", 1.0) or 1.0) * 0.78
                    except Exception:
                        curve["melody_total_notes_mult"] = 0.78
                    try:
                        curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0) or 1.0) * 0.86
                    except Exception:
                        curve["chord_motion_mult"] = 0.86
                    try:
                        curve["chord_rhythm_mult"] = float(curve.get("chord_rhythm_mult", 1.0) or 1.0) * 0.88
                    except Exception:
                        curve["chord_rhythm_mult"] = 0.88

        # ------------------------------------------------------------------
        # Emotion signature modulation (deterministic, emotion-dependent).
        #
        # Many emotions cluster around similar `energy`, which can cause full-song
        # macro curves (especially chorus roles) to converge. Apply a stable per-emotion
        # "signature" scalar to open up variety knobs while staying reproducible.
        # ------------------------------------------------------------------
        try:
            import hashlib as _hashlib

            en = canonical_emotion_name(str(getattr(emotion, "name", "") or "neutral"))
            digest = _hashlib.blake2b(en.encode("utf-8"), digest_size=4).digest()
            u = int.from_bytes(digest, byteorder="little", signed=False) / float(2**32 - 1)
            emo_sig = (2.0 * float(u)) - 1.0  # [-1..1]
        except Exception:
            emo_sig = 0.0
        sig_strength = resolve_config("composition", "emotion_arrangement_signature_strength", 0.55)
        var_boost = resolve_config("composition", "arrangement_variation_boost", 0.35)
        sig_strength = max(0.0, min(1.0, float(sig_strength)))
        s = float(emo_sig) * float(sig_strength)
        var_boost = max(0.0, min(1.0, float(var_boost)))

        def _mul(key: str, amount: float) -> None:
            try:
                curve[key] = float(curve.get(key, 1.0) or 1.0) * (1.0 + float(amount) * float(s))
            except Exception:
                pass

        _mul("arrangement_variation_depth", 0.40)
        _mul("arp_mode_variation_prob", 0.70)
        _mul("chord_template_diversity_mult", 0.24)
        _mul("melody_contour_variation_mult", 0.28)
        _mul("harmonic_color_mult", 0.22)
        _mul("chord_motion_mult", 0.18)
        try:
            if str(role).strip().lower() in {"b", "chorus", "hook", "tag", "a_prime", "pre_chorus"}:
                _mul("arp_density_mult", 0.16)
        except Exception:
            pass

        # Global variation boost (role-aware). This is not emotion-specific; it widens the
        # creative search space so different emotions don't collapse into similar arrangements.
        if var_boost > 1e-9:
            vb = float(var_boost)
            try:
                curve["arrangement_variation_depth"] = float(curve.get("arrangement_variation_depth", 0.5) or 0.5) * (1.0 + 0.55 * vb)
            except Exception:
                pass
            try:
                curve["arp_mode_variation_prob"] = float(curve.get("arp_mode_variation_prob", 0.18) or 0.18) * (1.0 + 0.85 * vb)
            except Exception:
                pass
            try:
                curve["chord_template_diversity_mult"] = float(curve.get("chord_template_diversity_mult", 1.0) or 1.0) * (1.0 + 0.32 * vb)
            except Exception:
                pass
            try:
                curve["melody_contour_variation_mult"] = float(curve.get("melody_contour_variation_mult", 1.0) or 1.0) * (1.0 + 0.34 * vb)
            except Exception:
                pass
            try:
                curve["harmonic_color_mult"] = float(curve.get("harmonic_color_mult", 1.0) or 1.0) * (1.0 + 0.26 * vb)
            except Exception:
                pass
            try:
                curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0) or 1.0) * (1.0 + 0.18 * vb)
            except Exception:
                pass
        # Feed global variation controls into existing runtime keys that are already consumed.
        try:
            var_depth = float(curve.get("arrangement_variation_depth", 0.5) or 0.5)
        except Exception:
            var_depth = 0.5
        var_depth = max(0.0, min(1.0, float(var_depth)))
        try:
            arp_var = float(curve.get("arp_mode_variation_prob", 0.18) or 0.18)
            curve["arp_mode_variation_prob"] = float(max(0.0, min(0.5, arp_var)))
        except Exception:
            curve["arp_mode_variation_prob"] = float(0.08 + 0.22 * var_depth)

        # ------------------------------------------------------------------
        # Recurrence-aware form shaping.
        #
        # Roles already sound different from each other; the missing contrast is
        # "same role later in the song". Push later occurrences into clearer
        # development rather than repeating the same section profile verbatim.
        # ------------------------------------------------------------------
        try:
            growth = max(0.0, float(role_occ - 1))
            late = float(section_progress)
            if role_lc == "a":
                # Later verses should feel familiar first, then developed second.
                curve["verse_sentence_pattern"] = str(curve.get("verse_sentence_pattern", "") or "statement-answer-restate-turn")
                curve["verse_development_mode"] = "return_lift" if growth > 0.0 else "statement"
                curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0)) * (1.0 + 0.02 * growth)
                curve["melody_contour_variation_mult"] = float(curve.get("melody_contour_variation_mult", 1.0)) * max(0.92, 1.0 - 0.04 * growth)
                curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0)) * (1.0 + 0.02 * growth)
                curve["phrase_repeat_mult"] = float(curve.get("phrase_repeat_mult", 1.0)) * (1.0 + 0.32 * growth)
                curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * (1.0 + 0.22 * growth)
                curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * (1.0 + 0.08 * growth)
                curve["section_dynamic"] = float(curve.get("section_dynamic", 1.0)) * (1.0 + 0.02 * growth)
                curve["counter_melody_enabled_mult"] = float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0) + (0.08 * growth)
                curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + min(3.0, 1.5 * growth)))
            elif role_lc == "pre_chorus":
                # Later lifts should still recall the first lift.
                curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0)) * (1.0 + 0.02 * growth)
                curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * (1.0 + 0.03 * growth)
                curve["temperature_mult"] = float(curve.get("temperature_mult", 1.0)) * (1.0 + 0.01 * growth)
                curve["section_dynamic"] = float(curve.get("section_dynamic", 1.0)) * (1.0 + 0.02 * growth)
                curve["cadence_strength_mult"] = float(curve.get("cadence_strength_mult", 1.0)) * max(0.78, 1.0 - 0.06 * growth)
                curve["phrase_repeat_mult"] = float(curve.get("phrase_repeat_mult", 1.0)) * (1.0 + 0.20 * growth)
                curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * (1.0 + 0.16 * growth)
            elif role_lc in {"b", "drop"}:
                # Choruses should recall strongly; later ones can get bigger without becoming new songs.
                curve["section_dynamic"] = float(curve.get("section_dynamic", 1.0)) * (1.0 + 0.03 * growth)
                curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * (1.0 + 0.02 * growth)
                curve["harmonic_color_mult"] = float(curve.get("harmonic_color_mult", 1.0)) * (1.0 + 0.03 * growth)
                curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * (1.0 + 0.26 * growth)
                curve["phrase_repeat_mult"] = float(curve.get("phrase_repeat_mult", 1.0)) * (1.0 + 0.36 * growth)
                curve["counter_melody_enabled_mult"] = float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0) + (0.08 * growth)
                curve["melody_lane_center_offset"] = int(round(float(curve.get("melody_lane_center_offset", 0) or 0) + (1.0 * growth)))
                if growth <= 0.0:
                    curve["melody_total_notes_mult"] = float(curve.get("melody_total_notes_mult", 1.0)) * 0.88
                else:
                    curve["melody_total_notes_mult"] = float(curve.get("melody_total_notes_mult", 1.0)) * max(0.84, 0.92 - 0.02 * min(2.0, growth))
            elif role_lc == "a_prime":
                # Return sections should feel developed, not just "verse again".
                curve["melody_contour_variation_mult"] = float(curve.get("melody_contour_variation_mult", 1.0)) * 1.10
                curve["harmonic_color_mult"] = float(curve.get("harmonic_color_mult", 1.0)) * 1.06
                curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * 1.08
                curve["counter_melody_enabled_mult"] = float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0) + 0.10
            elif role_lc == "tag":
                # Tags should read like peak hook recall.
                curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * 1.10
                curve["phrase_repeat_mult"] = float(curve.get("phrase_repeat_mult", 1.0)) * 0.82
                curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * 1.05
            elif role_lc == "outro":
                # Later-form outros settle down more and de-densify.
                curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0)) * (1.0 - 0.08 * late)
                curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0)) * (1.0 - 0.06 * late)
                curve["section_dynamic"] = float(curve.get("section_dynamic", 1.0)) * (1.0 - 0.04 * late)
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Default-form production profiles (intro/verse/pre/chorus/outro).
        # ------------------------------------------------------------------
        fm = str(self.form_mode or "").lower()
        if fm == "default":
            if str(role) == "intro" and int(section_index) == 0:
                try:
                    curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0)) * 0.82
                except Exception:
                    curve["melody_density_mult"] = 0.82
                try:
                    curve["phrase_repeat_mult"] = float(curve.get("phrase_repeat_mult", 1.0)) * 0.88
                except Exception:
                    curve["phrase_repeat_mult"] = 0.88
                try:
                    curve["section_dynamic"] = float(curve.get("section_dynamic", 1.0)) * 0.94
                except Exception:
                    curve["section_dynamic"] = 0.94
            elif str(role) in {"b", "chorus", "hook"}:
                curve["bass_enabled"] = 1.0
                try:
                    curve["cadence_strength_mult"] = float(max(float(curve.get("cadence_strength_mult", 1.0) or 1.0), 1.18))
                except Exception:
                    curve["cadence_strength_mult"] = 1.18
                try:
                    curve["phrase_repeat_mult"] = float(max(float(curve.get("phrase_repeat_mult", 1.0) or 1.0), 0.74))
                except Exception:
                    curve["phrase_repeat_mult"] = 0.74
                try:
                    curve["motif_prob_mult"] = float(max(float(curve.get("motif_prob_mult", 1.0) or 1.0), 1.36))
                except Exception:
                    curve["motif_prob_mult"] = 1.36

        # Snowfall-like arc: prioritize a steady bed + memorable motif recall.
        # (intro pads only; A bed introduces arp; B hook is fuller; A' breathes; B returns; outro fades.)
        if fm == "snowfall":
            if str(role) == "intro":
                # Deadmau5-style: let the arp establish early, but keep the topline sparse.
                curve["arp_enabled"] = 1.0
                try:
                    curve["arp_grid"] = float(curve.get("arp_grid", 0.5) or 0.5)
                except Exception:
                    curve["arp_grid"] = 0.5
                try:
                    curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.78))
                except Exception:
                    curve["arp_density_mult"] = 0.78
                try:
                    curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 0.30))
                except Exception:
                    curve["melody_density_mult"] = 0.30
                try:
                    curve["chord_motion_mult"] = min(float(curve.get("chord_motion_mult", 1.0)), 0.95)
                except Exception:
                    curve["chord_motion_mult"] = 0.95

            if str(role) == "a":
                # Bed: arp on, but not “sequencer-forward”; keep chords sustained.
                curve["arp_enabled"] = 1.0
                try:
                    curve["arp_grid"] = float(curve.get("arp_grid", 0.5) or 0.5)
                except Exception:
                    curve["arp_grid"] = 0.5
                try:
                    # Important: role_curve("a") may have arp_density_mult=0.0; enforce a floor so arp is audible.
                    curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 1.0) or 1.0), 1.12))
                except Exception:
                    curve["arp_density_mult"] = 1.12
                try:
                    curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 0.70))
                except Exception:
                    curve["melody_density_mult"] = 0.70
                try:
                    curve["chord_rhythm_mult"] = float(min(float(curve.get("chord_rhythm_mult", 1.0)), 0.88))
                except Exception:
                    curve["chord_rhythm_mult"] = 0.88
                try:
                    curve["chord_comping_strength_mult"] = float(min(float(curve.get("chord_comping_strength_mult", 1.0)), 0.82))
                except Exception:
                    curve["chord_comping_strength_mult"] = 0.82

            if str(role) == "b":
                # Hook: keep bed + a bit more motion, but avoid “pop chorus” punch.
                curve["arp_enabled"] = 1.0
                try:
                    curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0)), 1.03))
                except Exception:
                    curve["section_dynamic"] = 1.03
                try:
                    curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 1.0) or 1.0), 1.22))
                except Exception:
                    curve["arp_density_mult"] = 1.22
                try:
                    curve["melody_total_notes_mult"] = float(min(float(curve.get("melody_total_notes_mult", 1.0) or 1.0), 0.92))
                except Exception:
                    curve["melody_total_notes_mult"] = 0.92

            if str(role) == "a_prime":
                # Breathe: pull density down and let pads/arp carry.
                try:
                    curve["section_dynamic"] = float(min(float(curve.get("section_dynamic", 1.0)), 0.98))
                except Exception:
                    curve["section_dynamic"] = 0.98
                try:
                    curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.98))
                except Exception:
                    curve["arp_density_mult"] = 0.98
                try:
                    curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0)), 0.92))
                except Exception:
                    curve["melody_density_mult"] = 0.92

        # pop_ext: add an arp bed and thin the intro lead melody more.
        if self.form_mode == "pop_ext":
            curve["arp_enabled"] = 1.0 if role in POP_EXT_OVERRIDES["arp_enabled_roles"] else 0.0
            if role == "intro":
                intro = POP_EXT_OVERRIDES["intro"]
                curve.update(
                    {
                        "melody_density_mult": min(float(curve.get("melody_density_mult", 1.0)), float(intro["melody_density_mult"])),
                        "melody_total_notes_mult": min(float(curve.get("melody_total_notes_mult", 1.0)), float(intro["melody_total_notes_mult"])),
                        "melody_max_notes_per_phrase": min(int(curve.get("melody_max_notes_per_phrase", 12)), int(intro["melody_max_notes_per_phrase"])),
                        "arp_enabled": float(intro["arp_enabled"]),
                    }
                )
            elif role in {"a", "pre_chorus"}:
                curve.update(dict(POP_EXT_OVERRIDES["a__pre_chorus"]))
            elif role in {"b", "a_prime", "tag"}:
                curve.update(dict(POP_EXT_OVERRIDES["b__a_prime__tag"]))
            elif role == "outro":
                curve.update(dict(POP_EXT_OVERRIDES["outro"]))

        # cinematic_drop: big space + register arcs, avoid "same arpeggio everywhere".
        if fm == "cinematic_drop":
            r = str(role)
            # More space by default; let the payoff come from dynamics + harmony, not note spam.

            # Intro: sparse lead, sustained harmony, subtle bed.
            if r == "intro":
                curve["arp_enabled"] = float(min(float(curve.get("arp_enabled", 0.0) or 0.0), 1.0))
                curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 0.58))
                curve["melody_total_notes_mult"] = float(min(float(curve.get("melody_total_notes_mult", 1.0) or 1.0), 0.86))
                curve["chord_motion_mult"] = float(min(float(curve.get("chord_motion_mult", 1.0) or 1.0), 0.96))
                curve["chord_rhythm_mult"] = float(min(float(curve.get("chord_rhythm_mult", 1.0) or 1.0), 0.92))
                curve["section_dynamic"] = float(min(float(curve.get("section_dynamic", 1.0) or 1.0), 0.96))

            # Build: lift energy and color, but keep arp density controlled (tension via harmony).
            if r in {"build", "pre_chorus"}:
                curve["arp_enabled"] = 1.0
                curve["harmonic_color_mult"] = float(max(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.10))
                curve["chord_motion_mult"] = float(max(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.08))
                curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 1.10))
                curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 1.02))
                curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.05))

            # Drop / chorus: feel huge, but not busy; prefer unison-ish topline over call/response chatter.
            if r in {"drop", "b"}:
                curve["arp_enabled"] = 1.0
                curve["harmonic_color_mult"] = float(max(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.16))
                curve["chord_motion_mult"] = float(min(float(curve.get("chord_motion_mult", 1.0) or 1.0), 1.02))
                curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.96))
                curve["melody_total_notes_mult"] = float(min(float(curve.get("melody_total_notes_mult", 1.0) or 1.0), 0.98))
                curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.10))
                curve["chorus_interaction_unison_bias"] = float(max(float(curve.get("chorus_interaction_unison_bias", 0.5) or 0.5), 0.78))

            # Bridge: pull drums/bass a touch (if present), keep harmony vivid.
            if r in {"bridge", "break"}:
                curve["harmonic_color_mult"] = float(max(float(curve.get("harmonic_color_mult", 1.0) or 1.0), 1.10))
                curve["section_dynamic"] = float(min(float(curve.get("section_dynamic", 1.0) or 1.0), 1.00))
                curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.82))
                curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 0.90))

        # Default forms (except simplified `default`): enable a light arp bed in the core roles unless the emotion
        # explicitly wants a sustained/empty texture.
        if (fm not in {"default"}) and float(curve.get("arp_enabled", 0.0) or 0.0) < 0.5:
            emo = (getattr(emotion, "name", "") or "").strip().lower()
            quiet_verse_pulse = {"grief", "sadness", "remorse", "relief"}
            warm_sparse_verse = {"love", "caring"}
            if emo in quiet_verse_pulse and role in {"a", "pre_chorus"}:
                curve["arp_enabled"] = 1.0
                curve["arp_mode"] = "up"
                curve["arp_grid"] = 1.0 if role == "a" else 0.5
                curve["arp_mode_variation_prob"] = 0.0
                curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.30))
                curve["arp_target_notes_per_bar"] = float(min(float(curve.get("arp_target_notes_per_bar", 8.0) or 8.0), 2.2))
                curve["arp_velocity_scale"] = float(min(float(curve.get("arp_velocity_scale", 1.0) or 1.0), 0.72))
            elif emo in warm_sparse_verse and role in {"a", "pre_chorus"}:
                curve["arp_enabled"] = float(min(float(curve.get("arp_enabled", 0.0) or 0.0), 1.0))
                # Former caps (density<=0.42, tnpb<=2.8) read nearly silent with many
                # presets; lift to small-but-audible bed while staying under bright profiles.
                curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.72))
                curve["arp_target_notes_per_bar"] = float(min(float(curve.get("arp_target_notes_per_bar", 8.0) or 8.0), 7.25))
            elif role in {"a", "b", "pre_chorus", "a_prime", "tag"}:
                curve["arp_enabled"] = 1.0
                # For very low-energy emotions, keep the arp extremely subtle:
                # same rhythmic bed (16th grid) but low note density and low prominence.
                if emo in {"grief", "relief"}:
                    try:
                        curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * 0.55
                    except Exception:
                        curve["arp_density_mult"] = 0.55

        # Emotion anchors: stable semantic intent (texture / cadence feel / rhythm feel).
        # Applied before boundary defaults and emotion overrides so explicit overrides can win.
        try:
            curve.update(anchor_curve_overrides(emotion, section_role=role))
        except Exception:
            pass

        curve.update(BOUNDARY_DEFAULTS.get(role, {"boundary_bar0_vel_mult": 0.88, "boundary_first_phrase_note_mult": 1.0}))

        # Emotion-scoped overrides: blend temperament onto the role curve so intro/verse/chorus
        # stay distinct (plain dict.update previously flattened melody_density and dynamics).
        try:
            _merge_emotion_arrangement_overrides(curve, arrangement_overrides_for_emotion(emotion))
        except Exception:
            pass

        try:
            curve = apply_emotion_section_role_profile(
                curve,
                emotion_name=str(getattr(emotion, "name", "") or ""),
                role=str(role),
            )
        except Exception:
            pass
        try:
            _apply_emotion_chorus_texture_identity(
                curve,
                emotion_name=str(getattr(emotion, "name", "") or ""),
                role=str(role),
                section_index=int(section_index),
                role_occurrence=int(role_occ),
                song_seed=int(getattr(self, "song_identity_seed", 0) or 0),
                form_mode=str(getattr(self, "form_mode", "") or ""),
            )
        except Exception:
            pass

        # Default-style arranged forms: no arp in the first section (intro) — pads/chords
        # only; the arp bed can enter from the verse onward. Emotion x role profiles often
        # re-enable arp for intros; this override wins.
        # Note: `ambient` uses the same role sequence as `default` (see FORM_SEQUENCES
        # fallback) but keeps form_mode "ambient", so it must be listed here.
        _fm = str(self.form_mode or "").lower()
        if _fm in {"default", "ambient"} and str(role) == "intro":
            curve["arp_enabled"] = 0.0
            # Keep the intro primarily chord/pad-led, but do not hard-mute the lead:
            # emotion×role profiles and downstream contracts may still author a singable opening.

        # Ballad form: keep early sections harmonically restrained regardless of emotion.
        # Tests (and typical ballad production) expect verse color < 1.0.
        if str(self.form_mode or "").lower() == "ballad" and role in {"intro", "a"}:
            try:
                curve["harmonic_color_mult"] = float(min(float(curve.get("harmonic_color_mult", 1.0)), 0.98))
            except Exception:
                curve["harmonic_color_mult"] = 0.98

        # A/B (16-bar) development intent. This is a single scalar carried into the
        # section planner timeline targets to nudge the second half toward motion/motif
        # without adding generation attempts (RT-safe).
        base_dev = resolve_config("composition", "ab_development_strength", 0.15, float)
        base_dev = max(0.0, min(0.5, float(base_dev)))
        role_dev = {
            "intro": 0.35,
            "a": 0.85,
            "pre_chorus": 1.15,
            "b": 1.25,
            "a_prime": 1.05,
            "tag": 1.10,
            "outro": 0.45,
        }.get(str(role or "").lower(), 1.0)
        curve["ab_development_strength"] = max(0.0, min(0.5, float(base_dev) * float(role_dev)))

        # Longform contrast scheduling: every N sections, insert a controlled "breather"
        # (slightly sparser + less harmonic motion) to keep continuous playback evolving.
        n = resolve_config("composition", "contrast_every_n_sections", 4, int)
        strength = resolve_config("composition", "contrast_strength", 0.25, float)
        if n and n > 0 and int(section_index) >= 0 and (int(section_index) % int(n) == int(n) - 1):
            strength = max(0.0, min(1.0, float(strength)))
            # Density: reduce lead+arp slightly; keep bass on for continuity.
            curve["melody_total_notes_mult"] = float(curve.get("melody_total_notes_mult", 1.0)) * (1.0 - 0.25 * strength)
            curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0)) * (1.0 - 0.18 * strength)
            # Thin the arp texture without flipping the gate off (tests + players expect arp_enabled ∈ {0,1}).
            curve["arp_density_mult"] = float(curve.get("arp_density_mult", 1.0)) * (1.0 - 0.40 * strength)
            # Harmony motion: fewer changes + less color.
            curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0)) * (1.0 - 0.22 * strength)
            curve["chord_rhythm_mult"] = float(curve.get("chord_rhythm_mult", 1.0)) * (1.0 - 0.18 * strength)
            curve["harmonic_color_mult"] = float(curve.get("harmonic_color_mult", 1.0)) * (1.0 - 0.20 * strength)

        # Second and later choruses: pull away from copy-paste hooks (harmony + phrase DNA).
        try:
            rl = str(role or "").strip().lower()
            if rl == "b":
                co = int(self.chorus_occurrence_number(section_index))
                if co >= 2:
                    tier = min(float(co - 1), 4.0)
                    curve["motif_prob_mult"] = float(curve.get("motif_prob_mult", 1.0)) * (1.0 - 0.04 * tier)
                    curve["harmony_temperature_mult"] = float(curve.get("harmony_temperature_mult", 1.0)) * (
                        1.0 + 0.028 * tier
                    )
                    curve["harmonic_color_mult"] = float(curve.get("harmonic_color_mult", 1.0)) * (1.0 + 0.035 * tier)
                    curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0)) * (1.0 + 0.03 * tier)
                    curve["temperature_mult"] = float(curve.get("temperature_mult", 1.0)) * (1.0 + 0.018 * tier)
                    try:
                        base_off = float(curve.get("melody_lane_center_offset", 0) or 0)
                        curve["melody_lane_center_offset"] = int(round(min(11.0, base_off + 2.0 * tier)))
                    except Exception:
                        pass
                    curve["markov_rest_prob_mult"] = float(curve.get("markov_rest_prob_mult", 1.0)) * (
                        1.0 + 0.024 * tier
                    )
                    osc = int(co - 2) % 3
                    base_ad = float(curve.get("arp_density_mult", 1.0) or 1.0)
                    if osc == 0:
                        curve["arp_density_mult"] = base_ad * (1.02 + 0.005 * min(tier, 3.0))
                    elif osc == 1:
                        curve["arp_density_mult"] = base_ad * (0.975 - 0.005 * min(tier, 3.0))
        except Exception:
            pass

        # Chorus/hook/tag: emotion tables often cap arp_target_notes_per_bar; contrast passes
        # can thin arp_density_mult. Apply after contrast so peak sections keep a driven bed.
        try:
            rl = str(role or "").strip().lower()
            em_key = canonical_emotion_name(str(getattr(emotion, "name", "") or ""))
            if rl in {"a", "verse", "pre_chorus"}:
                quiet_written_verse = {"grief", "sadness", "remorse", "relief", "love", "caring"}
                if em_key in quiet_written_verse:
                    curve["counter_melody_enabled_mult"] = 0.0
                elif em_key in {"fear", "nervousness"}:
                    curve["counter_melody_enabled_mult"] = float(
                        min(0.10, float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0))
                    )
            if rl in {"b", "chorus", "hook", "tag"}:
                quiet = em_key in {"grief", "relief", "remorse", "sadness"}
                if float(curve.get("arp_enabled", 1.0) or 1.0) >= 0.5:
                    at = float(curve.get("arp_target_notes_per_bar", 8.0) or 8.0)
                    if quiet:
                        curve["arp_target_notes_per_bar"] = float(min(16.0, max(at, 6.2)))
                    else:
                        curve["arp_target_notes_per_bar"] = float(min(16.0, max(at, 9.25)))
                    ad = float(curve.get("arp_density_mult", 1.0) or 1.0)
                    if quiet and 0.30 <= ad < 0.92:
                        curve["arp_density_mult"] = float(min(1.15, max(ad, 0.92)))
                    elif not quiet and 0.40 <= ad < 1.15:
                        curve["arp_density_mult"] = float(min(1.65, max(ad, 1.12)))
                if em_key == "embarrassment":
                    curve["arp_target_notes_per_bar"] = float(min(float(curve.get("arp_target_notes_per_bar", 8.0) or 8.0), 5.8))
                    curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.86))
                    curve["chorus_interaction_mode"] = "coexist"
        except Exception:
            pass

        first_b = self._first_chorus_section_index()
        # Bass entrance policy:
        # - default form: bring bass in after N sections (bars_per_section each) for continuity
        fm = str(self.form_mode or "").lower()
        if fm == "default":
            wait_b = False
        else:
            wait_b = resolve_config("composition", "bass_wait_for_first_chorus", True, bool)
        delay_sections = resolve_config("composition", "bass_entry_delay_sections_default", 1, int)
        delay_sections = max(0, min(8, int(delay_sections)))
        # Default form: delay bass for the first N sections (N*bars_per_section bars),
        # but keep pre-chorus eligible to bring bass in for the lift.
        delayed_by_default = bool(self.form_mode == "default" and int(section_index) < int(delay_sections))
        bass_on = not (delayed_by_default or (wait_b and first_b > 0 and section_index < first_b))
        # Produced default arc: if bass is being delayed, still allow it in pre-chorus.
        if str(self.form_mode or "").lower() == "default" and str(role) == "pre_chorus":
            bass_on = True
        curve["bass_enabled"] = 1.0 if bass_on else 0.0
        if not str(curve.get("arp_mode", "") or "").strip():
            curve["arp_mode"] = arp_mode_for_role(role, form_mode=self.form_mode)

        # Final guardrails: clamp curve values so data outliers can't create harsh sections.
        if resolve_config("composition", "data_normalize_enabled", True, bool):
            curve = normalize_arrangement_curve(curve)
        # Final contract for simplified `default` form: the intro is chord/pad-led,
        # but allow a light lead + arp bed (avoid a dull opening).
        try:
            if str(self.form_mode or "").strip().lower() == "default" and str(role) == "intro":
                from data.emotion_profiles import section_arp_bed_suppressed

                curve["melody_density_mult"] = float(min(float(curve.get("melody_density_mult", 1.0) or 1.0), 1.05))
                curve["melody_total_notes_mult"] = float(min(float(curve.get("melody_total_notes_mult", 1.0) or 1.0), 1.10))
                if not section_arp_bed_suppressed(
                    section_emotion=emotion,
                    primary_emotion_name=str(getattr(self, "song_primary_emotion_name", "") or ""),
                ):
                    curve["arp_enabled"] = float(max(float(curve.get("arp_enabled", 0.0) or 0.0), 1.0))
                    curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.70))
        except Exception:
            pass

        # Final contract for simplified `default` form: the outro strips back.
        # (Downstream emotion/role profiles can otherwise re-densify it.)
        try:
            if str(self.form_mode or "").strip().lower() == "default" and str(role) in {"outro", "ending"}:
                curve["arp_enabled"] = 0.0
                curve["counter_melody_enabled_mult"] = 0.0
                curve["melody_density_mult"] = float(curve.get("melody_density_mult", 1.0) or 1.0) * 0.72
                curve["melody_total_notes_mult"] = float(curve.get("melody_total_notes_mult", 1.0) or 1.0) * 0.78
                curve["chord_motion_mult"] = float(curve.get("chord_motion_mult", 1.0) or 1.0) * 0.86
                curve["chord_rhythm_mult"] = float(curve.get("chord_rhythm_mult", 1.0) or 1.0) * 0.88
        except Exception:
            pass

        # Final profile clamps after normalization and global variation.
        try:
            if str(self.form_mode or "").strip().lower() == "default":
                sp = str(curve.get("arrangement_song_profile", "") or "")
                rl = str(role).strip().lower()
                ro = max(1, int(role_occ))
                if sp == "einaudi_ostinato":
                    curve["arrangement_variation_depth"] = float(min(float(curve.get("arrangement_variation_depth", 1.0) or 1.0), 0.20))
                    curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 1.0) or 1.0), 0.02 if rl in {"a", "verse", "b", "chorus", "hook", "tag"} else 0.03))
                elif sp == "pulse_lift":
                    if rl in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 1.0) or 1.0), 0.06 if ro <= 1 else 0.03))
                elif sp == "tension_ladder":
                    if rl in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 1.0) or 1.0), 0.07 if ro <= 1 else 0.04))
                elif sp == "glide_return":
                    if rl in {"b", "chorus", "hook", "tag"}:
                        curve["arp_mode_variation_prob"] = float(min(float(curve.get("arp_mode_variation_prob", 1.0) or 1.0), 0.05 if ro <= 1 else 0.03))
        except Exception:
            pass

        # Final chorus archetype reapply: chooser runs early, but song-profile shaping above can
        # overwrite arp_mode and related values. Reassert the chosen chorus execution here so
        # emotion/seed/form-specific chorus identity survives to the planner.
        try:
            rl = str(role).strip().lower()
            if rl in {"b", "chorus", "hook", "tag"}:
                arch_key = str(curve.get("chorus_texture_archetype", "") or "")
                if arch_key:
                    _apply_chorus_texture_archetype(curve, arch_key, authoritative=True)
        except Exception:
            pass

        # Late default-form polish: after the emotion/chorus identity is fixed, shape the
        # macro role contrast so full renders read as song sections instead of adjacent loops.
        try:
            if str(self.form_mode or "").strip().lower() == "default":
                contrast_s = resolve_config("composition", "default_form_contrast_polish_strength", 0.62, float)
                contrast_enabled = resolve_config("composition", "default_form_contrast_polish_enabled", True, bool)
                identity_s = resolve_config("composition", "default_form_emotion_identity_strength", 0.25, float)
                identity_enabled = resolve_config("composition", "default_form_emotion_identity_enabled", True, bool)
                if contrast_enabled:
                    _apply_default_form_contrast_polish(
                        curve,
                        emotion_name=str(getattr(emotion, "name", "") or ""),
                        role=str(role),
                        role_occurrence=int(role_occ),
                        section_progress=float(section_progress),
                        strength=float(contrast_s),
                    )
                if identity_enabled:
                    _apply_default_form_emotion_identity(
                        curve,
                        emotion_name=str(getattr(emotion, "name", "") or ""),
                        role=str(role),
                        role_occurrence=int(role_occ),
                        strength=float(identity_s),
                    )
        except Exception:
            pass

        try:
            apply_final_tension_arc_dynamics(
                curve,
                role=str(role),
                section_emotion_name=str(getattr(emotion, "name", "") or ""),
                song_primary_emotion_name=str(getattr(self, "song_primary_emotion_name", "") or ""),
            )
        except Exception:
            pass

        try:
            if str(self.form_mode or "").strip().lower() == "default":
                rl = str(role or "").strip().lower()
                em_key = canonical_emotion_name(str(getattr(emotion, "name", "") or ""))
                if rl in {"a", "verse"} and em_key in {"joy", "excitement", "optimism", "pride", "amusement", "admiration", "approval", "gratitude", "love", "surprise"}:
                    curve["section_dynamic"] = float(max(float(curve.get("section_dynamic", 1.0) or 1.0), 1.0))
        except Exception:
            pass

        # Anchor + override guard for arp suppression.
        #
        # `EMOTION_ANCHORS` (`arp_allowed=False`) and `EMOTION_ARRANGEMENT_OVERRIDES`
        # (`arp_enabled=0.0`) are the two authored ways an emotion can opt out of the
        # arp bed entirely (e.g. fear, disgust, annoyance). Earlier passes —
        # the role-curve table, default-form intro contract, chorus texture archetype
        # (especially the `tense_hook` family used by fear/disgust), and the
        # final authoritative chorus-archetype reapply — can each flip
        # `arp_enabled` back to 1.0. This block is the single choke point that
        # restores the authored intent so the planner's arp gate stays closed.
        try:
            from data.emotion_profiles import emotion_arp_bed_suppressed

            emotion_name_lc = canonical_emotion_name(str(getattr(emotion, "name", "") or ""))
            primary_name_lc = canonical_emotion_name(str(getattr(self, "song_primary_emotion_name", "") or ""))
            section_arp_off = bool(emotion_arp_bed_suppressed(emotion))
            primary_arp_off = bool(primary_name_lc) and bool(emotion_arp_bed_suppressed(primary_name_lc))
            anchor_arp_off = bool(section_arp_off or primary_arp_off)
            rl = str(role or "").strip().lower()
            tense_chorus_arp = rl in {"b", "chorus", "hook", "tag"} and (
                primary_name_lc in {"annoyance", "disgust"}
                or (not primary_name_lc and emotion_name_lc in {"annoyance", "disgust"})
            )
            if anchor_arp_off and tense_chorus_arp:
                # These emotions should stay sparse in verses, but the chorus
                # still needs the project-defining arp layer. Keep it tense and
                # clipped rather than bright/bubbly.
                curve["arp_enabled"] = 1.0
                curve["arp_mode"] = "downup"
                curve["arp_grid"] = 0.25
                curve["arp_density_mult"] = float(max(float(curve.get("arp_density_mult", 0.0) or 0.0), 0.74))
                curve["arp_target_notes_per_bar"] = float(
                    max(float(curve.get("arp_target_notes_per_bar", 0.0) or 0.0), 5.6)
                )
                curve["arp_velocity_scale"] = float(max(float(curve.get("arp_velocity_scale", 0.0) or 0.0), 0.78))
            elif anchor_arp_off:
                curve["arp_enabled"] = 0.0
                curve["arp_density_mult"] = 0.0
                curve["arp_target_notes_per_bar"] = 0.0
                curve["arp_velocity_scale"] = 0.0
        except Exception:
            pass

        # Final masking-focused chorus cap. Keep this late so earlier style,
        # archetype, and contrast passes cannot re-inflate the softer
        # embarrassment chorus bed.
        try:
            rl = str(role or "").strip().lower()
            em_key = canonical_emotion_name(str(getattr(emotion, "name", "") or ""))
            if rl in {"b", "chorus", "hook", "tag"} and float(curve.get("arp_enabled", 1.0) or 1.0) >= 0.5:
                if em_key == "embarrassment":
                    curve["arp_target_notes_per_bar"] = float(min(float(curve.get("arp_target_notes_per_bar", 8.0) or 8.0), 5.8))
                    curve["arp_density_mult"] = float(min(float(curve.get("arp_density_mult", 1.0) or 1.0), 0.86))
                    curve["chorus_interaction_mode"] = "coexist"
        except Exception:
            pass

        # Hard guarantee: arrangement curves never author FX automation.
        for _k in (
            "fx_return_mult",
            "reverb_send_mult",
            "delay_send_mult",
            "distortion_send_mult",
            "texture_fx_gesture_mult",
        ):
            try:
                curve.pop(_k, None)
            except Exception:
                pass

        return curve

class MelodyGenerationPolicy:
    """Emotion-specific melody shaping rules extracted from the melody mixin."""

    _MELODY_PARAM_MAP: Dict[str, Tuple[float, float]] = {
        # (temperature_mult, density_mult)
        "admiration": (0.40, 0.86),
        "amusement": (0.72, 1.22),
        "anger": (0.66, 1.12),
        "annoyance": (0.62, 0.96),
        "approval": (0.50, 1.00),
        "caring": (0.34, 0.74),
        "confusion": (0.68, 0.92),
        "curiosity": (0.66, 1.12),
        "desire": (0.46, 0.98),
        "disappointment": (0.30, 0.76),
        "disapproval": (0.60, 0.86),
        "disgust": (0.70, 0.98),
        "embarrassment": (0.36, 0.56),
        "excitement": (0.70, 1.34),
        "fear": (0.70, 0.94),
        "gratitude": (0.38, 0.82),
        "grief": (0.30, 0.72),
        "joy": (0.66, 1.28),
        "love": (0.38, 0.80),
        "nervousness": (0.68, 1.16),
        "optimism": (0.58, 1.18),
        "pride": (0.50, 0.96),
        "realization": (0.38, 0.78),
        "relief": (0.30, 0.66),
        "remorse": (0.34, 0.88),
        "sadness": (0.36, 0.90),
        "surprise": (0.74, 1.18),
        "calm": (0.24, 0.54),
        "peaceful": (0.30, 0.58),
        "serenity": (0.30, 0.58),
        "neutral": (0.46, 0.96),
    }

    def melody_params(self, emotion: EmotionProfile) -> Tuple[float, float]:
        name = emotion.name.lower()
        density = emotion.density
        tempo_mult = emotion.tempo_multiplier

        if name in self._MELODY_PARAM_MAP:
            temp_mult, density_mult = self._MELODY_PARAM_MAP[name]
        else:
            density_mult = 0.8 + 0.4 * density
            temp_mult = 0.35 + 0.25 * tempo_mult

        temp_mult = max(0.2, min(0.7, temp_mult))
        density_mult = max(0.5, min(1.5, density_mult))
        return temp_mult, density_mult

    def phrase_contours(
        self,
        emotion: EmotionProfile,
        phrases_per_section: int,
        *,
        section_role: str | None = None,
    ) -> List[str]:
        return melody_phrase_contour_sequence_for_emotion(
            emotion.name.lower(),
            phrases_per_section,
            section_role=section_role,
        )