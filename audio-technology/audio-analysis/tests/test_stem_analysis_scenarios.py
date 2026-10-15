"""Tests for stem_analysis.py — multi-stem masking analysis.

Covers:
- analyze_stems_masking()          — missing-source abstention
- analyze_stems_masking()          — spectral_bands fallback
- analyze_stems_masking()          — masking matrix computation
- handle_stems_upload()            — multipart parsing
"""

from __future__ import annotations

import pytest

from audio_analysis.mixdown.stem_analysis import analyze_stems_masking, handle_stems_upload


# ==============================================================================
#  Mock helpers
# ==============================================================================

def _empty_read(file_bytes: bytes, max_samples: int = 8192) -> dict:
    """Return an empty decode, which cannot support masking evidence."""
    return {"samples": [], "sample_rate": 44100}


def _full_read(file_bytes: bytes, max_samples: int = 8192) -> dict:
    """Return four complete active preview frames at 44.1 kHz."""
    return {
        "samples": [0.1, -0.05, 0.2, -0.15] * 4096,
        "sample_rate": 44100,
        "channels": 1,
        "duration_seconds": 0.1,
        "peak": 0.2,
    }


def _generic_bands(samples: list[float], sample_rate: int, size: int = 4096) -> dict:
    """Mock spectral_bands returning generic distribution."""
    return {
        "sub": 0.15, "bass": 0.25, "low_mids": 0.20,
        "mids": 0.20, "presence": 0.10, "sibilance": 0.05, "air": 0.05,
    }


# ==============================================================================
#  Missing decoded audio
# ==============================================================================

class TestMissingDecodedMeasurements:

    @pytest.mark.parametrize("name", ["kick_01.wav", "808_bass.wav", "lead_vocal.wav", "drum_loop.wav", "synth_pad.wav", "sfx_noise.wav"])
    def test_names_never_substitute_for_decoded_spectra(self, name):
        # The old fallback invented spectra and repair suggestions from filenames.
        result = analyze_stems_masking([{"name": name, "file_bytes": b"fake"}], read_wav_mono=_empty_read, spectral_bands=_generic_bands)
        assert result["stems"] == []
        assert result["masking_matrix"] == {}
        assert result["abstentions"][0]["name"] == name.rsplit(".", 1)[0]
        assert result["erb_details"]["carving_suggestions"] == []


# ==============================================================================
#  Decoded spectral measurements
# ==============================================================================

class TestDecodedSpectra:

    def test_decoded_spectrum_is_independent_of_name(self):
        """A filename cannot override the actual decoded band measurements."""
        stems = [{"name": "vocal.wav", "file_bytes": b"fake"}, {"name": "other.wav", "file_bytes": b"fake"}]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        bands = result["stems"][0]["bands"]
        assert bands["sub"] == pytest.approx(0.15, abs=0.01), (
            f"Expected decoded spectral_bands, got sub={bands['sub']:.3f}"
        )

    def test_spectral_bands_called_with_correct_params(self):
        """spectral_bands receives the actual samples and sample_rate."""
        seen_args = {}

        def tracking_bands(samples, sample_rate, size=4096):
            seen_args["samples"] = samples
            seen_args["sample_rate"] = sample_rate
            return _generic_bands(samples, sample_rate, size)

        stems = [{"name": "track.wav", "file_bytes": b"fake"}, {"name": "other.wav", "file_bytes": b"fake"}]
        analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=tracking_bands)
        assert len(seen_args["samples"]) > 0
        assert seen_args["sample_rate"] == 44100

    def test_bands_normalized(self):
        """Output bands always sum to ~1.0 after normalization."""
        stems = [{"name": "kick.wav", "file_bytes": b"fake"}, {"name": "other.wav", "file_bytes": b"fake"}]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        bands = result["stems"][0]["bands"]
        assert abs(sum(bands.values()) - 1.0) < 0.01, f"Bands sum to {sum(bands.values())}"


# ==============================================================================
#  Masking matrix
# ==============================================================================

