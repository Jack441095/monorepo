"""Regression tests for runtime phrase-length alignment in harmony modules."""

from __future__ import annotations

from pathlib import Path
from types import MethodType

import pytest


def test_chord_planner_uses_runtime_phrase_length(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod
    from composition.engine import CompositionGenerator
    from data.music_data import EMOTION_BY_NAME

    emotion = EMOTION_BY_NAME.get("neutral")
    assert emotion is not None

    # Force a non-default phrase length so we can detect propagation.
    monkeypatch.setattr(config_mod.CONFIG.composition, "phrase_length_bars", 6, raising=False)

    gen = CompositionGenerator(enable_perf_monitoring=False)
    planner = gen.chord_planner
    seen_phrase_lengths: list[int] = []

    def _sample_next(self, *args, **kwargs):  # noqa: ANN001
        # Positional shape:
        # context, simplified_vocab, history, temperature, repeat_penalty, bar_in_phrase, phrase_length, ...
        seen_phrase_lengths.append(int(args[6]))
        vocab = list(args[1] or [])
        return str(vocab[0]) if vocab else "maj"

    monkeypatch.setattr(
        planner,
        "sample_next_simplified_chord",
        MethodType(_sample_next, planner),
        raising=True,
    )

    chords, roots = planner.generate_chord_progression(
        emotion=emotion,
        root_note=60,
        bars=8,
        temperature=0.8,
        section_role="a",
    )
    assert chords
    assert roots
    assert seen_phrase_lengths
    assert all(v == 6 for v in seen_phrase_lengths)


def test_no_hardcoded_phrase_length_literals_in_key_modules() -> None:
    root = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"
    # chord_planner.py was split 2026-07-14 into chord_planner.py (class assembly)
    # plus chord_planner_bias.py/_weighting.py/_sampling.py/_progression.py mixins
    # (docs/codebase_scan_12_07.md decomposition pass). Glob so this guard still
    # covers the actual generation logic wherever it lives, instead of silently
    # checking only the now-mostly-empty top-level file.
    files = [
        *sorted((root / "composition").glob("chord_planner*.py")),
        root / "composition" / "voice_leading_engine.py",
        root / "composition" / "arpeggiator_engine.py",
    ]
    assert len(files) >= 3
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "phrase_length=4" not in content
        assert "phrase_length = 4" not in content
