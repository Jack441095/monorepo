#!/usr/bin/env python3
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from tools.classification_benchmark.build_all_packs_dataset import (
    worker_init, process_single_sample, SOURCE_ROOT, classify_relpath_and_name, AUDIO_EXTS
)

def main():
    samples = []
    for pack in sorted(os.listdir(SOURCE_ROOT)):
        pdir = os.path.join(SOURCE_ROOT, pack)
        if not os.path.isdir(pdir) or pack.startswith("."):
            continue
        for root, dirs, files in os.walk(pdir):
            rel = os.path.relpath(root, pdir)
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in AUDIO_EXTS and not f.startswith("."):
                    cls = classify_relpath_and_name(rel, f)
                    if cls:
                        samples.append((os.path.join(root, f), cls, pack, f))
                if len(samples) >= 100:
                    break
            if len(samples) >= 100:
                break
        if len(samples) >= 100:
            break

    print(f"Testing {len(samples)} samples with ProcessPoolExecutor...", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=8, initializer=worker_init) as ex:
        results = list(ex.map(process_single_sample, samples, chunksize=16))
    dt = time.time() - t0
    valid = [r for r in results if r is not None]
    print(f"SUCCESS: Processed {len(valid)}/{len(samples)} valid samples in {dt:.2f}s ({len(valid)/dt:.1f} samples/sec)!", flush=True)

if __name__ == "__main__":
    main()
