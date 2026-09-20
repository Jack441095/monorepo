"""Tests for thursday/watcher.py's file-stabilization wait (D2.4).

_wait_for_stable_size() replaced a flat time.sleep(1.5) "wait for the file
to finish writing" -- too short for large multitrack renders/slow copies,
and it fed a key computed *before* the wait into the seen-cache, which
caused a file caught mid-write to be re-analysed a second time once its
size settled. These tests exercise the stabilization primitive directly
(fast: capped poll intervals, no real audio files needed) rather than the
watch() loop itself, which runs forever and needs real audio-analysis
dependencies.
"""

from __future__ import annotations

import threading
import time

from thursday.watcher import _file_key, _wait_for_stable_size


def test_wait_returns_quickly_once_size_is_already_stable(tmp_path):
    f = tmp_path / "done.wav"
    f.write_bytes(b"x" * 1000)

    start = time.monotonic()
    _wait_for_stable_size(f, poll_interval=0.1, max_wait=5.0)
    elapsed = time.monotonic() - start

    # One poll interval to confirm stability, not the full max_wait.
    assert elapsed < 1.0


def test_wait_blocks_until_a_growing_file_stops_growing(tmp_path):
    f = tmp_path / "growing.wav"
    f.write_bytes(b"x" * 10)
    growth_done = threading.Event()

    # The writer grows the file several times *per* poll interval, so
    # every poll (including the first) is guaranteed to see a larger size
    # than the last one -- no poll can land in a quiet gap that predates
    # writing, which is what let earlier versions of this test return
    # "stable" before growth had even started.
    poll_interval = 0.05
    write_duration = 0.25

    def keep_growing():
        deadline = time.monotonic() + write_duration
        while time.monotonic() < deadline:
            time.sleep(0.01)
            with open(f, "ab") as fh:
                fh.write(b"x" * 50)
        growth_done.set()

    writer = threading.Thread(target=keep_growing)
    writer.start()
    start = time.monotonic()
    _wait_for_stable_size(f, poll_interval=poll_interval, max_wait=5.0)
    elapsed = time.monotonic() - start
    writer.join()

    # Must not have returned before the writer actually finished.
    assert growth_done.is_set()
    assert elapsed >= write_duration


def test_wait_gives_up_after_max_wait_on_a_file_that_never_stabilizes(tmp_path):
    f = tmp_path / "stuck.wav"
    f.write_bytes(b"x" * 10)
    stop = threading.Event()

    def keep_growing_forever():
        while not stop.is_set():
            time.sleep(0.05)
            with open(f, "ab") as fh:
                fh.write(b"x")

    writer = threading.Thread(target=keep_growing_forever)
    writer.start()
    start = time.monotonic()
    _wait_for_stable_size(f, poll_interval=0.05, max_wait=0.3)
    elapsed = time.monotonic() - start
    stop.set()
    writer.join()

    # Gives up at max_wait rather than hanging forever.
    assert elapsed < 1.0


def test_wait_on_a_file_that_disappears_returns_immediately(tmp_path):
    f = tmp_path / "gone.wav"
    f.write_bytes(b"x")
    f.unlink()

    start = time.monotonic()
    _wait_for_stable_size(f, poll_interval=0.1, max_wait=5.0)
    assert time.monotonic() - start < 1.0


def test_file_key_reflects_final_not_initial_size(tmp_path):
    # Regression guard for the double-fire bug: a key taken while a file is
    # still growing differs from the key taken once it's finished, which is
    # exactly why the watch loop now defers seen.add() until after the
    # stabilization wait rather than before it.
    f = tmp_path / "x.wav"
    f.write_bytes(b"x" * 10)
    key_before = _file_key(f)

    with open(f, "ab") as fh:
        fh.write(b"x" * 500)
    key_after = _file_key(f)

    assert key_before != key_after
