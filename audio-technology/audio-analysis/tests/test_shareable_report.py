"""Tests for mix_review/shareable_report.py, the module podcast_report.py
and delivery_report.py's HTML/CSS were deduplicated into after being found
character-for-character identical except status label text and podcast's
extra KENN-section CSS."""

from __future__ import annotations

from audio_analysis.mix_review.shareable_report import BASE_CSS, ORDER, check_rows


def test_check_rows_orders_fail_before_warn_before_ok():
    checks = [
        {"id": "a", "status": "ok", "label": "A"},
        {"id": "b", "status": "fail", "label": "B"},
        {"id": "c", "status": "warn", "label": "C"},
    ]
    status_colors = {"fail": ("#e00", "Fail"), "warn": ("#fa0", "Warn"), "ok": ("#0a0", "OK")}
    html = check_rows(checks, status_colors)
    assert html.index(">Fail<") < html.index(">Warn<") < html.index(">OK<")


def test_check_rows_uses_the_callers_own_status_labels():
    checks = [{"id": "a", "status": "fail", "label": "A"}]
    html = check_rows(checks, {"fail": ("#e00", "Fix before delivery"), "warn": ("#fa0", "x"), "ok": ("#0a0", "y")})
    assert "Fix before delivery" in html
    html2 = check_rows(checks, {"fail": ("#e00", "Fix before publishing"), "warn": ("#fa0", "x"), "ok": ("#0a0", "y")})
    assert "Fix before publishing" in html2


def test_check_rows_empty_list_says_no_issues():
    assert "No issues detected" in check_rows([], {})


def test_check_rows_escapes_html_in_fields():
    checks = [{"id": "a", "status": "ok", "label": "<script>alert(1)</script>", "fix": "<b>x</b>"}]
    html = check_rows(checks, {"ok": ("#0a0", "OK")})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_order_map_covers_all_three_statuses():
    assert ORDER == {"fail": 0, "warn": 1, "ok": 2}


def test_base_css_defines_the_shared_selectors_both_reports_rely_on():
    for selector in (".wrap", "header.hero", ".score", ".card", "ul.checks", "li.check", ".cta", "footer"):
        assert selector in BASE_CSS
