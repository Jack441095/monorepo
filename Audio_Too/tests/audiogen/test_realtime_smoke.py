import time


def test_realtime_smoke_start_stop():
    """
    Minimal regression test for the simplified project shape:
    - Markov composition engine imports
    - AudioContainer wires 6 mixer channels
    - PolyphonicPlayer can start, load an emotion, and stop without crashing

    This test is intentionally tolerant of environments with no audio devices:
    the player will run in headless mode when `sounddevice` is unavailable.
    """

    from audiogen_core.config import CONFIG
    from data.music_data import EMOTIONS
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer
    from composition.engine import CompositionGenerator

    # Keep the test fast and avoid long warmups.
    CONFIG.set_performance_mode("balanced")
    CONFIG.audio.target_buffer_bars = 2
    CONFIG.audio.startup_preroll_bars = 1
    CONFIG.audio.gen_burst_max_bars = 2
    # Arranged mode: keep the generated preview/song short so the smoke test
    # stays fast while still exercising multi-section scheduling.
    try:
        CONFIG.composition.arranged_songs_default = True
        CONFIG.composition.arranged_song_mode = "ambient"
        CONFIG.composition.arranged_song_seconds = 18.0
        CONFIG.composition.arranged_song_max_bars = 20
        CONFIG.composition.arranged_song_k = 1
        CONFIG.composition.arranged_song_pick_time_budget_s = 0.25
    except Exception:
        pass

    # Ensure samplers are consistent after any config changes.
    try:
        CONFIG.rebuild_samplers()
    except Exception:
        pass

    container = AudioContainer.create_from_config(CONFIG)
    assert container.mixer is not None
    # 7 channels: bass/chords/melody/arp/drone/counter_melody + chorus kick strip
    for ch in range(7):
        assert container.mixer.get_channel(ch) is not None

    gen = CompositionGenerator(enable_perf_monitoring=False)

    class _Adapter:
        def __init__(self, g, cfg):
            self.gen = g
            self.config = cfg
            self._song_gen = None

        def generate_section_events(
            self,
            emotion,
            root,
            bars,
            target_notes_per_bar=6.0,
            runtime_mode="normal",
            section_index=0,
            transition_handoff_context=None,
        ):
            self.gen.runtime_generation_mode = runtime_mode
            return self.gen.generate_section(
                emotion,
                root,
                bars,
                target_notes_per_bar=target_notes_per_bar,
                section_index=section_index,
                transition_handoff_context=transition_handoff_context,
            )

        def generate_arranged_song_events(self, emotion, root, runtime_mode="normal"):
            from composition.song_generator import SongGenerator

            self.gen.runtime_generation_mode = runtime_mode
            comp = getattr(self.config, "composition", None)
            mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
            seconds = float(getattr(comp, "arranged_song_seconds", 18.0) or 18.0) if comp is not None else 18.0
            max_bars = int(getattr(comp, "arranged_song_max_bars", 20) or 20) if comp is not None else 20
            base_tempo_bpm = 70.0

            if self._song_gen is None:
                self._song_gen = SongGenerator(composer=self.gen)

            base = getattr(emotion, "name", "neutral")
            if str(mode).strip().lower() == "ambient":
                specs = SongGenerator.ambient_form(
                    str(base),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            else:
                specs = SongGenerator.default_form(str(base), bars_per_section=8, root_note=int(root))
            song = self._song_gen.generate_song(specs, base_tempo_bpm=float(base_tempo_bpm), arrangement_form=str(mode), seed=0)
            total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
            return list(song.events or []), int(total_bars)

        def generate_arranged_preview_events(self, emotion, root, *, runtime_mode="normal", preview_sections: int = 2):
            from composition.song_generator import SongGenerator

            self.gen.runtime_generation_mode = runtime_mode
            comp = getattr(self.config, "composition", None)
            mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
            seconds = float(getattr(comp, "arranged_song_seconds", 18.0) or 18.0) if comp is not None else 18.0
            max_bars = int(getattr(comp, "arranged_song_max_bars", 20) or 20) if comp is not None else 20
            base_tempo_bpm = 70.0

            if self._song_gen is None:
                self._song_gen = SongGenerator(composer=self.gen)

            base = getattr(emotion, "name", "neutral")
            if str(mode).strip().lower() == "ambient":
                specs = SongGenerator.ambient_form(
                    str(base),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            else:
                specs = SongGenerator.default_form(str(base), bars_per_section=8, root_note=int(root))
            n = max(1, int(preview_sections))
            specs = list(specs[:n]) if specs else []
            song = self._song_gen.generate_song(specs, base_tempo_bpm=float(base_tempo_bpm), arrangement_form=str(mode), seed=0)
            total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
            return list(song.events or []), int(total_bars)

    player = PolyphonicPlayer(_Adapter(gen, CONFIG), CONFIG, container=container)
    player.start()
    try:
        player.load_emotion(0 if EMOTIONS else 0, 60)
        time.sleep(0.6)
        stats = player.get_stats()
        assert isinstance(stats, dict)
        # Sanity: arranged mode yields a multi-section timeline (not a single loop).
        ev, bars = player.composer.generate_arranged_song_events(EMOTIONS[0], 60, runtime_mode="balanced")
        assert isinstance(ev, list)
        assert int(bars) > 4
    finally:
        player.stop()

