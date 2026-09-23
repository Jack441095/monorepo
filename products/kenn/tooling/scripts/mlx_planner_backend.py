"""Serve KENN's planner calls from an in-process mlx-lm model (evaluation only).

``install(model, adapter)`` replaces ``llm_rewrite._chat_completion`` so
``live_command._generate_llm_plan`` (real system prompt, validator, repair)
runs against a base model or a LoRA adapter without a model server. Thinking
is off (the chat template's ``enable_thinking=False``, the same empty think
block KENN serves through Ollama). Decoding is greedy and not
schema-constrained, so the validator sees exactly what the model wrote.
Nothing here ships in KENN.
"""

from __future__ import annotations

import time
from typing import Any


def install(model_path: str, adapter_path: str | None = None, *, max_tokens: int = 256) -> None:
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler

    from kenn.llm import llm_rewrite

    model, tokenizer = load(model_path, adapter_path=adapter_path)
    sampler = make_sampler(temp=0.0)
    label = model_path + (f"+{adapter_path}" if adapter_path else "")

    def chat_completion(messages: list[dict[str, str]], task: str = "rewrite", *, system_prompt: str | None = None,
                        **_kwargs: Any) -> tuple[str, Any]:
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + [
                m for m in messages if m.get("role") != "system"]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                               enable_thinking=False)
        started = time.perf_counter()
        text = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
        usage = llm_rewrite.LLMUsage(model=label, provider="mlx-eval", task=task,
                                     prompt_tokens=len(tokenizer.encode(prompt)),
                                     completion_tokens=len(tokenizer.encode(text)),
                                     total_tokens=0, latency_ms=int((time.perf_counter() - started) * 1000))
        return text.strip(), usage

    llm_rewrite._chat_completion = chat_completion
    llm_rewrite.is_enabled = lambda task="rewrite": True


__all__ = ["install"]
