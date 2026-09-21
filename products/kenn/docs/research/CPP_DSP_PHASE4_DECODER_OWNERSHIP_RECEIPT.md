# KENN Phase 4 Native Decoder Ownership Receipt

**Run date:** 2026-09-21
**Status:** qualified opt-in implementation; release qualification unchanged

The native WAV decoder now allocates each channel buffer once and transfers
that allocation directly into the nanobind-owned NumPy array. The previous
implementation filled `std::vector<float>` channels and copied every sample
into a second array at the Python boundary. The new ownership handoff removes
that duplicate allocation/copy while preserving the decoder metadata and
sample contract.

Verification:

- 16/24/32-bit integer and 32-bit float decoder parity remains green;
- native DSP smoke and complete audio-analysis parity tests pass;
- Accelerate and portable scalar CMake builds pass;
- a 10-second, 48 kHz stereo PCM16 direct-decoder run measured a warm p50 of
  `0.807 ms` on the local macOS arm64 host after the ownership handoff;
- the rebuilt wheel installs into an isolated target and passes the native
  smoke contract.

This timing is a direct-kernel reference, not a release gate. The native
decoder remains opt-in until rights-cleared corpus, cross-platform, and full
AutoMix qualification are complete.
