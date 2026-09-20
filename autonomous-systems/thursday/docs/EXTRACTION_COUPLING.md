# Thursday Extraction — Audio_Too Coupling

**Status (2026-09-02):** this repo is now the live, canonical Thursday
deployment — `com.nitedsp.thursday-server` (launchd) runs
`thursday/server.py` from here, not from `Audio_Too/thursday` (archived,
no longer developed against; the founder's stated intent is to eventually
retire `Audio_Too` entirely once everything real is migrated out of it).
`import thursday` succeeds standalone (verified, see receipt at the bottom
of this doc), but Thursday still has real, undecoupled runtime
dependencies on Audio_Too's app/business/studio directories for a
meaningful slice of its features — reached via
`thursday.repo_root.audio_too_root()`'s upward search, not a fixed
relative path, so this keeps working if Audio_Too moves or is renamed
(only `repo_root.py` would need updating, or an `AUDIO_TOO_ROOT`/
`NITE_DSP_ROOT` env var override, instead of hunting through every module
again). This doc is the explicit contract for what that coupling is, so
nobody mistakes "the package imports without crashing" for "fully
standalone."

**Update — 2026-09-02, Ops upgrade migration:** the "Thursday Autonomous
Company Operations Upgrade" (task ledger, daily status, marketing/
advertising/funding readiness, QA/beta readiness, weekly reports, agent
briefing — 11 new modules) was built in `Audio_Too/thursday` over one
session, per an explicit decision to keep the extraction and Audio_Too
copies in sync only at natural checkpoints rather than mid-build. It's
migrated here now that phase 6 of that spec is done. See
`docs/NITE_DSP_THURSDAY_AUDIT_AND_UPGRADE_PLAN_V1.md` in the parent repo
for the full build history. All 11 new modules imported cleanly standalone
with zero changes needed — none of them touch `audio_too`/`business`/`app`
at all except `funding_ops.py`, which already used the established lazy-
import-with-honest-degrade pattern (see Category B) for its one real
dependency (`app.db.list_records`).

Migrating this also surfaced two coupling gaps **older than tonight's
build and not caused by it** — nobody had previously tried importing
`thursday.orchestrator` or `thursday.registry.handlers` directly in this
repo (the original 4 test files only touched `shadow_adapters`,
`lease_policy`, `_compat`, `orchestration_benchmark`, none of which reach
`thursday.registry`). Both are now fixed, joining Category B:

