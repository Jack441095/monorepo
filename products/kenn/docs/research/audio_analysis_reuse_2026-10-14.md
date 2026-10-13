# Audio analysis reuse review — 14 October 2026

This is a shortlist with a bounded offline comparison, not a dependency change
or host qualification. The standing reuse process lives in [KENN_PLAN.md](../../KENN_PLAN.md).
Distribution screening follows [THIRD_PARTY_LICENCES.md](THIRD_PARTY_LICENCES.md);
pinned package versions, transitive code and required notices remain part of the
distribution evidence. No library was installed or added during this review.

## Immediate meter candidates

| Candidate | Verified interface and fit | Decision for the next comparison |
|---|---|---|
| JUCE DSP, framework pinned to 8.0.2 | Oversampling supports 2x/4x/8x/16x, linear-phase FIR or phase-changing IIR, explicit buffer preparation and latency reporting. KENN already fetches JUCE; its plugin target does not currently link `juce_dsp`. | Evaluate FIR upsampling from the existing framework first, with a bounded module/build review. It supplies interpolation, not a complete loudness meter. Measure its peak error and upsampling delay; the documented overall round-trip latency must not be assumed to describe an upsampling-only measurement. [API](https://docs.juce.com/master/classjuce_1_1dsp_1_1Oversampling.html), [8.0.2 source](https://github.com/juce-framework/JUCE/blob/8.0.2/modules/juce_dsp/processors/juce_Oversampling.cpp). |
| libebur128, reviewed v1.2.6 | C API supplies 400 ms momentary, 3 s short-term, integrated loudness, LRA, and per-channel peak from the last `add_frames` call. True peak uses a 49-tap polyphase interpolator: 4x below 96 kHz, 2x below 192 kHz. [API](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.h). | Shortlist as an independent M/S comparison and possible worker implementation. MIT fits the existing permissive policy. Its 4x output at 44.1 kHz is 176.4 kHz, so reuse alone does not resolve KENN's high-frequency accuracy gate. Pin the version because upstream documents version-dependent peak behavior. [Licence](https://github.com/jiixyj/libebur128/blob/v1.2.6/COPYING). |
| r8brain-free-src, upstream reviewed on this date | Header-only C++ resampler, double precision, power-of-two conversion paths, maximum input length at construction, and APIs for input required before output. Output count varies; initial processing needs buffered input. [Upstream](https://github.com/avaneev/r8brain-free-src), [source contract](https://github.com/avaneev/r8brain-free-src/blob/master/CDSPResampler.h). | Shortlist for an 8x interpolation comparison if JUCE cannot meet accuracy/cost together. MIT fits the existing policy. It is a resampler, not an R128 meter. Pin the commit before evaluation and measure buffered-input delay, output intervals and allocation behavior. [Licence](https://github.com/avaneev/r8brain-free-src/blob/master/LICENSE). |

JUCE 8.0.2's framework modules are dual-licensed under AGPLv3 and the commercial
JUCE licence. Reuse follows KENN's existing JUCE distribution arrangement;
this review changes neither that arrangement nor the project's licence policy.
[Pinned licence](https://github.com/juce-framework/JUCE/blob/8.0.2/LICENSE.md).

libebur128 v1.2.6 allocates its audio ring and interpolation scratch during
initialization. Choosing `S | TRUE_PEAK` without `I` or `LRA` avoids their
growing history-list branches in `add_frames`; initialization and parameter
changes must stay outside processing. Its 3 s double ring plus true-peak input
and output float scratch total approximately 5.53 MB per stereo state at
96 kHz, or 354 MB for 64 states. These are source-derived array estimates,
not measured RSS, and exclude structures and allocator overhead. An allocation
guard and memory measurement are still required.
[Mode-specific source](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.c).

## Later spectrum, pitch and onset work

| Tool | Useful coverage | Screening outcome |
|---|---|---|
| Existing librosa | Spectral/tonal/rhythmic features, `yin`/`pyin` pitch and onset analysis. | Already listed as ISC in KENN's dependency record. Reuse for offline or companion analysis before writing another implementation; warm-up, allocation, hop size and delay still need workload tests. This does not establish audio-callback suitability. [Features](https://github.com/librosa/librosa/blob/main/librosa/feature/__init__.py), [pitch](https://github.com/librosa/librosa/blob/main/librosa/core/pitch.py), [onset](https://github.com/librosa/librosa/blob/main/librosa/onset.py), [licence](https://github.com/librosa/librosa/blob/main/LICENSE.md). |
| Existing pyloudnorm and SciPy | Python loudness reference plus existing filtering/resampling tooling. | Prefer the existing qualification/reference path for comparisons; batch reference agreement does not prove native streaming performance. pyloudnorm documents BS.1770-4 and is MIT. [Upstream](https://github.com/csteinmetz1/pyloudnorm), [licence](https://github.com/csteinmetz1/pyloudnorm/blob/master/LICENSE). |
| aubio | Native onset, pitch, beat, FFT and MFCC analysis; pitch objects take explicit analysis/hop sizes and sample rate. | GPLv3 source is already excluded by KENN's distribution policy. Keep excluded; a frame API does not demonstrate allocation-free processing or accuracy for our signals. [Features](https://aubio.org/manual/latest/), [pitch API](https://aubio.org/doc/latest/pitch_8h.html), [licence](https://github.com/aubio/aubio/blob/master/COPYING). |
| Essentia | Broad music analysis with a streaming graph and scheduler. | Its upstream licensing page offers Affero GPLv3 and commercial licensing, with separately licensed models and third-party dependencies. Existing KENN policy excludes its open-source distribution; do not introduce it as a shortcut. Streaming mode alone does not prove callback suitability. [Architecture](https://essentia.upf.edu/streaming_architecture.html), [licensing](https://essentia.upf.edu/licensing_information.html). |
| soxr | Multichannel stream resampling, caller-supplied output buffers, reset and current output-sample delay API. | LGPL-2.1-or-later falls outside the project's current permissive allowlist. Keep off the native shortlist while MIT and existing-framework options remain; allocation and deadline behavior are unmeasured here. [API](https://github.com/chirlu/soxr/blob/master/src/soxr.h), [licence](https://github.com/chirlu/soxr/blob/master/LICENCE). |

These licence facts are engineering screening against the existing project
policy; they do not replace review of the exact distribution and its notices.

## Measured offline comparisons

The [first measured comparison](peak_reuse_comparison_2026-10-14.json) uses the
existing cached JUCE 8.0.2 source, double-precision linear-phase FIR upsampling
and generated stereo audio. Current KENN, JUCE 4x, JUCE 8x in 128-frame chunks,
and JUCE 8x one frame at a time are tested at 44.1/48/96 kHz. Each mode/rate has
98 known-amplitude tones; a -0.2/+0.1 dB engineering margin is deliberately
stricter than the selected Tech 3341 cases. It is not a conformance claim.

At every rate, current KENN fails 28 tones (errors -0.455 to +0.220 dB), JUCE
4x fails six (minimum -0.436 dB), and both JUCE 8x modes pass all 98 (minimum
-0.108 dB). Better filtering removes one error source; a 4x sample grid still
misses some continuous peaks. Twelve silence/DC/boundary-impulse/noise checks
preserve the 8x peak bins across batch sizes. Upsampling-only delay is 35.75
input frames at 4x and 38.625 at 8x; the API reports round-trip delays of 59.5
and 64.25 frames. Corrected input intervals remain unimplemented.

**Decision:** keep this JUCE double 8x path as an accuracy reference, not a
selected runtime implementation. The receipt records its substantial CPU cost
before capture/FFT/publishing. Current mode also includes K-weighting and M/S,
whereas JUCE modes only interpolate and scan peaks, so this is not an equal-work
speedup comparison. Ordinary C++ `new/new[]` observations are zero; malloc,
aligned allocations, JUCE state size and RSS are not qualified. This historical
v1 receipt was produced by commit `684a9ffe6ac6c94ce14e9a307d0a412ae9f85580`.

The [variant comparison](peak_reuse_variants_2026-10-14.json) varies arithmetic
precision, FIR quality and filter algorithm in the same pinned framework. It
adds 18 equal-amplitude cosine pairs to the 98 single tones per mode/rate. The
two components reach +0.25 together every 40 input frames, so their exact
continuous peak is 0.5; changing their relative phase must not count as better
peak measurement. Every variant runs in prepared 128-frame chunks, with
one-frame calls used separately to check boundary history.

All four 8x FIR variants pass both families at 44.1/48/96 kHz. Their worst
single-tone error is -0.108 dB and worst paired-tone error is -0.0713 dB. Both
8x IIR variants pass the single tones but fail 9 of 18 pairs at every rate,
underreading by as much as -0.947 dB. This agrees with JUCE's documented
phase-changing IIR behavior; [the API](https://docs.juce.com/master/classjuce_1_1dsp_1_1Oversampling.html)
also identifies maximum quality as the more expensive setting. Pinned
[8.0.2 source](https://github.com/juce-framework/JUCE/blob/8.0.2/modules/juce_dsp/processors/juce_Oversampling.cpp)
selects wider transitions and lower stopband attenuation for the lower-quality
FIR. Lower-quality FIR's measured upsampling delay is 24.625 input frames,
versus 38.625 at maximum quality; round-trip delays are 41 and 64.25 frames.
IIR's 3.125-frame impulse maximum is recorded separately from delay. Its
frequency-dependent phase prevents reporting a fixed upsampling delay.

The Apple M3 arm64 Release run records 84 warmed CPU/wall cells with 20 raw
repeats, 72 passing boundary/history comparisons and zero observed ordinary C++
`new/new[]` calls during processing. At 64 inserts and 10 Hz, interpolation
and peak scanning alone use these percentages of one core:

| Input rate | FIR maximum quality, double | FIR maximum quality, float | FIR lower quality, double | FIR lower quality, float | IIR maximum quality, double | IIR maximum quality, float |
|---|---|---|---|---|---|---|
| 44.1 kHz | 43.54% | 46.70% | 31.71% | 34.33% | 21.26% | 21.15% |
| 48 kHz | 47.24% | 50.90% | 34.78% | 33.31% | 23.14% | 23.02% |
| 96 kHz | 94.58% | 101.40% | 68.48% | 66.87% | 46.44% | 46.03% |

**Variant decision:** reject these IIR configurations for peak measurement.
Float precision alone does not save CPU on this machine. Shorter FIR filters
reduce the 96 kHz/64-insert cost by 27.6% in double and 29.3% in float versus
the double maximum-quality reference, while clearing this bounded accuracy
screen. Shortlist both shorter FIR variants for further comparison; precision
ordering varies by sample rate. Their maximum serial 100 ms batch at 96 kHz
is 68.54 ms and 67.78 ms respectively, before capture/FFT, loudness, publication
or model work. This remains a substantial cost, not a worker deadline result.
Do not select a production implementation from these isolated timings. Broader
frequency/transient checks, corrected input intervals, reset/gap retirement,
prepared storage/RSS and combined-worker contention remain open. Keep the live
candidate disabled; retain the independently screened resampler/loudness
options if the existing framework cannot meet the remaining accuracy/cost gates.

Reproduce without fetching or installing libraries:

```sh
cmake -S tooling/native/peak_compare -B /tmp/kenn-peak-reuse \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DKENN_JUCE_SOURCE_DIR="$KENN_JUCE_SOURCE_DIR"
cmake --build /tmp/kenn-peak-reuse -j4
apps/backend/.venv/bin/python tooling/scripts/profile_peak_reuse.py \
  --binary /tmp/kenn-peak-reuse/KENNPeakCompare \
  --juce-source "$KENN_JUCE_SOURCE_DIR" --repeats 20 \
  --json-out /tmp/kenn-peak-reuse-variants.json
KENN_PEAK_REUSE_TEST_BINARY=/tmp/kenn-peak-reuse/KENNPeakCompare \
  apps/backend/.venv/bin/python -m pytest -q \
  apps/backend/src/kenn/tests/test_profile_peak_reuse.py
```

Set `KENN_JUCE_SOURCE_DIR` to the existing unmodified JUCE 8.0.2 checkout.
The tool pins its commit and rejects Debug or mismatched architecture builds;
run Python natively on the same architecture as the executable. Generated audio
stays in temporary storage. The current runner writes schema v2 and retains
failing configurations in its receipt; v1 reproduction requires the historical
commit above. The receipt carries compiler and source/binary hashes, raw timing
samples and every tone's generating parameters. The 87 scoped tool tests include
compiled filter checks for all batch variants and the mixed-signal IIR failure.
Passing the runner's bounded checks does not select a library or close a runtime
cost gate.

1. Keep the live LUFS/dBTP candidate disabled. Use the existing
   [qualification receipt](streaming_meter_qualification_2026-10-13.json) and
   plan gates as the baseline: broader high-frequency accuracy, delayed peak
   intervals, transient/temporal checks and sustained contention remain open.
2. Carry the shorter JUCE FIR shortlist through the remaining accuracy/cost
   gates; use pinned libebur128 as a separate loudness/peak comparator. Evaluate pinned
   r8brain only if the first comparison leaves an accuracy/cost gap. New
   dependency additions still require user approval.
3. Use the same generated signals at 44.1/48/96 kHz, phase/frequency sweeps,
   transient and bin-edge peaks, silence, DC, resets and dropped-source cases.
   Record warm-up/readiness and the exact input interval represented by each
   peak; higher interpolation rate alone is not qualification.
4. Measure steady-state allocations, storage/RSS and worker CPU/wall tails for
   1/8/32/64 inserts alongside FFT and publishing work. Keep library processing
   on the consumer worker; the audio callback retains its bounded queue copy.
5. Record the pinned sources, licence fit, measured benefit and integration
   cost before selecting reuse or custom code. Existing tools should save
   development time only when they meet the same accuracy and timing contract.
