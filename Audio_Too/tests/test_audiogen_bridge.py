"""Tests for the bounded LLM_AudioGen bridge."""

from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import audiogen_bridge  # noqa: E402
import audiogen_job_store  # noqa: E402
import artifact_store  # noqa: E402
import automix_jobs  # noqa: E402
import db  # noqa: E402
import portfolio_ops  # noqa: E402
import stem_uploads  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def isolated_render_database(tmp_path_factory):
    root = tmp_path_factory.mktemp("audiogen-render-db")
    patch = pytest.MonkeyPatch()
    patch.setattr(db, "DB_PATH", root / "audio_too.db")
    patch.setattr(db, "AGENT_DATA", root / "legacy-json")
    patch.setattr(db, "_migration_done", False)
    patch.setattr(artifact_store, "ARTIFACT_ROOT", root / "artifacts")
    audiogen_job_store.reset_connection_state()
    artifact_store.reset_connection_state()
    audiogen_job_store.ensure_schema()
    yield
    audiogen_bridge.stop_render_worker()
    patch.undo()
    audiogen_job_store.reset_connection_state()
    artifact_store.reset_connection_state()


@pytest.fixture(autouse=True)
def reset_render_queue():
    audiogen_job_store.clear_all()
    audiogen_bridge._QUEUE_LOADED = False  # noqa: SLF001
    yield
    audiogen_job_store.clear_all()
    audiogen_bridge._QUEUE_LOADED = False  # noqa: SLF001


def clear_render_queue() -> None:
    with audiogen_bridge._QUEUE_CONDITION:  # noqa: SLF001
        audiogen_job_store.clear_all()
        audiogen_bridge._QUEUE_LOADED = True  # noqa: SLF001
        audiogen_bridge._QUEUE_CONDITION.notify_all()  # noqa: SLF001


def test_prompt_requests_generation_detects_music_generation() -> None:
    assert audiogen_bridge.prompt_requests_generation("generate a sad chorus") is True
    assert audiogen_bridge.prompt_requests_generation("generate some music") is True
    assert audiogen_bridge.generation_request_kind("generate some music") == "clarify"
    assert audiogen_bridge.prompt_requests_generation("how do I fix muddy vocals") is False


def test_requests_automix_chain_detects_chaining_phrasing() -> None:
    # D3.2 (docs/KENN_FUTURE_PLAN.md Phase 3)
    assert audiogen_bridge.requests_automix_chain(
        "generate drums and bassline, then render an AutoMix pass from these"
    ) is True
    assert audiogen_bridge.requests_automix_chain("generate a song and automix it") is True
    assert audiogen_bridge.requests_automix_chain("generate a song, then run automix") is True
    assert audiogen_bridge.requests_automix_chain("give it a mix pass after") is True


def test_requests_automix_chain_false_for_a_plain_generation_request() -> None:
    assert audiogen_bridge.requests_automix_chain("generate a joyful 4 bar loop") is False
    assert audiogen_bridge.requests_automix_chain("generate a full song") is False
    assert audiogen_bridge.requests_automix_chain("") is False


def test_requests_variation_detects_variation_phrasing() -> None:
    # D3.5 (docs/KENN_FUTURE_PLAN.md Phase 3), buildable half
    assert audiogen_bridge.requests_variation("my loop is too repetitive, give me a variation") is True
    assert audiogen_bridge.requests_variation("try a different version") is True
    assert audiogen_bridge.requests_variation("switch it up") is True
    assert audiogen_bridge.requests_variation("generate another take") is True


def test_requests_variation_false_for_unrelated_text() -> None:
    assert audiogen_bridge.requests_variation("generate a joyful loop") is False
    assert audiogen_bridge.requests_variation("how do I saturate sub bass?") is False
    assert audiogen_bridge.requests_variation("") is False


def test_prompt_requests_generation_recognizes_a_variation_request_with_a_music_object() -> None:
    # Broadened 2026-08-07 (D3.5): a variation request implies wanting a
    # new generation even without an explicit generate/make verb.
    assert audiogen_bridge.prompt_requests_generation("my loop is too repetitive, give me a variation") is True


