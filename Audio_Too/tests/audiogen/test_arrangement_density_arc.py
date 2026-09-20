import unittest


class ArrangementDensityArcTests(unittest.TestCase):
    def test_timeline_exports_layer_presence_targets(self) -> None:
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        t = _make_timeline_targets("pre_chorus", 8, dict(curve))
        lp = dict(t.get("layer_presence_targets", {}) or {})
        for k in ("bass", "chords", "melody", "arp", "counter"):
            self.assertIn(k, lp)
            arr = list(lp.get(k, []) or [])
            self.assertEqual(len(arr), 8)
            self.assertTrue(all(0.0 <= float(v) <= 1.0 for v in arr))

    def test_texture_consumes_layer_presence_targets(self) -> None:
        from composition.section_planner import _make_texture_by_bar

        base_targets = {
            "tension": [0.8] * 8,
            "cadence_window": [0.0] * 8,
            "breath_window": [0.0] * 8,
        }
        low_arp = dict(base_targets)
        low_arp["layer_presence_targets"] = {
            "bass": [1.0] * 8,
            "chords": [1.0] * 8,
            "melody": [1.0] * 8,
            "arp": [0.55] * 8,
            "counter": [1.0] * 8,
        }

        plain = _make_texture_by_bar(section_role="b", bars=8, timeline_targets=base_targets, handoff_ctx={})
        shaped = _make_texture_by_bar(section_role="b", bars=8, timeline_targets=low_arp, handoff_ctx={})

        plain_arp = sum(float((x.get("layer_presence") or {}).get("arp", 0.0)) for x in plain) / len(plain)
        shaped_arp = sum(float((x.get("layer_presence") or {}).get("arp", 0.0)) for x in shaped) / len(shaped)
        self.assertLess(shaped_arp, plain_arp)


if __name__ == "__main__":
    unittest.main()

