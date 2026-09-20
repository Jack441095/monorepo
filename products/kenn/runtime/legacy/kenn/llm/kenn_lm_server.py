"""Persistent MLX model server for KENN's fine-tuned LM.

Runs under the native arm64 Python (see kenn_lm.py's _MLX_CMD) and loads the
MLX model exactly once for the life of the process, instead of the previous
pattern where every single generation call spawned a fresh subprocess that
re-loaded the full model from disk — up to 3x per answer turn with
self_correct=True (initial generation + critique + possible regeneration).
See docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md.

Protocol: newline-delimited JSON over a Unix domain socket. One request per
line in, one JSON response per line out. Deliberately not HTTP — no need for
a framework for a single local client, and a Unix socket avoids picking a
TCP port. Single-threaded/sequential by design: MLX generation on one model
instance isn't meant for concurrent calls, and this serves one user.
"""

from __future__ import annotations

import json
import os
import socketserver
import sys
import threading
import time


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: kenn_lm_server.py <model_path> <socket_path>", file=sys.stderr)
        return 1
    model_path, socket_path = sys.argv[1], sys.argv[2]

    from mlx_lm import load, generate, stream_generate

    print(f"Loading MLX model from {model_path}...", file=sys.stderr, flush=True)
    started = time.perf_counter()
    model, tokenizer = load(model_path)
    print(f"Model loaded in {time.perf_counter() - started:.1f}s. Ready.", file=sys.stderr, flush=True)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            line = self.rfile.readline()
            if not line:
                return
            try:
                job = json.loads(line.decode("utf-8"))
                if job.get("op") == "ping":
                    response = {"ok": True}
                    self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                    self.wfile.flush()
                elif job.get("op") == "shutdown":
                    response = {"ok": True, "status": "shutting down"}
                    self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                    self.wfile.flush()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                else:
                    prompt = tokenizer.apply_chat_template(
                        job["messages"], tokenize=False, add_generation_prompt=True
                    )
                    max_tokens = int(job.get("max_new_tokens", 220))
                    stop_markers = ("\n\nQuestion:", "\n\nContext:", "\n\nHuman:", "\n\nAssistant:")

                    if job.get("stream"):
                        collected = []
                        stopped = False
                        for resp in stream_generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens):
                            token_text = resp.text
                            collected.append(token_text)
                            current_full = "".join(collected)
                            for sm in stop_markers:
                                if sm in current_full:
                                    stopped = True
                                    break
                            if stopped:
                                break
                            chunk = json.dumps({"ok": True, "token": token_text}) + "\n"
                            self.wfile.write(chunk.encode("utf-8"))
                            self.wfile.flush()

                        final_text = "".join(collected)
                        for sm in stop_markers:
                            if sm in final_text:
                                final_text = final_text.split(sm)[0]
                        final_text = final_text.strip()
                        done_chunk = json.dumps({"ok": True, "done": True, "text": final_text}) + "\n"
                        self.wfile.write(done_chunk.encode("utf-8"))
                        self.wfile.flush()
                        return
                    else:
                        text = generate(
                            model,
                            tokenizer,
                            prompt=prompt,
                            max_tokens=max_tokens,
                            verbose=False,
                        )
                        # Clean truncation if model generates synthetic runaway turns
                        for stop_marker in stop_markers:
                            if stop_marker in text:
                                text = text.split(stop_marker)[0].strip()
                        response = {"ok": True, "text": text}
                        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                        self.wfile.flush()
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
                self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                self.wfile.flush()

    if os.path.exists(socket_path):
        os.unlink(socket_path)
    with socketserver.UnixStreamServer(socket_path, Handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
