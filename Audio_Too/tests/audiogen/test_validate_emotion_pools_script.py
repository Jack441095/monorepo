import subprocess
import sys
from pathlib import Path


def test_validate_emotion_pools_exits_zero():
    root = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"
    script = root / "scripts" / "validate_emotion_pools.py"
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "validate_emotion_pools: OK" in (r.stdout or "")
