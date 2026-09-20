"""Range-aware private media response helpers."""

from __future__ import annotations

from pathlib import Path


def send_audio_file_range(handler, file_path: Path) -> None:
    if not file_path.exists() or not file_path.is_file():
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b"File not found")
        return

    file_size = file_path.stat().st_size
    start = 0
    end = file_size - 1
    is_partial = False
    range_header = handler.headers.get("Range")
    if range_header and range_header.startswith("bytes="):
        is_partial = True
        try:
            start_text, end_text = range_header.removeprefix("bytes=").split("-", 1)
            if start_text:
                start = int(start_text)
            if end_text:
                end = int(end_text)
            if start >= file_size:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{file_size}")
                handler.end_headers()
                return
            end = min(end, file_size - 1)
        except (ValueError, IndexError):
            start = 0
            end = file_size - 1
            is_partial = False

    content_length = end - start + 1
    try:
        handler.send_response(206 if is_partial else 200)
        handler.send_header("Content-Type", "audio/wav")
        if is_partial:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        handler.send_header("Content-Length", str(content_length if is_partial else file_size))
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        with file_path.open("rb") as handle:
            if is_partial:
                handle.seek(start)
            remaining = content_length if is_partial else file_size
            while remaining > 0:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionError):
        pass
