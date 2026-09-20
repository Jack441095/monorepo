# DiskSweep changelog

## Unreleased
- C++ scanner: per-file >1GB fast path (mdfind + model-store walk), per-model HF/Ollama rows, EPERM warnings, depth-marked signatures.
- Policy: shared blocklist in C++ + Python, 5k-path parity fuzz, standalone `disksweep-policycheck` ctest.
- Sidecar: stdlib-only runtime, LLM budgets (10s/item, 120s/run) with rules-only banner, deduped reclaim math.
- CLI: `--json` verdicts, trash-log rotation (10), corrupt-log-safe undo, `doctor` subcommand.
- SwiftUI skeleton (parse-clean; full build needs Xcode 16+), FDA onboarding sheet.
- Privileged helper enforcing policy.hpp standalone (refuses BLOCKED + non-Trash dst).

## 0.1.0 — MVP
- Read-only scanner over 18 roots, JSONL scan items.
- Rule classifier (SAFE/REVIEW/BLOCKED), Ollama enrichment with fallback.
- CLI dry-run/trash/undo. 10 policy tests.
