"""Real Demucs inference smoke test -- needs torch/demucs installed and
downloads the htdemucs model (~80MB) on first run. Marked slow: excluded
from the default `pytest` run (see pyproject.toml's marker doc), run
explicitly with `pytest -m slow` inside this package's own venv."""

from __future__ import annotations

import math
import struct
import wave

import pytest

from core import STEM_NAMES, separate


def _write_sine_wav(path, *, seconds: float = 2.0, sr: int = 44100) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        for i in range(int(seconds * sr)):
            value = int(0.3 * 32767 * math.sin(2 * math.pi * 220 * i / sr))
            wav_file.writeframesraw(struct.pack("<hh", value, value))


@pytest.mark.slow
def test_separate_produces_all_four_stems_as_nonempty_wavs(tmp_path):
    input_path = tmp_path / "mix.wav"
    _write_sine_wav(input_path)
    output_dir = tmp_path / "out"

    stem_paths = separate(input_path, output_dir)

    assert set(stem_paths) == set(STEM_NAMES)
    for path_str in stem_paths.values():
        from pathlib import Path

        path = Path(path_str)
        assert path.exists()
        assert path.stat().st_size > 44  # more than just a WAV header
