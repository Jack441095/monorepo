# KENN MCP client setup

KENN exposes a local stdio MCP server for an MCP-capable LLM client. The MCP
process does not open AbletonOSC itself; it delegates to the running KENN
companion, which remains the single owner of the Live connection and all
proposal/readback safety checks.

## Start KENN

Start the companion from the repository root, with DAW control explicitly
enabled for a local development session:

```sh
AUDIO_TOO_ALLOW_DAW_CONTROL=1 ./scripts/start_server.sh
```

Verify it before connecting an LLM client:

```sh
curl -sS http://127.0.0.1:8090/api/health
```

The expected response contains `"ok": true` and `"app": "KENN"`.

## Configure an MCP client

The exact configuration file differs by client, but the stdio entry has this
shape. Replace `REPO_ROOT` with the absolute KENN repository path:

```json
{
  "mcpServers": {
    "kenn-live": {
      "command": "/usr/bin/env",
      "args": [
        "PYTHONPATH=REPO_ROOT/source",
        "python3",
        "REPO_ROOT/scripts/kenn_mcp_server.py"
      ],
      "env": {
        "KENN_MCP_COMPANION_URL": "http://127.0.0.1:8090",
        "KENN_DELIBERATIVE_MODEL": "off"
      }
    }
  }
}
```

If the client supports a direct environment map, the equivalent is:

```json
{
  "command": "python3",
  "args": ["REPO_ROOT/scripts/kenn_mcp_server.py"],
  "env": {
    "PYTHONPATH": "REPO_ROOT/source",
    "KENN_MCP_COMPANION_URL": "http://127.0.0.1:8090",
    "KENN_DELIBERATIVE_MODEL": "off"
  }
}
```

The server can also be probed directly:

```sh
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | PYTHONPATH=source python3 scripts/kenn_mcp_server.py
```

## Required LLM interaction pattern

For a producer goal, call `plan_assistant_goal(goal, session_id)`. This is the
preferred unified entry point. Recognized production symptoms route to KENN's
causal, one-hypothesis-at-a-time diagnostic loop and return `workflow=diagnostic`
with a typed `loop` and `next_plan`. Other goals route to the hybrid planner and
return `workflow=deliberative_task` with a persisted task and exactly one
`next_step` directive.

The hybrid path fetches a fresh KENN context, resolves hard policy and identity
boundaries deterministically, and calls the configured loopback Ollama planner
only when semantic planning is still needed. Ollama is constrained to actions
actually available in that context; KENN then hydrates and validates the compact
sketch before persistence. The unified call never changes Live and always
reports `execution_authorized=false`. Continue diagnostic results with
`record_diagnostic_test_result`; continue tasks with
`record_assistant_observation`, proposal/job tools carrying the returned task
and step IDs, and `resume_assistant_task`. A Live proposal still requires the
separate confirmation and apply sequence below. `plan_assistant_task` remains
available as the lower-level generic planner when diagnostic routing is not
wanted.

Diagnostic loops are authoritative server state. `start_production_diagnosis`
persists the returned `loop_id`; subsequent `record_diagnostic_test_result`
calls may send that ID alone. A legacy echoed `loop` is accepted only when it
exactly matches KENN's stored copy. MCP accepts direct caller evidence only as
an explicit `user_observation` with a turn identity; measurements and receipts
must be resolved inside KENN rather than supplied as claims. A fresh-context
check happens before the observation is committed, and concurrent/replayed
advances are rejected atomically.

When `resume_assistant_task` returns `mode=replan`, call
`replan_assistant_task(task_id, session_id)`. If the task is awaiting a producer
clarification, include that answer as `follow_up`. KENN replans against a fresh
context, atomically links the replacement to its source task, and cancels an
active superseded task. It refuses to abandon a pending confirmation or queued
job because their outcomes remain identity-bound and must be resolved first.
Replan chains are capped at eight replacements.

`KENN_DELIBERATIVE_MODEL` defaults to `off`, retaining deterministic policy
preflight while model planning is disabled. Enabling it is an explicit opt-in.
Set `KENN_DELIBERATIVE_PROVIDER` to `ollama` for a real local Ollama model or
`transformers` when using the qualified loopback Transformers bridge; unknown
provider identities fail closed. Optional settings are
`KENN_DELIBERATIVE_OLLAMA_URL` (an uncredentialed loopback HTTP origin only),
`KENN_DELIBERATIVE_TIMEOUT` (clamped to 1–120 seconds), and
`KENN_DELIBERATIVE_MAX_TOKENS` (clamped to 128–1024). If the endpoint is
missing, times out, or returns an invalid sketch, KENN returns an explicit
planning failure and creates no task.

`KENN_MCP_COMPANION_URL` is also enforced as an uncredentialed loopback HTTP
origin. Remote hosts, HTTPS origins, embedded credentials, paths, queries, and
fragments are rejected before the MCP server can send any companion request.
Redirects are not followed, so proposal and mutation payloads remain on that
validated loopback origin even if the companion is compromised or misconfigured.

