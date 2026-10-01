#!/usr/bin/env python3
"""Where chat messages land: Live, or the notes. Both directions, through the real chat route of a fake-Live KENN.

    PYTHONPATH=apps/backend/src:tooling python3 tooling/scripts/measure_chat_routing.py [--output report.json]

The phrasing scorer runs every labelled phrasing straight through the command gateway, so it can't see what the chat
does before that. On 26 Sept 2026 this found only 61% of the requests that should change Live reaching Live from chat,
and 44 of 481 knowledge questions coming back as Live proposals or set facts. This starts its own KENN on a spare port
with the fake Live backend (nothing touches a real set), sends:

- every phrasing in tooling/data/natural_*.jsonl that expects a Live action: it should reach Live;
- the 481 knowledge questions in the retrieval evals: they should not;

and stops the server. Fresh session per message, so nothing carries over.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling" / "scripts"))
DATA = ROOT / "tooling" / "data"
EVALS = ROOT / "apps" / "backend" / "src" / "kenn" / "evals"
from sealed_fixtures import tunable_cases  # noqa: E402
KNOWLEDGE_SETS = ("questions.json", "device_purpose_retrieval_cases.json", "device_purpose_sealed_qwen8b.json")
LIVE_ROUTES = {"ableton_controller", "ableton_live_inspection"}
NOT_A_LIVE_ACTION = {None, "", "clarify", "refuse", "chat", "none"}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(scratch: Path) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    env = {**os.environ, "KENN_PORT": str(port), "KENN_LIVE_BACKEND": "fake", "KENN_ALLOW_DAW_CONTROL": "1",
           "KENN_LLM_ENABLED": "0", "KENN_LIVE_LLM_ENABLED": "0", "KENN_LLM_ENABLED_COMMAND": "0", "KENN_USE_MLX": "0",
           "KENN_INSTANCE_LOCK_PATH": str(scratch / "instance.lock"),
           "KENN_ASKED_LOG": str(scratch / "asked_log.jsonl"),
           "KENN_LIVE_RECEIPT_JOURNAL": str(scratch / "receipts.jsonl")}
    log = open(scratch / "server.log", "w")
    server = subprocess.Popen([sys.executable, str(ROOT / "apps/backend/src/kenn/server.py")], cwd=ROOT, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(90):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=2)
            time.sleep(3)  # let the background auditor take its first look at the fake set
            return server, base
        except OSError:
            if server.poll() is not None:
                break
            time.sleep(1)
    server.kill()
    raise SystemExit(f"KENN didn't start; see {scratch / 'server.log'}")


def _ask(base: str, index: int, question: str) -> dict:
    body = json.dumps({"question": question, "session_id": f"route-{uuid.uuid4().hex[:8]}"}).encode()
    # A private fake server: a different client key per message keeps the 30-a-minute chat limit out of the way.
    request = urllib.request.Request(base + "/kenn/api/ask", body, {"Content-Type": "application/json",
                                                                     "X-Forwarded-For": f"10.{index // 62500}.{index // 250 % 250}.{index % 250}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"route": f"http_{exc.code}"}


def _reached_live(reply: dict) -> bool:
    return reply.get("route") in LIVE_ROUTES or bool(reply.get("proposal"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    requests = [row for path in sorted(DATA.glob("natural_*.jsonl")) for row in map(json.loads, path.open())
                if row.get("expected_action") not in NOT_A_LIVE_ACTION]
    # tunable_cases refuses a sealed fixture: routing thresholds get tuned against these
    # questions, so a holdout does not belong in the list even as a negative.
    questions = [case["question"] for name in KNOWLEDGE_SETS for case in tunable_cases(EVALS / name)]
    with tempfile.TemporaryDirectory() as scratch:
        server, base = _start_server(Path(scratch))
        try:
            with ThreadPoolExecutor(4) as pool:
                request_replies = list(pool.map(lambda item: _ask(base, *item), enumerate(r["query"] for r in requests)))
                question_replies = list(pool.map(lambda item: _ask(base, 100000 + item[0], item[1]), enumerate(questions)))
        finally:
            server.terminate()
            server.wait(timeout=30)

    missed = [{"query": r["query"], "expected": r["expected_action"], "route": d.get("route")}
              for r, d in zip(requests, request_replies) if not _reached_live(d)]
    taken = [{"question": q, "route": d.get("route"), "answer": str(d.get("answer"))[:200]}
             for q, d in zip(questions, question_replies) if _reached_live(d)]
    errors = [{"text": text, "route": d.get("route")} for text, d in
              zip([r["query"] for r in requests] + questions, request_replies + question_replies)
              if str(d.get("route")).startswith("http_")]
    reached = len(requests) - len(missed)
    print(f"requests that should change Live: {reached}/{len(requests)} reached Live ({reached / len(requests):.1%})")
    print("  missed, by route:", collections.Counter(m["route"] for m in missed).most_common())
    print(f"knowledge questions: {len(taken)}/{len(questions)} taken over by Live")
    for row in taken:
        print(f"  {row['route']:>24} | {row['question'][:100]}")
    print(f"server errors: {len(errors)}")
    for row in errors:
        print(f"  {row['route']} | {row['text'][:100]}")
    if args.output:
        args.output.write_text(json.dumps({"schema": "kenn.chat_routing.v1", "requests": len(requests),
                                           "reached_live": reached, "missed": missed, "questions": len(questions),
                                           "taken_over": taken, "errors": errors}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
