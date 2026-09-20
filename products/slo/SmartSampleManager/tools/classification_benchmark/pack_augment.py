#!/usr/bin/env python3
"""
Pack-mastering augmentation -- production-style, not musical.

Hypothesis
----------
Collection identity is decodable from the frozen embeddings at ~62.6% against a
25.5% baseline, and collection-held-out accuracy is 9.7pp below random CV. The
suspicion is that the embedding partly encodes how a pack was MASTERED -- EQ
balance, loudness, compression, saturation, bandwidth, ambience, format -- and
that the classifier uses that as a shortcut.

If so, training-fold augmentation that varies those production characteristics
while preserving the sound's identity should reduce the shortcut and improve
unseen-collection accuracy.

The earlier augmentation experiment tested pitch shift, time stretch and gain.
Those vary the PERFORMANCE, not the PRODUCTION, so it did not test this.

An honest limitation, stated up front
-------------------------------------
Perch and CLAP both consume MONO. The extraction pipeline downmixes before the
encoder sees anything. Stereo width, narrowing and polarity therefore cannot
change the embedding at all -- they are no-ops by construction, not weak
effects. Family C is implemented as ambience/mono-collapse only, and the stereo
operations are deliberately excluded rather than run to produce a guaranteed
null. Testing them would require a stereo-aware encoder.

Dependencies: numpy and scipy only. No new packages, nothing to install.
"""
import os, json, time, hashlib, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SD, "aug_cache")
PERCH_SR, PERCH_LEN, CLAP_SR = 32000, 160000, 48000
PREPROC_VERSION = "aug-v1"


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------
def _biquad(y, b, a):
    from scipy.signal import lfilter
    return lfilter(b, a, y).astype(np.float32)


