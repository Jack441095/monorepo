"""
Arpeggiator pitch classes should stay within the active chord's tone pool
(voicing + chord-symbol completion), including half-bar harmonic-rhythm steps.
"""
from __future__ import annotations

import unittest


def _arp_midi(ev) -> int:
    if len(ev) != 6:
        raise ValueError("expected 6-tuple event")
    notes = ev[5]
    if isinstance(notes, list) and notes:
        return int(notes[0])
    return int(ev[1])


def _allowed_pcs_for_bar(owner, chord: str, root: int, voiced_row: list[int]) -> set[int]:
    """Pitch classes the arpeggiator may use (voicing ∪ chord-symbol tones)."""
    pcs = {int(n) % 12 for n in voiced_row if isinstance(n, int)}
    try:
        sym = [int(n) for n in owner._chord_symbol_to_notes(str(chord), int(root)) if isinstance(n, int)]
    except Exception:
        sym = []
    pcs |= {int(n) % 12 for n in sym}
    return pcs


def _chord_bar_index_for_start(
    *,
    start_beats: float,
    beats_per_bar: float,
    hr_actions: list[str | None],
    grid: float,
) -> int:
    """
    Mirror ``Arpeggiator`` chord index selection for half/anticipate/triple
    when ``harmonic_rhythm_action_by_bar`` is provided (hold-only otherwise).
    """
    bpb = float(beats_per_bar)
    if bpb <= 1e-9:
        return 0
    bar = int(start_beats // bpb)
    bar_start = float(bar) * bpb
    steps_per_bar = max(1, int(round(bpb / float(grid))))
    step = int(round((float(start_beats) - bar_start) / float(grid)))
    step = max(0, min(steps_per_bar - 1, step))
    idx = int(bar)
    act = str(hr_actions[bar]).strip().lower() if bar < len(hr_actions) and hr_actions[bar] else "hold"
    if act == "half" and (bar + 1) < 256:  # upper bound sanity only for tests
        if int(step) >= int(steps_per_bar) // 2:
            idx = int(bar) + 1
    elif act == "anticipate" and (bar + 1) < 256:
        n_early = max(1, int(round(0.5 / float(grid))))
        if int(step) >= int(steps_per_bar) - int(n_early):
            idx = int(bar) + 1
    elif act == "triple" and (bar + 2) < 256:
        if int(step) >= (2 * int(steps_per_bar)) // 3:
            idx = int(bar) + 2
        elif int(step) >= int(steps_per_bar) // 3:
            idx = int(bar) + 1
    return int(idx)


class ArpChordPitchConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        from composition.engine import CompositionGenerator
        from audiogen_core.config import CONFIG

        self._gen = CompositionGenerator(enable_perf_monitoring=False)
        self._old_non_chord = bool(getattr(CONFIG.composition, "arp_non_chord_tones_enabled", False))
        self._old_hint = float(getattr(CONFIG.composition, "arp_next_bar_last_step_hint_prob", 0.0) or 0.0)
        CONFIG.composition.arp_non_chord_tones_enabled = False
        CONFIG.composition.arp_next_bar_last_step_hint_prob = 0.0

    def tearDown(self) -> None:
        from audiogen_core.config import CONFIG

        CONFIG.composition.arp_non_chord_tones_enabled = self._old_non_chord
        CONFIG.composition.arp_next_bar_last_step_hint_prob = self._old_hint

    def test_generate_from_chords_voiced_hold_only_stays_in_chord_pcs(self) -> None:
        from composition.arpeggiator_engine import Arpeggiator
        from data.music_data import EMOTION_BY_NAME

        owner = self._gen
        arp = Arpeggiator(owner=owner)
        emo = EMOTION_BY_NAME["neutral"]
        bars = 4
        bpb = 4.0
        chords = ["C", "F", "G", "C"]
        roots = [60, 65, 67, 60]
        voiced = [
            [60, 64, 67],
            [65, 69, 72],
            [67, 71, 74],
            [60, 64, 67],
        ]
        hr = ["hold"] * bars
        arp_plan = {
            "tones_source": "voiced",
            "harmonic_rhythm_action_by_bar": list(hr),
            "lane_center_by_bar": [67, 69, 71, 67],
            "lane_half_width": 12,
            "mode_by_bar": ["up"] * bars,
            "grid": 0.25,
        }
        events = arp.generate_from_chords(
            emo,
            chords,
            roots,
            bars,
            bpb,
            target_notes_per_bar=8.0,
            channel=3,
            chosen_lane=[67] * bars,
            voiced_chords=voiced,
            section_role="a",
            arp_plan=arp_plan,
        )
        self.assertTrue(events)
        grid = 0.25
        for ev in events:
            if len(ev) != 6 or int(ev[0]) != 3:
                continue
            st = float(ev[3])
            cbi = _chord_bar_index_for_start(
                start_beats=st,
                beats_per_bar=bpb,
                hr_actions=hr,
                grid=grid,
            )
            self.assertLess(cbi, len(chords), msg=f"chord index OOB at t={st}")
            pool = _allowed_pcs_for_bar(owner, chords[cbi], roots[cbi], voiced[cbi])
            pc = _arp_midi(ev) % 12
            self.assertIn(
                pc,
                pool,
                msg=f"arp pc={pc} at beat {st} (chord_bar={cbi}) not in pool {sorted(pool)}",
            )

    def test_half_bar_hr_second_half_uses_next_chord_pool(self) -> None:
        from composition.arpeggiator_engine import Arpeggiator
        from data.music_data import EMOTION_BY_NAME

        owner = self._gen
        arp = Arpeggiator(owner=owner)
        emo = EMOTION_BY_NAME["neutral"]
        bars = 2
        bpb = 4.0
        chords = ["C", "G"]
        roots = [60, 67]
        voiced = [[60, 64, 67], [67, 71, 74]]
        hr = ["half", "hold"]
        arp_plan = {
            "tones_source": "voiced",
            "harmonic_rhythm_action_by_bar": list(hr),
            "lane_center_by_bar": [67, 71],
            "lane_half_width": 12,
            "mode_by_bar": ["up"] * bars,
            "grid": 0.25,
        }
        events = arp.generate_from_chords(
            emo,
            chords,
            roots,
            bars,
            bpb,
            target_notes_per_bar=8.0,
            channel=3,
            chosen_lane=[67, 71],
            voiced_chords=voiced,
            section_role="a",
            arp_plan=arp_plan,
        )
        grid = 0.25
        for ev in events:
            if len(ev) != 6 or int(ev[0]) != 3:
                continue
            st = float(ev[3])
            cbi = _chord_bar_index_for_start(
                start_beats=st,
                beats_per_bar=bpb,
                hr_actions=hr,
                grid=grid,
            )
            pool = _allowed_pcs_for_bar(owner, chords[cbi], roots[cbi], voiced[cbi])
            pc = _arp_midi(ev) % 12
            self.assertIn(pc, pool, msg=f"beat {st} chord_idx={cbi} pc={pc} pool={sorted(pool)}")

    def test_generate_from_harmonic_plan_matches_voicing_pcs(self) -> None:
        from composition.arpeggiator_engine import Arpeggiator
        from composition.harmonic_plan import HarmonicPlan
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTION_BY_NAME

        owner = self._gen
        arp = Arpeggiator(owner=owner)
        emo = EMOTION_BY_NAME["neutral"]
        plan = SectionPlan(
            emotion=emo,
            root_note=60,
            bars=3,
            beats_per_bar=4.0,
            chords=["Dm7", "G7", "Cmaj7"],
            roots=[62, 67, 60],
            chosen_bass=[38, 43, 36],
            chosen_melody=[70, 71, 72],
            chosen_chord=[
                [62, 65, 69, 72],
                [67, 71, 74, 77],
                [60, 64, 67, 71],
            ],
        )
        hp = HarmonicPlan.from_section_plan(plan)
        voiced = hp.voiced_chords_as_lists() or []
        hr = ["hold"] * int(hp.bars)
        arp_plan = {
            "tones_source": "voiced",
            "harmonic_rhythm_action_by_bar": list(hr),
            "lane_center_by_bar": list(hp.chosen_melody),
            "lane_half_width": 12,
            "mode_by_bar": ["up"] * int(hp.bars),
            "grid": 0.25,
        }
        events = arp.generate_from_harmonic_plan(
            emo,
            hp,
            target_notes_per_bar=8.0,
            channel=3,
            chosen_lane=list(hp.chosen_melody),
            voiced_chords=voiced,
            arp_plan=arp_plan,
            section_role="a",
        )
        grid = 0.25
        chords = list(hp.chords)
        roots = list(hp.roots)
        for ev in events:
            if len(ev) != 6 or int(ev[0]) != 3:
                continue
            st = float(ev[3])
            cbi = _chord_bar_index_for_start(
                start_beats=st,
                beats_per_bar=float(hp.beats_per_bar),
                hr_actions=hr,
                grid=grid,
            )
            pool = _allowed_pcs_for_bar(owner, chords[cbi], roots[cbi], voiced[cbi])
            pc = _arp_midi(ev) % 12
            self.assertIn(pc, pool)


if __name__ == "__main__":
    unittest.main()
