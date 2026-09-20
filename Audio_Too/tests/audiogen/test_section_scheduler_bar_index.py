"""Regression: bar-indexed event slicing matches full linear scan."""

import threading

import pytest

from audio.RT_player.section_scheduler import SectionScheduler
from audiogen_core.config import CONFIG


def _ref_slice_bar_events(sched: SectionScheduler, bar_idx: int):
    bar_start_beats = float(bar_idx) * 4.0
    bar_end_beats = bar_start_beats + 4.0
    out = []
    for ev in sched.current_section_events or []:
        clipped = SectionScheduler._clip_event_to_bar_window(ev, bar_start_beats, bar_end_beats)
        if clipped is not None:
            out.append(clipped)
    return out


@pytest.fixture
def scheduler():
    class _DummyBufferController:
        def trim_queued_bars(self, _keep: int) -> None:
            return

    class _DummyContainer:
        sample_rate = 44100

    class _Owner:
        def __init__(self):
            self.section_lock = threading.RLock()
            self.state_lock = threading.Lock()
            self.config = CONFIG
            self.container = _DummyContainer()
            self.buffer_controller = _DummyBufferController()
            self.allow_async_pregen = False

        def _runtime_generation_mode(self):
            return "normal"

    return SectionScheduler(owner=_Owner(), logger=None)


def test_bar_index_matches_linear_scan_many_events(scheduler):
    n_bars = 32
    events = []
    # Dense grid: short notes on every sixteenth across the section.
    for bar in range(n_bars):
        for step in range(16):
            start = bar * 4.0 + step * 0.25
            events.append((2, 60 + (step % 12), 80, start, 0.24, [60]))
    # Long sustained chord overlapping several bars (bucket span).
    events.append((1, 60, 70, 10.0, 20.0, [60, 64, 67]))
    scheduler.current_section_events = events
    scheduler.current_section_bars = n_bars
    scheduler._invalidate_bar_event_index()

    for bi in range(n_bars):
        indexed = scheduler._slice_bar_events(bi)
        ref = _ref_slice_bar_events(scheduler, bi)
        assert indexed == ref, f"mismatch at bar {bi}"


def test_bar_index_rebuilds_when_events_mutated(scheduler):
    scheduler.current_section_events = [(3, 60, 90, 0.0, 0.5, [60])]
    scheduler.current_section_bars = 4
    scheduler._invalidate_bar_event_index()
    a0 = scheduler._slice_bar_events(0)
    scheduler.current_section_events.append((3, 62, 90, 0.5, 0.5, [62]))
    b0 = scheduler._slice_bar_events(0)
    assert b0 != a0
    assert b0 == _ref_slice_bar_events(scheduler, 0)
