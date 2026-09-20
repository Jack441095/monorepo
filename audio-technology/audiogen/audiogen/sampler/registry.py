import threading
from typing import Dict

MONOPHONIC_CHANNEL_NAMES = frozenset({"bass", "melody", "arp", "drone", "counter_melody"})


class SamplerRegistry:
    """Owns lazy sampler loading and monophonic renderer registration."""

    def __init__(self, config, sample_rate: int, sampler_factory, mono_renderer_factory):
        self.config = config
        self.sample_rate = sample_rate
        self.sampler_factory = sampler_factory
        self.mono_renderer_factory = mono_renderer_factory
        self.samplers: Dict[str, object] = {}
        self.mono_renderers: Dict[str, object] = {}
        self._load_lock = threading.Lock()
        self._loading_events: Dict[str, threading.Event] = {}
        self._load_errors: Dict[str, Exception] = {}

    def _attach_monophonic_if_needed(self, name: str, sampler) -> None:
        """Register MonophonicRenderer when a channel becomes monophonic after initial load."""
        if name not in MONOPHONIC_CHANNEL_NAMES:
            return
        with self._load_lock:
            if name in self.mono_renderers:
                return
            self.mono_renderers[name] = self.mono_renderer_factory(
                sampler, self.sample_rate
            )

    def get_sampler(self, name: str):
        sampler = self.samplers.get(name)
        if sampler is not None:
            self._attach_monophonic_if_needed(name, sampler)
            return sampler

        with self._load_lock:
            sampler = self.samplers.get(name)
            if sampler is not None:
                self._attach_monophonic_if_needed(name, sampler)
                return sampler

            wait_event = self._loading_events.get(name)
            if wait_event is None:
                wait_event = threading.Event()
                self._loading_events[name] = wait_event
                should_load = True
            else:
                should_load = False

        if should_load:
            try:
                sampler_config = next(
                    (sc for sc in self.config.samplers if sc.name == name), None
                )
                if sampler_config is None:
                    raise ValueError(f"No sampler config for '{name}'")
                sampler = self.sampler_factory(
                    sampler_config, sample_rate=self.sample_rate
                )
                mono_renderer = (
                    self.mono_renderer_factory(sampler, self.sample_rate)
                    if name in MONOPHONIC_CHANNEL_NAMES
                    else None
                )
                with self._load_lock:
                    self.samplers[name] = sampler
                    if mono_renderer is not None:
                        self.mono_renderers[name] = mono_renderer
                    self._load_errors.pop(name, None)
                    self._loading_events.pop(name, None)
                    wait_event.set()
                return sampler
            except Exception as exc:
                with self._load_lock:
                    self._load_errors[name] = exc
                    self._loading_events.pop(name, None)
                    wait_event.set()
                raise

        wait_event.wait()
        with self._load_lock:
            sampler = self.samplers.get(name)
            if sampler is not None:
                self._attach_monophonic_if_needed(name, sampler)
                return sampler
            exc = self._load_errors.get(name)
        if exc is not None:
            raise exc
        raise RuntimeError(f"Sampler '{name}' failed to load")

    def get_monophonic_renderer(self, name: str):
        return self.mono_renderers.get(name)

    def drop_sampler(self, name: str) -> bool:
        """
        Forget a cached sampler instance so it will be lazily reloaded next time.

        This is safe to call at runtime to refresh instrument definitions after
        preset/pack changes, while optionally keeping specific samplers alive
        (e.g. keep the drone continuous).
        """
        if not name:
            return False
        with self._load_lock:
            existed = name in self.samplers
            self.samplers.pop(name, None)
            self.mono_renderers.pop(name, None)
            self._load_errors.pop(name, None)
            ev = self._loading_events.pop(name, None)
            try:
                if ev is not None:
                    ev.set()
            except Exception:
                pass
        return bool(existed)

    def drop_all_except(self, keep: set[str]) -> int:
        """
        Drop all cached samplers except those in `keep`.

        Returns number of samplers dropped.
        """
        keep = {str(k) for k in (keep or set()) if str(k)}
        with self._load_lock:
            names = list(self.samplers.keys())
        dropped = 0
        for n in names:
            if n in keep:
                continue
            if self.drop_sampler(n):
                dropped += 1
        return int(dropped)

