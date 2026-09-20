# audio/RT_player/telemetry.py
# Project module `telemetry` (audio).

import time


class PlaybackTelemetry:
    """Tracks low-cost runtime health metrics for the real-time player."""

    def __init__(self, buffer_capacity: int, logger):
        self.buffer_capacity = buffer_capacity
        self.logger = logger
        self.buffer_underruns = 0
        self.stream_recovery_attempts = 0
        self.callback_count = 0
        self.callback_frames = 0
        self.callback_underflows = 0
        self.buffer_fill_ema = 0.0
        self.buffer_low_watermark = buffer_capacity
        self.buffer_high_watermark = 0
        self._last_status_log_time = 0.0
        self._telemetry_last_time = time.time()

    def note_stream_recovery_attempt(self):
        self.stream_recovery_attempts += 1

    def note_underrun(self):
        self.buffer_underruns += 1

    def note_callback_underflow(self):
        """PortAudio callback starvation (distinct from ring-buffer underruns)."""
        self.callback_underflows += 1

    def log_stream_status(self, status):
        if not status:
            return
        # Stream status can fire continuously under stress (under/overflows).
        # Keep it available for diagnosis, but don't spam normal runs.
        if not getattr(self.logger, "isEnabledFor", lambda *_: False)(10):  # logging.DEBUG == 10
            return
        now = time.time()
        if now - self._last_status_log_time >= 1.0:
            self.logger.debug("Audio stream status: %s", status)
            self._last_status_log_time = now

    def note_callback(
        self,
        frames: int,
        buffer_fill: int,
        target_buffer_bars: int,
        last_generation_time: float,
        max_generation_time: float,
    ):
        self.callback_count += 1
        self.callback_frames += max(0, int(frames))

        if self.callback_count == 1:
            self.buffer_fill_ema = float(buffer_fill)
            self.buffer_low_watermark = buffer_fill
            self.buffer_high_watermark = buffer_fill
        else:
            self.buffer_fill_ema = (0.92 * self.buffer_fill_ema) + (0.08 * float(buffer_fill))
            self.buffer_low_watermark = min(self.buffer_low_watermark, buffer_fill)
            self.buffer_high_watermark = max(self.buffer_high_watermark, buffer_fill)

        now = time.time()
        if now - self._telemetry_last_time >= 5.0:
            self.logger.debug(
                "Playback telemetry: avg_buffer=%.1f bars low=%d high=%d target=%d underruns=%d callback_underflows=%d last_gen=%.1fms max_gen=%.1fms",
                self.buffer_fill_ema,
                self.buffer_low_watermark,
                self.buffer_high_watermark,
                target_buffer_bars,
                self.buffer_underruns,
                self.callback_underflows,
                last_generation_time * 1000.0,
                max_generation_time * 1000.0,
            )
            self._telemetry_last_time = now
            self.buffer_low_watermark = buffer_fill
            self.buffer_high_watermark = buffer_fill

    def snapshot(self, buffer_fill: int, target_buffer_bars: int) -> dict:
        return {
            "buffer_fill": buffer_fill,
            "buffer_capacity": self.buffer_capacity,
            "buffer_underruns": self.buffer_underruns,
            "stream_recovery_attempts": self.stream_recovery_attempts,
            "callback_count": self.callback_count,
            "callback_frames": self.callback_frames,
            "callback_underflows": self.callback_underflows,
            "buffer_fill_avg": self.buffer_fill_ema,
            "buffer_low_watermark": self.buffer_low_watermark if self.callback_count else buffer_fill,
            "buffer_high_watermark": self.buffer_high_watermark,
            "target_buffer_bars": target_buffer_bars,
        }
