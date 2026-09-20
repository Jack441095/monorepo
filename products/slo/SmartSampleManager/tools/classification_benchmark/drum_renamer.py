#!/usr/bin/env python3
"""
Confidence-gated drum one-shot renamer.

Walks a folder, classifies each file as Kick/Snare/Hi-Hat/Clap using the
enriched handcrafted-feature detector (drum_detector_features.extract), and
renames ONLY files it is confident about, prefixing the detected class.
Everything else is left untouched.

Safe by design:
  - DRY RUN by default. Nothing is renamed without --apply.
  - Never overwrites: a name collision gets a numeric suffix.
  - Writes a reversible undo log (drum_rename_log.csv). `--undo <log>` restores.
  - Confidence gate (--min-conf, default 0.8) so precision stays high and
    ambiguous files are skipped rather than mis-tagged.

Training data:
  Prefers verified_drums.csv (by-ear ground truth from label_tool.py). Falls
  back to keyword labels from the corpus if no verified labels exist, and says
  which it used -- keyword-trained precision is only as good as the keywords.

Usage:
  python3 drum_renamer.py /path/to/folder                 # dry run
  python3 drum_renamer.py /path/to/folder --apply         # rename for real
  python3 drum_renamer.py /path/to/folder --min-conf 0.9  # stricter
  python3 drum_renamer.py --undo drum_rename_log.csv      # revert
"""
import os, sys, csv, argparse, random, importlib.util, pickle, datetime
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DRUMS = ["Kick", "Snare", "Hi-Hat", "Clap"]
MODEL_CACHE = os.path.join(SCRIPT_DIR, "drum_model.pkl")
VERIFIED = os.path.join(SCRIPT_DIR, "verified_drums.csv")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}

import drum_detector_features as ddf


def _labeller():
    spec = importlib.util.spec_from_file_location("lb", os.path.join(SCRIPT_DIR, "build_all_packs_dataset_v2.py"))
    m = importlib.util.module_from_spec(spec); sys.modules["lb"] = m
    try: spec.loader.exec_module(m)
    except SystemExit: pass
    return m


def train_model(force=False):
    """Return (clf, source_str). Cache to disk unless force."""
    from sklearn.ensemble import RandomForestClassifier
    if os.path.exists(MODEL_CACHE) and not force:
        with open(MODEL_CACHE, "rb") as f:
            d = pickle.load(f)
        return d["clf"], d["source"]

    X, y, source = [], [], None
    # 1) verified by-ear labels, if present
    if os.path.exists(VERIFIED):
        rows = [r for r in csv.DictReader(open(VERIFIED)) if r["label"] in DRUMS]
        if len(rows) >= 40:  # enough to train something
            print(f"training on {len(rows)} BY-EAR verified labels")
            for r in rows:
                f = ddf.extract(r["path"])
                if f is not None: X.append(f); y.append(r["label"])
            source = f"verified ({len(rows)} by-ear labels)"

    # 2) fall back to keyword labels
    if source is None:
        print("no verified labels yet -- training on KEYWORD labels (precision "
              "limited by keyword accuracy; run label_tool.py to improve)")
        import build_hybrid_v4_dataset as dsp
        fn_map = dsp.build_filename_map(dsp.SOURCE_ROOT)
        d = np.load(os.path.join(SCRIPT_DIR, "slo_all_packs_hybrid_v4.npz"), allow_pickle=True)
        fns = d["filenames"]; labs = np.array([str(v) for v in d["labels"]])
        rng = random.Random(42)
        for c in DRUMS:
            idx = [i for i in np.where(labs == c)[0] if str(fns[i]) in fn_map]
            rng.shuffle(idx)
            for i in idx[:700]:
                f = ddf.extract(fn_map[str(fns[i])])
                if f is not None: X.append(f); y.append(c)
        source = "keyword labels (~700/class)"

    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0)
    clf.fit(np.array(X), np.array(y))
    with open(MODEL_CACHE, "wb") as f:
        pickle.dump({"clf": clf, "source": source}, f)
    print(f"model trained on: {source}  ({len(X)} examples)")
    return clf, source


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
    rows = list(csv.DictReader(open(logfile)))
    ok = 0
    for r in reversed(rows):  # reverse order in case of chains
        if os.path.exists(r["new"]) and not os.path.exists(r["old"]):
            os.rename(r["new"], r["old"]); ok += 1
    print(f"restored {ok}/{len(rows)} files")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--apply", action="store_true", help="actually rename (default is dry run)")
    ap.add_argument("--min-conf", type=float, default=0.8)
    ap.add_argument("--prefix-only", action="store_true",
                    help="prefix the class but keep original name (default); "
                         "files already starting with the class are skipped")
    ap.add_argument("--retrain", action="store_true")
    ap.add_argument("--undo", metavar="LOG")
    a = ap.parse_args()

    if a.undo:
        undo(a.undo); return
    if not a.folder:
        ap.error("folder required (or --undo LOG)")

    clf, source = train_model(force=a.retrain)
    files = collect(a.folder)
    print(f"\nscanning {len(files)} audio files in {a.folder}")
    print(f"model: {source} | gate: confidence >= {a.min_conf} | "
          f"{'APPLY' if a.apply else 'DRY RUN'}\n")

    log = []
    counts = {c: 0 for c in DRUMS}; skipped = 0
    classes = list(clf.classes_)
    for p in files:
        feat = ddf.extract(p)
        if feat is None:
            skipped += 1; continue
        proba = clf.predict_proba([feat])[0]
        j = int(proba.argmax()); conf = float(proba[j]); cls = classes[j]
        if conf < a.min_conf:
            skipped += 1; continue
        d, name = os.path.split(p)
        if name.lower().startswith(cls.lower().replace("-", "")):
            skipped += 1; continue
        newname = f"{cls} - {name}"
        newpath = unique_path(os.path.join(d, newname))
        counts[cls] += 1
        log.append({"old": p, "new": newpath, "class": cls, "conf": round(conf, 3)})
        tag = "RENAME" if a.apply else "would rename"
        print(f"  [{cls:>6} {conf:.2f}] {tag}: {name}  ->  {os.path.basename(newpath)}")
        if a.apply:
            os.rename(p, newpath)

    print(f"\n{'renamed' if a.apply else 'would rename'}: " +
          ", ".join(f"{c} {counts[c]}" for c in DRUMS) +
          f" | skipped (low-confidence/other/already-tagged): {skipped}")

    if log:
        logpath = os.path.join(SCRIPT_DIR,
            f"drum_rename_log_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        with open(logpath, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["old", "new", "class", "conf"]); w.writeheader()
            w.writerows(log)
        print(f"\nlog: {logpath}")
        if a.apply:
            print(f"undo with:  python3 drum_renamer.py --undo {logpath}")
        else:
            print("this was a DRY RUN — nothing changed. Re-run with --apply to rename.")


if __name__ == "__main__":
    main()
