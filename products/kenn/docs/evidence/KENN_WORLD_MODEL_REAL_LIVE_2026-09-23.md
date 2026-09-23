# Real-Live proof: AbletonOSC deploy, selection fix, world model (2026-09-23)

Set: `KENN_Live12_Demo_RESET Project` open in Live 12.4.6. Companion on the latest code.

## A3 — first real deploy (hot reload, no Live restart)

`deploy_abletonosc.py --apply --reload` copied `abletonosc/application.py`,
`song.py`, `view.py` (all hot-reloadable), backed up the old copy to
`.runtime/remote-script-backup-20260923-144707`, stamped the deploy, and
`/live/api/reload` loaded it. `/live/kenn/version` then reported content hash
`1335b0f6d1…` at commit `f646979`, matching the repo. Preflight's new
`remote_script` check: "AbletonOSC 1335b0f6d1 (commit f646979) matches the repo".
Read-only preflight: 11/12, the remaining check being the expected undo skip.

## A2 — return/master selection

With the A-Reverb return selected in Live, "What's selected?" answered
"Return track 'A-Reverb' is selected." (status `inspected`, 382 ms). Before
the fix AbletonOSC raised, KENN waited ~1.2 s and reported the selection as
unavailable. The Current Project card now shows "Focus Track: A-Reverb"
instead of falling back to track 1.

## B1 — world model on real Live

`/api/ableton/world-model?refresh=1`: every section available — return tracks,
groups, selected scene/device, locators, routing, session and arrangement clip
inventory, track sends, device trees, return mixers, master, KENN reads. Returns
A-Reverb (Reverb, Hybrid Reverb) and B-Delay (Delay) at volume 0.85; master
"Main" with no devices; Drum Bus device tree reports Live's class
`Compressor2`.

## B3 — questions through the chat route (read-only)

| Question | Answer |
|---|---|
| What's on the A-Reverb return? | 'A-Reverb' has: Reverb; Hybrid Reverb. |
| What's on the master? | The master has no devices. |
| Which tracks send to the reverb? | No track sends to 'A-Reverb' right now. |
| What's the threshold on the Drum Bus compressor? | On 'Drum Bus' → Compressor: Threshold is 0.00 dB. |
| What's the output on the Lead Vocal compressor? | On 'Lead Vocal' → Compressor: Output is 0.00 dB. |
| Is anything muted? | Nothing is muted. Nothing is soloed. |
| What key is the song in? | Live's scale setting is C Major. That is the set's scale setting, not a key detected from the audio. |
