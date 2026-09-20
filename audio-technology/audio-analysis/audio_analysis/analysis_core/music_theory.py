from __future__ import annotations

from cmath import exp, pi
import math

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ROOT_TO_PC = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}
COMPLEX_QUALITIES = {"7", "Maj7", "Min7", "Dim"}
SIMPLE_QUALITY_FOR_COMPLEX = {
    "7": "Maj",
    "Maj7": "Maj",
    "Min7": "Min",
    "Dim": "Min",
}
SEMITONE_TO_INTERVAL = {
    0: "Unison",
    1: "Minor 2nd",
    2: "Major 2nd",
    3: "Minor 3rd",
    4: "Major 3rd",
    5: "Perfect 4th",
    6: "Tritone",
    7: "Perfect 5th",
    8: "Minor 6th",
    9: "Major 6th",
    10: "Minor 7th",
    11: "Major 7th",
}

TEMPERLEY_MAJ = [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
TEMPERLEY_MIN = [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]

_maj_norm = math.sqrt(sum(x * x for x in TEMPERLEY_MAJ))
TEMPERLEY_MAJ_NORM = [x / _maj_norm for x in TEMPERLEY_MAJ]
_min_norm = math.sqrt(sum(x * x for x in TEMPERLEY_MIN))
TEMPERLEY_MIN_NORM = [x / _min_norm for x in TEMPERLEY_MIN]


def _fft(values: list[complex]) -> list[complex]:
    n = len(values)
    if n <= 1:
        return values
    even = _fft(values[0::2])
    odd = _fft(values[1::2])
    factors = [exp(-2j * pi * k / n) * odd[k] for k in range(n // 2)]
    return [even[k] + factors[k] for k in range(n // 2)] + [even[k] - factors[k] for k in range(n // 2)]


def detect_chords_and_key(samples: list[float], sample_rate: float) -> dict:
    """Detect chord progression, estimated key, and intervals between consecutive chords."""
    if not samples or sample_rate <= 0 or len(samples) < 512:
        return {
            "estimated_key": "Unknown",
            "key_confidence_score": 0.0,
            "key_confidence": "low",
            "progression": [],
            "intervals": [],
            "sanity": {
                "notes": ["no_stable_progression", "key_confidence_low"],
                "changes_per_minute": 0.0,
                "low_confidence_sections": 0,
                "complex_chord_ratio": 0.0,
                "named_sections": 0,
            },
            "analysis_notes": ["no_stable_progression", "key_confidence_low"],
            "key_confidence_explanation": "No stable harmonic content was available, so the key estimate is unknown.",
            "progression_confidence_summary": "No stable chord progression was detected.",
        }

    chord_templates = []
    chord_template_map = {}
    qualities = {
        "Maj": ([0, 4, 7], [1.0, 0.8, 0.9]),
        "Min": ([0, 3, 7], [1.0, 0.8, 0.9]),
        "7": ([0, 4, 7, 10], [1.0, 0.7, 0.8, 0.6]),
        "Maj7": ([0, 4, 7, 11], [1.0, 0.7, 0.8, 0.6]),
        "Min7": ([0, 3, 7, 10], [1.0, 0.7, 0.8, 0.6]),
        "Dim": ([0, 3, 6], [1.0, 0.8, 0.7]),
    }
    for root_idx in range(12):
        for qual_name, (notes, weights) in qualities.items():
            template = [0.0] * 12
            for note, weight in zip(notes, weights):
                template[(root_idx + note) % 12] = weight
            t_norm = math.sqrt(sum(w * w for w in template))
            if t_norm > 0:
                template = [w / t_norm for w in template]
            chord_label = f"{ROOTS[root_idx]} {qual_name}"
            chord_templates.append((chord_label, root_idx, qual_name, template))
            chord_template_map[(root_idx, qual_name)] = (chord_label, template)

    n_fft = 2048
    if sample_rate < 2000:
        n_fft = 1024
    if sample_rate < 1000:
        n_fft = 512

    hop = n_fft // 4
    hann = [0.5 - 0.5 * math.cos((2.0 * math.pi * j) / (n_fft - 1)) for j in range(n_fft)]
    if NUMPY_AVAILABLE:
        hann_np = np.array(hann, dtype=np.float64)

    bin_to_pc = {}
    for k in range(n_fft // 2):
        freq = k * sample_rate / n_fft
        if 80.0 <= freq <= 1000.0:
            pitch = 12.0 * math.log2(freq / 440.0) + 69.0
            bin_to_pc[k] = int(round(pitch)) % 12

    if not bin_to_pc:
        for k in range(n_fft // 2):
            freq = k * sample_rate / n_fft
            if freq > 0:
                pitch = 12.0 * math.log2(freq / 440.0) + 69.0
                bin_to_pc[k] = int(round(pitch)) % 12

    raw_labels = []
    raw_confidences = []
    all_chromas = []

    num_frames = (len(samples) - n_fft) // hop + 1
    if num_frames <= 0:
        padded_samples = samples + [0.0] * (n_fft - len(samples))
        num_frames = 1
    else:
        padded_samples = samples

    for i in range(num_frames):
        start = i * hop
        window = padded_samples[start : start + n_fft]
        if len(window) < n_fft:
            window = window + [0.0] * (n_fft - len(window))

        rms = math.sqrt(sum(x * x for x in window) / n_fft)
        if rms < 0.005:
            raw_labels.append("N.C.")
            raw_confidences.append(0.0)
            continue

        if NUMPY_AVAILABLE:
            try:
                windowed = np.array(window, dtype=np.float64) * hann_np
                fft_vals = np.abs(np.fft.rfft(windowed))[: n_fft // 2]
            except Exception:
                windowed = [w * h for w, h in zip(window, hann)]
                fft_vals = [abs(item) for item in _fft([complex(val, 0) for val in windowed])[: n_fft // 2]]
        else:
            windowed = [w * h for w, h in zip(window, hann)]
            fft_vals = [abs(item) for item in _fft([complex(val, 0) for val in windowed])[: n_fft // 2]]

        chroma = [0.0] * 12
        for k, pc in bin_to_pc.items():
            if k < len(fft_vals):
                chroma[pc] += fft_vals[k]

        c_norm = math.sqrt(sum(x * x for x in chroma))
        if c_norm < 1e-4:
            raw_labels.append("N.C.")
            raw_confidences.append(0.0)
            continue

        chroma_normed = [x / c_norm for x in chroma]
        all_chromas.append(chroma_normed)

        best_chord = "N.C."
        best_sim = 0.0
        best_root = 0
        best_quality = ""
        for chord_label, root_idx, quality, template in chord_templates:
            sim = sum(c * t for c, t in zip(chroma_normed, template))
            if sim > best_sim:
                best_sim = sim
                best_chord = chord_label
                best_root = root_idx
                best_quality = quality

        best_chord, best_sim = prefer_simpler_chord(
            best_chord,
            best_sim,
            best_root,
            best_quality,
            chroma_normed,
            chord_template_map,
        )

        raw_labels.append(best_chord if best_sim >= 0.55 else "N.C.")
        raw_confidences.append(round(max(0.0, min(1.0, best_sim)), 3) if best_sim >= 0.55 else 0.0)

    estimated_key = "Unknown"
    if all_chromas:
        avg_chroma = [0.0] * 12
        for chroma in all_chromas:
            for c in range(12):
                avg_chroma[c] += chroma[c]
        avg_chroma = [x / len(all_chromas) for x in avg_chroma]

        avg_norm = math.sqrt(sum(x * x for x in avg_chroma))
        if avg_norm > 1e-4:
            avg_chroma_normed = [x / avg_norm for x in avg_chroma]

            best_key_label = "Unknown"
            best_key_sim = -1.0

            for key_root in range(12):
                maj_profile = TEMPERLEY_MAJ_NORM[-key_root:] + TEMPERLEY_MAJ_NORM[:-key_root]
                min_profile = TEMPERLEY_MIN_NORM[-key_root:] + TEMPERLEY_MIN_NORM[:-key_root]

                maj_sim = sum(c * p for c, p in zip(avg_chroma_normed, maj_profile))
                if maj_sim > best_key_sim:
                    best_key_sim = maj_sim
                    best_key_label = f"{ROOTS[key_root]} Major"

                min_sim = sum(c * p for c, p in zip(avg_chroma_normed, min_profile))
                if min_sim > best_key_sim:
                    best_key_sim = min_sim
                    best_key_label = f"{ROOTS[key_root]} Minor"

            estimated_key = best_key_label
            key_confidence_score = round(max(0.0, min(1.0, best_key_sim)), 3)
        else:
            key_confidence_score = 0.0
    else:
        key_confidence_score = 0.0

    smoothed_labels = []
    half_win = 3
    for i in range(len(raw_labels)):
        win = raw_labels[max(0, i - half_win) : min(len(raw_labels), i + half_win + 1)]
        counts = {}
        for item in win:
            counts[item] = counts.get(item, 0) + 1
        smoothed_labels.append(max(counts.items(), key=lambda pair: pair[1])[0])

    merged_segments = []
    if smoothed_labels:
        current_chord = smoothed_labels[0]
        start_idx = 0
        for idx in range(1, len(smoothed_labels)):
            if smoothed_labels[idx] != current_chord:
                start_time = (start_idx * hop) / sample_rate
                end_time = (idx * hop) / sample_rate
                merged_segments.append(
                    {
                        "chord": current_chord,
                        "start_time": round(start_time, 2),
                        "end_time": round(end_time, 2),
                        "duration": round(end_time - start_time, 2),
                        "confidence_score": _segment_confidence(raw_confidences, start_idx, idx),
                    }
                )
                current_chord = smoothed_labels[idx]
                start_idx = idx
        start_time = (start_idx * hop) / sample_rate
        end_time = len(smoothed_labels) * hop / sample_rate
        merged_segments.append(
            {
                "chord": current_chord,
                "start_time": round(start_time, 2),
                "end_time": round(end_time, 2),
                "duration": round(end_time - start_time, 2),
                "confidence_score": _segment_confidence(raw_confidences, start_idx, len(smoothed_labels)),
            }
        )

    refined_segments = []
    for seg in merged_segments:
        if seg["duration"] < 0.4:
            if refined_segments:
                _merge_segment_confidence(refined_segments[-1], seg)
                refined_segments[-1]["end_time"] = seg["end_time"]
                refined_segments[-1]["duration"] = round(
                    refined_segments[-1]["end_time"] - refined_segments[-1]["start_time"], 2
                )
            else:
                refined_segments.append(seg)
        elif refined_segments and refined_segments[-1]["chord"] == seg["chord"]:
            _merge_segment_confidence(refined_segments[-1], seg)
            refined_segments[-1]["end_time"] = seg["end_time"]
            refined_segments[-1]["duration"] = round(refined_segments[-1]["end_time"] - refined_segments[-1]["start_time"], 2)
        else:
            refined_segments.append(seg)

    if len(refined_segments) > 1 and refined_segments[0]["duration"] < 0.4:
        refined_segments[1]["start_time"] = refined_segments[0]["start_time"]
        refined_segments[1]["duration"] = round(refined_segments[1]["end_time"] - refined_segments[1]["start_time"], 2)
        refined_segments.pop(0)

    final_segments = []
    for seg in refined_segments:
        if final_segments and final_segments[-1]["chord"] == seg["chord"]:
            _merge_segment_confidence(final_segments[-1], seg)
            final_segments[-1]["end_time"] = seg["end_time"]
            final_segments[-1]["duration"] = round(final_segments[-1]["end_time"] - final_segments[-1]["start_time"], 2)
        else:
            seg["confidence"] = confidence_label(float(seg.get("confidence_score") or 0.0))
            final_segments.append(seg)
    final_segments = smooth_low_confidence_segments(final_segments)

    progression_list = []
    for seg in final_segments:
        chord_name = seg["chord"]
        if chord_name != "N.C." and (not progression_list or progression_list[-1] != chord_name):
            progression_list.append(chord_name)

    intervals = []
    for idx in range(len(progression_list) - 1):
        c1 = progression_list[idx]
        c2 = progression_list[idx + 1]
        r1 = ROOT_TO_PC.get(c1.split()[0], 0)
        r2 = ROOT_TO_PC.get(c2.split()[0], 0)
        diff = (r2 - r1) % 12
        intervals.append(
            {
                "from_chord": c1,
                "to_chord": c2,
                "interval": SEMITONE_TO_INTERVAL.get(diff, "Unknown"),
                "semitones": diff,
            }
        )

    sanity = chord_sanity_report(final_segments, estimated_key, key_confidence_score, sample_rate, len(samples))
    key_label = confidence_label(key_confidence_score)
    return {
        "estimated_key": estimated_key,
        "key_confidence_score": key_confidence_score,
        "key_confidence": key_label,
        "key_confidence_explanation": key_confidence_explanation(estimated_key, key_confidence_score, sanity),
        "progression": final_segments,
        "intervals": intervals,
        "sanity": sanity,
        "analysis_notes": sanity["notes"],
        "progression_confidence_summary": progression_confidence_summary(final_segments, sanity),
    }


def confidence_label(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.62:
        return "medium"
    return "low"


def key_confidence_explanation(estimated_key: str, score: float, sanity: dict) -> str:
    notes = set(sanity.get("notes") or [])
    named_sections = int(sanity.get("named_sections") or 0)
    label = confidence_label(score)
    if estimated_key == "Unknown":
        return "The key is unknown because there was not enough stable pitched harmonic content."
    if label == "high":
        return f"High confidence: the averaged chroma strongly matches {estimated_key} across {named_sections} named chord section(s)."
    if label == "medium":
        message = f"Medium confidence: {estimated_key} is the best match, but the harmonic evidence is not dominant."
    else:
        message = f"Low confidence: {estimated_key} is only a weak best match."
    if "low_confidence_sections" in notes:
        message += " Some chord sections were low confidence."
    if "busy_progression" in notes:
        message += " The progression changes quickly, which can reduce reliability."
    if "possible_over_detection" in notes or "complex_chord_heavy" in notes:
        message += " Complex-chord detection may be over-labelling some sections."
    if "no_stable_progression" in notes:
        message += " No stable named progression was detected."
    return message


def progression_confidence_summary(segments: list[dict], sanity: dict) -> str:
    named = [seg for seg in segments if isinstance(seg, dict) and seg.get("chord") != "N.C."]
    if not named:
        return "No stable chord progression was detected."
    low_count = int(sanity.get("low_confidence_sections") or 0)
    named_count = int(sanity.get("named_sections") or len(named))
    changes = sanity.get("changes_per_minute", 0.0)
    if low_count:
        return f"{named_count} named section(s), {low_count} low-confidence; about {changes} changes per minute."
    return f"{named_count} named section(s), no low-confidence named sections; about {changes} changes per minute."


def prefer_simpler_chord(
    best_chord: str,
    best_sim: float,
    best_root: int,
    best_quality: str,
    chroma: list[float],
    template_map: dict,
) -> tuple[str, float]:
    """Avoid over-labeling sevenths/diminished chords when triad evidence is close."""
    simple_quality = SIMPLE_QUALITY_FOR_COMPLEX.get(best_quality)
    if not simple_quality:
        return best_chord, best_sim
    simple = template_map.get((best_root, simple_quality))
    if not simple:
        return best_chord, best_sim
    simple_label, simple_template = simple
    simple_sim = sum(c * t for c, t in zip(chroma, simple_template))
    if best_quality == "Dim":
        margin = 0.10
        confidence_floor = 0.78
    else:
        margin = 0.08
        confidence_floor = 0.75
    if best_sim < confidence_floor or (best_sim - simple_sim) <= margin:
        return simple_label, simple_sim
    return best_chord, best_sim


def smooth_low_confidence_segments(segments: list[dict]) -> list[dict]:
    if len(segments) < 3:
        for seg in segments:
            seg["confidence"] = confidence_label(float(seg.get("confidence_score") or 0.0))
        return segments
    smoothed: list[dict] = []
    for idx, seg in enumerate(segments):
        score = float(seg.get("confidence_score") or 0.0)
        duration = float(seg.get("duration") or 0.0)
        if seg.get("chord") != "N.C." and score < 0.62 and duration < 1.0:
            prev_seg = smoothed[-1] if smoothed else None
            next_seg = segments[idx + 1] if idx + 1 < len(segments) else None
            target = prev_seg if prev_seg and prev_seg.get("chord") != "N.C." else None
            if next_seg and next_seg.get("chord") != "N.C.":
                if not target or float(next_seg.get("confidence_score") or 0.0) > float(target.get("confidence_score") or 0.0):
                    target = next_seg
            if target:
                if target is prev_seg:
                    _merge_segment_confidence(target, seg)
                    target["end_time"] = seg["end_time"]
                    target["duration"] = round(float(target["end_time"]) - float(target["start_time"]), 2)
                else:
                    seg = {**seg, "chord": str(target.get("chord") or seg.get("chord"))}
                    seg["confidence_score"] = max(score, float(target.get("confidence_score") or 0.0) * 0.8)
                    seg["confidence"] = confidence_label(float(seg["confidence_score"]))
                    smoothed.append(seg)
                continue
        seg["confidence"] = confidence_label(score)
        smoothed.append(seg)
    final: list[dict] = []
    for seg in smoothed:
        if final and final[-1].get("chord") == seg.get("chord"):
            _merge_segment_confidence(final[-1], seg)
            final[-1]["end_time"] = seg["end_time"]
            final[-1]["duration"] = round(float(final[-1]["end_time"]) - float(final[-1]["start_time"]), 2)
        else:
            final.append(seg)
    return final


def chord_sanity_report(segments: list[dict], estimated_key: str, key_confidence_score: float, sample_rate: float, sample_count: int) -> dict:
    named = [seg for seg in segments if isinstance(seg, dict) and seg.get("chord") != "N.C."]
    notes: list[str] = []
    duration = sample_count / sample_rate if sample_rate > 0 else 0.0
    changes_per_minute = round((max(0, len(named) - 1) / max(duration, 1.0)) * 60.0, 2)
    low_confidence_sections = sum(1 for seg in named if str(seg.get("confidence")) == "low")
    complex_sections = sum(1 for seg in named if chord_quality(str(seg.get("chord", ""))) in COMPLEX_QUALITIES)
    complex_ratio = round(complex_sections / len(named), 3) if named else 0.0
    if not named:
        notes.append("no_stable_progression")
    elif changes_per_minute > 24 and (len(named) >= 8 or duration >= 20.0):
        notes.append("busy_progression")
    else:
        notes.append("stable_progression")
    if low_confidence_sections:
        notes.append("low_confidence_sections")
    if complex_ratio > 0.35 and len(named) >= 8:
        notes.append("possible_over_detection")
    if complex_ratio > 0.5:
        notes.append("complex_chord_heavy")
    if key_confidence_score < 0.62 or estimated_key == "Unknown":
        notes.append("key_confidence_low")
    return {
        "notes": notes,
        "changes_per_minute": changes_per_minute,
        "low_confidence_sections": low_confidence_sections,
        "complex_chord_ratio": complex_ratio,
        "named_sections": len(named),
    }


def chord_quality(chord: str) -> str:
    parts = chord.split()
    return parts[1] if len(parts) > 1 else ""


def _segment_confidence(confidences: list[float], start: int, end: int) -> float:
    values = [value for value in confidences[start:end] if value > 0]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _merge_segment_confidence(target: dict, source: dict) -> None:
    target_duration = max(0.0, float(target.get("duration") or 0.0))
    source_duration = max(0.0, float(source.get("duration") or 0.0))
    total = target_duration + source_duration
    if total <= 0:
        target["confidence_score"] = max(float(target.get("confidence_score") or 0.0), float(source.get("confidence_score") or 0.0))
        target["confidence"] = confidence_label(float(target.get("confidence_score") or 0.0))
        return
    score = (
        (float(target.get("confidence_score") or 0.0) * target_duration)
        + (float(source.get("confidence_score") or 0.0) * source_duration)
    ) / total
    target["confidence_score"] = round(score, 3)
    target["confidence"] = confidence_label(target["confidence_score"])
