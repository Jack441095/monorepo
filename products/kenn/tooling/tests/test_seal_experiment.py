"""Offline examples of review gates, immutable trials and the two distinct SEAL updates."""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tooling"), str(ROOT / "apps/backend/src")]

from seal_experiment.backends import CudaBackend, FixtureBackend, tree_hash
from seal_experiment.cli import MODEL, fixture_dataset, summarize
from seal_experiment.cuda_worker import encode_targets, execute, generation_outcome, row_schedule
from seal_experiment.experiment import PendingReview, correlation, evaluate, grade, grade_packet, run
from seal_experiment.measurements import distribution, product_report
from seal_experiment.records import (Limits, digest, read, reviewed, self_edit,
                                     validate_dataset, validate_example, write)


@pytest.fixture
def data():
    return fixture_dataset()[0]


def approval():
    return {"verdict": "approved", "reviewer": "test-owner", "reviewed_at": "2026-10-13",
            "supported": True, "numbers_units_correct": True, "no_contradictions": True,
            "shared_weights_allowed": True}


def label(correct=True):
    return {"reviewer": "test-owner", "reviewed_at": "2026-10-13", "correct": correct,
            "usefulness": 2 if correct else 0, "unsupported_claims": 0, "policy_violation": False}


def test_source_and_task_splits_validate_without_reading_final_prompts():
    data, sealed = fixture_dataset()
    validate_dataset(data)
    validate_dataset(data, sealed)


@pytest.mark.parametrize("change", ["hash", "private", "permission", "license", "review"])
def test_source_changes_expire_permissions_and_review(data, change):
    source = data["sources"]["train-0"]
    if change == "hash":
        source["text"] += " changed"
    elif change == "private":
        source["privacy"] = "private"
    elif change == "permission":
        source["training_permission"] = False
    elif change == "license":
        source["license"] = ""
    else:
        data["approvals"].pop(digest(source))
    with pytest.raises(ValueError):
        validate_dataset(data)


@pytest.mark.parametrize("field", ["supported", "numbers_units_correct", "no_contradictions", "shared_weights_allowed"])
def test_schema_and_citation_cannot_replace_semantic_attestations(data, field):
    source = data["sources"]["train-0"]
    data["approvals"][digest(source)][field] = False
    assert not reviewed(source, data["approvals"])
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_source_family_cannot_have_training_and_reward_variants(data):
    source = data["sources"]["reward-technical"]
    source["family"] = "train-0"
    data["approvals"][digest(source)] = approval()
    with pytest.raises(ValueError, match="crosses partitions"):
        validate_dataset(data)


def test_final_tasks_are_forbidden_in_development_data(data):
    data["tasks"].append(fixture_dataset()[1]["tasks"][0])
    with pytest.raises(ValueError, match="sealed final"):
        validate_dataset(data)


def test_final_question_fingerprints_are_bound_to_the_sealed_file():
    data, sealed = fixture_dataset()
    data["sealed_questions"][0] = ["incorrect", "fingerprint"]
    with pytest.raises(ValueError, match="fingerprints"):
        validate_dataset(data, sealed)


def test_sealed_content_change_rejects_final_evaluation():
    data, sealed = fixture_dataset()
    sealed["tasks"][0]["question"] += " changed"
    with pytest.raises(ValueError, match="sealed tasks changed"):
        validate_dataset(data, sealed)


def test_reward_partition_requires_each_production_boundary(data):
    data["tasks"] = [t for t in data["tasks"] if t["id"] != "reward-proposal_policy"]
    with pytest.raises(ValueError, match="coverage"):
        validate_dataset(data)


@pytest.mark.parametrize("answer", ["Release is 10 ms.", "Release is 100 Hz.", "Release is 100 ms at 4:1.",
                                     "Release is 100 ms at 20%."])
def test_numbers_and_units_cannot_drift_in_generated_answers(data, answer):
    # The old answer tune passed delivery while inventing settings; changed units must stop before training.
    example = copy.deepcopy(data["ordinary_examples"][0])
    example["messages"][-1]["content"] = answer
    with pytest.raises(ValueError, match="number or unit"):
        validate_example(example, data["sources"], data, set())


