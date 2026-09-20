# Thursday security review — 2026-09-08

First security-focused review of the work done in this development cycle (23
commits, `2053c2b..78db984`), prompted by the decision to aim Thursday at
eventual commercial sale. Scope was the newly-added and recently-modified
code only, not a whole-codebase audit.

## Scope

New: `thursday/llm_provider.py`, `thursday/mcp_client.py`,
`thursday/training_export.py`, `thursday/evals/brain_benchmark.py`,
`thursday/evals/training_corpus.py`.
Modified: `thursday/specialists.py`, `registry/handlers.py`,
`registry/system.py`, `client.py`, `plan_memory.py`, `feedback.py`,
`brain.py`, `orchestrator.py`, `response_rewrite.py`, and (in the sibling
`Audio_Too` repo) `business/agents/{Marketing,Research}/{main,agent_loop}.py`.

Threat model used: free-text chat input from the user over HTTP
(Tailscale-bound, token-authed), CLI, and voice is the primary untrusted
input. The existing security model — `thursday/confirmation.py`'s HMAC-signed
expiring tokens binding `session_id + service_id + sha256(text)`, gating
everything `registry/core.py` classifies as `LOCAL_MUTATION`,
`EXTERNAL_COMMUNICATION`, or `DESTRUCTIVE` — is what new code was measured
against.

## Result: no HIGH or MEDIUM exploitable findings

Six data flows were traced specifically, all safe:

| Flow | Verdict |
| :--- | :--- |
| Chat text → `_handle_marketing_agent`/`_handle_research_agent` → `client._run_agent` → `subprocess.run` | **Safe.** Argument-vector form, no `shell=True` anywhere in `client.py`. `agent_path` and `sub_command` are hardcoded literals at every call site; only trailing fields carry chat text, and the agent `main.py` files parse `sys.argv` positionally (no argparse), so a field starting with `-` can't be reinterpreted as an option. |
| Chat text → `_handle_specialist_task` → `run_grounded_specialist` → ops evidence gatherers | **Safe.** Three of four gatherers take no arguments and read fixed module-resolved paths. The two that use the objective treat it as data only — substring match against in-memory FAQ dicts, and embedding input for cosine similarity. No path, glob, or SQL is built from user text. `specialist_id` is selected from a fixed 6-key dict. |
| `mcp_client.call_tool` confirmation check | **Sound.** Verification runs before execution with no bypass path. The binding is canonical (`json.dumps(..., sort_keys=True)`) and HMAC covers session + service + arg hash + expiry + nonce. (One latent replay gap found and fixed — see below.) |
| `auto_approve=True` in the agent CLI entry points | **Not reachable, but wrong — fixed.** See below. |
| `plan_memory.py` SQL | **Safe.** Every value-bearing statement parameterized. The two f-string statements interpolate only generated `?` placeholder lists. `ALTER TABLE ... ADD COLUMN` interpolates identifiers exclusively from the hardcoded `_NEW_COLUMNS` module constant. FTS `MATCH` is built from `\w+` tokens, which can't contain a quote or FTS operator. |
| `training_export.py` | **Safe.** Writes only to a caller-supplied path, atomically. No default/implicit destination, no in-repo caller passing untrusted text as the path. |

## Two LOW latent issues — both fixed same day

### 1. `auto_approve=True` in the agent CLI entry points

`Audio_Too/business/agents/{Marketing,Research}/main.py` passed
`auto_approve=True`, justified in a comment claiming Thursday's confirmation
gate had already vetted any request reaching that subprocess. **That
justification was factually wrong**: `request_risk("marketing_agent", <drafting
text>)` returns `PROPOSAL`, which requires no confirmation — nothing upstream
had approved anything.

Not exploitable as written, because the dispatched commands route to
`_generate_content()`/`generate_llm()` and never touch `run_task()`/
`agent_loop`, which is the only consumer of the flag. But it left a live
footgun: re-pointing any of those functions back at `run_task()` (exactly what
they did before this cycle) would have handed unconfirmed chat text a fully
auto-approved coding loop with write and commit rights across the Audio_Too
tree. `CodingAgent/permissions.py`'s `auto_approve` short-circuit disables the
whole rule table, including the `write_file "*" → DENY` default.

**Fixed** (`Audio_Too` commit `fc0b438`): pass `False` (the default). Nothing in
these paths reads the flag, so it costs nothing. Verified the original
interactive-hang problem does not return — a real subprocess call completed in
54.5s with real content, no hang. Noted in-code that if the hang ever does
return, the correct fix is a non-interactive **deny** mode in
`PermissionManager` (fail closed), never a blanket approve.

### 2. MCP confirmation tokens were not single-use

`mcp_client.call_tool()` verified the confirmation token but never consumed it.
`thursday/confirmation.py` holds no single-use state itself — replay prevention
lives in `thursday/action_receipts.py::claim_action`, which the macro and
plan-resume paths already use and this module didn't. A captured token could
re-fire the identical external tool call repeatedly within its 300s TTL.

Harmless while `MCPToolProvider` had no callers outside tests, but this has to
be correct *before* a real external platform is wired behind it, not after.

**Fixed** (commit `61e8c55`): `call_tool()` now claims the token via
`claim_action(receipt_id_for_token(token), ...)` after verifying it, and refuses
a replay with an explicit single-use message. Regression test asserts the same
valid, unexpired token executes once, is refused on replay, and that the replay
never reaches the transport.

## Known, accepted, documented

`thursday/redaction.py::redact()` is deliberately pattern-based — it catches
credential *shapes* (bearer tokens, `*_API_KEY=` assignments, known token
prefixes) and does **not** remove ordinary PII (client names, emails, message
bodies) that a user pastes into chat. That text lands verbatim in
`plan_memory.sqlite3`, `feedback.jsonl`, and any training export.

This is intentional and already documented, but it has a direct consequence for
the commercial goal: **treat the training export as user-data-bearing, not as a
sanitised artifact.** Before any export leaves the machine it was generated on
— to a GPU box for fine-tuning, to a customer, to a third party — it needs a
real PII pass, not just `redact()`. Tracked in
`docs/THURSDAY_LONG_TERM_PLAN.md` under the data-governance workstream.

## Recommended cadence

This was the first such review. For a product intended for sale, repeat it at
minimum: before any real external platform integration goes live (MCP), before
any training data leaves the machine, and before a first external user is
onboarded.
