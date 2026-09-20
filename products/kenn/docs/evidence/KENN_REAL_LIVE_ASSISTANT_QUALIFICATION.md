# KENN real-Live assistant-task qualification

## Purpose

`scripts/qualify_assistant_live_task.py` proves that KENN can carry one
model-planned task through fresh Live inspection, confirmation-only proposal,
explicit apply, verified receipt, replay rejection, identity-bound undo, and
exact final-state restoration. It complements action-specific Live qualifiers;
it does not replace them or authorize autonomous use.

## Safety boundary

- Use only the disposable qualification set and a reversible, already-qualified
  action.
- Run proposal-only mode first and review the exact target and before/after
  values.
- `--apply` is explicit authorization for one mutation and its immediate undo.
- Stop if the companion, Ableton, model endpoint, target identity, or proposal
  differs from the reviewed setup.
- A transport-uncertain apply is never retried. Inspect the session-scoped
  receipt journal and fresh Live snapshot before any further action.
- If replay verification fails after a confirmed write, qualification fails
  closed but the runner still attempts and verifies the identity-bound undo.
- An interrupted undo is never retried. The runner performs a fresh context
  read, records whether the initial fingerprint was restored, and requires
  receipt/snapshot inspection plus manual restoration when it cannot prove it.
- Unexpected or malformed apply responses trigger one read-only, session-bound
  snapshot reconciliation and never retry the write. An unchanged fingerprint
  records that no persistent change was observed; a changed or unavailable
  fingerprint remains transport-uncertain with explicit manual recovery
  requirements. Provider error text is redacted.
- Malformed non-object apply, undo, or final-context responses follow the same
  fail-closed recovery path and never cause an uncertain write to be retried.
- The initial context must carry the exact requested session identity and a
  non-empty snapshot fingerprint before any write is allowed. Final and
  recovery snapshots must match that session before they can prove restoration.
- The output removes confirmation tokens. It can still contain track/device
  names, so treat it as internal evidence.

The runner talks to the existing KENN companion and local Ollama endpoints. It
does not open an AbletonOSC socket, start a model service, or restart any host
component. Output evidence is written atomically with owner-only permissions;
an interrupted write cannot leave a partial release artifact at the requested
path.
Context events retain the session identity, snapshot fingerprint, connection
status, track count, and available-action scope, but omit the full track list,
producer preferences, and other unrelated session contents. The reviewed plan
and exact proposal still contain the target identity required for audit.

### Qualified Transformers checkpoint on the GPU host

The qualified Qwen checkpoint does not need to be imported into or served by a
shared Ollama installation. `scripts/serve_transformers_ollama_compat.py`
provides only the `/api/chat` subset required by Kenn. It is a disposable user
process, binds to remote loopback, requires `CUDA_VISIBLE_DEVICES=1,2,3,4`, and
rejects model paths outside `/mnt/data`. It never restarts or changes a service.
The process also pins Hugging Face and Transformers caches below the declared
data root, overriding inherited cache variables so qualification cannot write
model data outside `/mnt/data`. It permits one inference at a time, returns
HTTP 429 instead of accumulating blocked GPU requests, and rejects tokenized
prompts above 8,192 tokens before generation.

Copy the script to a project directory below `/mnt/data`, then launch it from
the GPU host's existing Python environment:

```sh
CUDA_VISIBLE_DEVICES=1,2,3,4 python3 /mnt/data/<kenn>/scripts/serve_transformers_ollama_compat.py \
  --model-path /mnt/data/<qualified-qwen-checkpoint> \
  --model-id Qwen3-4B-input-bound-v6 \
  --data-root /mnt/data \
  --host 127.0.0.1 \
  --port 11435
```

From the Ableton Mac, create a separate SSH local-forward session for that
loopback port. The qualification runner can then keep its safe loopback-only
transport and use `--ollama-url http://127.0.0.1:11435`. Stop the disposable
Python process and SSH tunnel after qualification; do not restart the host,
drivers, Ollama, containers, schedulers, or any other service.

## Procedure

First perform a non-mutating review:

```sh
PYTHONPATH=source python3 scripts/qualify_assistant_live_task.py \
  --model <qualified-local-model-tag> \
  --goal "Inspect the selected disposable track, then prepare the requested reversible pan adjustment" \
  --command "Set the selected disposable track pan to 10%" \
  --output /tmp/KENN_REAL_LIVE_ASSISTANT_PROPOSAL.json
```

Only after reviewing that output and confirming the target set is disposable,
repeat with `--apply` and write the release artifact:

```sh
PYTHONPATH=source python3 scripts/qualify_assistant_live_task.py \
  --model <qualified-local-model-tag> \
  --goal "Inspect the selected disposable track, then prepare the requested reversible pan adjustment" \
  --command "Set the selected disposable track pan to 10%" \
  --apply \
  --output evaluation/results/KENN_REAL_LIVE_ASSISTANT_TASK.json
```

The qualified-beta gate accepts the artifact only when the planner ID exactly
matches the recommendation in `KENN_DELIBERATIVE_MODEL_BAKEOFF.json`, both
forward and undo receipts are verified, exact replay is rejected, no secret
field is present, the assistant task ledger reaches `completed`, and the final
snapshot fingerprint equals the initial one. If Live applies but optional task
bookkeeping fails, the runner still attempts and verifies the identity-bound
undo; the set is restored but the qualification remains failed.
Before contacting Live, the CLI also verifies the requested model name against
that recommendation, derives the provider identity from the bake-off, and
hashes the exact bake-off artifact. The lifecycle receipt stores all three, and
the release gate recomputes them; reusing the same model label through a
different provider or with replaced qualification evidence cannot pass. The
Ollama-compatible HTTP shape is only a transport detail: the GPU bridge receipt
correctly retains the qualified `transformers` provider identity.

Proposal-only, blocked, failed, transport-uncertain, or incompletely restored
results never satisfy the gate.
