"""CLI contract tests that don't require torch/demucs installed -- only the
argument-parsing and error-reporting paths, which never reach separate()."""

from __future__ import annotations

import json

import main_separate
from core import STEM_NAMES


def test_stem_names_is_the_standard_four_stem_set():
    assert STEM_NAMES == ("drums", "bass", "vocals", "other")


def test_missing_input_file_reports_a_json_error_and_exits_nonzero(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.wav"
    exit_code = main_separate.main(["--input", str(missing), "--output-dir", str(tmp_path / "out")])

    assert exit_code == 1
    last_line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["ok"] is False
    assert "not found" in payload["error"].lower()


def test_separate_failure_is_reported_as_json_not_raised(tmp_path, monkeypatch, capsys):
    """Locks in the CLI's error contract: separate() raising must become a
    JSON {"ok": false} line + exit code 1, never an uncaught traceback --
    the bridge parsing the last stdout line depends on this."""
    real_input = tmp_path / "in.wav"
    real_input.write_bytes(b"not a real wav, just needs to exist")

    def boom(*args, **kwargs):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(main_separate, "separate", boom)
    exit_code = main_separate.main(["--input", str(real_input), "--output-dir", str(tmp_path / "out")])

    assert exit_code == 1
    last_line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload == {"ok": False, "error": "model exploded"}


def test_missing_stems_from_the_model_is_reported_as_json_error(tmp_path, monkeypatch, capsys):
    real_input = tmp_path / "in.wav"
    real_input.write_bytes(b"placeholder")

    monkeypatch.setattr(main_separate, "separate", lambda *a, **k: {"drums": "d.wav", "bass": "b.wav"})
    exit_code = main_separate.main(["--input", str(real_input), "--output-dir", str(tmp_path / "out")])

    assert exit_code == 1
    last_line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["ok"] is False
    assert "vocals" in payload["error"] and "other" in payload["error"]
