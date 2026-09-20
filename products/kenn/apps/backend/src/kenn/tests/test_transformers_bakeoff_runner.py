from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "run_deliberative_transformers_bakeoff.py"
spec = importlib.util.spec_from_file_location("transformers_bakeoff_runner", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_gpu_runner_requires_model_and_output_below_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    model = data_root / "models" / "qwen"
    output = data_root / "evidence" / "result.json"
    model.mkdir(parents=True)

    checked_model, checked_output, checked_root = module.validate_data_paths(
        model_path=model, output=output, data_root=data_root,
    )

    assert checked_model == model.resolve()
    assert checked_output == output.resolve()
    assert checked_root == data_root.resolve()


def test_gpu_runner_rejects_paths_outside_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    model = data_root / "models" / "qwen"
    model.mkdir(parents=True)

    with pytest.raises(ValueError, match="Output path"):
        module.validate_data_paths(
            model_path=model,
            output=tmp_path / "elsewhere" / "result.json",
            data_root=data_root,
        )

    outside_model = tmp_path / "outside-model"
    outside_model.mkdir()
    with pytest.raises(ValueError, match="Model path"):
        module.validate_data_paths(
            model_path=outside_model,
            output=data_root / "result.json",
            data_root=data_root,
        )


class _FakeTensor:
    def __init__(self, shape=(1, 42)):
        self.shape = shape
        self.device = None

    def to(self, device):
        self.device = device
        return self


class _FakeBatch(dict):
    def to(self, device):
        for value in self.values():
            value.to(device)
        return self


def test_generation_inputs_accepts_keyed_tokenizer_batch() -> None:
    ids = _FakeTensor()
    mask = _FakeTensor()
    inputs, length = module._generation_inputs(
        _FakeBatch(input_ids=ids, attention_mask=mask), "cuda:0",
    )

    assert inputs == {"input_ids": ids, "attention_mask": mask}
    assert length == 42
    assert ids.device == mask.device == "cuda:0"


def test_generation_inputs_accepts_bare_tensor_and_rejects_bad_batch() -> None:
    ids = _FakeTensor(shape=(1, 7))
    inputs, length = module._generation_inputs(ids, "cuda:0")
    assert inputs == {"input_ids": ids}
    assert length == 7

    with pytest.raises(ValueError, match="input_ids"):
        module._generation_inputs(_FakeBatch(attention_mask=_FakeTensor()), "cuda:0")


def test_only_runtime_dependency_errors_are_fatal_to_bakeoff() -> None:
    assert module._is_fatal_inference_error(ImportError("missing kernel")) is True
    assert module._is_fatal_inference_error(ModuleNotFoundError("missing package")) is True
    assert module._is_fatal_inference_error(ValueError("invalid model JSON")) is False


def test_gpu_evidence_hashes_policy_evaluator_and_benchmark_inputs() -> None:
    hashes = module.evidence_input_sha256(list(module.DEFAULT_BENCHMARKS))

    assert "tooling/scripts/run_deliberative_transformers_bakeoff.py" in hashes
    assert "apps/backend/src/kenn/core/deliberative_plan.py" in hashes
    assert "apps/backend/src/kenn/core/deliberative_planner.py" in hashes
    assert "apps/backend/src/kenn/core/model_recovery_eval.py" in hashes
    assert "packages/chat/evals/ableton_deliberative_holdout.json" in hashes
    assert "packages/chat/evals/ableton_deliberative_adversarial.json" in hashes
    assert all(len(value) == 64 for value in hashes.values())


class _FailingTokenizer:
    def apply_chat_template(self, *_args, **_kwargs):
        raise ImportError("finegrained-fp8 kernel requires kernels")


def test_predict_suite_aborts_on_systemic_inference_failure() -> None:
    benchmark = {
        "cases": [{
            "id": "provider_failure",
            "goal": "Inspect the current session",
            "context": {
                "schema": "kenn.session_context.v1",
                "session_id": "session-test",
                "snapshot_fingerprint": "12345678",
                "transport": {"status": "connected"},
                "tracks": [],
                "available_actions": ["inspect_live"],
            },
        }],
    }

    with pytest.raises(module.FatalInferenceError, match="provider_failure.*ImportError"):
        module._predict_suite(
            benchmark=benchmark,
            model=type("Model", (), {"device": "cuda:0"})(),
            tokenizer=_FailingTokenizer(),
            torch=object(),
            model_id="broken-fp8",
            max_output_tokens=128,
        )