def test_whitespace_variants_do_not_count_as_new_training_examples(data):
    first = data["ordinary_examples"][0]
    second = copy.deepcopy(first)
    second["messages"][-1]["content"] += "  \n"
    seen = set()
    validate_example(first, data["sources"], data, seen)
    with pytest.raises(ValueError, match="duplicate"):
        validate_example(second, data["sources"], data, seen)


def test_ordinary_corpus_also_rejects_duplicate_targets(data):
    data["ordinary_examples"].append(data["ordinary_examples"][0])
    with pytest.raises(ValueError, match="duplicate"):
        validate_dataset(data)


def test_evaluation_paraphrase_is_rejected_before_generation_review(data):
    example = copy.deepcopy(data["ordinary_examples"][0])
    example["messages"][0]["content"] = data["tasks"][0]["question"] + " Please?"
    with pytest.raises(ValueError, match="leakage"):
        validate_example(example, data["sources"], data, set())


def test_candidate_cannot_supply_executable_configuration(data):
    source = data["sources"]["train-0"]
    with pytest.raises(ValueError, match="only a bounded"):
        self_edit({"examples": [data["ordinary_examples"][0]], "command": "untrusted"},
                  source_id="train-0", source=source, policy="base", seed=0, data=data,
                  limits=Limits(), generator={"name": "fixture"})


@pytest.mark.parametrize("change", ["excerpt", "hash", "source"])
def test_support_must_be_exact_and_inside_the_supplied_training_source(data, change):
    example = copy.deepcopy(data["ordinary_examples"][0])
    item = example["support"][0]
    item[{"excerpt": "excerpt", "hash": "sha256", "source": "source_id"}[change]] = "unknown"
    with pytest.raises(ValueError):
        validate_example(example, data["sources"], data, set())


@pytest.mark.parametrize("key,value", [("iterations", 4), ("candidates", 5), ("steps", 33),
                                     ("max_length", 4096), ("rank", 17), ("run_seconds", 7201),
                                     ("max_memory_gb", 41), ("learning_rate", float("nan")),
                                     ("generated_tokens", True), ("training_tokens", 10)])
def test_mistyped_pilot_limits_fail_before_loading_a_model(key, value):
    with pytest.raises(ValueError):
        replace(Limits(), **{key: value}).validate()


def test_two_loops_use_isolated_trials_and_resample_after_policy_updates(data, tmp_path):
    backend = FixtureBackend({"model_name": MODEL})
    result = run(data, backend, tmp_path, Limits())
    adaptations = [e for e in result["events"] if e["kind"] == "adaptation"]
    policies = [e for e in result["events"] if e["kind"] == "policy"]
    assert len(policies) == 2
    assert result["arms"]["A"] == backend.base_checkpoint
    assert backend.states[backend.base_checkpoint] == {"adapted": False, "policy_round": 0}
    for iteration in range(2):
        trials = [e for e in adaptations if e["name"].startswith(f"D-iteration-{iteration}")]
        assert len(trials) == 2
        assert trials[0]["start_checkpoint"] == trials[1]["start_checkpoint"]
        assert policies[iteration]["start_checkpoint"] == trials[0]["start_checkpoint"]
        assert policies[iteration]["result"]["checkpoint"] not in [e["result"]["checkpoint"] for e in trials]
    before = read(tmp_path / "D-iteration-0-candidate-0.context-0.edit.json")
    after = read(tmp_path / "D-iteration-1-candidate-0.context-0.edit.json")
    assert before["policy_checkpoint"] != after["policy_checkpoint"]
    assert before["seed"] != after["seed"]
    assert before["payload"] != after["payload"]
    assert len(result["proxy_pairs"]) == 4
    assert len(result["retention"]) == 2
    assert all(e["result"]["steps"] == 4 for e in adaptations)
    summary = summarize(result, tmp_path)
    assert summary["SEAL_value_over_ordinary_finetuning"] == "unmeasured"
    assert summary["arms"]["B"]["complete_p50_seconds"] is None
    assert summary["compute"]["gpu_training_seconds"] is None
    assert summary["promotion"] == "disabled"


def test_failed_adaptation_is_never_reinforced(data, tmp_path):
    class NoLearning(FixtureBackend):
        def train(self, *args, **kwargs):
            result = super().train(*args, **kwargs)
            self.states[result["checkpoint"]]["adapted"] = False
            return result
    result = run(data, NoLearning({}), tmp_path, Limits())
    assert not any(e["kind"] == "policy" for e in result["events"])
    assert len([e for e in result["events"] if e["kind"] == "no_policy_update"]) == 2


