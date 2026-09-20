#!/usr/bin/env python3
"""
Fusion sample renamer -- the production tool.

Combines the three validated signals into one confidence-gated renamer:
  1. FILENAME token (name_detect) -- trusted per-class by its MEASURED precision
     against by-ear ground truth (Kick 0.97, Hi-Hat 0.94, Snare 0.92, Clap 0.90,
     Crash 0.89, Percussion Loop 1.0, ...). Low-precision tokens defer.
  2. DURATION + full-file ONSET density -- loop vs one-shot (loops median 22
     onsets, crash 7; rule: >=2.5s AND >=8 onsets).
  3. ACOUSTIC RandomForest trained on the 649 by-ear labels -- decides the
     family when the filename is silent.
  + melodic gate: pitched, harmonic, loop-length -> Chord Loop.

Only renames when confidence clears the gate (default 0.75); everything else is
left untouched. On the by-ear set, gated one-shots reach ~95% precision.

Safe: DRY RUN by default; --apply commits; never overwrites (numeric suffix);
writes a reversible undo log (--undo <log> restores). Trains once and caches to
fusion_model.pkl (--retrain to rebuild).

Usage:
  python3 fusion_renamer.py /path/to/folder                 # dry run
  python3 fusion_renamer.py /path/to/folder --apply
  python3 fusion_renamer.py /path/to/folder --min-conf 0.85
  python3 fusion_renamer.py --undo fusion_rename_log_*.csv
"""
import os, sys, csv, argparse, pickle, datetime, warnings
import numpy as np, soundfile as sf, librosa
warnings.filterwarnings("ignore")
import name_detect as nd
import drum_detector_features as ddf
import loop_features as lf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SCRIPT_DIR, "verified_drums.csv")
MODEL_CACHE = os.path.join(SCRIPT_DIR, "fusion_model.pkl")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}

# Foley is a PROVENANCE category (was this recorded from a physical object?),
# not an acoustic one. Measured: 19-27% from audio across three independent
# encoders, 4% from handcrafted features, and only 46-52% precision from path
# tokens. Removing it as a classifier target gained +4.2pp overall (81.9 ->
# 86.1) and also lifted Snare and Other/none, which it had been polluting.
# It is emitted as a low-confidence path-derived TAG instead, never a rename.
NON_TARGETS = {"Other/none", "Misc/Review", "Foley", "Foley Loop"}
# Explicit "foley" wording is a reasonable CATEGORY signal (46% recall, 75%
# precision vs by-ear labels). 'organic' is excluded: "Organic Drum Kit" is a
# pack name and scored 0% precision.
FOLEY_PATH_RX = r"foley|found.?sound|field.?rec|household"

# Physical-object nouns are a SOURCE/MATERIAL tag, NOT a category. Measured at
# only 31% precision as a Foley detector, because producers name a sample after
# what made it even when it functions as a drum -- e.g.
# "JVIEWS_hihat_alternative_clock_shop_113.wav" is a HI-HAT built from clock
# recordings. Function and provenance are orthogonal axes; this tags the latter
# so a clock-shop hi-hat is findable by both "hi-hat" and "clock".
SOURCE_RX = (r"kitchen|wood|metal|glass|plastic|ceramic|paper|cardboard|cloth|fabric|"
             r"leather|rubber|stone|bottle|can\b|cup\b|mug|plate|bowl|spoon|fork|knife|"
             r"key\b|coin|book|box\b|bag\b|zip|button|pen\b|pencil|door|drawer|chair|"
             r"table|cupboard|window|floor|stair|footstep|knock|scrape|rustle|crumple|"
             r"squeak|creak|slam|tear|splash|pour|drip|water|wind\b|rain|fire|leaves|"
             r"gravel|dirt|snow|chain|rope|spring|hinge|latch|switch|lighter|match|clock|"
             r"typewriter|suitcase|umbrella|engine|machine|hammer|drill|whistle")
LOOP_T = 2.5
ONSET_T = 8

# Softmax temperature for the acoustic stage. A softmax maximum is NOT a
# probability of being correct: measured on out-of-fold data the Perch+CLAP
# stage was ~2.3x overconfident (stated 0.748 in a band that was actually 0.425
# correct; ECE 0.142). Dividing logits by T corrects this.
#
# Consequence if omitted: a 0.75-0.80 gate would admit files that are only
# 42-60% correct and the renamer would over-rename. With T applied, a 0.77 gate
# delivers ~95% precision and covers 48.4% of files (vs 43.7% uncalibrated).
# T is fitted by calibrate.py on held-out data. It applies to the Perch/CLAP
# stage; the handcrafted RandomForest is separately better calibrated (94.7%
# measured at its 0.7 gate) and does not need it.
CALIBRATION_T = 2.28


