"""Aggregate status for the Audio_Too umbrella hub (port 8080)."""

from __future__ import annotations

import os

import ableton_bridge
import audiogen_bridge
import smart_sample_manager_bridge

HOST = os.getenv("AUDIO_TOO_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("AUDIO_TOO_PORT", "8080"))


def site_url(path: str = "/") -> str:
    base = f"http://{HOST}:{WEB_PORT}"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def hub_snapshot() -> dict:
    web = ableton_bridge.web_health()
    llm = ableton_bridge.llm_status()
    audiogen = audiogen_bridge.status()
    smart_sample_manager = smart_sample_manager_bridge.status()
    tips_url = web.get("url") or ableton_bridge.web_chat_url()

    return {
        "ok": True,
        "host": HOST,
        "website_port": WEB_PORT,
        "tips_port": ableton_bridge.ABLETON_WEB_PORT,
        "kenn": {
            "running": bool(web.get("running")),
            "url": tips_url,
            "app": web.get("app", "KENN"),
            "answer_mode": "retrieval+rewrite" if llm.get("enabled") else "retrieval",
            "rewrite_enabled": bool(llm.get("enabled")),
        },
        "llm": llm,
        "audiogen": audiogen,
        "smart_sample_manager": smart_sample_manager,
        "modules": [
            {
                "id": "public",
                "name": "Public website",
                "description": "Marketing page, portfolio, and project enquiry form.",
                "url": site_url("/"),
                "same_server": True,
                "running": True,
                "open_in": "same",
            },
            {
                "id": "portfolio",
                "name": "Portfolio",
                "description": "Showcase for codebases, systems, music, and audio work.",
                "url": site_url("/portfolio"),
                "same_server": True,
                "running": True,
                "open_in": "same",
            },
            {
                "id": "creative_lab",
                "name": "Creative Lab",
                "description": "Private workspace for KENN prompts, AudioGen generation, playback, and render history.",
                "url": site_url("/creative-lab"),
                "same_server": True,
                "running": True,
                "requires_auth": True,
                "open_in": "same",
            },
            {
                "id": "faq",
                "name": "Services FAQ",
                "description": "Indicative pricing and turnaround from business_knowledge.json.",
                "url": site_url("/#ask"),
                "same_server": True,
                "running": True,
                "open_in": "same",
            },
            {
                "id": "studio_tips",
                "name": "Studio tips (public)",
                "description": "Production Q&A from kenn — retrieval-only, no cloud rewrite.",
                "url": site_url("/tips"),
                "same_server": True,
                "running": True,
                "open_in": "same",
            },
            {
                "id": "stem_upload",
                "name": "Stem upload (client)",
                "description": "Signed link per project — clients upload ZIP/WAV (14-day link from dashboard).",
                "url": site_url("/upload"),
                "same_server": True,
                "running": True,
                "requires_auth": False,
                "open_in": "same",
            },
            {
                "id": "dashboard",
                "name": "Business dashboard",
                "description": "Clients, enquiries, invoices, agents, transcript review, embedded LM chat.",
                "url": site_url("/dashboard"),
                "same_server": True,
                "running": True,
                "requires_auth": True,
                "open_in": "same",
            },
            {
                "id": "tips_web",
                "name": "KENN — full chat UI",
                "description": "Production Q&A from approved notes and PDFs (separate process on :8090).",
                "url": tips_url,
                "same_server": False,
                "running": bool(web.get("running")),
                "app": web.get("app", "KENN"),
                "hint": web.get("hint", ""),
                "open_in": "new",
            },
            {
                "id": "demo",
                "name": "Tester demo",
                "description": "Password-protected tester chat with feedback logging and no dashboard access.",
                "url": site_url("/demo"),
                "same_server": True,
                "running": True,
                "requires_auth": True,
                "open_in": "same",
            },
            {
                "id": "tips_cli",
                "name": "KENN — terminal",
                "description": "Same knowledge base via ./audio-too ableton ask or chat.",
                "url": None,
                "command": "./audio-too ableton ask \"your question\"",
                "same_server": False,
                "running": True,
                "open_in": "cli",
            },
            {
                "id": "audiogen",
                "name": "LLM AudioGen",
                "description": "Markov composition, chorus generation, offline rendering, and realtime audit tools.",
                "url": None,
                "command": "./audio-too audiogen phrase --emotion joy --bars 8",
                "same_server": False,
                "running": bool(audiogen.get("ok")),
                "hint": "Generate phrases from terminal or KENN prompts.",
                "open_in": "cli",
            },
            {
                "id": "smart_sample_manager",
                "name": "Smart Sample Manager",
                "description": "JUCE VST3/AU plugin: AI sample tagging, similarity map, and library organizing.",
                "url": None,
                "same_server": False,
                "running": bool(smart_sample_manager.get("ok")),
                "hint": "Load as a plugin in your DAW — not a web page or CLI tool.",
                "open_in": "daw",
            },
        ],
    }
