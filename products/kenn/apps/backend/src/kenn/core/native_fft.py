"""Optional nanobind bridge for KENN's native PCM and DSP kernels.

The module is deliberately optional: a missing or incompatible extension keeps
the pure-Python reference path available. The native path is on by default
when the extension is built; set ``KENN_DSP_NATIVE=0`` to force the reference
implementation for parity tests and rollback. Loudness, mix-review decode and
masking have their own flags on top of this one.
"""

from __future__ import annotations

import os
from typing import Any

_native: Any | None = None
_load_attempted = False


def _load() -> Any | None:
    global _native, _load_attempted
    # Native is the default since 17 Oct 2026. On 26 real files (16/24-bit and
    # float, 11-96 kHz, mono and stereo, ten full mixdowns) the audio analysis
    # matched the Python reference everywhere except one peak bandwidth
    # (70.312 vs 70.313 Hz), and ran 1.4 s against 152.7 s with peak RSS
    # 1.1 GB against 4.6 GB (extension rebuilt from source the same day). That
    # covers analyze_wav, so the audio upload and AudioGen routes, Live session
    # advice and the extra spectral pass in mix review take the native path; the
    # main mix-review report runs local_engine and is unaffected. Mix-review
    # loudness and decode have their own flags, default-on after their own
    # corpus runs the same day (see local_engine); masking is default-on for
    # the Accelerate build only (see masking_band_energy).
    # A missing extension still falls through to the reference below.
    if os.environ.get("KENN_DSP_NATIVE", "1").strip().lower() in {"0", "false", "off", "no"}:
        return None
    if _load_attempted:
        return _native
    _load_attempted = True
    try:
        from . import _kenn_dsp_native
    except (ImportError, OSError):
        _native = None
    else:
        _native = _kenn_dsp_native
    return _native


def available() -> bool:
    """Return whether the optional native backend is loadable and enabled."""
    return _load() is not None


def spectral_powers(
    samples: list[float] | Any,
    fft_size: int,
    sample_rate: int | None = None,
    *,
    include_ltas: bool = False,
) -> dict[str, Any] | None:
    """Compute native Hann-windowed spectra for one contiguous mono buffer.

    The conversion to a C-contiguous float32 NumPy array is explicit so the
    returned ``copied`` flag exposes binding overhead to benchmark receipts.
    ``include_ltas`` asks the native kernel to return the optional 40-band
    levels from the same averaged FFT pass.
    """
    module = _load()
    if module is None:
        return None
    import numpy as np

    source = samples
    values = np.asarray(source, dtype=np.float32, order="C")
    copied = not isinstance(source, np.ndarray) or not np.shares_memory(values, source)
    try:
        result = dict(module.spectral_power(values, int(fft_size), int(sample_rate or 0), bool(include_ltas)))
    except TypeError:
        # Keep compatibility with an older optional wheel that predates the
        # native LTAS output; the Python report path can still calculate it.
        result = dict(module.spectral_power(values, int(fft_size), int(sample_rate or 0)))
    result["copied"] = copied
    result["input_dtype"] = str(values.dtype)
    result["input_contiguous"] = bool(values.flags.c_contiguous)
    return result


def decode_pcm(
    payload: bytes | bytearray | memoryview,
    *,
    allow_8bit: bool = False,
    max_channels: int = 2,
    allow_aiff: bool = False,
    max_frames: int = 0,
) -> dict[str, Any] | None:
    """Decode a PCM/float WAV or AIFF/AIFC payload through the optional native boundary.

    The payload is exposed as a uint8 view so nanobind can parse it without a
    second Python bytes allocation. The returned channel arrays are float32
    and remain contiguous for the downstream native metrics/spectral calls.
    """
    module = _load()
    if module is None or not hasattr(module, "decode_pcm"):
        return None
    import numpy as np

    values = np.frombuffer(payload, dtype=np.uint8)
    try:
        if allow_8bit or max_channels != 2 or allow_aiff or max_frames != 0:
            result = dict(
                module.decode_pcm(
                    values,
                    bool(allow_8bit),
                    int(max_channels),
                    bool(allow_aiff),
                    int(max_frames),
                )
            )
        else:
            result = dict(module.decode_pcm(values))
    except ValueError as exc:
        if "NaN or infinite" in str(exc):
            raise
        # Let the caller produce its stable public error or abstention reason
        # for malformed or unsupported audio containers.
        return None
    except (TypeError, RuntimeError):
        return None
    result["channels"] = [np.asarray(channel, dtype=np.float32, order="C") for channel in result["channels"]]
    result["input_copied"] = False
    return result


