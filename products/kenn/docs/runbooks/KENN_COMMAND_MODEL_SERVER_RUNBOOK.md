# KENN command-model server runbook

This is an offline research job. It must run on dedicated compute and must not
share the KENN bridge process, Ableton, or the real-time audio thread.

There are two deliberately separate hosts:

* The **Mac companion** is the local Live-control process. For a supervised
  disposable Live test, it may be started with
  `AUDIO_TOO_ALLOW_DAW_CONTROL=1 ./scripts/start_server.sh`. This affects only
  the Mac companion and does not restart Ableton.
* The **Ubuntu host** is training-only. The remote handoff below creates an
  isolated working directory and runs offline training commands; it never
  restarts a server service, Ableton, or an audio process on that host.

Never copy Live project files, audio, credentials, or private KENN knowledge
content to the training host. The handoff wrapper enforces an allow-list of
training files rather than archiving the repository wholesale.

## 1. Prepare the server

Use the server account only after SSH authentication has been verified. The
repository can be copied to a private working directory or cloned from its
configured remote; do not put credentials in this file or in shell history.

From a clean local checkout, the repository's committed `HEAD` can be shipped
and run through the guarded pilot with the wrapper below. It prompts through
the configured SSH authentication flow, stores no password, ships only the
allow-listed training subset, refuses a dirty worktree, and never overwrites
an existing remote pilot directory:

```sh
bash scripts/run_kenn_command_pilot_remote.sh \
  --remote-workdir /tmp/kenn-command-pilot-20260905 \
  --run \
  --allow-download
```

If the server administrator has authorized a specific SSH key, pass its local
private-key path explicitly. The wrapper uses that key only for the SSH
connection and never copies it to the server:

```sh
bash scripts/run_kenn_command_pilot_remote.sh \
  --identity-file "$HOME/.ssh/kenn_training_ed25519" \
  --remote-workdir /tmp/kenn-command-pilot-20260905 \
  --run
```

Omit `--run` for a remote CUDA preflight only. Omit `--allow-download` when
the selected base model is already cached on the server.

```sh
python3 -m venv .venv-kenn-training
. .venv-kenn-training/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-training.txt
```

Before training, record the host, Python version, PyTorch version, accelerator,
GPU memory, repository revision, and the SHA-256 of the training JSONL. The
server should have enough memory for the selected base model plus optimizer
state; a CUDA GPU is preferred for this pilot.

## 2. Validate the inputs

The preferred path is the safe orchestrator below. It defaults to corpus,
audit, and CUDA/device preflight only; add `--run` only after reviewing the
generated `pilot-manifest.json`.

```sh
PYTHONPATH=source python scripts/run_kenn_command_pilot.py \
  --workdir /tmp/kenn-command-pilot \
  --device cuda
```

Run the data generator if the checked-in export is not present, then perform a
read-only dry run. The dry run must report `status=ready` and
`holdout_protection=passed`.

```sh
python scripts/build_kenn_command_training.py
PYTHONPATH=source python scripts/train_kenn_command_lora.py \
  --epochs 1 --batch-size 4
```

The equivalent one-command training/evaluation run is:

```sh
PYTHONPATH=source python scripts/run_kenn_command_pilot.py \
  --workdir /tmp/kenn-command-pilot \
  --device cuda \
  --run
```

The training export is synthetic and separate from
`apps/backend/src/kenn/evals/ableton_llm_shadow_holdout.json`. Do not add holdout cases to
the training file to improve a score.

For the first controlled pilot, expand the reviewed seed records only through
their natural template variants. This still contains no private project or
audio data and must be treated as synthetic training material:

```sh
PYTHONPATH=source python scripts/build_kenn_command_corpus.py \
  --variants 28 \
  --scenarios 4 \
  --output /tmp/kenn-command-corpus.jsonl

PYTHONPATH=source python scripts/audit_kenn_command_corpus.py \
  --input /tmp/kenn-command-corpus.jsonl \
  --output /tmp/kenn-command-corpus-audit.json
```

The builder validates every label against the KENN plan validator and refuses
queries copied into the sealed shadow holdout. Mechanical variants are useful
for a pilot, but they are not a substitute for reviewed examples across
different Live snapshots, devices, and user phrasings.

The clean 28-variant-by-4-scenario export contains 2,016 records, zero
mechanical variant markers, and the current audit reports 100% deterministic
contract agreement across its 1,568 eligible supported/inspection records.
Those figures are parser-consistency evidence only, not human language or Live
quality evidence. The old `--variants 256` setting remains available as a
stress/oversampling experiment, not as the recommended first training run.

The trainer validates each row against the scenario snapshot recorded by the
corpus builder. A multi-scenario export therefore has to pass this same
preflight before any model is loaded or adapter directory is created.
The audit intentionally reports `status=review_required` for synthetic data;
that is a quality warning, not a training failure. In particular, do not treat
the record count as a proxy for distinct language coverage.

## 3. Run one pilot

Choose a new, empty output directory. Training is explicit and writes only the
adapter directory named below.

```sh
PYTHONPATH=source python scripts/train_kenn_command_lora.py \
  --run \
  --data /tmp/kenn-command-corpus.jsonl \
  --epochs 1 \
  --batch-size 4 \
  --device cuda \
  --output apps/backend/src/kenn/artifacts/models/kenn-command-lora-server-pilot
```

Keep the printed batch losses and the resulting
`kenn_experiment_manifest.json`. The manifest records the corpus SHA-256,
repository revision, Python/PyTorch environment, accelerator availability, and
training settings. A completed run is not product approval; it only proves
that an adapter artifact was produced.

## 4. Evaluate without Ableton

```sh
PYTHONPATH=source python scripts/evaluate_kenn_command_lora.py \
  --adapter apps/backend/src/kenn/artifacts/models/kenn-command-lora-server-pilot \
  --compare-base \
  --output apps/backend/src/kenn/artifacts/evals/kenn-command-lora-server-pilot.json
```

The evaluator uses the fixed deterministic fixture and the real KENN plan
validator. With `--compare-base`, it runs the untouched base model and the
adapter on the same cases and reports per-case results plus an
`adapter_minus_base` metric delta for schema acceptance, deterministic
agreement, and latency. It never opens OSC, creates a proposal, confirms an
action, or changes Live.

Do not promote the adapter unless the report shows that every generated plan
is schema-valid and validator-safe, and its exact action/track/device/value
agreement is materially better than the recorded local-model baseline. Any
rejected, invented, or ambiguous target remains a failed command-plan result.

## 5. Only then run shadow mode

Copy only a reviewed adapter and its manifest to the development machine. Keep
the existing deterministic parser authoritative and enable:

```text
KENN_LIVE_LLM_ENABLED=1
KENN_LIVE_LLM_MODE=shadow
```

Shadow mode is comparison telemetry only. It must not replace deterministic
intent, create an unconfirmed proposal, or permit an autonomous Live write.
The adapter becomes a Live candidate only after a fresh runtime preflight,
human review of representative commands, and the existing confirmation,
readback, stale-state, replay, and undo gates pass again.
