"""Stem pre-processing pipeline for the automated mixdown system.

Prepares raw stems for mixing by:
  - Removing DC offset
  - Trimming one shared session window while preserving relative timing
  - Validating and aligning sample rates
  - Zero-padding shorter stems to match the longest
  - Preserving source gain relationships by default
"""

from __future__ import annotations

import os
import struct
import wave
import io
from concurrent.futures import ThreadPoolExecutor

try:
    import numpy as np
    import scipy.signal as sig

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def _decode_worker_count(n_stems: int) -> int:
    """Threads for per-stem decode. Same convention as mix_renderer.py's
    _render_worker_count (default min(4, cores, stems)); a separate env var
    since decode (I/O + wave-module parsing) and render (DSP) have different
    optimal thread counts. Override with AUTOMIX_DECODE_WORKERS (=1 forces
    the sequential path)."""
    env = os.environ.get("AUTOMIX_DECODE_WORKERS")
    if env:
        try:
            return max(1, min(int(env), max(1, n_stems)))
        except ValueError:
            pass
    return max(1, min(4, os.cpu_count() or 1, max(1, n_stems)))


# ---------------------------------------------------------------------------
# Core pre-processing functions
# ---------------------------------------------------------------------------


def remove_dc_offset(samples: list[float]) -> list[float]:
    """Remove DC offset by subtracting the mean."""
    if len(samples) == 0:
        return samples
    if NUMPY_AVAILABLE:
        arr = np.asarray(samples, dtype=np.float64)
        return (arr - np.mean(arr)).tolist()
    mean = sum(samples) / len(samples)
    return [s - mean for s in samples]


def highpass_subsonic(samples: list[float], sample_rate: int,
                      cutoff_hz: float = 5.0, order: int = 2) -> list[float]:
    """Apply a subsonic high-pass filter to remove ultra-low-frequency rumble.

    Uses a Butterworth filter if scipy is available, otherwise falls back
    to simple DC offset removal.
    """
    if len(samples) == 0 or sample_rate <= 0:
        return samples

    if NUMPY_AVAILABLE:
        try:
            nyquist = sample_rate / 2.0
            if cutoff_hz >= nyquist:
                return samples
            sos = sig.butter(order, cutoff_hz / nyquist, btype="highpass", output="sos")
            arr = np.asarray(samples, dtype=np.float64)
            filtered = sig.sosfilt(sos, arr)
            # Return a numpy array (not .tolist()) so the prepare_stems decode ->
            # highpass -> resample -> mono-sum chain stays in arrays instead of
            # round-tripping through Python lists at every step (each .tolist()/
            # np.asarray on a full-length stem is ~0.4s and pure memory churn).
            return filtered
        except Exception:
            pass

    # Fallback: simple DC removal
    return remove_dc_offset(samples)


def trim_silence(samples: list[float], sample_rate: int,
                 threshold_db: float = -60.0, keep_ms: float = 10.0) -> list[float]:
    """Trim silence from head and tail, keeping a small buffer.

    Parameters
    ----------
    threshold_db : float
        Amplitude threshold below which is considered silence.
    keep_ms : float
        Milliseconds of silence to retain at each end for smooth transitions.
    """
    if len(samples) == 0 or sample_rate <= 0:
        return samples

    threshold_linear = 10.0 ** (threshold_db / 20.0)
    keep_samples = max(0, int(sample_rate * keep_ms / 1000.0))

    # Find first non-silent sample
    head = 0
    for i, s in enumerate(samples):
        if abs(s) > threshold_linear:
            head = i
            break
    else:
        # Entire signal is silence
        return samples[:keep_samples] if keep_samples < len(samples) else samples

    # Find last non-silent sample
    tail = len(samples) - 1
    for i in range(len(samples) - 1, -1, -1):
        if abs(samples[i]) > threshold_linear:
            tail = i
            break

    # Apply buffer
    start = max(0, head - keep_samples)
    end = min(len(samples), tail + keep_samples + 1)
    return samples[start:end]


