import unittest


class PopProgressionCleanupTests(unittest.TestCase):
    def test_core_pop_base_pools_avoid_harsh_modal_or_lydian_outliers(self):
        from data.music_data import EMOTION_BY_NAME

        checks = {
            "admiration": {"#11", "bVII"},
            "gratitude": {"#11", "bVII"},
            "love": {"bIII", "bVII"},
            "optimism": {"#11", "bVII"},
        }
        for name, banned in checks.items():
            emo = EMOTION_BY_NAME[name]
            text = " | ".join(" ".join(prog) for prog in emo.chord_progressions)
            for token in banned:
                self.assertNotIn(token, text, msg=f"{name}:{token}")

    def test_joy_and_optimism_chorus_sets_land_without_modal_detour(self):
        from data.music_data import EMOTION_BY_NAME

        for name in ("joy", "optimism"):
            emo = EMOTION_BY_NAME[name]
            chorus = list((getattr(emo, "arrangement_chord_sets", None) or {}).get("b") or [])
            self.assertTrue(chorus, msg=name)
            first_two = chorus[:2]
            text = " | ".join(" ".join(prog) for prog in first_two)
            self.assertNotIn("#11", text, msg=name)
            self.assertNotIn("bVII", text, msg=name)


if __name__ == "__main__":
    unittest.main()
