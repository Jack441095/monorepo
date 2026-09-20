"""Conservative, activity-derived arrangement evidence for AutoMix."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

import numpy as np

ARRANGEMENT_SCHEMA = "audio-too.arrangement.v1"
ARRANGEMENT_CORRECTION_SCHEMA = "audio-too.arrangement-correction.v1"
MAX_CORRECTED_SECTIONS = 256
MIN_CORRECTED_SECTION_SECONDS = 0.1


@dataclass(frozen=True)
class ArrangementSection:
    section_id: str
    start_seconds: float
    end_seconds: float
    active_stems: list[str]
    entering_stems: list[str]
    exiting_stems: list[str]
    density_ratio: float
    density_band: str
    boundary_confidence: float
    semantic_label: None = None


@dataclass(frozen=True)
class ArrangementMap:
    schema: str
    duration_seconds: float
    window_seconds: float
    stem_count: int
    sections: list[ArrangementSection] = field(default_factory=list)
    inference_source: str = "deterministic_activity_v1"
    semantic_labels_inferred: bool = False
    user_corrected: bool = False
    correction_schema: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _stem_activity(samples: list[float], sample_rate: int, window: int) -> list[bool]:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0:
        return []
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-9:
        return [False] * ((len(audio) + window - 1) // window)
    threshold = max(10.0 ** (-60.0 / 20.0), peak * 10.0 ** (-36.0 / 20.0))
    activity = []
    for start in range(0, len(audio), window):
        block = audio[start:start + window]
        rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
        activity.append(rms > threshold)
    # Bridge a single-window dropout between active neighbours. This suppresses
    # micro-sections from a breath or drum rest without deleting real entrances.
    bridged = activity[:]
    for index in range(1, len(activity) - 1):
        if not activity[index] and activity[index - 1] and activity[index + 1]:
            bridged[index] = True
    return bridged


def _density_band(ratio: float) -> str:
    if ratio == 0.0:
        return "silent"
    if ratio <= 0.25:
        return "sparse"
    if ratio <= 0.65:
        return "moderate"
    return "dense"


def infer_arrangement(
    prepared_stems: list[dict], *, window_seconds: float = 0.5
) -> ArrangementMap:
    """Segment a song when its active-stem set changes; never guess verse/chorus labels."""
    if not prepared_stems:
        return ArrangementMap(ARRANGEMENT_SCHEMA, 0.0, window_seconds, 0, [])
    sample_rates = {int(stem.get("sample_rate", 0)) for stem in prepared_stems}
    if len(sample_rates) != 1 or next(iter(sample_rates)) <= 0:
        raise ValueError("Arrangement inference requires one positive shared sample rate.")
    sample_rate = next(iter(sample_rates))
    window = max(1, int(sample_rate * window_seconds))
    max_samples = max(len(stem.get("samples", [])) for stem in prepared_stems)
    total_windows = (max_samples + window - 1) // window
    names = [str(stem.get("name", "unknown")) for stem in prepared_stems]
    if len(names) != len(set(names)):
        raise ValueError("Arrangement inference requires unique stem names.")
    activity_by_name = {
        # Pass the mono proxy (numpy) straight to _stem_activity, which converts
        # internally -- no caller-side .tolist()/list() round-trip. That copy was
        # measured at ~2.6s across roles + arrangement combined; see
        # docs/audits/2026-07-20-activity-analysis-list-roundtrip.md.
        name: _stem_activity(
            np.maximum(
                np.abs(np.asarray(stem.get("left_samples", []), dtype=np.float64)),
                np.abs(np.asarray(stem.get("right_samples", []), dtype=np.float64)),
            )
            if stem.get("stereo_preserved") else stem.get("samples", []),
            sample_rate,
            window,
        )
        for name, stem in zip(names, prepared_stems)
    }
    active_sets: list[tuple[str, ...]] = []
    for index in range(total_windows):
        active_sets.append(tuple(sorted(
            name for name in names
            if index < len(activity_by_name[name]) and activity_by_name[name][index]
        )))
    if not active_sets:
        return ArrangementMap(ARRANGEMENT_SCHEMA, 0.0, window_seconds, len(names), [])

    runs: list[tuple[int, int, tuple[str, ...]]] = []
    start = 0
    for index in range(1, len(active_sets) + 1):
        if index == len(active_sets) or active_sets[index] != active_sets[start]:
            runs.append((start, index, active_sets[start]))
            start = index

    sections = []
    previous: set[str] = set()
    for section_index, (start_window, end_window, active_tuple) in enumerate(runs, 1):
        active = set(active_tuple)
        entering = sorted(active - previous)
        exiting = sorted(previous - active)
        ratio = len(active) / len(names) if names else 0.0
        change_ratio = len(active.symmetric_difference(previous)) / len(names) if names else 0.0
        sections.append(ArrangementSection(
            section_id=f"section-{section_index:03d}",
            start_seconds=round(start_window * window_seconds, 3),
            end_seconds=round(min(max_samples / sample_rate, end_window * window_seconds), 3),
            active_stems=sorted(active),
            entering_stems=entering,
            exiting_stems=exiting,
            density_ratio=round(ratio, 4),
            density_band=_density_band(ratio),
            boundary_confidence=round(min(1.0, 0.5 + 0.5 * change_ratio), 4),
        ))
        previous = active

    # Merge sections that are shorter than 4.0 seconds if they have similar active sets
    min_duration = 4.0
    similarity_threshold = 0.70
    
    merged = True
    while merged:
        merged = False
        new_sections = []
        i = 0
        while i < len(sections):
            curr = sections[i]
            duration = curr.end_seconds - curr.start_seconds
            if duration < min_duration:
                best_neighbor_idx = None
                best_similarity = -1.0
                
                # Check left neighbor
                if i > 0:
                    left = sections[i - 1]
                    set_curr = set(curr.active_stems)
                    set_left = set(left.active_stems)
                    union_len = len(set_curr | set_left)
                    sim = len(set_curr & set_left) / union_len if union_len > 0 else 1.0
                    if sim >= similarity_threshold and sim > best_similarity:
                        best_similarity = sim
                        best_neighbor_idx = i - 1
                
                # Check right neighbor
                if i < len(sections) - 1:
                    right = sections[i + 1]
                    set_curr = set(curr.active_stems)
                    set_right = set(right.active_stems)
                    union_len = len(set_curr | set_right)
                    sim = len(set_curr & set_right) / union_len if union_len > 0 else 1.0
                    if sim >= similarity_threshold and sim > best_similarity:
                        best_similarity = sim
                        best_neighbor_idx = i + 1
                        
                if best_neighbor_idx is not None:
                    merged_with = sections[best_neighbor_idx]
                    new_start = min(curr.start_seconds, merged_with.start_seconds)
                    new_end = max(curr.end_seconds, merged_with.end_seconds)
                    new_active = sorted(set(curr.active_stems) | set(merged_with.active_stems))
                    
                    if best_neighbor_idx == i - 1:
                        new_sections[-1] = ArrangementSection(
                            section_id=left.section_id,
                            start_seconds=new_start,
                            end_seconds=new_end,
                            active_stems=new_active,
                            entering_stems=[],
                            exiting_stems=[],
                            density_ratio=0.0,
                            density_band="silent",
                            boundary_confidence=0.5,
                        )
                    else:
                        new_sections.append(ArrangementSection(
                            section_id=curr.section_id,
                            start_seconds=new_start,
                            end_seconds=new_end,
                            active_stems=new_active,
                            entering_stems=[],
                            exiting_stems=[],
                            density_ratio=0.0,
                            density_band="silent",
                            boundary_confidence=0.5,
                        ))
                        i += 1
                    
                    new_sections.extend(sections[i+1:])
                    sections = new_sections
                    merged = True
                    break
            
            new_sections.append(curr)
            i += 1
        
        if not merged:
            sections = new_sections

    # Re-compute section IDs, entering/exiting, density, boundary confidence
    final_sections = []
    previous_set = set()
    for index, sec in enumerate(sections, 1):
        active = set(sec.active_stems)
        entering = sorted(active - previous_set)
        exiting = sorted(previous_set - active)
        ratio = len(active) / len(names) if names else 0.0
        change_ratio = len(active.symmetric_difference(previous_set)) / len(names) if names else 0.0
        final_sections.append(ArrangementSection(
            section_id=f"section-{index:03d}",
            start_seconds=round(sec.start_seconds, 3),
            end_seconds=round(sec.end_seconds, 3),
            active_stems=sorted(active),
            entering_stems=entering,
            exiting_stems=exiting,
            density_ratio=round(ratio, 4),
            density_band=_density_band(ratio),
            boundary_confidence=round(min(1.0, 0.5 + 0.5 * change_ratio), 4),
        ))
        previous_set = active
    sections = final_sections

    return ArrangementMap(
        schema=ARRANGEMENT_SCHEMA,
        duration_seconds=round(max_samples / sample_rate, 3),
        window_seconds=window_seconds,
        stem_count=len(names),
        sections=sections,
    )


def validate_arrangement_correction_payload(corrections: object) -> dict:
    """Validate a complete manual timeline before a job is allowed into the queue."""
    if not isinstance(corrections, dict) or set(corrections) != {"schema", "sections"}:
        raise ValueError("Arrangement correction must contain exactly schema and sections.")
    if corrections.get("schema") != ARRANGEMENT_CORRECTION_SCHEMA:
        raise ValueError(f"Arrangement correction schema must be {ARRANGEMENT_CORRECTION_SCHEMA}.")
    sections = corrections.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_CORRECTED_SECTIONS:
        raise ValueError(
            f"Arrangement correction requires 1-{MAX_CORRECTED_SECTIONS} sections."
        )
    previous_end = 0.0
    normalized = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or set(section) != {
            "start_seconds", "end_seconds", "active_stems"
        }:
            raise ValueError(
                f"Arrangement correction sections[{index}] must contain exactly "
                "start_seconds, end_seconds, and active_stems."
            )
        start = section["start_seconds"]
        end = section["end_seconds"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(float(start))
            or not math.isfinite(float(end))
        ):
            raise ValueError(f"Arrangement correction sections[{index}] bounds must be finite.")
        start = float(start)
        end = float(end)
        if abs(start - previous_end) > 1e-6:
            raise ValueError("Arrangement correction sections must be contiguous from 0 seconds.")
        if end - start < MIN_CORRECTED_SECTION_SECONDS:
            raise ValueError(
                f"Arrangement correction sections must last at least "
                f"{MIN_CORRECTED_SECTION_SECONDS:.1f} seconds."
            )
        active = section["active_stems"]
        if (
            not isinstance(active, list)
            or len(active) > 32
            or any(not isinstance(name, str) or not name.strip() for name in active)
            or len(active) != len(set(active))
        ):
            raise ValueError(
                f"Arrangement correction sections[{index}].active_stems must contain "
                "unique non-empty stem names."
            )
        normalized.append({
            "start_seconds": round(start, 6),
            "end_seconds": round(end, 6),
            "active_stems": sorted(active),
        })
        previous_end = end
    return {"schema": ARRANGEMENT_CORRECTION_SCHEMA, "sections": normalized}


def apply_arrangement_corrections(
    inferred: ArrangementMap,
    corrections: dict | None,
    stem_names: list[str],
) -> ArrangementMap:
    """Replace an inferred timeline with one complete, validated producer timeline."""
    if corrections is None:
        return inferred
    payload = validate_arrangement_correction_payload(corrections)
    if len(stem_names) != len(set(stem_names)) or len(stem_names) != inferred.stem_count:
        raise ValueError("Arrangement correction requires every unique session stem name.")
    known = set(stem_names)
    referenced = {
        name for section in payload["sections"] for name in section["active_stems"]
    }
    unknown = sorted(referenced - known)
    if unknown:
        raise ValueError(f"Arrangement correction references unknown stem: {unknown[0]!r}.")
    corrected_end = float(payload["sections"][-1]["end_seconds"])
    if abs(corrected_end - inferred.duration_seconds) > 0.001:
        raise ValueError(
            "Arrangement correction must end at the inferred session duration "
            f"({inferred.duration_seconds:.3f} seconds)."
        )
    sections = []
    previous: set[str] = set()
    for index, corrected in enumerate(payload["sections"], 1):
        active = set(corrected["active_stems"])
        ratio = len(active) / inferred.stem_count if inferred.stem_count else 0.0
        sections.append(ArrangementSection(
            section_id=f"section-{index:03d}",
            start_seconds=corrected["start_seconds"],
            end_seconds=corrected["end_seconds"],
            active_stems=sorted(active),
            entering_stems=sorted(active - previous),
            exiting_stems=sorted(previous - active),
            density_ratio=round(ratio, 4),
            density_band=_density_band(ratio),
            boundary_confidence=1.0,
        ))
        previous = active
    return ArrangementMap(
        schema=ARRANGEMENT_SCHEMA,
        duration_seconds=inferred.duration_seconds,
        window_seconds=inferred.window_seconds,
        stem_count=inferred.stem_count,
        sections=sections,
        inference_source="user_correction_v1",
        semantic_labels_inferred=False,
        user_corrected=True,
        correction_schema=ARRANGEMENT_CORRECTION_SCHEMA,
    )
