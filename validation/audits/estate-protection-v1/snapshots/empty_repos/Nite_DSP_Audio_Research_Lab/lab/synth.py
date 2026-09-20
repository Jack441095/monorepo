"""Deterministic synthetic audio generators for ground-truth experiments."""
import numpy as np
from scipy import signal as sps


def rng(seed):
    return np.random.default_rng(seed)


def t_axis(n, sr):
    return np.arange(n) / sr


def _norm(x, peak=0.7):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def env_exp(n, sr, decay_s, attack_s=0.002):
    t = t_axis(n, sr)
    a = np.ones(n)
    if attack_s > 0:
        na = max(1, int(attack_s * sr))
        a[:na] = np.linspace(0, 1, na)
    return a * np.exp(-t / max(decay_s, 1e-6))


def kick(sr, dur, f_start=110.0, f_end=48.0, decay=0.25, click=0.35, seed=0):
    n = int(dur * sr)
    t = t_axis(n, sr)
    f = f_end + (f_start - f_end) * np.exp(-t / 0.012)
    ph = 2 * np.pi * np.cumsum(f) / sr
    body = np.sin(ph) * env_exp(n, sr, decay)
    nc = max(4, int(0.004 * sr))
    clickn = rng(seed).standard_normal(nc)
    clickn -= clickn.mean()
    cl = np.zeros(n)
    cl[:nc] = clickn / (np.max(np.abs(clickn)) + 1e-12)
    x = body + click * cl
    return _norm(x)


def snare(sr, dur, tone_f=185.0, noise_mix=0.65, decay=0.14, seed=0):
    n = int(dur * sr)
    g = rng(seed)
    noise = g.standard_normal(n)
    b, a = sps.butter(2, 1800 / (sr / 2), "highpass")
    noise = sps.lfilter(b, a, noise)
    tone = np.sin(2 * np.pi * tone_f * t_axis(n, sr)) * env_exp(n, sr, decay * 0.8)
    e = env_exp(n, sr, decay)
    x = (noise_mix * noise + (1 - noise_mix) * tone) * e
    return _norm(x)


def bass_note(sr, dur, f0, sustain=True, decay=None, sub=0.6, harmonics=(0.5, 0.25, 0.12), seed=0):
    n = int(dur * sr)
    t = t_axis(n, sr)
    ph = 2 * np.pi * f0 * t
    x = np.sin(ph) + sub * np.sin(2 * np.pi * f0 / 2 * t) if f0 > 40 else np.sin(ph)
    for i, amp in enumerate(harmonics):
        x += amp * np.sin((i + 2) * ph + 0.3 * (i + 1))
    if sustain:
        na = max(1, int(0.01 * sr))
        e = np.ones(n)
        e[:na] = np.linspace(0, 1, na)
        rel = max(1, int(0.03 * sr))
        e[-rel:] *= np.linspace(1, 0, rel)
    elif decay is not None:
        e = env_exp(n, sr, decay, attack_s=0.005)
    else:
        raise ValueError("sustain=False requires decay")
    x = x * e
    g = rng(seed)
    x += 0.01 * g.standard_normal(n)
    return _norm(x)


def harmonic_tone(sr, dur, f0, amps=(1.0, 0.5, 0.33, 0.25, 0.2), decay=None, seed=0):
    n = int(dur * sr)
    t = t_axis(n, sr)
    x = np.zeros(n)
    g = rng(seed)
    for i, a in enumerate(amps):
        x += a * np.sin(2 * np.pi * (i + 1) * f0 * t + g.uniform(0, 2 * np.pi))
    if decay is not None:
        x *= env_exp(n, sr, decay, attack_s=0.005)
    else:
        na = max(1, int(0.02 * sr))
        x[:na] *= np.linspace(0, 1, na)
    return _norm(x)


def pad_chord(sr, dur, freqs, seed=0):
    n = int(dur * sr)
    g = rng(seed)
    t = t_axis(n, sr)
    x = np.zeros(n)
    for f in freqs:
        detune = 1 + g.uniform(-0.0015, 0.0015)
        vib = 1 + 0.002 * np.sin(2 * np.pi * 4.5 * t + g.uniform(0, 6.28))
        x += np.sin(2 * np.pi * f * detune * vib * t + g.uniform(0, 6.28))
        x += 0.3 * np.sin(2 * np.pi * 2 * f * t + g.uniform(0, 6.28))
    na = int(0.15 * sr)
    e = np.ones(n)
    e[:na] = np.linspace(0, 1, na)
    e[-na:] *= np.linspace(1, 0, na)
    return _norm(x * e, 0.5)


def noise_burst(sr, dur, decay=0.05, lp=None, hp=None, seed=0):
    n = int(dur * sr)
    g = rng(seed)
    x = g.standard_normal(n)
    if lp:
        x = filter_signal(x, sr, "lowpass", lp)
    if hp:
        x = filter_signal(x, sr, "highpass", hp)
    return _norm(x * env_exp(n, sr, decay))


def reverb_tail(sr, dur, decay=0.8, channels=2, pre_delay_s=0.02, seed=0):
    n = int(dur * sr)
    out = np.zeros((n, channels))
    for c in range(channels):
        g = rng(seed + 100 * (c + 1))
        x = g.standard_normal(n)
        out[:, c] = x * env_exp(n, sr, decay, attack_s=pre_delay_s)
    return out


def silence_like(x_or_n):
    n = x_or_n if isinstance(x_or_n, int) else len(x_or_n)
    return np.zeros(n)


def delay_signal(x, sr, delay_ms, pad="end"):
    d = int(round(delay_ms * sr / 1000.0))
    out = np.zeros_like(x)
    if d >= 0:
        out[d:] = x[: len(x) - d]
    else:
        k = -d
        out[:-k] = x[k:]
    return out


def filter_signal(x, sr, kind, fc, order=4):
    if isinstance(fc, (list, tuple, np.ndarray)):
        sos = sps.butter(order, np.asarray(fc) / (sr / 2), kind, output="sos")
    else:
        sos = sps.butter(order, fc / (sr / 2), kind, output="sos")
    return sps.sosfilt(sos, x)


def place(events, sr, total_dur, gain_events=True):
    total = int(total_dur * sr)
    n_ch = events[0][2].ndim if events and events[0][2].ndim == 2 else 1
    out = np.zeros((total,) if n_ch == 1 else (total, n_ch))
    for start_s, gain, sig in events:
        s = int(start_s * sr)
        seg = sig if sig.ndim == 2 else sig[:, None] if out.ndim == 2 else sig
        seg = sig
        e = min(total, s + len(sig))
        seg = sig[: e - s]
        out[s:e] += gain * seg
    return out


def to_stereo(x, width=0.0, seed=0):
    if width <= 0:
        return np.stack([x, x], axis=1)
    g = rng(seed)
    side = g.standard_normal(len(x))
    side = filter_signal(side, 44100, "lowpass", 700)
    side = side / (np.max(np.abs(side)) + 1e-12) * np.max(np.abs(x)) * width
    mid = x
    left = mid + side
    right = mid - side
    return np.stack([left, right], axis=1)
