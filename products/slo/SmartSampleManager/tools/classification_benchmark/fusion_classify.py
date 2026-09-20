#!/usr/bin/env python3
"""
Evidence-fusion classifier across the full taxonomy.

Combines three signals, as the owner specified:
  1. FILENAME tokens (name_detect) -- high precision when the token is specific
  2. DURATION -- separates one-shot vs loop (empirically 2.5s, 91% on the
     by-ear set: one-shots median 0.74s, loops 5.58s)
  3. ACOUSTIC (f0, salience, sustain, MFCC via a RandomForest) -- decides when
     the filename is silent or ambiguous, and gates melodic content

Fusion logic:
  - loop/one-shot is resolved by DURATION, overriding a filename token that
    disagrees (a file named 'kick' that runs 6s is a Kick Loop, not a Kick)
  - a specific filename token sets the FAMILY (kick/snare/hat/perc/...); the
    loop variant is chosen by duration
  - no/weak token -> acoustic RF sets the family, duration sets loop/one-shot
  - melodic gate: pitched + harmonic (high f0 salience) + loop-length -> Chord

Reports filename-only vs acoustic-only vs FUSION against the ear labels.
"""
import csv, os, numpy as np, soundfile as sf, librosa, warnings
warnings.filterwarnings('ignore')
import name_detect as nd
import drum_detector_features as ddf
import loop_features as lf
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict

LOOP_T = 2.5
FAMILY_LOOP = {"Kick":"Kick Loop","Snare":"Snare Loop","Hi-Hat":"Hi-Hat Loop",
               "Percussion":"Percussion Loop","Foley":"Foley Loop","Bass":"Bass Loop"}
LOOP_FAMILY = {v:k for k,v in FAMILY_LOOP.items()}
ONESHOT = set(FAMILY_LOOP) | {"Rimshot","Crash","Clap"}
ALL_LOOPS = set(FAMILY_LOOP.values()) | {"Drum Loop","Top Loop","Loop","Chord Loop"}

def dur_of(path):
    try: i=sf.info(path); return i.frames/i.samplerate
    except: return 0.0

def decay_ratio(p):
    # energy last-third / first-third. A one-shot with a long tail (crash)
    # decays to ~0; a loop sustains (~0.87). Plugs crash->Drum Loop leak.
    try:
        y,sr=sf.read(p,dtype='float32',always_2d=False)
        if y.ndim>1: y=y.mean(1)
        n=len(y)//3
        if n<10: return 1.0
        return float(min((np.mean(y[-n:]**2)+1e-9)/(np.mean(y[:n]**2)+1e-9),2.0))
    except: return 1.0

def onset_count(path):
    # full-file onset count: a loop repeats (many onsets), a long one-shot
    # like a crash has one hit and a decay tail (few). Median loops=22, crash=7.
    try:
        y,sr=sf.read(path,dtype='float32',always_2d=False)
        if y.ndim>1: y=y.mean(1)
        if sr!=22050: y=librosa.resample(y,orig_sr=sr,target_sr=22050); sr=22050
        oe=librosa.onset.onset_strength(y=y,sr=sr)
        return len(librosa.util.peak_pick(oe,pre_max=3,post_max=3,pre_avg=5,post_avg=5,delta=0.2,wait=5))
    except: return 0

def load():
    rows=[r for r in csv.DictReader(open('verified_drums.csv'))
          if r['label'] not in ('__skip__','Misc/Review')]
    X,y,paths,durs=[],[],[],[]
    for r in rows:
        f=ddf.extract(r['path'])
        if f is None: continue
        X.append(f); y.append(r['label']); paths.append(r['path']); durs.append(dur_of(r['path']))
    ons=[onset_count(p) for p in paths]
    dr=[decay_ratio(p) for p in paths]
    return np.array(X),np.array(y),paths,np.array(durs),np.array(ons),np.array(dr)

def resolve_loop(cls, is_loop):
    """Reconcile a class with the duration verdict."""
    if is_loop and cls in FAMILY_LOOP: return FAMILY_LOOP[cls]
    if is_loop and cls in ("Rimshot","Crash","Clap"): return "Drum Loop"
    if (not is_loop) and cls in LOOP_FAMILY: return LOOP_FAMILY[cls]
    return cls