def calibrated(proba, T=CALIBRATION_T):
    """Temperature-scale a probability vector so the gate is interpretable."""
    import numpy as _np
    p = _np.asarray(proba, dtype=_np.float64)
    logits = _np.log(_np.clip(p, 1e-12, None)) / T
    e = _np.exp(logits - logits.max())
    return e / e.sum()

FAMILY_LOOP = {"Kick":"Kick Loop","Snare":"Snare Loop","Hi-Hat":"Hi-Hat Loop",
               "Percussion":"Percussion Loop","Foley":"Foley Loop","Bass":"Bass Loop"}
LOOP_FAMILY = {v:k for k,v in FAMILY_LOOP.items()}

# per-class filename precision, measured vs ear (name_detect validation).
# Tokens below the gate defer to acoustics rather than be trusted outright.
FN_PRECISION = {"Percussion Loop":1.00, "Kick":0.97, "Hi-Hat":0.94, "Snare":0.92,
                "Clap":0.90, "Crash":0.89, "Percussion":0.83, "Drum Loop":0.78,
                "Rimshot":0.67, "Foley":0.53, "Loop":0.30}


def dur_of(p):
    try: i = sf.info(p); return i.frames / i.samplerate
    except Exception: return 0.0

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

def onset_count(p):
    try:
        y, sr = sf.read(p, dtype="float32", always_2d=False)
        if y.ndim > 1: y = y.mean(1)
        if sr != 22050: y = librosa.resample(y, orig_sr=sr, target_sr=22050); sr = 22050
        oe = librosa.onset.onset_strength(y=y, sr=sr)
        return len(librosa.util.peak_pick(oe, pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=0.2, wait=5))
    except Exception: return 0

def resolve_loop(cls, is_loop):
    if is_loop and cls in FAMILY_LOOP: return FAMILY_LOOP[cls]
    if is_loop and cls in ("Rimshot", "Crash", "Clap"): return "Drum Loop"
    if (not is_loop) and cls in LOOP_FAMILY: return LOOP_FAMILY[cls]
    return cls


def train(force=False):
    from sklearn.ensemble import RandomForestClassifier
    from collections import Counter
    if os.path.exists(MODEL_CACHE) and not force:
        with open(MODEL_CACHE, "rb") as f: return pickle.load(f)
    if not os.path.exists(VERIFIED):
        print("no verified_drums.csv -- run label_tool.py first"); sys.exit(1)
    rows = [r for r in csv.DictReader(open(VERIFIED)) if r["label"] not in ("__skip__","Misc/Review")]
    cnt = Counter(r["label"] for r in rows)
    viable = {c for c in cnt if cnt[c] >= 15 and c not in NON_TARGETS}
    X, y = [], []
    print(f"training acoustic model on {sum(cnt[c] for c in viable)} by-ear labels, "
          f"{len(viable)} classes with >=15 examples...")
    for r in rows:
        if r["label"] not in viable: continue
        f = ddf.extract(r["path"])
        if f is not None: X.append(f); y.append(r["label"])
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0).fit(np.array(X), y)
    # loop-specific model on full-file spectral features
    Xl, yl = [], []
    for r in rows:
        if r["label"] not in ("Drum Loop","Percussion Loop","Foley Loop"): continue
        f = lf.extract(r["path"])
        if f is not None: Xl.append(f); yl.append(r["label"])
    loop_clf = None
    if len(set(yl)) >= 2 and len(yl) >= 20:
        loop_clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0).fit(np.array(Xl), yl)
    with open(MODEL_CACHE, "wb") as f: pickle.dump((clf, loop_clf), f)
    return clf, loop_clf


