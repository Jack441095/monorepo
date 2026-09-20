"""NITE DSP — main CLI entry point.

Run from the repo root:
  python main.py              Interactive menu (TTY)
  python main.py start        Start website + Ableton chat, open /hub
  python main.py help         Full command list
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "server"))

try:
    from repo_python import python_executable  # noqa: E402
except ImportError:
    def python_executable() -> str:
        return sys.executable

HOST = "127.0.0.1"
WEB_PORT = 8080
HUB_URL = f"http://{HOST}:{WEB_PORT}/hub"


def python_cmd() -> str:
    return python_executable()


def _with_audiogen_path() -> None:
    audiogen_root = ROOT / "studio" / "audiogen" / "audiogen"
    root_str = str(audiogen_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _discover_preset_families(*args, **kwargs):
    _with_audiogen_path()
    from runner.session import discover_preset_families

    return discover_preset_families(*args, **kwargs)


def _apply_drums_enabled(*args, **kwargs):
    _with_audiogen_path()
    from runner.session import apply_drums_enabled

    return apply_drums_enabled(*args, **kwargs)


def _resolve_drums_from_args(*args, **kwargs):
    _with_audiogen_path()
    from runner.session import resolve_drums_from_args

    return resolve_drums_from_args(*args, **kwargs)


def _slice_events_for_bar(*args, **kwargs):
    _with_audiogen_path()
    from runner.offline import slice_events_for_bar

    return slice_events_for_bar(*args, **kwargs)


def print_help() -> None:
    print(
        """Audio_Too — main entry point

Usage:
  python main.py                 Interactive menu (when run in a terminal)
  python main.py start           Start :8080 + :8090 and open /hub
  python main.py start --restart Restart listeners, then start + open
  python main.py start --no-open Start without opening a browser
  python main.py start --detach  Start services in background and return
  python main.py status          Show Website, KENN, and AudioGen status
  python main.py kenn-ready      Show KENN index, dataset, audit, and service readiness
  python main.py kenn-index-rollback [--apply]  Preview or apply validated index rollback
  python main.py stop            Stop listeners on :8080 and :8090
  python main.py setup           Create .venv and install dependencies
  python main.py uninstall       Remove virtual environment and clean up Thursday state
  python main.py fetch-models    Fetch KENN embedding + Kokoro TTS model files (~200MB, run once)
  python main.py agent ...       Business agents (same as ./agent)
  python main.py ableton ...     Audio Engineering LM (same as ./ableton)
  python main.py audiogen ...    LLM_AudioGen phrase/render/test/audit commands
  python main.py demo            Start tester demo only on :8091
  python main.py smoke           Run scripts/smoke_check.py
  python main.py check           Run Python, lint, test, hygiene, and smoke gates
  python main.py check --full    Also run automix-quality-gate and release-health (~5+ min)
  python main.py full-test       Run crash-isolated release suite and write JSON/Markdown reports
  python main.py automix-local DIR  Local/offline AutoMix -- no DB, job queue, or upload
  python main.py package build   Build a distributable release archive (artifacts/releases/)
  python main.py package verify ARCHIVE  Extract and verify an existing release archive
  python main.py release-health  Run the combined AutoMix/KENN/TTS performance SLO gate
  python main.py test            Run pytest
  python main.py lint            Run ruff
  python main.py hygiene         Run repo hygiene check, size report, and local data doctor
  python main.py eval            Run Ableton LM retrieval eval
  python main.py bench           Benchmark Ableton LM and write JSON logs
  python main.py audit           Run eval/benchmark/gap audit and write JSON
  python main.py feedback-review Review KENN feedback labels and export improvement artifacts
  python main.py promote-feedback-evals Promote selected draft feedback evals into questions.json
  python main.py brain-score     Score KENN routing, grounding, refusals, follow-ups, and latency
  python main.py reranker-export Export source-ranking pairs for future reranker/Torch work
  python main.py hard-negative-mine Mine near-miss sources for hard-negative review
  python main.py hard-negative-report Show promotable hard-negative candidates
  python main.py promote-hard-negative Promote one reviewed hard-negative candidate
  python main.py validate-hard-negatives Validate tracked hard-negative labels
  python main.py reranker-train  Train an offline reranker experiment
  python main.py reranker-eval   Evaluate the offline reranker model
  python main.py audio-scan      Scan a folder of audio files with Mix Review analysis
  python main.py analysis-feedback REVIEW_ID accepted|rejected [note]
  python main.py export-training Export KENN ML-ready JSONL records
  python main.py repair-training Export reviewed Creative Lab repair JSONL + manifest
  python main.py knowledge-audit Audit KENN note structure, provenance, coverage, and prompts
  python main.py knowledge-gaps  Rank real weak questions and recheck current coverage
  python main.py maintenance-log Show recent KENN autonomous-maintenance run receipts
  python main.py chat            Interactive chat with Thursday (terminal, no browser/password)
  python main.py thursday "..."  One-shot request to Thursday
  python main.py commands        Open commands.md
  python main.py session-dump    Dump KENN session memory data
  python main.py session-delete  Delete one KENN session (requires --yes)
  python main.py session-purge   Apply configured KENN session retention (requires --yes)

