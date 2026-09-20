# SLO class-gate audio/name fusion review — V1

Date: 2026-09-11

The 408 class-gate candidates now carry both physical waveform evidence and the
measured filename evidence layer. Filename evidence is descriptive only and
never overrides the audio gate.

| fusion state | rows |
|---|---:|
| audio/name agree | 385 |
| audio-only, no recognised token | 18 |
| audio/name conflict | 3 |
| audio/name family or risk-only | 2 |

The three conflicts are explicitly surfaced for human review; they are not
eligible for automatic action. Duplicate guards remain attached separately,
and every row is still `review_candidate_only`.

Receipts:

- `SmartSampleManager/tools/classification_benchmark/results_class_gate_fusion_review_packet_v1.json`
- `SmartSampleManager/tools/classification_benchmark/class_gate_fusion_review_packet_v1.csv`
- Runner: `SmartSampleManager/tools/classification_benchmark/build_class_gate_fusion_review_packet.py`
