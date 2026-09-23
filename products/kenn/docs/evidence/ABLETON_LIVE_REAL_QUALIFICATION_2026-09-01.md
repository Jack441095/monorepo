# Ableton Live real qualification — 2026-09-01

Status: **passed for the qualified read-only, track/transport, and EQ Eight/Compressor/Utility device-parameter subset**.
This is an internal disposable-set evidence record, not a full Ableton beta
approval.

## Environment

- Ableton Live 12 Suite 12.4.5, running locally through `KENN_Bridge`
- macOS 26.5.2, arm64
- Support matrix ID: `live-12.4.5-macos-26.5.2-arm64`
- OSC endpoint `127.0.0.1:11000`
- Real snapshot `session_version`: `101f69a00aa0db9f8fca8517a9aa338bd25551a9dd44859309f027d6f9666b07`
- Snapshot read-only probe: passed, latest runtime 54.27 ms
- Snapshot contained 2 MIDI tracks, 2 audio tracks, 2 return tracks, 1 master track, 8 scenes, tempo 120 BPM, and stopped transport

## Qualified operations

Each operation used `LiveActionService`: fresh snapshot, exact track identity,
proposal, single-use confirmation, write, readback, receipt, replay rejection,
and a fresh confirmed inverse. Original values were restored and verified.

| Operation | Target | Before → requested | Write receipt | Inverse receipt | Result |
|---|---|---:|---|---|---|
| Volume | `1-MIDI` / track 0 | `0.85000002 → 0.75` | `receipt-d83575a2a74d4d0d97d2d49dac7498a5` | `receipt-fb7f7078e14d4f64834f09d9fb7f232a` | passed |
| Pan | `1-MIDI` / track 0 | `0.0 → 0.2` | `receipt-aac6de7caed04fd8bd64068b95309010` | `receipt-69631bb118b44f04858ec83b04c0b90d` | passed |
| Mute | `1-MIDI` / track 0 | `false → true` | `receipt-d426229ccac44323abf9e654b54a82a4` | `receipt-9366e5e078074e519959039e84c2edfe` | passed |
| Solo | `1-MIDI` / track 0 | `false → true` | `receipt-f920b5e1156c42769b865579905181ff` | `receipt-863a94fab8484e2c8f50b0547e53e380` | passed |
| Arm | `1-MIDI` / track 0 | `false → true` | `receipt-2bee762d30ec4e4bb1740e637a984112` | `receipt-3f743db4219c4c16ae191aed04337cf0` | passed |
| Transport play | Live transport | `false → true` | `receipt-7ee3743e45d84ba69640c5b4259b0fb3` | `receipt-bd2240241d1948b99fbdfa3613debdc9` | passed |
| Transport stop | Live transport | `true → false` | `receipt-2c5b01d26e7b43aa8b7fbd3532f10a18` | `receipt-0e8d9e916f114113929fe6eba93fc1b6` | passed |

Every listed receipt reported `verified: true` and `status: applied`. Replay
of each original idempotency key was rejected. The final transport state was
stopped and the final track values matched their starting values.

The telemetry-enabled repeat for volume (`0.85000002 → 0.74 → 0.85000002`)
also matched every request ID to its response ID:

- Proposal snapshot: request/response `2/2`, 101.198 ms
- Write receipt `receipt-786afc48d1e240399085f4646147a322`: request/response
  `4/4`, 98.005 ms
- Write readback: request/response `5/5`, 102.260 ms
- Undo receipt `receipt-5f6bf09891f94a63b5890ce2a27766e4`: write request/response
  `8/8`, 96.996 ms; readback `9/9`, 102.019 ms

## HTTP route qualification

The temporary KENN server was run with DAW control explicitly enabled and the
real `/api/ableton/osc/volume` alias was exercised against the same Live set.
The route returned a proposal (`200`), a confirmed verified write (`200`),
rejected the exact replay (`409`), returned an undo proposal (`200`), and
completed the confirmed undo (`200`). The route-level write receipt was
`receipt-e69c45b633ef4eaab9d5c735effeda83`; its OSC write exchange was
request/response `15/15` at 97.437 ms and readback was `16/16` at 102.600 ms.
The undo receipt was `receipt-6d9cbd7d55474c84a3e13cf0b54a9047`; its exchanges
were `19/19` at 97.437 ms and `20/20` at 102.654 ms. The server was stopped
cleanly after the test. HTTP request IDs, in order, were
`2b0d4ed5707e`, `be94f87df452`, `7d4b1f9aeea1`, `008b2f28bf7a`, and
`b81a0b883cc4`.

## Device-parameter qualification

