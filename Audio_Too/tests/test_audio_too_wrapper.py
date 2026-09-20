"""The audio-too shell wrapper must let an explicit AUDIO_TOO_PYTHON override
win over .venv/bin/python, not the other way around (P4 fix, 2026-07-13) --
previously .venv was checked first, so setting AUDIO_TOO_PYTHON to point at
e.g. the native arm64 interpreter was silently ignored whenever a .venv
also happened to exist."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPER_SRC = ROOT / "audio-too"


def _make_sandbox(tmp_path: Path, *, with_venv: bool) -> Path:
    wrapper = tmp_path / "audio-too"
    wrapper.write_text(WRAPPER_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)

    main_py = tmp_path / "main.py"
    main_py.write_text("import sys\nprint(sys.executable)\n", encoding="utf-8")

    if with_venv:
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        # A real, executable (but trivial) interpreter stand-in: a shell
        # script masquerading at the expected path, since the wrapper only
        # checks -x, not that it's actually a Python binary.
        venv_python.write_text(
            f"#!/usr/bin/env bash\nexec {sys.executable} \"$@\"\n", encoding="utf-8"
        )
        venv_python.chmod(venv_python.stat().st_mode | stat.S_IEXEC)

    return wrapper


def _run(wrapper: Path, *, env_overrides: dict) -> str:
    env = os.environ.copy()
    env.update(env_overrides)
    result = subprocess.run(
        [str(wrapper)], capture_output=True, text=True, env=env, cwd=str(wrapper.parent)
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_audio_too_python_env_var_wins_over_existing_venv(tmp_path) -> None:
    wrapper = _make_sandbox(tmp_path, with_venv=True)
    override = tmp_path / "custom_python"
    override.write_text(f"#!/usr/bin/env bash\nexec {sys.executable} \"$@\"\n", encoding="utf-8")
    override.chmod(override.stat().st_mode | stat.S_IEXEC)

    output = _run(wrapper, env_overrides={"AUDIO_TOO_PYTHON": str(override)})

    assert output == sys.executable


def test_falls_back_to_venv_when_no_override_set(tmp_path) -> None:
    wrapper = _make_sandbox(tmp_path, with_venv=True)

    output = _run(wrapper, env_overrides={"AUDIO_TOO_PYTHON": ""})

    assert output == sys.executable  # the .venv stand-in re-execs into this interpreter


def test_falls_back_to_python3_when_no_venv_and_no_override(tmp_path) -> None:
    wrapper = _make_sandbox(tmp_path, with_venv=False)

    output = _run(wrapper, env_overrides={"AUDIO_TOO_PYTHON": ""})

    assert output  # resolved to *some* python3 on PATH and ran successfully
