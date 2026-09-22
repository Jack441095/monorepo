# KENN Investor Demo Live Qualification — 2026-09-23

## Scope

This record covers the checked-in Ableton Live 12 topology fixture, the full
demo preflight, and one bounded two-step mutation recipe exercised repeatedly
against real Live through the KENN HTTP and AbletonOSC control path.

It does **not** claim that the complete 20-step investor narrative has passed,
that the empty topology fixture is a polished mix, or that the audio-analysis
segments have been rehearsed with original or royalty-free stems.

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

The latest full backend suite completed after the investor-phrase hardening:

`1359 passed, 12 skipped, 4 warnings in 78.68s`

The skip count includes optional/environment-dependent coverage. The warnings
are existing HTTP-test and audio compatibility deprecations; there were no
test failures.

## Remaining demo gates

- Add original or licensed-for-demo musical material and deliberate audible
  issues before claiming the audio-analysis acts are qualified.
- Rehearse the complete scripted UI flow, deliberate fault recovery, reset,
  projector layout, and 8–12 minute timing ten consecutive times.

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
