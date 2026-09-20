from __future__ import annotations

import importlib.util
import json
import wave
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("label_free_zero_shot.py")
SPEC = importlib.util.spec_from_file_location("label_free_zero_shot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _tone(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 1600)


def test_discovery_is_recursive_and_extension_limited(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    _tone(nested / "a.wav")
    _tone(nested / "._a.wav")
    (nested / "ignore.txt").write_text("not audio", encoding="utf-8")
    assert [p.name for p in MODULE.discover_audio(tmp_path)] == ["a.wav"]


def test_custom_prompt_bank_is_validated(tmp_path):
    prompt_file = tmp_path / "prompts.json"
    prompt_file.write_text(json.dumps({"Kick": ["a kick drum"]}), encoding="utf-8")
    assert MODULE._prompt_bank(prompt_file) == {"Kick": ["a kick drum"]}


def test_result_row_is_never_a_label_or_action():
    row = MODULE._row(Path("/tmp/example.wav"), ["Kick", "Snare"],
                      __import__("numpy").array([0.4, 0.1]), 2, 0.15, 0.03,
                      error="fixture failure")
    assert row["semantic_label"] is None
    assert row["status"] == "review"
    assert "rename" not in row


def test_resume_receipt_retries_errors_but_skips_successes(tmp_path):
    receipt = tmp_path / "receipt.jsonl"
    header = {
        "record_type": "slo_label_free_zero_shot_receipt",
        "safety": {"semantic_labels_created": False, "rename_actions": False},
        "device": "cpu",
    }
    success = {"path": str(tmp_path / "ok.wav"), "semantic_label": None}
    error = {"path": str(tmp_path / "retry.wav"), "semantic_label": None,
             "error": "temporary decode failure"}
    receipt.write_text("\n".join(json.dumps(item) for item in (header, success, error)) + "\n",
                       encoding="utf-8")
    _, rows, completed = MODULE._load_resume_receipt(receipt)
    assert len(rows) == 2
    assert completed == {success["path"]}


def test_oversized_audio_is_rejected_before_decode(tmp_path, monkeypatch):
    path = tmp_path / "oversized.wav"
    path.write_bytes(b"fixture")
    monkeypatch.setattr(MODULE, "MAX_FILE_BYTES", 1)
    try:
        MODULE.load_audio(path)
    except ValueError as exc:
        assert "decode safety limit" in str(exc)
    else:
        raise AssertionError("oversized fixture was not rejected")


def test_multiview_row_requires_agreement(tmp_path):
    import numpy as np
    path = tmp_path / "example.wav"
    path.write_bytes(b"fixture")
    row = MODULE._row(path, ["Kick", "Snare"],
                      np.array([0.4, 0.1]), 2, 0.15, 0.03,
                      view_scores=np.array([[0.4, 0.1], [0.35, 0.2], [0.1, 0.3]]),
                      min_view_agreement=0.67)
    assert row["view_count"] == 3
    assert row["view_agreement"] == 2 / 3
    assert row["status"] == "review"


def test_error_paths_can_be_skipped_from_a_prior_receipt(tmp_path):
    receipt = tmp_path / "prior.jsonl"
    header = {"record_type": "slo_label_free_zero_shot_receipt",
              "safety": {"semantic_labels_created": False, "rename_actions": False}}
    bad = {"path": str(tmp_path / "bad.mp3"), "semantic_label": None,
           "error": "decoder failure"}
    receipt.write_text("\n".join(json.dumps(item) for item in (header, bad)) + "\n",
                       encoding="utf-8")
    assert MODULE._load_error_paths(receipt) == {bad["path"]}


def test_multiview_run_emits_every_batch(tmp_path, monkeypatch):
    import numpy as np
    import torch

    paths = []
    for name in ("a.wav", "b.wav", "c.wav"):
        path = tmp_path / name
        path.write_bytes(b"fixture")
        paths.append(path)
    prompt_file = tmp_path / "prompts.json"
    prompt_file.write_text(json.dumps({"Kick": ["kick"], "Snare": ["snare"]}),
                           encoding="utf-8")

    class Box:
        def __init__(self, value):
            self.value = value

        def to(self, _device):
            return self

    class FakeProcessor:
        def __call__(self, *, text=None, audio=None, **kwargs):
            return {"text": Box(text), "n": Box(len(text) if text is not None else len(audio))}

    class FakeModel:
        def get_text_features(self, *, text, n):
            return torch.tensor([[1.0, 0.0] if item == "kick" else [0.0, 1.0]
                                 for item in text.value])

        def get_audio_features(self, *, text, n):
            return torch.tensor([[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0]
                                 for i in range(n.value)])

    monkeypatch.setattr(MODULE, "_load_model", lambda *_: (FakeProcessor(), FakeModel()))
    monkeypatch.setattr(MODULE, "load_audio", lambda _: np.zeros(32, dtype=np.float32))
    out = tmp_path / "out.jsonl"
    header = MODULE.run(tmp_path, tmp_path / "unused-model", out,
                        prompts=prompt_file, device="cpu", batch_size=2, views=3)
    rows = [json.loads(line) for line in out.read_text().splitlines()[1:]]
    assert header["n_files"] == 3
    assert len(rows) == 3
    assert {row["path"] for row in rows} == {str(path.resolve()) for path in paths}
    assert all(row["view_count"] == 3 for row in rows)


def test_embedding_export_is_normalized_and_read_only(tmp_path, monkeypatch):
    import numpy as np
    import torch

    path = tmp_path / "a.wav"
    path.write_bytes(b"fixture")
    prompt_file = tmp_path / "prompts.json"
    prompt_file.write_text(json.dumps({"Kick": ["kick"], "Snare": ["snare"]}), encoding="utf-8")

    class Box:
        def __init__(self, value): self.value = value
        def to(self, _device): return self

    class Processor:
        def __call__(self, *, text=None, audio=None, **kwargs):
            return {"text": Box(text), "n": Box(len(text) if text is not None else len(audio))}

    class Model:
        def get_text_features(self, *, text, n):
            return torch.tensor([[1.0, 0.0] if item == "kick" else [0.0, 1.0] for item in text.value])
        def get_audio_features(self, *, text, n):
            return torch.tensor([[3.0, 4.0] for _ in range(n.value)])

    monkeypatch.setattr(MODULE, "_load_model", lambda *_: (Processor(), Model()))
    monkeypatch.setattr(MODULE, "load_audio", lambda _: np.zeros(32, dtype=np.float32))
    out = tmp_path / "out.jsonl"
    emb_out = tmp_path / "embeddings.npz"
    MODULE.run(tmp_path, tmp_path / "unused-model", out, prompts=prompt_file,
               device="cpu", batch_size=1, embedding_out=emb_out)
    payload = np.load(emb_out, allow_pickle=True)
    assert payload["embeddings"].shape == (1, 2)
    assert np.allclose(np.linalg.norm(payload["embeddings"], axis=1), 1.0)
    assert payload["paths"].tolist() == [str(path.resolve())]
    assert json.loads(str(payload["safety"]))["read_only"] is True


def test_resume_embedding_export_fails_closed_on_existing_rows(tmp_path):
    receipt = tmp_path / "receipt.jsonl"
    header = {"record_type": "slo_label_free_zero_shot_receipt",
              "prompt_bank": {"Kick": ["kick"]},
              "safety": {"read_only": True, "semantic_labels_created": False, "rename_actions": False}}
    row = {"path": str(tmp_path / "a.wav"), "semantic_label": None, "error": None}
    receipt.write_text("\n".join(json.dumps(x) for x in (header, row)) + "\n", encoding="utf-8")
    with __import__("pytest").raises(ValueError, match="resume with embedding_out"):
        MODULE.run(tmp_path, tmp_path / "model", receipt, prompts=None, device="cpu",
                   resume=True, embedding_out=tmp_path / "vectors.npz")
