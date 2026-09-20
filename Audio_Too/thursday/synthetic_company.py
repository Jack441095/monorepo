"""Persistent synthetic company for Thursday V2-I long-horizon runs.

V2-I qualification needs an evolving environment, not a fresh universe
per cycle. The SyntheticCompany holds multiple projects with branches,
SHAs, test status, dependencies, priorities, blockers and protection
flags — and persists across simulated weeks.

It is deliberately lightweight (plain dataclasses + JSON persistence):
the point is temporal coherence of Thursday's reasoning, not git
plumbing. SHAs are opaque strings that change only through events,
so stale-SHA scenarios are exact and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Project:
    """One evolving synthetic project."""

    project_id: str
    name: str
    priority: int                          # lower = more important
    main_sha: str = "s0"
    feature_branches: dict[str, str] = field(default_factory=dict)
    tests_passing: bool = True
    failing_test_suite: str = ""
    dependencies: dict[str, bool] = field(default_factory=dict)  # dep → landed?
    external_blocker: str = ""             # non-empty ⇒ externally blocked
    protected: bool = False                # owner said never-modify
    open_work_items: int = 0

    def clone(self) -> "Project":
        return Project(
            project_id=self.project_id, name=self.name, priority=self.priority,
            main_sha=self.main_sha, feature_branches=dict(self.feature_branches),
            tests_passing=self.tests_passing,
            failing_test_suite=self.failing_test_suite,
            dependencies=dict(self.dependencies),
            external_blocker=self.external_blocker,
            protected=self.protected,
            open_work_items=self.open_work_items,
        )


@dataclass
class CompanyState:
    """Whole-company snapshot at one simulated instant."""

    epoch: float
    day: int
    projects: dict[str, Project] = field(default_factory=dict)

    def project(self, pid: str) -> Project | None:
        return self.projects.get(pid)


def default_company() -> dict[str, Project]:
    """Canonical starting company used across scenarios/soak/holdout."""
    return {
        "alpha": Project(
            project_id="alpha", name="Project Alpha", priority=1,
            feature_branches={"feat/cache": "a1"}, open_work_items=3,
        ),
        "beta": Project(
            project_id="beta", name="Project Beta", priority=2,
            feature_branches={"feat/export": "b1"}, open_work_items=2,
        ),
        "gamma": Project(
            project_id="gamma", name="Project Gamma", priority=3,
            dependencies={"vendor-sdk": False}, open_work_items=4,
        ),
        "delta": Project(
            project_id="delta", name="Project Delta", priority=4,
            protected=True,                      # owner forbade modification
        ),
    }


class SyntheticCompany:
    """Persistent evolving company; mutated only by events."""

    def __init__(self) -> None:
        self.projects: dict[str, Project] = default_company()

    # ------------------------------------------------------------------
    # Observation surface (read-only views for the loop)
    # ------------------------------------------------------------------

    def snapshot(self, *, epoch: float, day: int) -> CompanyState:
        return CompanyState(
            epoch=epoch, day=day,
            projects={pid: p.clone() for pid, p in self.projects.items()},
        )

    def is_blocked(self, project_id: str) -> bool:
        p = self.projects.get(project_id)
        if p is None:
            return True
        if p.external_blocker:
            return True
        if any(landed is False for landed in p.dependencies.values()):
            return True
        return False

    def blocker_key(self, project_id: str) -> str:
        p = self.projects[project_id]
        if p.external_blocker:
            return f"{project_id}:blocker:{p.external_blocker}"
        missing = [d for d, ok in p.dependencies.items() if not ok]
        if missing:
            return f"{project_id}:dep:{sorted(missing)[0]}"
        return ""

    # ------------------------------------------------------------------
    # Mutation primitives (invoked ONLY by the event engine / scenario)
    # ------------------------------------------------------------------

    def commit_to_main(self, project_id: str, new_sha: str) -> None:
        self.projects[project_id].main_sha = new_sha

    def set_tests(self, project_id: str, passing: bool, suite: str = "") -> None:
        p = self.projects[project_id]
        p.tests_passing = passing
        p.failing_test_suite = "" if passing else suite

    def set_dependency(self, project_id: str, dep: str, landed: bool) -> None:
        self.projects[project_id].dependencies[dep] = landed

    def set_external_blocker(self, project_id: str, blocker: str) -> None:
        self.projects[project_id].external_blocker = blocker

    def set_priority(self, project_id: str, priority: int) -> None:
        self.projects[project_id].priority = priority

    def add_feature_branch(self, project_id: str, branch: str, sha: str) -> None:
        self.projects[project_id].feature_branches[branch] = sha

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {"projects": {pid: p.__dict__ for pid, p in self.projects.items()}}

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SyntheticCompany":
        comp = cls()
        comp.projects = {}
        for pid, raw in state.get("projects", {}).items():
            raw = dict(raw)
            raw["feature_branches"] = dict(raw.get("feature_branches", {}))
            raw["dependencies"] = dict(raw.get("dependencies", {}))
            comp.projects[pid] = Project(**raw)
        return comp


__all__ = ["CompanyState", "Project", "SyntheticCompany", "default_company"]