def test_prompt_requests_generation_ignores_bare_variation_phrasing_without_a_music_object() -> None:
    # "give me a different version" alone, with no music-object word,
    # stays conservative -- no session/history context available here
    # to resolve what "it" refers to.
    assert audiogen_bridge.prompt_requests_generation("give me a different version") is False


def test_generate_for_kenn_publishes_wav_to_portfolio(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    data_path = tmp_path / "portfolio" / "portfolio_data.json"
    history_path = tmp_path / "data" / "audiogen_render_history.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "HISTORY_PATH", history_path)
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(portfolio_ops, "DATA_PATH", data_path)
    monkeypatch.setattr(portfolio_ops, "PORTFOLIO_ROOT", tmp_path / "portfolio")

    def fake_phrase_command(**kwargs):
        wav_out = Path(kwargs["wav_out"])
        wav_out.parent.mkdir(parents=True, exist_ok=True)
        wav_out.write_bytes(b"RIFF")
        return {"ok": True, "result": {"ok": True, "wav_written": True, "wav_path": str(wav_out)}}

    monkeypatch.setattr(audiogen_bridge, "phrase_command", fake_phrase_command)

    result = audiogen_bridge.generate_for_kenn("generate a sad chorus", emotion="sadness", bars=4, project_id="proj-loop")

    assert result["ok"] is True
    assert result["emotion"] == "sadness"
    assert Path(result["wav_path"]).exists()
    assert result["src"].startswith("/portfolio/audio/")
    assert result["portfolio_entry"]["src"].startswith("/portfolio/audio/")
    assert result["artifact"]["kind"] == "audio.generated.loop"
    assert result["artifact"]["project_id"] == "proj-loop"
    assert artifact_store.verify(result["artifact"]["artifact_id"])["ok"] is True
    history = audiogen_bridge.list_render_history()
    assert history[0]["kind"] == "loop"
    assert history[0]["emotion"] == "sadness"
    assert history[0]["project_id"] == "proj-loop"
    assert result["project_id"] == "proj-loop"


def test_generate_for_kenn_falls_back_from_unsupported_emotion(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    history_path = tmp_path / "data" / "audiogen_render_history.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "HISTORY_PATH", history_path)

    seen = {}

    def fake_phrase_command(**kwargs):
        seen["emotion"] = kwargs["emotion"]
        wav_out = Path(kwargs["wav_out"])
        wav_out.parent.mkdir(parents=True, exist_ok=True)
        wav_out.write_bytes(b"RIFF")
        return {"ok": True, "result": {"ok": True, "wav_written": True, "wav_path": str(wav_out)}}

    monkeypatch.setattr(audiogen_bridge, "phrase_command", fake_phrase_command)

    result = audiogen_bridge.generate_for_kenn(
        "generate an uplifting chorus",
        emotion="calm",
        bars=1,
        publish=False,
    )

    assert result["ok"] is True
    assert result["emotion"] == "joy"
    assert seen["emotion"] == "joy"


def test_render_full_song_for_web_copies_latest_wav_to_portfolio(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    export_dir = tmp_path / "exports" / "web"
    data_path = tmp_path / "portfolio" / "portfolio_data.json"
    history_path = tmp_path / "data" / "audiogen_render_history.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "AUDIOGEN_ROOT", tmp_path)
    monkeypatch.setattr(audiogen_bridge, "HISTORY_PATH", history_path)
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(portfolio_ops, "DATA_PATH", data_path)
    monkeypatch.setattr(portfolio_ops, "PORTFOLIO_ROOT", tmp_path / "portfolio")

    def fake_render_command(**kwargs):
        args = kwargs["args"]
        prefix = args[args.index("--prefix") + 1]
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / f"{prefix}_20260611_120000.wav").write_bytes(b"RIFF")
        return {"ok": True, "stdout": "done", "stderr": ""}

    monkeypatch.setattr(audiogen_bridge, "render_command", fake_render_command)

    result = audiogen_bridge.render_full_song_for_web(emotion="relief", bars=4, k=1)

    assert result["ok"] is True
    assert result["emotion"] == "relief"
    assert Path(result["wav_path"]).exists()
    assert result["src"].startswith("/portfolio/audio/")
    assert result["portfolio_entry"]["src"] == result["src"]
    assert result["artifact"]["kind"] == "audio.generated.full_song"
    assert artifact_store.verify(result["artifact"]["artifact_id"])["ok"] is True


def test_render_full_song_for_web_streams_progress(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    export_dir = tmp_path / "exports" / "web"
    data_path = tmp_path / "portfolio" / "portfolio_data.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "AUDIOGEN_ROOT", tmp_path)
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(portfolio_ops, "DATA_PATH", data_path)
    monkeypatch.setattr(portfolio_ops, "PORTFOLIO_ROOT", tmp_path / "portfolio")
    progress = []

    def fake_render_command_stream(**kwargs):
        callback = kwargs["progress_callback"]
        callback(42, "Halfway there.")
        args = kwargs["args"]
        prefix = args[args.index("--prefix") + 1]
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / f"{prefix}_20260611_120000.wav").write_bytes(b"RIFF")
        return {"ok": True, "stdout": "done", "stderr": "", "duration_seconds": 1.2}

    monkeypatch.setattr(audiogen_bridge, "render_command_stream", fake_render_command_stream)

    result = audiogen_bridge.render_full_song_for_web(
        emotion="joy",
        bars=4,
        k=1,
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )

    assert result["ok"] is True
    assert progress[0] == (42, "Halfway there.")
    assert any(item[0] == 88 for item in progress)
    assert any(item[0] == 94 for item in progress)


def test_enqueue_full_song_render_completes_in_background(tmp_path, monkeypatch) -> None:
    clear_render_queue()
    history_path = tmp_path / "audiogen_render_history.json"
    queue_path = tmp_path / "audiogen_render_queue.json"
    monkeypatch.setattr(audiogen_bridge, "HISTORY_PATH", history_path)
    monkeypatch.setattr(audiogen_bridge, "QUEUE_PATH", queue_path)

    def fake_render_full_song_for_web(**kwargs):
        return {
            "ok": True,
            "emotion": kwargs["emotion"],
            "bars": kwargs["bars"],
            "src": "/portfolio/audio/test.wav",
        }

    monkeypatch.setattr(audiogen_bridge, "render_full_song_for_web", fake_render_full_song_for_web)

    queued = audiogen_bridge.enqueue_full_song_render(emotion="joy", bars=2, k=1, publish=False, project_id="proj1")
    job_id = queued["job"]["id"]

    deadline = time.time() + 2
    status = {}
    while time.time() < deadline:
        status = audiogen_bridge.render_job(job_id)
        if status["job"]["status"] == "completed":
            break
        time.sleep(0.02)

    assert status["job"]["status"] == "completed"
    assert status["job"]["project_id"] == "proj1"
    assert status["job"]["result"]["src"] == "/portfolio/audio/test.wav"
    assert audiogen_bridge.render_queue_snapshot()["recent"][0]["id"] == job_id
    history = audiogen_bridge.list_render_history()
    assert history[0]["kind"] == "full_song"
    assert history[0]["project_id"] == "proj1"


def test_queue_automix_from_stem_files_zips_stems_and_chains(tmp_path, monkeypatch) -> None:
    bass_wav = tmp_path / "bass.wav"
    melody_wav = tmp_path / "melody.wav"
    bass_wav.write_bytes(b"RIFF-bass")
    melody_wav.write_bytes(b"RIFF-melody")

    captured = {}

    def fake_store_upload(request, *, idempotency_key=""):
        captured["file_bytes"] = request.file_bytes
        captured["project_id"] = request.project_id
        return 200, {"ok": True, "upload_id": "up-1"}

    def fake_queue_job(request, *, idempotency_key=""):
        captured["genre"] = request.genre
        captured["style_prefs"] = request.style_prefs
        return 200, {"ok": True, "job_id": "job-1"}

    monkeypatch.setattr(stem_uploads, "store_upload", fake_store_upload)
    monkeypatch.setattr(automix_jobs, "queue_job", fake_queue_job)

    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1",
        genre="pop",
        style_prefs={"masking_corrections": True},
        stem_paths={"bass": str(bass_wav), "melody": str(melody_wav)},
    )

    assert result == {"ok": True, "upload_id": "up-1", "job_id": "job-1"}
    assert captured["project_id"] == "proj-1"
    assert captured["genre"] == "pop"
    assert captured["style_prefs"] == {"masking_corrections": True}
    with zipfile.ZipFile(io.BytesIO(captured["file_bytes"])) as zf:
        assert set(zf.namelist()) == {"bass.wav", "melody.wav"}
        assert zf.read("bass.wav") == b"RIFF-bass"


def test_queue_automix_from_stem_files_stores_stems_uncompressed(tmp_path, monkeypatch) -> None:
    # Real bug found live 2026-08-07 running this chain end-to-end: a
    # generated "drone" stem (long near-silent/sustained passage) zipped
    # with ZIP_DEFLATED compressed at ~1025:1 -- past
    # archive_safety.py's MAX_ZIP_COMPRESSION_RATIO (1000:1), a real
    # zip-bomb guard on the read side -- so the resulting AutoMix job
    # failed with "ZIP member compression ratio is too high: 'drone.wav'"
    # even though the content was completely legitimate. ZIP_STORED
    # (no compression) keeps the ratio at ~1:1 regardless of content.
    silent_wav = tmp_path / "drone.wav"
    silent_wav.write_bytes(b"\x00" * 200_000)  # highly compressible under DEFLATE

    captured = {}
    monkeypatch.setattr(
        stem_uploads, "store_upload",
        lambda request, **kw: captured.update(file_bytes=request.file_bytes) or (200, {"ok": True, "upload_id": "up-1"}),
    )
    monkeypatch.setattr(automix_jobs, "queue_job", lambda request, **kw: (200, {"ok": True, "job_id": "job-1"}))

    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1", genre="pop", style_prefs={}, stem_paths={"drone": str(silent_wav)},
    )

    assert result["ok"] is True
    with zipfile.ZipFile(io.BytesIO(captured["file_bytes"])) as zf:
        info = zf.getinfo("drone.wav")
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.file_size == info.compress_size


