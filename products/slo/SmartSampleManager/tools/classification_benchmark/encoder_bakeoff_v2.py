#!/usr/bin/env python3
"""
Extended encoder bake-off: add MERT (music SSL) and AST (AudioSet transformer)
to the measured Perch + CLAP baseline.

Rationale: every encoder tried so far is domain-ADJACENT -- CLAP is general
audio+text, Perch is bioacoustics, PANNs is AudioSet events. MERT is
self-supervised on actual MUSIC recordings, which is the corpus domain. And
since Perch+CLAP beat either alone by being complementary (transients vs
timbre), a music-trained third axis may add again.

Evaluated on the 649 by-ear labels, identical folds to prior bake-offs.
"""
import os, csv, warnings, numpy as np, soundfile as sf, librosa, torch
warnings.filterwarnings("ignore")
SD = os.path.dirname(os.path.abspath(__file__))

def load(path, sr, secs=5.0):
    y, s = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1: y = y.mean(1)
    if s != sr: y = librosa.resample(y, orig_sr=s, target_sr=sr)
    n = int(sr*secs); out = np.zeros(n, dtype=np.float32)
    k = min(len(y), n); out[:k] = y[:k]; return out

def mert_embed(paths, batch=8):
    from transformers import AutoModel, Wav2Vec2FeatureExtractor
    mid = "m-a-p/MERT-v1-95M"
    fe = Wav2Vec2FeatureExtractor.from_pretrained(mid, trust_remote_code=True)
    m = AutoModel.from_pretrained(mid, trust_remote_code=True).eval()
    sr = fe.sampling_rate
    out=[]
    for i in range(0,len(paths),batch):
        w=[load(p,sr) for p in paths[i:i+batch]]
        inp=fe(w, sampling_rate=sr, return_tensors="pt", padding=True)
        with torch.no_grad(): h=m(**inp, output_hidden_states=True)
        # mean-pool the last hidden state over time
        out.append(h.last_hidden_state.mean(1).numpy())
        if i and i%(batch*20)==0: print(f"  mert {i}/{len(paths)}", flush=True)
    return np.concatenate(out).astype(np.float32)

def ast_embed(paths, batch=8):
    from transformers import ASTModel, ASTFeatureExtractor
    mid="MIT/ast-finetuned-audioset-10-10-0.4593"
    fe=ASTFeatureExtractor.from_pretrained(mid); m=ASTModel.from_pretrained(mid).eval()
    out=[]
    for i in range(0,len(paths),batch):
        w=[load(p,16000) for p in paths[i:i+batch]]
        inp=fe(w, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad(): h=m(**inp)
        out.append(h.pooler_output.numpy())
        if i and i%(batch*20)==0: print(f"  ast {i}/{len(paths)}", flush=True)
    return np.concatenate(out).astype(np.float32)

def main():
    rows=[r for r in csv.DictReader(open(os.path.join(SD,'verified_drums.csv')))
          if r['label'] not in ('__skip__','Misc/Review') and os.path.exists(r['path'])]
    paths=[r['path'] for r in rows]; y=np.array([r['label'] for r in rows])
    z=np.load(os.path.join(SD,'bioacoustic_emb.npz')); Xperch, Xclap = z['perch'], z['clap']
    cache=os.path.join(SD,'encoder_v2_emb.npz')
    if os.path.exists(cache):
        c=np.load(cache); Xm,Xa=c['mert'],c['ast']; print("loaded cached MERT/AST")
    else:
        print(f"extracting MERT (music SSL) for {len(paths)} files..."); Xm=mert_embed(paths)
        print(f"extracting AST (AudioSet ViT)...");                      Xa=ast_embed(paths)
        np.savez(cache, mert=Xm, ast=Xa)
    print(f"\nperch{Xperch.shape[1]} clap{Xclap.shape[1]} mert{Xm.shape[1]} ast{Xa.shape[1]}\n")

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict
    from collections import Counter
    cnt=Counter(y); viable=[c for c in cnt if cnt[c]>=15]; m=np.isin(y,viable)
    def run(X,name):
        p=cross_val_predict(make_pipeline(StandardScaler(),
            LogisticRegression(max_iter=3000,class_weight='balanced')), X[m], y[m], cv=5)
        a=100*(p==y[m]).mean(); print(f"  {name:28} {a:5.1f}%"); return p,a
    res={}
    for X,n in [(Xperch,"Perch (bioacoustic)"),(Xclap,"CLAP (audio-text)"),
                (Xm,"MERT (music SSL)"),(Xa,"AST (AudioSet ViT)")]:
        res[n]=run(X,n)
    print()
    run(np.hstack([Xperch,Xclap]),"Perch+CLAP (prev best)")
    run(np.hstack([Xperch,Xclap,Xm]),"Perch+CLAP+MERT")
    best,_=run(np.hstack([Xperch,Xclap,Xm,Xa]),"Perch+CLAP+MERT+AST")
    print("\nper-class recall by encoder:")
    hdr=f"  {'class':>16} {'n':>4}"+"".join(f"{k.split(' ')[0]:>8}" for k in res)
    print(hdr)
    for c in sorted(viable,key=lambda k:-cnt[k]):
        s=y[m]==c; line=f"  {c:>16} {int(s.sum()):4d}"
        for k in res: line+=f"{100*(res[k][0][s]==c).mean():7.0f}%"
        print(line)

if __name__=="__main__": main()
