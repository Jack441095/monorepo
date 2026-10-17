import unittest
from types import SimpleNamespace


class _SeqRng:
    def __init__(self, seq):
        self.seq = list(seq)
        self.idx = 0

    def random(self):
        v = float(self.seq[self.idx % len(self.seq)])
        self.idx += 1
        return v

    def getstate(self):
        return int(self.idx)

    def setstate(self, state):
        self.idx = int(state)


class _FakeNoteGen:
    def __init__(self, rng):
        self.rng = rng

    def generate_phrase(self, **_kwargs):
        deg = int(self.rng.random() * 10.0)
        return [(deg, 1.0)], [], []


class _FakePost:
    @staticmethod
    def break_repetitions(melody, **_kwargs):
        return melody

    @staticmethod
    def remove_dissonant_leaps(melody):
        return melody

    @staticmethod
    def quantize_melody_strict(melody):
        return melody


class PhraseGenerationRngTests(unittest.TestCase):
    def test_best_of_k_uses_distinct_reproducible_candidates(self):
        from audiogen_core.config import CONFIG
        import ai.markov.melody.generation.phrase_generation as pg

        old_k = getattr(CONFIG.composition, "melody_phrase_k_samples", 1)
        old_beam = getattr(CONFIG.composition, "melody_phrase_beam_enabled", True)
        old_pos = getattr(CONFIG.composition, "melody_position_conditioning_enabled", False)
        old_vl = getattr(CONFIG.composition, "melody_voiceleading_rerank_enabled", False)

        prev_score = pg.score_phrase_candidate
        try:
            CONFIG.composition.melody_phrase_k_samples = 3
            CONFIG.composition.melody_phrase_beam_enabled = False
            CONFIG.composition.melody_position_conditioning_enabled = False
            CONFIG.composition.melody_voiceleading_rerank_enabled = False

            pg.score_phrase_candidate = lambda ph, **_kwargs: float(ph[0][0])

            rng = _SeqRng([0.1, 0.2, 0.9])
            gen = SimpleNamespace(
                rng=rng,
                planner=SimpleNamespace(
                    generate_plans=lambda *args, **kwargs: [
                        SimpleNamespace(
                            contour="static",
                            phrase_role="opening",
                            section_role="a",
                            cadence_zone_start=1.0,
                        )
                    ]
                ),
                note_gen=_FakeNoteGen(rng),
                markov=SimpleNamespace(
                    interval=SimpleNamespace(order=1),
                    rhythm=SimpleNamespace(order=1),
                ),
                post=_FakePost(),
                phrase_gap_prob=0.0,
                rest_prob=0.0,
                embellishment_prob=0.0,
                enforce_chord_tones_prob=0.0,
                enforce_climax=False,
                enforce_phrase_structure_prob=0.0,
            )

            out = pg.generate_with_phrases(
                gen,
                phrase_contours=["static"],
                start_degree=0,
                notes_per_phrase=[1],
                temperature=1.0,
                emotion=None,
                chords=None,
                roots=None,
                total_beats=4.0,
                runtime_mode="normal",
            )
            self.assertEqual(out, [(9, 1.0)])
        finally:
            pg.score_phrase_candidate = prev_score
            CONFIG.composition.melody_phrase_k_samples = old_k
            CONFIG.composition.melody_phrase_beam_enabled = old_beam
            CONFIG.composition.melody_position_conditioning_enabled = old_pos
            CONFIG.composition.melody_voiceleading_rerank_enabled = old_vl


if __name__ == "__main__":
    unittest.main()
