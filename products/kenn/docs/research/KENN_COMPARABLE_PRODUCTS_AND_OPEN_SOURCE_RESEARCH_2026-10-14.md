# KENN — Comparable products and open-source tools research

**Date:** 14 October 2026
**Purpose:** Survey of comparable Ableton/Live AI products and open-source audio tools that could be adopted or adapted to strengthen KENN's long-term roadmap toward the education/mixing-guidance end goal.

---

## 1. Why this exists

KENN's end goal is one local assistant that is specialised in music production and Ableton Live: answers ordinary questions, controls Live through Apply/Undo, teaches Live to the producer, and now — per the 14 October update — a dedicated **mixing and music-production education system** that grades work out of 100, uses real-time analysis, and suggests specific, actionable help.

Three adjacent product families already exist. This research:
1. Maps comparable products to KENN's capabilities.
2. Extracts transferable ideas and patterns.
3. Enumerates open-source audio tools that can be added to KENN's stack for long-term benefit.

All findings are research-only. No dependencies are added and no existing architecture is changed.

---

## 2. Comparable products

### 2.1 Product map

| Product | Stars | License | Primary claim | Architecture | Integration surface |
|---|---|---|---|---|---|
| `freekmurze/ableton-ai` | 20 | MIT | Control Ableton from an AI assistant via MCP | MCP server + remote script (TCP 9877), Python | MCP stdio, REST optional |
| `peterkolbe/ableton-for-ai` | 1 | MIT | Bridge between DAW and AI: makes projects hearable and visible | MCP server + OSC daemon | MCP, CLI, project snapshots + spectrograms |
| `F-Fischer/ableton-copilot` | 0 | MIT | Music-theory-aware generators, mixing, session tools on Live OMM | MCP server + remote script | MCP stdio |
| `josefigueredo/ableton-mcp` | 1 | MIT | Professional Ableton collaborator via MCP | MCP server, REST/Docker/systemd options | MCP, REST, Docker |
| `adamjmurray/producer-pal` | 328 | GPL-3.0 | AI music production assistant for Ableton (works with Claude, Gemini, ChatGPT, Ollama) | MCP server + REST API + Claude desktop extension | MCP, REST HTTP |
| `RiotTheMan/ableton-mentor-mcp` | 0 | MIT | Ableton feedback for mixing and mastering (analysis, not automation) | Remote script + MCP server over TCP 9877 | MCP stdio |
| `happysasha18/track-coach` | 1 | MIT | Measurement-first compositional coach (Claude Code skill) | Claude Code skill; librosa + Demucs | Skills/commands, local HTML reports |
| `bginigeme/mixbot-ai-mixing-assistant` | 0 | none (no licence file; ideas only) | AI mixing assistant with genre-aware feedback and DAW-specific plugin recommendations | FastMCP + Claude agentic loop + Streamlit UI | MCP, REST, Streamlit UI |
| `madisonrickert/ableton-tools` | 16 | MIT | Claude Code toolkit for Ableton: stem verification, tempo/drift, MIDI transcription, safe .als editing | Claude Code skill + local engine | Claude Code skills, local engine |
