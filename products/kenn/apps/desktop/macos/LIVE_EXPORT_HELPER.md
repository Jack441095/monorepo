# Experimental Live export helper

`KENNLiveExportHelper.swift` is a separately built, disabled export adapter for the
Scan audio job service. It adds no package dependency and does not install an app,
change macOS settings or request Accessibility access. It is not yet a working
automatic renderer.

The executable accepts one JSON request on standard input, writes one JSON receipt
on standard output and exits. Its only proposed menu action is Ableton Live's
fixed File > Export Audio/Video command. It never sends keystrokes, uses screen
coordinates, starts playback, changes the arrangement or invokes arbitrary menu
commands.

`action: "inspect"` is read-only. It validates the request, existing Accessibility
access, the Live process identity and the exact expected window title. It then
returns `unavailable` with `export_profile_unqualified`; inspection never opens a
dialog.

`action: "export"` requires both `KENN_EXPERIMENTAL_LIVE_EXPORT=1` and the exact
`--supervised-test` argument. This gate is for an owner-supervised disposable-set
check, not normal use. The current implementation can open one identifiable
Export Audio/Video dialog, read its exact settings/range AX identifiers, then
attempt its exact Cancel identifier and verify that the owned window disappears.
It returns `unavailable`. It deliberately cannot press Export: the save-panel
destination and export lifecycle have not been qualified. An inaccessible,
ambiguous or unknown UI is a capability failure, never permission to guess.

## Build and scoped verification

From the repository root on macOS:

```sh
products/kenn/apps/desktop/macos/build_live_export_helper.sh
products/kenn/apps/desktop/macos/test_live_export_helper.sh
```

The build script prints its executable path in a fresh temporary directory. An
optional first argument selects a build output directory. The test script builds
and removes its own temporary executables. Tests do not inspect or operate a Live
process and do not request Accessibility access. They exercise the double export
gate, exact receipt identity, private/exclusive directory ownership, overwrite and
symlink rejection, finalized PCM validation and an actual fixture file descriptor
opening/closing in the test process.

The 16 Oct fixtures also exercise the actual export caller with injected native
boundaries: failed, malformed, over-limit or late preflight UI reads prevent the
menu action. Full lifecycle fixtures acquire a synthetic dialog, read its profile
and verify cancellation and disappearance; every fixture rejects Export/Save
button actions. No fixture operates Live. The AX
reader distinguishes explicit optional absence from messaging failures, checks
each array element's CF type, rejects changed counts and applies one 2048-node
budget across all window roots. Deadline checks run before and after each read.

Eight additional native mutation checks on 16 Oct each failed their regression
assertion: treating a failed AX read as empty, accepting a malformed AX array,
truncating an overflowing tree, ignoring a read deadline, combining different WAV
generations, omitting descriptor identity rechecks, omitting parser identity
rechecks and ignoring ctime. These were run on temporary source copies. See
[completion evidence](../../../docs/evidence/KENN_OFFLINE_SCAN_COMPLETION_2026-10-16.md).

Mutation checks on 15 Oct 2026 independently removed the supervised flag gate,
accepted a nonprivate directory and treated unknown writer inspection as closed.
Each corresponding Swift regression test failed. Python adapter mutations also
removed its explicit gate and receipt identity check, and treated a launched
timeout as writer closure; each corresponding regression test failed. These checks qualify those boundaries,
not an actual Ableton export.

## Supervised disposable-set probe, 15 Oct 2026

The owner-supervised probe used Live 12.4.6 on macOS. The exact supported bundle
identifier is `com.ableton.live`. Accessibility was already trusted; the helper
did not prompt or change permissions. `inspect` returned the expected unqualified
capability result without opening a dialog.

The first experimental menu probe opened the correct Export Audio/Video dialog,
but cancellation by AXTitle failed because Live exposes the button through an
identifier and description. The supervisor cancelled that dialog. After switching
to the exact `Base.FinalButtonsBox.CancelButton` identifier, the second probe
returned `unavailable` with `export_settings_mismatch` for the MP3 preference,
`owned_dialog: true`, no cleanup error and `writer_closed: false`. It cancelled
and verified disappearance of its own export window. Independent UI inspection
confirmed only the main disposable-set window remained, with playback and recording
stopped, and the requested output WAV was absent. No render, save, preference
change, full-range proof or end-to-end automatic scan occurred. The render candidate
remains disabled and unwired.

An additional owner-supervised UI check opened the native Save panel without
starting a render. Its observed identifiers were `save-panel`,
`saveAsNameTextField`, `where popup`, `CancelButton` and `OKButton`. The native
Go To Folder sheet exposed `GoToWindow` and `PathTextField`. Navigation to a new
private empty directory produced a column-view URL for that exact directory and
retained `kenn-analysis.wav`. Save-panel Cancel returned to Export Audio/Video;
its exact Cancel returned to the main set. Both transport and record remained
stopped, and the directory stayed empty. This maps controls for future helper
work; the helper still cannot press Export or operate the Save panel. No save,
overwrite refusal, render progress or writer closure was qualified.

On 16 Oct the stricter AX reader repeated the supervised probe against the
disposable demo copy. It opened the correct Export dialog, rejected the existing
MP3 setting, cancelled its owned dialog and verified disappearance without a
cleanup error. Independent readback showed only the main set with playback and
both recording modes stopped; the private job directory remained empty. This
qualifies that window's bounded preflight/rejection/cancellation path. It does not
qualify Save, rendering, full-range discovery or Live writer closure.

A later 16 Oct supervised inspection did not establish a keystroke-free AX
action to open Go To Folder: the inspected location popup and Live Navigate menu
did not provide one. Both dialogs were cancelled and independent readback showed
playback and both recording modes stopped. Save was never pressed.

