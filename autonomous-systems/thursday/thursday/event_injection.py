"""Deterministic event injection for Thursday V2-I.

Simulated company evolution is driven by reproducible events:

    repository commit, branch divergence, test regression/recovery,
    dependency availability, blocker creation/resolution, priority
    change, resource contention, owner decision, approval grant /
    rejection / expiry, security policy change, specialist failure,
    process crash, stale report, contradictory report, malicious
    artifact, symlink attack, fake receipt, secret-bearing artifact,
    candidate supersession.

Two sources of events exist:

* ``scripted`` — a hand-authored scenario (canonical multi-week run);
  provenance "script".
* ``seeded`` — random-but-reproducible evolution from a seed;
  provenance "seeded".

Every event carries an id, day, kind and payload so runs can be replayed
exactly and event provenance can be audited.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    REPO_COMMIT = "REPO_COMMIT"
    BRANCH_DIVERGE = "BRANCH_DIVERGE"
    TEST_REGRESSION = "TEST_REGRESSION"
    TEST_RECOVERY = "TEST_RECOVERY"
    DEPENDENCY_LANDED = "DEPENDENCY_LANDED"
    BLOCKER_CREATED = "BLOCKER_CREATED"
    BLOCKER_RESOLVED = "BLOCKER_RESOLVED"
    PRIORITY_CHANGE = "PRIORITY_CHANGE"
    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"
    OWNER_DECISION = "OWNER_DECISION"
    APPROVAL_GRANT = "APPROVAL_GRANT"
    APPROVAL_REJECTION = "APPROVAL_REJECTION"
    APPROVAL_EXPIRY = "APPROVAL_EXPIRY"
    SECURITY_POLICY_CHANGE = "SECURITY_POLICY_CHANGE"
    SPECIALIST_FAILURE = "SPECIALIST_FAILURE"
    PROCESS_CRASH = "PROCESS_CRASH"
    STALE_REPORT = "STALE_REPORT"
    CONTRADICTORY_REPORT = "CONTRADICTORY_REPORT"
    MALICIOUS_ARTIFACT = "MALICIOUS_ARTIFACT"
    SYMLINK_ATTACK = "SYMLINK_ATTACK"
    FAKE_RECEIPT = "FAKE_RECEIPT"
    SECRET_ARTIFACT = "SECRET_ARTIFACT"
    CANDIDATE_SUPERSESSION = "CANDIDATE_SUPERSESSION"


@dataclass(frozen=True)
class Event:
    """One deterministic company-evolution event."""

    event_id: str
    day: int
    kind: str
    payload: dict[str, Any]
    provenance: str            # "script" | "seeded:<seed>"
    seq: int = 0               # ordering within the same day


def apply_event(company, event: Event) -> None:
    """Mutate the synthetic company per an event's kind+payload."""
    pid = event.payload.get("project", "")
    k = event.kind
    if k == EventKind.REPO_COMMIT.value:
        company.commit_to_main(pid, event.payload["new_sha"])
    elif k == EventKind.BRANCH_DIVERGE.value:
        company.add_feature_branch(pid, event.payload.get("branch", "feat/x"),
                                   event.payload["new_sha"])
    elif k == EventKind.TEST_REGRESSION.value:
        company.set_tests(pid, False, event.payload.get("suite", "ci"))
    elif k == EventKind.TEST_RECOVERY.value:
        company.set_tests(pid, True)
    elif k == EventKind.DEPENDENCY_LANDED.value:
        company.set_dependency(pid, event.payload["dependency"], True)
    elif k == EventKind.BLOCKER_CREATED.value:
        company.set_external_blocker(pid, event.payload["blocker"])
    elif k == EventKind.BLOCKER_RESOLVED.value:
        company.set_external_blocker(pid, "")
    elif k == EventKind.PRIORITY_CHANGE.value:
        company.set_priority(pid, int(event.payload["priority"]))
    elif k in (EventKind.RESOURCE_CONTENTION.value,
               EventKind.PROCESS_CRASH.value,
               EventKind.STALE_REPORT.value,
               EventKind.CONTRADICTORY_REPORT.value,
               EventKind.MALICIOUS_ARTIFACT.value,
               EventKind.SYMLINK_ATTACK.value,
               EventKind.FAKE_RECEIPT.value,
               EventKind.SECRET_ARTIFACT.value,
               EventKind.CANDIDATE_SUPERSESSION.value,
               EventKind.SPECIALIST_FAILURE.value,
               EventKind.SECURITY_POLICY_CHANGE.value):
        pass   # handled by the runner at execution time, not on the company
    elif k in (EventKind.OWNER_DECISION.value,
               EventKind.APPROVAL_GRANT.value,
               EventKind.APPROVAL_REJECTION.value,
               EventKind.APPROVAL_EXPIRY.value):
        pass   # owner/approval events are consumed by the runner's gates
    else:
        raise ValueError(f"Unknown event kind {k!r}")


