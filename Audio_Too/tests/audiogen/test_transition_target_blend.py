import unittest


class TransitionTargetBlendTests(unittest.TestCase):
    def test_transition_blend_bars_interpolates_tension_targets(self):
        # Arrange: pick two emotions with distinct tension arcs.
        from audiogen_core.config import CONFIG
        from composition.engine import CompositionGenerator
        from composition import section_planner as sp
        from data.music_data import EMOTION_BY_NAME

        prev = EMOTION_BY_NAME["fear"]
        new = EMOTION_BY_NAME["neutral"]

        gen = CompositionGenerator(enable_perf_monitoring=False)
        bars = 8
        section_index = 0
        role = gen.arrangement_policy.section_role(section_index)

        prev_curve = gen.arrangement_policy.arrangement_curve(section_index, prev)
        new_curve = gen.arrangement_policy.arrangement_curve(section_index, new)
        prev_targets = sp._make_timeline_targets(str(role), int(bars), dict(prev_curve), emotion=prev)
        new_targets = sp._make_timeline_targets(str(role), int(bars), dict(new_curve), emotion=new)

        old_blend = getattr(CONFIG.composition, "transition_blend_bars", 0)
        try:
            CONFIG.composition.transition_blend_bars = 4

            # Act: generate with a handoff context that declares the previous emotion.
            gen.generate_section(
                emotion=new,
                root_note=60,
                bars=bars,
                temperature=0.7,
                target_notes_per_bar=6.0,
                section_index=section_index,
                transition_handoff_context={"previous_emotion_name": "fear"},
            )

            trace = list(getattr(gen, "_last_section_debug_trace_by_bar", []) or [])
            self.assertGreaterEqual(len(trace), 4)
            t0 = trace[0].get("tension", None)
            t3 = trace[3].get("tension", None)

            # Assert: with smoothstep blending, bar 0 is exactly previous (w=0),
            # and bar (blend_bars-1) is exactly new (w=1).
            self.assertIsNotNone(t0)
            self.assertIsNotNone(t3)
            self.assertAlmostEqual(float(t0), float(prev_targets["tension"][0]), places=6)
            self.assertAlmostEqual(float(t3), float(new_targets["tension"][3]), places=6)
        finally:
            CONFIG.composition.transition_blend_bars = old_blend

