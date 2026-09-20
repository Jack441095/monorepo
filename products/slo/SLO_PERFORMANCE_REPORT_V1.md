# SLO Performance Report V1

> **STATUS (2026-09-17): SUPERSEDED as a standalone claim — see `SLO_BETA_BLOCKER_REGISTER_V2.md` B-009 (100/1k/10k + soak clean) and research task R-06 for the single regenerated receipt. Do not quote the 170-file numbers below externally.**

## Historical evidence

The repository performance artifact for a 170-file synthetic fixture reports:

- Cold scan mean: **25,043 ms**.
- Cached scan mean: **921 ms**.
- RSS peak: **2,439 MB**.
- RSS after scan: **1,360 MB**.

These are historical and fixture-specific. Current 1,000- and 10,000-file gates were not regenerated in this read-mostly audit.

## Risk assessment

Cold inference and resident memory are the dominant beta risks. A 2.4 GB peak on a 16 GB Mac is material for a DAW host, especially with multiple plugin instances or a large Live set. Cache reuse is much faster, but the retained RSS still needs a product policy.

## Required gate

Run representative 100/1,000/10,000-file scans on a clean machine, record cold/warm/rescan timings, peak and post-scan RSS, concurrent instance behavior, and a soak. Set a documented ceiling and show progress/cancellation behavior. Until then: read-only beta, bounded fixture sizes, and one-instance guidance.
