"""Tests for AudioGen utils/automix_export.py."""

from __future__ import annotations

import json
from utils.automix_export import export_automix_meta


def test_export_automix_meta(tmp_path):
    stem_roles = {
        "kick.wav": "kick",
        "bass.wav": "bass",
        "vocal.wav": "vocal",
    }
    meta_path = export_automix_meta(
        output_dir=tmp_path,
        stem_roles=stem_roles,
        genre="edm",
        target_lufs=-14.0,
        bpm=128.0,
        key="A_minor",
    )

    assert meta_path.exists()
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["genre"] == "edm"
    assert data["target_lufs"] == -14.0
    assert data["bpm"] == 128.0
    assert data["stems"]["kick.wav"] == "kick"
