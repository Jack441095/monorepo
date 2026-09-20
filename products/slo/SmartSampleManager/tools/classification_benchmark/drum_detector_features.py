#!/usr/bin/env python3
"""
Enriched feature set for atonal-hit (drum one-shot) detection.

Motivation and measured wins (2026-09-09):
  8 coarse DSP features alone           -> 71.5% CV on 4 drum classes
  + 3 f0/salience features              -> 80.1% (validated the fundamental-
                                            frequency idea: kick f0 ~67Hz,
                                            snare ~214Hz, threshold@150Hz = 79%)
This adds the temporal-envelope axis ("sustain over time"), clap-vs-snare
onset density, and the ADT-standard MFCC timbre features.

Feature groups (all cheap, no neural net):
  f0 block (3): fundamental Hz from attack, pitch salience, low-band fraction
  envelope (4): attack time, decay time, sustain ratio, crest factor
  onset    (1): onset count in first 80ms  -> clap (multi-transient) vs snare
  timbre  (20): MFCC mean (13) + std (7 of them) over the hit
"""
import numpy as np, soundfile as sf, librosa

SR = 22050  # MFCC-standard rate; drums have little above 11kHz that matters here

def extract(path):
    try:
        y, sr = sf.read(path, dtype='float32', always_2d=False)
        if y.ndim > 1: y = y.mean(1)
        if len(y) < 256: return None
        if sr != SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        y = y[:SR]  # cap 1s; one-shots are short
        n = len(y)

        # --- f0 block from the attack (first 120ms) ---
        aw = y[:int(SR*0.12)] * np.hanning(min(n, int(SR*0.12)))
        mag = np.abs(np.fft.rfft(aw, n=1<<15)); fr = np.fft.rfftfreq(1<<15, 1/SR)
        b = (fr>=30)&(fr<=600)
        f0 = fr[b][np.argmax(mag[b])] if b.any() else 0.0
        sal = float(mag[b].max()/(mag[b].mean()+1e-9)) if b.any() else 0.0
        lowfrac = float(mag[(fr>=30)&(fr<150)].sum()/(mag[fr<8000].sum()+1e-9))

        # --- temporal envelope (attack / decay / sustain) ---
        env = np.abs(librosa.util.frame(y, frame_length=256, hop_length=128)).max(0)
        env = env/(env.max()+1e-9)
        peak_i = int(np.argmax(env))
        attack = peak_i/(len(env)+1e-9)                       # time-to-peak (relative)
        # decay: frames from peak to fall below 10%
        after = env[peak_i:]
        decay = (np.argmax(after<0.1)/(len(env)+1e-9)) if (after<0.1).any() else 1.0
        sustain = float((env>0.3).mean())                     # fraction of time above 30% -> one-shot vs sustained
        peak = float(np.max(np.abs(y))); rms = float(np.sqrt(np.mean(y**2))+1e-9)
        crest = min(peak/rms/20, 1.0)

        # --- onset density in first 80ms: clap (multi-transient) vs snare ---
        oenv = librosa.onset.onset_strength(y=y[:int(SR*0.15)], sr=SR)
        onsets = librosa.util.peak_pick(oenv, pre_max=1,post_max=1,pre_avg=1,post_avg=1,delta=0.3,wait=1)
        n_onset = min(len(onsets)/4.0, 1.0)

        # --- MFCC timbre ---
        mf = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13)
        mfcc = np.concatenate([mf.mean(1), mf[:7].std(1)])    # 13 mean + 7 std = 20

        # --- timbre texture & pitch clarity (HPSS ratio, contrast, bandwidth, chroma peak, ZCR) ---
        y_harm, y_perc = librosa.effects.hpss(y)
        harm_e = float(np.mean(y_harm**2))
        perc_e = float(np.mean(y_perc**2))
        harm_ratio = harm_e / (harm_e + perc_e + 1e-9)

        spec_contrast = float(np.mean(librosa.feature.spectral_contrast(y=y, sr=SR)))
        spec_bw = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=SR)) / (SR / 2))
        chroma = librosa.feature.chroma_stft(y=y, sr=SR)
        chroma_peak = float(np.max(chroma.mean(axis=1)))
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

        timbre_extra = np.array([harm_ratio, min(spec_contrast/40.0, 1.0), spec_bw, chroma_peak, min(zcr*3.0, 1.0)], dtype=np.float32)

        base = np.array([min(f0/500,1), min(sal/50,1), lowfrac,
                         attack, decay, sustain, crest, n_onset], dtype=np.float32)
        return np.concatenate([base, mfcc, timbre_extra]).astype(np.float32)
    except Exception:
        return None

FEATURE_NAMES = (["f0","salience","lowfrac","attack","decay","sustain","crest","onsets"]
                 + [f"mfcc{i}" for i in range(13)] + [f"mfccstd{i}" for i in range(7)]
                 + ["harm_ratio","contrast","bandwidth","chroma_peak","zcr"])

if __name__ == "__main__":
    import sys, random, importlib.util
    import build_hybrid_v4_dataset as dsp
    spec=importlib.util.spec_from_file_location("lb","build_all_packs_dataset_v2.py")
    lb=importlib.util.module_from_spec(spec); sys.modules["lb"]=lb
    try: spec.loader.exec_module(lb)
    except SystemExit: pass
    fn_map=dsp.build_filename_map(dsp.SOURCE_ROOT)
    d=np.load('slo_all_packs_hybrid_v4.npz',allow_pickle=True)
    fns=d['filenames']; labs=np.array([str(v) for v in d['labels']])
    drums=['Kick','Snare','Hi-Hat','Clap']; random.seed(0)
    rows=[]
    for c in drums:
        idx=[i for i in np.where(labs==c)[0] if str(fns[i]) in fn_map]; random.shuffle(idx)
        for i in idx[:600]: rows.append((i,c))
    print(f"extracting enriched features for {len(rows)} drum hits...")
    feats=[]; ys=[]
    for k,(i,c) in enumerate(rows):
        f=extract(fn_map[str(fns[i])])
        if f is not None: feats.append(f); ys.append(c)
        if k and k%500==0: print(f"  {k}/{len(rows)}")
    Xr=np.array(feats); yr=np.array(ys)
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    from sklearn.metrics import classification_report, confusion_matrix
    pred=cross_val_predict(RandomForestClassifier(n_estimators=200,class_weight='balanced',random_state=0),Xr,yr,cv=5)
    print(f"\nEnriched drum detector ({len(FEATURE_NAMES)} features, RF, 5-fold): {100*(pred==yr).mean():.1f}%\n")
    print(classification_report(yr,pred,digits=3))
    print("confusion (rows=true):",drums)
    print(confusion_matrix(yr,pred,labels=drums))
    np.savez('drum_features_sample.npz', X=Xr, y=yr, names=FEATURE_NAMES)
