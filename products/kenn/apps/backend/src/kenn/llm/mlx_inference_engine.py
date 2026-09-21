"""KENN Apple Silicon MLX Neural Inference Engine.

Provides ultra-low-latency on-device LLM reasoning using Apple Silicon Metal unified memory
via mlx_lm. Eliminates network round-trips for sub-300ms time-to-first-token.
"""

from __future__ import annotations

import os
import platform
import sys
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_MLX_MODEL = os.environ.get(
    "KENN_MLX_MODEL", "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
)
DEFAULT_CACHE_LIMIT_MB = int(os.environ.get("KENN_MLX_MAX_MEMORY_MB", "2048"))


DEFAULT_STOP_SEQUENCES = [
    "\nUser:", "User:", "Human:", "Ableton>", "###", "<|im_end|>", "<|im_start|>"
]


class MLXInferenceEngine:
    """Manages loaded MLX model weights and executes local inference on Apple Silicon."""

    _instance: Optional[MLXInferenceEngine] = None
    _lock = threading.Lock()

    def __init__(self, model_id: str = DEFAULT_MLX_MODEL):
        self.model_id = model_id
        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._prewarmed = False
        self._pinned_prompt_cache: Optional[List[Any]] = None
        self._pinned_prefix_text: str = ""
        self._pinned_prefix_size: int = 0
        self._load_lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._configure_metal_guardrails()

    def _configure_metal_guardrails(self) -> None:
        """Limit Metal cache memory so Ableton Live audio threads are protected."""
        if not self.is_available():
            return
        try:
            import mlx.core as mx
            limit_bytes = DEFAULT_CACHE_LIMIT_MB * 1024 * 1024
            if hasattr(mx, "set_cache_limit"):
                mx.set_cache_limit(limit_bytes)
            elif hasattr(mx, "metal") and hasattr(mx.metal, "set_cache_limit"):
                mx.metal.set_cache_limit(limit_bytes)
        except Exception:
            pass

    @classmethod
    def get_instance(cls, model_id: str = DEFAULT_MLX_MODEL) -> MLXInferenceEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(model_id=model_id)
            return cls._instance

    @staticmethod
    def is_available() -> bool:
        """Check if platform is macOS Apple Silicon with mlx_lm installed."""
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return False
        try:
            import mlx.core
            import mlx_lm
            return True
        except ImportError:
            return False

    def create_prompt_cache(self) -> Optional[List[Any]]:
        """Create a fresh KV prompt cache for the current loaded model."""
        if not self.load_model():
            return None
        try:
            from mlx_lm.models.cache import make_prompt_cache
            return make_prompt_cache(self._model)
        except Exception:
            return None

    def get_memory_stats(self) -> Dict[str, Any]:
        """Return real-time Apple Silicon Metal memory usage."""
        if not self.is_available():
            return {"available": False, "reason": "Not Apple Silicon or mlx not installed"}
        try:
            import mlx.core as mx
            active = mx.get_active_memory() if hasattr(mx, "get_active_memory") else (
                mx.metal.get_active_memory() if hasattr(mx, "metal") and hasattr(mx.metal, "get_active_memory") else 0
            )
            peak = mx.get_peak_memory() if hasattr(mx, "get_peak_memory") else (
                mx.metal.get_peak_memory() if hasattr(mx, "metal") and hasattr(mx.metal, "get_peak_memory") else 0
            )
            cache = mx.get_cache_memory() if hasattr(mx, "get_cache_memory") else (
                mx.metal.get_cache_memory() if hasattr(mx, "metal") and hasattr(mx.metal, "get_cache_memory") else 0
            )
            return {
                "available": True,
                "active_mb": round(active / (1024 * 1024), 2),
                "peak_mb": round(peak / (1024 * 1024), 2),
                "cache_mb": round(cache / (1024 * 1024), 2),
                "model_loaded": self._loaded,
                "prewarmed": self._prewarmed,
            }
        except Exception as err:
            return {"available": True, "error": str(err)}

    def pin_system_prompt(self, system_prompt: str) -> bool:
        """Pre-compute and pin the static system prompt KV cache in Unified Memory."""
        if not self.load_model():
            return False
        with self._generation_lock:
            try:
                from mlx_lm import generate
                from mlx_lm.models.cache import make_prompt_cache
                cache = make_prompt_cache(self._model)
                prefix_text = f"<|im_start|>system\n{system_prompt.strip()}<|im_end|>\n"
                generate(self._model, self._tokenizer, prompt=prefix_text, max_tokens=1, prompt_cache=cache, verbose=False)
                self._pinned_prompt_cache = cache
                self._pinned_prefix_text = prefix_text
                self._pinned_prefix_size = cache[0].size() if hasattr(cache[0], "size") and callable(cache[0].size) else 0
                return True
            except Exception as exc:
                print(f"[!] Failed to pin system prompt in MLX: {exc}", file=sys.stderr)
                self._pinned_prompt_cache = None
                self._pinned_prefix_text = ""
                self._pinned_prefix_size = 0
                return False

    def prewarm(self, blocking: bool = False) -> bool:
        """Pre-warm model weights and compile Apple Metal shaders ahead of time."""
        def _run_prewarm() -> bool:
            t0 = time.perf_counter()
            if self.load_model():
                try:
                    dummy_prompt = "<|im_start|>system\nYou are KENN.<|im_end|>\n<|im_start|>user\nHi<|im_end|>\n<|im_start|>assistant\n"
                    self.generate(dummy_prompt, max_tokens=1)
                    # Pin the immutable senior studio engineer static persona prompt
                    try:
                        from kenn.llm.llm_rewrite import STATIC_CORE_SYSTEM_PROMPT
                        self.pin_system_prompt(STATIC_CORE_SYSTEM_PROMPT)
                    except Exception as pin_err:
                        print(f"[!] Warning: failed to pin STATIC_CORE_SYSTEM_PROMPT: {pin_err}", file=sys.stderr)
                    self._prewarmed = True
                    elapsed = time.perf_counter() - t0
                    pinned_info = f" with {self._pinned_prefix_size} prefix tokens pinned" if self._pinned_prefix_size else ""
                    print(f"[✓] KENN MLX Apple Silicon Engine pre-warmed in {elapsed:.2f}s (Metal GPU active{pinned_info}).")
                    return True
                except Exception as err:
                    print(f"[!] KENN MLX prewarm error: {err}", file=sys.stderr)
            return False

        if blocking:
            return _run_prewarm()
        else:
            t = threading.Thread(target=_run_prewarm, daemon=True, name="KENN-MLX-Prewarm")
            t.start()
            return True

    def load_model(self) -> bool:
        """Load model weights into unified Apple Silicon RAM."""
        if self._loaded and self._model is not None:
            return True

        if not self.is_available():
            return False

        with self._load_lock:
            if self._loaded:
                return True
            try:
                from mlx_lm import load
                from pathlib import Path
                # Check for cached local snapshot to eliminate HF Hub network latency
                cached_hub = Path.home() / ".cache/huggingface/hub"
                repo_dir_name = "models--" + self.model_id.replace("/", "--")
                snapshots_dir = cached_hub / repo_dir_name / "snapshots"
                load_target = self.model_id
                if snapshots_dir.is_dir():
                    snapshots = sorted([s for s in snapshots_dir.iterdir() if s.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
                    if snapshots:
                        load_target = str(snapshots[0])
                self._model, self._tokenizer = load(load_target)
                self._loaded = True
                return True
            except Exception as err:
                print(f"[!] Failed to load MLX model '{self.model_id}': {err}", file=sys.stderr)
                return False

    def format_chat_prompt(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Format messages using ChatML syntax (<|im_start|> ... <|im_end|>)."""
        prompt_parts: List[str] = []
        if system_prompt:
            prompt_parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")

        prompt_parts.append("<|im_start|>assistant\n")
        return "".join(prompt_parts)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.2,
        prompt_cache: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Generate full completion synchronously."""
        if not self.load_model():
            raise RuntimeError("MLX model failed to load or environment is unsupported.")

        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=temperature)
        t0 = time.perf_counter()

        use_pinned = False
        active_cache = prompt_cache
        if (
            active_cache is None
            and self._pinned_prompt_cache is not None
            and self._pinned_prefix_text
            and prompt.startswith(self._pinned_prefix_text)
        ):
            active_cache = self._pinned_prompt_cache
            use_pinned = True

        gen_kwargs: Dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "sampler": sampler,
            "verbose": False,
        }
        if active_cache is not None:
            gen_kwargs["prompt_cache"] = active_cache

        acquired = self._generation_lock.acquire(timeout=30.0)
        if not acquired:
            raise TimeoutError("MLX generation lock acquisition timed out.")
        before_size = 0
        try:
            if use_pinned and active_cache is not None and hasattr(active_cache[0], "size") and callable(active_cache[0].size):
                before_size = active_cache[0].size()
            text = generate(
                self._model,
                self._tokenizer,
                **gen_kwargs,
            )
        finally:
            if use_pinned and active_cache is not None:
                try:
                    from mlx_lm.models.cache import trim_prompt_cache
                    curr_size = active_cache[0].size() if hasattr(active_cache[0], "size") and callable(active_cache[0].size) else 0
                    if curr_size > before_size:
                        trim_prompt_cache(active_cache, curr_size - before_size)
                except Exception:
                    pass
            self._generation_lock.release()

        elapsed_s = time.perf_counter() - t0
        token_estimate = len(text.split()) * 1.3
        tok_per_sec = token_estimate / elapsed_s if elapsed_s > 0 else 0.0

        return {
            "text": text.strip(),
            "latency_ms": round(elapsed_s * 1000, 2),
            "tokens_per_second": round(tok_per_sec, 1),
            "engine": "apple_silicon_mlx",
            "model": self.model_id,
            "prefix_pinned": use_pinned,
        }

    def stream_generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.2,
        prompt_cache: Optional[List[Any]] = None,
        stop_sequences: Optional[List[str]] = None,
    ) -> Iterator[str]:
        """Stream token chunks with prefix KV cache reuse and strict stop sequences."""
        if not self.load_model():
            raise RuntimeError("MLX model failed to load.")

        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        stops = stop_sequences if stop_sequences is not None else DEFAULT_STOP_SEQUENCES
        sampler = make_sampler(temp=temperature)

        use_pinned = False
        active_cache = prompt_cache
        if (
            active_cache is None
            and self._pinned_prompt_cache is not None
            and self._pinned_prefix_text
            and prompt.startswith(self._pinned_prefix_text)
        ):
            active_cache = self._pinned_prompt_cache
            use_pinned = True

        gen_kwargs: Dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "sampler": sampler,
        }
        if active_cache is not None:
            gen_kwargs["prompt_cache"] = active_cache

        acquired = self._generation_lock.acquire(timeout=30.0)
        if not acquired:
            raise TimeoutError("MLX generation lock acquisition timed out.")
        before_size = 0
        try:
            if use_pinned and active_cache is not None and hasattr(active_cache[0], "size") and callable(active_cache[0].size):
                before_size = active_cache[0].size()

            buffer = ""
            stopped = False
            for response in stream_generate(
                self._model,
                self._tokenizer,
                **gen_kwargs,
            ):
                token = response.text if hasattr(response, "text") else (response if isinstance(response, str) else "")
                if not token:
                    continue
                buffer += token

                for stop_seq in stops:
                    if stop_seq in buffer:
                        idx = buffer.index(stop_seq)
                        cut = buffer[:idx]
                        if cut:
                            yield cut
                        stopped = True
                        break
                if stopped:
                    break

                # Check if buffer ends with a partial prefix of any stop sequence
                has_partial = False
                for stop_seq in stops:
                    for i in range(1, len(stop_seq)):
                        if buffer.endswith(stop_seq[:i]):
                            has_partial = True
                            break
                    if has_partial:
                        break

                if not has_partial:
                    yield buffer
                    buffer = ""

            if buffer and not stopped:
                yield buffer
        finally:
            if use_pinned and active_cache is not None:
                try:
                    from mlx_lm.models.cache import trim_prompt_cache
                    curr_size = active_cache[0].size() if hasattr(active_cache[0], "size") and callable(active_cache[0].size) else 0
                    if curr_size > before_size:
                        trim_prompt_cache(active_cache, curr_size - before_size)
                except Exception:
                    pass
            self._generation_lock.release()


__all__ = ["MLXInferenceEngine", "DEFAULT_MLX_MODEL"]
