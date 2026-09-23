# KENN Investor Demo Live Qualification — 2026-09-23

## Scope

This record covers the checked-in Ableton Live 12 topology fixture, the full
demo preflight, and one bounded two-step mutation recipe exercised repeatedly
against real Live through the KENN HTTP and AbletonOSC control path.

It does **not** claim that the complete 20-step investor narrative has passed
or that the generated stems have been imported and rehearsed in Live ten times.

## Environment

- Ableton Live 12 Suite with AbletonOSC listening on UDP 11000/11001
- KENN companion on `127.0.0.1:8090`
- `KENN_ALLOW_DAW_CONTROL=1` only for the supervised qualification window
- Fixture: `assets/demo/KENN_Live12_Demo.als`
- Fixture SHA-256: `ee15b701f44d17b0656b5cd127842b315a1912ebf70a307d342dea8c1cf41279`

## Fixture load/readback

The checked-in `.als` file was opened directly in Live after generation. KENN
then read back:

- Eight exact tracks: Kick, Snare / Clap, Hi-Hats, Drum Bus, Bass, Synth,
  Lead Vocal, and FX Print
- Compressor on Drum Bus
- EQ Eight on Bass, exposing 84 readable parameters
- Compressor on Lead Vocal
- A-Reverb containing Reverb followed by Hybrid Reverb

The file is a valid gzip-compressed Live Set with 317,175 bytes of expanded
XML, replacing the previous 357-byte placeholder.

## Full preflight result

`tooling/scripts/demo_preflight.py --allow-mutations --json` completed all
11 checks in 9.62 seconds:

- OSC ping: 21.5 ms
- Exact demo topology: passed
- Server health: passed
- Retrieval: available in explicit BM25-only mode
- DAW write boundary: confirmation and readback reported
- Grounded track-count Q&A: 100.2 ms
- Bass EQ and required return-chain identity: passed
- Known-good WAV analysis: passed
- Confirmed set plus exact undo round-trip: passed
- Frontend HTTP response: passed
- Command latency: 185.2 ms

The first supervised run exposed an ambiguous client timeout after Live had
already applied the pan probe. The set was immediately restored and the probe
was hardened to wait for the bounded mutation/readback path before requesting
the inverse. The repeated run then passed and restored the original pan.

## Ten-run recipe qualification

`tooling/scripts/qualify_ableton_live_recipe.py` was exercised ten consecutive
times against Bass (`track_index=4`) and its EQ Eight (`device_index=0`). Each
recipe performed these two steps:

1. Set Bass pan from `0.0` to `0.15`.
2. Set exact parameter `1 Gain A` from `0.0` to `1.0` dB.

For every run, KENN:

- returned a confirmation-bound recipe proposal;
- applied both steps with verified readback;
- rejected replay of the consumed proposal/idempotency key;
- generated a fresh inverse recipe from the verified receipt;
- applied the inverse with verified readback; and
- independently re-read Bass pan and `1 Gain A` as `0.0`.

Result: **10/10 consecutive passes**, zero partial successes counted.

## Automated regression

The latest full backend suite completed after the atomic-EQ, chat-routing, and
frontend-polish work:

`1410 passed, 5 skipped, 4 warnings in 77.33s`

The Vue frontend also completed all 18 Vitest checks and a production Vite
build. These automated checks do not replace the manual projector rehearsal.

The skip count includes optional/environment-dependent coverage. The warnings
are existing HTTP-test and audio compatibility deprecations; there were no
test failures.

## Remaining demo gates

- Import the generated original stems into a disposable Live copy and verify
  audible playback against the manifest-bound analysis renders.
- Rehearse the complete scripted UI flow, deliberate fault recovery, reset,
  projector layout, and 8–12 minute timing ten consecutive times.

## Original audio fixture evidence

`tooling/scripts/build_investor_demo_audio.py` now deterministically renders
`Neon Proof`, a 16-bar/32-second D-minor electronic composition. The generator
uses no samples, external recordings, model weights, or third-party musical
material. Its local manifest binds eight Live stems plus separate full-mix and
isolated-vocal evidence WAVs by SHA-256 and labels them `generated-internal`.

KENN's production analyzer measured the 48 kHz render as follows:

- Full mix: -0.070 dBFS sample peak, -11.574 dBFS RMS, and a strongest low-band
  deviation of +19.413 dB at 43.504 Hz against the anchored pink-noise-style
  diagnostic baseline.
- Isolated lead-vocal texture: -0.044 dBFS sample peak, 3,091 near-full-scale
  samples across 314 runs, producing the bounded high-confidence clipping
  finding.
- The mix also produced informational masking and resonance hypotheses. These
  remain listening prompts, not proof of a defect or an automatic processing
  instruction.

