# KENN Phase 4 Native Spectral Output Ownership Receipt

**Run date:** 2026-09-21
**Status:** qualified opt-in allocation optimization

The spectral, LTAS, masking, and window-RMS results now transfer their C++
vector storage into nanobind capsules instead of allocating a second array and
copying every result element at the Python boundary. The capsule owns the
original vector until the NumPy view is released, so output shapes and
lifetime remain explicit.

Verification:

- Native spectral, LTAS, masking, decoder, and AutoMix smoke checks pass;
- native/reference report parity remains exact;
- Accelerate and portable scalar CMake builds pass;
- rebuilt wheel installation and smoke pass;
- the current 10-second native complete-request benchmark remains at a warm
  p50 of approximately `4.048 ms` after the ownership change.

This is an allocation/peak-memory optimization rather than a new release
performance claim. Native dispatch remains opt-in pending the existing
rights-cleared, cross-platform, and full AutoMix gates.
