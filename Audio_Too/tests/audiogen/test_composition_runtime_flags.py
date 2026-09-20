"""Unit tests for ``core.composition_runtime_flags``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_markov_style_strength_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    comp.markov_style_strength = 1.8
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import markov_style_strength

    assert markov_style_strength() == 1.0


def test_phrase_length_bars_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    comp.phrase_length_bars = 99
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped

    assert phrase_length_bars_clamped(1, 16) == 16
    assert phrase_length_bars_clamped(2, 8) == 8


def test_stable_emotion_velocity_multiplier(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import stable_emotion_velocity_multiplier

    emotion = MagicMock()
    emotion.velocity_multiplier = 0.75

    comp.stable_emotion_dynamics = True
    assert stable_emotion_velocity_multiplier(emotion) == 1.0

    comp.stable_emotion_dynamics = False
    assert stable_emotion_velocity_multiplier(emotion) == 0.75


def test_melody_position_conditioning(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    comp.melody_position_conditioning_enabled = True
    comp.melody_position_conditioning_strength = 2.0
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import melody_position_conditioning

    on, strength = melody_position_conditioning()
    assert on is True
    assert strength == 1.0


def test_tension_trajectory_params(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    comp.tension_trajectory_enabled = False
    comp.tension_trajectory_strength = -1.0
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import tension_trajectory_params

    enabled, strength = tension_trajectory_params()
    assert enabled is False
    assert strength == 0.0


def test_motif_rhythm_only_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import nite_core.config as config_mod

    comp = MagicMock()
    comp.motif_rhythm_only_enabled = True
    mock_cfg = MagicMock()
    mock_cfg.composition = comp
    monkeypatch.setattr(config_mod, "CONFIG", mock_cfg, raising=False)

    from audiogen_core.composition_runtime_flags import motif_rhythm_only_enabled

    assert motif_rhythm_only_enabled() is True