The initial guarded device run was exercised against the native EQ Eight
inserted on disposable track `1-MIDI` (track index 0, device index 0). It resolved the
unique Live-returned `Output` parameter (parameter index 1, range -12 to +12)
and completed the full KENN flow:

| Parameter | Before → requested | Write readback | Replay | KENN inverse readback | Result |
|---|---:|---:|---|---:|---|
| EQ Eight / Output | `0.0 → -1.0 dB` | `-1.0` | rejected | `0.0` | passed |
| Compressor / Threshold | `0.85000002 → 0.75` (Live device value) | `0.75` | rejected | `0.85000002` | passed |
| Compressor / Ratio | `0.5 → 0.6` (Live device value) | `0.60000002` | rejected | `0.5` | passed |

The write receipt was `receipt-6dd02f52331d4011a9e6f9f76c57c649` and the fresh
inverse receipt was `receipt-0a359eb4ec8a404f90c472c3e2ec1a64`. Both reported
verified readback. That initial final query reported EQ Eight present and
Output at `0.0 dB`.

The Compressor qualification used the exact Live-returned `Threshold`
parameter (index 1, range 0 to 1) with write receipt
`receipt-7beec17dc8324962870862d1f024ffae` and inverse receipt
`receipt-176b954fdcde4a8a94e4adf280b260c6`; both reported verified readback.
The final Threshold readback matched its original `0.85000002` value.

The additional Compressor `Ratio` qualification resolved parameter index 2
(range 0 to 1), passed verified write/replay/inverse checks, and restored its
original `0.5` value.

Follow-up qualification on the connected disposable set resolved three native
device families by exact Live-returned names: EQ Eight `Output` (device index
1) `0.0 → -1.0 → 0.0`, EQ Eight `1 Gain A` (device index 1) `0.0 → 1.0 →
0.0`, Compressor `Output` (device index 0) `0.0 → 1.0 → 0.0`, and Utility
`Stereo Width` (device index 2) `1.0 → 0.8 → 1.0`. Each write had verified
readback, exact replay rejection, and a fresh verified inverse. The follow-up
snapshot hash was
`42094bb953ca5c6cc780f96d86e85ef3b1a1f31fb2f24bd9d341ea7702c98bd4`; it
showed Compressor, EQ Eight, and Utility on `1-MIDI`, with transport stopped.

Follow-up receipt pairs were EQ Eight `Output`
(`receipt-0587d3865f214aa187690601239fa073` /
`receipt-e63a1b2cc1df4fe38ebbb252cbf4993c`), EQ Eight `1 Gain A`
(`receipt-7f412fe2c4a14f67967c279cfed6b4b4` /
`receipt-149364f61a1f402f8c5619f2f674f1e6`), Compressor `Output`
(`receipt-1ff1bfb8be76418bb17a86ff16cbd5ae` /
`receipt-2fc00005ee7e433184cf71ae739cb81d`), and Utility `Stereo Width`
(`receipt-877725082ce1400b983a19097e16abe1` /
`receipt-9a443e2997fc4ea0a48594d5da0fdd32`).

Native Live Edit Undo was tested separately: a guarded KENN write moved the
same Output parameter from `0.0` to `2.0 dB`, then Live's own Cmd-Z restored the
real parameter to `0.0 dB` while EQ Eight remained present. This is separate
evidence from KENN's receipt inverse.

A companion-restart boundary probe created a real proposal for `0.0 → 3.0 dB`
in one process and attempted confirmation in a fresh process. The fresh
process rejected the process-bound token with no receipt and no Live write.

A real timeout/loss probe held a Compressor `Ratio` proposal at `0.5 → 0.6`,
terminated Live before confirmation, and then attempted the pending action.
KENN returned a failure receipt with `verified: false` and no readback; it did
not return a success-shaped mutation result. Live subsequently presented its
native crash-recovery dialog. This proves failure classification and no
overclaim after Live loss, but not retained-state restoration after recovery.

A second, saved-state retention probe used the disposable set saved as
`/Volumes/Jack_Gandy_1TB_SSD/Ableton Projects/2026/KENN-live-retention-20260901/KENN_retention_test Project/KENN_retention_test.als`
with Compressor, EQ Eight, and Utility present and their qualified values
restored. The exact Live process was then terminated, and Live reopened with
the recovery prompt for that set. A subsequent application poll showed the
normal saved `KENN_retention_test` window, with no recovery-button action made
by KENN. The bridge reconnected and returned the same snapshot hash
`42094bb953ca5c6cc780f96d86e85ef3b1a1f31fb2f24bd9d341ea7702c98bd4`, with
Compressor, EQ Eight, and Utility still present and all tested values restored.
Saved-set retained-state recovery therefore passed for this Live/OS/set.

