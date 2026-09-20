"""Shared resumable-download helper for large model-file fetch scripts.

Extracted from ``fetch_embedding_model.py`` after this exact resume logic
proved necessary in practice: this network has repeatedly dropped large
(~90MB+) downloads partway through (consistently after 80-95% complete,
across many attempts spanning a full session), so downloads must resume
from wherever the previous attempt left off rather than restart from
scratch every retry — a from-scratch retry loop never converged, resuming
did on the very next attempt.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1 MiB
MAX_ATTEMPTS = 5


def content_length(url: str) -> int | None:
    """Get the remote file size via a 1-byte Range GET.

    Not a HEAD request: some CDN/redirect chains fronting large release
    assets (observed on GitHub Releases) respond to HEAD with a 504 while
    GET+Range works fine.
    """
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content_range = resp.headers.get("Content-Range")
        if content_range and "/" in content_range:
            return int(content_range.rsplit("/", 1)[-1])
        length = resp.headers.get("Content-Length")
        return int(length) if length is not None else None


def _download_chunk(url: str, tmp_dest: Path, *, resume_from: int) -> None:
    """Append to ``tmp_dest`` starting at byte ``resume_from`` via an HTTP
    Range request, rather than re-downloading from scratch."""
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    req = urllib.request.Request(url, headers=headers)
    mode = "ab" if resume_from else "wb"
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_dest, mode) as fh:
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)


def download(url: str, dest: Path) -> None:
    """Download to a temp file and rename atomically so a failed/interrupted
    transfer never leaves a broken file at ``dest`` that a later run's
    existence check would mistake for a completed download. Resumes from
    wherever the previous attempt left off instead of restarting."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {url}\n    -> {dest}")
    tmp_dest = dest.with_suffix(dest.suffix + ".part")

    try:
        expected_bytes = content_length(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not reach {url} to check its size: {exc}") from exc

    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resume_from = tmp_dest.stat().st_size if tmp_dest.exists() else 0
        if expected_bytes is not None and resume_from > expected_bytes:
            # Stale/corrupt partial larger than the real file — can't trust it.
            tmp_dest.unlink(missing_ok=True)
            resume_from = 0
        try:
            _download_chunk(url, tmp_dest, resume_from=resume_from)
            received_bytes = tmp_dest.stat().st_size
            # A server can close the connection cleanly (empty chunk) before
            # sending everything it promised — that must not be mistaken for
            # a successful download, or a truncated file gets shipped.
            if expected_bytes is not None and received_bytes != expected_bytes:
                raise IOError(
                    f"Incomplete download: got {received_bytes:,} bytes, expected {expected_bytes:,}"
                )
            tmp_dest.replace(dest)
            print(f"    {dest.stat().st_size:,} bytes")
            return
        except (urllib.error.URLError, http.client.IncompleteRead, TimeoutError, OSError) as exc:
            last_exc = exc
            # Deliberately NOT deleting tmp_dest here — that's the whole
            # point of resuming. Only the "stale/too-large" case above and
            # final exhaustion (below) discard it.
            if attempt < MAX_ATTEMPTS:
                now_have = tmp_dest.stat().st_size if tmp_dest.exists() else 0
                wait = 2 ** attempt
                print(
                    f"    attempt {attempt}/{MAX_ATTEMPTS} failed ({exc}); "
                    f"have {now_have:,} bytes so far, resuming in {wait}s"
                )
                time.sleep(wait)
    tmp_dest.unlink(missing_ok=True)
    raise RuntimeError(f"Failed to download {url} after {MAX_ATTEMPTS} attempts") from last_exc
