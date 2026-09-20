from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArrangementConfiguration:
    # Section sizing (used by arranged forms + live scheduler)
    bars_per_section: int = 16
    phrases_per_section: int = 4

    # Bass entrance policies (arrangement-level)
    bass_wait_for_first_chorus: bool = True
    # Default form: bring bass in after N full sections (bars_per_section each).
    bass_entry_delay_sections_default: int = 1

    # Arranged song mode controls
    arranged_songs_default: bool = True
    arranged_song_loop: bool = True
    # When looping arranged songs, re-seed and reset per-song memories so bar 33
    # doesn't replay bar 1 verbatim.
    arranged_song_continuous: bool = True
    # Large step so each loop is audibly different even with deterministic sub-RNGs.
    arranged_song_loop_seed_step: int = 10_000_019
    # default | pop_ext | rondo | ballad | wave | ambient
    arranged_song_mode: str = "default"
    arranged_song_seconds: float = 150.0
    arranged_song_max_bars: int = 64
    arranged_song_k: int = 3
    arranged_disable_emotion_arc: bool = True
    arranged_song_pick_time_budget_s: float = 2.0
    arranged_emotion_switch_fast_chunk: bool = True
    # Arranged cold-start / preview: fewer sections = faster first sound after picking an emotion.
    arranged_emotion_switch_preview_sections: int = 2
    # When True, realtime arranged playback builds the full form timeline on cold start,
    # on arranged-loop pre-generation (even when buffer runway is low), and skips the
    # safe/emergency arranged preview fallback. False keeps shorter preview chunks for
    # faster first sound and lighter CPU under pressure.
    arranged_realtime_full_timeline: bool = False
    # Bars before section end to start pre-generating the next arranged loop (RT).
    arranged_loop_pregen_lead_bars: int = 6
    # After an arranged loop swap, warm chord cache + mix/master in the background.
    arranged_loop_handoff_prewarm: bool = True
    # If True, manual emotion switches in arranged-song mode will keep the current
    # arrangement role (e.g. switch while hearing CHORUS → start the new emotion at CHORUS).
    # If no role mapping exists, falls back to the normal start-of-form behavior.
    arranged_emotion_switch_keep_role: bool = True

    # Arranged-song looping: apply a master fade-out over the last N bars before
    # the next arranged song is activated (0 disables).
    arranged_song_end_fade_out_bars: int = 2
    # Do not apply that master fade unless the arranged timeline is at least this many
    # bars long. Short timelines (preview chunks, tight max_bars) otherwise treat the
    # last N bars as "song end" even when they are still early form roles (e.g. first verse),
    # which reads as an unintended dip at intro→verse.
    arranged_song_end_fade_min_total_bars: int = 20

    # Ambient form: how long to hold a chord template (bars)
    ambient_chord_hold_bars: int = 1