## Safety checks

- A proposal became stale after an external value change and was rejected with
  `Live track state changed since the proposal was created`.
- The test cleanup restored track 0 volume to `0.85000002` and verified it.
- Unknown track index `999` was refused before any write.
- A setup-only attempt to insert `EQ Eight` through the available Live bridge
  returned `Device creation not supported on track object`; no unsupported
  device-creation result was treated as qualification evidence.
- The managed User Library copy of `KENN_Bridge` was refreshed from the
  repository after this qualification attempt; its bridge-level guards now
  reject direct clip, scene, tempo, device-creation, and sidechain mutations.
  The guard takes effect on the next Live launch/control-surface load.
- The copied template `/tmp/KENN-qualification-Late-2021.als` was passed to
  Live after a controlled restart, but Live stopped at its crash-recovery
  modal before `KENN_Bridge` bound UDP 11000. The generated recovery artifacts
  were moved, recoverably, to `/tmp/KENN-live-crash-recovery-20260901-221759`.
- The initial disposable set exposed no device, so a native EQ Eight was
  inserted through Live's own browser UI before the device qualification. No
  device was created through the bridge. Native Live Edit Undo passed for the
  the tested device-parameter subset; saved-set process-crash recovery passed
  in the later probe below, while wider recovery scenarios remain open.
  A manual stale-parameter change between proposal and confirmation was
  rejected correctly. The
  earlier UI-control backend could not access the crash-recovery window
  (`cgWindowNotFound`).
- Latest unsaved-set crash probe: the exact Live process was terminated while the
  disposable set was active, then relaunched. At capture time Live presented
  its native crash-recovery dialog and did not bind `KENN_Bridge`; the device
  runner returned a non-mutating blocked result. Live has since returned to a
  normal window with the bridge connected, but the recovered `Untitled` set
  contains no device, so that earlier unsaved-set probe did not establish
  restoration. The later saved-set probe above did establish retained-state
  recovery for the named disposable `.als`.

The repeatable runner `python3 scripts/qualify_ableton_live_mutations.py`
passed all 7 operations (volume, pan, mute, solo, arm, transport play, and
transport stop) with verified write/inverse receipts, replay rejection, and
restored values. It also refused an unknown track. The runner is the preferred command for
repeating this evidence on another supported Live/OS configuration.

The device runner is `python3 scripts/qualify_ableton_live_device.py`; it
requires explicit `--track-index`, `--device-index`, `--parameter-name`, and
`--value` arguments, resolves the named parameter from Live, and never creates
a device. It is proposal-only by default; `--apply` is required for the
reversible qualification write. The initial no-device run returned
`status: blocked` and performed no mutation; after the native EQ Eight was
inserted through the UI, the `Output` qualification above returned
`status: passed`.

For a calibration candidate, repeat `--value` between 2 and 20 times. The
runner processes each point as a separate confirmed write/readback/inverse
lifecycle, verifies both raw and displayed restoration, and pauses between
points to respect the supervised HTTP rate limit. It stops at the first failed
restore and emits reviewable raw/display pairs, but deliberately does not add
or promote a `DeviceUnitProfile`; mapping shape and Live-version evidence still
require human review.

## Fresh current-runtime rerun — 2026-09-02

The current Live process was confirmed running with `KENN_Bridge` bound to
`127.0.0.1:11000`. A fresh read-only snapshot returned session version
`101f69a00aa0db9f8fca8517a9aa338bd25551a9dd44859309f027d6f9666b07` and
reported transport stopped with target track `1-MIDI` at index 0.

The repeatable mutation runner then passed all seven supported operations on
that real runtime: volume, pan, mute, solo, arm, independent transport play,
and independent transport stop. Each operation had verified write/readback,
exact replay rejection, and a fresh inverse restoration. The final transport
state was stopped and the track values were restored to their starting
values. Unknown track index `999` was refused before any write.

This rerun is current-runtime evidence for the already documented supported
subset. It does not add device-parameter or crash/restart evidence; the
device evidence above remains tied to the explicitly described disposable set.

## AbletonOSC follow-up qualification — 2026-09-03

### Bounded recipe proposal-only check

The repeatable runner `scripts/qualify_ableton_live_recipe.py` was exercised
against the connected current runtime in its default proposal-only mode. It
resolved `4-Audio` pan (`0.0 -> 0.1`) and the exact `EQ Eight` device 1,
`1 Gain A` parameter index 7 (`0.0 -> -1.0 dB`) as one two-step recipe and
returned `kenn.ableton_recipe_proposal.v1` with `step_count: 2` and
`changed: false`. No Live write was sent. This is proposal evidence only;
real multi-step apply, replay rejection, inverse recipe, and restoration remain
the next supervised qualification item.