def trim_stems_preserving_alignment(
    stems_samples: list[list[float]],
    sample_rate: int,
    *,
    threshold_db: float = -60.0,
    keep_ms: float = 10.0,
) -> tuple[list[list[float]], int, int]:
    """Crop a shared silent head/tail without moving stems relative to each other.

    Independent stem trimming changes musical entrances and can destroy phase
    relationships. This function finds the union of audible activity across the
    whole session and applies the exact same slice to every already-aligned stem.
    It returns ``(trimmed_stems, start_sample, end_sample)``; ``end_sample`` is
    exclusive and expressed in the original aligned session timeline.
    """
    if not stems_samples or sample_rate <= 0:
        return stems_samples, 0, max((len(samples) for samples in stems_samples), default=0)

    aligned = align_lengths(stems_samples)
    session_length = len(aligned[0]) if aligned else 0
    threshold_linear = 10.0 ** (threshold_db / 20.0)
    keep_samples = max(0, int(sample_rate * keep_ms / 1000.0))
    first_active = session_length
    last_active = -1

    if NUMPY_AVAILABLE:
        # Vectorized active-sample detection — the per-sample Python loop over
        # every sample of every stem was the super-linear cost that dominated
        # prepare_stems on long sessions. Same first/last audible index.
        for samples in aligned:
            active = np.nonzero(np.abs(np.asarray(samples)) > threshold_linear)[0]
            if active.size:
                first_active = min(first_active, int(active[0]))
                last_active = max(last_active, int(active[-1]))
    else:
        for samples in aligned:
            for index, sample in enumerate(samples):
                if abs(sample) > threshold_linear:
                    first_active = min(first_active, index)
                    break
            for index in range(len(samples) - 1, -1, -1):
                if abs(samples[index]) > threshold_linear:
                    last_active = max(last_active, index)
                    break

    if last_active < 0:
        # Preserve an all-silent session rather than manufacturing a tiny stem.
        return aligned, 0, session_length

    start = max(0, first_active - keep_samples)
    end = min(session_length, last_active + keep_samples + 1)
    return [samples[start:end] for samples in aligned], start, end


def validate_sample_rate(stems_data: list[dict], target_rate: int | None = None) -> int:
    """Determine the target sample rate for a set of stems.

    If *target_rate* is given, use that.  Otherwise pick the most common
    rate among the stems.  Returns the chosen target rate.
    """
    if target_rate:
        return target_rate

    rates: dict[int, int] = {}
    for stem in stems_data:
        sr = stem.get("sample_rate", 44100)
        rates[sr] = rates.get(sr, 0) + 1

    if not rates:
        return 44100

    # Most common rate wins
    return max(rates, key=rates.get)  # type: ignore[arg-type]


def resample(samples: list[float], original_rate: int, target_rate: int) -> list[float]:
    """Resample audio to a different sample rate using sinc interpolation.

    Falls back to linear interpolation if scipy is unavailable.
    """
    if original_rate == target_rate or len(samples) == 0:
        return samples

    if NUMPY_AVAILABLE:
        try:
            arr = np.asarray(samples, dtype=np.float64)
            # Compute GCD for rational resampling
            from math import gcd
            g = gcd(target_rate, original_rate)
            up = target_rate // g
            down = original_rate // g
            # Limit polyphase factor to prevent memory issues
            if up > 256 or down > 256:
                # Fall back to scipy.signal.resample for arbitrary ratios
                target_len = int(len(samples) * target_rate / original_rate)
                resampled = sig.resample(arr, target_len)
                return resampled
            resampled = sig.resample_poly(arr, up, down)
            # Return an array (not .tolist()) — keeps the prepare_stems chain in
            # numpy; downstream np.asarray on an array is a no-op.
            return resampled
        except Exception:
            pass

    # Fallback: linear interpolation
    ratio = target_rate / original_rate
    target_len = int(len(samples) * ratio)
    result: list[float] = []
    for i in range(target_len):
        src_pos = i / ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(samples):
            result.append(samples[idx] * (1.0 - frac) + samples[idx + 1] * frac)
        elif idx < len(samples):
            result.append(samples[idx])
        else:
            result.append(0.0)
    return result


def align_lengths(stems_samples):
    """Zero-pad all stems to match the length of the longest stem.

    Returns numpy float64 arrays when numpy is available (bit-identical
    zero-padding, but far less memory/time than list concatenation on
    full-length, many-stem sessions — the dominant prepare_stems cost).
    """
    if not stems_samples:
        return stems_samples
    if NUMPY_AVAILABLE:
        arrs = [np.asarray(s, dtype=np.float64) for s in stems_samples]
        max_len = max((a.shape[0] for a in arrs), default=0)
        result = []
        for a in arrs:
            if a.shape[0] < max_len:
                a = np.concatenate([a, np.zeros(max_len - a.shape[0], dtype=np.float64)])
            result.append(a)
        return result
    max_len = max(len(s) for s in stems_samples)
    result = []
    for samples in stems_samples:
        if len(samples) < max_len:
            result.append(samples + [0.0] * (max_len - len(samples)))
        else:
            result.append(samples)
    return result


