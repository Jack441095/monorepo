"""Checks for the scalable synthetic KENN command corpus builder."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_kenn_command_corpus import build_rows, scenario_snapshots
from scripts.build_kenn_command_training import assert_no_holdout_overlap
from scripts.train_kenn_command_lora import _load_rows
from kenn.core.live_command import validate_llm_plan


def test_corpus_expansion_is_valid_and_holdout_safe() -> None:
    rows = build_rows(variants=4, scenarios=3)
    assert len(rows) == 576
    query_labels: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        snapshot = row["messages"][1]["content"]
        query_labels.setdefault((snapshot, row["query"]), set()).add(json.dumps(row["label"], sort_keys=True))
    assert all(len(labels) == 1 for labels in query_labels.values())
    assert all(row["source_record_id"] for row in rows)
    snapshots = scenario_snapshots()
    assert all(validate_llm_plan(row["label"], snapshots[row["scenario"] - 1])["ok"] for row in rows)
    midi_rows = [row for row in rows if row["label"]["action"] == "create_midi_track"]
    assert len(midi_rows) == 36
    assert {row["label"].get("new_track_name") for row in midi_rows} == {None, "Hi Hats", "Bass Synth"}
    audio_rows = [row for row in rows if row["label"]["action"] == "create_audio_track"]
    assert len(audio_rows) == 24
    assert {row["label"].get("new_track_name") for row in audio_rows} == {None, "Vox Print"}
    return_rows = [row for row in rows if row["label"]["action"] == "create_return_track"]
    assert len(return_rows) == 36
    assert {row["label"].get("new_track_name") for row in return_rows} == {None, "Vocal Verb", "Parallel Crush"}
    setup_rows = [row for row in rows if row["label"]["action"] == "insert_device_with_parameter"]
    assert len(setup_rows) == 24
    assert {row["label"].get("parameter_name") for row in setup_rows} == {"Dry/Wet"}
    assert_no_holdout_overlap(rows)


def test_training_loader_validates_each_corpus_scenario(tmp_path: Path) -> None:
    """The full multi-snapshot export must be loadable before model training."""
    output = tmp_path / "multi-scenario.jsonl"
    rows = build_rows(variants=1, scenarios=4)
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    loaded = _load_rows(output)

    assert len(loaded) == 192
    assert {row["scenario"] for row in loaded} == {1, 2, 3, 4}
