# Training Commands

This repo supports **offline** training of a retrained melody Markov bundle (`.pkl`) and an optional interval **logit residual** (`.npz`), using a **melody training JSONL**.

**Canonical dataset in this tree:** `artifacts/datasets/live_melody/primary/live_melody_training.jsonl` (companion `emotion_diagnostics.json` and `run_meta.txt` in the same folder). A **full** rebuild from current code, without legacy Markov-pickle influence, should use `USE_RETRAINED_MARKOV=0` (default) and a chosen style, e.g. `STYLE=cinematic_minimal TAG=primary bash run_v012e_joint_tune_dataset_and_diagnostics.sh`. Clear old exports first: `rm -rf artifacts/datasets/live_melody/*` (or use a different `TAG=…` for an A/B run without deleting `primary`). Generator flags: all emotions, `per_emotion=32`, `bars=16`, `role_cycle=6`, `--quality-mode`, `--dedup-kept`, `--disable-retrained-markov` by default.

Most commands below use `python3` (recommended on macOS).

## Quickstart (offline, all emotions)

### Option 0: One-command pipeline (versioned artifacts)

This runs dataset generation → eval gate (writes JSON report) → offline training → promotion:

```bash
python3 scripts/run_training_pipeline.py --version v001 --train all --dedup --require-metadata
```

Artifacts are written under `artifacts/` and active models promoted to `training_data/active_models/`.

Optional: make the dataset cleaner (slower) with `--quality-mode`:

```bash
python3 scripts/run_training_pipeline.py --version v001 --train all --dedup --require-metadata --quality-mode
```

### Manual pipeline (if you want individual steps)

Generate the training JSONL **without** realtime playback/audio (writes a single JSONL file):

```bash
python3 scripts/generate_live_melody_training_jsonl.py \
  --out artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --per-emotion 64 \
  --bars 16
```

Train Markov + logit residual (and write a manifest) and exit:

```bash
python3 main.py --offline-train all \
  --offline-train-jsonl artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --offline-train-tag v001 \
  --offline-train-dir artifacts/runs/offline_training/v001 \
  --offline-train-require-metadata \
  --offline-train-min-emotions 4 \
  --offline-train-min-section-roles 3 \
  --offline-train-max-emotion-share 0.45 \
  --offline-train-dedup
```

Promote the run outputs into the active model folder:

```bash
python3 main.py --offline-promote-run artifacts/runs/offline_training/v001/v001 \
  --offline-promote-kind all \
  --offline-promote-dir training_data/active_models
```

Launch using the promoted artifacts:

```bash
python3 main.py --melody-retrained-markov \
  --melody-retrained-markov-path training_data/active_models/melody_markov.pkl \
  --melody-neural-logit-residual \
  --melody-neural-logit-residual-path training_data/active_models/melody_logit_residual.npz
```

## 1) Build the training JSONL

### Option A: Offline generation (recommended)

```bash
python3 scripts/generate_live_melody_training_jsonl.py \
  --out artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --out-rejects artifacts/datasets/live_melody/v001/live_melody_rejects.jsonl \
  --accept-threshold 0.0 \
  --dedup-kept \
  --per-emotion 64 \
  --bars 16
```

Useful flags:
- `--append`: append to an existing JSONL instead of overwriting it
- `--emotions joy sadness calm`: generate only a subset by name
- `--disable-retrained-markov`: ensure the dataset is generated without loading any retrained Markov
- Joint v012e script: `run_v012e_joint_tune_dataset_and_diagnostics.sh` passes this by default; set `USE_RETRAINED_MARKOV=1` to load a retrained pickle for generation instead
- `--target-notes-per-bar 5.5`: tune melody density
- `--role-cycle-length 6`: encourage section-role coverage
- `--quality-mode`: enable offline-quality generation knobs (slower, cleaner)
- `--out-rejects ...`: write rejected/low-score examples to a separate JSONL
- `--accept-threshold 0.7`: keep only rows with accept_score >= threshold
- `--dedup-kept`: deduplicate kept rows by melody content (recommended)

### Option B: Live capture (realtime playback)

```bash
python3 main.py --export-live-melody-training \
  --export-live-melody-training-path .cache/live_melody_training.jsonl
```

Let it run, switch emotions, then quit with `q`.

## 2) Offline training jobs

### Train melody Markov bundle

```bash
python3 main.py --offline-train markov \
  --offline-train-jsonl artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --offline-train-tag v001_markov \
  --offline-train-dir artifacts/runs/offline_training/v001_markov \
  --offline-train-grouped both \
  --offline-train-min-group-melodies 8 \
  --offline-train-dedup
```

### Train the interval logit residual (optional)

```bash
python3 main.py --offline-train logit \
  --offline-train-jsonl artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --offline-train-tag v001_logit \
  --offline-train-dir artifacts/runs/offline_training/v001_logit
```

### Run everything (markov + logit + emotion dataset export/validation)

```bash
python3 main.py --offline-train all \
  --offline-train-jsonl artifacts/datasets/live_melody/v001/live_melody_training.jsonl \
  --offline-train-tag v001 \
  --offline-train-dir artifacts/runs/offline_training/v001 \
  --offline-train-dedup
```

## 3) Promote trained artifacts into “active models”

```bash
python3 main.py --offline-promote-run artifacts/runs/offline_training/v001/v001 \
  --offline-promote-kind all \
  --offline-promote-dir training_data/active_models
```

Outputs:
- `training_data/active_models/melody_markov.pkl`
- `training_data/active_models/melody_logit_residual.npz` (if trained)
- `training_data/active_models/active_manifest.json`

## 4) Run with retrained models

Markov only:

```bash
python3 main.py --melody-retrained-markov \
  --melody-retrained-markov-path training_data/active_models/melody_markov.pkl
```

Markov + logit residual:

```bash
python3 main.py --melody-retrained-markov \
  --melody-retrained-markov-path training_data/active_models/melody_markov.pkl \
  --melody-neural-logit-residual \
  --melody-neural-logit-residual-path training_data/active_models/melody_logit_residual.npz
```

## Troubleshooting

### `python: command not found`
Use `python3 ...` for commands in this doc.

### “Offline training JSONL not found”
Make sure you generated the JSONL first:

```bash
python3 scripts/generate_live_melody_training_jsonl.py --out artifacts/datasets/live_melody/v001/live_melody_training.jsonl
```

### “No melodies after filtering.”
Your JSONL rows didn’t meet the Markov retrain filters (default `--min-notes` is 4). Regenerate with more bars and/or increase `--per-emotion`:

```bash
python3 scripts/generate_live_melody_training_jsonl.py \
  --out .cache/live_melody_training.jsonl --per-emotion 32 --bars 16
```
