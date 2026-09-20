# composition/section_planner/planner_arrangement_dynamics_mixin.py
# ---------------------------------------------------------------------------
# SectionPlanner mixin: verse-sentence/timeline/arrangement-energy-matrix
# target shaping, whole-song energy/director, and song-blueprint target
# blending. Split out of planner.py (see planner.py for the assembled class).
# ---------------------------------------------------------------------------
from typing import Any, Dict, List, Optional, Tuple

from audiogen_core.config import resolve_config
from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped
from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan
from .final_chorus_payoff import resolve_final_chorus_payoff_state
from .observability import log_degraded


class _PlannerArrangementDynamicsMixin:
    """Verse/timeline/energy-matrix/whole-song-director static helpers."""

    @staticmethod
    def _quiet_verse_ostinato_lock(
        *,
        emotion_name: str,
        section_role: str,
    ) -> Optional[Dict[str, float | str]]:
        emo = str(emotion_name or "").strip().lower()
        role = str(section_role or "").strip().lower()
        if emo not in {"grief", "sadness", "remorse", "relief"}:
            return None
        if role not in {"a", "pre_chorus"}:
            return None
        return {
            "mode": "up",
            "grid": 1.0 if role == "a" else 0.5,
            "target_notes_per_bar_max": 2.2,
            "density_mult_max": 0.30,
            "velocity_scale_max": 0.72,
        }

    @staticmethod
    def _apply_verse_sentence_targets(
        targets: Dict[str, Any],
        *,
        motif_stage: str,
        development_mode: str,
        layer_contract: Optional[Dict[str, float]],
        strength: float,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in dict(targets or {}).items():
            if isinstance(v, list):
                out[str(k)] = list(v)
            elif isinstance(v, dict):
                out[str(k)] = {str(k2): (list(v2) if isinstance(v2, list) else v2) for k2, v2 in dict(v).items()}
            else:
                out[str(k)] = v
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return out

        md = list(out.get("melody_density", []) or [])
        ms = list(out.get("motif_strength", []) or [])
        cad = list(out.get("cadence_window", []) or [])
        tens = list(out.get("tension", []) or [])
        lp = dict(out.get("layer_presence_targets", {}) or {})
        n = max(len(md), len(ms), len(cad), len(tens))
        if n <= 0:
            return out

        stage = str(motif_stage or "").strip().lower()
        dev_mode = str(development_mode or "").strip().lower()
        restate_bias = 1.0 if stage in {"restate", "payoff"} else (0.55 if stage in {"develop", "build"} else 0.0)
        return_lift = 1.0 if dev_mode == "return_lift" else 0.0
        phrase_blocks = max(1, int((n + 7) // 8))
        for block in range(phrase_blocks):
            start = int(block * 8)
            end = int(min(n, start + 8))
            if start >= end:
                continue
            for idx in range(start, end):
                local = int(idx - start)
                if local <= 1:
                    motif_mul = 1.12 + 0.06 * restate_bias
                    density_mul = 0.96
                    cadence_floor = 0.12
                    tension_bias = -0.02
                elif local <= 3:
                    motif_mul = 0.96 + 0.04 * restate_bias
                    density_mul = 1.00
                    cadence_floor = 0.18 if local == 3 else 0.10
                    tension_bias = 0.02
                elif local <= 5:
                    motif_mul = 1.08 + 0.10 * restate_bias + 0.04 * return_lift
                    density_mul = 0.94 + 0.04 * return_lift
                    cadence_floor = 0.14
                    tension_bias = 0.02 * return_lift
                else:
                    motif_mul = 0.92 + 0.04 * restate_bias
                    density_mul = (0.86 if idx == end - 1 else 0.92) + (0.05 * return_lift if idx != end - 1 else 0.0)
                    cadence_floor = 0.46 if local == 6 else 0.78
                    tension_bias = -0.04 if idx == end - 1 else 0.01

                if idx < len(ms):
                    base = float(ms[idx])
                    target = float(max(0.0, min(2.0, base * motif_mul)))
                    ms[idx] = float(max(0.0, min(2.0, (1.0 - s) * base + s * target)))
                if idx < len(md):
                    base = float(md[idx])
                    target = float(max(0.15, min(2.25, base * density_mul)))
                    md[idx] = float(max(0.15, min(2.25, (1.0 - s) * base + s * target)))
                if idx < len(cad):
                    base = float(cad[idx])
                    cad[idx] = float(max(0.0, min(1.35, max(base, (1.0 - s) * base + s * cadence_floor))))
                if idx < len(tens):
                    base = float(tens[idx])
                    target = float(max(0.0, min(1.35, base + tension_bias)))
                    tens[idx] = float(max(0.0, min(1.35, (1.0 - s) * base + s * target)))

        if md:
            out["melody_density"] = md
        if ms:
            out["motif_strength"] = ms
        if cad:
            out["cadence_window"] = cad
        if tens:
            out["tension"] = tens

        if lp and layer_contract:
            arp_arr = list(lp.get("arp", []) or [])
            counter_arr = list(lp.get("counter", []) or [])
            chords_arr = list(lp.get("chords", []) or [])
            melody_arr = list(lp.get("melody", []) or [])
            for idx in range(n):
                local = int(idx % 8)
                if idx < len(arp_arr):
                    base = float(arp_arr[idx])
                    target = base
                    if local <= 1:
                        target = max(base, float(layer_contract.get("arp", base)))
                    elif return_lift > 0.0 and local >= 4:
                        target = max(base, min(1.0, base + 0.08))
                    elif local >= 6:
                        target = max(base * 0.92, base - 0.06)
                    arp_arr[idx] = float(max(0.0, min(1.0, (1.0 - s) * base + s * target)))
                if idx < len(chords_arr):
                    base = float(chords_arr[idx])
                    target = base
                    if local in {0, 4}:
                        target = max(base, float(layer_contract.get("chords", base)))
                    chords_arr[idx] = float(max(0.0, min(1.0, (1.0 - s) * base + s * target)))
                if idx < len(melody_arr):
                    base = float(melody_arr[idx])
                    target = base
                    if local >= 6:
                        target = min(base, float(layer_contract.get("melody", base)) * 0.96)
                    melody_arr[idx] = float(max(0.0, min(1.0, (1.0 - s) * base + s * target)))
                if idx < len(counter_arr):
                    base = float(counter_arr[idx])
                    target = base
                    if local <= 5:
                        target = min(base, float(layer_contract.get("counter", base)) * (0.78 + 0.18 * restate_bias))
                    else:
                        target = min(base + 0.06 * return_lift, float(layer_contract.get("counter", base)) * (0.92 + 0.10 * restate_bias + 0.12 * return_lift))
                    counter_arr[idx] = float(max(0.0, min(1.0, (1.0 - s) * base + s * target)))
            if arp_arr:
                lp["arp"] = arp_arr
            if chords_arr:
                lp["chords"] = chords_arr
            if melody_arr:
                lp["melody"] = melody_arr
            if counter_arr:
                lp["counter"] = counter_arr
            out["layer_presence_targets"] = lp
        return out

    @staticmethod
    def _apply_timeline_targets_to_voicing(
        plan: SectionPlan,
        *,
        composition: Any = None,
        chord_utils: Any = None,
    ) -> SectionPlan:
        targets = getattr(plan, "timeline_targets", None) or {}
        melody_density = list(targets.get("melody_density", []) or [])
        if not melody_density or not getattr(plan, "chosen_melody", None):
            return plan

        # Register lane targets (stable “produced” bands per part).
        comp = composition
        if comp is None:
            comp = resolve_config("composition", "", None)
        if comp is not None:
            lane_center = int(getattr(comp, "melody_lane_center_midi", 72) or 72)
            lane_hw = int(getattr(comp, "melody_lane_half_width", 10) or 10)
            chords_off = int(getattr(comp, "chords_lane_offset_from_melody", 12) or 12)
            chords_hw = int(getattr(comp, "chords_lane_half_width", 10) or 10)
        else:
            lane_center = 72
            lane_hw = 10
            chords_off = 12
            chords_hw = 10
        # Song-level register arc: role-based lane center offset from arrangement curves.
        try:
            curve = getattr(plan, "arrangement_curve", None) or {}
            off = int(round(float(curve.get("melody_lane_center_offset", 0) or 0)))
        except Exception as exc:
            log_degraded(
                "apply_timeline_targets_voicing.arrangement_curve",
                exc,
                section_index=getattr(plan, "section_index", None),
                section_role=getattr(plan, "section_role", None),
            )
            off = 0
        lane_center = int(lane_center) + int(off)
        lane_hw = max(4, min(24, int(lane_hw)))
        chords_hw = max(4, min(24, int(chords_hw)))

        # Optional section-level melody register arc:
        # keep lead in a smooth register trajectory rather than per-bar jumps.
        if comp is not None:
            reg_arc = bool(getattr(comp, "melody_register_arc_enabled", True))
        else:
            reg_arc = True

        shaped_melody: List[int] = []
        shaped_bass: List[int] = []
        shaped_chords: List[List[int]] = []
        prev_m = None
        prev_ch_center = None
        for bar in range(int(plan.bars)):
            density = float(melody_density[bar]) if bar < len(melody_density) else 1.0
            melody_note = int(plan.chosen_melody[bar]) if bar < len(plan.chosen_melody) else int(lane_center)
            bass_note = int(plan.chosen_bass[bar]) if bar < len(plan.chosen_bass) else 36
            chord_notes = list(plan.chosen_chord[bar]) if getattr(plan, "chosen_chord", None) and bar < len(plan.chosen_chord) else []

            if density >= 1.12:
                melody_note += 5
                bass_note += 0
            elif density <= 0.82:
                melody_note -= 3
                bass_note -= 2
            elif density <= 0.92:
                melody_note -= 1

            # Pull planned melody lane toward the configured target band.
            # We allow the density arc to move it slightly within the lane.
            m0 = int(RANGE_LIMITER.clamp_note(int(melody_note), 2))
            lo = int(lane_center) - int(lane_hw)
            hi = int(lane_center) + int(lane_hw)
            m = int(max(int(lo), min(int(hi), int(m0))))
            m = int(RANGE_LIMITER.clamp_note(int(m), 2))
            if reg_arc and prev_m is not None:
                # Limit per-bar leaps in the planned register lane.
                # (The actual melody still varies inside this lane.)
                if abs(int(m) - int(prev_m)) > 7:
                    m = int(prev_m + (7 if int(m) > int(prev_m) else -7))
                    m = int(RANGE_LIMITER.clamp_note(int(m), 2))
            shaped_melody.append(int(m))
            prev_m = int(m)
            shaped_bass.append(RANGE_LIMITER.clamp_note(int(bass_note), 0))

            # Chord lane: keep chords in a stable band below the melody lane.
            # We only apply octave shifts (±12) to preserve voicing/spacing.
            if chord_notes:
                chord_notes = [int(RANGE_LIMITER.clamp_note(int(n), 1)) for n in chord_notes]
                chord_notes_sorted = sorted(chord_notes)
                ch_center = chord_notes_sorted[len(chord_notes_sorted) // 2]
                # Phrase mini-arc (cinematic): continuation lifts slightly, cadence settles.
                try:
                    phrase_len = phrase_length_bars_clamped(1, 16)
                    if chord_utils is not None and hasattr(chord_utils, "phrase_role"):
                        phr = chord_utils.phrase_role(int(bar), int(plan.bars), phrase_length=int(phrase_len))
                    else:
                        phr = ""
                except Exception as exc:
                    log_degraded(
                        "apply_timeline_targets_voicing.phrase_role",
                        exc,
                        section_index=getattr(plan, "section_index", None),
                        section_role=getattr(plan, "section_role", None),
                    )
                    phr = ""
                arc_off = {
                    "opening": -1,
                    "continuation": 2,
                    "answer": 1,
                    "cadence": -2,
                }.get(str(phr or ""), 0)
                # Sit under the melody lane, and keep within the chord lane band.
                target_center = int(m) - int(chords_off) + int(arc_off)
                ch_lo = int(m) - int(chords_off) - int(chords_hw)
                ch_hi = int(m) - int(chords_off) + int(chords_hw)
                target_center = int(max(int(ch_lo), min(int(ch_hi), int(target_center))))
                # Pick octave shift that best matches target center.
                best_shift = 0
                best_dist = abs(int(ch_center) - int(target_center))
                for shift in (-24, -12, 0, 12, 24):
                    dist = abs(int(ch_center + shift) - int(target_center))
                    if dist < best_dist:
                        best_dist = dist
                        best_shift = int(shift)
                shifted = [int(RANGE_LIMITER.clamp_note(int(n + best_shift), 1)) for n in chord_notes]
                shifted_sorted = sorted(shifted)
                new_center = shifted_sorted[len(shifted_sorted) // 2]
                if reg_arc and prev_ch_center is not None:
                    # Prevent sudden per-bar chord register jumps by applying octave corrections.
                    # Use a tight threshold so chord changes feel "handed off" like piano comping.
                    try:
                        max_jump = 7
                        # Apply up to 2 octave corrections if needed.
                        for _ in range(2):
                            if abs(int(new_center) - int(prev_ch_center)) <= max_jump:
                                break
                            # If we jumped up, bring chord down an octave; if we jumped down, bring it up.
                            dir_s = 12 if int(new_center) > int(prev_ch_center) else -12
                            shifted = [int(RANGE_LIMITER.clamp_note(int(n - dir_s), 1)) for n in shifted]
                            shifted_sorted = sorted(shifted)
                            new_center = shifted_sorted[len(shifted_sorted) // 2]
                    except Exception as exc:
                        log_degraded(
                            "apply_timeline_targets_voicing.chord_register_smooth",
                            exc,
                            section_index=getattr(plan, "section_index", None),
                            section_role=getattr(plan, "section_role", None),
                        )
                prev_ch_center = int(new_center)
                shaped_chords.append(sorted(shifted))
            else:
                shaped_chords.append([])

        if len(shaped_melody) == len(plan.chosen_melody):
            plan.chosen_melody = shaped_melody
        if len(shaped_bass) == len(plan.chosen_bass):
            plan.chosen_bass = shaped_bass
        if getattr(plan, "chosen_chord", None) and len(shaped_chords) == len(plan.chosen_chord):
            # Keep empty bars untouched.
            if any(bool(x) for x in shaped_chords):
                plan.chosen_chord = shaped_chords
        return plan

    @staticmethod
    def _apply_arrangement_energy_matrix_targets(
        targets: Dict[str, Any],
        *,
        section_role: str,
        section_index: int,
        form_section_count: int,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in dict(targets or {}).items():
            kk = str(k)
            if isinstance(v, list):
                out[kk] = list(v)
            elif isinstance(v, dict):
                out[kk] = {str(k2): (list(v2) if isinstance(v2, list) else v2) for k2, v2 in dict(v).items()}
            else:
                out[kk] = v

        enabled = resolve_config("composition", "arrangement_energy_matrix_enabled", True, bool)
        s = resolve_config("composition", "arrangement_energy_matrix_strength", 0.72, float)
        s = max(0.0, min(1.0, float(s)))
        if not enabled or s <= 1e-6:
            return out

        role = str(section_role or "").strip().lower()
        md = list(out.get("melody_density", []) or [])
        cr = list(out.get("chord_rhythm", []) or [])
        ms = list(out.get("motif_strength", []) or [])
        tn = list(out.get("tension", []) or [])
        phrase_roles = list(out.get("phrase_role_by_bar", []) or [])
        layer_targets = dict(out.get("layer_presence_targets", {}) or {})
        n = max(len(md), len(cr), len(ms), len(tn), len(phrase_roles))
        if n <= 0:
            return out
        if not phrase_roles:
            phrase_roles = ["continuation" for _ in range(n)]

        role_base = {
            "intro": {"melody": 0.86, "chord": 0.92, "motif": 0.82, "tension": 0.88, "bass": 0.70, "chords": 0.92, "melody_l": 0.90, "arp": 0.78, "counter": 0.42},
            "a": {"melody": 0.96, "chord": 1.00, "motif": 0.95, "tension": 0.96, "bass": 0.92, "chords": 0.96, "melody_l": 1.00, "arp": 0.84, "counter": 0.58},
            "verse": {"melody": 0.96, "chord": 1.00, "motif": 0.95, "tension": 0.96, "bass": 0.92, "chords": 0.96, "melody_l": 1.00, "arp": 0.84, "counter": 0.58},
            "pre_chorus": {"melody": 1.04, "chord": 1.04, "motif": 1.02, "tension": 1.08, "bass": 1.02, "chords": 0.96, "melody_l": 1.02, "arp": 1.06, "counter": 0.90},
            "b": {"melody": 1.10, "chord": 1.10, "motif": 1.14, "tension": 1.10, "bass": 1.08, "chords": 1.04, "melody_l": 1.04, "arp": 1.12, "counter": 1.22},
            "chorus": {"melody": 1.10, "chord": 1.10, "motif": 1.14, "tension": 1.10, "bass": 1.08, "chords": 1.04, "melody_l": 1.04, "arp": 1.12, "counter": 1.22},
            "hook": {"melody": 1.10, "chord": 1.10, "motif": 1.14, "tension": 1.10, "bass": 1.08, "chords": 1.04, "melody_l": 1.04, "arp": 1.12, "counter": 1.22},
            "tag": {"melody": 1.06, "chord": 0.98, "motif": 1.16, "tension": 1.04, "bass": 1.02, "chords": 0.98, "melody_l": 1.04, "arp": 1.04, "counter": 1.02},
            "a_prime": {"melody": 1.02, "chord": 1.06, "motif": 1.06, "tension": 1.06, "bass": 1.00, "chords": 1.00, "melody_l": 1.00, "arp": 1.00, "counter": 1.00},
            "outro": {"melody": 0.82, "chord": 0.88, "motif": 0.86, "tension": 0.84, "bass": 0.78, "chords": 0.86, "melody_l": 0.86, "arp": 0.74, "counter": 0.62},
            "ending": {"melody": 0.82, "chord": 0.88, "motif": 0.86, "tension": 0.84, "bass": 0.78, "chords": 0.86, "melody_l": 0.86, "arp": 0.74, "counter": 0.62},
        }.get(role, {"melody": 1.0, "chord": 1.0, "motif": 1.0, "tension": 1.0, "bass": 1.0, "chords": 1.0, "melody_l": 1.0, "arp": 1.0, "counter": 1.0})

        form_n = max(1, int(form_section_count))
        form_pos = max(0.0, min(1.0, float(section_index) / float(max(1, form_n - 1))))
        form_lift = 1.0 + 0.08 * float(form_pos)
        if role in {"outro", "ending"}:
            form_lift = 1.0 - 0.10 * float(form_pos)

        for i in range(n):
            pr = str(phrase_roles[i] if i < len(phrase_roles) else "continuation")
            phrase_mult = {
                "opening": {"melody": 0.96, "chord": 0.98, "motif": 1.02, "tension": 0.96, "arp": 0.95, "counter": 0.90},
                "continuation": {"melody": 1.04, "chord": 1.02, "motif": 0.98, "tension": 1.03, "arp": 1.04, "counter": 1.00},
                "answer": {"melody": 1.02, "chord": 1.00, "motif": 1.04, "tension": 1.02, "arp": 1.00, "counter": 1.05},
                "cadence": {"melody": 0.90, "chord": 0.94, "motif": 1.08, "tension": 0.90, "arp": 0.80, "counter": 0.72},
            }.get(pr, {"melody": 1.0, "chord": 1.0, "motif": 1.0, "tension": 1.0, "arp": 1.0, "counter": 1.0})

            mel_mult = float(role_base["melody"]) * float(phrase_mult["melody"]) * float(form_lift)
            chr_mult = float(role_base["chord"]) * float(phrase_mult["chord"]) * float(form_lift)
            mot_mult = float(role_base["motif"]) * float(phrase_mult["motif"]) * float(form_lift)
            ten_mult = float(role_base["tension"]) * float(phrase_mult["tension"]) * float(form_lift)

            if i < len(md):
                m = (1.0 - s) + s * float(mel_mult)
                md[i] = float(max(0.15, min(2.25, float(md[i]) * float(m))))
            if i < len(cr):
                m = (1.0 - s) + s * float(chr_mult)
                cr[i] = float(max(0.35, min(2.0, float(cr[i]) * float(m))))
            if i < len(ms):
                m = (1.0 - s) + s * float(mot_mult)
                ms[i] = float(max(0.0, min(2.0, float(ms[i]) * float(m))))
            if i < len(tn):
                m = (1.0 - s) + s * float(ten_mult)
                tn[i] = float(max(0.0, min(1.35, float(tn[i]) * float(m))))

        out["melody_density"] = md
        out["chord_rhythm"] = cr
        out["motif_strength"] = ms
        out["tension"] = tn

        lane_map = {
            "bass": float(role_base["bass"]),
            "chords": float(role_base["chords"]),
            "melody": float(role_base["melody_l"]),
            "arp": float(role_base["arp"]),
            "counter": float(role_base["counter"]),
        }
        for lk, arr in list(layer_targets.items()):
            if not isinstance(arr, list):
                continue
            base = float(lane_map.get(str(lk), 1.0))
            out_arr = list(arr)
            for i in range(len(out_arr)):
                pr = str(phrase_roles[i] if i < len(phrase_roles) else "continuation")
                ph = {
                    "opening": 0.95,
                    "continuation": 1.03,
                    "answer": 1.00,
                    "cadence": 0.85 if str(lk) in {"arp", "counter"} else 0.94,
                }.get(pr, 1.0)
                m = (1.0 - s) + s * float(base) * float(ph)
                out_arr[i] = float(max(0.0, min(1.0, float(out_arr[i]) * float(m))))
            layer_targets[str(lk)] = out_arr
        out["layer_presence_targets"] = layer_targets
        return out

    @staticmethod
    def _whole_song_energy(
        owner: Any,
        *,
        section_role: str,
        section_index: int,
        form_section_count: int,
    ) -> float:
        role = str(section_role or "").strip().lower()
        form_n = max(1, int(form_section_count))
        idx = max(0, int(section_index))
        pos = float(idx) / float(max(1, form_n - 1))
        base = {
            "intro": 0.28,
            "a": 0.46,
            "verse": 0.46,
            "pre_chorus": 0.66,
            "b": 0.82,
            "chorus": 0.82,
            "hook": 0.84,
            "a_prime": 0.58,
            "tag": 0.88,
            "outro": 0.30,
            "ending": 0.26,
        }.get(role, 0.55)
        energy = float(base) + (0.10 * float(pos))
        try:
            payoff = resolve_final_chorus_payoff_state(
                owner,
                role=str(role),
                section_index=int(idx),
                form_section_count=int(form_n),
            )
            if bool(payoff.get("is_final_chorus", False)):
                from audiogen_core.config import CONFIG
                lift = float(getattr(CONFIG.composition, "whole_song_final_chorus_lift", 0.14) or 0.14)
                energy += max(0.0, min(0.30, float(lift)))
            elif bool(payoff.get("is_final_outro", False)):
                energy -= 0.10
        except Exception:
            pass
        return float(max(0.05, min(1.0, energy)))

    @staticmethod
    def _apply_whole_song_director(
        targets: Optional[Dict[str, Any]],
        curve: Dict[str, Any],
        *,
        owner: Any,
        section_role: str,
        section_index: int,
        form_section_count: int,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        enabled = resolve_config("composition", "whole_song_director_enabled", True, bool)
        strength = resolve_config("composition", "whole_song_director_strength", 0.68, float)
        s = max(0.0, min(1.0, float(strength)))
        c2 = dict(curve or {})
        if not enabled or s <= 1e-6:
            return targets, c2

        energy = _PlannerArrangementDynamicsMixin._whole_song_energy(
            owner,
            section_role=str(section_role),
            section_index=int(section_index),
            form_section_count=int(form_section_count),
        )
        # Multipliers are intentionally modest; role/emotion curves remain the source of truth.
        density_m = 0.78 + 0.48 * float(energy)
        motion_m = 0.82 + 0.38 * float(energy)
        tension_m = 0.84 + 0.34 * float(energy)
        arp_m = 0.70 + 0.56 * float(energy)
        dyn_m = 0.90 + 0.20 * float(energy)

        role = str(section_role or "").strip().lower()
        if role in {"outro", "ending"}:
            density_m *= 0.86
            arp_m *= 0.78
        if role in {"b", "chorus", "hook", "tag"}:
            density_m *= 1.04
            tension_m *= 1.03

        def _mul_curve(key: str, mult: float, lo: float, hi: float) -> None:
            try:
                base = float(c2.get(key, 1.0) or 1.0)
            except Exception:
                base = 1.0
            blended = (1.0 - s) * base + s * base * float(mult)
            c2[key] = float(max(lo, min(hi, blended)))

        _mul_curve("melody_total_notes_mult", density_m, 0.35, 2.5)
        _mul_curve("melody_density_mult", density_m, 0.35, 2.5)
        _mul_curve("chord_motion_mult", motion_m, 0.35, 2.0)
        _mul_curve("chord_rhythm_mult", motion_m, 0.35, 2.0)
        _mul_curve("arp_density_mult", arp_m, 0.0, 2.5)
        _mul_curve("section_dynamic", dyn_m, 0.85, 1.12)

        if not isinstance(targets, dict):
            c2["whole_song_energy"] = float(energy)
            return targets, c2

        out: Dict[str, Any] = {}
        for k, v in dict(targets or {}).items():
            if isinstance(v, list):
                out[str(k)] = list(v)
            elif isinstance(v, dict):
                out[str(k)] = {str(k2): (list(v2) if isinstance(v2, list) else v2) for k2, v2 in dict(v).items()}
            else:
                out[str(k)] = v

        def _mul_series(key: str, mult: float, lo: float, hi: float) -> None:
            arr = list(out.get(key, []) or [])
            if not arr:
                return
            m = (1.0 - s) + s * float(mult)
            out[key] = [float(max(lo, min(hi, float(v) * float(m)))) for v in arr]

        _mul_series("melody_density", density_m, 0.15, 2.25)
        _mul_series("chord_rhythm", motion_m, 0.35, 2.0)
        _mul_series("tension", tension_m, 0.0, 1.35)
        _mul_series("motif_strength", 0.86 + 0.38 * float(energy), 0.0, 2.0)

        lp = dict(out.get("layer_presence_targets", {}) or {})
        layer_mult = {
            "bass": 0.78 + 0.34 * float(energy),
            "chords": 0.88 + 0.18 * float(energy),
            "melody": 0.86 + 0.28 * float(energy),
            "arp": 0.68 + 0.46 * float(energy),
            "counter": 0.54 + 0.46 * float(energy),
        }
        for lk, arr in list(lp.items()):
            if not isinstance(arr, list):
                continue
            m = (1.0 - s) + s * float(layer_mult.get(str(lk), 1.0))
            lp[str(lk)] = [float(max(0.0, min(1.0, float(v) * float(m)))) for v in list(arr)]
        if lp:
            out["layer_presence_targets"] = lp
        out["whole_song_energy"] = float(energy)
        c2["whole_song_energy"] = float(energy)
        return out, c2

    @staticmethod
    def _apply_song_blueprint_targets(
        targets: Dict[str, Any],
        *,
        curve: Dict[str, Any],
        section_blueprint: Optional[Any],
        strength: float,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        out: Dict[str, Any] = {}
        for k, v in dict(targets or {}).items():
            if isinstance(v, list):
                out[str(k)] = list(v)
            elif isinstance(v, dict):
                out[str(k)] = {str(k2): (list(v2) if isinstance(v2, list) else v2) for k2, v2 in dict(v).items()}
            else:
                out[str(k)] = v
        c2 = dict(curve or {})
        bp = section_blueprint
        if bp is None:
            return out, c2
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return out, c2

        def _blend_seq(key: str, target: float, lo: float, hi: float) -> None:
            arr = list(out.get(key, []) or [])
            if not arr:
                return
            t = float(max(lo, min(hi, float(target))))
            for i in range(len(arr)):
                try:
                    base = float(arr[i])
                except Exception:
                    continue
                arr[i] = float(max(lo, min(hi, (1.0 - s) * base + s * t)))
            out[key] = arr

        motif_stage = str(getattr(bp, "motif_stage", "") or "").strip().lower()
        development_mode = str(c2.get("verse_development_mode", "") or "").strip().lower()
        cad_style = str(getattr(bp, "cadence_style", "") or "").strip().lower()
        cad_mult = float(getattr(bp, "cadence_strength_mult", 1.0) or 1.0)
        target_tension = float(getattr(bp, "target_tension", 0.6) or 0.6)
        reg_off = int(getattr(bp, "target_register_offset", 0) or 0)
        layer_contract = dict(getattr(bp, "layer_contract", {}) or {})
        harmony_hint = str(getattr(bp, "harmony_function_hint", "") or "").strip().upper()

        if reg_off != 0:
            try:
                cur = int(round(float(c2.get("melody_lane_center_offset", 0) or 0)))
            except Exception:
                cur = 0
            c2["melody_lane_center_offset"] = int(round((1.0 - s) * float(cur) + s * float(reg_off)))

        _blend_seq("tension", float(target_tension), 0.0, 1.35)

        cad_win = list(out.get("cadence_window", []) or [])
        if cad_win:
            n = len(cad_win)
            i_pen = max(0, n - 2)
            i_last = max(0, n - 1)
            if cad_style in {"closed", "authentic"}:
                cad_win[i_pen] = float(max(cad_win[i_pen], (1.0 - s) * cad_win[i_pen] + s * (0.82 * cad_mult)))
                cad_win[i_last] = float(max(cad_win[i_last], (1.0 - s) * cad_win[i_last] + s * (1.08 * cad_mult)))
            elif cad_style in {"open"}:
                cad_win[i_pen] = float(min(cad_win[i_pen], (1.0 - s) * cad_win[i_pen] + s * 0.62))
                cad_win[i_last] = float(min(cad_win[i_last], (1.0 - s) * cad_win[i_last] + s * 0.72))
            elif cad_style in {"deceptive"}:
                cad_win[i_pen] = float((1.0 - s) * cad_win[i_pen] + s * 0.78)
                cad_win[i_last] = float((1.0 - s) * cad_win[i_last] + s * 0.86)
            out["cadence_window"] = [float(max(0.0, min(1.35, v))) for v in cad_win]

        hf = list(out.get("harmony_function_target_by_bar", []) or [])
        if hf and harmony_hint:
            try:
                hf[-1] = str(harmony_hint)
                if len(hf) >= 2 and cad_style in {"closed", "authentic"}:
                    hf[-2] = "D"
            except Exception:
                pass
            out["harmony_function_target_by_bar"] = [str(x) for x in hf]

        ms = list(out.get("motif_strength", []) or [])
        md = list(out.get("melody_density", []) or [])
        if ms:
            if motif_stage in {"introduce", "state"}:
                ms = [float(max(0.0, min(2.0, (1.0 - s) * float(x) + s * 0.88))) for x in ms]
            elif motif_stage in {"build", "develop"}:
                ms = [float(max(0.0, min(2.0, (1.0 - s) * float(x) + s * 1.02))) for x in ms]
            elif motif_stage in {"restate", "payoff"}:
                ms = [float(max(0.0, min(2.0, (1.0 - s) * float(x) + s * 1.18))) for x in ms]
            elif motif_stage in {"fragment"}:
                ms = [float(max(0.0, min(2.0, (1.0 - s) * float(x) + s * 0.74))) for x in ms]
            out["motif_strength"] = ms
        if md:
            if motif_stage in {"payoff"}:
                md = [float(max(0.15, min(2.25, (1.0 - s) * float(x) + s * 0.86))) for x in md]
            elif motif_stage in {"fragment"}:
                md = [float(max(0.15, min(2.25, (1.0 - s) * float(x) + s * 0.68))) for x in md]
            out["melody_density"] = md

        role_lc = str(getattr(bp, "section_role", "") or "").strip().lower()
        if role_lc in {"a", "verse"}:
            out = _PlannerArrangementDynamicsMixin._apply_verse_sentence_targets(
                out,
                motif_stage=motif_stage,
                development_mode=development_mode,
                layer_contract=layer_contract,
                strength=0.72 * s,
            )

        lp = dict(out.get("layer_presence_targets", {}) or {})
        if layer_contract:
            for lk, arr in list(lp.items()):
                if not isinstance(arr, list):
                    continue
                t = float(layer_contract.get(str(lk), 1.0))
                out_arr = []
                for val in list(arr):
                    try:
                        b = float(val)
                    except Exception:
                        b = 0.0
                    out_arr.append(float(max(0.0, min(1.0, (1.0 - s) * b + s * t))))
                lp[str(lk)] = out_arr
            out["layer_presence_targets"] = lp

        return out, c2

