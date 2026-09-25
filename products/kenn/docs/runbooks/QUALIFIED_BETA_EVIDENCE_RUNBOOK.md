# Qualified beta evidence runbook

This runbook turns the qualified-beta gate into an operator checklist. It does
not grant approval, create review scores, or replace a disposable Live set.
Freeze the source revision before beginning evidence collection; a source or
harness change can invalidate a receipt.

## Current state

As of the current `develop` candidate, the qualified-beta gate reports **7
passed, 1 failed, and 6 pending** gates. The failed gate is the stale
real-Live assistant receipt, which is bound to an older source/planner
revision and must be regenerated during a fresh Ableton-enabled
qualification. The remaining work is evidence collection:

- independent human answer review and adjudication;
- signed/notarized plug-in and clean-host validation;
- one disposable-set real-Live apply/readback/replay/undo lifecycle;
- a reconnect-aware 24-hour soak;
- consented real-mix review; and
- a ten-session, three-project supervised pilot.

Never put audio, project files, raw prompts, personal paths, credentials, or
private Live-set names in review receipts unless the respective schema and
consent process explicitly allow them.

## 1. Freeze and capture the candidate

Record the exact commit, keep the candidate clean, and take a read-only Live
preflight when a disposable set is open:

```bash
git rev-parse HEAD
python3 scripts/qualify_ableton_live.py --mode real --endpoint http://127.0.0.1:8090 \
  --output /absolute/evidence/current-live.json
```

This probe uses the running companion HTTP endpoint and does not compete for
AbletonOSC's reply socket. It performs no Live mutation.

## 2. Human answer review

Give the packet and a separate blank form to each independent reviewer. They
must work without seeing one another's scores, supply distinct `reviewer_id`
values, set `independent_review_confirmed` to `true`, and complete every case.

```bash
python3 scripts/adjudicate_human_review.py \
  --packet docs/ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json \
  --reviewer-a /absolute/evidence/reviewer-a.json \
  --reviewer-b /absolute/evidence/reviewer-b.json \
  --output /absolute/evidence/human-review-adjudication.json \
  --decision-template /absolute/evidence/human-review-decision-template.json
```

The command validates scores and reports disagreement. An authorized
adjudicator must review disagreements and create the final decision; KENN must
not infer it from averages.

## 3. Automated and intelligence receipts

Run these only while the candidate source is frozen. The full test suite can
be CPU-intensive; run it at a suitable time on the intended machine.

```bash
python3 scripts/qualify_internal_beta.py --profile qualified --run-suite \
  --automated-suite-report /absolute/evidence/automated-suite.json \
  --output /absolute/evidence/qualified-beta-after-suite.json

python3 scripts/qualify_internal_beta.py --profile qualified --run-intelligence \
  --intelligence-report /absolute/evidence/intelligence.json \
  --output /absolute/evidence/qualified-beta-after-intelligence.json
```

The intelligence receipt includes hard-case grounding, retrieval modes,
session-grounded evidence, assistant recovery, and Arrangement intelligence.
Neither command opens Ableton or authorizes a Live write.

## 4. Disposable real-Live lifecycle

Use a clearly disposable set and one bounded reversible operation. Capture a
proposal, explicit confirmation, verified readback receipt, replay rejection,
and exact undo. Do not run this against an irreplaceable production set.

Use the existing real-Live qualification tooling and store its resulting
privacy-safe receipt outside the repository. The qualified gate requires the
receipt to bind the exact source revision and prove the full lifecycle; a
read-only preflight alone is not enough.

## 5. Reconnect-aware 24-hour soak

Start this from a normal interactive Terminal so macOS does not terminate it
when an automation shell exits. Do not restart the companion or GPU server
merely to start the soak. Record the actual companion PID first:

```bash
ps -ax -o pid=,command= | rg 'apps/backend/src/kenn/server.py'
python3 scripts/soak_companion.py --pid <PID> \
  --endpoint http://127.0.0.1:8090 \
  --duration-seconds 86400 --interval-seconds 60 \
  --min-ableton-reconnects 1 --max-ableton-outage-seconds 300 \
  --require-ableton-connected-end --max-thread-growth 8 \
  --output /absolute/evidence/companion-24h-soak.json
```