_masking_backend_label: str | None = None


def _masking_backend(module: Any) -> str:
    """Return the backend label the loaded module reports for masking, probing once.

    The extension has no build-info export, so we run it on one 4096-sample
    frame of silence (93 ms at 44.1 kHz, about a millisecond) and keep the label.
    """
    global _masking_backend_label
    if _masking_backend_label is None:
        import numpy as np

        try:
            probe = module.masking_band_energy(np.zeros(4096, dtype=np.float32), 44100, 4096, 2048)
            _masking_backend_label = str(dict(probe).get("backend") or "")
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # An extension without a working masking kernel is not one we
            # measured, so it keeps the NumPy default.
            _masking_backend_label = ""
    return _masking_backend_label


def masking_band_energy(
    samples: list[float] | Any,
    sample_rate: int,
    *,
    fft_size: int = 4096,
    hop: int = 2048,
) -> dict[str, Any] | None:
    """Compute native per-frame energy for the stem-masking bands.

    The function is optional for the same reason as :func:`spectral_powers`:
    callers must retain their reference implementation when the extension is
    unavailable or explicitly disabled.
    """
    # Default-on for both Accelerate and portable scalar builds: on 260 real
    # stems (8 songs, 26 groups of up to 12, one arm64 Mac) the masking report
    # was identical to the NumPy reference apart from the implementation label.
    # The portable scalar build now uses a half-length real FFT with precomputed
    # twiddle and Hann tables (1.66 ms vs 3.57 ms per 5 s 48 kHz stem in NumPy).
    # =1 forces native on any build, =0 forces NumPy.
    setting = os.environ.get("KENN_DSP_MASKING_NATIVE", "").strip().lower()
    if setting in {"0", "false", "off", "no"}:
        return None
    module = _load()
    if module is None:
        return None
    import numpy as np

    if setting not in {"1", "true", "on", "yes"} and _masking_backend(module) not in {
        "cpp-accelerate",
        "cpp-scalar",
    }:
        return None

    source = samples
    values = np.asarray(source, dtype=np.float32, order="C")
    copied = not isinstance(source, np.ndarray) or not np.shares_memory(values, source)
    result = dict(module.masking_band_energy(values, int(sample_rate), int(fft_size), int(hop)))
    result["copied"] = copied
    result["input_dtype"] = str(values.dtype)
    result["input_contiguous"] = bool(values.flags.c_contiguous)
    return result


def channel_metrics(channels: list[list[float]] | Any) -> dict[str, Any] | None:
    """Compute bulk channel statistics natively; None when the extension is off or missing."""
    module = _load()
    if module is None:
        return None
    import numpy as np

    values = [np.asarray(channel, dtype=np.float32, order="C") for channel in channels]
    if len(values) == 1:
        function = getattr(module, "mono_metrics", None)
        return None if function is None else dict(function(values[0]))
    if len(values) == 2:
        function = getattr(module, "stereo_metrics", None)
        return None if function is None else dict(function(values[0], values[1]))
    raise ValueError("native channel metrics supports only mono and stereo input")


