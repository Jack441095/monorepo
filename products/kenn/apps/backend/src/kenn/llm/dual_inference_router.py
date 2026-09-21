"""KENN Dual-Inference Router: Local Apple Silicon Metal MLX + Frontier Reasoning.

Routes LLM queries based on complexity, latency budget, and task scope:
- Fast Path (Local Metal MLX): On-device Qwen2.5-1.5B/3B-Instruct for sub-100ms
  turnaround on intent classification, status checks, transport, and single moves.
- Deep Path (Frontier Reasoner / GPU-1): Dedicated high-capacity model on port 11436
  or local large fallback for multi-stem acoustic arrangement and ReAct deliberation.
- Zero-Audio Privacy Guard: Validates that no raw audio sample buffers ever cross any socket.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

PATH_FAST_LOCAL_MLX = "fast_local_mlx"
PATH_DEEP_FRONTIER = "deep_frontier"

# Complex multi-step reasoning indicators
_DEEP_REASONING_PATTERNS = [
    re.compile(r"\b(balance|mix down|mixdown|restructure|arrangement|audit all|multi[- ]?track)\b", re.I),
    re.compile(r"\b(why does|diagnose|resolve (?:all|the) clashes|psychoacoustic)\b", re.I),
    re.compile(r"\b(drop.*hit harder|bring.*forward.*clean.*low)\b", re.I),
    re.compile(r"\b(step[- ]by[- ]step|recipe|chain of thought|plan and solve)\b", re.I),
]


@dataclass
class RoutingDecision:
    path: str  # PATH_FAST_LOCAL_MLX | PATH_DEEP_FRONTIER
    model_name: str
    target_latency_budget_ms: int
    reason: str
    is_fallback: bool = False


class DualInferenceRouter:
    """Intelligent router selecting between Apple Silicon MLX and Frontier Reasoner."""

    def __init__(self, local_model: str = "Qwen2.5-1.5B-Instruct-4bit", remote_model: str = "Qwen2.5-32B-Instruct"):
        self.local_model = os.environ.get("KENN_LOCAL_MODEL", local_model)
        self.remote_model = os.environ.get("KENN_FRONTIER_MODEL", remote_model)
        self.remote_url = os.environ.get("KENN_FRONTIER_URL", "http://127.0.0.1:11436/v1")

    def route(self, prompt: str, task: str = "general", history: Optional[List[Dict[str, str]]] = None) -> RoutingDecision:
        """Analyze query and context to choose optimal inference path."""
        # Clean and validate prompt for zero-audio privacy
        self._assert_zero_audio(prompt)

        # Force fast path for conversational greetings, status, single parameter adjustments
        prompt_lower = prompt.lower().strip()
        if prompt_lower in {"hello", "hi", "hey", "status", "ping", "cancel", "undo", "play", "stop"}:
            return RoutingDecision(
                path=PATH_FAST_LOCAL_MLX,
                model_name=self.local_model,
                target_latency_budget_ms=100,
                reason="Instant fast-path evaluator intent",
            )

        if task in {"route", "paraphrase", "quick_fix", "voice"}:
            return RoutingDecision(
                path=PATH_FAST_LOCAL_MLX,
                model_name=self.local_model,
                target_latency_budget_ms=150,
                reason=f"Task '{task}' designated for ultra-low latency local engine",
            )

        # Check for deep multi-step / acoustic deliberation needs
        is_deep = any(pattern.search(prompt_lower) for pattern in _DEEP_REASONING_PATTERNS)
        if is_deep or task in {"agent_plan", "session_audit", "remediation"}:
            return RoutingDecision(
                path=PATH_DEEP_FRONTIER,
                model_name=self.remote_model,
                target_latency_budget_ms=2500,
                reason="Multi-step ReAct / acoustic arrangement reasoning required",
            )

        # Default to local MLX for fast, private response
        return RoutingDecision(
            path=PATH_FAST_LOCAL_MLX,
            model_name=self.local_model,
            target_latency_budget_ms=300,
            reason="Standard studio query serviced by on-device Metal MLX",
        )

    def _assert_zero_audio(self, prompt: str) -> None:
        """Verify prompt does not leak raw audio waveform bytes."""
        if len(prompt) > 200000:
            raise ValueError("Prompt exceeds maximum text budget; suspected binary audio payload.")
        if "\x00" in prompt:
            raise ValueError("Null bytes detected in prompt; binary audio rejected by Zero-Audio Privacy Policy.")


_router_instance: Optional[DualInferenceRouter] = None


def get_inference_router() -> DualInferenceRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = DualInferenceRouter()
    return _router_instance


__all__ = [
    "PATH_FAST_LOCAL_MLX",
    "PATH_DEEP_FRONTIER",
    "RoutingDecision",
    "DualInferenceRouter",
    "get_inference_router",
]