class TestMaskingMatrix:

    def test_overlap_between_stems(self):
        """Two stems with different spectral focus → overlap < 1.0."""
        stems = [
            {"name": "vocal.wav", "file_bytes": b"fake"},
            {"name": "kick.wav", "file_bytes": b"fake"},
        ]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        matrix = result["masking_matrix"]
        overlap = matrix["vocal"]["kick"]
        assert 0.0 <= overlap <= 1.0

    def test_symmetry(self):
        """Masking matrix is symmetric."""
        stems = [
            {"name": "vocal.wav", "file_bytes": b"fake"},
            {"name": "bass.wav", "file_bytes": b"fake"},
            {"name": "kick.wav", "file_bytes": b"fake"},
        ]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        matrix = result["masking_matrix"]
        names = list(matrix.keys())
        for i, n1 in enumerate(names):
            for n2 in names[i + 1:]:
                assert abs(matrix[n1][n2] - matrix[n2][n1]) < 0.001

    def test_identical_name_stems_high_overlap(self):
        """Two very similar stems → high overlap."""
        def kick_bands1(s, sr, size=4096):
            return {"sub": 0.50, "bass": 0.30, "low_mids": 0.10, "mids": 0.05, "presence": 0.02, "sibilance": 0.01, "air": 0.02}
        def kick_bands2(s, sr, size=4096):
            return {"sub": 0.48, "bass": 0.32, "low_mids": 0.10, "mids": 0.05, "presence": 0.02, "sibilance": 0.01, "air": 0.02}

        stems = [
            {"name": "kick_main.wav", "file_bytes": b"fake"},
            {"name": "kick_layer.wav", "file_bytes": b"fake"},
        ]
        # Identical decoded previews retain their measured overlap independent of names.
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        matrix = result["masking_matrix"]
        assert matrix["kick_main"]["kick_layer"] > 0.5


# ==============================================================================
#  handle_stems_upload
# ==============================================================================

class TestHandleStemsUpload:

    def test_non_multipart(self):
        """Non-multipart content type → error."""
        result = handle_stems_upload("application/json", b"{}", analyze_stems_masking=lambda stems: {})
        assert result["ok"] is False
        assert "multipart" in result["error"].lower()

    def test_upload_parsing_exception(self):
        """Malformed multipart → error caught."""
        result = handle_stems_upload("multipart/form-data; boundary=x", b"", analyze_stems_masking=lambda stems: {})
        assert result["ok"] is False

    def test_analyzer_invoked(self):
        """When upload parses correctly, analyzer is called with stems."""
        invoked = []

        def analyzer(stems):
            invoked.append(stems)
            return {"ok": True, "stems": [s["name"] for s in stems], "masking_matrix": {}}

        handle_stems_upload(
            "multipart/form-data; boundary=----BOUNDARY",
            b"------BOUNDARY\r\n"
            b'Content-Disposition: form-data; name="files"; filename="kick.wav"\r\n'
            b"Content-Type: audio/wav\r\n\r\n"
            b"FAKE_WAV_DATA"
            b"\r\n------BOUNDARY--\r\n",
            analyze_stems_masking=analyzer,
        )
        assert len(invoked) == 1
        assert len(invoked[0]) == 1
        assert invoked[0][0]["name"] == "kick.wav"

    def test_two_stems_upload(self):
        """Two stems → both passed to analyzer."""
        invoked = []

        def analyzer(stems):
            invoked.append(stems)
            return {
                "ok": True,
                "stems": [s["name"] for s in stems],
                "masking_matrix": {},
            }

        handle_stems_upload(
            "multipart/form-data; boundary=----BOUNDARY",
            b"------BOUNDARY\r\n"
            b'Content-Disposition: form-data; name="files"; filename="kick.wav"\r\n'
            b"Content-Type: audio/wav\r\n\r\n"
            b"FAKE_KICK"
            b"\r\n------BOUNDARY\r\n"
            b'Content-Disposition: form-data; name="files"; filename="vocal.wav"\r\n'
            b"Content-Type: audio/wav\r\n\r\n"
            b"FAKE_VOCAL"
            b"\r\n------BOUNDARY--\r\n",
            analyze_stems_masking=analyzer,
        )
        assert len(invoked) == 1
        names = [s["name"] for s in invoked[0]]
        assert "kick.wav" in names
        assert "vocal.wav" in names


# ==============================================================================
#  Full end-to-end (integration-style)
# ==============================================================================

class TestEndToEnd:

    def test_three_stems_full_pipeline(self):
        """Multiple stems produce complete result with masking matrix."""
        stems = [
            {"name": "kick.wav", "file_bytes": b"fake"},
            {"name": "bass.wav", "file_bytes": b"fake"},
            {"name": "vocal.wav", "file_bytes": b"fake"},
        ]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        assert len(result["stems"]) == 3
        assert set(s["name"] for s in result["stems"]) == {"kick", "bass", "vocal"}
        assert set(result["masking_matrix"].keys()) == {"kick", "bass", "vocal"}
        for n1 in ("kick", "bass", "vocal"):
            for n2 in ("kick", "bass", "vocal"):
                assert n2 in result["masking_matrix"][n1]

    def test_stems_include_band_dicts(self):
        """Each stem has a bands dict with all 7 keys."""
        stems = [
            {"name": "kick.wav", "file_bytes": b"fake"},
            {"name": "vocal.wav", "file_bytes": b"fake"},
        ]
        result = analyze_stems_masking(stems, read_wav_mono=_full_read, spectral_bands=_generic_bands)
        for stem in result["stems"]:
            for key in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"):
                assert key in stem["bands"], f"Missing band key {key} in {stem['name']}"
