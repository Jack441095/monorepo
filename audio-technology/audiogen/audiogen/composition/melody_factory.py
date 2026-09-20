# composition/melody_factory.py
# Project module `melody_factory` (composition).

from typing import List, Tuple

from data.music_data import EmotionProfile, merged_chord_progression_pool
from data.music_theory import ROMAN_TO_SCALE_DEGREE
from utils.phrase_extractor import split_into_phrases


_DUR_FAST = [0.25, 0.25, 0.5, 0.25, 0.5, 0.25, 0.25, 1.0]
_DUR_ACTIVE = [0.5, 0.5, 1.0, 0.5, 0.5, 0.25, 1.0]
_DUR_MODERATE = [1.0, 0.5, 1.0, 2.0, 0.5, 1.0, 1.0]
_DUR_SLOW = [2.0, 1.0, 2.0, 1.0, 4.0, 2.0]
_DUR_VERY_SLOW = [4.0, 2.0, 4.0, 4.0, 2.0]
_DUR_NERVOUS = [0.25, 0.5, 0.25, 0.75, 0.5, 0.25, 1.0, 0.25]

_EMOTION_DURS = {
    "joy": _DUR_FAST,
    "excitement": _DUR_FAST,
    "amusement": _DUR_FAST,
    "anger": _DUR_ACTIVE,
    "pride": _DUR_ACTIVE,
    "optimism": _DUR_ACTIVE,
    "approval": _DUR_MODERATE,
    "admiration": _DUR_MODERATE,
    "gratitude": _DUR_MODERATE,
    "love": _DUR_MODERATE,
    "curiosity": _DUR_MODERATE,
    "desire": _DUR_MODERATE,
    "realization": _DUR_MODERATE,
    "surprise": _DUR_NERVOUS,
    "fear": _DUR_NERVOUS,
    "nervousness": _DUR_NERVOUS,
    "confusion": _DUR_NERVOUS,
    "annoyance": _DUR_ACTIVE,
    "disapproval": _DUR_ACTIVE,
    "disgust": _DUR_ACTIVE,
    "caring": _DUR_SLOW,
    "sadness": _DUR_SLOW,
    "disappointment": _DUR_SLOW,
    "relief": _DUR_SLOW,
    "embarrassment": _DUR_SLOW,
    "grief": _DUR_VERY_SLOW,
    "remorse": _DUR_VERY_SLOW,
    "neutral": _DUR_MODERATE,
}

_NOTES_PER_CHORD = {
    "joy": 6,
    "excitement": 8,
    "amusement": 6,
    "anger": 4,
    "pride": 4,
    "optimism": 5,
    "curiosity": 5,
    "surprise": 5,
    "fear": 6,
    "nervousness": 6,
    "confusion": 4,
    "love": 3,
    "caring": 2,
    "admiration": 3,
    "gratitude": 3,
    "approval": 4,
    "desire": 4,
    "sadness": 3,
    "disappointment": 3,
    "relief": 3,
    "grief": 2,
    "remorse": 2,
    "embarrassment": 3,
    "disapproval": 3,
    "disgust": 3,
    "annoyance": 4,
    "realization": 3,
    "neutral": 4,
}


