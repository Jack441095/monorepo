from audiogen_core.config import resolve_config
# composition/voice_leading_engine.py
# Project module `voice_leading_engine` (composition).
import heapq
import time

from typing import Dict, List, Optional, Tuple

from functools import lru_cache

from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped
from data.voicing_profiles import voicing_profile_for_emotion


@lru_cache(maxsize=128)
def _voicing_profile_cached(emotion_name: str) -> dict:
    # `voicing_profile_for_emotion` is pure for a given emotion name (data-driven).
    # Caching is quality-neutral and reduces repeated dict construction/lookups.
    try:
        return dict(voicing_profile_for_emotion(str(emotion_name or "")) or {})
    except Exception:
        return {}


class VoiceLeadingEngine:
    """Owns global voice-leading search and note-choice enumeration."""

    def __init__(self, owner, beam_width: int = 10):
        self.owner = owner
        self.beam_width = beam_width
        # Memoize part-option generation; key choices are constructed to avoid
        # changing musical output (only skipping repeated computation).
        self._poss_cache_nonchord: Dict[Tuple[str, str, int, str], List[List[int]]] = {}
        self._poss_cache_chord: Dict[Tuple[str, int, Tuple[int, ...], str], List[List[int]]] = {}
        # Hot-path cost memoization (quality-neutral): beam search repeatedly evaluates the
        # same choice pairs. These caches only bypass recomputation.
        self._vl_cost_cache: Dict[Tuple, float] = {}
        self._la_cost_cache: Dict[Tuple, float] = {}
        self._sorted_chord_cache: Dict[Tuple, Tuple[int, ...]] = {}
        # Cache for guide-tone pitch classes derived from chord symbols.
        # Keyed by symbol string; safe and quality-neutral (pure mapping).
        self._guide_pcs_cache: Dict[str, Tuple[Tuple[int, ...], Tuple[int, ...]]] = {}
        # 2026-07-04: whole-section memoization for `optimise_global`. Verified this is a
        # pure function of its explicit args for the lifetime of one engine instance --
        # no owner instance-state reads, no mutation of self.beam_width after __init__ --
        # unlike the per-note rhythm-distribution caching considered and rejected earlier
        # (that one had real per-note state, like occupied_steps/rep_tracker, that isn't
        # in its argument list). Profiling showed 76% of `optimise_global` calls in a real
        # song repeat an already-seen (chords, roots, bars, beats_per_bar, emotion_name)
        # signature -- e.g. every section built from the same locked chord progression.
        self._optimise_global_cache: Dict[Tuple, Tuple[List[int], List[List[int]], List[int], List[int]]] = {}

    def _guide_pcs_cached(self, symbol: str) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
        sym = str(symbol or "")
        cached = self._guide_pcs_cache.get(sym)
        if cached is not None:
            return cached
        try:
            ivs = list(self.owner._chord_symbol_to_intervals(str(sym)) or [])
            ivs = [int(i) % 12 for i in ivs]
        except Exception:
            ivs = []
        third = tuple(i for i in ivs if i in (3, 4)) or (3, 4)
        seventh = tuple(i for i in ivs if i in (10, 11)) or (10, 11)
        out = (third, seventh)
        # Cap growth in long-running sessions.
        if len(self._guide_pcs_cache) > 512:
            self._guide_pcs_cache.clear()
        self._guide_pcs_cache[sym] = out
        return out

    @staticmethod
    def _choice_key(choice: Optional[Dict[str, List[int]]]) -> Tuple:
        """
        Canonical key for a choice dict. Only includes musical degrees used in
        costs; ignores metadata keys.
        """
        if not choice:
            return ("", (), None, None, None)
        # Fast path: allow callers to stash a precomputed key to avoid recomputation
        # in tight beam-search loops (quality-neutral; purely caching metadata).
        try:
            k0 = choice.get("_vl_cache_key")
            if k0 is not None:
                return k0
        except Exception:
            pass
        # 2026-07-04 (docs/AUDIOGEN_COMPOSITION_PLAN.md latency work): each of these used
        # to call `choice.get(key)` twice (once for the truthiness check, once inside the
        # expression) plus a dead `or [None]` fallback that can never trigger once the
        # outer truthiness check has already passed. Called 722K times in a real song
        # (2.3s tottime alone), so the redundant dict lookups were real, measurable cost.
        try:
            raw_bass = choice.get("bass")
            bass = int(raw_bass[0]) if raw_bass else None
        except Exception:
            bass = None
        try:
            raw_melody = choice.get("melody")
            melody = int(raw_melody[0]) if raw_melody else None
        except Exception:
            melody = None
        try:
            raw_harmony = choice.get("harmony")
            harmony = int(raw_harmony[0]) if raw_harmony else None
        except Exception:
            harmony = None
        try:
            # Chord voicings generated by this engine are already sorted/unique in most cases.
            # Avoid sorting in the hot path; fall back to sorting only if needed.
            raw_ch = choice.get("chord") or []
            if isinstance(raw_ch, (list, tuple)) and raw_ch:
                # Fast convert + check monotonicity.
                nn = []
                prev = None
                sorted_ok = True
                for x in raw_ch:
                    if not isinstance(x, int):
                        continue
                    xi = int(x)
                    nn.append(xi)
                    if prev is not None and xi < prev:
                        sorted_ok = False
                    prev = xi
                if sorted_ok:
                    chord_notes = tuple(nn)
                else:
                    chord_notes = tuple(sorted(nn))
            else:
                chord_notes = ()
        except Exception:
            chord_notes = ()
        # Include chord symbol/root if present since some costs use them indirectly.
        sym = str(choice.get("_chord_symbol", "") or "")
        try:
            root = int(choice.get("_chord_root", 0) or 0)
        except Exception:
            root = 0
        k = (sym, int(root), chord_notes, bass, melody, harmony)
        try:
            choice["_vl_cache_key"] = k
        except Exception:
            pass
        return k

    def _sorted_chord(self, choice: Dict[str, List[int]]) -> Tuple[int, ...]:
        """
        Cached sorted chord notes for a choice (used by lookahead + voicing costs).
        """
        try:
            ck = choice.get("_vl_cache_key")
        except Exception:
            ck = None
        if ck is None:
            ck = self._choice_key(choice)
        cached = self._sorted_chord_cache.get(ck)
        if cached is not None:
            return cached
        chord_notes = ck[2] if len(ck) >= 3 else ()
        self._sorted_chord_cache[ck] = chord_notes
        return chord_notes

    def voice_leading_cost(
        self,
        prev_notes: Dict[str, List[int]],
        curr_notes: Dict[str, List[int]],
        parallel_penalty: float = 50.0,
        crossing_penalty: float = 30.0,
        large_leap_penalty: float = 10.0,
        step_reward: float = -2.0,
        common_tone_reward: float = -3.0,
    ) -> float:
        cost = 0.0
        # Optional tighter piano-like chord motion penalties (configurable).
        chord_voice_max_leap = resolve_config("composition", "chord_voice_max_leap_semitones", 7, int)
        chord_voice_leap_pen = resolve_config("composition", "chord_voice_leap_penalty", 0.0, float)
        chord_center_jump_pen = resolve_config("composition", "chord_center_jump_penalty", 0.0, float)
        chord_voice_max_leap = max(0, int(chord_voice_max_leap))
        chord_voice_leap_pen = max(0.0, float(chord_voice_leap_pen))
        chord_center_jump_pen = max(0.0, float(chord_center_jump_pen))

        def note(notes_dict, part):
            v = notes_dict.get(part)
            return v[0] if v else None

        for v in ["bass", "melody", "harmony"]:
            if v in prev_notes and v in curr_notes:
                p = note(prev_notes, v)
                c = note(curr_notes, v)
                if p is not None and c is not None:
                    interval = c - p
                    if abs(interval) > 7:
                        cost += large_leap_penalty * (abs(interval) / 7)
                    if abs(interval) <= 2:
                        cost += step_reward

        pb = note(prev_notes, "bass")
        cb = note(curr_notes, "bass")
        pm = note(prev_notes, "melody")
        cm = note(curr_notes, "melody")
        if pb is not None and cb is not None and pm is not None and cm is not None:
            bd = cb - pb
            md = cm - pm
            if bd != 0 and md != 0 and (bd > 0) != (md > 0):
                cost += -1.8

        voice_pairs = [("bass", "melody"), ("bass", "harmony"), ("melody", "harmony")]
        for v1, v2 in voice_pairs:
            if v1 in prev_notes and v2 in prev_notes and v1 in curr_notes and v2 in curr_notes:
                prev_int = abs(note(prev_notes, v1) - note(prev_notes, v2)) % 12
                curr_int = abs(note(curr_notes, v1) - note(curr_notes, v2)) % 12
                if prev_int in (0, 7) and curr_int in (0, 7) and prev_int == curr_int:
                    cost += parallel_penalty

        order = ["bass", "chord", "harmony", "melody"]
        for i in range(len(order) - 1):
            v_low = order[i]
            v_high = order[i + 1]
            if v_low in curr_notes and v_high in curr_notes:
                low_note = min(curr_notes[v_low]) if v_low == "chord" else note(curr_notes, v_low)
                high_note = max(curr_notes[v_high]) if v_high == "chord" else note(curr_notes, v_high)
                if low_note is not None and high_note is not None and low_note >= high_note:
                    cost += crossing_penalty

        if "chord" in prev_notes and "chord" in curr_notes:
            # Use cached sorted chord notes when available (stored by _choice_key).
            # This avoids repeated sorting in the hot path without changing output.
            try:
                pk = prev_notes.get("_vl_cache_key")
                prev_chord = list(pk[2]) if pk is not None and len(pk) >= 3 else None
            except Exception:
                prev_chord = None
            if prev_chord is None:
                prev_chord = sorted(prev_notes.get("chord") or [])

            try:
                ck = curr_notes.get("_vl_cache_key")
                curr_chord = list(ck[2]) if ck is not None and len(ck) >= 3 else None
            except Exception:
                curr_chord = None
            if curr_chord is None:
                curr_chord = sorted(curr_notes.get("chord") or [])

            # Common-tone reward (set intersection).
            common = set(prev_chord).intersection(curr_chord)
            cost += common_tone_reward * len(common)

            min_len = min(len(prev_chord), len(curr_chord))
            cost += sum(abs(prev_chord[i] - curr_chord[i]) for i in range(min_len))
            if len(curr_chord) > min_len:
                cost += sum(curr_chord[min_len:]) * 2

            # Extra: penalize big per-voice leaps inside the chord.
            if chord_voice_leap_pen > 1e-9 and chord_voice_max_leap > 0 and min_len > 0:
                for i in range(min_len):
                    try:
                        d = abs(int(curr_chord[i]) - int(prev_chord[i]))
                    except Exception:
                        continue
                    if d > chord_voice_max_leap:
                        cost += chord_voice_leap_pen * float(d - chord_voice_max_leap)

            # Extra: penalize dramatic chord-center (median) jumps.
            if chord_center_jump_pen > 1e-9 and prev_chord and curr_chord:
                try:
                    pc = int(prev_chord[len(prev_chord) // 2])
                    cc = int(curr_chord[len(curr_chord) // 2])
                    cd = abs(int(cc) - int(pc))
                    # Allow a little movement, then penalize.
                    if cd > (chord_voice_max_leap + 2):
                        cost += chord_center_jump_pen * float(cd - (chord_voice_max_leap + 2))
                except Exception:
                    pass

            # Extra: guide-tone anchoring (3rd/7th). Keep these voices stable across bars.
            gt_enabled = resolve_config("composition", "chord_guide_tone_anchor_enabled", True, bool)
            gt_w = resolve_config("composition", "chord_guide_tone_anchor_weight", 1.25, float)
            gt_max = resolve_config("composition", "chord_guide_tone_max_motion_semitones", 3, int)
            if gt_enabled and gt_w > 1e-9 and prev_chord and curr_chord:
                try:
                    # If we have chord root/symbol metadata, anchor true guide tones (3rd/7th).
                    # Otherwise fall back to closest-note matching.
                    prev_root = prev_notes.get("_chord_root", [None])[0] if isinstance(prev_notes.get("_chord_root", None), list) else prev_notes.get("_chord_root", None)
                    curr_root = curr_notes.get("_chord_root", [None])[0] if isinstance(curr_notes.get("_chord_root", None), list) else curr_notes.get("_chord_root", None)
                    prev_sym = prev_notes.get("_chord_symbol", "")
                    curr_sym = curr_notes.get("_chord_symbol", "")

                    def _median(ns: List[int]) -> int:
                        nn = sorted(int(n) for n in ns)
                        return int(nn[len(nn) // 2]) if nn else 0

                    def _pick_tone(chord_ns: List[int], root_m: int, pcs_set: set[int]) -> Optional[int]:
                        if not chord_ns:
                            return None
                        med = _median(chord_ns)
                        best = None
                        best_d = None
                        for n in chord_ns:
                            rel = (int(n) - int(root_m)) % 12
                            if rel not in pcs_set:
                                continue
                            d = abs(int(n) - int(med))
                            if best is None or d < int(best_d):
                                best = int(n)
                                best_d = int(d)
                        return best

                    if isinstance(prev_root, int) and isinstance(curr_root, int):
                        p3, p7 = self._guide_pcs_cached(str(prev_sym))
                        c3, c7 = self._guide_pcs_cached(str(curr_sym))
                        p3s = {int(x) % 12 for x in p3}
                        p7s = {int(x) % 12 for x in p7}
                        c3s = {int(x) % 12 for x in c3}
                        c7s = {int(x) % 12 for x in c7}
                        prev3 = _pick_tone(prev_chord, int(prev_root), p3s)
                        prev7 = _pick_tone(prev_chord, int(prev_root), p7s)
                        curr3 = _pick_tone(curr_chord, int(curr_root), c3s)
                        curr7 = _pick_tone(curr_chord, int(curr_root), c7s)
                        pairs = [(prev3, curr3), (prev7, curr7)]
                        for a, b in pairs:
                            if a is None or b is None:
                                continue
                            d = abs(int(b) - int(a))
                            if d > int(gt_max):
                                cost += float(gt_w) * float(d - int(gt_max))
                    else:
                        # Fallback: pair the two closest-moving notes.
                        pairs = []
                        for a in prev_chord:
                            for b in curr_chord:
                                pairs.append((int(a), int(b), abs(int(a) - int(b))))
                        pairs.sort(key=lambda x: x[2])
                        used_a = set()
                        used_b = set()
                        out = []
                        for a, b, _d0 in pairs:
                            if a in used_a or b in used_b:
                                continue
                            used_a.add(a)
                            used_b.add(b)
                            out.append((a, b))
                            if len(out) >= 2:
                                break
                        for a, b in out:
                            d = abs(int(b) - int(a))
                            if d > int(gt_max):
                                cost += float(gt_w) * float(d - int(gt_max))
                except Exception:
                    pass

        return cost

    def get_possible_notes_for_part(
        self,
        part: str,
        chord: str,
        root: int,
        prev_notes: Optional[List[int]] = None,
        *,
        emotion_name: str = "",
    ) -> List[List[int]]:
        # Normalize cache keys aggressively to avoid float/noise differences.
        chord_s = str(chord or "")
        root_i = int(root)
        emo_s = str(emotion_name or "")

        if part == "bass":
            # For bass/melody/harmony, `prev_notes` only changes ordering, not the set.
            key = ("bass", chord_s, root_i, emo_s)
            out0 = self._poss_cache_nonchord.get(key)
            if out0 is None:
                all_tones = self.owner._get_bass_chord_tones(chord_s, root_i)
                if len(all_tones) >= 2:
                    root_pc = all_tones[0] % 12
                    fifth = next((n for n in all_tones if (n - root_pc) % 12 == 7), None)
                    notes = [all_tones[0], fifth] if fifth is not None else all_tones[:2]
                else:
                    notes = all_tones
                out0 = [[note] for note in notes]
                self._poss_cache_nonchord[key] = out0

            out = list(out0)
            if prev_notes:
                target = int(prev_notes[0])
                out = sorted(out, key=lambda notes: abs(int(notes[0]) - target))
            return out

        if part == "chord":
            # For chords, `prev_notes` can affect the voicing function itself, so include it.
            prev_key = tuple(sorted(int(n) for n in (prev_notes or []) if isinstance(n, int)))
            ckey = (chord_s, root_i, prev_key, emo_s)
            cached = self._poss_cache_chord.get(ckey)
            if cached is not None:
                return list(cached)

            prof = _voicing_profile_cached(emo_s)
            styles = list(prof.get("chord_styles") or [])
            prefer_stable = bool(prof.get("prefer_stable", False))
            # Safety: always keep at least a basic pool.
            if not styles:
                styles = ["drop2", "closed", "open", "tenth", "shell"]
            # Include 10th / barre options for more guitar/piano-like spreads.
            # Also keep a fallback set at the end to avoid profile mistakes.
            fallback = ["drop2", "closed", "open", "tenth", "barre", "shell"]
            for s in fallback:
                if s not in styles:
                    styles.append(s)
            # Keep chord voicings lean (piano-like comping) to avoid dramatic size/register swings.
            max_tones = resolve_config("composition", "max_chord_tones_in_voicing", 4, int)
            allow_ext = resolve_config("composition", "chord_voicing_allow_extensions", True, bool)
            allow_tenths = resolve_config("composition", "chord_voicing_allow_tenths", True, bool)
            hard_reject = resolve_config("composition", "chord_voicing_hard_cluster_reject", True, bool)
            min_span_3 = resolve_config("composition", "chord_voicing_min_span_3_tones_semitones", 10, int)
            min_span_4 = resolve_config("composition", "chord_voicing_min_span_4_tones_semitones", 14, int)
            sp_thr = resolve_config("composition", "chord_voicing_low_spacing_threshold_midi", 52, int)
            sp_min = resolve_config("composition", "chord_voicing_low_spacing_min_semitones", 4, int)
            if prefer_stable:
                max_tones = min(int(max_tones), 4)
            max_tones = max(2, min(6, int(max_tones)))
            min_span_3 = max(0, int(min_span_3))
            min_span_4 = max(0, int(min_span_4))
            sp_thr = int(sp_thr)
            sp_min = max(0, int(sp_min))
            pop_color_priority = [2, 9] if prefer_stable else [2, 9, 5]

            # Ensure the 10th option is present when enabled (3rd can be up an octave).
            if allow_tenths and "tenth" not in [s.lower() for s in styles]:
                styles.insert(0, "tenth")
            if not allow_tenths:
                styles = [s for s in styles if str(s).lower() not in {"tenth", "10th"}]
            if prefer_stable:
                prioritized = []
                for s in ["shell", "drop2", "closed", "tenth", "open"]:
                    if s in styles and s not in prioritized:
                        prioritized.append(s)
                for s in styles:
                    if s not in prioritized:
                        prioritized.append(s)
                styles = prioritized

            def _guide_shell(symbol: str, root_midi: int) -> List[int]:
                """
                Pianist-like guide-tone voicing candidate: prioritize 3rd+7th (+root, +color).
                Uses chord intervals (relative to root) and keeps it compact.
                """
                try:
                    ivs = list(self.owner._chord_symbol_to_intervals(symbol) or [])
                except Exception:
                    ivs = []
                if not ivs:
                    return []
                ivs = sorted(set(int(i) for i in ivs))
                # Pick third + seventh if available.
                third = next((i for i in ivs if i % 12 in {3, 4}), None)
                seventh = next((i for i in ivs if i % 12 in {10, 11}), None)
                fifth = next((i for i in ivs if i % 12 == 7), None)
                # Color preference: 9, #11/11, 13.
                color = next((i for i in ivs if i % 12 in set(pop_color_priority)), None) if allow_ext else None

                out = [0]
                if third is not None:
                    out.append(int(third))
                if seventh is not None:
                    out.append(int(seventh))
                # Add color before fifth (cinematic shells often omit the fifth).
                if color is not None and len(out) < max_tones:
                    out.append(int(color))
                if fifth is not None and len(out) < max_tones:
                    out.append(int(fifth))

                # Convert to midi notes and apply a mild 10th option if enabled.
                notes = [int(root_midi + int(i)) for i in out]
                if allow_tenths and third is not None:
                    # If the third is low, raise it by an octave to form a 10th.
                    for k, n in enumerate(notes):
                        if (n - root_midi) % 12 in {3, 4} and n < (root_midi + 4 + 12):
                            notes[k] = int(n + 12)
                            break
                return sorted(set(notes))

            def _pick_by_pc(nn: List[int], pcs: List[int], *, root_midi: int) -> List[int]:
                # Pick one representative note for each pitch class in `pcs`, preferring notes
                # closest to the chord's median register (keeps hand motion stable).
                if not nn:
                    return []
                med = int(nn[len(nn) // 2])
                out: List[int] = []
                for pc in pcs:
                    cand = [n for n in nn if ((n - root_midi) % 12) == (pc % 12)]
                    if not cand:
                        continue
                    best = min(cand, key=lambda n: abs(int(n) - med))
                    out.append(int(best))
                # Keep ordering stable/ascending.
                return sorted(set(out))

            def _trim(notes: List[int], *, root_midi: int) -> List[int]:
                nn = sorted({int(n) for n in (notes or []) if isinstance(n, int)})
                if len(nn) <= max_tones:
                    return nn
                if max_tones <= 2:
                    return [nn[0], nn[-1]]

                # Prioritize functional chord tones first, then (optionally) extensions/colors.
                # pcs are intervals relative to root: 0=root, 3/4=3rd, 7=5th, 10/11=7th, 2=9th, 5=11th, 9=13th, 6/#11.
                # 1) Always try to keep root + third + seventh (most "piano" shell).
                core = _pick_by_pc(nn, [0, 3, 4, 10, 11], root_midi=root_midi)
                # Ensure at most one of {m3,M3} and one of {m7,M7}.
                picked: List[int] = []
                if core:
                    # root
                    picked += _pick_by_pc(nn, [0], root_midi=root_midi)
                    # third (prefer whichever exists)
                    t = _pick_by_pc(nn, [4], root_midi=root_midi) or _pick_by_pc(nn, [3], root_midi=root_midi)
                    picked += t[:1]
                    # seventh (prefer m7 then M7 if present)
                    s = _pick_by_pc(nn, [10], root_midi=root_midi) or _pick_by_pc(nn, [11], root_midi=root_midi)
                    picked += s[:1]
                picked = sorted(set(picked))

                # 2) Add a color tone if allowed (9/#11/11/13) and we have room.
                if allow_ext and len(picked) < max_tones:
                    # Prefer 9, then #11/11, then 13.
                    color = _pick_by_pc(nn, pop_color_priority, root_midi=root_midi)
                    for n in color:
                        if len(picked) >= max_tones:
                            break
                        picked.append(int(n))
                    picked = sorted(set(picked))

                # 3) Add the fifth if there's still room (least important in dense voicings).
                if len(picked) < max_tones:
                    fifth = _pick_by_pc(nn, [7], root_midi=root_midi)
                    for n in fifth:
                        if len(picked) >= max_tones:
                            break
                        picked.append(int(n))
                    picked = sorted(set(picked))

                # 4) If still short (rare), fill with nearest-to-median unused notes.
                if len(picked) < max_tones:
                    med = int(nn[len(nn) // 2])
                    for n in sorted([n for n in nn if n not in set(picked)], key=lambda n: abs(int(n) - med)):
                        picked.append(int(n))
                        if len(picked) >= max_tones:
                            break

                # 5) If still too many (possible duplicates), trim by closeness to median.
                if len(picked) > max_tones:
                    med = int(nn[len(nn) // 2])
                    picked = sorted(sorted(set(picked)), key=lambda n: (abs(int(n) - med), int(n)))[:max_tones]
                    picked = sorted(picked)
                # Pop-safe consonance: prefer omitting 11/#11/b9/b13-type colors from
                # stable comping voicings unless they're the only available color tones.
                if prefer_stable and len(picked) > 3:
                    unstable = [n for n in picked if ((int(n) - int(root_midi)) % 12) in {1, 5, 6, 8}]
                    if unstable:
                        keep = [n for n in picked if n not in unstable]
                        med = int(nn[len(nn) // 2])
                        refill = [n for n in nn if n not in set(keep) and n not in set(unstable)]
                        refill = sorted(refill, key=lambda n: (abs(int(n) - med), int(n)))
                        for n in refill:
                            keep.append(int(n))
                            keep = sorted(set(keep))
                            if len(keep) >= min(max_tones, len(picked)):
                                break
                        picked = sorted(keep[:max_tones])
                return picked

            def _passes_hard_voicing_guardrails(notes: List[int]) -> bool:
                """
                Hard guardrails to avoid cluster chords in comping:
                - low-register adjacent spacing min
                - minimum overall chord span by chord size (3/4 tones)
                """
                nn = sorted(int(n) for n in (notes or []) if isinstance(n, int))
                if len(nn) < 2:
                    return True
                # 1) Low-register spacing: avoid tight stacks below sp_thr.
                if sp_min > 0:
                    for a, b in zip(nn, nn[1:]):
                        if int(a) >= int(sp_thr) and int(b) >= int(sp_thr):
                            continue
                        if (int(b) - int(a)) < int(sp_min):
                            return False
                # 2) Minimum span: discourage “all tones in one octave”.
                span = int(nn[-1]) - int(nn[0])
                if len(nn) >= 4 and min_span_4 > 0 and span < int(min_span_4):
                    return False
                if len(nn) == 3 and min_span_3 > 0 and span < int(min_span_3):
                    return False
                return True

            out = []
            # Guide-tone shell first (biases beam search toward pianist shapes).
            try:
                g0 = _guide_shell(str(chord_s or ""), int(root_i))
                if g0:
                    g0t = _trim(g0, root_midi=int(root_i))
                    if (not hard_reject) or _passes_hard_voicing_guardrails(g0t):
                        out.append(g0t)
            except Exception:
                pass
            for style in styles:
                voiced = self.owner._chord_voicing(chord_s, root_i, style=style, prev_notes=prev_notes)
                vt = _trim(voiced, root_midi=int(root_i))
                if hard_reject and not _passes_hard_voicing_guardrails(vt):
                    continue
                out.append(vt)
            # Safety: if hard guardrails filtered everything, fall back to the best trimmed candidates.
            if not out:
                try:
                    g0 = _guide_shell(str(chord_s or ""), int(root_i))
                    if g0:
                        out.append(_trim(g0, root_midi=int(root_i)))
                except Exception:
                    pass
                for style in styles:
                    try:
                        voiced = self.owner._chord_voicing(chord_s, root_i, style=style, prev_notes=prev_notes)
                        out.append(_trim(voiced, root_midi=int(root_i)))
                    except Exception:
                        continue
            if prev_notes:
                prev_sorted = sorted(int(n) for n in prev_notes)
                out = sorted(
                    out,
                    key=lambda notes: sum(
                        abs(int(a) - int(b))
                        for a, b in zip(sorted(int(n) for n in notes), prev_sorted)
                    ),
                )
            self._poss_cache_chord[ckey] = list(out)
            return out

        if part in ("melody", "harmony"):
            key = (str(part), chord_s, root_i, emo_s)
            out0 = self._poss_cache_nonchord.get(key)
            if out0 is None:
                all_notes = self.owner._chord_symbol_to_notes(chord_s, root_i)
                if part == "melody":
                    options = [n for n in all_notes if n >= 60] or all_notes
                else:
                    options = [n for n in all_notes if 48 <= n < 72] or all_notes
                options = sorted(set(options or all_notes))
                out0 = [[note] for note in options]
                self._poss_cache_nonchord[key] = out0

            out = list(out0)
            if prev_notes:
                target = int(prev_notes[0])
                # Avoid sorting huge lists during dataset generation; keep only the closest few.
                max_opts = resolve_config("composition", "voice_leading_max_part_options", 24, int)
                max_opts = max(4, min(96, int(max_opts)))
                if len(out) > max_opts:
                    out = heapq.nsmallest(max_opts, out, key=lambda notes: abs(int(notes[0]) - target))
                else:
                    out = sorted(out, key=lambda notes: abs(int(notes[0]) - target))
            return out

        return []

    @staticmethod
    def enumerate_combinations(possibilities: Dict[str, List[List[int]]]) -> List[Dict[str, List[int]]]:
        keys = ["bass", "chord", "melody", "harmony"]
        options = [possibilities[k] for k in keys]
        combinations = []
        for bass in options[0]:
            for chord in options[1]:
                for melody in options[2]:
                    for harmony in options[3]:
                        combinations.append({
                            "bass": bass,
                            "chord": chord,
                            "melody": melody,
                            "harmony": harmony,
                        })
        return combinations

    @staticmethod
    def enumerate_combinations_iter(possibilities: Dict[str, List[List[int]]]):
        """
        Iterator form of `enumerate_combinations` to avoid allocating a full list.
        Quality-neutral: yields the same dict shapes in the same nesting order.
        """
        keys = ["bass", "chord", "melody", "harmony"]
        options = [possibilities[k] for k in keys]
        for bass in options[0]:
            for chord in options[1]:
                for melody in options[2]:
                    for harmony in options[3]:
                        yield {
                            "bass": bass,
                            "chord": chord,
                            "melody": melody,
                            "harmony": harmony,
                        }

    def optimise_global(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float = 4.0,
        *,
        emotion_name: str = "",
    ) -> Tuple[List[int], List[List[int]], List[int], List[int]]:
        cache_key = (tuple(chords), tuple(roots), int(bars), float(beats_per_bar), str(emotion_name or ""))
        cached = self._optimise_global_cache.get(cache_key)
        if cached is not None:
            bass_c, chord_c, melody_c, harmony_c = cached
            # Return copies, not the cached lists themselves -- callers may mutate their
            # result in place downstream, and doing so would silently corrupt the cache.
            return (
                list(bass_c),
                [list(v) for v in chord_c],
                list(melody_c),
                list(harmony_c),
            )

        owner = self.owner

        cadence_enabled = resolve_config("composition", "cadence_voice_leading_enabled", True, bool)
        cadence_w = resolve_config("composition", "cadence_voice_leading_weight", 1.0, float)
        lookahead_strength = resolve_config("composition", "chord_voicing_lookahead_strength", 0.0, float)
        budget_s = resolve_config("composition", "voice_leading_time_budget_s", 0.0, float)
        beam_override = resolve_config("composition", "voice_leading_beam_width", 0, int)
        max_part_opts = resolve_config("composition", "voice_leading_max_part_options", 24, int)
        cadence_w = max(0.0, float(cadence_w))
        lookahead_strength = max(0.0, min(1.0, float(lookahead_strength)))
        budget_s = max(0.0, float(budget_s))
        beam_override = max(0, int(beam_override))
        max_part_opts = max(4, min(96, int(max_part_opts)))

        t0 = time.perf_counter()
        eff_beam_width = int(self.beam_width)
        if beam_override > 0:
            eff_beam_width = max(1, min(int(eff_beam_width), int(beam_override)))
        # Emotion anchors: scale cadence resolution pressure by archetype.
        try:
            from data.emotion_anchors import anchors_for_emotion

            cad_style = str(getattr(anchors_for_emotion(emotion_name), "cadence", "authentic") or "authentic").lower()
            cad_style = cad_style if cad_style in {"authentic", "plagal", "suspended", "avoid"} else "authentic"
            cad_scale = {
                "authentic": 1.25,
                "plagal": 1.05,
                "suspended": 0.85,
                "avoid": 0.60,
            }.get(cad_style, 1.0)
            cadence_w *= float(cad_scale)
        except Exception:
            pass

        def phrase_role_for_bar(bar_idx: int) -> str:
            try:
                phrase_len = phrase_length_bars_clamped(1, 16)
                return owner.chord_utils.phrase_role(
                    int(bar_idx),
                    int(bars),
                    phrase_length=int(phrase_len),
                )
            except Exception:
                return "continuation"

        def cadence_resolution_cost(
            prev_choice: Dict[str, List[int]],
            curr_choice: Dict[str, List[int]],
            *,
            chord: str,
            root: int,
            role: str,
            is_final_bar: bool,
        ) -> float:
            """
            Extra cost term applied on cadence-role bars (and final bar).
            Encourages:
            - bass in root position
            - melody landing on stable chord tones (root/3rd/5th)
            - smaller approach motion into the cadence
            """
            if not cadence_enabled or cadence_w <= 1e-9:
                return 0.0
            if (role or "") != "cadence" and not is_final_bar:
                return 0.0

            root_pc = int(root) % 12
            # Determine "stable" melody pitch classes given chord quality.
            try:
                sym = owner._simplify_chord_for_markov(chord)
            except Exception:
                sym = ""
            # Basic quality inference from symbol/string.
            chord_l = (chord or "").lower()
            is_minor = ("min" in chord_l) or ("m" in chord_l and "maj" not in chord_l)
            if sym == "min":
                is_minor = True
            if sym == "maj":
                is_minor = False

            stable = {0, 7}  # root, fifth
            stable.add(3 if is_minor else 4)  # third
            # For dominant/sus, still prefer 1/3/5 on cadence landing.

            cost = 0.0

            # Bass: reward root-position.
            try:
                bass_pc = int(curr_choice.get("bass", [root])[0]) % 12
                if bass_pc != root_pc:
                    cost += 1.15
            except Exception:
                pass

            # Melody: prefer stable chord tones at cadence landing.
            try:
                mel = int(curr_choice.get("melody", [0])[0])
                mel_int = (mel % 12 - root_pc) % 12
                if mel_int in stable:
                    cost += -1.05
                else:
                    # Penalize more strongly on final bar.
                    cost += 0.85 * (1.35 if is_final_bar else 1.0)
            except Exception:
                pass

            # Approach: discourage a large leap into the cadence melody note.
            try:
                pm = int(prev_choice.get("melody", [0])[0])
                cm = int(curr_choice.get("melody", [0])[0])
                leap = abs(cm - pm)
                if leap > 7:
                    cost += 0.55 * (leap / 7.0)
            except Exception:
                pass

            return float(cost) * float(cadence_w)

        def possibilities_for_bar(bar: int, prev_choice: Optional[Dict[str, List[int]]] = None) -> Dict[str, List[List[int]]]:
            chord = chords[bar]
            root = roots[bar]
            poss: Dict[str, List[List[int]]] = {}
            for part in ["bass", "chord", "melody", "harmony"]:
                prev = None if prev_choice is None else prev_choice.get(part)
                part_options = self.get_possible_notes_for_part(part, chord, root, prev, emotion_name=emotion_name)
                # Keep the search beam practical while preserving local alternatives.
                poss[part] = list(part_options[: max_part_opts] if len(part_options) > max_part_opts else part_options)
            return poss

        def lookahead_cost(curr_choice: Dict[str, List[int]], next_choice: Dict[str, List[int]]) -> float:
            """
            Small extra cost that encourages chord voicings which are closer to the *next* bar.
            This makes the harmony feel more "played" (anticipating the next shape) without
            overriding the main voice-leading cost.
            """
            if lookahead_strength <= 1e-9:
                return 0.0
            # Memoize: in beam search, these pairwise distances repeat heavily.
            try:
                ck = curr_choice.get("_vl_cache_key")
                if ck is None:
                    ck = self._choice_key(curr_choice)
                nk = next_choice.get("_vl_cache_key")
                if nk is None:
                    nk = self._choice_key(next_choice)
                k = (ck, nk, float(lookahead_strength))
                cached = self._la_cost_cache.get(k)
                if cached is not None:
                    return float(cached)
            except Exception:
                k = None
            try:
                cur = list(self._sorted_chord(curr_choice))
                nxt = list(self._sorted_chord(next_choice))
                if not cur or not nxt:
                    return 0.0
                m = min(len(cur), len(nxt))
                # Pairwise distance for the lowest m voices.
                d = sum(abs(int(cur[i]) - int(nxt[i])) for i in range(m))
                # Normalize lightly so the knob is reasonably stable across chord sizes.
                d = float(d) / float(m)
                out = float(d) * float(lookahead_strength)
                if k is not None:
                    # Cap cache size to avoid unbounded growth in long sessions.
                    if len(self._la_cost_cache) > 20000:
                        self._la_cost_cache.clear()
                        self._sorted_chord_cache.clear()
                    self._la_cost_cache[k] = float(out)
                return float(out)
            except Exception:
                return 0.0

        # Pull voicing quality config once (avoid per-call CONFIG reads).
        mud_thr = resolve_config("composition", "chord_voicing_mud_threshold_midi", 40, int)
        mud_pen = resolve_config("composition", "chord_voicing_mud_penalty", 0.55, float)
        sp_thr = resolve_config("composition", "chord_voicing_low_spacing_threshold_midi", 52, int)
        sp_min = resolve_config("composition", "chord_voicing_low_spacing_min_semitones", 4, int)
        sp_pen = resolve_config("composition", "chord_voicing_spacing_penalty", 0.35, float)
        top_bonus = resolve_config("composition", "chord_voicing_top_continuity_bonus", 0.4, float)
        top_max = resolve_config("composition", "chord_voicing_top_continuity_max_semitones", 7, int)
        # Memoize voicing-quality costs within this optimise_global() call.
        # Keyed by (prev_chord_tuple, curr_chord_tuple).
        _cvq_cache: Dict[Tuple[Tuple[int, ...], Tuple[int, ...]], float] = {}

        def chord_voicing_quality_cost(prev_choice: Optional[Dict[str, List[int]]], curr_choice: Dict[str, List[int]]) -> float:
            """
            Extra "produced voicing" cost terms:
            - low-end mud penalty (too many chord tones below a threshold)
            - spacing penalty (clustered low intervals)
            - top-voice continuity bonus (keep comping coherent)
            """
            # Chord notes (sorted tuples) from cached key if possible.
            try:
                curr_ns = self._sorted_chord(curr_choice)
            except Exception:
                curr_ns = tuple(sorted(int(n) for n in (curr_choice.get("chord") or []) if isinstance(n, int)))
            if not curr_ns:
                return 0.0
            try:
                prev_ns = () if prev_choice is None else self._sorted_chord(prev_choice)
            except Exception:
                prev_ns = () if prev_choice is None else tuple(
                    sorted(int(n) for n in (prev_choice.get("chord") or []) if isinstance(n, int))
                )
            k = (prev_ns, curr_ns)
            cached = _cvq_cache.get(k)
            if cached is not None:
                return float(cached)

            cost = 0.0

            # 1) Low-end mud: penalize extra low notes.
            if mud_pen > 1e-9:
                low = sum(1 for n in curr_ns if int(n) < int(mud_thr))
                if low > 0:
                    cost += float(mud_pen) * float(low)

            # 2) Spacing in low register: penalize clustered semitone gaps below threshold.
            if sp_pen > 1e-9 and sp_min > 0:
                for a, b in zip(curr_ns, curr_ns[1:]):
                    if int(a) >= int(sp_thr) and int(b) >= int(sp_thr):
                        continue
                    gap = int(b) - int(a)
                    if gap < int(sp_min):
                        cost += float(sp_pen) * float(int(sp_min) - int(gap))

            # 3) Top voice continuity: reward keeping top voice stable (bonus = negative cost).
            if top_bonus > 1e-9 and prev_choice is not None and prev_ns:
                try:
                    d = abs(int(curr_ns[-1]) - int(prev_ns[-1]))
                    if d <= int(top_max):
                        cost -= float(top_bonus) * (1.0 - float(d) / max(1.0, float(top_max)))
                except Exception:
                    pass

            out = float(cost)
            # Keep the cache bounded.
            if len(_cvq_cache) > 50000:
                _cvq_cache.clear()
            _cvq_cache[k] = out
            return out

        beam = []
        first_poss = possibilities_for_bar(0, None)
        for comb in self.enumerate_combinations_iter(first_poss):
            # Attach chord metadata so guide-tone anchoring can be chord-aware.
            comb["_chord_symbol"] = str(chords[0]) if chords else ""
            comb["_chord_root"] = int(roots[0]) if roots else 0
            # Precompute cache key once.
            try:
                _ = self._choice_key(comb)
            except Exception:
                pass
            beam.append((comb, 0.0, [comb]))

        beam.sort(key=lambda x: x[1])
        beam = beam[:eff_beam_width]

        bars = int(max(1, bars))
        for bar in range(1, bars):
            if budget_s > 1e-9 and (time.perf_counter() - t0) > budget_s:
                # Time budget exceeded: fall back to a greedy continuation from the best partial path.
                break
            new_beam = []
            for prev_choice, prev_cost, path in beam:
                # Precompute once per prev_choice (hot path).
                try:
                    prev_k = self._choice_key(prev_choice)
                except Exception:
                    prev_k = None
                curr_poss = possibilities_for_bar(bar, prev_choice)
                for curr_comb in self.enumerate_combinations_iter(curr_poss):
                    curr_comb["_chord_symbol"] = str(chords[bar])
                    curr_comb["_chord_root"] = int(roots[bar])
                    # Precompute once per curr choice (hot path).
                    try:
                        curr_k = self._choice_key(curr_comb)
                    except Exception:
                        curr_k = None
                    role = phrase_role_for_bar(bar)
                    is_final = bar == (bars - 1)
                    # Memoize voice-leading cost: repeated comparisons are common in beam search.
                    try:
                        vk = (prev_k, curr_k)
                        vcached = self._vl_cost_cache.get(vk)
                    except Exception:
                        vk, vcached = None, None
                    if vcached is None:
                        vc = float(self.voice_leading_cost(prev_choice, curr_comb))
                        if vk is not None:
                            if len(self._vl_cost_cache) > 20000:
                                self._vl_cost_cache.clear()
                            self._vl_cost_cache[vk] = float(vc)
                    else:
                        vc = float(vcached)

                    cost = float(prev_cost) + float(vc)
                    cost += chord_voicing_quality_cost(prev_choice, curr_comb)
                    cost += cadence_resolution_cost(
                        prev_choice,
                        curr_comb,
                        chord=chords[bar],
                        root=roots[bar],
                        role=role,
                        is_final_bar=is_final,
                    )
                    # Lookahead: prefer voicings that set up the next bar with smaller motion.
                    if lookahead_strength > 1e-9 and bar < (bars - 1):
                        try:
                            next_poss = possibilities_for_bar(bar + 1, curr_comb)
                            # Evaluate a small subset of next choices (best few by immediate cost).
                            # compute minimal lookahead cost among next options (up to 8)
                            la_min = None
                            k = 0
                            for nc in self.enumerate_combinations_iter(next_poss):
                                # Precompute once per next candidate (avoids repeated _choice_key work).
                                try:
                                    _ = self._choice_key(nc)
                                except Exception:
                                    pass
                                la = lookahead_cost(curr_comb, nc)
                                if la_min is None or la < la_min:
                                    la_min = la
                                k += 1
                                if k >= 8:
                                    break
                            if la_min is not None:
                                cost += float(la_min)
                        except Exception:
                            pass
                    new_beam.append((curr_comb, cost, path + [curr_comb]))
            new_beam.sort(key=lambda x: x[1])
            beam = new_beam[:eff_beam_width]

        # If we exited early due to budget, extend the best partial path greedily.
        best_choice, best_cost, path = beam[0]
        if len(path) < bars:
            prev_choice = best_choice
            prev_cost = float(best_cost)
            for bar in range(len(path), bars):
                curr_poss = possibilities_for_bar(bar, prev_choice)
                best_next = None
                best_next_cost = None
                for curr_comb in self.enumerate_combinations_iter(curr_poss):
                    curr_comb["_chord_symbol"] = str(chords[bar])
                    curr_comb["_chord_root"] = int(roots[bar])
                    try:
                        _ = self._choice_key(curr_comb)
                    except Exception:
                        pass
                    role = phrase_role_for_bar(bar)
                    is_final = bar == (bars - 1)
                    c = float(prev_cost) + float(self.voice_leading_cost(prev_choice, curr_comb))
                    c += chord_voicing_quality_cost(prev_choice, curr_comb)
                    c += cadence_resolution_cost(
                        prev_choice,
                        curr_comb,
                        chord=chords[bar],
                        root=roots[bar],
                        role=role,
                        is_final_bar=is_final,
                    )
                    if best_next is None or best_next_cost is None or float(c) < float(best_next_cost):
                        best_next = curr_comb
                        best_next_cost = float(c)
                if best_next is None:
                    break
                path.append(best_next)
                prev_choice = best_next
                prev_cost = float(best_next_cost or prev_cost)

        bass_notes = [c["bass"][0] for c in path]
        chord_voicings = [c["chord"] for c in path]
        melody_notes = [c["melody"][0] for c in path]
        harmony_notes = [c["harmony"][0] for c in path]
        # Store independent copies -- the objects we return below may be mutated in
        # place by the caller, which must not corrupt what's cached for later calls.
        self._optimise_global_cache[cache_key] = (
            list(bass_notes),
            [list(v) for v in chord_voicings],
            list(melody_notes),
            list(harmony_notes),
        )
        return bass_notes, chord_voicings, melody_notes, harmony_notes