def test_queue_automix_from_stem_files_requires_project_id() -> None:
    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="", genre="pop", style_prefs={}, stem_paths={"bass": "/tmp/bass.wav"}
    )
    assert result["ok"] is False
    assert "project_id" in result["error"]


def test_queue_automix_from_stem_files_requires_at_least_one_stem() -> None:
    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1", genre="pop", style_prefs={}, stem_paths={}
    )
    assert result["ok"] is False
    assert "stems" in result["error"].lower()


def test_queue_automix_from_stem_files_skips_missing_files_on_disk(tmp_path) -> None:
    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1",
        genre="pop",
        style_prefs={},
        stem_paths={"bass": str(tmp_path / "does-not-exist.wav")},
    )
    assert result["ok"] is False
    assert "no stem files" in result["error"].lower()


def test_queue_automix_from_stem_files_surfaces_upload_failure(tmp_path, monkeypatch) -> None:
    bass_wav = tmp_path / "bass.wav"
    bass_wav.write_bytes(b"RIFF")

    def fake_store_upload(request, *, idempotency_key=""):
        raise stem_uploads.UploadValidationError("Unsupported upload type.")

    monkeypatch.setattr(stem_uploads, "store_upload", fake_store_upload)

    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1", genre="pop", style_prefs={}, stem_paths={"bass": str(bass_wav)}
    )

    assert result["ok"] is False
    assert "Unsupported upload type" in result["error"]


