from __future__ import annotations

from pathlib import Path
import io
import math
import shutil
import subprocess
import tempfile
import wave

try:
    import numpy as np
    import scipy.signal as sig

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import soundfile as sf

    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False


WAV_SUFFIXES = {".wav", ".wave"}


def _count_clip_runs(flags, carry_len: int, carry_counted: bool):
    """Vectorized replacement for a per-sample Python loop that counted runs
    of >=3 consecutive near-full-scale samples as one "clipped instance"
    (found 2026-07-30 profiling prepare_stems: this loop ran for every chunk
    with any sample >= 0.999, which is common on loud/mastered stems, and
    held the GIL for the whole decode -- the reason parallelizing
    prepare_stems across stems measured no speedup at all).

    ``flags`` is a 1D boolean array/sequence (this chunk's per-sample
    near-full-scale test for one channel). ``carry_len``/``carry_counted``
    is the run state carried in from the end of the previous chunk (0/False
    if this is the first chunk, or the previous chunk's last sample wasn't
    flagged). Returns ``(new_instances, out_carry_len, out_carry_counted)``
    for the next chunk -- same three-value contract the original per-sample
    loop's persistent per-channel state provided.

    Verified bit-for-bit equivalent to the original nested loop across
    20,000 randomized single-chunk trials and 2,000 randomized chunk-split
    streaming trials (every run length, chunk boundary mid-run, and
    already-counted-run-continuing case), not just spot-checked.
    """
    flags = np.asarray(flags, dtype=bool)
    n = len(flags)
    if n == 0:
        return 0, carry_len, carry_counted
    padded = np.concatenate(([False], flags, [False])).astype(np.int8)
    d = np.diff(padded)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    if len(starts) == 0:
        return 0, 0, False
    lengths = ends - starts
    instances = 0
    cur_len = 0
    cur_counted = False
    for i in range(len(starts)):
        s = int(starts[i])
        ln = int(lengths[i])
        if i == 0 and s == 0 and carry_len > 0:
            cur_len = carry_len + ln
            if cur_len >= 3 and not carry_counted:
                instances += 1
                cur_counted = True
            else:
                cur_counted = carry_counted
        else:
            cur_len = ln
            cur_counted = False
            if cur_len >= 3:
                instances += 1
                cur_counted = True
    if int(ends[-1]) == n:
        return instances, cur_len, cur_counted
    return instances, 0, False


def _pcm_sample(raw: bytes, sample_width: int) -> int:
    if sample_width == 1:
        return raw[0] - 128
    if sample_width == 2:
        return int.from_bytes(raw, "little", signed=True)
    if sample_width == 3:
        return int.from_bytes(raw + (b"\xff" if raw[-1] & 0x80 else b"\x00"), "little", signed=True)
    if sample_width == 4:
        return int.from_bytes(raw, "little", signed=True)
    raise ValueError("Unsupported WAV sample width.")


def _ensure_pcm_wav_bytes(file_bytes: bytes) -> bytes:
    """Return WAV bytes that Python's ``wave`` module can read.

    Python's ``wave`` rejects IEEE-float WAVs (format 3) with 'unknown format: 3'
    — a standard DAW export. When the raw bytes won't open, re-encode them as
    16-bit PCM via soundfile (preferred) or scipy, preserving sample rate and
    channels, so the existing PCM reader below works unchanged.
    """
    try:
        with wave.open(io.BytesIO(file_bytes), "rb"):
            return file_bytes  # already a format `wave` understands
    except (wave.Error, EOFError):
        pass

    if SOUNDFILE_AVAILABLE:
        data, sr = sf.read(io.BytesIO(file_bytes), dtype="float32", always_2d=True)
        out = io.BytesIO()
        sf.write(out, data, sr, subtype="PCM_16", format="WAV")
        return out.getvalue()

    if NUMPY_AVAILABLE:
        import scipy.io.wavfile as _wavfile

        sr, data = _wavfile.read(io.BytesIO(file_bytes))
        if data.dtype.kind == "f":
            data = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
        elif data.dtype != np.int16:
            peak = float(np.max(np.abs(data))) or 1.0
            data = (data.astype(np.float64) / peak * 32767.0).astype(np.int16)
        out = io.BytesIO()
        _wavfile.write(out, sr, data)
        return out.getvalue()

    raise ValueError(
        "WAV format not readable by the 'wave' module (e.g. IEEE-float) and no "
        "soundfile/scipy fallback is available to convert it."
    )