The client or agent should use this sequence for a Live change:

1. Call `live_snapshot`, `live_devices`, or `live_parameters` when exact
   identity is needed. If a command uses a user-facing unit, call
   `live_parameter_profile` for the exact parameter so raw and displayed
   values are visible before interpreting the request. A display string is
   evidence, not permission to invent a raw-to-display conversion.
   For a session-wide inventory, call `live_device_matrix`; it returns exact
   track/device identities, readable parameter profiles, and qualification
   labels without enabling any write.
2. Call `create_live_proposal` with the user's natural-language command.
3. Show the returned exact target, before value, after value, and reason to the
   user. Do not apply automatically.
4. Only after explicit user confirmation, call `apply_live_proposal` with the
   complete proposal, its confirmation token, session ID, and idempotency key.
5. Report the verified receipt and readback. For reversal, call
   `undo_live_receipt` once to create the inverse proposal, show it, then call
   it again with the exact inverse and confirmation token.

Never send raw OSC addresses, arbitrary Python, device indices invented by the
model, or a free-form model-generated write object. KENN rejects stale identity,
wrong tokens, duplicate idempotency keys, unsupported schemas, failed readback,
and replayed confirmations.

For generated MIDI, keep the workflow explicit: use
`create_midi_clip_from_artifact` or `generate_audiogen_midi_proposal`, show and
confirm the returned MIDI-clip proposal, apply it, then use the returned
`next_actions` descriptor or call `create_clip_audition_from_receipt` with the
verified creation receipt. Show and confirm the separate audition proposal
before applying it. This preserves provenance and prevents the model from
guessing a track or clip slot after import.

After the audition has been heard, call `record_audition_feedback` with the
same verified applied audition receipt and a bounded `keep`, `revise`, or
`reject` verdict. Include a short comment or up to five requested changes when
useful. This records advisory evidence only. Read it back with
`audition_feedback` or let `kenn_context` include it on the next planning
turn; a `revise` result is a prompt for a new proposal, never an automatic
Live change.

For a `revise` response, call `create_audition_revision_brief` with its
`feedback_id` and session id. Use the returned exact target and bounded
listener intent to prepare a new candidate. The baseline audition receipt is
not replaced, and the new candidate must go through the normal proposal,
confirmation, readback, and undo sequence.

To generate a new symbolic candidate from that brief, call
`generate_audiogen_midi_revision_proposal` with the same session, feedback id,
and a new explicit integer seed. KENN preserves the feedback provenance and
rejects any target mismatch before calling the producer. The current AudioGen
producer accepts generation parameters rather than free-form revision prose,
so the brief is evidence for the LLM/planner and does not imply semantic
musical adaptation by AudioGen itself.

When the active assistant step has `action=revise_audition`, also pass its
`assistant_task_id` and `assistant_step_id`. KENN classifies this as a
confirmation-gated Live proposal—not a background generation job—because the
implemented endpoint returns a MIDI-clip proposal immediately. The task waits
for confirmation and completes only when `apply_live_proposal` returns the
matching verified MIDI receipt. Feedback remains server-resolved by
`feedback_id`; callers cannot supply a replacement feedback object.

For a rendered listening candidate, call `generate_audiogen_audio_candidate`
with a bounded prompt and optional emotion/bars. The result contains an
opaque local `audio_url` and `audition.status=ready` when the WAV is available.
This is an offline listen surface only: it does not insert audio into Live or
change any Live state.

For technical A/B evidence, generate or supply two candidate URLs and call
`compare_audiogen_audio_candidates` with `source_a` and `source_b`. KENN
accepts only its opaque local portfolio-audio references, returns hashes and
bounded metric deltas, and rejects arbitrary filesystem paths. The result is
advisory evidence, not an automatic quality ranking. When a listener says
`revise`, pass that comparison object to `create_audition_revision_brief` (or
`generate_audiogen_midi_revision_proposal`) so the planner sees both the
listener request and measured candidate differences. The normal exact-target,
proposal, confirmation, readback, and undo gates still apply.

## Uncertain requests

If `apply_live_proposal` or the applying phase of `undo_live_receipt` returns
`error_kind: "transport_uncertain"`, the client must not retry. First call
`live_receipts` for the session and `live_snapshot` to reconcile the current
state. The receipt journal is redacted and contains no confirmation tokens.

## Current boundary

The KENN MCP server is a local adapter over the existing AbletonOSC backend.
It is not a second Ableton Remote Script and must not be run alongside another
MCP server that binds AbletonOSC's fixed reply port. The current connection is
qualified across Live reads, parameter changes, pan, compound EQ, insertion,
replay rejection, and receipt undo. `create_live_proposal`'s natural-language
path additionally reaches send/return-track control, scene launch, clip-slot
stop, clip audition, and sample import -- see
`docs/evidence/ABLETON_LIVE_SUPPORT_MATRIX.json` for the exact qualified scope; none of
these need their own dedicated MCP tool since they go through the same
generic proposal path as everything else here. Deliberate real ambiguous-write
recovery remains a separate qualification gate.
