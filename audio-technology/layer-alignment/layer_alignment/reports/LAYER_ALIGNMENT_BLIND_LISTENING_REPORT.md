# LAYER ALIGNMENT BLIND LISTENING REPORT (V1 — AUTHORISED CORPUS)
### Status: PACK GENERATED AND READY — HUMAN-QUALIFIED: NO (awaiting owner judgements)

## Pack (`results/real_v1/blind_pack_real/`)

| stratum | entries |
|---|---|
| natural ALIGN auditions | 2 (multimic kick in/out; snare top/bottom +polarity) |
| controlled known-truth auditions | 30 (stratified: kick 8, snare 5, clap 3, bass 5, perc 3, synth 4, vocal 2 — highest-confidence per domain) |
| consistency traps (identical A/B) | 12 |
| deterministic repeats (~20%) | included |
| **total** | **52** |

Blinding seed `NLA-REAL-V1-BLIND-SEED-7f3a` (committed); A/B assignment and
presentation order reproducible from it. Level-match: scalar broadband-RMS
gain on SUGGESTED only, unmatched RMS delta recorded per entry.

## How to review (≈1-2 s per judgement)

```
cd Nite_DSP_RnD/layer_alignment
python3 eval/review_server.py results/real_v1/blind_pack_real \
       results/real_v1/blind_votes.json 8765
# open http://127.0.0.1:8765/
```

Play A / Play B → vote 1-6 (keys 1-6) → optional reason → auto-next.
Progress auto-saves; resume anytime. Algorithm outputs stay hidden until a
vote is stored.

## Frozen definitions

USEFUL = decoded preference for the suggested version · NEUTRAL =
Equivalent/Cannot-judge · HARMFUL = preference for original.
Traps decode as EQUIVALENT-correct; trap disagreement measures reviewer
reliability and is reported separately from product metrics.

## What the review will decide

1. Useful/harmful rates on natural recommendations (n=2 — reported but
   statistically weak; disclosed).
2. Useful/harmful rates on known-truth controlled auditions (n=30) —
   "when it recommends, does the change help by ear" measured properly.
3. Trap consistency for reviewer reliability.

Gate arithmetic after review: useful ≥80% / harmful ≤5% evaluated first on
natural-only, then on pooled natural+controlled sets, both reported without
cherry-picking.
