import unittest


class _DummyPolicy:
    form_mode = "default"
    _FORM_SEQUENCES = {"default": ("intro", "a", "pre_chorus", "b", "a", "b", "outro")}

    def form_section_count(self) -> int:
        return len(self._FORM_SEQUENCES["default"])


class _DummyOwner:
    def __init__(self) -> None:
        self.arrangement_policy = _DummyPolicy()
        self._chorus_hook_memory = None


class WholeSongArrangementDirectorTests(unittest.TestCase):
    def test_director_lifts_chorus_energy_above_verse(self) -> None:
        from composition.section_planner.planner import SectionPlanner

        owner = _DummyOwner()
        curve = {
            "melody_total_notes_mult": 1.0,
            "melody_density_mult": 1.0,
            "chord_motion_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "arp_density_mult": 1.0,
            "section_dynamic": 1.0,
        }
        targets = {
            "melody_density": [1.0] * 4,
            "chord_rhythm": [1.0] * 4,
            "tension": [1.0] * 4,
            "motif_strength": [1.0] * 4,
            "layer_presence_targets": {"arp": [1.0] * 4, "counter": [1.0] * 4},
        }

        verse_t, verse_c = SectionPlanner._apply_whole_song_director(
            dict(targets), dict(curve), owner=owner, section_role="a", section_index=1, form_section_count=7
        )
        chorus_t, chorus_c = SectionPlanner._apply_whole_song_director(
            dict(targets), dict(curve), owner=owner, section_role="b", section_index=5, form_section_count=7
        )

        self.assertGreater(float(chorus_c["whole_song_energy"]), float(verse_c["whole_song_energy"]))
        self.assertGreater(float(chorus_c["melody_total_notes_mult"]), float(verse_c["melody_total_notes_mult"]))
        self.assertGreater(float(chorus_t["tension"][0]), float(verse_t["tension"][0]))

    def test_chorus_hook_memory_restates_later_chorus_opening(self) -> None:
        from composition.section_plan import SectionPlan
        from composition.section_planner.planner import SectionPlanner
        from data.music_data import EMOTION_BY_NAME

        owner = _DummyOwner()
        emotion = EMOTION_BY_NAME["neutral"]
        first = SectionPlan(emotion=emotion, root_note=60, bars=4)
        first.melody_events = [
            (2, 72, 90, 0.0, 0.5, [72]),
            (2, 74, 88, 0.5, 0.5, [74]),
            (2, 76, 86, 1.0, 1.0, [76]),
        ]
        SectionPlanner._capture_chorus_hook_memory(owner, first, section_role="b", section_index=3)

        later = SectionPlan(emotion=emotion, root_note=62, bars=4)
        later.melody_events = [(2, 65, 70, 0.0, 1.0, [65]), (2, 67, 70, 2.0, 1.0, [67])]
        SectionPlanner._apply_chorus_hook_memory(owner, later, section_role="b", section_index=5)

        opening = [int(ev[1]) for ev in later.melody_events[:3]]
        self.assertEqual(opening, [79, 81, 83])


if __name__ == "__main__":
    unittest.main()
