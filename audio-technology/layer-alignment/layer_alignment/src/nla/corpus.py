"""NITE DSP layer-alignment R&D — deterministic synthetic corpus engine.

Every case is reproducible from an integer case id:
    rng = np.random.default_rng(case_seed)
    case_seed = zlib.crc32(case_id.encode()) & 0x7FFFFFFF

Ground truth is always recorded explicitly in CaseSpec.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
from scipy import signal as sps


def case_seed(case_id: str) -> int:
    return zlib.crc32(case_id.encode("utf-8")) & 0x7FFFFFFF


# ----------------------------------------------------------------------
# primitive generators (all take rng first so cases are seed-deterministic)
# ----------------------------------------------------------------------

def g_impulse(rng, n, fs):
    x = np.zeros(n)
    x[int(rng.integers(n // 8, n // 4))] = 1.0
    return x


def g_sine(rng, n, fs):
    f = float(rng.uniform(40, 8000))
    ph = float(rng.uniform(0, 2 * np.pi))
    t = np.arange(n) / fs
    return 0.9 * np.sin(2 * np.pi * f * t + ph)


def g_multisine(rng, n, fs):
    k = int(rng.integers(3, 8))
    freqs = rng.uniform(30, 12000, k)
    amps = rng.uniform(0.2, 1.0, k)
    phases = rng.uniform(0, 2 * np.pi, k)
    t = np.arange(n) / fs
    x = np.zeros(n)
    for f, a, p in zip(freqs, amps, phases):
        x += a * np.sin(2 * np.pi * f * t + p)
    return x / (np.max(np.abs(x)) + 1e-12)


def g_noise(rng, n, fs):
    return rng.standard_normal(n) / np.sqrt(n / 2)


def g_bandnoise(rng, n, fs):
    lo = float(rng.uniform(20, 4000))
    hi = min(lo * float(rng.uniform(1.2, 6.0)), fs * 0.45)
    sos = sps.butter(4, [lo, hi], btype="band", fs=fs, output="sos")
    return sps.sosfiltfilt(sos, g_noise(rng, n, fs))


def g_kick(rng, n, fs):
    """Pitch-swept sine body + beater click."""
    t = np.arange(n) / fs
    dur = float(rng.uniform(0.25, 0.5))
    f0 = float(rng.uniform(55, 75))
    f1 = float(rng.uniform(38, 50))
    sweep = f1 + (f0 - f1) * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(sweep) / fs
    env = np.exp(-t / (dur / 5.0))
    body = np.sin(phase) * env
    click_n = max(4, int(0.004 * fs))
    click_env = np.exp(-np.arange(n) / (click_n / 4.0))
    click = sps.sosfilt(sps.butter(2, 2000, fs=fs, output="sos"),
                        rng.standard_normal(n)) * click_env * 0.7
    x = body + click
    return x / (np.max(np.abs(x)) + 1e-12)


def g_snare_body(rng, n, fs):
    t = np.arange(n) / fs
    f = float(rng.uniform(170, 340))
    env = np.exp(-t / float(rng.uniform(0.05, 0.11)))
    return np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) * env


def g_snare_noise(rng, n, fs):
    hp = float(rng.uniform(1200, 3000))
    sos = sps.butter(2, hp, btype="high", fs=fs, output="sos")
    env = np.exp(-np.arange(n) / (float(rng.uniform(0.06, 0.16)) * fs))
    x = sps.sosfilt(sos, rng.standard_normal(n)) * env
    return x / (np.max(np.abs(x)) + 1e-12)


def g_bass_transient(rng, n, fs):
    t = np.arange(n) / fs
    f0 = float(rng.uniform(45, 90))
    nh = int(rng.integers(3, 7))
    env = np.exp(-t / float(rng.uniform(0.08, 0.2)))
    atk = 1 - np.exp(-t / (0.003 * fs / fs))  # ~3 ms attack
    x = np.zeros(n)
    for h in range(1, nh + 1):
        x += (1.0 / h) * np.sin(2 * np.pi * f0 * h * t) * np.exp(-t * h / 0.15)
    return (x * env * atk) / (np.max(np.abs(x)) + 1e-12)


def g_bass_sustained(rng, n, fs):
    t = np.arange(n) / fs
    f0 = float(rng.uniform(40, 80))
    vib = 1 + 0.002 * np.sin(2 * np.pi * float(rng.uniform(3, 6)) * t)
    ph = 2 * np.pi * f0 * np.cumsum(vib) / fs
    saw = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
    sub = np.sin(ph)
    x = 0.6 * sub + 0.35 * saw
    sos = sps.butter(2, 5000, fs=fs, output="sos")
    return sps.sosfilt(sos, x)


def g_synth_transient(rng, n, fs):
    """Detuned saw stab."""
    t = np.arange(n) / fs
    f0 = float(rng.uniform(110, 440))
    det = float(rng.uniform(0.003, 0.02))
    env = np.exp(-t / float(rng.uniform(0.1, 0.3)))
    atk_n = max(1, int(0.005 * fs))
    atk = np.minimum(t * fs / atk_n, 1.0)
    ph1 = 2 * np.pi * f0 * (1 + det) * t
    ph2 = 2 * np.pi * f0 * (1 - det) * t
    saw = lambda p: 2 * ((p / (2 * np.pi)) % 1.0) - 1
    x = saw(ph1) + saw(ph2) + 0.5 * np.sin(ph1 / 2)
    sos = sps.butter(2, 9000, fs=fs, output="sos")
    return sps.sosfilt(sos, x * env * atk)


SIGNAL_GENERATORS: dict[str, Callable] = {
    "impulse": g_impulse,
    "sine": g_sine,
    "multisine": g_multisine,
    "noise": g_noise,
    "bandnoise": g_bandnoise,
    "kick": g_kick,
    "snare_body": g_snare_body,
    "snare_noise": g_snare_noise,
    "bass_transient": g_bass_transient,
    "bass_sustained": g_bass_sustained,
    "synth_transient": g_synth_transient,
}

# ----------------------------------------------------------------------
# transforms (each records exact parameters into the transform log)
# ----------------------------------------------------------------------

@dataclass
class TransformLog:
    entries: list = field(default_factory=list)

    def add(self, name: str, **params):
        self.entries.append({"op": name, **params})

    @property
    def total_delay_samples(self) -> float:
        return sum(float(e.get("delay_samples", 0.0)) for e in self.entries)


def apply_gain(x, db, log: TransformLog):
    g = 10 ** (db / 20.0)
    log.add("gain_db", value=float(db), delay_samples=0.0)
    return x * g


def apply_polarity(x, flip: bool, log: TransformLog):
    if flip:
        log.add("polarity_invert", delay_samples=0.0)
        return -x
    return x


def apply_delay_exact(x, delay_samples: float, fs, log: TransformLog):
    """Exact fractional+integer delay via frequency-domain phase ramp.

    Signal is padded generously so wrap-around cannot reach the analysis
    region; caller slices afterwards.
    """
    d = float(delay_samples)
    if abs(d) < 1e-12:
        log.add("identity_delay", delay_samples=0.0)
        return x.copy()
    pad = len(x) + int(abs(np.ceil(d))) + 64
    X = np.fft.rfft(x, n=pad)
    f = np.fft.rfftfreq(pad, d=1.0 / fs)
    Y = X * np.exp(-2j * np.pi * f * d / fs)
    y = np.fft.irfft(Y, n=pad)[: len(x)]
    log.add("exact_delay", delay_samples=d)
    return y


def _rbj_peaking(f0, gain_db, q, fs):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2 * q)
    b0 = 1 + alpha * A
    b1 = -2 * np.cos(w0)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha / A
    return np.array([b0, b1, b2]) / a0, np.array([1.0, a1 / a0, a2 / a0])


def _rbj_allpass(f0, q, fs):
    w0 = 2 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2 * q)
    b = np.array([(1 - alpha), -2 * np.cos(w0), (1 + alpha)])
    a = np.array([(1 + alpha), -2 * np.cos(w0), (1 - alpha)])
    return b / a[0], a / a[0]


def apply_minphase_eq(x, fs, rng, log: TransformLog, n_bands=3):
    """Cascaded minimum-phase peaking EQ (IIR)."""
    y = x.astype(float)
    centers = np.sort(rng.uniform(60, min(12000, fs * 0.4), n_bands))
    for fc in centers:
        g = float(rng.uniform(-9, 9))
        q = float(rng.uniform(0.7, 2.5))
        b, a = _rbj_peaking(fc, g, q, fs)
        y = sps.lfilter(b, a, y)
        log.add("minphase_peaking", f0=float(fc), gain_db=g, q=q, delay_samples=0.0)
    return y


def apply_allpass_chain(x, fs, rng, log: TransformLog, n_stages=2):
    y = x.astype(float)
    for _ in range(n_stages):
        fc = float(rng.uniform(100, min(10000, fs * 0.35)))
        q = float(rng.uniform(0.5, 2.0))
        b, a = _rbj_allpass(fc, q, fs)
        y = sps.lfilter(b, a, y)
        log.add("allpass_stage", f0=fc, q=q, delay_samples=0.0)
    return y


def lr4_crossover_recombine(x, fs, fc_hz, log: TransformLog):
    """Split through Linkwitz-Riley 4th order and recombine (no delay comp).

    Sum is magnitude-flat but acquires a frequency-dependent phase response
    (an allpass around the crossover) — a classic real-world alignment trap.
    """
    sos_l = np.vstack([sps.butter(2, fc_hz, btype="low", fs=fs, output="sos")] * 2)
    sos_h = np.vstack([sps.butter(2, fc_hz, btype="high", fs=fs, output="sos")] * 2)
    y = sps.sosfilt(sos_l, x) + sps.sosfilt(sos_h, x)
    log.add("lr4_crossover_recombine", fc_hz=float(fc_hz), delay_samples=0.0)
    return y


def apply_linear_phase_eq(x, fs, rng, log: TransformLog, taps=1025):
    """Zero-phase FIR magnitude EQ; introduces exact latency of (taps-1)/2."""
    nfft = 4096
    Hmag = np.ones(nfft // 2 + 1)
    centers = np.sort(rng.uniform(80, min(12000, fs * 0.4), 3))
    freqs = np.concatenate([[0.0], centers, [fs / 2]])
    gains = np.ones_like(freqs)
    for i, fc in enumerate(centers, start=1):
        gains[i] = 10 ** (float(rng.uniform(-8, 8)) / 20.0)
    interp_f = np.linspace(0, fs / 2, nfft // 2 + 1)
    Hmag = 10 ** (np.interp(np.log2(interp_f + 1),
                            np.log2(freqs + 1), 20 * np.log10(gains + 1e-12)) / 20.0)
    Hsym = np.concatenate([Hmag, Hmag[-2:0:-1]]).astype(complex)
    h = np.real(np.fft.ifft(Hsym))
    h = np.roll(h, taps // 2)[:taps] * np.hamming(taps)
    y = np.convolve(x, h, mode="full")[: len(x)]
    latency = (taps - 1) / 2.0
    log.add("linear_phase_eq", taps=int(taps), delay_samples=latency)
    return y


def apply_distortion(x, drive, log: TransformLog):
    k = float(drive)
    y = np.tanh(k * x) / np.tanh(k)
    log.add("distortion_tanh", drive=k, delay_samples=0.0)
    return y


def add_noise_at_snr(x, snr_db, rng, log: TransformLog):
    px = np.mean(x ** 2) + 1e-20
    pn = px * 10 ** (-snr_db / 20.0)
    n = rng.standard_normal(len(x)) * np.sqrt(pn)
    log.add("add_noise", snr_db=float(snr_db), delay_samples=0.0)
    return x + n


def apply_mic_tf(x, fs, rng, log: TransformLog):
    """Microphone-like transfer function: resonances + tilt + HPF."""
    y = x.astype(float)
    for _ in range(int(rng.integers(2, 5))):
        fc = float(rng.uniform(120, min(11000, fs * 0.35)))
        g = float(rng.uniform(-6, 6))
        q = float(rng.uniform(1.0, 4.0))
        b, a = _rbj_peaking(fc, g, q, fs)
        y = sps.lfilter(b, a, y)
        log.add("mic_resonance", f0=fc, gain_db=g, q=q, delay_samples=0.0)
    hp = float(rng.uniform(28, 70))
    sos = sps.butter(2, hp, btype="high", fs=fs, output="sos")
    y = sps.sosfilt(sos, y)
    log.add("mic_hpf", fc=hp, delay_samples=0.0)
    return y


# ----------------------------------------------------------------------
# case container
# ----------------------------------------------------------------------

@dataclass
class CaseSpec:
    case_id: str
    family: str
    fs: int
    n_samples: int
    seed: int
    truth_offset_samples: float      # positive => B lags A
    truth_polarity: int              # +1 normal, -1 inverted
    label: str                       # ACTION_KNOWN | NO_ACTION | UNRELATED
    transform_log: list
    meta: dict


class LayerCase:
    """A generated pair (a, b) with full ground-truth metadata."""

    def __init__(self, spec: CaseSpec, a: np.ndarray, b: np.ndarray):
        self.spec = spec
        self.a = a
        self.b = b


def make_pair(base_kind_a: str, base_kind_b: Optional[str], fs: int, n_samples: int,
              case_id: str, build: Callable[[dict], tuple[np.ndarray, np.ndarray]],
              truth_offset: float, truth_polarity: int, label: str,
              meta: dict) -> LayerCase:
    raise NotImplementedError  # replaced by explicit builders below