def test_retention_loss_blocks_candidate_selection(data, tmp_path):
    class Forgets(FixtureBackend):
        def answer(self, checkpoint, task):
            response = super().answer(checkpoint, task)
            if task["split"] == "retention" and checkpoint != self.base_checkpoint:
                response["text"] = "Forgotten synthetic fixture."
            return response
    result = run(data, Forgets({}), tmp_path, Limits())
    assert not any(e["kind"] == "policy" for e in result["events"])
    assert result["arm_retention"]["D"]["reward"] == 0


def test_outer_policy_retention_loss_rolls_back_only_the_disposable_update(data, tmp_path):
    class PolicyForgets(FixtureBackend):
        def answer(self, checkpoint, task):
            response = super().answer(checkpoint, task)
            if task["split"] == "retention" and self.states[checkpoint]["policy_round"] > 0:
                response["text"] = "Forgotten synthetic fixture."
            return response
    result = run(data, PolicyForgets({}), tmp_path, Limits())
    assert len([e for e in result["events"] if e["kind"] == "policy_retention_rollback"]) == 2
    assert all(p["policy"]["checkpoint"] == "fixture-base" for p in result["retention"])


def test_unreviewed_self_edit_is_saved_but_never_trained(data, tmp_path):
    class ReviewRequired(FixtureBackend):
        def fixture_approvals(self, edit):
            return {}
    backend = ReviewRequired({})
    with pytest.raises(PendingReview, match="approval key"):
        run(data, backend, tmp_path, Limits())
    assert read(tmp_path / "status.json")["training_started_for_edit"] is False
    assert [c[2] for c in backend.calls if c[0] == "train"] == ["B-ordinary"]
    assert (tmp_path / "C-fixed-policy.context-0.edit.json").exists()


def test_missing_owner_reward_grades_pause_before_any_training(data, tmp_path):
    class RealReviewPath(FixtureBackend):
        is_fixture = False
    backend = RealReviewPath({})
    with pytest.raises(PendingReview, match="reward/retention"):
        run(data, backend, tmp_path, Limits())
    assert not any(c[0] == "train" for c in backend.calls)
    assert read(tmp_path / "status.json")["status"] == "pending_reward_review"
    assert read(tmp_path / "blind-progress.json")["cards"][0]["evidence"]


def test_review_resume_rejects_changed_budgets(data, tmp_path):
    run(data, FixtureBackend({}), tmp_path, Limits())
    with pytest.raises(ValueError, match="resume"):
        run(data, FixtureBackend({}), tmp_path, replace(Limits(), candidates=1))


def test_proxy_screen_does_not_invent_learning_rewards(data, tmp_path):
    result = run(data, FixtureBackend({}), tmp_path, Limits(), proxy_screen=0.9)
    assert result["proxy_pairs"] == []
    assert all(e["reward"] is None for e in result["events"] if e["kind"] == "proxy_screen")


def test_proxy_calibration_requires_real_variation():
    assert correlation([{"proxy": 0.5, "gain": 0.2}] * 4)["pearson"] is None
    assert correlation([{"proxy": 0.1, "gain": 0.2}])["pearson"] is None
    assert correlation([{"proxy": x, "gain": x * 2} for x in (0.1, 0.2, 0.3)])["pearson"] == pytest.approx(1)


def test_unknown_prose_cannot_receive_a_model_opinion_reward():
    result = grade("Fluent unsupported opinion", ["Reviewed target"], {})
    assert result["correct"] is False and result["review_status"] == "needs_owner_review"
    with pytest.raises(ValueError, match="owner grade"):
        grade("anything", ["reference"], {**label(), "correct": "false"})


def test_blind_owner_grades_are_content_bound_and_need_no_provider(data, tmp_path):
    run(data, FixtureBackend({}), tmp_path, Limits())
    packet_path = tmp_path / "blind-development.json"
    packet = read(packet_path)
    assert all("arm" not in c and "checkpoint" not in c for c in packet["cards"])
    grades = {c["id"]: label(False) for c in packet["cards"]}
    result = grade_packet(packet_path, grades, tmp_path / "review")
    assert all(r["reward"] == 0 for r in result["reports"].values())
    assert result["promotion"] == "disabled"
    packet["cards"][0]["answer"] = "changed after grading"
    write(packet_path, packet)
    with pytest.raises(ValueError, match="packet changed"):
        grade_packet(packet_path, grades, tmp_path / "review")


