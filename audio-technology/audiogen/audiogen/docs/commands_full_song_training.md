# Full song training (arranged, offline)

This doc is for **training from full arranged songs** (multi-section context) while still exporting the existing **JOINT per-section JSONL** rows (so the current offline trainers work unchanged).

## Recommended: one-command arranged-song retrain (default form)

This generates full songs in form **`default`**, then runs:
- eval gate
- offline train (`markov` + `chord` + `logit` + dataset validation)
- optional promotion to `training_data/active_models`

```bash
bash scripts/retrain_arranged_songs.sh
```

## Common overrides

### Name the run (tag)

```bash
TAG=v003_da01 bash scripts/retrain_arranged_songs.sh
```

### Make songs longer (more bars per section)

```bash
TAG=v003_da01 BARS_PER_SECTION=20 MAX_BARS=120 bash scripts/retrain_arranged_songs.sh
```

### Generate fewer/more songs per emotion

```bash
TAG=v003_da01 SONGS_PER_EMOTION=4 bash scripts/retrain_arranged_songs.sh
TAG=v003_da01 SONGS_PER_EMOTION=10 bash scripts/retrain_arranged_songs.sh
```

### Disable promotion (train only)

```bash
TAG=v003_da01 PROMOTE=0 bash scripts/retrain_arranged_songs.sh
```

### Dry-run promotion (see what would be copied)

```bash
TAG=v003_da01 DRY_RUN_PROMOTE=1 bash scripts/retrain_arranged_songs.sh
```

## Manual steps (if you want to run each stage yourself)

### 1) Generate arranged-song dataset (default form)

```bash
python3 -u scripts/generate_arranged_joint_training_jsonl.py \
  --out artifacts/datasets/arranged_joint/v003_da01/arranged_joint_training.jsonl \
  --out-rejects artifacts/datasets/arranged_joint/v003_da01/arranged_joint_rejects.jsonl \
  --form default \
  --songs-per-emotion 6 \
  --bars-per-section 16 \
  --max-bars 96 \
  --quality-mode --quality-k-samples 6 \
  --dedup-kept \
  --disable-retrained-markov
```

### 2) Train (eval gate + markov + chord + logit + dataset validation)

```bash
python3 -u main.py --offline-train all \
  --offline-train-jsonl artifacts/datasets/arranged_joint/v003_da01/arranged_joint_training.jsonl \
  --offline-train-tag v003_da01 \
  --offline-train-dir artifacts/runs/offline_training \
  --offline-train-require-metadata \
  --offline-train-min-emotions 4 \
  --offline-train-min-section-roles 3 \
  --offline-train-max-emotion-share 0.45 \
  --offline-train-dedup
```

### 3) Promote into active models

```bash
python3 -u main.py --offline-promote-run artifacts/runs/offline_training/v003_da01 \
  --offline-promote-kind all \
  --offline-promote-dir training_data/active_models
```

### 4) Run with retrained models

```bash
python3 main.py --melody-retrained-markov \
  --melody-retrained-markov-path training_data/active_models/melody_markov.pkl \
  --melody-neural-logit-residual \
  --melody-neural-logit-residual-path training_data/active_models/melody_logit_residual.npz
```

