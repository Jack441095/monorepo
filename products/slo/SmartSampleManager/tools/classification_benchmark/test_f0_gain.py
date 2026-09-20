import numpy as np, soundfile as sf, importlib.util, sys, random
from pathlib import Path
import build_hybrid_v4_dataset as dsp
BASE_DIR = Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("lb", BASE_DIR / "build_all_packs_dataset_v2.py")
lb=importlib.util.module_from_spec(spec); sys.modules["lb"]=lb
try: spec.loader.exec_module(lb)
except SystemExit: pass
fn_map=dsp.build_filename_map(dsp.SOURCE_ROOT)
d=np.load(BASE_DIR / 'slo_all_packs_hybrid_v4.npz',allow_pickle=True)
fns=d['filenames']; labs=np.array([str(v) for v in d['labels']]); X8=d['embeddings'][:,512:]

def f0_feats(path):
    try:
        y,sr=sf.read(path,dtype='float32',always_2d=False)
        if y.ndim>1: y=y.mean(1)
        if len(y)<256: return [0,0,0]
        a=y[:int(sr*0.12)]*np.hanning(min(len(y),int(sr*0.12)))
        mag=np.abs(np.fft.rfft(a,n=1<<15)); fr=np.fft.rfftfreq(1<<15,1/sr)
        b=(fr>=30)&(fr<=600)
        f0=fr[b][np.argmax(mag[b])] if b.any() else 0
        # low-band energy fraction <150Hz, and pitch salience (peak/mean in band)
        lowfrac=float(mag[(fr>=30)&(fr<150)].sum()/(mag[fr<8000].sum()+1e-9))
        sal=float(mag[b].max()/(mag[b].mean()+1e-9)) if b.any() else 0
        return [min(f0/500,1.0), lowfrac, min(sal/50,1.0)]
    except: return [0,0,0]

drums=['Kick','Snare','Hi-Hat','Clap']
random.seed(0)
rows=[]
for c in drums:
    idx=[i for i in np.where(labs==c)[0] if str(fns[i]) in fn_map]
    random.shuffle(idx)
    for i in idx[:600]: rows.append((i,c))
Xf=np.array([f0_feats(fn_map[str(fns[i])]) for i,_ in rows])
X8s=np.array([X8[i] for i,_ in rows]); y=np.array([c for _,c in rows])
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
for name,Xuse in [('8 DSP only',X8s),('8 DSP + 3 f0 feats',np.hstack([X8s,Xf]))]:
    sc=cross_val_score(RandomForestClassifier(n_estimators=100,class_weight='balanced',random_state=0),Xuse,y,cv=5)
    print(f'{name:>22}: {100*sc.mean():.1f}% CV (4 drum classes)')