def test_frozen_retrieval_keeps_the_real_grounding_checker_active(data, tmp_path):
    task = copy.deepcopy(data["tasks"][0])
    task.update(scope="frozen_retrieval", question="How should I compress the bass?", route="mix",
                confidence="high", answer_mode="", results=[{"score": 10.0, "chunk": {
                    "kind": "note", "source": "synthetic.md", "title": "Synthetic compression",
                    "text": "Key the bass compressor from the kick. Release is 100 ms."}}])
    answer = "Short answer: key the bass compressor from the kick.\n1. Use 10 ms release.\nSources: synthetic.md"
    task["accepted_answers"] = [answer]
    backend = FixtureBackend({})
    backend.states[backend.base_checkpoint]["adapted"] = True
    result = evaluate(backend, backend.base_checkpoint, [task], {}, tmp_path / "eval.json")
    row = result["rows"][0]
    assert row["correct"] is True
    assert row["gate"]["accepted"] is False
    assert row["gate"]["unsupported_measurements"]
    assert result["reward"] == 0


class Tokenizer:
    """Character tokens make assistant masking and truncation visible without model downloads."""

    def apply_chat_template(self, messages, **kwargs):
        prompt = "USER: " + messages[0]["content"] + " ASSISTANT: "
        return prompt if kwargs.get("add_generation_prompt") else prompt + messages[-1]["content"]

    def __call__(self, text, **kwargs):
        return {"input_ids": [ord(c) for c in text]}


def test_training_masks_prompt_tokens_and_never_truncates_reviewed_targets():
    messages = [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}]
    row = encode_targets(Tokenizer(), [messages], 100)[0]
    assert [x for x in row["labels"] if x != -100] == [ord(c) for c in "answer"]
    with pytest.raises(ValueError, match="never truncate"):
        encode_targets(Tokenizer(), [messages], 10)
    messages[-1]["content"] = ""
    with pytest.raises(ValueError, match="empty"):
        encode_targets(Tokenizer(), [messages], 100)


def test_token_prefix_mismatch_cannot_train_on_user_text():
    class BadTokenizer(Tokenizer):
        def __call__(self, text, **kwargs):
            result = super().__call__(text, **kwargs)
            if text.endswith("answer"):
                result["input_ids"][0] = 999
            return result
    messages = [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}]
    with pytest.raises(ValueError, match="prefix mismatch"):
        encode_targets(BadTokenizer(), [messages], 100)


def test_bounded_training_schedule_reaches_later_contexts():
    assert row_schedule(8, 4) == [0, 2, 4, 6]
    assert set(row_schedule(2, 4)) == {0, 1}


@pytest.mark.parametrize("devices", ["", "0", "0,1", "2", "1,2"])
def test_gpu_guard_runs_before_importing_or_loading_training_libraries(monkeypatch, tmp_path, devices):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", devices)
    with pytest.raises(ValueError, match="GPU 1"):
        CudaBackend(tmp_path, {}, tmp_path)
    with pytest.raises(ValueError, match="GPU 1"):
        execute({})


def cuda_shell(tmp_path):
    backend = object.__new__(CudaBackend)
    backend.base_model = tmp_path / "base"
    backend.work = tmp_path
    backend.remaining_seconds = 10
    backend.manifest = {"pinned": True}
    backend.identity = lambda checkpoint: "base-hash" if checkpoint == "base" else tree_hash(Path(checkpoint))
    return backend


def test_worker_inherits_only_gpu_1_and_local_module_paths(monkeypatch, tmp_path):
    backend = cuda_shell(tmp_path)
    calls = []
    def launch(command, **kwargs):
        calls.append((command, kwargs))
        request = read(Path(command[-1]))
        write(Path(request["response_path"]), {"text": "fixture"})
        class Process:
            def wait(self, timeout=None):
                return 0
        return Process()
    monkeypatch.setattr(subprocess, "Popen", launch)
    result = backend._operation("generate", "base", {"operation_seconds": 1}, purpose="self_edit")
    command, kwargs = calls[0]
    assert command[1:3] == ["-m", "seal_experiment.cuda_worker"]
    assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "1"
    assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert kwargs["env"]["KENN_LIVE_BACKEND"] == "fake"
    assert str(ROOT / "tooling") in kwargs["env"]["PYTHONPATH"]
    assert result["operation_purpose"] == "self_edit"
    assert result["start_checkpoint_sha256"] == "base-hash"


