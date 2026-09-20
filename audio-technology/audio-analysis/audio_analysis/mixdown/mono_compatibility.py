"""Section-aware stereo and mono-fold evidence for AutoMix.

This module measures prepared source audio only. It never changes samples or
authorizes processing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


MONO_COMPATIBILITY_SCHEMA = "audio-too.mono-compatibility.v1"
_EPSILON = 1e-12
SPECTRAL_FRAME_SIZE = 8192
MAX_SPECTRAL_FRAMES_PER_SECTION = 8


@dataclass(frozen=True)
class MonoCompatibilitySection:
    section_id: str
    start_seconds: float
    end_seconds: float
    correlation: float | None
    fold_down_change_db: float | None
    side_energy_ratio: float
    low_frequency_side_ratio: float
    low_frequency_energy_ratio: float
    severity: str
    reasons: list[str]


@dataclass(frozen=True)
class StemMonoCompatibility:
    stem_name: str
    channel_layout: str
    measured: bool
    severity: str
    reasons: list[str]
    sections: list[MonoCompatibilitySection]


@dataclass(frozen=True)
class MonoCollapseContributor:
    stem_name: str
    score: float
    fold_down_improvement_db: float
    correlation_improvement: float
    low_frequency_side_reduction: float


@dataclass(frozen=True)
class SummedSpatialSection:
    section_id: str
    start_seconds: float
    end_seconds: float
    active_stems: list[str]
    correlation: float | None
    fold_down_change_db: float | None
    side_energy_ratio: float
    low_frequency_side_ratio: float
    low_frequency_energy_ratio: float
    severity: str
    reasons: list[str]
    contributors: list[MonoCollapseContributor]


@dataclass(frozen=True)
class MonoCompatibilityReport:
    schema: str
    low_frequency_boundary_hz: float
    spectral_frame_size: int
    max_spectral_frames_per_section: int
    status: str
    measured_stereo_stems: int
    warning_stems: int
    critical_stems: int
    stems: list[StemMonoCompatibility]
    summed_sections: list[SummedSpatialSection]
    problematic_summed_sections: int
    applies_automatically: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    left_centered = left - np.mean(left)
    right_centered = right - np.mean(right)
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denominator <= _EPSILON:
        return None
    return float(np.clip(np.dot(left_centered, right_centered) / denominator, -1.0, 1.0))


def _band_energy(signal: np.ndarray, sample_rate: int, boundary_hz: float) -> float:
    """Return deterministic bounded spectral energy across representative frames."""
    if signal.size < 2:
        return 0.0
    frame_size = min(signal.size, SPECTRAL_FRAME_SIZE)
    if signal.size <= frame_size:
        starts = [0]
    else:
        starts = sorted(set(
            int(value) for value in np.linspace(
                0, signal.size - frame_size,
                num=MAX_SPECTRAL_FRAMES_PER_SECTION,
            )
        ))
    window = np.hanning(frame_size)
    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    bins = frequencies <= min(boundary_hz, sample_rate / 2.0)
    energies = []
    for start in starts:
        spectrum = np.fft.rfft(signal[start:start + frame_size] * window)
        energies.append(float(np.sum(np.square(np.abs(spectrum[bins])))))
    return float(np.mean(energies)) if energies else 0.0


def _measure_section(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    section: dict,
    low_frequency_boundary_hz: float,
) -> MonoCompatibilitySection:
    start = max(0, int(float(section.get("start_seconds", 0.0)) * sample_rate))
    end = min(left.size, int(float(section.get("end_seconds", 0.0)) * sample_rate))
    section_id = str(section.get("section_id", ""))
    if not section_id or end <= start:
        raise ValueError("Mono compatibility requires valid non-empty arrangement sections.")
    section_left = left[start:end]
    section_right = right[start:end]
    mid = 0.5 * (section_left + section_right)
    side = 0.5 * (section_left - section_right)
    reference_power = max(
        float(np.mean(np.square(section_left))),
        float(np.mean(np.square(section_right))),
    )
    mid_power = float(np.mean(np.square(mid)))
    fold_change = None
    if reference_power > _EPSILON:
        fold_change = 10.0 * np.log10(max(mid_power, _EPSILON) / reference_power)
    total_ms_power = mid_power + float(np.mean(np.square(side)))
    side_ratio = 0.0 if total_ms_power <= _EPSILON else 1.0 - mid_power / total_ms_power
    low_mid = _band_energy(mid, sample_rate, low_frequency_boundary_hz)
    low_side = _band_energy(side, sample_rate, low_frequency_boundary_hz)
    low_total = low_mid + low_side
    low_side_ratio = 0.0 if low_total <= _EPSILON else low_side / low_total
    full_energy = (
        _band_energy(mid, sample_rate, sample_rate / 2.0)
        + _band_energy(side, sample_rate, sample_rate / 2.0)
    )
    low_energy_ratio = 0.0 if full_energy <= _EPSILON else low_total / full_energy
    correlation = _safe_correlation(section_left, section_right)

    reasons: list[str] = []
    severity = "pass"
    if fold_change is not None and fold_change <= -12.0:
        reasons.append("severe_fold_down_cancellation")
        severity = "critical"
    if correlation is not None and correlation <= -0.5:
        reasons.append("strong_negative_channel_correlation")
        severity = "critical"
    if low_side_ratio >= 0.65 and low_energy_ratio >= 0.10:
        reasons.append("low_frequency_energy_is_predominantly_side")
        severity = "critical"
    if severity != "critical":
        if fold_change is not None and fold_change <= -6.0:
            reasons.append("material_fold_down_loss")
        if correlation is not None and correlation <= -0.20:
            reasons.append("negative_channel_correlation")
        if low_side_ratio >= 0.35 and low_energy_ratio >= 0.05:
            reasons.append("elevated_low_frequency_width")
        if reasons:
            severity = "warning"

    return MonoCompatibilitySection(
        section_id=section_id,
        start_seconds=round(start / sample_rate, 6),
        end_seconds=round(end / sample_rate, 6),
        correlation=None if correlation is None else round(correlation, 4),
        fold_down_change_db=None if fold_change is None else round(float(fold_change), 3),
        side_energy_ratio=round(float(side_ratio), 4),
        low_frequency_side_ratio=round(float(low_side_ratio), 4),
        low_frequency_energy_ratio=round(float(low_energy_ratio), 4),
        severity=severity,
        reasons=reasons,
    )


def _aligned_channels(stem: dict, length: int) -> tuple[np.ndarray, np.ndarray]:
    """Return aligned source channels; mono sources are represented as dual mono."""
    if stem.get("stereo_preserved"):
        left = np.asarray(stem.get("left_samples", []), dtype=np.float64)
        right = np.asarray(stem.get("right_samples", []), dtype=np.float64)
    else:
        left = np.asarray(stem.get("samples", []), dtype=np.float64)
        right = left.copy()
    if left.shape != right.shape or left.size > length:
        raise ValueError(f"Prepared stem '{stem.get('name', '')}' has unaligned channels.")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError(f"Prepared stem '{stem.get('name', '')}' has non-finite channels.")
    if left.size < length:
        left = np.pad(left, (0, length - left.size))
        right = np.pad(right, (0, length - right.size))
    return left, right


def _numeric_improvement(candidate: float | None, baseline: float | None) -> float:
    if candidate is None or baseline is None:
        return 0.0
    return float(candidate - baseline)


def _summed_section_evidence(
    prepared_stems: list[dict],
    sections: list[dict],
    low_frequency_boundary_hz: float,
) -> list[SummedSpatialSection]:
    """Measure rough-source sum and attribute problems with leave-one-out evidence."""
    if not prepared_stems:
        return []
    sample_rates = {int(stem.get("sample_rate", 0)) for stem in prepared_stems}
    if len(sample_rates) != 1 or next(iter(sample_rates)) <= 0:
        raise ValueError("Summed spatial evidence requires one positive shared sample rate.")
    sample_rate = next(iter(sample_rates))
    length = max(
        max(len(stem.get("samples", [])), len(stem.get("left_samples", [])))
        for stem in prepared_stems
    )
    channels_by_name = {
        str(stem["name"]): _aligned_channels(stem, length) for stem in prepared_stems
    }
    reports: list[SummedSpatialSection] = []
    for section in sections:
        active_names = [str(name) for name in section.get("active_stems", [])]
        unknown = sorted(set(active_names) - set(channels_by_name))
        if unknown:
            raise ValueError(f"Arrangement references unknown active stems: {unknown}")
        if not active_names:
            continue
        start = max(0, int(float(section.get("start_seconds", 0.0)) * sample_rate))
        end = min(length, int(float(section.get("end_seconds", 0.0)) * sample_rate))
        if end <= start:
            raise ValueError("Mono compatibility requires valid non-empty arrangement sections.")
        # Slice first. Summing full multi-minute channels once per arrangement
        # section made runtime proportional to song_length * section_count even
        # though only one local range was measured.
        local_channels = {
            name: (
                channels_by_name[name][0][start:end],
                channels_by_name[name][1][start:end],
            )
            for name in active_names
        }
        summed_left = np.sum([local_channels[name][0] for name in active_names], axis=0)
        summed_right = np.sum([local_channels[name][1] for name in active_names], axis=0)
        local_section = {
            "section_id": str(section.get("section_id", "")),
            "start_seconds": 0.0,
            "end_seconds": (end - start) / sample_rate,
        }
        measured = _measure_section(
            summed_left, summed_right, sample_rate, local_section, low_frequency_boundary_hz
        )
        contributors: list[MonoCollapseContributor] = []
        if measured.severity != "pass" and len(active_names) >= 2:
            for name in active_names:
                without_left = summed_left - local_channels[name][0]
                without_right = summed_right - local_channels[name][1]
                without = _measure_section(
                    without_left, without_right, sample_rate, local_section,
                    low_frequency_boundary_hz,
                )
                fold_improvement = _numeric_improvement(
                    without.fold_down_change_db, measured.fold_down_change_db
                )
                correlation_improvement = _numeric_improvement(
                    without.correlation, measured.correlation
                )
                low_reduction = measured.low_frequency_side_ratio - without.low_frequency_side_ratio
                score = (
                    0.5 * min(1.0, max(0.0, fold_improvement) / 12.0)
                    + 0.2 * min(1.0, max(0.0, correlation_improvement) / 2.0)
                    + 0.3 * min(1.0, max(0.0, low_reduction))
                )
                if score > 0.0:
                    contributors.append(MonoCollapseContributor(
                        stem_name=name,
                        score=round(score, 4),
                        fold_down_improvement_db=round(fold_improvement, 3),
                        correlation_improvement=round(correlation_improvement, 4),
                        low_frequency_side_reduction=round(float(low_reduction), 4),
                    ))
        contributors.sort(key=lambda item: (-item.score, item.stem_name))
        reports.append(SummedSpatialSection(
            section_id=measured.section_id,
            start_seconds=round(start / sample_rate, 6),
            end_seconds=round(end / sample_rate, 6),
            active_stems=active_names,
            correlation=measured.correlation,
            fold_down_change_db=measured.fold_down_change_db,
            side_energy_ratio=measured.side_energy_ratio,
            low_frequency_side_ratio=measured.low_frequency_side_ratio,
            low_frequency_energy_ratio=measured.low_frequency_energy_ratio,
            severity=measured.severity,
            reasons=measured.reasons,
            contributors=contributors,
        ))
    return reports


def analyze_mono_compatibility(
    prepared_stems: list[dict],
    arrangement: dict,
    *,
    low_frequency_boundary_hz: float = 120.0,
) -> MonoCompatibilityReport:
    """Measure stereo fold-down safety per arrangement section."""
    if not np.isfinite(low_frequency_boundary_hz) or low_frequency_boundary_hz <= 0.0:
        raise ValueError("Low-frequency boundary must be a positive finite value.")
    sections = arrangement.get("sections", []) if isinstance(arrangement, dict) else []
    if prepared_stems and not sections:
        raise ValueError("Mono compatibility requires an Arrangement v1 section timeline.")

    stem_reports: list[StemMonoCompatibility] = []
    for stem in prepared_stems:
        name = str(stem.get("name", ""))
        sample_rate = int(stem.get("sample_rate", 0))
        if not name or sample_rate <= 0:
            raise ValueError("Mono compatibility requires named stems with positive sample rates.")
        if not stem.get("stereo_preserved"):
            stem_reports.append(StemMonoCompatibility(name, "mono", False, "not_applicable", [], []))
            continue
        left = np.asarray(stem.get("left_samples", []), dtype=np.float64)
        right = np.asarray(stem.get("right_samples", []), dtype=np.float64)
        if left.size == 0 or left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError(f"Prepared stereo stem '{name}' has invalid or unaligned channels.")
        measured_sections = [
            _measure_section(left, right, sample_rate, section, low_frequency_boundary_hz)
            for section in sections
            if name in section.get("active_stems", [])
        ]
        severity = "pass"
        if any(item.severity == "critical" for item in measured_sections):
            severity = "critical"
        elif any(item.severity == "warning" for item in measured_sections):
            severity = "warning"
        reasons = sorted({reason for item in measured_sections for reason in item.reasons})
        stem_reports.append(StemMonoCompatibility(
            name, "stereo", True, severity, reasons, measured_sections
        ))

    measured = [stem for stem in stem_reports if stem.measured]
    critical = sum(stem.severity == "critical" for stem in measured)
    warnings = sum(stem.severity == "warning" for stem in measured)
    summed_sections = _summed_section_evidence(
        prepared_stems, sections, low_frequency_boundary_hz
    )
    summed_critical = any(item.severity == "critical" for item in summed_sections)
    summed_warning = any(item.severity == "warning" for item in summed_sections)
    status = (
        "critical" if critical or summed_critical
        else "warning" if warnings or summed_warning
        else "pass"
    )
    return MonoCompatibilityReport(
        schema=MONO_COMPATIBILITY_SCHEMA,
        low_frequency_boundary_hz=float(low_frequency_boundary_hz),
        spectral_frame_size=SPECTRAL_FRAME_SIZE,
        max_spectral_frames_per_section=MAX_SPECTRAL_FRAMES_PER_SECTION,
        status=status,
        measured_stereo_stems=len(measured),
        warning_stems=warnings,
        critical_stems=critical,
        stems=stem_reports,
        summed_sections=summed_sections,
        problematic_summed_sections=sum(
            item.severity != "pass" for item in summed_sections
        ),
    )
