# Disabled offline Scan audio foundation, 15 October 2026

This checkpoint adds a separately gated job service and macOS export probe. It
does **not** make the frontend Scan audio button render a track. The candidate
remains disabled, without an HTTP route or a default runtime exporter.

The owner approved the scoped Accessibility helper and supervised a check in a
disposable set. Existing Accessibility access was available; no permission was
requested or changed. No dependency, CI setting or DSP implementation changed.

## Reuse and authority

The job reuses `LocalMixReviewService` for measurements, findings and deterministic
advice. It adds no measurement algorithm. The preceding
[manual export/analysis/disposal rehearsal](KENN_SELECTED_INSERT_GRADE_ASK_2026-10-15.md#offline-render-feasibility-rehearsal)
recorded the Live Object Model and AbletonOSC reuse check: the reviewed bridge
has no audio-export command, and its structure export writes JSON.

`LiveActionService` requires the existing DAW-control policy, the experimental
export flag, an explicitly injected job service, an owner-bound single-use
confirmation and an idempotency key. The token binds an exact source fingerprint,
producer-confirmed musical range and within-range tail policy. The proposal hash
is calculated before the confirmation module's numeric normalization so a digit
change in a range or fingerprint cannot retain the same confirmation.

The current session bridge cannot independently establish a fresh full-arrangement
identity and range. Cached session snapshots are not that evidence. The injected
fingerprint callback and explicit confirmed range are testable contracts, not a
claim that automatic whole-track discovery works.

## Job and process boundaries

- One export/analysis/recovery lease per runtime, including separate service
  instances. An unresolved writer blocks another export after restart.
- A fresh private job directory owns only its generated `kenn-analysis.wav`.
  Imported originals, foreign files, symlinks and hard links are not deleted.
- Exact receipt identity, closed-writer evidence and a finalized stereo 24-bit,
  48 kHz PCM WAV are required before analysis. File-size stability, helper exit
  and helper termination do not prove Live stopped writing.
- WAV input is capped at 150 MiB and eight minutes. At most 64 job records and
  64 private review records are retained; receipts are capped at 2 MiB and reports
  at 1 MiB. Unknown writers remain pending for proven recovery.
- Source checks run before and after export, after analysis, before publication
  and on completed status reads. Changed sources are stale; cancelled late reports
  are discarded. Successful publication follows generated-WAV disposal, while
  the report can be reloaded from metadata.
- A short metadata lock orders cross-instance cancellation against final cleanup
  and publication. Cancellation wins before the commit; a completed commit is
  returned as completed by a later cancellation request.

The adapter launches a fixed executable without a shell. Requests are capped at
16 KiB, receipts at 64 KiB, and the explicit timeout is 1–600 seconds. The Swift
probe uses fixed AX menu/control identifiers, a bounded tree walk and descriptor
inspection. It neither starts playback nor accepts arbitrary UI commands.

These are configured and tested bounds, not measured end-to-end CPU/RSS figures.
Offline analysis still loads a bounded WAV and uses the existing analyzer's
buffers. Export and analysis run on a background worker, outside audio callbacks;
no new callback or publisher timing qualification is claimed.

## Supervised macOS observation

Live 12.4.6 used the supported `com.ableton.live` identity. The read-only inspect
request returned `export_profile_unqualified` without opening a dialog.

The first experimental export probe opened the correct Export Audio/Video dialog,
but its title-based Cancel match failed. The dialog was closed manually. The fix
uses the observed `Base.FinalButtonsBox.CancelButton` identifier. The repeat probe
opened the dialog, returned `export_settings_mismatch` for the existing MP3
preference, cancelled its own dialog and verified its disappearance. Independent
UI inspection confirmed playback and recording were stopped and no generated WAV
existed. The receipt retained `writer_closed=false` and reported no cleanup error.
Existing export preferences were not changed.

The helper cannot press Export yet. Save-panel destination, overwrite handling,
real progress/completion, real Live descriptor closure, range/tails and rendering
cancellation remain unqualified. The current fixed profile also rejects the
observed disabled-but-On video value; a disabled control is not silently treated
as Off. No audio was rendered by this helper check.

## Verification

Changed files, relative to `products/kenn`:

- `apps/backend/src/kenn/core/offline_scan.py`: owned job lifecycle and recovery.
- `apps/backend/src/kenn/core/actions/offline_scan_actions.py`: existing-authority confirmation gate.
- `apps/backend/src/kenn/core/live_action_service.py`: optional injection and schema dispatch.
- `apps/backend/src/kenn/core/macos_live_export.py`: bounded subprocess adapter.
- `apps/backend/src/kenn/tests/test_offline_scan.py`: job and cleanup boundaries.
- `apps/backend/src/kenn/tests/test_offline_scan_actions.py`: policy, confirmation and replay boundaries.
- `apps/backend/src/kenn/tests/test_offline_scan_flow.py`: real analyzer/disposal/reload integration.
- `apps/backend/src/kenn/tests/test_macos_live_export.py`: adapter protocol and process failures.
- `apps/desktop/macos/KENNLiveExportHelper.swift`: disabled fixed-menu AX probe.
- `apps/desktop/macos/KENNLiveExportHelperTests.swift`: native request/completion boundaries.
- `apps/desktop/macos/build_live_export_helper.sh`: temporary executable build.
- `apps/desktop/macos/test_live_export_helper.sh`: native and malformed-protocol checks.
- `apps/desktop/macos/LIVE_EXPORT_HELPER.md`: helper contract and supervised observations.
- `KENN_PLAN.md`: bounded progress and remaining gates only; unrelated research edits excluded.
- `docs/evidence/KENN_OFFLINE_SCAN_HELPER_2026-10-15.md`: this receipt.

The final scoped backend run passed **222 tests in 7.60 seconds** on FakeLive:

```sh
cd products/kenn/apps/backend
KENN_LIVE_BACKEND=fake /usr/bin/arch -arm64 .venv/bin/python -m pytest \
  src/kenn/tests/test_offline_scan.py \
  src/kenn/tests/test_offline_scan_actions.py \
  src/kenn/tests/test_offline_scan_flow.py \
  src/kenn/tests/test_macos_live_export.py \
  src/kenn/tests/test_live_action_service.py \
  src/kenn/tests/test_tier2_control_expansion.py \
  src/kenn/tests/test_tier3_full_control.py \
  src/kenn/tests/test_confirmation_replay.py \
  src/kenn/tests/test_local_mix_review_service.py -q
```

The synthetic integration test crosses confirmation, the real job service, real
Mix Review analysis, generated-WAV deletion and metadata reload with no FakeLive
writes. Unit checks cover owner isolation, replay/tamper refusal, byte/duration
limits, invalid WAVs, cancellation during export/analysis/disposal, stale sources,
changed file identity, crash recovery and bounded retention.

`apps/desktop/macos/test_live_export_helper.sh` passed its Swift build and checks
for request ownership, both export gates, receipt identity, all completion
predicates, PCM validation and an actual test-process descriptor opening/closing.
Its executable malformed-request check also passed. This tests a fixture process,
not writer closure in the real Live renderer.

Review found and fixed a late cancellation/publication race and an event leak on
thread startup failure. A separate read-only review reran 85 job/action tests and
found no remaining blocker for committing the disabled foundation. Mutation checks
detected removed owner, confirmation, helper gate, private-directory, exact-receipt
and writer-closure guards. Removing the final cancellation lock and startup event
cleanup also failed their respective regressions; source was restored exactly,
then both focused checks and all 56 scan tests passed. No failing test was weakened
or relabelled as passing.

Conditions were battery power, 17% then 16%, discharging, with Live open. No mains
callback/publisher benchmark was run, and the real-time loudness candidate remains
disabled. Initial GitHub CLI access failed and the connector returned 404. A later
CLI retry succeeded: the predecessor's [core run](https://github.com/Nite-DSP/monorepo/actions/runs/38753094616)
and [sharing run](https://github.com/Nite-DSP/monorepo/actions/runs/38753094637)
both failed before their steps started; their annotations still identify failed
account payments or the spending limit. No CI setting changed and no CI pass is
claimed.

## Save-panel and validation follow-up, later 15 October

The owner reconfirmed the disposable set was open and supervised this check.
UI automation opened Export Audio/Video, then its native Save panel. No export
preference changed. The panel exposed `save-panel`, `saveAsNameTextField`,
`where popup`, `CancelButton` and `OKButton`; Go To Folder exposed `GoToWindow`
and `PathTextField`. Navigating to a fresh owned `0700` directory produced its
full column-view URL and retained the exact filename `kenn-analysis.wav`.
Save-panel Cancel returned to Export Audio/Video; its exact Cancel returned to
the disposable set. Playback and Arrangement/Session Record read zero, and the
temporary directory contained no file. The Save button was not pressed. This
is control/destination observation only: it does not qualify helper navigation,
overwrite refusal, a real render, completion or writer closure.

Exact changed files for this follow-up, relative to `products/kenn`:

- `apps/backend/src/kenn/core/offline_scan.py`
- `apps/backend/src/kenn/core/macos_live_export.py`
- `apps/backend/src/kenn/tests/test_offline_scan.py`
- `apps/backend/src/kenn/tests/test_macos_live_export.py`
- `apps/desktop/macos/KENNLiveExportHelper.swift`
- `apps/desktop/macos/KENNLiveExportHelperTests.swift`
- `apps/desktop/macos/LIVE_EXPORT_HELPER.md`
- `docs/evidence/KENN_OFFLINE_SCAN_HELPER_2026-10-15.md`
- `KENN_PLAN.md` (only the owned follow-up paragraph).

Changed behavior:

- All three request layers now use ASCII musical ranges with 6/2/2 digit bounds,
  a positive start bar and numerically nonzero length. Padded nonzero ranges and
  ordinary Unicode titles remain valid; Python now rejects Unicode control and
  format characters like Foundation. Invalid adapter requests never launch the
  helper.
- Native toggle normalization accepts exact numeric zero/one. Fractional and NaN
  values remain unqualified instead of truncating into Off/On.
- Native WAV validation requires current-user ownership and a single link on both
  path and opened descriptor, and enforces the existing eight-minute ceiling.
  Sparse fixtures check exactly eight minutes and one extra frame without
  allocating full-track buffers.

The same nine-file FakeLive/backend command above passed **254 tests in 6.82
seconds**. The Swift script passed native and malformed-executable checks. New
range tests first reproduced an accepted over-wide musical component. Four
native mutation copies were each detected: widened range components, integer
toggle truncation, removed single-link checks and removed duration cap. Four
Python mutation rounds detected Unicode-digit acceptance, removed positive/nonzero
range checks, widened adapter components and restored C0-only title guards.
All production code was restored before the final checks. Independent read-only
review found no blocker for this disabled checkpoint.

No audio callback code changed. WAV inspection still reads headers and seeks
over payloads; the new duration/ownership checks do not allocate audio buffers.
No CPU/RSS or real-render timing qualification is claimed. Conditions were
battery power, 13% then 11%, discharging, with Live open; no mains gate closed.
GitHub listed both workflows for `71daad3e` as failed; fetching their job details
then failed to connect. The earlier billing/spending-limit annotations remain
the last verified cause, rather than a verified diagnosis of these newer runs.

## Remaining gate

`KENN_PLAN.md` remains the sole work queue. Qualify the real save/render lifecycle
and independent fresh source/range evidence, then add the HTTP/frontend states and
verify the complete button-to-report path on FakeLive and a supervised disposable
set. Neither this probe nor the prior manual render qualifies automatic Scan audio.
Before promotion, fix AX reads that collapse failure/truncation into empty results
and bind WAV validation plus descriptor inspection to one stable file identity.
Those known limitations do not become passing conformance because the candidate
is disabled.
