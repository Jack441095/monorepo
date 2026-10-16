# Offline Scan audio completion boundary, 16 October 2026

This checkpoint closes two prerequisite gaps in the existing disabled macOS
export helper and repeats its supervised Export-dialog probe. It does not
implement a one-click Scan audio renderer, operate a Save panel or enable the
candidate. `KENN_PLAN.md` remains the sole work queue.

## Baseline and conditions

- Branch: `feature/reference-review-grade`; starting commit `0f9c24db`.
- The working tree already contained unrelated plan/research changes. They are
  preserved and excluded from this checkpoint; only the new plan evidence entry
  is staged.
- Local macOS/arm64 verification used the existing Swift toolchain and backend
  virtual environment, with `KENN_LIVE_BACKEND=fake` for Python tests.
- Power observations: AC power, battery 10%, 15% then 19%, charging. No callback,
  publisher or sustained-insert benchmark ran, so no mains timing gate closes.
- The owner was available for a supervised disposable-set check. Initial UI
  inspection showed an empty `Untitled` window. After the owner opened the
  disposable demo copy, its expected window and stopped playback/recording were
  independently verified before the helper probe. No audio was rendered.

## Reproduced failures and changes

Before fixing each boundary, the Swift regression script failed with:

```text
FAIL: A failed AX window read was treated as an empty list
FAIL: A replaced WAV reused another file's validation evidence
```

`KENNExportAX.swift` now owns the bounded AX read contract. Only explicit
`attributeUnsupported` or `noValue` responses may represent optional absence.
Messaging failures, missing required values, malformed types, changed array
counts, exceeded deadlines and incomplete trees reject the request. Each array
element must have the AXUIElement CF type; Swift's array cast alone accepted a
numeric fixture. Arrays request one bounded extra slot to detect growth. Tree
traversal shares a 2048-node budget including all roots and verifies that nodes at
the limit are leaves. It never returns a truncated prefix as a complete tree.

The export caller uses these throwing reads. Injected process, AX and press
boundaries exercise the real orchestration without acting on Live. Every
incomplete-preflight fixture records zero presses; a positive control reaches
the action spy exactly once. Cancellation readback also rejects incomplete
window evidence. The executable still uses native boundaries and cannot select
fixture behavior through a request.

WAV validation returns a file-generation identity containing device, inode,
size, mode, nanosecond mtime and ctime. Every snapshot requires current-user
ownership, one link and a regular file. Validation compares the no-follow opened
descriptor and path before/after parsing. Descriptor inspection checks the same
identity before/after its bounded process scan. Completion accepts only matching
parser and descriptor identities plus observed progress, disappearance of owned
dialogs and proven descriptor closure. Unknown evidence remains unknown.

Fixtures cover replacement, same-size PCM rewrites, restored mtime, hard links,
missing/symlink paths, changes during parsing/inspection, fresh-reader isolation,
the complete completion truth table and actual open/closed descriptors in the
test process. This is not qualification of descriptor inspection against Live.

The AX absence/error contract follows Apple's
[attribute-value API](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue)
and [bounded-array API](https://developer.apple.com/documentation/applicationservices/1462060-axuielementcopyattributevalues).

## Verification

From the repository root:

```sh
products/kenn/apps/desktop/macos/test_live_export_helper.sh
```

Passed all Swift fixture groups and the malformed executable-request check.
Both native build scripts compile the extracted AX source. A parallel read-only
review found the numeric-array casting gap; the final review reported no remaining
concrete blocker for this disabled checkpoint.

From `products/kenn/apps/backend`:

```sh
env KENN_LIVE_BACKEND=fake /usr/bin/arch -arm64 .venv/bin/python -m pytest \
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

**254 passed in 7.70 seconds.** No Python source changed in this checkpoint.

Eight mutations were applied to temporary native source copies. Each compiled
and then failed a regression assertion: failed-read-as-empty, missing CF element
type check, prefix tree truncation, ignored deadline, mismatched completion
identity, omitted descriptor path rechecks, omitted final parser rechecks and
ignored ctime. Working-source hashes were unchanged after the mutation run.

The baseline's [core run](https://github.com/Nite-DSP/monorepo/actions/runs/38760565646)
and [sharing run](https://github.com/Nite-DSP/monorepo/actions/runs/38760565608)
both failed before execution. Current check annotations confirm failed account
payments or spending limits. The annotations also mention runner capacity, but
that does not remove the billing block. No CI pass is claimed.

## Supervised Export-dialog probe

The updated native executable ran once with both experimental gates on, an exact
Live PID/window binding, a fresh canonical mode-0700 directory and a 15-second
request deadline. The explicit one-bar request range was only a probe input;
it does not establish a full arrangement range. The helper opened Export
Audio/Video, read the existing profile and returned:

```json
{
  "status": "unavailable",
  "error_code": "export_settings_mismatch",
  "owned_dialog": true,
  "writer_closed": false
}
```

The mismatch was `Base.EncodeMp3Box.EncodeMp3`. The helper did not change it.
Its exact Cancel action and disappearance readback succeeded with no cleanup
error. Independent UI readback then showed only the main set window, Play 0,
Arrangement Record 0 and Session Record 0. The fresh job directory remained empty
and was removed after inspection. No Export-button press, Save-panel operation,
file creation or real Live descriptor inspection occurred. This qualifies this
Live window's bounded AX preflight and existing rejection/cancellation path, not
the full export lifecycle or arbitrary Live window layouts.

## Performance and remaining qualification

This adds bounded AX reads, file metadata checks and test seams off the audio
callback. Header parsing still skips PCM payloads; it does not load the full WAV.
The process scan caps evidence at 16384 descriptors, with 32 entries of allocation
headroom. No measured CPU/RSS or callback performance claim follows from these
structural bounds. DSP and HTTP publication cadence are unchanged.

The helper remains gated by both the experimental environment flag and supervised
argument. It can only probe and cancel its own Export dialog; every export receipt
still has `writer_closed: false`. Save-panel automation, job-only destination and
overwrite refusal, actual progress/cancellation, real Live writer closure, fresh
whole-arrangement identity/range and effect-tail policy remain unqualified. The
runtime/API/frontend path remains unwired. Native loudness promotion and E1
callback/publisher gates are separate and unchanged.

Files changed: `KENNExportAX.swift`, `KENNLiveExportHelper.swift`,
`KENNLiveExportHelperTests.swift`, both native helper build/test scripts,
`LIVE_EXPORT_HELPER.md`, this evidence file and the owned `KENN_PLAN.md` entry.
