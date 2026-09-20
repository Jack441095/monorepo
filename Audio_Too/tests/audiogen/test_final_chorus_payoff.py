import unittest


class FinalChorusPayoffTests(unittest.TestCase):
    def test_resolve_payoff_state_detects_final_chorus_and_tail_sections(self):
        from composition.engine import CompositionGenerator
        from composition.section_planner.final_chorus_payoff import (
            resolve_final_chorus_payoff_state,
        )
        from composition.section_planner.planner import SectionPlanner

        gen = CompositionGenerator(enable_perf_monitoring=False)
        gen.arrangement_policy.form_mode = "pop_ext"
        form_n = int(gen.arrangement_policy.form_section_count())

        final_chorus = resolve_final_chorus_payoff_state(
            gen,
            role="b",
            section_index=7,
            form_section_count=form_n,
        )
        self.assertTrue(bool(final_chorus.get("is_final_chorus", False)))
        # Thin wrapper on SectionPlanner stays aligned with the module.
        self.assertEqual(
            final_chorus,
            SectionPlanner._resolve_final_chorus_payoff_state(
                gen, role="b", section_index=7, form_section_count=form_n
            ),
        )

        tag = resolve_final_chorus_payoff_state(
            gen,
            role="tag",
            section_index=9,
            form_section_count=form_n,
        )
        self.assertTrue(bool(tag.get("is_post_tag", False)))

        outro = resolve_final_chorus_payoff_state(
            gen,
            role="outro",
            section_index=10,
            form_section_count=form_n,
        )
        self.assertTrue(bool(outro.get("is_final_outro", False)))

    def test_payoff_targets_raise_landing_intent_on_final_chorus(self):
        from composition.section_planner.final_chorus_payoff import apply_final_chorus_payoff_targets
        from composition.section_planner.planner import SectionPlanner

        targets = {
            "melody_density": [1.0] * 8,
            "motif_strength": [1.0] * 8,
            "tension": [0.85] * 8,
            "cadence_window": [0.0] * 8,
        }
        state = {"enabled": True, "is_final_chorus": True, "is_post_tag": False, "is_final_outro": False}
        out = apply_final_chorus_payoff_targets(
            dict(targets),
            payoff_state=dict(state),
            strength=1.0,
        )
        self.assertEqual(
            out,
            SectionPlanner._apply_final_chorus_payoff_targets(
                dict(targets), payoff_state=dict(state), strength=1.0
            ),
        )

        self.assertGreater(float(out["motif_strength"][-1]), float(targets["motif_strength"][-1]))
        self.assertGreater(float(out["tension"][-1]), float(targets["tension"][-1]))
        self.assertGreaterEqual(float(out["cadence_window"][-1]), 1.0)

    def test_payoff_curve_backs_off_final_outro_lead_density(self):
        from composition.section_planner.final_chorus_payoff import apply_final_chorus_payoff_curve
        from composition.section_planner.planner import SectionPlanner

        curve = {
            "markov_rest_prob_mult": 1.0,
            "melody_total_notes_mult": 1.0,
        }
        state = {"enabled": True, "is_final_chorus": False, "is_post_tag": False, "is_final_outro": True}
        out = apply_final_chorus_payoff_curve(
            dict(curve),
            payoff_state=dict(state),
            strength=1.0,
        )
        self.assertEqual(
            out,
            SectionPlanner._apply_final_chorus_payoff_curve(
                dict(curve), payoff_state=dict(state), strength=1.0
            ),
        )

        self.assertGreater(float(out["markov_rest_prob_mult"]), 1.0)
        self.assertLess(float(out["melody_total_notes_mult"]), 1.0)


if __name__ == "__main__":
    unittest.main()
