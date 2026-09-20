#!/usr/bin/env python3
"""
Merge the new domain-coverage labels into one aligned corpus.

Two label files now exist: the original verified_drums.csv and the new
verified_domain_coverage.csv from the breadth-first batch. They must be merged
by PATH, never by id -- the two manifests number their files independently, so
ids collide by construction.

The output is a single npz whose paths, labels and embeddings correspond by
construction, which is the only way this project has found to avoid the row
misalignment that produced a bogus 53.7% earlier.

Resumable: embeddings already present in bioacoustic_emb.npz or in a previous
run of this script are reused; only genuinely new files are encoded.
"""
import os, csv, json, time, argparse
import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SD, "corpus_v2.npz")
OLD_CSV = os.path.join(SD, "verified_drums.csv")
NEW_CSV = os.path.join(SD, "verified_domain_coverage.csv")
OLD_EMB = os.path.join(SD, "bioacoustic_emb.npz")

DROP = ("__skip__", "Misc/Review")


def read_labels(path, source):
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path)):
        if r["label"] in DROP or not os.path.exists(r["path"]):
            continue
        out.append({"path": r["path"], "label": r["label"], "source": source,
                    "percussion_subtype": r.get("percussion_subtype", ""),
                    "rejection_reason": r.get("rejection_reason", "")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()

    old = read_labels(OLD_CSV, "drums_v1")
    new = read_labels(NEW_CSV, "domain_coverage")
    print(f"old corpus: {len(old)} usable rows")
    print(f"new batch : {len(new)} usable rows")

    # merge by path, first occurrence wins; report any disagreement rather than
    # silently choosing
    seen, merged, conflicts = {}, [], []
    for r in old + new:
        p = r["path"]
        if p in seen:
            if seen[p]["label"] != r["label"]:
                conflicts.append((p, seen[p]["label"], r["label"]))
            continue
        seen[p] = r
        merged.append(r)
    if conflicts:
        print(f"\n{len(conflicts)} PATHS WITH CONFLICTING LABELS "
              f"(kept the first; review these):")
        for p, a1, b1 in conflicts[:10]:
            print(f"   {os.path.basename(p)[:44]:46} {a1!r} vs {b1!r}")
    print(f"\nmerged   : {len(merged)} unique paths "
          f"({len(merged)-len(old)} genuinely new)")

    # reuse existing embeddings where the path already had one
    have = {}
    if os.path.exists(OLD_EMB):
        z = np.load(OLD_EMB)
        oldpaths = [r["path"] for r in read_labels(OLD_CSV, "x")]
        # bioacoustic_emb.npz is positional over that same filtered list
        if len(z["perch"]) == len(oldpaths):
            for i, p in enumerate(oldpaths):
                have[p] = np.hstack([z["perch"][i], z["clap"][i]])
            print(f"reusing  : {len(have)} cached embeddings")
        else:
            print(f"WARNING: bioacoustic cache has {len(z['perch'])} rows but "
                  f"{len(oldpaths)} old paths -- not reusing, will re-encode")
    if os.path.exists(OUT):
        z = np.load(OUT, allow_pickle=True)
        for i, p in enumerate(list(z["paths"])):
            have.setdefault(p, z["emb"][i])
        print(f"reusing  : {len(have)} after previous corpus_v2 run")

    todo = [r["path"] for r in merged if r["path"] not in have]
    print(f"to encode: {len(todo)}")
    if todo:
        import aug_experiment as ax
        from multiprocessing import Pool

        def _enc(paths):
            pass
        t0 = time.time()
        with Pool(a.workers, initializer=ax._init_worker) as pool:
            for i, (p, em, vs, err) in enumerate(
                    pool.imap_unordered(_encode_one, [(q, "__orig__") for q in todo])):
                if err:
                    print(f"   skip {os.path.basename(p)[:40]}: {err}")
                else:
                    have[p] = em[0]
                if (i + 1) % 20 == 0:
                    print(f"   {i+1}/{len(todo)}  {(i+1)/(time.time()-t0):.2f}/s",
                          flush=True)

    keep = [r for r in merged if r["path"] in have]
    dropped = len(merged) - len(keep)
    if dropped:
        print(f"dropped {dropped} rows with no embedding")
    paths = [r["path"] for r in keep]
    emb = np.array([have[p] for p in paths], dtype=np.float32)
    assert len(emb) == len(paths) == len(keep), "alignment failure"
    np.savez(OUT, emb=emb, paths=np.array(paths, dtype=object),
             labels=np.array([r["label"] for r in keep]),
             source=np.array([r["source"] for r in keep]),
             percussion_subtype=np.array([r["percussion_subtype"] for r in keep]),
             rejection_reason=np.array([r["rejection_reason"] for r in keep]))
    print(f"\nwrote corpus_v2.npz: {emb.shape[0]} rows, {emb.shape[1]}-D")


def _encode_one(task):
    """Encode ONE original (unaugmented) file. Mirrors aug_experiment._one."""
    import aug_experiment as ax
    path, _ = task
    try:
        y = ax._load_native(path)
        if len(y) < ax.NATIVE_SR // 50:
            y = np.pad(y, (0, ax.NATIVE_SR // 50 - len(y)))
        em = ax._W["enc"].embed([y])
        if not np.isfinite(em).all():
            return (path, None, None, "non-finite")
        return (path, em.astype(np.float32), None, None)
    except Exception as e:
        return (path, None, None, str(e)[:70])


if __name__ == "__main__":
    main()
