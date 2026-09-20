# SLO Decision Policy Layer V1

_`tools/classification_benchmark/decision_policy.py`, policy v1.0.0._

## Why a policy layer

The classifier is 69.6% accurate. Shipping that as renames would be actively
harmful. The product question is not *what is this sound* but **what may SLO do
about it** — a different question with a different evidence bar.

## Four action states

| action | meaning | approval |
|---|---|---|
| `auto_rename` | act without asking | no |
| `suggest` | show a label, user applies | yes |
| `review` | uncertain → review queue | yes |
| `never_act` | class unsafe or incoherent | n/a |

## Tiers, set from measured precision (not intuition)

Per-class precision at a 0.5 gate, collection-held-out:

| class | measured precision | action |
|---|---|---|
| Kick | 94.3% | **auto_rename** |
| Clap | 93.5% | **auto_rename** |
| Drum Loop | 90.8% | **auto_rename** |
| Snare | 82.9% | suggest |
| Crash | 81.0% | suggest |
| Hi-Hat | 80.0% | suggest |
| Other/none | 72.4% | review *(it is the reject class)* |
| Foley | 68.0% | suggest |
| Percussion Loop | 61.5% | suggest |
| **Percussion** | **15.4%** | **never_act** |

**Percussion acts on half its files at 15.4% precision — five wrong renames for
every right one.** No threshold rescues that: the class names several unrelated
sounds (silhouette −0.120). The fix is taxonomy work, not tuning.

## What this layer deliberately is not

**It does not use per-class thresholds.** Those were measured and rejected: they
undershoot their precision promise by **12pp** on unseen collections because
each is fitted on a few dozen files. This layer uses **one global threshold** and
varies only *which classes may act*. Choosing eligibility is safe; tuning a
threshold per class is not.

## Safety rules that fire before the tiers

1. **Impulse responses → `never_act`.** A measurement of a space, never a sample.
2. **Never-act classes → `never_act`** regardless of confidence.
3. **`Other/none` → `review`**, never a rename.
4. **Below the gate → `review`.**
5. **A measured-unreliable filename token caps the action at `suggest`, even
   when the audio agrees.** This one was a bug in my first draft:
   `antique_shop_snap.wav` is a recorded Foley snap, and both the detector and a
   Clap prototype call it a Clap. Requiring *disagreement* would have
   auto-renamed it. Agreement is not independent evidence when both sources read
   the same misleading token (`snap`, `hit`, `tops`, `chord`, `loop`).

## Measured result (8 seeds, collection-held-out)

| action | share of files | precision |
|---|---|---|
| auto_rename | 15.1% | **90.8%** |
| suggest | 9.3% | 84.5% |
| review | 72.3% | — |
| never_act | 3.3% | — |

**Safety test — auto_rename must beat the raw classifier at the same gate:**

| | precision |
|---|---|
| raw classifier acting above the gate | 88.0% |
| **auto_rename tier** | **89.7%** |
| delta | **+1.7pp — PASS** |

Percussion in auto_rename: **0 — PASS.** Impulse responses in auto_rename:
**0 — PASS.**

## Calibration and the honest promise

| calibrate at | auto-rename precision | share auto-renamed |
|---|---|---|
| 0.90 | 89.7% ✗ | 17.9% |
| **0.93** | **90.8%** ✅ | **15.1%** |
| 0.95 | 92.9% | 11.6% |

Calibrating at the target itself **undershoots** — 0.90 delivers 89.7%. The
domain-shift shortfall is real and must be absorbed. **Recommended beta setting:
calibrate at 0.93.**

Per-seed range at 0.93 is 87.1–95.2%, so an unlucky library could see ~87%.
The honest phrasing is *"around 90%"*, never *"at least 90%"*.
