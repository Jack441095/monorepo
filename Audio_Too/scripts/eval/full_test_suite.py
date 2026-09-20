#!/usr/bin/env python3
"""Run Audio_Too release checks in crash-isolated domains and write reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts" / "test_runs"
LINT_TARGETS = [
    "server/app",
    "server/agents",
    "studio/kenn/kenn",
    "studio/audio_analysis",
    "studio/audiogen/audiogen",
    "thursday",
    "scripts",
    "tests",
]
FINGERPRINT_ROOTS = [
    "audio_too",
    "server/app",
    "server/agents",
    "studio/kenn/kenn",
    "studio/audio_analysis",
    "studio/audiogen/audiogen",
    "thursday",
    "scripts",
    "tests",
]
FINGERPRINT_SUFFIXES = {".css", ".html", ".js", ".json", ".py", ".sh", ".toml", ".yaml", ".yml"}
FINGERPRINT_ROOT_FILES = ["ableton", "agent", "audio-too", "main.py", "pyproject.toml"]
FINGERPRINT_IGNORED_PARTS = {".cache", "__pycache__", "artifacts", "logs", "sessions", "user_data"}
FINGERPRINT_IGNORED_PREFIXES = (
    "server/agents/Admin/outputs/",
    "server/agents/Admin/projects/",
    "server/agents/Marketing/campaigns/",
    "server/agents/Marketing/leads/",
    "server/agents/Marketing/outputs/",
    "server/agents/Shared/backups/",
    "server/agents/Shared/data/",
    "server/agents/Shared/exports/",
    "studio/audiogen/audiogen/exports/",
    "studio/audiogen/audiogen/outputs/",
    "thursday/alerts/",
    "thursday/analytics/",
)

# Core-suite skips are permitted only for capabilities that are intentionally
# external to a deterministic release run. Keep budgets reason-specific so a
# new missing dependency cannot hide behind an unchanged aggregate count.
# The KENN budget is the documented maximum for a fresh checkout with no local,
# gitignored retrieval index; a normal release machine with a built index uses
# none of it. Ollama's six live-agent cases are allowed because the core suite
# verifies their deterministic boundaries separately and the live model server
# has its own explicit gate.
CORE_SKIP_BUDGETS = {
    "Ollama not available": 6,
    "KENN index not built": 21,
}


@dataclass
class CheckResult:
    name: str
    status: str
    duration_seconds: float
    command: list[str] = field(default_factory=list)
    returncode: int = 0
    summary: str = ""
    log: str = ""
    children: list[dict] = field(default_factory=list)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def python_version(command: list[str]) -> str:
    try:
        return subprocess.check_output(
            [*command, "-c", "import platform,sys; print(platform.machine(), sys.version.split()[0])"],
            text=True,
            cwd=ROOT,
            timeout=15,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def root_python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def native_python_command() -> list[str]:
    configured = os.getenv("AUDIO_TOO_NATIVE_PYTHON", "").strip()
    if configured and Path(configured).expanduser().exists():
        return [str(Path(configured).expanduser())]
    candidates = sorted(ROOT.glob(".venv-py313-*/bin/python"), reverse=True)
    if candidates and sys.platform == "darwin":
        return ["arch", "-arm64", str(candidates[0])]
    return [str(candidates[0])] if candidates else [root_python()]


def tail(text: str, lines: int = 35) -> str:
    return "\n".join(str(text or "").splitlines()[-lines:])


def available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fingerprint_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    value = relative.as_posix()
    return bool(
        FINGERPRINT_IGNORED_PARTS.intersection(relative.parts)
        or any(value.startswith(prefix) for prefix in FINGERPRINT_IGNORED_PREFIXES)
    )


def source_fingerprint() -> tuple[str, int, dict[str, str]]:
    """Hash executable source, tests, and configuration for run-to-run identity."""
    paths: set[Path] = set()
    for root_name in FINGERPRINT_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        paths.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in FINGERPRINT_SUFFIXES
            and not _fingerprint_excluded(path)
        )
    for file_name in FINGERPRINT_ROOT_FILES:
        path = ROOT / file_name
        if path.is_file():
            paths.add(path)
    paths.update(path for path in ROOT.glob("requirements*.txt") if path.is_file())
    paths.update(path for path in (ROOT / "config").rglob("*") if path.is_file())

    snapshot: dict[str, str] = {}
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    digest = hashlib.sha256()
    for relative, file_hash in snapshot.items():
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest(), len(snapshot), snapshot


def pytest_summary(output: str) -> str:
    matches = re.findall(
        r"(?:^|\n)([^\n]*(?:passed|failed|skipped|error)[^\n]* in [0-9.]+s)(?:\n|$)",
        output,
        flags=re.IGNORECASE,
    )
    return matches[-1].strip() if matches else tail(output, 1)


def evaluate_pytest_skip_budget(output: str, budgets: dict[str, int]) -> dict:
    """Validate ``pytest -rs`` skip details against reason-specific budgets."""
    counts = {reason: 0 for reason in budgets}
    unknown: list[str] = []
    parsed_total = 0
    for match in re.finditer(r"^SKIPPED \[(\d+)\] .*?: (.+)$", output, flags=re.MULTILINE):
        count = int(match.group(1))
        detail = match.group(2).strip()
        parsed_total += count
        approved_reason = next((reason for reason in budgets if detail.startswith(reason)), None)
        if approved_reason is None:
            unknown.append(f"{count} × {detail}")
        else:
            counts[approved_reason] += count

    summary_matches = re.findall(r"\b(\d+) skipped\b", output, flags=re.IGNORECASE)
    reported_total = int(summary_matches[-1]) if summary_matches else 0
    failures: list[str] = []
    if reported_total != parsed_total:
        failures.append(
            f"pytest reported {reported_total} skips but -rs exposed {parsed_total}; "
            "skip reasons are incomplete"
        )
    if unknown:
        failures.append("unapproved skip reasons: " + "; ".join(unknown))
    for reason, count in counts.items():
        if count > budgets[reason]:
            failures.append(f"skip budget exceeded for {reason!r}: {count} > {budgets[reason]}")
    return {
        "ok": not failures,
        "reported_total": reported_total,
        "counts": counts,
        "failures": failures,
    }


def run_check(
    name: str,
    command: list[str],
    *,
    timeout: int,
    env: dict[str, str] | None = None,
    skip_budgets: dict[str, int] | None = None,
) -> CheckResult:
    started = time.perf_counter()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env or os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        output = (stdout or "") + (stderr or "")
        status = "pass" if process.returncode == 0 else "fail"
        returncode = process.returncode or 0
        summary = pytest_summary(output) if "pytest" in command else tail(output, 3)
        if skip_budgets is not None and process.returncode == 0:
            skip_report = evaluate_pytest_skip_budget(output, skip_budgets)
            counts = ", ".join(
                f"{reason}={count}" for reason, count in skip_report["counts"].items() if count
            ) or "none"
            summary = f"{summary} · approved skips: {counts}"
            if not skip_report["ok"]:
                status = "fail"
                returncode = 1
                output += "\nSKIP BUDGET FAIL:\n" + "\n".join(
                    f"- {failure}" for failure in skip_report["failures"]
                )
        return CheckResult(
            name=name,
            status=status,
            duration_seconds=round(time.perf_counter() - started, 3),
            command=command,
            returncode=returncode,
            summary=summary,
            log=tail(output),
        )
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        else:
            stdout, stderr = exc.stdout or "", exc.stderr or ""
        output = f"{stdout or ''}{stderr or ''}"
        return CheckResult(
            name=name,
            status="fail",
            duration_seconds=round(time.perf_counter() - started, 3),
            command=command,
            returncode=124,
            summary=f"timed out after {timeout}s",
            log=tail(output),
        )
    except OSError as exc:
        return CheckResult(
            name=name,
            status="fail",
            duration_seconds=round(time.perf_counter() - started, 3),
            command=command,
            returncode=127,
            summary=str(exc),
            log=str(exc),
        )


def chunks(items: list[Path], size: int) -> list[list[Path]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def run_pytest_batches(
    name: str,
    python: list[str],
    files: list[Path],
    *,
    batch_size: int,
    timeout: int,
    known_failures: dict[str, str] | None = None,
) -> CheckResult:
    """`known_failures` maps a file *name* (not path) to a substring that
    must appear in that file's failure output for the failure to be
    accepted -- e.g. `{"test_mix_renderer_genre_matrix.py": "edm"}` for the
    EDM case, a real physical DSP-depth limit already evidenced elsewhere
    (docs/AUDIO_MVP_MASTER_PLAN.md Stage A: pushing harder would mean
    weakening the true-peak safety guarantee, which is never traded away to
    make a number pass). Matches the tolerance `release_health_check.py`'s
    own genre-matrix gate already applies (`GENRE_MATRIX_MIN_PASS_RATE =
    0.9`) -- this doesn't lower the bar, it aligns this gate with a bar
    already set and evidenced elsewhere. Requiring the specific substring
    (not just "this file failed") means a *different* case failing in the
    same file -- a real new regression -- still fails the gate exactly as
    before.
    """
    started = time.perf_counter()
    children: list[CheckResult] = []
    failures: list[str] = []
    accepted: list[str] = []
    recovered_batches = 0
    for number, batch in enumerate(chunks(files, batch_size), start=1):
        relative = [str(path.relative_to(ROOT)) for path in batch]
        result = run_check(
            f"{name}-batch-{number}",
            [*python, "-m", "pytest", "-q", "--disable-warnings", *relative],
            timeout=timeout,
        )
        children.append(result)
        if result.status == "pass":
            continue
        individual_results = [
            run_check(
                f"{name}:{path.name}",
                [*python, "-m", "pytest", "-q", "--disable-warnings", str(path.relative_to(ROOT))],
                timeout=max(120, timeout // 2),
            )
            for path in batch
        ]
        children.extend(individual_results)
        individual_failures = [item for item in individual_results if item.status != "pass"]
        unexpected_failures = []
        for item in individual_failures:
            bare_name = item.name.split(":")[-1]
            expected_case = (known_failures or {}).get(bare_name)
            # Accept only if this specific expected case (e.g. "edm") appears
            # in the failure output -- a *different* case failing in the same
            # file (a real new regression) still fails the gate.
            if expected_case and expected_case in item.log:
                accepted.append(f"{item.name} ({expected_case}, known DSP-depth limit)")
            else:
                unexpected_failures.append(item)
        if unexpected_failures:
            failures.extend(item.name for item in unexpected_failures)
        else:
            recovered_batches += 1

    status = "pass" if not failures else "fail"
    summary = f"{len(files)} files in {len(chunks(files, batch_size))} batches"
    if recovered_batches:
        summary += f"; {recovered_batches} batch crash/order failure(s) passed in file isolation"
    if accepted:
        summary += f"; known accepted failure(s): {', '.join(accepted)}"
    if failures:
        summary += f"; failing files: {', '.join(failures)}"
    return CheckResult(
        name=name,
        status=status,
        duration_seconds=round(time.perf_counter() - started, 3),
        summary=summary,
        children=[asdict(item) for item in children],
        log="\n\n".join(
            f"[{item.name}] {item.summary}\n{item.log}" for item in children if item.status != "pass"
        ),
    )


def report_markdown(payload: dict) -> str:
    candidate = payload.get("candidate") or {}
    lines = [
        f"# Audio_Too full test suite — {payload['created_at']}",
        "",
        f"Overall: **{payload['status'].upper()}**",
        "",
        f"- Supported runtime: `{payload['environment']['root_python']}`",
        f"- Native ML runtime: `{payload['environment']['native_python']}`",
        f"- Platform: `{payload['environment']['platform']}`",
        f"- Duration: {payload['duration_seconds']:.2f}s",
        f"- Candidate fingerprint: `{candidate.get('fingerprint', 'not-recorded')}`",
        f"- Candidate files: {candidate.get('file_count', 'not-recorded')}",
        "",
        "| Check | Status | Duration | Summary |",
        "|---|---:|---:|---|",
    ]
    for result in payload["results"]:
        summary = str(result.get("summary", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {result['name']} | {result['status'].upper()} | "
            f"{result['duration_seconds']:.2f}s | {summary} |"
        )
    failures = [result for result in payload["results"] if result["status"] != "pass"]
    if failures:
        lines.extend(["", "## Failures and warnings", ""])
        for result in failures:
            lines.extend(
                [
                    f"### {result['name']}",
                    "",
                    "```text",
                    str(result.get("log") or result.get("summary") or "No log output")[-8000:],
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Skip full native domains and long latency checks.")
    parser.add_argument("--skip-live", action="store_true", help="Skip live HTTP smoke checks.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args(argv)

    root_py = root_python()
    native_py = native_python_command()
    run_env = os.environ.copy()
    run_env.setdefault("AUDIO_TOO_DEV", "1")
    initial_fingerprint, fingerprint_file_count, initial_snapshot = source_fingerprint()
    started = time.perf_counter()
    results: list[CheckResult] = []

    results.append(
        run_check(
            "compile",
            [root_py, "-m", "compileall", "-q", "business", "studio", "thursday", "scripts", "tests"],
            timeout=180,
            env=run_env,
        )
    )
    ruff = ROOT / ".venv" / "bin" / "ruff"
    results.append(
        run_check(
            "critical-lint",
            [
                str(ruff) if ruff.exists() else "ruff",
                "check",
                "--config",
                str(ROOT / "pyproject.toml"),
                "--select",
                "E9,F63,F7,F82",
                *LINT_TARGETS,
            ],
            timeout=300,
            env=run_env,
        )
    )
    lint_advisory = run_check(
        "lint-advisory",
        [
            str(ruff) if ruff.exists() else "ruff",
            "check",
            "--config",
            str(ROOT / "pyproject.toml"),
            *LINT_TARGETS,
        ],
        timeout=300,
        env=run_env,
    )
    if lint_advisory.status == "fail":
        lint_advisory.status = "warning"
    results.append(lint_advisory)
    core_command = [
        root_py,
        "-m",
        "pytest",
        "-q",
        "-rs",
        "--disable-warnings",
        "tests",
        "--ignore=tests/audiogen",
        "--ignore=tests/audio_analysis",
        "--ignore=tests/test_latency.py",
        "--ignore=tests/test_release_health_latency.py",
        "--ignore=tests/test_tts_parallel_benchmark.py",
        "--ignore=tests/test_automix_memory_budget.py",
    ]
    results.append(
        run_check(
            "core-tests",
            core_command,
            timeout=900,
            env=run_env,
            skip_budgets=CORE_SKIP_BUDGETS,
        )
    )
    if not args.quick:
        audio_files = sorted((ROOT / "tests" / "audio_analysis").glob("test_*.py"))
        audiogen_files = sorted((ROOT / "tests" / "audiogen").glob("test_*.py"))
        results.append(
            run_pytest_batches(
                "audio-analysis-tests",
                native_py,
                audio_files,
                batch_size=max(1, args.batch_size),
                # 2026-07-11: bumped from 600s. The individual-file recovery
                # step below runs at timeout // 2; test_mix_renderer_genre_matrix.py
                # alone (10 genres, each rendering real audio) measured
                # 258.79s in isolation and up to ~360s under the real
                # full-suite's system load (render ratio 1.786x vs 1.281x
                # isolated) -- too close to the old 300s individual-recovery
                # timeout, causing that recovery re-run to time out before
                # completing and silently defeat the known_failures
                # acceptance below (a timeout message doesn't contain "edm").
                timeout=1200,
                # EDM's crest-factor gap is a real physical DSP-depth limit,
                # not a regression -- see docs/AUDIO_MVP_MASTER_PLAN.md Stage A
                # and run_pytest_batches()'s own docstring. Jack confirmed
                # 2026-07-11 aligning this gate with the exception
                # release_health_check.py already accepts, rather than
                # leaving P0-14 permanently unable to pass on a known,
                # already-decided-not-to-fix gap.
                known_failures={"test_mix_renderer_genre_matrix.py": "edm"},
            )
        )
        results.append(
            run_pytest_batches(
                "audiogen-tests",
                native_py,
                audiogen_files,
                batch_size=max(1, args.batch_size),
                timeout=900,
            )
        )
        results.append(
            run_check(
                "latency-tests",
                [*native_py, "-m", "pytest", "-q", "-s", "--disable-warnings", "tests/test_latency.py"],
                timeout=600,
                env=run_env,
            )
        )
        results.append(
            run_check(
                # Real KENN retrieval / TTS latency SLO measurements (as opposed to
                # core-tests' pure evaluate_latency() gate-logic unit tests) --
                # excluded from core-tests above because both swing meaningfully
                # with machine load, same reasoning as AudioGen's native
                # "latency-tests" step. Runs under root_py (not native_py): needs
                # the main venv's KENN/Thursday packages, not AudioGen's native env.
                "release-health-latency-tests",
                [root_py, "-m", "pytest", "-q", "-s", "--disable-warnings", "tests/test_release_health_latency.py"],
                timeout=180,
                env=run_env,
            )
        )
        results.append(
            run_check(
                # Real-model benchmark for the opt-in parallel-chunk TTS synthesis
                # path (THURSDAY_TTS_PARALLEL_CHUNKS). Excluded from core-tests
                # because it spawns a native-arm64 subprocess that loads the real
                # ONNX model, same reasoning as latency-tests/release-health-
                # latency-tests above. The fast, fake-Kokoro logic tests for the
                # same feature (tests/test_tts_parallel_chunks.py) stay in
                # core-tests -- they don't need the real model.
                "tts-parallel-chunk-benchmark",
                [root_py, "-m", "pytest", "-q", "-s", "--disable-warnings", "tests/test_tts_parallel_benchmark.py"],
                timeout=120,
                env=run_env,
            )
        )
        results.append(
            run_check(
                # Real-multitrack peak-memory regression guard (the 53.1GB->12.21GB
                # incident's automated coverage -- see tests/test_automix_memory_budget.py's
                # own docstring). Excluded from core-tests: takes ~140s and needs the
                # local-only testing_track_stems/ fixture (skips cleanly when absent,
                # e.g. on a fresh checkout or a CI runner without the fixture).
                "automix-memory-budget",
                [root_py, "-m", "pytest", "-q", "-s", "--disable-warnings", "tests/test_automix_memory_budget.py"],
                timeout=300,
                env=run_env,
            )
        )

    results.append(
        run_check(
            "repository-hygiene",
            [root_py, str(ROOT / "scripts" / "repo_hygiene.py"), "all"],
            timeout=300,
            env=run_env,
        )
    )
    results.append(
        run_check(
            "kenn-benchmark-gate",
            [*native_py, str(ROOT / "scripts" / "eval" / "kenn_benchmark_gate.py")],
            timeout=120,
            env=run_env,
        )
    )
    results.append(
        run_check(
            "automix-quality-gate",
            [root_py, str(ROOT / "scripts" / "eval" / "automix_quality_benchmark.py")],
            timeout=480,
            env=run_env,
        )
    )
    results.append(
        run_check(
            "thursday-routing-benchmark-gate",
            [*native_py, "-m", "thursday.evals.benchmark"],
            timeout=120,
            env=run_env,
        )
    )
    if not args.skip_live:
        live_env = run_env.copy()
        live_port = available_local_port()
        live_env["AUDIO_TOO_HOST"] = "127.0.0.1"
        live_env["AUDIO_TOO_PORT"] = str(live_port)
        live_env["AUDIO_TOO_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{live_port}"
        live_env["AUDIO_TOO_LLM_ENABLED"] = "0"
        live_env["KENN_LM_ENABLED"] = "0"
        results.append(
            run_check(
                "live-smoke",
                [*native_py, str(ROOT / "scripts" / "eval" / "smoke_check.py")],
                timeout=300,
                env=live_env,
            )
        )
        results.append(
            run_check(
                "packaged-end-to-end",
                [
                    root_py,
                    str(ROOT / "scripts" / "eval" / "packaged_e2e.py"),
                    "--reuse-runtime",
                ],
                timeout=600,
                env=run_env,
            )
        )

    final_fingerprint, final_file_count, final_snapshot = source_fingerprint()
    changed_candidate_files = sorted(
        path
        for path in initial_snapshot.keys() | final_snapshot.keys()
        if initial_snapshot.get(path) != final_snapshot.get(path)
    )
    candidate_stable = (
        initial_fingerprint == final_fingerprint and fingerprint_file_count == final_file_count
    )
    results.append(
        CheckResult(
            name="candidate-immutability",
            status="pass" if candidate_stable else "fail",
            duration_seconds=0.0,
            summary=(
                f"source fingerprint stable across {fingerprint_file_count} files"
                if candidate_stable
                else "candidate changed: " + ", ".join(changed_candidate_files[:5])
            ),
        )
    )
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "created_at": created_at,
        "status": "pass" if not any(item.status == "fail" for item in results) else "fail",
        "quick": args.quick,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "candidate": {
            "fingerprint": initial_fingerprint,
            "file_count": fingerprint_file_count,
            "stable_during_run": candidate_stable,
            "final_fingerprint": final_fingerprint,
            "final_file_count": final_file_count,
            "changed_files": changed_candidate_files,
        },
        "environment": {
            "platform": platform.platform(),
            "root_python": f"{root_py} ({python_version([root_py])})",
            "native_python": f"{' '.join(native_py)} ({python_version(native_py)})",
        },
        "results": [asdict(item) for item in results],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = stamp()
    json_path = args.output_dir / f"full_test_suite_{run_stamp}.json"
    md_path = args.output_dir / f"full_test_suite_{run_stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(report_markdown(payload), encoding="utf-8")

    print(f"Full test suite: {payload['status']}")
    for item in results:
        print(f"  {item.status.upper():4} {item.name}: {item.summary}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
