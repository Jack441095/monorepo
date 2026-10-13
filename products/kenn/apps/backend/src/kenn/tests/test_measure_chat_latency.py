"""The chat-latency harness must not be able to report a latency it did not measure.

The two answer caches make a rerun look like a 0.08 s answer that never called the model, so
these tests pin the parts of `measure_chat_latency.py` that make the number honest: the cache
drop, the percentile arithmetic on a small sample, and the refusal to run without an index.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# kenn/tests/ -> src/ -> backend/ -> apps/ -> kenn/ -> tooling/scripts/
KENN_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = KENN_ROOT / "tooling" / "scripts" / "measure_chat_latency.py"


def _load():
    spec = importlib.util.spec_from_file_location("kenn_measure_chat_latency", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


@pytest.mark.parametrize("surface", ["foreground", "background"])
def test_templates_only_http_measurement_is_refused_before_contacting_the_companion(tool, monkeypatch, surface):
    # HTTP ignored allow_llm=False and could start inference while claiming the template floor.
    requests = []
    def ask(*args, **kwargs):
        requests.append(kwargs)
        return {}, 0, None
    monkeypatch.setattr(tool, "_ask_http", ask)
    with pytest.raises(ValueError, match="Templates-only measurement requires"):
        tool.measure([{"id": "fixture", "question": "Synthetic"}], allow_llm=False,
                     surface=surface, endpoint="http://127.0.0.1:1")
    assert requests == []


@pytest.mark.parametrize("surface", ["foreground", "background"])
def test_templates_only_http_cli_explains_the_supported_surfaces(tool, monkeypatch, capsys, surface):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--templates-only", "--surface", surface,
                                     "--endpoint", "http://127.0.0.1:1"])
    with pytest.raises(SystemExit) as error:
        tool.main()
    assert error.value.code == 2
    assert "--templates-only requires --surface payload or stream" in capsys.readouterr().err


def test_all_delivery_outcomes_stay_in_the_eligible_denominator_with_unknown_paint_time(tool, monkeypatch):
    # Accepted-only latency used to hide busy and timed-out requests from the product gate.
    outcomes = iter(("accepted", "rejected", "busy", "timeout", "not_attempted"))
    def ask(*args, **kwargs):
        outcome = next(outcomes)
        return {"answer": "Synthetic answer", "delivery_outcome": outcome,
                "generation_validation": {"attempted": outcome in {"accepted", "rejected"}, "accepted": outcome == "accepted"}}, 0, None
    monkeypatch.setattr(tool, "_ask_http", ask)
    report = tool.measure([{"id": f"c-{number}", "question": "Synthetic", "split": "regression"} for number in range(5)],
                          surface="background", endpoint="http://127.0.0.1:1", cache_condition="warm")
    assert report["counts"]["eligible"] == 5
    assert report["counts"]["delivery"] == {outcome: 1 for outcome in ("accepted", "rejected", "busy", "timeout", "not_attempted")}
    assert report["counts"]["eligible_accepted_within_15_seconds"] == 1
    assert report["counts"]["llm_attempted"] == 2
    assert all(row["final_displayed_answer_seconds"] is None and row["first_useful_answer_seconds"] is None and row["ttft_seconds"] is None for row in report["rows"])
    assert all(row["cache_dropped"] is False and row["server_cache_condition_verified"] is False for row in report["rows"])
    assert tool.answer_capture(report)["cases"][2]["delivery"] == "busy"
    assert report["provenance"]["model_digest"] is None


def test_expired_background_job_does_not_claim_an_inference_attempt(tool, monkeypatch):
    from kenn.core import mcp_facade
    requests = []
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def post(self, path, body):
            requests.append(body)
            return {"answer_upgrade": {"id": "fixture-job"}}
        def get(self, path, query):
            assert query["session_id"] == requests[0]["session_id"]
            return {"status": "expired"}
    monkeypatch.setattr(mcp_facade, "KennHTTPClient", Client)
    payload, _, _ = tool._ask_http("Synthetic", surface="background", endpoint="http://127.0.0.1:1", timeout=1)
    assert payload["delivery_outcome"] == "not_attempted"
    assert "generation_validation" not in payload


def test_percentile_uses_the_top_of_a_small_sample_not_an_interpolation(tool):
    """p95 of 10 answers is the slowest, not something between the two slowest.

    The gate is written as p95, and with a 10-question sample a naive nearest-rank on a
    fraction of len-1 lands on the 9th value and understates the tail. Round to the last
    index instead so a small sample reports the worst answer it actually saw.
    """
    ten = [float(v) for v in range(1, 11)]
    assert tool._percentile(ten, 0.95) == 10.0
    assert tool._percentile(ten, 0.5) == 5.0
    assert tool._percentile([4.0], 0.95) == 4.0
    assert tool._percentile([], 0.95) is None


def test_median_of_an_empty_sample_is_none_rather_than_a_crash(tool):
    """A run where nothing was accepted must print "(no answer was accepted)", not blow up."""
    assert tool._median([]) is None


def test_semantic_cache_drop_empties_every_tier(tool):
    """The in-memory L1/L2 tiers must be empty afterwards, or a rerun replays a prior answer.

    This is the trap that made three questions measure 57/54/73 s once and 0.1/0.1/1.5 s the
    next time, with `attempted=True` throughout and no model call on the second pass.
    """
    from kenn.core import session_memory

    with session_memory._L1_LOCK:
        session_memory._L1_EXACT_CACHE[("some-session", "a question that was asked before")] = (
            1e12, "v1", [{"event": "metadata"}],
        )
        session_memory._L2_QUERIES.append("a question that was asked before")
        session_memory._L2_SESSION_IDS.append("some-session")
        session_memory._L2_EVENTS.append([{"event": "metadata"}])
        session_memory._L2_TIMESTAMPS.append(1e12)
        session_memory._L2_VERSIONS.append("v1")

    tool._drop_semantic_cache()

    assert session_memory._L1_EXACT_CACHE == {}
    assert list(session_memory._L2_QUERIES) == []
    assert session_memory._L2_MATRIX is None


def test_run_is_refused_when_the_gitignored_index_is_missing(tool, tmp_path, capsys, monkeypatch):
    """No index means every answer would abstain, so the tool must exit 2 and say NOT_MEASURED.

    `apps/backend/src/kenn/data/` is git-ignored, so a fresh worktree has no index. Silently
    producing a report there would be a measurement of nothing wearing a measurement's name.
    """
    monkeypatch.setattr(tool, "KENN_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["measure_chat_latency.py", "--cases", str(SCRIPT)])

    assert tool.main() == 2
    assert "NOT_MEASURED" in capsys.readouterr().err


def test_a_missing_case_file_exits_1_rather_than_reporting_zero_answers(tool, tmp_path, monkeypatch):
    """A typo in --cases must not look like a clean run that asked nothing."""
    monkeypatch.setattr(sys, "argv", ["measure_chat_latency.py", "--cases", str(tmp_path / "nope.json")])
    assert tool.main() == 1


def test_accepted_rate_is_reported_against_attempts_not_against_questions_asked(tool):
    """One question never reached the model; dividing by 30 would understate the swap rate.

    Measured 1 Oct: 30 asked, 29 attempted, 7 accepted. Reporting 7/30 = 23% against the
    attempts that actually happened is the number Track D asks for.
    """
    report = {
        "model": "kenn-brain-qwen3-8b",
        "surface": "stream",
        "index_version": "v-test",
        "counts": {"asked": 30, "llm_attempted": 29, "llm_accepted": 7, "llm_rejected": 22, "errors": 0},
        "seconds": {"all_median": 60.2, "all_p95": 89.5, "attempted_median": 61.0,
                    "accepted_median": 64.5, "accepted_p95": 96.0},
        "top_rejection_reason": {"reason": "unsupported measurements", "answers": 17},
    }
    text = tool.render(report)
    assert "7  (24% of attempts)" in text
    assert "60.2s" in text and "89.5s" in text
    assert "unsupported measurements" in text
    # The surface has to be visible: a companion-surface run answers a different question.
    assert "stream" in text


def test_a_run_with_nothing_accepted_says_so_instead_of_printing_none(tool):
    """The companion surface accepts nothing; `None` in the summary is noise, not information."""
    report = {
        "model": "kenn-brain-qwen3-8b", "surface": "payload", "index_version": "v-test",
        "counts": {"asked": 30, "llm_attempted": 0, "llm_accepted": 0, "llm_rejected": 0, "errors": 0},
        "seconds": {"all_median": 20.2, "all_p95": 20.4, "attempted_median": None,
                    "accepted_median": None, "accepted_p95": None},
        "top_rejection_reason": {"reason": "", "answers": 0},
    }
    text = tool.render(report)
    assert "no answer was accepted" in text
    assert "none recorded" in text
    assert "None" not in text


def test_a_receipt_that_mixed_surfaces_would_say_so(tool):
    """A report claiming one surface while its rows say another is worse than no report."""
    report = {"rows": [{"surface": "stream"}, {"surface": "payload"}]}
    assert tool.surface_of(report) == "mixed"


def test_a_rejection_records_which_measurement_and_which_citation(tool, monkeypatch):
    """A warning names the class of fault but not the value.

    Measured 1 Oct: 19 of 30 rejections were "unsupported measurements", and nothing said which
    measurement, so a measure built on these receipts could count the problem without ever naming it.
    """
    payload = {
        "generation_validation": {
            "attempted": True,
            "accepted": False,
            "warnings": [
                "generated answer introduced unsupported measurements",
                "generated answer cites sources not in the retrieved evidence",
            ],
            "unsupported_measurements": ["128bpm"],
            "fabricated_sources": ["invented-guide.md"],
        },
        "llm_enhanced": False,
        "found": True,
        "sources": [{"title": "Reverb send workflow"}],
    }
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    # _ask returns (payload, token_event_count, seconds_to_first_token). The third was added when the harness
    # began recording TTFT; a two-tuple made measure()'s unpack fail, and its own except swallowed that into an
    # empty row reported as "no unsupported measurements" rather than as an error.
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (payload, 3, 1.2))

    report = tool.measure([{"id": "q1", "question": "how do I set a send?"}], allow_llm=True)

    (row,) = report["rows"]
    assert row["unsupported_measurements"] == ["128bpm"]
    assert row["fabricated_sources"] == ["invented-guide.md"]


def test_a_receipt_records_no_answer_text(tool, monkeypatch):
    """These receipts are committed, and route_log's rule is that timings and outcomes are kept, never the answer."""
    payload = {
        "generation_validation": {
            "attempted": True,
            "accepted": False,
            "warnings": ["generated answer introduced unsupported measurements"],
            "unsupported_measurements": ["-18 dbfs"],
        },
        "llm_enhanced": False, "found": True, "sources": [],
    }
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    # _ask returns (payload, token_event_count, seconds_to_first_token). The third was added when the harness
    # began recording TTFT; a two-tuple made measure()'s unpack fail, and its own except swallowed that into an
    # empty row reported as "no unsupported measurements" rather than as an error.
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (payload, 3, 1.2))

    report = tool.measure([{"id": "q1", "question": "how do I set a send?"}], allow_llm=True)

    blob = json.dumps(report)
    assert "short answer" not in blob.lower() and "try this" not in blob.lower()


