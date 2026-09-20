"""Tests for Mix Review Lab WAV analysis."""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))
sys.path.insert(0, str(ROOT / "studio" / "agents"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from MixReview import revision_agent  # noqa: E402
from audio_analysis.mix_review import mix_review  # noqa: E402


def sine_wav(
    *,
    frequency: float = 120.0,
    seconds: float = 0.2,
    sample_rate: int = 8000,
    channels: int = 1,
    amplitude: float = 0.5,
    inverted_right: bool = False,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = []
        for index in range(int(seconds * sample_rate)):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * index / sample_rate))
            if channels == 1:
                frames.append(struct.pack("<h", value))
            else:
                right = -value if inverted_right else value
                frames.append(struct.pack("<hh", value, right))
        wav.writeframes(b"".join(frames))
    return buffer.getvalue()


def chord_progression_wav(
    progression: list[tuple[str, list[float]]],
    *,
    seconds_per_chord: float = 1.2,
    sample_rate: int = 8000,
    amplitude: float = 0.45,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = []
        chord_frames = int(seconds_per_chord * sample_rate)
        fade_frames = max(1, int(0.05 * sample_rate))
        for _name, freqs in progression:
            for index in range(chord_frames):
                envelope = min(1.0, index / fade_frames, (chord_frames - index) / fade_frames)
                sample = sum(math.sin(2 * math.pi * freq * index / sample_rate) for freq in freqs) / len(freqs)
                value = int(max(-1.0, min(1.0, sample * amplitude * envelope)) * 32767)
                frames.append(struct.pack("<h", value))
        wav.writeframes(b"".join(frames))
    return buffer.getvalue()


def test_analyze_wav_returns_metrics_and_advice() -> None:
    report = mix_review.analyze_wav(sine_wav(), "bass-test.wav")

    assert report["ok"] is True
    assert report["metrics"]["sample_rate"] == 8000
    assert report["metrics"]["channels"] == 1
    assert "bass" in report["metrics"]["bands"]
    assert "technical_score" in report["metrics"]
    assert "stereo_correlation" in report["metrics"]
    assert "perceptual_bands" in report["metrics"]
    assert "perceptual_summary" in report["metrics"]
    assert "spectral_features" in report["metrics"]
    assert "tonal_balance" in report["metrics"]
    assert "dynamic_profile" in report["metrics"]
    assert "stereo_field" in report["metrics"]
    assert "goal_target_checks" in report["metrics"]
    assert report["metrics"]["mix_goal"]["key"] == "premaster"
    assert report["metrics"]["tonal_balance"]["profile"]
    assert report["metrics"]["dynamic_profile"]["profile"]
    assert report["metrics"]["stereo_field"]["summary"]
    assert report["metrics"]["section_analysis"]["sections"]
    assert report["metrics"]["section_analysis"]["highlights"]["loudest_section"]
    assert report["metrics"]["goal_target_checks"]["checks"]
    assert report["lesson_cards"]
    assert report["source_hypotheses"]
    assert report["frequency_repair_map"]
    assert report["ableton_repair_templates"]
    assert report["ableton_repair_chains"]["schema"] == "audio_too.ableton_repair_chains.v1"
    assert report["closed_loop_action_plan"]["schema"] == "audio_too.closed_loop_action_plan.v1"
    assert report["closed_loop_action_plan"]["steps"]
    assert any(item["range"] == "150-400 Hz" for item in report["frequency_repair_map"])
    assert report["revision_lesson"]["steps"]
    assert "flags" in report
    assert report["summary"]
    assert report["action_plan"]
    assert report["advice"]
    assert report["flags"][0]["confidence"] in {"high", "medium", "low"}
    assert report["action_plan"][0]["rank"] == 1
    assert report["action_plan"][0]["decision"] in {"fix_first", "check_by_ear", "needs_reference"}
    assert report["action_plan"][0]["confidence"] in {"high", "medium", "low"}


def test_scan_audio_files_analyzes_wavs_and_decoded_formats(tmp_path, monkeypatch) -> None:
    from audio_analysis.utils import audio_io_api

    wav_path = tmp_path / "mix.wav"
    mp3_path = tmp_path / "preview.mp3"
    wav_path.write_bytes(sine_wav())
    mp3_path.write_bytes(b"fake mp3 bytes")

    monkeypatch.setattr(audio_io_api, "_decode_with_soundfile_path", lambda _path: None)
    monkeypatch.setattr(audio_io_api, "_decode_with_ffmpeg_path", lambda _path: (sine_wav(frequency=440), "ffmpeg"))

    result = mix_review.scan_audio_files(tmp_path)

    assert result["ok"] is True
    assert result["summary"]["found"] == 2
    assert result["summary"]["analyzed"] == 2
    assert result["summary"]["skipped"] == 0

    analyzed = next(item for item in result["items"] if item["filename"] == "mix.wav")
    decoded = next(item for item in result["items"] if item["filename"] == "preview.mp3")

    assert analyzed["ok"] is True
    assert analyzed["summary"]
    assert analyzed["metrics"]["filename"] == "mix.wav"
    assert analyzed["kenn_handoff"]["schema"] == "kenn_mix_review_handoff.v1"
    assert analyzed["closed_loop_action_plan"]["steps"]
    assert analyzed["ableton_repair_chains"]["chains"]
    assert decoded["ok"] is True
    assert decoded["metrics"]["decoder"] == "ffmpeg"
    assert decoded["metrics"]["source_format"] == "mp3"


def test_scan_audio_files_compares_against_reference(tmp_path) -> None:
    mixes = tmp_path / "mixes"
    mixes.mkdir()
    mix_path = mixes / "mix.wav"
    reference_path = tmp_path / "reference.wav"
    mix_path.write_bytes(sine_wav(frequency=120, amplitude=0.35))
    reference_path.write_bytes(sine_wav(frequency=1200, amplitude=0.65))

    result = mix_review.scan_audio_files(mixes, reference_path=reference_path)

    assert result["ok"] is True
    assert result["reference"]["filename"] == "reference.wav"
    item = result["items"][0]
    assert item["comparison"]
    assert item["comparison_advice"]
    assert item["reference_coaching"]
    assert item["judgment"]["summary"] == item["summary"]


def test_handle_multipart_music_analysis_returns_chords() -> None:
    boundary = "music-boundary"
    wav_bytes = sine_wav(frequency=440, seconds=0.6)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="mix_goal"\r\n\r\n'
        "premaster\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="music.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_music_analysis(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    assert result["analysis"]["filename"] == "music.wav"
    assert "estimated_key" in result["analysis"]
    assert result["analysis"]["key_confidence"] in {"high", "medium", "low"}
    assert "progression" in result["analysis"]
    assert "intervals" in result["analysis"]
    assert result["analysis"]["technical_context"]["technical_score"] is not None


def test_handle_multipart_waveform_returns_downsampled_peaks() -> None:
    boundary = "waveform-boundary"
    wav_bytes = sine_wav(frequency=440, seconds=2.0)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="points"\r\n\r\n'
        "150\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="clip.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_waveform(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    assert result["points"] == 150
    assert len(result["peaks"]) == 150
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.05)
    # Never raw samples -- see analysis_core/waveform.py's own docstring on why.
    assert "samples" not in result


def test_handle_multipart_waveform_rejects_a_missing_file_field() -> None:
    boundary = "waveform-boundary-2"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="points"\r\n\r\n'
        "150\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    result = mix_review.handle_multipart_waveform(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is False
    assert "file" in result["error"].lower()


def test_handle_multipart_podcast_check_returns_a_scored_report() -> None:
    boundary = "podcast-boundary"
    wav_bytes = sine_wav(frequency=200, seconds=2.0, amplitude=0.2)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="target"\r\n\r\n'
        "spotify\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="episode.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_podcast_check(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    report = result["report"]
    assert report["target_label"]
    assert isinstance(report["score"], (int, float))
    assert isinstance(report["checks"], list)
    assert "<html" in result["html_report"].lower()


def test_handle_multipart_delivery_conform_returns_a_scored_report() -> None:
    boundary = "delivery-boundary"
    wav_bytes = sine_wav(frequency=200, seconds=2.0, amplitude=0.2)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="target"\r\n\r\n'
        "apple_music\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="master.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_delivery_conform(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    report = result["report"]
    assert report["target_label"] == "Apple Music"
    assert isinstance(report["score"], (int, float))
    assert isinstance(report["checks"], list)
    assert "<html" in result["html_report"].lower()


def test_handle_multipart_delivery_conform_defaults_target_to_spotify() -> None:
    boundary = "delivery-boundary-2"
    wav_bytes = sine_wav(frequency=200, seconds=1.0, amplitude=0.2)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="master.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_delivery_conform(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    assert result["report"]["target_label"] == "Spotify"


def test_handle_multipart_delivery_conform_rejects_a_missing_file_field() -> None:
    boundary = "delivery-boundary-3"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="target"\r\n\r\n'
        "spotify\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    result = mix_review.handle_multipart_delivery_conform(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is False
    assert "file" in result["error"].lower()


def test_handle_multipart_podcast_check_defaults_target_to_apple() -> None:
    boundary = "podcast-boundary-2"
    wav_bytes = sine_wav(frequency=200, seconds=1.0, amplitude=0.2)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="episode.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = mix_review.handle_multipart_podcast_check(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    assert "apple" in result["report"]["target_label"].lower()


def test_handle_multipart_podcast_check_rejects_a_missing_file_field() -> None:
    boundary = "podcast-boundary-3"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="target"\r\n\r\n'
        "apple\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    result = mix_review.handle_multipart_podcast_check(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is False
    assert "file" in result["error"].lower()


def test_music_analysis_detects_known_c_major_progression() -> None:
    wav_bytes = chord_progression_wav(
        [
            ("C", [261.63, 329.63, 392.00]),
            ("Am", [220.00, 261.63, 329.63]),
            ("F", [174.61, 220.00, 261.63]),
            ("G", [196.00, 246.94, 293.66]),
        ]
    )

    report = mix_review.analyze_wav(wav_bytes, "c-am-f-g.wav")
    chords = report["metrics"]["chords"]
    detected = [segment["chord"] for segment in chords["progression"] if segment["chord"] != "N.C."]

    assert chords["estimated_key"] == "C Major"
    assert chords["key_confidence"] in {"high", "medium", "low"}
    assert chords["key_confidence_score"] > 0
    assert chords["key_confidence_explanation"]
    assert chords["progression_confidence_summary"]
    assert detected[:4] == ["C Maj", "A Min", "F Maj", "G Maj"]
    assert all(segment["confidence"] in {"high", "medium", "low"} for segment in chords["progression"])
    assert all(segment["confidence_score"] >= 0 for segment in chords["progression"])
    assert [item["semitones"] for item in chords["intervals"][:3]] == [9, 8, 2]
    assert "stable_progression" in chords["analysis_notes"]
    assert chords["sanity"]["complex_chord_ratio"] <= 0.35


def test_scan_audio_benchmark_summarizes_throughput(tmp_path) -> None:
    for index in range(3):
        (tmp_path / f"mix-{index}.wav").write_bytes(sine_wav(frequency=120 + index * 20, seconds=0.15))

    result = mix_review.scan_audio_files(tmp_path)
    benchmark = mix_review.scan_audio_benchmark(result)

    assert benchmark["files_found"] == 3
    assert benchmark["files_analyzed"] == 3
    assert benchmark["files_failed"] == 0
    assert benchmark["total_elapsed_seconds"] >= 0
    assert benchmark["total_audio_seconds"] > 0
    assert benchmark["average_file_seconds"] >= 0
    assert benchmark["p50_file_seconds"] >= 0
    assert benchmark["slowest_files"]
    assert "filename" in benchmark["slowest_files"][0]


def test_batch_qa_summary_ranks_catalogue_risk(tmp_path) -> None:
    (tmp_path / "clean.wav").write_bytes(sine_wav(amplitude=0.2))
    (tmp_path / "hot.wav").write_bytes(sine_wav(amplitude=0.99, channels=2, inverted_right=True))

    result = mix_review.scan_audio_files(tmp_path)
    qa = mix_review.batch_qa_summary(result)

    assert qa["schema"] == "audio_too.batch_qa_summary.v1"
    assert qa["totals"]["found"] == 2
    assert qa["ranked_items"]
    assert qa["ranked_items"][0]["risk"] in {"failed", "high", "medium", "low"}
    assert isinstance(qa["issue_counts"], dict)


def test_record_review_feedback_writes_learning_record(tmp_path, monkeypatch) -> None:
    report = mix_review.analyze_wav(sine_wav(), "feedback.wav")
    monkeypatch.setattr(mix_review, "review_by_id", lambda _review_id: {"report_name": "feedback.json"})
    monkeypatch.setattr(mix_review, "read_report", lambda _name: report)

    output = tmp_path / "feedback.jsonl"
    result = mix_review.record_review_feedback("review-1", "accepted", "Good first fix.", path=output)

    assert result["ok"] is True
    assert result["record"]["schema"] == "audio_too.analysis_feedback.v1"
    assert result["record"]["decision"] == "accepted"
    assert "feedback.wav" in output.read_text(encoding="utf-8")


def test_repair_chains_json_bytes_exports_review_payload(monkeypatch) -> None:
    report = mix_review.analyze_wav(sine_wav(), "repair-export.wav")
    monkeypatch.setattr(mix_review, "review_by_id", lambda _review_id: report)

    body = mix_review.repair_chains_json_bytes("review-1")

    assert body is not None
    text = body.decode("utf-8")
    assert "audio_too.ableton_repair_chains.v1" in text
    assert "repair-export.wav" in text


def test_batch_music_analysis_exports_json_ready_summary_and_csv(tmp_path) -> None:
    wav_bytes = chord_progression_wav(
        [
            ("C", [261.63, 329.63, 392.00]),
            ("Am", [220.00, 261.63, 329.63]),
            ("F", [174.61, 220.00, 261.63]),
            ("G", [196.00, 246.94, 293.66]),
        ],
        seconds_per_chord=0.8,
    )
    (tmp_path / "known-progression.wav").write_bytes(wav_bytes)

    scan = mix_review.scan_audio_files(tmp_path)
    scan["benchmark"] = mix_review.scan_audio_benchmark(scan)
    batch = mix_review.batch_music_analysis(scan)
    csv_text = mix_review.batch_music_analysis_csv(batch)

    assert batch["ok"] is True
    assert batch["benchmark"]["files_found"] == 1
    assert batch["summary"]["found"] == 1
    assert batch["items"][0]["estimated_key"] != "Unknown"
    assert batch["items"][0]["key_confidence"] in {"high", "medium", "low"}
    assert batch["items"][0]["key_confidence_explanation"]
    assert batch["items"][0]["progression_confidence_summary"]
    assert "progression_summary" in batch["items"][0]
    assert "analysis_notes_summary" in batch["items"][0]
    assert "filename,relative_path,ok" in csv_text
    assert "analysis_notes" in csv_text.splitlines()[0]
    assert "key_confidence_explanation" in csv_text.splitlines()[0]
    assert "known-progression.wav" in csv_text


def test_goal_target_checks_follow_selected_mix_goal() -> None:
    club_report = mix_review.analyze_wav(sine_wav(frequency=55, channels=2), "club.wav", mix_goal="club")
    podcast_report = mix_review.analyze_wav(sine_wav(frequency=220, channels=1), "podcast.wav", mix_goal="podcast")

    club_checks = club_report["metrics"]["goal_target_checks"]
    podcast_checks = podcast_report["metrics"]["goal_target_checks"]

    assert club_checks["goal"]["key"] == "club"
    assert podcast_checks["goal"]["key"] == "podcast"
    assert any(check["label"] == "Low-end mono safety" for check in club_checks["checks"])
    assert any(check["label"] == "Consistent level" for check in podcast_checks["checks"])


def test_goal_target_checks_use_editable_config(tmp_path, monkeypatch) -> None:
    config = tmp_path / "targets.json"
    config.write_text(
        __import__("json").dumps(
            {
                "goals": {
                    "premaster": {
                        "summary": "Custom premaster target.",
                        "checks": [
                            {
                                "label": "Custom crest",
                                "metric": "crest_factor_db",
                                "min": 99,
                                "target": "Crest above 99 dB",
                                "education": "Proof that the JSON target file is active.",
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mix_review, "TARGET_CONFIG_PATH", config)

    report = mix_review.analyze_wav(sine_wav(), "custom-target.wav")
    checks = report["metrics"]["goal_target_checks"]

    assert checks["summary"] == "Custom premaster target."
    assert checks["checks"][0]["label"] == "Custom crest"
    assert checks["checks"][0]["status"] == "warn"
    assert checks["config_path"] == str(config)


def test_goal_target_checks_fall_back_when_config_is_invalid(tmp_path, monkeypatch) -> None:
    config = tmp_path / "broken-targets.json"
    config.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(mix_review, "TARGET_CONFIG_PATH", config)

    report = mix_review.analyze_wav(sine_wav(), "fallback-target.wav")
    labels = [check["label"] for check in report["metrics"]["goal_target_checks"]["checks"]]

    assert "Peak headroom" in labels


def test_kenn_handoff_contains_mix_review_context() -> None:
    report = mix_review.analyze_wav(sine_wav(), "handoff.wav")
    report["title"] = "Handoff Mix"
    mix_review.refresh_closed_loop_payloads(report)
    handoff = mix_review.kenn_handoff(report)

    assert handoff["schema"] == "kenn_mix_review_handoff.v1"
    assert handoff["title"] == "Handoff Mix"
    assert handoff["review_summary"] == report["summary"]
    assert handoff["metrics"]["technical_score"] == report["metrics"]["technical_score"]
    assert handoff["technical_metrics"]["peak_dbfs"] == report["metrics"]["peak_dbfs"]
    assert handoff["judgment"]["technical_score"] == report["metrics"]["technical_score"]
    assert handoff["section_highlights"]
    assert handoff["flags"]
    assert handoff["priority_actions"]
    assert handoff["priority_actions"][0]["decision"]
    assert handoff["ableton_repair_templates"]
    assert handoff["closed_loop_action_plan"]["schema"] == "audio_too.closed_loop_action_plan.v1"
    assert handoff["ableton_repair_chains"]["schema"] == "audio_too.ableton_repair_chains.v1"
    assert handoff["session_report"]["schema"] == "audio_too.session_report.v1"
    assert handoff["session_report"]["fix_first"]
    assert any("Fix first:" in line for line in handoff["session_report"]["kenn_memory_lines"])
    assert handoff["context_lines"]
    assert "Mix Review Lab context for Handoff Mix" in handoff["context"]
    assert "first three mix fixes" in handoff["prompt"]


def test_session_report_packages_engineer_and_client_summary() -> None:
    report = mix_review.analyze_wav(sine_wav(), "session-report.wav", mix_goal="club")
    report["title"] = "Session Report Mix"
    mix_review.refresh_closed_loop_payloads(report)
    session = report["session_report"]

    assert session["schema"] == "audio_too.session_report.v1"
    assert session["title"] == "Session Report Mix"
    assert session["fix_first"]
    assert session["leave_alone"]
    assert session["v2_export_checklist"]
    assert session["client_summary"]
    assert any(line.startswith("Track:") for line in session["kenn_memory_lines"])


def test_ableton_repair_templates_map_flags_to_live_moves() -> None:
    repairs = mix_review.ableton_repair_templates(
        [{"severity": "medium", "label": "Low-mid build-up", "detail": "150-400 Hz looks prominent."}],
        {"technical_score": 80},
    )

    assert repairs[0]["flag"] == "Low-mid build-up"
    assert "EQ Eight" in repairs[0]["device_chain"]
    assert "150-400 Hz" in repairs[0]["move"]
    assert repairs[0]["check"]


def test_next_revision_plan_combines_revision_reference_and_repair_moves() -> None:
    report = {
        "summary": "Solid with checks.",
        "metrics": {"technical_score": 78},
        "flags": [{"severity": "medium", "label": "Low dynamics", "detail": "Crest is low."}],
        "action_plan": [
            {
                "focus": "Low dynamics",
                "action": "Ease the limiter.",
                "reason": "Crest is low.",
            }
        ],
        "ableton_repair_templates": [
            {
                "flag": "Low dynamics",
                "device_chain": "Limiter",
                "move": "Reduce limiter input by 2 dB.",
                "target": "Restore punch.",
                "check": "Level-match the chorus.",
            }
        ],
        "comparison_advice": ["Reference has more crest factor."],
        "version_advice": ["Dynamics increased compared with the previous version."],
        "revision_coaching": {
            "headline": "This revision moved in the right direction.",
            "verdict": "improved",
            "score_delta": 8,
            "cleared_flags": ["Low headroom"],
            "new_flags": [],
            "unchanged_flags": ["Low dynamics"],
            "next_focus": "Remaining flag to address: Low dynamics.",
            "listening_test": "Level-match v1 and v2.",
        },
        "reference_coaching": {
            "headline": "Reference check.",
            "next_move": "Check punch against the reference.",
            "level_message": "Level-match before judging.",
        },
    }

    plan = mix_review.next_revision_plan(report)

    assert plan["schema"] == "kenn.next_revision_plan.v1"
    assert plan["verdict"] == "improved"
    assert plan["focus"] == "Remaining flag to address: Low dynamics."
    assert plan["cleared_flags"] == ["Low headroom"]
    assert any(step["source"] == "ableton_repair" for step in plan["steps"])
    assert any("Level-match" in check for check in plan["checks"])


def test_a_weighting_deemphasizes_subs_against_presence() -> None:
    assert mix_review.a_weighting_gain(50) < mix_review.a_weighting_gain(3000)


def test_analyze_wav_flags_clipping_and_mono_risk() -> None:
    report = mix_review.analyze_wav(
        sine_wav(frequency=1000.0, channels=2, amplitude=1.0, inverted_right=True),
        "phase-risk.wav",
    )

    labels = {flag["label"] for flag in report["flags"]}
    assert "Clipping risk" in labels
    assert "Mono risk" in labels
    assert report["metrics"]["technical_score"] < 100
    assert report["metrics"]["stereo_correlation"] < 0
    assert report["technical_metrics"]["peak_dbfs"] == report["metrics"]["peak_dbfs"]
    assert report["technical_metrics"]["section_analysis"]["sections"]
    assert "technical_score" not in report["technical_metrics"]
    assert report["judgment"]["technical_score"] == report["metrics"]["technical_score"]
    assert report["judgment"]["action_plan"] == report["action_plan"]


def test_save_review_with_reference_adds_comparison(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0, amplitude=0.4),
        filename="mix.wav",
        reference_bytes=sine_wav(frequency=1000.0, amplitude=0.6),
        reference_filename="reference.wav",
    )

    assert result["ok"] is True
    review = result["review"]
    assert review["reference"]["filename"] == "reference.wav"
    assert "rms_delta_db" in review["comparison"]
    assert "perceptual_band_delta" in review["comparison"]
    assert "largest_perceptual_difference" in review["comparison"]
    assert review["comparison_advice"]
    assert review["reference_coaching"]["headline"]
    assert "Level-match" in review["reference_coaching"]["level_message"]
    assert review["reference_coaching"]["next_move"]
    assert review["summary"]
    assert any(item["priority"] == "reference" for item in review["action_plan"])
    assert review["revision_agent"]["steps"]
    assert any(uploads.glob("*reference_reference.wav"))


def test_revision_agent_plan_creates_checklist_from_report() -> None:
    report = mix_review.analyze_wav(sine_wav(amplitude=0.95), "agent-test.wav")
    report.update(
        {
            "title": "Agent Test",
            "comparison_advice": ["Reference is wider than this mix."],
            "version_advice": ["This version is louder than v1."],
        }
    )

    agent = revision_agent.revision_agent_plan(report)

    assert agent["agent"] == "mix_revision_agent"
    assert "Agent Test" in agent["goal"]
    assert agent["steps"]
    assert any(step["focus"] == "Reference check" for step in agent["steps"])
    assert any(step["focus"] == "Revision check" for step in agent["steps"])
    assert agent["steps"][-1]["category"] == "export"


def test_revision_agent_impact_summarises_done_steps() -> None:
    previous = mix_review.analyze_wav(sine_wav(amplitude=0.9), "v1.wav")
    current = mix_review.analyze_wav(sine_wav(amplitude=0.4), "v2.wav")
    previous["revision_agent"] = {
        "steps": [{"id": "step-1", "status": "done", "focus": "Dynamics", "action": "Ease limiter."}]
    }
    current["version_comparison"] = mix_review.compare_metrics(current["metrics"], previous["metrics"])

    impact = revision_agent.revision_impact_summary(current, previous)

    assert impact is not None
    assert impact["completed_step_count"] == 1
    assert impact["completed_steps"][0]["action"] == "Ease limiter."
    assert impact["verdict"] in {"improved", "regressed", "mixed", "similar"}
    assert impact["checks"]


def test_save_reference_stores_metrics(tmp_path, monkeypatch) -> None:
    references = tmp_path / "references"
    monkeypatch.setattr(mix_review, "REFERENCE_ROOT", references)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_reference(
        file_bytes=sine_wav(frequency=1000.0),
        filename="bright-reference.wav",
        name="Bright Pop Ref",
        style="pop",
    )

    assert result["ok"] is True
    reference = result["reference"]
    assert reference["name"] == "Bright Pop Ref"
    assert reference["style"] == "pop"
    assert reference["metrics"]["technical_score"]
    assert any(references.glob("*bright-reference.wav"))


def test_save_review_uses_saved_reference(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    saved_metrics = mix_review.analyze_wav(sine_wav(frequency=1000.0), "saved-ref.wav")["metrics"]
    monkeypatch.setattr(
        mix_review,
        "reference_by_id",
        lambda reference_id: {
            "id": reference_id,
            "name": "Saved Ref",
            "style": "master",
            "original_name": "saved-ref.wav",
            "metrics": saved_metrics,
        },
    )
    monkeypatch.setattr(mix_review, "latest_review_for_title", lambda _title: None)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0),
        filename="mix.wav",
        title="Saved Ref Mix",
        reference_id="ref1",
    )

    assert result["ok"] is True
    review = result["review"]
    assert review["reference"]["id"] == "ref1"
    assert review["reference"]["saved"] is True
    assert review["comparison_advice"]


def _fake_conn(monkeypatch, target=mix_review):
    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(target, "connect", lambda: FakeConn())


def test_save_review_remembers_explicit_reference_on_project(tmp_path, monkeypatch) -> None:
    # D1.7: the first review for a project that explicitly picks a saved
    # reference should have that reference remembered on the project, so a
    # later review on the same project can reuse it automatically.
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    saved_metrics = mix_review.analyze_wav(sine_wav(frequency=1000.0), "saved-ref.wav")["metrics"]
    monkeypatch.setattr(
        mix_review,
        "reference_by_id",
        lambda reference_id: {
            "id": reference_id,
            "name": "Saved Ref",
            "style": "master",
            "original_name": "saved-ref.wav",
            "metrics": saved_metrics,
        },
    )
    monkeypatch.setattr(mix_review, "latest_review_for_title", lambda _title: None)
    _fake_conn(monkeypatch)

    monkeypatch.setattr(
        mix_review, "get_song_project", lambda project_id: {"id": project_id, "reference_track_id": None}
    )
    remembered = {}
    monkeypatch.setattr(
        mix_review,
        "set_project_reference_track",
        lambda project_id, reference_id: remembered.update(project_id=project_id, reference_id=reference_id),
    )

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0),
        filename="mix.wav",
        title="Project Ref Mix",
        reference_id="ref1",
        project_id="proj-A",
    )

    assert result["ok"] is True
    assert remembered == {"project_id": "proj-A", "reference_id": "ref1"}


def test_save_review_does_not_overwrite_an_already_remembered_reference(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    saved_metrics = mix_review.analyze_wav(sine_wav(frequency=1000.0), "saved-ref.wav")["metrics"]
    monkeypatch.setattr(
        mix_review,
        "reference_by_id",
        lambda reference_id: {
            "id": reference_id,
            "name": "Saved Ref",
            "style": "master",
            "original_name": "saved-ref.wav",
            "metrics": saved_metrics,
        },
    )
    monkeypatch.setattr(mix_review, "latest_review_for_title", lambda _title: None)
    _fake_conn(monkeypatch)

    monkeypatch.setattr(
        mix_review,
        "get_song_project",
        lambda project_id: {"id": project_id, "reference_track_id": "already-set"},
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("set_project_reference_track should not be called when already set")

    monkeypatch.setattr(mix_review, "set_project_reference_track", _fail_if_called)

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0),
        filename="mix.wav",
        title="Project Ref Mix",
        reference_id="ref1",
        project_id="proj-A",
    )
    assert result["ok"] is True


def test_save_review_auto_applies_projects_remembered_reference(tmp_path, monkeypatch) -> None:
    # D1.7: a later review on the same project, with no reference_id/bytes
    # given at all, should automatically use the project's remembered
    # reference.
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    saved_metrics = mix_review.analyze_wav(sine_wav(frequency=1000.0), "saved-ref.wav")["metrics"]

    seen_reference_ids = []

    def _fake_reference_by_id(reference_id):
        seen_reference_ids.append(reference_id)
        return {
            "id": reference_id,
            "name": "Saved Ref",
            "style": "master",
            "original_name": "saved-ref.wav",
            "metrics": saved_metrics,
        }

    monkeypatch.setattr(mix_review, "reference_by_id", _fake_reference_by_id)
    monkeypatch.setattr(mix_review, "latest_review_for_title", lambda _title: None)
    _fake_conn(monkeypatch)

    monkeypatch.setattr(
        mix_review,
        "get_song_project",
        lambda project_id: {"id": project_id, "reference_track_id": "remembered-ref"},
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("should not re-remember an already-remembered reference")

    monkeypatch.setattr(mix_review, "set_project_reference_track", _fail_if_called)

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0),
        filename="mix.wav",
        title="Project Ref Mix",
        project_id="proj-A",
    )

    assert result["ok"] is True
    assert seen_reference_ids == ["remembered-ref"]
    assert result["review"]["reference"]["id"] == "remembered-ref"


def test_save_review_without_project_id_is_unaffected_by_d17(tmp_path, monkeypatch) -> None:
    # No project_id at all -- the D1.7 lookup must not run (and definitely
    # must not crash on an empty project_id).
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.setattr(mix_review, "latest_review_for_title", lambda _title: None)
    _fake_conn(monkeypatch)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("get_song_project should not be called without a project_id")

    monkeypatch.setattr(mix_review, "get_song_project", _fail_if_called)

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0),
        filename="mix.wav",
        title="No Project Mix",
    )
    assert result["ok"] is True


def test_save_review_compares_against_previous_version(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)

    previous = mix_review.analyze_wav(sine_wav(frequency=1000.0, amplitude=0.3), "previous.wav")
    previous["revision_agent"] = {
        "steps": [
            {
                "id": "step-1",
                "status": "done",
                "focus": "Dynamics",
                "action": "Back off limiting.",
            }
        ]
    }
    monkeypatch.setattr(
        mix_review,
        "latest_review_for_title",
        lambda _title: {
            "id": "prev1",
            "title": "Track A",
            "created_at": "2026-06-06T10:00:00",
            "version_label": "v1",
            "metrics": previous["metrics"],
            "flags": previous["flags"],
            "revision_agent": previous["revision_agent"],
        },
    )

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_review(
        file_bytes=sine_wav(frequency=120.0, amplitude=0.6),
        filename="track-a-v2.wav",
        title="Track A",
        version_label="v2",
    )

    assert result["ok"] is True
    review = result["review"]
    assert review["version_label"] == "v2"
    assert review["previous_version"]["version_label"] == "v1"
    assert "rms_delta_db" in review["version_comparison"]
    assert review["version_advice"]
    assert review["revision_impact"]["completed_step_count"] == 1
    assert review["revision_impact"]["completed_steps"][0]["focus"] == "Dynamics"
    assert review["revision_coaching"]["headline"]
    assert review["revision_coaching"]["metric_deltas"]
    assert review["revision_coaching"]["next_focus"]
    assert "level-match" in review["revision_coaching"]["listening_test"].lower()
    assert review["next_revision_plan"]["schema"] == "kenn.next_revision_plan.v1"
    assert review["next_revision_plan"]["steps"]
    assert review["revision_agent"]["steps"]
    assert "Track A" in review["revision_agent"]["goal"]


def test_review_history_returns_compact_revision_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        mix_review,
        "list_reviews",
        lambda limit=50: [
            {
                "id": "rev2",
                "title": "Track A",
                "created_at": "2026-06-08 10:00:00",
                "version_label": "v2",
                "summary": "Improved low end.",
                "metrics": {
                    "technical_score": 82,
                    "technical_rating": "Solid with checks",
                    "peak_dbfs": -2.1,
                    "rms_dbfs_estimate": -12.4,
                    "crest_factor_db": 8.2,
                    "perceptual_summary": {"dominant_band": "mids"},
                },
                "flags": [{"label": "Low dynamics"}],
                "previous_version": {"id": "rev1", "version_label": "v1", "created_at": "2026-06-07 10:00:00"},
                "version_comparison": {"rms_delta_db": -1.2, "crest_delta_db": 1.8},
                "version_advice": ["Dynamics increased compared with the previous version."],
                "reference": {"filename": "ref.wav"},
                "revision_agent": {
                    "summary": "2 step revision checklist generated from Mix Review Lab.",
                    "steps": [
                        {
                            "focus": "Low-mid cleanup",
                            "action": "Clean 150-400 Hz.",
                            "why": "Low mids are heavy.",
                        }
                    ],
                },
            },
            {
                "id": "other",
                "title": "Other Track",
                "metrics": {},
            },
        ],
    )

    rows = mix_review.review_history(title="Track A")

    assert len(rows) == 1
    assert rows[0]["id"] == "rev2"
    assert rows[0]["score"] == 82
    assert rows[0]["dominant_band"] == "mids"
    assert rows[0]["version_delta"]["crest_delta_db"] == 1.8
    assert rows[0]["has_reference"] is True
    assert rows[0]["revision_agent"]["steps"][0]["action"] == "Clean 150-400 Hz."


def test_track_timeline_groups_versions_and_summarises(monkeypatch) -> None:
    monkeypatch.setattr(
        mix_review,
        "list_reviews",
        lambda limit=200: [
            {
                "id": "rev2",
                "title": "Track A",
                "created_at": "2026-06-08 10:00:00",
                "version_label": "v2",
                "summary": "Second version.",
                "metrics": {
                    "technical_score": 82,
                    "technical_rating": "Solid with checks",
                    "rms_dbfs_estimate": -12.0,
                    "crest_factor_db": 8.0,
                    "stereo_width_ratio": 0.2,
                    "perceptual_summary": {"dominant_band": "mids"},
                },
                "flags": [{"label": "Low dynamics"}],
                "version_comparison": {"rms_delta_db": -1.0, "crest_delta_db": 2.0},
                "version_advice": ["Dynamics improved."],
                "reference": {"id": "ref1", "name": "Pop Ref", "saved": True},
                "revision_agent": {
                    "summary": "1 step revision checklist generated from Mix Review Lab.",
                    "steps": [{"focus": "Export", "action": "Export v3.", "why": "Compare again."}],
                },
            },
            {
                "id": "other",
                "title": "Other Track",
                "created_at": "2026-06-07 09:00:00",
                "metrics": {},
            },
            {
                "id": "rev1",
                "title": "Track A",
                "created_at": "2026-06-07 10:00:00",
                "version_label": "v1",
                "metrics": {
                    "technical_score": 75,
                    "rms_dbfs_estimate": -14.0,
                    "crest_factor_db": 6.0,
                    "stereo_width_ratio": 0.1,
                    "perceptual_summary": {"dominant_band": "low_mids"},
                },
                "flags": [],
            },
        ],
    )

    timeline = mix_review.track_timeline("Track A")

    assert timeline["ok"] is True
    assert timeline["version_count"] == 2
    assert [item["version_label"] for item in timeline["versions"]] == ["v1", "v2"]
    assert timeline["summary"]["score_change"] == 7
    assert timeline["summary"]["rms_change_db"] == 2
    assert timeline["versions"][-1]["reference"]["name"] == "Pop Ref"
    assert timeline["versions"][-1]["revision_agent"]["steps"][0]["action"] == "Export v3."


def test_report_exports_return_html_and_json(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)

    report = mix_review.analyze_wav(sine_wav(), "export.wav")
    report.update(
        {
            "id": "rev-export",
            "title": "Export Mix",
            "version_label": "v3",
            "created_at": "2026-06-08 12:00:00",
            "mix_critique": {"text": "Main read:\nExportable report."},
            "reference_coaching": {
                "headline": "Reference coaching for Premaster.",
                "level_message": "Level-match first.",
                "tonal_message": "Raw spectrum differs.",
                "perceived_message": "Ear-weighted read differs.",
                "dynamics_message": "Dynamics differ.",
                "stereo_message": "Stereo differs.",
                "next_move": "Level-match the files before making tonal decisions.",
                "safe_use": "Use the reference as a direction check.",
            },
            "revision_coaching": {
                "headline": "This revision moved in the right direction.",
                "verdict": "improved",
                "score_delta": 7,
                "metric_deltas": [{"label": "Punch / crest", "value": 2, "unit": "dB"}],
                "next_focus": "Keep checking translation.",
                "listening_test": "Level-match v1 and v2.",
            },
            "revision_agent": {
                "goal": "Create the next focused revision for Export Mix.",
                "steps": [{"focus": "Export", "action": "Export the next version.", "why": "Compare again."}],
            },
        }
    )
    (reports / "rev-export.json").write_text(__import__("json").dumps(report), encoding="utf-8")

    class FakeResult:
        def fetchone(self):
            return {
                "id": "rev-export",
                "title": "Export Mix",
                "report_name": "rev-export.json",
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    html_report = mix_review.report_html("rev-export")
    json_report = mix_review.report_json_bytes("rev-export")

    assert html_report is not None
    assert "Export Mix" in html_report
    assert "Priority Actions" in html_report
    assert "Deeper Diagnostics" in html_report
    assert "Goal Target Checks" in html_report
    assert "Where To Look First" in html_report
    assert "Frequency Repair Map" in html_report
    assert "Before/After Coaching" in html_report
    assert "Revision Lesson" in html_report
    assert "Educational Notes" in html_report
    assert "Reference Coaching" in html_report
    assert "Revision Agent Checklist" in html_report
    assert json_report is not None
    assert b'"title": "Export Mix"' in json_report


def test_update_revision_agent_step_persists_status(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    report = mix_review.analyze_wav(sine_wav(), "step.wav")
    report.update(
        {
            "id": "rev-step",
            "title": "Step Mix",
            "revision_agent": {
                "steps": [
                    {"id": "step-1", "status": "todo", "focus": "First", "action": "Do first."},
                    {"id": "step-2", "status": "todo", "focus": "Second", "action": "Do second."},
                ]
            },
        }
    )
    (reports / "rev-step.json").write_text(__import__("json").dumps(report), encoding="utf-8")

    class FakeResult:
        def fetchone(self):
            return {
                "id": "rev-step",
                "title": "Step Mix",
                "report_name": "rev-step.json",
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.update_revision_agent_step("rev-step", "step-1", "done")

    assert result["ok"] is True
    assert result["revision_agent"]["done_count"] == 1
    assert result["revision_agent"]["total_steps"] == 2
    saved = __import__("json").loads((reports / "rev-step.json").read_text(encoding="utf-8"))
    assert saved["revision_agent"]["steps"][0]["status"] == "done"


def test_save_review_rejects_non_wav() -> None:
    result = mix_review.save_review(file_bytes=b"not audio", filename="mix.mp3")

    assert result["ok"] is False
    assert "does not match its extension" in result["error"]


def test_save_review_writes_report(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_review(file_bytes=sine_wav(), filename="mix.wav", title="Test Mix", mix_goal="club")

    assert result["ok"] is True
    assert result["review"]["title"] == "Test Mix"
    assert result["review"]["metrics"]["mix_goal"]["key"] == "club"
    assert result["review"]["revision_lesson"]["goal"]["label"] == "Club / electronic"
    assert any(reports.glob("*.json"))


def test_save_review_adds_offline_safe_mix_critique(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.delenv("AUDIO_TOO_MIX_REVIEW_LLM", raising=False)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(mix_review, "connect", lambda: FakeConn())

    result = mix_review.save_review(file_bytes=sine_wav(), filename="mix.wav", title="Critique Test")

    assert result["ok"] is True
    critique = result["review"]["mix_critique"]
    assert critique["mode"] == "deterministic"
    assert critique["available"] is False
    assert "AUDIO_TOO_MIX_REVIEW_LLM" in critique["message"]
    assert "Main read:" in critique["text"]
    assert "Fix first:" in critique["text"]
    assert "Revision agent next step:" in critique["text"]
    assert "Listening checks:" in critique["text"]


def test_generate_mix_critique_uses_llm_when_enabled(monkeypatch) -> None:
    report = mix_review.analyze_wav(sine_wav(), "mix.wav")

    class FakeLlmRewrite:
        @staticmethod
        def public_status():
            return {"message": "fake LLM ready"}

        @staticmethod
        def is_enabled():
            return True

        @staticmethod
        def chat_completion(_messages):
            return (
                "Main read:\n"
                "The technical report is usable and needs one focused revision.\n\n"
                "Fix first:\n"
                "Handle the top action plan item before changing tone elsewhere.\n\n"
                "What to leave alone:\n"
                "Do not change parts that are not flagged by the report.\n\n"
                "Listening checks:\n"
                "1. Level-match the revision.\n"
                "2. Check mono and low-end translation."
            )

    monkeypatch.setenv("AUDIO_TOO_MIX_REVIEW_LLM", "1")
    mix_review.set_mix_critique_provider(FakeLlmRewrite)
    try:
        critique = mix_review.generate_mix_critique(report)
    finally:
        mix_review.set_mix_critique_provider(None)

    assert critique["mode"] == "llm"
    assert critique["available"] is True
    assert critique["message"] == "fake LLM ready"
    assert "What to leave alone:" in critique["text"]


class _FakeConn:
    """No-op sqlite connection stand-in shared by the Stage 10 wiring tests
    below (same shape as the FakeConn used by test_save_review_writes_report
    and test_save_review_adds_offline_safe_mix_critique above)."""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None


def test_save_review_includes_stage10_style_and_critique(tmp_path, monkeypatch) -> None:
    """Stage 10 wiring: every real save_review() call — not just the
    standalone module tests — now returns mix_style (deterministic
    era/loudness-war/vintage-modern classification) and mix_review_critique
    (the Stage 10 AI-augmented critique, distinct from the legacy
    mix_critique field), without disturbing any existing report field."""
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.delenv("MIX_REVIEW_CRITIQUE_ENABLED", raising=False)
    monkeypatch.setattr(mix_review, "connect", lambda: _FakeConn())

    result = mix_review.save_review(file_bytes=sine_wav(), filename="mix.wav", title="Stage10 Style Test")

    assert result["ok"] is True
    review = result["review"]

    # Legacy critique field is untouched.
    assert review["mix_critique"]["mode"] == "deterministic"

    # New Stage 10 fields are present and well-formed.
    style = review["mix_style"]
    assert style["era"]["label"]
    assert style["loudness_war"]["severity"] in {"none", "borderline", "moderate", "severe", "unknown"}
    assert style["vintage_or_modern"]["label"] in {"vintage-leaning", "modern", "unknown"}
    assert isinstance(style["summary"], str) and style["summary"]

    critique = review["mix_review_critique"]
    assert critique["mode"] == "deterministic"  # env var unset -> deterministic fallback
    assert critique["available"] is False
    assert isinstance(critique["text"], str) and len(critique["text"]) >= 20
    assert "Overall:" in critique["text"]

    # Stage 10.1 metrics (stereo_asymmetry / loudness_range_by_section) were
    # already wired into analyze_wav before this change; confirm they still
    # flow through end-to-end.
    assert "stereo_asymmetry" in review["metrics"]
    assert "loudness_range_by_section" in review["metrics"]

    # No stems/pre-master supplied -> the opt-in Stage 10 fields must be
    # absent, not present-but-empty, so existing consumers see identical
    # report shapes to before this change.
    assert "stem_masking" not in review
    assert "stem_solo" not in review
    assert "transient_preservation" not in review


def test_save_review_with_stems_includes_stem_masking_and_solo(tmp_path, monkeypatch) -> None:
    """Stage 10 wiring: supplying stems to save_review() attaches real
    stem_frequency_masking + stem_solo spectral-comparison results to the
    report."""
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.setattr(mix_review, "connect", lambda: _FakeConn())

    stems = [
        {"name": "bass", "file_bytes": sine_wav(frequency=80.0, seconds=0.5, sample_rate=8000)},
        {"name": "lead", "file_bytes": sine_wav(frequency=2000.0, seconds=0.5, sample_rate=8000)},
    ]

    result = mix_review.save_review(
        file_bytes=sine_wav(seconds=0.5),
        filename="mix.wav",
        title="Stage10 Stem Test",
        stems=stems,
    )

    assert result["ok"] is True
    review = result["review"]

    masking = review["stem_masking"]
    assert masking["ok"] is True
    assert {s["name"] for s in masking["stems"]} == {"bass", "lead"}

    solo = review["stem_solo"]
    assert {s["name"] for s in solo["stems"]} == {"bass", "lead"}
    assert "dominant_band" in solo
    assert "low_end_summary" in solo

    # The Stage 10 critique should now be able to fold stem-masking findings
    # into its deterministic text (only when there's something notable to
    # report -- absence of a mention isn't itself a failure, but the field
    # must exist and stay well-formed alongside the new stem data).
    assert isinstance(review["mix_review_critique"]["text"], str)


def test_save_review_without_stems_omits_stem_fields(tmp_path, monkeypatch) -> None:
    """A single stem (or none) is not enough to compute masking/overlap;
    confirm the opt-in fields are cleanly omitted rather than present with
    garbage data."""
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.setattr(mix_review, "connect", lambda: _FakeConn())

    result = mix_review.save_review(
        file_bytes=sine_wav(seconds=0.5),
        filename="mix.wav",
        title="Stage10 Single Stem Test",
        stems=[{"name": "only_one", "file_bytes": sine_wav(seconds=0.5)}],
    )

    assert result["ok"] is True
    assert "stem_masking" not in result["review"]
    assert "stem_solo" not in result["review"]


def test_save_review_with_pre_master_includes_transient_preservation(tmp_path, monkeypatch) -> None:
    """Stage 10 wiring: supplying a pre-master render alongside the main
    upload attaches a real transient_preservation comparison to the report."""
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    monkeypatch.setattr(mix_review, "connect", lambda: _FakeConn())

    # Long enough (>= 2048 samples at the analysis rate) for onset detection
    # to run rather than short-circuiting on the "insufficient data" path.
    post = sine_wav(frequency=200.0, seconds=1.0, sample_rate=8000, amplitude=0.3)
    pre = sine_wav(frequency=200.0, seconds=1.0, sample_rate=8000, amplitude=0.6)

    result = mix_review.save_review(
        file_bytes=post,
        filename="master.wav",
        title="Stage10 Transient Test",
        pre_master_bytes=pre,
    )

    assert result["ok"] is True
    tp = result["review"]["transient_preservation"]
    assert "preservation_score" in tp
    assert "profile" in tp
    assert "matched_event_count" in tp


def test_save_review_background_processing(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    uploads = tmp_path / "uploads"
    reports.mkdir()
    uploads.mkdir()
    
    monkeypatch.setattr(mix_review, "REPORT_ROOT", reports)
    monkeypatch.setattr(mix_review, "UPLOAD_ROOT", uploads)
    
    import artifact_store
    import db
    import event_store
    db_path = tmp_path / "test_reviews.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    
    mix_review.init_reviews_table()
    
    res = mix_review.save_review(
        file_bytes=sine_wav(),
        filename="async_mix.wav",
        title="Async Track",
        project_id="project-async",
        background=True
    )
    
    assert res["ok"] is True
    assert res["status"] == "pending"
    assert res["review"]["status"] == "pending"
    
    review_id = res["id"]
    
    import time
    start_time = time.time()
    status_data = None
    # 3.0s was too tight once the from-scratch migration replay (this test
    # forces db._migration_done = False) grew to 17 migrations and stacked
    # on top of numba's cold-start JIT compile in the background thread --
    # both add fixed overhead per test run, not something a longer poll can
    # avoid (2026-08-05).
    while time.time() - start_time < 10.0:
        status_data = mix_review.mix_review_status(review_id)
        assert status_data["ok"] is True
        if status_data["status"] == "completed":
            break
        time.sleep(0.05)

    assert status_data["status"] == "completed"
    assert status_data["error"] is None
    
    report_file = reports / f"{review_id}.json"
    assert report_file.exists()
    assert status_data["artifacts"]["source"]["kind"] == "audio.source.mix_review"
    assert status_data["artifacts"]["source"]["project_id"] == "project-async"
    assert status_data["artifacts"]["report"]["kind"] == "audio.analysis.mix_review"
    assert (
        status_data["artifacts"]["report"]["parent_ids"]
        == [status_data["artifacts"]["source"]["artifact_id"]]
    )
    assert artifact_store.verify(
        status_data["artifacts"]["source"]["artifact_id"]
    )["ok"] is True
    assert [
        event["event_type"]
        for event in event_store.list_for_correlation(f"mix-review:{review_id}")
    ] == ["mix_review.created", "mix_review.completed"]
    artifact_store.reset_connection_state()
