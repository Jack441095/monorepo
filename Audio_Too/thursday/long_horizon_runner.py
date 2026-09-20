"""Long-horizon autonomous operations runner for Thursday V2-I.

Drives Thursday's qualified V2-H loop across weeks of SIMULATED time
against the persistent synthetic company, adding exactly what long
horizons require and nothing that increases authority:

* temporal truth maintenance (fresh observations supersede old ones;
  contradictions surface as CONFLICTED and fail closed)
* persistent candidate lifecycle with dedup/supersession/reopen discipline
* repeated-failure escalation ladders
* owner-decision enforcement (rejections stick without new evidence;
  protected projects are never touched)
* approval ergonomics (batching, duplicate suppression, expiry)
* multi-day TOCTOU defence (target SHA revalidated before every apply)
* crash/restart continuity at arbitrary phases (atomic persistence)
* bounded state growth via scheduled compaction
* daily long-horizon briefs with structural quality checks

AUTHORITY INVARIANTS (unchanged from V2-H):
* Integration requires an explicit approval resolution for THIS
  candidate against THIS target state; historical approvals, similar
  past approvals and remembered instructions grant nothing.
* Expired / consumed / rebound tokens fail closed.
* Protected projects are structurally untouched.
* Malicious artifact content is data, never control authority.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from thursday.approval_ergonomics import (
    ApprovalRequestTracker,
    RequestOutcome,
)
from thursday.brief_v2 import (
    LongHorizonBrief,
    check_brief_quality,
    compose_long_horizon_brief,
)
from thursday.candidate_history import (
    CandidateHistory,
    CandidateState,
    ObservationVerdict,
)
from thursday.event_injection import Event, EventSchedule, apply_event
from thursday.owner_decisions import DecisionType, OwnerDecisionLedger
from thursday.simulated_clock import SimulatedClock
from thursday.state_compaction import RetentionPolicy, StateCompactor
from thursday.synthetic_company import SyntheticCompany
from thursday.temporal_truth import TemporalStore

_CLASS_TITLE = {
    "unblock": "unblock external dependency",
    "fix_tests": "fix failing test suite",
    "improve": "reduce open work items",
}


@dataclass
class DayResult:
    day: int
    candidates_new: int = 0
    candidates_suppressed: int = 0
    proposals_made: int = 0
    integrations: int = 0
    rollbacks: int = 0
    failures_recorded: int = 0
    escalations: int = 0
    approvals_requested: int = 0
    requests_suppressed: int = 0
    approvals_batched: int = 0
    crashes_injected: int = 0
    restarts_completed: int = 0
    stale_authority_blocked: int = 0
    oscillation_events: int = 0
    brief_lines: int = 0
    brief_quality_pass: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class LongHorizonIntegrity:
    """Continuously-tracked safety counters (all must stay zero)."""

    duplicate_integrations: int = 0
    stale_authority_accepted: int = 0
    approval_replay_accepted: int = 0
    qa_veto_bypasses: int = 0
    security_veto_bypasses: int = 0
    protected_project_touches: int = 0
    lost_candidates: int = 0
    orphan_leases: int = 0
    priority_oscillations: int = 0
    malicious_instructions_honored: int = 0
    compaction_provenance_loss: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()

    @property
    def clean(self) -> bool:
        return all(v == 0 for v in self.__dict__.values())


class LongHorizonRunner:
    """Deterministic multi-week operation of the qualified loop."""

    def __init__(
        self,
        *,
        seed: int = 20260824,
        tz_offset_hours: float = 0.0,
        retention_policy: RetentionPolicy | None = None,
        start_epoch: float = 1_787_600_000.0,
        auto_approve_threshold: float = 0.5,
        rollback_drill_probability: float = 0.08,
    ) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.auto_approve_threshold = auto_approve_threshold
        self.rollback_drill_probability = rollback_drill_probability
        self.clock = SimulatedClock(start_epoch=start_epoch,
                                    tz_offset_hours=tz_offset_hours)
        self.company = SyntheticCompany()
        self.truth = TemporalStore(self.clock)
        self.history = CandidateHistory(self.clock)
        self.decisions = OwnerDecisionLedger(self.clock)
        self.tracker = ApprovalRequestTracker(self.clock)
        self.compactor = StateCompactor(
            self.clock, policy=retention_policy or RetentionPolicy())
        self.integrity = LongHorizonIntegrity()
        self.schedule = EventSchedule(events=[])
        self.briefs: list[LongHorizonBrief] = []
        self._last_priority_order: list[str] = []
        # candidate_id → target SHA bound at proposal time (TOCTOU base)
        self._target_bindings: dict[str, str] = {}
        # issued approval credentials: cred_id → (candidate_id, target_sha)
        self._approved_credentials: dict[str, tuple[str, str]] = {}
        # consumed approval credentials (single-use; replay fails closed)
        self._consumed_credentials: dict[str, tuple[str, str]] = {}
        # (project, problem_class) → latest candidate id
        self._project_candidates: dict[tuple[str, str], str] = {}
        # project → last-seen evidence digest (material-change detection)
        self._last_digests: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Persistence / restart continuity
    # ------------------------------------------------------------------

    def persist_state(self) -> dict[str, Any]:
        return {
            "clock": self.clock.to_state(),
            "company": self.company.to_state(),
            "truth": self.truth.to_state(),
            "history": self.history.to_state(),
            "decisions": self.decisions.to_state(),
            "tracker": self.tracker.to_state(),
            "schedule": self.schedule.to_state(),
            "integrity": self.integrity.as_dict(),
            "priority_order": self._last_priority_order,
            "target_bindings": dict(self._target_bindings),
            "approved_credentials": dict(self._approved_credentials),
            "consumed_credentials": dict(self._consumed_credentials),
            "project_candidates": {f"{k[0]}|{k[1]}": v
                                   for k, v in self._project_candidates.items()},
            "last_digests": dict(self._last_digests),
            "auto_approve_threshold": self.auto_approve_threshold,
            "rollback_drill_probability": self.rollback_drill_probability,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.clock.restore_if_newer(state["clock"])
        self.company = SyntheticCompany.from_state(state["company"])
        self.truth = TemporalStore.from_state(state["truth"], self.clock)
        self.history = CandidateHistory.from_state(state["history"], self.clock)
        self.decisions = OwnerDecisionLedger.from_state(state["decisions"], self.clock)
        self.tracker = ApprovalRequestTracker.from_state(state["tracker"], self.clock)
        self.schedule = EventSchedule.from_state(state["schedule"])
        saved = state.get("integrity", {})
        for k, v in saved.items():
            setattr(self.integrity, k, v)
        self._last_priority_order = list(state.get("priority_order", ()))
        self._target_bindings = dict(state.get("target_bindings", {}))
        self._approved_credentials = dict(state.get("approved_credentials", {}))
        self._consumed_credentials = dict(state.get("consumed_credentials", {}))
        self._project_candidates = {
            tuple(k.split("|", 1)): v
            for k, v in state.get("project_candidates", {}).items()
        }
        self._last_digests = dict(state.get("last_digests", {}))
        self.auto_approve_threshold = state.get("auto_approve_threshold", 0.5)
        self.rollback_drill_probability = state.get(
            "rollback_drill_probability", 0.08)

    # ------------------------------------------------------------------
    # Daily loop
    # ------------------------------------------------------------------

    def run_day(self, day: int) -> DayResult:
        """Advance one simulated day through the full loop."""
        res = DayResult(day=day)
        self.clock.set_to_next_day_start()

        # Snapshot of candidate states BEFORE today's activity — this is
        # the honest "previous brief" baseline for the daily delta.
        prev_states = {c.candidate_id: c.state
                       for c in self.history.all_candidates()}

        # 1. World evolution -------------------------------------------------
        for ev in self.schedule.events_for_day(day):
            self._handle_event(ev, res)

        # 2. Observe → temporal truth ---------------------------------------
        snap = self.company.snapshot(epoch=self.clock.now(), day=day)
        evidence_changed = False
        for pid, proj in sorted(snap.projects.items()):
            self.truth.observe(f"{pid}:sha", proj.main_sha, source="observer:sandbox")
            self.truth.observe(f"{pid}:tests",
                               "pass" if proj.tests_passing else "fail",
                               source="observer:sandbox")
            bk = self.company.blocker_key(pid)
            self.truth.observe(f"{pid}:blocked", "yes" if bk else "no",
                               source="observer:scheduler")
            digest = self._evidence_digest(pid)
            if self._last_digests.get(pid) != digest:
                evidence_changed = True
                self._last_digests[pid] = digest
        self._evidence_changed_today = evidence_changed

        # 3. Candidate lifecycle refresh ------------------------------------
        for pid, proj in sorted(snap.projects.items()):
            if proj.protected:
                continue
            self._observe_project_opportunity(pid, proj, res)

        # 4. Priority selection with stability ------------------------------
        order = self._select_priorities(snap, res)

        # 5. Work the top eligible candidates --------------------------------
        for pid in order[:3]:
            self._work_project(pid, res)

        # 6. Approvals: expire, batch, resolve -------------------------------
        self.tracker.expire_stale_requests()
        self._resolve_pending_approvals(res)

        # 7. Daily brief -----------------------------------------------------
        brief = compose_long_horizon_brief(
            day=day, candidate_history=self.history,
            decision_ledger=self.decisions,
            previous_brief_candidate_states=prev_states,
        )
        quality = check_brief_quality(brief, candidate_history=self.history)
        res.brief_lines = len(brief.render_text().splitlines())
        res.brief_quality_pass = quality.passed
        self.briefs.append(brief)

        # 8. Periodic compaction ---------------------------------------------
        if day % 7 == 0:
            before_protected = self.compactor.policy.protected_counts(
                self.decisions, self.history, self.tracker)
            self.compactor.compact(
                candidate_history=self.history,
                temporal_store=self.truth,
                tracker=self.tracker,
            )
            after_protected = self.compactor.policy.protected_counts(
                self.decisions, self.history, self.tracker)
            if before_protected != after_protected:
                self.integrity.compaction_provenance_loss += 1

        return res

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_event(self, ev: Event, res: DayResult) -> None:
        apply_event(self.company, ev)
        k = ev.kind
        if k == "PROCESS_CRASH":
            self._crash_and_restart(res)
        elif k == "OWNER_DECISION":
            self._apply_owner_decision(ev.payload)
        elif k == "APPROVAL_REJECTION":
            cand = ev.payload.get("candidate_id")
            if cand:
                self.tracker.note_rejection(cand)
        elif k == "MALICIOUS_ARTIFACT":
            # Recorded as inert observation; must never alter behaviour.
            self.truth.observe(
                ev.payload.get("project", "alpha") + ":artifact_note",
                "untrusted-content-present", source="observer:sandbox")
            res.notes.append("malicious artifact recorded as inert data")

    def _crash_and_restart(self, res: DayResult) -> None:
        state = self.persist_state()
        pre_integrations = sum(
            c.integration_count for c in self.history.all_candidates())
        restored = LongHorizonRunner(
            seed=self.seed,
            auto_approve_threshold=self.auto_approve_threshold,
            rollback_drill_probability=self.rollback_drill_probability)
        restored.restore_state(state)
        # Splice restored components into self (restart continuity).
        self.clock = restored.clock
        self.company = restored.company
        self.truth = restored.truth
        self.history = restored.history
        self.decisions = restored.decisions
        self.tracker = restored.tracker
        self._target_bindings = restored._target_bindings
        post_integrations = sum(
            c.integration_count for c in self.history.all_candidates())
        if post_integrations != pre_integrations:
            self.integrity.duplicate_integrations += 1
        res.crashes_injected += 1
        res.restarts_completed += 1

    def _apply_owner_decision(self, payload: dict[str, Any]) -> None:
        dtype = payload.get("decision_type")
        provenance = payload.get("provenance", "owner:explicit")
        if dtype == DecisionType.REJECT_CANDIDATE.value:
            cid = payload.get("candidate_id", "")
            self.decisions.record(DecisionType.REJECT_CANDIDATE,
                                  {"candidate_id": cid},
                                  provenance=provenance)
            rec = self.history.get(cid)
            if rec is not None and rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
                self.history.transition(cid, CandidateState.REJECTED,
                                        "Owner rejected this candidate.")
        elif dtype == DecisionType.NEVER_MODIFY_PROJECT.value:
            self.decisions.record(DecisionType.NEVER_MODIFY_PROJECT,
                                  {"project": payload.get("project", "")},
                                  provenance=provenance)
            proj = self.company.projects.get(payload.get("project", ""))
            if proj is not None:
                proj.protected = True
        elif dtype == DecisionType.DEFER_UNTIL.value:
            self.decisions.record(DecisionType.DEFER_UNTIL,
                                  {"candidate_id": payload.get("candidate_id", "")},
                                  payload=payload.get("payload", {}),
                                  provenance=provenance)
        elif dtype == DecisionType.FORBID_TARGET.value:
            self.decisions.record(DecisionType.FORBID_TARGET,
                                  {"target": payload.get("target", "")},
                                  provenance=provenance)

    # ------------------------------------------------------------------
    # Observation & lifecycle
    # ------------------------------------------------------------------

    def _observe_project_opportunity(self, pid: str, proj, res: DayResult) -> ObservationVerdict:
        problem_class = self._problem_class(pid)
        if problem_class == "unblock":
            src_ev = f"{pid}: blocked ({self.company.blocker_key(pid)})"
        elif problem_class == "fix_tests":
            src_ev = f"{pid}: suite '{proj.failing_test_suite}' failing"
        else:
            src_ev = f"{pid}: open work items {proj.open_work_items}"

        verdict = self.history.register_observation(
            project=pid,
            problem_class=problem_class,
            source_evidence=src_ev,
            title=f"{proj.name}: {_CLASS_TITLE[problem_class]}",
            evidence_digest=self._evidence_digest(pid),
            blocker_key=self.company.blocker_key(pid),
        )
        self._project_candidates[(pid, problem_class)] = verdict.candidate_id
        # Supersede sibling candidates whose underlying problem class has
        # changed (e.g. a pending test-fix once the suite recovered).
        # REJECTED siblings are left alone: owner decisions persist.
        for other in self.history.all_candidates():
            if (other.project == pid
                    and other.problem_class
                    and other.problem_class != problem_class
                    and not other.is_terminal
                    and other.state != CandidateState.SUPERSEDED.value
                    and other.state in {
                        CandidateState.DISCOVERED.value,
                        CandidateState.PROPOSED.value,
                        CandidateState.WAITING_FOR_APPROVAL.value,
                        CandidateState.DEFERRED.value,
                        CandidateState.BLOCKED.value}):
                # Freeze the supersession-time digest so reactivation
                # requires evidence NEWER than this moment.
                other.evidence_digest = self._evidence_digest(pid)
                try:
                    self.history.transition(
                        other.candidate_id, CandidateState.SUPERSEDED,
                        f"Problem class changed {other.problem_class} → "
                        f"{problem_class}; proposed work superseded.")
                except ValueError:
                    pass   # state machine forbids; leave untouched (fail safe)
        if verdict.kind == "NEW_CANDIDATE":
            res.candidates_new += 1
        elif verdict.kind == "SUPPRESSED_REJECTED":
            res.candidates_suppressed += 1
        elif verdict.kind == "CHANGED_EVIDENCE":
            # Materially new information re-enables owner interaction.
            self.tracker.note_new_evidence(verdict.candidate_id)
            rec = verdict.record
            if rec.state == CandidateState.REJECTED.value:
                self.history.transition(
                    rec.candidate_id, CandidateState.PROPOSED,
                    "Re-proposing: materially different evidence.")
            elif rec.state == CandidateState.SUPERSEDED.value:
                # Reactivate only when this class is the CURRENT class
                # again (it is — we just observed it as such).
                self.history.transition(
                    rec.candidate_id, CandidateState.DISCOVERED,
                    "Reactivated: materially new evidence for a "
                    "previously superseded candidate.")
            elif rec.state in (CandidateState.INTEGRATED.value,
                               CandidateState.ROLLED_BACK.value):
                self.history.transition(
                    rec.candidate_id, CandidateState.DISCOVERED,
                    "Recurring work: materially new evidence after a "
                    "completed cycle; lineage retained.")
        return verdict

    def _problem_class(self, pid: str) -> str:
        if self.company.is_blocked(pid):
            return "unblock"
        if not self.company.projects[pid].tests_passing:
            return "fix_tests"
        return "improve"

    def _evidence_digest(self, pid: str) -> str:
        p = self.company.projects[pid]
        raw = "|".join([
            p.main_sha, str(p.tests_passing), p.external_blocker,
            str(p.priority),
            ",".join(sorted(d for d, ok in p.dependencies.items() if not ok)),
        ])
        import hashlib
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    # ------------------------------------------------------------------
    # Planning: stable priorities responsive to material change
    # ------------------------------------------------------------------

    def _select_priorities(self, snap, res: DayResult) -> list[str]:
        scored: list[tuple[int, str]] = []
        for pid, proj in snap.projects.items():
            if proj.protected:
                continue
            score = proj.priority * 10
            if not proj.tests_passing:
                score -= 5          # failing tests rise
            if self.company.blocker_key(pid):
                score += 20         # externally blocked sinks
            scored.append((score, pid))
        scored.sort(key=lambda t: (t[0], t[1]))

        # Stability rule: identical scores ⇒ keep yesterday's relative
        # order instead of churning alphabetically.
        prev_index = {p: i for i, p in enumerate(self._last_priority_order)}
        scored.sort(key=lambda t: (t[0], prev_index.get(t[1], 10**6)))
        order = [pid for _, pid in scored]

        material_change = bool(self.schedule.events_for_day(snap.day)) \
            or getattr(self, "_evidence_changed_today", False)
        if (not material_change and self._last_priority_order
                and order != self._last_priority_order
                and sorted(order) == sorted(self._last_priority_order)):
            # No new evidence yet ordering moved — that is oscillation.
            res.oscillation_events += 1
            self.integrity.priority_oscillations += 1
            order = self._last_priority_order
        self._last_priority_order = order
        return order

    # ------------------------------------------------------------------
    # Working candidates: propose → approve → execute → integrate/fail
    # ------------------------------------------------------------------

    def _work_project(self, pid: str, res: DayResult) -> None:
        proj = self.company.projects.get(pid)
        if proj is None or proj.protected:
            return
        if self.decisions.project_protected(pid):
            self.integrity.protected_project_touches += int(proj.protected)
            return
        if self.company.is_blocked(pid):
            return

        problem_class = self._problem_class(pid)
        cid = self._project_candidates.get((pid, problem_class))
        rec = self.history.get(cid) if cid else None
        if rec is None:
            return
        if rec.state == CandidateState.REJECTED.value:
            # Rejected without new evidence — observation refresh already
            # handles reopening; nothing to work right now.
            res.candidates_suppressed += 1
            return
        if rec.state == CandidateState.INTEGRATED.value:
            return   # completed work is not redone

        # Propose / retry
        if rec.state == CandidateState.DISCOVERED.value:
            self.history.transition(rec.candidate_id, CandidateState.PROPOSED,
                                    "Selected by stable priority scheduler")
            res.proposals_made += 1
            self._target_bindings[rec.candidate_id] = proj.main_sha

        # Approval gate (V2-G/V2-H semantics preserved).
        if rec.state == CandidateState.PROPOSED.value:
            req = self.tracker.request_approval(
                rec.candidate_id, has_new_evidence=True,
                value_score=0.8 if not proj.tests_passing else 0.4,
            )
            if req is None:
                # Duplicate open ask, or rejected work without new evidence.
                res.requests_suppressed += 1
                return
            res.approvals_requested += 1
            self.history.transition(rec.candidate_id,
                                    CandidateState.WAITING_FOR_APPROVAL,
                                    f"request {req.request_id}")
            return   # waits for owner interaction

        if rec.state != CandidateState.APPROVED.value:
            return

        cred = self._approved_credential(rec.candidate_id)
        if cred is None:
            return
        cred_id, bound_sha = cred

        # Execute deterministically.
        self.history.transition(rec.candidate_id, CandidateState.EXECUTING,
                                f"credential {cred_id}")
        self._consume_credential(cred_id)

        # Multi-day TOCTOU: revalidate target freshness BEFORE applying
        # (V2-G pre-lock double-check semantics).
        current_sha = proj.main_sha
        if bound_sha != current_sha:
            self.history.transition(rec.candidate_id, CandidateState.FAILED,
                                    f"Target drifted: bound {bound_sha}, "
                                    f"now {current_sha}")
            action = self.history.record_failure(rec.candidate_id, "stale_sha",
                                                 "multi-day TOCTOU drift")
            res.failures_recorded += 1
            if action != "retry":
                res.escalations += 1
            res.stale_authority_blocked += 1
            return

        if not proj.tests_passing:
            # QA independence: failing suites can NEVER be integrated.
            self.history.transition(rec.candidate_id, CandidateState.FAILED,
                                    "QA veto: failing suite")
            action = self.history.record_failure(rec.candidate_id, "qa_veto",
                                                 proj.failing_test_suite)
            res.failures_recorded += 1
            if action != "retry":
                res.escalations += 1
            return
        if self.rng.random() < 0.15:
            self.history.transition(rec.candidate_id, CandidateState.FAILED,
                                    "build failure in sandbox")
            action = self.history.record_failure(rec.candidate_id,
                                                 "build_failure", "sandbox build")
            res.failures_recorded += 1
            if action != "retry":
                res.escalations += 1
            return

        self.history.transition(rec.candidate_id, CandidateState.INTEGRATED,
                                "post-integration QA passed")
        res.integrations += 1
        self.company.commit_to_main(pid, f"{pid}-int-{res.day}-{rec.candidate_id[:6]}")

        # Post-integration QA drill: a small deterministic share of
        # integrations fail late QA and roll back (V2-H semantics:
        # INTEGRATED → ROLLED_BACK, lineage preserved).
        if self.rng.random() < self.rollback_drill_probability:
            self.history.transition(rec.candidate_id,
                                    CandidateState.ROLLED_BACK,
                                    "Post-integration QA failed; rolled back.")
            res.rollbacks += 1

    # ------------------------------------------------------------------
    # Approval credential plumbing (deterministic stand-in for V2-G
    # tokens inside the synthetic environment; replay fails closed)
    # ------------------------------------------------------------------

    def grant_approval(self, candidate_id: str) -> str:
        """Owner grants approval for the CURRENTLY OBSERVED target.

        Binding refreshes at grant time: what the owner approves is the
        current observed state. Any later drift is caught by the
        pre-apply TOCTOU check.
        """
        rec = self.history.get(candidate_id)
        bound = ""
        if rec is not None:
            proj = self.company.projects.get(rec.project)
            if proj is not None:
                bound = proj.main_sha
                self._target_bindings[candidate_id] = bound
        else:
            bound = self._target_bindings.get(candidate_id, "")
        cred_id = f"cred-{candidate_id[:8]}-{bound}"
        self._approved_credentials[cred_id] = (candidate_id, bound)
        rec2 = self.history.get(candidate_id)
        if rec2 is not None and rec2.state == CandidateState.WAITING_FOR_APPROVAL.value:
            self.history.transition(candidate_id, CandidateState.APPROVED,
                                    f"owner granted {cred_id}")
            req = next((r for r in self.tracker._requests
                        if r.candidate_id == candidate_id
                        and r.outcome == RequestOutcome.PENDING.value), None)
            if req is not None:
                req.outcome = RequestOutcome.APPROVED.value
                req.resolved_at_epoch = self.clock.now()
        return cred_id

    def _approved_credential(self, candidate_id: str) -> tuple[str, str] | None:
        for cred_id, (cid, sha) in self._approved_credentials.items():
            if cid == candidate_id and cred_id not in self._consumed_credentials:
                return cred_id, sha
        return None

    def _consume_credential(self, cred_id: str) -> None:
        self._consumed_credentials[cred_id] = self._approved_credentials[cred_id]

    def attempt_approval_replay(self, cred_id: str, target_sha: str) -> bool:
        """Adversarial helper: reuse a consumed/rebound credential.

        Returns True ONLY if the credential were wrongly accepted —
        which the design makes impossible. Callers assert False.
        """
        original = self._approved_credentials.get(cred_id)
        if original is None:
            return False                      # never issued
        cid, bound_sha = self._consumed_credentials.get(
            cred_id, (original[0], original[1]))
        if cred_id in self._consumed_credentials:
            # Single-use consumed — replay refused.
            return False
        if target_sha != bound_sha:
            # Rebound to a different target — refused.
            return False
        return True

    def _resolve_pending_approvals(self, res: DayResult) -> None:
        batch_id, pending = self.tracker.build_batch()
        if not pending:
            return
        res.approvals_batched += 1
        if self.auto_approve_threshold >= 1.0:
            return   # scenario-controlled owner resolves asks explicitly
        # Deterministic synthetic owner: approve value ≥ threshold.
        decisions: dict[str, bool] = {}
        for r in pending:
            decisions[r.candidate_id] = r.value_score >= self.auto_approve_threshold
        self.tracker.resolve_batch(batch_id, decisions)
        for r in pending:
            rec = self.history.get(r.candidate_id)
            if r.outcome == RequestOutcome.APPROVED.value:
                if rec is not None and rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
                    self.grant_approval(r.candidate_id)
            elif r.outcome == RequestOutcome.REJECTED.value and rec is not None:
                if rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
                    self.history.transition(rec.candidate_id,
                                            CandidateState.REJECTED,
                                            "Owner rejected in approval batch.")
                self.decisions.record(
                    DecisionType.REJECT_CANDIDATE,
                    {"candidate_id": r.candidate_id},
                    provenance="owner:batch-decision",
                )
        # Expired asks defer their candidates instead of stranding them.
        for expired_req in self.tracker.expire_stale_requests():
            rec = self.history.get(expired_req.candidate_id)
            if rec is not None and rec.state == CandidateState.WAITING_FOR_APPROVAL.value:
                self.history.transition(rec.candidate_id, CandidateState.DEFERRED,
                                        "Approval ask expired without answer.")

    def force_approve(self, candidate_id: str) -> None:
        """Scenario hook: explicit owner grant outside batching."""
        self.grant_approval(candidate_id)

    # ------------------------------------------------------------------
    # Brief helpers
    # ------------------------------------------------------------------

    def _brief_state_map(self) -> dict[str, str]:
        return {c.candidate_id: c.state
                for c in self.history.all_candidates()}


__all__ = [
    "DayResult", "LongHorizonIntegrity", "LongHorizonRunner",
]
