# What a cancelled chat does to the model slot, measured on the real model — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and closes the "actual inference cancellation remains
unqualified" limit from the route-map work. It measures the behavior; it does not change it.

## What was measured

The box bridge (`tooling/scripts/serve_transformers_ollama_compat.py`, byte-identical to the box copy, sha256
`fa951adf…`) served Qwen3-4B-input-bound-v6 on GPU 0 of the shared box, reached over an SSH tunnel on port 11435.
The bridge is non-streaming and takes one generation at a time. A second request while one runs gets HTTP 429.

A probe sent the same long request KENN's answer path would send (1,024 new tokens allowed), closed the socket
2 s in, as a client that stops waiting does, then retried a short request every second.

| Measurement | Result |
| --- | --- |
| Short request (16 tokens) on an idle bridge | 1.1, 1.3, 1.2 s |
| Long request left to finish | 58.0 s, 4,673 characters |
| Slot busy after the client closed at 2 s | 45.5 s, 30 requests refused with 429 |

So the model finishes the whole generation after the client is gone. Closing the connection does not stop it and
nothing frees the slot early. Any chat or planner call behind the same bridge waits that long, or is refused.

## What this means for KENN's cancel

KENN's cancel and discard paths revoke Apply tokens and drop the late answer, and say so with
`inference_aborted: false` (`core/chat_answer.py`, `server.py`; pinned by
`test_cancel_stream_reports_its_revocation_instead_of_discarding_its_own_reply`). Nothing in them talks to the model
client. This measurement shows the cost of that on this bridge: a cancelled long answer blocks the next turn for up
to the rest of the generation, about 45 s here, not just the instant it takes to ignore the reply.

## Open finding (not changed)

Real cancellation needs two changes together: the bridge has to check a stop flag between tokens (a
`StoppingCriteria` in the `generate` call) and KENN has to signal it, for example by closing the connection and the
bridge noticing the dead socket. That is a behavior change on the bridge, whose source hash the real-Live task
checks, so it is a decision, not a drive-by edit. No change was made.

## Limits

- One run, one prompt, one GPU, on a shared box where other jobs may have affected timing. The 58 s and 45.5 s
  figures are indicative, not a benchmark.
- The probe talked to the bridge directly. It did not drive KENN's full stream-and-cancel route, so the end-to-end
  turn-blocking time through the companion was not measured.
- Nothing was run against real Live, and no source audio went to the box.
- The bridge and tunnel were stopped afterwards: no `serve_transformers` process on the box, GPUs 0 and 1 back at
  1 MiB, no local tunnel. The log is at `/mnt/data/kenn-bakeoff/logs/cancel-qual-20261002.log` on the box.

## Exact changed files

Paths are relative to `products/kenn`.

- `docs/evidence/KENN_INFERENCE_CANCELLATION_MEASURED_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 sub-bullet.
