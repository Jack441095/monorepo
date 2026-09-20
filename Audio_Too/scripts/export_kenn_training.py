#!/usr/bin/env python3
"""Export KENN eval cases as ML-ready JSONL records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_SUITE = ABLETON / "evals" / "questions.json"
DEFAULT_OUT = ABLETON / "artifacts" / "training" / "kenn_answer_records.jsonl"


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Suite must contain cases list: {path}")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Export KENN eval data as JSONL for future ML/Torch work.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Eval suite JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output JSONL path.")
    parser.add_argument("--limit", type=int, default=8, help="Retrieval source limit.")
    args = parser.parse_args()

    sys.path.insert(0, str(ABLETON.parent))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    from ableton_eval import evaluate_case  # noqa: E402
    from kenn.core.chat import answer_payload, warm_index  # noqa: E402
    from kenn.training.training_records import answer_record, write_jsonl  # noqa: E402

    warm_index()
    records = []
    for case in load_cases(args.suite):
        question = str(case.get("question", "")).strip()
        if not question:
            continue
        payload = answer_payload(question, limit=args.limit, allow_llm=False)
        records.append(answer_record(case, payload, evaluate_case(case, payload)))
    write_jsonl(args.output, records)
    passed = sum(1 for record in records if record["eval_passed"])
    print(f"Exported {len(records)} KENN training records to {args.output}")
    print(f"Eval labels: {passed}/{len(records)} passed")
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
