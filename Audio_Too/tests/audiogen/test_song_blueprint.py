import unittest


class SongBlueprintTests(unittest.TestCase):
    def test_build_song_blueprint_assigns_roles_and_narrative_fields(self):
        from composition.song_blueprint import build_song_blueprint
        from composition.song_generator import SongSectionSpec

        sections = [
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=60),
            SongSectionSpec("neutral", bars=4, root_note=62),
            SongSectionSpec("neutral", bars=4, root_note=62),
        ]
        bp = build_song_blueprint(sections, form_mode="default")
        self.assertEqual(len(bp.sections), 4)
        self.assertEqual(bp.sections[0].section_role, "intro")
        self.assertEqual(bp.sections[1].section_role, "a")
        self.assertEqual(bp.sections[2].section_role, "pre_chorus")
        self.assertEqual(bp.sections[3].section_role, "b")
        self.assertIn(bp.sections[3].motif_stage, {"restate", "payoff"})
        self.assertIn(bp.sections[2].cadence_style, {"open"})
        self.assertIn("melody", bp.sections[3].layer_contract)


if __name__ == "__main__":
    unittest.main()
