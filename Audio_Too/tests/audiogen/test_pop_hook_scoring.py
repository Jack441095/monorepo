import unittest

from audiogen_core.config import CONFIG
from composition.section_scoring import score_section


def _lead_events(pitches: list, *, bpb: float = 4.0, step: float = 0.4) -> list:
    out = []
    t = 0.0
    for p in pitches:
        out.append((2, 0, 90, t, 0.25, [int(p)]))
        t += float(step)
    return out


class PopHookScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._ph = float(getattr(CONFIG.composition, "pop_hook_scoring_strength", 0.0))

    def tearDown(self) -> None:
        try:
            CONFIG.composition.pop_hook_scoring_strength = self._ph
        except Exception:
            pass

    def test_chorus_concentrated_opening_beats_scattered_in_best_of_k(self) -> None:
        """With pop hook scoring on, a dense PC mode in the first two bars scores higher."""
        bpb = 4.0
        # Two bars: many onsets, one pitch class dominant (repeated C4).
        hooky = _lead_events([60, 60, 60, 64, 60, 60, 67, 60, 60, 64], bpb=bpb, step=0.35)
        # Many distinct pitch classes in the same window.
        scattered = _lead_events([60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71], bpb=bpb, step=0.32)

        CONFIG.composition.pop_hook_scoring_strength = 1.0
        s_h = score_section(
            hooky,
            beats_per_bar=bpb,
            bars=2,
            section_role="b",
        )
        s_s = score_section(
            scattered,
            beats_per_bar=bpb,
            bars=2,
            section_role="b",
        )
        b_h = float(s_h.details.get("pop_hook_scoring_bonus", 0.0) or 0.0)
        b_s = float(s_s.details.get("pop_hook_scoring_bonus", 0.0) or 0.0)
        # Term is isolated: total `score` still includes unrelated song metrics.
        self.assertGreater(b_h, b_s)
        self.assertGreater(s_h.details.get("pop_hook_shape", 0.0), s_s.details.get("pop_hook_shape", 0.0))

    def test_verse_role_ignores_pop_hook_term(self) -> None:
        CONFIG.composition.pop_hook_scoring_strength = 1.0
        hooky = _lead_events([60, 60, 60, 64, 60, 60], bpb=4.0, step=0.4)
        s = score_section(
            hooky,
            beats_per_bar=4.0,
            bars=2,
            section_role="a",
        )
        self.assertNotIn("pop_hook_scoring_bonus", s.details)
