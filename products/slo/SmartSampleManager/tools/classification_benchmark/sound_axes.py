#!/usr/bin/env python3
"""
The four gaps: inharmonicity, pitch trajectory, modulation, provenance.

Existing features cover two of the four families that describe a sound well
(SPECTRUM: centroid/rolloff/flatness/contrast/ZCR/HPSS; ENVELOPE: attack/decay/
sustain/onsets/periodicity). Two are thin or absent:

  MOTION      how the spectrum CHANGES over time. We take static averages, so a
              tom (a kick whose pitch falls) and a riser (a pad whose pitch
              climbs) look like their static counterparts.
  PROVENANCE  artefacts of how the file was MADE and RECORDED, rather than what
              it contains. Not a function signal -- a source signal. This is the
              axis that should serve Foley, which section 19 established is a
              source attribute, not a class.

Four feature groups, all genuinely new to this project:

1. INHARMONICITY  -- do the partials sit at integer multiples of f0?
     We already measure how MUCH energy is harmonic (HPSS ratio). We have never
     measured how harmonic it IS. Strings and voices are near-integer; bells,
     cymbals and metal are strongly inharmonic. Targets Crash/Hi-Hat/Ride/Tom,
     a known weak group, rather than general accuracy.
     Includes tristimulus and odd/even partial balance (classic timbre
     descriptors) and the voiced fraction -- for cymbals, f0 estimation FAILING
     is itself the signal.

2. PITCH TRAJECTORY -- f0 contour, not f0. Slope in semitones/second, total
     range, direction, monotonicity. Separates Tom from Kick, Riser from Pad,
     an 808 glide from an 808 hit.

3. MODULATION SPECTRUM -- the rate at which amplitude wobbles. 4-8 Hz is heard
     as roughness/grit, 0.1-2 Hz as slow evolution. This is how listeners
     actually describe texture, and we measure none of it. Relevant to the
     user's observation that "dirty" means slightly distorted.

4. PROVENANCE -- spectral ceiling (a hard lowpass at 11 or 16 kHz means a
     vintage sampled record, not a synth), noise floor, DC offset, clipping,
     stereo correlation and mid/side balance, native sample rate.

Prior expectation, recorded before running: handcrafted features previously
added +0.0pp on top of Perch+CLAP (section 26). The reason these may differ is
that groups 1, 3 and 4 are new AXES rather than new coordinates on axes already
spanned -- but the pattern all project has been that each new signal re-explains
the same easy files. Measured, not asserted.
"""
import os, csv, math, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SD, "verified_drums.csv")
CACHE = os.path.join(SD, "sound_axes_feats.npz")

INHARM = ["inharm", "odd_even", "tri1", "tri2", "tri3", "voiced_frac",
          "comb_score", "n_partials"]
PITCH = ["f0_med", "f0_slope", "f0_range", "f0_dir", "f0_mono", "f0_std"]
MODUL = ["mod_slow", "mod_rough", "mod_flutter", "mod_peak_hz", "mod_peak_str"]
PROV = ["ceiling_hz", "ceiling_ratio", "noise_floor_db", "dc_offset",
        "clip_frac", "stereo_corr", "side_mid", "native_sr", "crest_db"]
FEATURE_NAMES = INHARM + PITCH + MODUL + PROV
GROUPS = {"inharmonicity": INHARM, "pitch trajectory": PITCH,
          "modulation": MODUL, "provenance": PROV}

ANALYSIS_SR = 22050
MAX_SECONDS = 6.0


