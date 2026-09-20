"""Checks for the synthetic KENN command-model training export."""

from __future__ import annotations

import json

from scripts.build_kenn_command_training import DEFAULT_OUTPUT, assert_no_holdout_overlap, records, training_snapshot
from kenn.core.live_command import validate_llm_plan


def test_synthetic_command_records_are_valid_and_holdout_safe() -> None:
    rows = records()
    assert len(rows) == 48
    assert {row["label"]["action"] for row in rows} >= {"focus_track", "focus_device", "add_locator", "remove_locator", "create_midi_track", "create_audio_track", "create_return_track", "insert_device_with_parameter"}
    assert any(row["label"].get("unit") == "ms" for row in rows)
    assert any(row["label"].get("unit") == "ratio" for row in rows)
    midi_rows = [row for row in rows if row["label"]["action"] == "create_midi_track"]
    assert {row["label"].get("new_track_name") for row in midi_rows} == {None, "Hi Hats", "Bass Synth"}
    audio_rows = [row for row in rows if row["label"]["action"] == "create_audio_track"]
    assert {row["label"].get("new_track_name") for row in audio_rows} == {None, "Vox Print"}
    return_rows = [row for row in rows if row["label"]["action"] == "create_return_track"]
    assert {row["label"].get("new_track_name") for row in return_rows} == {None, "Vocal Verb", "Parallel Crush"}
    assert all(row["schema"] == "kenn.ableton_command_training.v1" for row in rows)
    assert all(row["split"] == "synthetic_train" for row in rows)
    assert all(validate_llm_plan(row["label"], training_snapshot())["ok"] for row in rows)
    assert_no_holdout_overlap(rows)


def test_tracked_training_artifact_matches_the_reviewed_generator() -> None:
    tracked = [
        json.loads(line)
        for line in DEFAULT_OUTPUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert tracked == records()
