# Selected-insert grade display checkpoint — 15 October 2026

This receipt covers the selected-source endpoint and browser display built on
`5847587e` on `feature/reference-review-grade`. The commit containing this receipt
identifies the final source. It does not qualify the grade Ask route, the disabled
streaming loudness candidate, callback deadlines or a producer's Live session.
`KENN_PLAN.md` remains the work queue.

## Evidence and scope

The existing owner-scoped insert list now adds `kenn.plugin_insert_grade.v1` only
to the explicitly selected source. It uses that source's captured window and
unrounded age under the handoff lock. It does not read the process-wide latest
Doctor report, infer a master bus from a host label, or prepare a Live action.

Points require all of the following:

- Matching conversation and insert identity, a valid contiguous 100 ms window,
  enabled analysis, no pending Pause/source reset and capture age at most 1 s.
- RMS strictly above the existing live -80 dBFS activity floor.
- Actual stereo input and defined correlation, with matching eligibility
  metadata on the frame and its owning window.

The standing reuse check retains the current C++ accumulated channel energies
and correlation denominator floor (`1e-12`). No new DSP algorithm or dependency
was added. C++ now retains `input_channels` and `correlation_valid` through the
snapshot, handoff window and paired history. The legacy numeric +1 fallback is
unchanged for observations, but mono duplication or undefined-energy correlation
cannot qualify for points. A mono/stereo layout change advances source generation
immediately and waits for a complete new window before recovery.

The existing Doctor correlation rule is extracted as a pure shared function.
Its four bands still award 1.5, 3.6, 5.1 or 6 points. Correlation sign is a meter
convention; the deduction sizes and positive thresholds remain house judgement
pending E9 listening checks. Negative correlation alone does not establish
audible severity. The existing session audit's numeric behavior is preserved.

The selected insert can therefore earn only six of the possible 100 points. The
other four technical dimensions, declared loudness/peak targets and reference
matching remain ungraded. No score is rescaled. Older publishers lacking the new
eligibility pair retain their existing observations but receive no stereo points.

The browser validates owner/insert/host identity, point totals, window geometry
and eligibility before rendering. It shows the available denominator, selected
100 ms scope, threshold, source/tier and omissions. It retires a score locally at
expiry, including when page polling is suspended, and immediately on pending
Pause or source selection. Selection/request revisions reject delayed A→B→A
responses and older responses after a newer failure. Request elapsed time counts
against the evidence lifetime. Existing 1 Hz browser polling and 2 Hz native
publication are unchanged; short ungraded gaps between fresh polls are possible.

## Verification

All checks used generated audio/features and `KENN_LIVE_BACKEND=fake`. The native
build was arm64 Release in `workspace/builds/kenn-plugin-e1`, using Homebrew's
arm64 CMake/CTest. The machine was on battery, with Ableton open; these are
functional results, not timing qualification. No producer-session writes occurred.

- Backend source/display tests cover real ingestion through the selected-source
  projection, all four rule bands, denominators, owner/sibling isolation, mono,
  undefined correlation, legacy metadata, quiet audio, stale/disabled windows,
  exact age expiry, queued Pause, source reset/recovery and replay rejection.
  Malformed or contradictory metadata is rejected before retained evidence changes.
- Removing the undefined-correlation eligibility guard fails its new regression;
  the source was restored before final verification. Existing shared-rule boundary
  mutation checks also fail as intended.
- Frontend: 128 tests passed; production typecheck/build passed. Three mutations
  fail for owner association, A→B→A retirement and hidden-page expiry, then pass
  after restoration.
- Chrome against an isolated FakeLive companion: one browser test passed
  (51.6 s test time). It covers Kick 5.1/6, Bass 6/6, mono abstention, explicit
  source selection, omissions, Pause/staleness, existing approved Apply/readback/
  Undo and foreign-owner refusal. The graded screenshot was visually reviewed.
  The owned companion was stopped afterwards; screenshots remain local artifacts.
- Native continuous analysis: 896 checks, zero failures. Mono, stereo, either
  silent channel, energy-floor boundaries, queued layout changes, reset/recovery,
  instance isolation and callback allocation checks are covered. All four scoped
  functional native targets passed: CommandIntegration offline,
  RealtimeThreadSafety, ContinuousAnalysis and StreamingMeter.

Final backend verification: 311 tests passed across handoff, insert sources,
insert grading, Mix Doctor, combined grade, track analysis and paired analysis;
four opt-in heavy publisher profiles were deselected. The new insert-grade file
contains 41 cases. A separate actual native `TestCommandIntegration` run through
the isolated FakeLive HTTP fixture passed. It checks root/window/paired metadata
from both native Kick and Bass inserts, existing guarded advice and FakeLive-only
confirmation behavior. This is not a grade Ask test. The final serializer pair
fix was rebuilt and its affected offline targets passed 2/2; the four-target
functional run above also passed before that wire-only fix.

Sharing-script verification: 24 tests passed with
`PYTHONPATH=products/kenn/tooling`. The first invocation without that configured
tooling import path failed collection; the corrected command passed. GitHub
Actions was rechecked on 15 October: the preceding core run `38737810711` could
not start because account payments/spending limits blocked jobs. No CI settings
were changed. Publication uses the existing manual product-tree sync and exact
committed-tree comparison.

## Cost and remaining limits

On this arm64 build, `KENNAnalysisSnapshot` grows from 904 to 912 bytes and
`KENNContinuousAnalysis` from 406,072 to 406,136 bytes: 64 bytes per insert,
4 KiB for 64 inserts. The fixed queue remains 145,976 bytes per insert because
the layout byte fits existing packet padding. Callback changes use the existing
atomic invalidation path and a fixed packet field; no allocation, network call or
blocking lock was added there. JSON eligibility fields and backend/browser grade
projection add work outside the callback. Their sustained publisher/model cost
has not been qualified. Memory remains bounded by the existing insert/window caps.

The grade Ask handoff and answer route are deliberately outside this checkpoint.
The native editor's text-only Ask answer does not yet expose this grade. The
existing browser surface embedded by the plug-in can display it through its
owner-scoped source poll. E1 and E2 remain open.

The machine was still on battery (47%, discharging) at publication preparation.
The controlled mains callback matrix, 64-insert sustained publisher/memory/delay
workloads, model-resident contention, authentic/remaining meter vectors and
supervised host qualification remain outstanding. Battery results cannot close
the mains gate. The streaming loudness/true-peak candidate remains disabled.

## Changed files

- Backend: `core/plugin_grade.py`, `core/grade.py`, `core/mix_doctor.py`,
  `plugin_handoff.py`; regression tests in `test_plugin_insert_grade.py`,
  `test_mix_doctor.py` and `test_live_track_analysis.py`.
- Frontend: `api/kenn.ts`, `api/pluginInsertGrade.ts`, their tests/fixture,
  `composables/useKenn.ts`, `useKennPlugin.test.ts`,
  `components/KennLiveStatus.vue` and `e2e/plugin_audio.e2e.ts`.
- Native: `ContinuousAnalysis.h/.cpp`, `PluginProcessor.cpp`,
  `test_continuous_analysis_main.cpp`.
- Planning: the existing E2 surface-delivery entry in `KENN_PLAN.md`.