def seeded_events(seed: int, days: int,
                  projects: tuple[str, ...] = ("alpha", "beta", "gamma"),
                  per_day_range: tuple[int, int] = (1, 4)) -> list[Event]:
    """Reproducible random evolution stream over ``days`` days."""
    rng = random.Random(seed)
    out: list[Event] = []
    sha_counter = 0
    for day in range(days):
        n = rng.randint(*per_day_range)
        for i in range(n):
            roll = rng.random()
            pid = rng.choice(projects)
            if roll < 0.30:
                sha_counter += 1
                ev = Event(f"s{day}-{i}", day, EventKind.REPO_COMMIT.value,
                           {"project": pid, "new_sha": f"c{sha_counter}"},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.45:
                ev = Event(f"s{day}-{i}", day,
                           (EventKind.TEST_REGRESSION.value if rng.random() < 0.5
                            else EventKind.TEST_RECOVERY.value),
                           {"project": pid, "suite": "unit"},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.60:
                ev = Event(f"s{day}-{i}", day,
                           (EventKind.BLOCKER_CREATED.value
                            if rng.random() < 0.5
                            else EventKind.BLOCKER_RESOLVED.value),
                           {"project": pid, "blocker": f"vendor-outage-{day}"},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.72:
                ev = Event(f"s{day}-{i}", day, EventKind.PRIORITY_CHANGE.value,
                           {"project": pid, "priority": rng.randint(1, 5)},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.80:
                ev = Event(f"s{day}-{i}", day, EventKind.DEPENDENCY_LANDED.value,
                           {"project": pid, "dependency": "vendor-sdk"},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.88:
                ev = Event(f"s{day}-{i}", day, EventKind.RESOURCE_CONTENTION.value,
                           {"project": pid},
                           provenance=f"seeded:{seed}", seq=i)
            elif roll < 0.94:
                ev = Event(f"s{day}-{i}", day, EventKind.PROCESS_CRASH.value,
                           {"phase": rng.choice(["observe", "execute",
                                                 "approval_wait", "reconcile"])},
                           provenance=f"seeded:{seed}", seq=i)
            else:
                ev = Event(f"s{day}-{i}", day, EventKind.BRANCH_DIVERGE.value,
                           {"project": pid, "branch": "feat/diverge",
                            "new_sha": f"d{sha_counter}-{day}{i}"},
                           provenance=f"seeded:{seed}", seq=i)
            out.append(ev)
    return out


@dataclass
class EventSchedule:
    """Ordered day-indexed event stream."""

    events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.events.sort(key=lambda e: (e.day, e.seq))

    def events_for_day(self, day: int) -> list[Event]:
        return [e for e in self.events if e.day == day]

    @classmethod
    def from_script(cls, events: list[Event]) -> "EventSchedule":
        return cls(events=list(events))

    @classmethod
    def seeded(cls, seed: int, days: int) -> "EventSchedule":
        return cls(events=seeded_events(seed, days))

    def to_state(self) -> dict[str, Any]:
        return {"events": [e.__dict__ for e in self.events]}

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "EventSchedule":
        return cls(events=[Event(**e) for e in state.get("events", ())])


__all__ = ["Event", "EventKind", "EventSchedule", "apply_event",
           "seeded_events"]