def test_prefix_rejection_capture_cannot_be_mistaken_for_the_model_candidate(tool, monkeypatch):
    # The stream drops the rejected prefix and returns a template; citation review must not grade that template.
    payload = {"answer": "Fallback template", "generation_validation": {
        "attempted": True, "accepted": False, "warnings": ["unsupported measurements"]}}
    captures = []
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (payload, 0, None))
    monkeypatch.setattr(tool, "_write_capture_row", captures.append)
    tool.measure([{"id": "release", "question": "What release?"}])
    (row,) = captures
    assert row["candidate_text_available"] is False
    assert row["gate_ran"] is False
    assert row["evidence_sources"] is None
    assert row["prompt_evidence"] is None


def test_rejected_answer_keeps_route_and_interrupted_provider_costs(tool, monkeypatch):
    from kenn.llm import llm_rewrite

    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    def ask(*args, **kwargs):
        llm_rewrite._add_usage(llm_rewrite.LLMUsage(task="route", load_duration_ns=123))
        llm_rewrite._add_usage(llm_rewrite.LLMUsage(task="rewrite", status="interrupted", provider_done=False))
        return {"generation_validation": {"attempted": True, "accepted": False,
                "warnings": ["unsupported measurements"]}}, 2, 0.1
    monkeypatch.setattr(tool, "_ask", ask)
    report = tool.measure([{"id": "rejected", "question": "Set release?"}])
    (row,) = report["rows"]
    assert row["attempted"] is True and row["accepted"] is False
    assert [call["task"] for call in row["provider_calls"]] == ["route", "rewrite"]
    assert row["provider_calls"][0]["load_duration_ns"] == 123
    assert row["provider_calls"][1]["eval_duration_ns"] is None
    assert report["counts"]["provider_attempts"] == 2
    assert report["counts"]["provider_interruptions"] == 1


