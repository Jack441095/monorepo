"""C6 corpus guards: no evaluation leakage, compact targets, drafted seeds stay labelled."""

import json

import pytest

from scripts.build_kenn_command_corpus import build_rows, scenario_snapshots
from scripts.build_kenn_command_training import (
    _plan, assert_no_holdout_overlap, evaluation_queries, normalize_query, plan_target,
)
from scripts.drafted_command_seeds import (
    DRAFTED_ACTION_SEEDS, DRAFTED_CLARIFY_SEEDS, DRAFTED_GLOBAL_SEEDS, DRAFTED_RECIPE_SEEDS, DRAFTED_TRACK_SEEDS,
    SOURCE_KIND, drafted_records,
)
from scripts.train_kenn_command_lora_mlx import split_rows
from kenn.core.live_command import validate_llm_plan


def test_overlap_guard_covers_natural_holdouts_and_ignores_case_and_punctuation() -> None:
    held_out = evaluation_queries()
    assert normalize_query("Vocals louder.") in held_out  # curated natural holdout
    assert normalize_query("drop the hats by 2 dB") in held_out  # drafted candidates
    with pytest.raises(ValueError, match="leakage"):
        assert_no_holdout_overlap([{"query": "VOCALS   louder!"}])


def test_targets_leave_out_nulls_and_the_schema_constant() -> None:
    target = json.loads(plan_target(_plan("set_mute", track_index=1, track_name="Drum Bus", value=True)))
    assert "schema" not in target and None not in target.values()
    assert target["action"] == "set_mute" and target["track_name"] == "Drum Bus"


def test_drafted_seeds_fill_scenario_names_validate_and_stay_labelled() -> None:
    for snapshot in scenario_snapshots():
        rows = drafted_records(snapshot, _plan)
        assert len(rows) == (len(DRAFTED_CLARIFY_SEEDS) + len(DRAFTED_ACTION_SEEDS) + len(DRAFTED_TRACK_SEEDS)
                             + len(DRAFTED_GLOBAL_SEEDS) + len(DRAFTED_RECIPE_SEEDS))
        assert all("{" not in row["query"] for row in rows)
        assert all(row["source_kind"] == SOURCE_KIND for row in rows)
        assert all(validate_llm_plan(row["label"], snapshot)["ok"] for row in rows)


def test_corpus_with_drafted_seeds_is_leak_free_and_at_least_a_third_clarify() -> None:
    rows = build_rows(variants=8, scenarios=4, include_drafted=True, clarify_variants=10)
    assert_no_holdout_overlap(rows)
    clarify = sum(row["label"]["action"] == "clarify" for row in rows)
    assert clarify * 3 >= len(rows)
    assert not any("(variant " in row["query"] for row in rows)
    assert {row["source_kind"] for row in rows} == {"reviewed_seed", SOURCE_KIND}
    assert all(row["messages"][1]["content"].endswith(row["query"]) for row in rows)
    # Without the flag, only reviewed seeds are used.
    assert {row["source_kind"] for row in build_rows(variants=2, scenarios=1)} == {"reviewed_seed"}


def test_split_is_deterministic_and_keeps_both_sides_non_empty() -> None:
    rows = [{"i": i} for i in range(20)]
    train, valid = split_rows(rows, valid_fraction=0.1, seed=0)
    assert (train, valid) == split_rows(rows, valid_fraction=0.1, seed=0)
    assert len(valid) == 2 and len(train) == 18
    assert split_rows(rows[:2], valid_fraction=0.9, seed=0)[0]


def test_compact_corpus_uses_the_compact_system_prompt() -> None:
    from kenn.core.live_command import LLM_COMMAND_SYSTEM_PROMPT_COMPACT

    rows = build_rows(variants=2, scenarios=1, prompt="compact")
    assert {row["messages"][0]["content"] for row in rows} == {LLM_COMMAND_SYSTEM_PROMPT_COMPACT}


def test_lora_merge_maps_adapter_pairs_and_scale() -> None:
    from scripts.merge_lora_into_checkpoint import lora_scale, pair_keys

    keys = ["base_model.model.model.layers.0.mlp.up_proj.lora_A.weight",
            "base_model.model.model.layers.0.mlp.up_proj.lora_B.weight"]
    assert pair_keys(keys, "base_model.model.model.", "model.language_model.") == {
        "model.language_model.layers.0.mlp.up_proj.weight": (keys[0], keys[1])}
    with pytest.raises(ValueError, match="lora_B"):
        pair_keys(keys[:1], "base_model.model.model.", "model.language_model.")
    assert lora_scale({"r": 16, "lora_alpha": 32}) == 2.0
    assert lora_scale({"r": 16, "lora_alpha": 32, "use_rslora": True}) == 8.0


def test_drafted_action_seeds_keep_their_wording_and_dB_volumes_convert() -> None:
    rows = build_rows(variants=8, scenarios=1, include_drafted=True)
    kill = [row for row in rows if row["source_record_id"] == "draft-mute-01"]
    assert kill[0]["query"] == "Kill Drum Bus" and json.loads(kill[0]["messages"][2]["content"])["action"] == "set_mute"
    relative = next(row for row in rows if row["source_record_id"] == "draft-vol-06")
    snapshot = scenario_snapshots()[0]
    checked = validate_llm_plan(relative["label"], snapshot)
    assert checked["ok"] and checked["plan"]["unit"] == "normalized"
    assert abs(checked["plan"]["value"] - 0.55 * 10 ** (3 / 20)) < 1e-6


def test_cap_per_action_spreads_across_seeds_and_exempts_clarify() -> None:
    from scripts.build_kenn_command_corpus import cap_per_action

    rows = ([{"label": {"action": "set_mute"}, "source_record_id": f"m{seed}", "n": n} for seed in (1, 2) for n in range(10)]
            + [{"label": {"action": "clarify"}, "source_record_id": "c", "n": n} for n in range(30)])
    capped = cap_per_action(rows, 6)
    mutes = [row for row in capped if row["label"]["action"] == "set_mute"]
    assert len(mutes) == 6 and {row["source_record_id"] for row in mutes} == {"m1", "m2"}
    assert sum(row["label"]["action"] == "clarify" for row in capped) == 30
