from __future__ import annotations
import math
from typing import Callable
from email import policy
from email.parser import BytesParser

from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes
from audio_analysis.analysis_core.analysis_features import rms_db
from audio_analysis.analysis_core.erb_masking import (
    get_erb_bands,
    compute_erb_profile,
    compute_combined_masking_threshold,
    calculate_visibility,
)

def _correlation(v1: list[float], v2: list[float]) -> float:
    n = len(v1)
    if n <= 1:
        return 0.0
    if len(set(v1)) <= 1 or len(set(v2)) <= 1:
        return 1.0
    mean1 = sum(v1) / n
    mean2 = sum(v2) / n
    
    diff1 = [x - mean1 for x in v1]
    diff2 = [x - mean2 for x in v2]
    
    num = sum(d1 * d2 for d1, d2 in zip(diff1, diff2))
    den1 = sum(d * d for d in diff1)
    den2 = sum(d * d for d in diff2)
    
    if den1 <= 1e-9 or den2 <= 1e-9:
        return 0.0
    return num / math.sqrt(den1 * den2)

def analyze_stems_masking(stems: list[dict], *, read_wav_mono: Callable, spectral_bands: Callable) -> dict:
    """Return relative ERB previews only for actually co-active decoded frames.

    Preview frames share the upload origin; differing effective sample rates
    cannot be compared without resampling. Activity gates publication, not
    psychoacoustic severity, and the existing ERB model remains uncalibrated.
    """
    bands_keys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"]
    erb_bands = get_erb_bands(num_bands=40)
    frame_size = 4096  # Samples per complete preview frame; no padded or repeated tails.
    max_frames = 16  # Preview budget, not an assertion that all uploads contain 16 frames.
    active_floor_dbfs = -60.0  # Existing upload publication floor, before spectral normalization.
    results = []
    sources = []
    abstentions = []
    names = [str(stem.get("name", "")).rsplit(".", 1)[0] for stem in stems]
    for stem, name in zip(stems, names):
        if not name or names.count(name) != 1:
            # Ambiguous identities cannot support a pair, but do not invalidate other uploads.
            abstentions.append({"name": name, "reason": "Missing or duplicate stem identity."})
            continue
        try:
            # Older piggyback previews label decimated samples with their native rate.
            # Re-decode those rather than manufacture a common time/frequency basis.
            if stem.get("masking_preview_samples") is not None and stem.get("masking_preview_analysis_sample_rate") is not None:
                samples = stem["masking_preview_samples"]
                fs = stem["masking_preview_analysis_sample_rate"]
            else:
                wav_data = read_wav_mono(stem.get("file_bytes", b""), max_samples=frame_size * max_frames)
                samples = wav_data.get("samples", [])
                fs = wav_data.get("analysis_sample_rate", wav_data.get("sample_rate"))
            if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not math.isfinite(fs) or fs <= 0:
                raise ValueError("Missing finite effective sample rate.")
            preview = [float(value) for value in samples[:frame_size * max_frames]]
            if any(not math.isfinite(value) for value in preview):
                raise ValueError("Preview has non-finite decoded samples.")
            frame_count = len(preview) // frame_size
            frames = []
            for frame_index in range(frame_count):
                frame = preview[frame_index * frame_size:(frame_index + 1) * frame_size]
                frame_rms_dbfs = rms_db(frame)
                if not math.isfinite(frame_rms_dbfs):
                    # Overflow cannot establish valid raw-level evidence for normalized spectra.
                    raise ValueError("Preview RMS is non-finite.")
                active = frame_rms_dbfs > active_floor_dbfs
                if not active:
                    # Quiet frames retain their timeline slot but contribute no normalized spectrum.
                    frames.append(None)
                    continue
                fb = spectral_bands(frame, fs, size=frame_size)
                band_values = {key: float(fb.get(key, 0.0)) for key in bands_keys}
                mags, fft_size = spectrum_magnitudes(frame, fs, size=frame_size)
                erb_profile = compute_erb_profile(mags, fs, fft_size, num_bands=40)
                if any(not math.isfinite(value) or value < 0 for value in [*band_values.values(), *erb_profile]):
                    raise ValueError("Preview spectrum is not finite non-negative energy.")
                frames.append({"bands": band_values, "erb_profile": erb_profile})
            active_count = sum(frame is not None for frame in frames)
            sources.append({"name": name, "sample_rate": float(fs), "frame_count": frame_count, "active_frame_count": active_count})
            results.append({"name": name, "sample_rate": fs, "frames": frames})
            if not active_count:
                # Names remain visible as abstentions; silence is not measured masking.
                abstentions.append({"name": name, "reason": "No complete preview frame exceeds -60 dBFS RMS."})
        except Exception:
            # A failed decode/measurement has no spectral substitute; names never manufacture evidence.
            abstentions.append({"name": name, "reason": "Decoded preview or effective sample rate is unavailable or invalid."})

    pairs = []
    pair_frames = {}
    for index, first in enumerate(results):
        for second in results[index + 1:]:
            if first["sample_rate"] != second["sample_rate"]:
                # Equal frame numbers represent different times at different effective sample rates.
                continue
            shared = [frame_index for frame_index, (left, right) in enumerate(zip(first["frames"], second["frames"])) if left is not None and right is not None]
            if shared:
                pair_frames[(first["name"], second["name"])] = shared
                pairs.append({"stems": [first["name"], second["name"]], "simultaneously_active_frame_count": len(shared)})
    qualified_names = {name for pair in pairs for name in pair["stems"]}
    for result in results:
        if result["name"] not in qualified_names and any(frame is not None for frame in result["frames"]):
            # An active solo source still cannot establish a simultaneous masking comparison.
            abstentions.append({"name": result["name"], "reason": "No co-active complete frame at a shared effective sample rate."})
    results = [result for result in results if result["name"] in qualified_names]
    matrix = {result["name"]: {result["name"]: 1.0} for result in results}
    heatmap = {result["name"]: {result["name"]: [1.0] * len(erb_bands)} for result in results}
    for first in results:
        name = first["name"]
        visible = []
        joint_frames = []
        for frame_index, frame in enumerate(first["frames"]):
            others = [other["frames"][frame_index]["erb_profile"] for other in results
                      if other["name"] != name and other["sample_rate"] == first["sample_rate"]
                      and frame_index < len(other["frames"]) and other["frames"][frame_index] is not None]
            if frame is None or not others:
                # Do not describe solo or missing tails as compared audio.
                continue
            threshold = compute_combined_masking_threshold(others, erb_bands)
            visible.append(calculate_visibility(frame["erb_profile"], threshold))
            joint_frames.append(frame)
        total_bands = {key: sum(frame["bands"][key] for frame in joint_frames) for key in bands_keys}
        total = sum(total_bands.values())
        # An active frame can lie outside these seven bands; zero band energy
        # stays zero rather than inventing a normalized frequency profile.
        first["bands"] = {key: value / total if total else 0.0 for key, value in total_bands.items()}
        first["overall_visibility"] = round(sum(value for value, _ in visible) / len(visible), 3)
        first["visibility_per_band"] = [round(sum(values[index] for _, values in visible) / len(visible), 3) for index in range(len(erb_bands))]
        for second in results:
            other_name = second["name"]
            if name == other_name:
                # The diagonal is an identity marker, never a measured conflict.
                continue
            shared = pair_frames.get((name, other_name), pair_frames.get((other_name, name), []))
            if not shared:
                # Omit unknown pairs instead of publishing zero as a measured clearance.
                continue
            index_sum = 0.0
            for key in bands_keys:
                left = [first["frames"][index]["bands"][key] for index in shared]
                right = [second["frames"][index]["bands"][key] for index in shared]
                left_total = sum(sum(first["frames"][index]["bands"].values()) for index in shared)
                right_total = sum(sum(second["frames"][index]["bands"].values()) for index in shared)
                overlap = min(sum(left) / left_total if left_total else 0.0, sum(right) / right_total if right_total else 0.0)
                index_sum += max(0.0, _correlation(left, right)) * overlap
            matrix[name][other_name] = round(min(1.0, index_sum), 3)
            band_masking = []
            for band in range(len(erb_bands)):
                fractions = []
                for index in shared:
                    left = first["frames"][index]["erb_profile"][band]
                    right = second["frames"][index]["erb_profile"][band]
                    # Preserve the ERB model's 1e-15 energy floor; numerical
                    # residue in an empty band must not become full overlap.
                    fractions.append(left / (left + right) if left + right > 1e-15 else 0.0)
                band_masking.append(round(sum(fractions) / len(shared), 3))
            heatmap[name][other_name] = band_masking

    return {
        "stems": [{key: result[key] for key in ("name", "bands", "overall_visibility", "visibility_per_band")} for result in results],
        "masking_matrix": matrix,
        "erb_details": {
            "erb_frequencies": [round(fc, 1) for fc, _, _ in erb_bands],
            "heatmap": heatmap,
            # Relative preview spectra do not qualify calibrated EQ repairs or predicted gains.
            "carving_suggestions": [],
            "clarity_improvement": {},
        },
        "activity": {"schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": active_floor_dbfs,
                     "frame_size_samples": frame_size, "sources": sources, "pairs": pairs},
        "abstentions": abstentions,
        "limitations": ["Relative ERB preview candidate only; no calibrated masking severity, EQ repair, or predicted clarity improvement. Bounded decimated previews compare only matching effective sample rates and upload origins."],
    }

def handle_stems_upload(content_type: str, body: bytes, *, analyze_stems_masking: Callable) -> dict:
    try:
        if "multipart/form-data" not in content_type.lower():
            return {"ok": False, "error": "Expected multipart form upload."}

        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8", errors="replace") + b"\r\n\r\n" + body
        )

        stems = []
        for part in message.iter_parts():
            if part.is_multipart():
                continue
            name = part.get_param("name", header="content-disposition")
            if name != "files":
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename and payload:
                stems.append({
                    "name": filename,
                    "file_bytes": payload
                })

        if not stems:
            return {"ok": False, "error": "No stems uploaded."}

        result = analyze_stems_masking(stems)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
