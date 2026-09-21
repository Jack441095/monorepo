# KENN Accelerate/vDSP Backend Receipt

**Status:** parity pass; no promotion

The portable scalar FFT now has an Apple Accelerate/vDSP implementation behind
the same optional nanobind module. The Apple build links the Accelerate
framework, reports `backend=cpp-accelerate`, and retains the scalar path for
non-Apple builds and fallback testing.

On the eight supplied canonical stereo mixdowns, the vDSP path produced zero
differences from the Python reference after excluding dynamic receipt fields
under the existing `2e-5` absolute/relative tolerance. Its complete-request
mean was **14,960.954 ms** versus **14,926.491 ms** for the reference, a
`1.00231x` ratio (0.23% slower). The backend is therefore retained as a
qualified experiment but not promoted as the default or a claimed speedup.

Machine-readable evidence is in
`results/phase4_accelerate_backend.json`. The Python/NumPy reference remains
the default; set `KENN_DSP_NATIVE=1` explicitly for vDSP qualification runs.
