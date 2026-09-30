#!/usr/bin/env python3
"""Answer audit: 100 answers, counting the ones with no citable source and the grounding gate's rejections.

    answer_audit.py [--limit 100] [--cases PATH] [--allow-llm] [--receipt PATH]

Two of the measures the North Star added on 28 Sept, because both were invisible until they were counted.

**Answers with no citable source must be zero.** The display layer is allowed to return nothing -- that is how KENN
says "I don't know", and `results_are_weak` checking the display set first is what stops a weak retrieval list from
producing a confident answer with an empty `Sources:` line. An answer that is still *built* with no source is the
failure, and this is the count that says whether that fix is holding.

**Answers rejected by the grounding gate, and why.** A jump means the retrieval or the notes changed, not that the
gate is misbehaving, so the top warning is reported rather than just the rate. The gate failing *open* is the thing
to alarm on; `test_the_marker_prefix_is_not_a_grounding_input_anywhere` is the standing guard for that, and this
script is the other half -- it says how often the gate actually spoke.

Read-only. It asks questions through `kenn.core.chat_answer.answer_payload` and writes nothing except an optional
receipt. No Live, no model unless `--allow-llm`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

DEFAULT_CASES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"


def audit(cases: list[dict], *, allow_llm: bool) -> dict:
    from kenn.core.chat_answer import answer_payload

    rows: list[dict] = []
    for case in cases:
        question = str(case.get("question") or "").strip()
        if not question:
            continue
        try:
            payload = answer_payload(question, allow_llm=allow_llm)
            error = None
        except Exception as exc:  # a fixture error is never reported as a clean audit
            payload, error = {}, f"{type(exc).__name__}: {exc}"
        sources = [s for s in (payload.get("sources") or []) if isinstance(s, dict)]
        answered = bool(payload.get("found"))
        raw_grounding = payload.get("grounding")
        grounding = raw_grounding or {}
        # The retrieval path always sets `grounding`; a recipe or plan does not, because it asserts nothing about a
        # device and so has nothing to cite. Counting "fix muddy low mids" -- a six-step mixer recipe with
        # grounding: null -- as an uncited factual answer was a false positive, and a gate that cries wolf is as
        # useless as one that never fires. Recipes are counted separately and stay visible.
        makes_claims = raw_grounding is not None
        warnings = [str(w) for w in (grounding.get("warnings") or [])]
        validation = payload.get("generation_validation") or {}
        warnings += [f"generation:{w}" for w in (validation.get("warnings") or [])]
        rows.append({
            "id": str(case.get("id") or "unknown"),
            "category": str(case.get("category") or "uncategorized"),
            "route": payload.get("route"),
            "answered": answered,
            "makes_claims": makes_claims,
            # The measure: an answer that made a factual claim and reached the producer with nothing to cite.
            "uncited": answered and makes_claims and not sources,
            "source_count": len(sources),
            "confidence": payload.get("confidence", "none"),
            "grounding_score": grounding.get("score"),
            "warnings": warnings,
            "error": error,
        })

    uncited = [r for r in rows if r["uncited"]]
    uncited_recipes = [r for r in rows if r["answered"] and not r["makes_claims"] and not r["source_count"]]
    warned = [r for r in rows if r["warnings"]]
    top_warning, top_count = ("", 0)
    if warned:
        common = Counter(w for r in warned for w in r["warnings"]).most_common(1)[0]
        top_warning, top_count = common
    return {
        "schema": "kenn.answer_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llm_enabled": allow_llm,
        "counts": {
            "answers": len(rows),
            "answered": sum(r["answered"] for r in rows),
            "abstained": sum(not r["answered"] for r in rows),
            "no_citable_source": len(uncited),
            "uncited_recipes": len(uncited_recipes),
            "grounding_warned": len(warned),
            "errors": sum(1 for r in rows if r["error"]),
        },
        "top_grounding_warning": {"warning": top_warning, "answers": top_count},
        "uncited": uncited,
        "rows": rows,
    }


def render(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "Answer audit (North Star: uncited answers must be 0)",
        f"  answers                      {counts['answers']}",
        f"  answered                     {counts['answered']}",
        f"  abstained ('I don't know')   {counts['abstained']}",
        f"  no citable source            {counts['no_citable_source']}"
        f"   {'PASS' if counts['no_citable_source'] == 0 else 'FAIL'} (required 0)",
        f"  grounding gate spoke         {counts['grounding_warned']}"
        f"   ({(100 * counts['grounding_warned'] / max(1, counts['answers'])):.1f}%)",
        f"  uncited recipes (no claim)    {counts['uncited_recipes']}   reported, not gated",
        f"  errors                       {counts['errors']}",
    ]
    top = report["top_grounding_warning"]
    if top["warning"]:
        lines.append(f"  top grounding warning: {top['warning']!r} on {top['answers']} answers")
    else:
        lines.append("  top grounding warning: none recorded")
    for row in report["rows"]:
        if row["answered"] and not row["makes_claims"] and not row["source_count"]:
            lines.append(f"  recipe, no claim: {row['id']} route={row['route']}")
    for row in report["uncited"][:10]:
        lines.append(f"  uncited: {row['id']} [{row['category']}] answered={row['answered']} sources={row['source_count']}")
    return "\n".join(lines)


def index_missing() -> Path | None:
    """The path of the retrieval artifact this audit cannot run without, or None if it is there.

    Without an index every question abstains, `no_citable_source` comes out 0, and the audit reports PASS for a
    retrieval path that never ran -- the same trap evaluate_retrieval_modes.py (recall 0.0, exit 0) and
    eval_chat_coverage.py (found false everywhere, so counting rows gives 0) both fall into. A missing index has to
    be unmeasured, not clean.
    """
    root = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "index"
    current = root / "CURRENT"
    if not current.is_file():
        return current
    active = current.read_text(encoding="utf-8").strip()
    version = root / "versions" / active
    if not version.is_dir():
        return version
    for name in ("chunks.jsonl", "terms.json"):
        if not (version / name).exists():
            return version / name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=100, help="how many answers to audit (default 100)")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--allow-llm", action="store_true", help="also run the model rewrite path")
    parser.add_argument("--receipt", type=Path, help="write the full JSON receipt here")
    args = parser.parse_args()

    if not args.cases.is_file():
        print(f"No cases at {args.cases}", file=sys.stderr)
        return 1
    missing = index_missing()
    if missing is not None:
        print(f"answer-audit=NOT_MEASURED no retrieval index at {missing}")
        print("Every answer would abstain, so 'no citable source' would read 0 and the audit would pass vacuously.")
        print("Run this from a checkout with apps/backend/src/kenn/data/index/ present (the main checkout has it).")
        return 2
    cases = json.loads(args.cases.read_text(encoding="utf-8")).get("cases", [])[: args.limit]
    report = audit(cases, allow_llm=args.allow_llm)
    print(render(report))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"receipt written to {args.receipt}")
    return 1 if report["counts"]["no_citable_source"] or report["counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