The first apply attempt was intentionally not counted as passed evidence. Both
steps applied and verified and the exact replay was rejected, but the inverse
recipe request was rejected by the shared undo dispatcher before the
recipe-specific branch. KENN restored `4-Audio` through a fresh, exact
confirmation-bound recovery recipe (`pan: 0.1 -> 0.0`, `1 Gain A: -1.0 ->
0.0 dB`), and a follow-up undo-proposal check now returns a fresh two-step
recipe with `changed: false`. The dispatcher fix is covered by regression
tests; a clean apply/replay/inverse/restoration run remains required before
real multi-step qualification can be marked passed.

After that fix, a clean rerun on the same disposable set passed the complete
two-step lifecycle. `4-Audio` pan changed `0.0 -> 0.1` and the exact
`EQ Eight` device 1, `1 Gain A` parameter index 7 changed `0.0 -> -1.0 dB`;
both writes returned verified readback, the exact recipe replay was rejected,
the fresh inverse recipe returned a verified receipt, and final readback
restored both values to `0.0`. This qualifies only this bounded recipe shape;
it does not qualify arbitrary multi-step or autonomous editing.

The active route is now the pinned vendored `AbletonOSC` Remote Script rather
than the historical `KENN_Bridge` route. KENN was run with DAW control
explicitly enabled, and the live companion reported healthy on
`127.0.0.1:8090`; AbletonOSC was connected on OSC port `11000` with replies on
`11001`.

### Compound EQ lifecycle

Target: `4-Audio` / `EQ Eight` / band `1A`, with Live-returned parameter
indices `1 Frequency A` and `1 Gain A`.

| Operation | Result |
|---|---|
| Confirmation-only proposal | Passed; `20.2088 Hz / 0 dB → 300 Hz / -3 dB` |
| Confirmed write and two-parameter readback | Passed |
| Exact replay | Rejected |
| Identity-bound undo and final readback | Passed; original values restored |

### Device insertion lifecycle

Target: disposable `3-Audio`, initially with no devices. The vendored
AbletonOSC browser lookup was updated to walk nested folders and select the
exact Live track before loading the allow-listed native device.

| Operation | Result |
|---|---|
| Confirmation-only `add EQ on track 3` proposal | Passed; no pre-confirmation change |
| Confirmed insertion and device identity/readback | Passed; `[] → [EQ Eight]` |
| Exact replay | Rejected |
| Identity-bound undo and final readback | Passed; `[EQ Eight] → []` |

The retained current session state is `4-Audio -> [EQ Eight]`; the disposable
qualification track `3-Audio` is clean. This closes the first real insertion
and compound-EQ lifecycle gates. It does not qualify every Ableton device,
every Live/OS version, the hosted rebuilt plug-in UI after the latest install,
or independent human review.

### Additional EQ Q qualification — 2026-09-03

The exact Live-returned parameter `1 Q A` on `4-Audio -> EQ Eight` was
qualified separately using the same KENN companion path. Parameter index `8`
was inspected with range `[0, 1]`; the temporary change
`0.37666621804237366 -> 0.45` passed verified readback, exact replay
rejection, and identity-bound inverse restoration to
`0.37666621804237366`.

### Additional EQ B-side gain qualification — 2026-09-03

The exact Live-returned parameter `1 Gain B` on `4-Audio -> EQ Eight` was
qualified through the same guarded companion route. Parameter index `12` was
inspected with range `[-15, 15]`; the disposable change `0.0 -> -1.0 dB`
passed verified Live readback, exact replay rejection, and identity-bound
inverse restoration to `0.0 dB`.

### Natural-language absolute compound EQ qualification — 2026-09-03

After restarting KENN to load the current parser module, the real command
`set EQ Eight band 1A frequency to 300 Hz and gain to -3 dB on track 4` was
resolved through the live command gateway. The proposal identified
`4-Audio -> EQ Eight -> 1A`, with `20.208775935691037 Hz / 0 dB` before and
`300 Hz / -3 dB` after. Confirmation applied the two writes and returned
`Live change applied and verified`; the final read-only parameter probe
confirmed the original normalized frequency `0.0914127379655838` and gain
`0.0` were restored. The proposal-only stage reported `changed=false`.

### Read-only user-command matrix — 2026-09-03

