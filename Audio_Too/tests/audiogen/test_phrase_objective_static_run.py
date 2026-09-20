import unittest


class PhraseObjectiveStaticRunTests(unittest.TestCase):
    def test_objective_penalizes_long_static_runs_when_enabled(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.generation.phrase_scoring import score_phrase_candidate

        plan = type(
            "Plan",
            (),
            {
                "cadence_degree": 0,
                "hook_anchor_degree": None,
                "phrase_role": "continuation",
                "section_role": "a",
                "contour": "static",
            },
        )()

        class _Emotion:
            name = "neutral"

        base_kwargs = dict(
            current_degree=0,
            phrase_start_beat=0.0,
            beats_per_bar=4.0,
            chord_weights_per_bar=[{0: 1.0}],
            plan=plan,
            entry_pen=0.0,
            leap_pen=0.0,
            leap_thr=4,
            cad_land=0.0,
            cad_app=0.0,
            cad_miss=0.0,
            occ_step_weights={},
            grid=0.25,
            emotion=_Emotion(),
        )

        # Same cadence landing; only interior motion differs.
        static_phrase = [(0, 0.5), (0, 0.5), (0, 0.5), (0, 0.5), (0, 1.0)]
        moving_phrase = [(0, 0.5), (1, 0.5), (0, 0.5), (1, 0.5), (0, 1.0)]

        old_on = getattr(CONFIG.composition, "melody_phrase_objective_enabled", False)
        old_w = getattr(CONFIG.composition, "melody_phrase_objective_static_run_weight", 0.22)
        try:
            CONFIG.composition.melody_phrase_objective_enabled = True
            CONFIG.composition.melody_phrase_objective_static_run_weight = 1.0

            s_static = score_phrase_candidate(static_phrase, **base_kwargs)
            s_moving = score_phrase_candidate(moving_phrase, **base_kwargs)
            self.assertGreater(s_moving, s_static)
        finally:
            CONFIG.composition.melody_phrase_objective_enabled = old_on
            CONFIG.composition.melody_phrase_objective_static_run_weight = old_w


if __name__ == "__main__":
    unittest.main()

