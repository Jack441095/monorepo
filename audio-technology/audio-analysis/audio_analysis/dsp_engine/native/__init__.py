"""Native (C++) compute kernels for the DSP core.

These are optional accelerators: the pure-Python/numpy processors in
``dsp_engine/streaming.py`` (``StreamingLimiter``) and ``dsp_engine/dynamics.py``
(``Limiter.apply()``, both true_peak modes) are the reference and always work.
A native kernel is built on demand with the system C++ compiler (matching the
running Python's architecture) and loaded via ctypes. If no compiler is
available the loader returns ``None`` and callers fall back to Python —
nothing here is required.

The compiled ``.dylib``/``.so`` is a platform/arch-specific build artifact and
is git-ignored; only the ``.cpp`` source and this loader are tracked.
"""

from __future__ import annotations

import ctypes
import platform
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "limiter_kernel.cpp"


def _lib_path() -> Path:
    # Arch in the name so an x86_64 (Rosetta) and an arm64 build can coexist.
    return _HERE / f"limiter_kernel.{platform.machine()}.dylib"


def build_kernel(force: bool = False) -> Path | None:
    """Compile the C++ kernel to a shared lib matching this Python's arch.

    Returns the library path, or ``None`` if compilation is unavailable/failed.
    Idempotent: skips the build if an up-to-date lib already exists."""
    lib = _lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_SRC)]
    if sys.platform == "darwin":
        # The dylib must match the interpreter's architecture (the project venv
        # is x86_64 under Rosetta on Apple Silicon — see requirements.txt notes).
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


_lib = None
_fn = None


def _load():
    global _lib, _fn
    if _fn is not None:
        return _fn
    path = build_kernel()
    if path is None:
        return None
    _lib = ctypes.CDLL(str(path))
    fn = _lib.limiter_gain_envelope
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # x
        ctypes.c_size_t,                  # n
        ctypes.c_double,                  # input_gain
        ctypes.c_double,                  # ceiling_lin
        ctypes.c_double,                  # alpha_rel
        ctypes.c_int,                     # L
        ctypes.POINTER(ctypes.c_double),  # gain_out
        ctypes.POINTER(ctypes.c_double),  # audio_out
    ]
    _fn = fn
    return _fn


def is_available() -> bool:
    """True if the native limiter kernel could be built and loaded here."""
    return _load() is not None


def limiter_gain_envelope(x, input_gain: float, ceiling_lin: float,
                          alpha_rel: float, lookahead_samples: int):
    """Native compute of the limiter gain envelope + limited output.

    Returns ``(gain, audio)`` as numpy float64 arrays, bit-identical to the
    Python ``StreamingLimiter`` / offline ``Limiter`` (either true_peak mode
    — pass the already-upsampled signal and input_gain=1.0 for true_peak=True,
    since Limiter.apply() applies input_gain before upsampling). Raises
    ``RuntimeError`` if the native kernel is unavailable — call
    :func:`is_available` first, or use the Python path.
    """
    import numpy as np

    fn = _load()
    if fn is None:
        raise RuntimeError("native limiter kernel unavailable (no C++ compiler?)")
    xa = np.ascontiguousarray(x, dtype=np.float64)
    n = xa.shape[0]
    gain = np.empty(n, dtype=np.float64)
    audio = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    fn(xa.ctypes.data_as(dbl), ctypes.c_size_t(n),
       ctypes.c_double(input_gain), ctypes.c_double(ceiling_lin),
       ctypes.c_double(alpha_rel), ctypes.c_int(int(lookahead_samples)),
       gain.ctypes.data_as(dbl), audio.ctypes.data_as(dbl))
    return gain, audio


_EQ_SRC = _HERE / "eq_kernel.cpp"
_eq_lib = None
_eq_fn = None


def _eq_lib_path() -> Path:
    return _HERE / f"eq_kernel.{platform.machine()}.dylib"