def test_timeout_kills_the_whole_trial_process_group_and_records_cost(monkeypatch, tmp_path):
    backend = cuda_shell(tmp_path)
    killed = []
    class Process:
        pid = 987654
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return -9
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(TimeoutError, match="process group stopped"):
        backend._operation("train", "base", {"operation_seconds": 1})
    assert killed == [(987654, signal.SIGKILL)]
    receipt = read(next((tmp_path / "operations").glob("*.response.json")))
    assert receipt["status"] == "timeout" and receipt["operation_wall_seconds"] >= 0


def test_saved_adapter_is_reused_only_for_the_same_training_request(tmp_path):
    backend = cuda_shell(tmp_path)
    calls = []
    def operation(kind, checkpoint, limits, **kwargs):
        calls.append(kind)
        adapter = Path(kwargs["output"]) / "adapter"
        adapter.mkdir(parents=True)
        (adapter / "adapter_model.safetensors").write_bytes(b"synthetic adapter")
        return {"steps": 4}
    backend._operation = operation
    output = tmp_path / "trial"
    first = backend.train("base", [[{"role": "assistant", "content": "fixture"}]], output, Limits())
    second = backend.train("base", [[{"role": "assistant", "content": "fixture"}]], output, Limits())
    assert first["checkpoint"] == second["checkpoint"] and second["reused_training_artifact"]
    assert calls == ["train"]
    (Path(first["checkpoint"]) / "adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        backend.train("base", [[{"role": "assistant", "content": "fixture"}]], output, Limits())


def test_tree_identity_changes_when_adapter_bytes_or_names_change(tmp_path):
    path = tmp_path / "adapter"
    path.mkdir()
    (path / "weights").write_bytes(b"same")
    before = tree_hash(path)
    (path / "weights").rename(path / "different-name")
    assert tree_hash(path) != before


def test_cli_dry_run_works_without_ollama_live_or_cuda(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "tooling/scripts/run_seal_experiment.py"),
                             "dry-run", "--out", str(tmp_path / "pilot")],
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["status"] == "dry_run"
    assert read(tmp_path / "pilot/identity.json")["experimental_serving_enabled"] is False


def test_owner_review_resume_reuses_the_answers_the_owner_actually_graded(data, tmp_path):
    class RealReviewPath(FixtureBackend):
        is_fixture = False
        answers = 0
        def answer(self, checkpoint, task):
            self.answers += 1
            return super().answer(checkpoint, task)
    backend = RealReviewPath({})
    with pytest.raises(PendingReview):
        run(data, backend, tmp_path, Limits())
    assert backend.answers == 7
    progress = read(tmp_path / "progress.json")
    labels = {r["label_key"]: label(False) for r in progress["reports"]["A-base"]["rows"]}
    result = run(data, backend, tmp_path, Limits(), labels=labels)
    assert result["reports"]["A"]["reward"] == 0
    assert all(r["review_status"] == "human" for r in result["reports"]["A"]["rows"])
    uninterrupted = RealReviewPath({})
    run(data, uninterrupted, tmp_path / "uninterrupted", Limits(), labels=labels)
    assert backend.answers == uninterrupted.answers  # Pausing for grades adds no provider calls.


def test_checkpoint_integrity_failure_is_recorded_after_worker_completion(monkeypatch, tmp_path):
    backend = cuda_shell(tmp_path)
    def launch(command, **kwargs):
        request = read(Path(command[-1]))
        write(Path(request["response_path"]), {"text": "fixture"})
        backend.identity = lambda cp: "mutated"
        class Process:
            def wait(self, timeout=None):
                return 0
        return Process()
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(RuntimeError, match="mutated"):
        backend._operation("generate", "base", {"operation_seconds": 1})
    assert read(next((tmp_path / "operations").glob("*.response.json")))["status"] == "checkpoint_mutation"


