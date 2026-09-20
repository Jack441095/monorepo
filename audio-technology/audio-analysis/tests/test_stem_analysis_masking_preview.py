"""prepare_stems can piggyback analyze_stems_masking's decimated preview onto
its own full-rate decode (masking_preview_max_samples=), so a caller running
both stages only parses each WAV once instead of twice. This must produce
IDENTICAL analyze_stems_masking results to the original independent-re-decode
path, since it changes what audio gets analyzed for real mixing decisions
(masking matrix, EQ carving suggestions) if it's wrong -- not just speed.
"""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from audio_analysis.analysis_core.dsp_metrics import spectral_bands
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
from audio_analysis.mixdown.stem_prep import prepare_stems
from audio_analysis.utils.audio_io import read_wav_mono


def _make_wav(samples: np.ndarray, sample_rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(samples.shape[1])
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _synth_stem(name: str, seed: int, seconds: float, sample_rate: int = 44100) -> dict:
    rng = np.random.default_rng(seed)
    n = int(sample_rate * seconds)
    t = np.arange(n) / sample_rate
    freqs = {"kick": (60, 120), "bass": (80, 300), "vocal": (300, 3000), "hat": (4000, 12000)}
    lo, hi = next((v for k, v in freqs.items() if k in name), (200, 4000))
    tone = 0.3 * np.sin(2 * np.pi * rng.uniform(lo, hi) * t)
    noise = 0.05 * rng.standard_normal(n)
    mono = tone + noise
    stereo = np.stack([mono, mono * 0.95], axis=1)
    return {"name": name, "file_bytes": _make_wav(stereo, sample_rate)}


@pytest.fixture
def stems_raw() -> list[dict]:
    return [
        _synth_stem("kick.wav", 1, 3.0),
        _synth_stem("bass.wav", 2, 3.0),
        _synth_stem("vocal.wav", 3, 3.0),
        _synth_stem("hat.wav", 4, 3.0),
    ]


def _independent_decode_result(stems_raw: list[dict]) -> dict:
    return analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)


def _piggybacked_result(stems_raw: list[dict]) -> dict:
    prepared = prepare_stems(
        stems_raw, read_wav_mono_fn=read_wav_mono, target_sample_rate=44100,
        trim=True, normalise=False, max_samples=0, masking_preview_max_samples=65536,
    )
    preview_by_name = {
        s["name"]: (s.get("masking_preview_samples"), s.get("masking_preview_sample_rate"))
        for s in prepared
    }
    annotated = [dict(s) for s in stems_raw]
    for s in annotated:
        preview = preview_by_name.get(s["name"])
        if preview and preview[0] is not None:
            s["masking_preview_samples"], s["masking_preview_sample_rate"] = preview
    return analyze_stems_masking(annotated, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)


def _assert_identical(independent: dict, piggybacked: dict) -> None:
    assert independent["masking_matrix"] == piggybacked["masking_matrix"]
    assert independent["erb_details"] == piggybacked["erb_details"]

    i_stems = {s["name"]: s for s in independent["stems"]}
    p_stems = {s["name"]: s for s in piggybacked["stems"]}
    assert set(i_stems) == set(p_stems)
    for name in i_stems:
        assert i_stems[name] == p_stems[name], f"[{name}] stem entry mismatch"


def test_piggybacked_preview_matches_independent_redecode(stems_raw: list[dict]) -> None:
    _assert_identical(_independent_decode_result(stems_raw), _piggybacked_result(stems_raw))


def test_piggyback_falls_back_cleanly_when_preview_absent(stems_raw: list[dict]) -> None:
    """A caller that never ran prepare_stems (e.g. a standalone masking-only
    endpoint) must get byte-for-byte today's behavior -- the precomputed-
    preview lookup only activates when the key is actually present."""
    result = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)
    names = {s["name"] for s in result["stems"]}
    assert names == {"kick", "bass", "vocal", "hat"}  # extension stripped internally
    for entry in result["stems"]:
        assert "bands" in entry and "overall_visibility" in entry


def test_piggyback_matches_on_mixed_short_stem_lengths() -> None:
    """A stem shorter than one frame_size*num_frames window exercises
    analyze_stems_masking's fallback single-pass branch -- must still match.
    Include a second longer stem: the ERB simulation must safely reuse the
    shorter stem's last frame rather than indexing past it."""
    stems_raw = [_synth_stem("kick.wav", 10, 0.2), _synth_stem("bass.wav", 5000, 0.15)]
    _assert_identical(_independent_decode_result(stems_raw), _piggybacked_result(stems_raw))
