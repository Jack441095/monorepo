# KENN Internal Beta 0.1

## Current release decision

The current evidence supports a **supervised pilot** on the single
configuration listed in `ABLETON_LIVE_SUPPORT_MATRIX.json`. It does not yet
support a qualified internal beta, autonomous operation, destructive project
edits, or public Ableton release.

The recorded qualified-profile gate run from earlier on 2026-09-07 passed
**5/7 then-required gates**. The release policy now has **14 required gates**:
it additionally enforces the intelligence benchmarks, reconnect-aware 24-hour
soak, consented real-mix evaluation, supervised-pilot evidence, and exact
release provenance described below. The thirteenth gate requires a complete,
input-bound, three-repeat deliberative-model bake-off with 100% trajectory,
contract, safety, and recovery results. That planner gate now passes using
`evaluation/results/KENN_DELIBERATIVE_MODEL_BAKEOFF.json`; changing any bound
runner, planner, evaluator, recovery, or sealed-suite file invalidates it. The recorded result
therefore predates the stricter policy and is not a current qualified-beta
approval. The current full regression suite passes **643 tests**. The result is recorded in
`ABLETON_INTERNAL_BETA_0.1_GATE_2026-09-07.json`. This run reused the captured
real-Live qualification evidence and did not claim that Live was currently
connected. Immediately before a supervised session, rerun the gate with
`--check-live` to require a fresh AbletonOSC snapshot. The stricter qualified
profile remains not ready because independent human review and a Developer ID
signed/notarized plug-in archive are still absent. The source-snapshot and
automated-suite gates now pass.

The fourteenth gate requires one model-planned real-Live assistant trajectory
through inspection, proposal, explicit confirmation, verified apply, replay
rejection, identity-bound undo, and exact snapshot restoration. Its runner is
documented in `KENN_REAL_LIVE_ASSISTANT_QUALIFICATION.md`; the evidence remains
pending until Ableton, the companion, and the qualified local model are
available together on the disposable set.

A fresh current-runtime pilot preflight at 15:58 BST on 2026-09-07 passed all
**5/5** required gates against Ableton Live 12.4.5: the AbletonOSC-backed
snapshot was connected and the complete suite passed **590 tests** in 119.73
seconds. This confirms readiness at that instant only; `--check-live` remains
mandatory before each later supervised session.

Evaluate the decision from the repository root with:

```bash
python3 scripts/qualify_internal_beta.py --profile pilot --run-suite
```

Immediately before a live pilot session, add `--check-live`:

```bash
python3 scripts/qualify_internal_beta.py --profile pilot --run-suite --check-live
```

That preflight requires the current AbletonOSC-backed KENN companion to answer
a fresh read-only snapshot; a blocked result means the session must not begin.

The stricter qualification profile is:

```bash
python3 scripts/qualify_internal_beta.py --profile qualified --run-suite \
  --run-intelligence \
  --plugin-host-report evaluation/results/KENN_PLUGIN_HOST_VALIDATION.json \
  --soak-report evaluation/results/KENN_COMPANION_24H_SOAK.json \
  --real-mix-report evaluation/results/KENN_REAL_MIX_EVALUATION.json \
  --pilot-report evaluation/results/KENN_SUPERVISED_PILOT_EVALUATION.json \
  --reviewer-a /path/to/reviewer-a.json \
  --reviewer-b /path/to/reviewer-b.json \
  --adjudication /path/to/adjudication-decision.json
```

Prepare two independent blank reviewer forms outside the repository with:

```bash
python3 scripts/export_human_review_forms.py --output-dir /secure/review/forms
```

Each reviewer must complete only their own form, enter a distinct reviewer ID,
and set `independent_review_confirmed` to `true` only after working without
seeing the other reviewer's scores. The forms are bound to the packet hash.
The adjudicator rejects blank identities, copied identities (case-insensitive),
or either missing independence confirmation.

Before reporting missing reviewers, the qualified gate validates the packet's
generator and question-corpus hashes, complete active-index/model identity,
source ancestry, and that no answer-engine input changed after generation. If
the packet is stale, rebuild it before distributing forms; do not continue a
review against superseded answers.

Validate both completed forms and create a blank, input-bound decision file:

```bash
python3 scripts/adjudicate_human_review.py \
  --reviewer-a /secure/review/forms/reviewer-a.json \
  --reviewer-b /secure/review/forms/reviewer-b.json \
  --output /secure/review/adjudication-summary.json \
  --decision-template /secure/review/adjudication-decision.json
```

The adjudicator reviews the summary, disagreements, and notes, then edits only
`status`, `release_decision`, `adjudicator_id`, `disagreements_reviewed`, and
`adjudicator_notes`. Set `disagreements_reviewed` to `true` only after that
review is complete. The qualified gate verifies that both forms retain their
assigned `a`/`b` slots and schema, and that the final decision names an
adjudicator, confirms disagreement review, and is bound to the exact packet
and both reviewer files; a blank, stale, swapped, or copied decision cannot
pass.

