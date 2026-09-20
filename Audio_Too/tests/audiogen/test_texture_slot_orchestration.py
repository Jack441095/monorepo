import unittest


class TextureSlotOrchestrationTests(unittest.TestCase):
    def test_texture_exports_layer_presence_schema(self):
        from composition.section_planner import _make_texture_by_bar

        out = _make_texture_by_bar(
            section_role="a",
            bars=8,
            timeline_targets={
                "tension": [0.7] * 8,
                "cadence_window": [0.0] * 7 + [1.0],
                "breath_window": [0.0] * 8,
            },
            handoff_ctx={},
        )
        self.assertEqual(len(out), 8)
        for row in out:
            lp = row.get("layer_presence")
            self.assertIsInstance(lp, dict)
            for k in ("bass", "chords", "melody", "arp", "counter"):
                self.assertIn(k, lp)
                self.assertGreaterEqual(float(lp[k]), 0.0)
                self.assertLessEqual(float(lp[k]), 1.0)

    def test_role_profiles_raise_chorus_and_prechorus_layers(self):
        from composition.section_planner import _make_texture_by_bar

        targets = {
            "tension": [0.7] * 8,
            "cadence_window": [0.0] * 8,
            "breath_window": [0.0] * 8,
        }
        verse = _make_texture_by_bar(section_role="a", bars=8, timeline_targets=targets, handoff_ctx={})
        pre = _make_texture_by_bar(section_role="pre_chorus", bars=8, timeline_targets=targets, handoff_ctx={})
        chorus = _make_texture_by_bar(section_role="b", bars=8, timeline_targets=targets, handoff_ctx={})
        intro = _make_texture_by_bar(section_role="intro", bars=8, timeline_targets=targets, handoff_ctx={})

        verse_arp = sum(float((x.get("layer_presence") or {}).get("arp", 0.0)) for x in verse) / len(verse)
        pre_arp = sum(float((x.get("layer_presence") or {}).get("arp", 0.0)) for x in pre) / len(pre)
        verse_counter = sum(float((x.get("layer_presence") or {}).get("counter", 0.0)) for x in verse) / len(verse)
        chorus_counter = sum(float((x.get("layer_presence") or {}).get("counter", 0.0)) for x in chorus) / len(chorus)
        intro_bass_start = float((intro[0].get("layer_presence") or {}).get("bass", 0.0))
        intro_bass_end = float((intro[-1].get("layer_presence") or {}).get("bass", 0.0))

        self.assertGreater(pre_arp, verse_arp)
        self.assertGreater(chorus_counter, verse_counter)
        self.assertGreater(intro_bass_end, intro_bass_start)

    def test_orchestration_script_stages_prechorus_build(self):
        from composition.section_planner import _make_texture_by_bar

        targets = {
            "tension": [0.78] * 8,
            "cadence_window": [0.0] * 8,
            "breath_window": [0.0] * 8,
        }
        pre = _make_texture_by_bar(
            section_role="pre_chorus",
            bars=8,
            timeline_targets=targets,
            handoff_ctx={},
            next_role="b",
        )

        arp_start = float((pre[0].get("layer_presence") or {}).get("arp", 0.0))
        arp_mid = float((pre[3].get("layer_presence") or {}).get("arp", 0.0))
        arp_end = float((pre[-1].get("layer_presence") or {}).get("arp", 0.0))
        counter_start = float((pre[0].get("layer_presence") or {}).get("counter", 0.0))
        counter_end = float((pre[-1].get("layer_presence") or {}).get("counter", 0.0))

        # Staged build through the section, then an intentional last-bar drop before chorus.
        self.assertGreater(arp_mid, arp_start)
        self.assertGreater(arp_mid, arp_end)
        self.assertGreater(counter_end, counter_start)

    def test_orchestration_script_spotlights_chorus_arp_on_entry(self):
        from composition.section_planner import _make_texture_by_bar

        targets = {
            "tension": [0.82] * 8,
            "cadence_window": [0.0] * 8,
            "breath_window": [0.0] * 8,
        }
        chorus = _make_texture_by_bar(
            section_role="b",
            bars=8,
            timeline_targets=targets,
            handoff_ctx={},
            next_role="a",
        )

        entry = chorus[0].get("layer_presence") or {}
        release = chorus[-1].get("layer_presence") or {}

        self.assertGreater(float(entry.get("arp", 0.0)), float(entry.get("melody", 0.0)))
        self.assertLess(float(release.get("arp", 0.0)), float(entry.get("arp", 0.0)))
        self.assertLess(float(release.get("counter", 0.0)), float((chorus[1].get("layer_presence") or {}).get("counter", 0.0)))


if __name__ == "__main__":
    unittest.main()
