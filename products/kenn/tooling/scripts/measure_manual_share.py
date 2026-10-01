#!/usr/bin/env python3
"""How much does the Live 11 manual actually contribute to retrieval? (Stage 1 / C1 keep-or-drop evidence)

    measure_manual_share.py [--cases ...] [--limit 0] [--receipt PATH]

The North Star records the open question as the owner's: the index carries 1,436 `official_ableton_manual` chunks,
all from **Live 11**, while the producer runs **Live 12 Suite**, and the Knowledge programme ranks the manual above
curated notes. So KENN can cite Live 11 documentation for a Live 12 product. The decision needs two numbers before it
can be made sensibly: how often the manual is retrieved at all, and whether it is displacing the curated note that
would have answered the question.

This measures the first, and the part of the second that does not need a rebuild. **It deliberately does not filter
the chunk pool to compare with-and-without**, because that does not work: `search()` hands `bm25_search` an index
cached against the full corpus, so passing a filtered pool raises `IndexError: list index out of range` at
`retrieval.py:781` — the doc indices belong to the 4,642-chunk index, not the 3,206 you passed. A real keep/drop
comparison means rebuilding the index without the manual, which is the owner's call anyway because it replaces the
live index.

Read-only: it searches the existing index and writes nothing but its own receipt.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

EVALS = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals"
DEFAULT_SETS = [
    ("device purpose", EVALS / "device_purpose_retrieval_cases.json"),
    ("technique", EVALS / "technique_purpose_retrieval_cases.json"),
    ("sealed holdout", EVALS / "device_purpose_sealed_holdout.json"),
]
MANUAL = "official_ableton_manual"


def _norm(value) -> str:
    """Fixture expectations name a source without its extension; the index carries the `.md`."""
    text = str(value).strip().casefold()
    return text[:-3] if text.endswith(".md") else text


def measure(paths: list[tuple[str, Path]], limit: int) -> dict:
    from kenn.core.chat_retrieval import load_chunks, load_terms, search

    chunks, terms = load_chunks(), load_terms()
    composition = Counter(c.get("evidence_class") for c in chunks)
    report: dict = {
        "schema": "kenn.manual_share.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_version": (KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT").read_text(
            encoding="utf-8").strip(),
        "chunks_total": len(chunks),
        "chunks_by_class": dict(composition.most_common()),
        "sets": [],
    }
    for label, path in paths:
        if not path.is_file():
            report["sets"].append({"name": label, "missing": str(path)})
            continue
        cases = json.loads(path.read_text(encoding="utf-8")).get("cases", [])
        if limit:
            cases = cases[:limit]
        asked = top1 = in_top4 = 0
        manual_slots: list[int] = []
        for case in cases:
            question = str(case.get("question") or "").strip()
            if not question:
                continue
            asked += 1
            results = search(question, chunks, terms, limit=4)
            classes = [c.get("evidence_class") for _score, c in results]
            slots = sum(1 for c in classes if c == MANUAL)
            manual_slots.append(slots)
            if slots:
                in_top4 += 1
            if classes and classes[0] == MANUAL:
                top1 += 1
        report["sets"].append({
            "name": label,
            "questions": asked,
            "manual_top1": top1,
            "manual_top1_rate": round(top1 / asked, 3) if asked else None,
            "manual_in_top4": in_top4,
            "manual_in_top4_rate": round(in_top4 / asked, 3) if asked else None,
            "mean_manual_per_query": round(statistics.mean(manual_slots), 3) if manual_slots else None,
        })
    return report


def render(report: dict) -> str:
    manual = report["chunks_by_class"].get(MANUAL, 0)
    share = 100 * manual / report["chunks_total"] if report["chunks_total"] else 0
    lines = [
        f"Live 11 manual share of retrieval (index {report['index_version']})",
        f"  manual chunks    {manual} of {report['chunks_total']} ({share:.0f}% of the index)",
        f"  {'set':<16} {'asked':>6} {'top-1':>8} {'in top-4':>10} {'mean/query':>11}",
    ]
    for row in report["sets"]:
        if row.get("missing"):
            lines.append(f"  {row['name']:<16} no fixture at {row['missing']}")
            continue
        lines.append(
            f"  {row['name']:<16} {row['questions']:>6} "
            f"{row['manual_top1']:>4} {row['manual_top1_rate']:>4.0%} "
            f"{row['manual_in_top4']:>5} {row['manual_in_top4_rate']:>4.0%} "
            f"{row['mean_manual_per_query']:>10.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=0, help="cap questions per set, for a quick look")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    report = measure(DEFAULT_SETS, args.limit)
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
