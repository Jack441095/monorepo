"""Reusable audio measurement library (research only, not production)."""
import numpy as np
from scipy import signal as sps


def peak_dbfs(x):
    p = np.max(np.abs(x))
    return 20 * np.log10(p + 1e-12)


def rms_db(x):
    r = np.sqrt(np.mean(np.square(x)))
    return 20 * np.log10(r + 1e-12)


def crest_db(x):
    r = np.sqrt(np.mean(np.square(x))) + 1e-12
    return 20 * np.log10(np.max(np.abs(x)) / r)


def dc_offset(x):
    return float(np.mean(x))


def silence_fraction(x, thr_db=-60):
    amp = np.abs(x)
    return float(np.mean(amp < 10 ** (thr_db / 20)))


def stft_mag(x, sr, n_fft=2048, hop=512):
    f, t, z = sps.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)
    return f, t, np.abs(z)


def band_energies(mag, freqs, bands=((20, 60), (60, 120), (120, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000))):
    out = {}
    total = np.sum(mag**2) + 1e-20
    for lo, hi in bands:
        m = (freqs >= lo) & (freqs < hi)
        out[f"{lo}-{hi}"] = float(np.sum(mag[m] ** 2) / total)
    return out


def spectral_centroid(x, sr, n_fft=2048):
    mag = np.abs(sps.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft // 2, boundary=None, padded=False)[2])
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    c = np.sum(freqs[:, None] * mag, axis=0) / (np.sum(mag, axis=0) + 1e-12)
    return float(np.mean(c))


def spectral_flatness_db(x, sr, n_fft=2048):
    mag = np.abs(sps.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft // 2, boundary=None, padded=False)[2]) + 1e-12
    logm = np.log(mag)
    flat = np.exp(np.mean(logm, axis=0)) / (np.mean(mag, axis=0) + 1e-20)
    return float(10 * np.log10(np.mean(flat) + 1e-20))


def onset_envelope(x, sr, n_fft=1024, hop=256):
    f, t, z = sps.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)
    mag = np.abs(z)
    flux = np.sqrt(np.sum(np.diff(mag, axis=1) ** 2, axis=0))
    flux = np.concatenate([[0], flux])
    return t, flux


def onsets(x, sr, delta_ratio=0.3, min_gap_s=0.03):
    t, flux = onset_envelope(x, sr)
    if len(flux) < 3:
        return np.array([]), flux, t
    thr = delta_ratio * (np.percentile(flux, 95) + 1e-12)
    peaks, props = sps.find_peaks(flux, height=thr, distance=max(1, int(min_gap_s * sr / 256)))
    return t[peaks], flux, t


def estimate_f0_autocorr(x, sr, fmin=25.0, fmax=400.0):
    x = x - np.mean(x)
    if len(x) < 64 or np.max(np.abs(x)) < 1e-6:
        return None
    ac = sps.correlate(x, x, mode="full", method="fft")
    ac = ac[len(ac) // 2:]
    ac /= ac[0] + 1e-20
    lo = max(1, int(sr / fmax))
    hi = min(len(ac) - 1, int(sr / fmin))
    if hi <= lo:
        return None
    seg = ac[lo:hi]
    k = np.argmax(seg)
    if seg[k] < 0.2:
        return None
    return float(sr / (lo + k))


def stereo_metrics(x):
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError("need stereo [n,2]")
    l, r = x[:, 0], x[:, 1]
    denom = np.sqrt(np.sum(l * l) * np.sum(r * r)) + 1e-20
    corr = float(np.sum(l * r) / denom)
    mid, side = (l + r) / 2, (l - r) / 2
    me, se = np.sum(mid**2), np.sum(side**2)
    el, er = np.sqrt(np.sum(l * l)), np.sqrt(np.sum(r * r))
    return {
        "correlation": corr,
        "side_mid_ratio": float(se / (me + 1e-20)),
        "mono_loss_db": float(10 * np.log10((me + 1e-20) / (np.sum(l**2 + r**2) / 2 + 1e-20))),
        "balance": float((el - er) / (el + er + 1e-20)),
    }


def band_side_energy(x, sr, bands=((20, 120), (120, 400), (400, 2000), (2000, 16000)), n_fft=2048):
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError("need stereo")
    side = (x[:, 0] - x[:, 1]) / 2
    mid = (x[:, 0] + x[:, 1]) / 2
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    _, _, S = sps.stft(side, fs=sr, nperseg=n_fft, noverlap=n_fft // 2, boundary=None, padded=False)
    _, _, M = sps.stft(mid, fs=sr, nperseg=n_fft, noverlap=n_fft // 2, boundary=None, padded=False)
    out = {}
    for lo, hi in bands:
        m = (f >= lo) & (f < hi)
        se, me = np.sum(S[m] ** 2), np.sum(M[m] ** 2)
        out[f"{lo}-{hi}"] = float(se / (se + me + 1e-20))
    return out


def cross_correlation_lag(a, b, sr, max_ms=25.0):
    a = a - np.mean(a)
    b = b - np.mean(b)
    cc = sps.correlate(b, a, mode="full", method="fft")
    mid = len(a) - 1
    maxlag = int(max_ms * sr / 1000)
    lo, hi = max(0, mid - maxlag), min(len(cc), mid + maxlag + 1)
    seg = cc[lo:hi]
    k = int(np.argmax(seg))
    lag = (lo + k) - mid
    energy = np.sqrt(np.sum(a * a) * np.sum(b * b)) + 1e-20
    peak_norm = float(seg[k] / energy)
    sharp = float(seg[k] / (np.max(np.abs(seg[np.arange(len(seg)) != k])) + 1e-12))
    return lag, peak_norm, sharp


def gcc_phat_lag(a, b, sr, max_ms=25.0, eps=1e-10):
    n = len(a) + len(b) - 1
    nfft = 1 << int(np.ceil(np.log2(n)))
    A = np.fft.rfft(a, nfft)
    B = np.fft.rfft(b, nfft)
    R = B * np.conj(A)
    mag = np.abs(R) + eps
    gcc = np.fft.irfft(R / mag, nfft)
    mid = 0
    gcc = np.concatenate([gcc[-len(a) + 1:], gcc[: len(b)]])
    mid = len(a) - 1
    maxlag = int(max_ms * sr / 1000)
    lo, hi = max(0, mid - maxlag), min(len(gcc), mid + maxlag + 1)
    seg = gcc[lo:hi]
    k = int(np.argmax(seg))
    lag = (lo + k) - mid
    peak = float(seg[k] / (np.max(np.abs(seg)) + 1e-20))
    sorted_seg = np.sort(np.abs(seg))
    ratio = float(sorted_seg[-1] / (sorted_seg[-2] + 1e-20))
    return lag, peak, ratio


def coherence(a, b, sr, nperseg=1024):
    f, c = sps.coherence(a, b, fs=sr, nperseg=min(nperseg, len(a)))
    return f, c


def lowband_correlation(a, b, sr, fc=120, order=4):
    sos = sps.iirfilter(order, fc / (sr / 2), btype="lowpass", output="sos")
    al, bl = sps.sosfilt(sos, a), sps.sosfilt(sos, b)
    denom = np.sqrt(np.sum(al * al) * np.sum(bl * bl)) + 1e-20
    return float(np.sum(al * bl) / denom)


def spectral_peaks(x, sr, n_fft=4096, prominence_db=8.0, min_sep_hz=20.0):
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    mag_db = 20 * np.log10(np.abs(np.fft.rfft(x, n_fft)) + 1e-12)
    pk, props = sps.find_peaks(mag_db, prominence=prominence_db, distance=max(1, int(min_sep_hz / (sr / n_fft))))
    return [(float(f[k]), float(mag_db[k]), float(props["prominences"][i])) for i, k in enumerate(pk)]


def peak_persistence(x, sr, fc_hz, tol_frac=0.04, n_fft=2048, hop=512):
    f, t, z = sps.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)
    mag_db = 20 * np.log10(np.abs(z) + 1e-12)
    nbins = mag_db.shape[1]
    if nbins == 0:
        return 0.0
    hits = 0
    for i in range(nbins):
        col = mag_db[:, i]
        mu = np.mean(col)
        pk, _ = sps.find_peaks(col - col.max(), prominence=6)
        if len(pk) == 0:
            continue
        best = pk[np.argmax(col[pk])]
        near = (np.abs(f - fc_hz) < tol_frac * fc_hz)
        if np.any(near) and col[near].max() > col.max() - 3:
            hits += 1
    return hits / nbins


def summarize(x, sr):
    if x.ndim == 2:
        mono = x.mean(axis=1)
        sm = stereo_metrics(x)
    else:
        mono = x
        sm = None
    f = np.fft.rfftfreq(4096, 1 / sr)
    mag = np.abs(np.fft.rfft(mono, 4096))
    be = band_energies(mag, f)
    out = {
        "peak_dbfs": peak_dbfs(mono),
        "rms_db": rms_db(mono),
        "crest_db": crest_db(mono),
        "dc": dc_offset(mono),
        "silence_fraction": silence_fraction(mono),
        "spectral_centroid_hz": spectral_centroid(mono, sr),
        "flatness_db": spectral_flatness_db(mono, sr),
        "band_fractions": be,
        "f0_hz": estimate_f0_autocorr(mono, sr),
    }
    if sm:
        out["stereo"] = sm
    return out
