# Ableton Live integration surfaces for a local AI assistant — notes, 15 October 2026

Lane 01 of the KENN landscape research, 2026-10-15. Research only; nothing here is an approval.
Markers: **[V]** verified against the cited URL on the date shown (default 2026-10-15), **[R]** carried from a previous run and not independently re-checked in this pass, **[I]** inferred, **[?]** unverified. A [V] is a citation, not a decision.
Provenance: first drafted 2026-10-15 by lane 01 (its own re-verification run followed the 2026-10-15 ~12:28 session-runtime loss). The same day, a takeover pass re-verified every headline claim, licence claim and quoted licence text against primary sources (ableton.com, help.ableton.com, GitHub API + licence endpoints, npm registry, raw source files) and rewrote this file in place. Changes are listed at the end under "15 Oct takeover review". Earlier drafts used `[U]`; that marker is now `[?]`.

Headline claims (expanded per section below):
1. Live stable is 12.4.6 (2026-09-15); the last feature release 12.4 shipped 2026-05-05. Beta channel at last check: 12.4.15b7 (2026-10-15). No public Live 13 pages.
2. Extensions SDK remains a public beta (announced 2026-06-02), macOS+Windows, Suite-only; run-once right-click tools, no observers/transport/real-time. Its licence text is still not public anywhere; a downstream project describes the SDK package as "non-redistributable", and the only public pointer is a docs landing page (`ableton.github.io/extensions-sdk`), not a source repo. No Ableton store; Ableton's own CDN distributes sample `.ablx` files.
3. AbletonOSC = MIT, 827★, last push 2025-11-19, no releases ever; structural gaps: no browser, no rack/chain traversal, no automation write, arrangement read-only (three properties exposed).
4. ableton-js is actively maintained (MIT, 532★, npm 5.0.4 on 2026-10-12); its Remote Script exposes Browser and Chain namespaces AbletonOSC lacks, plus grouped undo steps. Caveat: v5.0.1 exists as a GitHub release but never reached npm.
5. Earlier docs missed ahujasid/ableton-mcp (~3,190★) and dreamrec/LivePilot (BSL-1.1); producer-pal (GPL-3.0-or-later) is the most engineered Max-for-Live competitor and its public ADR explains why it refused the Extensions SDK.
6. New since the 14 Oct docs: an Extensions-SDK-based MCP cluster (Loophole et al.), producer-pal's ADR and Live-12.4.3-verified field notes, Protocol0's localhost-HTTP extension contract, Ableton's own CDN distributing sample `.ablx`, and (this takeover) `happysasha18/track-coach` — a measurement-first coaching skill whose Demucs dependency carries a non-MIT weights caveat.

## Q1. Live release status, October 2026

### Takeaway
Stable Live is 12.4.6 (bugfix, 2026-09-15) and it contains exactly one fix — a render/bounce/consolidate hang. The last feature release 12.4 (2026-05-05) brought Link Audio, stem-separation commands, and the Learn View. Extensions remain **beta-channel only** (`12.4.15b7`, 2026-10-15). There is no official Live 13 anything.

### Stable train (all dates [V] from https://www.ableton.com/en/release-notes/live-12/ checked 2026-10-15)
| Version | Date | Headline content |
|---|---|---|
| 12.4 | 2026-05-05 | Link Audio; Erosion rework; Chorus-Ensemble refinements; Delay LFO; Separate Stems for Time Selection; Merge Selected Stems to Single Track; Learn View |
| 12.4.1 | 2026-05-28 | Link Audio latency-compensation alignment fix; Komplete Kontrol S Mk3 direct track selection; NKS Connect; crash-on-restore fix |
| 12.4.2 | 2026-06-11 | Arturia MiniLab 37; Delay "Tape Warble" preset sound fix |
| 12.4.3 | 2026-07-14 | Re-Pitch warp respects clip groove; control-surface mapping updates; **"Max for Live can now open or close plug-in editor windows via the LOM"** |
| 12.4.5 | 2026-08-26 | Max 9.1.5; Splice installer 1.2.1; Ctrl/Cmd+F selects existing search term; Learn View screen-reader focus; Launchkey MK4 88 support; remote notifications in Status Bar; **last item: Max for Live "unstored" non-automatable parameters now initialise to their default value instead of resetting to 0/min** |
| 12.4.6 | 2026-09-15 | one Live bugfix only (hang when rendering/bouncing/consolidating with many Beats-warp Transients-Granular clips) |

Corrections folded in above (verified from the page today): the Max for Live "unstored non-automatable params" fix belongs to **12.4.5**, not 12.4.6 as the previous draft said; 12.4.6 has a single item. And a "12.4.4" section still does not appear on the public release-notes page (checked 2026-10-15); if it shipped, its notes are not public —[I] beta-only or folded. The page's only "Extensions" strings in stable notes are the unrelated "Show File Extensions" browser option, so "stable has no Extensions-SDK notes" holds in the SDK sense ([V], full-page scan).

### 12.4 feature details relevant to a companion ([V] release notes, same URL)
- **Link Audio**: real-time audio streaming between Link peers in a shared session; peers appear in a new Control Bar Link dropdown; receive via an audio track's input chooser; a dedicated Link settings page holds Audio/Name/Latency/Sync-to-Incoming-Audio/Peers; wired LAN recommended, Wi-Fi supported. Audio buffer size affects streaming latency.
- **Stem separation**: `Separate Stems for Time Selection` operates on an Arrangement time selection; separation now processes only the audible portion defined by clip start/end markers; `Merge to Single Track` merges 2–3 selected stems into one new clip/track (the checkbox only enables with 2 or 3 stems selected, not one or all four).
- **Learn View** replaces Help View: structured learning modules (video + written) inside Live, per Set.
- Also 12.4: Erosion updated (Noise Blend, Stereo Width; algorithmic latency reduced to 2 ms down from ~5 ms; old versions load as "Erosion Legacy"), Chorus-Ensemble "Classic" renamed "Chorus" with Time/Taps (Auto default preserves old presets), Delay LFO update (Hz/ms/tempo-synced rates, seven waveforms, Morph).

### Beta train ([V] https://www.ableton.com/en/release-notes/live-12-beta/ checked 2026-10-15)
- Current beta today: **12.4.15b7 (2026-10-15)** — "Updated software text in various areas of Live." plus a MIDI-notes/Transformations bugfix (individual undo steps per operation, no duplicate note IDs, Add Interval no longer loses base notes). This matches the previous run's claim.
- 12.4.15b6 (2026-10-08): Extensions Settings UI changes — search-field UI update, Sort Extensions toggle, "Fixed a bug where the sorting of extensions was case-sensitive".
- 12.4.15b5 (2026-09-30): Extensions SDK gains `performance`, `AbortSignal`, `Headers`, `Request`, `Response` and `FormData` globals.
- 12.4.15b4 (2026-09-23): rent-to-own/educational startup-dialog fix (not extension-related).
- 12.4.15b2 (2026-09-09): M4L Modulators audible-effect fix on ARM64; focus restore on Windows.
- 12.4.15b1 (2026-09-02): "A confirmation dialog is now shown when installing an Extension"; M4L Clip properties root_note/scale_name/scale_mode/scale_intervals; screen readers follow focus inside Extension modal dialogs; macOS `tempDirectory` ERR_ACCESS_DENIED fix.
- 12.4.5b5 (2026-06-24): accessibility item repeated; Learn View PiP sizing fixes; macOS tempDirectory fix backported.
- 12.4.5b4 (2026-06-17): **"A confirmation dialog is now shown when installing an Extension"**; "The Extension Host now connects to Live more reliably"; "Extensions SDK: showModalDialog does not retain data between calls anymore"; crash fix for the Extension Host restart notification.
- 12.4.5b3 (2026-06-02): **Extensions SDK introduced in beta** — "Extensions can interact with the elements of a Live Set, host custom UI elements, and integrate with external services"; "The Extensions SDK is now available as part of the 12.4.5 beta. You can download it directly from Centercode."
- Beta numbering history (12.4.5b1 May 12 → 12.4.5b11 Aug 12, then 12.4.15b1 Sep 2 → b7 Oct 15) supports the reading that the extension work rides the 12.4.5 → 12.4.15 beta branch, i.e. still unshipped to stable.

### Live 13
- No official Live 13 pages: `https://www.ableton.com/en/live-13/`, `/en/live/13/`, `/en/release-notes/live-13/` all return 404 (checked 2026-10-15). [V]
- boost.audio article "Ableton Live 13 in 2026 – Reality vs. Speculation" (2026-08-27) states Live 13 does not exist and calls 2026 release rumours misinformation; but it is a secondary commentary source with internal date sloppiness ("as of 2025, Live 12 remains..."). [R] source exists / [I] reliability: treat as weak secondary.
- Previous run's note that "a community extension dev references Live 13 Beta" — **not reproducible today** (websearch returns nothing in this environment; direct search found no page). Marked [?]; do not carry forward as a fact.

### What this means for KENN ([I])
- Do not build generic stem separation UX for Live users: Live 12.4 has native per-selection separation and stem merge. KENN's value sits above it (judgement, grading, context) and in the JUCE analyser.
- Link Audio is a Live-to-Live transport; KENN should assume stems remain files on disk for analysis, not a live audio stream, on a 16 GB M3.
- Learn View is now Live's own in-app teaching surface; KENN's "education" differentiation must be critique/measurement-based, not lesson replay.
- Extensions being beta-only means any KENN extension is a Suite-beta-only story until Ableton ships it to stable. See Q2.

