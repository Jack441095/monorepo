import unittest


class DeterminismTests(unittest.TestCase):
    def test_seeded_offline_song_generation_is_repeatable_with_fresh_generator(self):
        # Fresh SongGenerator (and therefore fresh CompositionGenerator) per run should
        # produce identical events for the same seed/config.
        from composition.song_generator import SongGenerator

        def run_once():
            from audiogen_core.config import CONFIG

            # Startup conversation preset enables wall-clock section picking; disable for seeded tests.
            CONFIG.composition.section_pick_use_wall_clock = False
            CONFIG.composition.joint_generation_use_wall_clock = False
            sg = SongGenerator()
            sections = sg.pop_form("joy", bars_per_section=8, root_note=60)
            song = sg.generate_song(
                sections,
                base_tempo_bpm=90.0,
                arrangement_form="pop",
                seed=9,
            )
            return song.events, (song.metadata or {}).get("metrics")

        ev1, m1 = run_once()
        ev2, m2 = run_once()
        self.assertEqual(ev1, ev2)
        self.assertEqual(m1, m2)

