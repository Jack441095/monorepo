#!/usr/bin/env python3
"""
Multi-window DSP features -- targeting FORM, not category.

Rationale, stated honestly. Handcrafted DSP features have failed twice in this
project (+0.0pp), because they were WHOLE-FILE descriptors of properties the
encoders already capture. This is a different bet: the remaining errors are
concentrated in TEMPORAL/FORM confusions --

  Percussion vs Percussion Loop      one hit or many?
  Top Loop vs Hi-Hat Loop            which layer dominates over time?
  Foley vs Percussion                does it evolve or decay?
  one-shot vs loop                   does the pattern repeat?
  Impact/SFX/Other-none boundary     is there structure at all?
  808/Reese vs bass hit              does the low end sustain?

-- and a whole-file average cannot express any of them. A per-window descriptor
can: "loud at the start and silent after" is a one-shot; "equally busy in every
third" is a loop. That contrast is the signal, and it is exactly what global
pooling destroys.

Windows: full, attack (0-120ms), early (0-1s), mid (middle third),
tail (last 25%), and three equal rhythm thirds for repetition.

Per window: transient strength, decay length, low-end energy, HF density,
spectral centroid, spectral flux, onset density, sustained tonal energy,
noise-vs-tonal balance. Plus cross-window CONTRASTS (early-vs-tail energy,
onset-rate consistency across thirds, rhythmic autocorrelation) and stereo
width, which is measured from the source file before any downmix.

Read-only. Never writes to, renames or moves a sample.
"""
import os, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

import feature_cache as fc

SD = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(SD, "mw_features_v1.npz")
DIGESTS = os.path.join(SD, "mw_features_digests_v1.json")
SR = 32000
VERSION = "mwf-v1"

WIN = ["full", "attack", "early", "mid", "tail"]
PER = ["transient", "decay_s", "low_energy", "hf_density", "centroid",
       "flux", "onset_rate", "sustain_tonal", "noise_ratio"]
CONTRAST = ["early_tail_ratio", "third_onset_cv", "rhythm_ac_peak",
            "rhythm_ac_lag", "repetition_score", "stereo_width",
            "stereo_corr", "duration", "crest", "silence_frac"]
NAMES = [f"{w}_{p}" for w in WIN for p in PER] + CONTRAST


def _win_feats(y, sr):
    """Nine descriptors for one window."""
    import librosa
    if len(y) < 256 or not np.isfinite(y).all() or np.abs(y).max() < 1e-8:
        return [0.0] * len(PER)
    hop = 256
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    pk = float(rms.max()) + 1e-9
    # transient strength: peak-to-mean of the onset envelope
    oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    transient = float(oe.max() / (oe.mean() + 1e-9)) if len(oe) else 0.0
    # decay: peak to 10% of peak
    pi = int(np.argmax(rms))
    post = rms[pi:]
    below = np.where(post <= 0.1 * pk)[0]
    decay = float((below[0] if len(below) else len(post)) * hop / sr)
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    tot = (S ** 2).sum() + 1e-9
    low = float((S[freqs < 200] ** 2).sum() / tot)
    hf = float((S[freqs > 6000] ** 2).sum() / tot)
    cent = float(librosa.feature.spectral_centroid(S=S, sr=sr).mean())
    flux = float(np.mean(np.diff(S, axis=1).clip(min=0).sum(0))) if S.shape[1] > 1 else 0.0
    n_on = len(librosa.onset.onset_detect(onset_envelope=oe, sr=sr, hop_length=hop))
    dur = len(y) / sr
    onset_rate = n_on / max(dur, 1e-6)
    # sustained tonal energy: middle-third energy that is harmonic
    flat = float(librosa.feature.spectral_flatness(S=S).mean())
    third = len(rms) // 3
    sustain = float(rms[third:2 * third].mean() / pk) if third > 0 else 0.0
    return [transient, decay, low, hf, cent, flux, onset_rate,
            sustain * (1.0 - flat), flat]


