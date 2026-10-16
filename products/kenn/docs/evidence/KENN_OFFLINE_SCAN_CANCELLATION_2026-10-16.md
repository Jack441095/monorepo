# Offline Scan audio dialog cancellation, 16 October 2026

This checkpoint follows `4177aa08` on `feature/reference-review-grade`. It fixes
the connected native helper's post-menu cancellation path. The helper remains
disabled and unwired; it cannot press Export, operate Save or return a completed
writer-closed receipt. No Live UI action ran during this checkpoint.

## Reproduced failure

The actual `LiveExportAccessibility.run()` fixture first failed with:

```text
Cancellation after the menu press left the newly opened export dialog visible
```

The old loop checked the cancellation marker before identifying the dialog that
the menu command had just opened. Its error path consequently had no owned
dialog to clean up. The native test script reproduced this in 1.98 seconds before
the fix; the fixture checks that the newly opened dialog actually disappears.

## Changed behavior

Each helper instance accepts one request. Before opening the fixed menu command,
the caller records and rechecks the exact original main AX window and complete
baseline window set. Acquisition accepts exactly one new top-level Export
Audio/Video dialog with a complete, unique native Cancel control. Existing,
replaced, ambiguous or incompletely observed windows cannot grant cleanup
authority.

Cancellation after the menu press allows a two-second acquisition grace for the
new dialog. If it cannot be identified, the receipt explicitly reports unresolved
acquisition; a delayed dialog may remain open. Cleanup has its own two-second
acceptance/poll budget and revalidates the Live process, original window set,
dialog and unchanged Cancel control, including its role and Boolean enabled
state. It presses at most once and independently checks disappearance. A changed
or unknown UI state reports a cleanup error without a retained-node press.

These budgets reject late results; they do not interrupt an in-flight AX call.
The production AX messaging timeout remains two seconds. Separate AX reads and
actions cannot establish atomic ownership across a concurrent user/UI change.
Strict baseline-window matching may conservatively refuse an unfamiliar Live
window arrangement. No actual render cancellation or writer closure is claimed.

## Independent remaining-gate audits

A temporary self-owned AppKit Save-panel probe tested Accessibility operations
without Live, keystrokes or file creation. The expanded browser reported that its
AXURL was not settable. Setting an absolute directory or output path through the
filename's AXValue left literal filename text; its advertised AXConfirm action
did not navigate or submit Save. The location remained the starting directory,
no Go To Folder sheet appeared and both starting/job directories stayed empty.
The browser URL read was unavailable, so this is not successful URL readback.
Both probe applications exited and their exact temporary directories were
removed. Generic AppKit behavior does not qualify Live's Save panel and supplies
no navigation implementation.

The source audit found reusable nonce-attributed parameter reads in the existing
bridge, but their handler epoch is not independently verified document identity.
Standard arrangement replies still lack nonce attribution. A future structural
observer can bind current Song/track/clip objects and reject replacements; it
must remain distinct from the offline job's full-source fingerprint. No inspected
API supplies a complete revision covering arrangement automation, MIDI/warp,
sample contents and arbitrary plug-in state. Structural agreement and a rendered
WAV hash cannot prove that Live's current mix remains unchanged. Exact export
range conversion and an explicit producer-confirmed tail policy remain open.

## Verification

From `products/kenn/apps/backend`:

```sh
env KENN_LIVE_BACKEND=fake /usr/bin/arch -arm64 .venv/bin/python -m pytest -q \
  src/kenn/tests/test_macos_live_export.py
```

**33 passed in 3.16 seconds.** The adapter's receipt, cancellation and unavailable
outcomes retain their existing protocol. No backend code changed.

Re-run at the start of the next session (committed as `b514adb1`): the same pytest
command passed again (33 passed in 3.18 seconds), and
`apps/desktop/macos/test_live_export_helper.sh` printed all seven PASS lines,
including "40 actual caller lifecycle scenarios" and the malformed-request check, in
about 3.3 seconds. The pre-fix 1.98 second reproduction above was not repeated,
because the new fixtures depend on the injected clock the fix introduced.

AC power was available, battery 31% and charging; load averages were
3.68/3.06/4.37. No callback/publisher or sustained 64-insert workload ran. This
closes no mains performance gate. The helper operates outside the audio callback;
this checkpoint adds no DSP or HTTP publication work.

The starting checkpoint's [core run](https://github.com/Nite-DSP/monorepo/actions/runs/38882897479)
and [sharing run](https://github.com/Nite-DSP/monorepo/actions/runs/38882897465)
failed before execution. The current core annotation still explicitly reports
failed account payments/spending limits. No CI pass is claimed and no workflow
was changed.

## Changed files and remaining work

- `apps/desktop/macos/KENNLiveExportHelper.swift`: actual caller acquisition and cleanup.
- `apps/desktop/macos/KENNLiveExportHelperTests.swift`: actual caller regression fixtures.
- `apps/desktop/macos/LIVE_EXPORT_HELPER.md`: cancellation contract and limits.
- `docs/evidence/KENN_OFFLINE_SCAN_CANCELLATION_2026-10-16.md`: this receipt.
- `KENN_PLAN.md`: this checkpoint's entry only.

Automatic Scan audio remains blocked on job-only destination navigation, newly
opened Save-panel ownership, overwrite exclusion, actual render
progress/completion/cancellation and Live writer closure. Full-source
identity/range/tails and the visible export/analysis/cancel/failure flow are also
unqualified. `KENN_PLAN.md` remains the sole work queue. The existing
`LocalMixReviewService` remains the analysis path; this checkpoint adds no DSP,
dependency or permission.