The preflight audio check now fails closed unless both files are present,
rights-cleared under the expected manifest schema, hash-matched to their roles,
and the actual chat-analysis responses bind themselves to those exact hashes
while still containing the intended low-end and vocal-clipping cues. The check
also warms a four-entry content-addressed analysis cache. In the measured Live
runtime, repeat low-end and vocal requests fell from about 2.6 seconds each to
190.63 ms and 207.82 ms respectively, both below the 650 ms command budget.

## Narrative correction

The canonical runbook now says `Focus EQ Eight on track 5` instead of inserting
a duplicate device. The following command is also band-specific:

`Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.`

Against the checked-in fixture, the focus request resolved exactly to Bass
track index 4, EQ Eight device index 0, with the previously selected Drum Bus
Compressor recorded in the proposal. The gain request resolved exactly to
`2 Gain A`, from 0 dB to 3 dB.

One bounded narrative rehearsal then confirmed both exact proposals. Live
verified the Bass/EQ Eight selection, verified `2 Gain A` at 3 dB, generated a
fresh inverse from `Undo that`, verified the inverse readback at 0 dB, and an
independent reproposal observed 0 dB as the restored baseline. This is one
successful sequence, not the required ten-run full-script qualification.

The real-Live command surface also resolved the canonical read-only and safety
phrases for track count, selected track, session overview, duplicate names,
low-end advice, vocal-clipping advice, receipt history, destructive track
deletion, and maximum master level. Vocal Compressor Output and hard-left Synth
pan both stopped at exact confirmation proposals during this audit.

## Non-mutating script-contract gate

`tooling/scripts/demo_script_gate.py --runs 10` completed **10/10 consecutive
passes** against the real AbletonOSC-backed demo session. It exercised 130
read-only or proposal-only command requests across scripted steps 2–9, 11–13,
15, and 16. No confirmation token was submitted and no Live mutation was sent.
Every response matched its exact target/refusal/advice contract; the slowest
reported command was 452.7 ms, below the 650 ms budget.

The gate paces requests below the supervised HTTP rate limit and stops at the
first contract or latency failure. It deliberately reports
`full_demo_qualified=false`: steps 1, 10, 14, and 17–20 still require the real
UI, confirmed mutation/readback/undo, receipt presentation, and roadmap
narration. This evidence does not replace the remaining full rehearsal gate.

## Post-restart read-only preflight

After restarting the companion with the manifest-bound analysis paths, the
full preflight was run without `--allow-mutations`. Ten of eleven checks passed
in 1.79 seconds: Ableton ping was 87.5 ms, the eight-track topology matched,
the session question returned in 100.1 ms, the exact Bass EQ and required
return chain resolved, the analysis cache was warmed, the frontend returned
HTTP 200, and the command round-trip was 171.4 ms. The undo round-trip reported
the expected explicit skip because no confirmed Live change was authorized.

A subsequent warmed non-mutating script-contract run passed all thirteen
covered prompts. Its slowest request was the proposal-only Compressor Output
step at 411.5 ms wall time, below the 650 ms budget.

## Atomic EQ and real chat-surface routing

The additional compound command `add an EQ to Synth and boost band 2A by 3 dB
at 5 kHz` now resolves to one confirmation token covering insertion, band
enable, frequency, and gain. The service performs per-control readback,
compensating removal on partial failure, a final all-control readback, and an
identity-bound exact undo. A dedicated qualifier defaults to proposal-only and
refuses to operate if the target chain is not empty. Its confirmed `--apply`
path remains pending real-Live qualification on the disposable rehearsal set;
no confirmed mutation was attempted for this update.

The actual Vue chat route was also exercised with `Pan the Synth hard left.`
after a companion restart. `/kenn/api/ask` returned the typed `set_pan`
proposal for Synth at `-1.0`, `changed=false`, and a bound confirmation token.
The UI rendered the proposal card, it was dismissed without applying, and the
status bar continued to report `Last action: None yet`. This closes the earlier
gap where the same sentence fell through to a generic Auto Pan knowledge
answer while preserving the confirmation boundary.

## Shadow-evidence integrity

The promotion audit found that repeated full test runs had appended 31 copies
of the same synthetic `mute track 2` conflict fixture to the default local
shadow log. Every row had the same command and mismatch, no session or model
provenance, and was produced by the promotion-stage cap test—not by studio use.
The rows were excluded from promotion evidence and moved intact to the ignored,
recoverable runtime quarantine.

The backend test harness now redirects both in-process and spawned-server
shadow writes to a session-scoped temporary log. A focused test and the full
1,410-test suite verified that the production evidence path remained absent.
The durable promotion state was not changed and remains at `shadow`; no model
stage was promoted from synthetic data.
