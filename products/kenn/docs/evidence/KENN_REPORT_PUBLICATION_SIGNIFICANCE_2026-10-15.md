# Saved publication, canonical receipts and grade validity — 15 October 2026

This slice closes reproducible publication and score-validity gaps found after the low-end stem work. It does not qualify the meters, perceptual usefulness, or the wider E2 gate.

## Reproductions and behavior

An active enclosing mix with unqualified optional stem/transient sections could repeat historical repair prose through saved HTML, raw handoff and session reports. The detailed renderer's qualified stem section did not protect its summary, action plan or cached critique. The signed-report renderer used a separate path.

`integration/handoff.py` now provides a pure `project_report_publication` used by both HTML renderers, the handoff and session-report builders. It copies inputs, qualifies optional sections independently, retains independently valid numeric measurements, and rebuilds mixed narrative caches when their source proof fails. Canonical top-level abstention takes precedence over older nested summaries. Empty sentinels and projection remain stable across replay. Activity proof does not validate retired overlap, carving or clarity predictions.

`mix_review_critique.py` shares the transient qualification helper. Its payload, cached flags and model prompt cannot publish a quiet comparison as measured damage. The deterministic template describes qualified scores as a matched-event proxy and retains a genuine zero, without inferring audible damage or limiter settings. Ordinary reviews without optional comparisons do not invent a failure.

A raw local-review receipt with active mix RMS and unsupported `stem_masking_lowest_visibility`/`stem_count` aliases could enter canonical session context, then become session measurement evidence in the intelligence brief. `session_context.py` now rebuilds optional facts and bounded proof with the existing typed evidence adapter. Mixed cached advice is withheld when optional qualification fails. `session_intelligence.py` repeats qualification for older or manually edited contexts. Independent whole-mix readings, qualified zero values and reference evidence survive.

Declared-target scoring previously awarded target points for NaN readings. `declared_target.py` now withholds non-finite, boolean and unrepresentable readings and invalid explicit targets. `grade.py` rejects malformed or over-budget parts without clamping; valid independent parts retain their points and denominator. Composed session tests cover peak and target changes A→B→A, equality on return, missing-peak denominators and isolation. These tests qualify score arithmetic, not acoustic accuracy.

## Verification

All verification used fake Live and deterministic fixtures. No audio algorithm, threshold, dependency, CI or permission changed. This reuses the existing activity helpers and typed projector, so it adds no measurement requiring a new upstream algorithm comparison.

- Saved publication, critique, handoff, renderer, session-report, transient and low-end scope: **156 passed**.
- Session context/intelligence, plug-in handoff, chat context and typed evidence scope: **409 passed**.
- Declared target, grade, reference matching and local-review service scope: **179 passed**. Includes existing generated browser reference A→B→A→none coverage.
- Process-local mutations: disabling canonical optional projection caused **14 expected failures**; admitting NaN caused **2 expected failures**; disabling the HTML publication projection was caught; bypassing the direct transient gate caused **6 expected failures**. No source mutation remained.
- Full backend and mix-review suite: **6071 passed, 55 skipped, 3 pre-existing failures**, in 139.48 seconds. The failures are `test_low_end_name_and_fader_overlap_is_an_advisory_candidate`, `test_near_ceiling_track_meter_creates_track_specific_headroom_advisory` (both missing advisories), and `test_fixed_session_grounded_benchmark_qualifies` (missing embedding index/BM25-only). These match the prior baseline; they are not hidden or counted as passes.

The 156-case command, from the monorepo root, used `KENN_LIVE_BACKEND=fake`, `PYTHONPATH=shared:audio-technology/audio-analysis:products/kenn/apps/backend/src:products/kenn/packages/mix-review/core` and the backend virtualenv's `python -m pytest -q -p no:randomly` against these files under `audio-technology/audio-analysis/tests/`: `test_transient_critique_significance.py`, `test_erb_critique_significance.py`, `test_report_publication_significance.py`, `test_transient_publication.py`, `test_low_end_rendering_significance.py`, `test_handoff_scenarios.py`, `test_report_rendering_scenarios.py`, `test_session_report_scenarios.py`, `test_shareable_report.py`.

The full command, from `products/kenn/apps/backend/src`, was:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

Tests exercise the real renderer functions, including the signed route's renderer, rather than booting the Audio_Too server and database. No provider output or listening session is qualified here. The offline comparison and producer listening gates remain open in `KENN_PLAN.md`.

## Files changed

- `audio-technology/audio-analysis/audio_analysis/integration/{handoff,report_rendering,session_report}.py`
- `audio-technology/audio-analysis/audio_analysis/mix_review/{mix_doctor,mix_review_critique}.py`
- `audio-technology/audio-analysis/tests/{test_report_publication_significance,test_transient_critique_significance}.py`
- `products/kenn/apps/backend/src/kenn/core/{declared_target,grade,session_context,session_intelligence}.py`
- `products/kenn/apps/backend/src/kenn/tests/{test_declared_target,test_grade,test_session_context,test_session_intelligence}.py`
- `products/kenn/KENN_PLAN.md` and this receipt.
