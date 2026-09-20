"""Security tests for identifiers, storage roots, and ZIP extraction."""

from __future__ import annotations

import io
import stat
import zipfile

import pytest

from archive_safety import extract_zip_safely
from path_safety import safe_child, validate_identifier


@pytest.mark.parametrize("value", ["project_123", "mix-job", "A1", "a" * 64])
def test_validate_identifier_accepts_portable_ids(value: str) -> None:
    assert validate_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    ["", ".hidden", "../escape", "project/child", "project\\child", "a" * 65, "has space"],
)
def test_validate_identifier_rejects_unsafe_ids(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid identifier"):
        validate_identifier(value)


def test_safe_child_rejects_escape(tmp_path) -> None:
    assert safe_child(tmp_path, "project_123").parent == tmp_path.resolve()
    with pytest.raises(ValueError, match="escapes"):
        safe_child(tmp_path, "..", "outside")


def _zip_with_member(name: str, payload: bytes = b"audio") -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)
    buffer.seek(0)
    return zipfile.ZipFile(buffer, "r")


def test_extract_zip_safely_extracts_regular_files(tmp_path) -> None:
    with _zip_with_member("stems/kick.wav") as archive:
        extracted = extract_zip_safely(archive, tmp_path)

    assert extracted == [(tmp_path / "stems" / "kick.wav").resolve()]
    assert extracted[0].read_bytes() == b"audio"


@pytest.mark.parametrize("name", ["../escape.wav", "/absolute.wav", "..\\escape.wav", "C:/drive.wav"])
def test_extract_zip_safely_rejects_traversal(tmp_path, name: str) -> None:
    with _zip_with_member(name) as archive:
        with pytest.raises(ValueError, match="Unsafe ZIP member path"):
            extract_zip_safely(archive, tmp_path)


def test_extract_zip_safely_rejects_symbolic_links(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        member = zipfile.ZipInfo("link.wav")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "target.wav")
    buffer.seek(0)

    with zipfile.ZipFile(buffer, "r") as archive:
        with pytest.raises(ValueError, match="symbolic links"):
            extract_zip_safely(archive, tmp_path)


def test_extract_zip_safely_rejects_duplicate_output_paths(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Stems/Kick.wav", b"first")
        archive.writestr("stems/kick.wav", b"second")
    buffer.seek(0)

    with zipfile.ZipFile(buffer, "r") as archive:
        with pytest.raises(ValueError, match="duplicate output path"):
            extract_zip_safely(archive, tmp_path)
