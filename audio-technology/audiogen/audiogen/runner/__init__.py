import logging
import os
import secrets
import sys
from pathlib import Path
from typing import List, Optional

from audiogen_core.config import CONFIG
from data.music_data import EMOTIONS
from utils.startup_profiler import get_startup_profiler
from composition.engine import CompositionGenerator
from composition.arrangement_role_labels import arrangement_role_display_name

from runner.cli_args import parse_args
from runner.session import (
    setup_logging,
    discover_preset_families,
    print_preset_family_block,
    apply_startup_configs,
    resolve_drums_from_args,
    initialize_generator,
)
from runner.offline import (
    run_offline_promotion,
    run_offline_training,
    run_offline_mode_generation,
)
from runner.ui_realtime_cli import (
    prompt_mode_selection,
    prompt_preset_selection,
    prompt_style_selection,
    interactive_choose_conversation_style,
    interactive_choose_drums,
    run_generative_mode,
)

class AdapterComposer:
    def __init__(self, g, cfg):
        self.gen = g
        self.config = cfg
        self._song_gen = None
        self._last_arranged_song_segments = None
        self._last_arranged_song_render = None

    @staticmethod
    def _role_label(role: str) -> str:
        return arrangement_role_display_name(role)

    def _store_arrangement_segments(self, song, *, mode: str) -> None:
        try:
            if song is None or not getattr(song, "sections", None):
                self._last_arranged_song_segments = None
                return
            roles = None
            try:
                md = getattr(song, "metadata", None)
                if isinstance(md, dict):
                    roles = md.get("section_roles")
            except Exception:
                roles = None
            if not isinstance(roles, list) or not roles:
                from composition.policies import ArrangementPolicy
                seq = ArrangementPolicy._FORM_SEQUENCES.get(str(mode)) or ArrangementPolicy._FORM_SEQUENCES.get("default") or ()
                roles = [seq[i] if i < len(seq) else (seq[-1] if seq else "") for i in range(len(song.sections))]

            segs = []
            start_bar = 0
            for i, sec in enumerate(list(song.sections)):
                bars = int(getattr(sec, "bars", 0) or 0)
                if bars <= 0:
                    continue
                role = str(roles[i] if i < len(roles) else "") or ""
                segs.append(
                    {
                        "index": int(i),
                        "role": role,
                        "role_label": self._role_label(role),
                        "start_bar": int(start_bar),
                        "end_bar": int(start_bar + bars),
                        "bars": int(bars),
                        "emotion_name": str(getattr(sec, "emotion_name", "") or ""),
                        "root_note": int(getattr(sec, "root_note", 60) or 60),
                    }
                )
                start_bar += int(bars)
            self._last_arranged_song_segments = segs or None
        except Exception:
            self._last_arranged_song_segments = None

    def generate_section_events(
        self,
        emotion,
        root,
        bars,
        target_notes_per_bar=6.0,
        runtime_mode="normal",
        planner_effort=None,
        section_index: int = 0,
        transition_handoff_context=None,
    ):
        prev_effort = getattr(self.gen, "runtime_planner_effort_override", None)
        self.gen.runtime_generation_mode = runtime_mode
        if planner_effort:
            self.gen.runtime_planner_effort_override = str(planner_effort)
        try:
            return self.gen.generate_section(
                emotion,
                root,
                bars,
                target_notes_per_bar=target_notes_per_bar,
                section_index=section_index,
                transition_handoff_context=transition_handoff_context,
            )
        finally:
            try:
                self.gen.runtime_planner_effort_override = prev_effort
            except Exception:
                pass

    def _resolve_arranged_mode(self, emotion, mode: str, *, mutate_last: bool) -> str:
        """Resolve the configured arranged mode. Per-song form variety
        (docs/AUDIOGEN_COMPOSITION_PLAN.md item 2): when the mode is "auto", pick a
        structural form via a seeded, emotion-weighted choice so the continuous generative
        stream varies structure (not just notes) while staying emotion-appropriate. Any
        explicit mode is returned unchanged. `mutate_last` is True for the authoritative
        song build (advances the anti-repeat state) and False for the preview (which should
        mirror, not consume, that state)."""
        if str(mode or "").strip().lower() != "auto":
            return mode
        try:
            from data.arrangement_forms import select_arranged_form

            emo_name = str(getattr(emotion, "name", "neutral") or "neutral")
            try:
                form_seed = int(getattr(self.gen, "seed", None))
            except Exception:
                form_seed = None
            prev_form = str(getattr(self, "_last_arranged_form", "") or "")
            chosen = select_arranged_form(emo_name, seed=form_seed, avoid=prev_form)
            if mutate_last:
                self._last_arranged_form = chosen
            return chosen
        except Exception:
            return "default"

    def _maybe_vary_root(self, comp, emotion, root: int) -> int:
        """Return a per-song tonic offset from `root` for key variety.

        Coherent transposition: the whole song derives from one root, so moving
        the root moves melody, harmony and bass together. Disabled when key_lock
        is on. Deterministic per (emotion, call-count) so behaviour is testable,
        while still differing song-to-song. Avoids immediately repeating the
        previous key when configured.
        """
        try:
            if comp is None:
                return int(root)
            if not bool(getattr(comp, "key_variation_enabled", False)):
                return int(root)
            if bool(getattr(comp, "key_lock_enabled", False)):
                return int(root)  # key_lock intentionally pins the key center
            offsets = list(getattr(comp, "key_variation_root_offsets", None) or [0])
            offsets = [int(o) for o in offsets] or [0]
            if len(offsets) == 1:
                return int(root) + offsets[0]
            import random as _random

            counter = int(getattr(self, "_key_variation_counter", 0))
            self._key_variation_counter = counter + 1
            emo_name = str(getattr(emotion, "name", "") or "")
            rng = _random.Random(hash((emo_name, counter)) & 0x7FFFFFFF)
            choice = rng.choice(offsets)
            if bool(getattr(comp, "key_variation_avoid_immediate_repeat", True)):
                prev = getattr(self, "_last_key_offset", None)
                if prev is not None and choice == prev and len(offsets) > 1:
                    alt = [o for o in offsets if o != prev]
                    if alt:
                        choice = rng.choice(alt)
            self._last_key_offset = choice
            return int(root) + int(choice)
        except Exception:
            return int(root)

    def _maybe_jitter_tempo(self, comp, emotion, base_tempo_bpm: float) -> float:
        """Return a per-song +/- jittered base tempo for variety.

        Multiplies base_tempo_bpm (which later gets scaled by the emotion's own
        tempo_multiplier downstream), so this composes cleanly rather than
        fighting the emotion's intended tempo character.
        """
        try:
            if comp is None:
                return float(base_tempo_bpm)
            if not bool(getattr(comp, "tempo_variation_enabled", False)):
                return float(base_tempo_bpm)
            max_pct = float(getattr(comp, "tempo_variation_max_pct", 0.0) or 0.0)
            if max_pct <= 0:
                return float(base_tempo_bpm)
            import random as _random

            counter = int(getattr(self, "_tempo_variation_counter", 0))
            self._tempo_variation_counter = counter + 1
            emo_name = str(getattr(emotion, "name", "") or "")
            rng = _random.Random(hash((emo_name, "tempo", counter)) & 0x7FFFFFFF)
            pct = rng.uniform(-max_pct, max_pct)
            return float(base_tempo_bpm) * (1.0 + pct)
        except Exception:
            return float(base_tempo_bpm)

    def generate_arranged_song_events(self, emotion, root, runtime_mode="normal", *, fast_build=None):
        from composition.song_generator import SongGenerator
        import time

        logger = logging.getLogger(__name__)
        self.gen.runtime_generation_mode = runtime_mode

        comp = getattr(self.config, "composition", None)
        # Per-song key variation: transpose the whole song to a fresh tonic so
        # successive generations of the same emotion aren't always in C. Skipped
        # when key_lock is on (that feature intentionally pins the key center).
        root = self._maybe_vary_root(comp, emotion, int(root))
        mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
        mode = self._resolve_arranged_mode(emotion, mode, mutate_last=True)
        bars_per_section = int(getattr(comp, "bars_per_section", 16) or 16) if comp is not None else 16
        seconds = float(getattr(comp, "arranged_song_seconds", 150.0) or 150.0) if comp is not None else 150.0
        max_bars = int(getattr(comp, "arranged_song_max_bars", 64) or 64) if comp is not None else 64
        base_tempo_bpm = self._maybe_jitter_tempo(comp, emotion, 70.0)
        runtime_norm = str(runtime_mode or "normal").strip().lower()
        if fast_build is None:
            fast_build = runtime_norm not in {"normal", "full", "offline", "export"}
        if bool(fast_build):
            k = int(getattr(comp, "arranged_realtime_song_k", 1) or 1) if comp is not None else 1
            budget_s = float(getattr(comp, "arranged_realtime_pick_time_budget_s", 0.0) or 0.0) if comp is not None else 0.0
        else:
            k = int(getattr(comp, "arranged_song_k", 1) or 1) if comp is not None else 1
            budget_s = float(getattr(comp, "arranged_song_pick_time_budget_s", 2.0) or 2.0) if comp is not None else 2.0
            try:
                if comp is not None and bool(getattr(comp, "hook_safe_mode", False)) and int(k) <= 1:
                    k = 4
            except Exception:
                pass
        try:
            if comp is not None and not bool(getattr(comp, "whole_song_rerank_enabled", True)):
                k = 1
        except Exception:
            pass

        if self._song_gen is None:
            self._song_gen = SongGenerator(composer=self.gen)

        def _build_specs(form: str):
            f = (form or "default").strip().lower()
            base = getattr(emotion, "name", "neutral")
            if f in {"ambient"}:
                return SongGenerator.ambient_form(
                    str(base),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            if f in {"pop_ext"}:
                return SongGenerator.pop_ext_form(
                    str(base),
                    bars_per_section=int(bars_per_section),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            if f in {"pop"}:
                return SongGenerator.pop_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"rondo"}:
                return SongGenerator.rondo_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"ballad"}:
                return SongGenerator.ballad_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"wave"}:
                return SongGenerator.wave_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"anthem"}:
                return SongGenerator.anthem_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            return SongGenerator.default_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))

        specs = _build_specs(mode)
        total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
        if total_bars <= 0:
            ev = self.generate_section_events(emotion, root, bars_per_section, runtime_mode=runtime_mode, section_index=0)
            self._last_arranged_song_segments = None
            self._last_arranged_song_render = None
            return ev, int(bars_per_section)

        base_seed = None
        try:
            base_seed = int(getattr(self.gen, "seed", None))
        except Exception:
            base_seed = None
        if base_seed is None:
            try:
                base_seed = int(getattr(comp, "seed", None))
            except Exception:
                base_seed = None

        kk = max(1, int(k))
        if kk <= 1:
            start_fast = time.time()
            best = self._song_gen.generate_song(
                specs,
                base_tempo_bpm=float(base_tempo_bpm),
                arrangement_form=str(mode),
                seed=base_seed,
            )
            elapsed_fast = float(time.time() - start_fast)
            try:
                logger.info(
                    "Arranged song built (form=%s bars=%s fast_build=%s tried=1/%s time=%.2fs)",
                    str(mode),
                    int(sum(int(s.bars) for s in best.sections)),
                    bool(fast_build),
                    int(kk),
                    elapsed_fast,
                )
            except Exception:
                pass
            self._store_arrangement_segments(best, mode=str(mode))
            self._last_arranged_song_render = best
            return list(best.events or []), int(total_bars)

        start_t = time.time()
        best = None
        best_score = None
        tried = 0
        budget = max(0.0, float(budget_s))
        for i in range(kk):
            if tried >= 1 and budget > 1e-9 and (time.time() - start_t) >= budget:
                break
            seed_i = (int(base_seed) + int(i)) if base_seed is not None else None
            cand = self._song_gen.generate_song(
                specs,
                base_tempo_bpm=float(base_tempo_bpm),
                arrangement_form=str(mode),
                seed=seed_i,
            )
            tried += 1
            score_i = None
            try:
                score_i, details = self._song_gen._score_candidate_song(cand, arrangement_form=str(mode))
                score_i = float(score_i)
                if cand.metadata is None:
                    cand.metadata = {}
                cand.metadata["candidate_score"] = float(score_i)
                cand.metadata["candidate_details"] = dict(details or {})
            except Exception:
                score_i = None
            if best is None:
                best = cand
                best_score = score_i
            else:
                if score_i is not None and (best_score is None or float(score_i) > float(best_score)):
                    best = cand
                    best_score = float(score_i)

        assert best is not None
        elapsed = time.time() - start_t
        try:
            sec_bars = [int(s.bars) for s in best.sections]
            sec_emos = [str(getattr(s, "emotion_name", "") or "") for s in best.sections]
            logger.info(
                "Arranged song built (form=%s bars=%s sections=%s tried=%s/%s time=%.2fs score=%s emos=%s)",
                str(mode),
                int(sum(sec_bars)),
                sec_bars,
                int(tried),
                int(kk),
                float(elapsed),
                None if best_score is None else float(best_score),
                sec_emos,
            )
        except Exception:
            pass

        self._store_arrangement_segments(best, mode=str(mode))
        self._last_arranged_song_render = best

        return list(best.events or []), int(total_bars)

    def generate_arranged_preview_events(
        self,
        emotion,
        root,
        *,
        runtime_mode: str = "normal",
        preview_sections: int = 2,
    ):
        from composition.song_generator import SongGenerator
        import time

        self.gen.runtime_generation_mode = runtime_mode
        comp = getattr(self.config, "composition", None)
        mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
        mode = self._resolve_arranged_mode(emotion, mode, mutate_last=False)
        bars_per_section = int(getattr(comp, "bars_per_section", 16) or 16) if comp is not None else 16
        seconds = float(getattr(comp, "arranged_song_seconds", 150.0) or 150.0) if comp is not None else 150.0
        max_bars = int(getattr(comp, "arranged_song_max_bars", 64) or 64) if comp is not None else 64
        base_tempo_bpm = 70.0

        if self._song_gen is None:
            self._song_gen = SongGenerator(composer=self.gen)

        def _build_specs(form: str):
            f = (form or "default").strip().lower()
            base = getattr(emotion, "name", "neutral")
            if f in {"ambient"}:
                return SongGenerator.ambient_form(
                    str(base),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            if f in {"pop_ext"}:
                return SongGenerator.pop_ext_form(
                    str(base),
                    bars_per_section=int(bars_per_section),
                    root_note=int(root),
                    base_tempo_bpm=float(base_tempo_bpm),
                    target_seconds=float(seconds),
                    max_bars=int(max_bars),
                )
            if f in {"pop"}:
                return SongGenerator.pop_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"rondo"}:
                return SongGenerator.rondo_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"ballad"}:
                return SongGenerator.ballad_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"wave"}:
                return SongGenerator.wave_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            if f in {"anthem"}:
                return SongGenerator.anthem_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))
            return SongGenerator.default_form(str(base), bars_per_section=int(bars_per_section), root_note=int(root))

        specs = _build_specs(mode)
        n = max(1, int(preview_sections))
        specs = list(specs[:n]) if specs else []
        total_bars = int(sum(int(s.bars) for s in (specs or []))) if specs else 0
        if total_bars <= 0:
            ev = self.generate_section_events(emotion, root, bars_per_section, runtime_mode=runtime_mode, section_index=0)
            return ev, int(bars_per_section)

        preview_seed = None
        try:
            audio_cfg = getattr(self.config, "audio", None)
            rnd_preview = bool(getattr(audio_cfg, "cold_start_randomize_arranged_preview_seed", True)) if audio_cfg is not None else True
        except Exception:
            rnd_preview = True
        try:
            pinned = bool(getattr(comp, "user_pinned_seed", False)) if comp is not None else False
        except Exception:
            pinned = False
        if pinned:
            try:
                preview_seed = int(getattr(comp, "seed", None)) if comp is not None else None
            except Exception:
                preview_seed = None
        elif rnd_preview:
            try:
                preview_seed = int(secrets.randbits(32))
            except Exception:
                preview_seed = None

        orig_drng = getattr(self.gen, "deterministic_rng", None)
        wrapped = None
        try:
            if (
                (not pinned)
                and rnd_preview
                and (preview_seed is not None)
                and callable(orig_drng)
            ):
                salt = int(preview_seed)

                def _wrapped_drng(*tokens):
                    return orig_drng("preview_entropy", int(salt), *tokens)

                wrapped = _wrapped_drng
                setattr(self.gen, "deterministic_rng", wrapped)

            song = self._song_gen.generate_song(
                specs,
                base_tempo_bpm=float(base_tempo_bpm),
                arrangement_form=str(mode),
                seed=preview_seed,
            )
        finally:
            try:
                if wrapped is not None and callable(orig_drng):
                    setattr(self.gen, "deterministic_rng", orig_drng)
            except Exception:
                pass
        self._store_arrangement_segments(song, mode=str(mode))
        self._last_arranged_song_render = song
        return list(song.events or []), int(total_bars)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    setup_logging(verbose=bool(getattr(args, "verbose", False)), quiet=bool(getattr(args, "quiet", False)))

    _sprof = get_startup_profiler()
    _sprof.mark("argparse_done")

    if str(getattr(args, "offline_promote_run", "") or "").strip():
        rc = run_offline_promotion(args)
        _sprof.mark("offline_promotion_done")
        _sprof.report(title="startup marks (offline promotion)")
        return int(rc)

    if str(getattr(args, "offline_train", "none") or "none").strip().lower() not in {"", "none"}:
        rc = run_offline_training(args)
        _sprof.mark("offline_training_done")
        _sprof.report(title="startup marks (offline training)")
        return int(rc)

    list_flags = {
        "list_preset_families": bool(getattr(args, "list_preset_families", False)),
        "list_meta_presets": bool(getattr(args, "list_meta_presets", False)),
        "list_packs": bool(getattr(args, "list_packs", False)),
        "list_styles": bool(getattr(args, "list_styles", False)),
        "list_style_architectures": bool(getattr(args, "list_style_architectures", False)),
        "list_conversations": bool(getattr(args, "list_conversations", False)),
        "list_fx": bool(getattr(args, "list_fx", False)),
        "list_arrangements": bool(getattr(args, "list_arrangements", False)),
        "list_producer_macros": bool(getattr(args, "list_producer_macros", False)),
    }
    if any(list_flags.values()):
        fam = discover_preset_families(CONFIG)
        if list_flags["list_preset_families"]:
            print_preset_family_block("Meta presets", fam.get("meta_presets", []))
            print_preset_family_block("Sample packs", fam.get("sample_packs", []))
            print_preset_family_block("Style profiles", fam.get("style_profiles", []))
            print_preset_family_block("Style architectures", fam.get("style_architectures", []))
            print_preset_family_block("Conversation presets", fam.get("conversation_presets", []))
            print_preset_family_block("FX presets", fam.get("fx_presets", []))
            print_preset_family_block("Arrangement modes", fam.get("arrangement_modes", []))
            print_preset_family_block("Producer macros", fam.get("producer_macros", []))
            return 0
        if list_flags["list_meta_presets"]:
            print_preset_family_block("Meta presets", fam.get("meta_presets", []))
        if list_flags["list_packs"]:
            print_preset_family_block("Sample packs", fam.get("sample_packs", []))
        if list_flags["list_styles"]:
            print_preset_family_block("Style profiles", fam.get("style_profiles", []))
        if list_flags["list_style_architectures"]:
            print_preset_family_block("Style architectures", fam.get("style_architectures", []))
        if list_flags["list_conversations"]:
            print_preset_family_block("Conversation presets", fam.get("conversation_presets", []))
        if list_flags["list_fx"]:
            print_preset_family_block("FX presets", fam.get("fx_presets", []))
        if list_flags["list_arrangements"]:
            print_preset_family_block("Arrangement modes", fam.get("arrangement_modes", []))
        if list_flags["list_producer_macros"]:
            print_preset_family_block("Producer macros", fam.get("producer_macros", []))
        return 0

    preset_name = apply_startup_configs(args, CONFIG)

    mode = str(getattr(args, "mode", "") or "").strip().lower() or None
    if mode not in {"generative", "offline"}:
        mode = prompt_mode_selection()
    logging.info("Startup mode selected: %s", mode)

    preset_selected = (args.preset is None)
    chosen_preset = prompt_preset_selection(current=preset_name) if preset_selected else None
    if chosen_preset:
        from presets import load_preset
        from presets.config_applier import apply_macros_snapshot, apply_preset_to_config
        try:
            p = load_preset(str(chosen_preset))
            apply_preset_to_config(CONFIG, p)
            apply_macros_snapshot(CONFIG, dict(getattr(p, "macros", {}) or {}))
            preset_name = str(chosen_preset)
            logging.info("Loaded preset (interactive): %s", str(chosen_preset))
        except Exception:
            logging.exception("Failed to load preset (interactive): %s", str(chosen_preset))

    style_selected = (args.style is None)
    current_style = None
    try:
        current_style = str(getattr(CONFIG, "active_style_profile", "") or "").strip() or None
    except Exception:
        current_style = None
    chosen_style = prompt_style_selection(CONFIG, current=current_style) if style_selected else None
    if chosen_style:
        try:
            CONFIG.set_style_profile(str(chosen_style))
            logging.info("Loaded style profile (interactive): %s", str(chosen_style))
        except Exception:
            logging.exception("Failed to load style profile (interactive): %s", str(chosen_style))

    resolve_drums_from_args(CONFIG, args)
    interactive_choose_drums(CONFIG, args, mode=str(mode))

    if not args.conversation and not getattr(args, "ambient01", False):
        interactive_choose_conversation_style(CONFIG, args)

    try:
        CONFIG.rebuild_samplers()
    except Exception:
        pass

    _sprof.mark("after_rebuild_samplers")

    try:
        from utils.numba_warmup import warmup_numba_kernels
        warmup_numba_kernels(logging.getLogger(__name__))
    except Exception:
        pass

    # Realtime: async model load only (docs/AUDIOGEN_COMPOSITION_PLAN.md). Loads the ~196MB
    # retrained bundle off the construction thread; first sections use the default melody
    # path and upgrade once it lands. This is the only responsiveness tweak kept on by
    # default -- it does NOT change the playback architecture (arranged/ambient song
    # generation stays intact). Per-section streaming (arranged_songs_default=False) and
    # smaller preroll were reverted: forcing streaming broke ambient/arranged playback
    # (no audio). Those remain opt-in via config for a dedicated streaming driver.
    if mode == "generative":
        try:
            CONFIG.composition.melody_retrained_markov_async_load = True
        except Exception:
            pass

    gen = CompositionGenerator(enable_perf_monitoring=False)
    launch_seed = int(args.seed) if args.seed is not None else int(secrets.randbits(32))
    initialize_generator(args, CONFIG, gen, launch_seed)

    _sprof.mark("after_composition_generator")

    adapter = AdapterComposer(gen, CONFIG)

    if mode == "offline":
        rc = run_offline_mode_generation(args, CONFIG, adapter)
        _sprof.mark("offline_mode_done")
        _sprof.report(title="startup marks (offline)")
        return rc

    _sprof.mark("before_realtime_audio_boot")
    rc = run_generative_mode(args, CONFIG, gen, adapter, launch_seed, preset_name)
    _sprof.mark("after_player_start")
    _sprof.report(title="startup marks (realtime)")
    return rc
