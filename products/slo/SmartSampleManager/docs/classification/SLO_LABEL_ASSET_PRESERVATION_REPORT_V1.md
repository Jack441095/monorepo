# SLO Label Asset Preservation Report V1

The by-ear labels are the only ground truth this project has. Every accuracy
figure depends on them, they cost owner time that cannot be recovered, and the
drive holding them lost power during this work.

## Current state

| asset | rows | sha256 (16) | in git |
|---|---|---|---|
| `verified_drums.csv` | 675 | `c06f9989f61997cd` | **NO** |
| `verified_domain_coverage.csv` | 500 | `794d226b21ef8f0d` | **NO** |
| `verified_percussion_subtype.csv` | 47 | `7373c84a0e615e29` | **NO** |
| `verified_percussion_corrections.csv` | 47 | `cbc0cbb01f082451` | **NO** |
| `ground_truth/SLO_GT_V1/labels.csv` | 1069 | `774ae0043d5feda5` | yes |

backups on internal disk: 15 items
GT builds backed up: 4

## What is protected

**Versioned dataset.** `ground_truth/SLO_GT_V1/` is force-added to git — it holds
paths and labels, which is metadata, never audio. It carries a `manifest.json`
with counts, provenance and per-asset SHA-256, plus `CHECKSUMS.sha256`.
`build_ground_truth.py --verify` re-checks every asset and reports whether the
source CSVs have drifted since the build.

**Provenance.** Every row records `label_source` (`drums_v1` or
`domain_coverage_v1`), `collection`, `pack`, `sample_family_id` and
`labelling_session`. Provenance is a meaningful covariate, not bookkeeping: a
label from an unseen collection is worth roughly two from a familiar one.

**Off-drive backups.** Every build copies the whole dataset plus the raw source
CSVs to `~/slo_label_backups/` on the **internal disk** — deliberately not the
sample drive.

**Notes are parsed, not discarded.** The sprint proved this matters: 11 files
marked `Unknown` carried written answers, and parsing them resolved all 11.

**No silent overwrites.** Corrections keep `original_label`, print every change
before writing, and default to a dry run. Conflicting labels for one path abort
the build rather than being resolved silently.

**Source audio untouched.** The builder records mtime and size for every source
file before the build and re-checks after, aborting on any change. Last build
verified **1,139 files unmodified**. No sample is read-modified, renamed or moved.

## Remaining gap

The working CSVs are still gitignored by the existing `verified_*.csv`
convention, so between builds the newest labels exist only on the sample drive
plus the timestamped backups. The dataset build closes this, but only at build
time.

**Recommendation:** track the working CSVs. They contain file paths and labels,
not audio, so tracking them distributes no licensed content. This is an owner
decision and has not been made unilaterally.