def build_eq_kernel(force: bool = False) -> Path | None:
    lib = _eq_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _EQ_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_EQ_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_eq():
    global _eq_lib, _eq_fn
    if _eq_fn is not None:
        return _eq_fn
    path = build_eq_kernel()
    if path is None:
        return None
    _eq_lib = ctypes.CDLL(str(path))
    fn = _eq_lib.biquad_sos_filter
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # sos
        ctypes.c_size_t,                  # n_sections
        ctypes.POINTER(ctypes.c_double),  # x
        ctypes.c_size_t,                  # n_samples
        ctypes.POINTER(ctypes.c_double),  # y_out
    ]
    _eq_fn = fn
    return _eq_fn


def is_eq_available() -> bool:
    """True if the native eq kernel could be built and loaded here."""
    return _load_eq() is not None


def biquad_sos_filter(sos, x):
    """Native compute of cascaded biquad (Second-Order Sections) filter."""
    import numpy as np

    fn = _load_eq()
    if fn is None:
        raise RuntimeError("native eq kernel unavailable (no C++ compiler?)")
    sos_arr = np.ascontiguousarray(sos, dtype=np.float64)
    x_arr = np.ascontiguousarray(x, dtype=np.float64)
    n_sections = sos_arr.shape[0]
    n_samples = x_arr.shape[0]
    y_out = np.empty(n_samples, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    fn(sos_arr.ctypes.data_as(dbl), ctypes.c_size_t(n_sections),
       x_arr.ctypes.data_as(dbl), ctypes.c_size_t(n_samples),
       y_out.ctypes.data_as(dbl))
    return y_out


_REVERB_SRC = _HERE / "reverb_kernel.cpp"
_reverb_lib = None
_comb_fn = None
_allpass_fn = None


def _reverb_lib_path() -> Path:
    return _HERE / f"reverb_kernel.{platform.machine()}.dylib"


def build_reverb_kernel(force: bool = False) -> Path | None:
    lib = _reverb_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _REVERB_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_REVERB_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_reverb():
    global _reverb_lib, _comb_fn, _allpass_fn
    if _comb_fn is not None and _allpass_fn is not None:
        return _comb_fn, _allpass_fn
    path = build_reverb_kernel()
    if path is None:
        return None, None
    _reverb_lib = ctypes.CDLL(str(path))

    comb_fn = _reverb_lib.lbcf_comb_filter
    comb_fn.restype = None
    comb_fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # x
        ctypes.c_size_t,                  # n
        ctypes.c_int,                     # d
        ctypes.c_double,                  # g
        ctypes.c_double,                  # damping
        ctypes.POINTER(ctypes.c_double),  # y_out
    ]

    allpass_fn = _reverb_lib.allpass_filter
    allpass_fn.restype = None
    allpass_fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # x
        ctypes.c_size_t,                  # n
        ctypes.c_int,                     # d
        ctypes.c_double,                  # g
        ctypes.POINTER(ctypes.c_double),  # y_out
    ]

    _comb_fn, _allpass_fn = comb_fn, allpass_fn
    return _comb_fn, _allpass_fn


def is_reverb_available() -> bool:
    """True if the native reverb kernel could be built and loaded here."""
    cf, af = _load_reverb()
    return cf is not None and af is not None


