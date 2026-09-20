# main_llm_chorus_only.py - J K Gandy 2026

#///////////////////////////////////////////////////////////
# This is the main entry point for the generative audio composition system.
# It initializes the audio context, loads trained AI models if available, and starts the interactive command loop
# for generating music based on emotional profiles. It also includes a status display thread to show current emotion,
# buffer status, and other relevant information. The composition generation is handled by the
# CompositionGenerator class, which can use Transformer models for chord and melody generation,
# as well as rule-based methods and chord substitutions. The system is designed 
# to be modular and extensible, to allow for future integration of additional AI models and features.
# This entry point is specifically designed to generate only chorus-like sections for each emotion,
# and is used by the `PolyphonicPlayer` to create a looping chorus-only loop.
# Realtime playback defaults to arranged timelines filtered to chorus-like roles (``b`` / hook / tag);
# pass ``--full-arrangement`` to hear intro→verse→… like main.py.
#
# Mix defaults: conversation layer matches startup ``default_ambient_01`` (ambient 01) unless you pass
# ``--conversation`` / ``--ambient01``; chorus kick and sidechain ducking are always off in this entry point.
#
# LLM / automation (no interactive player):
#   python main_llm_chorus_only.py --list-emotions-json
#   python main_llm_chorus_only.py --chorus-phrase-json --emotion joy --phrase-bars 4 --root 60
#   python main_llm_chorus_only.py --ambient01
#   python main_llm_chorus_only.py --list-conversations
# TTY phrase REPL (no player):  python main_llm_chorus_only.py --phrase-console
# Long-running JSONL control accepts {"op":"chorus_phrase",...} on stdin, or shorthand lines
#   "<emotion_index> <1|2|3>" (bars 4/8/16) or index then 1/2/3 on the next line.
#///////////////////////////////////////////////////////////


from __future__ import annotations

import argparse
import json
import logging
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app_controller import AppController
from composition.arrangement_role_labels import arrangement_role_display_name
from composition.section_planner.chorus_reference import (
    chorus_reference_arp_overrides,
    chorus_reference_melody_overrides,
)
from data.melody_phrase_profiles import melody_phrase_profile_for_emotion


