#!/usr/bin/env python3
"""
Cache interpretable physical descriptors for every file in corpus v2.

These are NOT model features -- that route is closed (handcrafted physics added
+0.0pp on top of the encoders). They are used to DEFINE and audit classes: to
split an incoherent class along a boundary a human can hear and state, and to
supply the temporal-form axis for the factorised taxonomy.

Resumable and alignment-safe: keyed by path, saved atomically, and the loader
returns rows in corpus order with an explicit assert.
"""
import os, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

import feature_cache as fc

SD = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(SD, "corpus_v2.npz")
CACHE = os.path.join(SD, "physics_cache_v1.npz")
DIGESTS = os.path.join(SD, "physics_cache_digests_v1.json")
VERSION = "phys-v1"
import class_anatomy as ca

NAMES = ca.NAMES


def load_aligned(paths):
    """Return (F, mask) with F in the SAME order as the paths where mask is True.

    A handful of files fail to decode. Returning a mask makes the caller drop
    them explicitly rather than silently imputing zeros -- an imputed row would
    sit at the origin of the feature space and quietly distort any clustering
    built on it.

    Entries are content-verified: a cached row is only used if the file still
    hashes to the digest recorded when the row was computed. Legacy rows
    without digests and rows whose file changed are dropped (stale row is
    worse than a recomputed one).
    """
    if not os.path.exists(CACHE):
        return None, None
    z = np.load(CACHE, allow_pickle=True)
    if "version" in z and str(z["version"]) != VERSION:
        return None, None
    cd = list(z["digests"]) if "digests" in z else [None] * len(z["paths"])
    digester = fc.DigestIndex(DIGESTS)
    have = {}
    for i, (p, d) in enumerate(zip(list(z["paths"]), cd)):
        cur = digester.digest(p)
        if cur is not None and cur == d:
            have[p] = i
    digester.flush()
    mask = np.array([p in have for p in paths])
    F = np.array([z["F"][have[p]] for p in paths if p in have], dtype=np.float32)
    assert len(F) == int(mask.sum()), "physics alignment failure"
    return F, mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    z = np.load(CORPUS, allow_pickle=True)
    paths = list(z["paths"])
    digester = fc.DigestIndex(DIGESTS)
    done = {}
    digests = {}
    if os.path.exists(CACHE):
        c = np.load(CACHE, allow_pickle=True)
        if "version" in c and str(c["version"]) != VERSION:
            print("cache version mismatch -- recomputing")
        else:
            cd = list(c["digests"]) if "digests" in c else [None] * len(c["paths"])
            for i, p in enumerate(list(c["paths"])):
                d = digester.digest(p)
                if d is not None and d == cd[i]:
                    done[p] = c["F"][i]
                    digests[p] = d
            print(f"resuming: {len(done)} content-verified cached "
                  f"({len(list(c['paths'])) - len(done)} stale/legacy dropped)")
    todo = [p for p in paths if p not in done]
    print(f"{len(paths)} files, {len(todo)} to compute")
    if todo:
        from multiprocessing import Pool
        import time
        t0 = time.time()
        with Pool(a.workers) as pool:
            for i, (p, r) in enumerate(zip(todo, pool.imap(ca.physics, todo,
                                                           chunksize=4))):
                if r is not None:
                    done[p] = np.array([r[n] for n in NAMES], dtype=np.float32)
                    d = digester.digest(p)
                    if d is not None:
                        digests[p] = d
                if (i + 1) % 200 == 0:
                    print(f"  {i+1}/{len(todo)}  {(i+1)/(time.time()-t0):.1f}/s",
                          flush=True)
        digester.flush()
    keep = [p for p in paths if p in done]
    F = np.array([done[p] for p in keep], dtype=np.float32)
    tmp = CACHE + ".tmp.npz"
    np.savez(tmp, F=F, paths=np.array(keep, dtype=object),
             names=np.array(NAMES, dtype=object), version=VERSION,
             digests=np.array([digests.get(p, "") for p in keep], dtype=object))
    os.replace(tmp, CACHE)
    print(f"wrote {os.path.basename(CACHE)}: {F.shape[0]} rows x {F.shape[1]} "
          f"descriptors ({len(paths)-len(keep)} unreadable)")


if __name__ == "__main__":
    main()
