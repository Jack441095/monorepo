#!/usr/bin/env python3
"""Fail-closed evaluator for the dedicated class-gate validation labels."""
from __future__ import annotations
import argparse, csv, json, math, time
from collections import Counter, defaultdict
from pathlib import Path

SD = Path(__file__).resolve().parent

def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    den = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / den
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / den
    return max(0.0, centre - margin), min(1.0, centre + margin)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', type=Path, default=SD / 'class_conditional_gate_validation_manifest_v1.json')
    ap.add_argument('--labels', type=Path, default=SD / 'verified_class_conditional_gate_validation_v1.csv')
    ap.add_argument('--out', type=Path, default=SD / 'results_class_conditional_gate_validation_v1.json')
    ap.add_argument('--min-per-class', type=int, default=40)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if not isinstance(manifest, list) or not manifest:
        raise SystemExit('FAIL CLOSED: validation manifest is empty or malformed')
    if not args.labels.exists():
        raise SystemExit('FAIL CLOSED: validation labels CSV does not exist yet')
    labels = list(csv.DictReader(args.labels.open(encoding='utf-8')))
    by_id = {int(row['id']): row for row in labels if row.get('id', '').isdigit()}
    expected = {int(row['id']) for row in manifest}
    missing = sorted(expected - set(by_id))
    if missing:
        raise SystemExit(f'FAIL CLOSED: validation is incomplete; missing {len(missing)} labels')
    if len(by_id) != len(labels):
        raise SystemExit('FAIL CLOSED: duplicate or malformed validation ids')
    rows, per_class, confusion = [], defaultdict(list), Counter()
    for item in manifest:
        ident = int(item['id']); label_row = by_id[ident]
        if str(label_row.get('path', '')) != str(item['path']):
            raise SystemExit(f'FAIL CLOSED: path mismatch for id {ident}')
        human = str(label_row.get('label', '')).strip()
        if not human or human == '__skip__':
            raise SystemExit(f'FAIL CLOSED: id {ident} has no usable human label')
        candidate = str(item['candidate_class']); correct = human == candidate
        per_class[candidate].append(correct); confusion[(candidate, human)] += 1
        rows.append({'id': ident, 'path': item['path'], 'candidate_class': candidate,
                     'human_label': human, 'candidate_correct': correct,
                     # Preserve the grouping and model-score context from the
                     # manifest so downstream, nested collection-held-out
                     # audits can consume this receipt without reconstructing
                     # metadata from paths.
                     'vendor': item.get('vendor', ''),
                     'candidate_confidence': item.get('candidate_confidence'),
                     'candidate_similarity': item.get('candidate_similarity')})
    classes = {}
    descriptive, statistical = [], []
    for cls in sorted(per_class):
        vals = per_class[cls]; n = len(vals); correct = int(sum(vals)); lo, hi = wilson(correct, n)
        rec = {'n': n, 'correct': correct, 'precision': correct / n,
               'wilson_95_lower': lo, 'wilson_95_upper': hi,
               'descriptive_95': n >= args.min_per_class and correct / n >= .95,
               'statistically_supported_95': n >= 100 and lo >= .95}
        classes[cls] = rec
        if rec['descriptive_95']: descriptive.append(cls)
        if rec['statistically_supported_95']: statistical.append(cls)
    payload = {'record_type': 'slo_class_conditional_gate_validation', 'schema_version': '1.0.0',
               'method_version': 'class_conditional_gate_validation_v1',
               'safety': {'read_only': True, 'source_audio_modified': False,
                          'production_model_changed': False, 'rename_actions': False,
                          'approval_granted': False},
               'source_manifest': str(args.manifest.resolve()), 'source_labels': str(args.labels.resolve()),
               'summary': {'n_manifest': len(manifest), 'n_labelled': len(rows),
                           'descriptive_95_classes': descriptive,
                           'statistically_supported_95_classes': statistical},
               'classes': classes,
               'confusion': {f'{a} -> {b}': n for (a, b), n in sorted(confusion.items())},
               'rows': rows, 'decision': 'validation evidence only; no class is promoted automatically',
               'generated': time.strftime('%Y-%m-%dT%H:%M:%S')}
    args.out.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['summary'], indent=2)); print(f'wrote {args.out}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