def _json_out(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _bars_from_quick_key(key: int) -> int:
    """Map console keys 1/2/3 to bar counts 4/8/16."""
    k = int(key)
    if k == 2:
        return 8
    if k == 3:
        return 16
    return 4


def _playback_soft_stop(player) -> None:
    """Pause, drain the ring buffer, and drop pending section handoffs (does not exit the process)."""
    try:
        player.pause()
    except Exception:
        pass
    try:
        player.buffer.clear()
    except Exception:
        pass
    try:
        with player.section_lock:
            sch = player.section_scheduler
            sch.next_section_ready = False
            sch.next_section_events = None
            sch.next_section_bars = 0
            sch.next_section_emotion = None
            sch.next_section_root = None
            sch.pending_emotion = None
            sch.pending_root = None
            sch.pre_generation_running = False
            sch._pregen_followup_needed = False
    except Exception:
        pass


def _try_resume_player(player) -> None:
    try:
        player.resume()
    except Exception:
        pass


def _beat_float_for_json(x: Any, *, places: int = 4) -> float:
    """Stable decimal rounding so JSON does not show binary float noise (e.g. …000001)."""
    try:
        return round(float(x), int(places))
    except Exception:
        return 0.0


def _serialize_event_for_json(ev: Any) -> Optional[Dict[str, Any]]:
    """Turn an internal event tuple into a JSON-friendly dict for LLM tools."""
    try:
        if not ev or len(ev) < 6:
            return None
        ch, midi, vel, st, dur, notes = ev
        ns = list(notes) if notes is not None else []
        return {
            "channel": int(ch),
            "midi": int(midi),
            "velocity": int(vel),
            "start_beats": _beat_float_for_json(st),
            "duration_beats": _beat_float_for_json(dur),
            "notes": [int(n) for n in ns],
        }
    except Exception:
        return None


def _emotion_from_cli_string(emotions, s: str) -> Tuple[Any, Optional[str]]:
    key = (s or "").strip().lower()
    if not key:
        return None, "missing_emotion_name"
    if key.isdigit() or (key.startswith("-") and key[1:].isdigit()):
        try:
            idx = int(key)
        except Exception:
            return None, "invalid_emotion_index"
        if 0 <= idx < len(emotions):
            return emotions[int(idx)], None
        return None, "emotion_index_out_of_range"
    idx0 = next((i for i, em in enumerate(emotions) if str(getattr(em, "name", "")).lower() == key), None)
    if idx0 is None:
        return None, "unknown_emotion"
    return emotions[int(idx0)], None


def _generate_chorus_phrase_events(
    gen,
    emotion,
    *,
    root: int,
    bars: int,
    form_mode: str = "pop_ext",
    target_notes_per_bar: float = 7.0,
    seed: Optional[int] = None,
) -> Tuple[List[Any], Optional[str]]:
    """
    Build one short section with arrangement role forced to chorus-like ``b``.

    Restores ``form_mode``, realtime role overrides, and ``runtime_generation_mode`` afterward
    so a long-lived ``CompositionGenerator`` (interactive player) is not left in chorus-only
    override state.
    """
    from data.arrangement_forms import FORM_SEQUENCES

    pol = getattr(gen, "arrangement_policy", None)
    if pol is None:
        return [], "no_arrangement_policy"

    fm = str(form_mode or "pop_ext").strip().lower()
    if fm not in FORM_SEQUENCES:
        fm = "pop_ext"

    prev_form = getattr(pol, "form_mode", None)
    prev_rt = getattr(gen, "runtime_generation_mode", None)
    try:
        prev_overrides = dict(getattr(pol, "_realtime_role_overrides", {}) or {})
    except Exception:
        prev_overrides = {}

    try:
        pol.form_mode = fm
        pol.set_realtime_role_override(0, "b")
        pol.set_realtime_role_override(1, "b")
        if seed is not None:
            try:
                gen.reseed(int(seed))
            except Exception:
                pass
        try:
            if hasattr(gen, "reset_song_arrangement_state"):
                gen.reset_song_arrangement_state()
        except Exception:
            pass
        setattr(gen, "runtime_generation_mode", "offline")
        events = gen.generate_section(
            emotion,
            int(root),
            bars=int(bars),
            section_index=0,
            target_notes_per_bar=float(target_notes_per_bar),
        )
        return list(events or []), None
    except Exception as exc:
        return [], f"generate_failed:{exc.__class__.__name__}:{exc}"
    finally:
        try:
            gen.runtime_generation_mode = (
                str(prev_rt) if isinstance(prev_rt, str) and str(prev_rt).strip() else "normal"
            )
        except Exception:
            pass
        try:
            pol.form_mode = str(prev_form) if isinstance(prev_form, str) and str(prev_form).strip() else "default"
        except Exception:
            pass
        try:
            setattr(pol, "_realtime_role_overrides", dict(prev_overrides))
        except Exception:
            pass


def _safe_load_emotion_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Optional mapping file to let an LLM pick preset/style by emotion.

    Format:
      {
        "joy": {"preset": "my_preset", "style": "lofi", "fx": "warm"},
        "sadness": {"style": "ambient", "arrangement_type": "ballad"}
      }
    """
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        key = str(k or "").strip().lower()
        if not key:
            continue
        out[key] = dict(v)
    return out


def _apply_preset_if_requested(*, preset_name: Optional[str], config) -> Optional[str]:
    if not preset_name:
        return None
    name = str(preset_name).strip()
    if not name:
        return None
    try:
        from presets import load_preset
        from presets.config_applier import apply_macros_snapshot, apply_preset_to_config

        p = load_preset(str(name))
        apply_preset_to_config(config, p)
        apply_macros_snapshot(config, dict(getattr(p, "macros", {}) or {}))
        return str(name)
    except Exception:
        return None


def _apply_conversation_from_cli(*, config, args: Any) -> None:
    """Match main.py: --conversation wins; else --ambient01 sets ambient01."""
    conv = getattr(args, "conversation", None)
    if conv is not None and str(conv).strip():
        config.set_conversation_preset(str(conv).strip())
    elif bool(getattr(args, "ambient01", False)):
        config.set_conversation_preset("ambient01")


def _apply_chorus_only_mixer_defaults(config: Any) -> None:
    """No chorus 4/4 kick stem and no ducking for this entry point (see ``ChorusKickSidechainConfig``)."""
    try:
        sc = getattr(getattr(config, "audio", None), "chorus_kick_sidechain", None)
        if sc is None:
            return
        sc.kick_enabled = False
        sc.sidechain_enabled = False
    except Exception:
        pass


def _install_chorus_only_mixer_guard(config: Any) -> None:
    """After any style/conversation layer rebuild, keep kick and sidechain off."""
    if getattr(config, "_chorus_only_mixer_guard_installed", False):
        return
    setattr(config, "_chorus_only_mixer_guard_installed", True)
    _orig_conv = config.set_conversation_preset
    _orig_style = config.set_style_profile

    def _wrapped_conv(name: str):
        _orig_conv(name)
        _apply_chorus_only_mixer_defaults(config)

    def _wrapped_style(name: str):
        _orig_style(name)
        _apply_chorus_only_mixer_defaults(config)

    config.set_conversation_preset = _wrapped_conv  # type: ignore[method-assign]
    config.set_style_profile = _wrapped_style  # type: ignore[method-assign]


def _apply_llm_chorus_only_config(*, config: Any, args: Any) -> None:
    _apply_conversation_from_cli(config=config, args=args)
    _apply_chorus_only_mixer_defaults(config)


class AdapterComposer:
    """
    Minimal adapter used by the realtime `PolyphonicPlayer`.

    This is intentionally duplicated from `main.py`'s nested class so this
    LLM entrypoint can bootstrap without importing CLI internals.
    """

    def __init__(self, g, cfg, *, chorus_only: bool = False):
        self.gen = g
        self.config = cfg
        self._song_gen = None
        self._last_arranged_song_segments = None
        self._last_arranged_song_render = None
        self._chorus_only = bool(chorus_only)
        # Arrangement roles that should be treated as "chorus-like" for chorus-only playback.
        self._chorus_roles = {"b", "chorus", "hook", "tag"}

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

                seq = (
                    ArrangementPolicy._FORM_SEQUENCES.get(str(mode))
                    or ArrangementPolicy._FORM_SEQUENCES.get("default")
                    or ()
                )
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
        section_index: int = 0,
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

        logger = logging.getLogger(__name__)
        self.gen.runtime_generation_mode = runtime_mode

        comp = getattr(self.config, "composition", None)
        mode = str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default"
        bars_per_section = int(getattr(comp, "bars_per_section", 16) or 16) if comp is not None else 16
        seconds = float(getattr(comp, "arranged_song_seconds", 150.0) or 150.0) if comp is not None else 150.0
        max_bars = int(getattr(comp, "arranged_song_max_bars", 64) or 64) if comp is not None else 64
        k = int(getattr(comp, "arranged_song_k", 1) or 1) if comp is not None else 1
        budget_s = float(getattr(comp, "arranged_song_pick_time_budget_s", 2.0) or 2.0) if comp is not None else 2.0
        base_tempo_bpm = 70.0
        try:
            if comp is not None and bool(getattr(comp, "hook_safe_mode", False)) and int(k) <= 1:
                k = 4
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

        start_t = time.time()
        best = None
        best_score = None
        tried = 0
        kk = max(1, int(k))
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
                score_i, details = self._song_gen._score_candidate_song(cand, arrangement_form=str(mode))  # type: ignore[attr-defined]
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
        events_out = list(best.events or [])
        bars_out = int(total_bars)

        if not bool(self._chorus_only):
            return events_out, bars_out

        try:
            segs = getattr(self, "_last_arranged_song_segments", None)
        except Exception:
            segs = None
        filtered = self._filter_events_to_roles(events_out, segs, beats_per_bar=4.0)
        if filtered is not None:
            return filtered["events"], int(filtered["bars"])
        return events_out, bars_out

    def _filter_events_to_roles(self, events, segs, *, beats_per_bar: float = 4.0) -> Optional[Dict[str, Any]]:
        """
        Build a new event timeline that keeps only chorus-like arrangement segments.

        We clip notes to each kept segment window and re-base time so segments
        play back-to-back as a shorter "chorus-only" loop.
        """
        if not isinstance(segs, list) or not segs:
            return None

        keep = []
        for s in segs:
            if not isinstance(s, dict):
                continue
            role = str(s.get("role", "") or "").strip().lower()
            if role in self._chorus_roles:
                keep.append(s)
        if not keep:
            return None

        def _clip_window(ev, *, win_start: float, win_end: float, out_offset: float):
            try:
                ch, midi, vel, st, dur, notes = ev
                stf = float(st)
                durf = float(dur)
            except Exception:
                return None
            if durf <= 1e-9:
                return None
            ev_end = stf + durf
            if ev_end <= win_start or stf >= win_end:
                return None
            local_start = max(stf, win_start) - win_start
            local_end = min(ev_end, win_end) - win_start
            local_dur = float(local_end - local_start)
            if local_dur <= 1e-9:
                return None
            try:
                return (int(ch), midi, int(vel), float(out_offset + local_start), float(local_dur), list(notes))
            except Exception:
                return None

        out_events = []
        out_segs = []
        out_bar_cursor = 0
        bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
        for seg in keep:
            try:
                start_bar = int(seg.get("start_bar", 0) or 0)
                end_bar = int(seg.get("end_bar", 0) or 0)
            except Exception:
                continue
            bars = max(0, int(end_bar - start_bar))
            if bars <= 0:
                continue
            win_start = float(start_bar) * bpb
            win_end = float(end_bar) * bpb
            out_offset = float(out_bar_cursor) * bpb
            for ev in list(events or []):
                clipped = _clip_window(ev, win_start=win_start, win_end=win_end, out_offset=out_offset)
                if clipped is not None:
                    out_events.append(clipped)
            # rewrite segment window to new timeline
            out_segs.append(
                {
                    **dict(seg),
                    "start_bar": int(out_bar_cursor),
                    "end_bar": int(out_bar_cursor + bars),
                }
            )
            out_bar_cursor += int(bars)

        if out_bar_cursor <= 0:
            return None
        # Expose filtered segments so the status line/UI reflect chorus-only playback.
        self._last_arranged_song_segments = out_segs or None
        return {"events": out_events, "bars": int(out_bar_cursor)}

def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--verbose", action="store_true", help="Verbose logging (not recommended for JSONL integration).")
    parser.add_argument("--quiet", action="store_true", help="Errors only on console.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive startup (prints emotion list, prompts select emotion, then starts playback).",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive prompt even when running in a TTY.",
    )
    parser.add_argument(
        "--chorus-only",
        action="store_true",
        help="Explicit chorus-only playback (default for this script). Kept for compatibility; same as omitting --full-arrangement.",
    )
    parser.add_argument(
        "--full-arrangement",
        action="store_true",
        help="Play the complete arranged timeline (intro, verses, etc.). Default is chorus-like segments only (roles b/chorus/hook/tag).",
    )
    parser.add_argument(
        "--cycle-all-emotions",
        action="store_true",
        help="Cycle chorus-only playback through all emotions automatically.",
    )
    parser.add_argument(
        "--cycle-bars",
        type=int,
        default=16,
        help="When cycling all emotions, switch emotion every N played bars (default: 16).",
    )
    parser.add_argument(
        "--cycle-include-neutral",
        action="store_true",
        help="Include neutral in the all-emotions cycle (default: off).",
    )
    parser.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60)")
    parser.add_argument(
        "--max-bars",
        type=int,
        default=None,
        help="Cap arranged-song timeline length (sets composition.arranged_song_max_bars, clamped 8–256).",
    )
    parser.add_argument(
        "--phrase-max-bars",
        type=int,
        default=24,
        help="Max bars for chorus-phrase generation (stdin / JSON / shorthand / phrase-console; clamped 1–24, default 24).",
    )
    parser.add_argument(
        "--performance",
        choices=("high", "low", "quality", "balanced", "maximum"),
        default="high",
        help="Audio engine profile (same as main.py).",
    )
    parser.add_argument("--preset", default="", help="Optional meta preset name to apply at boot.")
    parser.add_argument(
        "--conversation",
        default=None,
        help="Conversation preset (e.g. ambient01, default, opening; overrides meta preset).",
    )
    parser.add_argument(
        "--ambient01",
        action="store_true",
        help="Shorthand: same as --conversation ambient01 (layered OST-style).",
    )
    parser.add_argument(
        "--list-conversations",
        action="store_true",
        help="List conversation preset names and exit (no audio).",
    )
    parser.add_argument("--emotion", default="neutral", help="Boot emotion (name or index; default neutral).")
    parser.add_argument(
        "--mapping",
        default=".audiogen/llm_mapping.json",
        help="Optional emotion->scene mapping JSON path.",
    )
    parser.add_argument(
        "--list-emotions-json",
        action="store_true",
        help="Print a JSON line listing emotion indices/names and exit (for LLM tool discovery).",
    )
    parser.add_argument(
        "--chorus-phrase-json",
        action="store_true",
        help="One-shot: generate a short chorus-role phrase, print JSON to stdout, exit (no audio device).",
    )
    parser.add_argument(
        "--phrase-bars",
        type=int,
        default=4,
        help="Bar length for --chorus-phrase-json (clamped 1–24, default 4).",
    )
    parser.add_argument(
        "--phrase-form",
        default="pop_ext",
        help="ArrangementPolicy.form_mode for phrase generation (default: pop_ext).",
    )
    parser.add_argument(
        "--phrase-target-npb",
        type=float,
        default=7.0,
        help="Target notes-per-bar for chorus phrase (default: 7).",
    )
    parser.add_argument(
        "--phrase-seed",
        type=int,
        default=None,
        help="Optional integer seed for repeatable phrase generation.",
    )
    parser.add_argument(
        "--phrase-console",
        action="store_true",
        help="TTY-only: prompt for emotion then 1/2/3 (4/8/16 bars), print chorus phrase JSON each time; no audio player.",
    )
    args = parser.parse_args()

    if bool(getattr(args, "list_conversations", False)):
        from main import _discover_preset_families, _print_preset_family_block
        from audiogen_core.config import ConfigurationManager

        _print_preset_family_block(
            "Conversation presets", _discover_preset_families(ConfigurationManager()).get("conversation_presets", [])
        )
        return 0

    if bool(getattr(args, "list_emotions_json", False)):
        from data.music_data import EMOTIONS as _EMOS

        _json_out(
            {
                "type": "emotions",
                "ok": True,
                "emotions": [{"index": i, "name": str(getattr(e, "name", "") or "")} for i, e in enumerate(_EMOS)],
            }
        )
        return 0

    if bool(getattr(args, "chorus_phrase_json", False)):
        from main import _setup_logging  # noqa: WPS433
        from composition.engine import CompositionGenerator  # noqa: WPS433
        from audiogen_core.config import CONFIG  # noqa: WPS433
        from data.music_data import EMOTIONS  # noqa: WPS433

        _setup_logging(verbose=bool(getattr(args, "verbose", False)), quiet=bool(getattr(args, "quiet", False)))
        _install_chorus_only_mixer_guard(CONFIG)
        CONFIG.set_performance_mode(str(getattr(args, "performance", "high") or "high"))
        applied_preset = _apply_preset_if_requested(
            preset_name=str(getattr(args, "preset", "") or "").strip(),
            config=CONFIG,
        )
        if applied_preset:
            try:
                CONFIG.rebuild_samplers()
            except Exception:
                pass
        _apply_llm_chorus_only_config(config=CONFIG, args=args)

        emo, em_err = _emotion_from_cli_string(EMOTIONS, str(getattr(args, "emotion", "neutral") or "neutral"))
        if emo is None:
            _json_out({"type": "chorus_phrase", "ok": False, "error": em_err or "emotion_resolve_failed"})
            return 2
        try:
            pb = int(getattr(args, "phrase_bars", 4) or 4)
        except Exception:
            pb = 4
        try:
            phrase_cap = max(1, min(24, int(getattr(args, "phrase_max_bars", 24) or 24)))
        except Exception:
            phrase_cap = 24
        pb = max(1, min(phrase_cap, int(pb)))
        root = int(getattr(args, "root", 60) or 60)
        form_mode = str(getattr(args, "phrase_form", "pop_ext") or "pop_ext")
        try:
            tnpb = float(getattr(args, "phrase_target_npb", 7.0) or 7.0)
        except Exception:
            tnpb = 7.0
        seed = getattr(args, "phrase_seed", None)

        gen = CompositionGenerator(enable_perf_monitoring=False)
        events, gen_err = _generate_chorus_phrase_events(
            gen,
            emo,
            root=root,
            bars=pb,
            form_mode=form_mode,
            target_notes_per_bar=tnpb,
            seed=int(seed) if seed is not None else None,
        )
        if gen_err:
            _json_out(
                {
                    "type": "chorus_phrase",
                    "ok": False,
                    "error": gen_err,
                    "emotion": str(getattr(emo, "name", "") or ""),
                    "bars": pb,
                    "root": root,
                }
            )
            return 2
        out_ev = [_serialize_event_for_json(ev) for ev in events]
        out_ev = [x for x in out_ev if x is not None]
        bpb = 4.0
        _json_out(
            {
                "type": "chorus_phrase",
                "ok": True,
                "emotion": str(getattr(emo, "name", "") or ""),
                "bars": pb,
                "root": root,
                "beats_per_bar": int(bpb),
                "section_duration_beats": _beat_float_for_json(float(pb) * bpb),
                "form_mode": str(form_mode),
                "section_role": "b",
                "event_count": len(out_ev),
                "events": out_ev,
            }
        )
        return 0

    if bool(getattr(args, "phrase_console", False)):
        from main import _setup_logging  # noqa: WPS433
        from composition.engine import CompositionGenerator  # noqa: WPS433
        from audiogen_core.config import CONFIG  # noqa: WPS433
        from data.music_data import EMOTIONS  # noqa: WPS433

        _setup_logging(verbose=bool(getattr(args, "verbose", False)), quiet=bool(getattr(args, "quiet", False)))
        _install_chorus_only_mixer_guard(CONFIG)
        CONFIG.set_performance_mode(str(getattr(args, "performance", "high") or "high"))
        applied_preset = _apply_preset_if_requested(
            preset_name=str(getattr(args, "preset", "") or "").strip(),
            config=CONFIG,
        )
        if applied_preset:
            try:
                CONFIG.rebuild_samplers()
            except Exception:
                pass
        _apply_llm_chorus_only_config(config=CONFIG, args=args)

        root = int(getattr(args, "root", 60) or 60)
        form_mode = str(getattr(args, "phrase_form", "pop_ext") or "pop_ext")
        try:
            tnpb = float(getattr(args, "phrase_target_npb", 7.0) or 7.0)
        except Exception:
            tnpb = 7.0
        seed = getattr(args, "phrase_seed", None)
        seed_i = int(seed) if seed is not None else None

        gen = CompositionGenerator(enable_perf_monitoring=False)
        try:
            phrase_cap = max(1, min(24, int(getattr(args, "phrase_max_bars", 24) or 24)))
        except Exception:
            phrase_cap = 24

        try:
            sys.stderr.write("Phrase console — emotion index 0–27 (or name); then 1=4 bars, 2=8 bars, 3=16.\n")
            sys.stderr.write("One line also works: <index> <1|2|3>  e.g.  17 2\n")
            sys.stderr.write("Quit: q or quit on the emotion prompt. (Prompts on stderr; JSON on stdout.)\n\n")
            sys.stderr.flush()
        except Exception:
            pass

        while True:
            try:
                sys.stderr.write("Emotion number 0–27 (or name; q to quit): ")
                sys.stderr.flush()
                first = (sys.stdin.readline() or "").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not first or str(first).lower() in {"q", "quit", "exit"}:
                break
            parts = first.split()
            em_token = parts[0]
            bar_key: Optional[int] = None
            if len(parts) >= 2 and parts[1] in ("1", "2", "3"):
                try:
                    bar_key = int(parts[1])
                except Exception:
                    bar_key = None
            em, em_err = _emotion_from_cli_string(EMOTIONS, em_token)
            if em is None:
                try:
                    sys.stderr.write(f"Unknown emotion: {em_err or em_token}\n")
                except Exception:
                    pass
                continue
            if bar_key is None:
                try:
                    sys.stderr.write("Phrase length — 1=4 bars, 2=8 bars, 3=16 bars: ")
                    sys.stderr.flush()
                    bk_s = (sys.stdin.readline() or "").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if bk_s not in ("1", "2", "3"):
                    try:
                        sys.stderr.write("Please enter 1, 2, or 3.\n")
                    except Exception:
                        pass
                    continue
                bar_key = int(bk_s)
            bars = max(1, min(int(phrase_cap), int(_bars_from_quick_key(int(bar_key)))))
            events, gen_err = _generate_chorus_phrase_events(
                gen,
                em,
                root=root,
                bars=bars,
                form_mode=form_mode,
                target_notes_per_bar=float(tnpb),
                seed=seed_i,
            )
            if gen_err:
                _json_out(
                    {
                        "type": "chorus_phrase",
                        "ok": False,
                        "error": gen_err,
                        "emotion": str(getattr(em, "name", "") or ""),
                        "bars": bars,
                        "root": root,
                    }
                )
                continue
            out_ev = [_serialize_event_for_json(ev) for ev in events]
            out_ev = [x for x in out_ev if x is not None]
            bpb = 4.0
            _json_out(
                {
                    "type": "chorus_phrase",
                    "ok": True,
                    "emotion": str(getattr(em, "name", "") or ""),
                    "bars": bars,
                    "root": root,
                    "beats_per_bar": int(bpb),
                    "section_duration_beats": _beat_float_for_json(float(bars) * bpb),
                    "form_mode": str(form_mode),
                    "section_role": "b",
                    "event_count": len(out_ev),
                    "events": out_ev,
                }
            )
        return 0

    from main import _setup_logging  # noqa: WPS433
    from audio.audio_container import AudioContainer  # noqa: WPS433
    from audio.RT_player import PolyphonicPlayer  # noqa: WPS433
    from composition.engine import CompositionGenerator  # noqa: WPS433
    from audiogen_core.config import CONFIG  # noqa: WPS433
    from data.music_data import EMOTIONS  # noqa: WPS433

    _setup_logging(verbose=bool(getattr(args, "verbose", False)), quiet=bool(getattr(args, "quiet", False)))

    _install_chorus_only_mixer_guard(CONFIG)
    CONFIG.set_performance_mode(str(getattr(args, "performance", "high") or "high"))

    try:
        mb = getattr(args, "max_bars", None)
        if mb is not None:
            comp = getattr(CONFIG, "composition", None)
            if comp is not None:
                setattr(comp, "arranged_song_max_bars", max(8, min(256, int(mb))))
    except Exception:
        pass

    applied_preset = _apply_preset_if_requested(preset_name=str(getattr(args, "preset", "") or "").strip(), config=CONFIG)
    if applied_preset:
        try:
            CONFIG.rebuild_samplers()
        except Exception:
            pass
    _apply_llm_chorus_only_config(config=CONFIG, args=args)

    gen = CompositionGenerator(enable_perf_monitoring=False)
    # Default: chorus-like segments only (this entry point). Full form only with --full-arrangement.
    chorus_only_eff = not bool(getattr(args, "full_arrangement", False))
    adapter = AdapterComposer(gen, CONFIG, chorus_only=bool(chorus_only_eff))
    container = AudioContainer.create_from_config(CONFIG)
    player = PolyphonicPlayer(adapter, CONFIG, container=container)

    def _emotion_index_by_name(name: str) -> int:
        key = (name or "").strip().lower()
        idx0 = next((i for i, em in enumerate(EMOTIONS) if str(em.name).lower() == key), None)
        return int(idx0) if idx0 is not None else 0

    controller = AppController(
        player=player,
        config=CONFIG,
        emotions=EMOTIONS,
        container=container,
        root_default=int(getattr(args, "root", 60) or 60),
        emotion_index_by_name=_emotion_index_by_name,
    )

    mapping_path = Path(str(getattr(args, "mapping", "") or "")).expanduser()
    if not mapping_path.is_absolute():
        mapping_path = Path(__file__).resolve().parent / mapping_path
    emotion_mapping = _safe_load_emotion_mapping(mapping_path)

    def _select_emotion_interactive(*, default_name: str = "neutral") -> str:
        try:
            if not sys.stdin.isatty():
                return str(default_name)
        except Exception:
            return str(default_name)
        # print list first
        neutral_idx = _emotion_index_by_name(str(default_name))
        neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(EMOTIONS) else 0
        try:
            sys.stdout.write("\nEmotions:\n")
            sys.stdout.write(f"  0: {EMOTIONS[int(neutral_idx)].name} (neutral)\n")
            max_display_index = min(27, len(EMOTIONS) - 1)
            for i in range(1, max_display_index + 1):
                sys.stdout.write(f"  {i}: {getattr(EMOTIONS[int(i)], 'name', f'emo-{i}')}\n")
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass

        while True:
            try:
                sys.stdout.write("select emotion (name/index, Enter=neutral): ")
                sys.stdout.flush()
                line = sys.stdin.readline()
            except Exception:
                return str(default_name)
            if not line:
                return str(default_name)
            s = (line or "").strip()
            if s == "":
                return str(default_name)
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                try:
                    idx = int(s)
                except Exception:
                    idx = int(neutral_idx)
                if idx == 0:
                    return str(EMOTIONS[int(neutral_idx)].name)
                if 0 <= idx < len(EMOTIONS) and idx <= 27:
                    return str(getattr(EMOTIONS[int(idx)], "name", default_name))
                sys.stdout.write("Out of range. Use 0-27.\n")
                sys.stdout.flush()
                continue
            # name
            idx2 = _emotion_index_by_name(s)
            if 0 <= int(idx2) < len(EMOTIONS):
                return str(getattr(EMOTIONS[int(idx2)], "name", default_name))
            sys.stdout.write("Unknown emotion. Try an index 0-27.\n")
            sys.stdout.flush()

    # This entry point expects arranged timelines (so chorus filtering can run). Turn on
    # before the first load_emotion(); otherwise the player may build a single-section preview
    # that behaves like an intro.
    try:
        comp = getattr(CONFIG, "composition", None)
        if comp is not None:
            setattr(comp, "arranged_songs_default", True)
            setattr(comp, "arranged_song_loop", True)
    except Exception:
        pass

    # Select emotion BEFORE starting playback.
    interactive = bool(getattr(args, "interactive", False))
    if not interactive and not bool(getattr(args, "no_interactive", False)):
        try:
            # In a real terminal, default to prompting so we don't auto-play neutral.
            interactive = bool(sys.stdin.isatty())
        except Exception:
            interactive = False
    boot_emotion = str(getattr(args, "emotion", "neutral") or "neutral").strip()
    if interactive:
        boot_emotion = _select_emotion_interactive(default_name=boot_emotion or "neutral")

    # Ensure the very first bars are generated for the chosen emotion.
    # AppController can also apply config/style/fx, but emotion MUST be loaded
    # into the player before the thread starts to avoid a "neutral-first" bar.
    try:
        idx = None
        try:
            idx = int(str(boot_emotion).strip())
        except Exception:
            idx = _emotion_index_by_name(str(boot_emotion))
        idx = int(idx) if idx is not None else 0
        if 0 <= int(idx) < len(EMOTIONS):
            player.load_emotion(int(idx), int(getattr(args, "root", 60) or 60))
    except Exception:
        pass

    player.start()
    controller.apply_scene({"emotion": boot_emotion})

    # Optional: cycle chorus-only playback through all emotions.
    if bool(getattr(args, "cycle_all_emotions", False)):
        try:
            include_neutral = bool(getattr(args, "cycle_include_neutral", False))
        except Exception:
            include_neutral = False
        try:
            cycle_bars = int(getattr(args, "cycle_bars", 16) or 16)
        except Exception:
            cycle_bars = 16
        cycle_bars = max(1, min(64, int(cycle_bars)))

        def _cycle_thread() -> None:
            try:
                emos = [str(getattr(e, "name", "") or "").strip() for e in list(EMOTIONS)]
            except Exception:
                emos = []
            emos = [e for e in emos if e]
            if not include_neutral:
                emos = [e for e in emos if str(e).strip().lower() != "neutral"]
            if not emos:
                return
            # Start the cycle at the current emotion if possible.
            try:
                cur = str(controller.get_scene_snapshot().get("emotion", "") or "").strip().lower()
            except Exception:
                cur = ""
            start_idx = next((i for i, e in enumerate(emos) if str(e).strip().lower() == cur), 0)
            i = int(start_idx)
            last_switch_at = -1
            while True:
                try:
                    if not bool(getattr(player, "_running", True)):
                        return
                except Exception:
                    pass
                try:
                    played = int(getattr(player.section_scheduler, "bars_played_this_section", 0) or 0)
                except Exception:
                    played = 0
                # Switch on a clean bar boundary (every N heard bars).
                target = (played // int(cycle_bars)) * int(cycle_bars)
                if played >= int(cycle_bars) and target != last_switch_at and (played % int(cycle_bars) == 0):
                    last_switch_at = int(target)
                    i = (i + 1) % len(emos)
                    try:
                        controller.apply_scene({"emotion": str(emos[i])})
                    except Exception:
                        pass
                time.sleep(0.05)

        t = threading.Thread(target=_cycle_thread, name="cycle-all-emotions", daemon=True)
        t.start()

    try:
        phrase_bar_cap = max(1, min(24, int(getattr(args, "phrase_max_bars", 24) or 24)))
    except Exception:
        phrase_bar_cap = 24
    try:
        arranged_max = int(getattr(CONFIG.composition, "arranged_song_max_bars", 0) or 0)
    except Exception:
        arranged_max = 0

    _json_out(
        {
            "type": "ready",
            "ok": True,
            "scene": controller.get_scene_snapshot(),
            "mapping_loaded": bool(emotion_mapping),
            "mapping_path": str(mapping_path),
            "arranged_song_max_bars": int(arranged_max) if arranged_max else None,
            "phrase_max_bars": int(phrase_bar_cap),
            "phrase_shorthand_help": "Non-JSON: '<idx> <1|2|3>' phrase, idx alone then 1-3, e <name|idx> switch emotion, stop (pause+clear), q quit.",
            "stdin_note": "stdin is read on a background thread so you can type during generation; commands are processed in order.",
        }
    )

    phrase_pending_idx: Optional[int] = None
    stopped_await_emotion: bool = False
    phrase_root = int(getattr(args, "root", 60) or 60)
    phrase_form_mode = str(getattr(args, "phrase_form", "pop_ext") or "pop_ext")
    try:
        phrase_tnpb = float(getattr(args, "phrase_target_npb", 7.0) or 7.0)
    except Exception:
        phrase_tnpb = 7.0
    phrase_seed_i = int(getattr(args, "phrase_seed")) if getattr(args, "phrase_seed", None) is not None else None

    def _apply_emotion_for_cli(emo: str) -> Dict[str, Any]:
        em2 = str(emo or "").strip()
        emo_key = em2.lower()
        scene: Dict[str, Any] = {"emotion": em2}
        mapped = emotion_mapping.get(emo_key) or {}
        if isinstance(mapped, dict) and mapped:
            for k, v in mapped.items():
                if k in {"preset"}:
                    continue
                scene[str(k)] = v
            applied = _apply_preset_if_requested(preset_name=str(mapped.get("preset") or "").strip(), config=CONFIG)
            if applied:
                try:
                    CONFIG.rebuild_samplers()
                except Exception:
                    pass
        return controller.apply_scene(scene)

    def _stdin_emit_chorus_phrase_for_index(em_idx: int, bars: int) -> None:
        nonlocal phrase_pending_idx, stopped_await_emotion
        if not (0 <= int(em_idx) < len(EMOTIONS)):
            _json_out({"type": "chorus_phrase", "ok": False, "error": "emotion_index_out_of_range", "emotion_index": int(em_idx)})
            return
        em = EMOTIONS[int(em_idx)]
        if stopped_await_emotion:
            stopped_await_emotion = False
            _try_resume_player(player)
        try:
            _apply_emotion_for_cli(str(getattr(em, "name", "") or ""))
        except Exception:
            pass
        gen = getattr(getattr(player, "composer", None), "gen", None)
        if gen is None:
            _json_out({"type": "chorus_phrase", "ok": False, "error": "no_composer_generator"})
            return
        bars = max(1, min(int(phrase_bar_cap), int(bars)))
        events, gen_err = _generate_chorus_phrase_events(
            gen,
            em,
            root=int(phrase_root),
            bars=bars,
            form_mode=str(phrase_form_mode),
            target_notes_per_bar=float(phrase_tnpb),
            seed=phrase_seed_i,
        )
        if gen_err:
            _json_out({"type": "chorus_phrase", "ok": False, "error": gen_err, "emotion": str(getattr(em, "name", "") or ""), "bars": bars})
            return
        out_ev = [_serialize_event_for_json(ev) for ev in events]
        out_ev = [x for x in out_ev if x is not None]
        bpb = 4.0
        _json_out(
            {
                "type": "chorus_phrase",
                "ok": True,
                "emotion": str(getattr(em, "name", "") or ""),
                "emotion_index": int(em_idx),
                "bars": bars,
                "root": int(phrase_root),
                "beats_per_bar": int(bpb),
                "section_duration_beats": _beat_float_for_json(float(bars) * bpb),
                "form_mode": str(phrase_form_mode),
                "section_role": "b",
                "event_count": len(out_ev),
                "events": out_ev,
            }
        )
        phrase_pending_idx = None

    cmd_queue: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=512)

    def _stdin_reader() -> None:
        try:
            for raw in sys.stdin:
                try:
                    cmd_queue.put(raw)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            cmd_queue.put(None)
        except Exception:
            pass

    threading.Thread(target=_stdin_reader, name="stdin-reader", daemon=True).start()

    try:
        while True:
            raw = cmd_queue.get()
            if raw is None:
                break
            line = (raw or "").strip()
            if not line:
                continue

            if not line.startswith("{"):
                low = line.lower()
                if low in {"q", "quit", "exit"}:
                    _json_out({"type": "bye", "ok": True})
                    break
                if low in {"stop", "halt"}:
                    _playback_soft_stop(player)
                    phrase_pending_idx = None
                    stopped_await_emotion = True
                    _json_out(
                        {
                            "type": "stopped",
                            "ok": True,
                            "awaiting_emotion": True,
                            "hint": "Send emotion name or index, e <name|idx>, or JSON trigger_emotion / apply_scene; optional resume without new emotion: resume",
                        }
                    )
                    try:
                        sys.stderr.write("Stopped — send next emotion (name, index, or e <name|idx>), or resume.\n")
                        sys.stderr.flush()
                    except Exception:
                        pass
                    continue
                if low in {"resume", "play", "go"}:
                    stopped_await_emotion = False
                    _try_resume_player(player)
                    _json_out({"type": "resumed", "ok": True})
                    continue
                m_e = re.match(r"^(?:e|emotion)\s+(.+)$", line, flags=re.IGNORECASE)
                if m_e:
                    rest = str(m_e.group(1) or "").strip()
                    emo_o, em_err = _emotion_from_cli_string(EMOTIONS, rest)
                    if emo_o is None:
                        _json_out({"type": "trigger_emotion", "ok": False, "error": em_err or "unknown_emotion"})
                        continue
                    out = _apply_emotion_for_cli(str(getattr(emo_o, "name", "") or ""))
                    stopped_await_emotion = False
                    _try_resume_player(player)
                    _json_out({"type": "trigger_emotion", **out})
                    continue
                if not stopped_await_emotion and not re.fullmatch(r"\d{1,2}", line.strip()):
                    em_try, _em_err = _emotion_from_cli_string(EMOTIONS, line)
                    if em_try is not None:
                        out = _apply_emotion_for_cli(str(getattr(em_try, "name", "") or ""))
                        stopped_await_emotion = False
                        _try_resume_player(player)
                        _json_out({"type": "trigger_emotion", **out})
                        continue
                m_combo = re.fullmatch(r"(\d{1,2})\s+([123])", line.replace(",", " ").strip())
                if m_combo:
                    ei = int(m_combo.group(1))
                    bk = int(m_combo.group(2))
                    if 0 <= ei < len(EMOTIONS):
                        if stopped_await_emotion:
                            stopped_await_emotion = False
                            _try_resume_player(player)
                        _stdin_emit_chorus_phrase_for_index(ei, _bars_from_quick_key(bk))
                    else:
                        _json_out({"type": "chorus_phrase", "ok": False, "error": "emotion_index_out_of_range", "emotion_index": ei})
                    continue
                m_idx = re.fullmatch(r"\d{1,2}", line)
                if m_idx:
                    ei = int(line)
                    if stopped_await_emotion:
                        emo_o, em_err = _emotion_from_cli_string(EMOTIONS, line)
                        if emo_o is not None:
                            out = _apply_emotion_for_cli(str(getattr(emo_o, "name", "") or ""))
                            stopped_await_emotion = False
                            _try_resume_player(player)
                            _json_out({"type": "trigger_emotion", **out})
                            continue
                        _json_out({"type": "awaiting_emotion", "ok": False, "error": em_err or "unrecognized_emotion"})
                        continue
                    if 0 <= ei < len(EMOTIONS):
                        phrase_pending_idx = ei
                        _json_out(
                            {
                                "type": "phrase_await_bars",
                                "ok": True,
                                "emotion_index": ei,
                                "emotion": str(getattr(EMOTIONS[ei], "name", "") or ""),
                                "hint": "Send 1 (4 bars), 2 (8 bars), or 3 (16 bars) on the next line, or use '<index> <1-3>'.",
                            }
                        )
                    else:
                        _json_out({"type": "chorus_phrase", "ok": False, "error": "emotion_index_out_of_range", "emotion_index": ei})
                    continue
                if phrase_pending_idx is not None and re.fullmatch(r"[123]", line):
                    _stdin_emit_chorus_phrase_for_index(int(phrase_pending_idx), _bars_from_quick_key(int(line)))
                    continue
                if stopped_await_emotion:
                    emo_o, em_err = _emotion_from_cli_string(EMOTIONS, line)
                    if emo_o is not None:
                        out = _apply_emotion_for_cli(str(getattr(emo_o, "name", "") or ""))
                        stopped_await_emotion = False
                        _try_resume_player(player)
                        _json_out({"type": "trigger_emotion", **out})
                        continue
                    _json_out({"type": "awaiting_emotion", "ok": False, "error": em_err or "unrecognized_emotion", "hint": "Use emotion name/index, e <name|idx>, or resume."})
                    continue

            try:
                msg = json.loads(line)
            except Exception:
                if line.startswith("{"):
                    _json_out({"type": "error", "ok": False, "error": "invalid_json"})
                else:
                    _json_out({"type": "error", "ok": False, "error": "unrecognized_line", "hint": "Use JSON or '<idx> <1|2|3>' / index then 1-3."})
                continue

            op = str(msg.get("op", "") or msg.get("type", "") or "").strip().lower()
            if op in {"quit", "exit", "q"}:
                phrase_pending_idx = None
                _json_out({"type": "bye", "ok": True})
                break

            if op in {"ui_schema"}:
                _json_out({"type": "ui_schema", "ok": True, "schema": controller.get_ui_schema()})
                continue

            if op in {"scene", "get_scene"}:
                _json_out({"type": "scene", "ok": True, "scene": controller.get_scene_snapshot()})
                continue

            if op in {"stop", "soft_stop", "halt"}:
                _playback_soft_stop(player)
                phrase_pending_idx = None
                stopped_await_emotion = True
                _json_out(
                    {
                        "type": "stopped",
                        "ok": True,
                        "awaiting_emotion": True,
                        "hint": "Send trigger_emotion / apply_scene, or resume",
                    }
                )
                continue

            if op in {"resume", "play", "go"}:
                stopped_await_emotion = False
                _try_resume_player(player)
                _json_out({"type": "resumed", "ok": True})
                continue

            if op in {"set_scene", "apply_scene"}:
                scene = msg.get("scene")
                if not isinstance(scene, dict):
                    _json_out({"type": "set_scene", "ok": False, "error": "scene_must_be_object"})
                    continue
                out = controller.apply_scene(dict(scene))
                stopped_await_emotion = False
                _try_resume_player(player)
                _json_out({"type": "set_scene", **out})
                continue

            if op in {"trigger_emotion"}:
                emo = str(msg.get("emotion", "") or "").strip()
                if not emo:
                    _json_out({"type": "trigger_emotion", "ok": False, "error": "missing_emotion"})
                    continue
                emo_key = emo.lower()
                scene: Dict[str, Any] = {"emotion": emo}
                mapped = emotion_mapping.get(emo_key) or {}
                if isinstance(mapped, dict) and mapped:
                    # Allow mapping to inject other scene controls (style/fx/arrangement/etc).
                    for k, v in mapped.items():
                        if k in {"preset"}:
                            continue
                        scene[str(k)] = v
                    applied = _apply_preset_if_requested(preset_name=str(mapped.get("preset") or "").strip(), config=CONFIG)
                    if applied:
                        try:
                            CONFIG.rebuild_samplers()
                        except Exception:
                            pass
                out = controller.apply_scene(scene)
                stopped_await_emotion = False
                _try_resume_player(player)
                _json_out({"type": "trigger_emotion", **out})
                continue

            if op in {"chorus_phrase", "generate_chorus_phrase"}:
                emo_s = str(msg.get("emotion", "") or "").strip()
                if not emo_s:
                    _json_out({"type": "chorus_phrase", "ok": False, "error": "missing_emotion"})
                    continue
                em, em_err = _emotion_from_cli_string(EMOTIONS, emo_s)
                if em is None:
                    _json_out({"type": "chorus_phrase", "ok": False, "error": em_err or "unknown_emotion"})
                    continue
                try:
                    _apply_emotion_for_cli(str(getattr(em, "name", "") or ""))
                except Exception:
                    pass
                if stopped_await_emotion:
                    stopped_await_emotion = False
                    _try_resume_player(player)
                root = int(msg.get("root", int(getattr(args, "root", 60) or 60)) or 60)
                bars = int(msg.get("bars", 4) or 4)
                bars = max(1, min(int(phrase_bar_cap), int(bars)))
                form_mode = str(msg.get("form_mode", "pop_ext") or "pop_ext")
                try:
                    tnpb = float(msg.get("target_notes_per_bar", msg.get("phrase_target_npb", 7.0)) or 7.0)
                except Exception:
                    tnpb = 7.0
                seed = msg.get("seed")
                seed_i = None
                if seed is not None:
                    try:
                        seed_i = int(seed)
                    except Exception:
                        seed_i = None
                gen = getattr(getattr(player, "composer", None), "gen", None)
                if gen is None:
                    _json_out({"type": "chorus_phrase", "ok": False, "error": "no_composer_generator"})
                    continue
                events, gen_err = _generate_chorus_phrase_events(
                    gen,
                    em,
                    root=root,
                    bars=bars,
                    form_mode=form_mode,
                    target_notes_per_bar=tnpb,
                    seed=seed_i,
                )
                if gen_err:
                    _json_out({"type": "chorus_phrase", "ok": False, "error": gen_err})
                    continue
                out_ev = [_serialize_event_for_json(ev) for ev in events]
                out_ev = [x for x in out_ev if x is not None]
                bpb = 4.0
                _json_out(
                    {
                        "type": "chorus_phrase",
                        "ok": True,
                        "emotion": str(getattr(em, "name", "") or ""),
                        "bars": bars,
                        "root": root,
                        "beats_per_bar": int(bpb),
                        "section_duration_beats": _beat_float_for_json(float(bars) * bpb),
                        "form_mode": form_mode,
                        "section_role": "b",
                        "event_count": len(out_ev),
                        "events": out_ev,
                    }
                )
                continue

            if op in {"chorus_profile", "get_chorus_profile"}:
                emo = str(msg.get("emotion", "") or controller.get_scene_snapshot().get("emotion", "") or "").strip()
                role = str(msg.get("role", "chorus") or "chorus").strip()
                arp = chorus_reference_arp_overrides(emotion_name=str(emo), section_role=str(role))
                mel = chorus_reference_melody_overrides(emotion_name=str(emo), section_role=str(role))
                phrase = melody_phrase_profile_for_emotion(str(emo))
                _json_out(
                    {
                        "type": "chorus_profile",
                        "ok": True,
                        "emotion": emo,
                        "role": role,
                        "arp_overrides": dict(arp or {}),
                        "melody_overrides": dict(mel or {}),
                        "phrase_profile": dict(phrase or {}),
                    }
                )
                continue

            _json_out({"type": "error", "ok": False, "error": "unknown_op", "op": op})
    finally:
        try:
            player.stop()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

