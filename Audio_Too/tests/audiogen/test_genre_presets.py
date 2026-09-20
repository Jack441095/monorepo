"""Unit tests for AudioGen Genre Preset Generator Library."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIOGEN_DIR = ROOT / "studio" / "audiogen"
if str(AUDIOGEN_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIOGEN_DIR))

import pytest
from audiogen.presets.genre_presets import get_genre_preset, list_genre_presets, GENRE_PRESETS


def test_list_genre_presets():
    presets = list_genre_presets()
    assert "cyberpunk" in presets
    assert "synthwave" in presets
    assert "lofi_hiphop" in presets
    assert "cinematic_trailer" in presets
    assert "deep_house" in presets
    assert "acoustic_folk" in presets
    assert len(presets) >= 6


def test_get_genre_preset_valid():
    p = get_genre_preset("Cyberpunk")
    assert p.name == "cyberpunk"
    assert p.macros["energy"] == 0.95
    assert p.metadata["genre"] == "Cyberpunk"


def test_get_genre_preset_fallback():
    p = get_genre_preset("unknown_genre_xyz")
    assert p.name == "synthwave"
