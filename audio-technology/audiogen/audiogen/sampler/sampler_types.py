# sampler/sampler_types.py
"""
Leaf-layer plain data types for the Sampler.

Split out of sampler.py (P4 giant-file decomposition): `VelocityLayer` has no
methods and no `self`-coupling to the Sampler class, so it forms part of the
lowest layer of the sampler package's internal call graph. Re-exported from
sampler.py unchanged, since external code imports it as
`from sampler.sampler import VelocityLayer`.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class VelocityLayer:
    """A single sample with its velocity range and loop points."""

    file_path: Path
    root_midi: int
    lo_vel: int = 0
    hi_vel: int = 127
    pitch_tracking: bool = False  # optional low‑pass filter
    filter_settings: Optional[Dict[str, float]] = None
    loop_start: int = 0
    loop_end: int = 0  # 0 = no looping
    start_offset: float = 0.0
    # ADSR can be overridden per layer (optional)
    adsr_attack: Optional[float] = None
    adsr_decay: Optional[float] = None
    adsr_sustain: Optional[float] = None
    adsr_release: Optional[float] = None
