from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Region:
    start_bar: int
    bars: int
    emotion: str = "neutral"
    root: int = 60
    seed: Optional[int] = None
    arrangement_role: str = "A"
    macros: Dict[str, float] = field(default_factory=dict)


@dataclass
class Timeline:
    regions: List[Region] = field(default_factory=list)
    loop: bool = True
    playhead_bar: int = 0

    def total_bars(self) -> int:
        if not self.regions:
            return 0
        return max(int(r.start_bar) + int(r.bars) for r in self.regions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loop": bool(self.loop),
            "playhead_bar": int(self.playhead_bar),
            "regions": [
                {
                    "start_bar": int(r.start_bar),
                    "bars": int(r.bars),
                    "emotion": str(r.emotion),
                    "root": int(r.root),
                    "seed": None if r.seed is None else int(r.seed),
                    "arrangement_role": str(r.arrangement_role or ""),
                    "macros": {str(k): float(v) for k, v in dict(r.macros or {}).items()},
                }
                for r in (self.regions or [])
            ],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Timeline":
        regs = []
        for rr in list((d or {}).get("regions", []) or []):
            try:
                r = dict(rr or {})
                regs.append(
                    Region(
                        start_bar=int(r.get("start_bar", 0) or 0),
                        bars=int(r.get("bars", 16) or 16),
                        emotion=str(r.get("emotion", "neutral") or "neutral"),
                        root=int(r.get("root", 60) or 60),
                        seed=(None if r.get("seed", None) is None else int(r.get("seed"))),
                        arrangement_role=str(r.get("arrangement_role", "A") or "A"),
                        macros={str(k): float(v) for k, v in dict(r.get("macros", {}) or {}).items()},
                    )
                )
            except Exception:
                continue
        tl = Timeline(
            regions=regs,
            loop=bool((d or {}).get("loop", True)),
            playhead_bar=int((d or {}).get("playhead_bar", 0) or 0),
        )
        return tl

