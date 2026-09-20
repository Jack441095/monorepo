# composition/velocity_context.py
# ---------------------------------------------------------------------------
# Velocity chain transparency — diagnostic dataclass.
#
# The final lead velocity passes through 5+ multiplicative layers spread
# across emotion_profiles, section_role_profiles, arp_style_table,
# section_event_build, and melody_runtime.  ``VelocityContext`` captures
# each layer's contribution so the result can be inspected without
# trace-level logging.
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VelocityContext:
    """Records one velocity chain evaluation for auditing and debugging.

    Intended usage::

        ctx = VelocityContext(channel=2, bar=3)
        ctx.base_velocity = 82
        ctx.emotion_vel_mult = vel_m          # from stable_emotion_velocity_multiplier
        ctx.density_vel = density_vel          # from emotion.density
        ctx.velocity_scale = velocity_scale    # from arp_style_table / section curves
        ctx.articulation_vel_mult = vel_mult   # from melody articulation profiles
        ctx.section_dynamic = dyn              # from arrangement_curve

        final = ctx.compute()                  # → clamped int in [1, 127]
    """

    # Identity
    channel: int = 2
    bar: int = 0
    note_index: int = 0

    # Multiplier layers (default 1.0 = neutral)
    base_velocity: int = 82
    emotion_vel_mult: float = 1.0
    density_vel: float = 1.0
    velocity_scale: float = 1.0
    articulation_vel_mult: float = 1.0
    section_dynamic: float = 1.0

    # Result
    raw_product: float = field(init=False, default=0.0)
    final_velocity: int = field(init=False, default=0)

    def compute(self) -> int:
        """Multiply all layers and clamp to MIDI range [1, 127].

        Also stores intermediate results for diagnostic access.
        """
        # Emulate the exact double-truncation path from melody_runtime.py
        # to guarantee 100% backwards compatibility with old rendered values.
        base_calc = int(self.base_velocity * self.emotion_vel_mult)
        product = int(
            base_calc
            * self.density_vel
            * self.velocity_scale
            * self.articulation_vel_mult
            * self.section_dynamic
        )
        self.raw_product = (
            float(self.base_velocity)
            * self.emotion_vel_mult
            * self.density_vel
            * self.velocity_scale
            * self.articulation_vel_mult
            * self.section_dynamic
        )
        self.final_velocity = int(max(1, min(127, product)))
        return self.final_velocity

    def was_clamped(self) -> bool:
        """True when the raw product was outside [1, 127] and got clamped."""
        return self.raw_product < 1.0 or self.raw_product > 127.0

    def clamp_direction(self) -> Optional[str]:
        """Returns ``'floor'``, ``'ceiling'``, or ``None``."""
        if self.raw_product < 1.0:
            return "floor"
        if self.raw_product > 127.0:
            return "ceiling"
        return None

    def log_chain(self, level: int = logging.DEBUG) -> None:
        """Emit a compact single-line summary at the given log level."""
        if not logger.isEnabledFor(level):
            return
        clamp_tag = ""
        if self.was_clamped():
            clamp_tag = f" [CLAMPED {self.clamp_direction()}]"
        logger.log(
            level,
            "VelChain ch=%d bar=%d note=%d: base=%d × emo=%.3f × dens=%.3f "
            "× scale=%.3f × artic=%.3f × dyn=%.3f → raw=%.1f → final=%d%s",
            self.channel,
            self.bar,
            self.note_index,
            self.base_velocity,
            self.emotion_vel_mult,
            self.density_vel,
            self.velocity_scale,
            self.articulation_vel_mult,
            self.section_dynamic,
            self.raw_product,
            self.final_velocity,
            clamp_tag,
        )

    def as_dict(self) -> dict:
        """Flat dictionary for JSON/CSV export."""
        return {
            "channel": self.channel,
            "bar": self.bar,
            "note_index": self.note_index,
            "base_velocity": self.base_velocity,
            "emotion_vel_mult": round(self.emotion_vel_mult, 4),
            "density_vel": round(self.density_vel, 4),
            "velocity_scale": round(self.velocity_scale, 4),
            "articulation_vel_mult": round(self.articulation_vel_mult, 4),
            "section_dynamic": round(self.section_dynamic, 4),
            "raw_product": round(self.raw_product, 2),
            "final_velocity": self.final_velocity,
            "clamped": self.was_clamped(),
        }
