# Mix Review offline benchmark reuse check — 15 October 2026

This refresh covers the existing offline loudness benchmark, not live-meter
selection. It extends the [14 October reuse review](audio_analysis_reuse_2026-10-14.md)
and [phase 4 receipt](CPP_DSP_PHASE4_MIX_REVIEW_LOUDNESS_RECEIPT.md).
The inspected checkout was `d167d0055496c1e3709087f0aa13763f4f97d805`.
No dependency, audio asset or upstream checkout was installed or downloaded.

## Existing reference

The backend environment reports pyloudnorm **0.2.0**, SciPy **1.18.1**, NumPy
**2.5.3** and nanobind **3.1.0**, using `importlib.metadata.version` on this
date. These are installed versions, not a claim about the latest releases.

pyloudnorm 0.2.0 supplies integrated loudness and LRA. Its default integrated
path uses K-weighting, 400 ms blocks and 75% overlap. Its LRA implementation
uses 3 s blocks, 97% overlap, appends 1.5 s silence and takes the difference
between the 95th and 10th percentiles after gating. The overlap gives a
**90 ms step**, despite the nearby source comment describing approximately
10 Hz. Empty gated LRA returns NaN. These details are part of the existing
oracle contract, so a faster candidate must preserve them or report a
deliberate semantic difference. [Pinned meter source](https://github.com/csteinmetz1/pyloudnorm/blob/v0.2.0/pyloudnorm/meter.py).

SciPy's `resample_poly` uses a zero-phase FIR and defaults to constant zero
padding. KENN calls it at 4x for the reference peak path; matching it measures
implementation parity, not continuous-time peak accuracy. Boundary padding,
filter design and output alignment belong in the comparison.
[Pinned SciPy source](https://github.com/scipy/scipy/blob/v1.18.1/scipy/signal/_signaltools.py).

The installed reference remains the cheapest integration option: no new
adapter or dependency. pyloudnorm is MIT and SciPy's top-level licence is
BSD-3-Clause; retain notices and review the actual distributed wheel's bundled
components. [pyloudnorm licence](https://github.com/csteinmetz1/pyloudnorm/blob/v0.2.0/LICENSE),
[SciPy licence](https://github.com/scipy/scipy/blob/v1.18.1/LICENSE.txt),
[KENN distribution policy](THIRD_PARTY_LICENCES.md).

## Existing native candidate

KENN already has C++ loudness/peak kernels, Accelerate and scalar build
branches, and a nanobind bridge. The local
[kernel](../../tooling/native/dsp_core/loudness_bindings.cpp),
[build](../../tooling/native/dsp_core/CMakeLists.txt) and
[benchmark](../../tooling/scripts/benchmark_mix_review_native.py) establish that
scope. Reuse these before writing another implementation. The phase 4 timings
are historical evidence for one generated fixture, not measurements of the
expanded benchmark or the current machine state.

nanobind supports array dtype, shape, device and contiguity constraints, but
implicit conversions can create temporary copies. Full-request timing must
include decoding, conversions and binding overhead. Its BSD-3-Clause licence
fits the existing permissive screening; this does not license Apple's system
framework as redistributable project code.
[Pinned array contract](https://github.com/wjakob/nanobind/blob/v3.1.0/docs/ndarray.rst),
[pinned licence](https://github.com/wjakob/nanobind/blob/v3.1.0/LICENSE).

The opt-in flags alone do not prove native execution: the engine can fall back
to Python. Record the loaded extension identity and observed native calls,
then compare complete report metrics, findings and abstentions. Keep short,
silent and invalid input outcomes visible rather than treating missing values
as numeric zero. Keep the candidate opt-in until the plan's promotion gates
are met. [Local engine](../../packages/mix-review/core/local_engine.py).

## Independent comparator availability

libebur128 **v1.2.6** remains a useful independent integrated-loudness, LRA and
true-peak comparator. Its public API exposes frame ingestion and those
measurements. Its algorithms and histories differ from pyloudnorm's batch
oracle, so comparison needs explicit mode, channel mapping, duration and
boundary conventions; exact rounded equality must not be assumed.
[Pinned API](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.h),
[implementation](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.c).

Its MIT licence passes the existing screening, with retained notices.
[Pinned licence](https://github.com/jiixyj/libebur128/blob/v1.2.6/COPYING).
However, `ctypes.util.find_library("ebur128")` returned `None`, and no matching
library was found under `/opt/homebrew/lib` or `/usr/local/lib` on this date.
That bounded search does not prove absence everywhere. Record this comparator
as unavailable; do not install it or represent it as a measured alternative.
The executable comparison can proceed with the existing Python reference and
verified native candidate without changing dependencies.