def test_replayed_usage_metadata_is_not_counted_as_a_current_provider_call(tool, monkeypatch):
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    payload = {"semantic_cache_hit": True, "llm_usage": {"load_duration_ns": 123},
               "generation_validation": {"attempted": True, "accepted": True}}
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: (payload, 1, 0.01))
    report = tool.measure([{"id": "compression", "question": "Explain compression"}])
    assert report["rows"][0]["provider_calls"] == []
    assert report["counts"]["provider_attempts"] == 0


def test_provider_failure_is_kept_even_when_the_question_raises(tool, monkeypatch):
    from kenn.llm import llm_rewrite

    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    def ask(*args, **kwargs):
        llm_rewrite._add_usage(llm_rewrite.LLMUsage(status="failed", error_type="TimeoutError"))
        raise TimeoutError("test timeout")
    monkeypatch.setattr(tool, "_ask", ask)
    report = tool.measure([{"id": "compression", "question": "Explain compression"}])
    assert report["rows"][0]["provider_calls"][0]["error_type"] == "TimeoutError"
    assert report["counts"]["provider_failures"] == report["counts"]["errors"] == 1


def test_each_question_captures_only_its_calls_and_counts_response_cache_hits(tool, monkeypatch):
    from kenn.llm import llm_rewrite

    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    def ask(_chat, question, **kwargs):
        llm_rewrite._add_usage(llm_rewrite.LLMUsage(task=question, provider_attempted=False,
                                                 cache_hit=True, status="cache_hit"))
        return {}, 1, 0.01
    monkeypatch.setattr(tool, "_ask", ask)
    report = tool.measure([{"id": "first", "question": "first"}, {"id": "second", "question": "second"}])
    assert [[call["task"] for call in row["provider_calls"]] for row in report["rows"]] == [["first"], ["second"]]
    assert report["counts"]["provider_attempts"] == 0
    assert report["counts"]["response_cache_hits"] == 2


