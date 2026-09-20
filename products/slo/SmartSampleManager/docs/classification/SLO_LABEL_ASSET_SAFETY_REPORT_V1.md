# SLO Label Asset Safety Report V1

## Verdict: previously unsafe, now safe

**The risk found at audit:** all four working label CSVs — 1,175 rows of
irreplaceable by-ear labelling — were **gitignored** by a blanket
`verified_*.csv` rule. Between dataset builds they existed only on the sample
drive, which lost power during this work.

**Fixed.** The four critical CSVs are explicitly un-ignored. They contain file
paths and labels — metadata, never audio — so tracking them distributes no
licensed content.

| asset | status before | status now |
|---|---|---|
| `verified_drums.csv` | gitignored | **tracked** |
| `verified_domain_coverage.csv` | gitignored | **tracked** |
| `verified_percussion_subtype.csv` | gitignored | **tracked** |
| `verified_percussion_corrections.csv` | gitignored | **tracked** |
| `ground_truth/SLO_GT_V1/labels.csv` | tracked | tracked |

## Protections in place

**Versioned dataset.** `ground_truth/SLO_GT_V1/` carries `manifest.json` with
counts, provenance and per-asset SHA-256, plus `CHECKSUMS.sha256`.
`build_ground_truth.py --verify` re-checks every asset and reports source-CSV
drift.

**Per-row provenance.** `label_source`, `collection`, `pack`,
`sample_family_id`, `labelling_session`. Provenance is a covariate, not
bookkeeping — a label from an unseen collection is worth ~2× one from a familiar
collection.

**Off-drive backups.** Every build copies the dataset *and* the raw CSVs to
`~/slo_label_backups/` on the internal disk — deliberately not the sample drive.
15 snapshots exist.

**No silent overwrites.** Corrections preserve `original_label`, print every
change before writing, and default to a dry run. Conflicting labels for one path
**abort** the build rather than being resolved silently.

**Notes parsed.** 11 `Unknown` rows carried written answers; all 11 were
resolved rather than discarded.

**Source audio untouched.** The builder records mtime and size for every source
file before the build and re-checks after, aborting on change. Last build
verified **1,139 files unmodified**. No sample renamed, moved or rewritten.

## Regression tests

`test_label_safety.py` — 12 checks, all passing. It fails loudly if any critical
CSV becomes gitignored again, if checksums or provenance disappear, if duplicate
paths appear, or if backups end up on the sample drive.
