# KENN Ableton Live 12 implementation audit

Date: 2 October 2026. Installed application: **Live 12 Suite 12.4.6** (`2026-09-10_0de5c8fa9a`).

**KENN cannot currently claim control of every Live 12 device, parameter or library item.** The source supports generic raw-value control of exposed parameters on existing, top-level devices on regular tracks, with stronger guarded behavior for the established command path. It does not establish full rack-chain, return/master device, insertion, display-unit or library coverage. Several extension paths can report verification without observing a result.

This completes the source audit requested in **L1a** of [KENN_PLAN.md](../../KENN_PLAN.md). Implementation repairs and device qualification remain open under L1/L3/L5. This report is dated evidence, not another work queue. [Machine-readable evidence](KENN_LIVE12_IMPLEMENTATION_AUDIT_2026-10-02.json) contains the 78 rows, source hashes, exact endpoint differences, synthetic inputs and offline outputs.

## Scope and evidence boundaries

We inspected the command/planner/service path, both HTTP route implementations, MCP proposals/confirmation/reads, frontend API and recipe handling, the canonical JUCE plug-in, Swift desktop companion, binary OSC client and bundled Remote Script. We compared installed stock folder names with official Live 12 device chapters. Disk inventory, source inspection, fake-backend tests and in-memory transport reproductions were used. No running Live session was accessed and no audio or producer set was changed. A local GLM or other language model cannot supply missing transport targets, handlers or parameter metadata; model proposals must pass the same control contract.

The evidence records the inspected working-tree hashes. Three independent agents reviewed transport, app surfaces and inventory/plan boundaries, repeating the key failures in memory. Concurrent edits to `server.py` changed grounded-knowledge request context; their diff was inspected, Live command/Undo delegation remained unchanged, and the JSON records both hashes. Test totals describe the tested source state; the final fake-route reproduction used the current server. A hash identifies source, not a qualified build. Historical real-Live qualification receipts remain historical evidence; this pass requalified **zero** devices on the current installed Live version. It did not build or inspect a shipped JUCE binary or conduct a supervised release soak.

| Measure | Result | Meaning |
| --- | ---: | --- |
| Installed stock/catalog entries | 78 | 16 instruments, 47 audio effects, 15 MIDI effects |
| Entries with a matching knowledge note | 77 | Filename/content presence, not parameter-answer accuracy; Drum Synth is missing |
| Devices allowlisted for insertion | 10 | All 10 names are now recognized by the rule parser |
| Devices with built-in display-unit mapping families | 9 | 20 profile entries plus the separate EQ Eight band-gain path |
| Loaded JSON unit profiles / chooser tables | 0 / 0 | No additional measured mappings loaded in this checkout |
| Runtime parameter counts measured in this audit | 0 | The table below must not be read as runtime parameter enumeration |
| Registered bundled OSC addresses | 504 | Registration succeeded for the eight relevant handler modules |
| Declared addresses absent from the bundle | 4 reads / 12 writes | A declared client address is not proof of server support |

The inventory tool assigns `sees=True` to each stock entry without asking Live for that device's parameters ([device_coverage.py](../../tooling/scripts/device_coverage.py), lines 117–132). Its knowledge classification detects matching notes. Neither field proves end-to-end operation. Older evidence reporting eight parser-recognized insertion devices is superseded by this scan's ten.

