"""Scenario builders composing signals + ground-truth transforms."""
from __future__ import annotations

import numpy as np
from scipy import signal as sps

from . import corpus as C


def _finish(case_id, family, fs, n, a, b, d, pol, label, log, meta) -> C.LayerCase:
    spec = C.CaseSpec(case_id=case_id, family=family, fs=fs, n_samples=n,
                      seed=C.case_seed(case_id),
                      truth_offset_samples=float(d), truth_polarity=int(pol),
                      label=label, transform_log=log.entries, meta=meta)
    return C.LayerCase(spec, a, b)


def simple_delay_case(kind_a, kind_b_or_none, fs, n, case_id, delay_samples,
                      polarity=1, snr_db=None, gain_db=0.0):
    """B = transform(A) when kind_b is None, else independent B + A-like."""
    rng = np.random.default_rng(C.case_seed(case_id))
    log = C.TransformLog()
    a = C.SIGNAL_GENERATORS[kind_a](rng, n, fs)
    if kind_b_or_none is None:
        b = a.copy()
    else:
        b = C.SIGNAL_GENERATORS[kind_b_or_none](rng, n, fs)
        # make B partially related: mix 60% of A's content into B
        b = 0.6 * a / (np.max(np.abs(a)) + 1e-12) * float(
            rng.uniform(0.5, 1.5)) + 0.4 * b / (np.max(np.abs(b)) + 1e-12)
        b /= np.max(np.abs(b)) + 1e-12
    if gain_db:
        b = C.apply_gain(b, gain_db, log)
    if snr_db is not None:
        b = C.add_noise_at_snr(b, snr_db, rng, log)
    b = C.apply_polarity(b, polarity == -1, log)
    b = C.apply_delay_exact(b, delay_samples, fs, log)
    label = "NO_ACTION" if (abs(delay_samples) < 0.5 and polarity == 1
                            and not snr_db) else "ACTION_KNOWN"
    return _finish(case_id, f"delay/{kind_a}", fs, n, a, b,
                   delay_samples, polarity, label, log,
                   {"snr_db": snr_db, "gain_db": gain_db})


def filtered_phase_case(kind_a, fs, n, case_id, mode, delay_samples=0.0,
                        polarity=1):
    """B = A through dispersive processing (EQ/allpass/crossover/LP-FIR)."""
    rng = np.random.default_rng(C.case_seed(case_id))
    log = C.TransformLog()
    a = C.SIGNAL_GENERATORS[kind_a](rng, n, fs)
    b = a.copy()
    if mode == "minphase_eq":
        b = C.apply_minphase_eq(b, fs, rng, log)
    elif mode == "allpass":
        b = C.apply_allpass_chain(b, fs, rng, log)
    elif mode == "lr4_crossover":
        b = C.lr4_crossover_recombine(b, fs, float(rng.uniform(500, 3000)), log)
    elif mode == "linear_phase_eq":
        b = C.apply_linear_phase_eq(b, fs, rng, log)
    elif mode == "mic_tf":
        b = C.apply_mic_tf(b, fs, rng, log)
    else:
        raise ValueError(mode)
    b = C.apply_polarity(b, polarity == -1, log)
    b = C.apply_delay_exact(b, delay_samples, fs, log)
    embedded = sum(float(e.get("delay_samples", 0.0)) for e in log.entries
                   if e["op"] not in ("exact_delay",))
    truth_total = float(delay_samples) + embedded
    return _finish(case_id, f"phase/{mode}", fs, n, a, b,
                   truth_total, polarity, "ACTION_KNOWN", log,
                   {"mode": mode, "embedded_latency": embedded})


