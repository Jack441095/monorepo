# KENN Chat

Small public boundary around the real KENN retrieval engine.

This service is deliberately limited to text-based mix-engineering advice:

- The engine is this repository's own `source/` tree (no external checkout
  needed by default -- see `docs/KNOWN_ISSUES.md` ISSUE-06 for the fix
  history; `KENN_ENGINE_ROOT` can still point elsewhere if needed).
- `AUDIO_TOO_LLM_ENABLED` is forced to `0`; requests use `allow_llm=False`.
- Weak or missing source matches abstain with `intent: "out_of_scope"`.
- One narrow mastering/harshness query normalisation retries retrieval with
  equivalent approved terms when KENN's existing intent guard is too broad.
- No audio, upload, DAW-control, generation, agent, game-audio, or plugin-ranking path is exposed.
- Public sources contain provenance metadata only, not note text.

The knowledge index this service searches is generated, not committed --
build it first with `python3 apps/backend/src/kenn/main.py build` from the repo
root (see `docs/KENN_BETA_TESTER_GUIDE.md`).

## Local run

From the repository root:

```sh
python3 apps/backend/src/kenn/main.py build   # once, or after notes change
cd chat
python3 -m uvicorn app:app --host 127.0.0.1 --port 8091
```

Configure `KENN_CHAT_ALLOWED_ORIGINS` explicitly before browser use;
wildcard CORS is not supported.

For a container deployment, set `KENN_CHAT_INDEX_DIR` to writable runtime
storage. The included image builds the approved index there.

`KENN_ENGINE_ROOT` may point at another checkout if you want to run against
a different `source/`-shaped tree (e.g. a private engine checkout with a
larger knowledge base) instead of this repository's own.

```sh
curl -s http://127.0.0.1:8091/health
curl -s -X POST http://127.0.0.1:8091/kenn/chat \
  -H 'content-type: application/json' \
  -d '{"question":"The kick disappears when the bass comes in."}'
```

Runtime state is written under `.runtime/`, outside the `Audio_Too` checkout.

## Railway deployment shape

The included Dockerfile copies only the KENN engine dependency and wrapper,
builds the approved index into `/app/runtime-index`, and serves only the
wrapper route. It does not include an audio upload path or the wider KENN
assistant surface.

Run the service from `chat/` with:

```sh
uvicorn app:app --host 0.0.0.0 --port "$PORT"
```

Set these Railway variables (values containing hostnames are supplied by the
owner after the services exist):

```text
AUDIO_TOO_LLM_ENABLED=0
KENN_CHAT_ALLOWED_ORIGINS=https://<website-host>
KENN_CHAT_RUNTIME_DIR=/tmp/kenn-chat-runtime
KENN_CHAT_INDEX_DIR=/app/runtime-index
KENN_CHAT_ENGINE_TIMEOUT_SECONDS=30
KENN_CHAT_RATE_LIMIT_REQUESTS=30
KENN_CHAT_RATE_LIMIT_WINDOW_SECONDS=60
```

If the engine checkout is not at the wrapper's default `<repo>/source`,
set `KENN_ENGINE_ROOT` to its path.
The website should keep the browser same-origin by setting the server-side
proxy variable:

```text
KENN_CHAT_SERVICE_URL=https://<kenn-chat-host>
NEXT_PUBLIC_KENN_EVAL_URL=https://<kenn-chat-host>/eval
```

`NEXT_PUBLIC_KENN_CHAT_URL` is not required; the widget defaults to the
website's `/kenn/chat` proxy.

Before publication, smoke-test one diagnostic mix question, one out-of-scope
question, and the absence of any audio/file upload control. Then publish the
machine-readable receipt from the local eval run only after confirming the
deployed service uses the same approved index and LLM-off configuration.
