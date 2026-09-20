"""Stage O1 -- tests for scripts/automix_local.py, the local/offline AutoMix
CLI entry point.

The underlying DSP pipeline (classify/prepare/mask/generate_mix_plan/render/
validate/package) is already extensively tested elsewhere in this codebase
(tests/audio_analysis/*) and exercised for real by
scripts/eval/automix_quality_benchmark.py. These tests mock that pipeline
and instead verify automix_local.py's own logic: stem discovery, argument
handling, and that a delivery-safety failure is reported honestly (matching
_process_job()'s own _require_quality_gate behavior in
business/app/automix_worker.py) rather than silently swallowed or bypassed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import automix_local as cli  # noqa: E402


def _write_stub_wav(path: Path) -> None:
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)


def test_find_stem_files_only_matches_audio_suffixes_and_skips_hidden(tmp_path) -> None:
    (tmp_path / "kick.wav").write_bytes(b"fake")
    (tmp_path / "notes.txt").write_bytes(b"fake")
    (tmp_path / ".hidden.wav").write_bytes(b"fake")
    (tmp_path / "._macos_resource.wav").write_bytes(b"fake")
    (tmp_path / "bass.flac").write_bytes(b"fake")

    found = cli._find_stem_files(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["bass.flac", "kick.wav"]


def test_run_local_automix_raises_on_empty_stems_dir(tmp_path) -> None:
    import pytest
    with pytest.raises(ValueError, match="No audio stems found"):
        cli.run_local_automix(tmp_path, output_dir=tmp_path / "out")


def test_run_local_automix_reports_delivery_safety_failure_honestly(tmp_path) -> None:
    """Matches business/app/automix_worker.py's own _require_quality_gate:
    an unsafe render must raise, not silently degrade or bypass -- the local
    CLI's safety guarantees must be identical to the online job path's."""
    import pytest
    _write_stub_wav(tmp_path / "kick.wav")

    fake_render_result = {
        "quality_gate": {"passed": False, "hard_failures": ["true peak exceeded"]}
    }

    with patch.object(cli, "classify_stems", return_value=[]), \
         patch.object(cli, "prepare_stems", return_value=[]), \
         patch.object(cli, "correct_stem_polarity", return_value=([], {})), \
         patch.object(cli, "analyze_stems_masking", return_value={}), \
         patch.object(cli, "generate_mix_plan", return_value=SimpleNamespace(musical_roles=[])), \
         patch.object(cli, "validate_and_correct_mix", return_value=fake_render_result):
        with pytest.raises(RuntimeError, match="delivery safety gate: true peak exceeded"):
            cli.run_local_automix(tmp_path, output_dir=tmp_path / "out")


def test_run_local_automix_packages_on_success(tmp_path) -> None:
    _write_stub_wav(tmp_path / "kick.wav")

    fake_render_result = {"quality_gate": {"passed": True, "technical_score": 80, "minimum_score": 65}}
    fake_delivery = {"ok": True, "zip_path": str(tmp_path / "out" / "mix_package_v1.zip")}

    with patch.object(cli, "classify_stems", return_value=[]), \
         patch.object(cli, "prepare_stems", return_value=[]), \
         patch.object(cli, "correct_stem_polarity", return_value=([], {})), \
         patch.object(cli, "analyze_stems_masking", return_value={}), \
         patch.object(cli, "generate_mix_plan", return_value=SimpleNamespace(musical_roles=[])), \
         patch.object(cli, "validate_and_correct_mix", return_value=fake_render_result), \
         patch.object(cli, "package_mixdown_delivery", return_value=fake_delivery) as mock_package:
        result = cli.run_local_automix(
            tmp_path, genre="pop", target_lufs=-14.0, output_dir=tmp_path / "out", project_id="test-proj",
        )

    assert result == fake_delivery
    assert mock_package.call_args.kwargs["project_id"] == "test-proj"


def test_main_reports_failure_and_nonzero_exit(tmp_path, capsys) -> None:
    with patch.object(
        cli,
        "run_local_automix",
        side_effect=RuntimeError("Mix failed delivery safety gate: clipping"),
    ):
        with patch.object(sys, "argv", ["automix_local.py", str(tmp_path), "--output", str(tmp_path / "out")]):
            rc = cli.main()
    assert rc == 1
    assert "FAILED: Mix failed delivery safety gate" in capsys.readouterr().out


def test_main_rejects_nonexistent_stems_dir(capsys) -> None:
    with patch.object(sys, "argv", ["automix_local.py", "/no/such/directory"]):
        rc = cli.main()
    assert rc == 1
    assert "is not a directory" in capsys.readouterr().out
