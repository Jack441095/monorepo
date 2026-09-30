# SLO report index

**Purpose:** one row per report, so a stale claim is visible before it is quoted rather than after.
**Created:** 2026-09-30 by the review pass recorded in `docs/SLO_REVIEW_V1.md`.

The product root accumulates audit reports faster than it retires them, and the September 2026 review
found claims circulating that the code had already invalidated. Half the findings in that review were
staleness that this table would have surfaced on its own.

**Rules for adding a report:** give it a date, a status from the list below, and a `supersedes` pointer
if it replaces an earlier one. A report with no status is assumed stale.

**Status values:** `current` · `current, annotated` (true but carries a correction banner) ·
`current, disputed` (two sources conflict and neither is retired) · `historical, annotated` (its main
claim has been retracted in place) · `partly stale` (some claims wrong) · `stale` (do not quote) ·
`superseded` (retained for the record only).

| Report | Status | Date | Supersedes | Note |
|---|---|---|---|---|
| `docs/SLO_REVIEW_V1.md` | current | 2026-09-30 | — | Full code review: plugin core, ML pipeline, build, docs-vs-code. Every finding cited to file:line. |
| `docs/SLO_BETA_READINESS_V1.md` | current | 2026-09-30 | — | Beta gate verdict. Build, tests, secrets, read-only safety, owner decisions. |
| `docs/SLO_BETA_BLOCKERS_V1.md` | current | 2026-09-30 | — | Prioritized P0/P1 list with fix steps, and what is explicitly still open. |
| `docs/SLO_REVIEW_FIX_SHIP_PROMPT_V1.md` | current | 2026-09-30 | — | The reusable review/fix/ship prompt this pass was executed from. |
| `SLO_PRODUCT_TRUTH_MANIFEST_V1.json` | current | 2026-09-30 | `v1 (2026-08-30)` | Release authority. v2 retracted 5 unresolvable SHAs, corrected formats and version constants. |
| `docs/ROADMAP_TO_BETA.md` | current, annotated | 2026-09-30 | — | Owner decisions and acceptance thresholds. Carries UNVERIFIED accuracy and the WAV-only retraction. |
| `SLO_EVAL_SCORECARD_2026-09-18.md` | current, annotated | 2026-09-30 | — | Scorecard. Accuracy figures unverified; evidence-source claim corrected (81.2 FILENAME / 98.5 FOLDER). |
| `SLO_BETA_BLOCKER_REGISTER_V2.md` | partly stale | 2026-09-14 | `SLO_BETA_BLOCKER_REGISTER_V1.md` | Supersedes V1. Cites two master-plan files that do not exist; B-011 title still says move-based. |
| `SLO_PRIVATE_BETA_READINESS_V2.md` | superseded | 2026-09-14 | `SLO_PRIVATE_BETA_READINESS_V1.md` | Superseded by docs/SLO_BETA_READINESS_V1.md. V1 is still cited as live evidence and should not be. |
| `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md` | historical, annotated | 2026-08-28 | — | Predates the format-aware scan path. WAV-only and 5.4x accuracy claims retracted in place. |
| `SLO_V1_WORKING_PRODUCT_DEFINITION.md` | historical, annotated | 2026-08-30 | — | Item 2 (formats) is out of date; AIFF/FLAC ship. |
| `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md` | historical, annotated | 2026-08-30 | — | Format-coverage gap closed for AIFF/FLAC. |
| `SLO_SOURCE_ARCHITECTURE_MAP.md` | historical, annotated | 2026-08-30 | — | HEAD and taxonomy version were wrong; both corrected or retracted. |
| `slo_test_results_v1.json` | stale | 2026-08-30 | — | Asserts a Release build FAIL and a build path that does not exist. The FAIL is wrong: verified clean. |
| `SLO_LICENSE_MODEL_AUDIT_V1.md` | partly stale | 2026-08-28 | — | Model hashes verified correct. Taxonomy version said 2; it is 5. |
| `SLO_SECURITY_PRIVACY_AUDIT_V1.md` | partly stale | 2026-08-28 | — | Network claim accurate. Says sort is move-based; it defaults to copy. |
| `SLO_FILE_DATA_SAFETY_AUDIT_V1.md` | partly stale | 2026-08-28 | — | Read-only claim accurate. Says sort is move-by-default; it defaults to copy. |
| `SLO_FULL_PRODUCT_CLASSIFICATION_BETA_READINESS_AUDIT_V1_FINAL_REPORT.md` | historical, annotated | 2026-09-15 | — | Provenance SHAs retracted; conclusions retained as a record of the run. |
| `SLO_READ_ONLY_SAFETY_REPORT_V1.md` | current | 2026-08-30 | — | Conclusion correct. Line citations into SampleManagerEngine.cpp are wrong and unusable. |
| `SLO_RT_THREADING_AUDIT_V1.md` | current | 2026-08-30 | — | States the original limitation before closing it, and restates scope limits. Good practice. |
| `SLO_TEST_INVENTORY.md` | stale | 2026-08-30 | — | Claims 31 executables; 55 are built. The missing 24 are listed in docs/SLO_BETA_READINESS_V1.md. |
| `SmartSampleManager/docs/classification/OOD_RECALIBRATION_V1_REPORT.md` | current | 2026-09-15 | — | Rigorously documented null result. Source of the 39.0% figure that conflicts with the V2 artifact. |
| `SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` | current, disputed | 2026-09-15 | `V1 report` | The V2 artifact: 77.9% / 17.5%, macro-F1 0.528 / 0.073. Conflicts with the OOD report for the same corpus. |
| `docs/BUILD_TREE_POLICY.md` | partly stale | 2026-08-30 | — | Lists three presets; CMakePresets.json defines five, including the undocumented ssm-sanitize. |

## Not indexed

`docs/plans/*.md` (17 agent prompts), `docs/THURSDAY_*_FINAL_REPORT.md` ×3, and
`docs/NITE_DSP_BUILD_OPTIMISATION_REPORT_V1[_1].md` ×2 predate all product code and carry no
supersede banner. They are research and planning history, not release evidence.

`products/slo/nitedsp/` holds a single tracked `.DS_Store` and nothing else; the manifest's
`research_separation` entry describing `nitedsp/backend` and `nitedsp/website` as duplicate
platform authorities describes directories that no longer exist. **The `.DS_Store` should be removed
and the directory with it.**

## Gates

```
scripts/check_release_truth.sh       every cited commit resolves, or is explicitly retracted
scripts/check_no_personal_paths.sh   no home or media-library path in a tracked file
```

Both were verified to pass and verified to fail on a planted violation. Run them before any
release, and note that `release-truth-gate` only inspects committed content — an unretracted SHA
in a working-copy edit is caught on commit, not before.
