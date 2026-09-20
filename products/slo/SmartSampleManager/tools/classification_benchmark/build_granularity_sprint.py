#!/usr/bin/env python3
"""
Task 2/3 -- the granularity + token-risk sprint export.

The remaining risky tokens are GRANULARITY problems, not regex bugs. `perc`
usually means Percussion Loop; `loop` means a specific kind of loop; `top` is
half Hi-Hat Loop. Deleting them would lose real evidence; the fix is labels that
settle the boundary.

Selection is by EVIDENCE OF DIFFICULTY, not by class name -- picking files that
are already easy teaches nothing:

  high-risk token hits            the tokens we cannot currently trust
  name/audio disagreement         where fusion has to choose and might be wrong
  low classifier confidence       the review queue -- is abstaining correct?
  known false accepts             junk given a confident class
  thin classes                    Top Loop (6), Sub Bass (2) -- unscoreable today
  rejection boundary              Other/none, the largest error source

Read-only: selects paths, copies no audio, touches no sample.
"""
import os, csv, json, re, random, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import name_evidence as ne, acoustic_evidence as ae
OUT = os.path.join(SD, "SLO_GRANULARITY_LABEL_SPRINT_EXPORT_V1.csv")
TAX = json.load(open(os.path.join(SD, "taxonomy_v1.json")))["taxonomy_version"]
DSV = json.load(open(os.path.join(SD, "ground_truth", "SLO_GT_V1",
                                  "manifest.json")))["dataset_version"]

QUOTA = {
    "top_hihat_loop": 60,
    "bass_family": 60,
    "percussion_family": 60,
    "foley_sfx_impact": 60,
    "rejection_boundary": 80,
    "low_conf_or_disagreement": 80,
}

# label options offered per bucket -- every list ends with escape hatches
OPTIONS = {
    "top_hihat_loop": ["Top Loop", "Hi-Hat Loop", "Percussion Loop", "Drum Loop",
                       "Hi-Hat", "Other/none"],
    "bass_family": ["Sub Bass", "808", "Reese Bass", "Bass Hit", "Bass Loop",
                    "Synth Bass Sustained", "Not Bass", "Other/none"],
    "percussion_family": ["Tom", "Shaker/Tambourine", "Hand Drum", "Metallic",
                          "Other Percussive Hit", "Percussion Loop", "Rimshot",
                          "Other/none"],
    "foley_sfx_impact": ["Foley", "Foley Loop", "SFX", "Impact", "Riser",
                         "Atmosphere", "Weather/Nature Atmos", "Other/none"],
    "rejection_boundary": ["Other/none", "Foley", "SFX", "Percussion Loop",
                           "Drum Loop", "Synth Loop", "Not a sample"],
    "low_conf_or_disagreement": ["Kick", "Snare", "Clap", "Hi-Hat", "Crash",
                                 "Percussion", "Percussion Loop", "Drum Loop",
                                 "Foley", "Other/none"],
}
ESCAPES = ["Unknown (write a note)", "Not in this list (write it)",
           "Not enough information", "Corrupt / unusable", "Taxonomy gap"]

HIGH_RISK = re.compile(r"\b(shaker|tops?|perc|snap|sub|loop|bass|sd|hit|chord|texture)\b", re.I)
TOPHAT = re.compile(r"\btops?\b|\bhat\b|\bhh\b|\bchh\b|\bohh\b|hi[\s-]*hat", re.I)
BASSRX = re.compile(r"\b808\b|\bsub\b|reese|\bbass\b|\bbs\b|\b909\b", re.I)
PERCRX = re.compile(r"\bperc|\btom\b|shaker|tamb|conga|bongo|rim|cowbell|clave", re.I)
FXRX = re.compile(r"\bfoley\b|\bsfx\b|\bfx\b|impact|texture|atmos|riser|ambien", re.I)


