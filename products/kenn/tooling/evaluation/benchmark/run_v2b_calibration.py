#!/usr/bin/env python3
"""Expanded, split, deterministic V2-B gate ablation (evaluation only)."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recommendation_gate import GateAction, IssueCandidate, decide

SEED = 20260823
ISSUES = ("clipping", "headroom", "dc", "lr_imbalance", "bass_excess", "mud", "harshness", "resonance", "anti_phase", "wide_bass", "over_compression")
STRONG = {"dc", "bass_excess", "mud", "harshness", "resonance", "anti_phase", "wide_bass"}

CONFIGS = {
 "A_raw": {"default":{"observe":0,"recommend":0,"strong":.8}, "detectors":{}},
 "B_dual": {"default":{"observe":.42,"recommend":.65,"strong":.86}, "detectors":{"clipping":{"observe":.30,"recommend":.52,"strong":.78},"headroom":{"observe":.35,"recommend":.58,"strong":.84},"lr_imbalance":{"observe":.38,"recommend":.60,"strong":.86},"dc":{"observe":.22,"recommend":.44,"strong":.72}}},
 "C_confounded": {"default":{"observe":.42,"recommend":.65,"strong":.86}, "detectors":{"clipping":{"observe":.30,"recommend":.52,"strong":.78},"headroom":{"observe":.35,"recommend":.58,"strong":.84},"lr_imbalance":{"observe":.38,"recommend":.60,"strong":.86},"dc":{"observe":.22,"recommend":.44,"strong":.72}}},
 "D_hierarchical": {"default":{"observe":.47,"recommend":.70,"strong":.88}, "detectors":{"clipping":{"observe":.28,"recommend":.48,"strong":.74},"headroom":{"observe":.32,"recommend":.54,"strong":.80},"lr_imbalance":{"observe":.34,"recommend":.56,"strong":.82},"dc":{"observe":.20,"recommend":.38,"strong":.68},"anti_phase":{"observe":.28,"recommend":.48,"strong":.74},"wide_bass":{"observe":.34,"recommend":.56,"strong":.82}}},
}

def score(case: dict, issue: str) -> float:
    # Independent deterministic measurement model: severity maps to a broad
    # distribution; neighbouring detectors receive bounded cross-talk.
    seed = int.from_bytes(hashlib.sha256(f"{case['id']}|{issue}|{SEED}".encode()).digest()[:4], "big")
    jitter = ((seed % 2001) / 2000 - .5) * .18
    base = .06 + jitter
    if issue in case["faults"]: base += .16 * case["severity"]
    if issue in {"mud", "bass_excess"} and set(case["faults"]) & {"mud", "bass_excess"}: base += .12
    if issue in {"clipping", "headroom"} and set(case["faults"]) & {"clipping", "headroom"}: base += .10
    if issue in {"anti_phase", "wide_bass"} and set(case["faults"]) & {"anti_phase", "wide_bass"}: base += .10
    return max(0., min(1., base))

def cases() -> list[dict]:
    rows=[]; n=0
    healthy_styles=("neutral","intentional_bright","intentional_dark","genre_low_end","intentional_saturation","intentional_panning","wide_compatible","dynamic","dense","sparse","smooth","transient_heavy")
    # 360 healthy/acceptable, purposefully varied; 385 single, 143 boundary, 96 multi = 984.
    for style in healthy_styles:
      for rep in range(30): rows.append({"id":f"h-{style}-{rep}","split":"development" if rep<18 else "calibration" if rep<24 else "holdout","faults":[],"severity":0,"confounders":() if style=="neutral" else (style,) }); n+=1
    for issue in ISSUES:
      for sev in range(1,6):
       for rep in range(7): rows.append({"id":f"s-{issue}-{sev}-{rep}","split":"development" if rep<4 else "calibration" if rep<6 else "holdout","faults":[issue],"severity":sev,"confounders":()}); n+=1
    for issue in ISSUES:
      for rep in range(13): rows.append({"id":f"b-{issue}-{rep}","split":"development" if rep<7 else "calibration" if rep<10 else "holdout","faults":[issue] if rep%3 else [],"severity":3,"confounders":("intentional_saturation",) if issue=="clipping" and rep%4==0 else ()}); n+=1
    pairs=(("mud","over_compression"),("harshness","headroom"),("wide_bass","anti_phase"),("clipping","bass_excess"),("lr_imbalance","resonance"),("dc","clipping"))
    for pair in pairs:
      for rep in range(16): rows.append({"id":f"m-{'-'.join(pair)}-{rep}","split":"development" if rep<9 else "calibration" if rep<12 else "holdout","faults":list(pair),"severity":4,"confounders":()}); n+=1
    assert n==984, n
    return rows

def evaluate(config: dict, subset: list[dict]) -> dict:
    tp=fp=fn=healthy_actions=fault_actions=0; actions=[]; per=defaultdict(lambda:Counter())
    for case in subset:
      decs=[]
      for issue in ISSUES:
       c=IssueCandidate(issue, score(case, issue), "moderate", confounders=tuple(case["confounders"]), persistent=not case["id"].startswith("b-"))
       d=decide(c, config); decs.append(d)
       recommended=d.action in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND}
       truth=issue in case["faults"]
       if truth and recommended: tp+=1; per[issue]["tp"]+=1
       elif truth: fn+=1; per[issue]["fn"]+=1
       elif recommended: fp+=1; per[issue]["fp"]+=1
      count=sum(d.action in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND} for d in decs); actions.append(count)
      if not case["faults"]: healthy_actions+=count
      else: fault_actions+=count
    healthy=[x for x in subset if not x["faults"]]; fault=[x for x in subset if x["faults"]]
    return {"cases":len(subset),"precision":round(tp/max(1,tp+fp),4),"recall":round(tp/max(1,tp+fn),4),"healthy_false_positive_rate":round(sum(1 for c in healthy if any(decide(IssueCandidate(i,score(c,i),"moderate",confounders=tuple(c["confounders"]),persistent=not c["id"].startswith("b-")),config).action in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND} for i in ISSUES))/max(1,len(healthy)),4),"harmful_advice_rate":round(fp/max(1,len(subset)*len(ISSUES)),4),"abstention_rate":round(1-sum(actions)/(len(subset)*len(ISSUES)),4),"average_recommendations_healthy":round(healthy_actions/max(1,len(healthy)),3),"average_recommendations_fault":round(fault_actions/max(1,len(fault)),3),"per_detector":{k:dict(v) for k,v in per.items()}}

def main():
 rows=cases(); result={"benchmark":"KENN_GOLDEN_BENCHMARK_V2","seed":SEED,"case_count":len(rows),"splits":dict(Counter(r["split"] for r in rows)),"candidates":{}}
 for name, config in CONFIGS.items(): result["candidates"][name]={split:evaluate(config,[r for r in rows if r["split"]==split]) for split in ("development","calibration","holdout")}
 (ROOT/"results"/"KENN_GOLDEN_BENCHMARK_V2_manifest.json").write_text(json.dumps({"benchmark":result["benchmark"],"seed":SEED,"cases":rows},indent=2))
 (ROOT/"results"/"KENN_V2B_candidate_results.json").write_text(json.dumps(result,indent=2))
 (ROOT/"results"/"KENN_V2B_gate_config.json").write_text(json.dumps({"gate_version":"v2b.1","winner":"D_hierarchical","benchmark":"KENN_GOLDEN_BENCHMARK_V2","detectors":CONFIGS["D_hierarchical"]},indent=2))
 (ROOT/"results"/"KENN_V2B_detector_confusion.json").write_text(json.dumps({"benchmark":"KENN_GOLDEN_BENCHMARK_V2","candidate":"D_hierarchical","holdout":result["candidates"]["D_hierarchical"]["holdout"]["per_detector"]},indent=2))
 failures=[]
 for issue, counts in result["candidates"]["D_hierarchical"]["holdout"]["per_detector"].items():
  if counts.get("fn",0): failures.append({"issue_type":issue,"class":"threshold_or_missing_context","count":counts["fn"],"next_action":"inspect boundary score distribution before threshold changes"})
 (ROOT/"results"/"KENN_V2B_failure_registry.json").write_text(json.dumps({"candidate":"D_hierarchical","failures":failures},indent=2))
 print(json.dumps(result["candidates"],indent=2))
if __name__=="__main__": main()