def main():
    X,y,paths,durs,ons,dr=load()
    n=len(y); print(f"{n} by-ear labelled files\n")

    # acoustic RF with probability estimates
    from collections import Counter
    cnt=Counter(y); viable=[c for c in cnt if cnt[c]>=15]
    mask=np.array([t in viable for t in y])

    clf_ac = RandomForestClassifier(n_estimators=300, class_weight='balanced', random_state=0)
    ac_proba = cross_val_predict(clf_ac, X[mask], y[mask], cv=5, method='predict_proba')
    clf_ac.fit(X[mask], y[mask])
    classes_ac = list(clf_ac.classes_)
    
    ac_pred = np.array(['?']*n, dtype=object)
    ac_conf = np.zeros(n, dtype=np.float32)
    ac_pred[mask] = np.array(classes_ac)[ac_proba.argmax(axis=1)]
    ac_conf[mask] = ac_proba.max(axis=1)

    fn_pred=np.array([nd.detect(os.path.basename(p))[0] or '?' for p in paths], dtype=object)
    is_loop=(durs>=LOOP_T)&(ons>=8)&(dr>=0.25)   # rhythm + sustained-energy: excludes crashes

    # loop-specific model on full-file spectral features (Drum/Perc/Foley Loop)
    Xl=np.array([lf.extract(p) if lf.extract(p) is not None else np.zeros(len(lf.NAMES),dtype=np.float32) for p in paths])
    loop_classes=[c for c in Counter(y) if c in ('Drum Loop','Percussion Loop','Foley Loop') and Counter(y)[c]>=10]
    lmask=np.isin(y,loop_classes)
    loop_pred=np.array(['?']*n,dtype=object)
    if lmask.sum()>20:
        loop_pred[lmask]=cross_val_predict(RandomForestClassifier(n_estimators=300,class_weight='balanced',random_state=0),
                                           Xl[lmask], y[lmask], cv=5)

    # melodic gate: high f0 + high salience (harmonic) + loop-length
    f0=X[:,0]; sal=X[:,1]  # normalised f0, salience from ddf
    melodic = (f0>0.25)&(sal>0.5)&is_loop

    # Precision thresholds for filename tokens (from name_detect validation)
    WEAK_TOKENS = {'Percussion', 'Drum Loop', 'Rimshot', 'Foley', 'Loop'}

    fusion=np.empty(n, dtype=object)
    for i in range(n):
        fn_is_looptok = fn_pred[i] in ('Drum Loop','Percussion Loop','Hi-Hat Loop','Foley Loop','Chord Loop','Bass Loop','Top Loop')
        
        # High acoustic confidence (>= 0.70) overrides weak/generic filename tokens (e.g. generic Percussion or Rimshot)
        if fn_pred[i] in WEAK_TOKENS and ac_pred[i] != '?' and ac_conf[i] >= 0.70:
            fusion[i] = resolve_loop(ac_pred[i], is_loop[i])
        elif is_loop[i] and not fn_is_looptok and loop_pred[i]!='?':
            fusion[i]=loop_pred[i]               # two-stage: loop model picks the loop type
        elif fn_pred[i]!='?':
            fusion[i]=resolve_loop(fn_pred[i], is_loop[i])
        elif ac_pred[i]!='?':
            fusion[i]=resolve_loop(ac_pred[i], is_loop[i])
        else:
            fusion[i]='Drum Loop' if is_loop[i] else 'Percussion'
        if melodic[i] and is_loop[i] and fusion[i] in ('Drum Loop','Loop','Percussion Loop'):
            fusion[i]='Chord Loop'               # melodic override

    def acc(pred, name):
        cov=(pred!='?'); a=100*(pred[cov]==y[cov]).mean() if cov.any() else 0
        print(f"  {name:16} coverage {100*cov.mean():5.1f}%  precision {a:5.1f}%  "
              f"(overall {100*(pred==y).mean():.1f}%)")
    print("method comparison vs your ear:")
    acc(fn_pred,"filename-only"); acc(ac_pred,"acoustic-only"); acc(fusion,"FUSION")

    # fusion per-class
    print("\nfusion per-class recall:")
    for c in sorted(set(y), key=lambda k:-cnt[k]):
        m=y==c
        if m.sum()>=8: print(f"  {c:>16} n={int(m.sum()):3d}  {100*(fusion[m]==c).mean():5.1f}%")
    np.savez('fusion_eval.npz', y=y, fn=fn_pred, ac=ac_pred, fusion=fusion, dur=durs)

if __name__=="__main__": main()