def _inharmonicity(y, sr, f0_med, voiced_frac):
    """Magnitude-weighted deviation of spectral peaks from integer multiples."""
    import librosa
    from scipy.signal import find_peaks
    n_fft = 4096
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=1024)).mean(1)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    if S.max() <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0
    Sn = S / S.max()
    pk, _ = find_peaks(Sn, height=0.05, distance=3)
    pk = pk[freqs[pk] > 55.0]
    if len(pk) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0
    order = np.argsort(-Sn[pk])[:14]
    pf, pm = freqs[pk[order]], Sn[pk[order]]

    # fall back to the strongest low peak when pitch tracking found nothing
    f0 = f0_med if (f0_med and f0_med > 20 and voiced_frac > 0.05) else float(pf.min())
    if f0 <= 20:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, len(pf)

    ratios = pf / f0
    n = np.clip(np.round(ratios), 1, None)
    # relative deviation from the nearest integer multiple, weighted by loudness
    dev = np.abs(pf - n * f0) / (n * f0)
    w = pm / (pm.sum() + 1e-9)
    inharm = float((dev * w).sum())

    near = dev < 0.05                      # partials that ARE harmonic
    odd = float(pm[near & (n % 2 == 1)].sum())
    even = float(pm[near & (n % 2 == 0)].sum())
    odd_even = odd / (odd + even + 1e-9)

    # tristimulus: energy share of the fundamental / partials 2-4 / partials 5+
    tot = pm[near].sum() + 1e-9
    tri1 = float(pm[near & (n == 1)].sum() / tot)
    tri2 = float(pm[near & (n >= 2) & (n <= 4)].sum() / tot)
    tri3 = float(pm[near & (n >= 5)].sum() / tot)

    # how much of the loud spectrum lands on an integer comb at all
    comb = float(w[near].sum())
    return inharm, odd_even, tri1, tri2, tri3, comb, int(len(pf))


def _pitch(y, sr):
    """f0 CONTOUR statistics -- slope, range, direction, monotonicity."""
    import librosa
    try:
        f0, voiced, _ = librosa.pyin(y, fmin=50, fmax=2000, sr=sr,
                                     frame_length=2048, hop_length=512)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    v = np.isfinite(f0) & (voiced if voiced is not None else True)
    voiced_frac = float(v.mean()) if len(v) else 0.0
    if v.sum() < 4:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, voiced_frac
    t = np.arange(len(f0))[v] * 512.0 / sr
    semis = 12.0 * np.log2(f0[v] / (np.median(f0[v]) + 1e-9))
    slope = float(np.polyfit(t, semis, 1)[0]) if np.ptp(t) > 1e-3 else 0.0
    rng = float(semis.max() - semis.min())
    direction = float(np.sign(semis[-1] - semis[0]))
    d = np.diff(semis)
    mono = float(abs(np.sign(d).sum()) / max(len(d), 1))   # 1 = steady glide
    return (float(np.median(f0[v])), slope, rng, direction, mono,
            float(semis.std()), voiced_frac)


def _modulation(y, sr):
    """Where the amplitude envelope wobbles: slow evolution vs roughness."""
    import librosa
    hop = 256
    env = librosa.feature.rms(y=y, hop_length=hop)[0]
    if len(env) < 16:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    sr_env = sr / hop
    e = env - env.mean()
    win = np.hanning(len(e))
    sp = np.abs(np.fft.rfft(e * win))
    fq = np.fft.rfftfreq(len(e), 1.0 / sr_env)
    tot = sp.sum() + 1e-9

    def band(lo, hi):
        m = (fq >= lo) & (fq < hi)
        return float(sp[m].sum() / tot)

    slow, rough, flutter = band(0.3, 2.0), band(2.0, 8.0), band(8.0, 30.0)
    m = fq > 0.3
    if m.sum():
        k = int(np.argmax(sp[m]))
        peak_hz, peak_str = float(fq[m][k]), float(sp[m][k] / tot)
    else:
        peak_hz = peak_str = 0.0
    return slow, rough, flutter, peak_hz, peak_str


