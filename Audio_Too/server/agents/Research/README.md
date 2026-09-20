# Research Agent (Autonomous)

The Research agent is now fully autonomous, powered by Qwen Coder via the CodingAgent.

## Usage

```bash
# Run generic task
python -m business.agents.Research run "Analyze competitor pricing models"

# Specialized tasks
python -m business.agents.Research topic "spatial audio mixing" --depth deep
python -m business.agents.Research trends "AI in music production"
python -m business.agents.Research report "2026 audio tech landscape"
python -m business.agents.Research benchmark "StudioA" "StudioB"

# Memory
python -m business.agents.Research memory
```

## As Library

```python
from business.agents.Research.agent_loop import ResearchAgent

agent = ResearchAgent()
result = agent.research_topic("immersive audio")
print(result["success"])
```

## Architecture

- Inherits from `Shared/autonomous_base.py` `AutonomousAgent`
- Uses CodingAgent for planning/execution
- Persistent memory in `.agent_memory/`
- Git integration for rollback