Against the retained current session, the command gateway returned 84
readable parameters for `show parameters for EQ Eight on track 4`. The
duplicate request `add EQ on track 4` was refused because `4-Audio` already
contains an EQ Eight, with `changed=false`. The underspecified
`reduce amplitude by 3 dB at 250 Hz on track 4` clarified that no band is
tuned to 250 Hz and did not write. The exact request
`reduce amplitude by 3 dB at 200 Hz on track 4 band 1B` produced a precise
confirmation-only proposal for `4-Audio -> EQ Eight -> 1B -> 1 Gain B`,
`0 dB -> -3 dB`, also with `changed=false`.

The retained session's duplicate-device safety was also checked read-only:
both `set EQ Eight 1 Gain A to -3 dB on track 1` and the exact-band form
`reduce amplitude by 3 dB at 200 Hz on track 1 band 1B` were refused because
`1-MIDI` contains two EQ Eight devices. Both returned `changed=false` and no
write was sent.

The follow-up explicit-device check then used
`set EQ Eight device 3 1 Gain A to -3 dB on track 1`. KENN interpreted the
device number as the one-based position in the full chain, resolved
`1-MIDI -> EQ Eight` at Live device index `2`, and returned a confirmation-only
proposal from `0 dB` to `-3 dB`. The response named the exact device and
reported `changed=false`; no Live mutation was sent.

### Native candidate matrix first-control pass — 2026-09-05

The disposable Live set was expanded through the confirmation-bound insertion
path and the exact Live parameter endpoint. Each parameter test used the
proposal-only qualification runner first, then an explicit `--apply` run with
verified readback, exact replay rejection, and identity-bound inverse restore:

| Device | Live target | Temporary value | Restored value | Result |
|---|---|---:|---:|---|
| Glue Compressor | `4-Audio -> device 1 -> Threshold` | `0 -> -6` | `0` | Passed |
| Saturator | `4-Audio -> device 2 -> Drive` | `0.5 -> 0.65` | `0.5` | Passed |
| Auto Filter | `3-Audio -> device 0 -> Resonance` | `0 -> 0.25` | `0` | Passed |
| Drum Buss | `3-Audio -> device 1 -> Drive` | `0.2 -> 0.35` | `0.2` | Passed |

During the first Saturator insertion, Live performed the browser mutation but
the extension acknowledgment was lost. KENN did not retry; a fresh topology
readback proved that Saturator was present, and the insertion executor now
reconciles this condition before returning a final status. The installed
AbletonOSC browser handler was also tightened to select only loadable leaves
and log load exceptions.

### Glue Compressor display-unit boundary — 2026-09-05

The bulk AbletonOSC parameter inventory reports raw values and ranges, which
are not always the same units shown by Live. A targeted
`/live/device/get/parameter/value_string` probe reported the current Glue
display values as follows:

| Parameter | Raw value | Live display | Probe result |
|---|---:|---:|---|
| Attack | `3.0` | `1` | display mapping confirmed |
| Ratio | `1.0` | `4` | display mapping confirmed |

Two decimal qualification attempts (`Attack 3.0 -> 3.5` and `Ratio 1.0 ->
1.25`) were rejected by Live readback and left the set unchanged. A discrete
raw-step qualification (`Attack 3.0 -> 4.0 -> 3.0`) passed write readback,
exact replay rejection, and identity-bound inverse restoration. This is not a
failure of KENN's safety boundary; it is evidence that Glue's display-unit
conversion must be modeled before KENN accepts user-facing millisecond or ratio
commands for those controls.

### Evidence-backed percent mappings — 2026-09-05

Two additional reversible qualifications proved simple linear display mappings
for the exact parameters below. The mappings are enabled only for these device
and parameter identities; no general Live unit conversion is inferred.

| Parameter | Raw qualification | Live display qualification | Result |
|---|---|---|---|
| Auto Filter / Resonance | `0 -> 0.25 -> 0` | `0.0% -> 25% -> 0.0%` | Passed |
| Drum Buss / Drive | `0.2 -> 0.35 -> 0.2` | `20% -> 35% -> 20%` | Passed |

The command layer now converts `25%` Resonance to raw `0.25` and a relative
`5%` Drum Buss Drive change to raw delta `0.05` before creating the normal
confirmation-bound proposal. Glue Attack/Ratio, Saturator display units, and
all other unqualified units remain raw-only or clarification-gated.

## Evidence boundary

The report contains receipt identifiers and measured outcomes only; confirmation
tokens are not persisted. This record proves the qualified subset on this
specific Live/OS/set state. It does not prove broader device-parameter
coverage, recovery of unsaved sessions, cross-version crash behavior,
long-term reliability, or human usefulness.
