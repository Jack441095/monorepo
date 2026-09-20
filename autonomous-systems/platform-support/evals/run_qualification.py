"""Qualification metrics collector.

Tracks:
  A. Real Thursday intent routing over the frozen paraphrase corpus
     (imports thursday.intent READ-ONLY via the Audio_Too venv).
  B. Model bake-off: local Ollama (qwen2.5:0.5b) vs deterministic baseline
     on a grounded company-brief task (hallucination + latency).

Run with the Audio_Too venv so both nite_ai and thursday are importable:
    Audio_Too/.venv/bin/python evals/run_qualification.py

Writes docs/qualification_metrics.json. Read-only w.r.t. all repositories.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT))

from thursday_eval_v1 import GROUNDING_CORPUS, ROUTING_CORPUS  # noqa: E402

# Resolve the preserved owner-runtime boundary from the canonical estate root.
# This keeps the read-only qualification adapter portable after the estate move.
AUDIO_TOO = Path(__file__).resolve().parents[3] / "Audio_Too"
sys.path.insert(0, str(AUDIO_TOO))
sys.path.insert(0, str(AUDIO_TOO / "studio" / "kenn"))

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("EVAL_MODEL", "qwen2.5:0.5b")


def collect_thursday_routing() -> dict:
    """Run the REAL thursday.intent classifier over the frozen corpus."""
    from thursday.intent import classify_intent  # real product code, read-only

    results = {}
    total = correct_domain_hits = 0
    for capability_id, phrases in ROUTING_CORPUS.items():
        hits = []
        for phrase in phrases:
            intent = classify_intent(phrase)
            total += 1
            if intent:
                hits.append(str(intent))
        results[capability_id] = hits
        # Company capabilities do not exist in Thursday's intent taxonomy yet;
        # we record what it DOES classify so the gap is measurable.
        correct_domain_hits += len(hits)
    return {
        "corpus_size": total,
        "classified_by_thursday": correct_domain_hits,
        "unclassified": total - correct_domain_hits,
        "per_capability": {k: v for k, v in results.items()},
        "note": ("Thursday's intent taxonomy predates company capabilities; "
                 "an unclassified result is EXPECTED until company intents "
                 "are registered (tracked as improvement IMP-1)."),
    }


def _ollama_generate(prompt: str, timeout: float = 60.0) -> tuple[str, float]:
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data.get("response", ""), time.perf_counter() - start


def collect_model_bakeoff() -> dict:
    """Grounded summarisation task: model must report ONLY facts present in
    the provided DailyBriefData JSON. Fabricated blockers/priorities = fail."""
    from nite_ai.company_store import open_store
    from nite_ai.briefing import assemble_daily_brief

    conn, store = open_store(":memory:")
    from nite_ai.domain import Goal as DomainGoal

    store.create_goal(DomainGoal(goal_id="g1", kind="company", title="Ship products"))
    store.create_goal(DomainGoal(goal_id="g2", kind="quarterly", title="Q readiness",
                                 parent_goal_id="g1"))
    brief = assemble_daily_brief(store).to_dict()
    truth = {"top_priorities": set(brief["top_priorities"]),
             "blockers": set(brief["blockers"])}
    prompt = (
        "You are given company state as JSON:\n"
        f"{json.dumps(brief)}\n"
        "List ONLY the blocker task ids and priority task ids that appear in "
        'the JSON. If none exist, reply {"blockers": [], "priorities": []}. '
        "Do not invent anything."
    )
    trials = 5
    fabrications = 0
    latencies = []
    parse_failures = 0
    for _ in range(trials):
        try:
            text, dt = _ollama_generate(prompt)
            latencies.append(dt)
            try:
                out = json.loads(text)
                claimed = set(out.get("blockers", [])) | set(out.get("priorities", []))
                if claimed - truth["blockers"] - truth["priorities"]:
                    fabrications += 1
            except json.JSONDecodeError:
                parse_failures += 1
        except Exception as exc:
            latencies.append(-1.0)
            parse_failures += 1
            print(f"model call failed: {exc}", file=sys.stderr)
    conn.close()
    ok_lat = [l for l in latencies if l >= 0]
    return {
        "model": MODEL,
        "trials": trials,
        "fabrication_trials": fabrications,
        "parse_failure_trials": parse_failures - (len(latencies) - len(ok_lat)),
        "latency_p50_s": sorted(ok_lat)[len(ok_lat) // 2] if ok_lat else None,
        "deterministic_baseline": {
            "fabrication_trials": 0,
            "latency_ms_typical": "<1",
            "note": "assemble_daily_brief is pure code over SQLite",
        },
    }


def main() -> None:
    metrics = {
        "benchmark_version": "THURSDAY_EVAL_V1",
        "thursday_routing": collect_thursday_routing(),
        "model_bakeoff": collect_model_bakeoff(),
        "captured_at_epoch": time.time(),
    }
    out = ROOT / "docs" / "qualification_metrics.json"
    out.write_text(json.dumps(metrics, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in metrics.items() if k != "thursday_routing"},
                     indent=2)[:800])
    print(f"written: {out}")


if __name__ == "__main__":
    main()
