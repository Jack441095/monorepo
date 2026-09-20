#!/usr/bin/env python3
"""Build a randomised, label-hidden V2-D engineer review manifest."""
from __future__ import annotations
import hashlib,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
cases=json.loads((ROOT/'results/KENN_AUDIO_HOLDOUT_V1_manifest.json').read_text())['cases']
r=random.Random(20260823);r.shuffle(cases);chosen=cases[:80]
blind=[{'review_id':f'REV-{i+1:03d}','audio_generator_case_id':c['id'],'audio_reference':'generated on demand; no ground truth shown','analysis':'structured product analysis shown after listening','scores':{'correctness_1_5':None,'relevance_1_5':None,'safety_1_5':None,'clarity_1_5':None,'unnecessary_recommendation':None,'harmful_recommendation':None,'abstention_preferable':None},'notes':''} for i,c in enumerate(chosen)]
answer=[{'review_id':f'REV-{i+1:03d}','case_id':c['id'],'ground_truth':c['faults'],'scope':'mix_in_progress' if c['group']=='headroom' else 'master' if c.get('confounder')=='mastered' else 'unknown'} for i,c in enumerate(chosen)]
(ROOT/'results/KENN_V2D_blind_review_manifest.json').write_text(json.dumps({'review':'KENN_BLIND_ENGINEER_REVIEW_V1','cases':blind,'rubric':'1-5 correctness, relevance, safety, clarity; yes/no unnecessary, harmful, abstention preferable'},indent=2))
(ROOT/'results/KENN_V2D_blind_review_answer_key.json').write_text(json.dumps({'review':'KENN_BLIND_ENGINEER_REVIEW_V1','answer_key':answer,'sha256':hashlib.sha256(json.dumps(answer,sort_keys=True).encode()).hexdigest()},indent=2))
print(len(blind))
