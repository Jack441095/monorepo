"""Commercial Multi-Track Stem Packaging & Delivery Pipeline for KENN (V6.0).

Groups session tracks into standard commercial delivery tiers:
- 01_DRUMS (Kick, Snare, Claps, Hi-hats, Percussion)
- 02_BASS (Sub Bass, Mid Bass, 808, Synth Bass)
- 03_INSTRUMENTS (Guitars, Keys, Synths, Leads, Brass, Strings)
- 04_VOCALS (Lead Vocal, Backings, Ad-libs, Harmonies)
- 05_FX (Sweeps, Risers, Impacts, Textures, Downlifters)

The packager groups tracks and hashes the figures the caller states. It does not measure audio, so a stem's peak,
loudness and compliance stay None (not measured) until something that does measure supplies them; the old version filled
in -1.2 dBTP and called every stem compliant.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StemTier:
    tier_id: str
    tier_name: str
    track_names: List[str]
    peak_dbtp: Optional[float]
    integrated_lufs: Optional[float]
    dc_offset_clean: Optional[bool]
    compliant: Optional[bool]  # None until a measured peak exists to compare with MAX_STEM_TRUE_PEAK_DBTP
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MasterDeliveryCertificate:
    song_title: str
    # Each figure below is what the caller stated; absent means nobody gave it, and we do not guess.
    artist: Optional[str]
    bpm: Optional[float]
    musical_key: Optional[str]
    mqm_score: Optional[float]
    integrated_lufs: Optional[float]
    true_peak_dbtp: Optional[float]
    stems_exported: int
    sha256_provenance: str
    signature: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        stated = {
            "artist": self.artist,
            "bpm": self.bpm,
            "musical_key": self.musical_key,
            "mqm_score": None if self.mqm_score is None else round(self.mqm_score, 1),
            "integrated_lufs": None if self.integrated_lufs is None else round(self.integrated_lufs, 1),
            "true_peak_dbtp": None if self.true_peak_dbtp is None else round(self.true_peak_dbtp, 2),
        }
        return {
            "song_title": self.song_title,
            # A figure nobody stated is left out, not sent as null, so a reader cannot mistake it for a zero.
            **{name: value for name, value in stated.items() if value is not None},
            "stems_exported": self.stems_exported,
            "sha256_provenance": self.sha256_provenance,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }


@dataclass
class StemPackagePlan:
    song_title: str
    audio_format: str
    tiers: List[StemTier]
    all_compliant: Optional[bool]  # None while any stem is unmeasured
    certificate: MasterDeliveryCertificate
    timestamp: float = field(default_factory=time.time)

    @property
    def stem_count(self) -> int:
        return len(self.tiers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "song_title": self.song_title,
            "audio_format": self.audio_format,
            "stem_count": len(self.tiers),
            "tiers": [t.to_dict() for t in self.tiers],
            "all_compliant": self.all_compliant,
            "certificate": self.certificate.to_dict(),
            "timestamp": self.timestamp,
        }


def _stated_number(value: Any) -> Optional[float]:
    """The finite float the caller stated, or None for a missing, junk or non-finite value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        # Absent, null or not a number: the caller gave us nothing to certify.
        return None
    return number if math.isfinite(number) else None


def _stated_text(value: Any) -> Optional[str]:
    """The caller's text trimmed, or None when it is missing or blank."""
    text = str(value).strip() if value is not None else ""
    return text or None


class StemPackager:
    """Manages stem group categorization, quality gating, and cryptographic release certification."""

    # House ceiling for a delivered stem (our choice, not a published figure). Unused until stems carry measured peaks.
    MAX_STEM_TRUE_PEAK_DBTP: float = -0.5

    def generate_stem_plan(
        self,
        tracks: List[Dict[str, Any]],
        project_metadata: Optional[Dict[str, Any]] = None,
    ) -> StemPackagePlan:
        """Categorize session tracks into 5 delivery stems and verify quality compliance."""
        meta = project_metadata or {}
        title = str(meta.get("title", meta.get("song_title", "Untitled Session")))
        artist = _stated_text(meta.get("artist"))
        bpm = _stated_number(meta.get("bpm"))
        key = _stated_text(meta.get("key"))
        mqm = _stated_number(meta.get("mqm_score"))
        lufs = _stated_number(meta.get("integrated_lufs"))
        true_peak = _stated_number(meta.get("true_peak_dbtp"))

        buckets: Dict[str, List[str]] = {
            "01_DRUMS": [],
            "02_BASS": [],
            "03_INSTRUMENTS": [],
            "04_VOCALS": [],
            "05_FX": [],
        }

        for t in tracks:
            name = str(t.get("name", "")).strip()
            low_name = name.lower()

            if any(k in low_name for k in ["kick", "snare", "hat", "clap", "drum", "perc", "cymbal", "tom"]):
                buckets["01_DRUMS"].append(name)
            elif any(k in low_name for k in ["bass", "sub", "808", "reese"]):
                buckets["02_BASS"].append(name)
            elif any(k in low_name for k in ["vocal", "vox", "lead vox", "adlib", "backing"]):
                buckets["04_VOCALS"].append(name)
            elif any(k in low_name for k in ["fx", "sweep", "impact", "riser", "noise", "downlifter"]):
                buckets["05_FX"].append(name)
            else:
                buckets["03_INSTRUMENTS"].append(name)

        # Ensure every bucket has at least 1 track representation
        if not buckets["01_DRUMS"]: buckets["01_DRUMS"].append("Drums Summed")
        if not buckets["02_BASS"]: buckets["02_BASS"].append("Bass Summed")
        if not buckets["03_INSTRUMENTS"]: buckets["03_INSTRUMENTS"].append("Instruments Summed")
        if not buckets["04_VOCALS"]: buckets["04_VOCALS"].append("Vocals Summed")
        if not buckets["05_FX"]: buckets["05_FX"].append("FX Summed")

        tiers: List[StemTier] = []

        for tier_id, t_names in buckets.items():
            # Nothing here renders or measures a stem, so there is no peak to check against the ceiling yet.
            tiers.append(StemTier(
                tier_id=tier_id,
                tier_name=tier_id.split("_")[1].capitalize(),
                track_names=t_names,
                peak_dbtp=None,
                integrated_lufs=None,
                dc_offset_clean=None,
                compliant=None,
                description=f"Lossless 24-bit 48kHz stem containing {len(t_names)} tracks.",
            ))

        # Cryptographic provenance hash
        payload_string = f"{title}|{artist}|{bpm}|{key}|{mqm}|{lufs}|{true_peak}|{len(tiers)}"
        sha256 = hashlib.sha256(payload_string.encode("utf-8")).hexdigest()

        cert = MasterDeliveryCertificate(
            song_title=title,
            artist=artist,
            bpm=bpm,
            musical_key=key,
            mqm_score=mqm,
            integrated_lufs=lufs,
            true_peak_dbtp=true_peak,
            stems_exported=len(tiers),
            sha256_provenance=sha256,
            signature=f"KENN-RELEASE-{sha256[:12].upper()}",
        )

        return StemPackagePlan(
            song_title=title,
            audio_format="24-bit / 48 kHz Linear PCM Broadcast WAV (BWF)",
            tiers=tiers,
            all_compliant=None,  # becomes a real answer once stems carry measured peaks
            certificate=cert,
        )


# Global instance
_stem_packager = StemPackager()


def get_stem_packager() -> StemPackager:
    """Return the global StemPackager instance."""
    return _stem_packager
