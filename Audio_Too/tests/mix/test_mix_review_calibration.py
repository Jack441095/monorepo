"""Calibration snapshots for deterministic Mix Review scoring."""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_review import mix_review  # noqa: E402


def tone_wav(
    *,
    frequency: float = 440.0,
    seconds: float = 1.0,
    sample_rate: int = 44100,
    amplitude: float = 0.35,
    channels: int = 2,
    inverted_right: bool = False,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = []
        for index in range(int(seconds * sample_rate)):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * index / sample_rate))
            if channels == 1:
                frames.append(struct.pack("<h", value))
            else:
                right = -value if inverted_right else value
                frames.append(struct.pack("<hh", value, right))
        wav.writeframes(b"".join(frames))
    return buffer.getvalue()


def labels(report: dict) -> set[str]:
    return {str(flag.get("label")) for flag in report.get("flags", [])}


def test_calibration_clean_mid_tone_stays_in_expected_range() -> None:
    report = mix_review.analyze_wav(tone_wav(frequency=440, amplitude=0.28), "calibration-clean.wav")

    assert 70 <= report["metrics"]["technical_score"] <= 100
    assert "Clipping risk" not in labels(report)
    assert "Mono risk" not in labels(report)
    assert report["judgment"]["technical_rating"] in {"Solid with checks", "Clean technical pass"}


def test_calibration_clipped_phase_risk_remains_severe() -> None:
    report = mix_review.analyze_wav(
        tone_wav(frequency=1000, amplitude=1.0, inverted_right=True),
        "calibration-clipped-phase.wav",
    )

    flag_labels = labels(report)
    assert report["metrics"]["technical_score"] <= 65
    assert "Clipping risk" in flag_labels
    assert "Mono risk" in flag_labels
    assert any(action["decision"] == "fix_first" for action in report["action_plan"])

