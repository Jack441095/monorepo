from __future__ import annotations
import math
from typing import Callable
from email import policy
from email.parser import BytesParser

from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes
from audio_analysis.analysis_core.erb_masking import (
    get_erb_bands,
    compute_erb_profile,
    compute_combined_masking_threshold,
    calculate_visibility,
    generate_carving_suggestions,
    simulate_clarity_improvement
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
    results = []
    bands_keys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"]
    erb_bands = get_erb_bands(num_bands=40)
    
    # We will analyze up to 16 frames of size 4096 samples (approx 1.5 seconds of audio)
    frame_size = 4096
    num_frames = 16
    max_samples = frame_size * num_frames # 65536

    for stem in stems:
        name = stem["name"]
        # Only needed on the fallback (re-decode) path below -- a stem dict
        # that already carries a precomputed preview (see below) need not
        # supply file_bytes at all.
        file_bytes = stem.get("file_bytes", b"")
        
        # Default fallback profiles in case reading fails
        name_lower = name.lower()
        if "kick" in name_lower or "sub" in name_lower:
            default_bands = {"sub": 0.50, "bass": 0.35, "low_mids": 0.10, "mids": 0.03, "presence": 0.01, "sibilance": 0.005, "air": 0.005}
        elif "drum" in name_lower or "beat" in name_lower or "perc" in name_lower:
            default_bands = {"sub": 0.20, "bass": 0.30, "low_mids": 0.20, "mids": 0.15, "presence": 0.10, "sibilance": 0.03, "air": 0.02}
        elif "bass" in name_lower:
            default_bands = {"sub": 0.30, "bass": 0.45, "low_mids": 0.18, "mids": 0.05, "presence": 0.01, "sibilance": 0.005, "air": 0.005}
        elif "vocal" in name_lower or "voice" in name_lower or "vox" in name_lower:
            default_bands = {"sub": 0.01, "bass": 0.05, "low_mids": 0.20, "mids": 0.40, "presence": 0.25, "sibilance": 0.06, "air": 0.03}
        elif "synth" in name_lower or "pad" in name_lower or "guitar" in name_lower or "key" in name_lower or "inst" in name_lower:
            default_bands = {"sub": 0.02, "bass": 0.10, "low_mids": 0.30, "mids": 0.35, "presence": 0.15, "sibilance": 0.05, "air": 0.03}
        else:
            default_bands = {"sub": 0.14, "bass": 0.20, "low_mids": 0.20, "mids": 0.20, "presence": 0.14, "sibilance": 0.06, "air": 0.06}
            
        time_series: dict[str, list[float]] = {k: [] for k in bands_keys}
        average_bands = {k: 0.0 for k in bands_keys}
        erb_profiles = []
        average_erb = [0.0] * 40
        
        try:
            # If the caller already ran prepare_stems with
            # masking_preview_max_samples=max_samples on this same stem (see
            # that function's docstring), reuse its piggybacked preview
            # instead of re-parsing file_bytes a second time -- same
            # algorithm, verified bit-identical (tests/audio_analysis/
            # test_stem_analysis_masking_preview.py). Falls back to an
            # independent decode when no precomputed preview is attached
            # (e.g. this stem dict came straight from raw upload bytes).
            precomputed_samples = stem.get("masking_preview_samples")
            if precomputed_samples is not None:
                samples = precomputed_samples
                fs = stem.get("masking_preview_sample_rate") or 44100
            else:
                wav_data = read_wav_mono(file_bytes, max_samples=max_samples)
                samples = wav_data.get("samples", [])
                fs = wav_data.get("sample_rate", 44100)
            
            if len(samples) >= frame_size:
                # Divide samples into frames and analyze envelopes
                for f in range(num_frames):
                    start = f * frame_size
                    end = start + frame_size
                    if end <= len(samples):
                        frame_samples = samples[start:end]
                        fb = spectral_bands(frame_samples, fs, size=frame_size)
                        for k in bands_keys:
                            val = float(fb.get(k, 0.0))
                            time_series[k].append(val)
                            average_bands[k] += val
                            
                        # ERB Profile
                        mags, n = spectrum_magnitudes(frame_samples, fs, size=frame_size)
                        erb_prof = compute_erb_profile(mags, fs, n, num_bands=40)
                        erb_profiles.append(erb_prof)
                        for b_idx in range(40):
                            average_erb[b_idx] += erb_prof[b_idx]
                            
                # Normalize average bands
                total = sum(average_bands.values()) or 1.0
                average_bands = {k: v / total for k, v in average_bands.items()}
                
                # Normalize ERB
                total_erb = sum(average_erb) or 1.0
                average_erb = [v / total_erb for v in average_erb]
            else:
                # Fallback to single pass
                fb = spectral_bands(samples, fs, size=min(4096, len(samples))) if samples else {}
                average_bands = {k: float(fb.get(k, default_bands[k])) for k in bands_keys}
                total = sum(average_bands.values()) or 1.0
                average_bands = {k: v / total for k, v in average_bands.items()}
                # Duplicate time series for fallback
                for k in bands_keys:
                    time_series[k] = [average_bands[k]] * num_frames
                    
                # ERB fallback
                mags, n = spectrum_magnitudes(samples, fs, size=min(4096, len(samples))) if samples else ([], 0)
                if mags:
                    erb_prof = compute_erb_profile(mags, fs, n, num_bands=40)
                else:
                    erb_prof = [0.0] * 40
                    for b_idx, (fc, _, _) in enumerate(erb_bands):
                        if fc < 60:
                            val = default_bands.get("sub", 0.0)
                        elif fc < 150:
                            val = default_bands.get("bass", 0.0)
                        elif fc < 400:
                            val = default_bands.get("low_mids", 0.0)
                        elif fc < 2000:
                            val = default_bands.get("mids", 0.0)
                        elif fc < 6000:
                            val = default_bands.get("presence", 0.0)
                        elif fc < 8000:
                            val = default_bands.get("sibilance", 0.0)
                        else:
                            val = default_bands.get("air", 0.0)
                        erb_prof[b_idx] = val
                    total_erb = sum(erb_prof) or 1.0
                    erb_prof = [v / total_erb for v in erb_prof]
                average_erb = erb_prof
                erb_profiles = [erb_prof] * num_frames
        except Exception:
            average_bands = default_bands
            for k in bands_keys:
                time_series[k] = [average_bands[k]] * num_frames
                
            # ERB Exception fallback
            erb_prof = [0.0] * 40
            for b_idx, (fc, _, _) in enumerate(erb_bands):
                if fc < 60:
                    val = default_bands.get("sub", 0.0)
                elif fc < 150:
                    val = default_bands.get("bass", 0.0)
                elif fc < 400:
                    val = default_bands.get("low_mids", 0.0)
                elif fc < 2000:
                    val = default_bands.get("mids", 0.0)
                elif fc < 6000:
                    val = default_bands.get("presence", 0.0)
                elif fc < 8000:
                    val = default_bands.get("sibilance", 0.0)
                else:
                    val = default_bands.get("air", 0.0)
                erb_prof[b_idx] = val
            total_erb = sum(erb_prof) or 1.0
            erb_prof = [v / total_erb for v in erb_prof]
            average_erb = erb_prof
            erb_profiles = [erb_prof] * num_frames

        results.append({
            "name": name.rsplit(".", 1)[0],
            "bands": average_bands,
            "time_series": time_series,
            "erb_profile": average_erb,
            "erb_profiles": erb_profiles
        })

    # Compute masking matrix
    masking_matrix = {}
    for s1 in results:
        name1 = s1["name"]
        masking_matrix[name1] = {}
        for s2 in results:
            name2 = s2["name"]
            if name1 == name2:
                masking_matrix[name1][name2] = 1.0
            else:
                # Sum the masking index across all bands: correlation * overlap
                masking_index = 0.0
                for k in bands_keys:
                    corr = _correlation(s1["time_series"][k], s2["time_series"][k])
                    corr_clamped = max(0.0, corr)
                    
                    # Overlap is the minimum energy presence
                    overlap = min(s1["bands"][k], s2["bands"][k])
                    masking_index += corr_clamped * overlap
                    
                masking_matrix[name1][name2] = round(min(1.0, masking_index), 3)

    # Compute simultaneous masking & clarity scores
    for s in results:
        s["overall_visibility"] = 0.0
        s["visibility_per_band"] = [0.0] * 40
        
    for f_idx in range(num_frames):
        for s in results:
            name = s["name"]
            other_stems_energies = []
            for other in results:
                if other["name"] != name:
                    f_i = min(f_idx, len(other["erb_profiles"]) - 1)
                    other_stems_energies.append(other["erb_profiles"][f_i])
            
            f_i_s = min(f_idx, len(s["erb_profiles"]) - 1)
            threshold_spl = compute_combined_masking_threshold(other_stems_energies, erb_bands)
            vis, band_vis = calculate_visibility(s["erb_profiles"][f_i_s], threshold_spl)
            
            s["overall_visibility"] += vis
            for b_idx in range(40):
                s["visibility_per_band"][b_idx] += band_vis[b_idx]
                
    for s in results:
        s["overall_visibility"] = round(s["overall_visibility"] / num_frames, 3)
        s["visibility_per_band"] = [round(v / num_frames, 3) for v in s["visibility_per_band"]]

    # Compute 2D ERB Heatmap
    erb_heatmap = {}
    for s1 in results:
        name1 = s1["name"]
        erb_heatmap[name1] = {}
        for s2 in results:
            name2 = s2["name"]
            if name1 == name2:
                erb_heatmap[name1][name2] = [1.0] * 40
            else:
                band_masking = [0.0] * 40
                for f_idx in range(num_frames):
                    f_i1 = min(f_idx, len(s1["erb_profiles"]) - 1)
                    f_i2 = min(f_idx, len(s2["erb_profiles"]) - 1)
                    e1 = s1["erb_profiles"][f_i1]
                    e2 = s2["erb_profiles"][f_i2]
                    for b_idx in range(40):
                        if e1[b_idx] + e2[b_idx] > 1e-15:
                            band_masking[b_idx] += e1[b_idx] / (e1[b_idx] + e2[b_idx])
                erb_heatmap[name1][name2] = [round(v / num_frames, 3) for v in band_masking]

    suggestions = generate_carving_suggestions(results, erb_heatmap, erb_bands)
    improvements = simulate_clarity_improvement(results, suggestions, erb_bands)

    erb_details = {
        "erb_frequencies": [round(fc, 1) for fc, _, _ in erb_bands],
        "heatmap": erb_heatmap,
        "carving_suggestions": suggestions,
        "clarity_improvement": improvements
    }

    return {
        "stems": [
            {
                "name": r["name"],
                "bands": r["bands"],
                "overall_visibility": r["overall_visibility"],
                "visibility_per_band": r["visibility_per_band"]
            } for r in results
        ],
        "masking_matrix": masking_matrix,
        "erb_details": erb_details
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
