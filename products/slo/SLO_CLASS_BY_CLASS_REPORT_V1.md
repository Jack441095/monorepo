# SLO Class-by-Class Report V1

Historical benchmark per-class metrics:

| Class | Precision | Recall | F1 | Audit interpretation |
|---|---:|---:|---:|---|
| Bass Loop | 0.928 | 0.955 | 0.941 | good, loop/one-shot confusion |
| Bass One-Shot | 0.927 | 0.908 | 0.918 | good, loop/one-shot confusion |
| Clap | 0.930 | 0.952 | 0.941 | good |
| FX | 0.980 | 0.990 | 0.985 | strong |
| Foley | 0.990 | 0.960 | 0.975 | strong |
| Hi-Hat | 1.000 | 0.972 | 0.986 | strong |
| Impact | 0.944 | 1.000 | 0.971 | strong |
| Kick | 0.968 | 0.968 | 0.968 | strong |
| Music Loop | 0.962 | 1.000 | 0.980 | strong |
| Percussion | 0.957 | 0.947 | 0.952 | good |
| Riser | 0.989 | 0.989 | 0.989 | strong |
| Snare | 0.921 | 0.953 | 0.937 | good |
| Synth | 0.972 | 0.875 | 0.921 | recall weakness |
| Synth Loop | 1.000 | 0.936 | 0.967 | strong in this benchmark |
| Vocal Loop | 1.000 | 1.000 | 1.000 | benchmark conflicts with V4-H evaluation; do not combine |
| Vocal Phrase | 1.000 | 1.000 | 1.000 | benchmark conflicts with V4-H evaluation; do not combine |

The more targeted V4-H calibration report is the limiting evidence for the shipping gate: known accuracy 76.4% overall, Bass Loop and Synth Loop F1 0 in that evaluation, Vocal Loop recall 7.5%, and Vocal Phrase recall 86%. It attributes most Vocal Loop damage to filename evidence outranking ML. The conflicting artifacts prove that dataset and evidence path must be reported with every metric.

Primary remediation: separate audio-only and fused classifiers in the UI/reporting contract, improve Vocal Loop/loop-vs-one-shot handling, and evaluate on cross-vendor data.
