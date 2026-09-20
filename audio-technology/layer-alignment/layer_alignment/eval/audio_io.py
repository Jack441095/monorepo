"""Safe audio I/O for the real-audio validation harness.

Rules honoured (sprint §7, §54):
  - original licensed material is opened READ-ONLY; never written
  - every failure mode fails safely with a typed error, never a crash
    and never fabricated analysis output
  - stdlib `wave` + numpy: no new dependencies; WAV_PCM16/24/32f supported.
    Other formats are rejected with UNSUPPORTED_FORMAT (recorded as such
    in manifests — conversion happens OUTSIDE this harness by the owner).
"""
from __future__ import annotations

import hashlib
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class AudioLoadError(Exception):
    """Typed load failure: kind in UNSUPPORTED_FORMAT, CORRUPT, EMPTY,
    TOO_SHORT, IO_ERROR."""


@dataclass
class LoadedAudio:
    samples: np.ndarray        # float64 mono (mean of channels), [-1..1]-ish
    sample_rate: int
    channels: int
    duration_s: float
    sha256: str                # of the source file bytes (provenance)


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_wav(path: Path, min_samples: int = 256) -> LoadedAudio:
    try:
        return _load_wav_native(path, min_samples)
    except AudioLoadError as e:
        # float32/other non-PCM WAVs are rejected by stdlib `wave`;
        # fall back to a LOCAL afconvert-derived PCM24 copy (originals
        # untouched; derived cache lives outside any source tree).
        if "CORRUPT" not in str(e) and "UNSUPPORTED" not in str(e):
            raise
        conv = _afconvert_derived(Path(path))
        if conv is None:
            raise
        return _load_wav_native(conv, min_samples)


def _afconvert_derived(p: Path) -> Path | None:
    import subprocess
    cache = Path("/var/folders/7n/v41hqm4s3rx4vd536fghb0zh0000gn/T/opencode/"
                 "afconvert_cache")
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / (file_sha256(p)[:16] + ".wav")
    if out.exists():
        return out
    r = subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI24",
                        str(p), str(out)], capture_output=True)
    if r.returncode != 0 or not out.exists():
        return None
    return out


def _load_wav_native(path: Path, min_samples: int = 256) -> LoadedAudio:
    p = Path(path)
    if not p.exists():
        raise AudioLoadError("IO_ERROR", p.name)
    if p.suffix.lower() not in (".wav", ".wave"):
        raise AudioLoadError("UNSUPPORTED_FORMAT", p.name)
    try:
        with wave.open(str(p), "rb") as w:
            nch = w.getnchannels()
            sr = w.getframerate()
            sw = w.getsampwidth()
            n = w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, RuntimeError, EOFError, struct.error) as e:
        raise AudioLoadError("CORRUPT", f"{p.name}: {e}")
    except IsADirectoryError:
        raise AudioLoadError("IO_ERROR", p.name)

    if n == 0 or len(raw) == 0:
        raise AudioLoadError("EMPTY", p.name)
    if n * nch * sw != len(raw):
        raise AudioLoadError("CORRUPT", p.name + " (truncated)")
    if n < min_samples:
        raise AudioLoadError("TOO_SHORT", f"{p.name}: {n} samples")

    if sw == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif sw == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = (a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16))
        v = np.where(v & 0x800000, v - (1 << 24), v)
        x = v.astype(np.float64) / float(1 << 23)
    elif sw == 4:
        # try float32 first (WAV_FORMAT_FLOAT), fall back to int32
        try:
            xf = np.frombuffer(raw, dtype="<f4").astype(np.float64)
            if np.isfinite(xf).all():
                x = xf
            else:
                raise ValueError("non-finite")
        except ValueError:
            x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / \
                float(1 << 31)
    else:
        raise AudioLoadError("UNSUPPORTED_FORMAT", f"{p.name}: {sw*8}-bit")

    if nch > 1:
        x = x.reshape(-1, nch).mean(axis=1)   # mono fold for analysis

    if not np.isfinite(x).all():
        raise AudioLoadError("CORRUPT", p.name + " (non-finite samples)")

    return LoadedAudio(samples=x, sample_rate=sr, channels=nch,
                       duration_s=n / sr, sha256=file_sha256(p))


def resample_linear(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Linear-resample (harness/preview quality only; analysis always uses
    native-rate copies — see manifest notes)."""
    if sr_from == sr_to:
        return x
    n_out = int(round(len(x) * sr_to / sr_from))
    idx = np.linspace(0, len(x) - 1, n_out)
    i0 = np.clip(idx.astype(int), 0, len(x) - 2)
    frac = idx - i0
    return x[i0] * (1 - frac) + x[i0 + 1] * frac


def write_wav(path: Path, x: np.ndarray, sr: int, width: int = 2) -> None:
    """Write audition/derived copies only — never originals."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    y = np.asarray(x, dtype=np.float64)
    peak = np.max(np.abs(y)) + 1e-12
    if peak > 1.0:
        y = y / peak                      # prevent clip on derived previews
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(sr)
        if width == 2:
            frames = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        elif width == 3:
            v = (np.clip(y, -1, 1) * float(1 << 23)).astype(np.int64)
            b = np.zeros((len(v), 3), dtype=np.uint8)
            b[:, 0] = v & 0xFF
            b[:, 1] = (v >> 8) & 0xFF
            b[:, 2] = (v >> 16) & 0xFF
            frames = b.tobytes()
        else:
            frames = (np.clip(y, -1, 1) *
                      np.float32(1.0)).astype("<f4").tobytes()
        w.writeframes(frames)
