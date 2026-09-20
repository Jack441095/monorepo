from __future__ import annotations

import importlib.util
import json
import sqlite3
import struct
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("preflight_research_inputs.py")
SPEC = importlib.util.spec_from_file_location("slo_preflight_research_inputs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    audio = tmp_path / "native-name.wav"
    audio.write_bytes(b"fixture audio")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "filename": "opaque-name.wav",
        "sha256": __import__("hashlib").sha256(audio.read_bytes()).hexdigest(),
        "expected_subcategory": "Kick",
        "vendor_id": "vendor-a",
        "source_family": "family-a",
    }]), encoding="utf-8")
    db = tmp_path / "cache.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sample_cache (path TEXT, embedding BLOB, embedding_status INTEGER)")
        conn.execute(
            "INSERT INTO sample_cache VALUES (?, ?, 1)",
            (str(audio), struct.pack("512f", *([1.0] + [0.0] * 511))),
        )
        conn.commit()
    return manifest, db, audio


def test_preflight_reports_hash_join_and_stays_not_ready_without_ood(tmp_path: Path):
    manifest, db, _ = _fixture(tmp_path)
    receipt = MODULE.preflight(manifest, db)
    assert receipt["matched_manifest_rows"] == 1
    assert receipt["matched_by_content_hash"] == 1
    assert receipt["missing_manifest_rows"] == 0
    assert receipt["ready_for_research_runner"] is False
    assert receipt["safety"]["read_only"] is True


def test_preflight_reports_unmatched_cache_rows(tmp_path: Path):
    manifest, db, audio = _fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sample_cache VALUES (?, ?, 1)",
            (str(tmp_path / "unmatched.wav"), struct.pack("512f", *([1.0] + [0.0] * 511))),
        )
        conn.commit()
    receipt = MODULE.preflight(manifest, db)
    assert receipt["failures"]["unmatched_cache_row"] == 1
    assert receipt["matched_manifest_rows"] == 1
