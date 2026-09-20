import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_content_identity_manifest.py")
SPEC = importlib.util.spec_from_file_location("build_content_identity_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_content_identity_groups_aliases_and_is_read_only(tmp_path):
    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    unique = tmp_path / "c.wav"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    unique.write_bytes(b"different")
    before = {path: path.read_bytes() for path in (first, second, unique)}
    result = MODULE.build_manifest([str(first), str(second), str(unique)])
    assert result["n_hashed"] == 3
    assert result["n_unique_content_ids"] == 2
    assert result["n_duplicate_aliases"] == 1
    assert len(result["duplicate_content_groups"]) == 1
    assert result["safety"]["cache_key_is_complete_file_sha256"] is True
    assert {path: path.read_bytes() for path in (first, second, unique)} == before


def test_missing_file_is_reported_without_aborting(tmp_path):
    result = MODULE.build_manifest([str(tmp_path / "missing.wav")])
    assert result["n_hashed"] == 0
    assert result["n_errors"] == 1


def test_collect_directory_is_audio_only_and_does_not_follow_symlinks(tmp_path):
    audio = tmp_path / "pack" / "Kick.wav"
    text = tmp_path / "pack" / "notes.txt"
    hidden = tmp_path / ".hidden.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    text.write_text("not audio", encoding="utf-8")
    hidden.write_bytes(b"hidden")
    alias = tmp_path / "alias.wav"
    alias.symlink_to(audio)
    assert MODULE.collect(tmp_path) == [str(audio.resolve())]
