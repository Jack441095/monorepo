#!/usr/bin/env python3
"""
Task 5 -- build the 400-file rejection-boundary sprint export.

Bucketed by what the model DOES with each file, because the point of this sprint
is to fix the rejection boundary, not to collect more easy labels. Read-only:
selects paths, copies no audio, touches no sample.
"""
import os, csv, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")
SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec, incumbent_receipt as ir, mw_features as mwf
import decision_policy as dp, name_detect as nd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from collections import Counter

OUT = os.path.join(SD, "SLO_400_FILE_LABEL_SPRINT_EXPORT_V1.csv")
TAX = json.load(open(os.path.join(SD, "taxonomy_v1.json")))["taxonomy_version"]

BUCKETS = {"confident_other_none": 80, "low_confidence": 80,
           "known_false_accept": 60, "impulse_response": 30,
           "top_vs_hihat_loop": 60, "bass_family": 60,
           "atmos_sfx_impact": 30}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=400)
    a = ap.parse_args()
    d = ec.load(min_class=1)
    X, y, g = d["X"], d["y"], d["vendor"]
    paths = d["paths"]
    M, mask = mwf.load_aligned(paths)
    if M is not None and not mask.all():
        X, y, g = X[mask], y[mask], g[mask]
        paths = [p for p, k in zip(paths, mask) if k]
        M = M
    Mz = StandardScaler().fit_transform(M)
    XM = np.hstack([X, Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)])
    C = sorted(set(y))
    oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(XM, y, groups=g):
        keep = np.isin(y[tr], [c for c in C if (y[tr] == c).sum() >= 2])
        cls = sorted(set(y[tr][keep]))
        p, c = ir.centroid_fit_predict(XM[tr][keep], y[tr][keep], XM[te], cls)
        oof[te], conf[te] = p, c

    gt = {r["path"]: r for r in csv.DictReader(
        open(os.path.join(SD, "ground_truth", "SLO_GT_V1", "labels.csv")))}
    rows, used = [], set()

    def add(bucket, idxs, reason):
        n = 0
        for i in idxs:
            if n >= BUCKETS[bucket] or paths[i] in used:
                continue
            p = paths[i]; used.add(p); n += 1
            rec = gt.get(p, {})
            dec = dp.decide(predicted_class=str(oof[i]), confidence=float(conf[i]),
                            path=p, filename_class=nd.detect(os.path.basename(p))[0])
            rows.append({"bucket": bucket, "path": p,
                         "filename": os.path.basename(p),
                         "collection": rec.get("collection", ""),
                         "pack": rec.get("pack", ""),
                         "current_label": rec.get("label", ""),
                         "current_subtype": rec.get("percussion_subtype", ""),
                         "prediction": str(oof[i]),
                         "confidence": round(float(conf[i]), 3),
                         "action": dec.action,
                         "reason_selected": reason,
                         "policy_reason": dec.reason,
                         "taxonomy_version": TAX,
                         "corrected_label": "",
                         "corrected_subtype": "",
                         "not_in_list_label": "",
                         "note": ""})
        return n

    order = np.argsort(-conf)
    add("confident_other_none", [i for i in order if oof[i] == "Other/none"],
        "model is confident this is junk -- is the rejection right?")
    add("low_confidence", list(np.argsort(conf)),
        "review queue: is abstaining correct here?")
    add("known_false_accept",
        [i for i in order if y[i] == "Other/none" and oof[i] != "Other/none"],
        "junk given a confident real class -- the binding product risk")
    add("impulse_response",
        [i for i in range(len(y)) if dp.is_impulse_response(paths[i])],
        "build a real IR class instead of a path heuristic")
    add("top_vs_hihat_loop",
        [i for i in range(len(y)) if y[i] in ("Top Loop", "Hi-Hat Loop")
         or oof[i] in ("Top Loop", "Hi-Hat Loop")],
        "the overlap is entirely unevidenced (6 and 13 labels)")
    add("bass_family",
        [i for i in range(len(y)) if y[i] in ("Bass Reese", "Bass Hit", "Sub Bass",
                                              "Bass Loop")
         or oof[i] in ("Bass Reese", "Bass Hit")],
        "Sub Bass has ZERO labels; Bass Hit has 11")
    add("atmos_sfx_impact",
        [i for i in range(len(y)) if y[i] in ("Atmosphere", "SFX", "Impact",
                                              "Weather/Nature Atmos", "Riser")],
        "Atmosphere has 3 labels; SFX is incoherent")

    # Top up short buckets from the UNLABELLED library. A rejection-boundary
    # sprint should mostly target files that have never been labelled -- drawing
    # only from the labelled corpus re-asks questions we already answered, and
    # three buckets (confident Other/none, impulse responses, Top/Hi-Hat Loop)
    # are short precisely because those classes are rare in what we have.
    inv_path = os.path.join(SD, "sample_library_inventory_v1.json")
    if os.path.exists(inv_path):
        import random, re as _re
        inv = json.load(open(inv_path))["files"]
        labelled = set(gt)
        rng = random.Random(17)
        by_pack = {}
        for f in inv:
            if f["path"] in labelled or f["path"] in used:
                continue
            by_pack.setdefault(f["pack"], []).append(f)
        for v in by_pack.values():
            rng.shuffle(v)

        def topup(bucket, pred, reason):
            need = BUCKETS[bucket] - sum(1 for r in rows if r["bucket"] == bucket)
            if need <= 0:
                return 0
            packs = sorted(by_pack, key=lambda k: rng.random())
            added, r_i = 0, 0
            while added < need:
                progressed = False
                for pk in packs:
                    if r_i < len(by_pack[pk]):
                        f = by_pack[pk][r_i]
                        progressed = True
                        if f["path"] in used or not pred(f):
                            continue
                        used.add(f["path"]); added += 1
                        rows.append({"bucket": bucket, "path": f["path"],
                                     "filename": f["filename"],
                                     "collection": f["vendor"], "pack": f["pack"],
                                     "current_label": "", "current_subtype": "",
                                     "prediction": "", "confidence": "",
                                     "action": "unlabelled",
                                     "reason_selected": reason,
                                     "policy_reason": "never labelled -- new evidence",
                                     "taxonomy_version": TAX,
                                     "corrected_label": "", "corrected_subtype": "",
                                     "not_in_list_label": "", "note": ""})
                        if added >= need:
                            break
                if not progressed:
                    break
                r_i += 1
            return added

        ir_re = _re.compile(r"impluse|impulse|/ir/", _re.I)
        tl_re = _re.compile(r"top|hat|hh|hi.?hat", _re.I)
        bs_re = _re.compile(r"sub|808|bass|reese", _re.I)
        topup("impulse_response", lambda f: bool(ir_re.search(f["path"])),
              "unlabelled IR material -- build a real IR class")
        topup("top_vs_hihat_loop", lambda f: bool(tl_re.search(f["filename"])),
              "unlabelled top/hat candidates -- settle the overlap")
        topup("bass_family", lambda f: bool(bs_re.search(f["filename"])),
              "unlabelled bass material -- Sub Bass has zero labels")
        topup("confident_other_none", lambda f: True,
              "unlabelled, no filename evidence -- the reject population")

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} files exported -> {os.path.basename(OUT)}")
    for b, n in Counter(r["bucket"] for r in rows).most_common():
        print(f"  {b:24} {n:4d} / {BUCKETS[b]}")
    print(f"  collections covered: {len({r['collection'] for r in rows})}")
    print(f"  NO AUDIO COPIED -- paths only")


if __name__ == "__main__":
    main()
