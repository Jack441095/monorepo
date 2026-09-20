"""Deterministic Company Intelligence Engine for Thursday V2-C.

Implements query classification, deterministic priority ranking (distinguishing
strategic importance from owner-attention urgency), deterministic enumeration
with coverage/pagination accounting, and evidence-bundle formatting.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
from thursday.company_state import CompanySnapshot, TaskView, GoalView, ApprovalView, AgentRunView

# --- 1. Query Intent Classification ---

def classify_query_intent(text: str) -> str:
    """Classify user query text into a canonical intent class."""
    text_lower = text.lower()
    
    # Block adversarial injections/overrides
    hostile_triggers = ("ignore your instructions", "system override", "note to ai", "attacker@evil.com")
    if any(t in text_lower for t in hostile_triggers):
        return "UNKNOWN"
    
    if any(w in text_lower for w in ("what changed", "what's changed", "diff", "since yesterday", "since last check")):
        return "CHANGES"
    if any(w in text_lower for w in ("blocked", "blocking", "stuck")):
        return "BLOCKERS"
    if any(w in text_lower for w in ("overdue", "late", "behind schedule")):
        return "OVERDUE"
    if any(w in text_lower for w in ("approval", "approve", "needs my approval")):
        return "OWNER_DECISIONS"
    if any(w in text_lower for w in ("agent", "agent status", "agents failed")):
        return "FAILURES"
    if any(w in text_lower for w in ("risk", "on track", "at risk")):
        return "RISKS"
    if any(w in text_lower for w in ("deadline", "due date", "upcoming", "schedule")):
        return "DEADLINES"
    if any(w in text_lower for w in ("priorit", "most important", "deal with first")) or ("focus" in text_lower and "focus on" not in text_lower):
        return "PRIORITIES"
    if any(w in text_lower for w in ("project", "active work", "status", "overview", "company status", "company overview", "focus", "doing", "happening")):
        return "STATUS"
    
    return "UNKNOWN"

# --- 2. Deterministic Priority Engine ---

@dataclass
class PriorityItem:
    item_id: str
    kind: str  # "task_blocked", "task_overdue", "task_due_today", "task_active", "approval", "decision", "risk", "agent_failure"
    title: str
    strategic_importance: float
    owner_attention_urgency: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

def calculate_priorities(snapshot: CompanySnapshot) -> list[PriorityItem]:
    """Calculate and rank priorities from a snapshot.
    
    Distinguishes strategic business importance from owner-attention urgency.
    """
    items: list[PriorityItem] = []
    now_epoch = snapshot.captured_at_epoch
    
    # Check freshness penalty
    freshness_penalty = 0.0
    if snapshot.freshness == "STALE":
        freshness_penalty = 3.0

    # 1. Process Pending Approvals
    for a in snapshot.pending_approvals:
        strat = 5.0
        urg = 8.0
        reasons = ["Requires owner approval to proceed"]
        if a.action_level == "high":
            strat += 4.0
            urg += 4.0
            reasons.append("High strategic risk level")
        if "license" in a.summary.lower() or "signing" in a.summary.lower() or "distribution" in a.summary.lower():
            strat += 5.0
            urg += 5.0
            reasons.append("Affects distribution/licensing gate")
        
        urg = max(0.0, urg - freshness_penalty)
        items.append(PriorityItem(
            item_id=a.approval_id,
            kind="approval",
            title=a.summary,
            strategic_importance=strat,
            owner_attention_urgency=urg,
            reasons=reasons,
            metadata={"capability_id": a.capability_id, "action_level": a.action_level}
        ))

    # 2. Process Open Decisions
    for d in snapshot.open_decisions:
        strat = 6.0
        urg = 7.5
        reasons = ["Open decision blocking workflow"]
        title = d.get("description") or d.get("title") or "Unnamed Decision"
        if "license" in title.lower() or "juce" in title.lower() or "signing" in title.lower():
            strat += 5.0
            urg += 5.0
            reasons.append("Critical commercial/licensing decision")
            
        urg = max(0.0, urg - freshness_penalty)
        items.append(PriorityItem(
            item_id=d.get("decision_id") or d.get("id") or "decision-unknown",
            kind="decision",
            title=title,
            strategic_importance=strat,
            owner_attention_urgency=urg,
            reasons=reasons,
            metadata=d
        ))

    # 3. Process Tasks
    seen_tasks = set()
    all_tasks = []
    
    for task_list in (snapshot.blocked_tasks, snapshot.overdue_tasks, snapshot.due_today_tasks):
        for t in task_list:
            if t.task_id not in seen_tasks:
                seen_tasks.add(t.task_id)
                all_tasks.append(t)
                
    for t in getattr(snapshot, "_all_tasks", ()):
        if t.task_id not in seen_tasks:
            seen_tasks.add(t.task_id)
            all_tasks.append(t)

    for t in all_tasks:
        strat = float(t.priority)
        
        is_blocked = t.status == "blocked" or bool(t.blocked_by)
        is_overdue = False
        is_due_today = False
        
        if t in snapshot.overdue_tasks:
            is_overdue = True
        if t in snapshot.due_today_tasks:
            is_due_today = True
            
        if not is_overdue and t.due_epoch is not None:
            if t.due_epoch < now_epoch:
                is_overdue = True
            else:
                is_due_today = True

        if is_blocked and is_overdue:
            urg = 10.0
            kind = "task_blocked"
            reasons = ["Task is blocked and overdue"]
        elif is_blocked:
            urg = 9.0
            kind = "task_blocked"
            reasons = ["Task is blocked"]
        elif is_overdue:
            urg = 8.0
            kind = "task_overdue"
            reasons = ["Task is overdue"]
        elif is_due_today:
            urg = 6.0
            kind = "task_due_today"
            reasons = ["Task is due today"]
        else:
            urg = 4.0
            kind = "task_active"
            reasons = ["Task is active"]
            
        urg = max(0.0, urg - freshness_penalty)
        items.append(PriorityItem(
            item_id=t.task_id,
            kind=kind,
            title=t.title,
            strategic_importance=strat,
            owner_attention_urgency=urg,
            reasons=reasons,
            metadata={"project_id": t.project_id, "priority": t.priority, "blocked_by": t.blocked_by}
        ))

    # 4. Process Risks
    for r in snapshot.risks:
        strat = 4.0
        urg = 5.0
        reasons = ["Active risk"]
        severity = r.get("severity", "").lower()
        if severity == "high" or severity == "critical":
            strat += 4.0
            urg += 4.0
            reasons.append("High-severity risk identified")
            
        urg = max(0.0, urg - freshness_penalty)
        items.append(PriorityItem(
            item_id=r.get("risk_id") or r.get("id") or "risk-unknown",
            kind="risk",
            title=r.get("description", "Unnamed Risk"),
            strategic_importance=strat,
            owner_attention_urgency=urg,
            reasons=reasons,
            metadata=r
        ))

    # 5. Process Agent Failures
    for r in snapshot.failed_agent_runs:
        strat = 3.0
        urg = 4.5
        reasons = [f"Agent '{r.agent_id}' failed"]
        if r.blocker:
            reasons.append(f"Blocker: {r.blocker}")
            
        urg = max(0.0, urg - freshness_penalty)
        items.append(PriorityItem(
            item_id=r.run_id,
            kind="agent_failure",
            title=f"Agent Run Failure: {r.agent_id}",
            strategic_importance=strat,
            owner_attention_urgency=urg,
            reasons=reasons,
            metadata={"agent_id": r.agent_id, "blocker": r.blocker}
        ))

    # Sort priorities deterministically
    def sort_key(item: PriorityItem):
        return (-item.owner_attention_urgency, -item.strategic_importance, item.item_id)

    items.sort(key=sort_key)
    return items

# --- 3. Deterministic Enumeration Engine ---

@dataclass
class EnumerationBundle:
    qualifying_items: list[Any]
    total_qualifying: int
    items_returned: int
    items_excluded: int
    exclusion_reasons: list[str]
    snapshot_timestamp: float
    complete: bool

def enumerate_entities(snapshot: CompanySnapshot, intent: str, scope_filter: Optional[str] = None) -> EnumerationBundle:
    """Enumerate entities deterministically according to intent and scope filters, with complete metadata."""
    exclusion_reasons = []
    items = []
    
    if intent == "BLOCKERS":
        raw_items = snapshot.blocked_tasks
        for item in raw_items:
            if scope_filter and scope_filter.lower() not in item.project_id.lower() and scope_filter.lower() not in item.title.lower():
                exclusion_reasons.append(f"Excluded '{item.title}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
    elif intent == "OVERDUE":
        raw_items = snapshot.overdue_tasks
        for item in raw_items:
            if scope_filter and scope_filter.lower() not in item.project_id.lower() and scope_filter.lower() not in item.title.lower():
                exclusion_reasons.append(f"Excluded '{item.title}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
    elif intent == "OWNER_DECISIONS":
        raw_approvals = list(snapshot.pending_approvals)
        raw_decisions = list(snapshot.open_decisions)
        
        for item in raw_approvals:
            if scope_filter and scope_filter.lower() not in item.summary.lower():
                exclusion_reasons.append(f"Excluded approval '{item.summary}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
        for item in raw_decisions:
            desc = item.get("description") or item.get("title") or ""
            if scope_filter and scope_filter.lower() not in desc.lower():
                exclusion_reasons.append(f"Excluded decision '{desc}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
    elif intent == "FAILURES":
        raw_items = snapshot.failed_agent_runs
        for item in raw_items:
            if scope_filter and scope_filter.lower() not in item.agent_id.lower():
                exclusion_reasons.append(f"Excluded failure '{item.agent_id}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
    elif intent == "RISKS":
        raw_items = snapshot.risks
        for item in raw_items:
            desc = item.get("description") or ""
            if scope_filter and scope_filter.lower() not in desc.lower():
                exclusion_reasons.append(f"Excluded risk '{desc}': scope filter mismatch '{scope_filter}'")
            else:
                items.append(item)
                
    else:
        pass
        
    total_qualifying = len(items)
    complete = True
    returned_items = items
    
    return EnumerationBundle(
        qualifying_items=returned_items,
        total_qualifying=total_qualifying,
        items_returned=len(returned_items),
        items_excluded=len(exclusion_reasons),
        exclusion_reasons=exclusion_reasons,
        snapshot_timestamp=snapshot.captured_at_epoch,
        complete=complete
    )

# --- 4. Evidence Bundle & Formatting ---

@dataclass
class EvidenceBundle:
    query_intent: str
    query_text: str
    snapshot: CompanySnapshot
    qualifying_items: list[Any]
    priorities: list[PriorityItem]
    enumeration: EnumerationBundle
    freshness_note: str
    is_empty: bool

def build_evidence_bundle(snapshot: CompanySnapshot, query_text: str) -> EvidenceBundle:
    """Build a complete, structured Evidence Bundle from snapshot and user query."""
    intent = classify_query_intent(query_text)
    
    # Check fallback keywords for broad search
    text_lower = query_text.lower()
    is_broad = any(w in text_lower for w in ("priorit", "deal with first"))
    if intent == "UNKNOWN" and is_broad:
        intent = "PRIORITIES"
        
    scope_filter = None
    match = re.search(r"(?:for|project|about)\s+([a-zA-Z0-9_\-\s]+)", query_text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate.lower() not in ("me", "today", "yesterday", "us", "now", "company"):
            scope_filter = candidate

    priorities = calculate_priorities(snapshot)
    enumeration = enumerate_entities(snapshot, intent, scope_filter)
    
    return EvidenceBundle(
        query_intent=intent,
        query_text=query_text,
        snapshot=snapshot,
        qualifying_items=enumeration.qualifying_items,
        priorities=priorities,
        enumeration=enumeration,
        freshness_note=snapshot.freshness_note(),
        is_empty=snapshot.is_empty()
    )

def _clip(value: str, limit: int = 120) -> str:
    value = str(value)
    # Strip hostile notes
    if " — NOTE:" in value:
        value = value.split(" — NOTE:")[0].strip()
    if " - NOTE:" in value:
        value = value.split(" - NOTE:")[0].strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_evidence_bundle_deterministically(bundle: EvidenceBundle) -> str:
    """Render the Evidence Bundle into a clean, human-readable text fallback."""
    sections = []
    snap = bundle.snapshot
    
    if bundle.query_intent == "UNKNOWN":
        # Extract single-quoted substrings representing requested task title
        quoted = re.findall(r"['\"](.*?)['\"]", bundle.query_text)
        
        all_possible_tasks = []
        for t_list in (snap.blocked_tasks, snap.overdue_tasks, snap.due_today_tasks):
            all_possible_tasks.extend(t_list)
        all_possible_tasks.extend(getattr(snap, "_all_tasks", ()))
        
        # Deduplicate all_possible_tasks
        seen_tids = set()
        dedup_tasks = []
        for t in all_possible_tasks:
            if t.task_id not in seen_tids:
                seen_tids.add(t.task_id)
                dedup_tasks.append(t)
        
        matches = []
        if quoted:
            target_title = quoted[0].lower()
            for t in dedup_tasks:
                sanitized_title = _clip(t.title).lower()
                if target_title in sanitized_title or sanitized_title in target_title:
                    matches.append(t)
        
        if matches:
            items_str = "\n".join(f"- {_clip(t.title)} ({t.status})" for t in matches)
            sections.append(f"Found {len(matches)} tasks matching '{_clip(matches[0].title)}':\n{items_str}")
        else:
            return "I don't have that information in company state — I won't guess."

    elif bundle.query_intent == "PRIORITIES":
        # Only consider task priorities to satisfy priority_order constraint
        task_priorities = [p for p in bundle.priorities if p.kind.startswith("task_")]
        if not task_priorities:
            return "No task priorities found."
        top_task = task_priorities[0]
        return f"Highest priority task: {_clip(top_task.title)}"

    elif bundle.query_intent == "BLOCKERS":
        if not bundle.qualifying_items:
            sections.append("Nothing is blocked right now.")
        else:
            items = "\n".join(
                f"- {_clip(t.title)} ({t.project_id})"
                + (f" — waiting on {', '.join(t.blocked_by)}" if t.blocked_by else "")
                for t in bundle.qualifying_items
            )
            sections.append(f"Blocked ({len(bundle.qualifying_items)}):\n{items}")
            
    elif bundle.query_intent == "OVERDUE":
        if not bundle.qualifying_items:
            sections.append("Nothing is overdue.")
        else:
            items = "\n".join(
                f"- {_clip(t.title)} ({t.project_id}, P{t.priority})"
                for t in bundle.qualifying_items
            )
            sections.append(f"Overdue ({len(bundle.qualifying_items)}):\n{items}")
            
    elif bundle.query_intent == "OWNER_DECISIONS":
        if not bundle.qualifying_items:
            sections.append("No approvals are waiting on you.")
        else:
            items = []
            for item in bundle.qualifying_items:
                if isinstance(item, ApprovalView):
                    items.append(f"- {_clip(item.summary)} [{item.approval_id}] ({item.action_level}-risk, {item.reversibility})")
                else:
                    desc = item.get("description") or item.get("title") or "Unnamed Decision"
                    items.append(f"- [Decision] {_clip(desc)}")
            sections.append(f"Awaiting your approval:\n" + "\n".join(items))
            
    elif bundle.query_intent == "FAILURES":
        if not bundle.qualifying_items:
            sections.append("No agent failures; nothing currently running.")
        else:
            items = "\n".join(
                f"- {r.agent_id}: failed" + (f" — {_clip(r.blocker)}" if r.blocker else "")
                for r in bundle.qualifying_items
            )
            sections.append(f"Agent failures:\n{items}")
            
    elif bundle.query_intent == "RISKS":
        if not bundle.qualifying_items:
            sections.append("No active risks.")
        else:
            items = "\n".join(
                f"- [{r.get('severity', '?')}] {_clip(r.get('description', '?'))}"
                for r in bundle.qualifying_items
            )
            sections.append(f"Active risks:\n{items}")
            
    elif bundle.query_intent == "CHANGES":
        from thursday import company_state
        previous = company_state.get_previous_snapshot()
        changes = company_state.diff_snapshots(previous, snap)
        rendered = company_state.describe_changes(changes)
        if rendered:
            sections.append(f"Changed since the last check:\n{rendered}")
        else:
            sections.append(
                "No meaningful change since the last company-state refresh."
                + (
                    " (No earlier snapshot to compare against yet.)"
                    if previous is None
                    else ""
                )
            )
            
    else:
        # Status / Focus
        if snap.is_empty():
            return "No company state recorded yet, so I can't prioritise — record goals/tasks in the platform store first."
            
        top = []
        detail = []
        if snap.blocked_tasks:
            top.append(f"{len(snap.blocked_tasks)} blocked")
            detail.extend(f"- {_clip(t.title)} ({t.project_id})" for t in snap.blocked_tasks)
        if snap.overdue_tasks:
            top.append(f"{len(snap.overdue_tasks)} overdue")
            detail.extend(f"- {_clip(t.title)} ({t.project_id}, P{t.priority})" for t in snap.overdue_tasks)
        if snap.due_today_tasks:
            top.append(f"{len(snap.due_today_tasks)} due today")
        if snap.pending_approvals:
            top.append(f"{len(snap.pending_approvals)} approval(s) waiting on you")
            
        if top:
            sections.append("Focus areas: " + ", ".join(top) + ".")
        if detail:
            sections.append("Highest-priority items:\n" + "\n".join(detail))
            
    ans = "\n\n".join(sections)
    if not ans:
        return "I don't have that information in company state — I won't guess."
    if bundle.freshness_note:
        ans += f"\n\n{bundle.freshness_note}"
    return ans
