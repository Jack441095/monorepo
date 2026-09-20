#!/usr/bin/env python3
"""
Full-file spectral features for LOOP sub-classification.

The atonal-hit detector (drum_detector_features) is attack-focused: f0 from
the first 120ms, onset density, MFCCs of a single hit. That is right for
one-shots but blind to what separates loop TYPES, which is where the energy
sits across the whole bar:

  Drum Loop        strong sub/low (the kick)      sub~0.13 low~0.17
  Percussion Loop  mid, little sub (no kick)      sub~0.07 mid~0.29
  Hi-Hat Loop      high only, no low end          low~0.01 high~0.62 vhigh~0.28
  Foley Loop       mid-heavy, diffuse             mid~0.39

Measured: Drum Loop vs Percussion Loop reaches 86.8% on these features alone,
versus 36-49% from the one-shot detector. Hi-Hat Loop is near-trivial (no low
end, high centroid).
"""
import numpy as np, soundfile as sf, librosa, warnings
warnings.filterwarnings("ignore")

BANDS = [(0, 100), (100, 300), (300, 2000), (2000, 8000), (8000, 11025)]
NAMES = ["sub", "low", "mid", "high", "vhigh", "kick", "centroid",
         "flatness", "lowmid_ratio", "onset_reg"]


def extract(path):
    """Full-file loop profile -> 10-d feature vector, or None on failure."""
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
        if y.ndim > 1: y = y.mean(1)
        if len(y) < 2048: return None
        if sr != 22050:
            y = librosa.resample(y, orig_sr=sr, target_sr=22050); sr = 22050

        S = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        fr = np.fft.rfftfreq(len(y), 1 / sr)
        tot = S.sum() + 1e-9
        bf = [float(S[(fr >= lo) & (fr < hi)].sum() / tot) for lo, hi in BANDS]

        # kick presence: strong low-band onsets (a four-on-the-floor kick fires
        # regular low-frequency transients; a perc/hat loop does not)
        oe_low = librosa.onset.onset_strength(y=y, sr=sr, fmax=200)
        kick = float(np.mean(oe_low > oe_low.mean() + oe_low.std())) if oe_low.size else 0.0

        centroid = float((fr * S).sum() / tot) / (sr / 2)
        # spectral flatness (tonal vs noisy) over the whole file
        flat = float(np.exp(np.mean(np.log(S + 1e-9))) / (S.mean() + 1e-9))
        lowmid = bf[0] + bf[1]
        lowmid_ratio = float(lowmid / (bf[2] + bf[3] + 1e-9))

        # onset regularity: std of inter-onset intervals (a tight loop is
        # regular; foley/ambient is not). Lower = more regular.
        oe = librosa.onset.onset_strength(y=y, sr=sr)
        on = librosa.util.peak_pick(oe, pre_max=3, post_max=3, pre_avg=5,
                                    post_avg=5, delta=0.2, wait=5)
        if len(on) >= 3:
            iois = np.diff(on).astype(float)
            reg = float(np.std(iois) / (np.mean(iois) + 1e-9))
        else:
            reg = 1.0
        reg = min(reg, 2.0) / 2.0

        return np.array(bf + [kick, centroid, flat, lowmid_ratio, reg], dtype=np.float32)
    except Exception:
        return None


if __name__ == "__main__":
    import csv
    from collections import defaultdict
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    from sklearn.metrics import classification_report
    rows = [r for r in csv.DictReader(open("verified_drums.csv"))]
    LOOPS = ["Drum Loop", "Percussion Loop", "Hi-Hat Loop", "Foley Loop", "Chord Loop"]
    X, y = [], []
    for r in rows:
        if r["label"] not in LOOPS: continue
        f = extract(r["path"])
        if f is not None: X.append(f); y.append(r["label"])
    X, y = np.array(X), np.array(y)
    from collections import Counter
    viable = [c for c, n in Counter(y).items() if n >= 10]
    m = np.isin(y, viable)
    print(f"loop sub-classification, {m.sum()} files, classes {viable}")
    pred = cross_val_predict(RandomForestClassifier(n_estimators=300, class_weight="balanced",
                             random_state=0), X[m], y[m], cv=5)
    print(f"accuracy: {100*(pred==y[m]).mean():.1f}%\n")
    print(classification_report(y[m], pred, digits=3))
