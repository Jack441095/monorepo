#!/bin/bash
# Bootstrap all existing agents to be autonomous using MetaAgent
set -euo pipefail

ROOT="${1:-.}"
shift || true

echo "=== Bootstrapping All Agents ==="
echo "Root: $ROOT"

# Verify CodingAgent is ready
if [ ! -d "$ROOT/business/agents/CodingAgent" ]; then
    echo "ERROR: CodingAgent not found at $ROOT/business/agents/CodingAgent"
    exit 1
fi

# Verify Ollama is running
if ! curl -sf http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Ollama not running. Run: ollama serve"
    exit 1
fi

# Verify models pulled
if ! ollama list | grep -q "qwen2.5-coder:7b"; then
    echo "Pulling qwen2.5-coder:7b..."
    ollama pull qwen2.5-coder:7b
fi

export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE---keepalive}"
export AUDIO_TOO_AGENT_MODEL="${AUDIO_TOO_AGENT_MODEL:-qwen2.5-coder:7b}"
export AUDIO_TOO_AGENT_FAST_MODEL="${AUDIO_TOO_AGENT_FAST_MODEL:-qwen2.5-coder:1.5b}"

echo ""
echo "Step 1: Creating Shared/autonomous_base.py"
python -m business.agents.CodingAgent run \
    "Create Shared/autonomous_base.py with an AutonomousAgent mixin class that provides run_task(), generate_code(), review_file(), and memory integration. Import from CodingAgent. Follow project conventions: type hints, dataclasses, pathlib, logging." \
    --root "$ROOT"

echo ""
echo "Step 2: Bootstrapping Admin agent"
python -m business.agents.MetaAgent Admin --root "$ROOT"

echo ""
echo "Step 3: Bootstrapping Marketing agent"
python -m business.agents.MetaAgent Marketing --root "$ROOT"

echo ""
echo "Step 4: Bootstrapping Research agent"
python -m business.agents.MetaAgent Research --root "$ROOT"

echo ""
echo "=== Bootstrap Complete ==="
echo "Verify with:"
echo "  python -m business.agents.Admin --help"
echo "  python -m business.agents.Marketing --help"
echo "  python -m business.agents.Research --help"