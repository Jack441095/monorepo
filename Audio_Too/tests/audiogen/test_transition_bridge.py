import random
import unittest


class TransitionBridgeTests(unittest.TestCase):
    def test_transition_bridge_hold_bars_biases_early_chords_common_tones(self):
        from audiogen_core.config import CONFIG
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME
        import numpy as np

        # The bridge's common-tone bias is probabilistic, not a hard guarantee,
        # so this test must pin the RNG it draws from -- left unseeded it flaked
        # order-dependently (~1/15 runs) whenever prior tests in the same process
        # had consumed the global random/numpy state differently. Seed 1 is
        # verified stable (see test_section_generation_snapshots.py for the same
        # reseed-per-test convention used throughout this suite).
        old_py_random_state = random.getstate()
        old_np_random_state = np.random.get_state()
        random.seed(1)
        np.random.seed(1)

        gen = CompositionGenerator(enable_perf_monitoring=False)
        gen.reseed(1)
        bars = 8
        # Pick an emotion that reliably enables bass generation in arrangement curves.
        emotion = EMOTION_BY_NAME["joy"]
        # Outgoing chord pitch classes (C major triad) as a stable anchor.
        prev_pcs = frozenset({0, 4, 7})

        old_hold = getattr(CONFIG.composition, "transition_bridge_hold_bars", 1)
        old_min_common = getattr(CONFIG.composition, "transition_common_tone_min", 1)
        try:
            CONFIG.composition.transition_bridge_hold_bars = 2
            CONFIG.composition.transition_common_tone_min = 1

            events = gen.generate_section(
                emotion=emotion,
                root_note=60,
                bars=bars,
                temperature=0.7,
                target_notes_per_bar=6.0,
                section_index=0,
                transition_handoff_context={
                    "previous_emotion_name": "fear",
                    "previous_chord_pcs": prev_pcs,
                },
            )

            # Find a chord pitch-class set overlapping each bar (same overlap rule used by RT slicing).
            def chord_pcs_in_bar(bar_idx: int):
                bar_start = float(bar_idx) * 4.0
                bar_end = bar_start + 4.0
                for ev in list(events or []):
                    if not ev or len(ev) < 6:
                        continue
                    ch, midi, _vel, st, _dur, notes = ev
                    if int(ch) != 1:
                        continue
                    st = float(st)
                    en = st + float(_dur)
                    if en <= bar_start + 1e-6 or st >= bar_end - 1e-6:
                        continue
                    pcs = {int(n) % 12 for n in (notes or []) if isinstance(n, (int, float))}
                    if not pcs and isinstance(midi, (int, float)) and int(midi) > 0:
                        pcs = {int(midi) % 12}
                    if pcs:
                        return pcs
                return set()

            pcs0 = chord_pcs_in_bar(0)
            pcs1 = chord_pcs_in_bar(1)
            chans = sorted({int(ev[0]) for ev in (events or []) if isinstance(ev, tuple) and len(ev) == 6})
            self.assertTrue(bool(pcs0), msg=f"no chord pcs found in bar0; channels_present={chans}")
            self.assertTrue(bool(pcs1), msg=f"no chord pcs found in bar1; channels_present={chans}")
            self.assertGreaterEqual(len(set(pcs0) & set(prev_pcs)), 1)
            self.assertGreaterEqual(len(set(pcs1) & set(prev_pcs)), 1)
        finally:
            CONFIG.composition.transition_bridge_hold_bars = old_hold
            CONFIG.composition.transition_common_tone_min = old_min_common
            random.setstate(old_py_random_state)
            np.random.set_state(old_np_random_state)
