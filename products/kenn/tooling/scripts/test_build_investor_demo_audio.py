from __future__ import annotations

import json
import wave
from pathlib import Path

from build_investor_demo_audio import SCHEMA, TRACKS, render_demo_audio


def test_demo_audio_is_deterministic_rights_clear_and_matches_live_tracks(tmp_path: Path) -> None:
    first = render_demo_audio(tmp_path / "first", sample_rate=8000, bars=2, seed=17)
    second = render_demo_audio(tmp_path / "second", sample_rate=8000, bars=2, seed=17)

    assert first["schema"] == SCHEMA
    assert first["rights"]["status"] == "rights-cleared"
    assert first["rights"]["commercial_demo_allowed"] is True
    assert first["ableton_track_order"] == [name for name, _ in TRACKS]
    assert [item["sha256"] for item in first["files"]] == [item["sha256"] for item in second["files"]]
    assert all(item["license"] == "generated-internal" for item in first["files"])

    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["render"]["duration_seconds"] == 4.0
    assert len(manifest["files"]) == 10
    for item in manifest["files"]:
        assert (tmp_path / "first" / item["path"]).is_file()


def test_demo_audio_writes_stereo_pcm_with_exact_duration(tmp_path: Path) -> None:
    render_demo_audio(tmp_path, sample_rate=8000, bars=2, seed=23)

    with wave.open(str(tmp_path / "KENN_Demo_Mix_Analysis.wav"), "rb") as handle:
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        assert handle.getnframes() == 32000
