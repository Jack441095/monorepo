# KENN knowledge ingestion

Run from the KENN product root (`products/kenn`).

The crawler collects provenance and short summaries from approved sources. Raw
pages and full text stay in ignored local storage.

Run a dry-run pilot:

```bash
PYTHONPATH=tooling python3 -m scripts.knowledge_ingest.crawler \
  --source ableton-live-manual-12 \
  --source mit-ocw-music-technology \
  --limit 5 \
  --dry-run
```

The same safe pilot is available from the repository root:

```bash
make knowledge-pilot
```

Write local summaries and a de-duplicated provenance manifest:

```bash
PYTHONPATH=tooling python3 -m scripts.knowledge_ingest.crawler \
  --source ableton-live-manual-12 \
  --source ableton-help-tutorials \
  --source cycling74-max-docs \
  --output-dir local_data/knowledge_ingest
```

To run the current approved set of crawlable sources and keep the output
local, use:

```bash
make knowledge-crawl-open
```

The crawl is resumable through `local_data/knowledge_ingest/state.json` and
produces per-source JSONL plus a de-duplicated `manifest.jsonl`. The generated
directory is ignored by Git; only source configuration and crawler code are
committed.

The source registry records licensing and terms metadata. The crawler obeys
robots rules, uses bounded retries and per-domain delays, stops on repeated
blocking, and never bypasses login walls, CAPTCHA, paywalls, or anti-bot
controls. Add a source only after checking its terms and the intended storage
rights.
