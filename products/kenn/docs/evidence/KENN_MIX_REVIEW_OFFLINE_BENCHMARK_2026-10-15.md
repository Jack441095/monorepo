# Offline Mix Review comparison and temporal meter evidence — 15 October 2026

The Python/pyloudnorm + SciPy path remains the agreement reference. Decode-only
is the strongest candidate in this bounded comparison; native loudness is not
report-identical on every fixture. No production DSP, default gate, dependency,
permission or CI setting changed. The disabled plug-in meter stays disabled.

## Reuse and comparison contract

The [source and licence refresh](../research/KENN_MIX_REVIEW_BENCHMARK_REUSE_2026-10-15.md)
checks the existing implementations before adding another one. libebur128 was
unavailable in the bounded local search and was not installed or measured.
Agreement with the existing Python implementation is not independent accuracy
or listening validation.

The [harness](../../tooling/scripts/benchmark_mix_review_native.py) forces four
independent variants: reference, native decode only, native loudness only, and
both. It disables inherited masking/metrics gates and restores environment and
call observers on success or failure. Native claims require accepted output
inside each timed request, including finite native integrated loudness, LRA and
true peak; a missing peak cannot silently earn credit through SciPy fallback.
Each measured report must pass, rather than only the last repeat.

The matrix contains 27 generated PCM16 fixtures at 44.1, 48 and 96 kHz: mono and
stereo steady, stepped, silence and 200 ms short input, plus stereo anti-phase.
Active and silent fixtures last 6 s. Every variant has one independent warmup
and five measured requests: 108 warmups and 540 timed requests in total. Meter
comparison allows 0.01 LU or dB on the rounded report readings; all findings,
including numeric evidence and abstention reasons, must match exactly. The
receipt stores these three meters and all findings; it does not assert parity
of every other report metric or waveform array.

```sh
KENN_LIVE_BACKEND=fake products/kenn/apps/backend/.venv/bin/python \
  products/kenn/tooling/scripts/benchmark_mix_review_native.py \
  --matrix --seconds 6 --repeats 5 \
  --json-out products/kenn/docs/research/results/kenn_mix_review_native_matrix_2026-10-15.json
```

The [raw receipt](../research/results/kenn_mix_review_native_matrix_2026-10-15.json)
records fixture hashes, individual timings, per-request execution proof and
code/extension hashes. Its source revision is the parent checkout; the harness
hash identifies the uncommitted implementation measured here. Only generated
audio was used; no WAV or personal session was committed. Sequential variants
and uncontrolled background load limit timing conclusions. The Mac was on
battery, so all request timings are observational and do not qualify mains
callback/publisher performance.

## Results and reference decision

| Variant | Fixture comparisons passing | Active-fixture median request p50 | Median paired speed ratio |
|---|---:|---:|---:|
| Python reference | control | 48.587 ms | 1.000x |
| Native decode only | 27/27 | 47.695 ms | 1.026x |
| Native loudness only | 26/27 | 13.884 ms | 3.568x |
| Combined native | 26/27 | 12.630 ms | 3.870x |

These medians summarize fifteen active fixtures, each with five requests. They
are observational battery-powered timings, not a controlled speedup claim. The
twelve silent/short fixtures check refusal parity and are excluded from the
active timing summary. Native loudness is not required to execute when the
engine abstains, so those fixtures do not prove native loudness performance.
Each active native-loudness variant has 75/75 individually verified native
requests; decode-enabled variants prove decoding on all 135 measured requests.

Both loudness-enabled variants fail exact finding parity on the 6 s stepped
mono fixture at 44.1 kHz, in all five repeats: reference LRA is **21.53 LU**,
native **21.54 LU**. Integrated loudness and true peak agree. The 0.01 LU delta
meets the meter tolerance, but the finding's numeric evidence differs, so the
stricter finding contract correctly fails. Recommendation prose, detection and
severity are unchanged. The final CLI exits **1**, preserving this failed
comparison; it is not an infrastructure or test failure.

Keep Python/pyloudnorm + SciPy as the agreement reference because it defines
the existing report contract and avoids a dependency or adapter change.
Decode-only passes this matrix but shows little observed request saving.
Native loudness is faster in this exploratory run but cannot be called
report-identical. Any decision to accept rounded evidence differences needs an
explicit contract and boundary tests, alongside independent accuracy and
controlled timing evidence. None of these results promotes the candidate.

Scoped Python verification: **43 harness tests plus 67 existing loudness,
local-service, route and Mix Review evaluation tests passed**. Harness tests
cover hidden fallback, incomplete native peak output, inherited gate isolation,
restoration after exceptions, earlier failed reports and compensating calls
across repeats. Weakening native-result validation caused three expected
failures in a process-local mutation. No production source was mutated.
The full backend suite was not rerun for this harness/test/documentation diff;
the previously recorded three unrelated failures remain unqualified here.

## Generated temporal meter cases

The native test follows [EBU Tech 3341, November 2023, Table 1 p. 8 and the
clarification on p. 9](https://tech.ebu.ch/docs/tech/tech3341.pdf). Case 11 runs
one continuous 120 s stream with twenty 6 s segments; each contains a 3 s tone,
progressively offset by 150 ms, with successive targets from -38 to -19 LUFS.
Case 14 runs one continuous 16 s stream with twenty 800 ms segments, 400 ms
tones and 20 ms offsets. No reset between segments may erase rolling history.

| Sample rate | Case 11 worst absolute error | Case 14 worst absolute error |
|---|---:|---:|
| 44.1 kHz | 0.065667 LU | 0.450615 LU |
| 48 kHz | 0.066257 LU | 0.451204 LU |
| 96 kHz | 0.068645 LU | 0.453583 LU |

All twenty case 11 maxima per rate meet 0.1 LU. Case 14 has sixteen of twenty
maxima per rate outside that tolerance: the existing 100 ms reporting hop misses
off-grid momentary windows, as in case 13. The executable prints this known
conformance gap. Its regression pins the expected window-energy loss rather
than claiming that the standard passes. The candidate still needs a shorter
momentary hop and measured CPU cost before its EBU mode can qualify.

`TestStreamingMeter` reports 1,013 checks and zero regression failures.
Disabling the new temporal-maxima accumulation produced 126 failures; source
and binary were restored and retested. The scoped CTest run passed
ContinuousAnalysis, RealtimeThreadSafety and StreamingMeter, 3/3 in 5.34 s.
This is not the full native suite. Cases 6–8, native LRA, authentic programme
vectors and sustained contention qualification remain open.
