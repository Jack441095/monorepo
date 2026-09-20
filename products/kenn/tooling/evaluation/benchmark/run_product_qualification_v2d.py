#!/usr/bin/env python3
"""Read-only V2-D product decoder parity and realistic synthetic qualification."""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
from run_audio_holdout_v2c import cases, audio, wav_roundtrip, v2c_decide
from product_adapter_v2d import product_candidates
from recommendation_gate import GateAction

ROOT=Path(__file__).resolve().parents[1]
def scope(c): return 'mix_in_progress' if c['group']=='headroom' else 'master' if c.get('confounder')=='mastered' else 'unknown'
def decision(cand, case): return v2c_decide(cand,case['faults'],(case.get('confounder') or '',))
def run(rows):
    parity=[]; failures=[]; lats=[]; tp=fp=fn=0; healthy=healthy_bad=0; recs=[]
    for c in rows:
      raw,reference,sr=wav_roundtrip(audio(c),c['sr']); started=time.perf_counter(); product,meta=product_candidates(raw,scope=scope(c));lats.append(time.perf_counter()-started)
      ref=[x for x in (__import__('measured_candidates_v2c').clipping_candidate(reference,scope(c)),__import__('measured_candidates_v2c').headroom_candidate(reference,scope(c)),__import__('measured_candidates_v2c').lr_imbalance_candidate(reference,sr,scope(c)))]
      exact=all(a.payload()==b.payload() for a,b in zip(ref,product)); parity.append({'case_id':c['id'],'decoder':meta['decoder'],'exact':exact})
      picked=[]
      for cand in product:
       state,act=decision(cand,c); predicted=act in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND}; truth=cand.issue_type in c['faults'];picked.append((cand.issue_type,act.value))
       if truth and predicted:tp+=1
       elif truth:fn+=1;failures.append({'case_id':c['id'],'issue':cand.issue_type,'expected':'recommend','actual':act.value,'measurement':cand.payload(),'root_cause':'boundary_or_scope'})
       elif predicted:fp+=1;failures.append({'case_id':c['id'],'issue':cand.issue_type,'expected':'abstain_or_observe','actual':act.value,'measurement':cand.payload(),'root_cause':'false_positive'})
      # clipping subsumes lower-priority headroom in presentation.
      if any(i=='clipping' and a in ('recommend','strong_recommend') for i,a in picked):picked=[p for p in picked if p[0]!='headroom']
      recs.append(len([1 for _,a in picked if a in ('recommend','strong_recommend')]))
      if not c['faults']: healthy+=1;healthy_bad+=any(a in ('recommend','strong_recommend') for _,a in picked)
    return {'cases':len(rows),'parity_rate':sum(x['exact'] for x in parity)/len(parity),'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn),'healthy_fp':healthy_bad/max(1,healthy),'abstention':1-sum(recs)/(len(rows)*3),'average_recommendations':sum(recs)/len(recs),'p50_s':float(np.percentile(lats,50)),'p95_s':float(np.percentile(lats,95)),'parity':parity,'failures':failures}
def realistic_rows():
    base=cases();out=[]; styles=('bright','dark','bass_heavy','dynamic','dense','wide','narrow','ambient','drum_heavy','asymmetric_arrangement')
    # Select varied healthy controls plus every fifth target/multi case; audio
    # remains deterministic and uses the same product decode boundary.
    for c in base:
      if c['group'].startswith('healthy') or c['group'] in ('lr_alternating','multi_clip_bass','multi_lr_phase') or c['n']%5==0:
       d=dict(c);d['id']='realistic-'+c['id'];d['style']=styles[c['n']%len(styles)];out.append(d)
    return out
def main():
    all_rows=cases(); holdout=[c for c in all_rows if c['split']=='holdout']; real=realistic_rows(); results={'analysis_version':'kenn.measured_candidates.v2c.1','feature_flag':'KENN_MEASURED_GATE_V2C','feature_flag_default':'off','product_holdout':run(holdout),'realistic_synthetic':run(real)}
    (ROOT/'results/KENN_V2D_product_results.json').write_text(json.dumps(results,indent=2));(ROOT/'results/KENN_V2D_parity_results.json').write_text(json.dumps({'product_holdout':results['product_holdout']['parity'],'realistic':results['realistic_synthetic']['parity']},indent=2));(ROOT/'results/KENN_V2D_failure_registry.json').write_text(json.dumps({'product_holdout':results['product_holdout']['failures'],'realistic':results['realistic_synthetic']['failures']},indent=2));(ROOT/'results/KENN_V2D_analysis_manifest.json').write_text(json.dumps({'v2c_holdout_cases':len(holdout),'realistic_cases':len(real),'product_decoder':'audio_analysis.utils.audio_io_api.decode_audio_bytes','analysis_version':results['analysis_version'],'feature_flag':results['feature_flag'],'default':'off'},indent=2));print(json.dumps({k:{x:v for x,v in value.items() if x not in ('parity','failures')} for k,value in results.items() if isinstance(value,dict)},indent=2))
if __name__=='__main__':main()
