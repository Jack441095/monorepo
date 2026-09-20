# Headroom Measurement

Headroom is defined precisely as `-max_sample_peak_dBFS`: a derived sample-peak
margin, not a universal headroom target. Evidence includes overall and
per-channel peak dBFS. There is no true-peak estimator in this V2-C path.

Unknown and MASTER scope produce observation-only output in the V2-C gate.
Only `MIX_IN_PROGRESS` scope can progress to an intervention recommendation.
Holdout: 12/12 labelled mix-in-progress headroom cases detected with no false
recommendations. Mastered-like controls remain non-actionable.
