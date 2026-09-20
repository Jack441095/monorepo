#!/usr/bin/env python3
"""
Data augmentation on the by-ear labels.

Unlike pseudo-labelling (section 28), which manufactures EASY examples with
UNCERTAIN labels and was measured at +1.0pp on the full stack, augmentation
manufactures HARD variations with GUARANTEED-correct labels: a pitch-shifted
kick is still a kick. This is the standard remedy for a small labelled set and
directly attacks the binding constraint identified in sections 27-28.

Augmentations chosen to preserve class identity:
  pitch shift +/-1.5 semitones  (a kick stays a kick; avoids large shifts that
                                 would turn a kick into a tom)
  time stretch 0.92 / 1.09      (preserves timbre, changes envelope timing)
  gain -6dB                     (level invariance)
  light noise                   (robustness)
"""
import csv, os, sys, time, numpy as np, soundfile as sf, librosa, warnings
warnings.filterwarnings("ignore")
import onnxruntime as ort, torch
from transformers import ClapProcessor

SD=os.path.dirname(os.path.abspath(__file__))

def variants(y, sr):
    out={"orig": y}
    try: out["pitch_up"]   = librosa.effects.pitch_shift(y=y, sr=sr, n_steps=1.5)
    except Exception: pass
    try: out["pitch_down"] = librosa.effects.pitch_shift(y=y, sr=sr, n_steps=-1.5)
    except Exception: pass
    try: out["slow"]       = librosa.effects.time_stretch(y=y, rate=0.92)
    except Exception: pass
    try: out["fast"]       = librosa.effects.time_stretch(y=y, rate=1.09)
    except Exception: pass
    out["quiet"] = y*0.5
    return out

def main():
    rows=[r for r in csv.DictReader(open(os.path.join(SD,'verified_drums.csv')))
          if r['label'] not in ('__skip__','Misc/Review') and os.path.exists(r['path'])]
    ps=ort.InferenceSession(os.path.join(SD,"perch_int8_matmul.onnx"),providers=["CPUExecutionProvider"])
    cs=ort.InferenceSession(os.path.join(SD,"clap_onnx/clap_int8_matmul.onnx"),providers=["CPUExecutionProvider"])
    proc=ClapProcessor.from_pretrained(os.path.join(SD,"clap_model_music"))
    def emb(y32, y48):
        o=np.zeros(160000,dtype=np.float32); k=min(len(y32),160000); o[:k]=y32[:k]
        p=ps.run(["embedding"],{"inputs":o[None]})[0][0]
        f=proc(audio=[y48],sampling_rate=48000,return_tensors="pt")
        ins={"input_features":f["input_features"].numpy()}
        if "is_longer" in f: ins["is_longer"]=f["is_longer"].numpy()
        c=cs.run(None,ins)[0][0]
        return np.concatenate([p,c])
    X=[];Y=[];KIND=[];t0=time.time()
    for i,r in enumerate(rows):
        try:
            y,s=sf.read(r['path'],dtype='float32',always_2d=False)
            if y.ndim>1: y=y.mean(1)
            y32=librosa.resample(y,orig_sr=s,target_sr=32000) if s!=32000 else y
            for kind,v in variants(y32,32000).items():
                v48=librosa.resample(v,orig_sr=32000,target_sr=48000)
                X.append(emb(v,v48)); Y.append(r['label']); KIND.append(kind)
        except Exception: continue
        if i and i%60==0:
            r_=i/(time.time()-t0); print(f"  {i}/{len(rows)} files  {r_:.1f}/s  ETA {(len(rows)-i)/r_/60:.0f} min",flush=True)
    np.savez(os.path.join(SD,'augmented_emb.npz'),X=np.array(X,dtype=np.float32),
             y=np.array(Y),kind=np.array(KIND))
    print(f"saved {len(X)} embeddings ({len(rows)} files x variants) in {(time.time()-t0)/60:.1f} min")

if __name__=="__main__": main()
