"""Tests for repo-root main.py CLI."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as audio_too_main  # noqa: E402


def test_dispatch_help() -> None:
    assert audio_too_main.dispatch("help", []) == 0


def test_dispatch_unknown() -> None:
    assert audio_too_main.dispatch("not-a-real-command", []) == 1


def test_maintenance_log_prints_no_runs_message_when_empty(monkeypatch, capsys) -> None:
    from kenn.knowledge import maintenance_scheduler as sched

    monkeypatch.setattr(sched, "list_maintenance_runs", lambda limit=20: [])
    assert audio_too_main.cmd_maintenance_log([]) == 0
    assert "No maintenance runs recorded yet." in capsys.readouterr().out


def test_maintenance_log_prints_recent_runs(monkeypatch, capsys) -> None:
    from kenn.knowledge import maintenance_scheduler as sched

    fake_runs = [
        {
            "started_at": "2026-07-12T12:00:00+00:00",
            "job": "contradiction_scan",
            "status": "ok",
            "summary": {"contradictions_detected": 5},
        },
    ]
    monkeypatch.setattr(sched, "list_maintenance_runs", lambda limit=20: fake_runs)
    assert audio_too_main.cmd_maintenance_log([]) == 0
    out = capsys.readouterr().out
    assert "contradiction_scan" in out
    assert "contradictions_detected" in out


def test_maintenance_log_respects_limit_argument(monkeypatch) -> None:
    from kenn.knowledge import maintenance_scheduler as sched

    captured = {}

    def fake_list(limit=20):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(sched, "list_maintenance_runs", fake_list)
    audio_too_main.cmd_maintenance_log(["5"])
    assert captured["limit"] == 5


def test_check_stops_on_python_version_mismatch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(audio_too_main, "supported_python", lambda: (99, 1))

    assert audio_too_main.cmd_check([]) == 1
    assert "Python version gate failed" in capsys.readouterr().err


def test_check_runs_gates_in_order(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(audio_too_main, "supported_python", lambda: sys.version_info[:2])
    monkeypatch.setattr(audio_too_main, "cmd_lint", lambda args: calls.append(("lint", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_test", lambda args: calls.append(("test", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_hygiene", lambda args: calls.append(("hygiene", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_smoke", lambda args: calls.append(("smoke", args)) or 0)

    assert audio_too_main.cmd_check([]) == 0
    assert calls == [
        ("lint", []),
        ("test", ["-q"]),
        ("hygiene", ["all"]),
        ("smoke", []),
    ]


def test_check_full_adds_automix_quality_gate_and_release_health(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(audio_too_main, "supported_python", lambda: sys.version_info[:2])
    monkeypatch.setattr(audio_too_main, "cmd_lint", lambda args: calls.append(("lint", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_test", lambda args: calls.append(("test", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_hygiene", lambda args: calls.append(("hygiene", args)) or 0)
    monkeypatch.setattr(audio_too_main, "cmd_smoke", lambda args: calls.append(("smoke", args)) or 0)
    monkeypatch.setattr(
        audio_too_main, "cmd_automix_quality_gate", lambda args: calls.append(("automix-quality-gate", args)) or 0
    )
    monkeypatch.setattr(audio_too_main, "cmd_release_health", lambda args: calls.append(("release-health", args)) or 0)

    assert audio_too_main.cmd_check(["--full"]) == 0
    assert calls == [
        ("lint", []),
        ("test", ["-q"]),
        ("hygiene", ["all"]),
        ("smoke", []),
        ("automix-quality-gate", []),
        ("release-health", []),
    ]


def test_check_without_full_flag_does_not_run_heavy_gates(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(audio_too_main, "supported_python", lambda: sys.version_info[:2])
    monkeypatch.setattr(audio_too_main, "cmd_lint", lambda args: 0)
    monkeypatch.setattr(audio_too_main, "cmd_test", lambda args: 0)
    monkeypatch.setattr(audio_too_main, "cmd_hygiene", lambda args: 0)
    monkeypatch.setattr(audio_too_main, "cmd_smoke", lambda args: 0)
    monkeypatch.setattr(
        audio_too_main, "cmd_automix_quality_gate", lambda args: calls.append("automix-quality-gate") or 0
    )
    monkeypatch.setattr(audio_too_main, "cmd_release_health", lambda args: calls.append("release-health") or 0)

    assert audio_too_main.cmd_check([]) == 0
    assert calls == []


def test_check_rejects_unknown_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(audio_too_main, "supported_python", lambda: sys.version_info[:2])

    assert audio_too_main.cmd_check(["--bogus"]) == 2
    assert "Usage: ./audio-too check" in capsys.readouterr().err


def test_bench_command_routes_to_benchmark_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("bench", ["--repeat", "2"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "ableton_benchmark.py"
    assert calls[0][0][-2:] == ["--repeat", "2"]


def test_audio_scan_benchmark_adds_benchmark_payload(monkeypatch, capsys, tmp_path) -> None:
    fake_mix_review = types.SimpleNamespace()

    def fake_scan_audio_files(path, *, recursive=True, mix_goal="premaster", reference_path=None):
        assert path == tmp_path
        assert recursive is True
        assert mix_goal == "premaster"
        assert reference_path is None
        return {
            "ok": True,
            "summary": {"elapsed_seconds": 0.5},
            "items": [
                {
                    "ok": True,
                    "filename": "mix.wav",
                    "elapsed_seconds": 0.5,
                    "analysis_speed_x": 2.0,
                    "metrics": {"duration_seconds": 1.0},
                }
            ],
        }

    fake_mix_review.scan_audio_files = fake_scan_audio_files
    fake_mix_review.scan_audio_benchmark = lambda payload: {"files_found": len(payload["items"]), "audio_speed_x": 2.0}
    fake_mix_review.batch_qa_summary = lambda payload: {"totals": {"found": len(payload["items"])}}
    monkeypatch.setitem(sys.modules, "mix_review", fake_mix_review)
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review", types.SimpleNamespace(mix_review=fake_mix_review))
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review.mix_review", fake_mix_review)

    assert audio_too_main.dispatch("audio-scan", [str(tmp_path), "--benchmark", "--qa"]) == 0
    output = capsys.readouterr().out

    assert '"benchmark"' in output
    assert '"audio_speed_x": 2.0' in output
    assert '"qa"' in output


def test_audio_scan_music_analysis_csv_output(monkeypatch, capsys, tmp_path) -> None:
    fake_mix_review = types.SimpleNamespace()
    scan_payload = {
        "ok": True,
        "root": str(tmp_path),
        "summary": {"elapsed_seconds": 0.5},
        "items": [
            {
                "ok": True,
                "filename": "song.wav",
                "relative_path": "song.wav",
                "status": "analyzed",
                "elapsed_seconds": 0.5,
                "analysis_speed_x": 2.0,
                "metrics": {
                    "filename": "song.wav",
                    "duration_seconds": 1.0,
                    "chords": {
                        "estimated_key": "C Major",
                        "key_confidence": "high",
                        "key_confidence_score": 0.91,
                        "progression": [{"chord": "C Maj"}],
                        "intervals": [],
                    },
                    "technical_score": 88,
                },
            }
        ],
    }
    batch_payload = {
        "ok": True,
        "items": [
            {
                "filename": "song.wav",
                "relative_path": "song.wav",
                "ok": True,
                "status": "analyzed",
                "estimated_key": "C Major",
                "key_confidence": "high",
                "key_confidence_score": 0.91,
                "progression_summary": "C Maj",
                "technical_context": {"technical_score": 88},
            }
        ],
    }

    fake_mix_review.scan_audio_files = lambda *args, **kwargs: scan_payload
    fake_mix_review.batch_qa_summary = lambda payload: {"totals": {"found": 1}}
    fake_mix_review.batch_music_analysis = lambda payload: batch_payload
    fake_mix_review.batch_music_analysis_csv = lambda payload: "filename,estimated_key\nsong.wav,C Major\n"
    monkeypatch.setitem(sys.modules, "mix_review", fake_mix_review)
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review", types.SimpleNamespace(mix_review=fake_mix_review))
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review.mix_review", fake_mix_review)

    assert audio_too_main.dispatch("audio-scan", [str(tmp_path), "--music-analysis", "--format", "csv"]) == 0
    output = capsys.readouterr().out

    assert "filename,estimated_key" in output
    assert "song.wav,C Major" in output


def test_audio_scan_music_analysis_json_keeps_scan_sections(monkeypatch, capsys, tmp_path) -> None:
    fake_mix_review = types.SimpleNamespace()
    scan_payload = {
        "ok": True,
        "root": str(tmp_path),
        "summary": {"found": 1, "analyzed": 1, "failed": 0},
        "items": [{"ok": True, "filename": "song.wav", "metrics": {"duration_seconds": 1.0}}],
    }
    batch_payload = {
        "ok": True,
        "root": str(tmp_path),
        "summary": {"found": 1, "analyzed": 1, "failed": 0, "keys": {"C Major": 1}},
        "items": [{"ok": True, "filename": "song.wav", "estimated_key": "C Major"}],
    }

    fake_mix_review.scan_audio_files = lambda *args, **kwargs: dict(scan_payload)
    fake_mix_review.scan_audio_benchmark = lambda payload: {"files_found": 1, "audio_speed_x": 2.0}
    fake_mix_review.batch_qa_summary = lambda payload: {"totals": {"found": 1, "high_risk": 0}}
    fake_mix_review.batch_music_analysis = lambda payload: batch_payload
    fake_mix_review.batch_music_analysis_csv = lambda payload: ""
    monkeypatch.setitem(sys.modules, "mix_review", fake_mix_review)
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review", types.SimpleNamespace(mix_review=fake_mix_review))
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review.mix_review", fake_mix_review)

    assert audio_too_main.dispatch("audio-scan", [str(tmp_path), "--benchmark", "--qa", "--music-analysis"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["scan"]["summary"]["found"] == 1
    assert payload["benchmark"]["audio_speed_x"] == 2.0
    assert payload["qa"]["totals"]["found"] == 1
    assert payload["music_analysis"]["summary"]["keys"] == {"C Major": 1}


def test_analysis_feedback_command_records_decision(monkeypatch, capsys, tmp_path) -> None:
    fake_mix_review = types.SimpleNamespace()
    fake_mix_review.record_review_feedback = lambda review_id, decision, note, path=None: {
        "ok": True,
        "review_id": review_id,
        "path": str(path or ""),
        "record": {"decision": decision, "note": note},
    }
    monkeypatch.setitem(sys.modules, "mix_review", fake_mix_review)
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review", types.SimpleNamespace(mix_review=fake_mix_review))
    monkeypatch.setitem(sys.modules, "audio_analysis.mix_review.mix_review", fake_mix_review)

    assert audio_too_main.dispatch("analysis-feedback", ["review-1", "accepted", "Useful move.", "--output", str(tmp_path / "records.jsonl")]) == 0
    output = capsys.readouterr().out

    assert '"review_id": "review-1"' in output
    assert '"decision": "accepted"' in output


def test_audit_command_routes_to_audit_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("audit", ["--repeat", "2"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "ableton_audit.py"
    assert calls[0][0][-2:] == ["--repeat", "2"]


def test_trends_command_routes_to_trend_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("trends", ["--limit", "4"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_benchmark_trends.py"
    assert calls[0][0][-2:] == ["--limit", "4"]


def test_tester_probe_command_routes_to_probe_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("tester-probe", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_tester_probe.py"
    assert calls[0][0][-1:] == ["--json"]


def test_benchmark_gate_command_routes_to_gate_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("benchmark-gate", ["--max-p95-ms", "100"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_benchmark_gate.py"
    assert calls[0][0][-2:] == ["--max-p95-ms", "100"]


def test_fetch_models_command_routes_to_both_fetch_scripts(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("fetch-models", []) == 0
    assert len(calls) == 2
    assert Path(calls[0][0][1]).name == "fetch_embedding_model.py"
    assert Path(calls[1][0][1]).name == "fetch_kokoro_model.py"


def test_fetch_models_command_stops_on_first_failure(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 1

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("fetch-models", []) == 1
    # Kokoro fetch must not run once the embedding-model fetch fails.
    assert len(calls) == 1


def test_feedback_review_command_routes_to_feedback_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("feedback-review", ["--export"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_feedback_review.py"
    assert calls[0][0][-1:] == ["--export"]


def test_promote_feedback_evals_command_routes_to_promote_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("promote-feedback-evals", ["--id", "feedback-a"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_promote_feedback_evals.py"
    assert calls[0][0][-2:] == ["--id", "feedback-a"]


def test_brain_score_command_routes_to_score_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("brain-score", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_brain_score.py"
    assert calls[0][0][-1:] == ["--json"]


def test_reranker_export_command_routes_to_export_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("reranker-export", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_reranker_export.py"
    assert calls[0][0][-1:] == ["--json"]


def test_hard_negative_mine_command_routes_to_mine_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("hard-negative-mine", ["--limit", "5"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_hard_negative_mine.py"
    assert calls[0][0][-2:] == ["--limit", "5"]


def test_hard_negative_report_command_routes_to_promote_script_list_mode(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("hard-negative-report", ["--limit", "3"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_promote_hard_negative.py"
    assert calls[0][0][-3:] == ["--list", "--limit", "3"]


def test_promote_hard_negative_command_routes_to_promote_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("promote-hard-negative", ["--case-id", "case-1"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_promote_hard_negative.py"
    assert calls[0][0][-2:] == ["--case-id", "case-1"]


def test_validate_hard_negatives_command_routes_to_validator(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("validate-hard-negatives", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_validate_hard_negatives.py"
    assert calls[0][0][-1:] == ["--json"]


def test_kenn_index_rollback_routes_to_safe_preview_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("kenn-index-rollback", ["--json"]) == 0
    assert Path(calls[0][0][1]).name == "kenn_index_rollback.py"
    assert calls[0][0][-1:] == ["--json"]


def test_reranker_train_command_routes_to_train_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("reranker-train", ["--backend", "linear"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_reranker_train.py"
    assert calls[0][0][-2:] == ["--backend", "linear"]


def test_reranker_eval_command_routes_to_eval_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("reranker-eval", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_reranker_eval.py"
    assert calls[0][0][-1:] == ["--json"]


def test_export_training_command_routes_to_export_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("export-training", ["--limit", "4"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "export_training_data.py"
    assert calls[0][0][-2:] == ["--limit", "4"]


def test_knowledge_audit_command_routes_to_audit_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("knowledge-audit", ["--strict"]) == 0
    assert Path(calls[0][0][1]).name == "kenn_knowledge_audit.py"
    assert calls[0][0][-1:] == ["--strict"]


def test_knowledge_gaps_command_routes_to_gap_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("knowledge-gaps", ["--no-recheck"]) == 0
    assert Path(calls[0][0][1]).name == "kenn_gap_report.py"


def test_repair_training_command_routes_to_creative_repair_export_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("repair-training", ["--summary-only"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "export_creative_repair_training.py"
    assert calls[0][0][-1:] == ["--summary-only"]


def test_kenn_ready_command_routes_to_readiness_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("kenn-ready", ["--json"]) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "kenn_readiness.py"
    assert calls[0][0][-1:] == ["--json"]


def test_hygiene_command_routes_to_repo_hygiene_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("hygiene", []) == 0
    assert calls
    assert Path(calls[0][0][1]).name == "repo_hygiene.py"
    assert calls[0][0][-1:] == ["all"]


def test_hygiene_subcommand_routes_to_repo_hygiene_script(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None):
        calls.append((cmd, cwd))
        return 0

    monkeypatch.setattr(audio_too_main, "run", fake_run)
    assert audio_too_main.dispatch("hygiene", ["sizes", "--limit", "5"]) == 0
    assert calls[0][0][-3:] == ["sizes", "--limit", "5"]


def test_smoke_check_covers_repair_training_summary() -> None:
    smoke = (ROOT / "scripts" / "eval" / "smoke_check.py").read_text(encoding="utf-8")
    assert '"repair-training", "--summary-only"' in smoke
    assert "repair-training summary" in smoke


def test_audiogen_phrase_command_routes_to_bridge(monkeypatch, capsys) -> None:
    website = ROOT / "server" / "app"
    if str(website) not in sys.path:
        sys.path.insert(0, str(website))
    import audiogen_bridge

    calls = []

    def fake_phrase_command(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "result": {"ok": True}}

    monkeypatch.setattr(audiogen_bridge, "phrase_command", fake_phrase_command)

    assert audio_too_main.dispatch("audiogen", ["phrase", "--emotion", "joy", "--bars", "4"]) == 0
    assert calls == [{"emotion": "joy", "bars": 4, "seed": "", "wav_out": None, "include_events": False}]
    assert '"ok": true' in capsys.readouterr().out


def test_audiogen_render_command_routes_to_bridge(monkeypatch) -> None:
    website = ROOT / "server" / "app"
    if str(website) not in sys.path:
        sys.path.insert(0, str(website))
    import audiogen_bridge

    calls = []

    def fake_render_command(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(audiogen_bridge, "render_command", fake_render_command)

    assert audio_too_main.dispatch("audiogen", ["render", "--emotion", "grief", "--k", "2"]) == 0
    assert calls == [{"emotion": "grief", "k": 2, "args": []}]


def test_audiogen_audit_command_routes_to_bridge(monkeypatch) -> None:
    website = ROOT / "server" / "app"
    if str(website) not in sys.path:
        sys.path.insert(0, str(website))
    import audiogen_bridge

    calls = []

    def fake_audit_command(args):
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(audiogen_bridge, "audit_command", fake_audit_command)

    assert audio_too_main.dispatch("audiogen", ["audit", "--quick"]) == 0
    assert calls == [["--quick"]]


def test_status_reports_ports(monkeypatch, capsys) -> None:
    monkeypatch.setattr(audio_too_main, "port_open", lambda port: port == audio_too_main.WEB_PORT)
    monkeypatch.setattr(audio_too_main, "http_healthy", lambda port, path="/", timeout=3.0: port == audio_too_main.WEB_PORT)
    website = ROOT / "server" / "app"
    if str(website) not in sys.path:
        sys.path.insert(0, str(website))
    import audiogen_bridge

    monkeypatch.setattr(audiogen_bridge, "status", lambda: {"ok": True})

    assert audio_too_main.dispatch("status", []) == 1
    out = capsys.readouterr().out
    assert "Website :8080: online" in out
    assert "KENN    :8090: offline" in out
    assert "AudioGen     : ready" in out
    assert "Next step    : ./audio-too start --no-open" in out


def test_stop_terminates_known_port_pids(monkeypatch, capsys, tmp_path) -> None:
    killed = []
    monkeypatch.setattr(audio_too_main, "ROOT", tmp_path)
    monkeypatch.setattr(audio_too_main, "pids_for_port", lambda port: [111] if port == 8080 else [])
    monkeypatch.setattr(audio_too_main.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    assert audio_too_main.dispatch("stop", []) == 0
    assert killed == [(111, audio_too_main.signal.SIGTERM)]
    assert "stopped pid 111" in capsys.readouterr().out


def test_main_no_args_non_tty_prints_help(capsys, monkeypatch) -> None:
    monkeypatch.setattr(audio_too_main.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(audio_too_main.sys.stdout, "isatty", lambda: False)
    assert audio_too_main.main([]) == 0
    assert "Audio_Too" in capsys.readouterr().out
