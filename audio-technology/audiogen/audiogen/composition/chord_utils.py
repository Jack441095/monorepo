# composition/chord_utils.py
# Project module `chord_utils` (composition).

import random
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from data.chord_parser import midi_to_note, parse_chord_symbol
from data.music_data import apply_substitution, get_root
from data.music_theory import CHORD_VOICINGS


class ChordUtils:
    """Owns chord parsing, voicing, substitutions, and harmony helpers."""

    def __init__(self, owner):
        self.owner = owner

    def extract_root_and_quality(self, symbol: str) -> Tuple[str, str]:
        parsed = parse_chord_symbol(symbol)
        return parsed.root, parsed.quality

    def chord_symbol_to_intervals(self, symbol: str) -> List[int]:
        _, quality = self.extract_root_and_quality(symbol)
        if quality not in CHORD_VOICINGS:
            quality = "maj"
        voicings = CHORD_VOICINGS.get(quality, [[0, 4, 7]])
        return voicings[0] if voicings else [0, 4, 7]

    def validate_chord_symbol(self, symbol: str) -> bool:
        if symbol in self.owner._chord_validation_cache:
            return self.owner._chord_validation_cache[symbol]
        try:
            self.chord_symbol_to_intervals(symbol)
            self.owner._chord_validation_cache[symbol] = True
            return True
        except Exception:
            self.owner._chord_validation_cache[symbol] = False
            return False

    def apply_substitutions_to_progression(self, prog: List[str], prob: float) -> List[str]:
        key = (tuple(prog), prob)
        if key in self.owner._progression_expansion_cache:
            return self.owner._progression_expansion_cache[key].copy()

        new_prog = []
        rng = getattr(self.owner, "rng", random)
        for chord in prog:
            if rng.random() < prob:
                sub_type = rng.choice(["color", "tritone", "relative"])
                new_chord = apply_substitution(chord, sub_type)
                if not self.validate_chord_symbol(new_chord):
                    new_chord = chord
                new_prog.append(new_chord)
            else:
                new_prog.append(chord)

        self.owner._progression_expansion_cache[key] = new_prog.copy()
        return new_prog

    @lru_cache(maxsize=2048)
    def chord_symbol_to_notes_cached(self, symbol: str, root: int) -> Tuple[int, ...]:
        try:
            intervals = self.chord_symbol_to_intervals(symbol)
        except Exception:
            intervals = [0, 4, 7]

        notes = []
        for octave in range(-1, 2):
            for interval in intervals:
                note = root + interval + (12 * octave)
                if 36 <= note <= 84:
                    notes.append(note)

        return tuple(sorted(set(notes)))

    def chord_symbol_to_notes(self, symbol: str, root: int) -> List[int]:
        return list(self.chord_symbol_to_notes_cached(symbol, root))

    def chord_quality(self, symbol: str) -> str:
        _, quality = self.extract_root_and_quality(symbol)
        return quality

    def apply_voicing_style(self, intervals: List[int], style: str) -> List[int]:
        style = (style or "closed").lower()
        if style == "closed":
            return intervals[:]
        if style == "drop2" and len(intervals) >= 4:
            new_intervals = intervals[:]
            new_intervals[-2] -= 12
            new_intervals.sort()
            return new_intervals
        if style == "open":
            return [i + 12 if i > 4 else i for i in intervals]
        if style in {"tenth", "10th"}:
            # Replace the 3rd with a 10th (3rd + octave), optionally keep an octave root.
            third = next((i for i in intervals if i % 12 in {3, 4}), None)
            fifth = next((i for i in intervals if i % 12 == 7), None)
            root = next((i for i in intervals if i % 12 == 0), 0)
            out = [root]
            if fifth is not None:
                out.append(fifth)
            out.append(root + 12)  # octave root for "guitar-ish" weight
            if third is not None:
                out.append(third + 12)
            # keep chord color tones if present, but cap total notes for clarity
            color = [i for i in intervals if i % 12 in {10, 11, 2, 5, 6, 8, 9} and i not in out]
            out.extend(color[:1])
            return sorted(set(out))[:4]
        if style in {"barre", "guitar_barre", "gtr"}:
            # Compact "barre chord" shell: root + fifth + octave + 10th (3rd up an octave).
            third = next((i for i in intervals if i % 12 in {3, 4}), None)
            root = next((i for i in intervals if i % 12 == 0), 0)
            out = [root, root + 12]
            fifth = next((i for i in intervals if i % 12 == 7), None)
            if fifth is not None:
                out.append(fifth)
            if third is not None:
                out.append(third + 12)
            # If no third (power chord feel), keep it as a 3-note shell.
            return sorted(set(out))[:4]
        if style == "quartal":
            return [0, 5, 10, 15, 19]
        if style == "shell":
            # Guide-tone shell: root + (m3/M3) + (m7/M7) when present.
            # Keep this as *intervals* (relative to root); voicing/trim stages decide register and caps.
            root = next((i for i in intervals if i % 12 == 0), 0)
            third = next((i for i in intervals if i % 12 == 4), None)
            if third is None:
                third = next((i for i in intervals if i % 12 == 3), None)
            seventh = next((i for i in intervals if i % 12 == 10), None)
            if seventh is None:
                seventh = next((i for i in intervals if i % 12 == 11), None)
            out = [root]
            if third is not None:
                out.append(int(third))
            if seventh is not None:
                out.append(int(seventh))
            # If we didn't find a proper 3rd/7th (e.g. sus/power), fall back to the first 3 tones.
            return sorted(set(out)) if len(out) >= 2 else intervals[:3]
        return intervals[:]

    def inversions(self, intervals: List[int], root: int, register: int = 4) -> List[List[int]]:
        del register
        base_notes = [root + i for i in intervals]
        while min(base_notes) < 36:
            base_notes = [n + 12 for n in base_notes]
        while max(base_notes) > 84:
            base_notes = [n - 12 for n in base_notes]
        inversions = []
        for i in range(len(intervals)):
            inv = base_notes[i:] + [n + 12 for n in base_notes[:i]]
            while min(inv) < 36:
                inv = [n + 12 for n in inv]
            while max(inv) > 84:
                inv = [n - 12 for n in inv]
            inversions.append(inv)
        return inversions

    @staticmethod
    def best_inversion(inversions: List[List[int]], prev_notes: List[int]) -> List[int]:
        best = None
        best_dist = float("inf")
        for inv in inversions:
            sorted_inv = sorted(inv)
            sorted_prev = sorted(prev_notes)
            min_len = min(len(sorted_inv), len(sorted_prev))
            dist = sum(abs(sorted_inv[i] - sorted_prev[i]) for i in range(min_len))
            if dist < best_dist:
                best_dist = dist
                best = inv
        return best

    def chord_voicing(
        self,
        symbol: str,
        root: int,
        style: str = "closed",
        prev_notes: Optional[List[int]] = None,
        current_bass_note: Optional[int] = None,
        register: int = 4,
    ) -> List[int]:
        intervals = self.chord_symbol_to_intervals(symbol)
        if style == "closed" and len(intervals) > 3:
            style = "drop2"
        intervals = self.apply_voicing_style(intervals, style)
        inversions = self.inversions(intervals, root, register=register)

        if current_bass_note is not None:
            suitable = [inv for inv in inversions if (inv[0] % 12) == (current_bass_note % 12)]
            if not suitable:
                suitable = inversions
        else:
            suitable = inversions

        if prev_notes:
            chosen = self.best_inversion(suitable, prev_notes)
        else:
            chosen = suitable[0] if suitable else inversions[0]

        # Pop-voicing safety: reduce harsh dissonance in dense extensions by
        # trimming clusters and keeping a clear 3–4 note shell when needed.
        try:
            chosen = self._pop_sanitize_voicing(symbol, int(root), list(chosen))
        except Exception:
            pass
        return chosen

    @staticmethod
    def _pc(x: int) -> int:
        return int(x) % 12

    def _pop_sanitize_voicing(self, symbol: str, root: int, notes: List[int]) -> List[int]:
        """
        Keep chord voicings "pop-friendly":
        - limit to a small, stable shell (<= 4 notes) when the source voicing is dense
        - avoid obvious close clusters (m2/M2) in the mid register
        - avoid 3rd+11 clashes (e.g. E and F over C) unless it's explicitly #11
        """
        nn = sorted(int(n) for n in (notes or []) if isinstance(n, int))
        if len(nn) <= 2:
            return nn

        try:
            parsed = parse_chord_symbol(symbol)
            quality = str(getattr(parsed, "quality", "") or "").lower()
        except Exception:
            quality = ""

        root_pc = int(root) % 12
        pcs = {self._pc(n) for n in nn}

        # If both 3rd and 11th are present, drop the 11th (unless explicitly #11).
        has_M3 = ((root_pc + 4) % 12) in pcs
        has_m3 = ((root_pc + 3) % 12) in pcs
        has_11 = ((root_pc + 5) % 12) in pcs
        has_sharp11 = ((root_pc + 6) % 12) in pcs
        if (has_M3 or has_m3) and has_11 and (not has_sharp11) and ("#11" not in quality):
            # Drop the pitch(es) that represent the 11th.
            nn = [n for n in nn if self._pc(n) != ((root_pc + 5) % 12)]

        # Prefer a 4-note shell for extended chords.
        # Keep: root, 3rd (or sus4), 7th (if present), 5th; then optionally 9th.
        nn = sorted(int(n) for n in nn)
        if len(nn) > 4:
            pcs = [self._pc(n) for n in nn]
            # Candidate PCs by priority.
            want = []
            want.append(root_pc)
            if ((root_pc + 4) % 12) in pcs:
                want.append((root_pc + 4) % 12)
            elif ((root_pc + 3) % 12) in pcs:
                want.append((root_pc + 3) % 12)
            elif ((root_pc + 5) % 12) in pcs:
                want.append((root_pc + 5) % 12)  # sus4
            # 7ths
            if ((root_pc + 10) % 12) in pcs:
                want.append((root_pc + 10) % 12)
            elif ((root_pc + 11) % 12) in pcs:
                want.append((root_pc + 11) % 12)
            # 5th
            if ((root_pc + 7) % 12) in pcs:
                want.append((root_pc + 7) % 12)
            # 9th (gentle color)
            if ((root_pc + 2) % 12) in pcs:
                want.append((root_pc + 2) % 12)
            want = [int(x) for x in want]

            keep: List[int] = []
            used_pcs = set()
            for pc in want:
                if len(keep) >= 4:
                    break
                if pc in used_pcs:
                    continue
                # Pick the note closest to the middle of current voicing.
                target = int(round(sum(nn) / float(len(nn))))
                cand = [n for n in nn if self._pc(n) == pc]
                if not cand:
                    continue
                best = min(cand, key=lambda n: abs(int(n) - int(target)))
                keep.append(int(best))
                used_pcs.add(int(pc))
            if len(keep) >= 3:
                nn = sorted(set(int(n) for n in keep))

        # Remove tight clusters (1–2 semitone gaps) by dropping the "least structural" tone.
        # Keep at least 3 notes when possible.
        def _is_structural(pc: int) -> bool:
            return pc in {
                root_pc,
                (root_pc + 3) % 12,
                (root_pc + 4) % 12,
                (root_pc + 7) % 12,
                (root_pc + 10) % 12,
                (root_pc + 11) % 12,
            }

        changed = True
        while changed and len(nn) > 3:
            changed = False
            nn = sorted(nn)
            gaps = [(i, int(nn[i + 1]) - int(nn[i])) for i in range(len(nn) - 1)]
            bad = [i for i, g in gaps if g in (1, 2)]
            if not bad:
                break
            i = bad[0]
            a = int(nn[i])
            b = int(nn[i + 1])
            # Prefer dropping non-structural, higher note in the cluster.
            drop = None
            if not _is_structural(self._pc(b)):
                drop = b
            elif not _is_structural(self._pc(a)):
                drop = a
            else:
                drop = b
            nn = [n for n in nn if int(n) != int(drop)]
            changed = True

        return sorted(set(int(n) for n in nn))

    def chord_voicing_with_voice_leading(
        self,
        symbol: str,
        root: int,
        prev_notes: Dict[str, List[int]],
        style: str = "closed",
    ) -> List[int]:
        intervals = self.chord_symbol_to_intervals(symbol)
        if style == "closed" and len(intervals) > 3:
            style = "drop2"
        intervals = self.apply_voicing_style(intervals, style)
        inversions = self.inversions(intervals, root, register=3)

        best_cost = float("inf")
        best_voicing = None
        for inv in inversions:
            candidate = {"chord": inv}
            if "bass" in prev_notes:
                candidate["bass"] = [prev_notes["bass"][0]]
            if "melody" in prev_notes:
                candidate["melody"] = [prev_notes["melody"][0]]
            if "harmony" in prev_notes:
                candidate["harmony"] = [prev_notes["harmony"][0]]

            cost = self.owner._voice_leading_cost(prev_notes, candidate)
            if cost < best_cost:
                best_cost = cost
                best_voicing = inv

        return best_voicing if best_voicing is not None else inversions[0]

    @staticmethod
    def blend_probabilities(markov_probs: Dict, trans_probs: Dict, weight: float) -> Dict:
        del trans_probs, weight
        return markov_probs

    @staticmethod
    def find_best_note_numpy(upper_octave_notes: List[int], target_pc: int) -> int:
        if not upper_octave_notes:
            return 60
        notes_array = np.array(upper_octave_notes)
        pc_array = notes_array % 12
        dist1 = np.abs(pc_array - target_pc)
        dist2 = 12 - dist1
        distances = np.minimum(dist1, dist2)
        best_idx = np.argmin(distances)
        return upper_octave_notes[best_idx]

    @staticmethod
    def get_emotion_chord_vocabulary(emotion) -> set:
        vocab = set()
        for prog in emotion.chord_progressions:
            vocab.update(prog)
        return vocab

    def simplify_harmony_function(self, chord: str) -> str:
        if hasattr(self.owner, "_simplify_chord_for_markov"):
            return self.owner._simplify_chord_for_markov(chord)

        quality = self.chord_quality(chord)
        if quality.startswith("min"):
            return "min"
        if quality.startswith("dim"):
            return "dim"
        if quality.startswith("aug"):
            return "aug"
        if quality.startswith("sus"):
            return "sus"
        if quality.startswith("7") or quality.startswith("9") or quality.startswith("11") or quality.startswith("13"):
            return "dom"
        return "maj"

    @staticmethod
    def phrase_role(bar_idx: int, total_bars: int, phrase_length: int = 4) -> str:
        total_phrases = max(1, (total_bars + phrase_length - 1) // phrase_length)
        phrase_idx = bar_idx // phrase_length
        if total_phrases <= 1 or phrase_idx == 0:
            return "opening"
        if phrase_idx == total_phrases - 1:
            return "cadence"
        if phrase_idx % 2 == 1:
            return "answer"
        return "continuation"

    @staticmethod
    def is_rich_extension(quality: str) -> bool:
        return any(token in quality for token in ("9", "11", "13", "#11", "b13", "#9", "b9", "maj13"))

    @staticmethod
    def is_simple_extension(quality: str) -> bool:
        return quality in {"maj7", "min7", "7", "6", "6/9", "69", "sus4", "sus2"}

    @staticmethod
    def section_color_profile(emotion_name: str) -> str:
        name = emotion_name.lower()
        if name in {"joy", "excitement", "surprise", "anger", "optimism", "amusement"}:
            return "build"
        if name in {"grief", "sadness", "remorse", "fear", "disappointment"}:
            return "bloom_release"
        if name in {"neutral", "caring", "love", "admiration", "relief"}:
            return "gentle_bloom"
        return "balanced"

    def section_color_bias(self, emotion_name: str, bar_idx: int, total_bars: int) -> Tuple[float, float]:
        if total_bars <= 1:
            return 1.0, 1.0

        progress = bar_idx / max(total_bars - 1, 1)
        profile = self.section_color_profile(emotion_name)
        simple_bias = 1.0
        rich_bias = 1.0

        if profile == "build":
            rich_bias *= 0.82 + (0.55 * progress)
            simple_bias *= 1.18 - (0.22 * progress)
        elif profile == "bloom_release":
            midpoint_distance = abs(progress - 0.62)
            bloom = max(0.0, 1.0 - (midpoint_distance / 0.62))
            rich_bias *= 0.9 + (0.36 * bloom)
            simple_bias *= 1.08 - (0.16 * bloom)
            if progress > 0.85:
                rich_bias *= 0.9
                simple_bias *= 1.08
        elif profile == "gentle_bloom":
            rich_bias *= 0.92 + (0.28 * progress)
            simple_bias *= 1.08 - (0.1 * progress)
        else:
            rich_bias *= 0.95 + (0.22 * progress)
            simple_bias *= 1.05 - (0.08 * progress)

        return simple_bias, rich_bias

    def chord_pitch_classes(self, chord: str) -> List[int]:
        parsed = parse_chord_symbol(chord)
        intervals = list(parsed.intervals())
        chord_lower = chord.lower()
        inferred_intervals = []
        if "6/9" in chord_lower or "69" in chord_lower:
            inferred_intervals.extend([9, 14])
        else:
            if "maj13" in chord_lower or "13" in chord_lower:
                inferred_intervals.append(21)
            if "maj11" in chord_lower or "#11" in chord_lower or "11" in chord_lower:
                inferred_intervals.append(17)
            if "maj9" in chord_lower or "add9" in chord_lower or "9" in chord_lower:
                inferred_intervals.append(14)
            if (
                "maj7" in chord_lower
                and "maj7#11" not in chord_lower
                and "maj13" not in chord_lower
                and 11 not in intervals
            ):
                inferred_intervals.append(11)
            elif "7" in chord_lower and "dim7" not in chord_lower and "maj7" not in chord_lower and 10 not in intervals:
                inferred_intervals.append(10)
            if "6" in chord_lower and "6/9" not in chord_lower and "69" not in chord_lower:
                inferred_intervals.append(9)
        intervals.extend(inferred_intervals)
        if parsed.is_roman():
            root_pc = 0
        else:
            root_pc = parsed.root_pitch_class()
        return sorted({(root_pc + interval) % 12 for interval in intervals})

    def extension_resolution_bias(
        self,
        candidate: str,
        next_chord: str,
        prev_chord: str = "",
    ) -> float:
        if not next_chord:
            return 1.0

        candidate_pcs = self.chord_pitch_classes(candidate)
        next_pcs = self.chord_pitch_classes(next_chord)
        if not candidate_pcs or not next_pcs:
            return 1.0

        total_distance = 0
        common_tones = 0
        for pc in candidate_pcs:
            distances = [min((pc - target) % 12, (target - pc) % 12) for target in next_pcs]
            best = min(distances) if distances else 6
            total_distance += best
            if best == 0:
                common_tones += 1

        avg_distance = total_distance / len(candidate_pcs)
        bias = 1.0 + (0.12 * common_tones) - (0.08 * avg_distance)

        candidate_quality = self.chord_quality(candidate)
        next_function = self.simplify_harmony_function(next_chord)
        if next_function in {"maj", "min"} and any(token in candidate_quality for token in ("b9", "#9", "b13", "#5", "b5")):
            bias *= 0.9

        if prev_chord:
            prev_pcs = self.chord_pitch_classes(prev_chord)
            if prev_pcs:
                repeated_colors = len(set(candidate_pcs).intersection(prev_pcs))
                bias += 0.03 * repeated_colors

        return max(0.7, min(1.45, bias))

    def melodic_target_pitch_classes(self, emotion, role: str, base_function: str) -> List[int]:
        if emotion is None or not getattr(emotion, "scale_intervals", None):
            return []

        name = getattr(emotion, "name", "neutral").lower()
        scale_pcs = [interval % 12 for interval in emotion.scale_intervals]

        degree_map = {
            "opening": [0, 2, 4] if base_function == "maj" else [0, 2],
            "answer": [2, 4, 6] if base_function in {"maj", "dom"} else [2, 4],
            "continuation": [2, 4, 6] if base_function != "min" else [2, 3, 4],
            "cadence": [0, 2] if base_function in {"maj", "min"} else [4, 6],
        }
        degrees = degree_map.get(role, [0, 2, 4])

        if name in {"grief", "sadness", "remorse", "disappointment"}:
            if role == "cadence":
                degrees = [2, 4]
            elif base_function == "min":
                degrees = [2, 3, 4]
        elif name in {"joy", "excitement", "optimism", "amusement"}:
            if role in {"continuation", "answer"}:
                degrees = [1, 2, 4]
        elif name in {"fear", "nervousness", "confusion", "surprise"}:
            if base_function == "dom":
                degrees = [3, 4, 6]

        return [scale_pcs[degree % len(scale_pcs)] for degree in degrees if degree < len(scale_pcs)]

    @staticmethod
    def base_function_pitch_classes(base_function: str) -> List[int]:
        if base_function == "maj":
            return [0, 4, 7]
        if base_function == "min":
            return [0, 3, 7]
        if base_function == "dom":
            return [0, 4, 7, 10]
        if base_function == "sus":
            return [0, 5, 7]
        if base_function == "dim":
            return [0, 3, 6]
        if base_function == "aug":
            return [0, 4, 8]
        return [0, 4, 7]

    def melodic_support_bias(self, candidate: str, emotion, role: str, base_function: str) -> float:
        target_pcs = self.melodic_target_pitch_classes(emotion, role, base_function)
        if not target_pcs:
            return 1.0

        candidate_pcs = set(self.chord_pitch_classes(candidate))
        if not candidate_pcs:
            return 1.0

        support_count = len(candidate_pcs.intersection(target_pcs))
        if support_count == 0:
            return 0.9

        core_pcs = set(self.base_function_pitch_classes(base_function))
        color_targets = len((candidate_pcs - core_pcs).intersection(target_pcs))
        quality = self.chord_quality(candidate)
        bias = 1.0 + (0.08 * support_count) + (0.14 * color_targets)
        if self.is_rich_extension(quality) and color_targets > 0:
            bias += 0.08
        if role == "cadence" and base_function in {"maj", "min"} and support_count >= 2:
            bias += 0.05
        return min(1.35, bias)

    def extension_weight(
        self,
        candidate: str,
        base_function: str,
        emotion_name: str,
        role: str,
        emotion=None,
        prev_function: str = "",
        next_function: str = "",
        prev_chord: str = "",
        next_chord: str = "",
        previous_was_extended: bool = False,
        bar_idx: int = 0,
        total_bars: int = 1,
    ) -> float:
        quality = self.chord_quality(candidate)
        candidate_lower = candidate.lower()
        weight = 1.0
        emotion_name = emotion_name.lower()
        simple_bias, rich_bias = self.section_color_bias(emotion_name, bar_idx, total_bars)

        if base_function == "maj":
            if role in {"opening", "cadence"}:
                if quality in {"maj7", "6", "6/9", "69", "add9"}:
                    weight *= 1.45
                if self.is_rich_extension(quality):
                    weight *= 0.82
            else:
                if quality in {"maj9", "maj13", "maj13#11"}:
                    weight *= 1.25
                if quality == "maj7#11":
                    weight *= 1.1 if emotion_name in {"curiosity", "realization", "admiration"} else 0.92

        elif base_function == "min":
            if role in {"opening", "cadence"}:
                if quality in {"min7", "6", "min9"} or "i7" in candidate_lower or "i9" in candidate_lower:
                    weight *= 1.4
                if quality in {"min11", "min13"} or "i11" in candidate_lower or "i13" in candidate_lower:
                    weight *= 0.88
            else:
                if quality in {"min9", "min11"} or "i9" in candidate_lower or "i11" in candidate_lower:
                    weight *= 1.28
                if quality == "min13" or "i13" in candidate_lower:
                    weight *= 1.08
            if quality == "maj7":
                weight *= 0.78

        elif base_function == "dom":
            if next_function in {"maj", "min"}:
                if quality in {"7", "9", "13", "sus4", "13sus4"}:
                    weight *= 1.45
                if quality in {"7b9", "7#9", "7b13", "7#5", "7b5"}:
                    weight *= 1.12 if emotion_name in {"anger", "surprise", "excitement", "fear"} else 0.86
            elif role == "continuation":
                if quality in {"9", "13", "7#11"}:
                    weight *= 1.22
            if role == "cadence" and next_function in {"", "maj", "min"}:
                if quality in {"7b9", "7#9", "7b13", "7#5", "7b5"}:
                    weight *= 0.84

        elif base_function == "sus":
            if quality in {"sus4", "13sus4"}:
                weight *= 1.15

        if prev_function == base_function:
            if self.is_simple_extension(quality):
                weight *= 1.12
            if self.is_rich_extension(quality):
                weight *= 0.9

        if previous_was_extended and self.is_rich_extension(quality):
            weight *= 0.88

        # Mostly-key-locked, piano-pop safety: strongly downweight altered dominants (b9/#9)
        # unless the emotion is explicitly “tense/abrasive”. These are the most common source
        # of jarring playback even when voicings are well-spread.
        try:
            ql = str(quality or "").lower()
        except Exception:
            ql = ""
        if ("b9" in ql) or ("#9" in ql):
            tense_ok = (emotion_name or "").strip().lower() in {
                "anger",
                "disgust",
                "confusion",
                "fear",
                "nervousness",
                "surprise",
                "annoyance",
            }
            if not tense_ok:
                # Cadence/opening: avoid especially.
                if (role or "") in {"opening", "cadence"}:
                    weight *= 0.05
                else:
                    weight *= 0.20

        if role == "answer" and next_function in {"maj", "min"}:
            if quality in {"maj7", "min7", "9", "6/9", "69"}:
                weight *= 1.12

        if self.is_simple_extension(quality):
            weight *= simple_bias
        elif self.is_rich_extension(quality):
            weight *= rich_bias

        if emotion is not None:
            weight *= self.melodic_support_bias(candidate, emotion, role, base_function)

        if next_chord:
            resolution_bias = self.extension_resolution_bias(candidate, next_chord, prev_chord)
            if base_function == "dom" and next_function in {"maj", "min"}:
                weight *= resolution_bias ** 1.15
            else:
                weight *= resolution_bias

        return max(weight, 0.01)

    def apply_extension(
        self,
        chord: str,
        emotion,
        *,
        bar_idx: int = 0,
        total_bars: int = 1,
        previous_chord: str = "",
        next_chord: str = "",
    ) -> str:
        vocab = self.get_emotion_chord_vocabulary(emotion)
        parsed = parse_chord_symbol(chord)
        base_function = self.simplify_harmony_function(chord)
        candidates = []
        for candidate in vocab:
            candidate_parsed = parse_chord_symbol(candidate)
            if candidate == chord or candidate_parsed.root != parsed.root:
                continue
            if self.simplify_harmony_function(candidate) != base_function:
                continue
            candidates.append(candidate)

        if not candidates:
            return chord

        role = self.phrase_role(bar_idx, total_bars)
        prev_function = self.simplify_harmony_function(previous_chord) if previous_chord else ""
        next_function = self.simplify_harmony_function(next_chord) if next_chord else ""
        previous_was_extended = bool(previous_chord and self.chord_quality(previous_chord) != self.simplify_harmony_function(previous_chord))
        weights = [
            self.extension_weight(
                candidate,
                base_function,
                emotion.name,
                role,
                emotion=emotion,
                prev_function=prev_function,
                next_function=next_function,
                prev_chord=previous_chord,
                next_chord=next_chord,
                previous_was_extended=previous_was_extended,
                bar_idx=bar_idx,
                total_bars=total_bars,
            )
            for candidate in candidates
        ]
        rng = getattr(self.owner, "rng", random)
        return rng.choices(candidates, weights=weights)[0]

    def add_extensions(self, chords: List[str], emotion) -> List[str]:
        if not self.owner.use_extensions:
            return chords
        new_chords = []
        total_bars = len(chords)
        rng = getattr(self.owner, "rng", random)
        for idx, chord in enumerate(chords):
            previous_chord = new_chords[-1] if new_chords else ""
            next_chord = chords[idx + 1] if idx + 1 < total_bars else ""
            extension_prob = self.owner.extension_prob
            if previous_chord and self.simplify_harmony_function(previous_chord) == self.simplify_harmony_function(chord):
                extension_prob *= 0.8

            if rng.random() < extension_prob:
                new_chords.append(
                    self.apply_extension(
                        chord,
                        emotion,
                        bar_idx=idx,
                        total_bars=total_bars,
                        previous_chord=previous_chord,
                        next_chord=next_chord,
                    )
                )
            else:
                new_chords.append(chord)
        return new_chords

    def apply_modal_interchange(self, chords: List[str], emotion, key_mode: str = "major") -> List[str]:
        if not self.owner.use_modal_interchange:
            return chords
        vocab = self.get_emotion_chord_vocabulary(emotion)
        interchange_dict = (
            self.owner.MODAL_INTERCHANGE_MAJOR if key_mode == "major" else self.owner.MODAL_INTERCHANGE_MINOR
        )
        new_chords = []
        rng = getattr(self.owner, "rng", random)
        for chord in chords:
            if rng.random() < self.owner.interchange_prob and chord in interchange_dict:
                borrowed = interchange_dict[chord]
                new_chords.append(borrowed if borrowed in vocab else chord)
            else:
                new_chords.append(chord)
        return new_chords

    def add_secondary_dominants(self, chords: List[str], emotion) -> List[str]:
        if not self.owner.use_secondary_dominants:
            return chords
        vocab = self.get_emotion_chord_vocabulary(emotion)
        new_chords = []
        rng = getattr(self.owner, "rng", random)
        for i, chord in enumerate(chords):
            if i > 0 and rng.random() < self.owner.secondary_dominant_prob and chord in self.owner.SECONDARY_DOMINANTS:
                secondary = self.owner.SECONDARY_DOMINANTS[chord]
                if secondary in vocab:
                    new_chords.append(secondary)
            new_chords.append(chord)
        return new_chords

    def apply_advanced_harmony(self, chords: List[str], emotion) -> List[str]:
        chords = self.add_extensions(chords, emotion)
        if not chords:
            return chords
        first = chords[0].lstrip()
        key_mode = "major"
        for ch in first:
            if ch.isalpha():
                key_mode = "major" if ch.isupper() else "minor"
                break
        chords = self.apply_modal_interchange(chords, emotion, key_mode)
        chords = self.add_secondary_dominants(chords, emotion)
        return chords

    @staticmethod
    def midi_to_note_name(midi: int) -> str:
        return midi_to_note(midi)

    @staticmethod
    def chord_roots(chords: List[str], root_note: int) -> List[int]:
        key_root_name = midi_to_note(root_note)
        final_roots = []
        for chord in chords:
            offset = get_root(chord, key_root_name)
            final_roots.append(root_note + offset)
        return final_roots