def test_the_committed_receipts_have_the_shape_the_plan_quotes(tool):
    """Track D's gate is quoted straight out of these files, so their schema must not drift."""
    results = KENN_ROOT / "tooling" / "evaluation" / "results"
    receipts = sorted(results.glob("KENN_CHAT_LATENCY_M3_*_2026-10-01.json"))
    assert receipts, "no committed chat-latency receipts found"

    for path in receipts:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["schema"] == "kenn.chat_latency.v1", path.name
        assert tool.surface_of(report) in {"stream", "payload"}, path.name
        assert report["index_version"] == "v-db8c6334cf63", path.name
        assert report["counts"]["errors"] == 0, f"{path.name} recorded errors"
        assert report["rows"], path.name
        for key in ("all_median", "all_p95", "accepted_median", "accepted_p95"):
            assert key in report["seconds"], f"{path.name} missing {key}"
        assert tool.render(report), path.name


class _FakeCompanion:
    """A scripted loopback companion: post() and get() replay fixed replies or raise, no socket opened."""

    def __init__(self, post, gets=()):
        self._post, self._gets = post, list(gets)

    def __call__(self, *args, **kwargs):
        return self

    def post(self, path, body):
        if isinstance(self._post, BaseException):
            raise self._post
        return dict(self._post)

    def get(self, path, query):
        reply = self._gets.pop(0) if len(self._gets) > 1 else self._gets[0]
        if isinstance(reply, BaseException):
            raise reply
        return dict(reply)


def _transport_error(cause):
    from kenn.core.mcp_facade import KennTransportError

    try:
        raise KennTransportError("KENN companion request did not complete") from cause
    except KennTransportError as error:
        return error


def _measure_http(tool, monkeypatch, companion, surface="background", timeout=1.0):
    from kenn.core import mcp_facade

    monkeypatch.setattr(mcp_facade, "KennHTTPClient", companion)
    return tool.measure([{"id": "fixture", "question": "Synthetic"}], surface=surface,
                        endpoint="http://127.0.0.1:1", cache_condition="warm", timeout=timeout)["rows"][0]


@pytest.mark.parametrize("surface", ["foreground", "background"])
def test_a_companion_that_is_not_running_is_an_error_not_a_timeout(tool, monkeypatch, surface):
    # Before 13 Oct 2026 every KennTransportError matched "did not complete" and was booked as a timeout,
    # so a stopped companion read as 30 slow answers rather than zero measured ones.
    row = _measure_http(tool, monkeypatch, _FakeCompanion(_transport_error(ConnectionRefusedError(61, "refused"))),
                        surface=surface)
    assert row["delivery"] == "error"
    assert "ConnectionRefusedError" in row["error"]