class MelodyFactory:
    """Owns artificial melody/training-data generation helpers."""

    def __init__(self, owner):
        self.owner = owner

    def mel_durs(self, emo_name: str) -> List[float]:
        return _EMOTION_DURS.get(emo_name, _DUR_MODERATE)

    def mel_npb(self, emo_name: str) -> int:
        return _NOTES_PER_CHORD.get(emo_name, 4)

    def chord_degrees(self, chord: str, scale_len: int) -> Tuple[int, int, int, int]:
        root = ROMAN_TO_SCALE_DEGREE.get(chord, 0) % scale_len
        third = (root + 2) % scale_len
        fifth = (root + 4) % scale_len
        seventh = (root + 6) % scale_len
        return root, third, fifth, seventh

    def mel_arpeggio_up(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        mel, chords = [], []
        dur_idx = 0
        for chord in prog:
            root, third, fifth, seventh = self.chord_degrees(chord, scale_len)
            pattern = [root, third, fifth, seventh, third, root]
            for deg in pattern:
                mel.append((deg, durs[dur_idx % len(durs)]))
                chords.append(chord)
                dur_idx += 1
        return mel, chords

    def mel_arpeggio_down(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        mel, chords = [], []
        dur_idx = 0
        for chord in prog:
            root, third, fifth, seventh = self.chord_degrees(chord, scale_len)
            pattern = [seventh, fifth, third, root, third, root]
            for deg in pattern:
                mel.append((deg, durs[dur_idx % len(durs)]))
                chords.append(chord)
                dur_idx += 1
        return mel, chords

    def mel_scale_run_up(self, prog, scale_len, emo_name):
        step_dur = self.mel_durs(emo_name)[0]
        hold_dur = self.mel_durs(emo_name)[-1]
        mel, chords = [], []
        roots = [ROMAN_TO_SCALE_DEGREE.get(c, 0) % scale_len for c in prog]
        for i, chord in enumerate(prog):
            start = roots[i]
            end = roots[(i + 1) % len(prog)]
            if end > start:
                for degree in range(start, end):
                    mel.append((degree % scale_len, step_dur))
                    chords.append(chord)
            elif end < start:
                for degree in range(start, end, -1):
                    mel.append((degree % scale_len, step_dur))
                    chords.append(chord)
            else:
                mel.append((start % scale_len, hold_dur))
                chords.append(chord)
        return mel, chords

    def mel_scale_run_down(self, prog, scale_len, emo_name):
        step_dur = self.mel_durs(emo_name)[0]
        hold_dur = self.mel_durs(emo_name)[-1]
        mel, chords = [], []
        for chord in prog:
            root = ROMAN_TO_SCALE_DEGREE.get(chord, 0) % scale_len
            high = (root + 4) % scale_len
            degree = high
            steps = 0
            while degree != root and steps < scale_len:
                mel.append((degree % scale_len, step_dur))
                chords.append(chord)
                degree = (degree - 1) % scale_len
                steps += 1
            mel.append((root % scale_len, hold_dur))
            chords.append(chord)
        return mel, chords

    def mel_neighbor_ornament(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        short = min(durs)
        medium = sorted(durs)[len(durs) // 2]
        long_ = max(durs)
        mel, chords = [], []
        for chord in prog:
            root, third, _, _ = self.chord_degrees(chord, scale_len)
            pattern = [
                (root, medium),
                ((root + 1) % scale_len, short),
                (root, short),
                ((root - 1) % scale_len, short),
                (third, long_),
            ]
            for deg, dur in pattern:
                mel.append((deg % scale_len, dur))
                chords.append(chord)
        return mel, chords

    def mel_long_short(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        long_ = max(durs)
        short_ = min(durs)
        mel, chords = [], []
        roots = [ROMAN_TO_SCALE_DEGREE.get(c, 0) % scale_len for c in prog]
        for i, chord in enumerate(prog):
            root = roots[i]
            next_root = roots[(i + 1) % len(prog)]
            passing = (root + next_root) // 2 % scale_len
            mel.append((root, long_))
            chords.append(chord)
            mel.append((passing, short_))
            chords.append(chord)
        return mel, chords

    def mel_motivic_sequence(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        dur_idx = 0
        emo_asc = emo_name in (
            "joy",
            "excitement",
            "optimism",
            "pride",
            "amusement",
            "curiosity",
            "approval",
            "admiration",
            "gratitude",
        )
        mel, chords = [], []
        for chord in prog:
            root = ROMAN_TO_SCALE_DEGREE.get(chord, 0) % scale_len
            if emo_asc:
                motif = [root, (root + 1) % scale_len, (root + 2) % scale_len]
            else:
                motif = [root, (root - 1) % scale_len, (root - 2) % scale_len]
            for deg in motif:
                mel.append((deg % scale_len, durs[dur_idx % len(durs)]))
                chords.append(chord)
                dur_idx += 1
            mel.append((root % scale_len, durs[dur_idx % len(durs)]))
            chords.append(chord)
            dur_idx += 1
        return mel, chords

    def mel_rocking_pedal(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        beat = durs[len(durs) // 2]
        mel, chords = [], []
        for chord in prog:
            root, third, fifth, _ = self.chord_degrees(chord, scale_len)
            tonic = 0
            pattern = [tonic, root, tonic, third, tonic, fifth, tonic, root]
            for deg in pattern:
                mel.append((deg % scale_len, beat))
                chords.append(chord)
        return mel, chords

    def mel_call_answer(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        step = durs[0]
        hold = max(durs)
        mel, chords = [], []
        half = len(prog) // 2 or 1
        for chord in prog[:half]:
            root, _, fifth, _ = self.chord_degrees(chord, scale_len)
            for degree in range(root, fifth + 1):
                mel.append((degree % scale_len, step))
                chords.append(chord)
        for chord in prog[half:]:
            _, third, fifth, _ = self.chord_degrees(chord, scale_len)
            for degree in range(fifth, third - 1, -1):
                mel.append((degree % scale_len, step))
                chords.append(chord)
            mel.append((0, hold))
            chords.append(chord)
        return mel, chords

    def mel_with_rests(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        note_dur = durs[len(durs) // 2]
        rest_dur = note_dur
        mel, chords = [], []
        for i, chord in enumerate(prog):
            root, third, fifth, _ = self.chord_degrees(chord, scale_len)
            for deg in [root, third]:
                mel.append((deg, note_dur))
                chords.append(chord)
                if i < len(prog) - 1:
                    mel.append((-1, rest_dur))
                    chords.append(chord)
            mel.append((fifth, note_dur * 1.5))
            chords.append(chord)
        return mel, chords

    def mel_rhythmic_ostinato(self, prog, scale_len, emo_name):
        durs = self.mel_durs(emo_name)
        npb = self.mel_npb(emo_name)
        mel, chords = [], []
        for chord in prog:
            root, third, fifth, seventh = self.chord_degrees(chord, scale_len)
            pitches = [root, third, fifth, seventh, third, root, fifth, seventh]
            for idx in range(npb):
                mel.append((pitches[idx % len(pitches)], durs[idx % len(durs)]))
                chords.append(chord)
        return mel, chords

    def create_artificial_melodies(
        self, emotion: EmotionProfile
    ) -> Tuple[List[List[Tuple[int, float]]], List[List[str]], List[List[str]]]:
        with self.owner.perf_monitor.measure("create_artificial_melodies"):
            melodies: List[List[Tuple[int, float]]] = []
            chord_sequences: List[List[str]] = []
            phrase_contour_sequences = []

            scale_len = len(emotion.scale_intervals)
            emo_name = emotion.name.lower()

            generators = [
                self.mel_arpeggio_up,
                self.mel_arpeggio_down,
                self.mel_scale_run_up,
                self.mel_scale_run_down,
                self.mel_neighbor_ornament,
                self.mel_long_short,
                self.mel_motivic_sequence,
                self.mel_rocking_pedal,
                self.mel_call_answer,
                self.mel_with_rests,
                self.mel_rhythmic_ostinato,
            ]

            for prog in merged_chord_progression_pool(emotion):
                for gen in generators:
                    mel, chords = gen(prog, scale_len, emo_name)
                    if len(mel) >= 2:
                        melodies.append(mel)
                        chord_sequences.append(chords)

            extra_mels: List[List[Tuple[int, float]]] = []
            extra_chords: List[List[str]] = []

            n_gen = len(generators)
            n_prog = len(emotion.chord_progressions)
            base_count = n_gen * n_prog

            for flat_idx, (mel, chords_seq) in enumerate(
                zip(melodies[:base_count], chord_sequences[:base_count])
            ):
                gen_idx = flat_idx % n_gen

                extra_mels.append(
                    [((degree + 2) % scale_len if degree >= 0 else -1, dur) for degree, dur in mel]
                )
                extra_chords.append(chords_seq)

                extra_mels.append(
                    [((degree - 2) % scale_len if degree >= 0 else -1, dur) for degree, dur in mel]
                )
                extra_chords.append(chords_seq)

                if gen_idx in (0, 2, 6, 8):
                    extra_mels.append(list(reversed(mel)))
                    extra_chords.append(list(reversed(chords_seq)))

                if gen_idx in (0, 4, 5) and len(mel) > 1:
                    inverted = [mel[0]]
                    for idx in range(1, len(mel)):
                        prev_d, _ = mel[idx - 1]
                        cur_d, cur_dur = mel[idx]
                        if prev_d >= 0 and cur_d >= 0:
                            inv_d = (prev_d - (cur_d - prev_d)) % scale_len
                        else:
                            inv_d = cur_d
                        inverted.append((inv_d, cur_dur))
                    extra_mels.append(inverted)
                    extra_chords.append(chords_seq)

                if emo_name in ("grief", "remorse", "sadness", "caring") and gen_idx in (0, 4):
                    augmented = [(degree, dur * 2.0) for degree, dur in mel]
                    extra_mels.append(augmented)
                    extra_chords.append(chords_seq)

            melodies.extend(extra_mels)
            chord_sequences.extend(extra_chords)

            for mel in melodies:
                _, contours = split_into_phrases(mel, phrase_bars=4, beats_per_bar=4.0)
                phrase_contour_sequences.append(contours)

            self.owner._last_phrase_contours = phrase_contour_sequences
            return melodies, chord_sequences, phrase_contour_sequences
