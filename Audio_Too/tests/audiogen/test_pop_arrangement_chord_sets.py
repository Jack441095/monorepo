import unittest


class PopArrangementChordSetTests(unittest.TestCase):
    def test_core_pop_emotions_have_authored_role_pools(self):
        from data.music_data import EMOTION_BY_NAME

        for name in ("neutral", "love", "optimism", "gratitude", "admiration"):
            emo = EMOTION_BY_NAME[name]
            sets = getattr(emo, "arrangement_chord_sets", None) or {}
            self.assertTrue(sets, msg=name)
            self.assertIn("a", sets, msg=name)
            self.assertIn("pre_chorus", sets, msg=name)
            self.assertIn("b", sets, msg=name)

    def test_prechorus_ends_more_open_than_chorus_for_core_pop_emotions(self):
        from data.music_data import EMOTION_BY_NAME

        for name in ("neutral", "love", "optimism", "gratitude", "admiration"):
            emo = EMOTION_BY_NAME[name]
            sets = getattr(emo, "arrangement_chord_sets", None) or {}
            pre = list(sets.get("pre_chorus") or [])
            chorus = list(sets.get("b") or [])
            self.assertTrue(pre, msg=f"{name}:pre")
            self.assertTrue(chorus, msg=f"{name}:b")
            pre_last = str(pre[0][-1])
            chorus_last = str(chorus[0][-1])
            self.assertTrue(
                pre_last.startswith("V") or "7" in pre_last or "sus" in pre_last.lower(),
                msg=f"{name}:pre:{pre_last}",
            )
            self.assertTrue(
                chorus_last.startswith(("I", "i")),
                msg=f"{name}:chorus:{chorus_last}",
            )


if __name__ == "__main__":
    unittest.main()
