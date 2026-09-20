# KENN AbletonOSC Route

Status: **active qualification route — 2026-09-05**

KENN now uses the standard OSC protocol provided by the open-source
`AbletonOSC` Remote Script. The KENN companion remains the local safety layer:
it owns intent parsing, exact target selection, proposal display, explicit
confirmation, stale-state checks, readback verification, receipts, undo, and
replay rejection. AbletonOSC owns the Live object-model transport.

## Why this route

The previous `KENN_Bridge` path combined a private JSON-over-UDP protocol with
a custom Live Remote Script. That created two implementations of the same
transport and made reload failures difficult to distinguish from command
failures. Standard AbletonOSC gives KENN a known OSC wire format and a
maintained Live-side object-model adapter while preserving KENN's guarded write
boundary above it.

The upstream source is [AbletonOSC](https://github.com/ideoforms/AbletonOSC).
KENN's current installation uses the upstream `insert_device` extension from
[PR #173](https://github.com/ideoforms/AbletonOSC/pull/173), pinned locally to
commit `88b0847`. The extension is required for the confirmation-only “add EQ
Eight” pilot; read-only state and existing device parameters use the standard
AbletonOSC endpoints.

## Current verified state

- Ableton Live 12 Suite 12.4.5 is running.
- `AbletonOSC` is selected in Live's Control Surfaces settings.
- Live reports OSC listening on `127.0.0.1:11000` with response port `11001`.
- KENN reads the live track list, device list, transport, tempo, and track
  controls through standard OSC.
- The read-only `GET /api/ableton/capabilities` route now reports the explicit
  AbletonOSC read/write endpoint contract, current liveness, and the KENN
  write boundary (`LiveActionService`, confirmation, readback, and replay
  rejection). A timeout is not treated as an inferred capability.
- The local companion now exposes a read-only, index-bound parameter probe at
  `/api/ableton/osc/device-parameters?track_index=N&device_index=M`; it reuses
  the companion's single AbletonOSC reply socket so qualification tools do
  not compete with the running server.
- The companion also exposes a targeted UI-value probe at
  `/api/ableton/osc/device-parameter-value-string?track_index=N&device_index=M&parameter_index=P`.
  This reads Ableton's displayed value string without adding one request per
  parameter to the bulk matrix.
- `GET /api/ableton/device-matrix` now combines the topology and exact
  parameter probes into a read-only inventory. Each observed device is marked
  `qualified`, `candidate`, or `unqualified`; those labels never grant write
  permission, and missing candidate families are reported explicitly.
- Verified and failed Live receipts are now projected into a bounded local,
  non-secret journal and can be inspected read-only at
  `/api/ableton/receipts?session_id=...&limit=...`. Confirmation tokens and
  signing metadata remain process-bound and are never journaled.
- `add eq on track 4` creates an exact confirmation proposal and performs no
  mutation before confirmation.
- Native insertion is now allowlisted for `EQ Eight`, `Glue Compressor`,
  `Saturator`, `Auto Filter`, and `Drum Buss`; all insertions remain append-only
  and confirmation-bound.
- A fresh confirmed `add EQ on track 4` request has now inserted one native
  `EQ Eight` on `4-Audio` and verified the post-insert device list through
  AbletonOSC. The Remote Script insertion handler now searches nested browser
  folders and selects the exact target track before calling `load_item`.
- A fresh confirmed `add Glue Compressor on track 4` request appended Glue
  after `EQ Eight` and verified the resulting device list. Its `Threshold`
  parameter passed a reversible real-Live qualification (0 -> -6 -> 0),
  including readback and exact replay rejection; the family remains a
  candidate until broader coverage and review are complete.
- The first native candidate pass now also covers `Saturator -> Drive`
  (0.5 -> 0.65 -> 0), `Auto Filter -> Resonance` (0 -> 0.25 -> 0), and
  `Drum Buss -> Drive` (0.2 -> 0.35 -> 0), each with verified readback,
  replay rejection, and inverse restoration.
- The rebuilt C++ command client receives a real bounded Live response from the
  local companion; command planning now allows 15 seconds and confirmation
  allows 30 seconds for the guarded real-Live round trip.
- Real insertion lifecycle qualification is complete: a disposable
  `3-Audio` request inserted `EQ Eight`, verified identity and ordering,
  rejected an exact replay, and completed identity-bound undo back to an
  empty device list. The separately retained `EQ Eight` on `4-Audio` is the
  live parameter-inspection and compound-EQ target.
- An explicit compound command is now proposal-ready: `retune EQ Eight band
  1A to 300 Hz and reduce gain by 3 dB on track 4` reports the exact band,
  frequency before/after, and gain before/after. It performs no write until
  confirmation, then writes both parameters and verifies both by readback.
- The compiled C++ plug-in command client has now requested that compound
  proposal from the live server and verified the exact `4-Audio`, `EQ Eight`,
  `1A`, `1 Frequency A`, and `1 Gain A` identities. The real qualification
  then applied both values, verified both readbacks, rejected an exact replay,
  and restored the original values through identity-bound undo.
- Read-only parameter inspection is now live: `show parameters for EQ Eight on
  track 4` returned 84 readable parameters from `4-Audio`, including the
  original sparse indices and Live's normalized frequency values.
- Additional real EQ coverage is qualified: `4-Audio -> EQ Eight -> 1 Q A`
  (Live parameter index 8) temporarily changed from `0.37666621804237366` to
  `0.45`, passed readback and replay rejection, and restored its original
  value through identity-bound undo.
- B-side EQ coverage is also qualified: `4-Audio -> EQ Eight -> 1 Gain B`
  (Live parameter index 12, range `[-15, 15]`) temporarily changed from
  `0.0 dB` to `-1.0 dB`, passed verified readback and replay rejection, and
  restored its original value through identity-bound undo.
- The bounded recipe path is now qualified for one narrow two-step shape:
  `4-Audio` pan plus exact existing `EQ Eight -> 1 Gain A`. Both writes,
  replay rejection, inverse recipe, and final restoration passed through the
  KENN HTTP boundary. This is not a qualification of arbitrary recipes.
- If the insertion extension mutates Live but loses its OSC acknowledgment,
  KENN performs a fresh topology reconciliation before returning failure; it
  never asks the user to retry based only on an ambiguous insertion timeout.
- Generic natural-language device controls now resolve the parameter name from
  the exact Live device after topology selection. For example, `set Saturator
  Drive to 0.65 on track 4` produces a confirmation-only proposal using Live's
  actual `Drive` index and range; unsupported names are rejected after the
  fresh parameter probe.
- Glue Compressor's raw `Attack` and `Ratio` values are not display units:
  the live set reports raw `Attack=3` as display `1` and raw `Ratio=1` as
  display `4`. Decimal writes (`Attack 3.5`, `Ratio 1.25`) failed readback
  safely, while the discrete raw step `Attack 3 -> 4 -> 3` passed. These
  parameters remain unqualified until KENN has explicit display-unit mapping.

## Local setup

1. Install the pinned AbletonOSC package with
   `python3 scripts/install_abletonosc.py --replace`. The installer detects
   the User Library configured for Live. On this machine that is:
   `<LOCAL_VOLUME>/User Library/Remote Scripts/AbletonOSC`.
2. Restart Live after installing or changing the Remote Script.
3. In Preferences → Link / MIDI, choose `AbletonOSC` in an unused Control
   Surface slot. Leave MIDI Input and Output as `None`.
4. Start KENN with `PYTHONPATH=source python3 apps/backend/src/kenn/server.py`.
5. Verify `GET /api/ableton/status`, then `GET /api/ableton/osc/session`.
6. Inspect recent receipt history with `GET /api/ableton/receipts` when
   diagnosing a restart or uncertain result.
7. Reload the KENN plug-in in Live so it uses the rebuilt command client, then
   enter `add eq on track 4` and use the plug-in's **Confirm Live Proposal**
   control after reviewing the exact device-order proposal. Stop
   if the proposal is not exact; do not accept a different target.

Do not run both `KENN_Bridge` and `AbletonOSC` against UDP 11000 at the same
time. Keeping the old package installed is useful for rollback, but it must
not be selected while qualifying the standard route.

## Safety and upgrade order

The next upgrades should stay in this order:

1. Expand the qualified device matrix one family at a time, starting with
   read-only parameter discovery and one reversible control per device. The
   first-control pass is complete for Glue Compressor, Saturator, Auto Filter,
   and Drum Buss; the next target is broader per-family parameter coverage,
   beginning with display-unit mapping for discrete Glue controls.
2. Add a typed device-discovery and parameter-address cache so repeated
   questions do not rescan the whole session.
3. Add explicit capability negotiation from the OSC endpoint set rather than
   inferring support from a timeout.
4. Add the LLM command planner only above this deterministic boundary. The LLM
   may propose a typed action; it may not send raw OSC or bypass confirmation.

## Track-send (return) control: fully closed, natural-language control shipped

Reading and writing a track's send level to a return (`/live/track/get/send`,
`/live/track/set/send`) already existed in the vendored AbletonOSC Remote
Script. The enumeration gap (no way to know a return track's *name*, only a
bare index) closed on 2026-09-06: `/live/song/get/num_return_tracks`,
`/live/song/get/return_track_names`, and `/live/song/get/return_track_devices`
were added to the vendored fork, mirroring the existing regular-track
enumeration pattern exactly. Verified live against the real disposable set:
`A-Reverb` (device: `Reverb`) and `B-Delay` (device: `Delay`) came back
correctly through `kenn.ableton_osc_bridge.AbletonOSCClient.get_return_tracks()`
and `GET /api/ableton/osc/return-tracks`.

Natural-language control (e.g. "set the reverb send on track 3 to 0.5") also
shipped on 2026-09-06: `live_intent.py` recognizes a return track by name (not
just a bare send index), and `LiveActionService.propose_send_action` resolves
the exact return-track target through the same confirmation/readback/receipt/
undo boundary as every other action here. The exact-identity contract for a
compound reference (e.g. "the reverb send" against a return actually named
`A-Reverb`) is: an exact case-insensitive name match always wins; an
unambiguous substring match is a safe fallback only when it uniquely
identifies one return track; two or more plausible matches are refused, never
guessed. Real-Live verified end to end (propose -> confirm -> apply ->
verified readback -> undo via `/api/ableton/osc/undo` -> verified readback),
restoring the disposable set's original send value. See
`docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-06 entries.

Scene launching (`/live/scene/fire`) and clip-slot stop
(`/live/clip_slot/stop`) do not have this problem — scenes and clip slots
are already enumerated with real names/identity in the standard session
snapshot — so both are now wired through the normal confirmation/readback/
receipt boundary; see `docs/ABLETON_ASSISTANT_CURRENT_STATE.md`.

## Current command boundary

- `add EQ on track 4` and the equivalent exact candidate-device requests insert
  allowlisted native devices through confirmation-gated proposals and verify
  the resulting device chain.
- `set EQ Eight 1 Gain A to -3 dB on track 4` changes one exact, already
  existing parameter through the same proposal/readback boundary.
- When a track contains more than one EQ Eight, include the one-based device
  chain position, for example `set EQ Eight device 3 1 Gain A to -3 dB on
  track 1`. KENN resolves that to the exact Live device index and includes
  the device identity in the proposal; without the explicit position it
  refuses to guess.

`reduce amplitude by 3 dB at 250 Hz on track 4` is intentionally a
clarification when no unique EQ band is already tuned to 250 Hz. The next EQ
upgrade is an explicit compound proposal that names the band and shows both
the frequency retune and gain change before confirmation; it must not silently
retune whichever band happens to be closest.

The explicit compound form is now implemented and fake-Live verified:
`retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4`.
The real server produced the matching confirmation-only proposal on
`4-Audio`; the confirmed write, two-parameter readback, exact replay
rejection, and identity-bound undo all passed, with the original EQ values
restored.

The C++ plug-in remains the low-latency metering and user-interface client.
Python is appropriate for the local orchestration and OSC companion at this
stage; moving the safety and command path to C++ would add complexity without
removing the Live Remote Script or the need for a guarded local process.
