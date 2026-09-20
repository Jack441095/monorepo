"""In-process KENN client — replaces the subprocess-based kenn_bridge.py.

This module provides the same ``ask_kenn()`` and ``generate_agent_response()``
functions as the legacy bridge, but only uses the in-process path.  If the
direct import path fails, it returns a clear error message instead of
shelling out to a subprocess.

The subprocess fallback is retained **only** as a last resort (e.g. when
module-level imports collide with a different Python environment) and is
gated behind ``KENN_SUBPROCESS_FALLBACK=1``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent.parent
KENN_DIR = ROOT / "studio" / "kenn" / "kenn"

# Ensure importable paths
_PATHS = [
    str(KENN_DIR.parent),
    str(ROOT / "business" / "app"),
    str(ROOT / "studio" / "audio_analysis"),
    str(ROOT),
]
for _p in _PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def ask_kenn(question: str, limit: int = 5, fast: bool = False) -> str:
    """Ask KENN a question and return the answer.

    Uses the in-process ``kenn.core.chat.ask_once`` directly.
    Falls back to the legacy subprocess bridge only when
    ``KENN_SUBPROCESS_FALLBACK=1`` is set.
    """
    # Try in-process first
    try:
        voice_model = os.environ.get("AUDIO_TOO_LLM_MODEL_VOICE", "").strip()
        if fast and voice_model:
            os.environ["AUDIO_TOO_LLM_MODEL"] = voice_model
            os.environ["AUDIO_TOO_LLM_MODEL_REWRITE"] = voice_model

        from kenn.core.chat import ask_once

        result = ask_once(question=question, limit=limit, save=False, history=None)
        if result is not None:
            return result
    except ImportError:
        logger.debug("KENN in-process import failed; ask_once not available.")
    except Exception as exc:
        logger.warning("KENN in-process ask failed: %s", exc)

    # Optional subprocess fallback
    if os.environ.get("KENN_SUBPROCESS_FALLBACK", "").strip() == "1":
        try:
            from Shared.kenn_bridge import ask_kenn as _legacy_ask

            return _legacy_ask(question, limit=limit, fast=fast)
        except Exception as exc:
            return f"⚠️ KENN query failed (subprocess fallback): {exc}"

    return (
        "⚠️ KENN not available in-process.\n"
        "Ensure the KENN module is importable (studio/kenn/kenn on sys.path) "
        "and the model is downloaded.  Set KENN_SUBPROCESS_FALLBACK=1 to "
        "fall back to the legacy subprocess bridge."
    )


def generate_agent_response(
    role: str,
    task: str,
    rule: str,
    template: str,
) -> str | None:
    """Generate a response using KENN's local language model.

    Returns the generated string, or ``None`` if KENN is unavailable.
    """
    if os.environ.get("KENN_LM_ENABLED", "1").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return None

    try:
        from kenn.llm.kenn_lm import _get_kenn_lm

        lm = _get_kenn_lm()
        if not lm:
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {role} agent for the audio engineering company Audio_Too.\n"
                    f"Your task: {rule}\n"
                    f"Structure your response exactly like this template pattern:\n{template}"
                ),
            },
            {"role": "user", "content": task},
        ]
        return lm._run_generation(messages, max_new_tokens=450, temperature=0.3)
    except ImportError:
        logger.debug("KENN in-process import failed; LM generation unavailable.")
        return None
    except Exception as exc:
        logger.warning("KENN in-process generation failed: %s", exc)
        return None