| Module | What broke | Fix |
|---|---|---|
| `thursday/scheduler.py` | Module-level `from db import connect, now` (Audio_Too's `business/app/db.py`) — crashed on import, taking down anything that imports `thursday.orchestrator` or `thursday.registry.*` transitively (`orchestrator` → `registry` → `registry.handlers` → `daily_brief` → `scheduler`) | Lazy `try/except ImportError`, typed `SchedulerDatabaseUnavailable` raised only if a scheduling function is actually called standalone. Real integration point, not vendored. |
| `thursday/scheduling.py` | Module-level `from action_policy import action_allowed, action_denied_message` (Audio_Too's `scripts/action_policy.py`) — same transitive-crash shape | Lazy `try/except ImportError` — but this one **fails closed**, not typed-raise: `action_allowed()` gates a real mutating action (desktop automation) at its one call site, so an unavailable policy module must default to *deny*, never to *allowed* or to a crash that could be caught and ignored upstream. |

Post-fix, `import thursday.orchestrator` and `import thursday.registry.handlers`
both succeed standalone — genuinely more of the package is import-safe now
than before this migration, not just no-worse.

Reorg plan gate (`docs/NITE_DSP_REORGANISATION_PLAN.md` in the parent
NITE_DSP repo, line 150): "independent repositories connected through
explicit contracts." This doc *is* that explicit contract for the
`audio_too` / `business` / `app` boundary.

## What changed to make `import thursday` work

A `grep -rlE "^\s*(from|import)\s+(audio_too|business|app)\b" thursday/`
found 16 files importing from packages that only exist in the `Audio_Too`
repo. Of those, **7 imported at module level** — meaning `import thursday`
(or any submodule chain reaching them) crashed immediately, regardless of
whether the feature was ever used:

- `thursday/errors.py`
- `thursday/retry.py`
- `thursday/registry/core.py`
- `thursday/command_gateway.py`
- `thursday/brain.py`
- `thursday/response_rewrite.py`
- `thursday/voice_output.py`

The other **9 already used function-local (lazy) imports** and never broke
package import in the first place — they only fail when the specific
function that needs Audio_Too is actually called:

- `thursday/client.py`, `thursday/compound.py`, `thursday/monitor.py`,
  `thursday/orchestrator.py`, `thursday/phase3_handlers.py`,
  `thursday/macros/__init__.py`, `thursday/server.py`,
  `thursday/specialists.py`, `thursday/registry/handlers.py`

(`thursday/registry/handlers.py` had one exception: its
`_handle_company_state()` imported `audio_too.model_runtime.DEFAULT_LLM`
unconditionally at the top of the function, even on the code path where
`is_llm_enabled` is `False` and the import is never used. Moved inside the
`is_llm_enabled` branch, where it was already wrapped in `try/except
Exception` — so it now degrades the same way the other 8 files' pattern
does, instead of crashing every call standalone.)

## Category A — vendored (small, stable, needed at import time)

New file: `thursday/_compat.py`. Contains local copies of primitives that
are (a) small, (b) semantically stable, and (c) required at *import* time
(so they can't be deferred behind a lazy call-time import).

| Vendored | Source of truth | Used by |
|---|---|---|
| `PublicError`, `PublicErrorCode`, `PublicErrorDetails` (minus `to_contract_error()`, dropped — see below) | `audio_too/errors.py` | `thursday/errors.py`, `thursday/retry.py`, `thursday/command_gateway.py` |
| `PermissionScope` (5-value str Enum) | `audio_too/contracts.py` | `thursday/registry/core.py` (`ServiceDef.permissions` field default) |

These have no automated sync check against the Audio_Too originals — if
`audio_too/errors.py` or the `PermissionScope` enum changes upstream, this
file needs a manual re-sync. `PublicErrorDetails.to_contract_error()` was
deliberately **not** vendored: it converts into `audio_too.contracts
.ContractError`, which is Category B (see below), not something safe to fork
independently.

## Category B — real integration points (deferred, lazy import, typed error)

These are genuine cross-repo coupling — shared, schema-versioned contract
types or a live process-global runtime object — not vendored, because an
independently-maintained copy risks silently drifting from the real
contract. Each now imports lazily (inside a function, not at module top) and
raises a typed error naming the missing dependency instead of a raw
`ModuleNotFoundError`, so the package still imports cleanly and the failure
is legible when the feature is actually used standalone.

| File | What's deferred | Typed error | Notes |
|---|---|---|---|
| `thursday/command_gateway.py` | `AssistantResponse`, `CommandEnvelope`, `ContractError`, `ResultEnvelope`, `ResultStatus` (`audio_too.contracts`) | `CommandGatewayUnavailable` | The typed, machine-facing command/result contract. Every function that builds/consumes these calls `_contracts()` first. |
| `thursday/registry/core.py` | `Capability` (`audio_too`, schema-versioned) | `CapabilityContractUnavailable` | Only `ServiceDef.to_capability()` needs it; `ServiceDef` itself and everything else in the registry works standalone. |
| `thursday/brain.py` | `DEFAULT_LLM` (`audio_too.model_runtime`) | `ModelRuntimeUnavailable` (also already degrades to `BrainDecision(type="abstain", ...)` via the existing broad `except Exception` around both call sites) | Live LLM provider singleton with network calls (Ollama/remote). |
| `thursday/response_rewrite.py` | `DEFAULT_LLM` (`audio_too.model_runtime`) | (falls into the existing `except Exception: return None`) | Same provider as `brain.py`. |
| `thursday/voice_output.py` | `ONNX_SESSION_INIT_LOCK` (`audio_too.model_runtime`) | none needed — falls back to a fresh local `threading.RLock()` | This lock is *process-local* coordination by design (its own docstring says so). The only reason to share the exact object with Audio_Too is so the two don't race inside the **same process** in the live deployment. Standalone, nothing else in-process needs it, so a local lock is a correct, not a faked, fallback. |
| `thursday/registry/handlers.py` | `DEFAULT_LLM` (`audio_too.model_runtime`) | (falls into the existing `except Exception: pass`, returns the deterministic-only render) | Only reached when `AUDIO_TOO_LLM_ENABLED`/`THURSDAY_BRAIN_ENABLED` is set. |

## Category C — extensive, undocumented-further, already-lazy real coupling (left alone)

`thursday/client.py` (~40 call sites), plus `thursday/compound.py`,
`thursday/monitor.py`, `thursday/orchestrator.py`,
`thursday/phase3_handlers.py`, `thursday/macros/__init__.py`,
`thursday/server.py`, `thursday/specialists.py` call directly into
Audio_Too's real Flask app modules at the point of use: `app.ableton_bridge`,
`app.ableton_routes`, `app.audiogen_bridge`, `app.creative_lab`,
`app.portfolio_ops`, `app.api_schemas`, `app.invoice_pdf`, `app.db`.

This is legitimate, extensive cross-repo coupling — Thursday genuinely
orchestrates Audio_Too's live services (Ableton bridge, AudioGen render
queue, creative-lab repair recommendations, portfolio publishing, the
app-level record store). It was **not** touched in this pass:

- These imports were already function-local, so they don't break `import
  thursday` — the specific blocking bug (module-level crash) doesn't apply.
- Stubbing this out with fake logic would misrepresent Thursday's actual
  behavior; per the standing instruction for this work, real integration
  points get documented, not faked.
- `specialists.py`'s `run_specialist_with_llm()` already demonstrates the
  target pattern for this category (`try/except ImportError` → typed
  `SpecialistResult(status="FAILED", ...)`) — most of `client.py`'s ~40
  call sites do not yet follow it uniformly. Bringing all of them in line is
  real work, not a quick fix, and is left as a follow-up rather than rushed
  here to avoid subtly changing behavior in a live orchestrator.

**Bottom line:** `import thursday` works standalone. Building/composing
commands (`command_gateway`), listing typed capabilities
(`registry.core.ServiceDef.to_capability`), LLM-backed decisions
(`brain.py`), and most of `client.py`'s service bridges still require
running inside (or alongside) the real `Audio_Too` process to actually
function. That's expected and documented here, not a bug to hide.

## Orphaned test removed

`tests/test_thursday_routes.py` imported `business/app/routes
/thursday_routes.py`, a path that only exists in `Audio_Too`, not this repo.
It could never collect here (`ModuleNotFoundError: No module named 'app'`).
Diffed byte-for-byte identical against `Audio_Too/tests/test_thursday_routes
.py` — confirmed the real, working copy already lives there, so the copy in
this repo was deleted rather than fixed (nothing left it should have kept;
no coverage lost).

**Immediately after this pass, the extracted repo had zero
pytest-collectible test files.** That gap was closed in a follow-up pass
the same night: `tests/test_compat.py`, `tests/test_shadow_adapters.py`,
`tests/test_lease_policy.py`, and `tests/test_orchestration_benchmark.py`
(26 tests total) now cover every module confirmed standalone-safe above —
`thursday._compat`, `thursday.shadow_adapters`, `thursday.lease_policy`,
and `thursday.evals.orchestration_benchmark`. See the updated
clean-checkout receipt below. This is real coverage of the standalone
surface, not a substitute for `Audio_Too/tests/thursday`'s 819+ tests,
which still only run against the live copy.

One incidental finding while writing `test_lease_policy.py`:
`validate_lease_write_attempt()`'s traversal check
(`".." in os.path.normpath(path)`) never fires for an absolute path like
`/wt/../../etc/passwd`, because `normpath` resolves the `..` segments away
before the check runs — `/wt/allowed/../../etc/passwd` normalizes straight
to `/etc/passwd` with no `..` left in it. The write is still correctly
rejected either way (the *allowed-paths* prefix check below it catches
that case), so this isn't a security hole, but the "Path traversal attempt
detected" error message is effectively unreachable for the traversal
shape callers are most likely to send. Left as-is (a message-clarity
observation, not a bug fix — untangling which check is doing what should
be a deliberate small change, not an incidental one in a testing pass).

## Clean-checkout receipt

Environment: macOS, Python 3.13, this repo's own worktree checkout, **no
`audio_too`, `nite_ai`, or any Audio_Too code on `sys.path`** — confirmed
directly:

```
$ python3 -c "import audio_too"
ModuleNotFoundError: No module named 'audio_too'
```

Steps run and their real output (updated 2026-09-02, post Ops-upgrade
migration):

```
$ python3 -m pip install -e . --no-deps
Successfully installed thursday-0.1.0  (editable)

$ python3 -c "import thursday; print(thursday.__file__)"
<repo>/thursday/__init__.py
# succeeds — no ModuleNotFoundError, no audio_too/business/app on the path

$ python3 -c "import thursday.orchestrator; import thursday.registry.handlers"
# succeeds -- previously broken standalone (scheduler.py/scheduling.py,
# see above), now fixed as part of this migration

$ python3 -m pytest -q
........................................................................ [ 40%]
........................................................................ [ 80%]
....................................                                     [100%]
180 passed in 3.73s
```

No `THURSDAY_V2*` receipts, `thursday/evals/v2*` modules, or their JSON
outputs were touched, run, or re-verified in this pass — that machinery is
out of scope here per standing instruction and was left exactly as found.

## Update — 2026-09-02, second migration (phases 7–11 + reorg + beta invites + server work)

Migrated everything built in `Audio_Too/thursday` since the checkpoint
above: 6 new Ops modules (`engineering_ops`, `infrastructure_ops`,
`finance_ops`, `support_ops`, `documentation_ops`, `beta_invite_ops`), the
`thursday/ops/` folder reorganisation (the 11 previously-migrated modules
moved from `thursday/*.py` to `thursday/ops/*.py` in both repos), the
`registry/handlers.py` new handler functions (surgically merged — see
below), the mobile chat page (`thursday/static/chat.html`), and the
`launchd` server wrapper (`thursday/scripts/run_server.sh`, copied as-is;
it is genuinely Audio_Too-deployment-specific — resolves paths relative to
`Audio_Too/`, shells out to the Tailscale CLI — and is not runnable
standalone from this repo. Kept for audit completeness, not as a working
launcher here).

**`registry/handlers.py`:** the diff since the last checkpoint was too
scattered (many small edits interleaved with new additions, not one clean
block) for the surgical line-range insertion used last time. Instead: took
Audio_Too's current file wholesale, then re-applied the one isolated
divergence on top (the `DEFAULT_LLM` import moved from top-of-function to
inside the `try` block under `is_llm_enabled`, matching the existing
Category B pattern above). Diffed against Audio_Too's copy afterward to
confirm that's the *only* remaining difference.

**New coupling surfaced: `finance_ops.py` / `support_ops.py`.** Both read
`business/app/business_knowledge.json`. In Audio_Too, `thursday/ops/`'s
2-parents-up path happens to land on the `Audio_Too/` directory itself, so
the bare relative path resolves by coincidence of nesting. This repo is a
*sibling* of `Audio_Too/`, not nested under it, so the same upward search
can never reach it. Fixed by adding `"Audio_Too/business/app/business_knowledge.json"`
as a second candidate relative path (checked from the shared NITE_DSP root
the search already finds) — reaches the same real, live file rather than
vendoring a copy, consistent with the "not vendored" reasoning used for
`DEFAULT_LLM` elsewhere in this doc. This is a genuine, permanent
extraction/Audio_Too divergence in `finance_ops.py` (not present in
Audio_Too's own copy, which doesn't need it).

**Fallback-depth fixes**, same class of bug as `shadow_adapters.py`'s
existing one: `qa_ops.py`, `documentation_ops.py`, `beta_invite_ops.py`
each have a hardcoded fallback (only reached if the upward search fails)
tuned for Audio_Too's `thursday/ops/` depth (`parents[3]`). This repo
nests one level deeper (`thursday/thursday/ops/`), so each fallback was
bumped to `parents[4]` here. The upward search itself is depth-independent
and finds the real root correctly in both repos regardless — only the
never-normally-hit fallback needed a manual per-copy fix.

**Stale test removed:** `tests/test_shadow_adapters.py` (no `thursday_`
prefix) predates this migration and asserted the old, pre-Phase-7
`ADAPTERS` schema (`smart_sample_manager`, `slo_v5c`, hardcoded
`KENN`/`SLO_V5C` paths) that no longer exists. It was superseded by
`tests/test_thursday_shadow_adapters.py` (copied fresh from Audio_Too this
pass) and also actively broke other tests via `importlib.reload()`
side-effects that outlived its own test function. Deleted, not fixed —
its coverage is a strict subset of the new file's.

Updated receipt:

```
$ python3 -m pytest -q
........................................................................ [ 29%]
........................................................................ [ 59%]
........................................................................ [ 89%]
..........................                                               [100%]
242 passed in 8.37s
```

## Update — 2026-09-02, voice stack standalone-import fix

`thursday/voice.py`, `thursday/voice_output.py`, `thursday/tts_worker.py`,
and `thursday/tts_worker_mlx.py` were already present in this repo (STT via
faster-whisper, TTS via Kokoro, both real and already checked into this
extraction), but `voice.py` had never actually been import-tested
standalone: `from action_policy import action_allowed` at module level
crashed `import thursday.voice` immediately outside Audio_Too, joining the
same class of bug as `scheduler.py`/`scheduling.py` above. Fixed with the
identical pattern — `try/except ImportError`, fail-CLOSED stub
(`action_allowed` returns `False`) — since the one call site
(`record_audio()`) gates real microphone capture, a genuine mutating
action; an unavailable policy module must never silently grant permission.

Also copied over the matching test coverage
(`tests/test_thursday_voice.py`, `tests/test_thursday_voice_brief.py`,
`tests/test_thursday_voice_output.py` — 20 tests), which had not been
migrated before. `voice_output.py`'s `ONNX_SESSION_INIT_LOCK` fallback
(Category B, documented above) was already in place and needed no change.

```
$ python3 -m pytest -q
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
..............................................                           [100%]
262 passed in 13.48s
```

## Update — 2026-09-02, made this repo the live server; added thursday.repo_root

Added a `/speak` endpoint to `thursday/server.py` (mirrors Audio_Too's own
`/api/thursday/speak`, using the same real `thursday.voice_output.
synthesise_isolated()` Kokoro engine) and wired the mobile chat page
(`thursday/static/chat.html`) to play replies aloud, either per-message
(▶ button) or automatically via a "Speak replies" toggle.

Making that endpoint actually work standalone surfaced a bug class present
in 13 files: each computed "where's Audio_Too" with a fixed
`Path(__file__).resolve().parent.parent` (or `.parents[1]`) — correct only
because `Audio_Too/thursday/X.py`'s parent.parent happens to equal
`Audio_Too/`. This repo is a *sibling* of `Audio_Too`, not an ancestor, so
no amount of `.parent` from here ever reaches it (the same root cause as
`finance_ops.py`'s business-data lookup, fixed earlier, just far more
widespread). Added `thursday/repo_root.py`: one shared, upward-searching
`audio_too_root()` (same pattern as `shadow_adapters._nite_dsp_root()`),
correct unmodified in both repos, replacing the per-file fixed-depth
computation in `client.py`, `diagnostics.py`, `scheduling.py`,
`scheduler.py`, `server.py`, `orchestrator.py`, `bridge.py`, `brain.py`,
`voice.py`, and `voice_output.py` (Kokoro's model directory and CoreML
cache path). `registry/codebase.py`'s similarly-shaped `WORKSPACE_ROOT`
was checked and left alone — it means "the thursday package's own root"
(a code-search sandbox boundary), not "Audio_Too root", and is already
correct at any nesting depth since it's self-referential.

Not touched (not reachable from `thursday.server`'s live request path,
confirmed by import-tracing `/health`, `/ask`, `/speak`): `autonomous_
dispatcher.py`, `daw_watcher.py`, `main.py`, `watcher.py`. These still
compute Audio_Too's path the old, fixed way and would need the same
`repo_root.audio_too_root()` fix before being relied on standalone.

`scheduling.py`'s and `voice.py`'s `action_policy` fail-closed fallback
(added in an earlier pass) is now less likely to ever trigger in practice
— since `audio_too_root()` finds the real `Audio_Too/scripts/
action_policy.py` even from here, the fallback only fires if Audio_Too is
genuinely absent from disk, not merely because this is the standalone
extraction. Updated both files' comments to say so; behavior (fail closed,
never open) is unchanged.

**Live verification** (not a standalone-import check — an actual running
server, hit over HTTP, exercising the real `client.py`/`orchestrator.py`
Category C integrations and Kokoro TTS):

```
$ THURSDAY_SERVER_TOKEN=... .venv/bin/python3 -m thursday.server --host 127.0.0.1 --port 8099
$ curl -X POST http://127.0.0.1:8099/ask -d '{"question": "what is the beta readiness status"}'
# -> real answer, live-read from docs/NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md
$ curl -X POST http://127.0.0.1:8099/speak -d '{"text": "...", "voice": "thursday"}' -o out.wav
# -> 170028-byte real WAV, RIFF/WAVE, 16-bit mono 24kHz (Kokoro)
```

`com.nitedsp.thursday-server` (`thursday/scripts/com.nitedsp.thursday-
server.plist` + the rewritten `run_server.sh`, both in this repo) now runs
this as the actual production Tailscale-reachable service, replacing
`com.audio-too.thursday-server` (unloaded, plist archived to `~/Library/
LaunchAgents/archive/`, not deleted — a same-command rollback if needed).
`run_server.sh` still reuses Audio_Too's `.venv` (see the script's own
header comment for why: duplicating every ML/audio dependency into a
second venv isn't decoupling, just duplication) and `server.py` still
loads `THURSDAY_SERVER_TOKEN` from `Audio_Too/.env` via `audio_too_root()`
— real secrets stay real secrets, not vendored into this repo.
