#!/usr/bin/env python3
"""
Interpretable acoustic evidence -- physics_v1.

Purpose is NOT to beat the classifier. Two prior attempts at physics features
returned +0.0pp and +0.05pp, because the encoders already capture what generic
spectral descriptors say. This layer exists for two things a 2048-D embedding
cannot do:

  1. SEPARATE MECHANISMS THAT DIFFER PHYSICALLY, NOT TIMBRALLY.
     An 808 is a sub fundamental with a DOWNWARD PITCH GLIDE at the attack.
     A Sub Bass is the same fundamental with NO glide.
     A Reese is sustained with DETUNED BEATING between partials.
     A Bass Hit has low body but a HIT-LIKE ENVELOPE.
     Those are four mechanisms. Global pooling averages the glide and the
     beating away; a descriptor measures them directly.

  2. EXPLAIN ITSELF. "Likely 808: strong sub energy, 320-cent downward glide,
     1.8s decay" is a true, checkable statement about the audio. An embedding
     cannot say why.

Every value is interpretable and unit-bearing where possible (Hz, cents,
seconds, ratios), so a wrong answer can be argued with.

Read-only: opens files, writes nothing, mutates nothing.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(SD, "acoustic_evidence_v1.npz")
FEATURE_VERSION = "physics_v1_1"
SR = 32000

NAMES = [
    # pitch / harmonic structure
    "fundamental_hz", "pitch_confidence", "harmonicity", "inharmonicity",
    "harmonic_spacing_hz", "harmonic_density", "noise_tonal_ratio",
    # "a sub bass tends to be just a sine wave sustained" -- so measure exactly
    # that. A pure sine puts ~all its energy in one narrow band and has one
    # partial; this is the simplest spectrum a sound can have, and it is what
    # separates Sub Bass from an 808 (which glides) and from a Reese (which
    # beats). Cheap, unambiguous, and an encoder trained on natural sound has
    # little reason to represent it distinctly.
    "spectral_purity", "partial_count",
    # the 808 signature
    "pitch_drop_cents", "pitch_drop_rate_cps", "glide_within_100ms_cents",
    # the Reese signature
    "beating_rate_hz", "beating_depth", "sideband_energy",
    # spectral shape
    "spectral_centroid", "spectral_flatness", "spectral_flux",
    "sub_energy_ratio", "low_energy_ratio", "mid_energy_ratio",
    "high_energy_ratio",
    # envelope
    "transient_strength", "attack_ms", "decay_seconds", "sustain_ratio",
    "attack_to_tail_ratio", "onset_density",
    # rhythm / stereo
    "rhythmic_autocorr", "stereo_width", "mid_side_ratio", "phase_correlation",
]


def _safe(v, lo=-1e6, hi=1e6):
    v = float(v)
    if not np.isfinite(v):
        return 0.0
    return float(np.clip(v, lo, hi))


def extract(path):
    """Return a dict of interpretable evidence, or None if unreadable."""
    import soundfile as sf, librosa
    try:
        y2, sr0 = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        return None
    if y2.shape[0] < 128:
        return None

    # stereo measured BEFORE downmix -- the encoders are mono, so this is the
    # only place width and phase are observable at all
    if y2.shape[1] >= 2:
        L, R = y2[:, 0], y2[:, 1]
        phase = _safe(np.corrcoef(L, R)[0, 1]) if L.std() > 1e-9 and R.std() > 1e-9 else 1.0
        mid, side = (L + R) / 2, (L - R) / 2
        ms = _safe(np.sqrt((side ** 2).mean()) / (np.sqrt((mid ** 2).mean()) + 1e-9))
        width = _safe(ms / (1.0 + ms))
    else:
        phase, ms, width = 1.0, 0.0, 0.0

    y = y2.mean(1)
    if sr0 != SR:
        y = librosa.resample(y, orig_sr=sr0, target_sr=SR)
    y = y[: SR * 10].astype(np.float32)
    if len(y) < SR // 100 or np.abs(y).max() < 1e-8:
        return None
    y = y / (np.abs(y).max() + 1e-9)
    dur = len(y) / SR
    hop = 256

    # ---- envelope -------------------------------------------------------
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    pk = float(rms.max()) + 1e-9
    pi = int(np.argmax(rms))
    pre = rms[: pi + 1]
    if len(pre) > 1:
        lo_i = np.where(pre >= 0.1 * pk)[0]
        hi_i = np.where(pre >= 0.9 * pk)[0]
        attack_ms = ((hi_i[0] - lo_i[0]) * hop / SR * 1000.0) if len(lo_i) and len(hi_i) else 0.0
    else:
        attack_ms = 0.0
    post = rms[pi:]
    below = np.where(post <= 0.1 * pk)[0]
    decay_s = (below[0] if len(below) else len(post)) * hop / SR
    third = len(rms) // 3
    sustain = float(rms[third:2 * third].mean() / pk) if third > 0 else 0.0
    q = max(1, len(rms) // 4)
    attack_tail = _safe(rms[:q].mean() / (rms[-q:].mean() + 1e-9))
    oe = librosa.onset.onset_strength(y=y, sr=SR, hop_length=hop)
    transient = _safe(oe.max() / (oe.mean() + 1e-9)) if len(oe) else 0.0
    n_on = len(librosa.onset.onset_detect(onset_envelope=oe, sr=SR, hop_length=hop))
    onset_density = n_on / max(dur, 1e-6)
    ac = 0.0
    if len(oe) > 8:
        e = oe - oe.mean()
        a = np.correlate(e, e, "full")[len(e) - 1:]
        if a[0] > 1e-9:
            a = a / a[0]
            lo2 = max(2, int(0.12 * SR / hop)); hi2 = max(lo2 + 2, len(a) // 2)
            seg = a[lo2:hi2]
            if len(seg):
                ac = _safe(seg.max() - np.median(seg))

    # ---- spectrum -------------------------------------------------------
    S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=SR, n_fft=4096)
    P = S ** 2
    tot = P.sum() + 1e-9
    sub = _safe(P[freqs < 60].sum() / tot)
    low = _safe(P[(freqs >= 60) & (freqs < 250)].sum() / tot)
    mid = _safe(P[(freqs >= 250) & (freqs < 2000)].sum() / tot)
    high = _safe(P[freqs >= 2000].sum() / tot)
    cent = _safe(librosa.feature.spectral_centroid(S=S, sr=SR).mean())
    flat = _safe(librosa.feature.spectral_flatness(S=S).mean())
    flux = _safe(np.mean(np.diff(S, axis=1).clip(min=0).sum(0))) if S.shape[1] > 1 else 0.0

    # ---- pitch: the 808 signature ---------------------------------------
    f0 = pconf = drop_cents = drop_rate = glide100 = 0.0
    try:
        f0t, voiced, vprob = librosa.pyin(y, fmin=25, fmax=1200, sr=SR,
                                          frame_length=4096, hop_length=hop)
        ok = np.isfinite(f0t) & (voiced if voiced is not None else True)
        if ok.sum() >= 4:
            f0 = _safe(np.median(f0t[ok]), 0, 5000)
            pconf = _safe(np.nanmean(vprob[ok]) if vprob is not None else ok.mean())
            fv = f0t[ok]
            # total downward excursion, in cents (positive = drops)
            drop_cents = _safe(1200.0 * np.log2((fv[0] + 1e-9) / (fv[-1] + 1e-9)),
                               -6000, 6000)
            span = max((ok.sum() * hop) / SR, 1e-6)
            drop_rate = _safe(drop_cents / span, -20000, 20000)
            # glide inside the first 100ms -- an 808's pitch envelope
            n100 = max(2, int(0.1 * SR / hop))
            head = f0t[:n100][np.isfinite(f0t[:n100])]
            if len(head) >= 2:
                glide100 = _safe(1200.0 * np.log2((head[0] + 1e-9) / (head[-1] + 1e-9)),
                                 -6000, 6000)
    except Exception:
        pass

    # ---- harmonic structure ---------------------------------------------
    from scipy.signal import find_peaks
    Sm = S.mean(1)
    harmonicity = inharm = spacing = density = 0.0
    purity = 0.0
    n_partials = 0.0
    if Sm.max() > 0:
        Sn = Sm / Sm.max()
        pks, _ = find_peaks(Sn, height=0.05, distance=3)
        pks = pks[freqs[pks] > 20]
        n_partials = float(len(pks))

        # PURITY MUST BE COMPUTED OUTSIDE THE >=3 PEAK GUARD. A sustained sine
        # -- the definition of a Sub Bass -- has exactly ONE peak, so the
        # harmonic-analysis branch below never runs for it and purity stayed 0.
        # That made the purest possible spectrum score lowest, the exact
        # inverse of the intended meaning. Caught by the synthetic sine test.
        base_for_purity = f0 if f0 > 20 else (freqs[pks][int(np.argmax(Sn[pks]))]
                                              if len(pks) else 0.0)
        if base_for_purity > 20:
            band = (freqs > base_for_purity * 0.85) & (freqs < base_for_purity * 1.15)
            if band.any():
                purity = _safe(P[band].sum() / tot)

        if len(pks) >= 3:
            pf = freqs[pks][np.argsort(-Sn[pks])[:12]]
            pf = np.sort(pf)
            spacing = _safe(np.median(np.diff(pf)))
            density = _safe(len(pf) / max((pf[-1] - pf[0]) / 1000.0, 1e-6))
            base = f0 if f0 > 20 else pf[0]
            if base > 20:
                n = np.clip(np.round(pf / base), 1, None)
                dev = np.abs(pf - n * base) / (n * base)
                inharm = _safe(dev.mean())
                harmonicity = _safe((dev < 0.05).mean())

    # ---- beating: the Reese signature -----------------------------------
    # Amplitude modulation of the low/mid band. Two slightly detuned saws beat
    # at their frequency difference; that is audible as movement and measurable
    # as a peak in the modulation spectrum of the band envelope.
    beat_rate = beat_depth = sideband = 0.0
    try:
        band = P[(freqs >= 60) & (freqs < 1500)].sum(0)
        if len(band) > 32:
            env = band / (band.max() + 1e-9)
            e = env - env.mean()
            sp = np.abs(np.fft.rfft(e * np.hanning(len(e))))
            fq = np.fft.rfftfreq(len(e), hop / SR)
            m = (fq > 0.5) & (fq < 40)
            if m.sum() and sp[m].sum() > 0:
                k = int(np.argmax(sp[m]))
                beat_rate = _safe(fq[m][k])
                beat_depth = _safe(sp[m][k] / (sp.sum() + 1e-9))
            sideband = _safe(sp[m].sum() / (sp.sum() + 1e-9))
    except Exception:
        pass

    noise_tonal = _safe(flat)
    vals = [f0, pconf, harmonicity, inharm, spacing, density, noise_tonal,
            purity, n_partials,
            drop_cents, drop_rate, glide100,
            beat_rate, beat_depth, sideband,
            cent, flat, flux, sub, low, mid, high,
            transient, attack_ms, decay_s, sustain, attack_tail, onset_density,
            ac, width, ms, phase]
    return {n: _safe(v) for n, v in zip(NAMES, vals)}


def describe(ev):
    """Human-readable evidence -- the product explanation layer."""
    if ev is None:
        return "no readable audio"
    bits = []
    if ev["sub_energy_ratio"] > 0.35:
        bits.append(f"strong sub energy ({ev['sub_energy_ratio']*100:.0f}% below 60Hz)")
    if ev["pitch_drop_cents"] > 150:
        bits.append(f"{ev['pitch_drop_cents']:.0f}-cent downward pitch glide")
    if ev["beating_rate_hz"] > 1 and ev["beating_depth"] > 0.02:
        bits.append(f"detuned beating at {ev['beating_rate_hz']:.1f}Hz")
    if ev["decay_seconds"] > 1.0:
        bits.append(f"long {ev['decay_seconds']:.1f}s decay")
    if ev["attack_ms"] < 5 and ev["transient_strength"] > 4:
        bits.append("sharp transient")
    if ev["spectral_purity"] > 0.75 and ev["partial_count"] <= 3:
        bits.append(f"near-pure sine ({ev['spectral_purity']*100:.0f}% of energy "
                    f"at the fundamental)")
    if ev["harmonicity"] > 0.6:
        bits.append(f"clear harmonic series (f0 {ev['fundamental_hz']:.0f}Hz)")
    if ev["noise_tonal_ratio"] > 0.2:
        bits.append("noisy rather than tonal")
    if ev["stereo_width"] > 0.3:
        bits.append("wide stereo image")
    return "; ".join(bits) if bits else "no distinctive acoustic evidence"


def load_aligned(paths):
    if not os.path.exists(CACHE):
        return None, None
    z = np.load(CACHE, allow_pickle=True)
    if str(z["version"]) != FEATURE_VERSION:
        return None, None
    have = {p: i for i, p in enumerate(list(z["paths"]))}
    mask = np.array([p in have for p in paths])
    F = np.array([z["F"][have[p]] for p in paths if p in have], dtype=np.float32)
    return F, mask


def _one(p):
    d = extract(p)
    return (p, None if d is None else np.array([d[n] for n in NAMES], dtype=np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--paths-from", default=None)
    ap.add_argument("--describe", default=None)
    a = ap.parse_args()
    if a.describe:
        ev = extract(a.describe)
        print(json.dumps({**(ev or {}), "feature_version": FEATURE_VERSION},
                         indent=2, default=float))
        print("\n" + describe(ev))
        return
    import csv as _csv
    paths = list(np.load(os.path.join(SD, "corpus_v2.npz"), allow_pickle=True)["paths"])
    if a.paths_from and os.path.exists(a.paths_from):
        extra = [r["path"] for r in _csv.DictReader(open(a.paths_from))
                 if os.path.exists(r["path"])]
        paths = list(dict.fromkeys(paths + extra))
    done = {}
    if os.path.exists(CACHE):
        c = np.load(CACHE, allow_pickle=True)
        if str(c["version"]) == FEATURE_VERSION:
            done = {p: c["F"][i] for i, p in enumerate(list(c["paths"]))}
    todo = [p for p in paths if p not in done]
    print(f"{len(paths)} files, {len(todo)} to compute, {len(NAMES)} features")
    if todo:
        from multiprocessing import Pool
        import time
        t0 = time.time()
        with Pool(a.workers) as pool:
            for i, (p, v) in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
                if v is not None:
                    done[p] = v
                if (i + 1) % 200 == 0:
                    print(f"  {i+1}/{len(todo)} {(i+1)/(time.time()-t0):.1f}/s", flush=True)
    keep = [p for p in paths if p in done]
    F = np.array([done[p] for p in keep], dtype=np.float32)
    tmp = CACHE + ".tmp.npz"
    np.savez(tmp, F=F, paths=np.array(keep, dtype=object),
             names=np.array(NAMES, dtype=object), version=FEATURE_VERSION)
    os.replace(tmp, CACHE)
    print(f"wrote {os.path.basename(CACHE)}: {F.shape}")


if __name__ == "__main__":
    main()
