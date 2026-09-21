"""Optional nanobind bridge for KENN's native PCM and DSP kernels.

The module is deliberately optional: a missing or incompatible extension keeps
the pure-Python reference path available. Set ``KENN_DSP_NATIVE=1`` to enable
the native candidate explicitly, or ``KENN_DSP_NATIVE=0`` to force the
reference implementation for parity tests and rollback.
"""

from __future__ import annotations

import os
from typing import Any

_native: Any | None = None
_load_attempted = False


def _load() -> Any | None:
    global _native, _load_attempted
    # Keep the measured Python/NumPy reference as the release default. Native
    # candidates are enabled explicitly during qualification or benchmarking.
    if os.environ.get("KENN_DSP_NATIVE", "0").strip().lower() in {"0", "false", "off", "no"}:
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


def decode_pcm(payload: bytes | bytearray | memoryview) -> dict[str, Any] | None:
    """Decode a PCM WAV payload through the optional native boundary.

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
        result = dict(module.decode_pcm(values))
    except (TypeError, ValueError, RuntimeError):
        # Let the audited Python parser produce the stable public error for
        # malformed or unsupported WAV payloads.
        return None
    result["channels"] = [np.asarray(channel, dtype=np.float32, order="C") for channel in result["channels"]]
    result["input_copied"] = False
    return result


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
    # The Apple Accelerate build is faster than the NumPy reference on the
    # qualification host, while the portable scalar build is not. Keep this
    # path explicitly opt-in so installing the native spectral wheel cannot
    # change stem-masking behavior without a measured backend choice.
    if os.environ.get("KENN_DSP_MASKING_NATIVE", "0").strip().lower() not in {"1", "true", "on", "yes"}:
        return None
    module = _load()
    if module is None:
        return None
    import numpy as np

    source = samples
    values = np.asarray(source, dtype=np.float32, order="C")
    copied = not isinstance(source, np.ndarray) or not np.shares_memory(values, source)
    result = dict(module.masking_band_energy(values, int(sample_rate), int(fft_size), int(hop)))
    result["copied"] = copied
    result["input_dtype"] = str(values.dtype)
    result["input_contiguous"] = bool(values.flags.c_contiguous)
    return result


def channel_metrics(channels: list[list[float]] | Any) -> dict[str, Any] | None:
    """Compute bulk channel statistics through the opt-in native boundary."""
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
    """Compute an opt-in native K-weighted loudness/LRA candidate.

    The native candidate mirrors pyloudnorm's default K-weighting, gating, and
    4x true-peak FIR contract. Callers must compare rounded LUFS/LRA/true-peak
    output before promoting it.
    """
    module = _load()
    function = None if module is None else getattr(module, "loudness_metrics", None)
    if function is None:
        return None
    import numpy as np

    values = [np.asarray(channel, dtype=np.float32, order="C") for channel in channels]
    if len(values) not in (1, 2):
        raise ValueError("native loudness supports only mono and stereo input")
    if any(value.ndim != 1 or value.size == 0 for value in values):
        raise ValueError("native loudness requires non-empty one-dimensional channels")
    if any(value.shape != values[0].shape for value in values[1:]):
        raise ValueError("native loudness requires equal-length channels")
    matrix = np.ascontiguousarray(np.column_stack(values), dtype=np.float32)
    result = dict(function(matrix, int(sample_rate)))
    result["input_copied"] = True
    result["input_dtype"] = str(matrix.dtype)
    return result


__all__ = [
    "available",
    "channel_metrics",
    "decode_pcm",
    "loudness_metrics",
    "masking_band_energy",
    "spectral_powers",
]
