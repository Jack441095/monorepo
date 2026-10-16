# Offline Scan audio destination and arrangement observations, 16 October 2026

This follow-up advances two prerequisites in the disabled Scan audio candidate.
It does not enable automatic export or connect a frontend button.
`KENN_PLAN.md` remains the sole work queue.

## Baseline and supervised observations

- Branch `feature/reference-review-grade`, starting commit `ebf18431`.
- Existing unrelated plan/research changes were preserved and excluded from
  staging; only this checkpoint's plan entry is published.
- The owner selected a disposable copy of the demo set and was available to
  supervise the Export/Save dialog check. Both dialogs were cancelled. Final
  independent UI readback showed the disposable main window, Play 0,
  Arrangement Record 0 and Session Record 0.
- The native Save panel exposed its filename, location popup, column browser,
  Cancel and Save controls. Its location popup offered existing/recent locations;
  the inspected Live Navigate menu did not expose Go To Folder. This did not
  establish an AX action for automatic navigation. No filename or export
  preference was changed, and Save was never pressed.
- AC power was available, battery 22% and charging. No callback/publisher or
  sustained-insert workload ran; this closes no performance gate.

## Destination readback

The native validator is read-only and is not integrated into the helper's export
caller. It checks the supplied Save-panel subtree and job-directory state. It
does not navigate, edit fields, press Save, prove the panel was newly opened by
KENN or authorize a later Save action.

The exact native browser's typed file URL must identify the canonical job parent.
A location label or a child file's URL is insufficient. Unknown or incomplete AX
evidence rejects validation. Filesystem checks bracket the UI reads so a changed
directory, newly appearing output or cancellation cannot qualify the observation.
This proves neither atomic overwrite exclusion nor future writer closure.

## Structural arrangement observation

The new backend reader uses existing bundled AbletonOSC read endpoints and an
injected query boundary. It returns structural clip positions and labels after
matching complete observations. It does not use a cached session snapshot and
does not supply an offline-job source fingerprint.

Missing or malformed responses are failures rather than an empty arrangement.
Track/clip budgets reject oversized inventories instead of truncating them.
Matching repeated reads are not an atomic Live snapshot: clip content, warp,
automation, devices, effects and unsaved source state can change without changing
the returned structure. Beat positions do not establish musical export strings
or an effect-tail policy.

AbletonOSC replies carry no request nonce or source epoch. A delayed datagram
with matching address/index can satisfy a later request. The reader therefore
establishes uncached request-driven structural sampling, not independently
proven freshness. Its deadline rejects late results; it cannot interrupt a
blocked injected transport. The existing transport must bound its own calls.

Budgets are 256 regular tracks, 256 clips per track, 4096 total clips and 512 UTF-8
bytes per label. These bound accepted observations after the transport returns;
they do not cap allocations inside an injected transport. A nonempty read uses
six query batches and `12 + 6 * track_count` individual read requests (1548 at the
track limit). There is no measured latency, CPU or RSS qualification, and the
reader is not attached to a polling loop or audio callback.

## Verification

From `products/kenn/apps/backend`:

```sh
env KENN_LIVE_BACKEND=fake /usr/bin/arch -arm64 .venv/bin/python -m pytest \
  src/kenn/tests/test_arrangement_bounds.py \
  src/kenn/tests/test_ableton_osc_bridge.py \
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

**352 passed in 42.61 seconds.** The new reader's 73 tests also pass independently.
Integration-style fixtures bind the existing bridge `_query_many` seam to a fake
transport and reject any snapshot/cache/mutation fallback. Separate instances
retain independent immutable results and failures never reuse earlier results.

Four temporary-copy Python mutations each failed a regression assertion:
ignoring changed observations, exact track echoes, result deadlines or clip
budgets. Shared source/test hashes were unchanged by mutation checks.

From the repository root:

```sh
products/kenn/apps/desktop/macos/test_live_export_helper.sh
```

**Passed in 2.53 seconds.** Native fixtures cover 24 destination scenarios plus
actual cross-job rejection, healthy recovery, cancellation before AX reads and
read-only directory checks. Seven temporary-copy mutations each failed an
assertion: wrong directory, changed directory generation, omitted final
output/metadata validation, duplicate controls, missing cancellation checks,
missing enabled checks and missing nested-sheet rejection. Source/test hashes
were unchanged. No fixture queries or acts on Live.

Parallel independent review found no blocker within this disabled scope. It
confirmed that neither structural agreement nor destination readback grants
export authority. Scoped whitespace checks pass; the unrelated research README's
existing trailing whitespace remains untouched.

The starting checkpoint's [core run](https://github.com/Nite-DSP/monorepo/actions/runs/38881051364)
and [sharing run](https://github.com/Nite-DSP/monorepo/actions/runs/38881051394)
still failed before execution. Current annotations for all three jobs explicitly
confirm the account payments/spending-limit block. No CI pass is claimed and no
workflow was changed.

## Changed files

- `apps/backend/src/kenn/core/arrangement_bounds.py`: structural reader only.
- `apps/backend/src/kenn/tests/test_arrangement_bounds.py`: reader regression fixtures.
- `apps/desktop/macos/KENNExportAX.swift`: read-only destination verifier.
- `apps/desktop/macos/KENNLiveExportHelperTests.swift`: destination regression fixtures.
- `apps/desktop/macos/LIVE_EXPORT_HELPER.md`: verifier contract and supervised observations.
- `docs/evidence/KENN_OFFLINE_SCAN_DESTINATION_BOUNDS_2026-10-16.md`: this receipt.
- `KENN_PLAN.md`: this checkpoint's entry only.

## Remaining gates

The helper retains both experimental gates, cannot press Export or operate Save,
and returns no completed writer-closed receipt. Automatic destination navigation,
panel ownership, overwrite refusal, actual progress/cancellation/completion and
Live writer closure remain unqualified. Independent full-source identity, export
range/tails and the visible button-to-report flow remain open. The existing
`LocalMixReviewService` remains the analysis path; no DSP, dependency, permission
or CI change is introduced here.
