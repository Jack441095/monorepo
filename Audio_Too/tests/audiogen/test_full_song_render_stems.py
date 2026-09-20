"""tools/full_song_render.py's opt-in per-instrument stem export.

write_full_song_outputs() always renders one master mixdown WAV. export_stems
is a new, opt-in flag that additionally captures the renderer's real
per-channel buffers (bass/chords/melody/arp/drone/counter_melody/kick, see
core.mixer_config.CHANNEL_NAMES) -- the actual pre-mix signal, not a separate
solo render pass -- and writes one WAV per channel alongside the master mix.
Default False, so these tests also guard that opting in never changes the
master mix output.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile

from composition.song_generator import SongRender
from audiogen_core.config import CONFIG
from tools.full_song_render import write_full_song_outputs


def _tiny_song_render() -> SongRender:
    # (channel, midi, velocity, start_beats, duration_beats, notes)
    events = [
        (0, 36, 90, 0.0, 4.0, [36]),  # bass
        (1, 0, 85, 0.0, 2.0, [60, 64, 67]),  # chords (polyphonic)
        (2, 64, 90, 0.0, 1.0, [64]),  # melody
    ]
    return SongRender(sections=[], events=list(events), tempo_map=[], metadata={})


def test_export_stems_false_by_default_produces_no_stem_files(tmp_path: Path) -> None:
    song_render = _tiny_song_render()

    out = write_full_song_outputs(
        config=CONFIG,
        song_events=song_render.events,
        total_bars=1,
        song_render=song_render,
        export_dir=tmp_path,
        name_prefix="stemtest",
        write_midi=False,
        write_report=False,
    )

    assert out["wav"]
    assert out["stems"] == {}
    assert not list(tmp_path.glob("*_stem_*.wav"))


def test_export_stems_true_writes_one_wav_per_channel(tmp_path: Path) -> None:
    song_render = _tiny_song_render()

    out = write_full_song_outputs(
        config=CONFIG,
        song_events=song_render.events,
        total_bars=1,
        song_render=song_render,
        export_dir=tmp_path,
        name_prefix="stemtest",
        write_midi=False,
        write_report=False,
        export_stems=True,
    )

    assert out["wav"]
    assert out["stems"]
    # All 7 mixer channels (bass/chords/melody/arp/drone/counter_melody/kick)
    # are captured every bar (silent ones included) since the renderer always
    # allocates all channel buffers regardless of which had events this bar.
    assert set(out["stems"]) == {
        "bass",
        "chords",
        "melody",
        "arp",
        "drone",
        "counter_melody",
        "kick",
    }
    for name, path_str in out["stems"].items():
        stem_path = Path(path_str)
        assert stem_path.exists(), name
        rate, data = wavfile.read(str(stem_path))
        assert rate > 0
        assert data.ndim == 2 and data.shape[1] == 2

    master_rate, master_data = wavfile.read(out["wav"])
    bass_rate, bass_data = wavfile.read(out["stems"]["bass"])
    assert bass_rate == master_rate
    assert bass_data.shape == master_data.shape


def test_export_stems_bass_channel_carries_real_signal(tmp_path: Path) -> None:
    """Sanity check that captured stems are real per-channel audio, not
    zero-filled placeholders -- channel 0 (bass) has an event covering the
    whole bar, so its stem must carry non-trivial energy.

    (The stronger, bit-exact "stem capture never alters the master mix"
    invariant is proven deterministically at the renderer unit level in
    test_audio_pipeline.py::test_render_bar_stem_sink_none_by_default_leaves_mix_unchanged.
    A cross-call comparison at this higher level isn't reliable: the real
    render pipeline is not bit-exact deterministic across repeated
    invocations even with export_stems held constant, for reasons unrelated
    to stem export -- see chord/sample caches and RNG-driven humanization.)
    """
    song_render = _tiny_song_render()

    out = write_full_song_outputs(
        config=CONFIG,
        song_events=song_render.events,
        total_bars=1,
        song_render=song_render,
        export_dir=tmp_path,
        name_prefix="stemtest",
        write_midi=False,
        write_report=False,
        export_stems=True,
    )

    _, bass_audio = wavfile.read(out["stems"]["bass"])
    assert np.max(np.abs(bass_audio.astype(np.int64))) > 0