@pytest.mark.parametrize("cause", [TimeoutError("timed out"), __import__("urllib.error").error.URLError(TimeoutError())])
def test_a_read_that_ran_out_of_time_is_still_a_timeout(tool, monkeypatch, cause):
    row = _measure_http(tool, monkeypatch, _FakeCompanion(_transport_error(cause)), surface="foreground")
    assert row["delivery"] == "timeout"


@pytest.mark.parametrize("surface", ["foreground", "background"])
def test_a_reply_discarded_for_a_newer_turn_is_cancelled_not_unattempted(tool, monkeypatch, surface):
    # server.py answers a superseded turn with status "cancelled"; that is neither a template nor a skipped model.
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "", "status": "cancelled", "answer_delivery_discarded": True, "inference_aborted": False}),
        surface=surface)
    assert row["delivery"] == "cancelled"
    assert row["attempted"] is False


def test_a_background_row_keeps_the_server_timings_and_the_template_reply_time(tool, monkeypatch):
    timing = {"total_ms": 412.0, "context_build_ms": 3.1, "answer_pipeline_ms": 380.2, "augment_ms": 20.0}
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "Template", "timing": timing, "answer_upgrade": {"id": "job"}},
        [{"status": "pending"}, {"status": "accepted", "answer": "Model answer", "seconds": 12.3}]))
    assert row["delivery"] == "accepted"
    assert row["server_timing_ms"] == timing
    assert row["server_upgrade_seconds"] == 12.3
    assert row["initial_reply_seconds"] is not None and row["initial_reply_seconds"] <= row["seconds"]
    # "accepted" used to be written into warnings, which read as a reason on an answer that had none.
    assert row["warnings"] == []
    # The paint time and the useful-answer time stay unknown: receiving a reply is not seeing it.
    assert row["first_useful_answer_seconds"] is None and row["final_displayed_answer_seconds"] is None


def test_a_rejected_background_job_keeps_the_gate_reason(tool, monkeypatch):
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "Template", "answer_upgrade": {"id": "job"}},
        [{"status": "rejected", "reason": "unsupported measurements", "seconds": 9.0}]))
    assert row["delivery"] == "rejected"
    assert row["warnings"] == ["unsupported measurements"]
    assert row["server_upgrade_seconds"] == 9.0


def test_a_polling_timeout_keeps_the_template_that_was_already_delivered(tool, monkeypatch):
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "Template", "timing": {"total_ms": 5.0}, "answer_upgrade": {"id": "job"}}, [{"status": "pending"}]),
        timeout=0.12)
    assert row["delivery"] == "timeout"
    assert row["answer"] == "Template"
    assert row["server_timing_ms"] == {"total_ms": 5.0}
    assert row["server_upgrade_seconds"] is None


def test_the_response_cache_state_is_resolved_in_process_and_unknown_over_http(tool, monkeypatch):
    # KENN_LLM_CACHE unset means the response cache is ON, which the raw env echo (None) did not say.
    monkeypatch.delenv("KENN_LLM_CACHE", raising=False)
    assert tool.run_provenance()["cache_settings"]["response_cache_enabled"] is True
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    assert tool.run_provenance()["cache_settings"]["response_cache_enabled"] is False
    monkeypatch.delenv("KENN_LLM_CACHE", raising=False)
    from kenn.core import mcp_facade
    monkeypatch.setattr(mcp_facade, "KennHTTPClient", _FakeCompanion({"answer": "Template"}))
    row_report = tool.measure([{"id": "fixture", "question": "Synthetic"}], surface="foreground",
                              endpoint="http://127.0.0.1:1", cache_condition="warm")
    assert row_report["provenance"]["cache_settings"]["response_cache_enabled"] is None


def test_the_console_summary_shows_every_delivery_outcome(tool, monkeypatch):
    from kenn.core import mcp_facade
    monkeypatch.setattr(mcp_facade, "KennHTTPClient", _FakeCompanion(_transport_error(ConnectionRefusedError())))
    report = tool.measure([{"id": "a", "question": "Synthetic"}], surface="foreground",
                          endpoint="http://127.0.0.1:1", cache_condition="warm")
    assert "delivery           error 1" in tool.render(report)


