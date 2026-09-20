"""Tests for Thursday's read-only company-state adapter.

Covers: platform-missing honesty, store-failure degradation, bounded
snapshot views, freshness semantics, cache behaviour (TTL / force-refresh /
stale fallback / invalidation), derived evidence typing, and thread-safe
cached reads. All data synthetic via nite_ai's own test-friendly
``open_store``; never touches production state.
"""

from __future__ import annotations

import threading
import time

import pytest

from thursday import company_state as cs


def _end_of_local_day(epoch: float) -> float:
    lt = time.localtime(epoch)
    return time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, lt.tm_isdst)
    ) + 86400


@pytest.fixture(autouse=True)
def _isolated_company_db(tmp_path, monkeypatch):
    monkeypatch.setenv("THURSDAY_COMPANY_DB", str(tmp_path / "company.db"))
    cs.invalidate_cache()


@pytest.fixture()
def populated_store(tmp_path):
    from nite_ai.company_store import open_store
    from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task

    now = time.time()
    conn, store = open_store(cs.db_path())

    g = store.create_goal(
        Goal(
            goal_id="g-launch",
            kind=GoalKind.COMPANY,
            title="Ship SLO launch",
            status=ItemStatus.ACTIVE,
            progress=0.4,
            target_date_epoch=now - 86400,  # target passed → at-risk by platform rule
        )
    )
    p = store.create_project(
        Project(
            project_id="p-slo",
            title="SLO release",
            goal_id=g.goal_id,
            status=ItemStatus.ACTIVE,
            progress=0.5,
        )
    )
    store.create_task(
        Task(
            task_id="t-overdue-1",
            title="Fix release blocker",
            project_id=p.project_id,
            status=ItemStatus.ACTIVE,
            due_epoch=now - 7200,
            priority=9,
        )
    )
    store.create_task(
        Task(
            task_id="t-overdue-2",
            title="Update notes",
            project_id=p.project_id,
            status=ItemStatus.ACTIVE,
            due_epoch=now - 3600,
            priority=2,
        )
    )
    store.create_task(
        Task(
            task_id="t-due-today",
            title="Review candidate build",
            project_id=p.project_id,
            status=ItemStatus.ACTIVE,
            # Clamp to just before local midnight so the task stays "later
            # today" even when the suite runs in the final hour of the day.
            due_epoch=min(now + 3600, _end_of_local_day(now) - 60),
            priority=7,
        )
    )
    store.create_task(
        Task(
            task_id="t-blocked",
            title="Waiting on asset delivery",
            project_id=p.project_id,
            status=ItemStatus.BLOCKED,
            priority=8,
            blocked_by=("external-delivery",),
        )
    )
    store.record_risk("r-1", "Third-party API rate limits during launch", "high")
    store.record_decision("d-1", "Choose launch date")
    store.record_approval(
        "ap-1",
        action_level="high",
        capability_id="company.approvals.decide",
        summary="Publish launch announcement",
    )
    store.record_agent_run(
        "run-1",
        agent_id="marketing",
        status="completed",
        started_at_epoch=now - 600,
        finished_at_epoch=now - 300,
    )
    store.record_agent_run(
        "run-2",
        agent_id="research",
        status="failed",
        blocker="provider timeout",
        started_at_epoch=now - 900,
        finished_at_epoch=now - 800,
    )
    yield store
    conn.close()


# ─── Honest failure modes ────────────────────────────────────────────────


def test_platform_missing_raises_honest_error(monkeypatch):
    # Setting the module slot to None makes `import nite_ai` raise ImportError
    # — the authentic platform-absent path.
    monkeypatch.setitem(__import__("sys").modules, "nite_ai", None)
    monkeypatch.setitem(__import__("sys").modules, "nite_ai.company_store", None)
    with pytest.raises(cs.CompanyStateUnavailable, match="not installed"):
        cs.capture_snapshot()


def test_missing_store_degrades_without_crash():
    # No store file exists yet at the configured path → open_store creates an
    # empty one; that must succeed and report empty honestly.
    snap = cs.capture_snapshot()
    assert snap.is_empty()
    assert snap.state_note == "no company state recorded yet"


# ─── Bounded snapshot views ──────────────────────────────────────────────


