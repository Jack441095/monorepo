#!/usr/bin/env python3
"""
Re-derive the taxonomy ceiling on CLAP features.

The +7.16 pp drum-family merge and the 84.9% four-class ceiling were both
measured on PANNs features. CLAP then beat PANNs by +8.91 pp, which means
those numbers were partly measuring CNN10's representational limit rather
than the taxonomy. This re-measures them on the better encoder and saves the
OOF predictions the bake-off discarded.

Answers: does the taxonomy merge STACK with the encoder gain (is 90%
reachable), and how much of the residual is genuinely non-acoustic?
"""
import numpy as np, torch, json
from sklearn.model_selection import StratifiedKFold
import train_gpu_classifier_v4 as T

C = T.CLASSES

def cv(X, y, epochs=90, seed=42):
    torch.manual_seed(seed); np.random.seed(seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_cls = len(C)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    oof = np.zeros(len(y), dtype=int); conf = np.zeros(len(y), dtype=np.float32)
    for k,(tr,va) in enumerate(skf.split(X,y)):
        cnt = np.bincount(y[tr], minlength=n_cls)
        w = torch.tensor([len(tr)/(n_cls*max(c,1)) for c in cnt], dtype=torch.float32, device=dev)
        m = T.ClassifierV4(in_features=X.shape[1], num_classes=n_cls).to(dev)
        opt = torch.optim.AdamW(m.parameters(), lr=1.2e-3, weight_decay=1e-4)
        sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
        crit = T.FocalLoss(gamma=2.0, weight=w)
        ld = torch.utils.data.DataLoader(T.HybridDataset(X[tr],y[tr]), batch_size=256, shuffle=True)
        for _ in range(epochs):
            T.train_epoch(m, ld, opt, crit, dev); sch.step()
        m.eval()
        with torch.no_grad():
            xb = torch.tensor(X[va], dtype=torch.float32, device=dev)
            lg = m(xb, None); pr = torch.softmax(lg, dim=1)
            oof[va] = pr.argmax(1).cpu().numpy(); conf[va] = pr.max(1).values.cpu().numpy()
        print(f"  fold {k+1}/5 done", flush=True)
    return oof, conf

def regroup(y, p, mapping, label, base):
    m = {c: mapping.get(c, c) for c in C}
    names = sorted(set(m.values())); idx = {n:i for i,n in enumerate(names)}
    ry = np.array([idx[m[C[i]]] for i in y]); rp = np.array([idx[m[C[i]]] for i in p])
    acc = 100*(ry==rp).mean()
    print(f"  {label:<48} {len(names):2d} cls {acc:6.2f}%  ({acc-base:+.2f})")
    return acc

def main():
    X = np.load("hybrid_x.npy"); y = np.load("hybrid_y.npy")
    Xc = np.load("clap_all_music.npy")
    Xf = np.ascontiguousarray(np.hstack([Xc, X[:,512:]]).astype(np.float32))
    print(f"CLAP-music+DSP {Xf.shape}\n")
    oof, conf = cv(Xf, y)
    base = 100*(oof==y).mean()
    print(f"\nbaseline 16-class: {base:.2f}%\n")
    np.savez("clap_oof.npz", oof=oof, conf=conf, y=y)

    print("Taxonomy regrouping on CLAP features:")
    r = {}
    r['drum_merge'] = regroup(y,oof,{'Kick':'Drum','Snare':'Drum','Hi-Hat':'Drum','Clap':'Drum','Percussion':'Drum'},'merge drum family',base)
    r['foley_perc'] = regroup(y,oof,{'Foley':'PercFoley','Percussion':'PercFoley'},'merge Foley+Percussion (provenance, not acoustic)',base)
    r['loops'] = regroup(y,oof,{'Synth Loop':'Synth','Bass Loop':'Bass One-Shot','Music Loop':'Synth','Vocal Loop':'Vocal Phrase'},'collapse loop/one-shot split',base)
    r['drum+foley'] = regroup(y,oof,{'Kick':'Drum','Snare':'Drum','Hi-Hat':'Drum','Clap':'Drum','Percussion':'Drum','Foley':'Drum'},'drum family + Foley',base)
    r['coarse4'] = regroup(y,oof,{'Kick':'Drum','Snare':'Drum','Hi-Hat':'Drum','Clap':'Drum','Percussion':'Drum',
        'Foley':'Texture','FX':'Texture','Impact':'Texture','Riser':'Texture',
        'Synth':'Tonal','Synth Loop':'Tonal','Bass One-Shot':'Tonal','Bass Loop':'Tonal','Music Loop':'Tonal',
        'Vocal Loop':'Vocal','Vocal Phrase':'Vocal'},'coarse 4-way',base)

    print("\nPer-class recall (16-class):")
    for i,c in enumerate(C):
        m = y==i
        if m.sum(): print(f"  {c:>14} n={int(m.sum()):5d} recall {100*(oof[m]==i).mean():5.1f}%")
    json.dump({'base':float(base), **{k:float(v) for k,v in r.items()}}, open("clap_ceiling.json","w"), indent=2)
    print("\nSaved clap_ceiling.json, clap_oof.npz")

if __name__ == "__main__": main()
