import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("query_by_example.py")
SPEC = importlib.util.spec_from_file_location("query_by_example", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_rank_excludes_query_and_is_deterministic():
    x = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    first = MODULE.rank_embeddings(x, 0, 2)
    second = MODULE.rank_embeddings(x, 0, 2)
    assert first == second
    assert all(index != 0 for index, _ in first)
    assert first[0][0] == 1


def test_rank_rejects_bad_inputs():
    try:
        MODULE.rank_embeddings(np.ones((2, 2), dtype=np.float32), 4, 2)
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("invalid query index was accepted")


def test_content_dedupe_removes_query_aliases_and_keeps_one_per_hash():
    paths = ["/query.wav", "/alias.wav", "/same.wav", "/distinct.wav"]
    identity = {
        "/query.wav": {"content_sha256": "q"},
        "/alias.wav": {"content_sha256": "q"},
        "/same.wav": {"content_sha256": "s"},
        "/distinct.wav": {"content_sha256": "d"},
    }
    ranked = [(1, 0.99), (2, 0.98), (3, 0.97)]
    result = MODULE.dedupe_ranked_by_content(ranked, paths, identity, identity["/query.wav"], 10)
    assert result == [(2, 0.98), (3, 0.97)]


def test_content_identity_verification_rejects_changed_bytes(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"original")
    identity = {"content_sha256": MODULE._full_sha256(path)}
    assert MODULE.verify_content_identity(path, identity) is True
    path.write_bytes(b"changed")
    try:
        MODULE.verify_content_identity(path, identity)
    except ValueError as exc:
        assert "changed" in str(exc)
    else:
        raise AssertionError("stale content identity was accepted")
