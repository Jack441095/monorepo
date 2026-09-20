#!/usr/bin/env python3
"""Serve one local Transformers checkpoint through KENN's Ollama chat subset.

This is a disposable, loopback-only qualification process. It does not install,
restart, or modify Ollama or any system service. Model and cache paths must stay
under the declared data root.
"""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import traceback
from threading import Lock
from typing import Any


ALLOWED_GPU_SELECTION = "1,2,3,4"
MAX_INPUT_TOKENS = 8_192
CACHE_ENVIRONMENT = {
    "HF_HOME": Path("huggingface"),
    "HF_HUB_CACHE": Path("huggingface/hub"),
    "TRANSFORMERS_CACHE": Path("huggingface/transformers"),
}


def validate_configuration(*, host: str, model_path: Path, data_root: Path, cuda_devices: str | None = None) -> tuple[Path, Path]:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("The qualification endpoint must bind to loopback only.")
    if cuda_devices is None:
        cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_devices != ALLOWED_GPU_SELECTION:
        raise ValueError(f"CUDA_VISIBLE_DEVICES must be exactly {ALLOWED_GPU_SELECTION}.")
    root = data_root.expanduser().resolve()
    model = model_path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Data root does not exist: {root}")
    try:
        relative_model = model.relative_to(root)
    except ValueError as exc:
        raise ValueError("Model path must stay below the declared data root.") from exc
    if relative_model == Path("."):
        raise ValueError("Model path must be a dedicated directory below the declared data root.")
    if not model.is_dir():
        raise ValueError(f"Model path does not exist: {model}")
    return model, root


def configure_cache_environment(data_root: Path) -> dict[str, str]:
    """Pin every Hugging Face cache used by this process below data_root."""
    root = data_root.expanduser().resolve()
    configured = {name: str(root / relative) for name, relative in CACHE_ENVIRONMENT.items()}
    os.environ.update(configured)
    return configured


def generate_reply(*, model: Any, tokenizer: Any, torch: Any, messages: list[dict[str, Any]], max_tokens: int) -> str:
    clean_messages = [
        {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
        for item in messages if isinstance(item, dict)
    ]
    if not clean_messages or not clean_messages[-1]["content"].strip():
        raise ValueError("A non-empty final chat message is required.")
    template_options = {
        "tokenize": True, "add_generation_prompt": True,
        "return_tensors": "pt", "enable_thinking": False,
    }
    try:
        template = tokenizer.apply_chat_template(clean_messages, **template_options)
    except TypeError:
        template_options.pop("enable_thinking")
        template = tokenizer.apply_chat_template(clean_messages, **template_options)
    moved = template.to(model.device)
    if hasattr(moved, "keys"):
        if "input_ids" not in moved:
            raise ValueError("Tokenizer batch did not contain input_ids.")
        model_inputs = {key: moved[key] for key in moved.keys()}
        input_ids = model_inputs["input_ids"]
    else:
        input_ids = moved
        model_inputs = {"input_ids": input_ids}
    input_length = int(input_ids.shape[-1])
    if input_length > MAX_INPUT_TOKENS:
        raise ValueError(
            f"Tokenized prompt exceeds the {MAX_INPUT_TOKENS}-token qualification limit."
        )
    with torch.inference_mode():
        generated = model.generate(
            **model_inputs,
            max_new_tokens=max(128, min(1_024, int(max_tokens))),
            do_sample=False,
            use_cache=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(generated[0, input_length:], skip_special_tokens=True).strip()


class GenerationBusyError(RuntimeError):
    """Raised when the single qualified GPU generation slot is occupied."""


def generate_reply_exclusive(*, generation_lock: Lock, **kwargs: Any) -> str:
    """Run one generation without accumulating blocked request threads."""
    if not generation_lock.acquire(blocking=False):
        raise GenerationBusyError("The qualification model is already generating.")
    try:
        return generate_reply(**kwargs)
    finally:
        generation_lock.release()


def make_handler(
    *, model: Any, tokenizer: Any, torch: Any, model_id: str,
    generation_lock: Lock, source_sha256: str,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KENNTransformersQualification/1"

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/tags":
                self._json(200, {
                    "models": [{"name": model_id, "model": model_id}],
                    "kenn_transport": {
                        "schema": "kenn.transformers_ollama_compat.v1",
                        "source_sha256": source_sha256,
                    },
                })
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/chat":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_048_576:
                    raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(length))
                if payload.get("model") != model_id:
                    raise ValueError("Requested model does not match this qualified endpoint.")
                options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
                content = generate_reply_exclusive(
                        generation_lock=generation_lock,
                        model=model, tokenizer=tokenizer, torch=torch,
                        messages=payload.get("messages") or [],
                        max_tokens=int(options.get("num_predict", 320)),
                )
                self._json(200, {"model": model_id, "message": {"role": "assistant", "content": content}, "done": True})
            except GenerationBusyError as exc:
                encoded = json.dumps({"error": str(exc)}, separators=(",", ":")).encode("utf-8")
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "1")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:  # Keep provider details off the wire.
                print(f"Inference failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
                self._json(500, {"error": f"inference failed: {type(exc).__name__}"})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument(
        "--cuda-devices",
        default=ALLOWED_GPU_SELECTION,
        help=(
            "Comma-separated NVIDIA device IDs to expose to this process via "
            "CUDA_VISIBLE_DEVICES. Defaults to the qualification pool "
            f"({ALLOWED_GPU_SELECTION}). Set explicitly to repin a test run, "
            "e.g. --cuda-devices 1,2. NOTE: the inference server that KENN's "
            "plugin talks to is pinned to GPU 0 and is NOT touched by this flag."
        ),
    )
    args = parser.parse_args()
    # Honor an explicit repin so a second qualifier instance can run on a
    # different device slice without colliding with the GPU-0 inference server.
    os.environ["CUDA_VISIBLE_DEVICES"] = args.cuda_devices
    model_path, data_root = validate_configuration(
        host=args.host, model_path=args.model_path, data_root=args.data_root, cuda_devices=args.cuda_devices,
    )
    if not (1 <= args.port <= 65535):
        parser.error("port must be between 1 and 65535")
    model_id = str(args.model_id).strip()[:128]
    if not model_id:
        parser.error("model-id is required")
    configure_cache_environment(data_root)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False,
        torch_dtype="auto", device_map="auto",
    ).eval()
    handler = make_handler(
        model=model, tokenizer=tokenizer, torch=torch,
        model_id=model_id, generation_lock=Lock(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
