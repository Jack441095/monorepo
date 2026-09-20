# SLO Scan Admission Hardening V1

## Work package

- **ID/title:** `L-03-scan-admission-coalescing-v1` — duplicate-path and symlink-safe scan admission
- **Product/system:** SLO / Smart Sample Manager scan and classification pipeline
- **Owner/worktree:** NITE DSP / `engineering/slo-build-entry-v1` in `workspace/worktrees/slo/slo-build-entry-v1`
- **Base SHA:** `fd843f60d9d6`
- **Result SHA:** `30b2d1152b93`

## Objective and finding

The scan admission path accepted every registered-format path on every call.
Overlapping UI rescans could therefore queue the same path more than once while
the first copy was still being decoded or awaited by the inference worker. A
symlinked audio path could also widen a scan beyond the user-selected library
boundary. Both cases were inconsistent with L-03's duplicate-path and symlink
requirements.

## Files changed

- `Source/SampleManagerEngine.h`
- `Source/SampleManagerEngine.cpp`
- `Source/test_format_aware_scan_main.cpp`
- `docs/classification/CURRENT_PIPELINE.md`

## Implementation

- Reject direct symlink roots and symlinked audio children during format-aware
  admission.
- Track each admitted path from queue insertion through inference commit in a
  locked in-flight set.
- Coalesce overlapping admissions without suppressing a later deliberate
  rescan after the prior operation has committed; later rescans still use the
  normal path/mtime/size cache identity check.
- Release failed decode paths immediately and release successful paths only
  after the inference batch commits.
- Catch unexpected worker exceptions, log them, and release the admission
  guard so one bad file cannot permanently suppress future retries.

## Evidence and tests

The following low-CPU checks passed after the change:

- `test_research_v3_reporting.py`: 10/10
- `test_validate_l05_qualification_package.py`: 2/2
- `test_audit_corpus_metadata.py`: 2/2
- seven static scan-admission contract checks: pass
- `git diff --check`: pass

The native `TestFormatAwareScan` binary has not yet been built or executed.
That environment-backed evidence remains pending because five VS Code C++
language-service workers are saturating the machine CPU. No native execution
or mixed-format runtime result is claimed by this receipt.

## Scope boundaries

This package does not change classifier weights, OOD thresholds, taxonomy
labels, metadata precedence, cache schema, research manifests, private audio,
or source-family evaluation policy. It also does not physically migrate or
delete any files.

## Exit status and limitations

The admission behavior is implemented and statically verified. Full L-03 exit
still requires native execution against disposable mixed-format, malformed,
duplicate-path, symlink, permissions, and restart/cancellation fixtures, plus
scan throughput and memory measurements.

## Rollback

Revert commit `30b2d1152b93` from the isolated SLO candidate only after
recording the reason and rerunning the previous scan/cache regression checks.
Do not reset, clean, or overwrite the shared root or other product worktrees.

## Next package

When the native build lane is available, execute `TestFormatAwareScan` and the
cache qualification group. Independently, continue the owner-gated L-05
source-family/provenance decision and corrected 17-class evidence package.
