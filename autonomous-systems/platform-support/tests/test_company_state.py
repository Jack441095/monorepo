"""Company state store + daily brief / weekly review tests (synthetic data)."""

import sqlite3

import pytest

from nite_ai.briefing import assemble_daily_brief, assemble_weekly_review
from nite_ai.company_store import SCHEMA_VERSION, CompanyStore, connect, open_store, schema_version
from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task
from nite_ai.errors import ValidationError

NOW = 1_755_744_000.0  # fixed epoch for deterministic tests


@pytest.fixture
def store(tmp_path):
    conn, st = open_store(tmp_path / "company.db")
    yield st
    conn.close()


def company_fixture(st: CompanyStore):
    """Synthetic NITE DSP company data — no real/customer data."""
    st.create_goal(Goal(goal_id="g-company", kind=GoalKind.COMPANY,
                        title="Ship NITE DSP product line"))
    q = Goal(goal_id="g-q3", kind=GoalKind.QUARTERLY, title="Q3 release readiness",
             parent_goal_id="g-company", progress=0.4, status=ItemStatus.ACTIVE)
    st.create_goal(q)
    st.create_project(Project(project_id="p-slo", title="SLO release", goal_id="g-q3"))
    st.create_project(Project(project_id="p-aip", title="AI Platform", goal_id="g-q3"))
    st.create_task(Task(task_id="t-release-blocker", title="Fix SLO release blocker",
                        project_id="p-slo", status=ItemStatus.BLOCKED,
                        blocked_by=("t-classification",), priority=9))
    st.create_task(Task(task_id="t-overdue-review", title="Website review overdue",
                        project_id="p-aip", status=ItemStatus.ACTIVE,
                        due_epoch=NOW - 86400, priority=7))
    st.create_task(Task(task_id="t-due-today", title="Integration work",
                        project_id="p-aip", status=ItemStatus.ACTIVE,
                        due_epoch=NOW + 3600, priority=6))
    st.record_decision("d-1", "Defer local runtime POC until adapters proven")
    st.record_risk("r-1", "Single-maintainer bus factor on platform", severity="high")
    st.record_agent_run("run-1", agent_id="kenn-main", status="completed",
                        task_id="t-due-today", trace_id="trace-1",
                        started_at_epoch=NOW - 100, finished_at_epoch=NOW - 50)




def test_store_migration_and_version(store):
    # version row exists with expected value
    row = store._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    assert row["v"] == SCHEMA_VERSION


def test_goal_crud_and_validation(store):
    company_fixture(store)
    goals = {g.goal_id: g for g in store.list_goals()}
    assert goals["g-q3"].parent_goal_id == "g-company"
    store.update_goal_status("g-q3", ItemStatus.ACTIVE, progress=0.5)
    updated = {g.goal_id: g for g in store.list_goals()}["g-q3"]
    assert updated.progress == 0.5 and updated.status is ItemStatus.ACTIVE
    with pytest.raises(ValidationError):
        store.update_goal_status("missing", ItemStatus.ACTIVE)
    with pytest.raises(ValidationError):
        store.update_goal_status("g-q3", ItemStatus.ACTIVE, progress=2.0)


def test_task_persistence_and_foreign_keys(store, tmp_path):
    conn, st = open_store(tmp_path / "fk.db")
    goal = Goal(goal_id="g1", kind=GoalKind.COMPANY, title="root")
    st.create_goal(goal)
    st.create_project(Project(project_id="p1", title="proj", goal_id="g1"))
    st.create_task(Task(task_id="tk1", title="work", project_id="p1"))
    # FK enforcement: task referencing missing project must fail
    with pytest.raises(sqlite3.IntegrityError):
        st.create_task(Task(task_id="tk2", title="orphan", project_id="nope"))
    conn.close()
    # reopen persistence: data survives
    conn2, st2 = open_store(tmp_path / "fk.db")
    assert [t.task_id for t in st2.list_tasks()] == ["tk1"]
    conn2.close()


def test_future_schema_rejected(store, tmp_path):
    path = tmp_path / "future.db"
    conn = connect(path)
    conn.execute("INSERT INTO schema_version (version, applied_at_epoch) VALUES (999, 0)")
    conn.commit()
    with pytest.raises(ValidationError):
        connect(path)  # newer schema than supported -> refuse
    conn.close()


def test_decisions_risks_agent_runs(store):
    company_fixture(store)
    assert [d["decision_id"] for d in store.list_open_decisions()] == ["d-1"]
    assert [r["risk_id"] for r in store.list_active_risks()] == ["r-1"]
    runs = store.recent_agent_runs()
    assert runs[0]["agent_id"] == "kenn-main" and runs[0]["status"] == "completed"


def test_daily_brief_priorities_deterministic(store):
    company_fixture(store)
    brief = assemble_daily_brief(store, now_epoch=NOW)
    # overdue first, then due-today; blockers surfaced separately
    assert brief.top_priorities == ["t-overdue-review", "t-due-today"]
    assert brief.blockers == ["t-release-blocker"]
    assert brief.due_today == ["t-due-today"]
    assert brief.agent_completions == ["kenn-main"]


def test_daily_brief_goals_at_risk():
    from nite_ai.company_store import connect as c

    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn, st = open_store(path)
    try:
        st.create_goal(Goal(goal_id="g-risk", kind=GoalKind.COMPANY, title="at risk",
                            target_date_epoch=NOW - 100, progress=0.1,
                            status=ItemStatus.ACTIVE))
        brief = assemble_daily_brief(st, now_epoch=NOW)
        assert brief.goals_at_risk == ["g-risk"]
    finally:
        conn.close()
        os.unlink(path)


def test_weekly_review_assembly(store):
    company_fixture(store)
    review = assemble_weekly_review(store, now_epoch=NOW)
    assert review.week_label.startswith("20")
    assert ("g-q3", 0.4) in review.goals_progress
    assert review.risks == ("r-1",)
    assert "d-1" in review.decisions_made
