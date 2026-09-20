import unittest


class MainPresetFamilyDiscoveryTests(unittest.TestCase):
    def test_discovery_includes_all_family_keys(self) -> None:
        import main
        from audiogen_core.config import ConfigurationManager

        fam = main._discover_preset_families(ConfigurationManager())
        self.assertIn("meta_presets", fam)
        self.assertIn("sample_packs", fam)
        self.assertIn("style_profiles", fam)
        self.assertIn("style_architectures", fam)
        self.assertIn("conversation_presets", fam)
        self.assertIn("fx_presets", fam)
        self.assertIn("arrangement_modes", fam)
        self.assertIn("producer_macros", fam)
        self.assertIn("narrative", list(fam.get("producer_macros", [])))


if __name__ == "__main__":
    unittest.main()