def _provenance(path):
    """Recording artefacts -- computed at NATIVE rate, stereo preserved."""
    import soundfile as sf
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        return None
    if y.shape[0] < 256:
        return None
    y = y[: int(sr * MAX_SECONDS)]
    mono = y.mean(1)

    # stereo relationship
    if y.shape[1] >= 2:
        L, R = y[:, 0], y[:, 1]
        if L.std() > 1e-9 and R.std() > 1e-9:
            stereo_corr = float(np.corrcoef(L, R)[0, 1])
        else:
            stereo_corr = 1.0
        mid, side = (L + R) / 2, (L - R) / 2
        side_mid = float(np.sqrt((side ** 2).mean()) /
                         (np.sqrt((mid ** 2).mean()) + 1e-9))
    else:
        stereo_corr, side_mid = 1.0, 0.0

    # spectral ceiling: a hard lowpass edge betrays a resampled/vintage source
    n_fft = 4096
    sp = np.abs(np.fft.rfft(mono[:n_fft] * np.hanning(min(len(mono), n_fft)),
                            n=n_fft))
    fq = np.fft.rfftfreq(n_fft, 1.0 / sr)
    if sp.max() > 0:
        cum = np.cumsum(sp) / sp.sum()
        ceiling = float(fq[int(np.searchsorted(cum, 0.995))])
    else:
        ceiling = 0.0
    ceiling_ratio = ceiling / (sr / 2.0)

    import librosa
    rms = librosa.feature.rms(y=mono, hop_length=512)[0]
    peak = float(rms.max()) + 1e-12
    floor = float(np.percentile(rms, 5))
    noise_floor_db = float(20 * np.log10(floor / peak + 1e-12))
    crest_db = float(20 * np.log10(np.abs(mono).max() /
                                   (np.sqrt((mono ** 2).mean()) + 1e-12) + 1e-12))
    dc = float(abs(mono.mean()))
    clip = float((np.abs(mono) > 0.999).mean())
    return [ceiling, ceiling_ratio, noise_floor_db, dc, clip, stereo_corr,
            side_mid, float(sr), crest_db]


def features(path):
    import librosa, soundfile as sf
    prov = _provenance(path)
    if prov is None:
        return None
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if y.ndim > 1:
        y = y.mean(1)
    y = y[: int(sr * MAX_SECONDS)]
    if sr != ANALYSIS_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=ANALYSIS_SR)
    sr = ANALYSIS_SR
    if len(y) < sr // 20 or not np.isfinite(y).all() or np.abs(y).max() < 1e-7:
        return None
    y = y / (np.abs(y).max() + 1e-9)

    f0_med, slope, rng, direction, mono, f0_std, vf = _pitch(y, sr)
    inh = _inharmonicity(y, sr, f0_med, vf)
    mod = _modulation(y, sr)
    vec = (list(inh[:5]) + [vf] + list(inh[5:]) +
           [f0_med, slope, rng, direction, mono, f0_std] + list(mod) + prov)
    v = np.array(vec, dtype=np.float32)
    if len(v) != len(FEATURE_NAMES):
        return None
    return np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)


def build(paths, workers):
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        if list(z["paths"]) == paths:
            print("loaded cached features")
            return z["X"], z["ok"]
    from multiprocessing import Pool
    with Pool(workers) as p:
        res = p.map(features, paths, chunksize=2)
    ok = np.array([r is not None for r in res])
    X = np.zeros((len(paths), len(FEATURE_NAMES)), dtype=np.float32)
    for i, r in enumerate(res):
        if r is not None:
            X[i] = r
    np.savez(CACHE, X=X, ok=ok, paths=np.array(paths, dtype=object))
    print(f"extracted {int(ok.sum())}/{len(paths)}")
    return X, ok


