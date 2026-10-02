#!/usr/bin/env python3
"""Re-score a captured-answers JSONL against the current gate, with no model in the loop.

    rescore_captured_answers.py CAPTURE.jsonl [--per-item OUT.jsonl] [--strata PATH] [--abstain PATH]

The point is that a verdict must be re-derivable without re-running a brain. Every number the 2 Oct 2026 acceptance
work rests on came from a 29-row capture that had to be re-measured to check, because nothing could re-score it in
seconds. Point this at any `.runtime/eval/*.jsonl` written by
`measure_chat_latency.py --capture-answers` and it replays today's gate over the recorded answers.

**The gate is called, never reimplemented.** `generated_answer_validation` in `kenn.core.chat_grounding` is the
production function, imported and called. A copy of its thresholds would be correct on the day it was written and
silently wrong after the next tuning change, and this file exists precisely so that cannot happen -- the recorded
verdict and today's verdict are printed side by side for exactly that reason. When they disagree, either the gate
changed or the retrieval the capture saw has moved; both are answers, and the delta is the finding.

No model, no Live, no index rebuild. `KENN_LLM_ENABLED=0` goes in before any kenn import so an import-time model path
cannot open. Retrieval is re-run per question because the capture stores the rendered evidence text, not the result
list, and the gate needs `(score, chunk)` pairs to call `model_evidence()` on. Retrieval is deterministic, so this
reproduces the capture's own result list on an unchanged index.

**The gate's evidence is recomputed; the capture's own field is not trusted.** The captured `evidence_text` is what
the model was shown, which makes it the natural thing to judge against and the wrong thing to judge against: on the
22-row capture of 2 Oct 2026 it was rendered from `display_results(query, results, 3)` and raw `chunk["text"]` while
the gate had been reading `model_evidence()`'s cleaned, budgeted excerpts since that morning, and 14 of the 22 rows
disagreed. A leak check built on the field reported 8 of 18 accepted answers citing a measurement the gate had in
front of it; the same check against the gate's evidence reported 0 of 18. So every row is replayed through
`model_evidence()` here, the captured field is read only when replay yields nothing at all, and the count of rows
that fell back is printed with the rates.

**A capture that disagrees with today's configuration is labelled before any rate is.** Each row records the index
version and the evidence budget it was written under, and a capture whose recorded values differ from the current
ones -- or that predates the fields entirely -- produces a warning above the numbers rather than a clean result. The
figures that were untrustworthy on 2 Oct were untrustworthy for precisely this reason.

The per-item numeric column is not the gate's. The gate answers "is every measurement in the answer in the shown
evidence"; this additionally answers "is it in the *gold* chunk", which is the stricter question the eval set exists
to ask, and it is the one that separates a note-quoting answer from a training-prior number.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Before the kenn imports below. A model-backed path opening here would make a "no model in the loop" claim false.
os.environ["KENN_LLM_ENABLED"] = "0"

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

# Below this, a rate is a number that happened. 29 rows is the standing example: acceptance moved 41% to 66% on it and
# the interval still spans roughly plus or minus 17 points, so the move is real and the level is not.
MIN_INTERPRETABLE = 50


def _measurement_keys(text: str) -> set[str]:
    """The production measurement tokenizer, bound once so the harness reads numbers exactly as the gate does.

    Module level rather than a local import so there is a single place to point at when a unit list changes in
    chat_grounding.py, and so a test can assert the harness and the gate agree without reaching past it.
    """
    from kenn.core.chat_grounding import _measurements

    return _measurements(text)


def _load_index():
    from kenn.core.chat_retrieval import load_chunks, load_terms

    return load_chunks(), load_terms()


def _gate_budget_chars() -> int:
    """The evidence budget the gate reads today, which is model_evidence()'s own default.

    KENN_LLM_CONTEXT_CHARS moves the prompt's budget in llm_rewrite and not the gate's, so this deliberately
    reads the default rather than the environment: the question here is what the gate saw, not what the model did.
    """
    from kenn.llm.llm_rewrite import _CONTEXT_BLOCK_CHARS

    return int(_CONTEXT_BLOCK_CHARS)


def _index_version() -> str:
    """The index this checkout points at, to compare against what each captured row recorded.

    Duplicated from measure_chat_latency.py rather than imported: each script is run standalone from the
    repo root and neither should need the other installed.
    """
    pointer = KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT"
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else ""


def _replay_results(query: str, chunks: list[dict], terms: dict) -> list[tuple[float, dict]]:
    """The result list chat_answer would have handed the gate for this question.

    `limit=max(limit, 16)` at chat_answer.py:1197 is the ask path's depth, and `constrain_results_for_query` runs
    after it. Dropping either would put the gate on a different evidence list than production and quietly inflate
    acceptance -- the exact 41%-to-27% trap from 2 Oct.
    """
    from kenn.core.chat_routing import constrain_results_for_query
    from kenn.core.chat_retrieval import search

    return constrain_results_for_query(query, search(query, chunks, terms, limit=max(8, 16)))


def _gate_inputs(query: str, results: list[tuple[float, dict]], timeline_context: str):
    """Route, confidence and answer_mode the way make_answer derives them, so the gate sees the same answer shape.

    confidence_level and classify_answer_mode are the real production helpers, and route_query is the real router.
    The capture does not record these three, so re-deriving them is the only way to replay the gate faithfully.
    """
    from kenn.core.chat_formatting import confidence_level
    from kenn.core.chat_routing import classify_answer_mode, route_query

    route = route_query(query)
    confidence = "high" if timeline_context else confidence_level(query, results)
    return route, confidence, classify_answer_mode(query, route, history=None)


def score_item(row: dict, chunks: list[dict], terms: dict) -> dict:
    """One capture row, re-judged by today's gate."""
    from kenn.core.chat_grounding import generated_answer_validation
    from kenn.core.chat_retrieval import source_label
    from kenn.llm.llm_rewrite import model_evidence

    # _measurement_keys is bound to the production tokenizer in chat_grounding, not copied. A local copy of the
    # pattern would drift from the gate's the first time someone widened the unit list, and the harness would then
    # disagree with production on exactly the numbers it exists to audit.

    query = str(row.get("question") or "")
    answer = str(row.get("answer") or "")
    timeline_context = str(row.get("timeline_context") or "")
    additional = str(row.get("additional_evidence_text") or "")
    captured_evidence = str(row.get("evidence_text") or "")

    results = _replay_results(query, chunks, terms)
    route, confidence, answer_mode = _gate_inputs(query, results, timeline_context)
    validation = generated_answer_validation(
        query,
        results,
        answer,
        route=route,
        confidence=confidence,
        answer_mode=answer_mode,
        timeline_context=timeline_context or None,
        additional_evidence_text=additional or None,
    )

    _block, shown = model_evidence(results, source_label, max_chars=_gate_budget_chars())
    # Recomputed evidence wins over the capture's field, always. The field is the one thing a re-score must not
    # trust -- see the module docstring for the 8-of-18 phantom leak it produced -- and it is read only where
    # replaying is impossible: retrieval returning nothing today means an empty evidence set, which would report
    # every measurement in the answer as invented. The capture's field is a worse description of the gate's
    # evidence than nothing, and a better one than a replay that found nothing.
    if shown:
        evidence_source = "recomputed"
        evidence_text = " ".join(
            " ".join((str(chunk.get("title") or ""), str(chunk.get("source") or ""), body))
            for _score, chunk, body in shown
        )
    elif captured_evidence:
        evidence_source = "captured_field"
        evidence_text = captured_evidence
    else:
        evidence_source = "none"
        evidence_text = ""
    evidence_measurements = _measurement_keys(f"{evidence_text} {timeline_context} {additional}")

    answer_measurements = sorted(_measurement_keys(answer))
    gold_id = str(row.get("gold_chunk_id") or "")
    gold_measurements: set[str] = set()
    gold_found = False
    for _score, chunk, body in shown:
        if str(chunk.get("id") or "") == gold_id:
            gold_measurements = _measurement_keys(body)
            gold_found = True
            break

    # Gold-chunk traceability needs a replayed chunk to compare against. A row with no gold label, and a row that
    # fell back to the captured field because replay found nothing, cannot be gold-checked at all -- and scoring
    # them anyway calls every measurement untraceable, which is the same phantom in a second column.
    gold_chunk_scored = bool(gold_id) and gold_found
    untraceable = [
        m for m in answer_measurements
        if m not in evidence_measurements or m not in gold_measurements
    ] if gold_chunk_scored else []

    recorded = bool(row.get("accepted"))
    return {
        "question": query,
        "stratum": str(row.get("stratum") or ""),
        "gold_chunk_id": gold_id or None,
        "must_abstain": bool(row.get("must_abstain")),
        "route": route,
        "confidence": confidence,
        "answer_mode": answer_mode,
        "recorded_accepted": recorded,
        "accepted": bool(validation["accepted"]),
        "verdict_changed": recorded != bool(validation["accepted"]),
        "warnings": [str(w) for w in validation.get("warnings") or []],
        "unsupported_measurements": list(validation.get("unsupported_measurements") or []),
        "fabricated_sources": list(validation.get("fabricated_sources") or []),
        "evidence_source": evidence_source,
        "evidence_chunks_shown": len(shown),
        "evidence_measurements": sorted(evidence_measurements),
        "recorded_index_version": str(row.get("index_version") or ""),
        "recorded_evidence_budget_chars": row.get("evidence_budget_chars"),
        "recorded_prompt_context_chars": row.get("prompt_context_chars"),
        "answer_measurements": answer_measurements,
        "gold_chunk_scored": gold_chunk_scored,
        "measurements_not_in_gold_chunk": untraceable,
        "numeric_claims_traceable": (not untraceable) if gold_chunk_scored else None,
    }