def native_lbcf_comb_filter(x, d: int, g: float, damping: float):
    import numpy as np
    comb_fn, _ = _load_reverb()
    if comb_fn is None:
        raise RuntimeError("native reverb kernel unavailable")
    xa = np.ascontiguousarray(x, dtype=np.float64)
    n = xa.shape[0]
    y_out = np.zeros(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    comb_fn(xa.ctypes.data_as(dbl), ctypes.c_size_t(n), ctypes.c_int(d),
            ctypes.c_double(g), ctypes.c_double(damping), y_out.ctypes.data_as(dbl))
    return y_out


def native_allpass_filter(x, d: int, g: float):
    import numpy as np
    _, allpass_fn = _load_reverb()
    if allpass_fn is None:
        raise RuntimeError("native reverb kernel unavailable")
    xa = np.ascontiguousarray(x, dtype=np.float64)
    n = xa.shape[0]
    y_out = np.zeros(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    allpass_fn(xa.ctypes.data_as(dbl), ctypes.c_size_t(n), ctypes.c_int(d),
               ctypes.c_double(g), y_out.ctypes.data_as(dbl))
    return y_out


_SMOOTH_SRC = _HERE / "smooth_envelope_kernel.cpp"
_smooth_lib = None
_smooth_fn = None
_gate_fn = None


def _smooth_lib_path() -> Path:
    return _HERE / f"smooth_envelope_kernel.{platform.machine()}.dylib"


def build_smooth_envelope_kernel(force: bool = False) -> Path | None:
    lib = _smooth_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _SMOOTH_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_SMOOTH_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_smooth_envelope():
    global _smooth_lib, _smooth_fn, _gate_fn
    if _smooth_fn is not None and _gate_fn is not None:
        return _smooth_fn, _gate_fn
    path = build_smooth_envelope_kernel()
    if path is None:
        return None, None
    _smooth_lib = ctypes.CDLL(str(path))

    smooth_fn = _smooth_lib.smooth_attack_release
    smooth_fn.restype = None
    smooth_fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # values
        ctypes.c_size_t,                  # n
        ctypes.c_double,                  # alpha_att
        ctypes.c_double,                  # alpha_rel
        ctypes.c_double,                  # init
        ctypes.c_bool,                    # attack_when_less
        ctypes.POINTER(ctypes.c_double),  # out
    ]

    gate_fn = _smooth_lib.gate_envelope
    gate_fn.restype = None
    gate_fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # level_db
        ctypes.c_size_t,                  # n
        ctypes.c_double,                  # threshold
        ctypes.c_double,                  # alpha_att
        ctypes.c_double,                  # alpha_rel
        ctypes.c_int,                     # hold_samples
        ctypes.c_double,                  # target_gain_open
        ctypes.c_double,                  # target_gain_closed
        ctypes.POINTER(ctypes.c_double),  # g_out
    ]

    _smooth_fn, _gate_fn = smooth_fn, gate_fn
    return _smooth_fn, _gate_fn


def is_smooth_envelope_available() -> bool:
    s_fn, g_fn = _load_smooth_envelope()
    return s_fn is not None and g_fn is not None


def native_smooth_attack_release(values, alpha_att: float, alpha_rel: float, init: float, attack_when_less: bool):
    import numpy as np
    s_fn, _ = _load_smooth_envelope()
    if s_fn is None:
        raise RuntimeError("native smooth envelope kernel unavailable")
    va = np.ascontiguousarray(values, dtype=np.float64)
    n = va.shape[0]
    out = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    s_fn(va.ctypes.data_as(dbl), ctypes.c_size_t(n),
         ctypes.c_double(alpha_att), ctypes.c_double(alpha_rel),
         ctypes.c_double(init), ctypes.c_bool(attack_when_less),
         out.ctypes.data_as(dbl))
    return out


def native_gate_envelope(level_db, threshold: float, alpha_att: float, alpha_rel: float, hold_samples: int, target_gain_open: float, target_gain_closed: float):
    import numpy as np
    _, g_fn = _load_smooth_envelope()
    if g_fn is None:
        raise RuntimeError("native gate envelope kernel unavailable")
    la = np.ascontiguousarray(level_db, dtype=np.float64)
    n = la.shape[0]
    g_out = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    g_fn(la.ctypes.data_as(dbl), ctypes.c_size_t(n),
         ctypes.c_double(threshold), ctypes.c_double(alpha_att),
         ctypes.c_double(alpha_rel), ctypes.c_int(int(hold_samples)),
         ctypes.c_double(target_gain_open), ctypes.c_double(target_gain_closed),
         g_out.ctypes.data_as(dbl))
    return g_out


_REVERB_FULL_SRC = _HERE / "reverb_full_kernel.cpp"
_reverb_full_lib = None
_schroeder_fn = None


def _reverb_full_lib_path() -> Path:
    return _HERE / f"reverb_full_kernel.{platform.machine()}.dylib"