The three official device chapters contain 63 named device sections; all 63 names match this stock scan. The remaining 15 entries include racks, modulators and content families described elsewhere. This is a section-name comparison, not a claim that there are only 78 devices or that 78 individual instances were loaded. Live's browser also contains Packs, presets, Max for Live, plug-ins, clips, samples, grooves, templates, tunings and user locations. KENN's stock scan does not inventory or qualify all of those. [Live audio effects](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/), [instruments](https://www.ableton.com/en/live-manual/12/live-instrument-reference/), [MIDI effects](https://www.ableton.com/en/live-manual/12/live-midi-effect-reference/), [browser](https://www.ableton.com/en/live-manual/12/working-with-the-browser/).

## Control surfaces

| Surface | Inspected behavior | Coverage limit |
| --- | --- | --- |
| Chat / HTTP command gateway | Resolves grounded targets and submits proposals to guarded services | Allowed schema/actions do not express nested chains or general bus device targets |
| Established parameter service | Confirmation, identity/range checks, fresh observation, readback and receipts | Raw exposed parameters on regular-track top-level devices; metadata policy incomplete |
| Tier 2/3 extension service | Thirteen actions are dispatched before the ordinary execution path | Several return sent-only `verified=True`; handler and wire contracts are incomplete |
| MCP | Read tools and proposal/apply tools use the companion | Four newer proposal tools send typed fields the HTTP gateway ignores |
| Vue frontend | Uses companion endpoints for proposal/apply/undo | Passing API tests do not qualify every recipe or Live action |
| Canonical native plug-in | Normal Apply/Undo uses the companion; direct writer is OFF by default | HTTP result interpretation needs semantic receipt checks; no full native build in this pass |
| Swift desktop | Hosts the frontend in WKWebView and starts the Python companion | No separate device-control implementation extending coverage |
| ControlDeck / legacy executor | ControlDeck adapter is read-only; legacy mutations default to disabled | These are not automatic fallbacks for missing OSC writes |
| Bundled Remote Script | Current install is the binary OSC `integrations/ableton-osc` tree | Separate legacy JSON UDP script does not implement this binary wire contract |

## Findings and acceptance criteria

### 1. P1: Extension receipts can claim verification after sending alone

The bridge's [_send_only](../../apps/backend/src/kenn/ableton_osc_bridge.py) (lines 475–485) returns true when `send_command` produces a local command identifier. It does not wait for an acknowledgement or readback. Extension executors then create `verified=True` receipts ([tier2_tier3_actions.py](../../apps/backend/src/kenn/core/actions/tier2_tier3_actions.py), arrangement lines 121–168; automation 221–273; analogous rack/routing/freeze/variation paths).

An in-memory reproduction used the production client class with only its send function replaced and a synthetic proposal. `LiveActionService.execute` returned `ok=True, verified=True` for arrangement duplication after **one send, zero execution snapshot reads and zero clip readbacks**. No server acknowledgement existed. These paths do not inherit the ordinary parameter executor's guards merely because they share a class: extension dispatch precedes that path ([live_action_service.py](../../apps/backend/src/kenn/core/live_action_service.py), execute from line 3645).

The final modulation/warp-mode/Max for Live/master-limiter helpers additionally call `.send`, which the production client lacks. A mock returning `success=False` still yielded three successful verified execution receipts, including a safety-enforced label. These last helpers are not wired into the shared dispatcher/current UI; they are latent unqualified implementations, not evidence that the release UI can perform those writes. Group creation already refuses when it cannot supply verified routing/Undo.

**L5 acceptance:** each reachable executor must inspect fresh preconditions, use an implemented transport operation, observe the intended result, bind replay/idempotency behavior and produce an honest receipt. Sent-only, timeout and failed outcomes must not become verified. Replace permissive mocks with contract fakes that reject unavailable client methods and missing server handlers. Preserve refusal for unsupported actions.

### 2. P1: Clip automation confirmation binds point count, not the curve

Automation proposal and execution construct the confirmation text from track/clip/device/parameter indices and `len(points)` (extension source lines 214 and 241). The curve values and times are absent. In the offline shared-executor reproduction, a one-point proposal at `{time: 0, value: 0.25}` was replaced with `{time: 16, value: 0.9}`. The original confirmation token was accepted and the altered point was forwarded to the fake client.

This is a service contract failure demonstrated without a Live write. Reachability through each friendly UI is not established by this reproduction.

**L5 acceptance:** bind a canonical immutable digest of the complete automation payload, target identity and relevant before-state to confirmation; revalidate that same payload at execution. Add tamper cases for time, value, order, count and target, then mutation-check those regression tests.

### 3. P1: Declared endpoint coverage exceeds the bundled implementation

`capability_report` returns declared allowlists plus a liveness probe ([ableton_osc_bridge.py](../../apps/backend/src/kenn/ableton_osc_bridge.py), lines 693–725), not a versioned server feature handshake. Offline registration of the actual song/track/device/clip/clip-slot/scene/view/application handlers found these absent reads:

- `/live/m4l/get/parameters`
- `/live/rack/get/macros`
- `/live/track/get/arrangement_clips`
- `/live/track/get/meters`

Absent declared writes:

- `/live/browser/load_preset`
- `/live/clip/duplicate_to_arrangement`
- `/live/clip/set_automation`
- `/live/clip/set_modulation`
- `/live/master/enforce_safety_limiter`
- `/live/rack/map_macro`
- `/live/rack/recall_variation`
- `/live/rack/store_variation`
- `/live/song/create_group_track`
- `/live/track/set/freeze`
- `/live/track/set/input_routing`
- `/live/track/set/output_routing`

Other standard property aliases can exist; this list concerns the exact addresses emitted by these implementations. It does not establish that Live's API cannot support the operation. The excluded MIDI-map handler only registers MIDI mapping addresses absent from these declared lists.

The current installer bundles binary OSC ([abletonosc_bundle.py](../../apps/backend/src/kenn/core/abletonosc_bundle.py), line 14). The separate `KENN_Bridge.py` speaks JSON UDP and implements some similarly named operations; it cannot supply binary OSC handlers. The encoder also accepts scalar arguments only: encoding the automation writer's list of point dictionaries fails with `Unsupported OSC argument type: list` ([abletonosc_protocol.py](../../apps/backend/src/kenn/abletonosc_protocol.py), lines 38–58). Adding a handler alone would leave that wire failure.

**L5 acceptance:** test the actual packaged handler registry against the client contract, define a versioned feature handshake and a supported serialization for compound payloads. Gate unsupported operations before confirmation. Verify matched client/server reads, writes, acknowledgement and observable readback through HTTP and MCP, with fake transport first. [Upstream AbletonOSC](https://github.com/ideoforms/AbletonOSC).

### 4. P2: Nested rack devices and general return/master device writes lack targets

The standard device handler selects `song.tracks[track_index].devices[device_index]` ([device.py](../../integrations/ableton-osc/abletonosc/device.py), line 13; writes 128–139). The proposal schema contains flat indices and rejects `device_path` and `track_kind` ([live_command.py](../../apps/backend/src/kenn/core/live_command.py), lines 69–90). Both rejections were reproduced offline.

Custom reads expose regular/return/master top-level devices and a rack tree, but the tree stops recursing after depth three and has no parameter-address path for inner devices ([song.py](../../integrations/ableton-osc/abletonosc/song.py), lines 143–230). General device-parameter writes do not use that bus selection. Return mixer volume/pan/mute already has a dedicated guarded write/readback path; this finding does not remove that existing support.

**L1 acceptance:** introduce grounded bus and rack-chain identities consistently in discovery, proposals, confirmation, execution, readback and Undo. Qualify nested instrument/audio/MIDI racks, Drum Rack chains, return devices and master devices with duplicate names and topology changes. Report an explicit limit or refusal for unaddressable devices. Racks contain chains and devices beyond their top-level macros. [Live racks](https://www.ableton.com/en/live-manual/12/instrument-drum-and-effect-racks/), [RackDevice API](https://docs.cycling74.com/apiref/lom/rackdevice/).

### 5. P2: Parameter observation can invent ranges and omit control state

The ordinary bridge reads names/value/min/max/quantization in separate replies. It fails on absent replies but accepts shorter range lists, supplying missing `min=0, max=1` ([ableton_osc_bridge.py](../../apps/backend/src/kenn/ableton_osc_bridge.py), lines 1492–1537). A two-parameter fixture with one range entry returned success and fabricated the second range. Native C++ probing rejects these truncated ranges; Python needs the same strict boundary.

The ordinary observation omits `is_enabled`, `state`, enum labels, original names and automation state. The custom bus reader includes automation state but still omits enabled/state/enum labels. A fixture marked disabled and state 2 was accepted by the planner and executed once by FakeLiveBackend. This proves missing KENN preflight policy, not that real Live permits that write.

The official DeviceParameter reference distinguishes raw values, quantized choices, disabled/state behavior, automation overrides and display strings. Its current `display_value` entry should be treated as a read-only feature-probe candidate for the installed Remote Script API, not assumed available because a Max API page lists it. API-exposed parameters also do not cover every device or plug-in GUI operation. [DeviceParameter API](https://docs.cycling74.com/apiref/lom/deviceparameter/), [using plug-ins](https://www.ableton.com/en/live-manual/12/using-plug-ins/).

**L1/L5 acceptance:** reject partial or mismatched observation arrays; carry and validate enabled/state/quantized labels and automation policy. Resolve macro-controlled parameters intentionally. Measure display conversions against the installed version and preserve automation semantics during write/Undo. Record manual-only/API-unavailable controls explicitly.

### 6. P2: Insertion and human-unit coverage remain selective

Generic existing raw-parameter control is not limited to the ten insertion devices or nine unit-profile devices. A uniquely observed raw parameter with a valid range can be attempted on other existing top-level devices. However, safe insertion and human-unit conversion are separate capabilities.

Insertion is allowlisted for EQ Eight, Glue Compressor, Saturator, Auto Filter, Drum Buss, Compressor, Hybrid Reverb, Echo, Roar and Multiband Dynamics. No instrument or MIDI effect is allowlisted. Keep the safeguards: historical fuzzy browser matches loaded different effects for requested names.

Built-in conversion profiles cover 20 families across nine devices plus EQ Eight band gain. That count is not the number of all exposed parameters. `display_to_raw` refuses an unmapped Operator frequency request in Hz ([device_units.py](../../apps/backend/src/kenn/core/device_units.py), from line 257); raw requests remain a separate path. No JSON profile or chooser table was loaded. Family-level qualified labels in `DEVICE_FAMILY_PROFILES` rely on recorded history and do not look up installed build/per-parameter receipts.

**L1 acceptance:** retain the 78-stock baseline, then separately inventory configured Packs, user presets, Max devices and AU/VST/VST3 content. Distinguish known, observed, measured, fake-tested and real-Live-qualified capabilities for each parameter. Expand insertion only after exact browser identity and reversible readback evidence. Meet the existing 25-device/60-parameter milestone before advertising wider coverage.

### 7. P2: Four newer MCP proposals do not have an HTTP payload route

Clip launch, scene creation, warp/pitch and loop duplication tools post a typed `proposal_action` plus `payload` ([live_proposals.py](../../apps/backend/src/kenn/core/mcp/live_proposals.py), lines 117–186). Neither HTTP command handler reads those fields ([daw_routes.py](../../apps/backend/src/kenn/routes/daw_routes.py), lines 20–49; [daw_command_handler.py](../../apps/backend/src/kenn/routes/daw_command_handler.py), lines 114–125 and 255–265). Instead, the gateway parses their generated command strings. Stop, warp mode and pitch values only in the ignored payload cannot reach the intended service through that route.

All four generated strings produced no action in an offline rule parse. In particular, zero-based `track_index=0` becomes the text `track 0`, which is interpreted as a user-facing track number rather than that index. An LLM could clarify a string, but that would not prove typed argument fidelity. Existing MCP tests verify mocked POST shapes rather than the real gateway's action semantics.

**L5 acceptance:** route typed MCP proposals through the same validated service contract, resolve index/name semantics and preserve every typed field. Test the real HTTP handler with fake backends from MCP proposal through confirmation, refusal, readback, receipt and Undo. Do not add independent MCP write authority.

### 8. P1: Native Apply interprets HTTP 200 as a verified mutation

Normal native Apply forwards the proposal, confirmation token and idempotency key to the companion. However, [PluginProcessor.cpp](../../plugins/kenn-vst3-au/Source/PluginProcessor.cpp), lines 790–823, returns success solely when the HTTP status is 200. It does not require an applied outcome or a verified receipt. The editor then clears the pending proposal and displays applied/verified ([PluginEditor.cpp](../../plugins/kenn-vst3-au/Source/PluginEditor.cpp), lines 472–493).

The production Python HTTP handler/gateway/service, injected with a synthetic FakeLiveBackend, returned HTTP 200 with `status=requires_confirmation`, `changed=false`, `execution.ok=false`, no receipt and zero writes for a nonempty-bound proposal marked `requires_confirmation=false`. The route deliberately maps confirmation requests to HTTP 200. The fixture and response are in `native_apply_confirmation_refusal`. The native success display follows from inspected C++ source; a native client was not compiled or run against this fixture.

Undo differs: its native client requires a receipt object as well as HTTP 200. The corresponding refusal returns HTTP 409 and is rejected. It still needs semantic receipt validation, but this audit does not claim normal Undo refusals reproduce the Apply bug.

The direct C++ writer remains OFF by default ([CMakeLists.txt](../../plugins/kenn-vst3-au/CMakeLists.txt), line 36); local fallback plans cannot be applied in that default source configuration (processor lines 784–786). Its optional developer path is raw-value/flat-target only and does not add general device coverage. Swift hosts the frontend and Python companion rather than providing another device writer ([KENNDesktopCompanion.swift](../../apps/desktop/macos/KENNDesktopCompanion.swift), lines 37, 127 and 280–283).

**L5 acceptance:** native Apply/Undo must validate semantic outcome, changed/no-op status and verified receipt before updating UI state. Add fake HTTP 200 confirmation/refusal, missing/unverified receipt, malformed body, replay and verified-success cases. Keep direct writes disabled until the alternate path meets the same target/unit/metadata/receipt contract. Shared companion authority includes specialized clip/MIDI/sample services; it is not literally one service class for every action.

### 9. P2: A latent planner API bypasses dB conversion

`LiveControlPlanner.parse_and_propose` excludes `db` from conversion for absolute and relative requests ([live_control_planner.py](../../apps/backend/src/kenn/core/live_control_planner.py), lines 438 and 449). With FakeLiveBackend, a Compressor Threshold request of **0.5 dB** created a proposal for raw **0.5**; the existing profile maps it to raw **0.8625**. A request for **−12 dB** failed against the raw `[0,1]` range. No writes were made.

No production caller of this convenience method was found. The shared gateway uses `propose_parameter_change` with its own conversion path, so this is a latent API defect and test gap, not a demonstrated HTTP/UI dB failure. It also means a blanket claim that every human-unit path consults profiles would be wrong.

**L1/L5 acceptance:** remove or correct the unused duplicate conversion path before exposing it. Verify human-unit parity across actual public surfaces with values that differ from raw coordinates, including relative values and out-of-range requests. Tests must assert proposal targets and observed results rather than only fixture names.

## Per-device source matrix

`Note` means a matching local note, `Insert` means allowlisted and rule-parser recognized, and `Units` lists built-in display mapping families. A dash means no mapping listed, not that the device exposes no raw parameters. **Every row has zero runtime parameter counts measured and zero real-Live requalifications in this audit.** Existing generic writes have the shared regular-track/top-level scope described above.

| Device | Category | Note | Insert | Units |
| --- | --- | --- | --- | --- |
| Analog | Instruments | Yes | No | — |
| Collision | Instruments | Yes | No | — |
| Drift | Instruments | Yes | No | — |
| Drum Rack | Instruments | Yes | No | — |
| Drum Sampler | Instruments | Yes | No | — |
| Drum Synth | Instruments | No | No | — |
| Electric | Instruments | Yes | No | — |
| External Instrument | Instruments | Yes | No | — |
| Impulse | Instruments | Yes | No | — |
| Instrument Rack | Instruments | Yes | No | — |
| Meld | Instruments | Yes | No | — |
| Operator | Instruments | Yes | No | — |
| Sampler | Instruments | Yes | No | — |
| Simpler | Instruments | Yes | No | — |
| Tension | Instruments | Yes | No | — |
| Wavetable | Instruments | Yes | No | — |
| Align Delay | Audio Effects | Yes | No | — |
| Amp | Audio Effects | Yes | No | — |
| Audio Effect Rack | Audio Effects | Yes | No | — |
| Auto Filter | Audio Effects | Yes | Yes | Resonance (%); Frequency (Hz); Dry/Wet (%) |
| Auto Pan-Tremolo | Audio Effects | Yes | No | — |
| Auto Shift | Audio Effects | Yes | No | — |
| Beat Repeat | Audio Effects | Yes | No | — |
| Cabinet | Audio Effects | Yes | No | — |
| Channel EQ | Audio Effects | Yes | No | — |
| Chorus-Ensemble | Audio Effects | Yes | No | — |
| Compressor | Audio Effects | Yes | Yes | Threshold (dB); Ratio (ratio); Attack (ms); Release (ms); Dry/Wet (%) |
| Corpus | Audio Effects | Yes | No | — |
| Delay | Audio Effects | Yes | No | — |
| Drum Buss | Audio Effects | Yes | Yes | Drive (%); Dry/Wet (%) |
| Dynamic Tube | Audio Effects | Yes | No | — |
| EQ Eight | Audio Effects | Yes | Yes | Frequency (Hz); band gain (dB, on an existing tuned band) |
| EQ Three | Audio Effects | Yes | No | — |
| Echo | Audio Effects | Yes | Yes | Dry Wet (%) |
| Envelope Follower | Audio Effects | Yes | No | — |
| Erosion | Audio Effects | Yes | No | — |
| External Audio Effect | Audio Effects | Yes | No | — |
| Filter Delay | Audio Effects | Yes | No | — |
| Gate | Audio Effects | Yes | No | — |
| Glue Compressor | Audio Effects | Yes | Yes | Attack (ms); Ratio (ratio); Dry/Wet (%) |
| Grain Delay | Audio Effects | Yes | No | — |
| Hybrid Reverb | Audio Effects | Yes | Yes | Dry/Wet (%) |
| LFO | Audio Effects | Yes | No | — |
| Limiter | Audio Effects | Yes | No | — |
| Looper | Audio Effects | Yes | No | — |
| Multiband Dynamics | Audio Effects | Yes | Yes | — |
| Overdrive | Audio Effects | Yes | No | — |
| Pedal | Audio Effects | Yes | No | — |
| Phaser-Flanger | Audio Effects | Yes | No | — |
| Redux | Audio Effects | Yes | No | — |
| Resonators | Audio Effects | Yes | No | — |
| Reverb | Audio Effects | Yes | No | — |
| Roar | Audio Effects | Yes | Yes | Drive (dB); Dry/Wet (%) |
| Saturator | Audio Effects | Yes | Yes | Drive (dB); Dry/Wet (%) |
| Shaper | Audio Effects | Yes | No | — |
| Shifter | Audio Effects | Yes | No | — |
| Spectral Resonator | Audio Effects | Yes | No | — |
| Spectral Time | Audio Effects | Yes | No | — |
| Spectrum | Audio Effects | Yes | No | — |
| Tuner | Audio Effects | Yes | No | — |
| Utility | Audio Effects | Yes | No | — |
| Vinyl Distortion | Audio Effects | Yes | No | — |
| Vocoder | Audio Effects | Yes | No | — |
| Arpeggiator | MIDI Effects | Yes | No | — |
| CC Control | MIDI Effects | Yes | No | — |
| Chord | MIDI Effects | Yes | No | — |
| Envelope MIDI | MIDI Effects | Yes | No | — |
| Expression Control | MIDI Effects | Yes | No | — |
| MIDI Effect Rack | MIDI Effects | Yes | No | — |
| MIDI Monitor | MIDI Effects | Yes | No | — |
| MPE Control | MIDI Effects | Yes | No | — |
| Note Echo | MIDI Effects | Yes | No | — |
| Note Length | MIDI Effects | Yes | No | — |
| Pitch | MIDI Effects | Yes | No | — |
| Random | MIDI Effects | Yes | No | — |
| Scale | MIDI Effects | Yes | No | — |
| Shaper MIDI | MIDI Effects | Yes | No | — |
| Velocity | MIDI Effects | Yes | No | — |

## Verification and limits

Offline verification completed with **1,028 Python tests passing**, **20 frontend API/composable tests passing** and **three pure C++ test executables passing**. Those passes describe the existing tests; they do not overturn the concrete contract failures reproduced above. `test_full_control_40_capabilities.py` uses permissive `MagicMock` objects and its 100-percent claim is not end-to-end Live coverage.

The frontend recipe-card component test did not run because the existing installation lacks `happy-dom`. An initial x64 Node startup also lacked its platform binding; the existing ARM Node runtime ran the API/composable tests successfully. No dependency was installed. A pre-existing invalid `\w` escape warning remains in vendored `pythonosc/dispatcher.py:153`. The canonical full JUCE plug-in and Swift application were not built; source default settings are not shipped-binary certification. The older copy under `audio-technology/vst3-plugins/KENNMixAssistant` is outside current product packaging and adds no qualified coverage.

### Commands recorded for repeatability

Stock scan, from the KENN product root:

```sh
KENN_LIVE_BACKEND=fake apps/backend/.venv/bin/python tooling/scripts/device_coverage.py --out-json /tmp/kenn-live12-audit-device-scan.json --out-md /tmp/kenn-live12-audit-device-scan.md
```

Backend commands below run from `apps/backend/src`; browser/native commands run from the product root. Frontend commands run from `apps/frontend`.

Core/control: 437 passed.

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q \
  kenn/tests/test_ableton_osc_bridge.py \
  kenn/tests/test_live_action_service.py \
  kenn/tests/test_live_backend.py \
  kenn/tests/test_device_units.py \
  kenn/tests/test_device_choosers.py \
  kenn/tests/test_full_stock_device_control.py \
  kenn/tests/test_full_control_40_capabilities.py \
  kenn/tests/test_device_profile_files.py \
  kenn/tests/test_live_unmapped_units.py \
  kenn/tests/test_live_control_safe_pipeline.py \
  kenn/tests/test_live_control_stress.py \
  kenn/tests/test_live_receipt_journal.py \
  kenn/tests/test_return_mixer.py \
  kenn/tests/test_tier2_control_expansion.py \
  kenn/tests/test_tier3_full_control.py \
  kenn/tests/test_live_setup.py \
  kenn/tests/test_live_intent.py \
  kenn/tests/test_mcp_facade.py
```

Routes/tooling: 575 passed.

```sh
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q \
  kenn/tests/test_live_command.py \
  kenn/tests/test_live_clip_command.py \
  kenn/tests/test_live_intent_natural.py \
  kenn/tests/test_live_intent_rule_order.py \
  kenn/tests/test_live_follow_ups.py \
  kenn/tests/test_live_corrections.py \
  kenn/tests/test_live_conversation_context.py \
  kenn/tests/test_llm_command_adapter.py \
  kenn/tests/test_mcp_dispatch_routing.py \
  kenn/tests/test_mcp_new_tools.py \
  kenn/tests/test_kenn_mcp_server.py \
  kenn/tests/test_plugin_parameters_api.py \
  kenn/tests/test_plugin_handoff.py \
  kenn/tests/test_remote_scripts_compile.py \
  kenn/tests/test_device_zoo_wave1_prep.py \
  kenn/tests/test_qualify_device_candidates.py \
  kenn/tests/test_chaos_live.py \
  kenn/tests/test_fake_live.py \
  kenn/tests/test_installed_devices.py
```

Bundled browser: 16 passed.

```sh
KENN_LIVE_BACKEND=fake apps/backend/.venv/bin/python -m pytest -q integrations/ableton-osc/test_browser_search.py integrations/ableton-osc/test_browser_sample_search.py
```

Frontend: 20 passed. Adding the third path below to that run exits with the existing missing `happy-dom` worker dependency before the component test executes.

```sh
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run src/api/kenn.test.ts src/composables/useKenn.test.ts
# Blocked component path: src/components/__tests__/KennRecipeCard.component.test.ts
```

Native pure tests: compile and run each executable using the existing compiler. No JUCE fetch, socket probe or Live access was used.

```sh
xcrun clang++ -std=c++20 -O2 -I plugins/kenn-vst3-au/Source plugins/kenn-vst3-au/Source/LocalCommandLanguage.cpp plugins/kenn-vst3-au/Source/test_local_command_language_main.cpp -o /tmp/kenn-live12-audit-command-test
/tmp/kenn-live12-audit-command-test
xcrun clang++ -std=c++20 -O2 -I plugins/kenn-vst3-au/Source plugins/kenn-vst3-au/Source/LocalCommandLanguage.cpp plugins/kenn-vst3-au/Source/LocalLivePlan.cpp plugins/kenn-vst3-au/Source/test_local_live_plan_main.cpp -o /tmp/kenn-live12-audit-plan-test
/tmp/kenn-live12-audit-plan-test
xcrun clang++ -std=c++20 -O2 -I plugins/kenn-vst3-au/Source plugins/kenn-vst3-au/Source/LocalAbletonOscProtocol.cpp plugins/kenn-vst3-au/Source/test_local_ableton_osc_protocol_main.cpp -o /tmp/kenn-live12-audit-protocol-test
/tmp/kenn-live12-audit-protocol-test
```

The JSON preserves exact endpoint deltas and synthetic failing cases: `arrangement_send_only`, `automation_point_binding`, `automation_points_wire`, `truncated_ranges`, `disabled_parameter`, target schema rejections, MCP generated-command parses, the native Apply confirmation refusal and latent planner dB mapping. The reproductions used actual production methods with in-memory snapshots and explicitly replaced I/O. No live acknowledgements or qualification evidence were manufactured.

## Recorded change scope

This audit changes the plan and adds this report plus its JSON evidence. It does not change product behavior, transport handlers, model settings, dependencies or CI. The repairs remain reviewable acceptance criteria in the sole roadmap; L1a is the completed audit, while L1/L3/L5 and any supervised qualification remain open.
