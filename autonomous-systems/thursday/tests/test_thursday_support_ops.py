"""Tests for thursday/support_ops.py (Thursday Ops upgrade, phase 10).

Two real, live sources: business_knowledge.json's faqs, and qa_ops's
live-parsed beta checklist reframed as known issues. Neither
"tester support drafts" nor "support triage workflow" from the spec is
implemented (zero live testers/tickets exist to draft a response to).
"""

from __future__ import annotations

import json

import thursday.ops.support_ops as support
import thursday.ops.qa_ops as qa


# ── faq_lookup / get_faqs ────────────────────────────────────────────────


def test_get_faqs_returns_real_list():
    faqs = support.get_faqs()
    assert len(faqs) > 0
    assert all("question" in f for f in faqs)


def test_faq_lookup_no_query_returns_all():
    faqs = support.get_faqs()
    out = support.faq_lookup("")
    for f in faqs:
        assert f["question"] in out


def test_faq_lookup_matches_by_question_substring():
    out = support.faq_lookup("quote")
    assert "How do I get a quote?" in out


def test_faq_lookup_matches_by_keyword():
    out = support.faq_lookup("stems")
    assert "Q:" in out


def test_faq_lookup_no_match_reports_honestly():
    out = support.faq_lookup("completely unrelated nonsense query xyz123")
    assert "No FAQ entry matches" in out


def test_faq_lookup_evidence_missing_when_file_unavailable(monkeypatch):
    monkeypatch.setattr(support, "_business_knowledge_path", lambda: None)
    out = support.faq_lookup("")
    assert "Evidence missing" in out


# ── known_issues ──────────────────────────────────────────────────────────


def test_known_issues_evidence_missing_when_checklist_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    out = support.known_issues()
    assert "Evidence missing" in out


def test_known_issues_reflects_real_gate_0_state(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(
        "## Gate 0 — Owner decisions (nothing below moves without these)\n\n"
        "- [ ] Do the important thing.\n"
        "- [x] Already done thing.\n"
    )
    out = support.known_issues()
    assert "1 open item(s)" in out
    assert "Do the important thing." in out
    assert "Already done thing." not in out


def test_known_issues_none_when_gate_0_fully_cleared(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(
        "## Gate 0 — Owner decisions (nothing below moves without these)\n\n"
        "- [x] Done.\n"
    )
    out = support.known_issues()
    assert "None — the beta launch checklist's Gate 0 is fully cleared." in out