def norm(n):
    return re.sub(r"[_\-.]+", " ", os.path.splitext(os.path.basename(n))[0])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=400)
    a = ap.parse_args()
    rng = random.Random(23)

    gt = {r["path"]: r for r in csv.DictReader(
        open(os.path.join(SD, "ground_truth", "SLO_GT_V1", "labels.csv")))}
    for extra in ("verified_bass.csv", "verified_percussion_subtype.csv"):
        p = os.path.join(SD, extra)
        if os.path.exists(p):
            for r in csv.DictReader(open(p)):
                gt.setdefault(r["path"], {"label": r["label"], "collection": "",
                                          "pack": "", "percussion_subtype": ""})

    inv = json.load(open(os.path.join(SD, "sample_library_inventory_v1.json")))
    dups = set()
    for grp in inv["duplicate_groups"].values():
        for p in sorted(grp)[1:]:
            dups.add(p)
    files = [f for f in inv["files"]
             if f["path"] not in dups and (f.get("duration") or 0) > 0.05]

    # model opinion on the labelled corpus, for the difficulty-based buckets
    import eval_corpus_v2 as ec, incumbent_receipt as ir, mw_features as mwf
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.preprocessing import StandardScaler
    d = ec.load(min_class=15)
    X, y, g, lp = d["X"], d["y"], d["vendor"], d["paths"]
    M, mask = mwf.load_aligned(lp)
    if M is not None and not mask.all():
        X, y, g = X[mask], y[mask], g[mask]
        lp = [p for p, k in zip(lp, mask) if k]
        M = M
    Mz = StandardScaler().fit_transform(M)
    XM = np.hstack([X, Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)])
    C = sorted(set(y))
    oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(XM, y, groups=g):
        cls = sorted(set(y[tr]))
        p_, c_ = ir.centroid_fit_predict(XM[tr], y[tr], XM[te], cls)
        oof[te], conf[te] = p_, c_
    model = {lp[i]: (str(oof[i]), float(conf[i])) for i in range(len(lp))}

    rows, used = [], set()

    def add(bucket, cands, reason, limit=None):
        n = 0
        # NOT `limit or QUOTA[bucket]`: a computed top-up limit of 0 is falsy
        # and would fall back to the full quota, doubling the bucket.
        lim = QUOTA[bucket] if limit is None else limit
        if lim <= 0:
            return 0
        for f in cands:
            if n >= lim:
                break
            p = f["path"] if isinstance(f, dict) else f
            if p in used:
                continue
            used.add(p); n += 1
            rec = gt.get(p, {})
            nev = ne.extract(os.path.basename(p))
            mp, mc = model.get(p, ("", ""))
            rows.append({
                "bucket": bucket, "path": p, "filename": os.path.basename(p),
                "collection": rec.get("collection", "") or (f.get("vendor", "") if isinstance(f, dict) else ""),
                "pack": rec.get("pack", "") or (f.get("pack", "") if isinstance(f, dict) else ""),
                "current_label": rec.get("label", ""),
                "current_subtype": rec.get("percussion_subtype", ""),
                "model_prediction": mp,
                "model_confidence": round(mc, 3) if mc != "" else "",
                "token_evidence": "|".join(nev.tokens),
                "token_risk": nev.risk_level,
                "token_candidates": "|".join(nev.candidate_classes),
                "token_families": "|".join(nev.candidate_families),
                "action_state": ("review" if (mc == "" or mc < 0.5) else "suggest"),
                "reason_selected": reason,
                "options": " / ".join(OPTIONS[bucket] + ESCAPES),
                "label": "", "subtype": "", "form": "",
                "not_in_list_label": "", "not_enough_info": "",
                "taxonomy_gap": "", "reviewer_confidence": "", "note": "",
                "taxonomy_version": TAX, "dataset_version": DSV,
            })
        return n

    # 1. top / hi-hat loop -- 6 and 13 labels today, the overlap is unevidenced
    cands = [f for f in files if TOPHAT.search(norm(f["filename"]))
             and f["path"] not in gt]
    rng.shuffle(cands)
    add("top_hihat_loop", cands, "top/hat token: Top Loop has 6 labels, the "
                                 "Top-vs-Hi-Hat-Loop overlap is unevidenced")
    # 2. bass family -- Sub Bass has 2 labels
    cands = [f for f in files if BASSRX.search(norm(f["filename"]))
             and f["path"] not in gt]
    rng.shuffle(cands)
    add("bass_family", cands, "bass token: Sub Bass has 2 labels, 'sub' measures "
                              "11% and 'bass' 0%")
    # 3. percussion family -- perc measures 29%, shaker 43%
    cands = [f for f in files if PERCRX.search(norm(f["filename"]))
             and f["path"] not in gt]
    rng.shuffle(cands)
    add("percussion_family", cands, "perc/shaker/tom token: 'perc' measures 29% "
                                    "and usually means Percussion Loop")
    # 4. foley / sfx / impact / texture
    cands = [f for f in files if FXRX.search(norm(f["filename"]))
             and f["path"] not in gt]
    rng.shuffle(cands)
    add("foley_sfx_impact", cands, "fx/foley/texture token: 'texture' measures "
                                   "0%, Atmosphere has 3 labels")
    # 5. rejection boundary -- known false accepts first, then unlabelled
    fa = [p for p in lp if y[list(lp).index(p)] == "Other/none"
          and model.get(p, ("", 0))[0] != "Other/none"] if len(lp) else []
    got = add("rejection_boundary", fa,
              "junk given a confident real class -- the binding product risk")
    noev = [f for f in files if f["path"] not in gt
            and not ne.extract(f["filename"]).tokens]
    rng.shuffle(noev)
    add("rejection_boundary", noev,
        "no filename evidence at all -- the population the model must judge alone",
        limit=QUOTA["rejection_boundary"] - got)
    # 6. low confidence or name/audio disagreement
    lowc = sorted([p for p in lp if model[p][1] < 0.45], key=lambda q: model[q][1])
    got = add("low_conf_or_disagreement", lowc,
              "classifier abstained -- is the review queue right?")
    disagree = [p for p in lp
                if ne.extract(os.path.basename(p)).candidate_classes
                and model[p][0] not in ne.extract(os.path.basename(p)).candidate_classes]
    add("low_conf_or_disagreement", disagree,
        "filename and audio disagree -- fusion must choose",
        limit=QUOTA["low_conf_or_disagreement"] - got)

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} files -> {os.path.basename(OUT)}")
    for b, n in Counter(r["bucket"] for r in rows).most_common():
        short = "" if n >= QUOTA[b] else f"   SHORT by {QUOTA[b]-n}"
        print(f"  {b:26} {n:4d} / {QUOTA[b]}{short}")
    print(f"  collections: {len({r['collection'] for r in rows if r['collection']})}")
    print(f"  already labelled: {sum(1 for r in rows if r['current_label'])}")
    print(f"  never labelled  : {sum(1 for r in rows if not r['current_label'])}")
    print(f"  high-risk token : {sum(1 for r in rows if r['token_risk']=='high')}")
    print("  NO AUDIO COPIED -- paths and metadata only")


if __name__ == "__main__":
    main()
