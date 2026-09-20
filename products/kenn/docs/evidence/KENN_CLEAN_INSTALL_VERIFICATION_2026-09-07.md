# KENN clean-install verification

**Date:** 2026-09-07

**Source revision tested:** `fcd9c8a`

**Host:** macOS 26.6.2 (`arm64`)

**Python:** 3.13.7

**pip:** 25.2

## Result

A new local clone, new virtual environment, dependency install, generated
knowledge index, and complete documented Python test suite all succeeded from
committed repository content. The test result was:

```text
574 passed, 7 skipped, 4 warnings in 56.81s
```

The seven skips are the expected command-model training tests whose optional
PyTorch/Transformers training stack is not part of `requirements.txt`. Core
installation, retrieval, chat, audio analysis, server, control-contract, and
release-gate tests did not depend on that stack.

## Procedure exercised

```bash
git clone --local /Volumes/Jack_Gandy_1TB_SSD/Shenrendao/KENN repo-verified
python3 -m venv venv
venv/bin/python -m pip install -r repo-verified/requirements.txt
cd repo-verified
PYTHONPATH="$PWD/source:$PWD/chat:$PWD/mix-review/core" \
  ../venv/bin/python source/kenn/main.py build
PYTHONPATH="$PWD/source:$PWD/chat:$PWD/mix-review/core" \
  ../venv/bin/python -m pytest \
  mix-review/tests automix/tests chat/tests source/kenn/tests -q
```

The clone contained no ignored local model weights. Index generation therefore
used KENN's intentional BM25-only fallback and produced 1,116 chunks from 234
approved notes plus one approved PDF. This proves the core checkout works
offline after dependency installation; it does not claim semantic embeddings
were enabled in that clean clone.

## Optional hybrid retrieval

For hybrid BM25 plus semantic retrieval, run this before rebuilding the index:

```bash
python3 scripts/fetch_embedding_model.py
python3 source/kenn/main.py build
```

The fetcher uses certificate-verified TLS and pins
`Xenova/all-MiniLM-L6-v2` revision
`751bff37182d3f1213fa05d7196b954e230abad9`. It verifies the SHA-256 digest of
both the ONNX model and tokenizer before publishing either artifact. The model
weights remain generated/local artifacts and are intentionally not committed.

## Scope boundary

This run verifies reproducibility of the Python/core installation. Native AU
and VST3 host validation is recorded separately in
`KENN_PLUGIN_HOST_VALIDATION_2026-09-07.md`. Distribution signing,
notarization, an interactive Ableton host-load rehearsal, rollback rehearsal,
and two-person human review remain separate release evidence.
