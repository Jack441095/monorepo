import unittest


class SongGeneratorBudgetTests(unittest.TestCase):
    def test_best_of_k_respects_time_budget_after_first_candidate(self):
        from composition.song_generator import SongGenerator, SongSectionSpec

        sg = SongGenerator()
        sections = [SongSectionSpec("neutral", bars=4, root_note=60)]
        # time_budget_s=0 should still produce 1 candidate, then stop.
        song = sg.generate_song_best_of_k(
            sections,
            arrangement_form="default",
            seed=0,
            k=5,
            time_budget_s=0.0,
        )
        self.assertIsNotNone(song)
        self.assertIsNotNone(song.metadata)
        self.assertEqual(song.metadata.get("picked_by"), "best_of_k")
        self.assertEqual(song.metadata.get("picked_k"), 5)
        self.assertEqual(song.metadata.get("picked_k_actual"), 1)

    def test_generate_song_exports_motif_development_metadata(self):
        from composition.song_generator import SongGenerator, SongSectionSpec

        class _Composer:
            def __init__(self):
                self.arrangement_policy = type("Policy", (), {"form_mode": "default"})()

            def reset_song_arrangement_state(self):
                pass

            def generate_section(self, **kwargs):
                idx = int(kwargs.get("section_index", 0) or 0)
                self._last_section_motif_development = {
                    "section_index": idx,
                    "role": "b" if idx else "a",
                    "section_variant": "statement",
                    "motif_id": "theme",
                    "slot_count": 1,
                }
                return [(2, 72 + idx, 90, 0.0, 1.0, [72 + idx])]

        sg = SongGenerator(composer=_Composer())
        song = sg.generate_song(
            [
                SongSectionSpec("neutral", bars=1, root_note=60),
                SongSectionSpec("neutral", bars=1, root_note=60),
            ],
            arrangement_form="default",
            seed=0,
        )
        motif_meta = list((song.metadata or {}).get("motif_development", []) or [])
        self.assertEqual(len(motif_meta), 2)
        self.assertEqual(motif_meta[0]["absolute_start_beats"], 0.0)
        self.assertEqual(motif_meta[1]["absolute_start_beats"], 4.0)
        self.assertEqual(motif_meta[1]["role"], "b")
        self.assertIn("quality_report", song.metadata or {})


if __name__ == "__main__":
    unittest.main()