def test_queue_automix_from_stem_files_surfaces_source_not_ready(tmp_path, monkeypatch) -> None:
    bass_wav = tmp_path / "bass.wav"
    bass_wav.write_bytes(b"RIFF")

    monkeypatch.setattr(
        stem_uploads, "store_upload", lambda request, **kw: (200, {"ok": True, "upload_id": "up-1"})
    )

    def fake_queue_job(request, *, idempotency_key=""):
        raise stem_uploads.SourceNotReady("No renderable source uploaded yet.")

    monkeypatch.setattr(automix_jobs, "queue_job", fake_queue_job)

    result = audiogen_bridge.queue_automix_from_stem_files(
        project_id="proj-1", genre="pop", style_prefs={}, stem_paths={"bass": str(bass_wav)}
    )

    assert result["ok"] is False
    assert "No renderable source" in result["error"]


def test_render_full_song_for_web_chains_stems_to_automix(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    export_dir = tmp_path / "exports" / "web"
    data_path = tmp_path / "portfolio" / "portfolio_data.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "AUDIOGEN_ROOT", tmp_path)
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(portfolio_ops, "DATA_PATH", data_path)
    monkeypatch.setattr(portfolio_ops, "PORTFOLIO_ROOT", tmp_path / "portfolio")

    def fake_render_command(**kwargs):
        args = kwargs["args"]
        assert "--export-stems" in args
        prefix = args[args.index("--prefix") + 1]
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / f"{prefix}_20260611_120000.wav").write_bytes(b"RIFF")
        (export_dir / f"{prefix}_20260611_120000_stem_bass.wav").write_bytes(b"RIFF-bass")
        (export_dir / f"{prefix}_20260611_120000_stem_melody.wav").write_bytes(b"RIFF-melody")
        return {"ok": True, "stdout": "done", "stderr": ""}

    monkeypatch.setattr(audiogen_bridge, "render_command", fake_render_command)

    seen_stem_paths = {}

    def fake_queue_automix(*, project_id, genre, style_prefs, stem_paths):
        seen_stem_paths.update(stem_paths)
        return {"ok": True, "upload_id": "up-1", "job_id": "automix-job-1"}

    monkeypatch.setattr(audiogen_bridge, "queue_automix_from_stem_files", fake_queue_automix)

    result = audiogen_bridge.render_full_song_for_web(
        emotion="joy",
        bars=4,
        k=1,
        project_id="proj-1",
        chain_to_automix=True,
        genre="pop",
        style_prefs={"masking_corrections": True},
    )

    assert result["ok"] is True
    assert result["automix"] == {"ok": True, "upload_id": "up-1", "job_id": "automix-job-1"}
    assert set(seen_stem_paths) == {"bass", "melody"}


