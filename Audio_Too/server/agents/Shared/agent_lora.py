#!/usr/bin/env python3
"""Optional LoRA adapter selection for agents.

This is intentionally lightweight. It does not run training.
It only maps agent names to adapter paths and exports/imports
Ollama model configs if adapters are present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ADAPTERS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "Coding_LLM" / "adapters"
AGENT_LORA_CONFIG = ADAPTERS_DIR / "agent_lora_config.json"


def _ensure_config() -> dict[str, Any]:
    if AGENT_LORA_CONFIG.exists():
        return json.loads(AGENT_LORA_CONFIG.read_text(encoding="utf-8"))
    return {"agents": {}}


def _save_config(cfg: dict[str, Any]) -> None:
    ADAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_LORA_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def register_agent_adapter(agent_name: str, adapter_path: str | Path, base_model: str | None = None) -> dict[str, Any]:
    cfg = _ensure_config()
    cfg.setdefault("agents", {})
    cfg["agents"][agent_name] = {
        "adapter_path": str(adapter_path),
        "base_model": base_model or cfg.get("default_base_model", "qwen2.5-coder:7b"),
    }
    _save_config(cfg)
    return cfg


def get_agent_adapter(agent_name: str) -> dict[str, Any] | None:
    cfg = _ensure_config()
    return cfg.get("agents", {}).get(agent_name)


def export_agent_ollama_modelfile(agent_name: str, model_name: str | None = None) -> Path | None:
    cfg = get_agent_adapter(agent_name)
    if not cfg:
        return None
    adapter_path = Path(cfg["adapter_path"])
    adapter_file = None
    for candidate in [adapter_path / "adapters.safetensors", *adapter_path.glob("*.safetensors")]:
        if candidate.exists():
            adapter_file = candidate
            break
    if adapter_file is None:
        return None
    base_model = cfg.get("base_model", "qwen2.5-coder:7b")
    modelfile = (
        f"FROM {base_model}\n"
        f"PARAMETER temperature 0.2\n"
        f"PARAMETER top_p 0.9\n"
        f"PARAMETER stop \"</s>\"\n"
        f"SYSTEM \"You are the {agent_name} agent for Audio_Too.\"\n"
        f"ADAPTER {adapter_file}\n"
    )
    out_path = adapter_path / f"Modelfile.{agent_name}"
    out_path.write_text(modelfile, encoding="utf-8")
    return out_path


def agent_ollama_create_command(agent_name: str) -> str | None:
    cfg = get_agent_adapter(agent_name)
    if not cfg:
        return None
    modelfile = export_agent_ollama_modelfile(agent_name)
    if modelfile is None:
        return None
    model_name = f"audio-too-{agent_name.lower()}"
    return f"cd {cfg['adapter_path']} && ollama create {model_name} -f {modelfile.name}"