"""Seeded regression fingerprints for short section generation (refactor safety net).

Test methods are ordered ``test_01`` … ``test_03`` so goldens run before the
dual-generator planner check; global RNG consumption would otherwise shift later
fingerprints when this module runs after other tests in the same session.

Harmonic-plan tests live in ``tests/test_z_section_harmonic_plan.py`` so they
sort after this module under default ``pytest`` collection (stable RNG for these
goldens when running ``tests/test_section*.py``).

If other suites run **before** this file and perturb global PRNG state (e.g.
``tests/markov/test_melody_generator_integration.py``), ``test_01`` may drift;
run this snapshot module first in that session or re-capture the admiration tuple.
"""
from __future__ import annotations

import random
import unittest


def _fingerprint_section_events(evs):
    """Stable, order-preserving signature of rendered section events."""
    sig = []
    for ev in evs:
        if len(ev) != 6:
            continue
        ch, midi, vel, start, dur, notes = ev
        n = tuple(sorted(int(x) for x in (notes or [])))
        sig.append(
            (int(ch), int(midi), int(vel), round(float(start), 3), round(float(dur), 3), n)
        )
    return tuple(sig)


# Captured with an empty conversation layer (test-only),
# ``CONFIG.set_performance_mode("balanced")`` (maps to ``low``), ``section_k_samples=1``,
# ``joint_generation`` off, ``humanization_scale=0.0``.
# Regenerated when planner output shifts (same seeds).
# Regenerated 2026-07-03 (docs/AUDIOGEN_COMPOSITION_PLAN.md item 19): chord-progression
# template selection in `chord_planner.py::generate_chord_progression` switched from a
# hard `max()` over best-of-K scored candidates to temperature-based softmax sampling,
# to fix a real chord-repetition bug for emotions with narrow cadence archetypes
# (plagal/avoid). This intentionally changes chord output for a fixed seed.
# Regenerated 2026-07-04 (docs/AUDIOGEN_COMPOSITION_PLAN.md, variety work): each emotion's
# chord_progressions pool grew (self-generated augmentation, see
# scripts/augment_chord_progressions.py), which shifts which progression a fixed-seed
# random draw lands on -- an intentional side effect of adding harmonic variety, not a bug.
# Captured with pytest's actual cwd (repo root, where training_data/active_models/
# melody_markov.pkl is NOT found via relative path -- the retrained-Markov path falls back
# to the base generator here; capturing from a different cwd where the pickle IS found
# silently captures a different code path and drifts from what the test suite runs).
_EXPECTED_ADMIRATION_999001 = (
    (2, 64, 73, 0.0, 2.736, (64,)),
    (4, 60, 76, 0.0, 4000000.0, (60,)),
    (1, 48, 69, 0.25, 3.75, ()),
    (1, 52, 68, 0.25, 3.75, ()),
    (1, 55, 72, 0.25, 3.75, ()),
    (2, 67, 73, 3.0, 0.84, (67,)),
    (2, 60, 72, 4.0, 0.912, (62,)),
    (1, 48, 70, 4.0, 4.0, ()),
    (1, 55, 67, 4.0, 4.0, ()),
    (1, 52, 70, 4.0, 4.0, ()),
    (2, 64, 72, 5.0, 0.456, (64,)),
    (2, 67, 72, 5.5, 0.456, (67,)),
    (2, 64, 75, 6.0, 0.912, (64,)),
    (2, 67, 78, 7.0, 0.84, (67,)),
    (2, 69, 76, 8.0, 1.824, (69,)),
    (1, 53, 70, 8.25, 3.75, ()),
    (1, 57, 69, 8.25, 3.75, ()),
    (2, 65, 69, 10.0, 0.912, (65,)),
    (2, 69, 78, 11.0, 0.84, (69,)),
    (2, 64, 75, 12.0, 3.648, (64,)),
    (1, 52, 69, 12.0, 4.0, ()),
    (1, 60, 71, 12.0, 4.0, ()),
)

_EXPECTED_NEUTRAL_999003 = (
    (2, 62, 69, 0.0, 1.824, (62,)),
    (1, 50, 68, 0.0, 4.0, ()),
    (1, 57, 63, 0.0, 4.0, ()),
    (1, 61, 60, 0.0, 4.0, ()),
    (1, 66, 66, 0.0, 4.0, ()),
    (4, 62, 72, 0.0, 4000000.0, (62,)),
    (2, 66, 71, 2.0, 0.684, (66,)),
    (2, 67, 72, 2.75, 0.912, (67,)),
    (2, 73, 73, 3.75, 0.249, (73,)),
    (5, 66, 58, 4.0, 0.9, (66,)),
    (1, 62, 64, 4.25, 3.75, ()),
    (1, 62, 68, 4.25, 3.75, ()),
    (1, 66, 64, 4.25, 3.75, ()),
    (1, 69, 64, 4.25, 3.75, ()),
    (5, 66, 58, 6.0, 0.9, (66,)),
    (2, 66, 72, 7.75, 0.249, (66,)),
    (1, 67, 69, 8.0, 4.0, ()),
    (1, 71, 62, 8.0, 4.0, ()),
    (1, 74, 66, 8.0, 4.0, ()),
    (2, 71, 74, 8.75, 1.171, (71,)),
    (2, 74, 70, 10.0, 0.653, (74,)),
    (2, 78, 69, 10.75, 0.912, (78,)),
    (2, 79, 72, 11.75, 0.249, (78,)),
    (1, 62, 67, 12.0, 4.0, ()),
    (1, 66, 65, 12.0, 4.0, ()),
    (2, 74, 69, 12.75, 0.456, (74,)),
    (2, 67, 68, 13.25, 0.912, (67,)),
    (2, 66, 73, 14.25, 0.576, (66,)),
    (2, 62, 74, 15.0, 0.792, (62,)),
)


class SectionGenerationSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audiogen_core.config import CONFIG
        from audiogen_core.song_upgrade_profile import apply_legacy_composition_profile

        CONFIG.set_performance_mode("balanced")
        # Goldens were captured with an empty conversation layer, not the factory
        # Matsutake/ambient default (60 BPM, joint gen, etc.).
        CONFIG.conversation_presets["__test_empty_conversation__"] = {}
        CONFIG.set_conversation_preset("__test_empty_conversation__")
        apply_legacy_composition_profile(CONFIG)

    @classmethod
    def tearDownClass(cls):
        from audiogen_core.config import CONFIG

        try:
            CONFIG.set_conversation_preset("default_ambient_01")
        except Exception:
            pass

    def setUp(self):
        from audiogen_core.config import CONFIG
        from audiogen_core.song_upgrade_profile import apply_legacy_composition_profile
        import numpy as np

        # Re-apply each time so a prior test in the same session cannot leave
        # CONFIG in a different conversation/perf profile.
        CONFIG.set_performance_mode("balanced")
        CONFIG.conversation_presets["__test_empty_conversation__"] = {}
        CONFIG.set_conversation_preset("__test_empty_conversation__")
        apply_legacy_composition_profile(CONFIG)
        self._old_k = getattr(CONFIG.composition, "section_k_samples", 1)
        CONFIG.composition.section_k_samples = 1
        # Stabilize any incidental use of Python's global PRNG inside planners.
        self._old_py_random_state = random.getstate()
        random.seed(13371337)
        try:
            self._old_np_random_state = np.random.get_state()
            np.random.seed(13371337)
        except Exception:
            self._old_np_random_state = None

    def tearDown(self):
        from audiogen_core.config import CONFIG
        import numpy as np

        CONFIG.composition.section_k_samples = self._old_k
        try:
            random.setstate(self._old_py_random_state)
        except Exception:
            pass
        if getattr(self, "_old_np_random_state", None) is not None:
            try:
                np.random.set_state(self._old_np_random_state)
            except Exception:
                pass

    def test_01_generate_section_admiration_fingerprint(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTIONS
        import numpy as np

        random.seed(999001)
        try:
            np.random.seed(999001)
        except Exception:
            pass

        gen = CompositionGenerator(enable_perf_monitoring=False)
        gen.reseed(999001)
        evs = gen.generate_section(
            EMOTIONS[0],
            root_note=60,
            bars=4,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=0,
        )
        self.assertEqual(_fingerprint_section_events(evs), _EXPECTED_ADMIRATION_999001)

    def test_03_build_section_matches_planner_entry(self):
        """`SectionPlanner.build_section` should match `generate_section` for the same seed."""
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTIONS
        import numpy as np

        random.seed(999001)
        try:
            np.random.seed(999001)
        except Exception:
            pass
        gen_a = CompositionGenerator(enable_perf_monitoring=False)
        gen_a.reseed(999001)
        via_engine = gen_a.generate_section(
            EMOTIONS[0],
            root_note=60,
            bars=4,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=0,
        )
        random.seed(999001)
        try:
            np.random.seed(999001)
        except Exception:
            pass
        gen_b = CompositionGenerator(enable_perf_monitoring=False)
        gen_b.reseed(999001)
        via_planner = gen_b.section_planner.build_section(
            emotion=EMOTIONS[0],
            root_note=60,
            bars=4,
            key_changes=None,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            chord_progression=None,
            melody_styles=None,
            section_index=0,
        )
        self.assertEqual(
            _fingerprint_section_events(via_planner),
            _fingerprint_section_events(via_engine),
        )

    def test_02_generate_section_neutral_fingerprint(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME
        import numpy as np

        random.seed(999003)
        try:
            np.random.seed(999003)
        except Exception:
            pass

        gen = CompositionGenerator(enable_perf_monitoring=False)
        gen.reseed(999003)
        evs = gen.generate_section(
            EMOTION_BY_NAME["neutral"],
            root_note=62,
            bars=4,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=0,
        )
        self.assertEqual(_fingerprint_section_events(evs), _EXPECTED_NEUTRAL_999003)


if __name__ == "__main__":
    unittest.main()
