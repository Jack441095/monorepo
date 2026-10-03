# KENN handoff for Claude Cloud, 3 October 2026

Prepared at Jack's request for use while his Mac is off. This document does not
start a cloud task. Jack will say when to use it. Refresh the branch and this
handoff before starting; `KENN_PLAN.md` remains the only roadmap and work queue.

## Checkout and read order

Use the monorepo, branch **`fix/review-critical-2026-10-02`**. The verified source
checkpoint when this handoff was prepared is **`289a6066`**. Fetch the latest branch
and inspect status and history before editing; do not reset or overwrite another
worker's changes. The Mac has many unrelated dirty files, which are not part of
this cloud handoff. Do not import its untracked runtime or private data.

Read the checked-out `AGENTS.md` and `CLAUDE.md`, then:

1. [KENN_PLAN.md](../../KENN_PLAN.md), especially the next executable task and C1–C3.
2. [Recipe dispatch ownership receipt](KENN_A2_RECIPE_DISPATCH_OWNERS_2026-10-03.md).
3. [Anonymous dispatch ownership receipt](KENN_A2_ANONYMOUS_DISPATCH_OWNERS_2026-10-03.md).
4. [Speed research shortlist](KENN_SPEED_RESEARCH_2026-10-03.md), then the
   [phase/cap measurements](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and
   [brief-style measurements/runtime proposal](KENN_C2_BRIEF_STYLE_AND_RUNTIME_PROPOSAL_2026-10-03.md).

The older `KENN_CODEX_HANDOFF_2026-10-03.md` describes an earlier checkpoint.
Its next steps, test counts and GPU restrictions are superseded here and in the
current plan. Historical owner-audit observations about Thursday are excluded
from the KENN work queue: **Thursday is a separate product**.

## Completed and open

- The earlier correction routing and C3 history-boundary work has landed. Read
  [correction dispatch](KENN_C3_CORRECTION_DISPATCH_2026-10-03.md) and
  [history boundaries](KENN_C3_HISTORY_BOUNDARIES_2026-10-03.md) if touching those paths;
  do not repeat the original handoff's steps as though they are unimplemented.
- Live-command and autonomous-producer dispatch reject missing or malformed chat
  owners before proposal work. Rack, MIDI and surgical masking dispatch now do
  the same; valid owners are normalized. Anonymous rack catalogue reads remain.
- Latest verification at the source checkpoint: **134 scoped tests passed**;
  full backend **4133 passed, 12 skipped, 5 warnings, 1 pre-existing failure**.
  Failure: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`.
  Do not hide it, copy its private-path trace into git or silently relax the gate.
  Its outcome can differ in a clean cloud checkout; report what actually runs.
- Token distinctness in recipe dispatch tests does not establish registration,
  cancellation or execution. The next task is the autonomous producer token path.
- The local useful-answer delivery gate remains failed on stream and payload:
  at least 70% of eligible knowledge requests must receive an accepted, useful
  model answer within 15 seconds on M3 / 16 GB with Live open. **C1, C2 and C3
  remain unticked.** Fake Live or cloud inference cannot close this gate.

## Next task: autonomous confirmation tokens

Start with source lookup and a named failing regression, then make a bounded fix.
No new regression or implementation for this task has been written yet.

Relevant paths, relative to `products/kenn`:

- `apps/backend/src/kenn/orchestrator.py::_dispatch_autonomous_producer`
- `apps/backend/src/kenn/autonomous_agent.py::react_deliberate`
- `apps/backend/src/kenn/core/confirmation.py` — issue, verify, revoke and consume
- `apps/backend/src/kenn/core/live_recipe.py` — proposal construction and execution
- `apps/backend/src/kenn/tests/test_orchestrator_autonomous.py`
- `apps/backend/src/kenn/tests/test_react_deliberation.py`
- `apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py`
- `apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py`
- `apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py`

Source observation at `289a6066`: `react_deliberate` constructs a deterministic
`react_` hash token and a recipe-shaped dictionary directly. The shared confirmation
service registers signed `v1.` tokens; `LiveRecipeService` binds one token to exact
typed child proposals. The existing autonomous dispatch test asserts the `react_`
prefix, but does not test registration, cancellation or successful execution.
This is a source finding, not an already reproduced runtime result.

Trace the public dispatch through cancellation and recipe execution on isolated
fake Live state. Test pending registration, owner isolation, token cancellation,
tampering, replay and any successful Apply/Undo behavior the fix claims. Preparation
must not write to Live. Prefer the existing typed recipe/confirmation authority;
do not add a second token scheme or weaken validation to accept arbitrary hashes.
Check supported actions, exact targets/values and recipe step limits before choosing
the fix. Reject unsupported proposals explicitly; do not silently drop steps or
broaden safety limits. Keep valid existing behavior covered and report remaining gaps.

After this slice, re-read the plan's next task. Do not invent a parallel roadmap,
resume the withdrawn Thursday task or launch a large scrape.

## C2 research advice and limits

Other-hardware research numbers are candidate experiments, not KENN speed results.
At 13 tok/s, 220–280 tokens already cost about 17–21 seconds to decode; prefill
tuning alone cannot get those answers under 15 seconds. Measured Mac throughput
varies, so report prefill, decode tok/s and TTFT separately on the same questions.

The small fake-Live phase trial had timely acceptance of stream 2/5 and payload
2/5 at baseline; cap 128 gave stream 4/5 and payload 1/5 with truncated accepted
answers. A separate brief-style trial gave stream 3/5 and payload 1/5. Neither
experiment is adopted: Jack decides changes to answer style. Preserve grounding.

Thinking is already off (`think: false`) for `kenn-brain-qwen3-8b`. Production
ceiling remains 384 tokens. Existing residency remains `keep_alive=30m` with a
240-second ping, holding about 5.4 GB and potentially renewing residency indefinitely.
Jack decides that trade-off; do not change it. Memory pressure/audio dropouts
with Live remain unmeasured pending his scheduled soak.

MLX/runtime/model downloads, a speculative draft and dependencies require Jack's
approval. An MLX comparison proposal must use Qwen3 8B lineage, approximately
1,100-token KENN prompts, M3 / 16 GB and separate prefill/decode reporting. Cloud
GPU numbers cannot stand in for this Mac. Physical GPUs 0 and 1 are authorized
for KENN, but this handoff grants no new server access or installation permission;
GPUs 2–7 are prohibited and no server restarts are allowed. No credentials belong
in git. This next task needs no GPU job.

## Cloud verification and delivery

Use existing provisioned dependencies. The Mac's `.venv` is not portable. Select
an existing Python interpreter with the required packages; if unavailable, record
the exact missing prerequisites and ask Jack before installing anything. Do not
change CI or dependency files to make a cloud environment pass.

Run from `products/kenn`, using a fresh temporary cache per invocation:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' python3 -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_react_deliberation.py apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py -o cache_dir="$(mktemp -d /tmp/kenn-cloud-scoped-XXXXXX)"
```

Add relevant shared recipe tests for the actual change. After scoped checks pass,
run the full backend for a shared-entry-point change, one CPU-heavy job at a time:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' python3 -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir="$(mktemp -d /tmp/kenn-cloud-full-XXXXXX)"
```

These cloud commands are proposed, not cloud results. Do not run real-model
measurements against the absent Mac or claim a local gate pass. Keep raw test logs
outside git if they contain personal paths. Use fake Live only; real Live requires
Jack's scheduled supervised soak. Do not rebuild the index on his Mac.

Keep changes within KENN. Stage explicit files, never `git add -A`. Use one plain
line per commit with no AI attribution trailer. Push only the working branch,
never main; do not force-push. Do not delete anything, add dependencies, change CI,
widen permissions or commit runtime data, private audio, credentials or model prose.

Record each delivered slice in a dated evidence receipt: code commit, exact scoped
command, actual result, environment and limits. Update `KENN_PLAN.md` in the same
branch. Tick only what the evidence proves; leave C1–C3 open. Finish with the commit,
exact files/behavior changed, verification, known failures and next KENN task.