def product_fixture(data, tmp_path):
    task = data["tasks"][0]
    baseline = {"source_sha256": "code", "index_sha256": "index", "template_sha256": "prompt",
                "generation": {"temperature": 0.35}, "model_digest": "model",
                "hardware": {"chip": "Apple M3", "memory_bytes": 16 * 1024 ** 3}}
    call = {"prompt_tokens": 50, "completion_tokens": 20, "provider_attempted": True,
            "cache_hit": False, "load_duration_ns": 1000000000,
            "prompt_eval_duration_ns": 2000000000, "eval_duration_ns": 3000000000,
            "completion_reason": "stop"}
    row = {"id": task["id"], "question": task["question"], "answer": task["accepted_answers"][0],
           "provider_calls": [call], "cache_dropped": True, "accepted": True, "abstained": False,
           "unsupported_measurements": [], "fallback_reason": None, "captured_evidence": [{"text": "fixture"}],
           "first_useful_answer_seconds": None, "final_received_answer_seconds": 6.0,
           "final_displayed_answer_seconds": None, "memory_pressure": None}
    receipt = {"schema": "kenn.chat_latency.v2", "provenance": {"manifest": baseline,
                "surface": "stream", "cache_settings": {"KENN_LLM_CACHE": "0"}}, "rows": [row]}
    path = tmp_path / "receipt.json"
    write(path, receipt)
    spec = {"schema": "kenn.seal.product_receipts.v1", "baseline": baseline,
            "receipts": [{"arm": "A", "model_condition": "cold", "model_digest": "model", "path": str(path)}]}
    return spec, receipt


def test_missing_visible_timing_is_never_replaced_with_provider_ttft():
    assert distribution([1.0, None])["p50"] is None
    assert distribution([1.0, 2.0])["p50"] == 1.5


def test_offline_summary_keeps_incomplete_timing_coverage_unknown(data, tmp_path):
    result = run(data, FixtureBackend({}), tmp_path, Limits())
    rows = result["reports"]["B"]["rows"]
    for index, row in enumerate(rows):
        row["response"].update(complete_seconds=float(index + 1), prompt_tokens=20, output_tokens=10)
    measured = summarize(result, tmp_path)["arms"]["B"]
    assert measured["complete_p50_seconds"] == 4 and measured["complete_p95_seconds"] == 7
    rows[-1]["response"].update(complete_seconds=None, output_tokens=None)
    incomplete = summarize(result, tmp_path)["arms"]["B"]
    assert incomplete["complete_p50_seconds"] is None and incomplete["output_tokens"] is None
    assert incomplete["complete_timing_measured"] == 6
    assert incomplete["correct_useful_per_inference_second"] is None


def test_cuda_answer_counts_the_existing_grounding_abstention_shape():
    answer = "Insufficient context: the provided sources do not describe the selected track"
    assert generation_outcome(answer, False)["abstained"] is True
    assert generation_outcome(answer + "\nTry changing the release.", True)["abstained"] is False


def test_product_report_preserves_unknown_mac_metrics_and_supports_blind_review(data, tmp_path):
    spec, _ = product_fixture(data, tmp_path)
    report = product_report(spec, data, {}, tmp_path / "product")
    row = report["groups"]["A:cold:stream:cache_disabled"]
    assert row["complete_received_seconds"]["p50"] == 6
    assert row["first_visible_seconds"]["p50"] is None
    assert row["peak_memory_bytes"] is None and row["model_switches"] is None
    assert row["load_seconds"] == 1 and row["prefill_seconds"] == 2 and row["decode_seconds"] == 3
    assert report["amortization_usage_count"] is None and report["promotion"] == "disabled"
    packet = read(tmp_path / "product/blind-product.json")
    result = grade_packet(tmp_path / "product/blind-product.json",
                          {c["id"]: label() for c in packet["cards"]}, tmp_path / "review")
    assert result["reports"]["A:cold:stream:cache_disabled"]["reward"] == 1


@pytest.mark.parametrize("change", ["rejected", "truncated", "unknown_completion"])
def test_product_efficiency_needs_grounded_complete_delivery(data, tmp_path, change):
    # Fluent reference text still earns no delivery savings when grounding refuses it or completion is unknown.
    spec, receipt = product_fixture(data, tmp_path)
    row = receipt["rows"][0]
    if change == "rejected":
        row["accepted"] = False
    else:
        row["provider_calls"][0]["completion_reason"] = "length" if change == "truncated" else None
    write(Path(spec["receipts"][0]["path"]), receipt)
    metrics = product_report(spec, data, {}, tmp_path / "product")["groups"]["A:cold:stream:cache_disabled"]
    assert metrics["reviewed_correct_useful"] == 1
    expected = None if change == "unknown_completion" else 0
    assert metrics["grounded_complete_correct_useful"] == expected
    assert metrics["correct_useful_per_inference_second"] == expected


