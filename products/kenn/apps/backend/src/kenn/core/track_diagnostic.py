"""Acoustic Track Diagnostic Scanner for KENN.

Analyzes individual Ableton Live tracks to produce:
1. High-resolution waveform envelope (peaks and RMS).
2. 2D Time-Frequency Spectrogram (STFT energy distribution across 40 bark bands).
3. Acoustic "Weak Area" detection (sub rumble, mud resonance, harshness, sibilance, dynamics, phase).
4. Automated Live 12 surgical remediation proposals with direct parameter values.
"""

from __future__ import annotations

import gzip
import logging
import math
import os
import re
import struct
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("kenn.track_diagnostic")

# Frequency band centers for the 40-band diagnostic spectrogram (20 Hz - 20 kHz)
SPECTROGRAM_FREQUENCIES_HZ = [
    20, 25, 31, 40, 50, 63, 80, 100, 125, 160,
    200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
    2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
]

SPECTROGRAM_BAND_COUNT = len(SPECTROGRAM_FREQUENCIES_HZ)
SPECTROGRAM_TIME_SLICES = 64
WAVEFORM_POINTS = 300


def _db(value: float, floor: float = -96.0) -> float:
    if value <= 0.0:
        return floor
    return max(floor, round(20.0 * math.log10(value), 2))


def extract_session_tracks(als_path: str, project_dir: str = "") -> List[Dict[str, Any]]:
    """Extract tracks from an Ableton Live set (.als) and correlate with audio files."""
    if not als_path or not os.path.isfile(als_path):
        return []

    tracks: List[Dict[str, Any]] = []
    try:
        with gzip.open(als_path, "rb") as f:
            tree = ET.parse(f)
        root = tree.getroot()

        track_nodes = root.findall(".//Tracks/*")
        for idx, t in enumerate(track_nodes):
            tag = t.tag  # e.g., AudioTrack, MidiTrack, GroupTrack, ReturnTrack
            effective_name = t.find("./Name/EffectiveName")
            user_name = t.find("./Name/UserName")

            name = ""
            if user_name is not None and user_name.attrib.get("Value"):
                name = user_name.attrib["Value"]
            elif effective_name is not None and effective_name.attrib.get("Value"):
                name = effective_name.attrib["Value"]
            else:
                name = f"Track {idx + 1}"

            # Detect track type
            is_group = "Group" in tag
            is_return = "Return" in tag
            is_midi = "Midi" in tag
            is_audio = "Audio" in tag

            # Color index if present
            color_el = t.find("./Color")
            color_index = int(color_el.attrib.get("Value", "0")) if color_el is not None else 0

            tracks.append({
                "track_index": idx,
                "track_name": name,
                "track_type": "audio" if is_audio else ("midi" if is_midi else ("group" if is_group else ("return" if is_return else "other"))),
                "is_audio": is_audio,
                "color_index": color_index,
                "has_audio_match": False,
                "matched_file_path": None,
                "matched_label": None,
            })
    except Exception as exc:
        logger.debug("Failed to parse ALS XML: %s", exc)
        return []

    # Correlate tracks with bounces / stems found in project_dir
    if project_dir and os.path.isdir(project_dir):
        from kenn.core.ableton_project_detector import find_project_bounces
        bounces = find_project_bounces(project_dir)

        for track in tracks:
            t_name_clean = re.sub(r"[^\w\s-]", "", track["track_name"]).lower().strip()
            if not t_name_clean:
                continue

            # Look for exact or fuzzy match in bounces
            best_match: Optional[Dict[str, Any]] = None
            for b in bounces:
                b_name_clean = re.sub(r"[^\w\s-]", "", b.get("label", "")).lower()
                b_file_clean = re.sub(r"[^\w\s-]", "", b.get("filename", "")).lower()

                # If track name appears in bounce name or filename
                if t_name_clean in b_name_clean or t_name_clean in b_file_clean:
                    best_match = b
                    break

            if best_match:
                track["has_audio_match"] = True
                track["matched_file_path"] = best_match["path"]
                track["matched_label"] = best_match["label"]

    return tracks


