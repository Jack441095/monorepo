import unittest


class ListenerMemoryScoringTests(unittest.TestCase):
    def test_repeated_recent_phrase_gets_penalized(self) -> None:
        from ai.markov.melody.generation.phrase_scoring import score_phrase_candidate

        plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": 0,
                "phrase_role": "continuation",
                "section_role": "a",
            },
        )()
        repeated = [(0, 0.5), (1, 0.5), (0, 1.0)]
        fresh = [(0, 0.5), (2, 0.5), (1, 1.0)]
        prior = [list(repeated)]
        kwargs = dict(
            current_degree=0,
            phrase_start_beat=4.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0, 2: 0.7, 4: 0.6}],
            plan=plan,
            entry_pen=0.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
            prior_phrases=prior,
        )
        self.assertGreater(score_phrase_candidate(fresh, **kwargs), score_phrase_candidate(repeated, **kwargs))

    def test_chorus_opening_can_recall_anchor_phrase(self) -> None:
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
        anchor = [(0, 0.5), (1, 0.5), (0, 1.0)]
        far = [(3, 0.25), (5, 0.25), (6, 0.5), (2, 1.0)]
        prior = [list(anchor)]
        kwargs = dict(
            current_degree=0,
            phrase_start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0, 2: 0.7, 4: 0.6}],
            plan=plan,
            entry_pen=0.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
            prior_phrases=prior,
        )
        self.assertGreater(score_phrase_candidate(anchor, **kwargs), score_phrase_candidate(far, **kwargs))


if __name__ == "__main__":
    unittest.main()

