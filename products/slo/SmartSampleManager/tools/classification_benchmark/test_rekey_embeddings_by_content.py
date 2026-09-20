import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("rekey_embeddings_by_content.py")
SPEC = importlib.util.spec_from_file_location("rekey_embeddings_by_content", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_rekeys_alias_paths_to_one_content_record():
    paths = ["/b.wav", "/a.wav", "/c.wav"]
    identity = {"rows": [
        {"path": "/a.wav", "content_sha256": "a" * 64, "size_bytes": 4},
        {"path": "/b.wav", "content_sha256": "a" * 64, "size_bytes": 4},
        {"path": "/c.wav", "content_sha256": "b" * 64, "size_bytes": 5},
    ]}
    result = MODULE.build_index(paths, identity, "test", 4)
    assert result["n_embedding_rows"] == 3
    assert result["n_content_ids"] == 2
    assert result["n_alias_paths"] == 1
    alias = next(row for row in result["records"] if row["alias_count"] == 1)
    assert alias["canonical_path"] == "/a.wav"
    assert result["safety"]["embedding_values_modified"] is False


def test_identity_mismatch_fails_closed():
    try:
        MODULE.build_index(["/a.wav"], {"rows": []}, "test", 4)
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("path/identity mismatch was accepted")
