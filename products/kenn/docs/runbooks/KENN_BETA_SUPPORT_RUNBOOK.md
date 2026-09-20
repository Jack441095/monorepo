# KENN Internal Beta Support Runbook

Scope: supporting the Mix Review CLI (`mix-review/adapter.py`) and Chat
(`chat/app.py`) beta. AutoMix, desktop, and plugin surfaces are not in beta
-- if a tester reports an issue with one of those, the correct response is
"not in this beta," not troubleshooting.

## Triage order

1. **Reproduce.** Ask for the exact command run and the full JSON output
   (or error text). Run `python3 -m pytest mix-review/tests -v` yourself
   first to confirm the baseline is healthy before investigating a
   specific-file report.
2. **Classify.**
   - `status: "rejected"` -- input validation failure (bad path, wrong
     format, wrong bit depth, too large). This is expected, correct
     behaviour for unsupported input, not a bug, unless the file *should*
     have been accepted (see below).
   - `status: "failed"` -- the engine ran and raised an exception, or
     returned `ok: false`. This is a real bug; get the full traceback if
     possible (running the adapter directly, not swallowing stderr, will
     show it) and file it against `mix-review/core/local_engine.py`.
   - `status: "completed"` with a finding the tester disagrees with -- this
     is calibration feedback, not a crash. Log it against the specific
     `fault_family` for the qualification backlog (see GAP-01/GAP-07 in
     the gap matrix); do not treat it as a defect to silently patch away
     without evidence.
3. **Check for a known issue.** Cross-reference `docs/KNOWN_ISSUES.md` and
   `docs/KENN_BETA_GAP_MATRIX.md` before assuming something is new.

## Common failure modes and what they mean

| Symptom | Likely cause | Action |
|---|---|---|
| `"Unsupported bit depth"` error | 32-bit float WAV, or any non-16/24-bit PCM | Expected; not a bug. Ask the tester to export 16- or 24-bit PCM WAV. |
| `"Unsupported channel count"` | Mono/stereo only supported | Expected; not a bug. |
| `"could not be parsed as a valid WAV file"` | Corrupted, truncated, or non-WAV file (e.g. renamed MP3) | Expected; not a bug. Confirm the file plays correctly elsewhere first. |
| Every finding shows `confidence: 0.0`, `"unknown"` | File is under 1 second, or mono for a stereo-only family | Expected abstention behaviour, not a bug. |
| `status: "failed"` with a Python traceback | Real defect in `local_engine.py` | File a bug with the exact input file (or a minimal WAV that reproduces it) and full traceback. |
| Import error / `RuntimeError` at startup mentioning `Audio_Too` | The tester is running with `KENN_MIX_REVIEW_ENGINE=audio_too_legacy` set (non-default legacy path) without a real checkout | Tell them to unset `KENN_MIX_REVIEW_ENGINE`; the default engine has no external dependency. |
| `RuntimeError: KENN engine checkout not found` on `chat/app.py` startup | `apps/backend/src/kenn/data/index/` doesn't exist yet (gitignored, generated) | Run `python3 apps/backend/src/kenn/main.py build` first; see the tester guide. |
| Chat returns `found: false` for a question that seems in-scope | Retrieval is BM25 (keyword) only right now, not semantic -- wording mismatch is the most common cause | Ask the tester to retry with more specific audio-engineering terminology; log the question either way as retrieval-quality feedback (GAP-03), not necessarily a bug. |
| Chat's `answer` cites a source that doesn't actually support the claim | Possible retrieval/ranking defect | File against `apps/backend/src/kenn/retrieval/`, with the exact question and returned `sources`. |
| Chat's `/health` shows `llm_enabled: true`, or an answer looks generated rather than templated | Should never happen -- `AUDIO_TOO_LLM_ENABLED` is forced to `"0"` in code | Treat as a critical safety bug, not a normal support case; escalate immediately. |
| AutoMix, desktop app, or plugin doesn't work | Out of beta scope | Point to `docs/KENN_BETA_READINESS_REPORT.md`; not a support case. |

## Diagnostics to collect

- Full JSON receipt (includes `receipt_id`, `timestamp`, `analysis_version`
  for exact reproducibility).
- `python3 --version` and OS.
- Whether the input file plays correctly in another tool.
- If `status: "failed"`: run the same file directly and capture stderr
  (the CLI does not currently write a separate log file -- everything
  needed is in stdout/stderr of the single command).

## Data handling

Mix Review never uploads or persists audio (`storage: "memory_only"`,
`external_network: false` -- enforced by `contracts.receipt_errors`, not
just convention). If a tester shares a receipt for support purposes, it
contains a SHA-256 hash of their file and the measured evidence, not the
audio itself, so receipts can be shared/logged without exposing the
tester's actual mix.

## Escalation

- **Engine defects** (`status: "failed"`, incorrect measurements against a
  known-good synthetic case): file against `mix-review/core/local_engine.py`
  with a reproducing test case added to
  `mix-review/tests/test_local_engine.py`.
- **False positives/negatives on real mixes**: log as calibration evidence
  toward GAP-01/GAP-07 (real-mix benchmark), not as an immediate code
  change -- a single disagreement is a data point, not proof of a bug, per
  this repo's own "current evidence over anecdote" rule.
- **Chat retrieval/citation issues**: file against
  `apps/backend/src/kenn/retrieval/` or the specific note in
  `apps/backend/src/kenn/Training_Data_Notes/`, with the exact question and returned
  payload. Log toward GAP-03 (formal benchmark still pending).
- **Anything about AutoMix, desktop, plugin server-backed features**: not
  this beta's scope; redirect to the relevant gap-matrix entry.

## Rollback

If a change causes regressions, see `docs/KENN_BETA_ROLLBACK_PLAN.md`.