def extract(path):
    import soundfile as sf, librosa
    try:
        y2, sr0 = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        return None
    if y2.shape[0] < 256:
        return None
    # stereo measured BEFORE downmix -- the encoders are mono, so this is the
    # only place width can be observed at all
    if y2.shape[1] >= 2:
        L, R = y2[:, 0], y2[:, 1]
        sc = float(np.corrcoef(L, R)[0, 1]) if L.std() > 1e-9 and R.std() > 1e-9 else 1.0
        mid, side = (L + R) / 2, (L - R) / 2
        sw = float(np.sqrt((side ** 2).mean()) / (np.sqrt((mid ** 2).mean()) + 1e-9))
    else:
        sc, sw = 1.0, 0.0
    y = y2.mean(1)
    if sr0 != SR:
        y = librosa.resample(y, orig_sr=sr0, target_sr=SR)
    y = y[: SR * 12].astype(np.float32)
    if np.abs(y).max() < 1e-8:
        return None
    y = y / (np.abs(y).max() + 1e-9)
    n = len(y); dur = n / SR

    wins = {
        "full":   y,
        "attack": y[: int(SR * 0.12)],
        "early":  y[: SR],
        "mid":    y[n // 3: 2 * n // 3],
        "tail":   y[int(n * 0.75):],
    }
    out = []
    for w in WIN:
        out += _win_feats(wins[w], SR)

    # ---- cross-window contrasts: the actual point of this layer ----------
    import librosa
    hop = 256
    rms = librosa.feature.rms(y=y, hop_length=hop)[0] + 1e-9
    q = len(rms) // 4
    early_e = float(rms[:q].mean()); tail_e = float(rms[-q:].mean())
    early_tail = float(tail_e / (early_e + 1e-9))          # ~0 one-shot, ~1 loop

    oe = librosa.onset.onset_strength(y=y, sr=SR, hop_length=hop)
    t3 = len(oe) // 3
    rates = []
    for k in range(3):
        seg = oe[k * t3:(k + 1) * t3]
        rates.append(len(librosa.onset.onset_detect(onset_envelope=seg, sr=SR,
                                                    hop_length=hop))
                     if len(seg) > 4 else 0)
    rates = np.array(rates, dtype=float)
    cv = float(rates.std() / (rates.mean() + 1e-9))        # low = steady = loop

    ac_peak = ac_lag = 0.0
    if len(oe) > 8:
        e = oe - oe.mean()
        ac = np.correlate(e, e, "full")[len(e) - 1:]
        if ac[0] > 1e-9:
            ac /= ac[0]
            lo = max(2, int(0.12 * SR / hop)); hi = max(lo + 2, len(ac) // 2)
            seg = ac[lo:hi]
            if len(seg):
                k = int(np.argmax(seg))
                ac_peak = float(seg[k] - np.median(seg))
                ac_lag = float((lo + k) * hop / SR)
    repetition = float(ac_peak * (1.0 - min(cv, 1.0)) * min(early_tail, 1.0))
    crest = float(np.abs(y).max() / (np.sqrt((y ** 2).mean()) + 1e-9))
    silence = float((rms < 0.02 * rms.max()).mean())
    out += [early_tail, cv, ac_peak, ac_lag, repetition, sw, sc, dur,
            crest, silence]
    v = np.array(out, dtype=np.float32)
    return np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)


def _verify_digests(cached_paths, cached_digests):
    """Return {path: index} for entries whose file content still matches.

    Entries without a recorded digest (legacy cache) or whose file now hashes
    differently are DROPPED -- a stale row is worse than a recomputed one.
    """
    if cached_digests is None:
        return {}
    idx = fc.DigestIndex(DIGESTS)
    ok = {}
    for i, (p, d) in enumerate(zip(cached_paths, cached_digests)):
        if idx.digest(p) == d:
            ok[p] = i
    idx.flush()
    return ok


def load_aligned(paths):
    if not os.path.exists(CACHE):
        return None, None
    z = np.load(CACHE, allow_pickle=True)
    if str(z["version"]) != VERSION:
        return None, None
    have = _verify_digests(list(z["paths"]),
                           list(z["digests"]) if "digests" in z else None)
    mask = np.array([p in have for p in paths])
    F = np.array([z["F"][have[p]] for p in paths if p in have], dtype=np.float32)
    assert len(F) == int(mask.sum()), "mw feature alignment failure"
    return F, mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()
    import eval_corpus_v2 as ec
    z = np.load(os.path.join(SD, "corpus_v2.npz"), allow_pickle=True)
    paths = list(z["paths"])
    digester = fc.DigestIndex(DIGESTS)
    done = {}
    digests = {}
    if os.path.exists(CACHE):
        c = np.load(CACHE, allow_pickle=True)
        if str(c["version"]) == VERSION:
            cd = list(c["digests"]) if "digests" in c else [None] * len(c["paths"])
            for i, p in enumerate(list(c["paths"])):
                d = digester.digest(p)
                if d is not None and d == cd[i]:
                    done[p] = c["F"][i]
                    digests[p] = d
            print(f"resuming: {len(done)} content-verified cached "
                  f"({len(list(c['paths'])) - len(done)} stale/legacy dropped)")
    todo = [p for p in paths if p not in done]
    print(f"{len(paths)} files, {len(todo)} to compute, {len(NAMES)} features each")
    if todo:
        from multiprocessing import Pool
        import time
        t0 = time.time()
        with Pool(a.workers) as pool:
            for i, (p, r) in enumerate(zip(todo, pool.imap(extract, todo, chunksize=4))):
                if r is not None:
                    done[p] = r
                    d = digester.digest(p)
                    if d is not None:
                        digests[p] = d
                if (i + 1) % 200 == 0:
                    print(f"  {i+1}/{len(todo)}  {(i+1)/(time.time()-t0):.1f}/s",
                          flush=True)
        digester.flush()
    keep = [p for p in paths if p in done]
    F = np.array([done[p] for p in keep], dtype=np.float32)
    tmp = CACHE + ".tmp.npz"
    np.savez(tmp, F=F, paths=np.array(keep, dtype=object),
             names=np.array(NAMES, dtype=object), version=VERSION,
             digests=np.array([digests.get(p, "") for p in keep], dtype=object))
    os.replace(tmp, CACHE)
    print(f"wrote {os.path.basename(CACHE)}: {F.shape[0]} x {F.shape[1]}")


if __name__ == "__main__":
    main()
