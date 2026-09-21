# KENN Native PCM Decoder Receipt

**Status:** qualified opt-in slice; no release-default promotion

The opt-in nanobind module now decodes supported RIFF/WAVE PCM payloads into
contiguous float32 channel arrays before native bulk metrics and spectral
analysis. The Python decoder remains the reference path when
`KENN_DSP_NATIVE=0`, when the extension is unavailable, or when a native decode
attempt rejects malformed input.

Direct parity passed for 16-bit PCM, 24-bit PCM, 32-bit integer PCM, and
32-bit IEEE-float WAV fixtures. The existing audio-analysis suite passes in
both native and forced-reference modes, and the wheel smoke now checks decoder
metadata, sample values, malformed-input rejection, and reference parity.

On a deterministic 10-second mono request, enabling the decoder reduced the
native-spectral baseline from 230.873 ms mean to 11.336 ms mean (95.1% faster).
The follow-on native spectral result also returns localized window RMS and
five-band energy, removing duplicate Python scans; warm-request median fell
from 21.027 ms to 5.163 ms (75.4% faster).
Across eight supplied internal mixdowns, one fresh-process run measured
83,181.766 ms total for the Python reference and 830.670 ms total for the
native candidate (0.009986x, 99.0% faster). The native run's peak RSS was
699,924,480 bytes versus 5,525,422,080 bytes for the reference process.

These corpus files are marked `TODO-vendor-pack`, so this is internal
performance/parity evidence only. It is not rights-cleared release evidence.
The native path remains opt-in pending rights-cleared fixtures, Windows/DAW
validation, and macOS signing/notarization.

Machine-readable evidence is in
`results/phase4_native_decoder.json`. The post-change native cProfile is in
`results/phase4_native_profile.json`; it shows retained Python peak selection
and report orchestration rather than another dominant sample-conversion loop.
