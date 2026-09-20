# SLO artifact handoff for KENN

When the SLO training run is complete, export a self-contained artifact
directory and create a completed version of
[`SLO_ARTIFACT_MANIFEST_TEMPLATE.json`](SLO_ARTIFACT_MANIFEST_TEMPLATE.json)
in that directory.

The directory must contain:

- model weights in ONNX, TorchScript, or safetensors format;
- the exact label map used at inference;
- preprocessing parameters, including sample rate, channel policy, crop/pad
  rules, normalisation, and feature settings;
- calibration/OOD thresholds;
- a machine-readable evaluation receipt that records audio-only and
  metadata-assisted metrics separately, per-class metrics, split definition,
  model/export versions, and date;
- SHA-256 hashes for every referenced file.

From the KENN checkout, validate the export without importing model code or
enabling inference:

```sh
python3 scripts/inspect_slo_artifact.py --manifest /absolute/path/to/manifest.json
```

The command must report `status: "verified"`. This only proves the export is
complete and immutable; it does **not** activate it. KENN still needs its own
fixed retrieval/context/latency evaluation and an explicit advisory-only
feature flag before the classifier can appear in live assistant context.

For KENN's fixed adapter boundary, provide a privacy-safe JSONL holdout with
opaque case and project buckets plus expected labels and completed
`kenn.audio_classification.v1` payloads. Evaluate it separately from the
training repository's own metrics:

```sh
python3 scripts/evaluate_slo_adapter.py --cases /absolute/path/to/kenn-slo-holdout.jsonl
```

It reports audio-only and metadata-assisted accuracy/macro-F1 separately,
per-class precision/recall/F1, and Unknown/OOD counts. It still never enables
the classifier automatically.

Do not place model weights, sample audio, absolute workstation paths, training
data, credentials, or raw user prompts in the KENN repository.
