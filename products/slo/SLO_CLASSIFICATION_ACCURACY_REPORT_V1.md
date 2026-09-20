# SLO Classification Accuracy Report V1

**SUPERSEDED (2026-09-08):** the 96.54% headline below is the repository-benchmark
number described in this doc's own evidence boundary, not real-corpus accuracy. The
team has since published corrected real-corpus numbers (62.9% / 30.2% once
filename-metadata leakage is controlled for) in `SLO_PRIVATE_BETA_READINESS_V1.md`
and `SLO_BETA_BLOCKER_REGISTER_V2.md` (B-006, CLOSED). Do not quote 96.54% externally
or treat it as current accuracy — use the real-corpus figures instead.

## Evidence boundary

No owner audio, protected labels, or protected holdouts were opened or rerun. The numbers below are repository-held evidence and are not new audit execution unless explicitly marked current.

## Historical repository metrics

The benchmark artifact reports 1,272 clean samples and 250 OOD samples:

- Overall accuracy: **96.54%**.
- Macro F1: **96.45%**.
- Fusion-adversarial accuracy: **88.29%**.

These results represent the repository benchmark and fused output path. They must not be presented as arbitrary-user-library accuracy because filename/folder semantics are part of the production evidence hierarchy.

## Leakage-controlled evidence

`GOLDEN_SET_V1_REPORT.md` records a synthetic set where full-evidence accuracy was 58.8%, audio-only accuracy 5.9%, filename-only 58.8%, folder-only 58.8%, and adversarial accuracy 0%. This is a diagnostic that demonstrates the product’s dependence on naming/folder evidence for that fixture; it is not a claim about all user libraries.

## AL-001 and AL-002

- **AL-001:** hard diagnostic only. The brief records 25 reviewed items, 21 in-taxonomy and 4 outside taxonomy. It was not rerun in this audit, and labels are not reproduced here.
- **AL-002:** **WAITING FOR BLIND REVIEW**. No protected labels or predictions are exposed and no completion receipt was available to authorize a pass claim.

## Accuracy decision

Accuracy is **PASS WITH LIMITATIONS** for controlled internal evaluation only. A public accuracy claim is blocked until cross-vendor, filename/folder-shuffled, audio-only and fused metrics are reported separately, with confidence intervals and completed blind review.
