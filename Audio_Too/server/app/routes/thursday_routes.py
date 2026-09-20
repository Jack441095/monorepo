"""Thursday API routes for the business server.

Core conversational routes — /api/thursday/ask (text + SSE stream),
/api/thursday/transcribe (browser audio -> local Whisper), /api/thursday/speak
(TTS) — plus the status route and the autonomous producer / commercial-dispatch
routes.

Note: the autonomous handlers are imported at module top on purpose. Importing
them lazily instead removes an early import that (as a side effect) resolves the
AudioGen `training`/`composition` namespace packages before pytest's collection
order can bind a shadowing `training` package — see the audiogen namespace note
in the project memory. Keeping these eager preserves that resolution so the
autonomous-producer/dispatcher tests collect cleanly.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from app.api_errors import exception_payload, send_public_exception
from thursday.autonomous_producer import AutonomousProducerUnavailable, ThursdayTaskDirector
from thursday.autonomous_dispatcher import ThursdayCommercialDispatcher

MAX_TRANSCRIPTION_BYTES = 2 * 1024 * 1024
TRANSCRIPTION_SUFFIXES = {
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
}


def handle_thursday_get(handler, parsed_path: str) -> bool:
    """Handle GET /api/thursday/* routes."""
    path_only = urlparse("https://host" + parsed_path).path
    if path_only in {"/api/thursday/status", "/api/thursday/dashboard-status"}:
        # Liveness only: confirms this process is up and routing Thursday
        # requests. ThursdayTaskDirector has no task-tracking/health-scoring
        # of its own to report here (previously this endpoint claimed
        # "active_tasks": 0 / "system_health": "100% operational" as fixed
        # literals regardless of actual state -- removed rather than kept
        # as a number nothing computes).
        handler.send_json(200, {
            "ok": True,
            "status": "online",
            "mode": "autonomous_commercial_orchestrator",
        })
        return True
    return False


def handle_thursday_post(handler, parsed_path: str) -> bool:
    """Handle POST /api/thursday/* routes."""
    path_only = urlparse("https://host" + parsed_path).path

    if path_only == "/api/thursday/ask":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        question = str(payload.get("question", "")).strip()
        if not question:
            handler.send_json(400, {"error": "question is required."})
            return True
        session_id = str(payload.get("session_id", "")).strip()
        request_id = (
            handler.request_id()
            if callable(getattr(handler, "request_id", None))
            else ""
        )
        if bool(payload.get("stream")):
            try:
                from thursday.bridge import ask_stream

                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")
                handler.send_header("Cache-Control", "no-cache")
                handler.send_header("Connection", "close")
                handler.end_headers()
                for chunk in ask_stream(
                    question, session_id=session_id, request_id=request_id
                ):
                    handler.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    handler.wfile.flush()
            except Exception as exc:
                try:
                    _, public = exception_payload(exc, request_id=request_id)
                    handler.wfile.write(
                        f"data: {json.dumps({'event': 'error', **public})}\n\n".encode()
                    )
                    handler.wfile.flush()
                except Exception:
                    pass
            return True
        try:
            from thursday.bridge import ask

            result = ask(question, session_id=session_id, request_id=request_id)
        except Exception as exc:
            send_public_exception(handler, exc)
            return True
        handler.send_json(200, result)
        return True

    if path_only == "/api/thursday/feedback":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        turn_id = str(payload.get("turn_id", "")).strip()
        rating_val = payload.get("rating")
        session_id = str(payload.get("session_id", "")).strip()

        if not turn_id or rating_val is None:
            handler.send_json(400, {"error": "turn_id and rating are required."})
            return True

        try:
            rating = int(rating_val)
        except (ValueError, TypeError):
            handler.send_json(400, {"error": "rating must be an integer."})
            return True

        try:
            from thursday.bridge import feedback
            res = feedback(turn_id, rating, session_id=session_id)
            handler.send_json(200, res)
        except Exception as exc:
            send_public_exception(handler, exc)
        return True

    if path_only == "/api/thursday/jarvis-action":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        action = str(payload.get("action", "")).strip().lower()

        if action == "query":
            prompt = str(payload.get("prompt", "")).strip()
            from kenn.core.chat import ask_once
            answer = ask_once(prompt)
            spoken = str(answer).replace("*", "").replace("#", "").replace("`", "")
            handler.send_json(200, {
                "ok": True,
                "text": answer,
                "spoken_text": spoken,
                "action": "query",
            })
            return True

        # explain_decisions/analyze_ableton/audit_session: the modules these
        # actions called (kenn.core.kenn_decision_explainer/kenn_daw_assistant/
        # kenn_mix_doctor) no longer exist anywhere in the repo -- removed at
        # some point without this dispatcher being updated, so each raised an
        # unhandled ModuleNotFoundError. The current thursday_hub.js UI never
        # sends these actions (only "query"), so this was unreachable via the
        # real UI but still crashed ungracefully for any direct API caller.
        # Failing honestly here instead of resurrecting unverified modules.
        if action in {"explain_decisions", "analyze_ableton", "audit_session"}:
            handler.send_json(501, {
                "ok": False,
                "error": f"Thursday action '{action}' is not currently available.",
                "action": action,
            })
            return True

        handler.send_json(400, {"error": f"Unknown action '{action}'"})
        return True


    if path_only == "/api/thursday/transcribe":
        mime_type = (
            str(handler.headers.get("Content-Type", ""))
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if mime_type not in TRANSCRIPTION_SUFFIXES:
            handler.send_json(400, {"error": "Unsupported browser audio format."})
            return True
        audio = handler.read_body_bytes()
        if not audio or len(audio) > MAX_TRANSCRIPTION_BYTES:
            handler.send_json(413, {"error": "Audio clip is empty or too large."})
            return True
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=TRANSCRIPTION_SUFFIXES[mime_type], delete=False
            ) as temp_file:
                temp_file.write(audio)
                temp_path = temp_file.name
            from thursday.voice import transcribe_with_metadata

            res = transcribe_with_metadata(temp_path)
            transcript = res.get("text", "").strip()
        except Exception as exc:
            send_public_exception(handler, exc)
            return True
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
        if not transcript:
            handler.send_json(422, {"error": "No speech was detected. Please try again."})
            return True
        handler.send_json(
            200,
            {
                "ok": True,
                "text": transcript,
                "engine": "local-whisper",
                "confidence": res.get("confidence", 1.0),
                "no_speech_prob": res.get("no_speech_prob", 0.0),
                "language": res.get("language", "en"),
                "duration": res.get("duration", 0.0),
                "clipping": res.get("clipping", False),
                "noise_floor_db": res.get("noise_floor_db", -96.0),
            },
        )
        return True

    if path_only == "/api/thursday/speak":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        text = str(payload.get("text", "")).strip()
        voice = str(payload.get("voice", "af_heart")).strip()
        speed = payload.get("speed")
        if speed is not None:
            try:
                speed = float(speed)
            except (TypeError, ValueError):
                speed = None
        if not text:
            handler.send_json(400, {"error": "text is required."})
            return True
        try:
            from thursday.voice_output import (
                KENN_VOICE,
                KOKORO_VOICE,
                synthesise_isolated,
            )

            resolved_voice = (
                KENN_VOICE
                if voice == "kenn"
                else KOKORO_VOICE
                if voice == "thursday"
                else voice
            )
            wav = synthesise_isolated(text, voice=resolved_voice, speed=speed)
        except Exception as exc:
            send_public_exception(handler, exc)
            return True
        if wav is None:
            handler.send_json(503, {"error": "TTS unavailable."})
            return True
        handler.send_bytes(200, wav, "audio/wav")
        return True

    if path_only in {"/api/thursday/autonomous-execute", "/api/v1/thursday/autonomous-execute"}:
        try:
            content_len = int(handler.headers.get("Content-Length", 0))
            raw_body = handler.rfile.read(content_len).decode("utf-8")
            data = json.loads(raw_body)
        except Exception as exc:
            handler.send_json(400, {"error": f"Invalid JSON body: {exc}"})
            return True

        instruction = data.get("instruction", "Create a 90 BPM Lo-Fi beat with swing")
        genre = data.get("genre", "lofi")
        bpm = int(data.get("bpm", 90))

        try:
            director = ThursdayTaskDirector()
            result = director.run_autonomous_producer_pipeline(
                instruction=instruction, genre=genre, bpm=bpm
            )
        except AutonomousProducerUnavailable as exc:
            handler.send_json(503, {"error": str(exc)})
            return True
        handler.send_json(200, result)
        return True

    if path_only in {"/api/thursday/commercial-dispatch", "/api/v1/thursday/commercial-dispatch"}:
        try:
            content_len = int(handler.headers.get("Content-Length", 0))
            raw_body = handler.rfile.read(content_len).decode("utf-8")
            data = json.loads(raw_body)
        except Exception as exc:
            handler.send_json(400, {"error": f"Invalid JSON body: {exc}"})
            return True

        client_name = data.get("client_name", "Acme Records")
        project_title = data.get("project_title", "Commercial Single #001")
        genre = data.get("genre", "pop")
        bpm = int(data.get("bpm", 120))
        target_lufs = float(data.get("target_lufs", -14.0))

        dispatcher = ThursdayCommercialDispatcher()
        result = dispatcher.execute_commercial_job(
            client_name=client_name,
            project_title=project_title,
            genre=genre,
            bpm=bpm,
            target_lufs=target_lufs,
        )
        handler.send_json(200, result)
        return True

    return False