def test_swap_and_memory_pressure_are_parsed_from_the_mac_sysctls(tool, monkeypatch):
    # Every C1 row carried memory_pressure=None and swap_bytes=None however it was run, so a Mac session
    # could not record what C1 asks for. Output strings below are the macOS 14 formats.
    replies = {"vm.swapusage": "total = 2048.00M  used = 1186.25M  free = 861.75M  (encrypted)",
               "kern.memorystatus_vm_pressure_level": "2"}
    monkeypatch.setattr(tool, "_sysctl", lambda name: replies.get(name))
    sample = tool.memory_sample()
    assert sample == {"swap_bytes": int(1186.25 * 1024 ** 2), "memory_pressure": "warn"}


def test_memory_readings_stay_unknown_where_the_sysctls_do_not_exist(tool, monkeypatch):
    monkeypatch.setattr(tool, "_sysctl", lambda name: None)
    assert tool.memory_sample() == {"swap_bytes": None, "memory_pressure": None}
    monkeypatch.setattr(tool, "_sysctl", lambda name: "garbled")
    assert tool.memory_sample() == {"swap_bytes": None, "memory_pressure": None}


def test_each_row_carries_its_memory_sample_and_dropouts_stay_unmeasured(tool, monkeypatch):
    monkeypatch.setattr(tool, "memory_sample", lambda: {"swap_bytes": 42, "memory_pressure": "normal"})
    monkeypatch.setattr(tool, "_ask_http", lambda *a, **k: ({"answer": "Template"}, 0, None))
    row = tool.measure([{"id": "a", "question": "Synthetic"}], surface="foreground",
                       endpoint="http://127.0.0.1:1", cache_condition="warm")["rows"][0]
    assert row["swap_bytes"] == 42 and row["memory_pressure"] == "normal"
    # No tool here can see Live's audio engine, so the field exists and says so rather than reading zero.
    assert row["audio_dropouts"] is None


def test_provenance_names_the_model_each_task_resolves_to(tool, monkeypatch):
    # KENN_LLM_MODEL alone missed per-task overrides, and read None when only KENN_LLM_MODEL_REWRITE was set.
    monkeypatch.delenv("KENN_LLM_MODEL", raising=False)
    monkeypatch.setenv("KENN_LLM_MODEL_REWRITE", "fixture-rewrite-model")
    models = tool.run_provenance()["resolved_models"]
    assert models["rewrite"] == "fixture-rewrite-model"
    assert set(models) == {"rewrite", "route", "paraphrase", "followups"}


def test_payload_retrieval_time_fills_the_context_retrieval_phase(tool, monkeypatch):
    # answer_payload has returned timings_ms all along; the harness left context_retrieval unknown regardless.
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    timings = {"load_index_ms": 12.0, "search_ms": 30.0, "section_ms": 1.0, "answer_ms": 9000.0}
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: ({"answer": "x", "timings_ms": timings}, 0, None))
    row = tool.measure([{"id": "a", "question": "Synthetic"}], surface="payload")["rows"][0]
    assert row["phase_seconds"]["context_retrieval"] == pytest.approx(0.042)
    assert row["payload_timings_ms"] == timings
    # The gate runs inside answer_ms with the model call, so verification is still not separable.
    assert row["phase_seconds"]["verification"] is None


def test_foreground_retrieval_time_comes_from_the_companion_timing_block(tool, monkeypatch):
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "x", "timing": {"total_ms": 9100.0, "load_index_ms": 2.0, "search_ms": 18.0}}), surface="foreground")
    assert row["phase_seconds"]["context_retrieval"] == pytest.approx(0.020)


def test_background_retrieval_stays_unknown_because_the_template_is_not_the_upgrade(tool, monkeypatch):
    row = _measure_http(tool, monkeypatch, _FakeCompanion(
        {"answer": "Template", "timing": {"load_index_ms": 2.0, "search_ms": 18.0}, "answer_upgrade": {"id": "job"}},
        [{"status": "accepted", "answer": "Model", "seconds": 8.0}]))
    assert row["phase_seconds"]["context_retrieval"] is None


def test_retrieval_stays_unknown_when_either_half_is_missing(tool, monkeypatch):
    monkeypatch.setattr(tool, "_drop_semantic_cache", lambda: None)
    monkeypatch.setattr(tool, "_ask", lambda *a, **k: ({"answer": "x", "timings_ms": {"search_ms": 30.0}}, 0, None))
    row = tool.measure([{"id": "a", "question": "Synthetic"}], surface="payload")["rows"][0]
    assert row["phase_seconds"]["context_retrieval"] is None