Examples:
  python main.py
  python main.py start
  python main.py ableton ask "How do I sidechain bass to the kick?"
  python main.py audiogen phrase --emotion joy --bars 8
  python main.py agent dashboard

Equivalent: ./audio-too <command>  (shell wrapper calls this file)
See commands.md for full reference."""
    )


def run(cmd: list[str], *, cwd: Path | None = None) -> int:
    return subprocess.run(cmd, cwd=cwd or ROOT, check=False).returncode


def cmd_setup(args: list[str]) -> int:
    script = SCRIPTS / "setup" / "setup_venv.sh"
    return run(["/bin/bash", str(script), *args])


def cmd_uninstall(args: list[str]) -> int:
    script = SCRIPTS / "setup" / "uninstall.sh"
    return run(["/bin/bash", str(script), *args])


def cmd_fetch_models(args: list[str]) -> int:
    """Fetch the local model files ./audio-too setup doesn't (deliberately —
    they're a combined ~200MB download and setup must stay CI-safe): the
    ONNX embedding model KENN's retrieval needs, and the Kokoro TTS voice
    model Thursday's voice output needs. Without these, KENN retrieval has
    no embeddings and TTS silently falls back to macOS `say` (or nothing at
    all for browser playback) with no error telling you why."""
    for label, script in (
        ("embedding model", SCRIPTS / "fetch_embedding_model.py"),
        ("Kokoro TTS model", SCRIPTS / "fetch_kokoro_model.py"),
    ):
        print(f"\n== Fetching {label} ==", flush=True)
        result = run([python_cmd(), str(script), *args])
        if result:
            print(f"Failed to fetch {label} (exit {result}).", file=sys.stderr)
            return result
    print(
        "\nModels fetched. Run ./audio-too readiness for a full status check, "
        "or ./audio-too start to launch."
    )
    return 0


def cmd_start(args: list[str]) -> int:
    from serve import main as serve_main

    return serve_main(args)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, int(port))) == 0


def http_healthy(port: int, path: str = "/", timeout: float = 3.0) -> bool:
    """True only if the server actually answers HTTP on ``path``.

    A plain TCP ``port_open`` check passes as long as *something* is bound —
    even a wedged server whose worker threads die and return an empty reply
    (seen under memory pressure). Any HTTP status line back (2xx/3xx/4xx)
    proves the request loop is alive; an empty/reset/timeout reply does not.
    """
    url = f"http://{HOST}:{int(port)}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True  # server responded (e.g. 401/403) — the loop is alive
    except (urllib.error.URLError, OSError, ConnectionError):
        return False


def pids_for_port(port: int) -> list[int]:
    result = subprocess.run(["lsof", "-ti", f"tcp:{int(port)}"], capture_output=True, text=True, check=False)
    return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]


def _service_state(port: int, path: str) -> str:
    """Three-state health: offline (nothing bound), wedged (bound but not
    answering HTTP), or online (serving)."""
    if not port_open(port):
        return "offline"
    return "online" if http_healthy(port, path) else "bound but NOT responding (wedged?)"


def cmd_status(_args: list[str]) -> int:
    website_state = _service_state(WEB_PORT, "/")
    kenn_state = _service_state(8090, "/api/health")
    print(f"Website :{WEB_PORT}: {website_state}")
    print(f"KENN    :8090: {kenn_state}")
    website = website_state == "online"
    kenn = kenn_state == "online"
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    try:
        import audiogen_bridge  # noqa: E402

        audiogen = audiogen_bridge.status()
        print(f"AudioGen     : {'ready' if audiogen.get('ok') else 'not detected'}")
    except Exception as exc:
        print(f"AudioGen     : status failed ({exc})")
    if not website or not kenn:
        if website and not kenn:
            print("Next step    : ./audio-too start --no-open  (will start KENN without restarting the website)")
        else:
            print("Next step    : ./audio-too start --restart")
    return 0 if website and kenn else 1


def cmd_stop(_args: list[str]) -> int:
    stopped = 0
    for port, label in ((WEB_PORT, "Website"), (8090, "KENN")):
        pids = pids_for_port(port)
        if not pids:
            print(f"{label} :{port}: already stopped")
            continue
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped += 1
                print(f"{label} :{port}: stopped pid {pid}")
            except OSError as exc:
                print(f"{label} :{port}: could not stop pid {pid} ({exc})", file=sys.stderr)
                return 1

    # The automix worker (started detached by `start --detach`) binds no
    # port, so the lsof-based discovery above can't find it -- serve.py
    # writes its PID here on start specifically so stop can clean it up too
    # (found 2026-07-30: it was being left orphaned after every stop).
    worker_pid_file = ROOT / "data" / "logs" / "worker.pid"
    if worker_pid_file.exists():
        try:
            pid = int(worker_pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            stopped += 1
            print(f"Automix worker: stopped pid {pid}")
        except ProcessLookupError:
            print("Automix worker: already stopped")
        except (OSError, ValueError) as exc:
            print(f"Automix worker: could not stop ({exc})", file=sys.stderr)
        finally:
            worker_pid_file.unlink(missing_ok=True)
    else:
        print("Automix worker: already stopped")
    return 0


def cmd_agent(args: list[str]) -> int:
    return run([str(ROOT / "server" / "agents" / "agent"), *args])


def cmd_ableton(args: list[str]) -> int:
    return run([python_cmd(), str(ROOT / "studio" / "kenn" / "kenn" / "main.py"), *args])


def cmd_audiogen(args: list[str]) -> int:
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    import audiogen_bridge  # noqa: E402

    parser = argparse.ArgumentParser(prog="audio-too audiogen")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status")

    test_parser = sub.add_parser("test")
    test_parser.add_argument("pytest_args", nargs=argparse.REMAINDER)

    phrase = sub.add_parser("phrase")
    phrase.add_argument("--emotion", default="joy")
    phrase.add_argument("--bars", type=int, default=8)
    phrase.add_argument("--seed", default="")
    phrase.add_argument("--wav-out", default="")
    phrase.add_argument("--include-events", action="store_true")

    render = sub.add_parser("render")
    render.add_argument("--emotion", default="joy")
    render.add_argument("--k", type=int, default=3)
    render.add_argument("render_args", nargs=argparse.REMAINDER)

    audit = sub.add_parser("audit")
    audit.add_argument("audit_args", nargs=argparse.REMAINDER)

    parsed, unknown = parser.parse_known_args(args or ["status"])
    if parsed.command == "status":
        print(json_dump(audiogen_bridge.status()))
        return 0 if audiogen_bridge.status().get("ok") else 1
    if parsed.command == "test":
        result = audiogen_bridge.test_command([*parsed.pytest_args, *unknown])
    elif parsed.command == "phrase":
        result = audiogen_bridge.phrase_command(
            emotion=parsed.emotion,
            bars=parsed.bars,
            seed=parsed.seed,
            wav_out=parsed.wav_out or None,
            include_events=parsed.include_events,
        )
    elif parsed.command == "render":
        result = audiogen_bridge.render_command(emotion=parsed.emotion, k=parsed.k, args=[*parsed.render_args, *unknown])
    elif parsed.command == "audit":
        result = audiogen_bridge.audit_command([*parsed.audit_args, *unknown])
    else:
        parser.print_help()
        return 0
    print(json_dump(result))
    return 0 if result.get("ok") else int(result.get("returncode") or 1)


def cmd_demo(args: list[str]) -> int:
    return run([python_cmd(), str(ROOT / "server" / "app" / "demo_server.py"), *args])


def cmd_smoke(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "smoke_check.py"), *args])


def supported_python() -> tuple[int, int]:
    version_text = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    major, minor = version_text.split(".", 1)
    return int(major), int(minor)


def cmd_check(args: list[str]) -> int:
    full = False
    if args:
        if args == ["--full"]:
            full = True
        else:
            print("Usage: ./audio-too check [--full]", file=sys.stderr)
            return 2
    expected = supported_python()
    actual = sys.version_info[:2]
    print(f"python: {actual[0]}.{actual[1]} (required {expected[0]}.{expected[1]})")
    if actual != expected:
        print("Python version gate failed. Recreate .venv with ./audio-too setup.", file=sys.stderr)
        return 1
    gates = (
        ("lint", cmd_lint),
        ("tests", lambda _args: cmd_test(["-q"])),
        ("hygiene", lambda _args: cmd_hygiene(["all"])),
        ("smoke", cmd_smoke),
    )
    if full:
        # Opt-in: both gates run real DSP through the full pipeline (the
        # genre-matrix stress test alone is ~5 minutes), so they stay out of
        # the default fast check and are only added here on request.
        gates = gates + (
            ("automix-quality-gate", cmd_automix_quality_gate),
            ("release-health", cmd_release_health),
        )
    for label, gate in gates:
        print(f"\n== {label} ==", flush=True)
        result = gate([])
        if result:
            print(f"{label} gate failed with exit code {result}.", file=sys.stderr)
            return result
    print("\nAll repository checks passed.")
    return 0


def cmd_test(args: list[str]) -> int:
    return run([python_cmd(), "-m", "pytest", *args], cwd=ROOT)


def cmd_full_test(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "full_test_suite.py"), *args])


def cmd_lint(args: list[str]) -> int:
    ruff = ROOT / ".venv" / "bin" / "ruff"
    targets = ["server/app", "server/agents", "studio/kenn/kenn", "studio/audio_analysis", "studio/audiogen/audiogen", "thursday", "scripts", "tests"]
    if ruff.exists():
        return run([str(ruff), "check", *targets, *args])
    return run(["ruff", "check", *targets, *args])


def cmd_hygiene(args: list[str]) -> int:
    hygiene_args = args or ["all"]
    return run([python_cmd(), str(SCRIPTS / "repo_hygiene.py"), *hygiene_args])


def cmd_eval(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "ableton_eval.py"), *args])


def cmd_bench(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "ableton_benchmark.py"), *args])


def cmd_audit(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "ableton_audit.py"), *args])


def cmd_trends(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_benchmark_trends.py"), *args])


def cmd_tester_probe(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_tester_probe.py"), *args])


def cmd_benchmark_gate(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_benchmark_gate.py"), *args])


def cmd_automix_quality_gate(args: list[str]) -> int:
    """AutoMix output-quality gate (docs/AUDIT_FIX_EXECUTION_PLAN_2026-07-08.md Stage 1).

    Previously a standalone script nothing called — a regression in the limiter/
    validator chain (the exact P0 clipping bug fixed 2026-07-08) could ship
    silently again. Non-zero exit fails the release the same way benchmark-gate does.
    """
    return run([python_cmd(), str(SCRIPTS / "eval" / "automix_quality_benchmark.py"), *args])


def cmd_automix_local(args: list[str]) -> int:
    """Stage O1 — local/offline AutoMix: point at a folder of stems, get a
    mixed file back. No DB, job queue, or HTTP upload -- the product-facing
    entry point for a standalone KENN+DSP build. Same pipeline and quality
    gate as the online job path (server/app/automix_worker.py); see
    scripts/automix_local.py.

    python main.py automix-local <stems-dir> --genre pop --target-lufs -14
    """
    return run([python_cmd(), str(SCRIPTS / "automix_local.py"), *args])


def cmd_package(args: list[str]) -> int:
    """Build or verify a distributable release archive (Stage F).

    python main.py package build              Build artifacts/releases/audio-too-<timestamp>.tar.gz
    python main.py package build --output P    Build to a specific path
    python main.py package verify ARCHIVE      Extract + verify an existing archive
    """
    return run([python_cmd(), str(SCRIPTS / "build_release_package.py"), *args])


def cmd_release_health(args: list[str]) -> int:
    """Combined release-health gate (docs/AUDIO_MVP_MASTER_PLAN.md Stage E):
    KENN retrieval latency, TTS latency, AutoMix quality benchmark, and the
    AutoMix genre-matrix stress test, gated against the plan's SLOs.
    """
    return run([python_cmd(), str(SCRIPTS / "eval" / "release_health_check.py"), *args])


def cmd_feedback_review(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_feedback_review.py"), *args])


def cmd_promote_feedback_evals(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_promote_feedback_evals.py"), *args])


def cmd_brain_score(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_brain_score.py"), *args])


def cmd_reranker_export(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_reranker_export.py"), *args])


def cmd_hard_negative_mine(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_hard_negative_mine.py"), *args])


def cmd_promote_hard_negative(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_promote_hard_negative.py"), *args])


def cmd_hard_negative_report(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_promote_hard_negative.py"), "--list", *args])


def cmd_validate_hard_negatives(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_validate_hard_negatives.py"), *args])


def cmd_reranker_train(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_reranker_train.py"), *args])


def cmd_reranker_eval(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_reranker_eval.py"), *args])


def cmd_audio_scan(args: list[str]) -> int:
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    if str(ROOT / "server" / "agents") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "agents"))
    if str(ROOT / "studio") not in sys.path:
        sys.path.insert(0, str(ROOT / "studio"))
    from audio_analysis.mix_review import mix_review  # noqa: E402

    parser = argparse.ArgumentParser(prog="audio-too audio-scan")
    parser.add_argument("path", nargs="?", default=str(ROOT / "server" / "portfolio" / "audio"))
    parser.add_argument("--mix-goal", default="premaster")
    parser.add_argument("--reference", default="")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--benchmark", action="store_true", help="Include scan throughput and slowest-file summary")
    parser.add_argument("--qa", action="store_true", help="Include catalogue QA risk ranking and issue counts")
    parser.add_argument("--music-analysis", action="store_true", help="Output batch key/chord analysis summaries")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--output", "-o", default="")
    parsed = parser.parse_args(args)

    scan_payload = mix_review.scan_audio_files(
        Path(parsed.path),
        recursive=not parsed.no_recursive,
        mix_goal=parsed.mix_goal,
        reference_path=Path(parsed.reference) if parsed.reference else None,
    )
    if parsed.benchmark:
        scan_payload["benchmark"] = mix_review.scan_audio_benchmark(scan_payload)
    if parsed.qa:
        scan_payload["qa"] = mix_review.batch_qa_summary(scan_payload)
    payload = scan_payload
    music_payload = None
    if parsed.music_analysis:
        music_payload = mix_review.batch_music_analysis(scan_payload)
        payload = {
            "ok": bool(scan_payload.get("ok")) and bool(music_payload.get("ok")),
            "root": scan_payload.get("root", ""),
            "scan": scan_payload,
            "benchmark": scan_payload.get("benchmark", {}),
            "qa": scan_payload.get("qa", {}),
            "music_analysis": music_payload,
        }
    if parsed.format == "csv":
        if not parsed.music_analysis:
            parser.error("--format csv requires --music-analysis")
        body = mix_review.batch_music_analysis_csv(music_payload or {}).rstrip("\n")
    else:
        body = json_dump(payload)
    if parsed.output:
        output_path = Path(parsed.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body + "\n", encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        print(body)
    return 0 if payload.get("ok") else 1


def cmd_analysis_feedback(args: list[str]) -> int:
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    if str(ROOT / "server" / "agents") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "agents"))
    from audio_analysis.mix_review import mix_review  # noqa: E402

    parser = argparse.ArgumentParser(prog="audio-too analysis-feedback")
    parser.add_argument("review_id")
    parser.add_argument("decision", choices=["accepted", "rejected", "useful", "not_useful", "needs_work"])
    parser.add_argument("note", nargs="?", default="")
    parser.add_argument("--output", default="")
    parsed = parser.parse_args(args)
    path = Path(parsed.output) if parsed.output else None
    payload = mix_review.record_review_feedback(parsed.review_id, parsed.decision, parsed.note, path=path)
    print(json_dump(payload))
    return 0 if payload.get("ok") else 1


def cmd_export_training(args: list[str]) -> int:
    return run(
        [
            python_cmd(),
            str(ROOT / "studio" / "kenn" / "kenn" / "training" / "export_training_data.py"),
            *args,
        ]
    )


def cmd_repair_training(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "export_creative_repair_training.py"), *args])


def cmd_kenn_ready(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_readiness.py"), *args])


def cmd_kenn_index_rollback(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "eval" / "kenn_index_rollback.py"), *args])


def cmd_knowledge_audit(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "kenn_knowledge_audit.py"), *args])


def cmd_knowledge_gaps(args: list[str]) -> int:
    return run([python_cmd(), str(SCRIPTS / "kenn_gap_report.py"), *args])


def cmd_kenn_maintenance(args: list[str]) -> int:
    """Stage G — KENN's autonomous, unattended knowledge-base maintenance
    scan (detection + draft generation only; never resolution/approval/
    trust-score writes). See docs/AUDIO_MVP_MASTER_PLAN.md Stage G and
    studio/kenn/kenn/knowledge/maintenance_scheduler.py."""
    return run([python_cmd(), str(SCRIPTS / "kenn_maintenance_scan.py"), *args])


def cmd_maintenance_log(args: list[str]) -> int:
    """Stage G — show recent kenn-maintenance run receipts (the durable,
    human-reviewable record every autonomous G1/G2/G3 run writes to
    knowledge_maintenance_runs). Previously documented but never actually
    wired to a command; list_maintenance_runs() itself already existed."""
    limit = 20
    if args and args[0].isdigit():
        limit = int(args[0])
    from kenn.knowledge.maintenance_scheduler import list_maintenance_runs  # noqa: E402

    runs = list_maintenance_runs(limit=limit)
    if not runs:
        print("No maintenance runs recorded yet.")
        return 0
    for run_row in runs:
        summary = run_row.get("summary", {})
        print(
            f"{run_row.get('started_at', '?')}  {run_row.get('job', '?'):24s} "
            f"{run_row.get('status', '?'):8s} {summary}"
        )
    return 0


def cmd_thursday(args: list[str]) -> int:
    """Thursday — natural language orchestration agent."""
    thurs_dir = ROOT / "thursday"
    if not thurs_dir.exists():
        print("Error: thursday/ not found.", file=sys.stderr)
        return 1
    return run([python_cmd(), str(thurs_dir / "main.py"), *args])


def cmd_chat(_args: list[str]) -> int:
    """Interactive chat with Thursday — one warm process, no browser/password needed."""
    return cmd_thursday(["--repl"])


def cmd_commands(_args: list[str]) -> int:
    path = ROOT / "docs" / "commands.md"
    if sys.platform == "darwin":
        return run(["open", str(path)])
    return run(["less", str(path)])


def cmd_ask(args: list[str]) -> int:
    if not args:
        print('Usage: python main.py ask "your question"', file=sys.stderr)
        return 1
    question = " ".join(args).strip()
    from kenn.core.chat import answer_payload  # noqa: E402

    payload = answer_payload(question, limit=8)
    print(payload.get("answer", ""))
    if payload.get("related_questions"):
        print("\nYou could also ask:")
        for item in payload["related_questions"][:5]:
            print(f"  - {item}")
    print(f"\nConfidence: {payload.get('confidence', 'unknown')}")
    return 0


def cmd_worker(args: list[str]) -> int:
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    from app.automix_worker import start_worker
    worker_id = args[0] if args else None
    start_worker(worker_id)
    return 0


def cmd_retention(args: list[str]) -> int:
    if str(ROOT / "server" / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "server" / "app"))
    import retention
    return retention.main()


def cmd_session_dump(args: list[str]) -> int:
    if not args:
        print("Usage: python main.py session-dump <session_id>", file=sys.stderr)
        return 1
    session_id = args[0].strip()
    from kenn.core.session_memory import load_session
    state = load_session(session_id=session_id)
    if not state.get("created_at"):
        print(f"Error: Session {session_id} not found in database.", file=sys.stderr)
        return 1
    print(json_dump(state))
    return 0


def cmd_session_delete(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="audio-too session-delete")
    parser.add_argument("session_id")
    parser.add_argument("--yes", action="store_true")
    parsed = parser.parse_args(args)
    if not parsed.yes:
        print("Refusing to delete without --yes.", file=sys.stderr)
        return 2
    from kenn.core.session_memory import clear_session, load_session_from_db

    if load_session_from_db(parsed.session_id) is None:
        print(f"Session not found: {parsed.session_id}", file=sys.stderr)
        return 1
    clear_session(parsed.session_id)
    print(f"Deleted KENN session: {parsed.session_id}")
    return 0


def cmd_session_purge(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="audio-too session-purge")
    parser.add_argument("--keep-hours", type=int)
    parser.add_argument("--yes", action="store_true")
    parsed = parser.parse_args(args)
    if not parsed.yes:
        print("Refusing to purge without --yes.", file=sys.stderr)
        return 2
    from kenn.core.session_memory import configured_retention_hours, delete_old_sessions

    keep_hours = parsed.keep_hours or configured_retention_hours()
    deleted = delete_old_sessions(keep_hours=keep_hours)
    print(f"Deleted {deleted} KENN session(s) older than {keep_hours} hours.")
    return 0


def cmd_scheduler(args: list[str]) -> int:
    """Run scheduled agents check."""
    from thursday.scheduler import run_scheduled_tasks
    result = run_scheduled_tasks()
    print(json_dump(result))
    return 0 if result.get("ok") else 1


def json_dump(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2, ensure_ascii=False)

COMMANDS: dict[str, object] = {
    "help": lambda a: (print_help(), 0)[1],
    "setup": cmd_setup,
    "uninstall": cmd_uninstall,
    "fetch-models": cmd_fetch_models,
    "fetch-model": cmd_fetch_models,
    "start": cmd_start,
    "serve": cmd_start,
    "server": cmd_start,
    "status": cmd_status,
    "stop": cmd_stop,
    "agent": cmd_agent,
    "agents": cmd_agent,
    "a": cmd_agent,
    "ableton": cmd_ableton,
    "lm": cmd_ableton,
    "at": cmd_ableton,
    "audiogen": cmd_audiogen,
    "ag": cmd_audiogen,
    "demo": cmd_demo,
    "tester-demo": cmd_demo,
    "smoke": cmd_smoke,
    "check": cmd_check,
    "test": cmd_test,
    "pytest": cmd_test,
    "full-test": cmd_full_test,
    "release-test": cmd_full_test,
    "lint": cmd_lint,
    "ruff": cmd_lint,
    "hygiene": cmd_hygiene,
    "repo-hygiene": cmd_hygiene,
    "eval": cmd_eval,
    "bench": cmd_bench,
    "benchmark": cmd_bench,
    "audit": cmd_audit,
    "llm-audit": cmd_audit,
    "trends": cmd_trends,
    "benchmark-trends": cmd_trends,
    "tester-probe": cmd_tester_probe,
    "probe": cmd_tester_probe,
    "benchmark-gate": cmd_benchmark_gate,
    "gate": cmd_benchmark_gate,
    "automix-quality-gate": cmd_automix_quality_gate,
    "automix-local": cmd_automix_local,
    "package": cmd_package,
    "release-package": cmd_package,
    "release-health": cmd_release_health,
    "release-health-check": cmd_release_health,
    "feedback-review": cmd_feedback_review,
    "kenn-feedback": cmd_feedback_review,
    "promote-feedback-evals": cmd_promote_feedback_evals,
    "promote-evals": cmd_promote_feedback_evals,
    "brain-score": cmd_brain_score,
    "kenn-score": cmd_brain_score,
    "reranker-export": cmd_reranker_export,
    "ranking-export": cmd_reranker_export,
    "hard-negative-mine": cmd_hard_negative_mine,
    "mine-hard-negatives": cmd_hard_negative_mine,
    "hard-negative-report": cmd_hard_negative_report,
    "report-hard-negatives": cmd_hard_negative_report,
    "promote-hard-negative": cmd_promote_hard_negative,
    "hard-negative-promote": cmd_promote_hard_negative,
    "validate-hard-negatives": cmd_validate_hard_negatives,
    "hard-negative-validate": cmd_validate_hard_negatives,
    "reranker-train": cmd_reranker_train,
    "reranker-eval": cmd_reranker_eval,
    "audio-scan": cmd_audio_scan,
    "analysis-scan": cmd_audio_scan,
    "mix-scan": cmd_audio_scan,
    "analysis-feedback": cmd_analysis_feedback,
    "mix-feedback": cmd_analysis_feedback,
    "export-training": cmd_export_training,
    "training-export": cmd_export_training,
    "repair-training": cmd_repair_training,
    "creative-repair-training": cmd_repair_training,
    "knowledge-audit": cmd_knowledge_audit,
    "kenn-knowledge-audit": cmd_knowledge_audit,
    "knowledge-gaps": cmd_knowledge_gaps,
    "kenn-gaps": cmd_knowledge_gaps,
    "kenn-maintenance": cmd_kenn_maintenance,
    "kenn-maintain": cmd_kenn_maintenance,
    "maintenance-log": cmd_maintenance_log,
    "kenn-ready": cmd_kenn_ready,
    "readiness": cmd_kenn_ready,
    "kenn-index-rollback": cmd_kenn_index_rollback,
    "commands": cmd_commands,
    "docs": cmd_commands,
    "ask": cmd_ask,

    "thursday": cmd_thursday,
    "thurs": cmd_thursday,
    "t": cmd_thursday,
    "chat": cmd_chat,
    "talk": cmd_chat,
    "session-dump": cmd_session_dump,
    "session-delete": cmd_session_delete,
    "session-purge": cmd_session_purge,
    "worker": cmd_worker,
    "retention": cmd_retention,
    "scheduler": cmd_scheduler,
    "scheduled": cmd_scheduler,
}


def interactive() -> int:
    menu = """
