"""Small HTTP plumbing shared by the KENN server and its route modules.

We keep these beside the server instead of inside it so ``server.py`` stays a
thin dispatcher and ``routes/audio_handler.py`` + ``routes/upload_handler.py``
import from one place. All three are pure: bytes or a parsed URL in, plain
data out, no Live writes, no filesystem reads. A wrong answer here only
misroutes or miswords one reply.

Multipart decoding stays bounded and in memory: uploads are small form fields
and WAV names, never multi-gigabyte stems, so holding ``body`` (a few MB at
most) while parsing is cheaper than spooling to disk. The ``/kenn`` prefix
strip dates to the Aug 2026 proxy rework: app.js calls ``/kenn/api/...``
uniformly, while the route table is still keyed on bare ``/api/...`` paths.
"""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_default


def multipart_files(content_type: str, body: bytes) -> list[tuple[str, bytes, str]]:
    """Decode bounded multipart form fields without writing uploaded bytes."""
    envelope = BytesParser(policy=email_default).parsebytes(
        (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
    )
    files: list[tuple[str, bytes, str]] = []
    for part in envelope.walk():
        if part.get_content_disposition() != "form-data":
            continue
        payload = part.get_payload(decode=True)
        filename = str(part.get_filename() or "")
        name = str(part.get_param("name", header="content-disposition") or "")
        if isinstance(payload, (bytes, bytearray)) and filename:
            files.append((name, bytes(payload), filename))
    return files


def strip_kenn_prefix(parsed):
    """Strip the ``/kenn`` proxy prefix (and legacy ``/api/admin/``) once, centrally.

    Every ``if parsed.path == "/api/..."`` check then keeps working unchanged
    for both direct ``:8090`` access and proxied requests, instead of
    duplicating every route. ``kenn_proxy_routes.py`` already strips this same
    prefix before forwarding, so a proxied request usually arrives bare
    already; this only matters for direct access.
    """
    if parsed.path in ("/kenn", "/kenn/"):
        return parsed._replace(path="/")
    if parsed.path.startswith("/kenn/"):
        return parsed._replace(path=parsed.path[len("/kenn"):])
    if parsed.path.startswith("/api/admin/"):
        return parsed._replace(path="/api/" + parsed.path[len("/api/admin/"):])
    return parsed


def build_tool_answer(tool_name: str, result: dict, filename: str) -> dict:
    """Chat-shaped {answer, tool_invoked, tool_result} reply for a tool call
    that already ran -- shared by the text-only trigger
    (_maybe_run_explicit_tool_trigger) and the chat-bar-attachment handler
    (handle_ask_attachment), so both produce identical wording/shape (the
    frontend's pollAndRenderToolResult() branches on tool_invoked the same
    way regardless of which path fired it)."""
    if not result.get("ok"):
        return {
            "answer": f"I tried to run that but it didn't work: {result.get('error', 'unknown error')}",
            "tool_invoked": tool_name,
            "tool_result": result,
        }
    if tool_name == "run_stem_separation":
        answer = f"Started separating {filename} into stems (job {result.get('job', {}).get('id', '')})."
    elif tool_name == "run_automix":
        answer = f"Started an AutoMix render (project {result.get('project_id', '')})."
    elif tool_name == "run_stem_masking":
        stem_count = len(result.get("stems") or [])
        finding_count = len(result.get("findings") or [])
        answer = f"Completed a stem masking check on {stem_count} stems; found {finding_count} listening check(s)."
    else:
        answer = f"Started a mix review on {filename}."
    return {"answer": answer, "tool_invoked": tool_name, "tool_result": result}
