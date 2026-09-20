#!/usr/bin/env python3
"""
Instrument-specific modal physics -- is a sound's PHYSICAL MODE STRUCTURE a
vendor-independent classifier?

What has already been tested and failed at +0.0pp: GENERIC harmonicity --
inharmonicity, tristimulus, odd/even balance, comb salience, pitch trajectory.
Those ask "how harmonic is this". They do not ask "what kind of object made it".

This asks the second question. Different physical objects have different, known
mode ratios:

  circular membrane (drum head)  1.000 1.594 2.136 2.296 2.653 2.918 3.156 3.501
  free-free bar / plate (metal)  1.000 2.756 5.404 8.933
  string / air column (tonal)    1 2 3 4 5 ...  (integer)
  stiff string                   f_n = n*f0*sqrt(1 + B*n^2), B measurable

THE REAL HYPOTHESIS. Not "this classifies better" -- the encoders already see
spectra. It is that mode structure is a property of the OBJECT, not of the
studio that recorded it, so it should be VENDOR-INDEPENDENT in a way learned
embeddings measurably are not (collection identity is decodable from Perch+CLAP
at ~59%). If true, these features should help most where the vendor gap hurts:
on unseen collections.

Two things are therefore measured, and the second matters more:
  1. do they add accuracy / coverage?
  2. do they REDUCE vendor decodability -- are they vendor-independent?

An honest prior: most samples in a real library are not recordings of a single
vibrating object. An 808 is a sine with a pitch envelope and no modes at all; a
commercial snare is layered, tuned, compressed and reverberated. Modal structure
may simply not survive. That is what the measurement is for.
"""
import os, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(SD, "modal_physics_v1.npz")
SR = 32000
VERSION = "modal-v1"

MEMBRANE = np.array([1.000, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501])
BAR      = np.array([1.000, 2.756, 5.404, 8.933])
HARMONIC = np.arange(1, 11, dtype=float)

NAMES = ["membrane_fit", "bar_fit", "harmonic_fit", "best_template",
         "membrane_minus_harmonic", "bar_minus_harmonic",
         "inharmonicity_B", "f0_hz", "n_partials", "partial_density",
         "spectral_irregularity", "mode_decay_spread", "tuned_partial_frac"]


def _partials(y, sr, max_p=12):
    """Strongest spectral peaks: frequency, magnitude."""
    import librosa
    from scipy.signal import find_peaks
    n_fft = 8192
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=2048)).mean(1)
    f = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    if S.max() <= 0:
        return np.array([]), np.array([])
    Sn = S / S.max()
    pk, _ = find_peaks(Sn, height=0.04, distance=4)
    pk = pk[(f[pk] > 40) & (f[pk] < 12000)]
    if len(pk) == 0:
        return np.array([]), np.array([])
    o = np.argsort(-Sn[pk])[:max_p]
    idx = np.sort(pk[o])
    return f[idx], Sn[idx]


def _template_fit(freqs, mags, template):
    """Magnitude-weighted closeness of observed partials to a mode template.

    f0 is taken as the lowest strong partial. For each observed partial we find
    the nearest template ratio and score by relative deviation, so a sound whose
    partials land on the template scores high regardless of absolute pitch.
    """
    if len(freqs) < 3:
        return 0.0
    f0 = freqs[0]
    if f0 <= 0:
        return 0.0
    ratios = freqs / f0
    w = mags / (mags.sum() + 1e-9)
    score = 0.0
    for r, wi in zip(ratios, w):
        d = np.min(np.abs(template - r) / np.maximum(template, 1e-9))
        score += wi * np.exp(-(d / 0.06) ** 2)      # 6% tolerance
    return float(score)


def _inharmonicity_B(freqs):
    """Stiff-string B from partial stretching: f_n = n*f0*sqrt(1+B n^2)."""
    if len(freqs) < 4:
        return 0.0
    f0 = freqs[0]
    n = np.round(freqs / f0)
    ok = (n >= 1) & (n <= 12)
    if ok.sum() < 4:
        return 0.0
    n, f = n[ok], freqs[ok]
    with np.errstate(all="ignore"):
        lhs = (f / (n * f0)) ** 2 - 1.0
        rhs = n ** 2
        B = float(np.sum(lhs * rhs) / (np.sum(rhs ** 2) + 1e-12))
    return float(np.clip(B, -0.01, 0.05))


def extract(path):
    import soundfile as sf, librosa
    try:
        y, sr0 = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if y.ndim > 1:
        y = y.mean(1)
    if sr0 != SR:
        y = librosa.resample(y, orig_sr=sr0, target_sr=SR)
    y = y[: SR * 6].astype(np.float32)
    if len(y) < SR // 50 or np.abs(y).max() < 1e-8:
        return None
    y = y / (np.abs(y).max() + 1e-9)

    f, m = _partials(y, SR)
    if len(f) < 3:
        return np.zeros(len(NAMES), dtype=np.float32)
    mem = _template_fit(f, m, MEMBRANE)
    bar = _template_fit(f, m, BAR)
    har = _template_fit(f, m, HARMONIC)
    best = float(np.argmax([mem, bar, har]))
    B = _inharmonicity_B(f)
    dens = len(f) / max((f[-1] - f[0]) / 1000.0, 1e-6)
    irreg = float(np.mean(np.abs(np.diff(m)))) if len(m) > 1 else 0.0
    ratios = f / f[0]
    tuned = float(np.mean([np.min(np.abs(HARMONIC - r)) < 0.06 for r in ratios]))
    spread = float(np.std(np.diff(f))) if len(f) > 2 else 0.0
    v = np.array([mem, bar, har, best, mem - har, bar - har, B, f[0],
                  len(f), dens, irreg, spread, tuned], dtype=np.float32)
    return np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)


def load_aligned(paths):
    if not os.path.exists(CACHE):
        return None, None
    z = np.load(CACHE, allow_pickle=True)
    if str(z["version"]) != VERSION:
        return None, None
    have = {p: i for i, p in enumerate(list(z["paths"]))}
    mask = np.array([p in have for p in paths])
    F = np.array([z["F"][have[p]] for p in paths if p in have], dtype=np.float32)
    return F, mask


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    z = np.load(os.path.join(SD, "corpus_v2.npz"), allow_pickle=True)
    paths = list(z["paths"])
    done = {}
    if os.path.exists(CACHE):
        c = np.load(CACHE, allow_pickle=True)
        if str(c["version"]) == VERSION:
            done = {p: c["F"][i] for i, p in enumerate(list(c["paths"]))}
    todo = [p for p in paths if p not in done]
    print(f"{len(paths)} files, {len(todo)} to compute")
    if todo:
        from multiprocessing import Pool
        import time
        t0 = time.time()
        with Pool(a.workers) as pool:
            for i, (p, r) in enumerate(zip(todo, pool.imap(extract, todo, chunksize=4))):
                if r is not None:
                    done[p] = r
                if (i + 1) % 200 == 0:
                    print(f"  {i+1}/{len(todo)} {(i+1)/(time.time()-t0):.1f}/s", flush=True)
    keep = [p for p in paths if p in done]
    F = np.array([done[p] for p in keep], dtype=np.float32)
    tmp = CACHE + ".tmp.npz"
    np.savez(tmp, F=F, paths=np.array(keep, dtype=object),
             names=np.array(NAMES, dtype=object), version=VERSION)
    os.replace(tmp, CACHE)
    print(f"wrote {os.path.basename(CACHE)}: {F.shape}")


if __name__ == "__main__":
    main()
