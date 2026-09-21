# KENN Ableton capability matrix

`Offline verified` means exercised through fake/simulated Live contracts. It is not a real-Live claim.

| Capability | Implementation state | Safety/verification | Verdict |
|---|---|---|---|
| Inspect tracks/devices/parameters/session | Wired through OSC bridge and HTTP/MCP | Read-only; real probe blocked offline | Working, insufficiently verified |
| Volume, pan, mute, solo, arm | Intent + proposal + execute path | Confirmation, fresh identity, readback, receipt, inverse | Offline verified only |
| Rename/select track; select device | Implemented | Identity and previous-focus receipt | Offline verified only |
| Create audio/MIDI/return track | Implemented | Confirmation and structure fingerprint | Offline verified; return deletion intentionally not automatic |
| Delete/group arbitrary tracks | Grouping exists; general deletion absent | Grouping confirmation/readback; destructive deletion refused | Partial / safer omission |
| Transport play/stop | Implemented | Confirmation/readback; uncertainty status | Offline verified only |
| Tempo | Bridge method exists; natural command not in qualified parser set | No current end-to-end qualification | Bridge-only / partial |
| Scenes | Launch implemented; bridge can create | Launch confirmation/readback; create not high-level qualified | Partial |
| Clip launch/stop | Stop is qualified parser action; launch exists lower-level | Receipt/readback paths vary | Partial |
| MIDI clip create/update/remove/read | Specialist service implemented | Bounds, note parity, confirmation, fingerprint, exact undo | Offline verified only |
| Duplicate/rename clip | Specialist services implemented | Source/target fingerprints and inverse | Offline verified only |
| Move/crop/loop/replace arrangement clips | Some bridge primitives and recipes; no coherent full surface | Incomplete | Missing/partial |
| AudioGen MIDI insert | Typed artifact to MIDI proposal wired | Confirmation and bounded artifact; Live round trip absent | Working contract, unqualified integration |
| Sample import | Specialist service implemented | Library allowlist, proposal, readback, remove inverse | Offline verified only |
| Device insert/configure/remove | Implemented for allowlisted devices | Chain fingerprint, readback, rollback, identity-bound undo | Offline verified only |
| Device bypass/reorder/arbitrary plug-ins | Parser explicitly refuses enable/bypass; arbitrary reorder absent | Fail closed | Missing by design |
| Sends | Exact named-return send supported | Fresh return identity/readback/undo | Offline verified only |
| Routing | Bridge and recipe paths exist | Not in broad natural-language qualification | Partial |
| Locators | Named add/remove at stopped playhead | Toggle-protection, identity/readback/inverse | Offline verified only |
| Arrangement sections | Analyzer/context structures exist | Four synthetic cases; no stable section graph from real set | Experimental |
| Automation | Bridge has clip automation; high-level coverage narrow | Incomplete readback/undo qualification | Partial |
| Loudness/peaks/dynamics/stereo/masking | Offline analysis implemented | Extensive local tests; not Live meter/audio readback | Working offline |
| Exact retry across process restart | In-process tokens and keys only | Restart invalidates pending work; no mutation reconciliation | Missing |

Real qualification command:

```sh
cd products/kenn
PYTHONPATH=apps/backend/src apps/backend/.venv/bin/python tooling/scripts/qualify_ableton_live.py --mode real --output docs/research/results/kenn_audit_ableton_real_qualification_2026-09-21.json
```

Then use a disposable set and the mutation qualification scripts only after explicit operator confirmation. Expected evidence is a real session version, exact pre/post identity, OSC exchange, verified receipt and verified inverse receipt.
