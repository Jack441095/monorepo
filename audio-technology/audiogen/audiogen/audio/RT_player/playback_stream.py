import os
import threading


def _first_output_device_index(devices):
    for min_channels in (2, 1):
        for i, info in enumerate(devices or []):
            try:
                if int(info.get("max_output_channels", 0)) >= min_channels:
                    return int(i)
            except Exception:
                continue
    return None


def _device_options(devices):
    # Try default device first, then fall back to the first enumerated output device.
    options = [None]
    fallback_idx = _first_output_device_index(devices)
    if fallback_idx is not None:
        options.append(int(fallback_idx))
    return options


def _stream_start_options(devices):
    for device in _device_options(devices):
        for latency in ("high", "low", None):
            for prime in (True, False):
                yield device, latency, prime


class AudioOutputStream:
    """Thin wrapper around the optional sounddevice output stream."""

    def __init__(self, sd_module, sample_rate: int, blocksize: int, callback, logger):
        self._sd = sd_module
        self._sample_rate = sample_rate
        self._blocksize = blocksize
        self._callback = callback
        self._logger = logger
        # Stream lifecycle must be serialized. PortAudio callbacks run on a separate
        # thread; starting/stopping while a callback is in-flight can crash/hang.
        self._lifecycle_lock = threading.RLock()
        self.stream = None
        self.failed = False
        self.recovery_requested = False

    def _close_existing_stream(self):
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None

    def _query_devices(self):
        try:
            return self._sd.query_devices()
        except Exception:
            # If querying devices itself fails, fall back to the normal attempt loop.
            return None

    def _open_stream_with_fallbacks(self, devices):
        last_exc = None
        for device, latency, prime in _stream_start_options(devices):
            try:
                return self._sd.OutputStream(
                    samplerate=self._sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=self._blocksize,
                    latency=latency,
                    callback=self._callback,
                    prime_output_buffers_using_stream_callback=prime,
                    device=device,
                )
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        return None

    def start(self):
        with self._lifecycle_lock:
            if self.failed:
                return
            if os.getenv("AUDIOGEN_HEADLESS", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                self._logger.info("Audio stream disabled by AUDIOGEN_HEADLESS")
                self.failed = True
                self.stream = None
                return
            if self._sd is None:
                self._logger.warning("sounddevice not available; audio stream disabled")
                self.failed = True
                self.stream = None
                return
            try:
                self._close_existing_stream()
                # Try a few safe configurations. Some PortAudio backends/devices fail for
                # specific latency/priming combinations (especially on first open).
                # If PortAudio sees no devices (or default output is invalid), disable stream
                # gracefully so the app can still run (e.g. headless generation / sandbox).
                devices = self._query_devices()
                if devices is not None and len(devices) <= 0:
                    self._logger.warning("No audio output devices available; disabling audio stream")
                    self.failed = True
                    self.stream = None
                    return

                self.stream = self._open_stream_with_fallbacks(devices)
                if self.stream is None:
                    raise RuntimeError("Failed to create audio output stream")
                self.stream.start()
                self.failed = False
                self.recovery_requested = False
                self._logger.info("Audio stream started")
            except Exception:
                self._logger.exception("Failed to start audio stream")
                self.stream = None
                self.failed = True

    def stop(self):
        with self._lifecycle_lock:
            if self.stream is None:
                return
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                self._logger.exception("Stream shutdown warning")
            finally:
                self.stream = None

    def request_recovery(self):
        with self._lifecycle_lock:
            self.recovery_requested = True
