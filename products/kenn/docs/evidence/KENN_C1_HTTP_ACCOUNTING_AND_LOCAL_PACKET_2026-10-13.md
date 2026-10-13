# C1 measurement accounting fixes and the local session packet — 13 October 2026

Cloud session, tooling only. No model, Ollama, Live or companion was run, so nothing here is a latency, memory,
swap, dropout or answer-quality result. C1 stays open until the local measurements below are taken on the M3/16 GB.
Production chat remains `qwen3:4b-instruct-2507-q4_K_M`.

## What C1 already had

From the plan and the 2–5 Oct evidence: the stream surface has three 30-question runs (8B model, before the
4B switch), the payload surface one run, rejection reasons per row and per background upgrade (`fcd2914f`,
`2be6a7c6`), provider phase telemetry with unknowns kept unknown, and `measure_chat_latency.py` with
`stream`, `payload`, `foreground` and `background` surfaces. Missing for C1: foreground and background HTTP runs,
repeats on the current 4B model, cold/warm separation, memory pressure, swap and dropouts, and the controlled
Live-open/closed comparison.

## Gaps found in the tooling, and what changed

Each was shown by a failing test before the change, using a scripted fake companion (no socket) or stubbed
`sysctl` output.

1. **A stopped companion was booked as a timeout.** `KennTransportError` says "did not complete" for every socket
   failure, and the row classifier matched that text. A refused connection now reads `delivery: "error"` with the
   cause in `error`; only a `TimeoutError` (direct, via `URLError.reason`, or an httpx `*Timeout`) in the cause
   chain reads `timeout`. An in-process exception that is not a timeout is also `error` now, not `not_attempted`.
2. **Cancellation was invisible.** `server.py` replies to a superseded turn with `status: "cancelled"` and
   `answer_delivery_discarded`. The harness counted that as a template (`not_attempted`); it is now
   `delivery: "cancelled"`. A background job discarded for a newer turn still reads `expired` from
   `/api/ask/upgrade`, indistinguishable from a TTL lapse; that stays `not_attempted` and is documented, since the
   server contract cannot tell them apart.
3. **Server pipeline timings were dropped.** HTTP rows now keep the companion's `timing` block verbatim as
   `server_timing_ms` (not mapped onto `phase_seconds`, because `context_build_ms` is plug-in context, not
   retrieval), `server_upgrade_seconds` (answer_upgrades' own model-run clock) and `initial_reply_seconds` (when
   the template reply arrived, timed apart from the upgrade). `first_useful_answer_seconds` and
   `final_displayed_answer_seconds` stay `None`: receiving a reply is not seeing it.
4. **Accepted upgrades carried `"accepted"` as a warning.** Only rejections carry a reason now.
5. **A background polling timeout threw the delivered template away.** The row now keeps the template answer,
   job id and server timing.
6. **Response-cache state was ambiguous.** `cache_settings.KENN_LLM_CACHE` echoed `None` when unset, which is the
   cache **on**. `cache_settings.response_cache_enabled` now resolves it in-process and is `None` over HTTP, where
   this process says nothing about the companion.
7. **Per-task model overrides were missed.** `provenance.resolved_models` names what `rewrite`, `route`,
   `paraphrase` and `followups` resolve to in-process (`None` over HTTP). The weights digest still comes only from
   `--build-manifest`.
8. **Memory pressure and swap were hard-coded `None`.** Each row now samples `vm.swapusage` (used bytes) and
   `kern.memorystatus_vm_pressure_level` (normal/warn/critical) after its clock stops. It is an end-of-answer
   snapshot, not a peak. Off-Mac, or on an unfamiliar format, both stay `None`. `audio_dropouts` is a new field and
   is always `None`: nothing in the harness sees Live's audio engine, so the owner records dropouts.
9. **The console summary hid timeouts and errors.** `render()` prints the delivery breakdown.
10. `build_captured_review_packet.py` accepts the two new outcomes, `cancelled` and `error`, so a capture holding
    them still exports and keeps them in the denominator.

Files: `tooling/scripts/measure_chat_latency.py`, `tooling/scripts/build_captured_review_packet.py`,
`apps/backend/src/kenn/tests/test_measure_chat_latency.py`,
`apps/backend/src/kenn/tests/test_captured_review_contract.py`.

Not changed: `probe_advanced_questions.py` already keeps the upgrade reason, `model_seconds` and template time
apart. It does not mark a discarded `/api/ask` reply as cancelled, but each probe question uses its own session, so
that reply only occurs if something else reuses the session. Left as is.

## Checks

Dependencies were missing in the container (no `pytest`, `httpx` or `numpy` for `python3`). With the owner's
approval they were installed into a throwaway virtualenv in the session scratchpad from
`apps/backend/requirements.txt`; nothing in the repository, CI or system Python changed.

- Before the change: 138 passed across the latency, probe, swap, telemetry, upgrade, phase and admission tests.
- New tests: 15 in `test_measure_chat_latency.py`, 1 in `test_captured_review_contract.py`; 13 of them failed
  before the change (the two real-timeout cases passed before and stay as guards). Reverting only
  `build_captured_review_packet.py` fails its new test.
