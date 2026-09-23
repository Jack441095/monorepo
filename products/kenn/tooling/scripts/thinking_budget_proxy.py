#!/usr/bin/env python3
"""OpenAI-compatible proxy that bounds a reasoning model's thinking (bake-off tooling only).

Through Ollama's /v1 route, thinking models (DeepSeek-R1 distills, qwen3.5)
ignore ``reasoning_effort``/``think`` once a JSON schema is set and think until
the token cap, returning no answer. This proxy lets the planner bake-off run
KENN's real planner path against a bounded-thinking variant, chosen by a
model-name suffix:

    deepseek-r1:7b@nothink    empty think block prefilled, answer immediately
    deepseek-r1:7b@think128   think for at most 128 tokens, then close the
                              think block and decode the schema-bound answer

It renders the model family's chat template itself and calls Ollama's raw
/api/generate in two stages. Any model without a suffix is passed through to
the upstream /v1 unchanged. Nothing here ships in KENN.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

SUFFIX = re.compile(r"^(?P<model>.+)@(?:(?P<nothink>nothink)|think(?P<budget>\d+))$")
TEMPLATES = {
    # DeepSeek-R1 distills: the system prompt is plain text after BOS.
    "r1": {"bos": "<｜begin▁of▁sentence｜>", "system": "{content}", "user": "<｜User｜>{content}",
           "assistant": "<｜Assistant｜>{content}<｜end▁of▁sentence｜>", "open": "<｜Assistant｜><think>\n"},
    "qwen": {"bos": "", "system": "<|im_start|>system\n{content}<|im_end|>\n",
             "user": "<|im_start|>user\n{content}<|im_end|>\n",
             "assistant": "<|im_start|>assistant\n{content}<|im_end|>\n",
             "open": "<|im_start|>assistant\n<think>\n"},
}


def family(model: str) -> str:
    return "r1" if "deepseek-r1" in model else "qwen"


def render(messages: list[dict], fam: str) -> str:
    template = TEMPLATES[fam]
    parts = [template["bos"]]
    for message in messages:
        role = message.get("role")
        if role in ("system", "user", "assistant"):
            parts.append(template[role].format(content=message.get("content") or ""))
    parts.append(template["open"])
    return "".join(parts)


class Proxy(BaseHTTPRequestHandler):
    upstream = "http://127.0.0.1:11434"
    client = httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0))

    def log_message(self, *_args) -> None:  # quiet
        pass

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        response = self.client.get(self.upstream + self.path)
        self._send(response.status_code, response.json())

    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        match = SUFFIX.match(str(payload.get("model") or ""))
        if not self.path.endswith("/chat/completions") or not match:
            if match:  # e.g. KENN's keep-alive ping names the suffixed model
                payload["model"] = match.group("model")
            response = self.client.post(self.upstream + self.path, json=payload)
            self._send(response.status_code, response.json())
            return
        model = match.group("model")
        budget = 0 if match.group("nothink") else int(match.group("budget"))
        prompt = render(payload.get("messages") or [], family(model))
        options = {"temperature": payload.get("temperature", 0.0)}
        started = time.perf_counter()
        thinking, think_tokens, prompt_tokens = "", 0, 0
        if budget:
            first = self.client.post(self.upstream + "/api/generate", json={
                "model": model, "prompt": prompt, "raw": True, "stream": False,
                "options": {**options, "num_predict": budget, "stop": ["</think>"]},
            }).json()
            thinking, think_tokens = first.get("response") or "", int(first.get("eval_count") or 0)
            prompt_tokens = int(first.get("prompt_eval_count") or 0)
        answer_request = {
            "model": model, "prompt": prompt + thinking + "\n</think>\n\n", "raw": True, "stream": False,
            "options": {**options, "num_predict": int(payload.get("max_tokens") or 256)},
        }
        schema = ((payload.get("response_format") or {}).get("json_schema") or {}).get("schema")
        if schema is not None:
            answer_request["format"] = schema
        elif (payload.get("response_format") or {}).get("type") == "json_object":
            answer_request["format"] = "json"
        second = self.client.post(self.upstream + "/api/generate", json=answer_request).json()
        if "error" in second:
            self._send(500, {"error": {"message": second["error"]}})
            return
        completion = int(second.get("eval_count") or 0) + think_tokens
        self._send(200, {
            "id": "kenn-bakeoff", "object": "chat.completion", "model": payload.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": second.get("response") or "",
                                     "reasoning": thinking}}],
            "usage": {"prompt_tokens": prompt_tokens or int(second.get("prompt_eval_count") or 0),
                      "completion_tokens": completion, "total_tokens": completion + prompt_tokens,
                      "thinking_tokens": think_tokens},
            "kenn_proxy_ms": round((time.perf_counter() - started) * 1000.0, 1),
        })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upstream", default="http://127.0.0.1:11434", help="Ollama base URL (no /v1)")
    parser.add_argument("--port", type=int, default=11439)
    args = parser.parse_args()
    Proxy.upstream = args.upstream.rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Proxy)
    print(f"thinking-budget proxy on 127.0.0.1:{args.port} -> {Proxy.upstream}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
