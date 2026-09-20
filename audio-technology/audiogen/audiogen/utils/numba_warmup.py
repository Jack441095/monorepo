from __future__ import annotations

import logging
from typing import Optional

import numpy as np


def warmup_numba_kernels(logger: Optional[logging.Logger] = None) -> None:
    """
    Trigger compilation of optional Numba kernels ahead of realtime playback.

    This is quality-neutral: it only compiles code paths that would otherwise be
    compiled on first audio/render use (often during the first "slow bar").
    """
    log = logger or logging.getLogger(__name__)

    # Loud check: numba failing to import silently drops ALL DSP (reverb/delay/mixer/
    # sampler filters) to pure Python -- ~100x slower render (7-15s/bar), which shows up
    # as NO AUDIO in the realtime player, not an error. The most common cause is a NumPy
    # version numba can't support (e.g. an unpinned upgrade to NumPy 2.1+ on Intel macOS,
    # where numba 0.60 only supports NumPy<=2.0). Make it a loud ERROR, not a quiet no-op.
    try:
        import numba  # noqa: F401
    except Exception as exc:
        try:
            import numpy as _np
            _npv = _np.__version__
        except Exception:
            _npv = "?"
        log.error(
            "NUMBA UNAVAILABLE (%s) -- audio DSP will run in PURE PYTHON (~100x slower "
            "render; the realtime player may produce little or NO audio). numpy=%s. Fix: "
            "align numpy/numba (Intel macOS needs numpy 2.0.x + numba 0.60.0 + llvmlite "
            "0.43.0; see requirements.txt). Then relaunch.",
            exc, _npv,
        )
        return

    # 1) Delay line kernel (audio/engine/mixer.py)
    try:
        from audio.engine.mixer import _delay_process_nb  # type: ignore

        x = np.zeros((64, 2), dtype=np.float32)
        buf = np.zeros((256, 2), dtype=np.float32)
        _delay_process_nb(x, buf, 0, 0, 20.25, 0.12, 1.0)
    except Exception as exc:
        log.debug("Numba warmup: delay kernel skipped (%s)", exc)

    # 2) One-pole sampler filter kernels (sampler/sampler.py)
    try:
        from sampler.sampler import (
            _one_pole_filter_nb_mono,
            _one_pole_filter_nb_stereo,
            _variable_rate_read_nb,
            _variable_rate_read_hq_nb,
            _variable_rate_read_positions_nb,
            _variable_rate_read_positions_hq_nb,
        )

        xm = np.zeros((128,), dtype=np.float32)
        _one_pole_filter_nb_mono(xm, 0.05, 0.0)

        xs = np.zeros((128, 2), dtype=np.float32)
        _one_pole_filter_nb_stereo(xs, 0.05, 0.0, 0.0)

        # Warm up new transposition kernels
        raw_stereo = np.zeros((128, 2), dtype=np.float32)
        _variable_rate_read_nb(raw_stereo, 1.25, 0, 128, True, 64)
        _variable_rate_read_hq_nb(raw_stereo, 1.25, 0, 128, True, 64)
        positions = np.zeros(64, dtype=np.float64)
        _variable_rate_read_positions_nb(raw_stereo, positions)
        _variable_rate_read_positions_hq_nb(raw_stereo, positions)
    except Exception as exc:
        log.debug("Numba warmup: sampler kernels skipped (%s)", exc)

    # 3) Schroeder reverb comb/allpass kernels (audio/engine/reverb.py)
    try:
        from audio.engine.reverb import NUMBA_AVAILABLE, RoomReverb

        if bool(NUMBA_AVAILABLE):
            rv = RoomReverb(sample_rate=48000, rt60=1.0, damping=0.5, wet=0.3)
            sig = np.zeros((512, 2), dtype=np.float32)
            sig[0, :] = 0.01
            rv.process(sig, quality_tier="balanced")
    except Exception as exc:
        log.debug("Numba warmup: reverb kernels skipped (%s)", exc)

    # 4) Mixer filters and EQ biquad kernels (audio/engine/mixer.py)
    try:
        from audio.engine.mixer import (
            _channel_filter_process_nb,
            _biquad_cascade_process_nb,
            _process_channel_strip_nb,
            _accumulate_send_nb,
            _sum_bus_and_meters_nb,
        )

        audio = np.zeros((64, 2), dtype=np.float32)
        hp_prev_x = np.zeros((2, 4), dtype=np.float32)
        hp_prev_y = np.zeros((2, 4), dtype=np.float32)
        lp_prev_y = np.zeros((2, 4), dtype=np.float32)
        _channel_filter_process_nb(
            audio,
            True,
            0.05,
            2,
            hp_prev_x,
            hp_prev_y,
            True,
            0.05,
            2,
            lp_prev_y,
        )

        sos = np.zeros((3, 6), dtype=np.float32)
        zi = np.zeros((3, 2, 2), dtype=np.float32)
        _biquad_cascade_process_nb(audio, sos, zi)

        # Warm up new sum-mixer kernels
        _process_channel_strip_nb(audio, 1.0, 0.0, True)
        send_buf = np.zeros((64, 2), dtype=np.float32)
        _accumulate_send_nb(send_buf, audio, 0.5)
        _sum_bus_and_meters_nb(audio, True)
    except Exception as exc:
        log.debug("Numba warmup: mixer/filter kernels skipped (%s)", exc)

    # 5) Master bus lookahead limiter kernel (audio/engine/master_bus.py)
    try:
        from audio.engine.master_bus import _limiter_gain_nb

        req_gain = np.ones(64, dtype=np.float32)
        _limiter_gain_nb(req_gain, 10, 0.99)
    except Exception as exc:
        log.debug("Numba warmup: limiter kernel skipped (%s)", exc)


