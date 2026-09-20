import unittest


class ChorusToplineScorerTests(unittest.TestCase):
    def test_chorus_topline_prefers_repeatable_stepwise_phrase(self):
        from ai.markov.melody.generation.phrase_scoring import score_phrase_candidate

        plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": 0,
                "phrase_role": "opening",
                "section_role": "b",
            },
        )()
        good = [(0, 0.5), (1, 0.5), (0, 0.5), (1, 0.5), (0, 1.0)]
        bad = [(0, 0.25), (4, 0.25), (2, 0.25), (6, 0.25), (3, 0.25), (5, 0.25), (1, 0.25), (4, 0.25)]
        kwargs = dict(
            current_degree=0,
            phrase_start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0, 2: 0.6, 4: 0.6}],
            plan=plan,
            entry_pen=0.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
        )

        self.assertGreater(score_phrase_candidate(good, **kwargs), score_phrase_candidate(bad, **kwargs))

    def test_chorus_topline_bonus_does_not_apply_to_verse_role(self):
        from ai.markov.melody.generation.phrase_scoring import score_phrase_candidate

        chorus_plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": 0,
                "phrase_role": "opening",
                "section_role": "b",
            },
        )()
        verse_plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": 0,
                "phrase_role": "opening",
                "section_role": "a",
            },
        )()
        phrase = [(0, 0.5), (1, 0.5), (0, 0.5), (1, 0.5), (0, 1.0)]
        kwargs = dict(
            current_degree=0,
            phrase_start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0, 2: 0.6, 4: 0.6}],
            entry_pen=0.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
        )

        self.assertGreater(
            score_phrase_candidate(phrase, plan=chorus_plan, **kwargs),
            score_phrase_candidate(phrase, plan=verse_plan, **kwargs),
        )


if __name__ == "__main__":
    unittest.main()
