# SLO Estate Refresh Package Report V1

Date: 2026-08-30  
Package ID: `L-01-SLO-ESTATE-REFRESH-V1`  
Product/system: SLO / Smart Sample Manager  
Status: additive read-only estate evidence; no cleanup or release promotion.

## Objective

Refresh SLO's source, worktree, generated-state, protected-data, duplicate-
authority, and provenance map. Establish a declared canonical source candidate
without pretending that a dirty checkout or compiled qualification output is a
clean release truth.

The machine-readable registry is
`slo_estate_refresh_registry_v1.json`.

## Owner, worktree, and SHAs

- Owner: NITE DSP.
- Shared canonical candidate: `products/slo`, `main`,
  `c6d0746ac876a0a3af9244907486ffc001b3e718`, remote
  `https://github.com/Jack441095/Nite_DSP_01.git`.
- Shared state: 49 untracked entries, no tracked modifications, and no
  release-truth claim.
- Isolated evidence worktree: `workspace/worktrees/slo/format-aware-scan-v1`,
  branch `engineering/slo-format-aware-scan-v1`,
  `4645425535a35da06fb734c0a9a08e821b116ade`, clean.
- The shared SLO SHA is an ancestor of the isolated qualification checkpoint.

## Findings

- Current size is 20G, with 19G under `SmartSampleManager`.
- `_build` is 593M/1,154 files and `_cache` is 885M/7,494 files.
- The classification benchmark area contains 15,354 files; contents were not
  opened. `SmartSampleManager/Models` is 23M and its contents were not opened.
- Filename-only inventory found 15,287 WAV files, four ONNX model files, one
  environment-named file, and no files with database or key extensions. This
  is not a secret-content audit.
- Text-like reference scan found 21 files containing absolute volume paths,
  12 containing `Audio_Too`, and 15 containing `Nite_DSP_01`. These require
  semantic review, not blind replacement.
- The root recorded SLO gitlink is
  `0c679644c11770890159f46978ba05c6bbebc4de`, which differs from checked-out
  `c6d0746ac876a0a3af9244907486ffc001b3e718`. No correction was attempted.
- Twelve additional SLO worktrees were inventoried, including research,
  build, release, qualification, and dirty engineering WIP lanes. The full
  map and dirty counts are in the JSON registry.
- `nitedsp/backend` and `nitedsp/website` remain duplicate platform
  authorities. The P-01 audit records bounded divergence of 17/56 against
  Platform; no copy, merge, quarantine, or retirement occurred.

## Untracked path classification

All 49 untracked entries in the shared checkout were preserved and classified
in the registry as product documentation, qualification evidence, build/release
tooling, generated state, protected evaluation results, historical evidence, or
legacy duplicate authority. The classification is path-based and deliberately
does not inspect protected result contents.

## Security and privacy boundary

- No audio, model, private corpus, holdout, secret, environment value, or
  evaluation-result content was opened.
- No file was moved, deleted, staged, cleaned, copied, or reclassified.
- No active SLO WIP worktree was modified.
- Generated state remains in place; this package does not perform cleanup.

## Capability and limitations

This package establishes current estate truth and a preserved source/worktree
map. It does not make SLO release-ready, select a final clean checkpoint,
resolve product-vs-research ownership, remove duplicate platform code, or
prove host, licensing, signing, installation, or capacity gates.

The previously recorded isolated full-build/direct-binary qualification remains
valid only for its declared checkpoint and scope; it does not override the
dirty shared checkout or protected-data boundary.

## Verification

```text
git -C products/slo status --porcelain=v1
git -C products/slo worktree list --porcelain
du -sh products/slo products/slo/SmartSampleManager products/slo/_build products/slo/_cache
find products/slo -type f -name '*.wav' -o -name '*.onnx'
rg -l -I '/Volumes/|Audio_Too|Nite_DSP_01' products/slo
python3 -m json.tool validation/audits/stage-2-slo-estate-refresh-v1/slo_estate_refresh_registry_v1.json
git diff --check
```

The direct snapshot produced the counts recorded above. The JSON registry
contains 13 worktree records and all 49 untracked entries.

## Decisions required

1. Choose a clean SLO source checkpoint for release qualification.
2. Decide which benchmark/evaluation material may remain in the product tree
   and provide an approved external private-data boundary.
3. Assign owners for product, qualification, research, release, and duplicate
   platform capabilities.
4. Approve semantic migration units before any duplicate authority is changed.

## Rollback

This is additive evidence in the isolated SLO qualification worktree. Withdraw
only the registry and report; do not reset, clean, delete, or overwrite the
shared SLO checkout, any worktree, audio/model/evaluation state, or duplicate
platform tree.

## Next safest package

Refresh SLO's product and release manifests from this registry, then qualify a
clean source checkpoint through the documented build, direct-test, host,
licensing, package, install, and rollback gates. Keep research and protected
evaluation state out of release claims.
