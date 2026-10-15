# Reference comparison significance gate — 15 October 2026

This records a bounded E2 follow-up in [KENN_PLAN.md](../../KENN_PLAN.md), based on `94ad8a7d`. It is committed with the implementation and regression tests on `feature/reference-review-grade`.

## Changed behavior

The reference scorer already withholds all reference points when either source RMS is missing, non-finite or at/below -60 dBFS. The ordinary upload comparison now uses the same RMS evidence from the scorer's dynamics result before exposing reference-derived comparison details. This includes 40-band and LTAS deltas, EQ moves, LUFS and pink-noise summaries, tonal balance, matching gains, dynamics, stereo, coaching, recommendations and the EQ Eight preset.

Using the scorer's result matters for stereo: it downmixes L/R before measuring RMS. A loud anti-phase file can have audible channels and a near-silent downmix; per-channel RMS would have shown advice while the grade correctly withheld points. Quiet and anti-phase sources now retain the scorer's exact ungraded reason and show no comparison details.

The change is confined to the local comparison service and its generated WAV tests. It adds no dependency and retains the existing -60 dBFS boundary. It does not establish individual stem significance: this path compares whole-file uploads, while Live stem meters remain unqualified.

## Verification

Backend command, from `products/kenn/apps/backend/src`, using FakeLive:

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_local_mix_review_service.py
```

**33 passed in 2.23 s.** Generated tests cover a quiet mix, quiet reference and stereo anti-phase mix whose downmix falls below the scorer floor. They assert the reference score is unavailable, the source-specific reason is preserved, and all comparison-derived fields are withheld. Existing significant comparisons continue to assert their normal outputs.

An independent read-only review identified the channel-average/downmix mismatch, then signed off after the gate used the scorer's own downmixed RMS and the anti-phase regression was added. `git diff --check` passed.

## Exact changed files

- `apps/backend/src/kenn/core/local_mix_review_service.py`: gate reference-derived comparison details using the scorer's source RMS values.
- `apps/backend/src/kenn/tests/test_local_mix_review_service.py`: cover quiet mix, quiet reference and anti-phase stereo; pin the withheld fields.
- `KENN_PLAN.md`: record the evidence and keep individual Live-stem significance open.
- `docs/evidence/KENN_REFERENCE_SIGNIFICANCE_2026-10-15.md`: this receipt.