def peak_normalise(samples: list[float], target_dbfs: float = -1.0) -> list[float]:
    """Normalise samples so the peak level matches *target_dbfs*.

    Parameters
    ----------
    target_dbfs : float
        Target peak level in dBFS.  Default is -1.0 dBFS.
    """
    if len(samples) == 0:
        return samples

    if NUMPY_AVAILABLE:
        arr = np.asarray(samples, dtype=np.float64)
        peak = float(np.max(np.abs(arr)))
        if peak < 1e-12:
            return samples  # silence — don't amplify noise
        gain = 10.0 ** (target_dbfs / 20.0) / peak
        return arr * gain

    peak = max(abs(s) for s in samples)
    if peak < 1e-12:
        return samples
    gain = 10.0 ** (target_dbfs / 20.0) / peak
    return [s * gain for s in samples]


# ---------------------------------------------------------------------------
# Stereo stem handling
# ---------------------------------------------------------------------------


def read_wav_stereo(file_bytes: bytes, *, max_samples: int = 0) -> dict:
    """Read a WAV file and return separate left/right channels.

    Returns a dict with keys:
      - "left": list[float]   (normalised to [-1.0, 1.0])
      - "right": list[float]  (normalised to [-1.0, 1.0], or same as left if mono)
      - "sample_rate": int
      - "channels": int
      - "bit_depth": int
      - "duration_seconds": float
    """
    with wave.open(io.BytesIO(file_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        raw = wav.readframes(frame_count)

    max_int = float((1 << (sample_width * 8 - 1)) - 1) if sample_width > 1 else 127.0

    if NUMPY_AVAILABLE:
        if sample_width == 2:
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / max_int
        elif sample_width == 3:
            n_samples = len(raw) // 3
            temp = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
            padded = np.zeros((n_samples, 4), dtype=np.uint8)
            padded[:, :3] = temp
            sign_mask = temp[:, 2] & 0x80
            padded[sign_mask != 0, 3] = 0xFF
            data = padded.view(np.int32).flatten().astype(np.float64) / 8388607.0
        elif sample_width == 4:
            data = np.frombuffer(raw, dtype=np.int32).astype(np.float64) / max_int
        elif sample_width == 1:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 127.0
        else:
            data = np.zeros(frame_count * channels, dtype=np.float64)

        if max_samples > 0 and len(data) > max_samples * channels:
            data = data[: max_samples * channels]

        if channels >= 2:
            left = data[0::channels].tolist()
            right = data[1::channels].tolist()
        else:
            left = data.tolist()
            right = left[:]
    else:
        # Pure-Python fallback
        left: list[float] = []
        right: list[float] = []
        frame_size = channels * sample_width
        for i in range(frame_count):
            if max_samples > 0 and i >= max_samples:
                break
            offset = i * frame_size
            if offset + frame_size > len(raw):
                break
            l_raw = raw[offset: offset + sample_width]
            l_val = _pcm_to_float(l_raw, sample_width, max_int)
            left.append(l_val)
            if channels >= 2:
                r_raw = raw[offset + sample_width: offset + 2 * sample_width]
                right.append(_pcm_to_float(r_raw, sample_width, max_int))
            else:
                right.append(l_val)

    actual_len = min(len(left), len(right))
    return {
        "left": left[:actual_len],
        "right": right[:actual_len],
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": sample_width * 8,
        "duration_seconds": frame_count / max(sample_rate, 1),
    }


def _pcm_to_float(raw_bytes: bytes, sample_width: int, max_int: float) -> float:
    """Convert raw PCM bytes to a normalised float."""
    if sample_width == 1:
        return (raw_bytes[0] - 128) / 127.0
    if sample_width == 2:
        return int.from_bytes(raw_bytes, "little", signed=True) / max_int
    if sample_width == 3:
        val = int.from_bytes(raw_bytes + (b"\xff" if raw_bytes[-1] & 0x80 else b"\x00"),
                             "little", signed=True)
        return val / 8388607.0
    if sample_width == 4:
        return int.from_bytes(raw_bytes, "little", signed=True) / max_int
    return 0.0


def write_wav(left: list[float], right: list[float], sample_rate: int,
              bit_depth: int = 24) -> bytes:
    """Render stereo float samples to WAV bytes.

    Parameters
    ----------
    left, right : list[float]
        Normalised samples in [-1.0, 1.0].
    sample_rate : int
        Output sample rate.
    bit_depth : int
        Output bit depth (16 or 24).

    Returns
    -------
    bytes
        Complete WAV file as bytes.
    """
    channels = 2
    sample_width = bit_depth // 8
    if sample_width not in (2, 3):
        sample_width = 3  # default to 24-bit

    max_int = (1 << (bit_depth - 1)) - 1
    frame_count = min(len(left), len(right))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)

        if NUMPY_AVAILABLE and frame_count > 0:
            # Vectorized encode — bit-identical to the per-sample loop below but
            # ~100x+ faster (the loop's per-sample int()/to_bytes()/struct.pack
            # was ~17s of a full-length render, and scales with duration).
            # int() truncates toward zero; np.astype(int32) from float does too,
            # so the sample values match exactly.
            left_c = np.clip(np.asarray(left[:frame_count], dtype=np.float64), -1.0, 1.0)
            right_c = np.clip(np.asarray(right[:frame_count], dtype=np.float64), -1.0, 1.0)
            inter = np.empty(frame_count * 2, dtype=np.int32)
            inter[0::2] = (left_c * max_int).astype(np.int32)
            inter[1::2] = (right_c * max_int).astype(np.int32)
            if sample_width == 2:
                frames = inter.astype("<i2").tobytes()
            else:  # 24-bit: little-endian signed, low 3 bytes of int32
                le = inter.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]
                frames = np.ascontiguousarray(le).tobytes()
            wav.writeframes(frames)
        else:
            # Pure-Python fallback (numpy unavailable). Chunked to manage memory.
            chunk_size = 8192
            for start in range(0, frame_count, chunk_size):
                end = min(start + chunk_size, frame_count)
                raw = bytearray()
                for i in range(start, end):
                    l_val = max(-1.0, min(1.0, left[i]))
                    r_val = max(-1.0, min(1.0, right[i]))
                    l_int = int(l_val * max_int)
                    r_int = int(r_val * max_int)
                    if sample_width == 2:
                        raw += struct.pack("<hh", l_int, r_int)
                    elif sample_width == 3:
                        raw += l_int.to_bytes(3, "little", signed=True)
                        raw += r_int.to_bytes(3, "little", signed=True)
                wav.writeframes(bytes(raw))

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Full preparation pipeline
# ---------------------------------------------------------------------------


