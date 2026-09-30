"""Keep pytest from collecting the research scripts that happen to be named test_*.

`test_f0_drums.py`, `test_f0_gain.py` and `test_batch_extract.py` are one-off
research scripts, not tests: none of them defines a `test_` function, and each
one loads the gitignored 100MB `slo_all_packs_hybrid_v4.npz` and runs
`cross_val_score` at module scope. pytest collected them anyway, so on a clean
clone the suite aborted with three collection errors before a single assertion
ran -- the 358 real tests were unreachable unless you knew to pass --ignore.

They are named `test_*` because they were exploratory feature probes (F0 drums,
F0 gain) and the names are cited in
`SmartSampleManager/docs/classification/SLO_CLASSIFICATION_V4_REMEDIATION_2026-09-09.md`,
so renaming them would break a provenance trail. Skipping collection here keeps
the citation intact and makes a bare `pytest` do the right thing.

If any of these ever becomes a real test, delete its entry below instead.
"""

collect_ignore = [
    "test_f0_drums.py",
    "test_f0_gain.py",
    "test_batch_extract.py",
]
