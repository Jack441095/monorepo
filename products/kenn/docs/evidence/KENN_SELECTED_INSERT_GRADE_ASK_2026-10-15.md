# Selected-insert grade answers — 15 October 2026

Recorded branch: `feature/reference-review-grade`, working tree based on
`d2c1179e` (`Show qualified stereo grades for the selected insert`). This receipt
qualifies the bounded Ask connection. E1/E2 remain open in `KENN_PLAN.md`.

## Behavior and reuse

An explicit request such as `Grade this insert`, `Grade Kick` or `Grade track 1`
now returns the same `kenn.plugin_insert_grade.v1` projection used by the selected
source display. Supported polite prefixes, `rate`, `selected insert` and instruction
suffixes also work. General grading explanations and uploaded-mix grading keep
their existing routes. Arbitrary track names can use the selected-insert wording
or a track number; this bounded intent matcher does not recognise every name.

The existing six-point correlation rule, validated 100 ms window, activity floor,
ownership and freshness policy are reused unchanged. No measurement, DSP library,
dependency or scoring threshold was added. The standing reuse check therefore
retains the implementations recorded in the [selected-insert display receipt](KENN_SELECTED_INSERT_GRADE_2026-10-15.md).

The answer identifies the insert, sample interval, rate, sequence, source
generation, capture age, correlation, threshold band, rule source and tier. It
shows the available six-point denominator and the full 100-point budget without
rescaling. Dynamic health, low-end control, spectral balance, stem separation,
declared targets and reference matching remain explicitly ungraded. Correlation
alone does not establish audible cancellation severity. An unavailable grade
means missing qualified evidence, not zero-quality audio.

The backend reads fresh topology before taking the grade snapshot. Context and
grade are projected under the same handoff lock, with exact nonempty owner and
selected insert identity. A Pause, expiry, generation reset or owner change while
topology is being read cannot restore an earlier score. A binding cannot discard
another explicitly named track, including names outside the role-word list.
Generic context reads remain grade-free. Grade requests return before the
analysis advice/proposal policy and cannot create an action card or write to Live.

Native explicit Ask includes its compact handoff even with background publishing
off. Browser Ask already sends the selected insert ID and now receives the
grounded answer through that existing transport. Answers describe their captured
window; they are not a continuously refreshed score in chat history.

## Verification

- Backend: **347 passed, four deselected**, including the compiled native client
  against an isolated ephemeral FakeLive HTTP server. Command from `apps/backend`:

  ```sh
  KENN_LIVE_BACKEND=fake \
  KENN_NATIVE_COMMAND_TEST_BINARY=/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/workspace/builds/kenn-plugin-e1/TestCommandIntegration \
  .venv/bin/python -m pytest -q \
    src/kenn/tests/test_plugin_insert_grade_ask.py \
    src/kenn/tests/test_plugin_insert_grade.py \
    src/kenn/tests/test_plugin_handoff.py \
    src/kenn/tests/test_plugin_insert_sources.py \
    src/kenn/tests/test_mix_doctor.py src/kenn/tests/test_grade.py \
    src/kenn/tests/test_live_track_analysis.py src/kenn/tests/test_live_paired_analysis.py \
    -k 'not native_feature_publishers_remain_fresh'
  ```

- The new Ask file has **36 cases**: exact source-payload equality; named/numbered
  targets; no-owner/foreign/unknown selection; A→B→A isolation; mono, quiet,
  legacy and undefined readings; unrounded expiry; queued Pause and late frames;
  reset/recovery; explicit bindings; blocked topology reads; and actual HTTP.
- Actual C++ Ask runs five request spellings before ordinary analysis, with
  background publishing off. Python proves each spelling ingests its own native
  handoff and returns that exact insert/window, six available points, full budget
  100 and no action card. Existing two-insert analysis, paired evidence and
  confirmed FakeLive Apply/readback behavior still pass.
- Native arm64 Release functional CTest: **4/4 passed** (CommandIntegration,
  RealtimeThreadSafety, ContinuousAnalysis and StreamingMeter), 5.50 seconds.
  After adding the five-spelling regression, CommandIntegration was rebuilt and
  exercised again by the passing backend run above. Build command uses
  `/opt/homebrew/bin/cmake`, build directory `workspace/builds/kenn-plugin-e1`.
- Frontend scoped unit verification: **42 passed across three files**:
  `npm test -- src/composables/useKennPlugin.test.ts src/api/kenn.test.ts src/api/pluginInsertGrade.test.ts`.
- Chrome E2E: **1 passed**, 44.3-second test / 51.3-second total, using the owned
  isolated FakeLive companion on port 18937 with the answer model disabled.
  `KENN_E2E_PORT=18937 npx playwright test e2e/plugin_audio.e2e.ts --workers=1`
  proves Kick 5.1/6 in chat, Bass 6/6 after explicit selection and Pause abstention
  without grade action cards, while retaining display, mono, owner, stale and
  FakeLive Apply/readback/Undo checks. The fixture server was stopped afterward.

Mutation checks: moving the grade snapshot before topology observation fails all
four blocked-read lifecycle cases; removing native grade handoff inclusion fails
the first grade Ask; removing the bound-target guard fails the Piano regression.
All mutations were removed and the affected production checks rerun green;
the Python source restorations were also checked byte-for-byte.
An initial mutation selector matched no tests; the corrected selector produced
the guarded failure. An initial native CTest call omitted offline mode and failed
companion availability; `KENN_TEST_OFFLINE_ONLY=1` passed. Neither is a product
failure hidden by relaxing assertions. Two existing native timestamp-conversion
warnings remain. The browser fixture also logged unavailable optional SLO cache
and BM25-only retrieval state; neither supplies this deterministic grade.

## Performance and remaining gates

No callback, DSP, queue capacity, fixed analyser storage, HTTP publication cadence
or permission changed. Added work is bounded request parsing, one selected-window
projection/copy and deterministic answer formatting on existing workers. No model
inference is required. Sustained CPU/RSS and callback-tail implications remain
unmeasured for this build.

Conditions observed: battery power, 39% and discharging; load averages
3.48/2.87/2.91. These are functional test conditions, not performance qualification.
The four publisher profiles were deliberately deselected. Controlled mains/quiet
callback cells, delayed/memory/65-second publisher profiles, five-minute workloads,
64-insert model/ordinary-traffic contention and supervised disposable-host
qualification remain open. The StreamingMeter loudness candidate stays disabled;
its remaining conformance and promotion gates are unchanged.

GitHub Actions on the preceding `d2c1179e` checkpoint still could not start jobs
because account payments/spending limits blocked them: [core run 38742613212](https://github.com/Nite-DSP/monorepo/actions/runs/38742613212).
No CI settings were changed. Publication must still verify the matching
`kenn-app` branch's exact committed product-tree equality.

Owned paths: backend `core/live_track_analysis.py`, `core/plugin_grade.py`,
`plugin_handoff.py`, `tests/test_plugin_insert_grade_ask.py`,
`tests/test_live_track_analysis.py`; frontend `e2e/plugin_audio.e2e.ts`; native
`Source/PluginProcessor.cpp`, `Source/test_command_integration_main.cpp`; this
receipt and `KENN_PLAN.md`. Unrelated untracked research is excluded.
