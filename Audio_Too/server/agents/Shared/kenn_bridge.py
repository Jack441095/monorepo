"""CLI bridge to the KENN knowledge base.

Allows querying the Ableton training knowledge base from the agent CLI.
Supports in-process imports where possible to optimize latency, falling back
to clean subprocess command invocations without writing temporary scripts to disk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
KENN_DIR = ROOT / "studio" / "kenn" / "kenn"


def _python_cmd() -> str:
    """Find the right Python interpreter to use."""
    venv_python = ROOT / "business" / "agents" / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    # Check for KENN venv
    kenn_venv = KENN_DIR / ".venv" / "bin" / "python"
    if kenn_venv.exists():
        return str(kenn_venv)
    return sys.executable


def _try_in_process_ask(question: str, limit: int, fast: bool) -> str | None:
    try:
        # Direct local sys.path injection to find kenn module
        import sys
        for path in (str(KENN_DIR.parent), str(ROOT / "business" / "app"), str(ROOT / "studio" / "audio_analysis")):
            if path not in sys.path:
                sys.path.insert(0, path)

        from kenn.core.chat import ask_once
        voice_model = os.environ.get("AUDIO_TOO_LLM_MODEL_VOICE", "").strip()
        if fast and voice_model:
            os.environ["AUDIO_TOO_LLM_MODEL"] = voice_model
            os.environ["AUDIO_TOO_LLM_MODEL_REWRITE"] = voice_model

        return ask_once(question=question, limit=limit, save=False, history=None)
    except Exception:
        return None


def _try_in_process_gen(role: str, task: str, rule: str, template: str) -> str | None:
    try:
        import sys
        for path in (str(KENN_DIR.parent), str(ROOT / "business" / "app"), str(ROOT / "studio" / "audio_analysis")):
            if path not in sys.path:
                sys.path.insert(0, path)

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
                )
            },
            {
                "role": "user",
                "content": task
            }
        ]
        return lm._run_generation(messages, max_new_tokens=450, temperature=0.3)
    except Exception:
        return None


def ask_kenn(question: str, limit: int = 5, fast: bool = False) -> str:
    """Ask KENN a question and return the answer.

    Args:
        question: The question to ask.
        limit:    Number of source chunks to retrieve.
        fast:     Use the smaller voice model (qwen2.5:1.5b) for faster responses.

    Delegates to KENN's ask_once function via direct import or clean subprocess fallback.
    """
    # 1. Try direct in-process query
    in_proc = _try_in_process_ask(question, limit, fast)
    if in_proc is not None:
        return in_proc

    # 2. Subprocess fallback using python -c to avoid disk script creation
    voice_model = os.environ.get("AUDIO_TOO_LLM_MODEL_VOICE", "").strip()
    script = (
        "import sys, os; "
        f"sys.path.insert(0, {str(KENN_DIR.parent)!r}); "
        f"sys.path.insert(0, {str(ROOT / 'business' / 'app')!r}); "
        f"sys.path.insert(0, {str(ROOT / 'studio' / 'audio_analysis')!r}); "
        f"env_file = {str(ROOT / '.env')!r}; "
        "try:\n"
        "    for line in open(env_file).read().splitlines():\n"
        "        line = line.strip()\n"
        "        if line and not line.startswith('#') and '=' in line:\n"
        "            k, _, v = line.partition('=')\n"
        "            os.environ.setdefault(k.strip(), v.strip())\n"
        "except FileNotFoundError: pass\n"
        f"if {fast!r} and {voice_model!r}:\n"
        f"    os.environ['AUDIO_TOO_LLM_MODEL'] = {voice_model!r}\n"
        f"    os.environ['AUDIO_TOO_LLM_MODEL_REWRITE'] = {voice_model!r}\n"
        "try:\n"
        "    from kenn.core.chat import ask_once\n"
        f"    print(ask_once(question={question!r}, limit={limit}, save=False, history=None))\n"
        "except Exception as e:\n"
        "    print(f'Error querying KENN: {e}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )

    try:
        result = subprocess.run(
            [_python_cmd(), "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or "Unknown error"
            return f"⚠️ KENN query failed: {error}"
        answer = result.stdout.strip()
        if not answer:
            return "KENN returned an empty answer."
        return answer
    except subprocess.TimeoutExpired:
        return "⚠️ KENN query timed out after 60 seconds."
    except FileNotFoundError:
        return (
            "⚠️ KENN not available.\n"
            "To use the knowledge base, install requirements and ensure the model is downloaded:\n"
            "  cd studio/kenn/kenn && pip install -r requirements.txt"
        )


def generate_agent_response(role: str, task: str, rule: str, template: str) -> str | None:
    """Generate a response using KENN's local language model.

    Returns the generated string, or None if KENN is unavailable.
    """
    if os.environ.get("KENN_LM_ENABLED", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    # 1. Try direct in-process generation
    in_proc = _try_in_process_gen(role, task, rule, template)
    if in_proc is not None:
        return in_proc

    # 2. Subprocess fallback using python -c
    script = (
        "import sys, os, json; "
        f"sys.path.insert(0, {str(KENN_DIR.parent)!r}); "
        f"sys.path.insert(0, {str(ROOT / 'business' / 'app')!r}); "
        f"sys.path.insert(0, {str(ROOT / 'studio' / 'audio_analysis')!r}); "
        f"env_file = {str(ROOT / '.env')!r}; "
        "try:\n"
        "    for line in open(env_file).read().splitlines():\n"
        "        line = line.strip()\n"
        "        if line and not line.startswith('#') and '=' in line:\n"
        "            k, _, v = line.partition('=')\n"
        "            os.environ.setdefault(k.strip(), v.strip())\n"
        "except FileNotFoundError: pass\n"
        "try:\n"
        "    from kenn.llm.kenn_lm import _get_kenn_lm\n"
        "    lm = _get_kenn_lm()\n"
        "    if not lm:\n"
        "        print('LM not available', file=sys.stderr)\n"
        "        sys.exit(1)\n"
        f"    messages = [{{'role': 'system', 'content': 'You are the {role} agent for Audio_Too.\\nYour task: {rule}\\nStructure response like this template:\\n{template}'}}, {{'role': 'user', 'content': {task!r}}}]\n"
        "    res = lm._run_generation(messages, max_new_tokens=450, temperature=0.3)\n"
        "    print(res)\n"
        "except Exception as e:\n"
        "    print(f'Error: {e}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )

    try:
        result = subprocess.run(
            [_python_cmd(), "-c", script],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=ROOT,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None
