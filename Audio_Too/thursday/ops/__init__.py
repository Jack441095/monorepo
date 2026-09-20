"""Company operations modules (the "Thursday Autonomous Company
Operations Upgrade", built 2026-09-02).

Founder-facing capability on top of Thursday's core orchestrator:
task_ledger, daily_status, weekly_report + agent_briefing (reporting),
marketing_ops/advertising_ops/funding_ops/qa_ops/engineering_ops/
infrastructure_ops/finance_ops/support_ops/documentation_ops (the
per-domain readiness/planning modules), structured_commands (the
pre-scoring command dispatcher these all share), ops_intake (the shared
pipe-delimited intake parser), macro_analytics, and beta_invite_ops.

Every module here holds the same evidence discipline: a live query, a
live-parsed real file, or an explicit "Evidence missing"/"Not tracked" --
never a fabricated number. See
docs/NITE_DSP_THURSDAY_AUDIT_AND_UPGRADE_PLAN_V1.md (parent NITE_DSP
repo) for the full build history and the reasoning behind each module's
scope.

Grouped into this subpackage (rather than left flat in thursday/
alongside the ~96 pre-existing orchestrator modules) so it's obvious at a
glance which modules are this body of work versus the original
orchestrator/registry/intent machinery.
"""
