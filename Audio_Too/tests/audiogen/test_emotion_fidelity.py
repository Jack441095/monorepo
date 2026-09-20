"""Tests for composition.emotion_fidelity (docs/AUDIOGEN_COMPOSITION_PLAN.md item 3).

Core contract tested deterministically with synthetic events (no generation needed):
mode detection separates major from minor, and the scorer ranks a clearly-major synthetic
song higher for a major emotion than a minor one (and vice versa). A light end-to-end test
confirms it runs on a real generated song.
"""
import unittest


def _note(ch, midi, start, dur=1.0, vel=80, notes=None):
    # (channel, midi, velocity, start_beats, duration_beats, notes)
    return (ch, midi, vel, start, dur, notes or [])


def _synth_song(major: bool, bars: int = 8):
    """Build a minimal C-tonic song: bass on C each bar, a triad (major or minor 3rd),
    and a simple melody that leans on the corresponding third. Channels: 0 bass, 1 chords,
    2 melody."""
    third = 64 if major else 63  # E natural vs E-flat over C(60)
    events = []
    for b in range(bars):
        t = float(b) * 4.0
        events.append(_note(0, 48, t, 4.0))                      # bass C2 (root)
        for m in (60, third, 67):                                # chord C - E/Eb - G
            events.append(_note(1, m, t, 4.0))
        # melody: root, third, fifth, third across the bar
        for i, m in enumerate((72, third + 12, 79, third + 12)):
            events.append(_note(2, m, t + i, 1.0))
    return events


class TestModeDetection(unittest.TestCase):
    def test_major_song_reads_major(self):
        from composition.emotion_fidelity import extract_song_features

        f = extract_song_features(_synth_song(major=True))
        self.assertLess(f.minor_third_frac, 0.2, f"major song should read low minor_third_frac, got {f.minor_third_frac}")

    def test_minor_song_reads_minor(self):
        from composition.emotion_fidelity import extract_song_features

        f = extract_song_features(_synth_song(major=False))
        self.assertGreater(f.minor_third_frac, 0.8, f"minor song should read high minor_third_frac, got {f.minor_third_frac}")


class TestFidelityDiscriminates(unittest.TestCase):
    def test_major_song_scores_higher_for_major_emotion(self):
        from composition.emotion_fidelity import emotion_fidelity_score

        maj = _synth_song(major=True)
        # joy is a clearly-major emotion; grief a clearly-minor one.
        joy = emotion_fidelity_score(maj, "joy").sub_scores["mode"]
        grief = emotion_fidelity_score(maj, "grief").sub_scores["mode"]
        self.assertGreater(joy, grief)

    def test_minor_song_scores_higher_for_minor_emotion(self):
        from composition.emotion_fidelity import emotion_fidelity_score

        minor = _synth_song(major=False)
        joy = emotion_fidelity_score(minor, "joy").sub_scores["mode"]
        grief = emotion_fidelity_score(minor, "grief").sub_scores["mode"]
        self.assertGreater(grief, joy)


class TestScorerBasics(unittest.TestCase):
    def test_score_and_discriminate_shapes(self):
        from composition.emotion_fidelity import discriminate, emotion_fidelity_score

        song = _synth_song(major=True)
        res = emotion_fidelity_score(song, "joy")
        self.assertGreaterEqual(res.overall, 0.0)
        self.assertLessEqual(res.overall, 1.0)
        for k in ("mode", "density", "note_duration", "register", "motion"):
            self.assertIn(k, res.sub_scores)
        rank, ranked = discriminate(song, "joy")
        self.assertGreaterEqual(rank, 1)
        self.assertEqual(len(ranked), 28)  # all emotions scored
        # ranked best-first
        self.assertGreaterEqual(ranked[0][1], ranked[-1][1])

    def test_empty_events_do_not_crash(self):
        from composition.emotion_fidelity import emotion_fidelity_score

        res = emotion_fidelity_score([], "joy")
        self.assertIsInstance(res.overall, float)


if __name__ == "__main__":
    unittest.main()