def prepare_stems(
    stems: list[dict],
    *,
    read_wav_mono_fn,
    target_sample_rate: int | None = None,
    trim: bool = True,
    normalise: bool = False,
    target_peak_dbfs: float = -1.0,
    max_samples: int = 0,
    masking_preview_max_samples: int = 0,
) -> list[dict]:
    """Run the full stem preparation pipeline.

    Parameters
    ----------
    stems : list[dict]
        Each dict has ``"name"`` and ``"file_bytes"``.
    read_wav_mono_fn : callable
        ``(file_bytes, max_samples=N) -> dict`` with ``"samples"`` and
        ``"sample_rate"`` keys.
    target_sample_rate : int, optional
        Force a specific sample rate.  If *None*, the most common rate among
        the stems is used.
    trim : bool
        Whether to trim silence at head/tail.
    normalise : bool
        Whether to peak-normalise each stem. Disabled by default because independent
        normalisation erases rough-mix balance and invalidates gain decisions measured
        from the original source. Enable only for an explicit analysis workflow.
    target_peak_dbfs : float
        Target peak level when normalising.
    max_samples : int
        Maximum samples to read per stem (0 = unlimited).
    masking_preview_max_samples : int
        When > 0, ALSO decode a decimated preview per stem (same algorithm
        analyze_stems_masking's own independent decode uses) from the SAME
        read_wav_mono_fn call used for the full-rate decode above, instead of
        a second WAV parse. Pass 65536 to match analyze_stems_masking's
        hardcoded preview size and let a caller that runs both stages reuse
        this decode -- see that function's ``masking_preview_samples``
        stem-dict lookup. 0 (default) adds no extra work and no new keys.

    Returns
    -------
    list[dict]
        Each dict contains:
          - ``"name"``
          - ``"samples"``  (prepared mono analysis proxy)
          - ``"left_samples"`` / ``"right_samples"`` for preserved stereo sources
          - ``"sample_rate"``
          - ``"original_sample_rate"``
          - ``"masking_preview_samples"`` / ``"masking_preview_sample_rate"``
            (only when masking_preview_max_samples > 0)
          - ``"original_duration_seconds"``
    """
    # Step 1: Read all stems. Each stem's decode is independent (pure function
    # of its own file_bytes), so this is parallelized across a thread pool --
    # same pattern and rationale as mix_renderer.py's per-stem render loop:
    # the actual decode work (numpy chunk accumulation in read_wav_mono, and
    # any underlying C-level WAV/format parsing) releases the GIL, and
    # results are collected via map() which preserves input order, so output
    # is bit-identical to the sequential loop -- just not serialized on I/O.
    def _decode_one(stem: dict) -> dict:
        name = stem.get("name", "unknown.wav")
        file_bytes = stem.get("file_bytes", b"")
        try:
            # Always forward zero: read_wav_mono's own default is a bounded
            # analysis preview, while preparation requires full-rate audio.
            # as_arrays=True asks the decoder for numpy arrays instead of Python
            # lists (opt-in on read_wav_mono; ~4x less memory and no per-chunk
            # tolist()/extend() churn -- this decode step was the majority of
            # prepare_stems' cost on long sessions, see
            # docs/audits/2026-07-16-detect-correct-and-perf.md). Guarded in case
            # a caller ever injects a custom read_wav_mono_fn that predates the
            # parameter.
            kwargs = {"max_samples": max_samples, "as_arrays": True}
            if masking_preview_max_samples > 0:
                kwargs["preview_max_samples"] = masking_preview_max_samples
            try:
                wav_data = read_wav_mono_fn(file_bytes, **kwargs)
            except TypeError:
                wav_data = read_wav_mono_fn(file_bytes, max_samples=max_samples)
            samples = wav_data.get("samples", [])
            sr = wav_data.get("sample_rate", 44100)
            channels = int(wav_data.get("channels", 1))
            left = wav_data.get("left_samples", [])
            right = wav_data.get("right_samples", [])
            preview_samples = wav_data.get("preview_samples")
            preview_sample_rate = wav_data.get("preview_sample_rate")
        except Exception as exc:
            # Fail loudly: a stem that cannot be decoded must not become a silent
            # empty stem that crashes cryptically several stages later (e.g. the
            # multiband compressor's filtfilt). Name the file and the real cause.
            raise ValueError(f"Could not read audio stem '{name}': {exc}") from exc
        if len(samples) == 0:
            raise ValueError(
                f"Audio stem '{name}' decoded to zero samples (empty, silent, or corrupt file)."
            )
        return {
            "name": name,
            "samples": samples,
            "sample_rate": sr,
            "original_duration_seconds": len(samples) / max(sr, 1),
            "source_channels": channels,
            "left_samples": left if channels >= 2 and len(left) == len(samples) else [],
            "right_samples": right if channels >= 2 and len(right) == len(samples) else [],
            "masking_preview_samples": preview_samples,
            "masking_preview_sample_rate": preview_sample_rate,
        }

    _n_decode_workers = _decode_worker_count(len(stems))
    if _n_decode_workers > 1:
        with ThreadPoolExecutor(max_workers=_n_decode_workers) as _ex:
            raw_stems: list[dict] = list(_ex.map(_decode_one, stems))
    else:
        raw_stems = [_decode_one(stem) for stem in stems]

    # Step 2: Determine target sample rate
    target_sr = validate_sample_rate(raw_stems, target_sample_rate)

    # Step 3: Process each stem. Free each raw (decoded) stem the moment it has
    # been consumed into `prepared` -- raw_stems otherwise stays alive through the
    # memory-heavy alignment/trim below (step 4 only reads `prepared`), so the raw
    # and prepared copies coexist and roughly double peak RAM. Each stem is
    # processed independently and the outputs are freshly computed arrays, so this
    # is bit-identical; it just doesn't hold the source audio longer than needed.
    def _prep_one_stem(stem_data: dict) -> dict:
        samples = stem_data["samples"]
        orig_sr = stem_data["sample_rate"]
        preserve_stereo = len(stem_data["left_samples"]) > 0 and len(stem_data["right_samples"]) > 0

        # DC removal + subsonic filter
        if preserve_stereo:
            left = highpass_subsonic(stem_data["left_samples"], orig_sr, cutoff_hz=5.0)
            right = highpass_subsonic(stem_data["right_samples"], orig_sr, cutoff_hz=5.0)
        else:
            samples = highpass_subsonic(samples, orig_sr, cutoff_hz=5.0)

        # Resample if needed
        if orig_sr != target_sr:
            if preserve_stereo:
                left = resample(left, orig_sr, target_sr)
                right = resample(right, orig_sr, target_sr)
            else:
                samples = resample(samples, orig_sr, target_sr)
        if preserve_stereo:
            channel_length = min(len(left), len(right))
            left = left[:channel_length]
            right = right[:channel_length]
            samples = (np.asarray(left, dtype=np.float64) + np.asarray(right, dtype=np.float64)) * 0.5

        return {
            "name": stem_data["name"],
            "samples": samples,
            "sample_rate": target_sr,
            "original_sample_rate": orig_sr,
            "original_duration_seconds": stem_data["original_duration_seconds"],
            "source_channels": stem_data["source_channels"],
            "channel_layout": "stereo" if preserve_stereo else "mono",
            "stereo_preserved": preserve_stereo,
            "left_samples": left if preserve_stereo else [],
            "right_samples": right if preserve_stereo else [],
            "masking_preview_samples": stem_data.get("masking_preview_samples"),
            "masking_preview_sample_rate": stem_data.get("masking_preview_sample_rate"),
        }

    if _n_decode_workers > 1:
        with ThreadPoolExecutor(max_workers=_n_decode_workers) as _ex:
            prepared = list(_ex.map(_prep_one_stem, raw_stems))
    else:
        prepared = [_prep_one_stem(sd) for sd in raw_stems]
    raw_stems = []  # free raw decoded list

    # Step 4: Align first, then crop one shared session window. Trimming stems
    # independently would erase their relative entrances and break phase timing.
    all_samples = [
        np.maximum(
            np.abs(np.asarray(p["left_samples"], dtype=np.float64)),
            np.abs(np.asarray(p["right_samples"], dtype=np.float64)),
        )
        if p["stereo_preserved"] else np.asarray(p["samples"], dtype=np.float64)
        for p in prepared
    ]
    aligned = align_lengths(all_samples)
    aligned_session_length = len(aligned[0]) if aligned else 0
    trim_start = 0
    trim_end = len(aligned[0]) if aligned else 0
    if trim:
        aligned, trim_start, trim_end = trim_stems_preserving_alignment(
            aligned, target_sr
        )
    # Store the final sample fields as float64 numpy arrays rather than Python
    # lists. Bit-identical to the list path (same values, same float64 math) but
    # ~4x less memory (a list[float] of 9M samples is ~290 MB vs ~72 MB as an
    # array) and it removes the list<->array churn that inflated peak memory on
    # long, many-stem sessions to the point of swap-thrashing. These arrays live
    # for the whole render (the memory-peak phase); the renderer already does
    # np.asarray() on them, so an array is a no-op there instead of a re-alloc.
    for i, p in enumerate(prepared):
        target_length = aligned_session_length
        if p["stereo_preserved"]:
            left = np.asarray(p["left_samples"], dtype=np.float64)
            right = np.asarray(p["right_samples"], dtype=np.float64)
            if left.shape[0] < target_length:
                left = np.concatenate([left, np.zeros(target_length - left.shape[0], dtype=np.float64)])
            if right.shape[0] < target_length:
                right = np.concatenate([right, np.zeros(target_length - right.shape[0], dtype=np.float64)])
            left = left[trim_start:trim_end]
            right = right[trim_start:trim_end]
            if normalise:
                peak = max(
                    float(np.max(np.abs(left))) if left.size else 0.0,
                    float(np.max(np.abs(right))) if right.size else 0.0,
                )
                if peak >= 1e-12:
                    gain = 10.0 ** (target_peak_dbfs / 20.0) / peak
                    left = left * gain
                    right = right * gain
            p["left_samples"] = left
            p["right_samples"] = right
            p["samples"] = (left + right) * 0.5
        else:
            samples = aligned[i]
            if normalise:
                samples = peak_normalise(samples, target_peak_dbfs)
            p["samples"] = np.asarray(samples, dtype=np.float64)
        p["session_trim_start_samples"] = trim_start
        p["session_trim_end_samples"] = trim_end
        p["session_trim_start_seconds"] = trim_start / max(target_sr, 1)

    return prepared