@pytest.mark.parametrize("change", ["hardware", "index", "model", "question"])
def test_product_receipt_cannot_claim_gpu_or_changed_inputs_as_mac_evidence(data, tmp_path, change):
    spec, receipt = product_fixture(data, tmp_path)
    receipt = copy.deepcopy(receipt)
    if change == "hardware":
        receipt["provenance"]["manifest"]["hardware"]["chip"] = "CUDA GPU"
    elif change == "index":
        receipt["provenance"]["manifest"]["index_sha256"] = "changed"
    elif change == "model":
        receipt["provenance"]["manifest"]["model_digest"] = "changed"
    else:
        receipt["rows"][0]["question"] += " changed"
    write(Path(spec["receipts"][0]["path"]), receipt)
    with pytest.raises(ValueError):
        product_report(spec, data, {}, tmp_path / "product")


def test_actual_cache_hits_get_a_separate_efficiency_group(data, tmp_path):
    spec, receipt = product_fixture(data, tmp_path)
    cached = copy.deepcopy(receipt)
    cached["rows"][0]["provider_calls"][0].update(cache_hit=True, provider_attempted=False)
    cached_path = tmp_path / "cached.json"
    write(cached_path, cached)
    spec["receipts"].append({**spec["receipts"][0], "path": str(cached_path), "model_condition": "warm"})
    report = product_report(spec, data, {}, tmp_path / "product")
    assert set(report["groups"]) == {"A:cold:stream:cache_disabled", "A:warm:stream:cache_hit"}
    assert report["groups"]["A:warm:stream:cache_hit"]["provider_calls"] == 0
    assert report["groups"]["A:warm:stream:cache_hit"]["correct_useful_per_inference_second"] is None


def test_amortization_uses_declared_comparable_costs_instead_of_adding_mac_and_gpu_seconds(data, tmp_path):
    spec, _ = product_fixture(data, tmp_path)
    spec["costs"] = {"unit": "GBP", "baseline_per_answer": 0.02,
                     "arms": {"D": {"per_answer": 0.01, "extra_adaptation": 2.0},
                              "B": {"per_answer": 0.03, "extra_adaptation": 1.0}}}
    report = product_report(spec, data, {}, tmp_path / "product")
    assert report["amortization_usage_count"] == {"D": 200, "B": None}


def test_sealed_cli_reserves_one_shot_before_evaluation_and_refuses_a_second_run(monkeypatch, tmp_path):
    from seal_experiment import cli
    data, sealed = fixture_dataset()
    data["synthetic"] = False  # A synthetic backend stands in for the worker; no real data or provider is used.
    out = tmp_path / "pilot"
    backend = FixtureBackend({"model_name": MODEL, "experimental_serving_enabled": False})
    run(data, backend, out, Limits())
    write(tmp_path / "data.json", data)
    write(tmp_path / "sealed.json", sealed)
    write(tmp_path / "baseline.json", backend.manifest)
    monkeypatch.setattr(cli, "CudaBackend", lambda *args: backend)
    monkeypatch.setattr(sys, "argv", ["seal", "final", "--data", str(tmp_path / "data.json"),
        "--sealed", str(tmp_path / "sealed.json"), "--baseline", str(tmp_path / "baseline.json"),
        "--base-model", str(tmp_path), "--out", str(out)])
    assert cli.main() == 0
    final = read(out / "sealed-final.json")
    assert final["tuning_allowed"] is False and final["promotion"] == "disabled"
    assert (out / "blind-final.json").exists()
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_run_ceiling_includes_compute_from_earlier_review_attempts(data, tmp_path):
    write(tmp_path / "operations/previous.response.json", {"operation_wall_seconds": 3601})
    backend = FixtureBackend({})
    with pytest.raises(TimeoutError, match="wall-clock"):
        run(data, backend, tmp_path, Limits())
    assert backend.calls == []


def test_private_artifacts_cannot_be_written_to_another_tracked_product(monkeypatch):
    from seal_experiment import cli
    monkeypatch.setattr(sys, "argv", ["seal", "dry-run", "--out", str(ROOT.parents[1] / "backend/seal-output")])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
