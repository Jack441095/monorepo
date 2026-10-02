#!/usr/bin/env python3
"""Prepare frozen answer captures for review, then score independent claim labels.

No model, retrieval, or production gate runs here. Unreviewed answers stay out of
metric denominators and remain visible in the coverage counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

SCHEMA = "kenn.citation_labels.v1"
# Keep the wire syntax shared with llm_rewrite, without importing its model runtime.
CITATION = re.compile(r"\[\s*#\s*([^\]\s]{1,32})\s*\]")


def fingerprint(capture: dict) -> str:
    encoded = json.dumps(capture, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def unavailable_reason(capture: dict) -> str:
    if capture.get("candidate_text_available") is not True:
        return "candidate text not recorded"
    if not isinstance(capture.get("answer"), str) or not capture["answer"].strip():
        return "empty candidate"
    if not isinstance(capture.get("evidence_sources"), list):
        return "per-source evidence not recorded"
    if not isinstance(capture.get("question"), str) or not capture["question"].strip():
        return "question not recorded"
    ids = set()
    for source in capture["evidence_sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]:
            return "invalid source id"
        if source["id"] in ids:
            return "duplicate source id"
        ids.add(source["id"])
        if not isinstance(source.get("text"), str) or not source["text"].strip():
            return "empty source excerpt"
    return ""


def prepare_rows(captures: list[dict]) -> list[dict]:
    rows = []
    seen = set()
    for capture in captures:
        digest = fingerprint(capture)
        if digest in seen:
            raise ValueError("duplicate capture; repeated rows cannot increase sample size")
        seen.add(digest)
        # Partition by question so repeated generations cannot leak across calibration and test.
        question_key = " ".join(str(capture.get("question") or "").casefold().split())
        bucket = int(hashlib.sha256(question_key.encode("utf-8")).hexdigest()[:8], 16) % 5
        rows.append({
            "schema": SCHEMA, "id": digest, "split": "test" if bucket == 0 else "calibration",
            "capture": capture, "unavailable_reason": unavailable_reason(capture),
            "review": {"complete": False, "reviewer": "", "origin": "",
                       "answer_acceptable": None},
            "claims": [],
        })
    return rows


def _boolean(record: dict, key: str) -> bool:
    value = record.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def validate_review(row: dict) -> dict:
    capture, review = row["capture"], row["review"]
    if unavailable_reason(capture):
        raise ValueError("an unavailable candidate cannot be reviewed")
    if review.get("origin") not in {"human", "model"} or not str(review.get("reviewer") or "").strip():
        raise ValueError("review requires a named reviewer and human/model origin")
    acceptable = _boolean(review, "answer_acceptable")
    answer = capture["answer"]
    sources = {s["id"] for s in capture["evidence_sources"]}
    claims = row.get("claims")
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    counts = Counter()
    consumed = []
    previous_end = 0
    for claim in claims:
        start, end = claim.get("start"), claim.get("end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(answer):
            raise ValueError("claim offsets must select a nonempty answer span")
        if start < previous_end or not answer[start:end].strip():
            raise ValueError("claims must be ordered, nonoverlapping, and nonempty")
        previous_end = end
        factual = _boolean(claim, "factual")
        shown = _boolean(claim, "shown_support")
        cited = _boolean(claim, "cited_support")
        mentions = list(CITATION.finditer(answer, start, end))
        labels = claim.get("citations")
        if not isinstance(labels, list) or [c.get("id") for c in labels] != [m.group(1) for m in mentions]:
            raise ValueError("citation labels must match every mention in the claim, in order")
        useful = 0
        for mention, label in zip(mentions, labels):
            supports = _boolean(label, "supports")
            if supports and (label["id"] not in sources or not cited):
                raise ValueError("a useful citation needs a shown source and a jointly supported claim")
            useful += supports
            consumed.append(mention.span())
        if cited and (not factual or not shown or not useful):
            raise ValueError("cited support needs a factual, shown-supported claim and a useful citation")
        if shown and not factual:
            raise ValueError("nonfactual spans cannot have support labels")
        counts["factual_claims"] += factual
        counts["shown_supported_claims"] += factual and shown
        counts["cited_supported_claims"] += factual and cited
        counts["citation_mentions"] += len(mentions)
        counts["useful_citations"] += useful
        counts["unknown_citations"] += sum(m.group(1) not in sources for m in mentions)
    if consumed != [m.span() for m in CITATION.finditer(answer)]:
        raise ValueError("every citation in the answer must belong to a labelled claim")
    return {"counts": counts, "acceptable": acceptable,
            "unsupported": counts["shown_supported_claims"] < counts["factual_claims"]}


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson(numerator: int, denominator: int) -> list[float] | None:
    if not denominator:
        return None
    z = 1.959963984540054
    p = numerator / denominator
    scale = 1 + z * z / denominator
    centre = (p + z * z / (2 * denominator)) / scale
    half = z * ((p * (1 - p) / denominator + z * z / (4 * denominator**2)) ** 0.5) / scale
    return [max(0.0, centre - half), min(1.0, centre + half)]


def score_rows(rows: list[dict]) -> dict:
    counts = Counter(total=len(rows))
    origins, splits, unavailable = Counter(), Counter(), Counter()
    reviewed_queries = set()
    seen = set()
    for row in rows:
        if row.get("schema") != SCHEMA or not isinstance(row.get("capture"), dict):
            raise ValueError("wrong label schema or missing capture")
        digest = fingerprint(row["capture"])
        if row.get("id") != digest:
            raise ValueError("capture changed after preparation; prepare a new review")
        if digest in seen:
            raise ValueError("duplicate review row")
        seen.add(digest)
        expected = prepare_rows([row["capture"]])[0]
        if row.get("split") != expected["split"] or row.get("unavailable_reason") != expected["unavailable_reason"]:
            raise ValueError("capture availability or question split changed")
        review = row.get("review")
        if not isinstance(review, dict):
            raise ValueError("missing review")
        complete = _boolean(review, "complete")
        if row["unavailable_reason"]:
            if complete:
                raise ValueError("unavailable row marked complete")
            counts["unavailable"] += 1
            unavailable[row["unavailable_reason"]] += 1
            continue
        if not complete:
            counts["pending"] += 1
            continue
        result = validate_review(row)
        counts.update(result["counts"])
        counts["reviewed"] += 1
        counts["acceptable_answers"] += result["acceptable"]
        counts["unsupported_answers"] += result["unsupported"]
        accepted = _boolean(row["capture"], "accepted")
        counts["gate_accepted_reviewed"] += accepted
        counts["gate_accepted_unsupported"] += accepted and result["unsupported"]
        origins[review["origin"]] += 1
        splits[row["split"]] += 1
        reviewed_queries.add(" ".join(row["capture"]["question"].casefold().split()))
    counts["unique_reviewed_questions"] = len(reviewed_queries)
    keys = ("total", "reviewed", "pending", "unavailable", "unique_reviewed_questions",
            "acceptable_answers", "unsupported_answers", "gate_accepted_reviewed",
            "gate_accepted_unsupported", "factual_claims", "shown_supported_claims",
            "cited_supported_claims", "citation_mentions", "useful_citations", "unknown_citations")
    independent_rows = counts["reviewed"] == len(reviewed_queries)
    return {
        "schema": "kenn.citation_scores.v1",
        "counts": {key: counts[key] for key in keys},
        "review_origins": dict(origins), "reviewed_splits": dict(splits),
        "unavailable_reasons": dict(unavailable),
        "metrics": {
            "citation_precision": ratio(counts["useful_citations"], counts["citation_mentions"]),
            "citation_recall": ratio(counts["cited_supported_claims"], counts["factual_claims"]),
            "faithfulness": ratio(counts["shown_supported_claims"], counts["factual_claims"]),
            "answer_acceptability": ratio(counts["acceptable_answers"], counts["reviewed"]),
            "accepted_unsupported_risk": ratio(counts["gate_accepted_unsupported"], counts["gate_accepted_reviewed"]),
        },
        # Claims within an answer are correlated; intervals use answers, and repeated questions
        # disable them rather than pretending each generation is an independent observation.
        "answer_acceptability_wilson95": wilson(counts["acceptable_answers"], counts["reviewed"]) if independent_rows else None,
        "accepted_unsupported_wilson95": wilson(counts["gate_accepted_unsupported"], counts["gate_accepted_reviewed"]) if independent_rows else None,
        "minimum_sample_met": len(reviewed_queries) >= 150,
        "coverage_complete": counts["pending"] == counts["unavailable"] == 0 and bool(rows),
        "labels_are_human_only": bool(origins) and set(origins) == {"human"},
    }


def read_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("input must contain JSON objects, one per line")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("prepare", "score"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = read_rows(args.input)
        if args.action == "prepare":
            result = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepare_rows(rows))
        else:
            result = json.dumps(score_rows(rows), indent=2) + "\n"
        # Refuse accidental overwrites: labels contain review work that cannot be regenerated.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(result)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"citation-eval: {exc}", file=sys.stderr)
        return 1
    print(f"{args.action}: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