The packet also binds quantitative release floors to its own SHA-256 identity:
the two-reviewer combined mean must be at least 1.7/2 overall, at least 1.8/2
for technical correctness, evidence use, safety, and overclaiming control, and
at least 1.5/2 in every represented category. An adjudicator may reject a
numerically passing result, but cannot approve a numerically failing result.
Changing this policy invalidates previously exported forms by changing the
packet hash.

The gate is fail-closed. It never treats missing human scores, a narrative
claim, or a mock/simulator result as real-Live approval.

After packaging, copy
`evaluation/review/PLUGIN_HOST_VALIDATION_TEMPLATE.json` outside the repository
and test the exact archive from a clean local macOS account or a second Mac.
Record its SHA-256, source commit, and the Developer Team ID shown by the
signed bundles, then mark AU validation, VST3 validation, Ableton discovery
for both formats, rollback, timestamp, and tester sign-off.
Save the completed privacy-safe receipt as
`evaluation/results/KENN_PLUGIN_HOST_VALIDATION.json` (or pass its secure path
with `--plugin-host-report`). Local codesign, stapler, and Gatekeeper success
without this exact-archive host receipt remains pending rather than passing.

## Pilot boundary

The pilot is limited to a small supervised cohort using disposable Ableton
sets and the qualified Live/OS configuration. The interaction contract is:

`Inspect -> Explain -> Propose -> Confirm -> Apply -> Verify -> Undo`

Allowed operations are the real-qualified read-only snapshot, supported track
and transport controls, and the named EQ Eight, Compressor, and Utility
parameters documented in the qualification report. Every mutation must show
the target, before/after values, confirmation state, verified readback, and
undo path.

Record each session with the privacy-safe
[pilot run-log template](ABLETON_INTERNAL_BETA_0.1_RUN_LOG_TEMPLATE.md).
The Markdown log is useful for human notes, but qualification uses a separate
copy of `evaluation/review/PILOT_SESSION_LOG_TEMPLATE.json` for each run.
Aggregate the ten completed JSON logs with:

```bash
python3 scripts/evaluate_supervised_pilot.py \
  --log /secure/pilot/run-01.json \
  --log /secure/pilot/run-02.json \
  --log /secure/pilot/run-03.json \
  --log /secure/pilot/run-04.json \
  --log /secure/pilot/run-05.json \
  --log /secure/pilot/run-06.json \
  --log /secure/pilot/run-07.json \
  --log /secure/pilot/run-08.json \
  --log /secure/pilot/run-09.json \
  --log /secure/pilot/run-10.json \
  --output evaluation/results/KENN_SUPERVISED_PILOT_EVALUATION.json
```

Project identity must be a stable SHA-256 pseudonym, never a project/client
name or path. Tester identity must also be a stable SHA-256 pseudonym. Every
log must target the exact release-candidate commit.

At the end of each session, create a session-filtered privacy-safe receipt
bundle beside that session's JSON log:

```bash
python3 scripts/build_support_bundle.py \
  --session-id <local-session-id> \
  --output /secure/pilot/run-01-support.zip
shasum -a 256 /secure/pilot/run-01-support.zip
```

Record only the bundle's sibling filename and SHA-256 in the session log. The
evaluator verifies its support-bundle schema, exact source revision, every
manifest file hash, and enough receipt events for every declared mutation and
undo. Duplicate, encrypted, or oversized ZIP members are rejected, and each
session must use distinct evidence. The local session ID filters the HTTP
request but is not stored in the archive or aggregate report.

Auto mode, clip loading, device creation through the bridge, batch mutation,
stem separation, voice control, destructive project operations, and calibrated
LUFS/LRA/true-peak claims remain outside this pilot.

## Evidence still required for full qualification

- Two independent completed human-review score files and an explicit
  adjudication decision.
- A Developer ID signed, notarized, stapled, Gatekeeper-accepted plug-in archive
  and matching checksum produced by `scripts/package_macos_plugins.sh`.
- A qualified 24-hour companion soak receipt with at least one observed Live
  disconnect/reconnect and a connected final state.
- A qualifying consented real-mix receipt covering at least 12 cases scored by
  two independent reviewers.
- A qualifying ten-session supervised-pilot receipt spanning at least three
  hashed project identities with zero recorded safety incidents.
- Additional Live/OS or device coverage if the supported matrix is expanded.

The exact-release provenance gate hashes the source revision, active retrieval
index and embedding model, support matrix, plug-in archive and clean-host
receipt, technical qualification receipts, planner bake-off, real-Live
baseline and assistant lifecycle, soak, real-mix and pilot results, human-review
packet, both reviewer files, and the final adjudication. Missing evidence keeps
the gate pending; replacing any completed artifact changes the release identity.

New soak runs checkpoint every sample atomically with owner-only permissions.
Partial checkpoints always carry `qualified=false` and
`progress.complete=false`; the release gate rejects them even if another field
is altered to claim qualification. Only the final complete 24-hour artifact can
satisfy the soak gate. Legacy artifacts without a complete progress block,
current harness hash, sequential raw samples, and independently recomputable
memory/thread/reconnect facts are rejected. An older diagnostic run may still
inform engineering, but it cannot be promoted to current release evidence.