def build_tracks_from_live_session(
    live_tracks: List[Dict[str, Any]],
    bounces: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build track diagnostic entries from real-time Ableton Live session state."""
    bounces = bounces or []
    tracks: List[Dict[str, Any]] = []

    for t in live_tracks:
        idx = t.get("index", 0)
        name = str(t.get("name") or f"Track {idx + 1}").strip()
        devices = t.get("devices") or []

        # Determine if track is MIDI or Audio based on name and instrument devices
        name_lower = name.lower()
        dev_names = [str(d.get("name", "")).lower() for d in devices if isinstance(d, dict)]
        is_midi = "midi" in name_lower or any(
            any(inst in dn for inst in ("instrument", "operator", "wavetable", "simpler", "sampler", "drift", "analog", "vst"))
            for dn in dev_names
        )

        matched_file = None
        matched_lbl = None
        has_match = False
        if bounces:
            t_clean = re.sub(r"[^\w\s-]", "", name).lower().strip()
            for b in bounces:
                b_lbl = re.sub(r"[^\w\s-]", "", b.get("label", "")).lower()
                b_fn = re.sub(r"[^\w\s-]", "", b.get("filename", "")).lower()
                if t_clean and (t_clean in b_lbl or t_clean in b_fn):
                    matched_file = b.get("path")
                    matched_lbl = b.get("label")
                    has_match = True
                    break

        tracks.append({
            "track_index": idx,
            "track_name": name,
            "track_type": "midi" if is_midi else "audio",
            "is_audio": not is_midi,
            "color_index": 13,
            "has_audio_match": has_match,
            "matched_file_path": matched_file,
            "matched_label": matched_lbl,
        })

    return tracks


def _decode_pcm_channels(payload: bytes) -> Tuple[List[List[float]], int, float]:
    """Decode a WAV payload into per-channel float samples, sample_rate and full duration.

    Channels stay separate so level and loudness are measured per channel. The
    old decoder averaged to mono first, which read a polarity-flipped stereo
    file at -96 dBFS and put every stereo LUFS 3 dB low (16 Oct 2026).
    """
    from kenn.core.audio_analysis import _parse_wav
    channels, sampwidth, framerate, data_bytes, audio_format = _parse_wav(payload)
    if channels < 1 or framerate <= 0:
        raise ValueError("WAV header has no channels or no sample rate")

    total_frames = len(data_bytes) // (channels * sampwidth)
    duration = total_frames / framerate
    # 4,000,000 frames (83 s at 48 kHz) keeps the pure-Python loops and their
    # float lists bounded; duration still reports the whole file.
    frames_to_read = min(total_frames, 4_000_000)
    count = frames_to_read * channels

    if sampwidth == 2 and audio_format == 1:
        values = [v / 32768.0 for v in struct.unpack_from(f"<{count}h", data_bytes)]
    elif sampwidth == 4 and audio_format == 3:
        values = list(struct.unpack_from(f"<{count}f", data_bytes))
    elif sampwidth == 4 and audio_format == 1:
        values = [v / 2147483648.0 for v in struct.unpack_from(f"<{count}i", data_bytes)]
    elif sampwidth == 3 and audio_format == 1:
        values = [
            int.from_bytes(data_bytes[offset : offset + 3], byteorder="little", signed=True) / 8388608.0
            for offset in range(0, count * 3, 3)
        ]
    elif sampwidth == 1 and audio_format == 1:
        # 8-bit WAV is unsigned with its midpoint at 128.
        values = [(v - 128) / 128.0 for v in data_bytes[:count]]
    else:
        # The old fallback read any other layout as 8-bit bytes and measured
        # nonsense; refusing is the truthful answer for a diagnostic.
        raise ValueError(f"unsupported WAV sample format ({sampwidth * 8}-bit, format tag {audio_format})")

    return [values[ch::channels] for ch in range(channels)], framerate, duration


def _analysis_signal(channels: List[List[float]]) -> List[float]:
    """Return the single signal the waveform, spectrogram and spectral features read.

    That is the mono sum, unless the channels hold audio that cancels in the
    sum (L = -R), where the side signal is used so the display is not blank.
    """
    if len(channels) == 1:
        return channels[0]
    count = len(channels)
    mono = [sum(frame) / count for frame in zip(*channels)]
    mono_peak = max((abs(v) for v in mono), default=0.0)
    channel_peak = max((abs(v) for ch in channels for v in ch), default=0.0)
    # -60 dB below the louder channel: the sum is gone but the channels are not.
    if channel_peak > 0.0 and mono_peak < channel_peak * 0.001 and count == 2:
        return [(left - right) * 0.5 for left, right in zip(channels[0], channels[1])]
    return mono


def compute_waveform_envelope(samples: List[float], points: int = WAVEFORM_POINTS) -> Tuple[List[float], List[float]]:
    """Compute normalized peak and RMS envelopes across specified number of points."""
    if not samples:
        return [0.0] * points, [0.0] * points

    peaks: List[float] = []
    rms_list: List[float] = []
    chunk_size = max(1, len(samples) // points)

    for i in range(points):
        start = i * chunk_size
        end = min(len(samples), start + chunk_size)
        chunk = samples[start:end]
        if not chunk:
            peaks.append(0.0)
            rms_list.append(0.0)
            continue

        p = max((abs(v) for v in chunk), default=0.0)
        r = math.sqrt(sum(v * v for v in chunk) / len(chunk))
        peaks.append(round(min(1.0, p), 4))
        rms_list.append(round(min(1.0, r), 4))

    return peaks, rms_list


def compute_spectrogram_matrix(
    samples: List[float],
    sample_rate: int,
    time_slices: int = SPECTROGRAM_TIME_SLICES,
) -> List[List[float]]:
    """Compute 2D spectrogram matrix (time_slices x 31 log bands) in decibels."""
    if not samples or sample_rate <= 0:
        return [[-80.0] * SPECTROGRAM_BAND_COUNT for _ in range(time_slices)]

    matrix: List[List[float]] = []
    slice_len = max(512, len(samples) // time_slices)
    nyquist = sample_rate / 2.0

    for s_idx in range(time_slices):
        start = s_idx * slice_len
        end = min(len(samples), start + slice_len)
        slice_samples = samples[start:end]
        if len(slice_samples) < 64:
            matrix.append([-80.0] * SPECTROGRAM_BAND_COUNT)
            continue

        # Estimate energy in each frequency band using DFT bins
        band_energies: List[float] = []
        n_pts = min(2048, len(slice_samples))
        # Precompute window
        win = [0.5 * (1.0 - math.cos(2.0 * math.pi * n / (n_pts - 1))) for n in range(n_pts)]
        windowed = [slice_samples[n] * win[n] for n in range(n_pts)]

        for f_center in SPECTROGRAM_FREQUENCIES_HZ:
            if f_center >= nyquist:
                band_energies.append(-80.0)
                continue

            # Goertzel / Single-bin DFT magnitude for f_center
            k = int(round(f_center * n_pts / sample_rate))
            omega = 2.0 * math.pi * k / n_pts
            coeff = 2.0 * math.cos(omega)
            q1 = 0.0
            q2 = 0.0
            for sample in windowed:
                q0 = coeff * q1 - q2 + sample
                q2 = q1
                q1 = q0

            mag_sq = q1 * q1 + q2 * q2 - q1 * q2 * coeff
            mag = math.sqrt(max(0.0, mag_sq)) / (n_pts / 2.0)
            db_val = _db(mag, floor=-80.0)
            band_energies.append(db_val)

        matrix.append(band_energies)

    return matrix


def detect_weak_areas(
    samples: List[float],
    sample_rate: int,
    peak_dbfs: float,
    rms_dbfs: float,
    spectrogram: List[List[float]],
    track_name: str = "Track",
    track_index: int = 0,
    resonant_peaks: Optional[List[Dict[str, float]]] = None,
) -> List[Dict[str, Any]]:
    """Detect acoustic flaws: sub rumble, mud, harshness, sibilance, dynamics."""
    weak_areas: List[Dict[str, Any]] = []

    # 1. Average spectral energy across all time slices for each band
    if not spectrogram:
        return weak_areas

    avg_bands = [0.0] * SPECTROGRAM_BAND_COUNT
    valid_slices = max(1, len(spectrogram))
    for slice_energies in spectrogram:
        for b_idx in range(SPECTROGRAM_BAND_COUNT):
            avg_bands[b_idx] += slice_energies[b_idx] / valid_slices

    # Find band indices
    # Sub: 20, 25 Hz (b0, b1)
    # Bass: 50, 63, 80 Hz (b4, b5, b6)
    # Mud: 200, 250, 315 Hz (b10, b11, b12)
    # Mid reference: 500, 630, 800 Hz (b14, b15, b16)
    # Harshness: 2.5k, 3.15k, 4.0k Hz (b21, b22, b23)
    # Sibilance: 6.3k, 8k, 10k Hz (b25, b26, b27)

    sub_energy = max(avg_bands[0], avg_bands[1])
    bass_energy = max(avg_bands[4], avg_bands[5], avg_bands[6])
    mud_energy = max(avg_bands[10], avg_bands[11], avg_bands[12])
    mid_energy = max(avg_bands[14], avg_bands[15], avg_bands[16])
    harsh_energy = max(avg_bands[21], avg_bands[22], avg_bands[23])
    sib_energy = max(avg_bands[25], avg_bands[26], avg_bands[27])

    crest_factor = round(peak_dbfs - rms_dbfs, 2) if rms_dbfs > -90.0 else 0.0

    # Defect 0: Digital Clipping Overs
    if peak_dbfs >= -0.05:
        over_db = round(max(0.1, peak_dbfs - 0.0), 2)
        cut_db = round(over_db + 1.0, 1)
        weak_areas.append({
            "id": f"clipping_{track_index}",
            "type": "clipping",
            "title": f"Digital Clipping Overs (+{over_db:.1f} dBFS)",
            "severity": "critical",
            "frequency_range": "Full Spectrum",
            "measured_value": f"Peak at +{over_db:.2f} dBFS over 0 dBFS ceiling",
            "description": "Signal exceeds 0 dBFS full scale, causing inter-sample clipping distortion on digital converters.",
            "suggestion": f"Lower track volume fader or Utility output by -{cut_db:.1f} dB to restore clean headroom.",
            "remedy": {
                "action": "insert_device_with_parameter",
                "device_name": "Utility",
                "track_index": track_index,
                "track_name": track_name,
                "parameter_name": "Gain",
                "parameter_value": -cut_db,
                "explanation": f"Trim Utility gain on '{track_name}' by -{cut_db:.1f} dB to clear converter clipping.",
            },
        })

    # Defect A: Sub-bass Rumble (< 32 Hz)
    # If sub energy is strong relative to bass, it wastes headroom without musical pitch
    if sub_energy > -45.0 and sub_energy > (bass_energy - 6.0):
        weak_areas.append({
            "id": f"sub_rumble_{track_index}",
            "type": "sub_rumble",
            "title": "Sub Rumble Build-up (< 32 Hz)",
            "severity": "critical" if sub_energy > -30.0 else "warning",
            "frequency_range": "18 Hz - 32 Hz",
            "measured_value": f"{sub_energy:.1f} dBFS in sub register",
            "description": "Excessive energy below 32 Hz wastes converter headroom and causes compressor pumping without musical pitch.",
            "suggestion": "Apply an 18 dB/oct high-pass filter at 32 Hz on EQ Eight.",
            "remedy": {
                "action": "insert_device_with_parameter",
                "device_name": "EQ Eight",
                "track_index": track_index,
                "track_name": track_name,
                "parameter_name": "1 Frequency A",
                "parameter_value": 32.0,
                "filter_type": "high_pass_18",
                "explanation": f"Filter out infrasonic rumble below 32 Hz on '{track_name}' to reclaim headroom.",
            },
        })

    # Defect B: Boxy Mud Resonance (200 Hz - 450 Hz)
    # If mud energy sticks out > 4 dB above mids
    if mud_energy > -42.0 and mud_energy > (mid_energy + 4.5):
        peak_mud_idx = 10 if avg_bands[10] >= avg_bands[11] and avg_bands[10] >= avg_bands[12] else (11 if avg_bands[11] >= avg_bands[12] else 12)
        mud_freq = float(SPECTROGRAM_FREQUENCIES_HZ[peak_mud_idx])
        # If scipy found a clinical peak in the 200..450 Hz range, use its exact frequency
        if resonant_peaks:
            for rp in resonant_peaks:
                rf = rp.get("frequency_hz", 0.0)
                if 200.0 <= rf <= 450.0:
                    mud_freq = rf
                    break

        cut_db = min(5.0, round(mud_energy - mid_energy, 1))

        weak_areas.append({
            "id": f"mud_resonance_{track_index}",
            "type": "mud_resonance",
            "title": f"Boxy Mud Resonance ({mud_freq:.0f} Hz)",
            "severity": "warning",
            "frequency_range": f"{mud_freq - 40:.0f} Hz - {mud_freq + 60:.0f} Hz",
            "measured_value": f"+{cut_db:.1f} dB above midrange balance",
            "description": f"Accumulation at {mud_freq:.0f} Hz creates a boxy, cloudy character that smears the center image.",
            "suggestion": f"Carve a narrow bell notch (-{cut_db:.1f} dB, Q=3.8) centered at {mud_freq:.0f} Hz.",
            "remedy": {
                "action": "set_eq_band_tuning_gain",
                "device_name": "EQ Eight",
                "track_index": track_index,
                "track_name": track_name,
                "eq_band": "3A",
                "frequency_hz": mud_freq,
                "gain_db": -cut_db,
                "q": 3.8,
                "explanation": f"Dip {mud_freq:.0f} Hz on '{track_name}' by -{cut_db:.1f} dB to clear boxiness.",
            },
        })

    # Defect C: Harshness / Piercing Resonance (2.5 kHz - 4.5 kHz)
    if harsh_energy > -38.0 and harsh_energy > (mid_energy + 3.0):
        harsh_idx = 21 if avg_bands[21] >= avg_bands[22] and avg_bands[21] >= avg_bands[23] else (22 if avg_bands[22] >= avg_bands[23] else 23)
        harsh_freq = float(SPECTROGRAM_FREQUENCIES_HZ[harsh_idx])
        # If scipy found a clinical peak in the 2.5k..4.5k Hz range, use its exact frequency
        if resonant_peaks:
            for rp in resonant_peaks:
                rf = rp.get("frequency_hz", 0.0)
                if 2400.0 <= rf <= 4800.0:
                    harsh_freq = rf
                    break

        cut_db = min(4.0, round(harsh_energy - mid_energy, 1))

        weak_areas.append({
            "id": f"harshness_{track_index}",
            "type": "harshness",
            "title": f"Harsh Upper-Mid Spike ({harsh_freq:.0f} Hz)",
            "severity": "warning",
            "frequency_range": f"{harsh_freq - 250:.0f} Hz - {harsh_freq + 350:.0f} Hz",
            "measured_value": f"+{cut_db:.1f} dB resonance spike",
            "description": "High-Q energy in the 2.5–4.5 kHz zone induces listener fatigue and brittle texture.",
            "suggestion": f"Apply a subtle dynamic notch (-{cut_db:.1f} dB, Q=4.2) at {harsh_freq:.0f} Hz.",
            "remedy": {
                "action": "set_eq_band_tuning_gain",
                "device_name": "EQ Eight",
                "track_index": track_index,
                "track_name": track_name,
                "eq_band": "5A",
                "frequency_hz": harsh_freq,
                "gain_db": -cut_db,
                "q": 4.2,
                "explanation": f"Notch {harsh_freq:.0f} Hz on '{track_name}' by -{cut_db:.1f} dB to remove upper-mid harshness.",
            },
        })

    # Defect D: Sibilance / Splash (7 kHz - 10 kHz)
    if sib_energy > -36.0 and sib_energy > (harsh_energy + 2.5):
        weak_areas.append({
            "id": f"sibilance_{track_index}",
            "type": "sibilance",
            "title": "Excessive Sibilance & Splash (8 kHz)",
            "severity": "info",
            "frequency_range": "7.5 kHz - 9.5 kHz",
            "measured_value": f"{sib_energy:.1f} dBFS high register energy",
            "description": "Prominent top-end creates distracting vocal sibilance or splashy cymbal wash.",
            "suggestion": "Tame with a smooth high-shelf attenuation (-2.0 dB at 8.5 kHz) or De-Esser.",
            "remedy": {
                "action": "set_eq_band_tuning_gain",
                "device_name": "EQ Eight",
                "track_index": track_index,
                "track_name": track_name,
                "eq_band": "7A",
                "frequency_hz": 8500.0,
                "gain_db": -2.0,
                "q": 0.71,
                "explanation": f"High shelf cut on '{track_name}' at 8.5 kHz by -2.0 dB to tame top-end splash.",
            },
        })

    # Defect E: Dynamics & Crest Factor
    if crest_factor < 6.0 and peak_dbfs > -18.0:
        weak_areas.append({
            "id": f"squashed_dynamics_{track_index}",
            "type": "over_compressed",
            "title": "Over-Compressed (Squashed Crest Factor)",
            "severity": "warning",
            "frequency_range": "Full Spectrum",
            "measured_value": f"Crest factor only {crest_factor:.1f} dB (target > 8 dB)",
            "description": "Dynamics are heavily squashed. Transients lack punch, leaving the track flat in the mix.",
            "suggestion": "Lengthen compressor attack time (> 25 ms) or ease ratio down to 2:1.",
            "remedy": {
                "action": "set_device_parameter",
                "device_name": "Compressor",
                "track_index": track_index,
                "track_name": track_name,
                "parameter_name": "Attack",
                "parameter_value": 30.0,
                "explanation": f"Open Compressor attack to 30 ms on '{track_name}' to restore punch.",
            },
        })
    elif crest_factor > 16.5:
        weak_areas.append({
            "id": f"wild_transients_{track_index}",
            "type": "wild_transients",
            "title": "Uncontrolled Peak Transients",
            "severity": "info",
            "frequency_range": "Full Spectrum",
            "measured_value": f"Crest factor {crest_factor:.1f} dB (excessive dynamic spike)",
            "description": "Sudden transient peaks spike high above average musical body, eating mix bus ceiling.",
            "suggestion": "Use gentle peak limiting or soft clipping to tame the initial 2-3 dB transient spike.",
            "remedy": {
                "action": "insert_device_with_parameter",
                "device_name": "Compressor",
                "track_index": track_index,
                "track_name": track_name,
                "parameter_name": "Ratio",
                "parameter_value": 4.0,
                "explanation": f"Insert Compressor on '{track_name}' with 4:1 ratio to control peak transients.",
            },
        })

    return weak_areas


def _extract_dsp_features_with_open_source_tools(
    samples: List[float],
    sample_rate: int,
    channels: Optional[List[List[float]]] = None,
) -> Dict[str, Any]:
    """Extract clinical acoustic features using librosa, pyloudnorm, and scipy."""
    result: Dict[str, Any] = {
        "lufs_integrated": None,
        "spectral_centroid_hz": None,
        "spectral_flatness": None,
        "resonant_peaks": [],
    }
    try:
        import numpy as np

        audio_np = np.array(samples, dtype=np.float32)

        # 1. ITU-R BS.1770 LUFS via pyloudnorm, on the real channels: BS.1770
        # sums channel powers, so a downmix reads stereo 3 dB low.
        try:
            import pyloudnorm as pyln
            meter = pyln.Meter(sample_rate)
            lufs = meter.integrated_loudness(np.array(channels, dtype=np.float32).T if channels else audio_np)
            if not math.isnan(lufs) and not math.isinf(lufs):
                result["lufs_integrated"] = round(float(lufs), 2)
        except Exception:
            pass

        # 2. Spectral Centroid and Flatness via librosa
        try:
            import librosa
            centroid = librosa.feature.spectral_centroid(y=audio_np, sr=sample_rate)
            flatness = librosa.feature.spectral_flatness(y=audio_np)
            if centroid.size:
                result["spectral_centroid_hz"] = round(float(np.mean(centroid)), 1)
            if flatness.size:
                result["spectral_flatness"] = round(float(np.mean(flatness)), 5)
        except Exception:
            pass

        # 3. Clinical Resonance Detection via scipy Welch PSD & peak prominence
        try:
            from scipy import signal
            nperseg = min(4096, max(512, len(samples) // 4))
            freqs, psd = signal.welch(audio_np, sample_rate, nperseg=nperseg)
            psd_db = 10 * np.log10(np.maximum(psd, 1e-12))
            peaks_idx, _ = signal.find_peaks(psd_db, prominence=5.0, distance=8)
            found_peaks = []
            for p in peaks_idx:
                f_val = round(float(freqs[p]), 1)
                db_val = round(float(psd_db[p]), 1)
                if 40.0 <= f_val <= 14000.0:
                    found_peaks.append({"frequency_hz": f_val, "level_db": db_val})
            found_peaks.sort(key=lambda x: x["level_db"], reverse=True)
            result["resonant_peaks"] = found_peaks[:6]
        except Exception:
            pass
    except Exception as exc:
        logger.debug("Open source DSP extractor fallback: %s", exc)

    return result


def analyze_track_diagnostic(
    payload: bytes,
    filename: str = "track.wav",
    track_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform full diagnostic on audio payload for a track."""
    started = time.perf_counter()
    track_name = track_info.get("track_name", "Track") if track_info else "Track"
    track_index = int(track_info.get("track_index", 0)) if track_info else 0

    try:
        channels, sample_rate, duration = _decode_pcm_channels(payload)
    except Exception as exc:
        logger.error("Track diagnostic audio decode error: %s", exc)
        return {
            "ok": False,
            "error": f"Failed to decode audio: {exc}",
            "track_name": track_name,
            "track_index": track_index,
        }

    samples = _analysis_signal(channels)
    if not samples:
        return {
            "ok": False,
            "error": "Audio file contains no playable samples.",
            "track_name": track_name,
            "track_index": track_index,
        }

    # Signal measurements
    # Peak is the loudest channel and RMS the mean of channel RMS, matching
    # analyze_wav, so the two routes agree on the same file.
    peak_val = max((abs(v) for ch in channels for v in ch), default=0.0)
    rms_val = sum(math.sqrt(sum(v * v for v in ch) / len(ch)) for ch in channels) / len(channels)
    peak_dbfs = _db(peak_val)
    rms_dbfs = _db(rms_val)
    crest_factor = round(peak_dbfs - rms_dbfs, 2)

    # Waveform envelope points
    waveform_peaks, waveform_rms = compute_waveform_envelope(samples, points=WAVEFORM_POINTS)

    # 2D Spectrogram Matrix
    spectrogram_matrix = compute_spectrogram_matrix(samples, sample_rate, time_slices=SPECTROGRAM_TIME_SLICES)

    # Open-source DSP extraction (librosa, pyloudnorm, scipy)
    dsp_extra = _extract_dsp_features_with_open_source_tools(samples, sample_rate, channels)

    # Weak areas detection
    weak_areas = detect_weak_areas(
        samples=samples,
        sample_rate=sample_rate,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        spectrogram=spectrogram_matrix,
        track_name=track_name,
        track_index=track_index,
        resonant_peaks=dsp_extra.get("resonant_peaks"),
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)

    return {
        "ok": True,
        "track_name": track_name,
        "track_index": track_index,
        "filename": filename,
        "duration_seconds": round(duration, 3),
        "sample_rate_hz": sample_rate,
        "metrics": {
            "peak_dbfs": peak_dbfs,
            "rms_dbfs": rms_dbfs,
            "crest_factor_db": crest_factor,
            "lufs_integrated": dsp_extra.get("lufs_integrated"),
            "spectral_centroid_hz": dsp_extra.get("spectral_centroid_hz"),
            "spectral_flatness": dsp_extra.get("spectral_flatness"),
            "resonant_peaks": dsp_extra.get("resonant_peaks", []),
            "duration_seconds": round(duration, 3),
            "sample_rate_hz": sample_rate,
        },
        "waveform": {
            "peaks": waveform_peaks,
            "rms": waveform_rms,
            "points_count": len(waveform_peaks),
        },
        "spectrogram": {
            "matrix": spectrogram_matrix,
            "time_slices": len(spectrogram_matrix),
            "frequencies_hz": SPECTROGRAM_FREQUENCIES_HZ,
            "band_count": len(SPECTROGRAM_FREQUENCIES_HZ),
        },
        "weak_areas": weak_areas,
        "weak_areas_count": len(weak_areas),
        "elapsed_ms": elapsed_ms,
    }
