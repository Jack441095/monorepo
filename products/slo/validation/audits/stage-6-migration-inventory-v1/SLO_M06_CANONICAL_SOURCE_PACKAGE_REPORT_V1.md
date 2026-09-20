# SLO M-06 Canonical-Source Package Report V1

Observation date: 2026-08-30

Status: clean canonical-source candidate; release remains blocked. This
package does not change the shared SLO checkout, root gitlink, platform
duplicates, protected data, models, holdouts, or release authority.

## Package identity

- ID: `SLO-M06-CANONICAL-SOURCE-V1`
- Product: SLO / Smart Sample Manager
- Candidate worktree: `workspace/worktrees/slo/slo-m06-canonical-source-v1`
- Candidate branch/SHA: `engineering/slo-m06-canonical-source-v1 @ 68b67009dc25`
- Candidate state: clean, 32M source-only worktree
- Shared checkout: `products/slo @ c6d0746ac876`, main, 49 dirty entries

## Objective and result

M-06 treats Smart Sample Manager as a provenance problem. The clean isolated
candidate is now the recommended SLO engineering/release candidate. It retains
the SLO product identity, declares WAV-only support, keeps Platform as release
authority, and preserves the existing source/release limitations.

Eight gates are recorded in the machine-readable receipt. Clean source,
product truth, declared-scope build evidence, and safety scope pass with
limitations. Data boundary, host/licensing/release, and duplicate-authority
gates remain blocked; shared cutover/rollback observation has not started.

Owner permission unblocks the migration lane, but it does not turn incomplete
qualification into a release approval. No protected data or credentials were
opened, and no data or model material was moved.

## Direct checks

```text
python3 -B tools/validate_slo_product_truth_manifest.py
slo_product_truth_manifest=valid

python3 -B -m unittest tools/test_slo_product_truth_manifest.py
OK

python3 -B tools/validate_slo_m06_canonical_source.py \
  --source-worktree /Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/workspace/worktrees/slo/slo-m06-canonical-source-v1
VALID SLO M-06 canonical-source candidate: 8 gates; release blocked; shared checkout preserved

python3 -B -m unittest tools/test_slo_m06_canonical_source.py
OK (1 test)
```

The fresh M-06A receipt records the full `ssm_qual_full` build and direct
execution result: 37 passed, 1 owner/environment-blocked, 0 code failures for
the declared local scope. BenchmarkScan and ClassificationBenchmark also
passed on ten disposable synthetic WAV fixtures. The candidate is now
engineering-qualified for this declared local scope; release and shared
cutover remain blocked.

## Files changed

Only the clean SLO candidate worktree contains new package files:

- `validation/audits/stage-6-migration-inventory-v1/slo_m06_canonical_source_readiness_v1.json`
- `validation/audits/stage-6-migration-inventory-v1/SLO_M06A_FULL_QUALIFICATION_RECEIPT_V1.md`
- `validation/audits/stage-6-migration-inventory-v1/SLO_M06_CANONICAL_SOURCE_PACKAGE_REPORT_V1.md`
- `tools/validate_slo_m06_canonical_source.py`
- `tools/test_slo_m06_canonical_source.py`

No shared `products/slo` checkout, Audio_Too checkout, platform checkout,
owner data, holdout, model, credential, provider, or customer file was changed.

## Security, rollback, and remaining work

The candidate worktree contains source and tracked product assets only; the
large dirty shared estate remains preserved. No protected contents were read
or moved. The external private data root remains absent.

Rollback is simply to leave the shared checkout and root gitlink unchanged and
stop using this additional worktree. Do not clean or delete any prior SLO
worktree.

Remaining gates are licensing, host/UI/DAW behavior, signing/notarisation,
clean-machine installation/update, support, large-library capacity, platform
duplicate consumer migration, protected-data cutover, observation, and release
approval.

## Next package

L-07/L-08: execute owner-approved host/licensing/release checks and a semantic
consumer/cutover plan. Keep release readiness fail-closed until those receipts
exist.
