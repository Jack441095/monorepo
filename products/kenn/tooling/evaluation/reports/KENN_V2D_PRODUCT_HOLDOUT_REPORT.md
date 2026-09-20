# Product Audio Holdout

88 frozen holdout cases ran via the product decoder and V2-C measured/gate
semantics: precision 1.000, recall 1.000 for clipping/headroom/persistent L/R,
healthy FP 0.000, abstention 0.8030, mean recommendations 0.591/case. The
headroom recommendation path requires explicit `MIX_IN_PROGRESS` scope;
MASTER and UNKNOWN remain observation-only.

No product flag exists yet, so flag-off legacy parity and rollback are not
proven. This report is read-only integration qualification, not a release.