`ExportSaveDestination.validate` is a fixture-qualified, read-only prerequisite
for future Save work. It requires a complete bounded subtree, the exact native
control roles/identifiers, Boolean enabled states, `kenn-analysis.wav` and a typed
file URL on `ColumnView` identifying the exact canonical job directory. It
rechecks output absence, owned metadata, cancellation and directory identity
around those reads. It neither navigates nor changes values or presses buttons,
and it is not called by the executable's export path. The caller must separately
establish newly opened panel ownership; a successful observation grants no later
Save authority or atomic overwrite guarantee. See
[destination/bounds evidence](../../../docs/evidence/KENN_OFFLINE_SCAN_DESTINATION_BOUNDS_2026-10-16.md).

## Request and receipt boundary

Requests use `schema: "kenn.live_export_request.v1"` and these fields:

- `action`: `inspect` or `export`.
- `live_pid`: positive process identifier for Ableton Live.
- `expected_window_title`: exact current main-window title, at most 512 UTF-8 bytes.
- `output_path`: canonical absolute path ending in `kenn-analysis.wav`.
- `render_start`, `render_length`: explicit nonempty bars.beats.sixteenths values;
  ASCII digits with at most 6/2/2 digits respectively, a positive start bar and
  numerically nonzero length. The helper never infers the full arrangement from
  Live's current selection. Titles reject Unicode control/format characters in
  all three request-validation layers.
- `sample_rate`: exactly `48000` Hz.
- `timeout_seconds`: from 1 to 600 seconds.

The backend must create the exclusive parent job directory with mode `0700`. Only
its `manifest.json`, `receipt.json` and optional `cancel.requested` may exist there;
those entries must be owned, single-link regular files of at most 64 KiB each. An existing
output, including a symbolic link, is rejected. The helper neither creates nor
deletes the job directory or its audio. The job service owns cleanup and retention.

Decoded requests always produce a receipt containing schema, requested process,
output, range, sample rate, stereo channel count, status and `writer_closed`.
Malformed/oversized JSON cannot establish those identities and produces a bounded
`invalid_request` protocol error. A receipt's `owned_dialog` only identifies a
newly opened known export dialog; `cleanup_error` reports a failed Cancel action.
Neither implies that a file writer closed. All current export receipts have
`writer_closed: false` and do not authorize publication.

The completion checks prepared for a qualified profile require all four facts:
observed export progress, disappearance of the owned export dialogs, a finalized
owned, single-link stereo 48 kHz/24-bit PCM RIFF file within 150 MiB and eight
minutes, and successful native inspection
showing that Live has no descriptor open for that exact device/inode. Parser and
descriptor evidence carry the same file generation: device, inode, size, mode,
nanosecond mtime and ctime. Ownership and single-link status are required at each
snapshot. Validation checks the opened descriptor and path before and after
parsing; descriptor inspection rechecks that identity before and after its scan.
Replacement, same-size rewrites, restored mtime and link changes invalidate the
evidence. File-size stability and a missing/permission-denied process inspection
do not count. The RIFF check reads chunk headers, not the entire audio file.
Descriptor inspection is bounded to 16384 entries with 32 entries of allocation
headroom; an incomplete snapshot remains unknown. This metadata contract is
fixture-qualified, not proof that a real Live export has completed.
Numeric toggle readback accepts only exact zero or one; fractional or NaN AX
values cannot be rounded into a qualified Off/On preference.

The cancellation path must acquire a newly appearing dialog before reporting
post-menu cancellation, so an immediate cancellation does not skip cleanup.
The caller binds the original main AX window and baseline window set, then
requires exactly one new top-level export dialog. Cleanup rereads the process,
window set and exact Cancel control's identity, role and Boolean enabled state;
an unknown or changed state produces a cleanup error instead of a retained-node
press. No Escape or generic close action is sent. These observations cannot make
AX's separate read and press operations atomic.

## Remaining qualification

The sole work queue remains `products/kenn/KENN_PLAN.md`. The supervised read-only
probe exposed exact Live 12 export identifiers for Main, range and format settings.
The fixed profile rejects mismatched MP3/video values even if a control is disabled;
it never changes a preference. Before this adapter can render, the supervised check
must establish the full arrangement range and tail policy, stereo PCM WAV, 48 kHz,
24-bit, normalization/loop/MP3/video off, a job-only destination, overwrite rejection
and export lifecycle/cancellation. Existing preferences must be verified
rather than silently changed. Writer inspection must also work against the real
Live process. Until then, the job service must show the unavailable reason and
retain any uncertain owned file for recovery rather than publish an analysis.
The failed/truncated AX-read boundary and shared WAV/descriptor generation now
have fixture and mutation coverage. The strict AX profile passed one supervised
preflight/rejection/cancellation check; its node budget and required attributes
may conservatively reject an unfamiliar window. No real render progress or Live
writer closure has been qualified, and these checks do not enable the candidate.

The optional Python `MacOSLiveExportHelper` adapter in backend `core/macos_live_export.py`
accepts a fixed executable path and explicit `enabled` and `supervised_test` flags.
It is not wired into default server startup. Its synchronous `(request, cancel_event)`
call sends at most 16 KiB of JSON without a shell, caps stdout at 64 KiB, propagates
the job cancellation marker and binds every receipt to the exact request. It can
report `writer_closed: true` before launch because it has started no writer; after
launch it requires a matching helper receipt, and timeout/termination/malformed or
foreign output remains unknown. Process termination does not cancel Live's renderer.

```sh
KENN_LIVE_BACKEND=fake /usr/bin/arch -arm64 products/kenn/apps/backend/.venv/bin/python -m pytest -q products/kenn/apps/backend/src/kenn/tests/test_macos_live_export.py
```
