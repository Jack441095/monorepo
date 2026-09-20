from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "kenn_gap_report.py"
SPEC = importlib.util.spec_from_file_location("kenn_gap_report", PATH)
assert SPEC and SPEC.loader
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def test_report_prioritizes_repeated_unresolved_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        reporter,
        "fetch_query_signals",
        lambda: [
            {"question": "weak bass", "normalized": "weak bass", "occurrences": 3, "severity": 6, "sources": ["gaps", "feedback"]},
            {"question": "vocal delay", "normalized": "vocal delay", "occurrences": 1, "severity": 1, "sources": ["gaps"]},
        ],
    )
    monkeypatch.setattr(reporter, "cluster_queries", lambda questions: {})

    report = reporter.build_report(recheck=False)

    assert report["summary"]["open_ranked_gaps"] == 2
    assert report["gaps"][0]["question"] == "weak bass"
    assert report["gaps"][0]["priority_score"] > report["gaps"][1]["priority_score"]


def test_report_separates_resolved_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        reporter,
        "fetch_query_signals",
        lambda: [{"question": "fixed", "normalized": "fixed", "occurrences": 1, "severity": 2, "sources": ["gaps"]}],
    )
    monkeypatch.setattr(reporter, "_recheck", lambda question: {"resolved_now": True, "confidence_now": "high", "weak_match_now": False, "top_source_now": "note", "route_now": "production"})
    monkeypatch.setattr(reporter, "cluster_queries", lambda questions: {})
    monkeypatch.setitem(__import__("sys").modules, "kenn.core.chat", type("Chat", (), {"warm_index": staticmethod(lambda: None)}))

    report = reporter.build_report(recheck=True)

    assert report["summary"]["resolved_since_capture"] == 1
    assert report["summary"]["open_ranked_gaps"] == 0


def test_report_excludes_obvious_test_questions(monkeypatch) -> None:
    monkeypatch.setattr(
        reporter,
        "fetch_query_signals",
        lambda: [{"question": "test weak question", "normalized": "test weak question", "occurrences": 99, "severity": 3, "sources": ["feedback"]}],
    )
    report = reporter.build_report(recheck=False)
    assert report["summary"]["signals"] == 0
    assert report["summary"]["synthetic_rows_excluded"] == 1
