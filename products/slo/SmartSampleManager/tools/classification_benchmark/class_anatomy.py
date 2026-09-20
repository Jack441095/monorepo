#!/usr/bin/env python3
"""
What is actually inside the incoherent classes?

Measured today: Percussion (-0.154), Percussion Loop (-0.114), Foley (-0.102)
and Synth One-Shot (-0.005) have NEGATIVE silhouette -- the average file in each
sits closer to some other class than to its own. They name several unrelated
sounds.

Handcrafted physics FEATURES are a closed route: inharmonicity, pitch
trajectory, modulation and provenance each added +0.0pp on top of the encoders,
which already capture the physics. This does something different -- it uses
physics to DEFINE, not to predict.

Method: cluster inside each incoherent class using the encoder embedding (which
knows what things sound like), then describe each cluster with interpretable
physical measurements (attack, decay, sustain, centroid, bandwidth, harmonicity,
onset density). The clusters say where the natural boundaries are; the physics
says what to CALL them and how a human should tell them apart.

Output is a labelling definition, not a feature vector.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SD, "results_class_anatomy.json")
CORPUS = os.path.join(SD, "corpus_v2.npz")
NATIVE_SR = 32000


def physics(path):
    """Interpretable descriptors a human can also hear and reason about."""
    import soundfile as sf, librosa
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if y.ndim > 1:
        y = y.mean(1)
    if sr != NATIVE_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=NATIVE_SR)
    sr = NATIVE_SR
    y = y[: sr * 10]
    if len(y) < sr // 50 or np.abs(y).max() < 1e-7:
        return None
    y = y / (np.abs(y).max() + 1e-9)
    dur = len(y) / sr
    hop = 256
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    peak_i = int(np.argmax(rms))
    pk = float(rms.max()) + 1e-9

    # attack: time from 10% to 90% of peak, before the peak
    pre = rms[: peak_i + 1]
    if len(pre) > 1:
        lo = np.where(pre >= 0.1 * pk)[0]
        hi = np.where(pre >= 0.9 * pk)[0]
        attack = ((hi[0] - lo[0]) * hop / sr) if len(lo) and len(hi) else 0.0
    else:
        attack = 0.0
    # decay: time from peak to 10% of peak
    post = rms[peak_i:]
    below = np.where(post <= 0.1 * pk)[0]
    decay = (below[0] * hop / sr) if len(below) else (len(post) * hop / sr)
    # sustain: mean energy of the middle third relative to peak
    third = len(rms) // 3
    sustain = float(rms[third:2 * third].mean() / pk) if third > 0 else 0.0

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    cent = float(librosa.feature.spectral_centroid(S=S, sr=sr).mean())
    bw = float(librosa.feature.spectral_bandwidth(S=S, sr=sr).mean())
    flat = float(librosa.feature.spectral_flatness(S=S).mean())
    zcr = float(librosa.feature.zero_crossing_rate(y, hop_length=hop).mean())
    try:
        H, P = librosa.decompose.hpss(S)
        harm = float(H.sum() / (H.sum() + P.sum() + 1e-9))
    except Exception:
        harm = 0.0
    oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onsets = len(librosa.onset.onset_detect(onset_envelope=oe, sr=sr, hop_length=hop))
    lo_e = float((S[:int(200/(sr/2)*S.shape[0])] ** 2).sum() / ((S ** 2).sum() + 1e-9))
    return dict(duration=dur, attack_ms=attack * 1000, decay_s=decay,
                sustain=sustain, centroid_hz=cent, bandwidth_hz=bw,
                flatness=flat, zcr=zcr, harmonicity=harm,
                onsets_per_s=onsets / max(dur, 1e-6), low_energy=lo_e)


NAMES = ["duration", "attack_ms", "decay_s", "sustain", "centroid_hz",
         "bandwidth_hz", "flatness", "zcr", "harmonicity", "onsets_per_s",
         "low_energy"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="Percussion,Synth One-Shot,Percussion Loop,Foley")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    z = np.load(CORPUS, allow_pickle=True)
    paths = list(z["paths"]); X = z["emb"]; y = np.array(z["labels"])
    targets = [c.strip() for c in a.classes.split(",")]

    from multiprocessing import Pool
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score

    out = {}
    for cls in targets:
        idx = np.where(y == cls)[0]
        if len(idx) < 12:
            print(f"{cls}: only {len(idx)} examples, skipping\n"); continue
        print(f"\n{'='*74}\n{cls}  ({len(idx)} files)\n{'='*74}")
        with Pool(a.workers) as pool:
            feats = pool.map(physics, [paths[i] for i in idx])
        ok = [j for j, f in enumerate(feats) if f is not None]
        idx, feats = idx[ok], [feats[j] for j in ok]
        F = np.array([[f[n] for n in NAMES] for f in feats])

        Z = StandardScaler().fit_transform(X[idx])
        Z = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
        best = None
        for k in range(2, min(a.k, len(idx) // 4) + 1):
            lab = KMeans(k, n_init=10, random_state=0).fit_predict(Z)
            if len(set(lab)) < 2:
                continue
            s = silhouette_score(Z, lab, metric="cosine")
            if best is None or s > best[0]:
                best = (s, k, lab)
        if best is None:
            print("  could not cluster"); continue
        s, k, lab = best
        print(f"  best split: {k} clusters, silhouette {s:.3f}")
        cl = {}
        for c in range(k):
            m = lab == c
            med = {n: float(np.median(F[m, i])) for i, n in enumerate(NAMES)}
            ex = [os.path.basename(paths[i])[:40] for i in idx[m][:3]]
            cl[f"cluster_{c}"] = {"n": int(m.sum()), "median": med,
                                 "examples": ex}
            print(f"\n  cluster {c}: {m.sum()} files")
            print(f"    attack {med['attack_ms']:7.1f} ms   decay {med['decay_s']:5.2f} s"
                  f"   sustain {med['sustain']:.2f}   dur {med['duration']:5.2f} s")
            print(f"    centroid {med['centroid_hz']:7.0f} Hz  bandwidth "
                  f"{med['bandwidth_hz']:7.0f} Hz  harmonicity {med['harmonicity']:.2f}")
            print(f"    zcr {med['zcr']:.3f}   flatness {med['flatness']:.4f}   "
                  f"onsets/s {med['onsets_per_s']:.2f}   low<200Hz {med['low_energy']:.2f}")
            for e in ex:
                print(f"      e.g. {e}")
        # which physical measurement separates the clusters best?
        print(f"\n  most discriminative physics (|d-prime| between clusters):")
        seps = []
        for i, n in enumerate(NAMES):
            vals = [F[lab == c, i] for c in range(k)]
            d = 0.0
            for p in range(k):
                for q in range(p + 1, k):
                    sd = np.sqrt((vals[p].var() + vals[q].var()) / 2) + 1e-9
                    d = max(d, abs(vals[p].mean() - vals[q].mean()) / sd)
            seps.append((n, d))
        for n, d in sorted(seps, key=lambda t: -t[1])[:5]:
            print(f"    {n:16} {d:5.2f}")
        cl["discriminative"] = {n: round(float(d), 3) for n, d in seps}
        cl["silhouette"] = round(float(s), 3)
        out[cls] = cl

    json.dump(out, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
