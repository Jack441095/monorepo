# KENN native DSP core

This directory contains the first offline DSP vertical slice: a portable C++20
Hann-windowed FFT/power kernel and an optional nanobind module consumed by
`kenn.core.audio_analysis`. Apple builds also link Accelerate/vDSP for the
spectral hot path and retain the scalar implementation as the portable
fallback. The module also exposes opt-in bulk mono/stereo statistics and
correlation kernels plus a bounded PCM WAV decoder; complete-request evidence
for those slices is recorded in
`products/kenn/docs/research/CPP_DSP_PHASE4_NATIVE_BULK_METRICS_RECEIPT.md`
and `products/kenn/docs/research/CPP_DSP_PHASE4_NATIVE_DECODER_RECEIPT.md`.
The spectral result also carries localized window RMS and the five report band
levels so the Python layer does not rescan the same FFT windows. When the
caller requests LTAS, the same call can also return the 40-band LTAS levels;
the report layer uses those values instead of scanning the averaged powers a
second time. Aggregate and localized dominant-peak records are also emitted
from the C++ power arrays, with the audited Python peak extractor retained as
the compatibility fallback. Large spectral and masking result vectors transfer
their C++ storage through nanobind ownership capsules to avoid a second result
copy at the boundary.

The extension also contains an opt-in ``automix`` submodule that exposes the
recovered C++ limiter, SOS biquad, direct correlation, attack/release and gate
envelopes, and rolling median/MAD threshold kernels. The adapter is available
through ``kenn.core.automix_native`` and returns ``None`` when native dispatch
is disabled or unavailable; the existing Python AutoMix path remains the
release default until complete-request parity and rights-cleared corpus gates
are satisfied.

Stem-masking analysis can opt into the seven-band native path with
``KENN_DSP_MASKING_NATIVE=1``. On macOS Accelerate builds this uses vDSP and
has a separate parity/performance receipt; portable scalar builds remain
available for compatibility but are not promoted as a speed claim.

The Mix Review calibrated loudness path has a separate candidate gate:
``KENN_DSP_LOUDNESS_NATIVE=1`` together with ``KENN_DSP_NATIVE=1`` enables
the C++ K-weighting/LRA/4x true-peak kernel. Its rounded LUFS/LRA/true-peak
output is parity-tested against pyloudnorm. Complete-request
timing and promotion evidence are recorded in
``CPP_DSP_PHASE4_MIX_REVIEW_LOUDNESS_RECEIPT.md``.
Mix Review WAV decoding can be enabled independently with
``KENN_DSP_MIX_REVIEW_DECODE_NATIVE=1`` (and ``KENN_DSP_NATIVE=1``); it uses
the same native float32 decoder while retaining the Python parser as the
fallback.
The full optimization-pass evidence, including 24-bit testing-assets runs,
is recorded in ``CPP_DSP_MEGA_OPTIMIZATION_PASS_RECEIPT.md``.

Use `-DKENN_USE_ACCELERATE=OFF` to force the portable scalar backend on macOS
when validating the fallback; non-Apple builds select it automatically.

Build prerequisites are CMake 3.20+, a C++20 compiler, Python 3.11+, NumPy,
nanobind, and scikit-build-core installed in the selected Python environment.
The wheel target intentionally disables pip build isolation so it uses that
known toolchain rather than an incompatible system CMake. The Make target also
passes its selected CMake path through `CMAKE_EXECUTABLE`, which avoids a stale
system CMake taking precedence on mixed-architecture macOS hosts. From
`products/kenn`:

```sh
make native-build NATIVE_PYTHON=/path/to/python NATIVE_BUILD_DIR=/tmp/kenn-dsp-native-build
make native-wheel NATIVE_PYTHON=/path/to/python NATIVE_BUILD_DIR=/tmp/kenn-dsp-native-build
# after installing the wheel into the selected environment:
python tooling/scripts/test_native_dsp.py
```

The Python/NumPy reference is the release default. Set `KENN_DSP_NATIVE=1` to
enable the optional native module for qualification or benchmarking, or set
`KENN_DSP_NATIVE=0` to force the reference implementation. The native module
is optional and is not compiled at runtime. With the flag enabled, the
nanobind boundary decodes supported PCM WAV payloads into contiguous float32
channels before dispatching bulk metrics and spectral kernels. Decoder channel
buffers transfer ownership directly to the returned NumPy arrays to avoid a
second full PCM copy; the audited Python decoder remains the fallback.
