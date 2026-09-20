import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("canonical_duplicate_groups.py")
SPEC = importlib.util.spec_from_file_location("canonical_duplicate_groups", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_groups_exact_duplicates_and_deterministic_canonical(tmp_path):
    first = tmp_path / "z.wav"
    second = tmp_path / "a.wav"
    unique = tmp_path / "unique.wav"
    first.write_bytes(b"same-audio")
    second.write_bytes(b"same-audio")
    unique.write_bytes(b"different")

    result = MODULE.group_paths([str(first), str(second), str(unique)])
    assert result["summary"]["n_exact_duplicate_groups"] == 1
    group = result["groups"][0]
    assert group["canonical_path"] == str(second)
    assert group["alias_paths"] == [str(first)]
    assert group["decision"].startswith("never_act")


def test_missing_paths_fail_closed_without_mutation(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"keep")
    missing = tmp_path / "missing.wav"
    result = MODULE.group_paths([str(source), str(missing)])
    assert result["summary"]["n_missing_or_error"] == 1
    assert result["groups"] == []
    assert source.read_bytes() == b"keep"
