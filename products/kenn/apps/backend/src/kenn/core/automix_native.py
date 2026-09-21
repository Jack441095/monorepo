"""Optional nanobind adapters for the recovered AutoMix DSP kernels.

The adapters are deliberately opt-in and return ``None`` when the extension
is disabled or unavailable so callers can retain the audited Python kernels.
"""

from __future__ import annotations

import os
from typing import Any

_native: Any | None = None
_load_attempted = False


def _load() -> Any | None:
    global _native, _load_attempted
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
        _native = getattr(_kenn_dsp_native, "automix", None)
    return _native


def available() -> bool:
    """Return whether the optional AutoMix module is enabled and loadable."""
    return _load() is not None


def _vector(values: Any):
    import numpy as np

    return np.ascontiguousarray(values, dtype=np.float64)


def limiter(values: Any, *, input_gain: float, ceiling_lin: float, alpha_rel: float, lookahead: int) -> dict[str, Any] | None:
    module = _load()
    if module is None:
        return None
    result = dict(module.limiter(_vector(values), float(input_gain), float(ceiling_lin), float(alpha_rel), int(lookahead)))
    return {key: value for key, value in result.items()}


def biquad(sos: Any, values: Any) -> Any | None:
    module = _load()
    if module is None:
        return None
    import numpy as np

    sections = np.ascontiguousarray(sos, dtype=np.float64)
    return module.biquad(sections, _vector(values))


def correlation(left: Any, right: Any, *, max_lag: int) -> dict[str, Any] | None:
    module = _load()
    if module is None:
        return None
    result = dict(module.correlation(_vector(left), _vector(right), int(max_lag)))
    return {key: value for key, value in result.items()}


def smooth(values: Any, *, alpha_att: float, alpha_rel: float, init: float, attack_when_less: bool) -> Any | None:
    module = _load()
    if module is None:
        return None
    return module.smooth(_vector(values), float(alpha_att), float(alpha_rel), float(init), bool(attack_when_less))


def gate(
    levels: Any,
    *,
    threshold: float,
    alpha_att: float,
    alpha_rel: float,
    hold_samples: int,
    target_gain_open: float,
    target_gain_closed: float,
) -> Any | None:
    module = _load()
    if module is None:
        return None
    return module.gate(
        _vector(levels), float(threshold), float(alpha_att), float(alpha_rel), int(hold_samples),
        float(target_gain_open), float(target_gain_closed)
    )


def threshold(flux: Any, *, radius: int, min_floor: float, mad_multiplier: float) -> Any | None:
    module = _load()
    if module is None:
        return None
    return module.threshold(_vector(flux), int(radius), float(min_floor), float(mad_multiplier))


__all__ = ["available", "biquad", "correlation", "gate", "limiter", "smooth", "threshold"]
