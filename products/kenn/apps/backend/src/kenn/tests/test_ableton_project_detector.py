"""Tests for Ableton project document and bounce detector."""

import os
import tempfile
import pytest

from kenn.core.ableton_project_detector import find_project_bounces


def test_find_project_bounces_detects_and_prioritizes_main_bounce():
    with tempfile.TemporaryDirectory() as tmpdir:
        bounce_dir = os.path.join(tmpdir, "Samples", "Processed", "Bounce")
        os.makedirs(bounce_dir)

        # Create a tiny file that should be ignored (< 500 KB)
        tiny_path = os.path.join(bounce_dir, "click.wav")
        with open(tiny_path, "wb") as f:
            f.write(b"0" * 1024)

        # Create a regular bounce (> 500 KB)
        regular_path = os.path.join(bounce_dir, "Bounce Synth [2026-10-13].wav")
        with open(regular_path, "wb") as f:
            f.write(b"0" * (600 * 1024))

        # Create a main master bounce (> 500 KB)
        main_path = os.path.join(bounce_dir, "Bounce MAIN [2026-10-13].wav")
        with open(main_path, "wb") as f:
            f.write(b"0" * (700 * 1024))

        bounces = find_project_bounces(tmpdir)
        assert len(bounces) == 2
        # Main bounce must be ranked first
        assert bounces[0]["filename"] == "Bounce MAIN [2026-10-13].wav"
        assert bounces[0]["is_main_bounce"] is True
        assert bounces[1]["filename"] == "Bounce Synth [2026-10-13].wav"
        assert bounces[1]["is_main_bounce"] is False


def test_find_project_bounces_detects_new_render_by_mtime():
    """Verify that a newly written render has an mtime that exceeds earlier bounces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bounce_dir = os.path.join(tmpdir, "Bounces")
        os.makedirs(bounce_dir)

        path1 = os.path.join(bounce_dir, "Take 1.wav")
        with open(path1, "wb") as f:
            f.write(b"0" * (600 * 1024))
        # Explicit mtime 1000.0
        os.utime(path1, (1000.0, 1000.0))

        bounces = find_project_bounces(tmpdir)
        assert len(bounces) == 1
        baseline_mtime = bounces[0]["modified_time"]
        assert baseline_mtime == 1000.0

        # Simulate fresh export from Live
        path2 = os.path.join(bounce_dir, "Take 2 Final.wav")
        with open(path2, "wb") as f:
            f.write(b"0" * (600 * 1024))
        os.utime(path2, (1050.0, 1050.0))

        updated_bounces = find_project_bounces(tmpdir)
        assert len(updated_bounces) == 2
        newest = max(updated_bounces, key=lambda b: b["modified_time"])
        assert newest["filename"] == "Take 2 Final.wav"
        assert newest["modified_time"] > baseline_mtime
