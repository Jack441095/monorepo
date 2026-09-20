# SLO OOD Benchmark V1

## 1. Out-of-Distribution Methods Comparison
We evaluated the classifier on 250 acoustic OOD samples (piano, acoustic guitar, violins, animal noises, white noise, etc.).

| Metric | Max Softmax Prob (MSP) | Softmax Entropy | Margin Score |
|---|---|---|---|
| **AUROC** | 0.697 | 0.694 | **0.698** |
| **AUPR** | 0.901 | 0.900 | **0.902** |
| **FPR@95TPR** | 0.784 | 0.812 | **0.804** |

## 2. Verdict & Failure Cases
The Margin Score is the marginally superior OOD rejection method, but it is **not sufficient for commercial production authority**.
- An FPR@95 of **80.4%** means that to retain 95% of valid drum/synth samples, we must falsely accept 80.4% of unsupported OOD files.
- Acoustic instruments (like cello or guitar stabs) are regularly mapped to "Synth Pad" or "Foley" classes with confidence > 0.80.
- Additional OOD signals (like reconstruction error or Mahalanobis centroid boundaries) are required to build a safer classifier.
