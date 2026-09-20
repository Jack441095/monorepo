"""Qualification scoring — frozen definitions (sprint §26-§35, §43).

Definitions fixed BEFORE any real-audio contact:

USEFUL   : blind vote decodes to the version containing SUGGESTED with
           margin >= 'slightly better' (choices 2/4 count as slight).
NEUTRAL  : 'Equivalent' or 'Cannot judge'.
HARMFUL  : SUGGESTED judged meaningfully worse (margin >= 'slightly worse').

HEALTHY FALSE POSITIVE : engine gives ALIGN/BANDWISE_WARNING on a case
whose ground-truth expectation is NO_ACTION. ABSTAIN/NO_ACTION on
actionable ground truth is NOT a false positive (it is lost coverage).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


CHOICE_DECODE = {1: "A", 2: "A_slight", 3: "EQUIV", 6: "CANNOT_JUDGE",
                 4: "B_slight", 5: "B"}
MARGIN = {"A": +2, "A_slight": +1, "EQUIV": 0, "CANNOT_JUDGE": 0,
          "B_slight": -1, "B": -2}


def decode_vote(vote: dict, entry: dict) -> dict:
    """vote choice -> which decoded side won, given pack slot assignment."""
    pick = CHOICE_DECODE.get(int(vote.get("choice", 0)), "SKIP")
    if pick == "SKIP":
        return {"verdict": "SKIPPED"}
    margin = MARGIN[pick]              # positive => A preferred
    winner = ("A" if margin > 0 else "B" if margin < 0 else "TIE")
    suggested_slot = None
    if margin != 0:
        suggested_slot = ("A" if entry["slot_a"] == "SUGGESTED" else "B") \
            if winner in ("A", "B") else None
        if suggested_slot and winner != suggested_slot:
            margin = -margin           # preference was for ORIGINAL
    if margin > 0:
        verdict = "SUGGESTED_BETTER"
    elif margin < 0:
        verdict = "ORIGINAL_BETTER"
    else:
        verdict = pick                  # EQUIV / CANNOT_JUDGE
    return {"verdict": verdict,
            "suggested_won": margin > 0,
            "original_won": margin < 0,
            "strength": abs(margin)}


def score(records: list[dict], votes: list[dict],
          pack_entries: list[dict]) -> dict:
    by_id = {e["case_id"]: e for e in pack_entries}
    per_case = []
    for v in votes:
        cid = v["case_id"].replace("|REPEAT", "")
        e = by_id.get(cid)
        if not e or int(v.get("choice", 0)) == 0:
            continue
        d = decode_vote(v, e)
        per_case.append({"case_id": cid,
                         "repeat": v["case_id"] != cid,
                         "choice": int(v["choice"]),
                         **d})
    actionable = [r for r in records
                  if r["product_output"]["action"] == "ALIGN"]
    n_votes = len([p for p in per_case if not p["repeat"]])
    sug_better = [p for p in per_case if p["verdict"] == "SUGGESTED_BETTER"]
    orig_better = [p for p in per_case if p["verdict"] == "ORIGINAL_BETTER"]
    neutral = [p for p in per_case
               if p["verdict"] in ("EQUIV", "CANNOT_JUDGE")]

    def rate(xs):
        return round(len(xs) / n_votes, 4) if n_votes else None

    useful_rate = rate(sug_better)
    harmful_rate = rate(orig_better)
    neutral_rate = rate(neutral)

    # self-consistency on repeats
    rep_pairs = defaultdict(list)
    for p in per_case:
        rep_pairs[p["case_id"]].append(p["verdict"])
    consistent, total_rep = 0, 0
    for cid, vs in rep_pairs.items():
        if len(vs) >= 2:
            total_rep += 1
            same_sign = all((v in ("SUGGESTED_BETTER")) ==
                            (vs[0] == "SUGGESTED_BETTER")
                            for v in vs) or \
                all(v in ("EQUIV", "CANNOT_JUDGE") for v in vs)
            consistent += int(same_sign)

    # ---- classification-side metrics over ALL records ------------------
    healthy = [r for r in records
               if r["meta"]["expected_action"] == "NO_ACTION"]
    fp = [r for r in healthy
          if r["product_output"]["action"] in ("ALIGN", "BANDWISE_WARNING")]
    fpr = round(len(fp) / len(healthy), 4) if healthy else None

    abstain = [r for r in records
               if r["product_output"]["action"] in
               ("NO_ACTION", "ABSTAIN")]
    actionable_truth = [r for r in records
                        if r["meta"]["expected_action"] == "ACTION_KNOWN"]
    missed = [r for r in actionable_truth
              if r["product_output"]["action"] in
              ("NO_ACTION", "ABSTAIN")]

    cov = (round(len(actionable) /
                 max(1, sum(1 for r in records
                            if r["meta"]["class"] == "NATURAL")), 4))

    reasons = Counter()
    for r in abstain:
        rs = (r["recommendation"].get("reason") or "").lower()
        keys = ("tonal", "ambiguous", "decorrelated", "little spectrum",
                "low-band", "frequency-dependent",
                "already aligned", "improves objective")
        key = next((t for t in keys if t in rs), "other")
        reasons[key] += 1

    # confidence calibration buckets (usefulness among voted actionable)
    buckets = defaultdict(lambda: {"n": 0, "useful": 0, "harmful": 0})
    vote_by_cid = defaultdict(list)
    for p in per_case:
        vote_by_cid[p["case_id"]].append(p["verdict"])
    for r in actionable:
        c = float(r["product_output"].get("confidence", 0))
        b = min(int(c * 10), 9) / 10.0
        key = f"{b:.1f}-{b+0.1:.1f}"
        vs = vote_by_cid.get(r["meta"]["case_id"])
        if not vs:
            continue
        buckets[key]["n"] += 1
        if any(v == "SUGGESTED_BETTER" for v in vs):
            buckets[key]["useful"] += 1
        if any(v == "ORIGINAL_BETTER" for v in vs):
            buckets[key]["harmful"] += 1

    return {
        "blind_review": {
            "votes_total": len(per_case),
            "unique_cases_voted": len({p["case_id"] for p in per_case}),
            "useful_rate": useful_rate,
            "neutral_rate": neutral_rate,
            "harmful_rate": harmful_rate,
            "repeat_self_consistency":
                round(consistent / total_rep, 3) if total_rep else None,
        },
        "classification": {
            "healthy_false_positive_rate": fpr,
            "healthy_fp_cases": [{"id": r["meta"]["case_id"],
                                  "action": r["product_output"]["action"]}
                                 for r in fp][:20],
            "abstention_rate_overall": round(
                len(abstain) / max(1, len(records)), 4),
            "missed_actionable": len(missed),
            "actionable_coverage_natural": cov,
            "abstention_reason_counts": dict(reasons),
        },
        "confidence_calibration": {k: v for k, v in sorted(buckets.items())},
    }


if __name__ == "__main__":
    rec_p, votes_p, pack_p = map(Path, sys.argv[1:4])
    records = json.loads(rec_p.read_text())
    votes = json.loads(votes_p.read_text())
    pack = json.loads(pack_p.read_text())["entries"]
    print(json.dumps(score(records, votes, pack), indent=1))
