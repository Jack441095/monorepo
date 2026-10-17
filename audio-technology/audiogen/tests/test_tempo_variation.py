"""Per-song tempo jitter (docs/AUDIOGEN_COMPOSITION_PLAN.md, variety work 2026-07-04).

Companion to key variation: small +/- jitter on base_tempo_bpm so successive generations of
the same emotion don't all land at the exact same bpm. Pins the contract on `_maybe_jitter_tempo`.
"""
import types
import unittest


def _make_runner():
    from runner import AdapterComposer

    r = AdapterComposer.__new__(AdapterComposer)
    return r


class _Comp:
    def __init__(self, **kw):
        self.tempo_variation_enabled = kw.get("tempo_variation_enabled", True)
        self.tempo_variation_max_pct = kw.get("tempo_variation_max_pct", 0.06)


_EMO = types.SimpleNamespace(name="admiration")


class TestTempoVariation(unittest.TestCase):
    def setUp(self):
        self.r = _make_runner()

    def test_disabled_returns_base_tempo(self):
        comp = _Comp(tempo_variation_enabled=False)
        self.assertEqual(self.r._maybe_jitter_tempo(comp, _EMO, 70.0), 70.0)

    def test_zero_pct_returns_base_tempo(self):
        comp = _Comp(tempo_variation_max_pct=0.0)
        self.assertEqual(self.r._maybe_jitter_tempo(comp, _EMO, 70.0), 70.0)

    def test_jitter_within_bounds(self):
        comp = _Comp(tempo_variation_max_pct=0.06)
        lo, hi = 70.0 * 0.94, 70.0 * 1.06
        for _ in range(50):
            bpm = self.r._maybe_jitter_tempo(comp, _EMO, 70.0)
            self.assertGreaterEqual(bpm, lo - 1e-6)
            self.assertLessEqual(bpm, hi + 1e-6)

    def test_tempo_actually_varies(self):
        comp = _Comp()
        bpms = {round(self.r._maybe_jitter_tempo(comp, _EMO, 70.0), 3) for _ in range(30)}
        self.assertGreaterEqual(len(bpms), 5, "tempo should vary across generations, not stay fixed")

    def test_none_comp_safe(self):
        self.assertEqual(self.r._maybe_jitter_tempo(None, _EMO, 70.0), 70.0)


if __name__ == "__main__":
    unittest.main()
