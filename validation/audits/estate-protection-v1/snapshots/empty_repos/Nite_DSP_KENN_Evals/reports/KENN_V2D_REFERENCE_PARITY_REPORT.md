# Reference / Product Parity

The read-only adapter uses the actual product `decode_audio_bytes` seam, then
applies the frozen V2-C candidate code. On all 88 frozen holdout WAV cases,
candidate payload parity was **100%** (including measurements, severity,
scope, analysis version, and gate outcome). The product decoder used its WAV
path throughout.

This proves decoder/measurement semantic compatibility, not a merged product
implementation. Corrupt and empty inputs raise structured local exceptions;
production integration must translate these to KENN error contracts.
