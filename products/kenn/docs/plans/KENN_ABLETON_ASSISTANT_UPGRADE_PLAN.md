# KENN Ableton Assistant Upgrade Plan

Planning baseline: 2026-09-01 readiness report. Current decision: **not ready**. The repository is locally useful, but wider Ableton Live qualification and independent human review remain open.

## Upgrade objective

Move KENN from “tested local assistant with mocked Live control” to “qualified internal Ableton beta,” while keeping the public web beta and Ableton beta as separate release decisions.

The next release should earn its claims in this order:

`safe boundary -> real read-only Live state -> one real reversible write -> supported write set -> evidence quality -> beta qualification`

## Internal Beta 0.1 gate — implemented

The release decision is now executable through
`scripts/qualify_internal_beta.py`. The `pilot` profile requires the release
artifacts, explicit supported Live/OS matrix, captured real-Live evidence, and
a fresh passing regression suite. The `qualified` profile additionally
requires two complete independent human reviews, an explicit adjudication
approval, and a clean reviewed source snapshot. The first pilot run passed
4/4 required gates with 200 tests; it authorizes supervised disposable-set
piloting only. The Mix Review performance gate now passes at 3.40 ms mean
latency against the documented <100 ms target.

## Next execution slice — 2026-09-02

The next work is evidence closure, not feature expansion. The current Live
runtime slice is now complete: `KENN_Bridge` answered a fresh snapshot, and all
seven supported track/transport operations passed verified restoration and
replay rejection.

1. Export the two packet-bound human-review forms, obtain independent scores,
   and adjudicate them without entering scores on behalf of reviewers.
2. Review the current worktree as one release snapshot, then create a neutral
   release commit with no AI-related tags or wording.
3. After the pilot, expand one device/OS configuration at a time and update
   the support matrix only when fresh real-Live evidence exists.

Until steps 1–2 are complete, the correct claim remains “ready for a
supervised disposable-set pilot,” not “qualified internal beta.”

## Priority 0 — close the mutation boundary

This is the highest-risk gap because the repository still contains legacy HTTP Live-write routes alongside the newer planner/executor path.

Tasks:

1. Create one `LiveActionService` used by the tool registry, autonomous tools, server routes, and UI.
2. Route volume, pan, mute, solo, arm, play, and stop through Inspect → Propose → Confirm → Execute → Read back → Receipt.
3. Disable or return a clear `410 unsupported` response from direct legacy OSC mutation routes until they use that service.
4. Make proposal records persist enough state to survive a process restart, or explicitly invalidate all pending proposals on restart.
5. Make token consumption atomic and bounded with expiry cleanup; keep request binding, session binding, exact target/value binding, and replay rejection.
6. Add idempotency keys so timeout retries cannot apply a confirmed action twice.
7. Ensure every failed write/readback/undo returns a failure state and never a success-shaped response.

Exit gate:

* Static audit finds no reachable Ableton mutation path that bypasses the service.
* Adversarial tests cover forged, expired, replayed, stale, changed-target, changed-value, timeout, and partial-failure requests.
* Unauthorized mutation count is zero.

## Priority 1 — qualify the real Live read-only boundary

No amount of mock testing can close the current primary blocker. Use a disposable Ableton Live 12 set and record the evidence described in `docs/ABLETON_LIVE_TEST_PROCEDURE.md`.

Tasks:

1. Verify `KENN_Bridge` loads as a real `ControlSurface` after Live restart.
2. Capture a real session snapshot containing Live version if available, tempo, transport, tracks, indices, names, volume, pan, mute, solo, arm, devices, and parameters.
3. Add a snapshot `session_version`/hash generated from the actual returned state.
4. Measure OSC request, response, and readback latency, including packet timeout behavior.
5. Compare Remote Script values against Live’s visible UI for representative audio, MIDI, return, group, and master tracks.
6. Confirm that unknown tracks/devices/parameters are refused and duplicate names require clarification.

Exit gate:

* Real read-only snapshot passes on the supported Live version and OS.
* No mock result is included in the real-Live qualification report.
* Connection loss produces an understandable offline state without a write.

## Priority 2 — qualify one real reversible mutation

Start with one device parameter, then add track controls only after the first path is proven.

Tasks:

