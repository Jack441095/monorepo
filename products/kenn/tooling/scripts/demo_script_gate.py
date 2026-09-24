#!/usr/bin/env python3
"""Exercise the non-mutating contract of the KENN investor-demo script.

This gate never confirms a proposal and cannot qualify a complete rehearsal.
It covers the thirteen scripted prompts that can be checked without changing
Live; the remaining UI, mutation, undo, and presentation steps stay manual.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable


MAX_COMMAND_LATENCY_MS = 650.0
# Stay under KENN's per-route budgets (server_rate_limit.RATE_LIMITS):
# the command route allows 60/min and the chat route ("ask") 30/min.
ROUTE_INTERVAL_MS = {"command": 1100.0, "ask": 2100.0}
MANUAL_STEPS = {
    1: "Show the loaded Live set and connected status in the UI.",
    10: "Confirm and verify the EQ inverse against Live.",
    14: "Show the advice cards in the frontend.",
    17: "Explain a pending token in the UI without confirming a hazardous action.",
    18: "Show the receipt journal and before/after values.",
    19: "Use the receipt Undo control and verify independent Live readback.",
    20: "Deliver the roadmap explanation with shipped/future labels.",
}


@dataclass(frozen=True)
class GateResult:
    step: int
    command: str
    passed: bool
    detail: str
    elapsed_ms: float


def _intent_action(body: dict[str, Any]) -> str:
    intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
    return str(intent.get("action") or "")


def _require_read_only(body: dict[str, Any]) -> None:
    if body.get("changed") is not False:
        raise ValueError("response did not explicitly prove changed=false")


def _require_session_answer(body: dict[str, Any], action: str) -> None:
    _require_read_only(body)
    # The command gateway labels these "session_question"; the chat route
    # (/kenn/api/ask) serves the same grounded answer as "live_inspection".
    if body.get("status") != "inspected" or body.get("answer_mode") not in {"session_question", "live_inspection"}:
        raise ValueError("response was not a grounded session answer")
    if _intent_action(body) != action:
        raise ValueError(f"expected intent {action}")
    if not str(body.get("answer") or "").strip():
        raise ValueError("answer text was empty")


def _require_proposal(
    body: dict[str, Any],
    *,
    operation: str,
    track_name: str,
    after: float | int | None = None,
    device_name: str | None = None,
    parameter: str | None = None,
) -> None:
    _require_read_only(body)
    proposal = body.get("proposal") if isinstance(body.get("proposal"), dict) else {}
    if body.get("status") != "confirmation_required":
        raise ValueError("command did not stop for confirmation")
    if proposal.get("requires_confirmation") is not True or not proposal.get("confirmation_token"):
        raise ValueError("proposal was not bound to a confirmation token")
    if proposal.get("operation") != operation or proposal.get("track_name") != track_name:
        raise ValueError(f"proposal did not resolve exactly to {track_name} / {operation}")
    if device_name is not None and proposal.get("device_name") != device_name:
        raise ValueError(f"proposal did not resolve device {device_name}")
    if parameter is not None and proposal.get("parameter") != parameter:
        raise ValueError(f"proposal did not resolve parameter {parameter}")
    if after is not None:
        try:
            matches = abs(float(proposal.get("after")) - float(after)) <= 1e-6
        except (TypeError, ValueError):
            matches = False
        if not matches:
            raise ValueError(f"proposal target value was not {after}")


def _track_count(body: dict[str, Any]) -> None:
    _require_session_answer(body, "inspect_track_count")
    if body.get("track_count") != 8:
        raise ValueError("demo fixture did not report exactly eight tracks")


def _selected_track(body: dict[str, Any]) -> None:
    _require_session_answer(body, "inspect_selected_track")
    track = body.get("track") if isinstance(body.get("track"), dict) else {}
    if track.get("name") != "Drum Bus" or track.get("number") != 4:
        raise ValueError("Drum Bus (track 4) was not selected")


def _overview(body: dict[str, Any]) -> None:
    _require_session_answer(body, "inspect_overview")
    names = [str(item.get("name")) for item in body.get("tracks") or [] if isinstance(item, dict)]
    if names != ["Kick", "Snare / Clap", "Hi-Hats", "Drum Bus", "Bass", "Synth", "Lead Vocal", "FX Print"]:
        raise ValueError("session overview did not match the ordered demo fixture")


def _duplicates(body: dict[str, Any]) -> None:
    _require_session_answer(body, "inspect_duplicate_names")
    if body.get("duplicate_track_names") != []:
        raise ValueError("demo fixture contains duplicate track names")


def _vocal_output(body: dict[str, Any]) -> None:
    _require_proposal(
        body,
        operation="set_device_parameter",
        track_name="Lead Vocal",
        device_name="Compressor",
        parameter="Output",
        after=3.0,
    )


def _synth_pan(body: dict[str, Any]) -> None:
    _require_proposal(body, operation="set_pan", track_name="Synth", parameter="pan", after=-1.0)


def _bass_focus(body: dict[str, Any]) -> None:
    _require_proposal(body, operation="focus_device", track_name="Bass", device_name="EQ Eight")


def _bass_eq(body: dict[str, Any]) -> None:
    _require_proposal(
        body,
        operation="set_device_parameter",
        track_name="Bass",
        device_name="EQ Eight",
        parameter="2 Gain A",
        after=3.0,
    )
    proposal = body["proposal"]
    if proposal.get("eq_band") != "2A":
        raise ValueError("EQ proposal did not retain the explicit 2A band identity")
    try:
        frequency_matches = abs(float(proposal.get("requested_frequency_hz")) - 200.0) <= 1e-6
    except (TypeError, ValueError):
        frequency_matches = False
    if not frequency_matches:
        raise ValueError("EQ proposal did not retain the requested 200 Hz frequency")


def _history(body: dict[str, Any]) -> None:
    # History is scoped to the asking session, and this gate never confirms a
    # change, so an honest "no changes yet" answer is the expected contract.
    if body.get("status") == "no_changes":
        body = {**body, "status": "inspected"}
    _require_session_answer(body, "inspect_change_history")
    if not isinstance(body.get("changes"), list):
        raise ValueError("change history did not return a structured list")


def _advice(body: dict[str, Any], *, scope: str, finding_type: str) -> None:
    _require_session_answer(body, "inspect_mix_advice")
    if body.get("advice_mode") != "audio_analysis" or body.get("analysis_scope") != scope:
        raise ValueError(f"{scope} request did not use measured audio analysis")
    if body.get("advisory_only") is not True:
        raise ValueError("audio result was not explicitly advisory-only")
    source = body.get("analysis_source") if isinstance(body.get("analysis_source"), dict) else {}
    if len(str(source.get("sha256") or "")) != 64:
        raise ValueError("audio result was not bound to a source hash")
    if source.get("cache_hit") is not True:
        raise ValueError("analysis cache was not warmed by preflight")
    findings = {str(item.get("type")) for item in body.get("findings") or [] if isinstance(item, dict)}
    if finding_type not in findings:
        raise ValueError(f"expected measured finding {finding_type}")


def _low_end(body: dict[str, Any]) -> None:
    _advice(body, scope="low_end", finding_type="possible_low_end_excess")


def _vocal_clipping(body: dict[str, Any]) -> None:
    _advice(body, scope="vocal", finding_type="clipping")


def _refusal(body: dict[str, Any], *, phrase: str) -> None:
    _require_read_only(body)
    if body.get("status") != "refused" or body.get("confirmation_required") is not False:
        raise ValueError("unsafe command was not refused without a proposal")
    answer = str(body.get("answer") or "")
    if phrase.casefold() not in answer.casefold():
        raise ValueError("refusal did not contain the expected plain-English boundary")


def _delete_refusal(body: dict[str, Any]) -> None:
    _refusal(body, phrase="disabled by the KENN assistant boundary")


def _master_refusal(body: dict[str, Any]) -> None:
    _refusal(body, phrase="outside KENN's qualified control boundary")


SCRIPT_STEPS: tuple[tuple[int, str, Callable[[dict[str, Any]], None]], ...] = (
    (2, "How many tracks do I have?", _track_count),
    (3, "What's selected?", _selected_track),
    (4, "Describe this session.", _overview),
    (5, "Any duplicate track names?", _duplicates),
    (6, "Set Compressor Output to 3 dB on track 7.", _vocal_output),
    (7, "Pan the Synth hard left.", _synth_pan),
    (8, "Focus EQ Eight on track 5.", _bass_focus),
    (9, "Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.", _bass_eq),
    (11, "What did you change?", _history),
    (12, "How does my low end sound?", _low_end),
    (13, "Check the vocals for clipping.", _vocal_clipping),
    (15, "Delete track 3.", _delete_refusal),
    (16, "Set the master volume to maximum.", _master_refusal),
)


class DemoScriptGate:
    def __init__(
        self,
        base_url: str,
        *,
        max_latency_ms: float = MAX_COMMAND_LATENCY_MS,
        command_interval_ms: float = 1100.0,
        route: str = "command",
    ) -> None:
        if route not in {"command", "ask"}:
            raise ValueError("route must be 'command' or 'ask'")
        self.route = route
        self.base_url = base_url.rstrip("/")
        self.max_latency_ms = max_latency_ms
        self.command_interval_ms = command_interval_ms
        self._last_command_started = 0.0

    def _command(self, command: str, *, session_id: str) -> tuple[dict[str, Any], float]:
        wait_seconds = max(
            0.0,
            (self.command_interval_ms / 1000.0) - (time.monotonic() - self._last_command_started),
        )
        if wait_seconds:
            time.sleep(wait_seconds)
        self._last_command_started = time.monotonic()
        if self.route == "ask":
            path = "/kenn/api/ask"
            payload = {"session_id": session_id, "question": command, "stream": False}
        else:
            path = "/api/ableton/command"
            payload = {"session_id": session_id, "command": command, "deterministic_only": True}
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=8.0) as response:
            body = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError("KENN returned a non-success response.")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if self.route == "ask":
            # A Live command answered in chat embeds the gateway's own result;
            # validate that exact contract, and time the chat round trip.
            orchestration = body.get("orchestration") if isinstance(body.get("orchestration"), dict) else {}
            inner = orchestration.get("result")
            if body.get("route") == "ableton_controller" and isinstance(inner, dict):
                body = dict(inner)
            elif body.get("route") == "ableton_live_inspection":
                # The chat envelope replaces status with "succeeded" and flattens
                # intent to a string; rebuild the gateway view from found/live_intent.
                intent = body.get("live_intent") if isinstance(body.get("live_intent"), dict) else {
                    "action": body.get("intent")
                }
                grounded = bool(body.get("found")) or intent.get("action") == "inspect_change_history"
                body = {**body, "intent": intent, "status": "inspected" if grounded else body.get("status")}
            if not isinstance((body.get("latency") or {}).get("total_ms"), (int, float)):
                body = {**body, "latency": {"total_ms": elapsed_ms}}
        return body, elapsed_ms

    @staticmethod
    def _friendly_failure(exc: Exception) -> str:
        if isinstance(exc, urllib.error.HTTPError):
            if exc.code == 429:
                return "KENN rate-limited the rehearsal burst — wait for the window to reset and restart the count."
            return "KENN reported that the command route is unavailable."
        if isinstance(exc, (urllib.error.URLError, ConnectionError)):
            return "KENN is not responding — start the server and retry."
        if isinstance(exc, (TimeoutError, OSError)) and "tim" in str(exc).casefold():
            return "KENN did not respond within the rehearsal timeout."
        if isinstance(exc, (ValueError, RuntimeError)) and str(exc).strip():
            return str(exc).strip()
        return "The scripted check could not complete safely; inspect the server log."

    def run_once(self, *, run_number: int = 1) -> list[GateResult]:
        session_id = f"demo-script-gate-{run_number}-{uuid.uuid4().hex}"
        results: list[GateResult] = []
        for step, command, validator in SCRIPT_STEPS:
            started = time.perf_counter()
            try:
                body, elapsed_ms = self._command(command, session_id=session_id)
                validator(body)
                reported_ms = (body.get("latency") or {}).get("total_ms")
                if not isinstance(reported_ms, (int, float)):
                    raise ValueError("response did not report end-to-end command latency")
                if float(reported_ms) >= self.max_latency_ms:
                    raise ValueError(
                        f"reported command latency {float(reported_ms):.1f}ms exceeded "
                        f"the {self.max_latency_ms:.0f}ms budget"
                    )
                detail = f"contract matched; reported latency {float(reported_ms):.1f}ms"
                passed = True
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                detail = self._friendly_failure(exc)
                passed = False
            results.append(GateResult(step, command, passed, detail, round(elapsed_ms, 1)))
            if not passed:
                break
        return results


def run_gate(
    base_url: str,
    *,
    runs: int,
    max_latency_ms: float,
    command_interval_ms: float = 1100.0,
    route: str = "command",
) -> dict[str, Any]:
    gate = DemoScriptGate(
        base_url,
        max_latency_ms=max_latency_ms,
        command_interval_ms=command_interval_ms,
        route=route,
    )
    run_results: list[dict[str, Any]] = []
    for run_number in range(1, runs + 1):
        results = gate.run_once(run_number=run_number)
        passed = len(results) == len(SCRIPT_STEPS) and all(item.passed for item in results)
        run_results.append({
            "run": run_number,
            "passed": passed,
            "results": [asdict(item) for item in results],
        })
        if not passed:
            break
    passed_runs = sum(bool(item["passed"]) for item in run_results)
    return {
        "schema": "kenn.investor_demo_script_gate.v1",
        "mode": "non_mutating_contract_only",
        "requested_runs": runs,
        "passed_runs": passed_runs,
        "automated_steps": [step for step, _, _ in SCRIPT_STEPS],
        "manual_steps": MANUAL_STEPS,
        "full_demo_qualified": False,
        "runs": run_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-latency-ms", type=float, default=MAX_COMMAND_LATENCY_MS)
    parser.add_argument(
        "--command-interval-ms",
        type=float,
        default=None,
        help="Minimum interval between requests; the default stays below KENN's supervised API rate limit.",
    )
    parser.add_argument(
        "--route",
        choices=("command", "ask"),
        default="command",
        help="'ask' sends every prompt through /kenn/api/ask, the route the chat UI uses.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error("--runs must be between 1 and 10")
    if args.max_latency_ms <= 0:
        parser.error("--max-latency-ms must be positive")
    if args.command_interval_ms is None:
        args.command_interval_ms = ROUTE_INTERVAL_MS[args.route]
    if args.command_interval_ms < 0:
        parser.error("--command-interval-ms must be non-negative")

    report = run_gate(
        args.url,
        runs=args.runs,
        max_latency_ms=args.max_latency_ms,
        command_interval_ms=args.command_interval_ms,
        route=args.route,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("KENN Investor Demo Script Contract Gate\n" + "=" * 39)
        for run in report["runs"]:
            print(f"Run {run['run']}: {'PASS' if run['passed'] else 'FAIL'}")
            for item in run["results"]:
                symbol = "✓" if item["passed"] else "x"
                print(f"  [{symbol}] step {item['step']}: {item['detail']} ({item['elapsed_ms']:.1f}ms)")
        print(
            f"\n{report['passed_runs']}/{report['requested_runs']} non-mutating contract run(s) passed. "
            "This is not a full demo qualification; seven steps remain manual."
        )
    return 0 if report["passed_runs"] == report["requested_runs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
