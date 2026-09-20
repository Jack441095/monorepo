#!/usr/bin/env python3
"""Blind model comparison for the KENN SLM decision (plan §8.5 / §23 Stage 2).

Runs the SAME held-out cases through three configurations and scores each on
the metrics that actually decide whether to keep investing in the fine-tuned
model:

  A. deterministic  — answer_payload(allow_llm=False): the current safe default
  B. base           — base Qwen2.5-1.5B-Instruct, identical prompt to the LoRA
  C. lora           — the merged 4-bit fine-tune (kenn-mlx), KENN's generative path

Metrics (per config, aggregated):
  - answer quality: gold must-include coverage, must-not-include violations,
    topic-match rate (from the eval suite's labelled criteria)
  - hallucinated measurements: numeric+unit tokens (dB/Hz/LUFS/ms/%/ratios/BPM…)
    that appear in the answer but NOT in the retrieved source context — this is
    the config-independent safety metric and the real differentiator
  - latency: wall-clock generation seconds
  - length: answer characters

Design notes:
  - Must run under the native arm64 Python that hosts mlx-lm (see kenn_lm.py's
    _MLX_PYTHON) — that interpreter can also import KENN's onnx retrieval, so the
    whole comparison runs in one process with one retrieval per case (fair: all
    three configs see identical context).
  - Base and LoRA are generated with self_correct OFF (raw model behaviour), so
    the comparison isolates the model, not the post-processing critique loop.

Usage (from repo root, arm64 python):
  arch -arm64 <py3.13> scripts/eval/kenn_model_blind_eval.py --limit 30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KENN_ROOT = REPO_ROOT / "studio" / "kenn"
SUITE_PATH = KENN_ROOT / "kenn" / "evals" / "questions.json"
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
LORA_MODEL = str(KENN_ROOT / "kenn" / "artifacts" / "models" / "kenn-mlx")
ARTIFACT_DIR = KENN_ROOT / "kenn" / "artifacts" / "model_eval"

sys.path.insert(0, str(KENN_ROOT))
sys.path.insert(0, str(REPO_ROOT))

# Measurement tokens: a number (optionally signed/decimal) immediately tied to
# an audio unit. These are the values a model must never invent — if the answer
# states "cut 4 dB at 3 kHz" it must be backed by the retrieved sources.
_MEASUREMENT_RE = re.compile(
    r"[-+]?\d+(?:\.\d+)?\s?"
    r"(?:dbtp|dbfs|db|hz|khz|lufs|lu|khz|ms|bpm|%|semitones?|cents?|:1|:\d)",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower())


def extract_measurements(text: str) -> list[str]:
    return [re.sub(r"\s+", "", m.group(0).lower()) for m in _MEASUREMENT_RE.finditer(text or "")]


def hallucinated_measurements(answer: str, context: str) -> list[str]:
    ctx = _normalize(context).replace(" ", "")
    leaks = []
    for meas in extract_measurements(answer):
        if meas not in ctx:
            leaks.append(meas)
    return leaks


def score_quality(case: dict, answer: str) -> dict:
    low = _normalize(answer)
    must = [t for t in case.get("answer_must_include", []) if t]
    must_not = [t for t in case.get("answer_must_not_include", []) if t]
    present = [t for t in must if t.lower() in low]
    include_any = [t for t in case.get("answer_must_include_any", []) if t]
    any_hit = not include_any or any(t.lower() in low for t in include_any)
    critical = [t for t in case.get("critical_forbidden_claims", []) if t]
    violations = [t for t in [*must_not, *critical] if t.lower() in low]
    covered = len(present) + int(bool(include_any) and any_hit)
    total = len(must) + int(bool(include_any))
    return {
        "must_include_total": total,
        "must_include_hit": covered,
        "must_include_coverage": round(covered / total, 3) if total else 1.0,
        "must_not_violations": len(violations),
        "violation_terms": violations,
    }


def build_grounding_corpus(sources: list[dict]) -> str:
    """All retrieved source text (untruncated) for the hallucination check.

    A measurement counts as hallucinated only if it appears in NO retrieved
    source — not merely because it fell outside the truncated prompt block.
    This keeps the safety metric fair across all three configs.
    """
    return " ".join(str(s.get("text", "")) for s in sources)


def build_context_block(sources: list[dict], *, max_chars: int = 3500) -> str:
    """Mirror llm_rewrite.build_raw_context_block from answer_payload sources."""
    parts, count = [], 0
    for src in sources[:4]:
        label = src.get("label") or src.get("title") or src.get("source") or "source"
        text = str(src.get("text", ""))[:1200]
        score = float(src.get("score", 0) or 0)
        block = f"[Source: {label} | relevance {score:.1f}]\n{text}"
        if count + len(block) > max_chars:
            remaining = max_chars - count
            if remaining > 200:
                parts.append(block[:remaining])
            break
        parts.append(block)
        count += len(block)
    return "\n\n".join(parts) if parts else "(no source excerpts provided)"


def build_messages(context: str, query: str, *, strict: bool = False) -> list[dict]:
    """Identical to KennLM.generate's structural prompt (kenn_lm.py)."""
    system = "You are KENN, a senior audio engineer answering from provided sources."
    if strict:
        system += (
            " Answer ONLY from the provided context. Do not use memorized facts or invent "
            "settings. When the context is irrelevant or insufficient, say exactly: "
            "'The provided sources do not contain enough information to answer that.'"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}"},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind KENN model comparison.")
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max cases (0 = all).")
    parser.add_argument("--max-tokens", type=int, default=450)
    parser.add_argument("--stride", type=int, default=1, help="Sample every Nth case for a spread.")
    parser.add_argument(
        "--ensure-category",
        action="append",
        default=[],
        help="Append the first omitted case in this category after stride/limit selection.",
    )
    parser.add_argument(
        "--configs", default="deterministic,base,lora",
        help="Comma-separated subset of {deterministic,base,lora}. Drop 'base' to halve "
             "memory/time — the fp16 base is the heavy leg and its inferiority is already established.",
    )
    parser.add_argument(
        "--prompt",
        choices=("legacy", "strict"),
        default="strict",
        help="Prompt policy for base/LoRA generations.",
    )
    args = parser.parse_args()

    from mlx_lm import load, generate
    from kenn.core.chat import answer_payload

    configs = [c.strip() for c in args.configs.split(",") if c.strip()]

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    all_cases = suite.get("cases", suite) if isinstance(suite, dict) else suite
    cases = list(all_cases)
    if args.stride > 1:
        cases = cases[:: args.stride]
    if args.limit:
        cases = cases[: args.limit]
    selected_ids = {str(case.get("id") or "") for case in cases}
    for category in args.ensure_category:
        if any(str(case.get("category") or "standard") == category for case in cases):
            continue
        extra = next(
            (
                case
                for case in all_cases
                if str(case.get("category") or "standard") == category
                and str(case.get("id") or "") not in selected_ids
            ),
            None,
        )
        if extra is not None:
            cases.append(extra)
            selected_ids.add(str(extra.get("id") or ""))

    print(f"Loaded {len(cases)} cases. Configs: {configs}. Loading models…", flush=True)
    models: dict[str, tuple] = {}
    if "base" in configs:
        t = time.time()
        models["base"] = load(BASE_MODEL)
        print(f"  base Qwen loaded in {time.time() - t:.1f}s", flush=True)
    if "lora" in configs:
        t = time.time()
        models["lora"] = load(LORA_MODEL)
        print(f"  LoRA (kenn-mlx) loaded in {time.time() - t:.1f}s", flush=True)

    def gen(model, tok, messages) -> tuple[str, float]:
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        start = time.time()
        out = generate(model, tok, prompt=prompt, max_tokens=args.max_tokens, verbose=False)
        return out.strip(), time.time() - start

    agg = {c: {"cases": 0, "coverage": 0.0, "violations": 0, "halluc_measurements": 0,
               "halluc_cases": 0, "latency": 0.0, "chars": 0} for c in configs}
    rows = []

    for i, case in enumerate(cases, 1):
        q = str(case.get("question", "")).strip()
        if not q:
            continue
        supplied_context = str(case.get("context") or "").strip()
        if supplied_context:
            det_answer = ""
            sources = [
                {
                    "label": "sealed synthetic context",
                    "source": "sealed-context",
                    "kind": "eval",
                    "text": supplied_context,
                }
            ]
            context = supplied_context
            grounding_corpus = supplied_context
        else:
            det = answer_payload(q, history=None, limit=8, allow_llm=False)
            det_answer = det.get("answer", "")
            sources = det.get("sources", [])
            context = build_context_block(sources)
            grounding_corpus = build_grounding_corpus(sources)

        answers = {}
        messages = build_messages(context, q, strict=args.prompt == "strict")
        if "deterministic" in configs:
            if supplied_context:
                raise ValueError(
                    "deterministic config cannot consume case-supplied context; "
                    "use base/lora for sealed context-adherence suites"
                )
            answers["deterministic"] = (det_answer, 0.0)
        for cfg in ("base", "lora"):
            if cfg in configs:
                answers[cfg] = gen(*models[cfg], messages)

        row = {
            "id": case.get("id", q[:40]),
            "question": q,
            "source_labels": [str(source.get("label") or "") for source in sources],
            "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
            "context_mode": "sealed" if supplied_context else "retrieved",
        }
        for cfg in configs:
            answer, latency = answers[cfg]
            quality = score_quality(case, answer)
            leaks = hallucinated_measurements(answer, grounding_corpus)
            row[cfg] = {
                "coverage": quality["must_include_coverage"],
                "violations": quality["must_not_violations"],
                "halluc_measurements": len(leaks),
                "halluc_terms": leaks[:6],
                "latency_s": round(latency, 2),
                "chars": len(answer),
                "answer": answer,
            }
            a = agg[cfg]
            a["cases"] += 1
            a["coverage"] += quality["must_include_coverage"]
            a["violations"] += quality["must_not_violations"]
            a["halluc_measurements"] += len(leaks)
            a["halluc_cases"] += 1 if leaks else 0
            a["latency"] += latency
            a["chars"] += len(answer)
        rows.append(row)
        print(f"[{i}/{len(cases)}] {row['id']}: "
              + " | ".join(f"{c}=cov{row[c]['coverage']:.2f},leak{row[c]['halluc_measurements']}" for c in configs),
              flush=True)

    summary = {}
    for cfg in configs:
        a = agg[cfg]
        n = max(a["cases"], 1)
        summary[cfg] = {
            "cases": a["cases"],
            "avg_must_include_coverage": round(a["coverage"] / n, 3),
            "total_must_not_violations": a["violations"],
            "total_hallucinated_measurements": a["halluc_measurements"],
            "cases_with_hallucination": a["halluc_cases"],
            "hallucination_case_rate": round(a["halluc_cases"] / n, 3),
            "avg_latency_s": round(a["latency"] / n, 2),
            "avg_answer_chars": round(a["chars"] / n),
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": stamp,
        "suite": str(args.suite),
        "suite_sha256": hashlib.sha256(args.suite.read_bytes()).hexdigest(),
        "n_cases": len(rows),
        "prompt_policy": args.prompt,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "models": {"base": BASE_MODEL, "lora": LORA_MODEL},
        "summary": summary,
        "rows": rows,
    }
    out_path = ARTIFACT_DIR / f"blind_eval_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(f"{'config':<14}{'cases':>6}{'coverage':>10}{'violations':>12}{'halluc/case':>13}{'latency_s':>11}{'chars':>8}")
    for cfg in configs:
        s = summary[cfg]
        print(f"{cfg:<14}{s['cases']:>6}{s['avg_must_include_coverage']:>10.3f}"
              f"{s['total_must_not_violations']:>12}{s['hallucination_case_rate']:>13.3f}"
              f"{s['avg_latency_s']:>11.2f}{s['avg_answer_chars']:>8}")
    print(f"\nReport: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