def test_render_full_song_for_web_without_chaining_has_no_automix_key(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "portfolio" / "audio"
    export_dir = tmp_path / "exports" / "web"
    data_path = tmp_path / "portfolio" / "portfolio_data.json"
    monkeypatch.setattr(audiogen_bridge, "PORTFOLIO_AUDIO", audio_dir)
    monkeypatch.setattr(audiogen_bridge, "AUDIOGEN_ROOT", tmp_path)
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(portfolio_ops, "DATA_PATH", data_path)
    monkeypatch.setattr(portfolio_ops, "PORTFOLIO_ROOT", tmp_path / "portfolio")

    def fake_render_command(**kwargs):
        args = kwargs["args"]
        assert "--export-stems" not in args
        prefix = args[args.index("--prefix") + 1]
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / f"{prefix}_20260611_120000.wav").write_bytes(b"RIFF")
        return {"ok": True, "stdout": "done", "stderr": ""}

    monkeypatch.setattr(audiogen_bridge, "render_command", fake_render_command)

    result = audiogen_bridge.render_full_song_for_web(emotion="joy", bars=4, k=1)

    assert result["ok"] is True
    assert "automix" not in result


def test_enqueue_full_song_render_links_chained_automix_job_id(tmp_path, monkeypatch) -> None:
    clear_render_queue()
    history_path = tmp_path / "audiogen_render_history.json"
    queue_path = tmp_path / "audiogen_render_queue.json"
    monkeypatch.setattr(audiogen_bridge, "HISTORY_PATH", history_path)
    monkeypatch.setattr(audiogen_bridge, "QUEUE_PATH", queue_path)

    seen_kwargs = {}

    def fake_render_full_song_for_web(**kwargs):
        seen_kwargs.update(kwargs)
        return {
            "ok": True,
            "emotion": kwargs["emotion"],
            "bars": kwargs["bars"],
            "src": "/portfolio/audio/test.wav",
            "automix": {"ok": True, "upload_id": "up-1", "job_id": "automix-job-99"},
        }

    monkeypatch.setattr(audiogen_bridge, "render_full_song_for_web", fake_render_full_song_for_web)

    queued = audiogen_bridge.enqueue_full_song_render(
        emotion="joy",
        bars=2,
        k=1,
        publish=False,
        project_id="proj1",
        chain_to_automix=True,
        genre="pop",
        style_prefs={"masking_corrections": True},
    )
    job_id = queued["job"]["id"]
    assert queued["job"]["chain_to_automix"] is True
    assert queued["job"]["genre"] == "pop"

    deadline = time.time() + 2
    status = {}
    while time.time() < deadline:
        status = audiogen_bridge.render_job(job_id)
        if status["job"]["status"] == "completed":
            break
        time.sleep(0.02)

    assert status["job"]["status"] == "completed"
    assert status["job"]["automix_job_id"] == "automix-job-99"
    assert seen_kwargs["chain_to_automix"] is True
    assert seen_kwargs["genre"] == "pop"
    assert seen_kwargs["style_prefs"] == {"masking_corrections": True}