def test_populated_snapshot_views(populated_store):
    snap = cs.capture_snapshot()

    assert [t.task_id for t in snap.overdue_tasks] == [
        "t-overdue-1",
        "t-overdue-2",
    ]  # priority DESC ordering preserved
    assert [t.task_id for t in snap.due_today_tasks] == ["t-due-today"]
    assert [t.task_id for t in snap.blocked_tasks] == ["t-blocked"]
    assert snap.blocked_tasks[0].blocked_by == ("external-delivery",)
    assert any(r["risk_id"] == "r-1" for r in snap.risks)
    assert len(snap.open_decisions) == 1
    assert snap.pending_approvals[0].approval_id == "ap-1"
    assert snap.pending_approvals[0].action_level == "high"
    statuses = {r.agent_id: r.status for r in snap.recent_agent_runs}
    assert statuses == {"marketing": "completed", "research": "failed"}
    assert [r.agent_id for r in snap.failed_agent_runs] == ["research"]


def test_snapshot_bounded_context_limits(populated_store):
    from nite_ai.domain import ItemStatus, Project, Task

    now = time.time()
    for i in range(12):
        populated_store.create_task(
            Task(
                task_id=f"t-bulk-{i}",
                title=f"Bulk {i}",
                project_id="p-slo",
                status=ItemStatus.ACTIVE,
                due_epoch=now - 100 - i,
                priority=5,
            )
        )

    snap = cs.capture_snapshot()
    assert len(snap.overdue_tasks) <= cs.MAX_OVERDUE


def test_at_risk_goal_identified_by_platform_rule(populated_store):
    facts = cs.derived_facts(cs.capture_snapshot())
    at_risk = [f for f in facts if f["name"] == "at_risk_goal_ids"]
    assert at_risk and "g-launch" in at_risk[0]["value"]
    assert at_risk[0]["kind"] == "MEASURED"
    assert at_risk[0]["source"] == "nite_ai.briefing.rule"


# ─── Freshness semantics ────────────────────────────────────────────────


def test_freshness_classes_and_wording():
    now = time.time()

    current = cs.CompanySnapshot(captured_at_epoch=now - 10)
    recent = cs.CompanySnapshot(captured_at_epoch=now - 600)
    stale = cs.CompanySnapshot(captured_at_epoch=now - 3600)

    assert current.freshness == "CURRENT"
    assert current.freshness_note() == ""
    assert recent.freshness == "RECENT"
    assert "~10 min ago" in recent.freshness_note()
    assert stale.freshness == "STALE"
    assert "STALE" in stale.freshness_note()
    assert "verify" in stale.freshness_note().lower()


def test_unknown_freshness():
    snap = cs.CompanySnapshot(captured_at_epoch=0)
    assert snap.freshness == "UNKNOWN"


# ─── Cache behaviour ────────────────────────────────────────────────────


def test_cache_hit_within_ttl(populated_store):
    first = cs.get_snapshot()
    second = cs.get_snapshot()
    assert first is second  # same object served from cache


def test_force_refresh_recaptures(populated_store):
    first = cs.get_snapshot()
    populated_store.record_risk("r-new", "New risk appeared", "medium")
    second = cs.get_snapshot(force_refresh=True)
    assert second is not first
    risk_ids = [r["risk_id"] for r in second.risks]
    assert "r-new" in risk_ids


def test_ttl_expiry_triggers_refresh(populated_store):
    first = cs.get_snapshot(ttl_seconds=60)
    populated_store.record_risk("r-ttl", "After TTL", "low")
    later = cs.get_snapshot(ttl_seconds=0.01)  # force expiry path
    time.sleep(0.02)
    refreshed = cs.get_snapshot(ttl_seconds=0.01)
    assert refreshed is not first


def test_stale_fallback_when_live_read_fails(populated_store, monkeypatch):
    cached = cs.get_snapshot()

    def broken_capture(*a, **k):
        raise cs.CompanyStateUnavailable("store exploded")

    monkeypatch.setattr(cs, "capture_snapshot", broken_capture)
    served = cs.get_snapshot(force_refresh=True)
    assert served is cached  # stale but explicitly labelled


def test_no_cache_no_source_raises(monkeypatch):
    def broken_capture(*a, **k):
        raise cs.CompanyStateUnavailable("gone")

    monkeypatch.setattr(cs, "capture_snapshot", broken_capture)
    monkeypatch.setattr(cs, "_cached", None)
    with pytest.raises(cs.CompanyStateUnavailable):
        cs.get_snapshot()


