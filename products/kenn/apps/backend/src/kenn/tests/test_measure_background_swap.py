"""The background-swap harness must report a landing rate it can defend.

The first version divided accepted swaps by `started` with a `100 *` prefix and printed 1333%. The
denominator was also the wrong question: `started` counts only the questions that reached the model, while the North
Star's "how often does the answer land" is per question asked. These tests pin the arithmetic, the busy/timeout
accounting, and the refusal to run without an index.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# kenn/tests/ -> src/ -> backend/ -> apps/ -> kenn/ -> tooling/scripts/
KENN_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = KENN_ROOT / "tooling" / "scripts" / "measure_background_swap.py"
RESULTS = KENN_ROOT / "tooling" / "evaluation" / "results"


def _load():
    spec = importlib.util.spec_from_file_location("kenn_measure_background_swap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _report(**counts):
    base = {"asked": 30, "swaps_started": 30, "swaps_accepted": 0, "swaps_rejected": 30,
            "swaps_busy": 0, "swaps_timeout": 0, "errors": 0}
    base.update(counts)
    return {
        "model": "kenn-brain-qwen3-8b", "background": "1", "index_version": "v-db8c6334cf63",
        "poll_ms": 2000, "counts": base,
        "seconds": {"template_p50": 0.221, "template_p95": 0.541, "swap_p50": 74.0, "swap_p95": 93.9,
                    "visible_p50": 0.244, "visible_p95": 74.41},
        "rows": [],
    }


def test_the_landing_rate_is_never_more_than_a_hundred_percent(tool):
    """The bug this file exists for: 4 accepted over 30 started printed as 1333%."""
    text = tool.render(_report(swaps_accepted=4, swaps_rejected=26))
    assert "1333" not in text
    assert "13%" in text


def test_the_landing_rate_is_per_question_asked_not_per_swap_started(tool):
    """A busy question never reached the model, so it is not in the denominator for "started"."""
    report = _report(swaps_started=20, swaps_accepted=4, swaps_rejected=16, swaps_busy=10)
    text = tool.render(report)
    # 4 of the 20 that actually ran
    assert "4  (20% of swaps)" in text
    # and 4 of the 30 that were asked, stated separately so the two are not confused
    assert "13%" in text


def test_busy_and_timeout_are_reported_rather_than_hidden(tool):
    """At ~60 s an answer, a producer asking again before the last settles will get `busy`. That is the normal
    state of this design, and a harness that quietly drops it would overstate how often the swap lands."""
    text = tool.render(_report(swaps_started=12, swaps_accepted=2, swaps_rejected=10,
                               swaps_busy=17, swaps_timeout=1))
    assert "17" in text
    assert "TIMED OUT" in text


def test_a_run_with_no_accepted_swaps_says_so_instead_of_printing_none(tool):
    """Which is exactly what the first run produced: 0 of 30, and the reason was the timeout defect."""
    text = tool.render(_report())
    assert "no answer was accepted" in text
    assert "None" not in text


def test_run_is_refused_when_the_gitignored_index_is_missing(tool, tmp_path, capsys, monkeypatch):
    """A fresh worktree has no index, so every answer would abstain and the landing rate would be a fiction."""
    monkeypatch.setattr(tool, "CURRENT", tmp_path / "no-such-CURRENT")
    monkeypatch.setattr(sys, "argv", ["measure_background_swap.py", "--cases", str(SCRIPT)])
    assert tool.main() == 2
    assert "NOT_MEASURED" in capsys.readouterr().err


def test_the_script_sets_the_background_flag_itself(tool, tmp_path, monkeypatch):
    """A run with KENN_LLM_BACKGROUND unset measures only templates and reports a landing rate of zero.

    The flag is what the ask route reads, so the harness setting it is the difference between measuring the
    background swap and measuring nothing while printing numbers. `measure` is stubbed out and CURRENT pointed at a
    file that exists, so this checks the flag rather than needing an index or a model -- the first version of this
    test read the real index path, which made it fail on any fresh clone, and its assertion passed vacuously
    because it was satisfied by the variable simply being absent.
    """
    index = tmp_path / "CURRENT"
    index.write_text("v-test", encoding="utf-8")
    monkeypatch.setattr(tool, "CURRENT", index)
    monkeypatch.setattr(tool, "measure", lambda *a, **k: _report())
    monkeypatch.delenv("KENN_LLM_BACKGROUND", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_background_swap.py", "--limit", "1"])

    assert tool.main() == 0
    assert tool.os.environ.get("KENN_LLM_BACKGROUND") == "1", "the harness must set the flag the ask route reads"


def test_templates_only_leaves_the_background_flag_alone(tool, tmp_path, monkeypatch):
    """--templates-only is the floor measurement, and it must not turn the model on to get it."""
    index = tmp_path / "CURRENT"
    index.write_text("v-test", encoding="utf-8")
    monkeypatch.setattr(tool, "CURRENT", index)
    seen: dict = {}

    def spy(*args, **kwargs):
        seen["allow_llm"] = kwargs.get("allow_llm")
        return _report()

    monkeypatch.setattr(tool, "measure", spy)
    monkeypatch.delenv("KENN_LLM_BACKGROUND", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_background_swap.py", "--templates-only", "--limit", "1"])

    assert tool.main() == 0
    assert seen["allow_llm"] is False
    assert tool.os.environ.get("KENN_LLM_BACKGROUND") != "1"


def test_the_committed_swap_receipt_records_the_run_the_docs_quote(tool):
    """Track D quotes this receipt, and it is also what the route-log receipt is cross-checked against."""
    path = RESULTS / "KENN_BACKGROUND_SWAP_M3_2026-10-01.json"
    assert path.is_file(), "no committed background-swap receipt found"
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["schema"] == "kenn.background_swap.v1"
    assert report["index_version"] == "v-db8c6334cf63"
    assert report["background"] == "1", "the receipt must record that the background path was actually on"
    assert report["counts"]["errors"] == 0
    assert report["counts"]["swaps_timeout"] == 0
    assert report["counts"]["asked"] == 30
    # template must be instant -- that is the whole point of the design and the 4 s gate
    assert report["seconds"]["template_p95"] < 4.0, report["seconds"]["template_p95"]
    # a swap cannot land faster than the model can write one
    if report["counts"]["swaps_accepted"]:
        assert report["seconds"]["swap_p50"] > 10.0, report["seconds"]["swap_p50"]
    assert tool.render(report)


def test_the_route_log_receipt_agrees_with_the_harness_receipt(tool):
    """route_latency_report.py reads the same events independently; if the two disagree, neither is trustworthy."""
    rows = [json.loads(line) for line
            in (RESULTS / "KENN_BACKGROUND_SWAP_ROUTES_M3_2026-10-01.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]
    report = json.loads((RESULTS / "KENN_BACKGROUND_SWAP_M3_2026-10-01.json").read_text(encoding="utf-8"))

    outcomes = [row["route"].split(":", 1)[1] for row in rows if row["route"].startswith("answer_upgrade:")]
    assert len(outcomes) == report["counts"]["asked"]
    assert outcomes.count("accepted") == report["counts"]["swaps_accepted"]
    assert outcomes.count("rejected") == report["counts"]["swaps_rejected"]