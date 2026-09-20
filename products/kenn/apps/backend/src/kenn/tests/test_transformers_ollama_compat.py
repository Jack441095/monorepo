from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "serve_transformers_ollama_compat.py"
SPEC = importlib.util.spec_from_file_location("serve_transformers_ollama_compat", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def test_configuration_requires_exact_gpu_selection(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2")

    with pytest.raises(ValueError, match="exactly 1,2,3,4"):
        server.validate_configuration(host="127.0.0.1", model_path=model, data_root=tmp_path)


def test_configuration_rejects_non_loopback_bind(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2,3,4")

    with pytest.raises(ValueError, match="loopback"):
        server.validate_configuration(host="0.0.0.0", model_path=model, data_root=tmp_path)


def test_configuration_requires_model_below_data_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data"
    root.mkdir()
    model = tmp_path / "elsewhere"
    model.mkdir()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2,3,4")

    with pytest.raises(ValueError, match="below"):
        server.validate_configuration(host="localhost", model_path=model, data_root=root)


def test_configuration_rejects_data_root_as_model_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2,3,4")

    with pytest.raises(ValueError, match="dedicated directory below"):
        server.validate_configuration(
            host="127.0.0.1", model_path=tmp_path, data_root=tmp_path,
        )


def test_configuration_accepts_qualified_boundary(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "models" / "qwen"
    model.mkdir(parents=True)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2,3,4")

    assert server.validate_configuration(
        host="127.0.0.1", model_path=model, data_root=tmp_path,
    ) == (model.resolve(), tmp_path.resolve())


def test_cache_environment_is_forced_below_data_root(tmp_path: Path, monkeypatch) -> None:
    for name in server.CACHE_ENVIRONMENT:
        monkeypatch.setenv(name, f"/tmp/untrusted-{name.casefold()}")

    configured = server.configure_cache_environment(tmp_path)

    assert configured == {
        "HF_HOME": str(tmp_path / "huggingface"),
        "HF_HUB_CACHE": str(tmp_path / "huggingface" / "hub"),
        "TRANSFORMERS_CACHE": str(tmp_path / "huggingface" / "transformers"),
    }
    assert all(server.os.environ[name] == value for name, value in configured.items())


def test_generation_passes_all_tokenizer_batch_fields_to_model() -> None:
    class Tensor:
        shape = (1, 2)

        def to(self, _device):
            return self

        def __getitem__(self, _item):
            return self

    class Batch(dict):
        def to(self, _device):
            return self
    class Tokenizer:
        eos_token_id = 0

        def apply_chat_template(self, *_args, **_kwargs):
            return Batch(input_ids=Tensor(), attention_mask=Tensor())

        def decode(self, *_args, **_kwargs):
            return "ready"
    class Model:
        device = "cuda:0"

        def generate(self, **kwargs):
            assert set(kwargs) >= {"input_ids", "attention_mask"}
            return Tensor()
    class InferenceMode:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
    class Torch:
        @staticmethod
        def inference_mode(): return InferenceMode()

    assert server.generate_reply(
        model=Model(), tokenizer=Tokenizer(), torch=Torch(),
        messages=[{"role": "user", "content": "hello"}], max_tokens=128,
    ) == "ready"


def test_generation_rejects_oversized_tokenized_prompt_before_model_call() -> None:
    class Tensor:
        shape = (1, server.MAX_INPUT_TOKENS + 1)

        def to(self, _device): return self
        def __getitem__(self, _item): return self

    class Tokenizer:
        eos_token_id = 0
        def apply_chat_template(self, *_args, **_kwargs): return Tensor()

    class Model:
        device = "cuda:0"
        def generate(self, **_kwargs): raise AssertionError("generation must not run")

    with pytest.raises(ValueError, match="8192-token"):
        server.generate_reply(
            model=Model(), tokenizer=Tokenizer(), torch=object(),
            messages=[{"role": "user", "content": "large"}], max_tokens=128,
        )


def test_exclusive_generation_fails_fast_when_busy_and_releases_after_error(monkeypatch) -> None:
    from threading import Lock

    lock = Lock()
    lock.acquire()
    with pytest.raises(server.GenerationBusyError):
        server.generate_reply_exclusive(generation_lock=lock)
    lock.release()

    def fail(**_kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(server, "generate_reply", fail)
    with pytest.raises(ValueError, match="bad"):
        server.generate_reply_exclusive(generation_lock=lock)
    assert lock.acquire(blocking=False) is True
    lock.release()
