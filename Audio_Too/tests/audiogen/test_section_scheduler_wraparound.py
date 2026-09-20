import threading


def test_section_scheduler_wraps_when_next_not_ready():
    """
    Regression: when the current section ends but the next section isn't ready yet,
    the scheduler should not pin playback on the last bar forever.

    Instead it should wrap around and keep progressing through the existing section
    (bar 0, 1, 0, 1, ...) while background pre-generation catches up.
    """
    from audio.RT_player.section_scheduler import SectionScheduler
    from audiogen_core.config import CONFIG

    class _DummyBufferController:
        def trim_queued_bars(self, _keep: int) -> None:
            return

    class _DummyContainer:
        sample_rate = 44100

    class _DummyEmotion:
        name = "neutral"

    class _Owner:
        def __init__(self):
            self.section_lock = threading.RLock()
            self.state_lock = threading.Lock()
            self.config = CONFIG
            self.container = _DummyContainer()
            self.buffer_controller = _DummyBufferController()
            self._emotion = _DummyEmotion()
            self._root = 60
            # Prevent spawning background pre-generation threads in tests.
            self.allow_async_pregen = False

    owner = _Owner()
    sched = SectionScheduler(owner=owner, logger=None)

    # Two bars worth of events: one note in bar 0 and one in bar 1.
    # Event tuple: (channel, midi, velocity, start_beats, duration_beats, notes)
    sched.current_section_events = [
        (3, 60, 90, 0.0, 0.25, [60]),  # bar 0
        (3, 64, 90, 4.0, 0.25, [64]),  # bar 1
    ]
    sched.current_section_bars = 2
    sched.next_section_ready = False
    sched.next_section_events = None
    sched.next_section_bars = 0

    # Simulate we've already played past the end of the section.
    sched.next_bar_index = 2
    sched.bars_played_this_section = 2

    b0 = sched.prepare_next_bar()["bar_index"]
    b1 = sched.prepare_next_bar()["bar_index"]
    b2 = sched.prepare_next_bar()["bar_index"]

    assert [b0, b1, b2] == [0, 1, 0]

