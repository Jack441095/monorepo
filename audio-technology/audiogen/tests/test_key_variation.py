"""Per-song key variation (docs/AUDIOGEN_COMPOSITION_PLAN.md, variety work 2026-07-04).

Successive generations of the same emotion used to always be in C (root 60). The runner
now transposes each whole song to a fresh tonic via `_maybe_vary_root`. These tests pin the
contract: it varies keys, respects the pool, and yields to key_lock when that's on.
"""
import types
import unittest


def _make_runner():
    """A minimal object carrying just the method + attrs _maybe_vary_root needs, so the
    test doesn't build the whole composition engine."""
    from runner import AdapterComposer  # actual class holding the method

    r = AdapterComposer.__new__(AdapterComposer)
    return r


class _Comp:
    def __init__(self, **kw):
        self.key_variation_enabled = kw.get("key_variation_enabled", True)
        self.key_lock_enabled = kw.get("key_lock_enabled", False)
        self.key_variation_root_offsets = kw.get(
            "key_variation_root_offsets", [-5, -3, -2, 0, 2, 4, 5, 7]
        )
        self.key_variation_avoid_immediate_repeat = kw.get(
            "key_variation_avoid_immediate_repeat", True
        )


_EMO = types.SimpleNamespace(name="admiration")


class TestKeyVariation(unittest.TestCase):
    def setUp(self):
        self.r = _make_runner()

    def test_disabled_returns_base_root(self):
        comp = _Comp(key_variation_enabled=False)
        self.assertEqual(self.r._maybe_vary_root(comp, _EMO, 60), 60)

    def test_key_lock_takes_precedence(self):
        comp = _Comp(key_variation_enabled=True, key_lock_enabled=True)
        for _ in range(10):
            self.assertEqual(self.r._maybe_vary_root(comp, _EMO, 60), 60)

    def test_roots_within_pool(self):
        comp = _Comp()
        allowed = {60 + o for o in comp.key_variation_root_offsets}
        for _ in range(50):
            self.assertIn(self.r._maybe_vary_root(comp, _EMO, 60), allowed)

    def test_keys_actually_vary(self):
        comp = _Comp()
        roots = {self.r._maybe_vary_root(comp, _EMO, 60) for _ in range(30)}
        # Should hit several distinct keys, not stay frozen on one.
        self.assertGreaterEqual(len(roots), 4)

    def test_no_immediate_repeat(self):
        comp = _Comp(key_variation_avoid_immediate_repeat=True)
        prev = None
        repeats = 0
        for _ in range(40):
            r = self.r._maybe_vary_root(comp, _EMO, 60)
            if prev is not None and r == prev:
                repeats += 1
            prev = r
        self.assertEqual(repeats, 0, "immediate key repeats should be suppressed")

    def test_single_offset_pool_is_deterministic(self):
        comp = _Comp(key_variation_root_offsets=[3])
        self.assertEqual(self.r._maybe_vary_root(comp, _EMO, 60), 63)

    def test_none_comp_safe(self):
        self.assertEqual(self.r._maybe_vary_root(None, _EMO, 60), 60)


if __name__ == "__main__":
    unittest.main()
