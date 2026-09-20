#!/usr/bin/env python3
"""Knowledge Flywheel Agent - Automated knowledge gap resolution.

This agent runs nightly to:
1. Identify knowledge gaps from KENN gap reports
2. Generate candidate notes via LoRA
3. Email digest for human review
4. Self-improve the knowledge base over time
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure Shared is importable
_SYSTEM_ROOT = Path(__file__).parent.parent.parent
_AGENT_SHARED = _SYSTEM_ROOT / "business" / "agents" / "Shared"
if str(_AGENT_SHARED) not in sys.path:
    sys.path.insert(0, str(_AGENT_SHARED))

from autonomous_base import AutonomousAgent

# Ensure app is importable
_APP_PATH = _SYSTEM_ROOT / "business" / "app"
if str(_APP_PATH) not in sys.path:
    sys.path.insert(0, str(_APP_PATH))

from db import connect
from email_notify import send_email, smtp_delivery_enabled


class KnowledgeFlywheelAgent(AutonomousAgent):
    """Automated knowledge improvement through gap analysis and LoRA generation."""

    def __init__(self, root: Path | None = None, auto_approve: bool = False):
        super().__init__(root=root or _SYSTEM_ROOT, auto_approve=auto_approve)

    def run_knowledge_flywheel(self, max_gaps: int = 5) -> dict[str, Any]:
        """Daily loop: identify gaps → generate candidates → notify for review.
        
        Args:
            max_gaps: Maximum gaps to process per day
            
        Returns:
            Summary of generated candidates and any errors
        """
        # Get knowledge gaps (you'll need to integrate with your gap_report script)
        gaps = self._get_knowledge_gaps(limit=max_gaps)
        
        candidates = []
        for gap in gaps:
            # Generate candidate note via LoRA
            candidate = self._generate_candidate_note(gap["question"])
            if candidate.get("ok"):
                candidates.append(candidate)
        
        # Send digest email if candidates generated
        if candidates and smtp_delivery_enabled():
            self._send_candidate_digest(candidates)
        
        return {
            "ok": True,
            "gaps_analyzed": len(gaps),
            "candidates_generated": len(candidates),
            "candidates": candidates,
        }

    def _get_knowledge_gaps(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get top knowledge gaps from the gap report system.
        
        Integrates with your existing kenn_gap_report infrastructure.
        """
        # This would call your gap_report logic
        # For now, return placeholder structure
        conn = connect()
        try:
            gaps = conn.execute(
                """
                SELECT question, COUNT(*) as attempt_count
                FROM knowledge_attempts
                WHERE success = 0
                GROUP BY question
                ORDER BY attempt_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [{"question": g["question"], "attempts": g["attempt_count"]} for g in gaps]
        except Exception:
            # Fallback: query from a simple gaps table
            try:
                gaps = conn.execute(
                    "SELECT question FROM knowledge_gaps ORDER BY priority DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [{"question": g["question"], "attempts": 1} for g in gaps]
            finally:
                conn.close()

    def _generate_candidate_note(self, question: str) -> dict[str, Any]:
        """Generate a draft knowledge note for the given question.
        
        Uses the LLM to create a properly formatted KENN note.
        """
        # Generate draft note using agent's LLM capabilities
        result = self.run_task(
            f"Create a KENN knowledge note about: {question}. "
            "Include: Type tag, Tags, Short answer, and Try this section with practical steps."
        )
        
        if result.get("success"):
            # Store as draft candidate
            note_id = self._store_candidate_note(question, result)
            return {
                "ok": True,
                "question": question,
                "note_id": note_id,
                "status": "draft_ready",
            }
        
        return {
            "ok": False,
            "question": question,
            "error": "Failed to generate candidate note",
        }

    def _store_candidate_note(self, question: str, result: dict) -> str:
        """Store the generated note as a candidate for review."""
        # Generate note ID
        slug = question.lower().replace(" ", "-").replace("?", "")[:50]
        note_id = f"candidate-{slug}-{datetime.now().strftime('%Y%m%d')}"
        
        # Write to candidates directory
        candidates_dir = Path(__file__).parent / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        
        note_content = f"""# {question[:70]}

Type: Candidate
Tags: audio, kenn, knowledge, candidate
Status: Draft
Source title: Knowledge Flywheel
Source creator: KnowledgeFlywheelAgent
Generated: {datetime.now().isoformat()}

Short answer:
{result.get('synthesized_output', 'Draft answer placeholder')}

Try this:
[To be filled with practical steps after review]

Why it matters:
This note addresses a frequently asked question that KENN could not adequately answer.
"""
        
        note_path = candidates_dir / f"{note_id}.md"
        note_path.write_text(note_content, encoding="utf-8")
        
        return note_id

    def _send_candidate_digest(self, candidates: list[dict]) -> bool:
        """Email a digest of new knowledge candidates."""
        candidate_list = "\n".join(
            f"- {c['question'][:60]}... (Note: {c['note_id']})"
            for c in candidates
        )
        
        subject = f"KENN Knowledge Candidates: {len(candidates)} New Items Ready"
        body = f"""KENN Knowledge Flywheel Digest
{'=' * 40}

{len(candidates)} new knowledge candidate notes have been generated:

{candidate_list}

Review and approve these notes in:
  business/services/candidates/

After approval, run index rebuild to update KENN.
"""
        
        try:
            send_email(
                to="your-email@example.com",  # Replace with your email
                subject=subject,
                text_body=body,
            )
            return True
        except Exception:
            return False


def main():
    """Run nightly knowledge flywheel check."""
    agent = KnowledgeFlywheelAgent()
    result = agent.run_knowledge_flywheel(max_gaps=5)
    print(f"Knowledge flywheel completed: {result['candidates_generated']} candidates generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())