## Q2. Extensions SDK

### Takeaway
Extensions are a real, first-party, typed JS/TS surface — but as of 15 Oct 2026 they remain **beta-channel only** (Live 12 Suite beta 12.4.15b7), can only run single-shot menu commands (no transport, no observers, no real-time), have no browser/filesystem-library access, use ephemeral handles, and their SDK is not publicly distributable (no public licence text; a downstream project calls the package "non-redistributable"). KENN can ship an `.ablx`, but only to Suite-beta users, and never as the sole path.

### Status and availability ([V] https://www.ableton.com/en/live/extensions/ , https://ableton.github.io/extensions-sdk/ , https://help.ableton.com/hc/en-us/articles/27303428331420-Ableton-Extensions-FAQ , https://www.ableton.com/en/blog/introducing-extensions-sdk/ , all checked 2026-10-15)
- Announced 2 June 2026 ("Introducing Extensions SDK: An experimental playground inside Live", blog dated June 2, 2026; beta notes 12.4.5b3 same day).
- Free public beta, downloaded via **Centercode** (Ableton beta programme; requires owning Live 12 Suite). The standalone docs landing page (ableton.github.io/extensions-sdk, HTTP 200) says "Public beta only … available exclusively in the Live 12.4.5 public beta. It does not work with any earlier version of Live." and links to Centercode for the SDK download and documentation.
- Live 12 **Suite Beta** only, 12.4.5 or later — FAQ: "Extensions are available in Live 12 Suite Beta, version 12.4.5 or later. Extensions are not available in Live Standard, Intro, or Lite." Stable notes contain no Extension mentions ([V] stable notes page); beta channel today is 12.4.15b7 (2026-10-15).
- macOS and Windows; "The NodeJS development environment v24.16.0 (LTS) or higher"; FAQ: "The Extensions SDK uses less than 5MB of disk space."
- Install path per FAQ: "After you install an Extension in Live (via Settings → Extensions)". (Previous draft said "Preferences → Extensions"; the official wording is Settings.)
- Dev loop: Developer Mode in Live; `extensions-cli run` against the local build (paulstretch's `npm start` = build + `extensions-cli run`); package to `.ablx` (paulstretch: `node package.js`; devDeps include esbuild) and install via Settings → Extensions ([V] paulstretch package.json + README; Ronvaknins skill README).
- Public claims about it: "The Extensions SDK is now available as part of the 12.4.5 beta" (beta notes 12.4.5b3). The blog states "Extensions SDK is an open JavaScript toolkit" and later points readers to "the documentation in the Ableton Extensions SDK GitHub repository" — that link resolves to the docs landing page above, which is served from Ableton's `ableton.github.io` repo (`extensions-sdk/index.md`); there is **no public SDK source repository** (`github.com/ableton/extensions-sdk` returns 404, checked 2026-10-15).

### What an extension can do ([V] SDK 1.0.0-beta API surface as documented publicly by Ronvaknins/ableton-extensions-skill reference/api.md, master branch, pushed 2026-06-06, 7,176 bytes; cross-checked against beta release notes and producer-pal ADR)
| Area | Surface |
|---|---|
| Entry | `activate(activation: ActivationContext)`; `initialize(activation, "1.0.0")` → `ExtensionContext`; `EXTENSIONS_API_VERSIONS = ["1.0.0"]` |
| Song | `tracks[]`, `returnTracks[]`, `mainTrack`, `scenes[]`, `cuePoints[]`; `tempo` get/set; `gridQuantization`, `gridIsTriplet`; scale `rootNote`/`scaleName`/`scaleMode`/`scaleIntervals`; `createAudioTrack`, `createMidiTrack`, `createScene`, `createCuePoint`, `deleteTrack/Scene/CuePoint`, `duplicateTrack/Scene` |
| Tracks | `name`, `arm`, `mute`, `solo`, `mutedViaSolo`, `groupTrack`, `mixer`; `devices[]`, `clipSlots[]`, `arrangementClips[]`, `takeLanes[]`; `insertDevice(name, index)`, `duplicateDevice`, `deleteDevice`, `deleteClip`, `clearClipsInRange`, `createTakeLane` |
| Clips | `name`, `color`, `muted`, `looping`, timing fields; `MidiClip.notes` **whole-array get/set** (`pitch, startTime, duration, velocity, releaseVelocity, probability, velocityDeviation, muted, selected`); `AudioClip.filePath`, `warping`, `warpMode`, `warpMarkers` |
| Devices | `Device { name, parameters[] }`; `DeviceParameter { name, min, max, defaultValue, isQuantized, valueItems[]{name,value}; async getValue()/setValue() }`; `RackDevice.chains[]`, `selectedChain`; `Chain.devices[]`, `mixer`; `DrumRack`, `Simpler`. **No parameter units/value-strings or observers in the public object model.** |
| UI | `ui.registerContextMenuAction(scope, title, commandId)`; `ui.showModalDialog(url,width,height)` (WebView HTML, resolves a posted-back string); `ui.withinProgressDialog(text, {progress}, body(update, signal))` with `AbortSignal` |
| Resources | `resources.importIntoProject(filePath)` (host copies file into project); `resources.renderPreFxAudio(track, start, end)` → WAV path. **Pre-FX only** |
| Undo | `context.withinTransaction(fn)` groups mutations into **one undo step** (nested calls collapse) |
| Identity | `Handle { id: bigint }`; invalidated on delete/move/Set change — no move-stable identity |
| Environment | `storageDirectory`, `tempDirectory`, `language` (uppercase ISO-639-1) |

### What an extension cannot do ([V] same sources)
- Official FAQ "What can't I do": no real-time audio processing, no real-time MIDI processing/monitoring, no in-chain devices (synths/samplers/effects), no background processing during playback/recording, no sample-accurate/event-accurate performance timing, **no real-time interaction with transport**. FAQ adds the steer: "Real-time and performance-oriented tools can be created and customized using Max for Live."
- producer-pal ADR (investigated 2026-06-23 against SDK type definitions; ADR-0007 accepted 2026-06-28): no play/stop, no clip/scene fire, no `current_song_time`; no MIDI-instrument or post-FX render ("`renderPreFxAudio` is pre-FX only, so there's no freeze, flatten, or bounce, and you can't resample a MIDI instrument. This is the real blocker."); ephemeral handles break its stable-id contract; "Revisit if the SDK gains either MIDI-instrument/post-FX render (or freeze/flatten) or a move-stable identity primitive." Verdict: stayed on Max for Live + V8.
- [V] its public write-up (why-not-an-extension.md): can't read arm-ability, group status, monitoring state, currently-playing clip, time signatures — "And there's no 'escape hatch' to read or set anything outside"; can't browse/scan sample folders ("Ableton has said today's permission model will harden into a stricter sandbox"); "There isn't even a native file picker".
- Community extensions confirm the boundary: "extensions are an offline editing/automation layer, not a real-time MIDI/audio effect" ([V] Ronvaknins skill README).

### Distribution, licensing, trust ([V] FAQ, blog, beta notes, repos checked 2026-10-15)
- **The SDK is free; third-party developers may charge for their extensions** — FAQ: "The Extensions SDK itself is free. However, third-party Extension developers may choose to charge for their products."
- Distribution unit is the `.ablx` file installed via Settings → Extensions; no official Ableton store exists. Channels today: Ableton's Discord (#extensions, #extensions-sdk discussion; #extensions-gallery for sharing), GitHub Releases (e.g. paulstretch ships `Paulstretch-<version>.ablx`; noise-canvas ships `noise-canvas.ablx`; BBenCut links to GitHub), and **Ableton's own CDN** — the Extensions landing page offers first-party sample `.ablx` zips (Notation, Photo MIDI, Vivarium, pet) from `cdn-resources.ableton.com`, and each sample is labelled "requires Live 12.4.5 Suite, currently in public beta".
- FAQ support split: "Since Extensions themselves are not created by Ableton, please contact the developer of the device if you have issues using it."
- SDK packages `@ableton-extensions/sdk` / `-cli` / `-create-extension` are **not published to public npm** ([V] registry.npmjs.org returns "Not found" for all three scoped names, 2026-10-15; unscoped placeholder `ableton-extensions-sdk@1.0.0` published 2026-06-18 by `hdj-ableton` (hidde.dejong@ableton.com) says "Please use `@ableton-extensions/sdk`"). Paulstretch README: the SDK and CLI tarballs must be dropped into `vendor/` from the downloaded zip.
- Two independent repos keep SDK tarballs **out of their public trees**: paulstretch `.gitignore` — "/vendor/*.tgz … Not committed; their integrity is pinned in package-lock.json", plus "extensions-sdk-*.zip"; Loophole CONTRIBUTING — "CI rejects imports outside that boundary without requiring the non-redistributable SDK package", and its extension README states the CONTRIBUTING rule explains "why the SDK never enters the source tree or the lockfile". **[?]** I could not read the SDK licence text itself: it is Centercode-gated, and no public page carries it (checked: FAQ, blog, landing, docs site, ableton.com/en/legal, ableton.com/en/eula — the EULA's "Extensions" definition is about Ableton-supplied add-ons, not the SDK). The strongest public evidence is the downstream "non-redistributable" phrasing above. **Owner/legal flag: read the licence inside the SDK zip before any `.ablx` commercial distribution decision; this remains the one unresolved gate in this lane.**
- Trust model: install shows a confirmation dialog (12.4.5b4); FAQ warns Node runs outside Live and "third parties [could create] malicious Extensions"; no code signing, sandbox-escape list, or store review described anywhere. Extensions execute with the user's full user-level privileges (Node process). `tempDirectory`/storage confinement is the only stated filesystem scope.
- Extension Host: separate process; "an uncaught error kills the whole Extension Host"; no formal deactivate hook (teardown on SIGTERM) ([V] Protocol0 README, npm @protocol0/extension-sdk 0.1.2, published 2026-06-11, MIT).

### What it unlocks beyond OSC ([I], grounded in the API surface)
- A supported, typed profile: stable across Live point releases in a way scripted Remote Scripts are not — no Remote Scripts folder, no MIDI remote-script injection, no OSC daemon.
- Same-process Node: extensions can open loopback HTTP servers and call external services (explicitly sold as "connect Live to entirely new services and systems"), which is how Loophole turns the SDK into an MCP bridge.
- Grouped undo via `withinTransaction` — undo-granularity KENN's AbletonOSC path has to engineer itself.
- MIDI notes as a whole-array get/set; device insert/duplicate/delete; arrangement clip creation; take lanes — areas where AbletonOSC is thin.
- Pre-FX region render to WAV — usable for analysis without a Live audio tap.
- What it does NOT unlock: transport, observers, browser/library search, third-party plug-in parameter introspection beyond the curated `DeviceParameter` shape, stable identity, real-time anything.

### Extensions-SDK MCP servers already exist (checked 2026-10-15)
- OthmanAdi/loophole — MIT, 22★, created 2026-06-02, pushed 2026-10-11, 0 releases; "the first MCP server built on Ableton's official Extensions SDK"; 12 deterministic MCP tools + read-only resources + queued mutations in `@othmanadi/ableton-mcp`, and a Kit of **five context-menu extensions packaged as one `.ablx`**; SDK-free core with a `LiveBridge` port and shipped `FakeLiveBridge`; E2E checklist marks unchecked gates `NOT_RUN`; MCP spec revision 2025-11-25.
- jasper-zheng/ableton-sdk-mcp — 19★, **no licence**, pushed 2026-06-15.
- t1merickson/next-live-mcp (MIT, "Capability-honest — `ableton://capabilities` reports the active adapter…"), ulm0/ableton-live-mcp (MIT), idx3d/ableton-mcp-extension (MIT, 2★) — extension-embedded MCP, 2026.
- pnomolos/live-wire — GPL-3.0, Max-for-Live-proxy MCP bridge (contrast path).

## Q3. AbletonOSC

### Takeaway
AbletonOSC is still the deepest *free* control surface for KENN, but it is a stalled project (last code/enhancement activity 2025-11-19; 39 open issues + 34 open PRs; no releases ever) with structural gaps that matter to KENN: no browser, no rack/chain traversal, no automation, arrangement read-only and thin, groove unsettable, no take lanes.

### Repo state ([V] GitHub API + source, checked 2026-10-15)
- MIT licence; 827★; 161 forks; created 2021-05-02; default branch `master`.
- Last push 2025-11-19 (last commits at 15:03–15:11 UTC: "Add issue templates", "Add pull request template", "Update README" — housekeeping, not code; last code commit 2025-11-17). **Zero releases.**
- 73 open items = **39 open issues + 34 open PRs**. Most recent open issue: #212 (2026-06-20), "clip_slot callback raises RemoteScriptError on every message (logger.info called with non-format args)" — a real bug sitting untriaged (a matching fix PR #213 also sits open).
- KENN's vendored copy at `integrations/ableton-osc` is pinned to upstream commit `88b08476a2d24406dce54ef5f45d516c9affbf72`, whose pin source is "the upstream `insert_device` extension in PR #173" ([V] `KENN_VENDOR_METADATA.md`) — i.e. KENN already rides an unmerged upstream PR, and the metadata file instructs that transport policy stays in `apps/backend/src/kenn/`, not in the vendor dir.

### Coverage — verified from master source (raw.githubusercontent.com/ideoforms/AbletonOSC/master/abletonosc/, 2026-10-15)
Handler modules: `application, clip, clip_slot, constants, device, handler, introspection, midimap, osc_server, scene, song, track, view` (+ `__init__.py`). **No browser module, no groove module, no take-lane module, no automation module** (all four filenames 404 on master).

| Surface | What actually exists | Gap |
|---|---|---|
| Song | r: `can_redo, can_undo, is_playing, song_length, session_record_status`; rw: `tempo, current_song_time, loop/loop_start/loop_length, metronome, record_mode, session_record, punch_in/out, back_to_arranger, arrangement_overdub, clip_trigger_quantization, midi_recording_quantization, groove_amount, root_note, scale_name, signature_numerator/denominator, is_ableton_link_enabled, nudge_up/down`; methods include `undo`, `redo`, `start_playing`, `stop_playing`, `stop_all_clips`, `trigger_session_record`, `tap_tempo`, `set_or_delete_cue`, `capture_midi`, create/delete/duplicate track/scene/return-track, cue-point jump | No `str_for_value`-style display at song level; `groove_amount` scalar only; no tuning access in song.py |
| Track | r: `can_be_armed, fired_slot_index, playing_slot_index, is_grouped, is_foldable, is_visible, has_*_input/output, output_meter_level/left/right`; rw: `arm, color, mute, solo, name, fold_state, current_monitoring_state`; methods: `delete_device`, `stop_all_clips` | Arrangement clips reachable only as `get/arrangement_clips/{length,start_time,name}` — **arrangement read-only and very thin**; no `duplicate_clip_to_arrangement`; no automation; no take lanes; no device-chain traversal |
| Clip | methods: `fire, stop, duplicate_loop, remove_notes_by_id` (+ notes get/set arrays); r: `end_time, file_path, gain_display_string, has_groove, is_* , length, playing_position, sample_length, start_time, will_record_on_start`; rw: `color, end_marker, gain, launch_mode, launch_quantization, legato, loop_end, loop_start, looping, muted, name, pitch_coarse/fine, position, ram_mode, start_marker, velocity_amount, warp_mode, warping` | `groove` property is explicitly commented out in source with the recorded error "Error handling OSC message: Infered arg_value type is not supported"; `warp_markers` and `view` same; `is_arrangement_clip` TODO |
| Device | r: `class_name, name, type`; special parameter API: `get num_parameters`, `get parameters/{name,value,min,max,is_quantized}`, `set parameters/value`, `get parameter/value`, `get parameter/value_string` (uses `str_for_value`: "Uses str_for_value method to return the UI-friendly version of a parameter value (ex: \"2500 Hz\")"), **value listeners** (`/live/device/start_listen|stop_listen/...` backed by `add_value_listener`) | **0 mentions of `chain` in device.py** — nested rack chains are not addressable; the only `rack` substrings are inside `track_index` (3 occurrences), i.e. no rack code at all; no device move/reorder; delete only via track method |
| Session | clip_slots fire/stop, scenes create/delete/duplicate, `view` handler, `midimap` handler | — |

### Assessment ([I] unless marked)
- The listeners (device parameter value, track meters via `output_meter_*`) are the one observability feature KENN's proposal/readback/Undo policy could lean on — but neither is documented as actively maintained; #212 shows the callback path can throw on every message.
- Upstream is effectively unmaintained for a year (Nov 2025). KENN already vendors and patches it (`integrations/ableton-osc`, pin `88b08476…`), so continuity risk is real: any Live point release that changes the Remote Script surface lands on KENN to fix.
- No releases means no version pinning signal; `master` is the only artefact. For a closed-source product this is a supply-chain and stability flag, not a licence flag (MIT is clean).
- **Correction vs previous run:** the previous run's "~73 open issues/PRs" was correct as a combined number (39 issues + 34 PRs [V]); the "4 `rack` mentions are type checks" detail was wrong (see table row above, verified by grep). "No automation" holds (0 automation mentions in track/song/device/clip). "Arrangement read-only" holds, and is worse than it sounds — only three arrangement properties are exposed.
- One prior-run detail needs care: the previous KENN research doc (13 Oct) said the *bundled* KENN copy comments out `groove`; I verified the same is true of *upstream master* AND of the vendored copy at the current pin — the block is upstream's, not KENN's invention.

## Q4. ableton-js and other bridges

### Takeaway
ableton-js (leolabs) is the strongest third-party bridge for breadth and maintenance: MIT, 532★, npm 5.0.4 on 2026-10-12, WebSocket Remote Script, **Browser and Chain namespaces included** — coverage AbletonOSC does not have — plus grouped undo calls. Its cost: another Remote Script to install, unencrypted loopback WebSocket, and its own version drift. Max for Live remains the other commercial-grade path but adds Max runtime constraints (see licence note below).

### ableton-js ([V] npm + GitHub + source, 2026-10-15)
- Repo `leolabs/ableton-js`: MIT, 532★, 72 forks, 5 open issues, created 2019-05-19, last push 2026-10-12. npm `ableton-js` latest **5.0.4 (2026-10-12)**. GitHub releases this year: 5.0.0 (2026-09-11), 5.0.1 (09-15), 5.0.2 (09-19), 5.0.3 (09-21), 5.0.4 (10-12) — note **5.0.1 is a GitHub release that never appeared on npm** (registry time data jumps 5.0.0 → 5.0.2), so pin from the registry, not the release list. Engines `node >=21`; deps: lodash, p-limit, lru-cache, @noble/hashes.
- Transport: a **MIDI Remote Script** (`midi-script/`, plugin name `AbletonJS` in `Config.py`, renamed `AbletonJS` in the Remote Scripts folder) opens a **WebSocket server on 127.0.0.1:39031**; optional password auth (per-connection salt from `os.urandom(16)`, HMAC-SHA256 `hmac.new(password, salt, sha256)`; the socket itself stays `ws://`). "Control Ableton 11 or later"; goal is to expose all MIDI Remote Script functions to TypeScript.
- Namespaces present (mirroring LOM classes) — [V] tree at `midi-script/Namespaces/`: Application, ApplicationView, **Browser**, **BrowserItem**, **Chain**, ChainMixerDevice, Clip, ClipSlot, CuePoint, Device, DeviceParameter, DeviceView, DrumChain, DrumPad, Envelope, Groove, GroovePool, Interface, Internal, LooperDevice, Midi, MixerDevice, PluginDevice, RackDevice, RackDeviceView, Scene, Session, Song, SongView, TakeLane, Track, TrackView, TuningSystem.
- Verified calls in source [V]: `beginUndoStep()`/`endUndoStep()` → `begin_undo_step`/`end_undo_step` ("Begins a grouped undo step for subsequent song edits"; "Ends the current grouped undo step"), `undo()`, `redo()`; `duplicate_clip_to_arrangement` present in `track.ts` + `Track.py` (and CHANGELOG); `load_item` + `preview_item` present in `Browser.py` + `browser.ts`; `get_full_refresh` carries the comment "Bang-only listener; no readable property on Live's Browser."
- Notable: author (Léo Bernard/leolabs) sells **AbleSet**, a setlist app built on ableton-js — commercial use of the MIT library is fine (MIT). [V npm/GitHub; AbleSet link in README]
- Gaps/risks [I]: still requires the user to install a Remote Script (same fragility class as AbletonOSC); WebSocket is unencrypted (loopback only; password is optional); subscribes to the entire LOM surface, so Live point releases can break it; TypeScript-only client (KENN is Python/JUCE — it would be a second runtime to ship).

### The official Python LiveAPI Remote Script path (what KENN already rides) — cross-checked in Q5
- AbletonOSC, ableton-js, and ableton-mcp all ride the same private `LiveAPI` surface; the differences are transport (OSC vs WebSocket vs raw socket) and how much of the LOM they expose, not capability class. [I from sources] For KENN, AbletonOSC remains the sole Live write authority: any breadth borrowed from ableton-js's coverage (browser, chains) must be qualified through KENN's vendored Remote Script, not by adding a second bridge.

### Max for Live ([V] FAQ cross-reference within Extensions FAQ; licence text not yet seen)
- Ableton's own FAQ steers real-time/performance work to Max for Live ("Real-time and performance-oriented tools can be created and customized using Max for Live"). LivePilot ships an "M4L Analyzer" to listen to audio — evidence the M4L path remains the way to touch audio in real time from a companion.
- **Licence flag (owner/legal):** Max for Live requires a Live Suite licence and Max; commercial distribution of M4L devices is standard practice (many paid M4L devices exist; Ableton itself has an `ableton/m4l-connection-kit` under MIT), but the Max/MSP licensing terms for embedding/redistribution need reading; I did not verify those terms in this pass (previous lane or owner legal should confirm). [?]
- Genuinely useful M4L-only surfaces: real-time audio/MIDI observation, `live.remote~`, parameter modulation, devices in chains — the class of things the Extensions SDK explicitly cannot do and OSC cannot do in real time.

### Other bridges checked
- pnomolos/live-wire — GPL-3.0, MCP via M4L proxy (licence problem for KENN reuse).
- alpacaaa/max4node (124★, no licence, last push 2020) — dead.
- 2bbb/node-abletonlink (159★, MIT, 2023) — Link tempo sync only; irrelevant to control.
- ableton-mcp (ahujasid) is a Remote Script + socket bridge, not a library; see Q6.

## Q5. LiveAPI remote-script surface as of Live 12

### Takeaway
The private Python `LiveAPI` (what AbletonOSC/ableton-js/ableton-mcp all ride) is broader than the public LOM docs suggest: browser load, grouped undo steps, device parameter display strings, take lanes, and arrangement clip duplication all exist. But several write paths are quietly broken or constraining even in Live 12.4.x, and the community's field notes are the only reliable documentation of those.

### Undo granularity ([V] sources below)
- Public LOM documents `Song.undo`, `Song.redo`, `Song.can_undo`, `Song.can_redo` as atomic operations. [Song LOM, checked 2026-10-15]
- The Remote Script API additionally supports **grouped undo steps**: ableton-js maps `beginUndoStep()`/`endUndoStep()` to `begin_undo_step`/`end_undo_step` ("Begins a grouped undo step for subsequent song edits") and these are used by Live's own Push framework — e.g. `pushbase/undo_step_handler.py` calls `self._song.begin_undo_step()` / `end_undo_step()` in the gluon Live 11 Remote Scripts mirror, and the Live 12 mirror's `pushbase/elements.py` + `_Framework/ButtonElement.py` wire the same pair to buttons. **These are not on the public LOM page** (0 hits for `begin_undo_step`/`end_undo_step` on the Song page) — treat as supported-but-undocumented, and qualify per version. [V ableton-js source + gluon mirrors]
- Practical granularity for KENN: OSC path gets atomic undo only, so multi-step edits need the begin/end pair to collapse, or KENN's own inverse receipts (already the KENN design). The Extensions SDK formalises the same idea as `withinTransaction`. [I]

### Device parameter metadata ([V] DeviceParameter LOM, checked 2026-10-15)
- `value` (get/set/observe) internal, `display_value` (get/set/observe) as shown in GUI, `str_for_value(value) → symbol`, `__str__` → current display string — **units and value strings are available**, contrary to what a raw numeric bridge would suggest. The class doc says it "represents an (automatable) parameter within a MIDI or audio device".
- `min`, `max`, `default_value` (only non-quantized), `is_quantized` (booleans/enums), `value_items StringVector` (only quantized), `name`, `original_name` (macro pre-assignment name), `automation_state` (0 none / 1 active / 2 overridden), `state` (0 active / 1 changed-but-inactive / 2 unchangeable), `is_enabled`.
- Hard limit: `Device.parameters` exposes **only automatable parameters** — non-automatable params are invisible to the Remote Script API entirely. [Device LOM: "Only automatable parameters are accessible."]
- Device metadata: `class_name` (e.g. `PluginDevice`, `Operator`), `class_display_name`, `type` (1 instrument / 2 audio effect / 4 MIDI effect), `can_have_chains`, `can_have_drum_pads`, `is_active` (get/observe), `latency_in_samples`/`latency_in_ms` (get/observe), plus device A/B compare properties `can_compare_ab`, `is_using_compare_preset_b`, `save_preset_to_compare_ab_slot` (the A/B feature itself shipped in the live-123 section, i.e. Live 12.3). [Device LOM + 12.3 release notes section on the same page]
- Third-party plug-ins: VST3/AU appear as `PluginDevice` with parameters reachable through the same `DeviceParameter` model **when automatable**; parameter sets are plugin-defined and can be large/reordered, so KENN should resolve parameters by name at read time, never by index across sessions. [V docs + I]

### Browser access ([V] ableton-js `midi-script/Namespaces/Browser.py`, 2026-10-15)
- `application.browser` exists in the Remote Script API and is enumerated by ableton-js: categories `audio_effects`, `clips`, `colors`, `current_project`, `drums`, `instruments`, `legacy_libraries`, `max_for_live`, `midi_effects`, `packs`, `plugins`, `samples`, `sounds`, `user_folders`, `user_library`; `filter_type` get/set (`Live.Browser.FilterType`); `hotswap_target`; `load_item(id)`; `preview_item`; `relation_to_hotswap_target`; `full_refresh` is bang-only ("# Bang-only listener; no readable property on Live's Browser.").
- Public docs check: `https://docs.cycling74.com/apiref/lom/browser/` returns 404 (checked 2026-10-15) and the LOM `Application` page lists only `view` + `control_surfaces` children. So browser reach is **real but undocumented**; version fragility unknown. The previous KENN note (13 Oct) that the public reference has no Browser class is reproduced, with the added nuance that ableton-js proves the API exists underneath.

### Arrangement, take lanes, clips ([V] Track LOM, checked 2026-10-15)
- Children: `take_lanes`, `clip_slots`, `arrangement_clips`, `devices`, `group_track`, `mixer_device`, `view`.
- Functions: `create_midi_clip`, `create_audio_clip`, `create_take_lane`, `delete_clip`, `delete_device`, `duplicate_clip_slot`, **`duplicate_clip_to_arrangement(clip, destination_time)`** — "Duplicate the given clip to the Arrangement, placing it at the given destination_time in beats. The source clip can be a session or an arrangement clip." Also `insert_device(device_name, target_index)` (throws if insertion impossible), `jump_in_running_session_clip`, `stop_all_clips`.
- Song-level recording: `record_mode` (get/set/observe, = Arrangement Record button), `arrangement_overdub`/`overdub`, `punch_in`/`punch_out`, `session_record`/`session_automation_record`, `trigger_session_record(record_length?)`, `capture_midi(destination 0 auto/1 session/2 arrangement)`, `current_song_time` (get/set/observe, beats), `jump_by`, `play_selection`, `re_enable_automation`, `set_or_delete_cue`, `find_device_position`, `move_device`. [Song LOM]
- Live 12 LOM growth examples: 12.4.3 stable notes — "Max for Live can now open or close plug-in editor windows via the LOM"; 12.2b16 beta notes (May 7, 2025) — "Clips in Take Lanes can now be accessed via the Max for Live API. Additionally, the create_audio_clip and create_midi_clip functions have been added to the API, making it possible to add clips to Take Lanes." [V release-notes pages]

### What community paths cannot do reliably ([V] producer-pal field notes, verified against Live 12.4.3; URL below)
- **Warp markers cannot be written**: `Clip.add_warp_marker` and `Clip.move_warp_marker` "both report success and change nothing (verified against Live 12.4.3, on a warped session clip)"; `warp_markers` reads fine. (AbletonOSC blocks `warp_markers` at the OSC layer for the same net effect.)
- **Warped looped arrangement clips cannot be resized**: "Arrangement clip length cannot be changed after creation by any means for warped looped clips" — not `end_time`, `end_marker`, `loop_end`, or any other property; only create-with-the-right-length via session tiling or duplication. (Exception: for *unlooped* clips `loop_end` is writable and extends arrangement length.)
- **Mid-clip splitting doesn't work**: overlapping a temp clip on the middle of an existing clip truncates and discards the tail rather than splitting; only edge trims work. Producer-pal uses a holding-area algorithm instead.
- `end_marker` is not clamped (`99999` sticks), so it can't be trusted as content length; `loop_end` reverts on warped clips when looping is toggled off; `loop_end` units differ by clip type (MIDI: beats; unwarped audio: seconds, auto-clamped; warped audio: content beats, no clamp).
- These are the constraints behind KENN's own "MIDI clip create/update/remove/read" being the qualified path and "move/crop/loop/replace arrangement clips" still incomplete in the capability matrix.

Source: [producer-pal dev/live-api/arrangement-operations.md](https://github.com/adamjmurray/producer-pal/blob/main/dev/live-api/arrangement-operations.md) (checked 2026-10-15; states verified against Live 12.4.3).

## Q6. MCP / assistant-bridge ecosystem refresh

### Takeaway
The ecosystem split in one year: Remote-Script bridges (ahujasid ableton-mcp, 3,190★) still dominate by adoption; the fastest-moving surfaces are now Max-for-Live-proxy and **Extensions-SDK** MCP servers; LivePilot is the closest full competitor (BSL-1.1). New since ~14 Oct: extension-native MCP servers, two first-week repos, and (this takeover) `happysasha18/track-coach`. Transferable patterns are worth more than the repos: capability-honest verification gates, context economy (publish few tools, keep many searchable), evidence labelling, set-scoped memory, and undo-boundary discipline.

### Refresh of the previously listed repos ([V] GitHub API, all checked 2026-10-15)
| Repo | Stars | Licence | Last push | Notes vs 14 Oct doc |
|---|---|---|---|---|
| ahujasid/ableton-mcp | 3,190 | MIT | 2026-09-22 | The field's biggest. Remote Script socket + MCP; PyPI (`uvx ableton-mcp`); features: track/clip manipulation, library instrument/effect selection, arrangement composition, session/transport control; **anonymous telemetry, disable-able** ("Usage tracking to help improve the tool (can be disabled)"); README warns "Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both." |
| dreamrec/LivePilot | 82 | **BSL-1.1** (not open source; change → MIT 2030-04-13) | 2026-10-15 | Direct competitor. v1.30.0 (npm `livepilot`): 474 tools / 57 domains; advertises 28 entry points per session; evidence labels (measured/heuristic/artistic); project memory follows the Live set; M4L Analyzer + Remote Script + Python env installer; architecture: Remote Script on TCP 9878, M4L bridge on UDP 9880 / OSC 9881, version capability tiers (12.0+/12.1.10+/12.3+/12.4+); in-set changes ride Ableton's undo stack, out-of-set changes (downloads/memory/scans/installer) do not |
| adamjmurray/producer-pal | 329 | **GPL-3.0-or-later** (verified from LICENSE: "GNU General Public License v3.0 or (at your option) any later version. SPDX-License-Identifier: GPL-3.0-or-later") | 2026-10-14 | M4L + V8 host; ADR-0007 explains why not an extension; publishes field notes on Live API traps (Q5); stable-id contract for model references |
| freekmurze/ableton-ai | 20 | MIT | 2026-08-09 | stale since Aug |
| peterkolbe/ableton-for-ai | 1 | MIT | 2026-05-15 | effectively dormant |
| F-Fischer/ableton-copilot | 0 | MIT | 2026-07-23 | dormant |
| josefigueredo/ableton-mcp | 1 | MIT | 2026-02-05 | dormant |
| RiotTheMan/ableton-mentor-mcp | 0 | MIT | 2026-04-13 | dormant |
| madisonrickert/ableton-tools | 16 | MIT | 2026-10-09 | active; Claude Code skills; also ships `ableton-sheet-music-extension` (MIT, 46★, pushed 2026-07-13) |

### New since 14 October ([V] GitHub API, 2026-10-15)
| Repo | Stars | Licence | Created/push | What |
|---|---|---|---|---|
| OthmanAdi/loophole | 22 | MIT | created 2026-06-02, push 2026-10-11 | MCP built **inside** Live on the Extensions SDK; one `.ablx` (five context-menu tools) + 12 MCP tools + read-only resources + queued mutations; core/MCP/extension split; E2E gates `NOT_RUN`; no release |
| CanArslanDev/ableton-live-mcp | 2 | MIT | created 2026-10-10, push 2026-10-11 | README claims: "expose the complete Live Object Model, plus music-theory generators and an audio 'ear'"; Remote Script based, Live 11/12 |
| cmdiego/ableton_live_mcp | 1 | Apache-2.0 | created 2026-10-11, push 2026-10-13 | "uses only the standard Live API and Max for Live"; Remote Script on TCP 9877 |
| xiaolaa2/ableton-copilot-mcp | 93 | MIT | created 2025-03-30, push 2026-07-29 | MCP on ableton-js; Arrangement View ops, MIDI editing, audio recording |
| t1merickson/next-live-mcp | 0 | MIT | push 2026-09-29 | "Capability-honest" extension-embedded MCP; reports active adapter/API via `ableton://capabilities`; passed a focused in-Live run (Live 12.4.5b8 / 12.4.15b1) |
| ulm0/ableton-live-mcp | 0 | MIT | push 2026-09-03 | MCP inside a Live Extension |
| idx3d/ableton-mcp-extension | 2 | MIT | push 2026-08-17 | MCP extension |
| jasper-zheng/ableton-sdk-mcp | 19 | **none** | push 2026-06-15 | TS-command MCP on the Extensions SDK; no licence file → not reusable |
| pnomolos/live-wire | 7 | GPL-3.0 | push 2026-06-05 | M4L-proxy MCP bridge |
| amitbaz/music-production-ai-mentor | 0 | MIT | created 2026-10-12, push **2026-10-15** | "Explains and acts in Live"; provider-agnostic TS agent harness; today it reads the Live Set through a hand-installed Remote Script and acts only in the terminal (read-only so far, 17 open issues) — closest to KENN's education framing, first week only |
| rremedio-web/composing-sidekick | 0 | MIT | created 2026-10-14 | Learns composer identity from the MIDI inside `.als` files and works "inside Live through the Producer Pal MCP device" — a cross-tool dependency on producer-pal (protocol-level only, so the GPL of the dependency does not reach this MIT repo) |

Also seen in the Extensions ecosystem: `@protocol0/extension-sdk` (MIT, npm 0.1.2, 2026-06-11) — a paid third-party tool exposing extension actions over **localhost HTTP** with `/openapi.json`, registering with an agent via `POST http://localhost:9010/api/extensions/register` so external keybinds can drive an extension; Paulstretch for Live (GPL-2.0, 106★, distributed from GitHub by Ableton's own landing page) and Noise Canvas (AGPL-3.0, 306★, pushed 2026-10-11 — ships a standalone app *and* an Ableton Live 12 extension (beta) `noise-canvas.ablx` on Releases) are the two most visible public extensions; both copyleft.
Also noted: `happysasha18/track-coach` (MIT, 1★, created 2026-06-15, pushed 2026-07-17) — "Measurement-first compositional coach for electronic music — librosa + Demucs diagnostics as a Claude Code skill. Reports only what it measures." Closest published artefact to KENN's measurement-first education framing; licence caveat in the Avoid list (Demucs weights).

### Transferable patterns (what the ecosystem has converged on) ([I] from the above)
1. **Split the SDK-free core from the Live adapter** — Loophole's `core`/`mcp`/`extension` packages exist so logic is testable without Live; KENN already does this with `FakeLiveBackend`. Loophole even names a `FakeLiveBridge`.
2. **Capability-honest verification gates** — Loophole's E2E checklist marks unverified gates NOT_RUN rather than implying CI coverage; `next-live-mcp` brands itself "capability-honest". Directly comparable to KENN's "offline verified only" matrix column.
3. **Context economy** — LivePilot advertises 28 entry points while keeping 474 tools searchable/callable on demand. For a local 16 GB M3 setup, small advertised surface + on-demand discovery is the sane pattern.
4. **Evidence labelling** — LivePilot separates measured audio, setup-derived heuristics, and artistic judgement in every report. KENN's grading features need exactly this honesty taxonomy.
5. **Undo-boundary discipline** — LivePilot states in-set changes use Ableton's undo stack while downloads/memory/library scans do not; producer-pal keeps a stable-id contract so the model can name objects across a session. Both map onto KENN's proposal/readback/undo + fingerprints.
6. **Set-scoped memory** — LivePilot ties learned taste to the Live Set ("project memory follows the Live set rather than ordinary edits"). KENN's project memory should key off set identity (file_path/name from `Song`, available via LOM).
7. **Localhost HTTP + OpenAPI between agent and extension** — Protocol0's contract is a clean way for a KENN `.ablx` (future) to expose typed actions to the assistant without re-implementing MCP inside Live.
8. **Telemetry is optional and off by default in the serious tools** — ahujasid (telemetry, disable-able) vs LivePilot (no cloud service claim) vs KENN (local-first). KENN's positioning should be explicit about never phoning home.
9. Ratings caveat: stars moved materially since 14 Oct only for producer-pal (328→329); no listed repo was archived or licence-changed in the interval. [V] `amitbaz/music-production-ai-mentor` pushed today (2026-10-15) but still has 0★.

## Capability matrix (capability × access path × status × licence × caveats)

Status legend: **Y** = available and used by real projects; **P** = partial/needs qualification; **N** = absent; **X** = available-but-broken (verified field reports). All paths were checked 2026-10-15; "Remote Script direct" = the private Python LiveAPI that all bridges ride. KENN's write path stays AbletonOSC (vendored, pinned `88b08476…`); the other columns are candidate capability sources to qualify **through** that bridge, never alongside it.

| Capability | AbletonOSC (MIT) | ableton-js / Remote Script direct (MIT) | Extensions SDK 12.4.15b7 (beta, licence [?] — downstream calls the package "non-redistributable") | Max for Live (licence [?]) | Caveats |
|---|---|---|---|---|---|
| Play/stop/continue, transport | Y | Y | **N** | Y | Extensions FAQ: no real-time transport interaction |
| Set/read song time, jump, loop, punch | Y | Y | N (no `current_song_time`) | Y | — |
| Record into Arrangement / overdub / session record | Y (`record_mode`, `punch_in/out`, `session_record`; `trigger_session_record`) | Y | N | Y | Recording while KENN drives = high-risk automation |
| Locators (cue points) create/delete/jump | Y | Y | Y (`createCuePoint`, cuePoints[]) | Y | — |
| Tracks create/duplicate/delete/group/colour | Y (create/delete/duplicate; group not verified upstream) | Y | Y (create/duplicate/delete; arm/mute/solo/name; no grouping call in public API doc) | Y | — |
| Scenes create/delete/duplicate | Y | Y | Y | Y | — |
| Clip CRUD session view | Y (fire/stop/duplicate_loop/notes) | Y | Y (`ClipSlot.createMidiClip/createAudioClip/deleteClip`) | Y | — |
| MIDI notes read/write | Y (arrays, `remove_notes_by_id`) | Y | Y (whole-array get/set) | Y | Extensions: no per-note API, whole-array writes |
| Audio clip create from file | Y (create via LOM) | Y | Y (`createAudioClip{filePath}`, `importIntoProject`) | Y | Extensions import copies into project |
| Arrangement clip enumerate | **P** (only `length/start_time/name`) | Y (`arrangement_clips`) | Y (`arrangementClips[]`) | Y | AbletonOSC arrangement is nearly blind |
| Duplicate clip to Arrangement | N | Y (`duplicate_clip_to_arrangement`) | Y (`MidiTrack.createMidiClip` etc.; duplication beyond holes) | Y | — |
| Move/split/resize arrangement clips | N | P (holding-area workarounds; resize impossible for warped looped clips) | P | P | producer-pal field notes, verified Live 12.4.3 |
| Take lanes | N | Y (`TakeLane.py`, `create_take_lane`) | Y (`takeLanes[]`, `createTakeLane`) | Y (12.2b16+ API) | — |
| Devices insert/delete/duplicate/reorder | P (`delete_device`; insert via LOM not exposed as OSC addr) | Y (`insert_device`, `find_device_position`, `move_device`) | Y (`insertDevice(name,index)`, `duplicateDevice`, `deleteDevice`) | Y | Device name resolution differs (class vs display name) |
| Device parameter read/write | Y (value + min/max/is_quantized + value_string + listeners) | Y | Y (`getValue`/`setValue`; no display strings/units in public doc) | Y | Only automatable params (LOM) |
| Parameter value strings/units | Y (`str_for_value` via `get parameter/value_string`) | Y (`DeviceParameter.display_value`, `str_for_value`) | P (`valueItems` for quantized only) | Y | KENN readback layer should adopt this |
| Nested rack / chain traversal | **N** (0 `chain` mentions in device.py; only `track_index` substrings contain "rack") | Y (`RackDevice`, `Chain`, `DrumChain`, `ChainMixer`) | Y (`RackDevice.chains[]`, `Chain.devices[]`) | Y | Biggest AbletonOSC coverage gap |
| Browser search/load/preview | N | Y (`application.browser`, `load_item`, `preview_item`; undocumented publicly) | **N** (no browser; can't scan folders) | Y | Undocumented ⇒ version fragility |
| Groove pool read + assign | P (`has_groove` read; `groove` commented out with OSC type error) | Y (`Groove`, `GroovePool` namespaces) | N in public API doc | Y | Only via Remote Script paths |
| Automation read/write | N in track/song/device handlers | Y (`Envelope` namespace; `automation_state`) | N (no automation object surface in public doc) | Y | KENN marks automation partial already |
| Sends/return routing | Y (return track + mixer LOM) | Y (`MixerDevice`) | Y (`TrackMixer`, returnTracks) | Y | — |
| Meters (track level L/R) | Y (`output_meter_level/left/right` getters) | Y | N | Y | Real-time-ish polling only |
| Live audio observation | N | N (only meters) | N; `renderPreFxAudio` offline pre-FX render | Y (M4L device) | LivePilot ships an M4L Analyzer for this |
| Undo | Y atomic (`undo`/`redo`) | Y atomic + **grouped steps** (`begin_undo_step`/`end_undo_step`) | Y (`withinTransaction`, nested collapse) | Y | Grouped steps undocumented in public LOM |
| Stable object identity across moves | N (index-based) | N (index/name based) | N (handles invalidate on move) | N | KENN fingerprints remain the answer |
| Warp markers write | N (OSC type error) | **X** (add/move report success, change nothing — Live 12.4.3) | N | Y | Never promise this |
| Third-party plug-in params | Y if automatable (PluginDevice via LOM) | Y | Y (`DeviceParameter`) | Y | Name-resolve, never index-persist |
| Bundle as one-file install | N (Remote Scripts folder copy) | N (Remote Scripts folder copy) | Y (`.ablx` via Settings → Extensions) | N (`.amxd` + Max needed) | Extensions beta-only, Suite-only |
| Closed-source commercial redistribution | Y (MIT) | Y (MIT) | **[?]** (downstream calls the SDK package non-redistributable; read the licence in the SDK zip before shipping) | [?] (Max terms to read) | Owner/legal gate |

## What KENN should watch or adopt (ranked, effort S/M/L)

1. **Adopt the evidence-labelling taxonomy in outputs (S).** LivePilot separates measured audio, setup-derived heuristics, and artistic judgement in every report ([README v1.30.0](https://github.com/dreamrec/LivePilot)). KENN's grade/proposal receipts should carry the same three labels; it is a wording + schema change, not an architecture change. **First step:** add the three labels to the grade/proposal receipt schema and render them on one existing recipe card (`glue_drum_bus`).
2. **Use `display_value` / `str_for_value` / `value_items` in the readback layer (S).** LOM exposes GUI strings and enum names ([DeviceParameter LOM](https://docs.cycling74.com/apiref/lom/deviceparameter/)); KENN's typed proposals become more explainable with zero new transport. The vendored bridge already carries `get parameter/value_string`. **First step:** return `value_string` alongside raw values from the existing parameter inspect route for one device and show both in the readback card.
3. **Key project memory to the Live Set identity (S).** `Song.name`/`Song.file_path` are readable (LOM), and LivePilot's "memory follows the Live set rather than ordinary edits" is the proven pattern. **First step:** hash `file_path` + `name` into the memory key and add a FakeLiveBackend test proving a renamed copy starts clean.
4. **Adopt context economy for MCP tool exposure (M).** LivePilot reduced its advertised surface to 28 entry points out of 474 callable tools. KENN's MCP handlers should advertise a small named core and keep the long tail discoverable, especially on a 16 GB M3 serving a local model. **First step:** snapshot current advertised-tool schema token count, then define the named core and move the rest behind a discovery tool; re-measure.
5. **Steal producer-pal's field-notes discipline (S).** Its `arrangement-operations.md` (verified against Live 12.4.3) documents exactly which writes silently no-op. **First step:** create `docs/field-notes/ableton-osc-quirks.md` seeded with the groove/warp comment-outs, issue #212's callback bug, and the producer-pal-verified arrangement limits; keep it per bridge surface.
6. **Qualify a browser path via KENN's vendored Remote Script (M).** `application.browser` + `load_item`/`preview_item` exist and ableton-js proves them ([Browser.py](https://github.com/leolabs/ableton-js/blob/master/midi-script/Namespaces/Browser.py)); it is undocumented publicly, so it needs a feature handshake and real-Live qualification. This must be added to the vendored AbletonOSC handler (single write authority), not by installing a second bridge. **First step:** add a capability probe that reports whether `application.browser` exists, with a fake-backend test and an explicit refusal path when absent.
7. **Watch the Extensions SDK for a companion `.ablx` (M now, L later).** Decision gate = the producer-pal revisit triggers (MIDI-instrument/post-FX render or freeze/flatten, plus move-stable identity) *and* stable-channel availability *and* a readable SDK licence. Until then it is Suite-beta-only and cannot be the sole path. **First step:** owner downloads the SDK zip and captures the licence text; that single document unblocks or kills any `.ablx` distribution decision.
8. **Watch the extension-native MCP cluster (Loophole et al.) (S to monitor).** If any of them ships a polished `.ablx` with broad coverage, it becomes the UX benchmark for KENN's install story; their "SDK never in the source tree" packaging rule is also the right default while the SDK licence is unknown. **First step:** subscribe to Loophole releases and the `#extensions-gallery` channel; re-check monthly.
9. **Consider adopting the Loophole test-split shape (M).** A `LiveBridge`-style port (they call it exactly that) formalises what KENN's `FakeLiveBackend` already does; if KENN adds an extension path later, the same port keeps it Live-free for CI. **First step:** write the one-page port boundary for the future extension adapter against the existing `FakeLiveBackend`; no code until the `.ablx` gate opens.
10. **Track LivePilot's confidence gates and 3-way exploration (M).** "Quick creative requests take a quick path. Three-way exploration, broad memory reads, and full critic passes are reserved for real ambiguity." **First step:** map that policy onto the planner shadow gates (L4) as a design note; test with ambiguity/missing-range cases already in the L4 corpus.

## Avoid list

- **Do not adopt copyleft/BSL code into the product:** producer-pal (GPL-3.0-or-later), LivePilot (BSL-1.1, not open source), live-wire (GPL-3.0), Paulstretch for Live (GPL-2.0), Noise Canvas (AGPL-3.0), and no-licence repos such as jasper-zheng/ableton-sdk-mcp. Ideas are fine; code is not, under KENN's licence policy. (xiaolaa2/ableton-copilot-mcp is MIT — reusable in principle, but it is a competing bridge, not a dependency candidate.)
- **Do not reuse track-coach's Demucs pipeline without a weights decision:** the repo is MIT, but its Demucs dependency does not carry MIT weights — Demucs author adefossez, issue #327 (open since 2022-05-05), comment 2022-05-23: "The model weights are not covered by the MIT license, and are provided only for scientific purposes." Read its technique list as ideas; do not vendor the models.
- **Do not redistribute or depend on SDK tarballs** (`extensions-sdk-*.zip`, `vendor/*.tgz`); `@ableton-extensions/{sdk,cli,create-extension}` scoped npm names are not publicly installable, and a downstream project describes the package as "non-redistributable". Read the licence inside the zip before any `.ablx` distribution decision — no public text exists, and the docs-page "GitHub" pointer is a documentation site, not a source repo.
- **Do not promise writes that are verified broken:** warp-marker add/move (no-ops on Live 12.4.3), arrangement resize of warped looped clips, mid-clip "split" semantics. Also don't advertise groove assignment via OSC until the object-serialisation seam is engineered (upstream comments it out with a recorded OSC type error).
- **Do not treat the Extensions SDK as the path to transport, real-time audio/MIDI, browser/library scanning, or stable identity** — none exist there today, officially.
- **Do not build what Live 12.4 now does natively:** stem separation UX (incl. per-time-selection + stem merge), audio streaming between machines (Link Audio), lesson content (Learn View). KENN's differentiation is measurement, judgement, and controlled editing, not these primitives.
- **Do not build against the public LOM docs alone** for Browser/groove/take-lane paths; they are absent there. Either qualify via a real session or keep them behind feature handshakes.
- **Do not assume AbletonOSC will be maintained upstream** (last push Nov 2025, 34 open PRs, no releases). Plan to own any fix through KENN's vendored copy (pin `88b08476…`, already carrying PR #173's `insert_device` extension), and consider a thin superset handler inside that copy if browser/rack gaps block roadmap items — not a second bridge.
- **Do not copy LivePilot's BSL grant reading casually:** "You may make production use of the Licensed Work, provided your use does not include offering it as a commercial hosted service to third parties." That still forbids nothing KENN might do with *code*, but BSL violates KENN's "clean for closed-source" policy; treat as reference reading only.
- **Do not enable telemetry by default** in anything KENN ships; ahujasid's anonymous telemetry is a contrast example, not a norm to follow for a local-first product.

## Verified vs inferred

### Verified [V] (checked 2026-10-15 unless dated otherwise)
- Live stable 12.4.6 (2026-09-15) with full point-release dates and contents from [ableton.com release notes](https://www.ableton.com/en/release-notes/live-12/); 12.4 = 2026-05-05 with Link Audio/Erosion/Chorus/Delay/stem commands/Learn View; 12.4.6 contains exactly one bugfix; the Max-for-Live "unstored" fix is the last item of 12.4.5; no 12.4.4 section; stable notes contain no Extensions-SDK mentions.
- Beta 12.4.15b7 dated 2026-10-15 and the entire Extensions-related beta history (12.4.5b3 → 12.4.15b7) from [the beta release-notes page](https://www.ableton.com/en/release-notes/live-12-beta/), including verbatim b7/b6/b5/b1 and 12.4.5b4/b3 items.
- Extensions SDK announcement 2026-06-02 (blog dated June 2, 2026) and FAQ wording (free SDK; "third-party Extension developers may choose to charge"; Suite Beta only; explicit can't-do list; "Settings → Extensions"; Node v24.16.0+; "<5MB"; support disclaimer) from [blog](https://www.ableton.com/en/blog/introducing-extensions-sdk/), [FAQ](https://help.ableton.com/hc/en-us/articles/27303428331420-Ableton-Extensions-FAQ), [landing](https://www.ableton.com/en/live/extensions/), [docs landing](https://ableton.github.io/extensions-sdk/).
- Extensions API object model (1.0.0-beta) — [ableton-extensions-skill reference/api.md](https://github.com/Ronvaknins/ableton-extensions-skill/blob/master/reference/api.md) (community doc, cross-checked against beta notes and producer-pal).
- SDK npm reality: scoped packages not found; placeholder `ableton-extensions-sdk` published 2026-06-18 by `hdj-ableton` — [registry.npmjs.org](https://registry.npmjs.org/); tarball-vendoring rules — [paulstretch .gitignore](https://github.com/olilarkin/paulstretch-for-live/blob/main/.gitignore), [Loophole CONTRIBUTING](https://github.com/OthmanAdi/loophole/blob/main/CONTRIBUTING.md).
- Extension runtime behaviours: install confirmation dialog; Extension Host crash semantics; `withinTransaction`; `renderPreFxAudio` — beta notes + [Protocol0 README](https://www.npmjs.com/package/@protocol0/extension-sdk) + API doc above.
- producer-pal ADR-0007 (accepted 2026-06-28, investigation dated 2026-06-23) and field notes — [ADR](https://github.com/adamjmurray/producer-pal/blob/main/dev/decisions/0007-no-native-ableton-extension.md), [why-not write-up](https://github.com/adamjmurray/producer-pal/blob/main/docs/how-it-works/why-not-an-extension.md), [arrangement-operations](https://github.com/adamjmurray/producer-pal/blob/main/dev/live-api/arrangement-operations.md).
- AbletonOSC repo state: MIT, 827★, 161 forks, created 2021-05-02, pushed 2025-11-19, 0 releases, 39 open issues + 34 open PRs = 73; #212 (2026-06-20); module inventory incl. `constants.py`; device.py `chain`/`rack` reality; clip.py groove/warp comment-outs with error text; track.py arrangement thinness; device value listeners + `str_for_value` — GitHub API + master source.
- KENN vendor pin `88b08476a2d24406dce54ef5f45d516c9affbf72`, "Pin source: the upstream `insert_device` extension in PR #173" — repo `integrations/ableton-osc/KENN_VENDOR_METADATA.md`.
- ableton-js repo/npm/releases/namespaces/undo-step calls/Browser.load_item/39031/HMAC-SHA256 — [github.com/leolabs/ableton-js](https://github.com/leolabs/ableton-js), npm registry; 5.0.1 GitHub release absent from npm.
- LOM facts (Song undo/redo/record/current_song_time/file_path; DeviceParameter display_value/str_for_value/is_quantized/value_items; Device class_name/can_have_chains/latency/AB-compare; Track take_lanes/duplicate_clip_to_arrangement/insert_device; Application children view+control_surfaces; `/browser/` 404; no begin/end_undo_step on Song page) — [docs.cycling74.com LOM pages](https://docs.cycling74.com/apiref/lom/).
- All repo stars/licences/push dates in Q6 via GitHub API on 2026-10-15; LivePilot licence text (BSL 1.1, Licensor Pilot Studio, "LivePilot 1.30.0", change date April 13, 2030 → MIT) via raw LICENSE; producer-pal GPL-3.0-or-later via LICENSE file; track-coach MIT; sheet-music-extension MIT/46★.
- Live 13 absence: three ableton.com URLs 404; boost.audio 2026-08-27 article exists — [boost.audio](https://boost.audio/en/news/ableton-live-13-w-2026-roku-rzeczywistosc-vs-spekulacje) (weak secondary).

### Inferred [I]
- Stability classification of undocumented-but-working APIs (begin_undo_step, application.browser) and the recommendation to gate them behind feature handshakes.
- All "what this means for KENN" judgements, ranked adoption items, and effort sizes.
- Mapping of extension capability gaps onto KENN roadmap items (browser, transport, fixtures).

### Carried [R]
- The boost.audio article's existence/content as a weak secondary source (not re-read in full this pass).
- The 14 Oct doc's repo list as the comparison baseline; today's numbers supersede individual entries.
- Previous-run methodology note: its `websearch` returned no results for every query; it used curl to DuckDuckGo HTML + direct fetches + GitHub API. This takeover reproduced the same websearch failure and relied on direct fetches, GitHub API/`gh`, npm registry and raw source only. If a discovery engine would have surfaced a very recent news item, it would not appear here.

### Unverified [?] / gaps
- **SDK licence text**: Centercode-gated; not read (no-install rule). Public pages do not carry it. Strongest public evidence: Loophole CONTRIBUTING's "non-redistributable SDK package" and two repos' vendoring rules. Flag for owner/legal before any `.ablx` commercial distribution.
- **Max for Live commercial redistribution terms**: not verified in this pass.
- **"12.4.4"**: no public release-notes section; existence/nature unknown.
- **Previous run's "Live 13 Beta" community reference**: could not reproduce; treat the claim as dead unless the original source is re-found.
- **LivePilot "474 tools / 57 domains"**: vendor-stated in its README, not independently counted.
- **"Ableton has said today's permission model will harden into a stricter sandbox"** (producer-pal): official statement not located; treat as their report.
- **AbletonOSC master vs the KENN pin**: source checks were run against upstream `master` (2025-11-19) and spot-checked against the vendored pin; deep diff of pin vs master not performed.
- **Extensions sample `.ablx` files on Ableton's CDN**: download URLs observed on the landing page; files not downloaded (no-install rule), so their contents/licences inside the zips were not inspected.

## Corrections vs the previous run

| Previous claim | Status after re-verification |
|---|---|
| Live stable 12.4.6; 12.4 shipped 2026-05-05; beta 12.4.15b7 | **Confirmed exactly** (beta b7 dated 2026-10-15). Added: full point-release dates; Extensions absent from stable notes; 12.4.4 section missing |
| "12.4.6 = one Live bugfix + one Max for Live bugfix (unstored non-automatable params)" | **Corrected**: 12.4.6 contains exactly one bugfix (the render/bounce hang). The "unstored" Max-for-Live fix is the last item of the **12.4.5** section |
| No public Live 13 pages (404) | **Confirmed** (3 URLs). The "community extension dev references Live 13 Beta" sub-claim could **not be reproduced** — downgraded to [?] |
| Extensions = public beta, announced 2026-06-02, Suite-only, macOS+Windows, run-once right-click, no observers/transport/real-time | **Confirmed and expanded** (full API object model, grouped undo, pre-FX render, webviews, Extension Host, install confirmation) |
| SDK licence confidential; forbids redistributing SDK tarballs; devs may charge; no public licence text or store | **Partially verified**: devs may charge (FAQ, verbatim); no store; SDK not on public npm; new public docs landing page exists but carries no licence; **new evidence**: Loophole CONTRIBUTING calls the SDK package "non-redistributable". Licence wording itself still unreadable publicly — [?], owner/legal flagged |
| AbletonOSC: MIT, ~827★, last push 2025-11-19, no releases, ~73 open issues/PRs; no browser, no rack/chain traversal, no automation, arrangement read-only | **Confirmed, with sharper numbers**: 39 open issues + 34 open PRs; device-parameter listeners, meters, and undo/redo DO exist; only three arrangement properties; groove/warp_markers comment-outs are upstream master's, with the exact OSC error text. **One sub-claim corrected**: device.py has no "rack type checks" — the only `rack` substrings sit inside `track_index` (3 occurrences) |
| ableton-js active, MIT, v5.0.4 2026-10-12; "Live 12.3 LOM dump verifies begin_undo_step/end_undo_step, str_for_value, Browser.load_item, duplicate_clip_to_arrangement, take lanes" | **Version/npm confirmed** (with the 5.0.1-not-on-npm nuance). The "12.3 LOM dump" artefact was not located; each item was **re-verified independently**: grouped undo via ableton-js source + Push framework mirrors; str_for_value/display_value via DeviceParameter LOM; Browser.load_item via ableton-js Browser.py (public LOM `/browser/` 404s); duplicate_clip_to_arrangement and take_lanes via Track LOM page |
| ahujasid/ableton-mcp ~3,190★ MIT; producer-pal GPL-3.0-or-later; LivePilot BSL-1.1, 474 tools, M4L analyzer + undo-boundary discipline, pushed today | **All confirmed** (verbatim licence texts read this pass). LivePilot licence details added (Licensor Pilot Studio, "LivePilot 1.30.0", change 2030-04-13 → MIT, production-use grant except hosting); ahujasid telemetry "can be disabled" + one-instance warning; producer-pal from LICENSE |
| (New findings this run, not in the previous conclusions) | Extensions-SDK-native MCP cluster (loophole, next-live-mcp, ulm0, idx3d, jasper-zheng); Protocol0 localhost-HTTP/OpenAPI contract; producer-pal ADR + field notes; Ableton-owned npm placeholder; ableton-js Browser/Chain coverage; `xiaolaa2/ableton-copilot-mcp` (93★) |

### 15 Oct takeover review (this pass — what changed and why)

Scope: every headline claim, every licence claim and every quoted licence string above was re-checked today against primary sources (ableton.com release notes ×2, Extensions landing/blog/FAQ/docs landing, legal + EULA pages, GitHub API + licence endpoints, raw LICENSE files, npm registry, raw source of AbletonOSC/ableton-js/Browser.py/song.ts/Config.py/Socket.py, producer-pal docs, LivePilot/Protocol0/Loophole/ahujasid/next-live-mcp READMEs). Changes made:

1. **12.4.6 vs 12.4.5 attribution fixed** (above) — the previous draft gave 12.4.6 a second bugfix that belongs to 12.4.5. Fixed by re-reading both sections from the page source.
2. **AbletonOSC `rack` detail fixed**: "4 rack mentions are type checks" → zero rack code; 3 raw substrings inside `track_index`. The "0 chain mentions" claim survives.
3. **AbletonOSC module list completed** with `constants.py` (verified from the directory listing).
4. **ableton-js release-cadence nuance added**: v5.0.1 exists on GitHub (2026-09-15) but is absent from npm — pin from the registry.
5. **Install path corrected to "Settings → Extensions"** per the official FAQ (the draft twice said "Preferences").
6. **SDK licence status sharpened**: added the public docs landing page and its "public beta only" wording; documented that the blog's "GitHub repository" pointer resolves to a docs site, not a source repo (ableton/extensions-sdk 404); added the Loophole "non-redistributable" quote and the legal/EULA checks that came up empty. Status stays [?] with the owner/legal gate.
7. **Distribution facts added**: Ableton's own CDN serves sample `.ablx` zips; Discord channel names; support disclaimer.
8. **Q6 refreshed**: amitbaz pushed 2026-10-15 (17 open issues); added `track-coach` (MIT, measurement-first, Demucs weights caveat, with the adefossez quote); clarified Noise Canvas as standalone app *and* `.ablx`; noted composing-sidekick depends on Producer Pal's MCP device (protocol-level, licences do not contaminate).
9. **Vendored-pin provenance added** (`88b08476…`, PR #173 source) from `KENN_VENDOR_METADATA.md` — strengthens the "we own the fix, on top of an unmerged PR" reading.
10. **12.2 LOM citation sharpened** to 12.2b16 (May 7, 2025) with verbatim text.
11. **Marker convention aligned**: `[U]` → `[?]`, `[R]` introduced for carried claims; no unverifiable claim is marked [V].
12. **Ranked list made actionable**: each of the 10 items now carries effort (S/M/L) plus a first concrete step, and item 6 explicitly routes browser qualification through the vendored Remote Script (AbletonOSC stays the sole write authority).
13. **Wording**: "Preferences → Extensions" cells in the matrix changed to "Settings → Extensions"; matrix licence cells marked [?] with the downstream evidence.

Not changed (kept deliberately): structure, section order, tables, the provenance notes about the earlier runtime-loss runs and the previous methodology limit (websearch returns nothing here; direct fetches only), and all [R]/[I] items where re-verification was impossible today.

