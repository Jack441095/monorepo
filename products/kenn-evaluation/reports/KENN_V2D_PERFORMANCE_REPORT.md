# Performance

Read-only product decoder + measured candidate extraction over the 88 product
holdout cases: p50 3.49 ms and p95 35.54 ms (decode/measurement segment).
On the 232-case realistic corpus: p50 3.88 ms, p95 40.79 ms. These values do
not include the full legacy Mix Review pipeline or UI/network work.

The path is offline/background analysis only; it has not been placed on a
plugin real-time thread. Future integration must preserve that boundary.
