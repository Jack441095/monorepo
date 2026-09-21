# KENN Phase 4 Zero-Lag Correlation POC Receipt

**Run date:** 2026-09-20
**Status:** no-go for production integration

The long-mix profile identified Python zero-lag stereo correlation as a hot
stage. A temporary nanobind C++ implementation was measured against the same
complete-request path after removing an existing duplicate Python correlation
call. The native stage itself was faster, but the complete-request result did
not clear the 25% adoption gate:

| Fixture | Python reference (ms) | Native candidate (ms) | Improvement |
| --- | ---: | ---: | ---: |
| `dream_of_you` (80.8 s) | 3566.103 | 3243.985 | 9.0% |
| `ae_mere_humsafar` (263.9 s) | 11811.109 | 10617.583 | 10.1% |

The result is consistent with the broader finding that Python orchestration,
decode, summary loops, and report construction remain a substantial fraction
of the request. A faster isolated correlation kernel does not justify another
native boundary by itself.

## Decision

Do not retain the temporary correlation binding or enable a new production
flag. Keep the single-call Python correction, retain the existing spectral
native path as opt-in, and only revisit correlation after a larger fused
summary/metrics boundary is profiled and can clear the complete-request gate.
