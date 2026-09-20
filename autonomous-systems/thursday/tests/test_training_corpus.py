"""Tests for thursday/evals/training_corpus.py -- the synthetic supervised
fine-tuning corpus generator. No LLM/network calls: this only exercises the
programmatic generation and validates its own invariants.
"""

from __future__ import annotations

import json

from thursday.evals import training_corpus as tc
from thursday.evals.brain_benchmark import build_corpus as eval_corpus


def test_corpus_has_a_meaningful_number_of_examples():
    examples = tc.build_training_corpus()
    assert len(examples) >= 200


def test_every_completion_is_valid_json():
    for ex in tc.build_training_corpus():
        data = json.loads(ex.completion)  # must not raise
        assert "type" in data and "steps" in data and "confidence" in data


def test_every_completion_type_is_a_known_decision_type():
    valid_types = {"chat", "plan", "subagent", "abstain", "parallel_swarm"}
    for ex in tc.build_training_corpus():
        data = json.loads(ex.completion)
        assert data["type"] in valid_types, f"{ex.example_id}: unknown type {data['type']!r}"


def test_chat_type_targets_always_have_a_message_and_no_steps():
    for ex in tc.build_training_corpus():
        data = json.loads(ex.completion)
        if data["type"] == "chat":
            assert data["message"], f"{ex.example_id}: chat target missing message"
            assert data["steps"] == [], f"{ex.example_id}: chat target has steps"


def test_plan_type_targets_reference_only_real_catalog_services():
    catalog = tc.build_catalog()
    for ex in tc.build_training_corpus():
        data = json.loads(ex.completion)
        for step in data.get("steps", []):
            if step.get("kind") == "service":
                assert step["service_id"] in catalog, f"{ex.example_id}: unknown service_id {step['service_id']!r}"
            elif step.get("kind") == "subagent":
                assert step["agent"] in tc.SUBAGENTS, f"{ex.example_id}: unknown agent {step['agent']!r}"


def test_messages_end_with_a_user_turn():
    for ex in tc.build_training_corpus():
        assert ex.messages[-1]["role"] == "user"
        assert ex.messages[0]["role"] == "system"


def test_example_ids_are_unique():
    ids = [ex.example_id for ex in tc.build_training_corpus()]
    assert len(ids) == len(set(ids))


def test_disjoint_from_eval_benchmark_corpus():
    """Training on the same text used for evaluation would make
    brain_benchmark.py's 50-case corpus meaningless as a held-out check."""
    eval_texts = {c.user_text.strip().lower() for c in eval_corpus()}
    train_texts = {ex.messages[-1]["content"].strip().lower() for ex in tc.build_training_corpus()}
    overlap = eval_texts & train_texts
    assert not overlap, f"Training corpus overlaps eval corpus: {overlap}"


def test_write_training_jsonl_round_trips(tmp_path):
    out_path = tmp_path / "sft.jsonl"
    count = tc.write_training_jsonl(str(out_path))
    lines = out_path.read_text().splitlines()
    assert count == len(lines)
    first = json.loads(lines[0])
    assert set(first.keys()) == {"example_id", "family", "messages", "completion"}


def test_all_seed_families_are_represented():
    examples = tc.build_training_corpus()
    families = {ex.family for ex in examples}
    assert families == set(tc._SEED_FAMILIES.keys())


def test_clarification_family_sets_question_for_user():
    examples = [ex for ex in tc.build_training_corpus() if ex.family == "clarification_needed"]
    assert examples, "clarification_needed family produced no examples"
    for ex in examples:
        data = json.loads(ex.completion)
        assert data["type"] == "abstain"
        assert data["question_for_user"], f"{ex.example_id}: missing question_for_user"


def test_train_val_split_is_disjoint_and_covers_everything():
    train, val = tc.train_val_split()
    train_ids = {ex.example_id for ex in train}
    val_ids = {ex.example_id for ex in val}
    all_ids = {ex.example_id for ex in tc.build_training_corpus()}
    assert not (train_ids & val_ids)
    assert train_ids | val_ids == all_ids


def test_train_val_split_every_family_represented_in_both():
    train, val = tc.train_val_split()
    train_families = {ex.family for ex in train}
    val_families = {ex.family for ex in val}
    all_families = set(tc._SEED_FAMILIES.keys())
    assert train_families == all_families
    assert val_families == all_families


def test_train_val_split_is_deterministic():
    train1, val1 = tc.train_val_split()
    train2, val2 = tc.train_val_split()
    assert [ex.example_id for ex in train1] == [ex.example_id for ex in train2]
    assert [ex.example_id for ex in val1] == [ex.example_id for ex in val2]


def test_write_train_val_jsonl(tmp_path):
    train_path = tmp_path / "train.jsonl"
    val_path = tmp_path / "val.jsonl"
    n_train, n_val = tc.write_train_val_jsonl(str(train_path), str(val_path))
    assert n_train == len(train_path.read_text().splitlines())
    assert n_val == len(val_path.read_text().splitlines())
    assert n_train > n_val
