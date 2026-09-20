# SLO Classification V3 Error Analysis

## 1. Top Misclassifications
The primary failures on clean data occur at taxonomy boundaries:
1. **Hi-Hat vs. Percussion**: Closed hi-hats with slightly lower frequency profiles are classified as Percussion.
2. **Music Loop vs. Synth Loop**: Complex synth loops are misclassified as full Music Loops, or vice versa.
3. **Bass Loop vs. Synth Loop**: Sustained synth loops containing low-frequency modulation are predicted as Bass Loops.

## 2. OOD False Accepts
The OOD failure analysis identified that:
- **Acoustic Guitars** are falsely accepted as Synth plucks.
- **Orchestral Violins / Brass** are accepted as Synth pads or Foley.
- **Animal noises** map to Foley or FX with confidence > 0.80.

## 3. Owner Review Queue
We generated `owner_review_queue.csv` containing **50 high-priority review samples** where:
- Classifier predictions disagree with pack folder labels.
- The top-1 class margin is < 0.20.
These representatives are marked for owner labeling verification.
