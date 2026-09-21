"""Upload-based routes: ask-attachment, automix, and stem separation."""

from __future__ import annotations

from typing import Any


def handle_ask_attachment(handler: Any) -> None:
    """POST /api/ask-attachment: a chat message with one or more audio
    files attached directly in the composer, instead of the separate
    upload widget. Jack's decision (2026-08-05): explicit phrase
    required, same rule as text-only chat triggers -- attaching a file
    with no matching instruction gets a clarifying question back, not a
    guess at what to do with it."""
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"error": "Invalid Content-Length."})
        return
    if length <= 0:
        handler.send_json(400, {"error": "Upload body is required."})
        return
    if length > 150 * 1024 * 1024:
        handler.send_json(413, {"error": "Upload is too large."})
        return
    try:
        body = handler.rfile.read(length)
        import stem_uploads
        fields = stem_uploads.parse_multipart_form(content_type, body)
    except Exception as exc:
        handler.send_json(500, {"error": f"Attachment upload failed: {exc}"})
        return

    question = str(fields.get("question", "")).strip()
    session_id = str(fields.get("session_id", "")).strip()
    files: list[tuple[bytes, str]] = []
    index = 0
    while f"file_{index}" in fields:
        file_bytes = fields.get(f"file_{index}")
        if isinstance(file_bytes, (bytes, bytearray)):
            filename = str(fields.get(f"file_{index}__filename", f"file_{index}.wav"))
            files.append((bytes(file_bytes), filename))
        index += 1
    if not files:
        handler.send_json(400, {"error": "No audio file attached."})
        return

    from kenn.core.tool_trigger import detect_tool_trigger
    tool_name = detect_tool_trigger(question)
    if tool_name is None:
        handler.send_json(200, {
            "answer": (
                "I see you attached audio, but I'm not sure what you'd like me to do with it. "
                'Try "run a mix review on this," "separate this into stems," '
                '"analyze these stems for masking," or "start an automix from these."'
            ),
            "tool_invoked": None,
        })
        return

    from kenn.server import resolve_session_project, _build_tool_answer

    project_id = resolve_session_project(session_id)
    try:
        from kenn.core.tool_registry import invoke_tool
        if tool_name in {"run_automix", "run_stem_masking"}:
            result = invoke_tool(tool_name, session_id=session_id, files=files, project_id=project_id)
            filename = ", ".join(name for _bytes, name in files)
        else:
            file_bytes, filename = files[0]
            result = invoke_tool(
                tool_name, session_id=session_id, file_bytes=file_bytes,
                filename=filename, project_id=project_id,
            )
    except Exception as exc:
        handler.send_json(500, {"error": f"Could not run {tool_name}: {exc}"})
        return
    handler.send_json(200, _build_tool_answer(tool_name, result, filename))


def handle_automix_upload(handler: Any, automix_public: Any) -> None:
    """Multiple stem files -> a fresh AutoMix project + a real queued
    job, called directly in-process via business/app/automix_public.py
    (same shared-filesystem import pattern already used here for
    mix_review/audiogen_bridge -- no HTTP proxy to :8080). The job row
    lands in the same SQLite DB the standalone AutoMix worker process
    (main.py worker, launched alongside this server by scripts/serve.py)
    already polls, so it gets picked up and rendered the normal way.
    """
    if not automix_public:
        handler.send_json(503, {"error": "AutoMix is unavailable."})
        return
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"error": "Invalid Content-Length."})
        return
    if length <= 0:
        handler.send_json(400, {"error": "Upload body is required."})
        return
    if length > 500 * 1024 * 1024:
        handler.send_json(413, {"error": "AutoMix stem upload exceeds the 500 MB limit."})
        return
    try:
        body = handler.rfile.read(length)
        import stem_uploads
        fields = stem_uploads.parse_multipart_form(content_type, body)
    except ValueError as exc:
        handler.send_json(400, {"error": str(exc)})
        return
    except Exception as exc:
        handler.send_json(500, {"error": f"AutoMix upload failed: {exc}"})
        return
    files: list[tuple[bytes, str]] = []
    index = 0
    while f"stem_{index}" in fields:
        file_bytes = fields.get(f"stem_{index}")
        if isinstance(file_bytes, (bytes, bytearray)):
            filename = str(fields.get(f"stem_{index}__filename", f"stem_{index}.wav"))
            files.append((bytes(file_bytes), filename))
        index += 1
    if not files:
        handler.send_json(400, {"error": "No stem files provided (expected stem_0, stem_1, ...)."})
        return

    from kenn.server import resolve_session_project

    genre = str(fields.get("genre", "pop") or "pop")
    project_id = resolve_session_project(str(fields.get("session_id", "")).strip())
    try:
        result = automix_public.start_public_automix(files, genre=genre, project_id=project_id)
    except Exception as exc:
        handler.send_json(500, {"error": f"AutoMix upload failed: {exc}"})
        return
    handler.send_json(200 if result.get("ok") else 400, result)


def handle_stem_separate_upload(handler: Any, stem_separation_bridge: Any) -> None:
    """One mixed track -> a real Demucs stem-separation job, called
    directly in-process via business/app/stem_separation_bridge.py --
    same shared-filesystem import pattern as handle_automix_upload
    above, not the public/token-gated /api/public/stem-separate path
    (that one's for external callers with no dashboard/KENN session)."""
    if not stem_separation_bridge:
        handler.send_json(503, {"error": "Stem separation is unavailable."})
        return
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"error": "Invalid Content-Length."})
        return
    if length <= 0:
        handler.send_json(400, {"error": "Upload body is required."})
        return
    if length > 150 * 1024 * 1024:
        handler.send_json(413, {"error": "Upload is too large."})
        return
    try:
        body = handler.rfile.read(length)
        import stem_uploads
        fields = stem_uploads.parse_multipart_form(content_type, body)
    except ValueError as exc:
        handler.send_json(400, {"error": str(exc)})
        return
    except Exception as exc:
        handler.send_json(500, {"error": f"Stem separation upload failed: {exc}"})
        return
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        handler.send_json(400, {"error": "Missing file field."})
        return

    from kenn.server import resolve_session_project

    filename = str(fields.get("file__filename", "mix.wav"))
    project_id = resolve_session_project(str(fields.get("session_id", "")).strip())
    try:
        result = stem_separation_bridge.enqueue_separation(bytes(file_bytes), filename, project_id=project_id)
    except Exception as exc:
        handler.send_json(500, {"error": f"Stem separation upload failed: {exc}"})
        return
    if not result.get("ok"):
        handler.send_json(400, result)
        return
    handler.send_json(200, {"ok": True, "job_id": result["job"]["id"], "status": result["job"]["status"]})
