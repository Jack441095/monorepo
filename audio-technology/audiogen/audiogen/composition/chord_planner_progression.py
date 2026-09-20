# composition/chord_planner_progression.py
"""Top-layer progression generation for ChordPlanner.

Split 2026-07-14 from the single 2,065-line chord_planner.py (see
chord_planner_bias.py for the full split rationale). This is the top of the
call graph: `prepare_chord_progression` and `generate_chord_progression`
call into every lower layer (`self.generate_chord_progression`,
`self.sample_next_simplified_chord`, `self.restore_chord_extension`, and the
leaf bias/token helpers, all via `self.`) plus extensive `self.owner` state.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config
from audiogen_core.composition_runtime_flags import markov_style_strength, phrase_length_bars_clamped

from composition.harmony_pacing import apply_harmony_pacing_to_tokens, harmony_pacing_for_section
from composition.intent_context import IntentContext
from data.audit import normalize_progression_pool
from data.emotion_anchors import anchors_for_emotion
from data.harmony_profiles import harmony_profile_for_emotion
from data.music_data import EmotionProfile, chord_progression_pool_for_section_role, get_root

from .protocols import MarkovChain


class _ChordProgressionMixin:
    """Generates and shapes full chord progressions for a section."""

    def prepare_chord_progression(
        self,
        emotion: EmotionProfile,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]],
        temperature: float,
        chord_progression: Optional[List[str]],
        section_role: Optional[str] = None,
        *,
        section_index: int = 0,
        form_section_count: int = 1,
        chord_motion_mult: float = 1.0,
        harmony_temperature_mult: float = 1.0,
        cadence_strength_mult: float = 1.0,
    ) -> Tuple[List[str], List[int]]:
        tonal_offset = self._section_tonal_center_offset(
            section_index=int(section_index),
            form_section_count=int(form_section_count),
        )
        shifted_root = int(root_note) + int(tonal_offset)
        # Keep in a practical harmonic range.
        while shifted_root < 36:
            shifted_root += 12
        while shifted_root > 84:
            shifted_root -= 12
        try:
            setattr(self.owner, "_section_tonal_center_offset", int(tonal_offset))
        except Exception:
            pass
        if chord_progression is not None:
            chords = chord_progression
            roots = [int(shifted_root) + get_root(ch) for ch in chords]
            return chords, roots

        chords, roots = self.generate_chord_progression(
            emotion,
            int(shifted_root),
            bars,
            key_changes,
            temperature,
            section_role=section_role,
            section_index=section_index,
            form_section_count=form_section_count,
            chord_motion_mult=chord_motion_mult,
            harmony_temperature_mult=harmony_temperature_mult,
        )
        if not chords:
            return [], []
        # ------------------------------------------------------------
        # Tension-controlled harmonic color (extensions/interchange/secondary dom).
        # Default is no-op unless harmony_tension_control_strength > 0.
        # ------------------------------------------------------------
        ht = resolve_config("composition", "harmony_tension", None)
        if ht is not None:
            strength = max(0.0, min(1.0, float(getattr(ht, "strength", 0.0) or 0.0)))
            low_cap = max(0.0, min(1.0, float(getattr(ht, "color_cap_low", 1.0) or 1.0)))
            high_cap = max(0.0, min(1.0, float(getattr(ht, "color_cap_high", 1.0) or 1.0)))
        else:
            strength = 0.0
            low_cap, high_cap = 1.0, 1.0
        cap_dbg = None
        if strength > 1e-6:
            # Style profile color allowance (blended by markov_style_strength).
            style_cap = 1.0
            s = markov_style_strength()
            if s > 1e-6:
                try:
                    from composition.markov_style_profiles import style_profile_for_emotion_and_role

                    prof = style_profile_for_emotion_and_role(str(getattr(emotion, "name", "") or ""), str(section_role or ""))
                    allow = float(getattr(prof, "harmony_color_allowance", 0.5) or 0.5)
                    allow = max(0.0, min(1.0, float(allow)))
                    # Map 0..1 allowance to 0.75..1.15 cap (then blend by strength).
                    target = 0.75 + 0.40 * float(allow)
                    style_cap = 1.0 + (float(target) - 1.0) * float(s)
                except Exception:
                    style_cap = 1.0
            # Average tension from the section target profile (best-effort).
            try:
                prof = getattr(self.owner, "_section_tension_profile", None)
            except Exception:
                prof = None
            tavg = 0.85
            if isinstance(prof, list) and prof:
                try:
                    vals = [float(v) for v in prof if v is not None]
                    if vals:
                        tavg = float(sum(vals) / max(1, len(vals)))
                except Exception:
                    tavg = 0.85
            tavg = float(max(0.0, min(1.35, float(tavg))))
            t01 = float(max(0.0, min(1.0, (float(tavg) - 0.45) / 0.90)))
            cap = float(low_cap + (high_cap - low_cap) * float(t01))
            # Hysteresis smoothing (avoid bar-to-bar thrash across sections).
            try:
                prev = getattr(self.owner, "_last_harmony_color_cap", None)
                prev = float(prev) if prev is not None else None
            except Exception:
                prev = None
            if prev is not None:
                cap = float(0.70 * float(prev) + 0.30 * float(cap))
            # Apply style cap after hysteresis so it's stable per section.
            cap = float(max(0.0, min(1.0, float(cap) * float(style_cap))))
            try:
                setattr(self.owner, "_last_harmony_color_cap", float(cap))
            except Exception:
                pass
            cap_dbg = float(cap)
            # Blend toward cap by `strength` (1.0 = full cap, 0.0 = no-op).
            scale = float(1.0 + (float(cap) - 1.0) * float(strength))
            scale = float(max(0.0, min(1.0, scale)))
            with self.owner.snapshot_settings("extension_prob", "interchange_prob", "secondary_dominant_prob"):
                try:
                    self.owner.extension_prob = float(self.owner.extension_prob) * float(scale)
                    self.owner.interchange_prob = float(self.owner.interchange_prob) * float(scale)
                    self.owner.secondary_dominant_prob = float(self.owner.secondary_dominant_prob) * float(scale)
                except Exception:
                    pass
                chords = self.owner._apply_advanced_harmony(chords, emotion)
        else:
            chords = self.owner._apply_advanced_harmony(chords, emotion)
        # Export for debug trace.
        try:
            if cap_dbg is not None:
                setattr(self.owner, "_debug_harmony_color_cap", float(cap_dbg))
        except Exception:
            pass

        # Functional cadence shaping (lightweight, role-aware).
        # If emotion provides cadence_progressions, use them to steer phrase endings:
        # - verses (`a`) tend to avoid full closure
        # - choruses/returns (`b`, `a_prime`, `tag`, `outro`) cadence more strongly
        # - bridge-like `b` (late `b` before a return/tag/outro) prefers a deceptive resolution
        try:
            cadences = list(getattr(emotion, "cadence_progressions", None) or [])
        except Exception:
            cadences = []
        r = (section_role or "").lower() if section_role else ""
        try:
            next_role = str(getattr(self.owner, "_next_section_role_hint", "") or "").strip().lower()
        except Exception:
            next_role = ""
        dest_enabled = resolve_config("composition", "harmonic_destination_planner_enabled", True, bool)
        dest_strength = resolve_config("composition", "harmonic_destination_planner_strength", 0.72, float)
        dest_strength = max(0.0, min(1.0, float(dest_strength)))
        profile = harmony_profile_for_emotion(emotion.name)
        cadence_strength = max(0.72, min(1.28, float(profile.get("cadence_strength", 1.0))))
        deceptive_strength = max(0.55, min(1.35, float(profile.get("deceptive_strength", 1.0))))
        # Global macro cadence knob: scales emotion profile cadence strength.
        # Section-role cadence intent: scale cadence strength per role (cheap but effective).
        # - pre_chorus: avoid full closure (keeps lift into chorus)
        # - a/verse: medium (unless last section)
        # - b/chorus/outro: stronger closure
        r_lc = (section_role or "").lower() if section_role else ""
        role_mult = {
            "intro": 0.82,
            "a": 0.95,
            "pre_chorus": 0.72,
            "b": 1.18,
            "a_prime": 1.08,
            "tag": 1.10,
            "outro": 1.25,
        }.get(r_lc, 1.0)
        try:
            cadence_strength *= float(role_mult) * float(max(0.25, min(2.0, float(cadence_strength_mult))))
        except Exception:
            cadence_strength *= float(role_mult)
        # Song blueprint cadence style override (narrative-scale cadence contracts).
        cad_first = resolve_config("composition", "cadence_first_harmony_enabled", True, bool)
        cad_first_strength = resolve_config("composition", "cadence_first_harmony_strength", 0.78, float)
        cad_first_strength = max(0.0, min(1.0, float(cad_first_strength)))
        if cad_first and cad_first_strength > 1e-6:
            try:
                bp_style = str(getattr(self.owner, "_song_blueprint_cadence_style", "") or "").strip().lower()
            except Exception:
                bp_style = ""
            if bp_style in {"closed", "authentic"}:
                cadence_strength *= float(1.0 + 0.18 * cad_first_strength)
                deceptive_strength *= float(1.0 - 0.12 * cad_first_strength)
            elif bp_style in {"open"}:
                cadence_strength *= float(1.0 - 0.16 * cad_first_strength)
                deceptive_strength *= float(1.0 + 0.10 * cad_first_strength)
            elif bp_style in {"deceptive"}:
                deceptive_strength *= float(1.0 + 0.24 * cad_first_strength)
                cadence_strength *= float(1.0 - 0.08 * cad_first_strength)

        def _is_tonic(sym: str) -> bool:
            s = (sym or "").strip()
            return s.startswith("I") or s.startswith("i")

        def _deceptive_tonic(sym: str) -> str:
            # Very lightweight roman-numeral transform:
            # major tonic (I...) -> vi..., minor tonic (i...) -> VI...
            s = (sym or "").strip()
            if s.startswith("I"):
                return "vi"
            if s.startswith("i"):
                return "VI"
            return "vi"

        is_last_section = int(section_index) >= max(0, int(form_section_count) - 1)
        try:
            dest = getattr(self.owner, "_section_harmonic_destination", None)
        except Exception:
            dest = None
        if not isinstance(dest, dict):
            dest = self.section_harmonic_destination(
                section_role=section_role,
                next_role=next_role,
                is_last_section=bool(is_last_section),
            )
        if dest_enabled and dest_strength > 1e-6:
            try:
                cbm = float(dest.get("cadence_bias_mult", 1.0) or 1.0)
                dbm = float(dest.get("deceptive_bias_mult", 1.0) or 1.0)
                cadence_strength *= float(1.0 + (cbm - 1.0) * dest_strength)
                deceptive_strength *= float(1.0 + (dbm - 1.0) * dest_strength)
            except Exception:
                pass
        # Best-effort bridge detector: in longer forms, the last few sections often contain a bridge.
        bridge_like_b = bool(r == "b" and int(form_section_count) >= 8 and int(section_index) >= int(form_section_count) - 4)

        if cadences and len(chords) >= 2:
            rng = getattr(self.owner, "rng", random)
            phrase_len = phrase_length_bars_clamped(1, 16)
            cadence_windows = []
            for end_bar in range(phrase_len - 1, len(chords), phrase_len):
                if end_bar - 1 < 0:
                    continue
                cadence_windows.append((end_bar - 1, end_bar))
            if cadence_windows and cadence_windows[-1][1] != len(chords) - 1:
                cadence_windows.append((len(chords) - 2, len(chords) - 1))

            for penult_idx, final_idx in cadence_windows:
                # Filter cadences by anchor archetype when possible.
                try:
                    anc = anchors_for_emotion(emotion)
                    cad_style_base = str(getattr(anc, "cadence", "authentic") or "authentic").lower()
                except Exception:
                    cad_style_base = "authentic"

                # Cadence vocabulary scheduling for 16-bar sections:
                # bars 7-8: allow a mid-cadence type (often deceptive/suspended)
                # bars 15-16: use the anchor cadence archetype (strong resolution or intentional openness).
                cad_style = str(cad_style_base)
                try:
                    if int(len(chords)) == 16 and int(final_idx) == 7 and int(final_idx) != (len(chords) - 1):
                        # Mid cadence: prefer a \"question\" cadence.
                        if cad_style_base in {"avoid", "suspended"}:
                            cad_style = "suspended"
                        elif cad_style_base in {"plagal"}:
                            cad_style = "plagal"
                        else:
                            # Default emotions: deceptive is a strong mid-form signal.
                            # Use deceptive_strength to scale how often we choose it.
                            if rng.random() < min(0.85, 0.55 * float(deceptive_strength)):
                                cad_style = "avoid"  # treat as \"avoid tonic\" -> deceptive pair transform below
                            else:
                                cad_style = "authentic"
                except Exception:
                    cad_style = str(cad_style_base)

                cands = list(cadences)
                if cad_style == "plagal":
                    cands = [c for c in cands if c and any(str(x).strip().lower().startswith("iv") for x in c[:1])] or cands
                elif cad_style == "suspended":
                    cands = [c for c in cands if c and any("sus" in str(x).lower() for x in c)] or cands
                elif cad_style == "avoid":
                    # Prefer cadences that do NOT end on tonic if present.
                    cands = [c for c in cands if c and len(c) >= 2 and not _is_tonic(str(c[-1]))] or cands

                cadence = list(rng.choice(cands) or [])
                if len(cadence) < 2:
                    continue
                pair = list(cadence[-2:])
                is_section_final_pair = final_idx == len(chords) - 1
                # Anchor cadence archetype: "avoid" and "suspended" should resist full tonic closure.
                if cad_style in {"avoid", "suspended"}:
                    if _is_tonic(str(pair[-1])):
                        pair = self._deceptive_cadence_pair(pair)
                if r in {"pre_chorus"} and not is_section_final_pair:
                    pair = self._deceptive_cadence_pair(pair)
                # Next-role planning:
                # - verse -> pre_chorus: avoid full tonic closure (keep it open)
                # - pre_chorus -> chorus: strongly avoid tonic closure (dominant pull)
                # - chorus/tag -> outro: prefer closure
                if next_role in {"pre_chorus"} and r in {"a"} and is_section_final_pair:
                    pair = self._deceptive_cadence_pair(pair)
                if next_role in {"b", "chorus", "hook"} and r in {"pre_chorus"} and is_section_final_pair:
                    # Ensure the pre-chorus doesn't resolve fully before the chorus.
                    if _is_tonic(str(pair[-1])):
                        pair = self._deceptive_cadence_pair(pair)
                    # Also bias toward a dominant-feeling penultimate chord so the chorus lands.
                    try:
                        if len(pair) >= 2:
                            # If we somehow ended up with tonic-ish penultimate, push it to V7.
                            if str(pair[0]).strip().startswith(("I", "i")):
                                pair[0] = "V7"
                    except Exception:
                        pass
                if next_role in {"outro", "ending"} and r in {"b", "tag", "a_prime"} and is_section_final_pair:
                    # Prefer a more closed cadence heading into the ending.
                    if not _is_tonic(str(pair[-1])):
                        # Best-effort: flip back toward tonic by using the cadence pair as-is.
                        pass
                if dest_enabled and dest_strength > 1e-6 and is_section_final_pair:
                    try:
                        target_degree = dest.get("target_degree", None)
                        arrival_type = str(dest.get("arrival_type", "neutral") or "neutral").lower()
                    except Exception:
                        target_degree = None
                        arrival_type = "neutral"
                    if target_degree == 4 or arrival_type in {"open", "lift"}:
                        if _is_tonic(str(pair[-1])):
                            pair = self._deceptive_cadence_pair(pair)
                        if len(pair) >= 2 and str(pair[0]).strip().startswith(("I", "i")):
                            pair[0] = "V7"
                    elif target_degree == 0 and arrival_type in {"closed", "return"}:
                        if len(pair) >= 2 and not _is_tonic(str(pair[-1])):
                            pair[-1] = "I" if str(pair[-1]).strip()[:1].isupper() else "i"
                    elif arrival_type == "release":
                        if len(pair) >= 2 and str(pair[0]).strip().startswith(("V", "v")):
                            pair[0] = "ii"
                elif r in {"a"} and not is_last_section:
                    if rng.random() < min(0.92, 0.75 * deceptive_strength):
                        pair = self._deceptive_cadence_pair(pair)
                elif r in {"b", "a_prime", "tag", "outro"} and bridge_like_b and is_section_final_pair:
                    pair = self._deceptive_cadence_pair(pair)
                elif r in {"intro", "answer", ""} and rng.random() < max(0.0, 0.16 * (deceptive_strength - 1.0)):
                    pair = self._deceptive_cadence_pair(pair)

                c2 = str(pair[0])
                c1 = str(pair[1])
                weight = 0.0
                if r in {"b", "a_prime", "tag", "outro"}:
                    weight = 1.0 if is_section_final_pair else 0.58
                elif r == "pre_chorus":
                    weight = 0.78 if is_section_final_pair else 0.52
                elif r == "a":
                    weight = 0.64 if is_last_section and is_section_final_pair else 0.34
                else:
                    weight = 0.28 if is_section_final_pair else 0.18

                weight *= cadence_strength
                weight = max(0.0, min(1.0, weight))
                if rng.random() < weight:
                    chords[penult_idx] = c2
                    chords[final_idx] = c1

        # Harmonic hook restatement: if we captured a chorus/tag cadence signature earlier,
        # optionally restate it on later chorus/tag sections so harmony has a recognizable hook.
        try:
            sig = getattr(self.owner, "_harmonic_hook_signature", None)
        except Exception:
            sig = None
        if sig and r in {"b", "tag"} and len(chords) >= 2:
            enabled = resolve_config("composition", "hook_restatement_enabled", True, bool)
            hs = resolve_config("composition", "motif_use_chance", 0.5, float)
            # Realtime recap intent: when the form scheduler marks this as a recap/tag moment,
            # increase the probability of restating the harmonic hook (but don't force).
            try:
                ctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
            except Exception:
                ctx = {}
            try:
                recap_intent = bool(ctx.get("rt_recap_intent", False))
            except Exception:
                recap_intent = False
            try:
                rt_special = str(ctx.get("rt_special_event", "") or "").strip().lower()
            except Exception:
                rt_special = ""
            try:
                pair = list(sig.get("pair", []) or [])
            except Exception:
                pair = []
            if enabled and len(pair) >= 2:
                # Prefer restating on later sections (avoid overriding the very first statement).
                try:
                    p = max(0.0, min(0.95, 0.25 + 0.55 * float(hs)))
                    if r == "tag":
                        p = min(0.95, p + 0.12)
                    if recap_intent or rt_special == "tag_recap":
                        p = min(0.95, p + 0.25)
                    do = rng.random() < float(p)
                except Exception:
                    do = False
                if do:
                    chords[-2] = str(pair[-2])
                    chords[-1] = str(pair[-1])

        # Transition handoff: bias early chords toward common tones with outgoing harmony.
        # This stays lightweight (small candidate pool, few bars) so it doesn't add runtime cost.
        try:
            ctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
            prev_pcs = ctx.get("previous_chord_pcs")
        except Exception:
            prev_pcs = None
        # Only treat this as a handoff when the previous emotion differs.
        try:
            prev_name = str(ctx.get("previous_emotion_name", "") or "").strip().lower()
        except Exception:
            prev_name = ""
        cur_name = str(getattr(emotion, "name", "") or "").strip().lower()
        is_handoff = bool(prev_name and cur_name and prev_name != cur_name)
        if is_handoff and prev_pcs and chords:
            min_common = resolve_config("composition", "transition_common_tone_min", 1, int)
            hold_bars = resolve_config("composition", "transition_bridge_hold_bars", 1, int)
            try:
                pivot_strategy = str(ctx.get("handoff_pivot_strategy", "") or "").strip().lower()
            except Exception:
                pivot_strategy = ""
            if pivot_strategy == "common_tone":
                min_common = int(min_common) + 1
            elif pivot_strategy == "pedal":
                hold_bars = int(hold_bars) + 1
            elif pivot_strategy == "dominant_pivot":
                min_common = max(1, int(min_common) - 1)
            min_common = max(1, min(3, int(min_common)))
            hold_bars = max(1, min(int(len(chords)), int(hold_bars)))
            try:
                prev_fz = frozenset(int(p) % 12 for p in (prev_pcs or []))
            except Exception:
                prev_fz = frozenset()
            if prev_fz:
                # Candidate pool: first chords of progressions in the same section role.
                cand_pool = chord_progression_pool_for_section_role(emotion, section_role)
                try:
                    cand_pool = normalize_progression_pool(cand_pool)
                except Exception:
                    pass
                candidates = {str(chords[0])}
                for prog in list(cand_pool or []):
                    if prog:
                        candidates.add(str(prog[0]))

                def _pcs_for(sym: str) -> set[int]:
                    root_pc = int(get_root(sym)) % 12
                    chord_root = int(root_note) + int(root_pc)
                    try:
                        notes = self.owner._chord_symbol_to_notes(str(sym), int(chord_root))
                    except Exception:
                        notes = []
                    return {int(n) % 12 for n in (notes or []) if isinstance(n, int)}

                best_shared0 = None
                best0 = None
                for i in range(int(hold_bars)):
                    cur_pcs = _pcs_for(str(chords[i]))
                    cur_shared = len(cur_pcs & set(prev_fz)) if cur_pcs else 0
                    best = str(chords[i])
                    best_shared = int(cur_shared)
                    for sym in candidates:
                        pcs = _pcs_for(str(sym))
                        shared = len(pcs & set(prev_fz)) if pcs else 0
                        if shared > best_shared:
                            best_shared = int(shared)
                            best = str(sym)
                    if best != str(chords[i]) and int(best_shared) >= int(min_common):
                        chords[i] = str(best)
                    if i == 0:
                        best_shared0 = int(best_shared)
                        best0 = str(chords[0])
                # Expose pivot metrics for the realtime player/CLI (best-effort).
                if best_shared0 is not None and best0 is not None:
                    try:
                        setattr(self.owner, "_last_handoff_bar0_common_tones", int(best_shared0))
                        setattr(self.owner, "_last_handoff_bar0_chord", str(best0))
                    except Exception:
                        pass
        roots = [root_note + get_root(ch) for ch in chords]
        return chords, roots

    def generate_chord_progression(
        self,
        emotion: EmotionProfile,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]] = None,
        temperature: float = 0.9,
        section_role: Optional[str] = None,
        *,
        section_index: int = 0,
        form_section_count: int = 1,
        chord_motion_mult: float = 1.0,
        harmony_temperature_mult: float = 1.0,
    ) -> Tuple[List[str], List[int]]:
        roots = [root_note] * bars
        if key_changes:
            for bar, new_root in key_changes:
                if 0 <= bar < bars:
                    for i in range(bar, bars):
                        roots[i] = new_root

        pool = chord_progression_pool_for_section_role(emotion, section_role)
        # Guardrail: normalize pool entries to avoid dataset artifacts.
        if resolve_config("composition", "data_normalize_enabled", True, bool):
            pool = normalize_progression_pool(pool)
        recent_signatures = set(getattr(self.owner, "recent_section_chord_signatures", ()))
        # Cross-song anti-repeat: also treat the last song's *opening* progression signature
        # (for this emotion) as "recent" so regenerating a new song in the same emotion
        # starts from a different backbone when possible.
        try:
            mem = getattr(self.owner, "last_song_opening_chord_signature_by_emotion", None)
            if isinstance(mem, dict):
                key = str(getattr(emotion, "name", "") or "").strip().lower()
                sig = mem.get(key)
                if sig:
                    recent_signatures.add(tuple(sig))
        except Exception:
            pass

        def _signature(prog: List[str]) -> Tuple[str, ...]:
            return tuple(prog[: min(4, len(prog))])

        def _canon(ch: str) -> str:
            # Keep accidentals + roman numeral root, drop most extensions for scoring.
            s = (ch or "").strip()
            if not s:
                return ""
            i = 0
            while i < len(s) and s[i] in {"b", "#"}:
                i += 1
            while i < len(s) and s[i] in {"i", "v", "I", "V"}:
                i += 1
            root = s[:i] if i > 0 else s
            rest = s[i:]
            # keep coarse quality markers
            q = ""
            rlc = rest.lower()
            if "dim" in rlc or "°" in rest or "ø" in rest:
                q = "dim"
            elif "aug" in rlc or "+" in rest:
                q = "aug"
            elif "sus" in rlc:
                q = "sus"
            elif "min" in rlc or (root and root[0].islower()):
                q = "min"
            elif "maj" in rlc or (root and root[0].isupper()):
                q = "maj"
            elif "7" in rest:
                q = "dom"
            return f"{root}{q}"

        def _score_progression(prog: List[str]) -> float:
            # Score a candidate progression against emotion anchors (cadence + brightness + tension + motion).
            if not prog:
                return -1e9
            anc = anchors_for_emotion(emotion)
            cad = str(getattr(anc, "cadence", "authentic") or "authentic").lower()
            bright = float(getattr(anc, "brightness", 0.0) or 0.0)
            arc = str(getattr(anc, "tension_arc", "rise") or "rise").lower()
            p = [str(x) for x in prog if x]
            last = p[-1] if p else ""
            pen = p[-2] if len(p) >= 2 else ""
            tonicish = last.strip().startswith(("I", "i"))
            susish = ("sus" in last.lower()) or ("sus" in pen.lower())
            # crude "plagal-ish" check: IV->I or iv->i.
            plagalish = (pen.strip().startswith(("IV", "iv")) and tonicish)

            s = 0.0
            # Cadence intent
            if cad in {"authentic"}:
                s += 2.0 if tonicish else -1.0
            elif cad in {"plagal"}:
                s += 2.0 if plagalish else (0.8 if tonicish else -0.6)
            elif cad in {"suspended"}:
                s += 1.4 if susish else (-0.4 if tonicish else 0.2)
            elif cad in {"avoid"}:
                s += 1.6 if not tonicish else -1.2

            # Brightness: major/minor leaning in the pool
            maj = sum(1 for ch in p if ch.strip().startswith("I") and not ch.strip().startswith("i"))
            minr = sum(1 for ch in p if ch.strip().startswith("i"))
            if bright >= 0.15:
                s += 0.35 * maj - 0.25 * minr
            elif bright <= -0.10:
                s += 0.35 * minr - 0.20 * maj

            # Tension: bII, dim/aug, b9/#9 tags are strong signals
            txt = " ".join(p).lower()
            s += 0.9 * txt.count("bii")
            s += 0.6 * (txt.count("dim") + txt.count("°") + txt.count("ø"))
            s += 0.5 * (txt.count("aug") + txt.count("+"))
            s += 0.25 * (txt.count("b9") + txt.count("#9"))
            # Arc: spike likes at least some tension tokens; flat prefers fewer.
            if arc == "spike":
                s += 0.35 if ("bii" in txt or "dim" in txt or "b9" in txt) else -0.15
            if arc == "flat":
                s -= 0.15 * (txt.count("bii") + txt.count("dim") + txt.count("aug"))

            # Motion: more distinct chords + changes (but keep it bounded)
            changes = sum(1 for a, b in zip(p, p[1:]) if _canon(a) != _canon(b))
            uniq = len(set(_canon(ch) for ch in p if ch))
            s += 0.10 * min(10, changes) + 0.08 * min(10, uniq)
            return float(s)

        # Pick a template progression from the emotion pool to prime variety AND anchor match.
        # Avoid repeating the same signature, then pick best by anchor scoring (best-of-K).
        template_pool = [p for p in pool if _signature(p) not in recent_signatures] or list(pool)
        rng = getattr(self.owner, "rng", random)
        if template_pool:
            # Optional bias: sometimes prefer templates that already contain explicit extensions.
            # This is useful for ambient presets where we want some progressions to *author* 9ths/11ths/13ths
            # (not just add them stochastically after the fact).
            prefer_ext_prob = resolve_config("composition", "prefer_extension_rich_progressions_prob", 0.0, float)
            prefer_ext_prob = max(0.0, min(1.0, float(prefer_ext_prob)))

            def _is_extension_rich(prog: List[str]) -> bool:
                txt = " ".join(str(x) for x in (prog or []) if x).lower()
                if not txt:
                    return False
                # Treat any explicit extended quality as "rich".
                return any(
                    tok in txt
                    for tok in (
                        "maj7",
                        "min7",
                        "m7",
                        "7",
                        "add9",
                        "9",
                        "11",
                        "13",
                        "6/9",
                        "69",
                        "#11",
                    )
                )

            if prefer_ext_prob > 0.0 and rng.random() < prefer_ext_prob:
                ext_pool = [p for p in template_pool if _is_extension_rich(p)]
                if ext_pool:
                    template_pool = ext_pool
            k_templates = resolve_config("composition", "chord_k_samples", 3, int)
            k_templates = max(1, min(9, int(k_templates)))
            candidates = rng.sample(template_pool, k=min(k_templates, len(template_pool)))
            # 2026-07-03 (docs/AUDIOGEN_COMPOSITION_PLAN.md item 19): `_score_progression`
            # scores candidates against the emotion's cadence archetype (authentic/plagal/
            # suspended/avoid). For emotions with a narrow archetype (e.g. "plagal" or
            # "avoid") only a small subset of the pool scores well, so a hard `max()` over
            # only `k_templates` random draws reliably converged on the same 1-2
            # progressions across different seeds/songs regardless of the random draw.
            # First attempt: softmax the raw scores using this function's own `temperature`
            # param (~0.9 in practice). Verified empirically that this was NOT enough
            # smoothing -- `_score_progression`'s point-scale bonuses (e.g. +2.0 for cadence
            # match) create gaps large enough that softmax(gap / 0.9) still puts ~90% of the
            # mass on the top scorer. Small section-role pools compound this: e.g. caring's
            # "a"-role pool has only 3 progressions, so with the default `chord_k_samples=3`
            # every call samples the *entire* pool -- there's no randomness left in which
            # candidates even get considered, so the softmax sharpness is the only thing
            # standing between "converges every time" and real variety.
            # Fix: min-max normalize scores to [0, 1] *within this candidate set* before
            # softmax, so sharpness depends on a dedicated, tunable knob
            # (`chord_template_selection_temperature`) rather than on the arbitrary point
            # scale `_score_progression` happens to produce.
            scores = [_score_progression(c) for c in candidates]
            score_lo, score_hi = min(scores), max(scores)
            score_span = score_hi - score_lo
            normalized = [(s - score_lo) / score_span if score_span > 1e-9 else 0.0 for s in scores]
            # Tuned empirically (not just guessed): for the common case of a 2-progression
            # section-role pool (many emotions' intro/a_prime/outro pools are this small),
            # temp=0.55 gives an 86/14 split, so 3 independent seeds land on the *same*
            # winner ~64% of the time (p^3 + (1-p)^3). temp=2.0 gives 62/38, cutting that
            # to ~28% -- still favors the better-scoring progression, just not so hard that
            # it swallows the seed's randomness for small pools.
            select_temp = resolve_config("composition", "chord_template_selection_temperature", 2.0, float)
            select_temp = max(0.05, float(select_temp))
            weights = [math.exp(n / select_temp) for n in normalized]
            template = rng.choices(candidates, weights=weights)[0]
        else:
            template = None

        # ------------------------------------------------------------------
        # Replay mode: tile a scanned pool progression verbatim.
        # ------------------------------------------------------------------
        replay = resolve_config("composition", "chord_progression_replay_enabled", False, bool)
        if replay and template:
            # Repeat the chosen template to match section length; keep chord symbols
            # exactly as authored in the dataset (extensions, alterations, etc.).
            chords = [str(template[i % len(template)]) for i in range(int(bars))]
            # Roots are already expanded for key changes above; use per-bar key root
            # name for chord-parser helpers.
            final_roots: List[int] = []
            for i, ch in enumerate(chords):
                key_root = int(roots[i]) if i < len(roots) else int(root_note)
                key_root_name = self.owner._midi_to_note_name(int(key_root))
                final_roots.append(int(key_root) + int(get_root(str(ch), key_root_name)))
            return chords, final_roots

        # Progression-level motion intent (very lightweight): bars where the template changes
        # get a slightly higher harmonic-rhythm target later (chord hits feel more "active").
        try:
            if template:
                tmp = [str(x) for x in list(template) if x]
                if len(tmp) >= 2:
                    prof = []
                    prev = None
                    for i in range(int(bars)):
                        cur = tmp[i % len(tmp)]
                        changed = (prev is not None and _canon(prev) != _canon(cur))
                        prof.append(1.12 if changed else 0.96)
                        prev = cur
                    setattr(self.owner, "_section_harmonic_motion_profile", prof)
        except Exception:
            pass

        def _vocab_from_pool(p: List[List[str]]):
            source_progressions = [
                progression
                for progression in p
                if tuple(progression[: min(4, len(progression))]) not in recent_signatures
            ] or p
            # Determinism: avoid hash-order dependence from set iteration.
            all_chords = sorted({str(ch) for prog in source_progressions for ch in prog})
            return sorted({self._markov_token(ch) for ch in all_chords if str(ch).strip()})

        simplified_vocab = _vocab_from_pool(pool)
        if not simplified_vocab and pool is not emotion.chord_progressions:
            pool = emotion.chord_progressions
            simplified_vocab = _vocab_from_pool(pool)
        if not simplified_vocab:
            return [], []

        opening_weights = [self.opening_bias(emotion.name, sym) for sym in simplified_vocab]
        ctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
        prev_pcs = ctx.get("previous_chord_pcs")
        try:
            pivot_strategy = str(ctx.get("handoff_pivot_strategy", "") or "")
        except Exception:
            pivot_strategy = ""
        if prev_pcs is not None:
            prev_fz = frozenset(prev_pcs) if not isinstance(prev_pcs, frozenset) else prev_pcs
            if prev_fz:
                pivot = [
                    self._handoff_pivot_multiplier(sym, root_note, prev_fz, pivot_strategy=pivot_strategy)
                    for sym in simplified_vocab
                ]
            else:
                prev_fz = None
        else:
            prev_fz = None
        if prev_fz:
            opening_weights = [w * p for w, p in zip(opening_weights, pivot)]
        role_lc = (section_role or "").lower()
        if role_lc == "pre_chorus" and prev_fz:
            opening_weights = [
                w * (1.32 if sym == "dom" else 0.94 if sym == "maj" else 1.0)
                for w, sym in zip(opening_weights, simplified_vocab)
            ]
        if template:
            # Prime the opening from a concrete pool progression, not just function bias.
            seed_simplified = self._markov_token(template[0])
            if seed_simplified not in simplified_vocab:
                seed_simplified = rng.choices(simplified_vocab, weights=opening_weights)[0]
        else:
            seed_simplified = rng.choices(simplified_vocab, weights=opening_weights)[0]
        simplified_chords = [seed_simplified]
        phrase_length = phrase_length_bars_clamped(1, 16)
        total_phrases = max(1, (bars + phrase_length - 1) // phrase_length)

        try:
            next_role_hint = str(getattr(self.owner, "_next_section_role_hint", "") or "")
        except Exception:
            next_role_hint = ""
        pacing_plan = harmony_pacing_for_section(
            section_role,
            bars,
            next_role=next_role_hint,
        )
        motion = max(0.62, min(1.42, float(chord_motion_mult) * float(pacing_plan.motion_multiplier)))
        h_temp = max(0.72, min(1.28, float(harmony_temperature_mult)))
        chord_sample_temp = float(temperature) * h_temp
        # Optional: within-section temperature schedule by phrase role.
        t_open = resolve_config("composition", "chord_temp_opening_mult", 0.92, float)
        t_cont = resolve_config("composition", "chord_temp_continuation_mult", 1.04, float)
        t_ans = resolve_config("composition", "chord_temp_answer_mult", 1.0, float)
        t_cad = resolve_config("composition", "chord_temp_cadence_mult", 0.9, float)
        k_samples = resolve_config("composition", "chord_k_samples", 1, int)
        change_bonus = resolve_config("composition", "chord_rerank_change_bonus", 0.08, float)
        cad_bonus = resolve_config("composition", "chord_rerank_cadence_bonus", 0.12, float)
        def _temp_for_phrase_role(role: str) -> float:
            return {
                "opening": t_open,
                "continuation": t_cont,
                "answer": t_ans,
                "cadence": t_cad,
            }.get(role, 1.0)

        chord_change_params = self.owner.arrangement_policy.chord_change_params(
            emotion.name,
            {
                "max_repeats": self.owner.max_chord_repeats,
                "force_prob": self.owner.force_change_prob,
                "repeat_penalty": self.owner.chord_repeat_penalty,
            },
        )
        effective_max_repeats = max(
            1, min(6, int(round(chord_change_params["max_repeats"] / max(0.72, motion))))
        )
        effective_force_prob = min(0.92, float(chord_change_params["force_prob"]) * motion)
        base_rp = float(chord_change_params["repeat_penalty"])
        effective_repeat_penalty = max(
            0.04, min(0.5, base_rp * (1.12 / max(0.65, motion)))
        )

        form_n = max(1, int(form_section_count))
        idx = max(0, int(section_index))
        is_first_form_section = idx == 0
        is_last_form_section = idx >= form_n - 1

        # Optional guided start: borrow the first 2–4 bars from the chosen
        # template progression with a probability that scales down as motion increases.
        guided = []
        if template:
            guided = [self._markov_token(ch) for ch in template]
        guided_prob = max(0.0, min(0.85, 0.55 / max(0.75, motion)))

        # ------------------------------------------------------------------
        # Phrase-level harmony function scaffolding (T / PD / D).
        # This provides a phrase-scale harmonic narrative by role, while still
        # sampling from the local Markov distribution.
        # ------------------------------------------------------------------
        def _target_function(
            *,
            section_role: Optional[str],
            phrase_role: str,
            bar_in_phrase: int,
            phrase_length: int,
            is_last_phrase: bool,
        ) -> Tuple[Optional[str], float]:
            r = (section_role or "").strip().lower()
            pr0 = (phrase_role or "").strip().lower()
            # Strength: keep light overall; tighten near cadences.
            base = {
                "intro": 0.25,
                "a": 0.35,
                "pre_chorus": 0.55,
                "b": 0.55,
                "a_prime": 0.45,
                "tag": 0.50,
                "outro": 0.60,
            }.get(r, 0.35)
            end_boost = 0.22 if (phrase_length >= 2 and bar_in_phrase >= phrase_length - 2) else 0.0
            strength = max(0.0, min(1.0, float(base) + float(end_boost)))

            # Default phrase trajectory: T -> PD -> D -> (T)
            if bar_in_phrase == 0:
                return "T", strength
            if bar_in_phrase == phrase_length - 2:
                return "D", strength

            is_final_bar = bar_in_phrase == phrase_length - 1
            if is_final_bar:
                # Role-aware phrase endings.
                if r == "pre_chorus":
                    return "D", min(1.0, strength + 0.20)  # set up the chorus
                if r in {"b", "outro", "tag"}:
                    return "T", min(1.0, strength + 0.20)  # land the hook/ending
                if r == "a" and not is_last_phrase:
                    return "PD", strength  # keep verse endings more open mid-song
                return "T", strength

            if pr0 in {"opening"}:
                return "T", strength
            if pr0 in {"cadence"}:
                return "D", strength
            # Mid-phrase motion: prefer PD (setup) unless pre-chorus wants more drive.
            if r == "pre_chorus":
                return "D", strength
            return "PD", strength

        for bar in range(1, bars):
            if guided and bar < len(guided) and rng.random() < guided_prob:
                simplified_chords.append(guided[bar])
                continue
            bar_in_phrase = bar % phrase_length
            phrase_idx = bar // phrase_length
            pr = self.phrase_role(int(phrase_idx), int(total_phrases))
            # Cadence intent: match Melody PhrasePlanner cadence targets at phrase boundaries.
            is_last_phrase = phrase_idx == (total_phrases - 1)
            cadence_target_degree = None
            if bar_in_phrase == phrase_length - 1:
                cadence_target_degree = self._cadence_degree_for_phrase(
                    emotion_name=emotion.name,
                    is_last_phrase=bool(is_last_phrase),
                )
            intent = None
            try:
                intent = IntentContext(
                    section_role=str(section_role or ""),
                    phrase_role=str(pr or ""),
                    contour="static",
                    phrase_idx=int(phrase_idx),
                    total_phrases=int(total_phrases),
                    output_channel=1,
                    cadence_degree=int(cadence_target_degree or 0),
                    cadence_zone_start=0.75,
                    is_final_phrase=bool(is_last_phrase),
                )
            except Exception:
                intent = None
            temp_bar = max(0.25, float(chord_sample_temp) * float(_temp_for_phrase_role(pr)))
            previous_phrase_end = simplified_chords[(phrase_idx * phrase_length) - 1] if phrase_idx > 0 else ""
            is_penultimate_bar = bar == bars - 2
            tf, tf_strength = _target_function(
                section_role=section_role,
                phrase_role=str(pr or ""),
                bar_in_phrase=int(bar_in_phrase),
                phrase_length=int(phrase_length),
                is_last_phrase=bool(is_last_phrase),
            )
            contracts_on = resolve_config("composition", "harmony_function_contracts_enabled", True, bool)
            contracts_strength = resolve_config("composition", "harmony_function_contract_strength", 0.72, float)
            contracts_strength = max(0.0, min(1.0, float(contracts_strength)))
            if contracts_on and contracts_strength > 1e-6:
                # Phrase-boundary hardening: role-aware final/penultimate targets.
                if int(bar_in_phrase) == int(phrase_length) - 1:
                    rlc = str(section_role or "").strip().lower()
                    if rlc in {"pre_chorus"}:
                        tf = "D"
                    elif rlc in {"b", "chorus", "hook", "tag", "outro", "ending"}:
                        tf = "T"
                elif int(bar_in_phrase) == int(phrase_length) - 2 and str(tf or "").upper() not in {"D"}:
                    tf = "D"
                # Raise target-function influence under contracts.
                tf_strength = float(max(float(tf_strength), 0.52 + 0.38 * float(contracts_strength)))
            # Optional phrase-intent profile from SectionPlanner timeline targets.
            # This lets phrase/cadence intent override the local heuristic when available.
            try:
                tf_prof = getattr(self.owner, "_section_harmony_function_target_profile", None)
                if isinstance(tf_prof, list) and 0 <= int(bar) < len(tf_prof):
                    tfs = str(tf_prof[int(bar)] or "").strip().upper()
                    if tfs in {"T", "PD", "D"}:
                        tf = str(tfs)
            except Exception:
                pass
            try:
                cs_prof = getattr(self.owner, "_section_cadence_strength_profile", None)
                if isinstance(cs_prof, list) and 0 <= int(bar) < len(cs_prof):
                    csi = max(0.0, min(1.35, float(cs_prof[int(bar)])))
                    tf_strength = float(max(float(tf_strength), min(1.0, float(tf_strength) + 0.42 * float(csi))))
                    if str(tf) == "D" and float(csi) >= 0.85:
                        tf_strength = float(max(float(tf_strength), 0.80))
                    if (
                        str(tf) == "T"
                        and int(bar) == int(bars) - 1
                        and str(section_role or "").strip().lower() in {"b", "chorus", "hook", "tag", "outro"}
                    ):
                        tf_strength = float(max(float(tf_strength), 0.86))
                    if contracts_on and float(contracts_strength) > 1e-6 and float(csi) >= 0.85:
                        tf_strength = float(max(float(tf_strength), min(1.0, 0.82 + 0.14 * float(contracts_strength))))
            except Exception:
                pass

            # Motif-aware reharmonization (lightweight):
            # when motif strength is high, prefer tonic stability and reduce temperature slightly
            # so hooks land against a predictable harmonic bed.
            try:
                prof = getattr(self.owner, "_section_motif_strength_profile", None)
            except Exception:
                prof = None
            ms = 0.0
            if isinstance(prof, list) and 0 <= int(bar) < len(prof):
                try:
                    ms = float(prof[int(bar)])
                except Exception:
                    ms = 0.0
            ms = max(0.0, min(1.0, float(ms)))
            if ms >= 0.70:
                try:
                    rlc = str(section_role or "").strip().lower()
                except Exception:
                    rlc = ""
                if rlc in {"b", "a_prime", "tag"}:
                    tf = "T"
                    try:
                        tf_strength = max(float(tf_strength), 0.72 + 0.18 * float(ms))
                    except Exception:
                        tf_strength = 0.80
                temp_bar = float(temp_bar) * float(max(0.82, 1.0 - 0.10 * float(ms)))

            repeat_count = 1
            for j in range(len(simplified_chords) - 1, 0, -1):
                if simplified_chords[j] == simplified_chords[j - 1]:
                    repeat_count += 1
                else:
                    break

            if repeat_count >= effective_max_repeats:
                context = simplified_chords[-3:]
                next_simplified = self.sample_next_simplified_chord(
                    context,
                    simplified_vocab,
                    simplified_chords,
                    temp_bar,
                    effective_repeat_penalty,
                    bar_in_phrase,
                    phrase_length,
                    force_change=True,
                    greedy=True,
                    k_samples=max(1, k_samples),
                    change_bonus=change_bonus,
                    cadence_bonus=cad_bonus,
                    emotion_name=emotion.name,
                    is_section_start=(bar_in_phrase == 0),
                    is_final_phrase_bar=(bar == bars - 1),
                    phrase_idx=phrase_idx,
                    total_phrases=total_phrases,
                    previous_phrase_end=previous_phrase_end,
                    section_opening=seed_simplified,
                    section_role=section_role,
                    bar_index=bar,
                    total_bars=bars,
                    is_penultimate_section_bar=is_penultimate_bar,
                    is_first_form_section=is_first_form_section,
                    is_last_form_section=is_last_form_section,
                    cadence_target_degree=cadence_target_degree,
                    intent=intent,
                    target_function=tf,
                    target_function_strength=float(tf_strength),
                )
                simplified_chords.append(next_simplified)
                continue

            if rng.random() < effective_force_prob and len(simplified_chords) > 0:
                context = simplified_chords[-3:]
                next_simplified = self.sample_next_simplified_chord(
                    context,
                    simplified_vocab,
                    simplified_chords,
                    temp_bar,
                    effective_repeat_penalty,
                    bar_in_phrase,
                    phrase_length,
                    force_change=True,
                    emotion_name=emotion.name,
                    is_section_start=(bar_in_phrase == 0),
                    is_final_phrase_bar=(bar == bars - 1),
                    phrase_idx=phrase_idx,
                    total_phrases=total_phrases,
                    previous_phrase_end=previous_phrase_end,
                    section_opening=seed_simplified,
                    section_role=section_role,
                    bar_index=bar,
                    total_bars=bars,
                    is_penultimate_section_bar=is_penultimate_bar,
                    is_first_form_section=is_first_form_section,
                    is_last_form_section=is_last_form_section,
                    k_samples=max(1, k_samples),
                    change_bonus=change_bonus,
                    cadence_bonus=cad_bonus,
                    cadence_target_degree=cadence_target_degree,
                    intent=intent,
                    target_function=tf,
                    target_function_strength=float(tf_strength),
                )
                simplified_chords.append(next_simplified)
                continue

            with self.owner.perf_monitor.measure("chord_gen_iteration"):
                context = simplified_chords[-3:]
                next_simplified = self.sample_next_simplified_chord(
                    context,
                    simplified_vocab,
                    simplified_chords,
                    temp_bar,
                    effective_repeat_penalty,
                    bar_in_phrase,
                    phrase_length,
                    emotion_name=emotion.name,
                    is_section_start=(bar_in_phrase == 0),
                    is_final_phrase_bar=(bar == bars - 1),
                    phrase_idx=phrase_idx,
                    total_phrases=total_phrases,
                    previous_phrase_end=previous_phrase_end,
                    section_opening=seed_simplified,
                    section_role=section_role,
                    bar_index=bar,
                    total_bars=bars,
                    is_penultimate_section_bar=is_penultimate_bar,
                    is_first_form_section=is_first_form_section,
                    is_last_form_section=is_last_form_section,
                    k_samples=max(1, k_samples),
                    change_bonus=change_bonus,
                    cadence_bonus=cad_bonus,
                    cadence_target_degree=cadence_target_degree,
                    intent=intent,
                    target_function=tf,
                    target_function_strength=float(tf_strength),
                )
                simplified_chords.append(next_simplified)

        # Global ambient hold can make the harmony feel "stuck" for non-ambient emotions.
        # For neutral (the default bed emotion), prefer motion: never force-hold chords.
        hold = int(getattr(self.owner, "ambient_chord_hold_bars", 1) or 1)
        if emotion.name.lower() == "neutral":
            hold = 1
        # Also reduce forced holds when the section is explicitly requesting more motion.
        if motion >= 1.12:
            hold = min(hold, 1)
        if hold > 1:
            for bar in range(1, bars):
                if bar % hold != 0:
                    simplified_chords[bar] = simplified_chords[bar - 1]

        pacing_on = resolve_config("composition", "harmony_pacing_policy_enabled", True, bool)
        pacing_strength = resolve_config("composition", "harmony_pacing_policy_strength", 1.0, float)
        if pacing_on and float(pacing_strength) > 1e-6:
            simplified_chords = apply_harmony_pacing_to_tokens(simplified_chords, pacing_plan)

        gbl: Optional[MarkovChain] = self.owner.global_chord_markov
        if gbl is not None and self.owner.global_blend_weight > 0:
            with self.owner.perf_monitor.measure("global_model_blend"):
                global_simplified = gbl.generate(
                    [seed_simplified], bars, chord_sample_temp
                )
                if len(global_simplified) < bars:
                    global_simplified.extend([global_simplified[-1]] * (bars - len(global_simplified)))
                blended = []
                for i in range(bars):
                    if rng.random() < self.owner.global_blend_weight:
                        blended.append(global_simplified[i])
                    else:
                        blended.append(simplified_chords[i])
                simplified_chords = blended

        chords = [self.restore_chord_extension(simplified, emotion.name, section_role=section_role) for simplified in simplified_chords]
        key_root_name = self.owner._midi_to_note_name(root_note)
        final_roots = [root_note + get_root(chord, key_root_name) for chord in chords]
        return chords, final_roots