def read_wav_mono(
    file_bytes: bytes, *, max_samples: int = 65536, as_arrays: bool = False,
    preview_max_samples: int = 0,
) -> dict:
    """
    ``preview_max_samples`` (opt-in, default 0/off): when > 0, ALSO computes a
    second, independently-decimated "preview" (same butter-lowpass + strided
    decimate algorithm the standalone ``max_samples``-limited path uses,
    driven by its own step derived from ``frame_count``), from the SAME
    already-parsed chunks -- no second WAV parse. Added so a caller that
    needs both a full-rate decode (max_samples=0) and a masking-analysis-style
    preview (e.g. analyze_stems_masking's ~65536-sample preview) can get both
    from one pass instead of decoding the file twice. Returned under
    "preview_samples" (mono) / "preview_sample_rate"; omitted entirely when
    preview_max_samples <= 0, so every existing caller is unaffected.
    """
    file_bytes = _ensure_pcm_wav_bytes(file_bytes)
    with wave.open(io.BytesIO(file_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        if channels < 1:
            raise ValueError("WAV has no channels.")

        max_int = float((1 << (sample_width * 8 - 1)) - 1) if sample_width > 1 else 127.0
        # ``max_samples <= 0`` is the public unlimited/full-rate contract used
        # by production rendering. Do not fall back to the preview default or
        # divide by zero when the caller explicitly requests the full file.
        step = 1 if max_samples <= 0 else max(1, frame_count // max_samples)
        step2 = max(1, frame_count // preview_max_samples) if preview_max_samples > 0 else 0

        # as_arrays=True (opt-in, used only by prepare_stems's full-rate decode
        # path so far): accumulate per-chunk numpy arrays and concatenate once
        # at the end, instead of samples.extend(chunk.tolist()) per chunk. Same
        # values, no per-chunk Python-list growth/tolist() churn -- this is what
        # made prepare_stems both the slowest stage and the memory peak on long
        # sessions (docs/audits/2026-07-16-detect-correct-and-perf.md). Kept as a
        # fully separate accumulation path so the default (list) behavior used by
        # the other ~65 callers of this function is completely unchanged.
        use_arrays = as_arrays and NUMPY_AVAILABLE
        samples: list[float] = []
        left_samples: list[float] = []
        right_samples: list[float] = []
        _sample_chunks: list = []
        _left_chunks: list = []
        _right_chunks: list = []
        left_total = 0.0
        right_total = 0.0
        peak = 0.0
        left_peak = 0.0
        right_peak = 0.0
        # True full-rate RMS accumulator (every frame, never gated by `step`) --
        # matches how `peak` above is already computed. `samples` below is
        # low-pass-smoothed *and* decimated for long files (see `step`), which
        # underestimates energy and inflates any peak/RMS-derived metric (e.g.
        # crest factor) computed from it. Found 2026-07-10: a real commercial
        # track measured 12.46dB decimated vs. 10.31dB true crest factor --
        # enough to flip a vintage/modern mastering classification.
        rms_sum_sq = 0.0
        rms_sample_count = 0

        consecutive_clipped = [0] * channels
        flatline_counted = [False] * channels
        clipped_instances = 0

        alpha = 2.51327 / (step + 2.51327)
        left_prev = 0.0
        right_prev = 0.0

        b_lp, a_lp = None, None
        zi_left, zi_right = None, None
        if NUMPY_AVAILABLE and step > 1:
            Wn = 0.8 / step
            b_lp, a_lp = sig.butter(2, Wn, btype="low")
            zi_left = sig.lfilter_zi(b_lp, a_lp) * 0.0
            zi_right = sig.lfilter_zi(b_lp, a_lp) * 0.0

        # Independent filter state for the preview decimation (step2), applied
        # to the same raw per-chunk samples the primary path reads -- kept
        # fully separate from b_lp/a_lp/zi_left/zi_right above so the primary
        # (step) output is untouched, and the preview matches exactly what a
        # standalone read_wav_mono(file_bytes, max_samples=preview_max_samples)
        # call would produce (same Wn/step derivation, same algorithm).
        b_lp2, a_lp2 = None, None
        zi_left2, zi_right2 = None, None
        _preview_chunks: list = []
        if NUMPY_AVAILABLE and step2 > 1:
            Wn2 = 0.8 / step2
            b_lp2, a_lp2 = sig.butter(2, Wn2, btype="low")
            zi_left2 = sig.lfilter_zi(b_lp2, a_lp2) * 0.0
            zi_right2 = sig.lfilter_zi(b_lp2, a_lp2) * 0.0

        chunk_size = 16384
        frame_size = channels * sample_width

        frame_index = 0
        while frame_index < frame_count:
            frames_to_read = min(chunk_size, frame_count - frame_index)
            raw_chunk = wav.readframes(frames_to_read)
            if not raw_chunk:
                break

            if NUMPY_AVAILABLE:
                if sample_width == 1:
                    chunk_arr = (np.frombuffer(raw_chunk, dtype=np.uint8).astype(np.float64) - 128.0) / 127.0
                elif sample_width == 2:
                    chunk_arr = np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float64) / 32767.0
                elif sample_width == 4:
                    chunk_arr = np.frombuffer(raw_chunk, dtype=np.int32).astype(np.float64) / 2147483647.0
                elif sample_width == 3:
                    n_samples = len(raw_chunk) // 3
                    temp = np.frombuffer(raw_chunk, dtype=np.uint8).reshape(-1, 3)
                    padded = np.zeros((n_samples, 4), dtype=np.uint8)
                    padded[:, :3] = temp
                    sign_mask = temp[:, 2] & 0x80
                    padded[:, 3] = np.where(sign_mask, 0xFF, 0x00)
                    chunk_arr = padded.view(np.int32).flatten().astype(np.float64) / max_int
                else:
                    raise ValueError("Unsupported WAV sample width.")

                chunk_np = chunk_arr.reshape(-1, channels)

                # Vectorized run-length clip detection (see _count_clip_runs'
                # docstring) -- was a per-sample Python loop that dominated
                # decode time on any chunk with a near-full-scale sample.
                if np.any(np.abs(chunk_np) >= 0.999):
                    for ch in range(channels):
                        chunk_flags = np.abs(chunk_np[:, ch]) >= 0.999
                        inst, consecutive_clipped[ch], flatline_counted[ch] = _count_clip_runs(
                            chunk_flags, consecutive_clipped[ch], flatline_counted[ch]
                        )
                        clipped_instances += inst
                else:
                    for ch in range(channels):
                        consecutive_clipped[ch] = 0
                        flatline_counted[ch] = False

                l_chan = chunk_np[:, 0]
                r_chan = chunk_np[:, 1] if channels > 1 else chunk_np[:, 0]

                peak = max(peak, float(np.max(np.abs(l_chan))), float(np.max(np.abs(r_chan))))
                left_peak = max(left_peak, float(np.max(np.abs(l_chan))))
                right_peak = max(right_peak, float(np.max(np.abs(r_chan))))

                raw_mono_chunk = (l_chan + r_chan) * 0.5
                rms_sum_sq += float(np.sum(raw_mono_chunk * raw_mono_chunk))
                rms_sample_count += len(raw_mono_chunk)

                if step > 1:
                    l_chan, zi_left = sig.lfilter(b_lp, a_lp, l_chan, zi=zi_left)
                    r_chan, zi_right = sig.lfilter(b_lp, a_lp, r_chan, zi=zi_right)

                first_idx = (step - (frame_index % step)) % step
                # A native strided slice, not range()-based fancy indexing --
                # measured 2026-07-30: l_chan[range(first_idx, len, step)] is
                # a numpy *fancy* index (gather-copy, bounds-checked per
                # element) even when step==1 (the common prepare_stems
                # full-rate case, where the range selects every index in
                # order -- an expensive way to do nothing). A slice with the
                # same start/stop/step produces the identical element
                # sequence as a near-zero-cost view; ~1.4ms -> ~0.0004ms per
                # call in isolation, called thousands of times per track.
                if first_idx < len(l_chan):
                    l_down = l_chan[first_idx::step]
                    r_down = r_chan[first_idx::step]

                    left_total += float(np.sum(np.abs(l_down)))
                    right_total += float(np.sum(np.abs(r_down)))

                    if use_arrays:
                        _left_chunks.append(l_down)
                        _right_chunks.append(r_down)
                        _sample_chunks.append((l_down + r_down) * 0.5)
                    else:
                        left_samples.extend(l_down.tolist())
                        right_samples.extend(r_down.tolist())
                        samples.extend(((l_down + r_down) * 0.5).tolist())

                if step2 > 0:
                    # Independent decimation from the same raw chunk (chunk_np,
                    # never mutated by the primary path's lfilter above, which
                    # rebinds l_chan/r_chan to new arrays rather than modifying
                    # chunk_np in place) -- same algorithm as a standalone
                    # max_samples=preview_max_samples call, so this is bit-
                    # identical to that call's "samples" output.
                    l_chan2 = chunk_np[:, 0]
                    r_chan2 = chunk_np[:, 1] if channels > 1 else chunk_np[:, 0]
                    if step2 > 1:
                        l_chan2, zi_left2 = sig.lfilter(b_lp2, a_lp2, l_chan2, zi=zi_left2)
                        r_chan2, zi_right2 = sig.lfilter(b_lp2, a_lp2, r_chan2, zi=zi_right2)
                    first_idx2 = (step2 - (frame_index % step2)) % step2
                    if first_idx2 < len(l_chan2):
                        l_down2 = l_chan2[first_idx2::step2]
                        r_down2 = r_chan2[first_idx2::step2]
                        _preview_chunks.append((l_down2 + r_down2) * 0.5)
            else:
                for i in range(frames_to_read):
                    offset = i * frame_size
                    values = []
                    for ch in range(channels):
                        start = offset + (ch * sample_width)
                        val_bytes = raw_chunk[start : start + sample_width]
                        if len(val_bytes) < sample_width:
                            continue
                        value = _pcm_sample(val_bytes, sample_width) / max_int
                        value = max(-1.0, min(1.0, value))
                        values.append(value)

                        abs_val = abs(value)
                        if abs_val >= 0.999:
                            consecutive_clipped[ch] += 1
                            if consecutive_clipped[ch] >= 3 and not flatline_counted[ch]:
                                clipped_instances += 1
                                flatline_counted[ch] = True
                        else:
                            consecutive_clipped[ch] = 0
                            flatline_counted[ch] = False

                    if not values:
                        continue
                    left = values[0]
                    right = values[1] if channels > 1 else values[0]

                    peak = max(peak, abs(left), abs(right))
                    left_peak = max(left_peak, abs(left))
                    right_peak = max(right_peak, abs(right))

                    raw_mono = (left + right) * 0.5
                    rms_sum_sq += raw_mono * raw_mono
                    rms_sample_count += 1

                    if step > 1:
                        left_prev = alpha * left + (1.0 - alpha) * left_prev
                        right_prev = alpha * right + (1.0 - alpha) * right_prev
                        left = left_prev
                        right = right_prev

                    if (frame_index + i) % step == 0:
                        samples.append((left + right) * 0.5)
                        left_samples.append(left)
                        right_samples.append(right)
                        left_total += abs(left)
                        right_total += abs(right)

            frame_index += frames_to_read

        duration = frame_count / sample_rate if sample_rate else 0
        if use_arrays:
            samples = np.concatenate(_sample_chunks) if _sample_chunks else np.asarray(samples, dtype=np.float64)
            left_samples = np.concatenate(_left_chunks) if _left_chunks else np.asarray(left_samples, dtype=np.float64)
            right_samples = np.concatenate(_right_chunks) if _right_chunks else np.asarray(right_samples, dtype=np.float64)
        result = {
            "samples": samples,
            "left_samples": left_samples,
            "right_samples": right_samples,
            "sample_rate": sample_rate,
            "analysis_sample_rate": sample_rate / step if step else sample_rate,
            "channels": channels,
            "duration_seconds": duration,
            "peak": peak,
            "left_peak": left_peak,
            "right_peak": right_peak,
            "true_rms": math.sqrt(rms_sum_sq / rms_sample_count) if rms_sample_count else 0.0,
            "clipped_frames_estimate": clipped_instances,
            "stereo_balance": round(left_total / right_total, 3) if right_total else 1.0,
        }
        if step2 > 0:
            # .tolist() to match the plain-list "samples" type a standalone
            # read_wav_mono(file_bytes, max_samples=preview_max_samples) call
            # returns (as_arrays defaults False on that call path) -- callers
            # consuming this preview shouldn't have to care which path produced it.
            preview = np.concatenate(_preview_chunks) if _preview_chunks else np.asarray([], dtype=np.float64)
            result["preview_samples"] = preview.tolist()
            # The NATIVE rate, matching "sample_rate" above -- NOT sample_rate/step2.
            # A standalone read_wav_mono(file_bytes, max_samples=preview_max_samples)
            # call's "sample_rate" key (what analyze_stems_masking actually reads as
            # `fs`) is always the native rate too, even though "samples" is decimated;
            # this must match that exactly for a caller to treat the two as equivalent.
            result["preview_sample_rate"] = sample_rate
        return result


def _write_wav_from_float_array(samples: "np.ndarray", sample_rate: int) -> bytes:
    if not NUMPY_AVAILABLE:
        raise ValueError("NumPy is required for decoded audio conversion.")
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim == 1:
        samples = samples.reshape(-1, 1)
    if samples.shape[1] > 2:
        samples = samples[:, :2]
    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(int(pcm.shape[1]))
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


def _decode_with_soundfile_bytes(file_bytes: bytes) -> tuple[bytes, str] | None:
    if not (SOUNDFILE_AVAILABLE and NUMPY_AVAILABLE):
        return None
    try:
        samples, sample_rate = sf.read(io.BytesIO(file_bytes), always_2d=True, dtype="float64")
        return _write_wav_from_float_array(samples, int(sample_rate)), "soundfile"
    except Exception:
        return None


def _decode_with_soundfile_path(path: Path) -> tuple[bytes, str] | None:
    if not (SOUNDFILE_AVAILABLE and NUMPY_AVAILABLE):
        return None
    try:
        samples, sample_rate = sf.read(str(path), always_2d=True, dtype="float64")
        return _write_wav_from_float_array(samples, int(sample_rate)), "soundfile"
    except Exception:
        return None


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or ""


def _decode_with_ffmpeg_path(path: Path) -> tuple[bytes, str] | None:
    binary = ffmpeg_path()
    if not binary:
        return None
    result = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-f",
            "wav",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout, "ffmpeg"


def _decode_with_ffmpeg_bytes(file_bytes: bytes, suffix: str) -> tuple[bytes, str] | None:
    binary = ffmpeg_path()
    if not binary:
        return None
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix or ".audio", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_name = tmp.name
        return _decode_with_ffmpeg_path(Path(tmp_name))
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass


def decode_audio_bytes(file_bytes: bytes, filename: str) -> dict:
    """Return WAV PCM bytes for supported audio formats."""
    suffix = Path(filename or "").suffix.lower()
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WAVE":
        return {"wav_bytes": file_bytes, "decoder": "wave", "source_format": suffix.lstrip(".") or "wav"}
    if suffix in WAV_SUFFIXES:
        return {"wav_bytes": file_bytes, "decoder": "wave", "source_format": suffix.lstrip(".") or "wav"}
    decoded = _decode_with_soundfile_bytes(file_bytes)
    if decoded is None:
        decoded = _decode_with_ffmpeg_bytes(file_bytes, suffix)
    if decoded is None:
        raise ValueError("Could not decode audio. Install soundfile/libsndfile or ffmpeg, or convert the file to WAV.")
    wav_bytes, decoder = decoded
    return {"wav_bytes": wav_bytes, "decoder": decoder, "source_format": suffix.lstrip(".") or "audio"}


def decode_audio_file(path: Path) -> dict:
    """Return WAV PCM bytes for a path without loading through upload validation."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in WAV_SUFFIXES:
        return {"wav_bytes": path.read_bytes(), "decoder": "wave", "source_format": suffix.lstrip(".") or "wav"}
    decoded = _decode_with_soundfile_path(path)
    if decoded is None:
        decoded = _decode_with_ffmpeg_path(path)
    if decoded is None:
        raise ValueError("Could not decode audio. Install soundfile/libsndfile or ffmpeg, or convert the file to WAV.")
    wav_bytes, decoder = decoded
    return {"wav_bytes": wav_bytes, "decoder": decoder, "source_format": suffix.lstrip(".") or "audio"}
