# composition/harmonic_plan.py
"""
Read-only harmonic context for melody (and related monophonic) layers.

Harmony is planned on ``SectionPlan`` (chords, roots, voice-leading targets).
After voicing and lane shaping are stable, call ``SectionPlan.refresh_harmonic_plan()``
(or set ``harmonic_plan``) so downstream layers share one **immutable** snapshot.

**Contract:** once ``SectionPlan.harmonic_plan`` is set, melody/arp/counter should
prefer it over re-reading ``plan.chords`` / ``plan.chosen_*`` in parallel, so
lists cannot silently diverge. If you mutate harmony fields on the plan, call
``refresh_harmonic_plan()`` before the next consumer.

**Orchestration snapshot:** late passes (e.g. busy-section voicing trim before chord
comping) may change ``plan.chosen_chord`` after ``harmonic_plan`` was built. Call
``SectionPlan.refresh_harmonic_plan_comping()`` immediately before chord comping so
``harmonic_plan_comping`` matches the voicing actually sent to the chord layer; keep
``harmonic_plan`` as the snapshot those melodic layers consumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from .section_plan import SectionPlan


@dataclass(frozen=True)
class HarmonicPlan:
    """Immutable, bar-aligned harmony + voicing + register lanes."""

    chords: Tuple[str, ...]
    roots: Tuple[int, ...]
    bars: int
    beats_per_bar: float
    chosen_bass: Tuple[int, ...]
    chosen_melody: Tuple[int, ...]
    chosen_chord: Tuple[Tuple[int, ...], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "chords", tuple(str(c or "") for c in self.chords))
        object.__setattr__(self, "roots", tuple(int(x) for x in self.roots))
        object.__setattr__(self, "chosen_bass", tuple(int(x) for x in self.chosen_bass))
        object.__setattr__(self, "chosen_melody", tuple(int(x) for x in self.chosen_melody))
        cc = self.chosen_chord
        if cc:
            object.__setattr__(
                self,
                "chosen_chord",
                tuple(tuple(int(x) for x in row) for row in cc),
            )
        else:
            object.__setattr__(self, "chosen_chord", ())

    @classmethod
    def from_section_plan(cls, plan: "SectionPlan") -> "HarmonicPlan":
        """Snapshot from a prepared ``SectionPlan`` (post voicing / lane shaping)."""
        cc = getattr(plan, "chosen_chord", None) or []
        chord_voicings = tuple(tuple(int(x) for x in row) for row in cc) if cc else ()
        return cls(
            chords=tuple(str(c or "") for c in (plan.chords or [])),
            roots=tuple(int(x) for x in (plan.roots or [])),
            bars=int(plan.bars),
            beats_per_bar=float(plan.beats_per_bar),
            chosen_bass=tuple(int(x) for x in (plan.chosen_bass or [])),
            chosen_melody=tuple(int(x) for x in (plan.chosen_melody or [])),
            chosen_chord=chord_voicings,
        )

    def voiced_chords_as_lists(self) -> Optional[List[List[int]]]:
        """Mutable copy for APIs that expect ``List[List[int]]`` (e.g. Markov)."""
        if not self.chosen_chord:
            return None
        return [list(row) for row in self.chosen_chord]

    def slice_for_bar_range(self, start_bar: int, n_bars: int) -> "HarmonicPlan":
        """Return a new plan covering ``n_bars`` starting at ``start_bar`` (inclusive)."""
        s = max(0, int(start_bar))
        n = max(0, int(n_bars))
        if n <= 0 or s >= int(self.bars):
            return HarmonicPlan(
                chords=(),
                roots=(),
                bars=0,
                beats_per_bar=float(self.beats_per_bar),
                chosen_bass=(),
                chosen_melody=(),
                chosen_chord=(),
            )
        e = min(int(self.bars), s + n)
        sl = slice(s, e)
        cc = self.chosen_chord[sl] if self.chosen_chord else ()
        return HarmonicPlan(
            chords=self.chords[sl],
            roots=self.roots[sl],
            bars=int(e - s),
            beats_per_bar=float(self.beats_per_bar),
            chosen_bass=self.chosen_bass[sl],
            chosen_melody=self.chosen_melody[sl],
            chosen_chord=cc,
        )

    def validate(self) -> None:
        """Assert bar alignment and basic MIDI sanity."""
        b = int(self.bars)
        if b <= 0:
            raise ValueError("HarmonicPlan.bars must be positive")
        if float(self.beats_per_bar) <= 0:
            raise ValueError("HarmonicPlan.beats_per_bar must be positive")
        if len(self.chords) != b:
            raise ValueError(f"chords length {len(self.chords)} != bars {b}")
        if len(self.roots) != b:
            raise ValueError(f"roots length {len(self.roots)} != bars {b}")
        if len(self.chosen_bass) != b:
            raise ValueError(f"chosen_bass length {len(self.chosen_bass)} != bars {b}")
        if len(self.chosen_melody) != b:
            raise ValueError(f"chosen_melody length {len(self.chosen_melody)} != bars {b}")
        if self.chosen_chord and len(self.chosen_chord) != b:
            raise ValueError(f"chosen_chord length {len(self.chosen_chord)} != bars {b}")
        try:
            from midi.midi_range_limiter import RANGE_LIMITER

            for i in range(b):
                RANGE_LIMITER.clamp_note(int(self.chosen_bass[i]), 0)
                RANGE_LIMITER.clamp_note(int(self.chosen_melody[i]), 2)
        except Exception:
            pass
