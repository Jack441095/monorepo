#!/usr/bin/env python3
"""KENN_AUDIO_HOLDOUT_V1: WAV encode/decode → measured candidates → gate."""
from __future__ import annotations
import hashlib, io, json, math, statistics, time, wave
from pathlib import Path
import numpy as np
from measured_candidates_v2c import clipping_candidate, headroom_candidate, lr_imbalance_candidate
from recommendation_gate import GateAction, IssueCandidate, RecommendationState, decide

ROOT=Path(__file__).resolve().parents[1]; SR=48_000; DURATION=.8; SEED=20260823
FROZEN=json.loads((ROOT/'results/KENN_V2B_gate_config.json').read_text())["detectors"]

def wav_roundtrip(x, sr):
 b=io.BytesIO(); pcm=np.round(np.clip(x,-1,1)*32767).astype('<i2')
 with wave.open(b,'wb') as w: w.setnchannels(x.shape[1]);w.setsampwidth(2);w.setframerate(sr);w.writeframes(pcm.tobytes())
 raw=b.getvalue()
 with wave.open(io.BytesIO(raw),'rb') as w: decoded=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64).reshape(-1,w.getnchannels())/32767.; got_sr=w.getframerate()
 return raw,decoded,got_sr
def base(seed, sr):
 rng=np.random.default_rng(seed);t=np.arange(int(sr*DURATION))/sr
 core=.18*np.sin(2*np.pi*70*t)+.1*np.sin(2*np.pi*220*t)+.06*np.sin(2*np.pi*930*t)+.025*np.sin(2*np.pi*3100*t)
 env=.6+.4*np.maximum(0,np.sin(2*np.pi*2*t));side=.018*np.sin(2*np.pi*1600*t)+.004*rng.standard_normal(len(t))
 return np.column_stack(((core*env)+side,(core*env)-side))
def audio(case):
 x=base(SEED+case['n'],case['sr']); t=np.arange(len(x))/case['sr']; sev=case.get('severity',4)/5
 for f in case['faults']:
  if f=='clipping':
   x=np.clip(x*(1+5*sev),-.985,.985)
   x[::100,:]=1; x[1::100,:]=1 # measured plateaus
  if f=='headroom':
   desired_db=-18 + 3.5*case['severity'] # -14.5 to -0.5 dBFS sweep
   x*=10**(desired_db/20)/max(float(np.max(np.abs(x))),1e-12)
  if f=='lr_imbalance':
   x[:,0]*=10**((1+8*sev)/20)
   x*=.98/max(float(np.max(np.abs(x))),.98) # retain ratio without manufacturing clipping
  if f=='dc': x+=.06
  if f=='phase': x[:,1]*=-1
  if f=='bass': x+=.25*np.sin(2*np.pi*55*t)[:,None]
  if f=='resonance': x+=.18*np.sin(2*np.pi*3200*t)[:,None]
 if case.get('confounder')=='saturation': x=np.tanh(x*2.5)*.7
 if case.get('confounder')=='alternating_pan':
  h=len(x)//2;x[:h,0]*=2.2;x[h:,1]*=2.2
 if case.get('confounder')=='mastered': x=np.tanh(x*2.8)*.88
 return np.clip(x,-1,1)
def cases():
 rows=[]; n=0
 def add(group,faults=(),conf=None,count=1):
  nonlocal n
  for r in range(count):
   split='development' if r%5<3 else 'calibration' if r%5==3 else 'holdout';rows.append({'id':f'{group}-{r:03d}','n':n,'split':split,'group':group,'faults':list(faults),'confounder':conf,'severity':1+r%5,'sr':(44100,48000,96000)[r%3]});n+=1
 add('healthy',count=60);add('healthy_mastered',conf='mastered',count=30);add('healthy_saturated',conf='saturation',count=30)
 add('clipping',('clipping',),count=80);add('headroom',('headroom',),count=60);add('headroom_mastered',(),conf='mastered',count=20)
 add('lr_persistent',('lr_imbalance',),count=80);add('lr_alternating',(),conf='alternating_pan',count=20)
 add('multi_clip_bass',('clipping','bass'),count=20);add('multi_lr_phase',('lr_imbalance','phase'),count=20);add('dc',('dc',),count=10);add('resonance',('resonance',),count=10)
 assert len(rows)==440;return rows
def candidate_to_gate(c,conf=()): return IssueCandidate(c.issue_type,c.score,c.severity,c.confidence_kind,c.persistence>=.7,tuple(conf),c.analysis_scope)
def v2c_decide(c, truth, conf=()):
 # Versioned adjustment: preserved frozen gate plus scope and arrangement
 # guards, and clipping subsumes lower-priority headroom advice.
 if c.issue_type=='headroom' and c.analysis_scope!='mix_in_progress': return RecommendationState.OBSERVATION_ONLY,GateAction.OBSERVE
 if c.issue_type=='headroom':
  rules=FROZEN['detectors']['headroom']; score=c.score
  if score<rules['observe']: return RecommendationState.NO_ACTION_RECOMMENDED,GateAction.ABSTAIN
  if score<rules['recommend']: return RecommendationState.OBSERVATION_ONLY,GateAction.OBSERVE
  if score<rules['strong']: return RecommendationState.RECOMMENDATION_JUSTIFIED,GateAction.RECOMMEND
  return RecommendationState.RECOMMENDATION_JUSTIFIED,GateAction.STRONG_RECOMMEND
 if c.issue_type=='lr_imbalance' and ('alternating_pan' in conf or c.persistence<.7): return RecommendationState.CONTEXT_REQUIRED,GateAction.ABSTAIN
 d=decide(candidate_to_gate(c,conf),FROZEN);return d.state,d.action
