import unittest


class PhraseScoringWrapTests(unittest.TestCase):
    def test_entry_penalty_uses_wrapped_scale_distance(self):
        from ai.markov.melody.generation.phrase_scoring import score_phrase_candidate

        plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": 0,
                "phrase_role": "opening",
                "section_role": "a",
            },
        )()
        kwargs = dict(
            current_degree=6,
            phrase_start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0}],
            plan=plan,
            entry_pen=1.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
            emotion=None,
        )

        wrapped_step = [(0, 1.0)]
        mid_jump = [(3, 1.0)]
        self.assertGreater(
            score_phrase_candidate(wrapped_step, **kwargs),
            score_phrase_candidate(mid_jump, **kwargs),
        )


if __name__ == "__main__":
    unittest.main()
