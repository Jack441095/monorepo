# Ableton Assistant Tester Guide

Local-only install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/source:$PWD/chat:$PWD/mix-review/core"
python3 apps/backend/src/kenn/main.py build
python3 -m pytest mix-review/tests automix/tests chat/tests apps/backend/src/kenn/tests -q
python3 scripts/eval_ableton_assistant.py
```

That default clean-checkout path is fully functional with BM25 keyword
retrieval. To enable the optional local semantic layer, securely fetch the
pinned MiniLM ONNX artifacts before building the index:

```bash
python3 scripts/fetch_embedding_model.py
python3 apps/backend/src/kenn/main.py build
```

The fetcher verifies TLS, the pinned upstream revision, and both artifact
digests. If the model is absent, index construction prints a BM25-only fallback
message; that is a supported mode, not a failed installation. The optional
PyTorch/Transformers command-model training environment is separate from this
core tester setup, so training-only tests may be skipped.

On macOS, install the Remote Script into the standard User Library with:

```bash
python3 scripts/install_abletonosc.py --list-paths
python3 scripts/install_abletonosc.py --target "$HOME/Music/Ableton/User Library/Remote Scripts"
```

Restart Live, open Preferences → Link/Tempo/MIDI, choose `AbletonOSC` as the Control Surface, and leave MIDI Input/Output as None. Start the companion with `AUDIO_TOO_ALLOW_DAW_CONTROL=1 ./scripts/start_server.sh` for a supervised write pilot (or `python3 apps/backend/src/kenn/server.py` for a read-only loopback run), then test `curl http://127.0.0.1:8090/api/health` and a read-only `GET /api/ableton/osc/session`.

The assistant can answer grounded production questions, inspect supplied WAVs, run deterministic analysis, and prepare a Live proposal. It cannot hear an absent file, inspect an absent Live session, or safely infer a missing/duplicate target. Confirmations are explicit and single-use.

For Live testing use `docs/ABLETON_LIVE_TEST_PROCEDURE.md`. Test only a disposable set, keep Auto mode disabled, and attach the receipt to every bug report. Never paste confirmation tokens into public issue trackers.

For the Internal Beta 0.1 supervised pilot, use
`docs/ABLETON_INTERNAL_BETA_0.1_RUN_LOG_TEMPLATE.md` for each session and
submit only sanitized receipts, hashes, and observations. Run the pilot gate
with `--check-live` immediately before testing so an offline AbletonOSC
companion cannot be
mistaken for the captured qualification evidence.

The reproducible clean-checkout evidence is recorded in
`docs/KENN_CLEAN_INSTALL_VERIFICATION_2026-09-07.md`.
