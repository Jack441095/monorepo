#!/usr/bin/env python3
"""Measure a CMake preset build with wall time, CPU time, and peak RSS.

Examples:
    python3 scripts/measure_build.py --preset ssm-dev-ninja \
        --target ssm_qual_fast_regression --clean-first \
        --json ../reports/ssm-dev-ninja-clean.json

    python3 scripts/measure_build.py --preset ssm-dev-ninja \
        --target TestXmpWriter --touch Source/test_xmp_writer_main.cpp \
        --json ../reports/ssm-dev-ninja-incremental.json

The command output is streamed so a long build remains observable. The JSON
record is intentionally toolchain-neutral and can be compared across presets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def peak_rss_bytes(value: int) -> int:
    # macOS reports ru_maxrss in bytes; Linux reports it in KiB.
    if sys.platform == "darwin":
        return value
    return value * 1024


def run_stage(command: list[str], label: str) -> dict[str, Any]:
    print(f"\n=== {label} ===")
    print("$ " + " ".join(command))
    started = time.monotonic()
    output: list[str] = []
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        output.append(line)
    return_code = process.wait()
    elapsed = time.monotonic() - started
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    text_output = "".join(output)
    return {
        "label": label,
        "command": command,
        "returncode": return_code,
        "wall_seconds": round(elapsed, 3),
        "user_seconds": round(usage.ru_utime, 3),
        "system_seconds": round(usage.ru_stime, 3),
        "peak_rss_bytes": peak_rss_bytes(int(usage.ru_maxrss)),
        "compile_commands": len(
            re.findall(r"Building (?:C|CXX|OBJC|OBJCXX) object", text_output)
        ),
        "link_commands": len(re.findall(r"Linking", text_output)),
        "built_targets": len(re.findall(r"Built target", text_output)),
    }


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", required=True, help="CMake build/configure preset")
    parser.add_argument("--target", default="ssm_qual_fast_regression")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--source-dir", type=Path, default=project_dir)
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--clean-first", action="store_true")
    parser.add_argument(
        "--touch",
        type=Path,
        help="Touch a source path relative to --source-dir before building",
    )
    parser.add_argument("--json", type=Path, help="Write the measurement record here")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"source directory does not exist: {source_dir}")

    stages: list[dict[str, Any]] = []
    if args.configure:
        configure_command = ["cmake"]
        if args.fresh:
            configure_command.append("--fresh")
        configure_command.extend(["--preset", args.preset])
        stages.append(run_stage(configure_command, "configure"))

    if args.touch:
        touch_path = args.touch
        if not touch_path.is_absolute():
            touch_path = source_dir / touch_path
        if not touch_path.is_file():
            raise SystemExit(f"touch path does not exist: {touch_path}")
        os.utime(touch_path, None)

    build_command = [
        "cmake",
        "--build",
        "--preset",
        args.preset,
        "--target",
        args.target,
        "--parallel",
        str(args.jobs),
    ]
    if args.clean_first:
        build_command.append("--clean-first")
    stages.append(run_stage(build_command, "build"))

    result = {
        "preset": args.preset,
        "target": args.target,
        "source_dir": str(source_dir),
        "stages": stages,
        "success": all(stage["returncode"] == 0 for stage in stages),
    }
    encoded = json.dumps(result, indent=2) + "\n"
    if args.json:
        output_path = args.json if args.json.is_absolute() else source_dir / args.json
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded, encoding="utf-8")
        print(f"\nMeasurement written to {output_path}")
    print("\n" + encoded)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
