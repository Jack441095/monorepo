# Transient comparison source significance

Recorded 15 October 2026 on `feature/reference-review-grade`, after `5005f47d`.

## Behavior

The optional pre/post transient comparison peak-normalizes its inputs. The enclosing upload's RMS cannot qualify the separate pre-render, and normalized onset shapes cannot establish original source activity.

The review workflow now retains both decoded renders' existing full-file raw mono RMS in a versioned `kenn.transient_preservation.activity.v1` envelope. Both readings must be finite and strictly above the established -60 dBFS uploaded-source floor. Different analysis sample rates abstain because one render's sample rate cannot timestamp the other's events. No new decoder, resampler, onset detector or activity threshold is introduced.

Handoff and typed evidence require that envelope, a positive integer matched-event count, a finite preservation score in [0, 1] and a nonempty bounded profile. A measured score of zero remains valid. Legacy or malformed summaries abstain; an active main upload alone cannot restore them. Cached prose is rebuilt when transient evidence is unqualified. History retains bounded provenance and rebuilds transient facts from it instead of accepting cached scalar facts.

The cross-boundary check also exposed an existing RMS field mismatch: the handoff emitted `rms_dbfs_estimate`, whereas KENN qualifies `rms_dbfs`. The legacy estimate is derived from decoded `true_rms` or measured sample-square RMS in `analysis_core.py`, not inferred from sample peak. The handoff now emits the canonical alias, retaining explicit canonical values even when quiet or invalid. It never falls back from a quiet canonical value to a louder legacy value or substitutes peak for RMS.

## Exact files

Paths are relative to the monorepo root.

- `audio-technology/audio-analysis/audio_analysis/mix_review/review_workflow.py`: reuse pre/post decoded raw RMS, abstain before normalization and reject incompatible analysis rates.
- `audio-technology/audio-analysis/audio_analysis/integration/handoff.py`: bounded qualified transient summary or abstention marker; canonical measured RMS alias.
- `audio-technology/audio-analysis/tests/test_transient_publication.py`: producer and handoff activity, malformed values, rate mismatch, anti-phase cancellation, isolation and RMS field precedence.
- `audio-technology/audio-analysis/tests/test_handoff_scenarios.py`: qualified optional transient fixture.
- `products/kenn/apps/backend/src/kenn/core/evidence.py`: shared qualification, bounded history provenance and rebuilt transient facts; legacy scalar aliases excluded.
- `products/kenn/apps/backend/src/kenn/server_payloads.py`: cached narrative qualification, validated summary projection and stale metric exclusion while retaining independently qualified own/reference evidence.
- `products/kenn/apps/backend/src/kenn/tests/test_evidence.py` and `test_server_payloads.py`: boundary, history, legacy narrative and valid-zero regressions.
- `products/kenn/KENN_PLAN.md` and this receipt: progress and remaining qualification work.

## Reuse decision

This slice changes publication and carries an existing measurement; it adds no audio measurement or dependency. Source inspection of `audio_analysis/utils/audio_io.py` confirms that `read_wav_mono` accumulates `(left + right) / 2` squared before its preview low-pass filter and decimation, then returns `true_rms`. Reusing that reading avoids a second decode and additional sample allocations. It also keeps anti-phase cancellation aligned with the mono signal used by the transient comparison. The existing normalized onset algorithm and its numerical behavior remain unchanged.

The standing external-tool comparison and synthetic benchmark requirement applies when extending a measurement. No external replacement was shortlisted here because neither the RMS implementation nor the transient measurement is being extended. Generated-signal verification below checks this publication contract rather than claiming new metrological or listening qualification.

## Verification

From the monorepo root:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=shared:audio-technology/audio-analysis \
  products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly \
  audio-technology/audio-analysis/tests/test_transient_publication.py \
  audio-technology/audio-analysis/tests/test_handoff_scenarios.py \
  audio-technology/audio-analysis/tests/test_transient_groove.py \
  Audio_Too/tests/mix/test_mix_review_stage10.py \
  Audio_Too/tests/mix/test_mix_review.py -k 'transient or TestKennHandoff'
```

Result: **94 passed, 72 deselected** in 1.89 seconds. An initial invocation omitted `shared` from `PYTHONPATH` and failed collection because `nite_core` was unavailable; the corrected command above passed without dependency changes.

From `products/kenn/apps/backend/src`:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_evidence.py kenn/tests/test_server_payloads.py \
  kenn/tests/test_diagnostic_loop.py kenn/tests/test_server_evidence_context.py
```

Result: **210 passed** in 1.09 seconds. Process-local mutations removing the handoff RMS floor produced **4 expected failures**; bypassing server transient qualification produced **6 expected failures**. Removing the canonical RMS alias failed its new regression; rejecting every transient result failed the active zero-score regression. No mutation was retained.

A generated 44.1 kHz, 32-bit PCM click train traversed the real producer, handoff, typed adapter and JSON history replay. Identical active renders retained a score of **1.0** with **14 matched events**. Reducing either source by 80 dB withheld the score, as did an anti-phase stereo pre-render. Audio remained in memory. Independent review caught stale transient scalar metrics leaking beside a qualified summary; normal-path filtering and poisoned-metric regression now cover it.

Full-suite command from `products/kenn/apps/backend/src`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests ../../../packages/mix-review/tests
```

Result: **5895 passed, 55 skipped, 3 failed** in 129.44 seconds. The three failures match the preceding Doctor receipt:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: missing embedding index leaves retrieval BM25-only and the benchmark does not qualify.

No new failures appeared. The final scoped backend run includes the normal-path scalar filtering correction. `git diff --check` passed.

## Remaining work

E2 and the source-significance checkbox remain open. Legacy ERB stem previews and low-end stem rankings still need genuine per-source activity provenance through handoff and history. Raw source activity does not prove that a transient profile identifies an audible cause, that the renders contain matching material, or that the grade's meters meet conformance requirements. No real Live session was modified.