def _stratum_of(item: dict) -> str:
    """Fall back to a coarse bucket when the capture predates the eval set, so a run is never silently unstratified."""
    if item["stratum"]:
        return item["stratum"]
    if item["must_abstain"]:
        return "must_abstain(unlabelled)"
    return f"{item['route']}(unlabelled)"


def provenance_warnings(items: list[dict], *, current_index: str = "", current_budget: int = 0) -> list[str]:
    """Ways this capture could disagree with today's configuration, named before any rate is printed.

    Every acceptance figure that needed re-measuring on 2 Oct 2026 came from a capture that recorded neither the
    index version nor the evidence budget, so nobody could say whether the replay had read the same evidence the
    model did. A rate whose capture cannot be placed in time is a rate nobody should quote, and that is a warning
    rather than an exit code: the numbers are still worth printing as what they are.
    """
    warnings: list[str] = []
    recorded_budgets = {str(i.get("recorded_evidence_budget_chars")) for i in items} - {"None", ""}
    recorded_indexes = {str(i.get("recorded_index_version") or "") for i in items} - {""}

    if not recorded_budgets and not recorded_indexes:
        return [
            "capture records neither an index version nor an evidence budget, so it predates those fields and "
            "cannot be checked against today's configuration. Every rate below is provisional: if the index was "
            "rebuilt or the budget changed since this capture was taken, the evidence it was taken against is not "
            "the evidence the rows below were re-judged on."
        ]

    if current_budget and recorded_budgets and recorded_budgets != {str(current_budget)}:
        warnings.append(
            f"capture was written at evidence budget {', '.join(sorted(recorded_budgets))} chars; today's gate reads "
            f"{current_budget}. Excerpts are cut to that budget, so a row can hold numbers today would never have "
            f"shown the model. Re-measure before quoting these rates."
        )
    if recorded_indexes:
        if not current_index:
            warnings.append(
                f"capture was taken against index {', '.join(sorted(recorded_indexes))} and this checkout has no "
                f"index at all, so nothing here was replayed against the index those rows saw."
            )
        elif recorded_indexes != {current_index}:
            warnings.append(
                f"capture was taken against index {', '.join(sorted(recorded_indexes))}; this checkout points at "
                f"{current_index}. Retrieval results differ between indexes, so the replay is not reading the "
                f"evidence the answers were written from."
            )

    split = [
        i for i in items
        if i.get("recorded_prompt_context_chars") is not None
        and i.get("recorded_evidence_budget_chars") is not None
        and i["recorded_prompt_context_chars"] != i["recorded_evidence_budget_chars"]
    ]
    if split:
        warnings.append(
            f"{len(split)} row(s) recorded a prompt budget other than the gate's evidence budget, so the model was "
            f"shown less than the gate vouches for on those rows. No re-score of them can be exact."
        )
    return warnings