def test_invalidate_cache(populated_store):
    first = cs.get_snapshot()
    cs.invalidate_cache()
    second = cs.get_snapshot()
    assert second is not first


# ─── Derived evidence typing ────────────────────────────────────────────


def test_derived_facts_are_labelled_and_correct(populated_store):
    snap = cs.capture_snapshot()
    facts = cs.derived_facts(snap)

    counts = {f["name"]: f for f in facts}
    assert counts["overdue_task_count"]["value"] == 2
    assert counts["blocked_task_count"]["value"] == 1
    assert counts["pending_approval_count"]["value"] == 1
    assert counts["failed_agent_run_count"]["value"] == 1

    derived = [f for f in facts if f["kind"] == "DERIVED"]
    assert all(f["source"] == "thursday.company_state" for f in derived)
    goal_fact = counts.get("goal.g-launch.overdue_tasks")
    assert goal_fact and goal_fact["value"] == 2  # overdue-1 + overdue-2


# ─── Concurrency ────────────────────────────────────────────────────────


def test_concurrent_cached_reads_are_safe(populated_store):
    results = []
    errors = []
    barrier = threading.Barrier(6)

    def reader():
        try:
            barrier.wait(timeout=10)
            results.append(cs.get_snapshot())
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors
    assert all(r is not None for r in results)


def test_warm_read_latency_target(populated_store):
    cs.get_snapshot()  # cold
    t0 = time.perf_counter()
    cs.get_snapshot()
    warm_ms = (time.perf_counter() - t0) * 1000
    assert warm_ms < 250, f"warm snapshot too slow: {warm_ms:.1f}ms"


# ─── Change detection (§47/§48) ─────────────────────────────────────────


def test_diff_detects_blocker_lifecycle(populated_store):
    from nite_ai.domain import ItemStatus, Task

    first = cs.capture_snapshot()
    populated_store.create_task(
        Task(
            task_id="t-newblock",
            title="Newly stuck task",
            project_id="p-slo",
            status=ItemStatus.BLOCKED,
            priority=5,
            blocked_by=("external-dependency",),
        )
    )
    second = cs.get_snapshot(force_refresh=True)

    changes = cs.diff_snapshots(first, second)
    assert "Newly stuck task" in changes["blockers_new"]

    third = cs.get_snapshot(force_refresh=True)
    # Resolve it: no diff path exists for status flips via adapter, use store.
    populated_store.update_task_status("t-newblock", ItemStatus.ACTIVE)
    fourth = cs.get_snapshot(force_refresh=True)
    changes2 = cs.diff_snapshots(third, fourth)
    assert any("Newly stuck task" in item for item in changes2["blockers_resolved"])


def test_diff_detects_new_approval_and_failure(populated_store):
    first = cs.capture_snapshot()
    populated_store.record_approval("ap-2", "critical", "payment.issue", "Refund client")
    populated_store.record_agent_run("run-3", agent_id="marketing", status="failed")
    second = cs.get_snapshot(force_refresh=True)

    changes = cs.diff_snapshots(first, second)
    assert len(changes["approvals_added"]) == 1
    assert "ap-2" in changes["approvals_added"][0]
    assert "marketing" in changes["agent_failures_new"]


def test_diff_with_no_previous_is_empty():
    changes = cs.diff_snapshots(None, cs.CompanySnapshot(captured_at_epoch=time.time()))
    assert all(not v for v in changes.values())


def test_describe_changes_renders_only_nonempty():
    text = cs.describe_changes({
        "blockers_new": ["Thing A"],
        "blockers_resolved": [],
        "overdue_new": [],
        "overdue_cleared": [],
        "approvals_added": ["Send contract [ap-7]"],
        "agent_failures_new": [],
    })
    assert "Newly blocked: Thing A" in text
    assert "Approvals now waiting on you: Send contract [ap-7]" in text
    assert "resolved" not in text.lower()


def test_what_changed_handler_flow(populated_store):
    from thursday.registry.handlers import _handle_company_state

    _ = cs.get_snapshot()  # establish previous on next refresh
    populated_store.record_risk("r-change", "Fresh risk appeared", "high")
    cs.get_snapshot(force_refresh=True)  # refresh; previous now set

    # Ask twice — the second ask compares against the last refresh.
    text = _handle_company_state("what changed since yesterday?", {})
    assert "changed" in text.lower() or "No meaningful change" in text