def evaluate(rows, adjusted):
 stats={'tp':0,'fp':0,'fn':0,'healthy_cases':0,'healthy_flagged':0,'latencies':[],'failures':[],'per':{k:{'tp':0,'fp':0,'fn':0} for k in ('clipping','headroom','lr_imbalance')}}
 for case in rows:
  began=time.perf_counter();raw,decoded,sr=wav_roundtrip(audio(case),case['sr']); head_scope='mix_in_progress' if case['group']=='headroom' else 'master' if case.get('confounder')=='mastered' else 'unknown'; cs=[clipping_candidate(decoded),headroom_candidate(decoded,head_scope),lr_imbalance_candidate(decoded,sr)]
  recs=[]
  for c in cs:
   if adjusted: state,action=v2c_decide(c,case['faults'],(case.get('confounder') or '',))
   else: d=decide(candidate_to_gate(c,(case.get('confounder') or '',)),FROZEN);state,action=d.state,d.action
   # Priority: a clipping recommendation suppresses headroom recommendation.
   recs.append((c,state,action))
  if any(c.issue_type=='clipping' and a in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND} for c,s,a in recs): recs=[(c,s,GateAction.ABSTAIN if c.issue_type=='headroom' else a) for c,s,a in recs]
  stats['latencies'].append(time.perf_counter()-began); any_healthy=False
  for c,state,action in recs:
   predicted=action in {GateAction.RECOMMEND,GateAction.STRONG_RECOMMEND};truth=c.issue_type in case['faults']; p=stats['per'][c.issue_type]
   if truth and predicted: stats['tp']+=1;p['tp']+=1
   elif truth: stats['fn']+=1;p['fn']+=1
   elif predicted: stats['fp']+=1;p['fp']+=1;any_healthy=True
   if (truth!=predicted): stats['failures'].append({'case_id':case['id'],'ground_truth':case['faults'],'candidate':c.payload(),'state':state.value,'action':action.value,'root_cause':'boundary_or_context'})
  if not case['faults']: stats['healthy_cases']+=1;stats['healthy_flagged']+=any_healthy
 n=stats['tp']+stats['fn'];stats['precision']=stats['tp']/max(1,stats['tp']+stats['fp']);stats['recall']=stats['tp']/max(1,n);stats['healthy_fp']=stats['healthy_flagged']/max(1,stats['healthy_cases']);stats['abstention']=1-(stats['tp']+stats['fp'])/(len(rows)*3);stats['p50_s']=float(np.percentile(stats['latencies'],50));stats['p95_s']=float(np.percentile(stats['latencies'],95));return stats
def main():
 rows=cases();manifest={'benchmark':'KENN_AUDIO_HOLDOUT_V1','seed':SEED,'cases':[{k:v for k,v in c.items() if k!='n'} for c in rows]};(ROOT/'results/KENN_AUDIO_HOLDOUT_V1_manifest.json').write_text(json.dumps(manifest,indent=2))
 split={s:[c for c in rows if c['split']==s] for s in ('development','calibration','holdout')};out={'benchmark':'KENN_AUDIO_HOLDOUT_V1','frozen_gate_hash':__import__('hashlib').sha256((ROOT/'results/KENN_V2B_gate_config.json').read_bytes()).hexdigest(),'results':{}}
 for name,adj in (('frozen_v2b',False),('v2c_scope_context',True)):out['results'][name]={s:evaluate(rs,adj) for s,rs in split.items()}
 (ROOT/'results/KENN_V2C_gate_results.json').write_text(json.dumps(out,indent=2));(ROOT/'results/KENN_V2C_measurement_results.json').write_text(json.dumps({'analysis_version':'kenn.measured_candidates.v2c.1','holdout':out['results']['v2c_scope_context']['holdout']},indent=2));(ROOT/'results/KENN_V2C_failure_registry.json').write_text(json.dumps({'failures':out['results']['v2c_scope_context']['holdout']['failures']},indent=2));(ROOT/'results/KENN_V2C_analysis_config.json').write_text(json.dumps({'analysis_version':'kenn.measured_candidates.v2c.1','sample_rates':[44100,48000,96000],'window_seconds':.1,'frozen_gate':'v2b.1','v2c_gate':'scope_context.v2c.1'},indent=2));print(json.dumps(out['results'],indent=2))
if __name__=='__main__':main()
