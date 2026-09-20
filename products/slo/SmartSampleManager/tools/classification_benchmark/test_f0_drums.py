import numpy as np, soundfile as sf, os, importlib.util, random
from pathlib import Path
import build_hybrid_v4_dataset as dsp
BASE_DIR = Path(__file__).resolve().parent
# reuse the keyword labeller + file map
spec=importlib.util.spec_from_file_location("lb", BASE_DIR / "build_all_packs_dataset_v2.py")
lb=importlib.util.module_from_spec(spec)
import sys; sys.modules["lb"]=lb
try: spec.loader.exec_module(lb)
except SystemExit: pass
fn_map=dsp.build_filename_map(dsp.SOURCE_ROOT)
d=np.load(BASE_DIR / 'slo_all_packs_hybrid_v4.npz',allow_pickle=True)
fns=d['filenames']; labs=np.array([str(v) for v in d['labels']])

def fundamental_hz(path, fmax=600):
    """Dominant spectral peak below fmax, from the attack (first 100ms)."""
    try:
        y,sr=sf.read(path,dtype='float32',always_2d=False)
        if y.ndim>1: y=y.mean(1)
        if len(y)<256: return None
        y=y[:int(sr*0.12)]  # attack window where the pitch lives
        w=y*np.hanning(len(y))
        mag=np.abs(np.fft.rfft(w, n=1<<15))
        freqs=np.fft.rfftfreq(1<<15, 1/sr)
        band=(freqs>=30)&(freqs<=fmax)
        if not band.any(): return None
        return float(freqs[band][np.argmax(mag[band])])
    except Exception: return None

random.seed(0)
print(f"{'class':>8} {'n':>4}  {'f0 median':>9} {'p25':>6} {'p75':>6}  {'user range':>12}")
ranges={'Kick':'50-120','Snare':'180-350','Hi-Hat':'>350 noise','Clap':'180-350'}
for c in ['Kick','Snare','Hi-Hat','Clap']:
    idx=[i for i in np.where(labs==c)[0] if str(fns[i]) in fn_map]
    random.shuffle(idx); idx=idx[:300]
    f0=[fundamental_hz(fn_map[str(fns[i])]) for i in idx]
    f0=np.array([x for x in f0 if x]); 
    print(f"{c:>8} {len(f0):4d}  {np.median(f0):8.0f}Hz {np.percentile(f0,25):5.0f} {np.percentile(f0,75):5.0f}  {ranges[c]:>12}")
# separability: kick vs snare by a single f0 threshold at 150Hz
ki=[i for i in np.where(labs=='Kick')[0] if str(fns[i]) in fn_map][:300]
si=[i for i in np.where(labs=='Snare')[0] if str(fns[i]) in fn_map][:300]
kf=np.array([x for x in (fundamental_hz(fn_map[str(fns[i])]) for i in ki) if x])
sf_=np.array([x for x in (fundamental_hz(fn_map[str(fns[i])]) for i in si) if x])
thr=150
acc=( (kf<thr).sum()+(sf_>=thr).sum() )/(len(kf)+len(sf_))
print(f"\nKick-vs-Snare by single f0 threshold at {thr}Hz: {100*acc:.1f}% ({100*(kf<thr).mean():.0f}% kicks below, {100*(sf_>=thr).mean():.0f}% snares above)")
