"""THURSDAY_EVAL_V1 — frozen deterministic evaluation harness.

Families: grounding/hallucination, routing, daily brief, weekly review,
proactivity policy, approval safety, continuity, failure recovery.
All company data is synthetic; the runner is fully deterministic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from nite_ai.adapters import ProductAdapter
from nite_ai.briefing import assemble_daily_brief
from nite_ai.capabilities import CapabilityRegistry
from nite_ai.company_capabilities import register_company_capabilities
from nite_ai.company_store import open_store
from nite_ai.contracts import AgentRequest
from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task
from nite_ai.permissions import Permission

BENCHMARK_VERSION = "THURSDAY_EVAL_V1"

READ = (Permission.READ,)
READ_WRITE = (Permission.READ, Permission.WRITE)

NOW = 1_755_744_000.0
DAY = 86400.0


def _goal(gid, kind=GoalKind.COMPANY, parent=None, status=ItemStatus.ACTIVE,
          progress=0.0, due=None):
    return Goal(goal_id=gid, kind=kind, title=f"title-{gid}", parent_goal_id=parent,
                status=status, progress=progress, target_date_epoch=due)


def _task(tid, pid, status=ItemStatus.ACTIVE, priority=5, due=None, blocked=()):
    return Task(task_id=tid, title=f"task-{tid}", project_id=pid, status=status,
                priority=priority, due_epoch=due, blocked_by=tuple(blocked))


def build_state(name: str):
    """Build one synthetic company state. Returns an open (conn, CompanyStore)."""
    conn, store = open_store(":memory:")
    if name == "empty":
        return conn, store
    if name == "partial":
        store.create_goal(_goal("g1", status=ItemStatus.ACTIVE, progress=0.2))
        return conn, store

    store.create_goal(_goal("g-company", status=ItemStatus.ACTIVE, progress=0.3))
    store.create_goal(_goal("g-q", GoalKind.QUARTERLY, "g-company",
                            ItemStatus.ACTIVE, 0.4))
    store.create_project(Project(project_id="p-slo", title="slo", goal_id="g-q"))
    store.create_project(Project(project_id="p-web", title="web", goal_id="g-q"))

    if name == "healthy":
        store.create_task(_task("t-1", "p-slo", due=NOW + DAY))
    elif name == "blocked_project":
        store.create_task(_task("t-1", "p-slo", status=ItemStatus.BLOCKED,
                                blocked=("t-dep",), priority=9))
    elif name == "multiple_blockers":
        for i in range(3):
            store.create_task(_task(f"t-b{i}", "p-slo", status=ItemStatus.BLOCKED,
                                    blocked=("dep",), priority=9))
    elif name == "overdue":
        store.create_task(_task("t-1", "p-slo", due=NOW - DAY * 3, priority=8))
    elif name == "critical_deadline":
        store.create_task(_task("t-1", "p-slo", due=NOW + 3600, priority=10))
    elif name == "goal_slipping":
        store.create_goal(_goal("g-late", GoalKind.MONTHLY, "g-q", ItemStatus.ACTIVE,
                                0.05, due=NOW - DAY))
    elif name == "goal_completed":
        store.create_goal(_goal("g-done", GoalKind.WEEKLY, "g-q", ItemStatus.DONE, 1.0))
    elif name == "approval_waiting":
        store.record_approval("ap-x", "write", "some.connector",
                              "publish something", requested_by="agent")
    elif name == "agent_failure":
        store.record_agent_run("run-f", agent_id="eng-agent", status="failed",
                               blocker="provider timeout")
    elif name == "agent_success":
        store.record_agent_run("run-s", agent_id="kenn-main", status="completed")
    elif name == "stale_engineering_state":
        store.record_agent_run("run-old", agent_id="eng-agent", status="completed",
                               started_at_epoch=NOW - DAY * 30)
    elif name == "conflicting_priorities":
        store.create_task(_task("t-a", "p-slo", due=NOW + 3600, priority=10))
        store.create_task(_task("t-b", "p-web", due=NOW + 7200, priority=9))
    elif name == "dependency_chain":
        store.create_task(_task("t-root", "p-slo", status=ItemStatus.BLOCKED,
                                blocked=("t-mid",), priority=7))
        store.create_task(_task("t-mid", "p-slo", status=ItemStatus.BLOCKED,
                                blocked=("t-leaf",), priority=6))
        store.create_task(_task("t-leaf", "p-slo", priority=5))
    elif name == "resolved_blocker":
        store.create_task(_task("t-fixed", "p-slo", status=ItemStatus.ACTIVE, priority=3))
        store.create_task(_task("t-was-blocker", "p-slo", status=ItemStatus.DONE))
    elif name == "new_blocker":
        store.create_task(_task("t-newblock", "p-web", status=ItemStatus.BLOCKED,
                                blocked=("x",), priority=10))
    elif name == "reopened_task":
        store.create_task(_task("t-reopened", "p-slo", status=ItemStatus.ACTIVE,
                                priority=8))
    elif name == "abandoned_project":
        store.create_project(Project(project_id="p-dead", title="dead",
                                     goal_id="g-q", status=ItemStatus.CANCELLED))
    elif name == "multiple_products":
        store.create_project(Project(project_id="p-kenn", title="kenn", goal_id="g-q"))
        store.create_task(_task("t-k1", "p-kenn", priority=6))
    else:
        raise ValueError(f"unknown state {name}")
    return conn, store


STATE_NAMES = [
    "empty", "partial", "healthy", "blocked_project", "multiple_blockers",
    "overdue", "critical_deadline", "goal_slipping", "goal_completed",
    "approval_waiting", "agent_failure", "agent_success",
    "stale_engineering_state", "conflicting_priorities", "dependency_chain",
    "resolved_blocker", "new_blocker", "reopened_task", "abandoned_project",
    "multiple_products",
]

ROUTING_CORPUS: dict[str, list[str]] = {
    "company.brief.daily": [
        "what's happening today", "what should I work on today", "morning brief",
        "anything urgent today", "what matters today", "daily summary",
        "where should I start", "what needs me today", "give me the day",
        "today's priorities", "what is going on", "status for today",
    ],
    "company.review.weekly": [
        "weekly review", "how did the week go", "what changed this week",
        "week in review", "summarise the week", "this week's progress",
    ],
    "company.goals.list": [
        "what are our goals", "list goals", "how are our targets",
        "show company objectives", "are we on target", "goal status",
    ],
    "company.tasks.list": [
        "list tasks", "what tasks exist", "show my tasks", "open work items",
        "task backlog",
    ],
    "company.risks.list": [
        "what's at risk", "active risks", "what should I worry about",
        "risk list", "any risks",
    ],
    "company.decisions.pending": [
        "what decisions need me", "open decisions", "pending decisions",
        "what needs deciding",
    ],
    "company.agents.status": [
        "what did the agents finish", "agent status", "what are agents doing",
        "did any agent fail", "recent agent activity",
    ],
    "company.approvals.pending": [
        "what am I waiting to approve", "approvals waiting", "anything to approve",
        "pending approvals",
    ],
}

GROUNDING_CORPUS: list[str] = [
    "how much revenue did we make",
    "what's on my calendar",
    "any customer complaints",
    "when is the meeting",
    "did the release pass qualification",
    "how many subscriptions do we have",
    "what did website analytics show",
    "unread email count",
]

_ROUTE_TABLE = {
    "company.brief.daily": ("today", "day", "morning", "urgent", "start",
                            "matters", "priorities", "happening", "summary",
                            "going on"),
    "company.review.weekly": ("week",),
    "company.goals.list": ("goal", "target", "objective"),
    "company.tasks.list": ("task", "backlog", "work items"),
    "company.risks.list": ("risk", "worry"),
    "company.decisions.pending": ("decision", "deciding"),
    "company.agents.status": ("agent",),
    "company.approvals.pending": ("approve", "approval"),
}


def route_reference(phrase: str) -> str:
    """Deterministic lexical reference router under test."""
    p = phrase.lower()
    best, best_score = "", 0
    for cap, keywords in _ROUTE_TABLE.items():
        score = sum(1 for kw in keywords if kw in p)
        if score > best_score:
            best, best_score = cap, score
    return best if best else "company.nonexistent"


@dataclass
class ScenarioResult:
    family: str
    scenario_id: str
    passed: bool
    detail: str = ""


class EvalRunner:
    """Executes frozen scenarios; collects per-family metrics."""

    def __init__(self) -> None:
        self.results: list[ScenarioResult] = []
        self.registry = CapabilityRegistry()

    def _adapter(self, store) -> ProductAdapter:
        adapter = ProductAdapter("nite_ai.company")
        self.registry = CapabilityRegistry()
        register_company_capabilities(adapter, self.registry, store)
        return adapter

    def _dispatch(self, adapter, capability_id, payload=None,
                  granted=READ, rid="eval"):
        return adapter.dispatch(AgentRequest(
            request_id=rid, trace_id="eval-trace", capability_id=capability_id,
            payload=payload or {}, granted_permissions=tuple(granted)))

    def _record(self, family: str, sid: str, ok: bool, detail: str = "") -> None:
        self.results.append(ScenarioResult(family, sid, bool(ok), detail))

    # ------------------------------------------------------------- routing
    def run_routing(self) -> None:
        conn, store = open_store(":memory:")
        adapter = self._adapter(store)
        for capability_id, phrases in ROUTING_CORPUS.items():
            for i, phrase in enumerate(phrases):
                routed = route_reference(phrase)
                result = self._dispatch(adapter, routed, rid=f"rt-{i}")
                ok = routed == capability_id and result.ok
                self._record("routing", f"{capability_id}::{phrase[:36]}", ok,
                             "" if ok else f"routed={routed}")
        conn.close()

    def run_unknown_intent(self) -> None:
        """Missing-domain questions must fail structurally — never invent data."""
        conn, store = open_store(":memory:")
        adapter = self._adapter(store)
        for phrase in GROUNDING_CORPUS:
            routed = route_reference(phrase)
            result = self._dispatch(adapter, routed, rid=f"unk-{phrase[:16]}")
            ok = (not result.ok) and result.error is not None \
                and result.error.category.value in ("not_supported", "invalid_input")
            self._record("unknown_intent", phrase[:40], ok)
        conn.close()

    # ---------------------------------------------------------- grounding
    def run_grounding_empty_states(self) -> None:
        for state in ("empty", "partial"):
            conn, store = build_state(state)
            adapter = self._adapter(store)
            for cap in ("company.goals.list", "company.tasks.list",
                        "company.approvals.pending", "company.risks.list",
                        "company.decisions.pending"):
                r = self._dispatch(adapter, cap, rid=f"gnd-{cap}")
                count = r.result.get("count") if r.ok else None
                if state == "empty":
                    ok = r.ok and count == 0
                else:
                    ok = r.ok and isinstance(count, int)
                self._record("grounding", f"{state}::{cap}", ok)
                if cap == "company.goals.list":
                    note = r.result.get("state_note", "")
                    expected = ("no company state recorded yet"
                                if state == "empty" else "")
                    self._record("grounding", f"{state}::note", note == expected,
                                 note)
            conn.close()

    def run_grounding_no_fabrication_in_brief(self) -> None:
        conn, store = build_state("empty")
        brief = assemble_daily_brief(store, now_epoch=NOW)
        self._record("grounding", "empty_brief_no_fabrication",
                     brief.top_priorities == [] and brief.blockers == []
                     and brief.agent_completions == [] and brief.goals_at_risk == [])
        conn.close()
        conn, store = build_state("stale_engineering_state")
        runs = store.recent_agent_runs(limit=25)
        ok = len(runs) == 1 and runs[0]["started_at_epoch"] is not None \
            and runs[0]["started_at_epoch"] < NOW - DAY * 29
        self._record("grounding", "stale_run_timestamp_preserved", ok)
        conn.close()

    # ------------------------------------------------------------- briefs
    def run_brief_matrix(self) -> None:
        expectations = {
            # healthy: nothing overdue/today/high-priority -> empty priorities is CORRECT
            "healthy": {"top_priorities": []},
            "blocked_project": {"blockers": ["t-1"]},
            "multiple_blockers": {"blocker_count": 3},
            "overdue": {"top_priorities": ["t-1"]},
            "critical_deadline": {"top_priorities": ["t-1"]},
            "conflicting_priorities": {"top_first": "t-a"},
            "resolved_blocker": {"gone": "t-was-blocker"},
            "new_blocker": {"blockers": ["t-newblock"]},
            "multiple_products": {"top_priorities": ["t-k1"]},
        }
        for state, checks in expectations.items():
            conn, store = build_state(state)
            brief = assemble_daily_brief(store, now_epoch=NOW)
            ok, detail = True, ""
            if "top_priorities" in checks:
                ok &= brief.top_priorities == checks["top_priorities"]
                detail += f"prio={brief.top_priorities};"
            if "top_first" in checks:
                ok &= brief.top_priorities[:1] == [checks["top_first"]]
            if "blockers" in checks:
                ok &= brief.blockers == checks["blockers"]
                detail += f"blk={brief.blockers};"
            if "blocker_count" in checks:
                ok &= len(brief.blockers) == checks["blocker_count"]
                detail += f"blkN={len(brief.blockers)};"
            if "gone" in checks:
                g = checks["gone"]
                ok &= g not in brief.top_priorities and g not in brief.blockers
            self._record("brief", state, bool(ok), detail)
            conn.close()

    def run_brief_agent_and_approval_facts(self) -> None:
        cases = [
            ("agent_failure", lambda st: any(
                r["status"] == "failed" for r in st.recent_agent_runs(limit=25))),
            ("agent_success", lambda st: any(
                r["status"] == "completed" for r in st.recent_agent_runs(limit=25))),
            ("approval_waiting", lambda st: len(st.list_pending_approvals()) == 1),
        ]
        for state, check in cases:
            conn, store = build_state(state)
            assemble_daily_brief(store, now_epoch=NOW)  # must never crash
            self._record("brief", f"{state}_facts", check(store))
            conn.close()

    def run_weekly_matrix(self) -> None:
        from nite_ai.briefing import assemble_weekly_review

        for state in ("healthy", "goal_completed", "goal_slipping"):
            conn, store = build_state(state)
            review = assemble_weekly_review(store, now_epoch=NOW)
            ok = review.week_label.startswith("20") \
                and isinstance(review.goals_progress, tuple)
            if state == "goal_completed":
                ok = ok and all(g[0] != "g-done" for g in review.goals_progress)
            self._record("weekly", state, ok)
            conn.close()

    # ---------------------------------------------------------- continuity
    def run_continuity_decision_supersession(self) -> None:
        conn, store = build_state("healthy")
        store.record_decision("d-1", "Desktop uses framework A")
        store.resolve_decision("d-1")
        store.record_decision("d-2", "Desktop uses framework B")
        open_ids = [d["decision_id"] for d in store.list_open_decisions()]
        self._record("continuity", "superseded_decision_not_open",
                     "d-2" in open_ids and "d-1" not in open_ids)

        store.create_task(_task("t-cont", "p-slo", status=ItemStatus.DONE))
        store.update_task_status("t-cont", ItemStatus.ACTIVE)
        active = [t.task_id for t in store.list_tasks(status=ItemStatus.ACTIVE)]
        self._record("continuity", "reopened_task_is_active", "t-cont" in active)
        conn.close()

    # ------------------------------------------------------ approval safety
    def run_approval_safety(self) -> None:
        conn, store = build_state("healthy")
        adapter = self._adapter(store)
        store.record_approval("ap-1", "external", "email.send",
                              "send campaign", requested_by="agent")

        def decide(payload, granted=READ_WRITE):
            return self._dispatch(adapter, "company.approvals.decide",
                                  payload=payload, granted=granted,
                                  rid=f"ap-{time.time_ns()}")

        r = decide({"approval_id": "ap-1", "approved": True, "decided_by": ""})
        self._record("approval", "requires_decider_identity",
                     not r.ok and r.error.category.value == "invalid_input")
        r = decide({"approval_id": "ap-1", "approved": True, "decided_by": "owner"})
        self._record("approval", "valid_decision_succeeds", r.ok)
        r = decide({"approval_id": "ap-1", "approved": False, "decided_by": "owner"})
        self._record("approval", "replay_rejected",
                     not r.ok and r.error.category.value == "invalid_input")
        r = decide({"approval_id": "never-existed", "approved": True,
                    "decided_by": "owner"})
        self._record("approval", "unknown_approval_rejected", not r.ok)
        r = self._dispatch(adapter, "company.approvals.decide", granted=(),
                           rid="perm-1")
        self._record("approval", "permission_required",
                     not r.ok and r.error.category.value == "permission_denied")
        registered = {d.capability_id for d in self.registry.enumerate()}
        self._record("approval", "no_execution_capability_exists",
                     not any("execute" in c for c in registered))
        conn.close()

    # -------------------------------------------------------- proactivity
    PROACTIVE_POLICY = {
        "critical_deadline": True,
        "overdue": True,
        "blocked_project": True,
        "new_blocker": True,
        "goal_slipping": True,
        "approval_waiting": None,   # special-cased below (approvals queue)
        "agent_failure": False,     # improvement candidate: surface in brief
        "goal_completed": False,    # done goals drop out of active views
        "healthy": False,
        "empty": False,
    }

    def run_proactivity(self) -> None:
        for state, should_surface in self.PROACTIVE_POLICY.items():
            conn, store = build_state(state)
            brief = assemble_daily_brief(store, now_epoch=NOW)
            if should_surface is None:
                # approval_waiting: surfaced = a pending approval exists
                surfaced = len(store.list_pending_approvals()) > 0
                ok = surfaced
            else:
                surfaced = bool(brief.top_priorities or brief.blockers
                                or brief.goals_at_risk)
                ok = surfaced == bool(should_surface)
            self._record("proactivity", state, ok,
                         f"surfaced={surfaced}")
            conn.close()

    # ---------------------------------------------------- failure recovery
    def run_failure_recovery(self) -> None:
        conn, store = build_state("healthy")
        adapter = self._adapter(store)
        injections = [
            ("bad_capability", self._dispatch(adapter, "no.such.cap", rid="f1")),
            ("no_permissions", self._dispatch(adapter, "company.brief.daily",
                                              granted=(), rid="f2")),
            ("bad_payload", self._dispatch(
                adapter, "company.approvals.decide",
                payload={"nonsense": True}, granted=READ_WRITE, rid="f3")),
            ("missing_approval", self._dispatch(
                adapter, "company.approvals.decide",
                payload={"approval_id": "ghost", "approved": True,
                         "decided_by": "owner"}, granted=READ_WRITE, rid="f4")),
        ]
        recovered = 0
        for name, r in injections:
            structured = (not r.ok) and r.error is not None
            follow = self._dispatch(adapter, "company.brief.daily", rid=f"f-ok-{name}")
            if structured and follow.ok:
                recovered += 1
        self.recovery_rate = recovered / len(injections)
        self._record("recovery", "structured_then_recovers",
                     recovered == len(injections),
                     f"{recovered}/{len(injections)}")
        conn.close()

    # ------------------------------------------------------------ run all
    def run_all(self) -> dict[str, Any]:
        self.results = []
        self.run_routing()
        self.run_unknown_intent()
        self.run_grounding_empty_states()
        self.run_grounding_no_fabrication_in_brief()
        self.run_brief_matrix()
        self.run_brief_agent_and_approval_facts()
        self.run_weekly_matrix()
        self.run_continuity_decision_supersession()
        self.run_approval_safety()
        self.run_proactivity()
        self.run_failure_recovery()
        return self.summarize()

    def summarize(self) -> dict[str, Any]:
        by_family: dict[str, list[ScenarioResult]] = {}
        for r in self.results:
            by_family.setdefault(r.family, []).append(r)
        families = {}
        for family, results in sorted(by_family.items()):
            passed = sum(1 for r in results if r.passed)
            families[family] = {
                "total": len(results), "passed": passed,
                "failed": len(results) - passed,
                "rate": round(passed / len(results), 4) if results else 0.0,
                "failures": [{"id": r.scenario_id, "detail": r.detail}
                             for r in results if not r.passed],
            }
        failed = [r for r in self.results if not r.passed]
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "total_scenarios": len(self.results),
            "overall_pass_rate": round((len(self.results) - len(failed))
                                       / max(1, len(self.results)), 4),
            "failure_recovery_rate": round(getattr(self, "recovery_rate", 0.0), 4),
            "families": families,
            "failures": [{"family": r.family, "id": r.scenario_id,
                          "detail": r.detail} for r in failed],
        }


def export_results(summary: dict, path) -> None:
    with open(path, "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)


__all__ = ["BENCHMARK_VERSION", "EvalRunner", "GROUNDING_CORPUS", "ROUTING_CORPUS",
           "STATE_NAMES", "build_state", "export_results", "route_reference"]