- After: 265 passed across the 14 related test files.
- Full backend suite (`KENN_LIVE_BACKEND=fake`): 4795 passed, 137 skipped, 2 failed. Both are outside the touched
  files. `test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`
  fails identically on a clean checkout of `main` at `a05c04a` (routes to `unknown`; this container has no
  git-ignored index). `test_latency_budget.py::test_tier1_short_circuit_sub_millisecond` holds a 2 ms wall-clock
  budget; it failed under full-suite load and passed alone three times on this tree and once on `main`.

## Remaining C1 gates (local, owner-supervised)

- At least 30 questions per surface on the M3/16 GB with the current 4B model: stream, foreground and background
  as separate runs, each repeated, with cold and warm declared.
- Model digest, index and code identity in the receipt (manifest below).
- Memory pressure and swap readings across the run; audio dropouts at a fixed Live buffer and session, recorded by
  the owner.
- The Live-open/closed comparison only under controlled, supervised conditions, with FakeLive and no writes.
- Admission/queue, retrieval, verification and displayed-result timing remain unknown in the tooling; the plan's
  C2 items own instrumenting them. The receipts will say `None` for them.

## Commands for the local session

Run from the main checkout on the Mac (the index under `apps/backend/src/kenn/data/` is git-ignored). Plug in
power first; the 4 and 5 Oct probe runs on battery were unusable. Keep receipts outside git unless they are being
committed as evidence, and keep `--capture-answers`/`--review-capture` files out of git.

```bash
cd ~/path/to/monorepo/products/kenn
export KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=1 KENN_LLM_PROVIDER=ollama \
       KENN_LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M KENN_LLM_CACHE=0
OUT=.runtime/c1-$(date +%Y-%m-%d); mkdir -p "$OUT"

# 1. Pin the build: model digest from Ollama, plus hardware. Model-cold vs warm: record `ollama ps` before run 1.
curl -s http://127.0.0.1:11434/api/tags > "$OUT/ollama-tags.json"
ollama ps > "$OUT/ollama-ps-before.txt"
python3 - "$OUT" <<'PY'
import json, subprocess, sys
out = sys.argv[1]
tags = json.load(open(f"{out}/ollama-tags.json"))["models"]
digest = next(m["digest"] for m in tags if m["name"] == "qwen3:4b-instruct-2507-q4_K_M")
sh = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.strip()
json.dump({"model_digest": digest, "ollama_version": sh("ollama", "--version"),
           "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"), "memory_bytes": int(sh("sysctl", "-n", "hw.memsize")),
           "live_buffer_samples": None, "live_open": None, "supervised_by": None},
          open(f"{out}/manifest.json", "w"), indent=1)
PY
# Fill live_buffer_samples, live_open and supervised_by by hand before the Live-open runs.

# 2. Stream surface, in-process, cold then warm, each twice.
for cond in cold warm; do for rep in 1 2; do
  python3 tooling/scripts/measure_chat_latency.py --limit 30 --surface stream --cache-condition $cond \
    --build-manifest "$OUT/manifest.json" --receipt "$OUT/stream-$cond-$rep.json"
done; done

# 3. Foreground HTTP. Start the companion yourself with KENN_LLM_CACHE=0 and KENN_LLM_BACKGROUND=0:
#    with background on, /api/ask answers allow_llm=False and the foreground run is templates-only.
python3 tooling/scripts/measure_chat_latency.py --limit 30 --surface foreground --endpoint http://127.0.0.1:8090 \
  --cache-condition warm --timeout 90 --build-manifest "$OUT/manifest.json" --receipt "$OUT/foreground-1.json"

# 4. Background HTTP. Restart the companion yourself with KENN_LLM_CACHE=0 and KENN_LLM_BACKGROUND=1.
python3 tooling/scripts/measure_chat_latency.py --limit 30 --surface background --endpoint http://127.0.0.1:8090 \
  --cache-condition warm --timeout 90 --build-manifest "$OUT/manifest.json" --receipt "$OUT/background-1.json"
# Repeat 3 and 4 once more each (-2.json). HTTP runs cannot clear the companion's semantic cache, so they are
# declared warm and the receipt marks server_cache_condition_verified=false.

ollama ps > "$OUT/ollama-ps-after.txt"
```

What to read off each receipt: `counts.delivery` (accepted/rejected/timeout/cancelled/error/not_attempted),
`counts.eligible_accepted_within_15_seconds` against 70% of 30, `seconds.ttft_*` beside `seconds.all_*`,
`top_rejection_reason`, `provenance.cache_settings.response_cache_enabled` (must be `false` on stream runs),
`provenance.resolved_models`, and per row `swap_bytes`, `memory_pressure`, `server_timing_ms`,
`server_upgrade_seconds`. Audio dropouts, and whether Live was open, are written down by hand during the session.