1. Use a real Compressor or EQ Eight parameter returned by Live, not a hardcoded parameter index. **Implemented locally:** native EQ Eight `Output` was resolved by name from Live and qualified on the disposable set.
2. Test the full flow: inspect, plan, display, confirm, write, read back, receipt, undo, read back again. **Implemented locally:** EQ Eight `Output` passed verified write/readback, replay rejection, fresh inverse, and final restoration.
3. Manually change the parameter between proposal and confirmation and verify stale rejection. **Implemented locally:** Live was moved from 1 to 2 dB after a 1 → 4 proposal, and the original proposal was rejected with no successful write.
4. Kill/restart the companion between proposal and confirmation and verify the documented behavior. **Implemented locally:** a fresh process rejected the process-bound confirmation token without a receipt or write.
5. Test native Live undo separately from KENN’s receipt undo. **Implemented locally:** Live Cmd-Z restored a separate guarded EQ Eight write and left the device present.
6. Qualify volume, pan, mute, solo, arm, play, and stop one at a time. **Implemented locally:** the real runner passed all seven independently, including setup/cleanup for the stop direction.

Exit gate:

* One real parameter mutation and undo are verified in a disposable set.
* Each supported operation has a real receipt and readback record.
* A failed readback is classified as failure, never “applied_unverified” success.

## Priority 3 — make audio analysis product-visible and auditable

The KENN-owned analyzer is now useful locally, but the public Mix Review path must expose it consistently before spectral claims are made to users.

Tasks:

1. Make the upload/API path return `analysis.spectral_evidence` with the documented schema.
2. Add UI cards for measured peak, RMS, crest factor, clipping, correlation, mono drop, dominant peaks, and limitations.
3. Add version comparison using input hashes and comparable analysis settings.
4. Add resource limits and benchmark fixtures for long files, high sample rates, and concurrent requests.
5. Add time-localized FFT windows before increasing the strength of resonance/harshness/masking hypotheses. **Implemented locally:** the result now carries bounded source-time windows and the UI displays them; this remains an audit aid, not a continuous STFT or source-separation claim.
6. Only implement BS.1770 LUFS/LRA and true peak if a release requirement justifies the added calibration burden. If implemented, validate against published/reference fixtures and expose algorithm metadata.

Exit gate:

* Every displayed number maps to a field in the versioned result schema.
* Spectral hypotheses retain uncertainty, listening tests, and limitations.
* No RMS proxy is labelled LUFS and no sample peak is labelled true peak.

## Priority 4 — upgrade assistant intelligence evaluation

The original 16/16 intent result was a deterministic fixture result, not a general intelligence qualification.

Tasks:

1. Expand the held-out set to at least 100 cases across beginner, intermediate, expert, analysis, Ableton, ambiguous, unsupported, and adversarial categories. **Implemented locally:** the 108-case deterministic boundary/coverage holdout reports precision/recall/F1, clarification/abstention/refusal accuracy, and category accuracy; it is not independent human review.
2. Add independent human review for intent, technical correctness, evidence use, Ableton practicality, uncertainty, citation support, clarity, completeness, and overclaiming.
3. Report precision, recall, F1, clarification accuracy, abstention accuracy, citation accuracy, and human usefulness by category.
4. Add paired tests proving whether an LLM changes correctness or merely paraphrases retrieved notes. **Implemented locally:** the deterministic grounding gate accepts a factual paraphrase and rejects a structured candidate with an unsupported measurement and fabricated citation; a provider-backed LLM run remains pending.
5. Remove stale `Audio_Too` provenance labels from KENN-only evaluation outputs, or clearly mark the remaining historical dependency. **Implemented locally:** the Ableton holdout receipt identifies the repository-owned KENN engine, disables LLM synthesis, and has a regression test rejecting legacy labels.
6. Add prompt-injection fixtures in filenames, WAV metadata, notes, track names, and device names. **Implemented locally:** fixtures cover all five input surfaces, and retrieved-note context is explicitly delimited as untrusted reference text before optional LLM synthesis.

Exit gate:

* ≥90% held-out audio-engineering correctness.
* ≥95% supported-action intent correctness.
* ≥95% citation support accuracy.
* ≥99% ambiguity/unsupported clarification or abstention accuracy.
* Zero absent-audio and absent-Live overclaims.

## Priority 5 — UX and operational release hardening

Tasks:

1. Ensure the UI distinguishes Ask, Inspect, Analyse, Suggest, Assist, pending confirmation, applied/readback verified, undo, and disabled features.
2. Add Live freshness timestamp and stale-state warning to every proposal card.
3. Show exact before/after values, target identity, valid range, evidence, confidence, risk, and undo state.
4. Add safe error cards for offline Live, stale proposals, failed readback, and partial rollback.
5. Add session history and before/after mix comparison without retaining source audio unnecessarily.
6. Add support diagnostics that redact tokens, audio, personal paths, and project content. **Implemented locally:** `/api/support/diagnostics` is loopback-only and returns an allow-listed payload with explicit redaction fields and tests.

Exit gate:

* A tester can tell whether KENN advised, inspected, proposed, changed, verified, undid, or refused something without reading logs.
* Rollback and support procedures work from a fresh installation.

## Release sequence