def test_cancel_queued_render_job(tmp_path, monkeypatch) -> None:
    clear_render_queue()
    monkeypatch.setattr(audiogen_bridge, "QUEUE_PATH", tmp_path / "audiogen_render_queue.json")
    with audiogen_bridge._QUEUE_CONDITION:  # noqa: SLF001
        job = audiogen_job_store.create(
            emotion="sadness", bars=2, candidate_count=1, publish=False, project_id=""
        )
        result = audiogen_bridge.cancel_render_job(job["id"])

    assert result["ok"] is True
    assert result["job"]["status"] == "cancelled"


def test_render_queue_persists_queued_jobs(tmp_path, monkeypatch) -> None:
    clear_render_queue()
    queue_path = tmp_path / "audiogen_render_queue.json"
    monkeypatch.setattr(audiogen_bridge, "QUEUE_PATH", queue_path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        """
{
  "updated_at": "2026-06-11 12:00:00",
  "order": ["queued-persist-test"],
  "jobs": {
    "queued-persist-test": {
      "id": "queued-persist-test",
      "type": "full_song",
      "status": "queued",
      "emotion": "relief",
      "bars": 2,
      "k": 1,
      "publish": false,
      "project_id": "",
      "progress": 0,
      "message": "Queued.",
      "created_at": "2026-06-11 12:00:00",
      "started_at": "",
      "finished_at": "",
      "cancel_requested": false,
      "result": null,
      "error": ""
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with audiogen_bridge._QUEUE_CONDITION:  # noqa: SLF001
        audiogen_bridge._QUEUE_LOADED = False  # noqa: SLF001

    reloaded = audiogen_bridge.render_job("queued-persist-test")

    assert reloaded["ok"] is True
    assert reloaded["job"]["status"] == "queued"
    assert reloaded["job"]["emotion"] == "relief"


def test_render_queue_marks_running_jobs_interrupted_after_restart(tmp_path, monkeypatch) -> None:
    clear_render_queue()
    queue_path = tmp_path / "audiogen_render_queue.json"
    monkeypatch.setattr(audiogen_bridge, "QUEUE_PATH", queue_path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        """
{
  "updated_at": "2026-06-11 12:00:00",
  "order": ["running-test"],
  "jobs": {
    "running-test": {
      "id": "running-test",
      "type": "full_song",
      "status": "running",
      "emotion": "joy",
      "bars": 4,
      "k": 1,
      "publish": true,
      "project_id": "",
      "progress": 10,
      "message": "Rendering full song in LLM_AudioGen.",
      "created_at": "2026-06-11 12:00:00",
      "started_at": "2026-06-11 12:00:01",
      "finished_at": "",
      "cancel_requested": false,
      "result": null,
      "error": ""
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    with audiogen_bridge._QUEUE_CONDITION:  # noqa: SLF001
        audiogen_bridge._QUEUE_LOADED = False  # noqa: SLF001

    result = audiogen_bridge.render_job("running-test")

    assert result["ok"] is True
    assert result["job"]["status"] == "failed"
    assert result["job"]["progress"] == 100
    assert "restart" in result["job"]["message"].lower()
