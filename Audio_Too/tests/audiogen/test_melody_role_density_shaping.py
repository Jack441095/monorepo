import unittest


class MelodyRoleDensityShapingTests(unittest.TestCase):
    def test_role_density_multiplier_trend(self) -> None:
        from composition.melody_runtime import MelodyRuntime

        intro = MelodyRuntime._section_role_density_multiplier("intro")
        verse = MelodyRuntime._section_role_density_multiplier("a")
        pre = MelodyRuntime._section_role_density_multiplier("pre_chorus")
        chorus = MelodyRuntime._section_role_density_multiplier("b")
        outro = MelodyRuntime._section_role_density_multiplier("outro")

        self.assertLess(float(intro), float(verse))
        self.assertLess(float(verse), float(pre))
        self.assertLess(float(pre), float(chorus))
        self.assertLess(float(outro), float(verse))

    def test_counter_line_ignores_role_density_shaping(self) -> None:
        from composition.melody_runtime import MelodyRuntime

        for role in ("intro", "a", "pre_chorus", "b", "outro"):
            self.assertEqual(
                float(MelodyRuntime._section_role_density_multiplier(role, counter_line=True)),
                1.0,
            )


if __name__ == "__main__":
    unittest.main()
