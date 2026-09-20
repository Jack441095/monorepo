from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("extract_manifest_panns_embeddings.py")
SPEC = importlib.util.spec_from_file_location("slo_extract_manifest_panns_embeddings", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_load_audio_normalizes_to_runtime_shape(tmp_path: Path):
    sf = pytest.importorskip("soundfile")
    import numpy as np

    audio = tmp_path / "short.wav"
    sf.write(audio, np.zeros(800, dtype=np.float32), 16000)
    result = MODULE.load_audio(audio)
    assert result.shape == (MODULE.TARGET_FRAMES,)
    assert result.dtype == np.float32


def test_sha256_file_is_stable(tmp_path: Path):
    path = tmp_path / "bytes.bin"
    path.write_bytes(b"identity")
    assert MODULE.sha256_file(path) == MODULE.sha256_file(path)


def test_manifest_loader_rejects_non_list(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"rows": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty JSON list"):
        MODULE.load_manifest(path)
