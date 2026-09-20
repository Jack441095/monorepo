# sampler/sampler_layers.py
"""
Layer-selection/routing logic for the Sampler.

Split out of sampler.py (P4 giant-file decomposition) as a mixin: these methods
only touch `self.layers` / `self._ordered_layers` / `self._layer_id_to_idx`
(built during `Sampler.__init__`), not the resampling/render state, so they
form a distinct mid-level layer of the sampler package's internal call graph,
above `sampler_types`/`sampler_kernels` and below `sampler_resample`/
`sampler_render`. Method bodies are moved verbatim (precise line-range
extraction) -- no behavior changes. `Sampler` mixes this class in; tests that
build a `Sampler` via `Sampler.__new__(Sampler)` and call these methods
directly keep working unchanged since MRO resolution is unaffected by which
file a method is defined in.
"""
from pathlib import Path
from typing import Tuple

from audiogen_core.config import SamplerConfiguration

from .sampler_types import VelocityLayer


class _LayerRoutingMixin:
    def _build_layers(self, config: SamplerConfiguration):
        """Build velocity layers from config (supports single or multiple layers)."""
        if hasattr(config, "velocity_layers") and config.velocity_layers:
            for layer_cfg in config.velocity_layers:
                self.layers.append(
                    VelocityLayer(
                        file_path=Path(layer_cfg["file"]),
                        root_midi=layer_cfg.get("root_midi", config.root_midi),
                        lo_vel=layer_cfg.get("lo_vel", 0),
                        hi_vel=layer_cfg.get("hi_vel", 127),
                        pitch_tracking=layer_cfg.get(
                            "pitch_tracking", config.use_pitch_tracking_lowpass
                        ),
                        filter_settings=layer_cfg.get("filter_settings"),
                        loop_start=layer_cfg.get("loop_start", 0),
                        loop_end=layer_cfg.get("loop_end", 0),
                        start_offset=layer_cfg.get(
                            "start_offset", getattr(config, "start_offset", 0.0)
                        ),
                        adsr_attack=layer_cfg.get("adsr_attack"),
                        adsr_decay=layer_cfg.get("adsr_decay"),
                        adsr_sustain=layer_cfg.get("adsr_sustain"),
                        adsr_release=layer_cfg.get("adsr_release"),
                    )
                )
        else:
            # Single layer
            self.layers.append(
                VelocityLayer(
                    file_path=Path(config.file_path),
                    root_midi=config.root_midi,
                    lo_vel=0,
                    hi_vel=127,
                    pitch_tracking=config.use_pitch_tracking_lowpass,
                    filter_settings=getattr(config, "filter_settings", None),
                    loop_start=getattr(config, "loop_start", 0),
                    loop_end=getattr(config, "loop_end", 0),
                    start_offset=getattr(config, "start_offset", 0.0),
                )
            )

    @staticmethod
    def _velocity_range_key(layer) -> Tuple[int, int]:
        lo = getattr(layer, "lo_vel", 0)
        hi = getattr(layer, "hi_vel", 127)
        return (lo, hi)

    def _rebuild_layer_route_cache(self) -> None:
        self._ordered_layers = tuple(sorted(self.layers, key=self._velocity_range_key))
        self._layer_id_to_idx = {id(lyr): i for i, lyr in enumerate(self.layers)}
        self._layer_cache_list_ref = self.layers

    def _ensure_layer_route_cache(self) -> None:
        if getattr(self, "_layer_cache_list_ref", None) is not self.layers:
            self._rebuild_layer_route_cache()

    def _ordered_velocity_layers(self) -> Tuple[VelocityLayer, ...]:
        self._ensure_layer_route_cache()
        return self._ordered_layers

    def _layer_index(self, layer: VelocityLayer) -> int:
        self._ensure_layer_route_cache()
        return self._layer_id_to_idx[id(layer)]

    def _select_layers_for_velocity(
        self, velocity: int
    ) -> Tuple[VelocityLayer, VelocityLayer, float, float]:
        """Return (lower_layer, upper_layer, weight_low, weight_up)."""
        ordered = self._ordered_velocity_layers()
        if not ordered:
            return None, None, 1.0, 0.0

        if not self.use_velocity_crossfade or len(ordered) == 1:
            for layer in ordered:
                if layer.lo_vel <= velocity <= layer.hi_vel:
                    return layer, layer, 1.0, 0.0
            # fallback to nearest
            return ordered[0], ordered[0], 1.0, 0.0

        # Crossfade between two adjacent layers
        centers = [(layer.lo_vel + layer.hi_vel) / 2.0 for layer in ordered]
        if velocity <= centers[0]:
            return ordered[0], ordered[0], 1.0, 0.0
        if velocity >= centers[-1]:
            return ordered[-1], ordered[-1], 1.0, 0.0

        for i in range(len(ordered) - 1):
            if centers[i] <= velocity <= centers[i + 1]:
                lower = ordered[i]
                upper = ordered[i + 1]
                span = centers[i + 1] - centers[i]
                if span <= 0:
                    return lower, lower, 1.0, 0.0
                w_up = (velocity - centers[i]) / span
                w_low = 1.0 - w_up
                return lower, upper, w_low, w_up
        return ordered[-1], ordered[-1], 1.0, 0.0
