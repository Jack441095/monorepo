"""Speakable brief renderer tests — one factual source, speech output.

Covers §30 scenarios: normal day, quiet day, many blockers, approvals,
stale company state, partial source failure. Pins: no markdown, no raw
IDs, critical facts survive compression, quiet days stay short.
"""

from __future__ import annotations

from thursday import daily_brief
from thursday.daily_brief import render_speakable_brief


def make_brief(company_payload="No company state recorded yet.",
               agenda_payload="No reminders for today.\n\nReady when you are.",
               receipts=None, scheduler_due=None, statuses_ok=True):
    ok = "ok" if statuses_ok else "unavailable"
    return {
        "today": "2026-08-23",
        "generated_at": "2026-08-23T09:00:00",
        "sections": {
            "business_status": {"status": ok, "payload": "" if not statuses_ok else "status"},
            "company_state": {"status": "ok", "payload": company_payload},
            "agenda": {"status": "ok" if agenda_payload is not None else "unavailable",
                       "payload": agenda_payload or ""},
            "week_ahead": {"status": "ok", "payload": ""},
            "agent_receipts": {
                "status": "ok",
                "payload": receipts or [],
            },
            "scheduler": {"status": "ok", "payload": {"registered": {}, "due_now": scheduler_due or []}},
        },
        "summary": {"available": [], "unavailable": [], "total_sections": 6},
    }


def test_quiet_day_is_short_and_reassuring():
    text = render_speakable_brief(make_brief())
    assert text.startswith("All clear")
    assert len(text.split()) < 15
    assert "#" not in text and "*" not in text


def test_normal_day_names_blocker_overdue_approval_counts():
    payload = (
        "**Blocked:**\n- Fix renderer crash (p-slo)\n"
        "**Overdue:**\n- Chase invoice (p-slo)\n"
        "**Needs your approval:**\n- Send announcement [ap1] (high risk)"
    )
    text = render_speakable_brief(make_brief(company_payload=payload))
    assert "1 blocked task needing attention" in text
    assert "1 task is overdue" in text
    assert "1 item needs your approval" in text
    # Speech hygiene: no markdown bullets or bold markers leak through.
    assert "**" not in text and "\n-" not in text and "[ap1]" not in text


def test_many_blockers_use_plural_and_survive_compression():
    payload = "**Blocked:**\n" + "".join(
        f"- Task {i} blocked (p)\n" for i in range(5)
    )
    text = render_speakable_brief(make_brief(company_payload=payload))
    assert "5 blocked tasks needing attention" in text


def test_agent_failure_surfaced_without_ids():
    payload = "**Agent failures:**\n- research — provider timeout\n"
    text = render_speakable_brief(make_brief(company_payload=payload))
    assert "agent failed" in text.lower() or "agents failed" in text.lower()
    assert "run-" not in text and "act-" not in text


def test_stale_company_state_warned_in_speech():
    payload = "**Blocked:**\n- Something stuck (p)\n\n_(company state is STALE — captured 45 min ago; verify before acting)_"
    text = render_speakable_brief(make_brief(company_payload=payload))
    assert "stale" in text.lower()


def test_receipts_completed_count_spoken():
    text = render_speakable_brief(make_brief(receipts=[
        {"receipt_id": "act-a", "service_id": "email.send", "status": "completed"},
        {"receipt_id": "act-b", "service_id": "email.send", "status": "completed"},
    ]))
    assert "2 agent actions completed" in text


def test_partial_source_failure_still_speaks_available_facts():
    brief = make_brief(company_payload="**Blocked:**\n- Only fact available (p)\n")
    brief["sections"]["agenda"] = {"status": "unavailable", "payload": ""}
    brief["sections"]["agent_receipts"] = {"status": "unavailable", "payload": []}
    brief["sections"]["scheduler"] = {"status": "unavailable", "payload": {}}
    spoken = render_speakable_brief(brief)
    assert "blocked" in spoken.lower()
