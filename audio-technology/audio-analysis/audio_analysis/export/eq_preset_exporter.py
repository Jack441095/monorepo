"""EQ Preset Exporter for FabFilter Pro-Q 3 and Ableton EQ Eight.

Exports EQBand recommendations from the Audio Analysis DSP suite into:
1. FabFilter Pro-Q 3 compatible JSON/XML preset structures.
2. Ableton Live 12 EQ Eight parameter configurations.
3. Interactive SVG spectrum and EQ curve visualization data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ExportableBand:
    type: str  # "highpass", "lowpass", "peaking", "lowshelf", "highshelf", "notch"
    frequency: float
    gain_db: float = 0.0
    q: float = 0.707
    enabled: bool = True


class EQPresetExporter:
    """Export utility for multi-format EQ preset generation."""

    FILTER_TYPE_MAP_FABFILTER = {
        "highpass": "HighPass",
        "lowpass": "LowPass",
        "peaking": "Bell",
        "lowshelf": "LowShelf",
        "highshelf": "HighShelf",
        "notch": "Notch",
    }

    FILTER_TYPE_MAP_ABLETON = {
        "highpass": "Highpass48",
        "lowpass": "Lowpass48",
        "peaking": "Cutoff",
        "lowshelf": "Lowshelf",
        "highshelf": "Highshelf",
        "notch": "Notch",
    }

    def __init__(self, bands: list[ExportableBand | dict[str, Any]] | None = None):
        self.bands: list[ExportableBand] = []
        if bands:
            for b in bands:
                if isinstance(b, dict):
                    self.bands.append(ExportableBand(**b))
                else:
                    self.bands.append(b)

    def add_band(
        self,
        filter_type: str,
        frequency: float,
        gain_db: float = 0.0,
        q: float = 0.707,
        enabled: bool = True,
    ) -> EQPresetExporter:
        """Add a band to the exporter."""
        self.bands.append(
            ExportableBand(
                type=filter_type.lower(),
                frequency=frequency,
                gain_db=gain_db,
                q=q,
                enabled=enabled,
            )
        )
        return self

    def export_fabfilter_json(self) -> str:
        """Export preset payload structured for FabFilter Pro-Q 3 integration."""
        bands_data = []
        for i, band in enumerate(self.bands, start=1):
            bands_data.append({
                "index": i,
                "shape": self.FILTER_TYPE_MAP_FABFILTER.get(band.type, "Bell"),
                "frequency_hz": round(band.frequency, 2),
                "gain_db": round(band.gain_db, 2),
                "q_factor": round(band.q, 3),
                "enabled": band.enabled,
            })
        return json.dumps(
            {
                "plugin": "FabFilter Pro-Q 3",
                "version": "3.0",
                "band_count": len(bands_data),
                "bands": bands_data,
            },
            indent=2,
        )

    def export_ableton_eq_eight_dict(self) -> dict[str, Any]:
        """Export parameter map for Ableton Live 12 EQ Eight device."""
        eight_bands = []
        for i in range(8):
            if i < len(self.bands):
                b = self.bands[i]
                eight_bands.append({
                    "band_number": i + 1,
                    "on": b.enabled,
                    "mode": self.FILTER_TYPE_MAP_ABLETON.get(b.type, "Cutoff"),
                    "freq": round(b.frequency, 2),
                    "gain": round(b.gain_db, 2),
                    "q": round(b.q, 3),
                })
            else:
                eight_bands.append({
                    "band_number": i + 1,
                    "on": False,
                    "mode": "Cutoff",
                    "freq": 1000.0,
                    "gain": 0.0,
                    "q": 0.707,
                })

        return {
            "device": "Eq8",
            "band_count": 8,
            "bands": eight_bands,
        }

    def export_svg_curve(
        self, width: int = 800, height: int = 300, max_db: float = 18.0
    ) -> str:
        """Generate interactive SVG path representation of the EQ response curve."""
        import math

        num_points = 200
        points = []

        min_freq = 20.0
        max_freq = 20000.0
        log_min = math.log10(min_freq)
        log_max = math.log10(max_freq)

        for step in range(num_points):
            ratio = step / (num_points - 1)
            freq = 10.0 ** (log_min + ratio * (log_max - log_min))

            # Approximate total gain at frequency
            total_gain = 0.0
            for b in self.bands:
                if not b.enabled or b.type in ("highpass", "lowpass", "notch"):
                    continue
                # Simple Gaussian-like approximation for SVG visualization
                octaves = math.log2(freq / max(b.frequency, 1.0))
                bw = 1.0 / max(b.q, 0.1)
                gain = b.gain_db * math.exp(-0.5 * (octaves / max(bw, 0.1)) ** 2)
                total_gain += gain

            x = ratio * width
            y_ratio = 0.5 - (total_gain / (2.0 * max_db))
            y = max(0, min(height, y_ratio * height))
            points.append(f"{x:.1f},{y:.1f}")

        path_data = "M " + " L ".join(points)
        svg_content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" class="eq-curve-svg">'
            f'<line x1="0" y1="{height/2}" x2="{width}" y2="{height/2}" stroke="#444" stroke-dasharray="4" />'
            f'<path d="{path_data}" fill="none" stroke="#00f0ff" stroke-width="2" />'
            f"</svg>"
        )
        return svg_content