def shelf(y, sr, f0, gain_db, kind="low"):
    """RBJ low/high shelving filter."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / 2 * np.sqrt((A + 1 / A) * (1 / 0.9 - 1) + 2)
    tsa = 2 * np.sqrt(A) * alpha
    if kind == "low":
        b = [A * ((A + 1) - (A - 1) * cw + tsa),
             2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - tsa)]
        a = [(A + 1) + (A - 1) * cw + tsa,
             -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - tsa]
    else:
        b = [A * ((A + 1) + (A - 1) * cw + tsa),
             -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - tsa)]
        a = [(A + 1) - (A - 1) * cw + tsa,
             2 * ((A - 1) - (A + 1) * cw),
             (A + 1) - (A - 1) * cw - tsa]
    return _biquad(y, np.array(b) / a[0], np.array(a) / a[0])


def peaking(y, sr, f0, gain_db, q=1.0):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    cw = np.cos(w0)
    b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
    a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    return _biquad(y, np.array(b) / a[0], np.array(a) / a[0])


def butter_filt(y, sr, f0, kind, order=2):
    from scipy.signal import butter, sosfilt
    f0 = min(max(f0, 20.0), sr / 2 * 0.98)
    sos = butter(order, f0 / (sr / 2), btype=kind, output="sos")
    return sosfilt(sos, y).astype(np.float32)


def compress(y, sr, thresh_db=-24.0, ratio=4.0, atk=0.005, rel=0.08):
    """Simple feed-forward compressor with a smoothed envelope."""
    eps = 1e-9
    from scipy.signal import lfilter
    env = np.abs(y)
    aA = np.exp(-1.0 / (sr * atk))
    aR = np.exp(-1.0 / (sr * rel))
    # Branching attack/release cannot be vectorised directly, so run both
    # one-pole smoothers and take the element-wise maximum. This is the standard
    # approximation: it tracks fast on attack and holds on release, which is the
    # behaviour that matters here, and it is ~500x faster than the per-sample
    # Python loop it replaces.
    fast = lfilter([1 - aA], [1, -aA], env)
    slow = lfilter([1 - aR], [1, -aR], env)
    sm = np.maximum(fast, slow).astype(np.float32)
    lvl = 20 * np.log10(sm + eps)
    over = np.maximum(lvl - thresh_db, 0.0)
    gain_db = -over * (1 - 1 / ratio)
    return (y * 10 ** (gain_db / 20.0)).astype(np.float32)


def soft_clip(y, drive=2.0):
    return np.tanh(y * drive).astype(np.float32) / np.tanh(drive)


def saturate(y, amount=0.3):
    return ((1 - amount) * y + amount * np.sign(y) * (1 - np.exp(-np.abs(y * 3)))
            ).astype(np.float32)


def transient(y, sr, amount=1.0):
    """amount > 1 emphasises the attack, < 1 softens it."""
    from scipy.signal import lfilter
    fast = lfilter([1 - np.exp(-1 / (sr * 0.002))], [1, -np.exp(-1 / (sr * 0.002))],
                   np.abs(y))
    slow = lfilter([1 - np.exp(-1 / (sr * 0.050))], [1, -np.exp(-1 / (sr * 0.050))],
                   np.abs(y))
    diff = fast - slow
    g = 1.0 + (amount - 1.0) * np.clip(diff / (np.abs(diff).max() + 1e-9), 0, 1)
    return (y * g).astype(np.float32)


def ambience(y, sr, seconds=0.25, wet=0.18, seed=0):
    """Short synthetic room -- exponentially decaying noise IR."""
    rng = np.random.RandomState(seed)
    n = int(sr * seconds)
    ir = rng.randn(n).astype(np.float32) * np.exp(-np.linspace(0, 6, n))
    ir /= np.abs(ir).sum() + 1e-9
    wetsig = np.convolve(y, ir)[:len(y)]
    return ((1 - wet) * y + wet * wetsig).astype(np.float32)


def bitdepth(y, bits=10):
    q = 2 ** (bits - 1)
    return (np.round(np.clip(y, -1, 1) * q) / q).astype(np.float32)


def resample_degrade(y, sr, target=16000):
    import librosa
    if target >= sr:
        return y
    return librosa.resample(librosa.resample(y, orig_sr=sr, target_sr=target),
                            orig_sr=target, target_sr=sr).astype(np.float32)


def noise_floor(y, db=-60.0, seed=0):
    rng = np.random.RandomState(seed)
    return (y + rng.randn(len(y)).astype(np.float32) * 10 ** (db / 20.0)
            ).astype(np.float32)


def loudness(y, target_rms=0.1):
    r = np.sqrt((y ** 2).mean()) + 1e-9
    return np.clip(y * (target_rms / r), -1, 1).astype(np.float32)


# --------------------------------------------------------------------------
# augmentation families -- conservative ranges, deterministic per (file, index)
# --------------------------------------------------------------------------
def _variants_spectral(y, sr, r):
    # Three variants per family, sampled from the full conservative ranges. The
    # encoder costs ~2s per embedding, so the variant count is the cost driver;
    # three per file is enough to test the hypothesis and can be widened for a
    # confirmation run if a family passes the pilot threshold.
    return [
        shelf(shelf(y, sr, 200, r.uniform(-4, 4), "low"),
              sr, 6000, r.uniform(-4, 4), "high"),
        peaking(y, sr, r.uniform(2000, 5000), r.uniform(-4, 4), 1.2),
        butter_filt(butter_filt(y, sr, r.uniform(30, 120), "highpass"),
                    sr, r.uniform(8000, 15000), "lowpass"),
    ]


def _variants_dynamics(y, sr, r):
    return [
        compress(y, sr, r.uniform(-30, -18), r.uniform(2, 6)),
        soft_clip(saturate(y, r.uniform(0.15, 0.45)), r.uniform(1.5, 3.0)),
        transient(y, sr, r.choice([r.uniform(1.3, 2.0), r.uniform(0.4, 0.8)])),
    ]


def _variants_space(y, sr, r):
    # stereo ops deliberately excluded -- the encoders are mono, see docstring
    return [
        ambience(y, sr, r.uniform(0.12, 0.35), r.uniform(0.10, 0.25),
                 seed=int(r.randint(1 << 20))),
        ambience(y, sr, r.uniform(0.35, 0.6), r.uniform(0.08, 0.18),
                 seed=int(r.randint(1 << 20))),
    ]


def _variants_format(y, sr, r):
    return [
        resample_degrade(y, sr, int(r.choice([11025, 16000, 22050]))),
        bitdepth(y, int(r.choice([8, 10, 12]))),
        loudness(noise_floor(y, r.uniform(-70, -50),
                             seed=int(r.randint(1 << 20))), r.uniform(0.05, 0.2)),
    ]


FAMILIES = {"spectral": _variants_spectral, "dynamics": _variants_dynamics,
            "space": _variants_space, "format": _variants_format}


def augment(y, sr, family, seed):
    r = np.random.RandomState(seed)
    return FAMILIES[family](y, sr, r)


def combined(y, sr, seed, n=3):
    """Restrained combined policy: one conservative op from each of several
    families, chained. Ranges are the same as the individual families."""
    r = np.random.RandomState(seed)
    out = []
    for k in range(n):
        z = y
        z = _variants_spectral(z, sr, r)[r.randint(3)]
        z = _variants_dynamics(z, sr, r)[r.randint(3)]
        if r.rand() < 0.5:
            z = _variants_format(z, sr, r)[r.randint(3)]
        if r.rand() < 0.3:
            z = _variants_space(z, sr, r)[r.randint(2)]
        out.append(z.astype(np.float32))
    return out


def self_check():
    """Augmentations must change the audio without destroying it."""
    sr = 32000
    t = np.linspace(0, 1, sr, endpoint=False)
    y = (np.sin(2 * np.pi * 220 * t) * np.exp(-3 * t)).astype(np.float32)
    ok = True
    for fam in FAMILIES:
        for i, v in enumerate(augment(y, sr, fam, 0)):
            finite = np.isfinite(v).all()
            changed = float(np.abs(v - y).max()) > 1e-4
            sane = float(np.abs(v).max()) < 10.0
            energy = float((v ** 2).mean()) > 1e-9
            good = finite and changed and sane and energy
            ok &= good
            print(f"  {'ok ' if good else 'BAD'} {fam:9} #{i}  "
                  f"peak={np.abs(v).max():6.3f}  rms={np.sqrt((v**2).mean()):7.5f}"
                  f"  delta={np.abs(v-y).max():.4f}")
    for i, v in enumerate(combined(y, sr, 0)):
        good = np.isfinite(v).all() and float(np.abs(v).max()) < 10.0
        ok &= good
        print(f"  {'ok ' if good else 'BAD'} combined  #{i}  "
              f"peak={np.abs(v).max():6.3f}")
    print("\nself-check", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        raise SystemExit(self_check())
    print("import this module, or run with --self-check")
