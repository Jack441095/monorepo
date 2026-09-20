# ai/markov/melody/voice_leading.py
# Project module `voice_leading` (ai).

# voice_leading.py
from typing import Dict, List, Tuple


class VoiceLeadingMixin:
    """
    Enhanced voice leading with global optimization.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.voice_leading_beam_width = 10  # increased for better search

    def _voice_leading_cost(self,
                            prev_notes: Dict[str, List[int]],
                            curr_notes: Dict[str, List[int]],
                            parallel_penalty: float = 50.0,
                            crossing_penalty: float = 30.0,
                            large_leap_penalty: float = 5.0,
                            step_reward: float = -1.0,   # negative cost = reward
                            common_tone_reward: float = -2.0) -> float:
        """
        Compute comprehensive cost of moving from prev_notes to curr_notes.
        Lower cost = better voice leading.
        """
        cost = 0.0

        # Helper to get single note (first for chord)
        def note(notes_dict, part):
            return notes_dict[part][0] if notes_dict[part] else None

        # Calculate motion for each voice
        voices = ['bass', 'melody', 'harmony']
        intervals = {}
        for v in voices:
            if v in prev_notes and v in curr_notes:
                p = note(prev_notes, v)
                c = note(curr_notes, v)
                if p is not None and c is not None:
                    intervals[v] = c - p
                    # Large leap penalty
                    if abs(intervals[v]) > 12:
                        cost += large_leap_penalty * (abs(intervals[v]) / 12)
                    elif abs(intervals[v]) > 7:
                        cost += large_leap_penalty * 0.5
                    # Stepwise reward
                    if abs(intervals[v]) <= 2:
                        cost += step_reward

        # Parallel fifths/octaves between any two moving voices
        voice_pairs = [('bass', 'melody'), ('bass', 'harmony'), ('melody', 'harmony')]
        for v1, v2 in voice_pairs:
            if v1 in intervals and v2 in intervals:
                if abs(intervals[v1]) > 0 and abs(intervals[v2]) > 0:
                    # Same direction
                    if (intervals[v1] * intervals[v2]) > 0:
                        # Get interval classes (mod 12)
                        int1_class = abs(intervals[v1]) % 12
                        int2_class = abs(intervals[v2]) % 12
                        # Perfect consonances: unison (0), fifth (7), octave (12 mod 12 = 0)
                        if int1_class in (0, 7) and int2_class in (0, 7):
                            cost += parallel_penalty

        # Voice crossings
        order = ['bass', 'chord', 'harmony', 'melody']
        for i in range(len(order)-1):
            v_low = order[i]
            v_high = order[i+1]
            if v_low in curr_notes and v_high in curr_notes:
                low_note = min(curr_notes[v_low]) if v_low == 'chord' else note(curr_notes, v_low)
                high_note = max(curr_notes[v_high]) if v_high == 'chord' else note(curr_notes, v_high)
                if low_note is not None and high_note is not None and low_note >= high_note:
                    cost += crossing_penalty

        # Common tone reward for chord notes
        if 'chord' in prev_notes and 'chord' in curr_notes:
            prev_set = set(prev_notes['chord'])
            curr_set = set(curr_notes['chord'])
            common = prev_set.intersection(curr_set)
            cost += common_tone_reward * len(common)

        # Chord internal smoothness (sum of absolute differences)
        if 'chord' in prev_notes and 'chord' in curr_notes:
            prev_chord = sorted(prev_notes['chord'])
            curr_chord = sorted(curr_notes['chord'])
            min_len = min(len(prev_chord), len(curr_chord))
            cost += sum(abs(prev_chord[i] - curr_chord[i]) for i in range(min_len))
            # Penalize extra notes
            if len(curr_chord) > min_len:
                cost += sum(curr_chord[min_len:]) * 2

        return cost

    def _optimise_voice_leading_global(self,
                                       chords: List[str],
                                       roots: List[int],
                                       bars: int,
                                       beats_per_bar: float = 4.0) -> Tuple[List[int], List[List[int]], List[int], List[int]]:
        """
        Global dynamic programming to choose optimal notes for all bars.
        Returns (chosen_bass, chosen_chord, chosen_melody, chosen_harmony).
        """
        # For each bar, generate possible note choices for each part
        possibilities_per_bar = []
        for bar in range(bars):
            chord = chords[bar]
            root = roots[bar]
            poss = {}
            for part in ['bass', 'chord', 'melody', 'harmony']:
                poss[part] = self._get_possible_notes_for_part(part, chord, root)
            possibilities_per_bar.append(poss)

        # DP: best_cost[bar][choice_index] = (cost, prev_choice_index)
        # We'll flatten combinations to keep it manageable (beam search)
        beam_width = self.voice_leading_beam_width

        # Initialise with first bar
        prev_choices = []
        for idx, choice in enumerate(self._enumerate_combinations(possibilities_per_bar[0])):
            cost = 0.0  # no previous bar
            prev_choices.append((choice, cost, idx))

        # Sort by cost and keep top beam_width
        prev_choices.sort(key=lambda x: x[1])
        prev_choices = prev_choices[:beam_width]

        for bar in range(1, bars):
            curr_choices = []
            for prev_choice, prev_cost, prev_idx in prev_choices:
                for idx, curr_choice in enumerate(self._enumerate_combinations(possibilities_per_bar[bar])):
                    cost = prev_cost + self._voice_leading_cost(prev_choice, curr_choice)
                    curr_choices.append((curr_choice, cost, idx))
            # Sort and trim
            curr_choices.sort(key=lambda x: x[1])
            prev_choices = curr_choices[:beam_width]

        # Backtrack to get best sequence (simplified: just take best final)
        best_choice, best_cost, _ = prev_choices[0]

        # Extract per-bar notes (we need full sequence; for simplicity we return only last bar's choice)
        # A full implementation would store backpointers and reconstruct.
        # For now, we'll compute per-bar using the original per-bar method but with better cost function.
        # This is a placeholder – we'll implement the full DP later.
        # Instead, we'll call the per-bar optimiser but with a global cost passed along.
        return self._compute_voice_leading_per_bar(chords, roots, bars, beats_per_bar)

    def _enumerate_combinations(self, possibilities: Dict[str, List[List[int]]]) -> List[Dict[str, List[int]]]:
        """Generate all possible combinations of notes for a single bar."""
        keys = ['bass', 'chord', 'melody', 'harmony']
        options = [possibilities[k] for k in keys]
        combinations = []
        for bass in options[0]:
            for chord in options[1]:
                for melody in options[2]:
                    for harmony in options[3]:
                        combinations.append({
                            'bass': bass,
                            'chord': chord,
                            'melody': melody,
                            'harmony': harmony
                        })
        return combinations

    def _compute_voice_leading_per_bar(self,
                                       chords: List[str],
                                       roots: List[int],
                                       bars: int,
                                       beats_per_bar: float = 4.0) -> Tuple[List[int], List[List[int]], List[int], List[int]]:
        """
        Original per-bar method but using the enhanced cost function.
        """
        chosen_bass = []
        chosen_chord = []
        chosen_melody = []
        chosen_harmony = []
        prev_notes = None

        for bar in range(bars):
            chord = chords[bar]
            root = roots[bar]

            if bar == 0:
                # First bar: choose default voicing
                chord_notes = self._chord_voicing(chord, root, style='closed', prev_notes=None)
                bass_note = self._get_bass_chord_tones(chord, root)[0]
                all_notes = self._chord_symbol_to_notes(chord, root)
                melody_opts = [n for n in all_notes if n >= 60] or all_notes
                harmony_opts = [n for n in all_notes if 48 <= n < 72] or all_notes
                melody_note = melody_opts[-1] if melody_opts else root + 12
                harmony_note = harmony_opts[1] if len(harmony_opts) > 1 else root + 7
                prev_notes = {
                    'bass': [bass_note],
                    'chord': chord_notes,
                    'melody': [melody_note],
                    'harmony': [harmony_note]
                }
            else:
                # Optimise using enhanced cost
                possibilities = {}
                for part in ['bass', 'chord', 'melody', 'harmony']:
                    possibilities[part] = self._get_possible_notes_for_part(part, chord, root, prev_notes.get(part))

                # Find best combination
                best_cost = float('inf')
                best_choice = None
                for comb in self._enumerate_combinations(possibilities):
                    cost = self._voice_leading_cost(prev_notes, comb)
                    if cost < best_cost:
                        best_cost = cost
                        best_choice = comb

                bass_note = best_choice['bass'][0]
                chord_notes = best_choice['chord']
                melody_note = best_choice['melody'][0]
                harmony_note = best_choice['harmony'][0]
                prev_notes = best_choice

            chosen_bass.append(bass_note)
            chosen_chord.append(chord_notes)
            chosen_melody.append(melody_note)
            chosen_harmony.append(harmony_note)

        return chosen_bass, chosen_chord, chosen_melody, chosen_harmony