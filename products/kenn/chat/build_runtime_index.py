"""Build a KENN index into wrapper-owned runtime storage."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_ROOT.parents[2]
ENGINE_ROOT = Path(
    os.environ.get("KENN_ENGINE_ROOT", str(REPO_ROOT / "Audio_Too" / "studio" / "kenn"))
).expanduser().resolve()
RUNTIME_INDEX_DIR = Path(
    os.environ.get("KENN_CHAT_INDEX_DIR", str(SERVICE_ROOT / ".runtime" / "index"))
).expanduser()

if not ENGINE_ROOT.is_dir():
    raise RuntimeError(f"KENN engine checkout not found at {ENGINE_ROOT}")
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))
if str(ENGINE_ROOT.parents[1]) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT.parents[1]))

os.environ["AUDIO_TOO_LLM_ENABLED"] = "0"

from index_runtime import configure_index_dir  # noqa: E402
from kenn.retrieval import build_index  # noqa: E402


configure_index_dir(RUNTIME_INDEX_DIR)
build_index.build_index()