def kick_layer_stack(fs, n, case_id, offsets=(0, 0, 0), polarities=(1, 1, 1),
                     pitch_scale=(1.0, 1.0, 1.0), env_scale=(1.0, 1.0, 1.0),
                     overlap=True):
    """Sub + body + click kick stack.

    A = sub layer. B = body + click composite (each part carrying its own
    timing/polarity). With overlap=True the body fundamental sits inside
    the sub's sweep region so timing genuinely changes low-band summation;
    with overlap=False layers are spectrally disjoint (intentional
    layering — correct outcome is usually NO ACTION).
    """
    rng = np.random.default_rng(C.case_seed(case_id))
    log = C.TransformLog()
    t = np.arange(n) / fs

    sub_f0 = 48.0 * pitch_scale[0]
    sweep = 40 + (sub_f0 - 40) * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(sweep) / fs
    env = np.exp(-t / 0.09 * env_scale[0])
    sub = np.sin(phase) * env

    if overlap:
        # Reinforcing layer: same pitch contour as the sub (sample
        # replacement / reinforcement scenario) so timing genuinely
        # changes low-band summation.
        body_env = np.exp(-t / 0.06 * env_scale[1])
        body = np.sin(phase * 1.0) * body_env * 0.8
    else:
        body_f0 = 95.0 * pitch_scale[1]
        body = np.sin(2 * np.pi * body_f0 * t) * \
            np.exp(-t / 0.06 * env_scale[1]) * 0.8

    click_n = max(4, int(0.003 * fs))
    click_env = np.exp(-np.arange(n) / (click_n / 4.0))
    click = sps.sosfilt(sps.butter(2, 3000, fs=fs, output="sos"),
                        rng.standard_normal(n)) * click_env * 0.6

    a = sub / (np.max(np.abs(sub)) + 1e-12)
    parts = []
    for sig, d, p in ((body, offsets[1], polarities[1]),
                      (click, offsets[2], polarities[2])):
        s = C.apply_polarity(sig.copy(), p == -1, log)
        s = C.apply_delay_exact(s, d, fs, log)
        parts.append(s)
    b = parts[0] + parts[1]
    b = b / (np.max(np.abs(b)) + 1e-12)
    truth_d = float(np.mean([offsets[1], offsets[2]]))
    return _finish(case_id, "layers/kick", fs, n, a, b, truth_d, 1,
                   "ACTION_KNOWN" if any(abs(o) > 0.5 for o in offsets)
                   else "NO_ACTION", log,
                   {"offsets": list(offsets), "polarities": list(polarities)})


def parallel_processing_case(fs, n, case_id, mode, latency_samples=0.0):
    """A = dry; B = processed copy (+ plugin latency)."""
    rng = np.random.default_rng(C.case_seed(case_id))
    log = C.TransformLog()
    kind = str(rng.choice(["kick", "bass_transient", "synth_transient",
                           "snare_body"]))
    a = C.SIGNAL_GENERATORS[kind](rng, n, fs)

    def comp_env(x, ratio=4.0, thresh=0.05):
        win = int(0.005 * fs)
        e = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, mode="same"))
        g = np.where(e > thresh, (thresh / (e + 1e-9)) ** (1 - 1 / ratio), 1.0)
        return x * g

    if mode == "compressed":
        b = comp_env(a) * 2.2
        log.add("parallel_compression", delay_samples=latency_samples)
    elif mode == "saturated":
        b = C.apply_distortion(a, 3.0, log) * 0.9
    elif mode == "filtered":
        sos = sps.butter(4, [300, 6000], btype="band", fs=fs, output="sos")
        b = sps.sosfilt(sos, a)
        log.add("band_filter", lo=300, hi=6000, delay_samples=latency_samples)
    elif mode == "multiband":
        lo_sos = sps.butter(4, 200, btype="low", fs=fs, output="sos")
        hi_sos = sps.butter(4, 200, btype="high", fs=fs, output="sos")
        b = sps.sosfilt(lo_sos, a) + 1.3 * sps.sosfilt(hi_sos, comp_env(a))
        log.add("multiband_parallel", delay_samples=latency_samples)
    elif mode == "oversampled":
        b = C.apply_linear_phase_eq(a, fs, rng, log, taps=257)
    else:
        raise ValueError(mode)
    if latency_samples:
        b = C.apply_delay_exact(b, latency_samples, fs, log)
    b /= max(np.max(np.abs(a)), np.max(np.abs(b)), 1e-12)
    a /= np.max(np.abs(a)) + 1e-12
    # total ground-truth offset includes processing-embedded latency
    # (e.g. linear-phase FIR) recorded in the transform log
    embedded = sum(float(e.get("delay_samples", 0.0)) for e in log.entries
                   if e["op"] not in ("exact_delay",))
    truth_total = float(latency_samples) + embedded
    label = "ACTION_KNOWN" if abs(truth_total) >= 0.5 else "NO_ACTION"
    return _finish(case_id, f"parallel/{mode}", fs, n, a, b,
                   truth_total, 1, label, log,
                   {"mode": mode, "plugin_latency": latency_samples,
                    "embedded_latency": embedded})
