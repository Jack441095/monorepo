"""Static checks for GitHub Actions workflow coverage.

CI intentionally does NOT run `python3 main.py setup` / `python3 main.py
check` (the full local gate) -- those pull in macOS/Apple-Silicon-only test
domains (AudioGen DSP under native arm64 numba, KENN-LM/Kokoro TTS under
MLX, real CoreAudio device I/O) that cannot run on a standard ubuntu-latest
runner. A prior version of this workflow did run the full gate and failed on
all 87/87 recorded runs as a result (see docs/CI.md). These assertions check
that CI stays routed through main.py's real per-concern subcommands
(`lint`, `hygiene`, `test`) -- so it can't silently drift from what
`./audio-too lint`/`hygiene`/`test` actually do locally -- while confirming
it does NOT fall back to the unscoped aggregate commands or stale paths from
a previous repo layout.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_ci_uses_authoritative_per_concern_commands() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python-version: \"3.12\"" in ci
    assert "main.py lint" in ci
    assert "main.py hygiene check" in ci
    assert "main.py test " in ci
    assert "pip install -r requirements.txt" in ci

    # The full local gate bundles macOS-only domains (see docs/CI.md) --
    # CI must not silently fall back to it.
    assert "run: python3 main.py setup" not in ci
    assert "run: python3 main.py check" not in ci
    assert "scripts/smoke_check.py" not in ci
    assert "website/server.py" not in ci
    assert "Audio_Tips_LLM" not in ci

    # The domains this workflow deliberately excludes (docs/CI.md has the
    # full reasoning) must actually be named, not just absent -- an
    # unscoped `pytest tests` with no --ignore flags would also pass this
    # substring check for the "not in" assertions above while silently
    # trying (and failing) to run the excluded domains.
    for excluded in (
        "--ignore=tests/audiogen",
        "--ignore=tests/audio_analysis",
        "--ignore=tests/test_latency.py",
        "--ignore=tests/test_finetune_lora_dataset.py",
    ):
        assert excluded in ci