def _rate(count: int, total: int) -> str:
    return f"{count}/{total} = {count / total:.1%}" if total else "0/0 = n/a"


def report(items: list[dict], *, source: Path, current_index: str = "", current_budget: int = 0) -> dict:
    n = len(items)
    accepted = sum(1 for i in items if i["accepted"])
    changed = [i for i in items if i["verdict_changed"]]
    provenance = provenance_warnings(items, current_index=current_index, current_budget=current_budget)

    print(f"source: {source}")
    print(f"items:  {n}")
    for warning in provenance:
        print(f"\nWARNING: {warning}")
    if n < MIN_INTERPRETABLE:
        print(
            f"\nWARNING: n={n} is below {MIN_INTERPRETABLE}. These rates are not statistically interpretable and must "
            f"not be quoted as an acceptance level. Read them as a smoke test of the harness, not a measurement."
        )
    print(f"\nacceptance: {_rate(accepted, n)}")

    evidence_sources = Counter(i.get("evidence_source", "unknown") for i in items)
    print(f"\nevidence source: {', '.join(f'{k} {v}' for k, v in sorted(evidence_sources.items()))}")
    if evidence_sources.get("captured_field"):
        print(
            f"  WARNING: {evidence_sources['captured_field']} row(s) replayed to no evidence on today's index and "
            f"fell back to the capture's own evidence_text. They are not judged against the gate's current "
            f"evidence and cannot be gold-checked, so count them as unverified rather than as passing."
        )

    # Macro over strata, because 52% of live traffic is one route. Micro (top-1 accuracy) is printed too, but only as
    # the number it is: a figure that hides whatever the dominant stratum is doing to the tail.
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_stratum[_stratum_of(item)].append(item)
    print(f"\nper-stratum (n printed on every rate; {len(by_stratum)} strata)")
    for stratum, rows in sorted(by_stratum.items(), key=lambda kv: -len(kv[1])):
        ok = sum(1 for r in rows if r["accepted"])
        changed_here = sum(1 for r in rows if r["verdict_changed"])
        tail = f", {changed_here} verdict changed" if changed_here else ""
        print(f"  {stratum:34s} {_rate(ok, len(rows))}{tail}")
    macro = sum(
        sum(1 for r in rows if r["accepted"]) / len(rows) for rows in by_stratum.values()
    ) / len(by_stratum) if by_stratum else 0.0
    print(f"  {'macro (unweighted mean of strata)':34s} {macro:.1%}")

    # Rows with no gold label, or no replayed chunk to check the label against, are excluded from the denominator
    # rather than counted as untraceable. Reporting them would turn a missing label into a leak finding.
    # A row with no gold label, or no replayed chunk to check the label against, is excluded from the denominator
    # rather than counted as untraceable: reporting it would turn a missing label into a leak finding. A row from
    # before this field existed reads as unscored rather than as scoreable, because only one of those two answers
    # is safe -- an unknown label must never be able to claim a number was invented.
    unscored = [i for i in items if i["answer_measurements"] and not i.get("gold_chunk_scored")]
    numeric = [i for i in items if i["answer_measurements"] and i.get("gold_chunk_scored")]
    traceable = sum(1 for i in numeric if i["numeric_claims_traceable"])
    print(f"\nnumeric traceability: {_rate(traceable, len(numeric))} of answers carrying any measurement")
    if numeric:
        untraceable_claims = sum(len(i["measurements_not_in_gold_chunk"]) for i in numeric)
        print(f"  {untraceable_claims} measurement(s) absent from the gold chunk, across {len(numeric)} answers")
    if unscored:
        print(
            f"  {len(unscored)} answer(s) carry measurements but carry no gold chunk this run could match, so they "
            f"are excluded from the rate rather than counted as untraceable."
        )

    print("\nwarning distribution (answers may carry more than one)")
    counts = Counter(w for i in items for w in i["warnings"])
    if not counts:
        print("  none")
    for warning, c in counts.most_common():
        print(f"  {c:4d}  ({c / n:.1%} of {n} answers)  {warning}")

    if changed:
        print(f"\nverdict changed since the capture: {len(changed)}/{n}")
        for item in changed[:10]:
            was = "accepted" if item["recorded_accepted"] else "rejected"
            now = "accepted" if item["accepted"] else "rejected"
            reason = item["warnings"][0] if item["warnings"] else "no warning recorded"
            print(f"  {was} -> {now}: {item['question'][:64]!r} ({reason})")
        if len(changed) > 10:
            print(f"  ... and {len(changed) - 10} more")

    must_abstain = [i for i in items if i["must_abstain"]]
    if must_abstain:
        print(f"\nmust-abstain items scored: {len(must_abstain)}")
        print(
            "  NOTE: `accepted` here means the gate cleared the answer as grounded. On a must-abstain item a grounded, "
            "confident answer is the failure being measured, so read these as 'answered anyway', not 'passed'."
        )
        answered = sum(1 for i in must_abstain if i["accepted"])
        print(f"  answered anyway: {_rate(answered, len(must_abstain))}")

    return {
        "items": n,
        "accepted": accepted,
        "acceptance_rate": accepted / n if n else 0.0,
        "macro_acceptance_rate": macro,
        "statistically_interpretable": n >= MIN_INTERPRETABLE,
        "provenance_warnings": provenance,
        "evidence_sources": dict(evidence_sources),
        "verdicts_changed": len(changed),
        "warning_distribution": dict(counts),
        "per_stratum": {
            s: {"n": len(r), "accepted": sum(1 for x in r if x["accepted"])} for s, r in by_stratum.items()
        },
        "numeric_answers": len(numeric),
        "numeric_answers_unscorable": len(unscored),
        "numeric_claims_traceable": traceable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path, help="JSONL from measure_chat_latency.py --capture-answers")
    parser.add_argument("--per-item", type=Path, help="write per-item JSONL here")
    parser.add_argument("--strata", type=Path, action="append", default=[],
                        help="eval set to join stratum labels from; repeatable")
    parser.add_argument("--abstain", type=Path, action="append", default=[],
                        help="adversarial set to join must_abstain from; repeatable")
    parser.add_argument("--receipt", type=Path, help="write the macro summary as JSON")
    args = parser.parse_args()

    if not args.capture.exists():
        print(f"FATAL: {args.capture} does not exist.", file=sys.stderr)
        return 1

    labels: dict[str, dict] = {}
    for path in [*args.strata, *args.abstain]:
        if not path.exists():
            print(f"WARNING: {path} does not exist; its rows stay unlabelled.", file=sys.stderr)
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                labels[str(row.get("query") or "")] = row

    rows = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks, terms = _load_index()
    if not chunks:
        print("FATAL: retrieval index is empty; the gate cannot be replayed without evidence.", file=sys.stderr)
        return 1

    items: list[dict] = []
    for row in rows:
        label = labels.get(str(row.get("question") or ""))
        item = score_item(row, chunks, terms)
        if label:
            item["stratum"] = str(label.get("stratum") or "")
            item["must_abstain"] = bool(label.get("must_abstain"))
            item["gold_chunk_id"] = label.get("gold_chunk_id")
        items.append(item)

    summary = report(
        items,
        source=args.capture,
        current_index=_index_version(),
        current_budget=_gate_budget_chars(),
    )

    if args.per_item:
        args.per_item.parent.mkdir(parents=True, exist_ok=True)
        args.per_item.write_text(
            "".join(json.dumps(i, sort_keys=True) + "\n" for i in items), encoding="utf-8"
        )
        print(f"\nper-item: {args.per_item}")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"receipt:  {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
