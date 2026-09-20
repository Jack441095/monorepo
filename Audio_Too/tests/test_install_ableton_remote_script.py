"""Tests for scripts/install_ableton_remote_script.py.

Ableton's User Library location isn't fixed to the documented default --
these tests prove the Log.txt auto-detection logic resolves the *real*
configured path (mirroring how the repointed location was found on Jack's
own machine) rather than always falling back to the default, plus the
install/copy behavior itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import install_ableton_remote_script as installer  # noqa: E402


def _write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_detect_user_library_finds_repointed_path(tmp_path) -> None:
    real_library = tmp_path / "CustomDrive" / "User Library"
    real_library.mkdir(parents=True)

    log_file = tmp_path / "Live 12.4.3" / "Log.txt"
    _write_log(
        log_file,
        [
            '2026-07-17T09:24:43: info: Message Box: The file '
            f'"{real_library}/Presets/Instruments/Instrument Rack/folow.adg" already exists.',
            '2026-07-17T10:12:34: info: Message Box: The file '
            f'"{real_library}/Presets/Audio Effects/Audio Effect Rack/thing.adg" already exists.',
        ],
    )

    result = installer.detect_user_library(log_files=[log_file])
    assert result == real_library


def test_detect_user_library_ignores_stale_deleted_paths(tmp_path) -> None:
    # A log entry pointing at a location that no longer exists on disk
    # (e.g. an unplugged drive from months ago) must not win.
    stale_library = tmp_path / "OldDrive" / "User Library"  # never created
    real_library = tmp_path / "CurrentDrive" / "User Library"
    real_library.mkdir(parents=True)

    log_file = tmp_path / "Live 12.4.3" / "Log.txt"
    _write_log(
        log_file,
        [
            f'info: Message Box: The file "{stale_library}/Presets/x.adg" already exists.',
            f'info: Message Box: The file "{real_library}/Presets/y.adg" already exists.',
        ],
    )

    result = installer.detect_user_library(log_files=[log_file])
    assert result == real_library


def test_detect_user_library_prefers_most_recent_log_file(tmp_path) -> None:
    older_library = tmp_path / "Old" / "User Library"
    newer_library = tmp_path / "New" / "User Library"
    older_library.mkdir(parents=True)
    newer_library.mkdir(parents=True)

    older_log = tmp_path / "Live 11.0" / "Log.txt"
    newer_log = tmp_path / "Live 12.4.3" / "Log.txt"
    _write_log(older_log, [f'info: Message Box: The file "{older_library}/x.adg" already exists.'])
    _write_log(newer_log, [f'info: Message Box: The file "{newer_library}/x.adg" already exists.'])

    # Log files list is expected pre-sorted newest-first by the caller
    # (ableton_log_files() sorts by mtime); simulate that ordering directly.
    result = installer.detect_user_library(log_files=[newer_log, older_log])
    assert result == newer_library


def test_detect_user_library_returns_none_when_no_logs(tmp_path) -> None:
    assert installer.detect_user_library(log_files=[]) is None


def test_detect_user_library_returns_none_for_unreadable_logs(tmp_path) -> None:
    log_file = tmp_path / "Live 12.4.3" / "Log.txt"
    _write_log(log_file, ["nothing relevant in here"])
    assert installer.detect_user_library(log_files=[log_file]) is None


def test_install_copies_remote_script_into_remote_scripts_dir(tmp_path) -> None:
    target_library = tmp_path / "User Library"
    target_library.mkdir()

    dest = installer.install(target_library)

    assert dest == target_library / "Remote Scripts" / "AudioToo_Bridge"
    assert (dest / "AudioToo_Bridge.py").is_file()
    assert (dest / "__init__.py").is_file()
    assert not (dest / "__pycache__").exists()


def test_install_dry_run_does_not_copy_anything(tmp_path) -> None:
    target_library = tmp_path / "User Library"
    target_library.mkdir()

    dest = installer.install(target_library, dry_run=True)

    assert not dest.exists()


def test_install_overwrites_existing_install(tmp_path) -> None:
    target_library = tmp_path / "User Library"
    dest = target_library / "Remote Scripts" / "AudioToo_Bridge"
    dest.mkdir(parents=True)
    (dest / "stale_leftover_file.py").write_text("old version", encoding="utf-8")

    installer.install(target_library)

    assert (dest / "AudioToo_Bridge.py").is_file()
    assert not (dest / "stale_leftover_file.py").exists()


def test_main_errors_when_target_dir_does_not_exist(tmp_path, capsys) -> None:
    missing = tmp_path / "does-not-exist"
    rc = installer.main(["--target-dir", str(missing)])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err


def test_main_explicit_target_dir_skips_autodetection(tmp_path, monkeypatch) -> None:
    target_library = tmp_path / "User Library"
    target_library.mkdir()

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("detect_user_library should not run when --target-dir is given")

    monkeypatch.setattr(installer, "detect_user_library", _fail_if_called)

    rc = installer.main(["--target-dir", str(target_library), "--dry-run"])
    assert rc == 0