Manually close and reopen Live once during the run to exercise the reconnect
gate; the harness only observes it and never injects a failure or mutation.
Follow the reconnect procedure in [OPERATIONS.md](OPERATIONS.md) exactly. A
partial run, missing reconnect, unhealthy sample, unbounded state, or wrong
source/harness revision does not qualify.

## 6. Consented real-mix evaluation

Prepare a consented, privacy-safe manifest and keep the audio root outside the
repository. The preparation command creates review material; it does not
approve the result:

```bash
python3 scripts/evaluate_real_mix_corpus.py prepare \
  --manifest /absolute/evidence/real-mix-manifest.json \
  --audio-root /absolute/consented-audio \
  --packet /absolute/evidence/real-mix-packet.json \
  --reviewer-a-template /absolute/evidence/real-mix-reviewer-a.json \
  --reviewer-b-template /absolute/evidence/real-mix-reviewer-b.json
```

After independent review and adjudication, score the completed review using
the script's `score` subcommand and store the output in the evidence folder.

## 7. Supervised pilot

Log ten supervised sessions spanning at least three projects with the
privacy-safe session-outcome contract, then aggregate:

```bash
python3 scripts/evaluate_supervised_pilot.py \
  --log /absolute/evidence/supervised-pilot-log.jsonl \
  --matrix docs/evidence/ABLETON_LIVE_SUPPORT_MATRIX.json \
  --source-revision "$(git rev-parse HEAD)" \
  --output /absolute/evidence/supervised-pilot.json
```

Do not add raw prompts, audio, or project names to the log. Each mutation must
remain explicitly confirmed and receipt-backed.

Recording one session, straight after it ends (each session needs at least one applied change and one undo):

```bash
python3 tooling/scripts/build_support_bundle.py --output ~/kenn-pilot/s01.zip
python3 tooling/scripts/record_pilot_session.py --bundle ~/kenn-pilot/s01.zip \
  --project "Tester A, song 1" --tester "Tester A" --started-at 2026-09-27T14:05:00+01:00
```

The recorder counts changes and receipts from the bundle, asks how many were undos, then walks through the
pre-flight checklist, the safety questions and the tester's sign-off. Project and tester names are hashed on the spot
and never written. It checks the log with the same evaluator as the gate and says what's missing if it won't count.

## 8. Signed plug-in distribution

This is an Apple-release-owner task. First run the non-mutating preflight:

```bash
bash scripts/package_macos_plugins.sh --preflight
```

It requires a Developer ID Application identity and an Apple notarytool
keychain profile. The packager intentionally refuses to publish unsigned or
ad-hoc artifacts. After signing, notarization, stapling, checksum generation,
and clean-host AU/VST3/Ableton/rollback validation, provide the exact archive,
checksum, and host-validation receipt to the gate.

## Final gate

Only after every receipt is complete, evaluate the exact candidate:

```bash
python3 scripts/qualify_internal_beta.py --profile qualified --check-live \
  --reviewer-a /absolute/evidence/reviewer-a.json \
  --reviewer-b /absolute/evidence/reviewer-b.json \
  --adjudication /absolute/evidence/human-review-decision.json \
  --plugin-archive /absolute/evidence/KENN-Mix-Assistant-macOS.zip \
  --plugin-host-report /absolute/evidence/plugin-host-validation.json \
  --soak-report /absolute/evidence/companion-24h-soak.json \
  --real-mix-report /absolute/evidence/real-mix-evaluation.json \
  --pilot-report /absolute/evidence/supervised-pilot.json \
  --real-live-assistant /absolute/evidence/real-live-assistant.json \
  --automated-suite-report /absolute/evidence/automated-suite.json \
  --intelligence-report /absolute/evidence/intelligence.json \
  --output /absolute/evidence/qualified-beta-final.json
```

Treat `ready_for_qualified_internal_beta` as evidence of this exact candidate
only. Any source, artifact, harness, or receipt change requires re-evaluation.
