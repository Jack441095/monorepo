#!/usr/bin/env python3
"""
Content-addressed cache keying for feature extraction pipelines.

The feature caches (mw_features_v1.npz, physics_cache_v1.npz, ...) were keyed
by PATH STRING ONLY. If a sample file is edited, re-rendered, or replaced by a
different file at the same path, the stale features are silently reused -- a
quiet correctness hole in every benchmark built on those caches.

Fix: key cache entries by the sha256 of the file CONTENT, memoised behind a
(size, mtime_ns) sidecar so unchanged files are never rehashed. A file whose
size or mtime changed is rehashed; a hash miss means "recompute this file".

No numpy/object-array assumptions beyond what the callers already use.
"""
import hashlib
import json
import os

CHUNK = 1 << 20


class DigestIndex:
    """sha256 digests for a set of files, memoised by (size, mtime_ns).

    Sidecar layout: {path: {"size": int, "mtime_ns": int, "sha256": hex}}
    If size AND mtime_ns both match the sidecar, the stored digest is trusted.
    Otherwise the file is rehashed and the sidecar updated (atomically).
    """

    def __init__(self, sidecar_path):
        self.sidecar = sidecar_path
        self._memo = {}
        self._dirty = False
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path) as f:
                    self._memo = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._memo = {}

    def digest(self, path):
        """Content sha256 for path (hex). Returns None if unreadable."""
        path = os.path.abspath(path)
        try:
            st = os.stat(path)
        except OSError:
            return None
        key_size, key_mtime = st.st_size, st.st_mtime_ns
        rec = self._memo.get(path)
        if rec and rec.get("size") == key_size and rec.get("mtime_ns") == key_mtime:
            return rec.get("sha256")
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while True:
                    b = f.read(CHUNK)
                    if not b:
                        break
                    h.update(b)
        except OSError:
            return None
        d = h.hexdigest()
        self._memo[path] = {"size": key_size, "mtime_ns": key_mtime, "sha256": d}
        self._dirty = True
        return d

    def flush(self):
        """Persist the sidecar atomically (no-op if nothing changed)."""
        if not self._dirty:
            return
        tmp = self.sidecar + ".tmp"
        os.makedirs(os.path.dirname(self.sidecar) or ".", exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(self._memo, f)
        os.replace(tmp, self.sidecar)
        self._dirty = False