### Milestone A — boundary-safe internal build

Complete Priority 0. All Live writes use one service; Auto remains disabled.

### Milestone B — Live observer build

Complete Priority 1 on one supported Live/OS configuration. Read-only inspection only.

### Milestone C — Ableton internal beta

Complete Priority 2 for one device parameter plus volume/pan/mute/solo/arm/play/stop, with real receipts and undo. Use only disposable sets and a small tester cohort.

### Milestone D — evidence-qualified assistant beta

Complete Priorities 3 and 4. Keep source-aware masking, mastering approval, AutoMix rendering, stem separation, destructive project edits, and Auto mode disabled unless separately qualified.

### Milestone E — public web decision

Evaluate chat/upload privacy, rate limits, hosted processing, and support independently. Public web readiness must not be used as evidence of Ableton readiness.

## Explicitly defer

AutoMix rendering, stem separation, voice control, project deletion/overwrite, automatic arrangement changes, source-aware masking diagnosis, professional mastering approval, and silent Auto mode. These add scope without closing the current highest-risk qualification gates.

## Working commands

```bash
python3 apps/backend/src/kenn/main.py build
python3 -m pytest -q
python3 scripts/eval_mix_review.py
PYTHONPATH=source python3 scripts/benchmark_audio_analysis.py
python3 scripts/qualify_ableton_live_device.py --track-index 0 --device-index 0 --parameter-name "Output" --value -1
python3 scripts/eval_ableton_assistant.py
./scripts/start_server.sh
python3 scripts/install_remote_script.py --list-paths
python3 scripts/install_remote_script.py --target "$HOME/Music/Ableton/User Library/Remote Scripts"
```

The real-Live evidence package must include the Live version, OS, disposable set hash, Remote Script log, snapshot, request/response IDs, latency, receipts, readback values, undo result, and any failures.

## Current autonomous execution status — 2026-09-01

Implemented locally: the supported track/transport mutation boundary,
confirmation/idempotency/readback/undo tests, fail-closed unsupported routes,
the KENN spectral analysis endpoint and two-file comparison endpoint, UI
evidence cards, provenance-labelled real/mock qualification, a local UDP
Remote Script simulator, and a 128-case public chat coverage receipt with
84 grounded-answer cases and 44 expected abstentions. The 108-case
deterministic Ableton boundary/coverage holdout passes 108/108 with
precision, recall, F1, clarification, abstention, and refusal accuracy of
1.00 and category breakdowns. Real Live 12
read-only inspection, the supported track/transport subset, and EQ Eight,
Compressor, and Utility device parameters have now also passed on the disposable local set; the
repeatable runners are `scripts/qualify_ableton_live_mutations.py` and
`scripts/qualify_ableton_live_device.py`. The bounded spectral resource
benchmark (`scripts/benchmark_audio_analysis.py`) passes long-file, high-rate,
and four-worker concurrency cases. Bounded time-localized FFT windows are now
included in the spectral result and displayed in the UI, with transient-fixture
regression coverage. The repository-wide suite is green.
Confirmation tokens are process-bound, so pending proposals are explicitly
invalidated on companion restart even when a configured root secret is used.
Legacy AudioGen clip-loading side effects were removed from the orchestrator
and chat routing paths; clip loading remains explicitly disabled pending a
typed reversible proposal.
The legacy batch-device executor is also fail-closed by default; its rollback
tests require an explicit compatibility opt-in while batch migration remains
open.
The installed managed Remote Script copy has also been refreshed with
bridge-level guards for unsupported direct mutation addresses.
Prompt-injection fixtures now cover Live names, WAV metadata/filenames, and
retrieved-note excerpts; note context is explicitly marked as untrusted
reference text before optional LLM synthesis.
The paired rewrite gate accepts a factual paraphrase and rejects an
unsupported/fabricated candidate against the same evidence; this is a
provider-independent validator test, not an external LLM quality result.
The loopback support-diagnostics endpoint exposes only allow-listed capability
and health summaries; tests verify that tokens, audio, paths, project content,
and raw Live snapshots are excluded.

Live-loss failure classification is also qualified: a pending real Compressor
proposal returned a failure receipt with no readback after Live was terminated;
no success-shaped mutation was emitted. Still open by evidence requirement:
additional device-matrix coverage and wider crash scenarios,
human-reviewed language/evidence scoring, and any calibrated LUFS/LRA or
true-peak implementation. The real track/transport evidence is recorded in
`docs/ABLETON_LIVE_REAL_QUALIFICATION_2026-09-01.md`; mock and simulator
results remain labelled as non-Live evidence. The human-review packet can be
validated with `scripts/adjudicate_human_review.py` once two independent score
files are supplied; no scores or release decision have been fabricated.