def build_reverb_full_kernel(force: bool = False) -> Path | None:
    lib = _reverb_full_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _REVERB_FULL_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_REVERB_FULL_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_reverb_full():
    global _reverb_full_lib, _schroeder_fn
    if _schroeder_fn is not None:
        return _schroeder_fn
    path = build_reverb_full_kernel()
    if path is None:
        return None
    _reverb_full_lib = ctypes.CDLL(str(path))

    fn = _reverb_full_lib.schroeder_reverb
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # left
        ctypes.POINTER(ctypes.c_double),  # right
        ctypes.c_size_t,                  # n
        ctypes.c_int,                     # pre_delay_samples
        ctypes.c_double,                  # room_size
        ctypes.c_double,                  # decay_time
        ctypes.c_double,                  # damping
        ctypes.c_double,                  # wet_dry
        ctypes.c_double,                  # sample_rate
        ctypes.POINTER(ctypes.c_double),  # out_l
        ctypes.POINTER(ctypes.c_double),  # out_r
    ]
    _schroeder_fn = fn
    return _schroeder_fn


def is_reverb_full_available() -> bool:
    return _load_reverb_full() is not None


def native_schroeder_reverb(left, right, pre_delay_samples: int, room_size: float, decay_time: float, damping: float, wet_dry: float, sample_rate: float):
    import numpy as np
    fn = _load_reverb_full()
    if fn is None:
        raise RuntimeError("native full reverb kernel unavailable")
    la = np.ascontiguousarray(left, dtype=np.float64)
    ra = np.ascontiguousarray(right if right is not None else left, dtype=np.float64)
    n = la.shape[0]
    out_l = np.empty(n, dtype=np.float64)
    out_r = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    fn(la.ctypes.data_as(dbl), ra.ctypes.data_as(dbl), ctypes.c_size_t(n),
       ctypes.c_int(int(pre_delay_samples)), ctypes.c_double(room_size),
       ctypes.c_double(decay_time), ctypes.c_double(damping),
       ctypes.c_double(wet_dry), ctypes.c_double(sample_rate),
       out_l.ctypes.data_as(dbl), out_r.ctypes.data_as(dbl))
    return out_l, out_r


_SATURATOR_SRC = _HERE / "saturator_kernel.cpp"
_saturator_lib = None
_saturator_fn = None


def _saturator_lib_path() -> Path:
    return _HERE / f"saturator_kernel.{platform.machine()}.dylib"


def build_saturator_kernel(force: bool = False) -> Path | None:
    lib = _saturator_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _SATURATOR_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_SATURATOR_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_saturator():
    global _saturator_lib, _saturator_fn
    if _saturator_fn is not None:
        return _saturator_fn
    path = build_saturator_kernel()
    if path is None:
        return None
    _saturator_lib = ctypes.CDLL(str(path))

    fn = _saturator_lib.saturator_waveshape
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # x_up
        ctypes.c_size_t,                  # n
        ctypes.c_double,                  # drive_linear
        ctypes.c_double,                  # even_harmonics_a
        ctypes.c_double,                  # mix
        ctypes.POINTER(ctypes.c_double),  # x_orig
        ctypes.c_size_t,                  # n_orig
        ctypes.POINTER(ctypes.c_double),  # y_out
    ]
    _saturator_fn = fn
    return _saturator_fn


def is_saturator_available() -> bool:
    return _load_saturator() is not None


def native_saturator_waveshape(x_up, drive_linear: float, even_harmonics_a: float, mix: float = 1.0, x_orig=None):
    import numpy as np
    fn = _load_saturator()
    if fn is None:
        raise RuntimeError("native saturator kernel unavailable")
    x_up_arr = np.ascontiguousarray(x_up, dtype=np.float64)
    n = x_up_arr.shape[0]
    y_out = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    x_orig_ptr = None
    n_orig = 0
    if x_orig is not None:
        x_orig_arr = np.ascontiguousarray(x_orig, dtype=np.float64)
        x_orig_ptr = x_orig_arr.ctypes.data_as(dbl)
        n_orig = x_orig_arr.shape[0]

    fn(x_up_arr.ctypes.data_as(dbl), ctypes.c_size_t(n),
       ctypes.c_double(drive_linear), ctypes.c_double(even_harmonics_a),
       ctypes.c_double(mix), x_orig_ptr, ctypes.c_size_t(n_orig),
       y_out.ctypes.data_as(dbl))
    return y_out


_PHASE_SRC = _HERE / "phase_correlation_kernel.cpp"
_phase_lib = None
_phase_fn = None


def _phase_lib_path() -> Path:
    return _HERE / f"phase_correlation_kernel.{platform.machine()}.dylib"


