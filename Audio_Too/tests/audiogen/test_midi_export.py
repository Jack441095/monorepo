"""Regression test for MIDI export (docs/AUDIOGEN_COMPOSITION_PLAN.md).

`SongGenerator.export_to_midi` crashed for every song because channel 6 (percussion) was
routed through `pretty_midi.instrument_name_to_program("Acoustic Bass Drum")` -- a GM
*drum* name, not a melodic *instrument program* name -- which raised ValueError. Percussion
must use `is_drum=True` (MIDI channel 10). This guards that the export succeeds and the
file round-trips.
"""
import os
import tempfile
import unittest


class TestMidiExport(unittest.TestCase):
    def test_export_succeeds_and_round_trips(self):
        try:
            import pretty_midi  # noqa: F401
        except Exception:
            self.skipTest("pretty_midi not installed")

        from composition.song_generator import SongGenerator

        sg = SongGenerator()
        sections = sg.pop_form("joy", bars_per_section=2, root_note=60)
        song = sg.generate_song(sections, base_tempo_bpm=100, arrangement_form="pop", seed=1)

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "song.mid")
            path = SongGenerator.export_to_midi(song, out_path=out)  # must not raise
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

            import pretty_midi

            pm = pretty_midi.PrettyMIDI(path)  # loadable
            n_notes = sum(len(i.notes) for i in pm.instruments)
            self.assertGreater(n_notes, 0)

    def test_channel_6_configured_as_drum(self):
        """Directly exercise the percussion channel so a drum instrument is actually
        emitted (guards the is_drum routing, not just the no-percussion happy path)."""
        try:
            import pretty_midi  # noqa: F401
        except Exception:
            self.skipTest("pretty_midi not installed")

        from composition.song_generator import SongGenerator, SongRender

        # one melodic note + one percussion note on channel 6
        events = [
            (2, 72, 90, 0.0, 1.0, [72]),
            (6, 35, 100, 0.0, 0.5, [35]),  # kick (GM note 35) on the drum channel
        ]
        song = SongRender(sections=[], events=events, tempo_map=[(0.0, 100.0)], metadata={})
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "drum.mid")
            SongGenerator.export_to_midi(song, out_path=out)
            import pretty_midi

            pm = pretty_midi.PrettyMIDI(out)
            drum_notes = sum(len(i.notes) for i in pm.instruments if i.is_drum)
            self.assertGreater(drum_notes, 0, "percussion should export as a drum-channel instrument")


if __name__ == "__main__":
    unittest.main()