def loudness_metrics(channels: list[list[float]] | Any, sample_rate: int) -> dict[str, Any] | None:
    """Compute native K-weighted loudness, LRA and 8x true peak; None when unavailable.

    Mirrors pyloudnorm's K-weighting and gating and scipy resample_poly's
    default 8x filter, so rounded output matches the Python fallback.
    """
    module = _load()
    function = None if module is None else getattr(module, "loudness_metrics", None)
    if function is None:
        return None
    import numpy as np

    values = [np.asarray(channel, dtype=np.float32, order="C") for channel in channels]
    if not (1 <= len(values) <= 64):
        raise ValueError("native loudness supports 1..64 channels")
    if any(value.ndim != 1 or value.size == 0 for value in values):
        raise ValueError("native loudness requires non-empty one-dimensional channels")
    if any(value.shape != values[0].shape for value in values[1:]):
        raise ValueError("native loudness requires equal-length channels")
    matrix = np.ascontiguousarray(np.column_stack(values), dtype=np.float32)
    result = dict(function(matrix, int(sample_rate)))
    result["input_copied"] = True
    result["input_dtype"] = str(matrix.dtype)
    return result


def true_peak_dbtp(samples: Any) -> float | None:
    """Compute native 8x oversampled true peak in dBTP for a 1D or 2D (frames, channels) array; None when unavailable."""
    module = _load()
    function = None if module is None else getattr(module, "true_peak_dbtp", None)
    if function is None:
        # An older or disabled extension lacks the standalone true-peak kernel.
        return None
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2 or arr.size == 0:
        return None
    matrix = np.ascontiguousarray(arr, dtype=np.float32)
    result = function(matrix)
    return float(result) if result is not None else None


def loudness_range_lu(short_term: Any) -> float | None:
    """Compute native EBU Tech 3342 gated loudness range (P95 - P10) from short-term LUFS values; None when unavailable."""
    module = _load()
    function = None if module is None else getattr(module, "loudness_range_lu", None)
    if function is None:
        # An older or disabled extension lacks the standalone LRA kernel.
        return None
    import numpy as np

    values = np.ascontiguousarray(short_term, dtype=np.float64)
    if values.ndim != 1 or values.size < 2:
        return None
    result = function(values)
    return float(result) if result is not None else None


def windowed_loudness(
    samples: Any,
    sample_rate: int,
    window_s: float,
    hop_s: float,
) -> list[float] | None:
    """Compute native K-weighted rectangular window LUFS values at the given window and hop seconds; None when unavailable."""
    module = _load()
    function = None if module is None else getattr(module, "windowed_loudness", None)
    if function is None:
        # An older or disabled extension lacks the standalone windowed loudness kernel.
        return None
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2 or arr.size == 0:
        return []
    matrix = np.ascontiguousarray(arr, dtype=np.float32)
    return [float(x) for x in function(matrix, int(sample_rate), float(window_s), float(hop_s))]


def key_tempo_features(samples: Any, sample_rate: int) -> dict[str, Any] | None:
    """Return native mean chroma (index 0 = C) and a tempo estimate for mono audio; None when unavailable.

    ``tempo_bpm`` is None when the audio has fewer than two clear onsets (a
    held tone, a pad, noise, a one-shot) or no beat periodicity, which callers
    should report as an absent BPM, not a zero. Rates outside 8-768 kHz raise ValueError.
    """
    module = _load()
    function = None if module is None else getattr(module, "key_tempo_features", None)
    if function is None:
        return None
    import numpy as np

    values = np.ascontiguousarray(samples, dtype=np.float32)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("native key/tempo needs one non-empty mono channel")
    return dict(function(values, int(sample_rate)))


