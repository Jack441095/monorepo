from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("build_research_cache_from_manifest_embeddings.py")
SPEC = importlib.util.spec_from_file_location("slo_build_research_cache", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"audio")
    digest = MODULE.sha256_file(audio)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "sample_id": 1, "path": str(audio), "sha256": digest,
        "expected_subcategory": "Kick", "ood": False,
    }]), encoding="utf-8")
    embeddings = tmp_path / "embeddings.npz"
    np.savez_compressed(
        embeddings,
        paths=np.asarray([str(audio)], dtype=object),
        embeddings=np.asarray([[1.0] + [0.0] * 511], dtype=np.float32),
        errors=np.asarray([""], dtype=object),
        source_sha256=np.asarray([digest], dtype=object),
        manifest_id=np.asarray([1], dtype=object),
    )
    return manifest, embeddings, audio


def test_build_cache_writes_runner_compatible_embedding(tmp_path: Path):
    manifest, embeddings, _ = _fixture(tmp_path)
    output = tmp_path / "cache.sqlite3"
    receipt = MODULE.build_cache(manifest, embeddings, output)
    assert receipt["rows"] == 1
    with sqlite3.connect(output) as conn:
        row = conn.execute("SELECT path, length(embedding), embedding_status FROM sample_cache").fetchone()
    assert row[1:] == (2048, 1)


def test_build_cache_rejects_error_rows(tmp_path: Path):
    manifest, embeddings, _ = _fixture(tmp_path)
    archive = np.load(embeddings, allow_pickle=True)
    np.savez_compressed(
        embeddings,
        paths=archive["paths"], embeddings=archive["embeddings"],
        errors=np.asarray(["decode failed"], dtype=object),
        source_sha256=archive["source_sha256"], manifest_id=archive["manifest_id"],
    )
    with pytest.raises(ValueError, match="extraction failed"):
        MODULE.build_cache(manifest, embeddings, tmp_path / "cache.sqlite3")