Audio_Too
─────────
  1) Start hub (website :8080 + chat :8090, open browser)
  2) Start servers only (no browser)
  3) Restart and open hub
  4) Ask the knowledge LM (terminal)
  5) Chat with Thursday (terminal)
  6) Business agent menu
  7) Smoke check
  8) Command reference (help)
  9) Quit
"""
    handlers = {
        "1": lambda: cmd_start([]),
        "2": lambda: cmd_start(["--no-open"]),
        "3": lambda: cmd_start(["--restart"]),
        "4": _interactive_ask,
        "5": lambda: cmd_chat([]),
        "6": lambda: cmd_agent([]),
        "7": lambda: cmd_smoke([]),
        "8": lambda: (print_help(), 0)[1],
        "9": None,
        "q": None,
        "quit": None,
        "exit": None,
    }

    print(menu.strip())
    while True:
        try:
            choice = input("\nChoice [1-9]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in {"", "9", "q", "quit", "exit"}:
            print("Bye.")
            return 0
        handler = handlers.get(choice)
        if handler is None:
            print("Unknown choice. Enter 1–9 or q to quit.")
            continue
        if choice in {"4", "5"}:
            handler()
            continue
        print()
        code = handler()
        if choice in {"1", "2", "3"}:
            return code
        print()


def _interactive_ask() -> None:
    question = input("Question: ").strip()
    if not question:
        print("No question entered.")
        return
    cmd_ask([question])


def dispatch(command: str, args: list[str]) -> int:
    key = command.lower()
    if key in {"-h", "--help"}:
        print_help()
        return 0
    handler = COMMANDS.get(key)
    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        print_help()
        return 1
    if key == "help":
        print_help()
        return 0
    return int(handler(args))


def main(argv: list[str] | None = None) -> int:
    from thursday.runtime_paths import ensure_runtime_state

    ensure_runtime_state()
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return interactive()
        print_help()
        return 0
    return dispatch(args[0], args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
