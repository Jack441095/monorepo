# sampler/sampler_kernels.py
"""
Leaf-layer numeric kernels for the Sampler's resampling/pitch-tracking hot paths.

Split out of sampler.py (P4 giant-file decomposition): pure, stateless
functions/JIT kernels with no `self` dependency, so they form the lowest layer
of the sampler package's internal call graph. Moved verbatim (precise
line-range extraction, byte-identical bodies) -- no numeric/behavior changes.

Numba-JIT kernels below are only DEFINED when numba is importable, exactly as
in the original module -- these names simply do not exist in this module's
namespace when numba is unavailable. Callers must guard access with
`_have_numba()` first (as the original code did) and must NOT do
`from .sampler_kernels import _variable_rate_read_nb` etc. at module load
time, since that raises ImportError instead of falling back to pure Python
when numba is missing. Use `from . import sampler_kernels` and access
`sampler_kernels._name` lazily inside the already-existing `if
_have_numba():` guarded call site instead.
"""
import numpy as np

# Optional acceleration for tiny tight loops (pure-Python fallback).
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _have_numba() -> bool:
    return _nb is not None


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _one_pole_filter_nb_stereo(audio, coeff, state_l, state_r):
        n = audio.shape[0]
        out = audio  # mutate in place
        one_minus = 1.0 - coeff
        sl = state_l
        sr = state_r
        for i in range(n):
            sl = coeff * out[i, 0] + one_minus * sl
            sr = coeff * out[i, 1] + one_minus * sr
            out[i, 0] = sl
            out[i, 1] = sr
        return out, sl, sr


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _one_pole_filter_nb_mono(audio, coeff, state):
        n = audio.shape[0]
        out = audio  # mutate in place
        one_minus = 1.0 - coeff
        st = state
        for i in range(n):
            st = coeff * out[i] + one_minus * st
            out[i] = st
        return out, st


    @_nb.njit(cache=True, fastmath=True)
    def _variable_rate_read_nb(raw_stereo, step, loop_start, loop_end, looping, max_samples):
        src_len = raw_stereo.shape[0]
        if looping:
            n_valid = max_samples
        else:
            if step > 0.0:
                val = float(src_len) / step
                n_valid = int(np.ceil(val))
                if n_valid < 0:
                    n_valid = 0
                elif n_valid > max_samples:
                    n_valid = max_samples
            else:
                n_valid = max_samples

        out = np.empty((n_valid, 2), dtype=np.float32)
        pos = 0.0
        loop_range = float(loop_end - loop_start)

        for i in range(n_valid):
            curr_pos = pos
            if looping:
                if curr_pos >= loop_end:
                    curr_pos = loop_start + (curr_pos - loop_end) % loop_range

            idx_f = int(curr_pos)
            frac = float(curr_pos - idx_f)
            idx_c = idx_f + 1
            if idx_c >= src_len:
                idx_c = src_len - 1

            out[i, 0] = raw_stereo[idx_f, 0] * (1.0 - frac) + raw_stereo[idx_c, 0] * frac
            out[i, 1] = raw_stereo[idx_f, 1] * (1.0 - frac) + raw_stereo[idx_c, 1] * frac
            pos += step

        return out


    @_nb.njit(cache=True, fastmath=True)
    def _variable_rate_read_hq_nb(raw_stereo, step, loop_start, loop_end, looping, max_samples):
        src_len = raw_stereo.shape[0]
        if looping:
            n_valid = max_samples
        else:
            if step > 0.0:
                val = float(src_len) / step
                n_valid = int(np.ceil(val))
                if n_valid < 0:
                    n_valid = 0
                elif n_valid > max_samples:
                    n_valid = max_samples
            else:
                n_valid = max_samples

        out = np.empty((n_valid, 2), dtype=np.float32)
        pos = 0.0
        loop_range = float(loop_end - loop_start)

        for i in range(n_valid):
            curr_pos = pos
            if looping:
                if curr_pos >= loop_end:
                    curr_pos = loop_start + (curr_pos - loop_end) % loop_range

            idx_f = int(curr_pos)
            frac = float(curr_pos - idx_f)

            idx_m1 = idx_f - 1
            if idx_m1 < 0:
                idx_m1 = 0

            idx_0 = idx_f
            if idx_0 >= src_len:
                idx_0 = src_len - 1

            idx_p1 = idx_f + 1
            if idx_p1 >= src_len:
                idx_p1 = src_len - 1

            idx_p2 = idx_f + 2
            if idx_p2 >= src_len:
                idx_p2 = src_len - 1

            t = frac
            t2 = t * t
            t3 = t2 * t

            for ch in range(2):
                p0 = raw_stereo[idx_m1, ch]
                p1 = raw_stereo[idx_0, ch]
                p2 = raw_stereo[idx_p1, ch]
                p3 = raw_stereo[idx_p2, ch]

                out[i, ch] = 0.5 * (
                    (2.0 * p1)
                    + (-p0 + p2) * t
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                    + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
                )
            pos += step

        return out


    @_nb.njit(cache=True, fastmath=True)
    def _variable_rate_read_positions_nb(raw_stereo, positions):
        n = positions.shape[0]
        out = np.empty((n, 2), dtype=np.float32)
        src_len = raw_stereo.shape[0]

        for i in range(n):
            curr_pos = float(positions[i])
            idx_f = int(curr_pos)
            frac = float(curr_pos - idx_f)
            idx_c = idx_f + 1
            if idx_c >= src_len:
                idx_c = src_len - 1

            out[i, 0] = raw_stereo[idx_f, 0] * (1.0 - frac) + raw_stereo[idx_c, 0] * frac
            out[i, 1] = raw_stereo[idx_f, 1] * (1.0 - frac) + raw_stereo[idx_c, 1] * frac

        return out


    @_nb.njit(cache=True, fastmath=True)
    def _variable_rate_read_positions_hq_nb(raw_stereo, positions):
        n = positions.shape[0]
        out = np.empty((n, 2), dtype=np.float32)
        src_len = raw_stereo.shape[0]

        for i in range(n):
            curr_pos = float(positions[i])
            idx_f = int(curr_pos)
            frac = float(curr_pos - idx_f)

            idx_m1 = idx_f - 1
            if idx_m1 < 0:
                idx_m1 = 0

            idx_0 = idx_f
            if idx_0 >= src_len:
                idx_0 = src_len - 1

            idx_p1 = idx_f + 1
            if idx_p1 >= src_len:
                idx_p1 = src_len - 1

            idx_p2 = idx_f + 2
            if idx_p2 >= src_len:
                idx_p2 = src_len - 1

            t = frac
            t2 = t * t
            t3 = t2 * t

            for ch in range(2):
                p0 = raw_stereo[idx_m1, ch]
                p1 = raw_stereo[idx_0, ch]
                p2 = raw_stereo[idx_p1, ch]
                p3 = raw_stereo[idx_p2, ch]

                out[i, ch] = 0.5 * (
                    (2.0 * p1)
                    + (-p0 + p2) * t
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                    + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
                )

        return out


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)
