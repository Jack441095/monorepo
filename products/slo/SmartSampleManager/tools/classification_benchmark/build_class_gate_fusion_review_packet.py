#!/usr/bin/env python3
"""Join class-gate audio and filename evidence."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path

SD = Path(__file__).resolve().parent

def _load_name():
    spec = importlib.util.spec_from_file_location('slo_name_evidence', SD / 'name_evidence.py')
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', type=Path, default=SD / 'results_class_conditional_gate_testing_review_v1.json')
    ap.add_argument('--cards', type=Path, default=SD / 'results_class_conditional_gate_testing_cards_v1.json')
    ap.add_argument('--out', type=Path, default=SD / 'results_class_gate_fusion_review_packet_v1.json')
    ap.add_argument('--csv', type=Path, default=SD / 'class_gate_fusion_review_packet_v1.csv')
    args = ap.parse_args()
    queue = json.loads(args.queue.read_text(encoding='utf-8'))
    cards_payload = json.loads(args.cards.read_text(encoding='utf-8'))
    if queue.get('record_type') != 'slo_class_conditional_gate_testing_review' or cards_payload.get('n_errors', 0):
        raise SystemExit('FAIL CLOSED: invalid queue/card receipt')
    cards = {str(c['path']): c for c in cards_payload.get('cards', [])}
    name = _load_name(); rows = []; states = Counter()
    for original in queue.get('rows', []):
        path = str(original['path'])
        if path not in cards: raise SystemExit(f'FAIL CLOSED: missing physical card for {path}')
        ev = name.extract(path); exact = list(ev.candidate_classes); candidate = str(original['candidate_class'])
        if not ev.tokens: state = 'audio_only_no_name_token'
        elif exact and candidate in exact and ev.risk_level != 'high': state = 'audio_name_agree'
        elif exact and candidate not in exact: state = 'audio_name_conflict'
        else: state = 'audio_name_family_or_risk_only'
        states[state] += 1; card = cards[path]
        rows.append({**original, 'name_evidence': ev.as_dict(), 'fusion_state': state,
                     'physical_form_hint': card.get('temporal', {}).get('form_hint'),
                     'physical_form_confidence': card.get('temporal', {}).get('form_hint_confidence'),
                     'low_band_energy_ratio': card.get('spectrum', {}).get('low_band_energy_ratio'),
                     'spectral_centroid_hz': card.get('spectrum', {}).get('spectral_centroid_hz'),
                     'median_f0_hz': card.get('pitch', {}).get('median_f0_hz')})
    payload = {'record_type': 'slo_class_gate_fusion_review_packet', 'schema_version': '1.0.0',
               'method_version': 'class_gate_fusion_review_v1',
               'safety': {'read_only': True, 'source_audio_modified': False, 'semantic_labels_created': False,
                          'production_model_changed': False, 'rename_actions': False, 'auto_approved': False},
               'source_queue': str(args.queue.resolve()), 'source_cards': str(args.cards.resolve()),
               'summary': {'n_rows': len(rows), 'fusion_states': dict(sorted(states.items())),
                           'n_audio_name_agree': states['audio_name_agree'], 'n_audio_name_conflict': states['audio_name_conflict']},
               'decision': 'review-only; name evidence never overrides audio or gate evidence', 'rows': rows}
    args.out.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    fields = ['path','candidate_class','confidence','similarity','fusion_state','name_risk_level','name_token_confidence',
              'name_candidate_classes','physical_form_hint','physical_form_confidence','low_band_energy_ratio',
              'spectral_centroid_hz','median_f0_hz','exact_duplicate_group','near_duplicate_group','action','auto_approved']
    with args.csv.open('w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=fields, lineterminator='\n'); w.writeheader()
        for row in rows:
            ev = row['name_evidence']; out = {**row, 'name_risk_level': ev.get('risk_level'),
                'name_token_confidence': ev.get('token_confidence'), 'name_candidate_classes': ';'.join(ev.get('candidate_classes', []))}
            w.writerow({f: out.get(f, '') for f in fields})
    print(json.dumps(payload['summary'], indent=2)); print(f'wrote {args.out}'); print(f'wrote {args.csv}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
