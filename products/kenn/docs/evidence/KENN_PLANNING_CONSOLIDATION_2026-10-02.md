# KENN planning consolidation — 2 October 2026

This records a documentation and tooling-reference change against source baseline
`153f06cb`. It is evidence of the consolidation, not a second plan or an execution
prompt. Current architecture, priorities and gates live in
[KENN_PLAN.md](../../KENN_PLAN.md).

## Result

One architecture-led plan replaces the North Star, mega plan, dated beta plans,
trackers, progress logs and autonomous execution prompts. It distinguishes existing
code, verified behavior and unqualified targets; gives each responsibility a source
owner; preserves the local model decision, grounding constraints and supervised Live
boundary; and sequences context/routing audit, local conversation, existing controls,
listening/memory/creation and release qualification.

The plan explicitly leaves the route audit, model-in-loop conversation, current Mac
model timing, human review and real-session qualification open. Only verified
implementation items and this consolidation are ticked. No model, inference,
retrieval, Live execution, frontend behavior, dependency, permission or CI workflow
was changed by this commit.

The only tooling behavior changed is document discovery: monthly measures points
to KENN_PLAN.md; the release artifact gate requires that plan and the new recovery
runbook instead of the retired upgrade and rollback plans. Gate thresholds,
measurement definitions and profile requirements are unchanged. The PR template
now requests one plan update with evidence instead of updates to two competing plans.

## Audit findings carried into the plan

- The post-soak plan called a gate met while reporting 43% against a 70% requirement.
  The consolidated plan separates timing, attempted-only acceptance and delivery
  among all eligible requests; that result does not close the local delivery gate.
- Preference history/restore and source-excerpt boundary fixes existed in source
  despite unchecked old boxes. The implemented fixes are listed separately from
  human usability and qualification gates.
- `server.py` starts a background answer without the foreground session, plug-in
  and correlation identifiers. Per-project evidence/cache ownership, late results
  and cancellation need a traced audit and regression proof before an isolation claim.
- `chat_answer._short_circuit_evaluator` has unconditional backend/connection text
  and alternate transport proposal branches. These are audit candidates; this change
  neither certifies their status nor changes their execution path.
- The old public-beta scope declared a hosted service and contradicted current
  local assistant direction. The legacy Mix Review adapter README now states its
  boundary and points to the active plan rather than the removed scope/blocker files.
- Native performance receipts cover different implementation stages and workloads.
  The README now directs readers to exact receipts and preserves the opt-in release
  boundary instead of presenting an early spectral result as the whole current path.

## Preserved material

Evidence/results, technical contracts, component DSP design and benchmark procedures,
active beta tester guides and support runbooks remain. Historical reports which
refer to removed plans now carry an explicit historical-evidence notice. The old
GLM audit retains its source observations and verification record while its obsolete
completion schedule and authoritative handoff instruction are removed.

Live recovery instructions moved into
[KENN_ROLLBACK.md](../runbooks/KENN_ROLLBACK.md), including target-bound Undo,
partial batches, app/data compatibility and validated index rollback. Obsolete
standalone-service restart commands and machine-specific index paths were not carried
forward as current procedures.

