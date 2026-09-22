from __future__ import annotations

import sys
from pathlib import Path

# Add project root, business/app folder, and studio/audio_analysis folder to sys.path
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WEBSITE_DIR = ROOT / "server" / "app"
if str(WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(WEBSITE_DIR))
ANALYSIS_DIR = ROOT / "studio" / "audio_analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from audio_analysis.mix_review.mix_review import save_review

def analyze_rendered_wav(wav_path: Path, mix_goal: str = "club") -> dict:
    """Analyze a rendered WAV file using the mix review tool."""
    file_bytes = wav_path.read_bytes()
    res = save_review(
        file_bytes=file_bytes,
        filename=wav_path.name,
        title=wav_path.stem,
        mix_goal=mix_goal,
        background=False,
    )
    if not res.get("ok"):
        raise RuntimeError(f"Analysis failed: {res.get('error')}")
    return res.get("review") or res.get("report") or {}