def dprime(a, b):
    sd = math.sqrt((a.var() + b.var()) / 2) + 1e-9
    return (a.mean() - b.mean()) / sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-class", type=int, default=15)
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]
    y = np.array([r["label"] for r in rows])
    print(f"{len(paths)} by-ear labelled files\n")

    X, ok = build(paths, a.workers)
    Xo, yo = X[ok], y[ok]
    d = {n: Xo[:, i] for i, n in enumerate(FEATURE_NAMES)}

    # ---- does inharmonicity do the specific job it was proposed for? ----
    print("TARGETED TEST -- inharmonicity on the metal/noise confusions")
    print("(the reason this feature group was proposed; general accuracy is not "
          "the claim)")
    pairs = [("Crash", "Hi-Hat"), ("Crash", "Snare"), ("Snare", "Clap"),
             ("Kick", "Percussion"), ("Hi-Hat", "Clap")]
    keyf = ["inharm", "comb_score", "voiced_frac", "tri3", "odd_even"]
    print(f"  {'pair':>22}" + "".join(f"{k:>13}" for k in keyf))
    for c1, c2 in pairs:
        m1, m2 = yo == c1, yo == c2
        if m1.sum() < 8 or m2.sum() < 8:
            continue
        line = f"  {c1+' vs '+c2:>22}"
        for k in keyf:
            line += f"{dprime(d[k][m1], d[k][m2]):13.2f}"
        print(line)
    print("  (|d-prime| >= 0.8 is a usable separation; >= 1.2 is strong)\n")

    from collections import Counter
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict
    cnt = Counter(yo)
    viable = [c for c in cnt if cnt[c] >= a.min_class]
    m = np.isin(yo, viable)
    Xv, yv = Xo[m], yo[m]
    print(f"evaluating on {m.sum()} files, {len(viable)} classes\n")

    print("each NEW axis group alone (random forest):")
    for g, names in GROUPS.items():
        idx = [FEATURE_NAMES.index(n) for n in names]
        rf = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                    random_state=0, n_jobs=-1)
        p = cross_val_predict(rf, Xv[:, idx], yv, cv=5)
        print(f"  {g:22} ({len(names):2d}-D) {100*(p==yv).mean():5.1f}%")
    rf = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                random_state=0, n_jobs=-1)
    p = cross_val_predict(rf, Xv, yv, cv=5)
    print(f"  {'ALL FOUR':22} ({Xv.shape[1]:2d}-D) {100*(p==yv).mean():5.1f}%")
    print(f"  {'majority-class floor':22}        "
          f"{100*max(cnt[c] for c in viable)/m.sum():5.1f}%\n")

    # ---- the decisive test: do they ADD to the deployed stack? ----
    bio = os.path.join(SD, "bioacoustic_emb.npz")
    if not os.path.exists(bio):
        print("no bioacoustic_emb.npz -- skipping the additive test")
        return
    z = np.load(bio)
    Xp, Xc = z["perch"], z["clap"]
    if len(Xp) != len(paths):
        print(f"\nSKIPPING additive test: embedding cache holds {len(Xp)} rows "
              f"but {len(paths)} labelled files are on disk now.\n"
              f"Rows would not correspond -- refusing to produce a number that "
              f"looks valid.\nRebuild with bioacoustic_bakeoff.py.")
        return
    Xp, Xc = Xp[ok][m], Xc[ok][m]

    def run(M, name):
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=3000,
                                               class_weight="balanced"))
        p = cross_val_predict(clf, M, yv, cv=5)
        acc = 100 * (p == yv).mean()
        print(f"  {name:40} {acc:5.1f}%")
        return p, acc

    print("THE DECISIVE TEST -- do the new axes add to the deployed stack?")
    base_p, base = run(np.hstack([Xp, Xc]), "BASELINE Perch+CLAP")
    for g, names in GROUPS.items():
        idx = [FEATURE_NAMES.index(n) for n in names]
        _, acc = run(np.hstack([Xp, Xc, Xv[:, idx]]), f"+ {g}")
        print(f"  {'':40} {acc-base:+5.1f}pp")
    full_p, acc = run(np.hstack([Xp, Xc, Xv]), "+ ALL FOUR AXES")
    print(f"  {'':40} {acc-base:+5.1f}pp\n")

    print("per-class recall, baseline -> with all four axes:")
    print(f"  {'class':>16} {'n':>4} {'base':>7} {'+axes':>7} {'delta':>7}")
    for c in sorted(viable, key=lambda k: -cnt[k]):
        sel = yv == c
        b = 100 * (base_p[sel] == c).mean()
        f = 100 * (full_p[sel] == c).mean()
        print(f"  {c:>16} {int(sel.sum()):4d} {b:6.0f}% {f:6.0f}% {f-b:+6.0f}pp")


if __name__ == "__main__":
    main()