def track_diagnostic_features(
    channels: list[Any] | Any,
    sample_rate: int,
    band_frequencies_hz: list[float] | tuple[float, ...],
    *,
    time_slices: int = 64,
    waveform_points: int = 300,
) -> dict[str, Any] | None:
    """Return native waveform envelope, Goertzel spectrogram, spectral shape and Welch resonances; None when unavailable.

    Accepts a sequence of 1D per-channel arrays or a 2D ``(frames, channels)``
    array. Silent frames (>60 dB below the loudest frame) are excluded from the
    spectral centroid and flatness means, and pure silence reports ``None`` for
    both rather than 0 Hz and 1.0.
    """
    module = _load()
    function = None if module is None else getattr(module, "track_diagnostic_features", None)
    if function is None:
        return None
    import numpy as np

    if isinstance(channels, np.ndarray) and channels.ndim == 2:
        matrix = np.ascontiguousarray(channels, dtype=np.float32)
    else:
        arrays = [np.asarray(ch, dtype=np.float32) for ch in channels]
        if not arrays or any(arr.ndim != 1 or arr.size == 0 for arr in arrays):
            raise ValueError("native track diagnostic requires non-empty one-dimensional channels")
        if any(arr.shape != arrays[0].shape for arr in arrays[1:]):
            raise ValueError("native track diagnostic requires equal-length channels")
        matrix = np.ascontiguousarray(np.column_stack(arrays), dtype=np.float32)
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("native track diagnostic requires a non-empty (frames, channels) matrix")
    return dict(
        function(
            matrix,
            float(sample_rate),
            [float(f) for f in band_frequencies_hz],
            int(time_slices),
            int(waveform_points),
        )
    )


def erb_spectrum(
    magnitudes: Any,
    sample_rate: int = 44100,
    fft_size: int = 4096,
    num_bands: int = 40,
) -> list[float] | None:
    """Group one-sided FFT magnitudes into discrete Glasberg & Moore ERB band energies; None when unavailable."""
    module = _load()
    function = None if module is None else getattr(module, "erb_spectrum", None)
    if function is None:
        # An older or disabled extension lacks the kernel; let the caller raise or abstain.
        return None
    import numpy as np

    values = np.ascontiguousarray(magnitudes, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("native erb_spectrum requires a one-dimensional magnitude sequence")
    return [float(x) for x in function(values, int(sample_rate), int(fft_size), int(num_bands))]


def resample_mono_window(
    channels: list[Any] | Any,
    sample_rate: int,
    *,
    target_sample_rate: int = 32000,
    target_samples: int = 160000,
) -> Any | None:
    """Fold channels to mono, resample via a Kaiser-windowed polyphase FIR, and pad/truncate to target_samples.

    Returns a 1D float32 NumPy array of length ``target_samples``, or ``None`` when the
    native extension is disabled or predates ``resample_mono_window``.
    """
    module = _load()
    function = None if module is None else getattr(module, "resample_mono_window", None)
    if function is None:
        # An older or disabled extension lacks the kernel; let the caller abstain honestly.
        return None
    import numpy as np

    if isinstance(channels, np.ndarray) and channels.ndim == 2:
        matrix = np.ascontiguousarray(channels, dtype=np.float32)
    elif isinstance(channels, np.ndarray) and channels.ndim == 1:
        if channels.size == 0:
            raise ValueError("native resample_mono_window requires non-empty channels")
        matrix = np.ascontiguousarray(channels.reshape(-1, 1), dtype=np.float32)
    else:
        arrays = [np.asarray(ch, dtype=np.float32) for ch in channels]
        if not arrays or any(arr.ndim != 1 or arr.size == 0 for arr in arrays):
            raise ValueError("native resample_mono_window requires non-empty one-dimensional channels")
        if any(arr.shape != arrays[0].shape for arr in arrays[1:]):
            raise ValueError("native resample_mono_window requires equal-length channels")
        matrix = np.ascontiguousarray(np.column_stack(arrays), dtype=np.float32)
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("native resample_mono_window requires a non-empty (frames, channels) matrix")
    return np.asarray(
        function(matrix, int(sample_rate), int(target_sample_rate), int(target_samples)),
        dtype=np.float32,
        order="C",
    )


__all__ = [
    "available",
    "channel_metrics",
    "decode_pcm",
    "erb_spectrum",
    "key_tempo_features",
    "loudness_metrics",
    "loudness_range_lu",
    "masking_band_energy",
    "resample_mono_window",
    "spectral_powers",
    "track_diagnostic_features",
    "true_peak_dbtp",
    "windowed_loudness",
]
