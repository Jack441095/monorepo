import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest


pytestmark = [pytest.mark.benchmark, pytest.mark.slow]


class TestSystemPerformanceBenchmark(unittest.TestCase):
    def test_orchestrator_gate_smoke(self):
        root = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"
        py = root / ".venv" / "bin" / "python"
        if not py.is_file():
            py = Path(sys.executable)

        out_dir = root / ".cache" / "system_performance_benchmark_test"
        out_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["AUDIOGEN_TEST_SUBPROCESS"] = "1"
        env.setdefault("SYS_BENCH_MAX_SECTION_MS", "300000")
        env.setdefault("SYS_BENCH_MAX_SONG_MS", "600000")
        env.setdefault("SYS_BENCH_MAX_RENDER_RATIO", "5.0")
        env.setdefault("SYS_BENCH_MAX_OVER_BUDGET_BARS", "999")
        env.setdefault("SYS_BENCH_MAX_UNDERRUNS", "999")
        env.setdefault("SYS_BENCH_MIN_PROFILED_BARS", "1")

        cmd = [
            str(py),
            "tools/system_performance_benchmark.py",
            "--output-dir",
            str(out_dir),
            "--performance",
            "low",
            "--rt-seconds",
            "12",
            "--emotion",
            "neutral",
            "--seed",
            "0",
            "--gate",
        ]
        proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(f"benchmark failed rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")

        # The tool prints a small JSON object to stdout with report path.
        data = {}
        try:
            import json

            data = json.loads((proc.stdout or "").strip())
        except Exception:
            data = {}
        report_path = data.get("report")
        self.assertTrue(report_path, f"missing report path in stdout:\n{proc.stdout}")
        self.assertTrue(Path(str(report_path)).is_file(), f"report.json not found at {report_path}")