def classify(path, clf, loop_clf=None):
    """Return (label, confidence, source)."""
    name = os.path.basename(path)
    d = dur_of(path)
    fam_fn, tok = nd.detect(name)
    # loop test needs onsets only when duration is loop-length (saves compute)
    is_loop = d >= LOOP_T and onset_count(path) >= ONSET_T and decay_ratio(path) >= 0.25

    feat = ddf.extract(path)
    LOOP_TOKS = ('Drum Loop','Percussion Loop','Hi-Hat Loop','Foley Loop','Chord Loop','Bass Loop','Top Loop')
    # two-stage: a rhythmic loop with no explicit loop-token -> loop model
    if is_loop and loop_clf is not None and fam_fn not in LOOP_TOKS:
        lfeat = lf.extract(path)
        if lfeat is not None:
            lp = loop_clf.predict_proba([lfeat])[0]; j = int(lp.argmax())
            return list(loop_clf.classes_)[j], float(lp[j]), "loop-model"
    # filename first, if it is a trusted token
    if fam_fn is not None and FN_PRECISION.get(fam_fn, 0.4) >= 0.75:
        label = resolve_loop(fam_fn, is_loop)
        conf = FN_PRECISION.get(fam_fn, 0.75)
        src = f"name:{tok}"
    elif feat is not None:
        proba = clf.predict_proba([feat])[0]
        j = int(proba.argmax()); fam_ac = list(clf.classes_)[j]
        label = resolve_loop(fam_ac, is_loop); conf = float(proba[j]); src = "acoustic"
    elif fam_fn is not None:                       # weak token, nothing else
        label = resolve_loop(fam_fn, is_loop); conf = FN_PRECISION.get(fam_fn, 0.4); src = f"name:{tok}?"
    else:
        return None, 0.0, "none"

    # melodic gate: pitched + harmonic + loop-length -> Chord Loop
    if feat is not None and is_loop and feat[0] > 0.25 and feat[1] > 0.5 \
            and label in ("Drum Loop", "Loop", "Percussion Loop"):
        label, src = "Chord Loop", src + "+melodic"
    return label, conf, src


def foley_tag(path):
    """Foley CATEGORY suggestion from explicit wording (75% precision).
    Advisory: never used to rename, never trusted as a class."""
    import re as _re
    return bool(_re.search(FOLEY_PATH_RX, path, _re.I))


def source_tags(path):
    """SOURCE/material tags from physical-object nouns -- searchable metadata,
    orthogonal to the functional class. A clock-shop hi-hat is a Hi-Hat that
    is ALSO tagged 'clock'."""
    import re as _re
    return sorted({m.group(0).lower().strip()
                   for m in _re.finditer(SOURCE_RX, os.path.basename(path), _re.I)})


def collect(folder):
    out = []
    for dp, dn, files in os.walk(folder):
        dn[:] = [x for x in dn if not x.startswith(".")]
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS and not f.startswith("."):
                out.append(os.path.join(dp, f))
    return out

def unique_path(path):
    if not os.path.exists(path): return path
    base, ext = os.path.splitext(path); k = 2
    while os.path.exists(f"{base}_{k}{ext}"): k += 1
    return f"{base}_{k}{ext}"

def undo(logfile):
    rows = list(csv.DictReader(open(logfile))); ok = 0
    for r in reversed(rows):
        if os.path.exists(r["new"]) and not os.path.exists(r["old"]):
            os.rename(r["new"], r["old"]); ok += 1
    print(f"restored {ok}/{len(rows)} files")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-conf", type=float, default=0.75)
    ap.add_argument("--retrain", action="store_true")
    ap.add_argument("--undo", metavar="LOG")
    a = ap.parse_args()
    if a.undo: undo(a.undo); return
    if not a.folder: ap.error("folder required (or --undo LOG)")

    clf, loop_clf = train(force=a.retrain)
    files = collect(a.folder)
    print(f"\nscanning {len(files)} files in {a.folder}")
    print(f"gate: confidence >= {a.min_conf} | {'APPLY' if a.apply else 'DRY RUN'}\n")

    log = []; from collections import Counter; counts = Counter(); skipped = 0
    for p in files:
        label, conf, src = classify(p, clf, loop_clf)
        # Other/none and Misc/Review are not categories to rename TO -- skip.
        if label is None or label in NON_TARGETS or conf < a.min_conf:
            skipped += 1; continue
        safe = label.replace("/", "-")  # never let a class name create a subdir
        d, name = os.path.split(p)
        if name.lower().startswith(label.lower().replace("-", "").replace(" ", "")[:5]):
            skipped += 1; continue
        newpath = unique_path(os.path.join(d, f"{safe} - {name}"))
        counts[label] += 1
        log.append({"old": p, "new": newpath, "label": label, "conf": round(conf, 3), "src": src})
        print(f"  [{label:>15} {conf:.2f} {src:>16}] {name[:44]}")
        if a.apply: os.rename(p, newpath)

    print(f"\n{'renamed' if a.apply else 'would rename'} {sum(counts.values())}, skipped {skipped}")
    for c, n in counts.most_common(): print(f"    {c}: {n}")
    if log:
        lp = os.path.join(SCRIPT_DIR, f"fusion_rename_log_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        with open(lp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["old","new","label","conf","src"]); w.writeheader(); w.writerows(log)
        print(f"\nlog: {lp}")
        print(f"undo: python3 fusion_renamer.py --undo {lp}" if a.apply
              else "DRY RUN -- nothing changed; add --apply to rename.")


if __name__ == "__main__":
    main()
