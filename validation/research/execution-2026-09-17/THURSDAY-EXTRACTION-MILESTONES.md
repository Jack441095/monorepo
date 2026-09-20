# THURSDAY EXTRACTION MILESTONES (from EXTRACTION_COUPLING.md — no new code)

State (verified by doc read + earlier file counts): `import thursday` standalone
OK. Cat A vendored. Cat B lazy-import + typed errors. Cat C (~40 call sites in
`client.py` + `compound/monitor/orchestrator/phase3_handlers/macros/server/
specialists`) is real, documented Audio_Too coupling — orchestrator genuinely
drives Ableton bridge, AudioGen queue, creative-lab, portfolio, app record
store. Not a duplicate to delete; a migration to finish.

## M1 — Uniform typed-error treatment for Category C (est. 1–2 wks)
Bring all ~40 `client.py` call sites + 7 modules in line with the
`specialists.py::run_specialist_with_llm` pattern (`try/except ImportError` →
typed FAILED result). No behavior change when Audio_Too present; clean typed
failures when absent. DoD: grep shows zero bare cross-repo imports outside
try/except; `import thursday` + capability listing green in both layouts.

## M2 — repo_root pattern to the 4 leftovers (est. 0.5 wk)
`autonomous_dispatcher.py`, `daw_watcher.py`, `main.py`, `watcher.py` still
compute Audio_Too's path fixed-depth. Apply `thursday/repo_root.py`
`audio_too_root()` like the 13 files already converted. DoD: import-trace
`/health`, `/ask`, `/speak` green from a sibling checkout.

## M3 — Contract freeze + cutover decision (est. 0.5 wk + owner call)
Freeze the cross-repo call surface (explicit versioned contract types OR
accept permanent sibling-layout coupling). Then owner decides: Thursday stays
a satellite of Audio_Too (kill the standalone dream, delete nothing) or
completes to independent repo (cutover + CI of its own). Until M3, scope-freeze
Thursday: no new bridges, no new coupling.

Kill rule (from research plan): if M1+M2 exceed 3 wks, freeze extraction work
and treat Thursday as Audio_Too-internal permanently.