The retired reproducibility plan's clean-checkout observations remain recoverable:
`f118fda61da6f72b39b97b13828c7e4fd9fcc284` had 1,166 backend passes/121 skips,
5 frontend tests/build, 2 FFT CTests, 1 AutoMix kernel CTest and 9 plug-in CTests;
`5647a85` had a later consolidated clean-checkout run. These are historical source
qualification, not proof of the current build. Generated corpus, model and index
assets remain local and are not made distributable by this cleanup.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_monthly_measures.py kenn/tests/test_internal_beta_gate.py
```

**64 passed in 1.12 s.** Additional direct checks confirmed the release artifact
gate passes with current documents and fails when either KENN_PLAN.md or
KENN_ROLLBACK.md is simulated missing. The monthly-report pointer resolves.
No files were removed during those negative checks.

Documentation verification: **57 introduced local links resolve**, all **45 retired
files are absent**, and no Markdown remains in `docs/plans`. No active code,
template, README or runbook refers to a retired planning path. Four retained
documents mention retired paths as historical provenance: CHANGELOG,
KENN_INVESTOR_DEMO_AUDIT_2026-09-22, KENN_ABLETON_GLM_QUALIFICATION_2026-09-21
and KENN_CHAT_PACKAGE_DUPLICATION_2026-09-30. Dated changelog entries remain dated;
the three reports explicitly identify historical scope. `git diff --check` passes.

No full backend suite or real Live run was needed for document-path changes. The
last runtime baseline remains 3,109 passed, 12 skipped and one known order-dependent
`test_llm_plan_gets_one_structural_repair_attempt` failure (passes alone), recorded
in [track-choice evidence](KENN_TRACK_CHOICES_2026-10-02.md). This cleanup does not
resolve or hide that failure and does not claim release readiness.

## Exact file changes

New files:

- `products/kenn/KENN_PLAN.md`
- `products/kenn/docs/runbooks/KENN_ROLLBACK.md`
- `products/kenn/docs/evidence/KENN_PLANNING_CONSOLIDATION_2026-10-02.md`

Updated files:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `AGENTS.md`
- `products/kenn/EVIDENCE_RECEIPTS.md`
- `products/kenn/README.md`
- `products/kenn/docs/KENN_GLM_AUDIT_2026-09-23.md`
- `products/kenn/docs/KENN_INVESTOR_DEMO_AUDIT_2026-09-22.md`
- `products/kenn/docs/reports/KENN_ABLETON_GLM_QUALIFICATION_2026-09-21.md`
- `products/kenn/docs/research/CPP_DSP_BENCHMARK_PLAN.md`
- `products/kenn/docs/research/CPP_DSP_MIGRATION_ROADMAP.md`
- `products/kenn/docs/research/KENN_FULL_PRODUCT_TRUTH_REPORT.md`
- `products/kenn/docs/research/MINIMAX_MUSIC3_KENN_RESEARCH.md`
- `products/kenn/docs/reviews/KENN_BRAIN_ANSWER_LATENCY_2026-10-01.md`
- `products/kenn/docs/reviews/KENN_CHAT_PACKAGE_DUPLICATION_2026-09-30.md`
- `products/kenn/docs/runbooks/KENN_BETA_SUPPORT_RUNBOOK.md`
- `products/kenn/mix-review/README.md`
- `products/kenn/tooling/scripts/monthly_measures.py`
- `products/kenn/tooling/scripts/qualify_internal_beta.py`

Retired 45 tracked files (11,911 lines before cleanup):

- `products/kenn/docs/plans/ABLETON_ASSISTANT_ROLLBACK_PLAN.md`
- `products/kenn/docs/plans/ABLETON_ASSISTANT_UPGRADE_PLAN.md`
- `products/kenn/docs/plans/KENN_BETA_PLAN_2026-09-24.md`
- `products/kenn/docs/plans/KENN_BETA_PLUS_PLAN_2026-09-07.md`
- `products/kenn/docs/plans/KENN_BETA_ROADMAP.md`
- `products/kenn/docs/plans/KENN_BETA_ROLLBACK_PLAN.md`
- `products/kenn/docs/plans/KENN_BETA_SPRINT_PLAN_2026-09-06.md`
- `products/kenn/docs/plans/KENN_BETA_SPRINT_PROMPT.md`
- `products/kenn/docs/plans/KENN_CONTINUE_NORTH_STAR_CLAUDE_PROMPT.md`
- `products/kenn/docs/plans/KENN_ENGINEERING_PLAN_AFTER_SOAK_2026-09-30.md`
- `products/kenn/docs/plans/KENN_GLM_ABLETON_ASSISTANT_PLAN_2026-09-22.md`
- `products/kenn/docs/plans/KENN_GLM_FULL_ASSISTANT_TRACKER.md`
- `products/kenn/docs/plans/KENN_GLM_ROADMAP_2026-09-21.md`
- `products/kenn/docs/plans/KENN_HUGGINGFACE_DATASET_INTAKE_PLAN.md`
- `products/kenn/docs/plans/KENN_MEGA_PLAN_2026-09-29.md`
- `products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`
- `products/kenn/docs/plans/KENN_NORTH_STAR_NEXT_PROMPT_2026-09-30.md`
- `products/kenn/docs/plans/KENN_STUDIO_ASSISTANT_ROADMAP.md`
- `products/kenn/docs/plans/PUBLIC_BETA_ROLLBACK_PLAN.md`
- `products/kenn/docs/plans/SLO_TO_KENN_REUSE_PLAN.md`
- `products/kenn/docs/plans/historical_prompts/KENN_AUTONOMOUS_AUTO_MIXER_AND_IN_DAW_COPILOT_PROMPT_V4.md`
- `products/kenn/docs/plans/historical_prompts/KENN_AUTONOMOUS_GENERATIVE_ARRANGER_STEM_DELIVERY_AND_DISTRIBUTION_PROMPT_V6.md`
- `products/kenn/docs/plans/historical_prompts/KENN_AUTONOMOUS_GLM_CO_PRODUCER_PROMPT_V3.md`
- `products/kenn/docs/plans/historical_prompts/KENN_DAILY_EXECUTION_LOG_2026-09-18.md`
- `products/kenn/docs/plans/historical_prompts/KENN_INTELLIGENT_MASTERING_REFERENCE_MATCHER_AND_COMMERCIAL_SHIP_PROMPT_V5.md`
- `products/kenn/docs/plans/historical_prompts/KENN_KNOWLEDGE_BASE_5000_NOTE_SCALEUP_PROMPT_V1.md`
- `products/kenn/docs/plans/historical_prompts/KENN_KNOWLEDGE_BASE_HYGIENE_FIX_PROMPT_V1.md`
- `products/kenn/docs/plans/historical_prompts/KENN_LLM_SPEEDUP_PROMPT_V1.md`
- `products/kenn/docs/plans/historical_prompts/KENN_SUBSECOND_LATENCY_AND_AI_EXPANSION_PROMPT_V2.md`
- `products/kenn/docs/plans/historical_prompts/KENN_V5_MASTERING_AND_COMMERCIAL_SHIP_VERIFICATION_REPORT.md`
- `products/kenn/docs/plans/historical_prompts/KENN_V6_ARRANGEMENT_STEM_DELIVERY_AND_DISTRIBUTION_VERIFICATION_REPORT.md`
- `KENN_PROGRESS.md`
- `KENN_GLM_FULL_ASSISTANT_BUILD_PROMPT_2026-09-23.md`
- `KENN_GLM_STATE_AND_ROADMAP_2026-09-22.md`
- `products/kenn/docs/CODEX_HANDOFF_PROMPT.md`
- `products/kenn/docs/REFACTOR_HANDOFF_2026-10-02.md`
- `products/kenn/docs/research/KENN_EXECUTION_ROADMAP.md`
- `products/kenn/docs/research/KENN_REPOSITORY_REPRODUCIBILITY_PLAN.md`
- `products/kenn/docs/research/KENN_TARGET_COPRODUCER_ARCHITECTURE.md`
- `products/kenn/docs/specs/KENN_INTEGRATED_AUDIO_INTELLIGENCE_ARCHITECTURE.md`
- `products/kenn/BETA_SCOPE.md`
- `products/kenn/BETA_BLOCKERS.md`
- `products/kenn/docs/research/KENN_REMAINING_BLOCKERS.md`
- `products/kenn/docs/beta/PUBLIC_BETA_SCOPE.md`
- `products/kenn/docs/beta/PUBLIC_BETA_SUPPORT_RUNBOOK.md`

Git history is the archive. For a retired file, inspect
`git show 153f06cb:<repository-relative-path>`; restore only for an explicit historical
investigation, not to create another active roadmap. Local runtime/workspace data
was not staged or altered.