def build_phase_correlation_kernel(force: bool = False) -> Path | None:
    lib = _phase_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _PHASE_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_PHASE_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_phase_correlation():
    global _phase_lib, _phase_fn
    if _phase_fn is not None:
        return _phase_fn
    path = build_phase_correlation_kernel()
    if path is None:
        return None
    _phase_lib = ctypes.CDLL(str(path))

    fn = _phase_lib.direct_cross_correlation
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # a
        ctypes.POINTER(ctypes.c_double),  # b
        ctypes.c_size_t,                  # n
        ctypes.c_int,                     # max_lag
        ctypes.POINTER(ctypes.c_double),  # out_best_corr
        ctypes.POINTER(ctypes.c_int),     # out_best_lag
    ]
    _phase_fn = fn
    return _phase_fn


def is_phase_correlation_available() -> bool:
    return _load_phase_correlation() is not None


def native_direct_cross_correlation(a, b, max_lag: int):
    import numpy as np
    fn = _load_phase_correlation()
    if fn is None:
        raise RuntimeError("native phase correlation kernel unavailable")
    a_arr = np.ascontiguousarray(a, dtype=np.float64)
    b_arr = np.ascontiguousarray(b, dtype=np.float64)
    n = min(a_arr.shape[0], b_arr.shape[0])
    best_corr = ctypes.c_double(0.0)
    best_lag = ctypes.c_int(0)
    dbl = ctypes.POINTER(ctypes.c_double)
    iptr = ctypes.POINTER(ctypes.c_int)

    fn(a_arr.ctypes.data_as(dbl), b_arr.ctypes.data_as(dbl),
       ctypes.c_size_t(n), ctypes.c_int(int(max_lag)),
       ctypes.byref(best_corr), ctypes.byref(best_lag))
    return float(best_corr.value), int(best_lag.value)


_TRANSIENT_SRC = _HERE / "transient_threshold_kernel.cpp"
_transient_lib = None
_transient_fn = None


def _transient_lib_path() -> Path:
    return _HERE / f"transient_threshold_kernel.{platform.machine()}.dylib"


def build_transient_threshold_kernel(force: bool = False) -> Path | None:
    lib = _transient_lib_path()
    if lib.exists() and not force and lib.stat().st_mtime >= _TRANSIENT_SRC.stat().st_mtime:
        return lib

    compiler = "clang++" if sys.platform == "darwin" else "g++"
    ext_suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = lib.with_suffix(ext_suffix) if sys.platform != "darwin" else lib

    cmd = [compiler, "-O3", "-std=c++17", "-shared", "-fPIC", "-o", str(lib), str(_TRANSIENT_SRC)]
    if sys.platform == "darwin":
        cmd[1:1] = ["-arch", platform.machine()]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return lib if lib.exists() else None


def _load_transient_threshold():
    global _transient_lib, _transient_fn
    if _transient_fn is not None:
        return _transient_fn
    path = build_transient_threshold_kernel()
    if path is None:
        return None
    _transient_lib = ctypes.CDLL(str(path))

    fn = _transient_lib.rolling_median_mad_threshold
    fn.restype = None
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_double),  # flux
        ctypes.c_size_t,                  # n
        ctypes.c_int,                     # radius
        ctypes.c_double,                  # min_floor
        ctypes.c_double,                  # mad_multiplier
        ctypes.POINTER(ctypes.c_double),  # threshold_out
    ]
    _transient_fn = fn
    return _transient_fn


def is_transient_threshold_available() -> bool:
    return _load_transient_threshold() is not None


def native_rolling_median_mad_threshold(flux, radius: int, min_floor: float, mad_multiplier: float):
    import numpy as np
    fn = _load_transient_threshold()
    if fn is None:
        raise RuntimeError("native transient threshold kernel unavailable")
    flux_arr = np.ascontiguousarray(flux, dtype=np.float64)
    n = flux_arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    dbl = ctypes.POINTER(ctypes.c_double)
    fn(flux_arr.ctypes.data_as(dbl), ctypes.c_size_t(n), ctypes.c_int(int(radius)),
       ctypes.c_double(min_floor), ctypes.c_double(mad_multiplier),
       out.ctypes.data_as(dbl))
    return out
