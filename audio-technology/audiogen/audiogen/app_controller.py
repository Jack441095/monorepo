from __future__ import annotations

import logging
import math
import random
import secrets
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from data.style_architecture_macros import (
    STYLE_ARCHITECTURE_MACROS,
    apply_style_architecture,
    canonical_style_name,
)
from utils.cli_dialogue import parse_on_off as _cli_parse_on_off


class AppController:
    """
    Thin command/controller surface for CLI today, GUI tomorrow.

    This keeps interaction logic out of ``main.py`` and gives frontends a single
    command entrypoint (`execute_command`) they can reuse.
    """

    HELP_TEXT = (
        "Commands: <index> | list | e <name|index> | n | root <midi> | "
        "fresh | variety <0..1> | "
        "menu | replay | save | save wav | save midi | "
        "drums [show|on|off] | "
        "notelog on|off|show|path <file>|console on|off | "
        "presets | preset <name> | "
        "forms | form <name> | "
        "arpboost [off|on|<db>] | "
        "pause | resume | p | "
        "boundary <bars> | handoff <bars|on|off> | "
        "dialogue <0..1> | dialogue preset <off|tight|strong|experimental|clear> | "
        "melody | melody show | melody pos|rpc|vl on|off [strength] | "
        "stats (buffer/tier) | health [log_path] | help | q"
    )
    SWING_LEVELS = ("off", "light", "medium", "heavy")
    _SWING_TO_AMOUNTS = {
        "off": (False, 0.00, 0.00),
        "light": (True, 0.04, 0.06),
        "medium": (True, 0.08, 0.10),
        "heavy": (True, 0.12, 0.14),
    }

    def __init__(
        self,
        *,
        player,
        config,
        emotions: Sequence,
        container,
        root_default: int,
        emotion_index_by_name: Callable[[str], int],
        rng: Optional[random.Random] = None,
    ):
        self.player = player
        self.config = config
        self.emotions = emotions
        self.container = container
        self.root_default = int(root_default)
        self.emotion_index_by_name = emotion_index_by_name
        self.rng = rng or random.Random()
        self._style_architecture_name = str(
            canonical_style_name(getattr(self.config, "active_style_profile", "default") or "default")
        )
        self._arp_base_volume = self._get_arp_volume()
        self._arp_boost_db = 0.0

    @staticmethod
    def _db_to_gain(db: float) -> float:
        return float(math.pow(10.0, float(db) / 20.0))

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return float(max(float(lo), min(float(hi), float(v))))

    def _available_forms(self) -> List[str]:
        try:
            from composition.policies import ArrangementPolicy

            seq = getattr(ArrangementPolicy, "_FORM_SEQUENCES", {}) or {}
            out = sorted(str(k).strip() for k in dict(seq).keys() if str(k).strip())
        except Exception:
            out = []
        if "default" not in out:
            out.insert(0, "default")
        return out

    def _set_form_mode(self, mode: str) -> None:
        comp = getattr(self.config, "composition", None)
        if comp is not None:
            setattr(comp, "arranged_song_mode", str(mode))
            setattr(comp, "arranged_songs_default", True)
            # Realtime scheduler can consume this immediately when available.
            setattr(comp, "realtime_form_mode_override", str(mode))
        for owner in (getattr(self.player, "generator", None), getattr(self.player, "composer", None), self.player):
            try:
                pol = getattr(owner, "arrangement_policy", None)
                if pol is not None:
                    setattr(pol, "form_mode", str(mode))
            except Exception:
                pass

    def _get_arp_volume(self) -> float:
        try:
            strips = getattr(getattr(self.config, "audio", None), "mixer_strips", {}) or {}
            if 3 in strips and hasattr(strips[3], "volume"):
                return float(getattr(strips[3], "volume", 0.18) or 0.18)
        except Exception:
            pass
        try:
            mix = getattr(getattr(self.config, "audio", None), "channel_mix", {}) or {}
            return float((mix.get(3) or {}).get("volume", 0.18) or 0.18)
        except Exception:
            pass
        return 0.18

    def _set_arp_volume(self, volume: float) -> None:
        v = self._clamp(float(volume), 0.0, 2.0)
        try:
            strips = getattr(getattr(self.config, "audio", None), "mixer_strips", None)
            if isinstance(strips, dict) and 3 in strips and hasattr(strips[3], "volume"):
                setattr(strips[3], "volume", float(v))
        except Exception:
            pass
        try:
            mix = getattr(getattr(self.config, "audio", None), "channel_mix", None)
            if isinstance(mix, dict):
                cur = dict(mix.get(3, {}))
                cur["volume"] = float(v)
                mix[3] = cur
        except Exception:
            pass
        try:
            mx = getattr(self.container, "mixer", None)
            if mx is not None and hasattr(mx, "set_channel_volume"):
                mx.set_channel_volume(3, float(v))
        except Exception:
            pass

    def _set_arp_boost_db(self, db: float) -> float:
        self._arp_boost_db = self._clamp(float(db), -24.0, 24.0)
        base = max(1e-4, float(self._arp_base_volume))
        vol = self._clamp(base * self._db_to_gain(self._arp_boost_db), 0.0, 2.0)
        self._set_arp_volume(vol)
        return float(vol)

    def _log_melody_dialogue_status(self) -> None:
        comp = getattr(self.config, "composition", None)
        if comp is None:
            logging.info("melody: (no composition config)")
            return
        logging.info(
            "dialogue: amount=%.3f preset=%r",
            float(getattr(comp, "dialogue_amount", 0.0) or 0.0),
            str(getattr(comp, "dialogue_preset", "") or ""),
        )
        logging.info(
            "melody: pos=%s %.2f | rpc=%s %.2f | vl=%s %.2f",
            bool(getattr(comp, "melody_position_conditioning_enabled", False)),
            float(getattr(comp, "melody_position_conditioning_strength", 0.75) or 0.75),
            bool(getattr(comp, "melody_rhythm_pitch_coupling_enabled", False)),
            float(getattr(comp, "melody_rhythm_pitch_coupling_strength", 0.65) or 0.65),
            bool(getattr(comp, "melody_voiceleading_rerank_enabled", False)),
            float(getattr(comp, "melody_voiceleading_rerank_strength", 0.60) or 0.60),
        )
        logging.info(
            "composition: melody_amount_scale=%.2f motif_use=%.2f motif_var=%.2f hook_dev=%.2f | "
            "harmony_dev=%.2f (enabled=%s) | counter_melody=%s | bestofk=%s k=%d jitter=%.2f",
            float(getattr(comp, "melody_amount_scale", 1.0) or 1.0),
            float(getattr(comp, "motif_use_chance", 0.0) or 0.0),
            float(getattr(comp, "motif_variation_prob", 0.0) or 0.0),
            float(getattr(comp, "hook_development", 0.5) or 0.5),
            float(getattr(comp, "harmony_development_strength", 0.0) or 0.0),
            bool(getattr(comp, "harmony_development_enabled", True)),
            bool(getattr(comp, "counter_melody_enabled", False)),
            bool(getattr(comp, "bestofk_enabled", False)),
            int(getattr(comp, "bestofk_k", 1) or 1),
            float(getattr(comp, "bestofk_temperature_jitter", 0.0) or 0.0),
        )

    def _log_runtime_health(self, log_path: Optional[str] = None) -> None:
        try:
            from tools.rt_log_health import summarize_runtime_log
        except Exception:
            logging.exception("health: failed to import tools.rt_log_health")
            return
        p = Path(str(log_path or "logs/runtime.log")).expanduser().resolve()
        if not p.exists():
            logging.warning("health: log not found: %s", str(p))
            return
        try:
            s = summarize_runtime_log(p)
            logging.info("health: log=%s", str(p))
            logging.info(
                "health: time_range=%s -> %s sessions=%d lines=%d",
                str(s.get("first_ts", "") or ""),
                str(s.get("last_ts", "") or ""),
                int(s.get("sessions", 0) or 0),
                int(s.get("lines", 0) or 0),
            )
            logging.info(
                "health: underruns=%d callback_underflows=%d portaudio_underflows=%d",
                int(s.get("buffer_underruns", 0) or 0),
                int(s.get("callback_underflows", 0) or 0),
                int(s.get("portaudio_underflows", 0) or 0),
            )
            logging.info(
                "health: slow_bars=%d avg_ratio=%.2fx max_ratio=%.2fx",
                int(s.get("slow_bar_count", 0) or 0),
                float(s.get("slow_bar_avg_ratio", 0.0) or 0.0),
                float(s.get("slow_bar_max_ratio", 0.0) or 0.0),
            )
        except Exception:
            logging.exception("health: failed to summarize %s", str(p))

    @staticmethod
    def _parse_bool(v: Any) -> Optional[bool]:
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, (int, float)):
            return bool(int(v))
        s = str(v or "").strip().lower()
        if s in {"1", "true", "on", "yes", "y"}:
            return True
        if s in {"0", "false", "off", "no", "n"}:
            return False
        return None

    def _apply_runtime_config(self) -> None:
        try:
            self.config.rebuild_samplers()
        except Exception:
            pass
        try:
            self.container.apply_audio_config(self.config)
        except Exception:
            pass

    def _drums_enabled(self) -> bool:
        try:
            sc = getattr(getattr(self.config, "audio", None), "chorus_kick_sidechain", None)
            return bool(getattr(sc, "enabled", False)) if sc is not None else False
        except Exception:
            return False

    def _set_drums_enabled(self, enabled: bool) -> None:
        on = bool(enabled)
        try:
            sc = getattr(getattr(self.config, "audio", None), "chorus_kick_sidechain", None)
            if sc is not None:
                sc.enabled = on
                sc.kick_enabled = on
                sc.sidechain_enabled = on
        except Exception:
            pass
        try:
            comp = getattr(self.config, "composition", None)
            if comp is not None:
                setattr(comp, "percussion_lane_enabled", on)
        except Exception:
            pass
        self._apply_runtime_config()

    def _capture_current_fx_state(self) -> Dict[str, float]:
        state: Dict[str, float] = {}
        try:
            mb = getattr(self.container, "master_bus", None)
            if mb is not None:
                state["reverb_return_wet"] = float(getattr(mb, "reverb_return_wet", 0.5) or 0.5)
                state["distortion_drive"] = float(
                    getattr(getattr(mb, "distortion", None), "drive", 1.35) or 1.35
                )
                state["distortion_mix"] = float(
                    getattr(mb, "distortion_return_level", getattr(self.config.audio, "distortion_mix", 0.08)) or 0.08
                )
        except Exception:
            pass
        try:
            rev = getattr(self.container, "reverb", None)
            if rev is not None:
                state["reverb_rt60"] = float(getattr(rev, "rt60", getattr(self.config.audio, "reverb_rt60", 0.8)) or 0.8)
                state["reverb_damping"] = float(
                    getattr(rev, "damping", getattr(self.config.audio, "reverb_damping", 0.5)) or 0.5
                )
                state["reverb_wet_proc"] = float(getattr(rev, "wet", getattr(self.config.audio, "reverb_wet", 0.3)) or 0.3)
        except Exception:
            pass
        return state

    def _normalize_swing_level(self, value: Any) -> Optional[str]:
        b = self._parse_bool(value)
        if b is not None:
            return "medium" if bool(b) else "off"
        if isinstance(value, (int, float)):
            try:
                x = float(value)
            except Exception:
                x = 0.0
            if x <= 1e-9:
                return "off"
            if x < 0.20:
                return "light"
            if x < 0.60:
                return "medium"
            return "heavy"
        s = str(value or "").strip().lower()
        if s in self.SWING_LEVELS:
            return s
        return None

    def _infer_swing_level(self) -> str:
        comp = getattr(self.config, "composition", None)
        if comp is None:
            return "off"
        enabled = bool(getattr(comp, "swing_enabled", False) or getattr(comp, "melody_swing_enabled", False))
        if not enabled:
            return "off"
        try:
            a = max(
                float(getattr(comp, "swing_amount", 0.0) or 0.0),
                float(getattr(comp, "melody_swing_amount", 0.0) or 0.0),
            )
        except Exception:
            a = 0.0
        if a < 0.07:
            return "light"
        if a < 0.13:
            return "medium"
        return "heavy"

    def get_scene_contract(self) -> Dict[str, Any]:
        """
        Explicit mapping contract for GUI clients.
        """
        return {
            "version": 1,
            "scene_semantics": "partial_update",
            "required_fields": [],
            "controls": {
                "tempo": {"type": "number", "range": [40.0, 200.0]},
                "emotion": {"type": "string_or_index"},
                "arrangement_type": {"type": "string"},
                "instrument_source": {"type": "enum", "enum": ["sampler", "piano"]},
                "style": {"type": "string"},
                "fx_preset": {"type": "string"},
                "swing": {
                    "type": "enum_or_bool",
                    "enum": list(self.SWING_LEVELS),
                    "bool_backward_compatible": True,
                },
            },
        }

    def get_ui_schema(self) -> Dict[str, Any]:
        """
        GUI-facing schema for controls and choice sets.
        """
        profile_styles = set(str(k) for k in dict(getattr(self.config, "style_profiles", {}) or {}).keys())
        macro_styles = set(str(k) for k in dict(STYLE_ARCHITECTURE_MACROS or {}).keys())
        styles = sorted(profile_styles | macro_styles)
        fx = sorted(str(k) for k in dict(getattr(self.config, "post_process_presets", {}) or {}).keys())
        emotions = [str(getattr(e, "name", "") or "") for e in (self.emotions or []) if str(getattr(e, "name", "") or "")]
        arrangement_choices: List[str] = []
        try:
            from composition.policies import ArrangementPolicy

            seq = getattr(ArrangementPolicy, "_FORM_SEQUENCES", {}) or {}
            arrangement_choices = sorted(str(k) for k in dict(seq).keys() if str(k))
        except Exception:
            arrangement_choices = []
        if "default" not in arrangement_choices:
            arrangement_choices = ["default"] + arrangement_choices
        return {
            "tempo": {"type": "number", "min": 40.0, "max": 200.0, "step": 1.0},
            "emotion": {"type": "choice", "options": emotions},
            "arrangement_type": {"type": "choice", "options": arrangement_choices},
            "instrument_source": {"type": "choice", "options": ["sampler", "piano"]},
            "style": {"type": "choice", "options": styles},
            "fx_preset": {"type": "choice", "options": fx},
            "swing": {
                "type": "choice",
                "options": list(self.SWING_LEVELS),
                "accepts_boolean": True,
            },
        }

    def get_scene_snapshot(self) -> Dict[str, Any]:
        """
        Read current runtime + config values in the 6-control shape.
        """
        comp = getattr(self.config, "composition", None)
        emo_name = str(getattr(getattr(self.player, "emotion", None), "name", "") or "")
        return {
            "tempo": float(getattr(comp, "default_tempo", 70.0) or 70.0) if comp is not None else 70.0,
            "emotion": emo_name,
            "arrangement_type": str(getattr(comp, "arranged_song_mode", "default") or "default") if comp is not None else "default",
            "instrument_source": str(getattr(comp, "instrument_source", "sampler") or "sampler"),
            "style": str(getattr(self, "_style_architecture_name", "") or ""),
            "fx_preset": str(getattr(self.config, "active_post_process_preset", "") or ""),
            "swing": self._infer_swing_level(),
        }

    def apply_scene(self, scene: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply GUI scene controls:
        - tempo
        - emotion
        - arrangement_type
        - style
        - fx_preset
        - swing
        """
        out: Dict[str, Any] = {"ok": True, "applied": {}, "warnings": []}
        data = dict(scene or {})
        comp = getattr(self.config, "composition", None)
        fx_changed = False
        fx_start_state: Dict[str, float] = {}

        # 1) Style first (can carry broad profile defaults).
        if "style" in data and data.get("style") not in (None, ""):
            style = str(data.get("style")).strip()
            style_key = canonical_style_name(style)
            style_profile_applied = False
            try:
                self.config.set_style_profile(style)
                style_profile_applied = True
            except Exception:
                # Profile set is optional; macro layer can still drive composition behavior.
                style_profile_applied = False
            macro_applied = False
            try:
                macro_applied = apply_style_architecture(getattr(self.config, "composition", None), style_key)
            except Exception:
                macro_applied = False
            if style_profile_applied or macro_applied:
                self._style_architecture_name = str(style_key or style)
                out["applied"]["style"] = str(self._style_architecture_name)
            else:
                out["ok"] = False
                out["warnings"].append(f"Unknown style '{style}'")

        # 2) Arrangement mode.
        if comp is not None and "arrangement_type" in data and data.get("arrangement_type") not in (None, ""):
            mode = str(data.get("arrangement_type")).strip()
            try:
                comp.arranged_song_mode = str(mode or "default")
                comp.arranged_songs_default = True
                out["applied"]["arrangement_type"] = comp.arranged_song_mode
            except Exception:
                out["ok"] = False
                out["warnings"].append(f"Failed to set arrangement_type '{mode}'")

        # 2.5) Instrument source (sampler|piano).
        if comp is not None and "instrument_source" in data and data.get("instrument_source") not in (None, ""):
            src = str(data.get("instrument_source")).strip().lower()
            if src in {"sampler", "piano"}:
                try:
                    comp.instrument_source = str(src)
                    out["applied"]["instrument_source"] = str(src)
                except Exception:
                    out["ok"] = False
                    out["warnings"].append(f"Failed to set instrument_source '{src}'")
            else:
                out["ok"] = False
                out["warnings"].append(f"Invalid instrument_source '{src}' (expected sampler|piano)")

        # 3) Tempo.
        if comp is not None and "tempo" in data and data.get("tempo") not in (None, ""):
            try:
                tempo = float(data.get("tempo"))
                tempo = max(40.0, min(200.0, float(tempo)))
                comp.default_tempo = float(tempo)
                out["applied"]["tempo"] = float(tempo)
            except Exception:
                out["ok"] = False
                out["warnings"].append(f"Invalid tempo '{data.get('tempo')}'")

        # 4) Swing architecture control (off/light/medium/heavy; bool still accepted).
        if comp is not None and "swing" in data and data.get("swing") not in (None, ""):
            level = self._normalize_swing_level(data.get("swing"))
            if level is None:
                out["ok"] = False
                out["warnings"].append(f"Invalid swing '{data.get('swing')}'")
            else:
                enabled, swing_amt, melody_swing_amt = self._SWING_TO_AMOUNTS.get(str(level), (False, 0.0, 0.0))
                comp.swing_enabled = bool(enabled)
                comp.melody_swing_enabled = bool(enabled)
                comp.swing_amount = float(swing_amt)
                comp.melody_swing_amount = float(melody_swing_amt)
                out["applied"]["swing"] = str(level)

        # 5) FX preset.
        if "fx_preset" in data and data.get("fx_preset") not in (None, ""):
            fx = str(data.get("fx_preset")).strip()
            try:
                fx_start_state = self._capture_current_fx_state()
                self.config.set_post_process_preset(fx)
                out["applied"]["fx_preset"] = fx
                fx_changed = True
            except Exception:
                out["ok"] = False
                out["warnings"].append(f"Unknown fx_preset '{fx}'")

        # Push updated config into runtime systems.
        self._apply_runtime_config()
        if fx_changed:
            try:
                emo_name = str(data.get("emotion", "") or str(getattr(getattr(self.player, "emotion", None), "name", "") or ""))
                style_name = str(data.get("style", "") or str(getattr(self, "_style_architecture_name", "") or "default"))
                if hasattr(self.player, "queue_fx_preset_transition"):
                    self.player.queue_fx_preset_transition(
                        style_name=str(style_name),
                        emotion_name=str(emo_name),
                        start_state=dict(fx_start_state or {}),
                    )
            except Exception:
                pass

        # 6) Emotion switch last so the next bars use updated scene settings.
        if "emotion" in data and data.get("emotion") not in (None, ""):
            target = str(data.get("emotion")).strip()
            idx = None
            try:
                idx = int(target)
            except Exception:
                idx = self.emotion_index_by_name(target)
            if idx is None or not (0 <= int(idx) < len(self.emotions)):
                out["ok"] = False
                out["warnings"].append(f"Unknown emotion '{target}'")
            else:
                try:
                    # If enabled, reseed + reset per-song memory so an emotion click produces
                    # a fresh variation rather than replaying the same deterministic choices.
                    try:
                        reseed_on_change = bool(getattr(comp, "reseed_on_emotion_change_enabled", True)) if comp is not None else True
                    except Exception:
                        reseed_on_change = True
                    if reseed_on_change:
                        try:
                            gen = getattr(getattr(self.player, "composer", None), "gen", None)
                            if gen is not None and hasattr(gen, "reseed"):
                                new_seed = int(secrets.randbits(32))
                                try:
                                    # Keep config in sync so deterministic_rng uses the new base.
                                    if comp is not None:
                                        comp.seed = int(new_seed)
                                except Exception:
                                    pass
                                try:
                                    gen.reseed(int(new_seed))
                                except Exception:
                                    pass
                                try:
                                    gen.reset_song_arrangement_state()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    root = int(getattr(self.player, "root", self.root_default) or self.root_default)
                    self.player.load_emotion(int(idx), int(root))
                    out["applied"]["emotion"] = str(self.emotions[int(idx)].name)
                except Exception:
                    out["ok"] = False
                    out["warnings"].append(f"Failed to load emotion '{target}'")

        out["scene"] = self.get_scene_snapshot()
        out["contract_version"] = int(self.get_scene_contract().get("version", 1))
        return out

    def execute_command(self, command: str) -> bool:
        """
        Execute one user command.

        Returns:
            True to continue loop, False to request shutdown.
        """
        c = (command or "").strip()
        if not c:
            return True

        def _maybe_reseed_for_fresh_emotion_click() -> None:
            """
            Reseed the runtime generator + reset per-song memory so repeated
            emotion switches do not replay the same deterministic choices.
            """
            comp = getattr(self.config, "composition", None)
            try:
                reseed_on_change = bool(getattr(comp, "reseed_on_emotion_change_enabled", True)) if comp is not None else True
            except Exception:
                reseed_on_change = True
            if not reseed_on_change:
                return
            try:
                import secrets

                gen = getattr(getattr(self.player, "composer", None), "gen", None)
                if gen is None or not hasattr(gen, "reseed"):
                    return
                new_seed = int(secrets.randbits(32))
                try:
                    # Keep config in sync so deterministic_rng uses the new base.
                    if comp is not None:
                        comp.seed = int(new_seed)
                except Exception:
                    pass
                try:
                    gen.reseed(int(new_seed))
                except Exception:
                    pass
                try:
                    gen.reset_song_arrangement_state()
                except Exception:
                    pass
            except Exception:
                # Best-effort; never block an emotion switch on reseeding.
                return

        # Numeric-only shortcut: pressing a number + Enter switches emotion by index.
        if c.isdigit():
            try:
                idx2 = int(c)
            except Exception:
                idx2 = -1
            if 0 <= int(idx2) < len(self.emotions):
                _maybe_reseed_for_fresh_emotion_click()
                self.player.load_emotion(int(idx2), int(self.player.root or self.root_default))
                logging.info("Queued emotion (numeric): %s", str(self.emotions[int(idx2)].name))
            else:
                logging.warning("Emotion index %s out of range. Try: list", c)
            return True

        parts = c.split()
        op = parts[0].strip().lower()

        if op in {"q", "quit", "exit"}:
            return False
        if op in {"help", "h", "?"}:
            logging.info(self.HELP_TEXT)
            return True

        if op in {"fresh", "reseed"}:
            # Force a brand-new song immediately (same emotion/root).
            _maybe_reseed_for_fresh_emotion_click()
            try:
                cur_name = str(getattr(self.player.emotion, "name", "neutral"))
            except Exception:
                cur_name = "neutral"
            try:
                idx = int(self.emotion_index_by_name(cur_name))
            except Exception:
                idx = 0
            try:
                root = int(getattr(self.player, "root", self.root_default) or self.root_default)
            except Exception:
                root = int(self.root_default)
            self.player.load_emotion(int(idx), int(root))
            logging.info("Fresh variation queued (emotion=%s root=%d).", str(cur_name), int(root))
            return True

        if op in {"variety", "vary"}:
            # Loosen "stabilizers" that intentionally keep per-emotion output consistent.
            # 0.0 = tighter / more consistent; 1.0 = more exploratory.
            if len(parts) < 2:
                logging.info("Usage: variety <0..1>  (e.g. variety 0.0 | variety 0.6 | variety 1.0)")
                return True
            try:
                amt = float(parts[1])
            except Exception:
                logging.info("Usage: variety <0..1>")
                return True
            amt = self._clamp(float(amt), 0.0, 1.0)
            comp = getattr(self.config, "composition", None)
            if comp is None:
                logging.warning("No composition config available")
                return True
            try:
                # Prefer new chord openings / gentle register drift.
                setattr(comp, "section_sampler_novelty_enabled", bool(amt > 1e-6))
                setattr(comp, "section_sampler_novelty_weight", float(0.10 + 0.25 * amt))
                setattr(comp, "section_sampler_chord_novelty_weight", float(0.06 + 0.18 * amt))
                setattr(comp, "section_sampler_register_novelty_weight", float(0.04 + 0.12 * amt))
            except Exception:
                pass
            try:
                # Loosen the per-emotion arp style lock so arps vary more.
                setattr(comp, "arp_style_table_strength", float(self._clamp(0.95 - 0.75 * amt, 0.0, 1.0)))
                setattr(comp, "arp_allow_mode_variation_enabled", bool(amt >= 0.25))
            except Exception:
                pass
            try:
                # Allow wider per-bar temperature range for the melody Markov.
                setattr(comp, "melody_bar_temperature_mult_max", float(self._clamp(1.35 + 0.65 * amt, 1.0, 3.0)))
                setattr(comp, "melody_bar_temperature_mult_min", float(self._clamp(0.80 - 0.30 * amt, 0.3, 1.0)))
            except Exception:
                pass
            try:
                # Reduce motif "same hook" pressure a bit as variety increases.
                setattr(comp, "motif_use_chance", float(self._clamp(0.88 - 0.35 * amt, 0.15, 0.95)))
                setattr(comp, "motif_variation_prob", float(self._clamp(0.12 + 0.55 * amt, 0.0, 1.0)))
            except Exception:
                pass

            logging.info(
                "variety=%.2f applied (arp_style_strength=%.2f novelty=%s)",
                float(amt),
                float(getattr(comp, "arp_style_table_strength", 0.0) or 0.0),
                "on" if bool(getattr(comp, "section_sampler_novelty_enabled", False)) else "off",
            )
            return True

        if op in {"drums", "drum", "kick"}:
            sub = parts[1].strip().lower() if len(parts) >= 2 else "show"
            if sub in {"", "show", "status"}:
                logging.info("drums: %s", "on" if self._drums_enabled() else "off")
                return True
            b = _cli_parse_on_off(sub)
            if b is None:
                logging.warning("Usage: drums [show|on|off]")
                return True
            self._set_drums_enabled(bool(b))
            logging.info("drums: %s", "on" if bool(b) else "off")
            return True

        if op in {"notelog", "note-log"} or (op == "note" and len(parts) >= 2 and parts[1].strip().lower() == "log"):
            comp = getattr(self.config, "composition", None)
            if comp is None:
                logging.warning("No composition config available")
                return True
            # Normalize: `note log ...` -> `notelog ...`
            if op == "note" and len(parts) >= 2 and parts[1].strip().lower() == "log":
                parts = ["notelog"] + parts[2:]

            sub = parts[1].strip().lower() if len(parts) >= 2 else ""
            if sub in {"", "show", "status"}:
                logging.info(
                    "notelog: enabled=%s path=%r console=%s",
                    bool(getattr(comp, "note_log_enabled", False)),
                    str(getattr(comp, "note_log_path", "logs/note_log.csv") or "logs/note_log.csv"),
                    "on" if bool(getattr(comp, "note_log_console_enabled", False)) else "off",
                )
                return True
            if sub in {"on", "enable", "true", "1"}:
                setattr(comp, "note_log_enabled", True)
                logging.info("notelog: enabled (path=%r)", str(getattr(comp, "note_log_path", "") or ""))
                return True
            if sub in {"off", "disable", "false", "0"}:
                setattr(comp, "note_log_enabled", False)
                logging.info("notelog: disabled")
                return True
            if sub in {"path"}:
                if len(parts) < 3:
                    logging.warning("Usage: notelog path <file>")
                    return True
                p = " ".join(parts[2:]).strip()
                if not p:
                    logging.warning("Usage: notelog path <file>")
                    return True
                setattr(comp, "note_log_path", str(Path(p).expanduser()))
                logging.info("notelog: path=%r", str(getattr(comp, "note_log_path", "") or ""))
                return True
            if sub in {"console"}:
                if len(parts) < 3:
                    logging.warning("Usage: notelog console on|off")
                    return True
                b = _cli_parse_on_off(parts[2])
                if b is None:
                    logging.warning("Usage: notelog console on|off")
                    return True
                setattr(comp, "note_log_console_enabled", bool(b))
                logging.info("notelog: console=%s", "on" if bool(b) else "off")
                return True

            logging.warning("Usage: notelog on|off|show|path <file>|console on|off")
            return True
        if op in {"list", "ls", "emotions"}:
            names = [str(em.name) for em in (self.emotions or [])]
            logging.info("Emotions (%d): %s", len(names), ", ".join(names))
            return True
        if op in {"stats"}:
            try:
                st = self.player.get_stats()
                logging.info("Stats: %s", st)
            except Exception:
                logging.exception("Failed to read stats")
            return True
        if op in {"health", "rthealth"}:
            p = None
            if len(parts) >= 2:
                p = " ".join(parts[1:]).strip()
            self._log_runtime_health(p)
            return True
        if op in {"pause", "hold"}:
            self.player.pause()
            logging.info("Playback paused (buffer frozen; generation paused).")
            return True
        if op in {"resume", "play", "unpause"}:
            self.player.resume()
            logging.info("Playback resumed.")
            return True
        if op in {"p"}:
            self.player.toggle_pause()
            logging.info("Playback %s", "paused" if self.player.paused else "resumed")
            return True
        if op in {"root", "r"} and len(parts) >= 2:
            try:
                new_root = int(parts[1])
            except Exception:
                logging.warning("Invalid root. Usage: root <midi>")
                return True
            cur_name = str(getattr(self.player.emotion, "name", "neutral"))
            self.player.load_emotion(self.emotion_index_by_name(cur_name), int(new_root))
            logging.info("Queued root change: %d", int(new_root))
            return True
        if op in {"e", "emo", "emotion"} and len(parts) >= 2:
            target = " ".join(parts[1:]).strip()
            idx2: Optional[int]
            try:
                idx2 = int(target)
            except Exception:
                idx2 = self.emotion_index_by_name(target)
            if not (0 <= int(idx2) < len(self.emotions)):
                logging.warning("Unknown emotion '%s'. Try: list", target)
                return True
            _maybe_reseed_for_fresh_emotion_click()
            self.player.load_emotion(int(idx2), int(self.player.root or self.root_default))
            logging.info("Queued emotion: %s", str(self.emotions[int(idx2)].name))
            return True
        if op in {"n", "next", "rand", "random"}:
            names = [
                str(em.name).strip().lower()
                for em in (self.emotions or [])
                if str(getattr(em, "name", "")).strip()
            ]
            if not names:
                logging.warning("No emotions available")
                return True
            cur = str(getattr(self.player.emotion, "name", "") or "").strip().lower()
            choices = [x for x in names if x != cur] or names
            picked = self.rng.choice(choices)
            idx2 = self.emotion_index_by_name(picked)
            _maybe_reseed_for_fresh_emotion_click()
            self.player.load_emotion(int(idx2), int(self.player.root or self.root_default))
            logging.info("Queued random emotion: %s", str(self.emotions[int(idx2)].name))
            return True

        if op in {"boundary", "phrase", "grid"} and len(parts) >= 2:
            try:
                b = max(1, int(parts[1]))
            except Exception:
                logging.warning("Usage: boundary <bars>  (e.g. boundary 1 | boundary 2 | boundary 4)")
                return True
            try:
                setattr(self.config.audio, "emotion_transition_boundary_bars", int(b))
            except Exception:
                try:
                    self.config.audio.emotion_transition_boundary_bars = int(b)
                except Exception:
                    pass
            logging.info(
                "emotion_transition_boundary_bars=%d (lower=faster `n`, higher=smoother)", int(b)
            )
            return True

        if op in {"handoff", "fastchunk", "switch"} and len(parts) >= 2:
            comp = getattr(self.config, "composition", None)
            if comp is None:
                logging.warning("No composition config")
                return True
            v = parts[1].strip().lower()
            if v in {"on", "true", "1", "enable", "enabled"}:
                setattr(comp, "emotion_switch_fast_chunk_enabled", True)
                logging.info("emotion_switch_fast_chunk_enabled=True")
                return True
            if v in {"off", "false", "0", "disable", "disabled"}:
                setattr(comp, "emotion_switch_fast_chunk_enabled", False)
                logging.info("emotion_switch_fast_chunk_enabled=False")
                return True
            try:
                n = int(v)
            except Exception:
                logging.warning("Usage: handoff <bars|on|off>  (e.g. handoff 2 | handoff 4 | handoff off)")
                return True
            n = max(1, min(8, int(n)))
            setattr(comp, "emotion_switch_fast_chunk_enabled", True)
            setattr(comp, "emotion_switch_fast_chunk_bars", int(n))
            logging.info("emotion_switch_fast_chunk_bars=%d (enabled)", int(n))
            return True

        if op == "dialogue":
            comp = getattr(self.config, "composition", None)
            if comp is None:
                logging.warning("No composition config")
                return True
            if len(parts) == 1:
                self._log_melody_dialogue_status()
                return True
            if len(parts) >= 2 and parts[1].strip().lower() == "preset":
                if len(parts) < 3:
                    logging.warning("Usage: dialogue preset <off|tight|strong|experimental|clear>")
                    return True
                name = parts[2].strip().lower()
                if name == "clear":
                    setattr(comp, "dialogue_preset", "")
                elif name in {"off", "tight", "strong", "experimental"}:
                    setattr(comp, "dialogue_preset", name)
                else:
                    logging.warning("Unknown dialogue preset %r", name)
                    return True
                self.config.apply_dialogue_macro()
                logging.info(
                    "dialogue preset=%r amount=%.3f (macro applied)",
                    str(getattr(comp, "dialogue_preset", "") or ""),
                    float(getattr(comp, "dialogue_amount", 0.0) or 0.0),
                )
                return True
            try:
                amt = float(parts[1])
            except Exception:
                logging.warning("Usage: dialogue <0..1> | dialogue preset <name> | dialogue (show)")
                return True
            amt = max(0.0, min(1.0, float(amt)))
            setattr(comp, "dialogue_amount", float(amt))
            self.config.apply_dialogue_macro()
            logging.info(
                "dialogue amount=%.3f (macro applied)",
                float(getattr(comp, "dialogue_amount", 0.0) or 0.0),
            )
            return True

        if op == "melody":
            comp = getattr(self.config, "composition", None)
            if comp is None:
                logging.warning("No composition config")
                return True
            if len(parts) == 1 or (len(parts) == 2 and parts[1].strip().lower() in {"show", "status"}):
                self._log_melody_dialogue_status()
                return True
            if len(parts) >= 3:
                sub = parts[1].strip().lower()
                if sub not in {"pos", "rpc", "vl"}:
                    logging.warning("Usage: melody | melody show | melody pos|rpc|vl on|off [0..1]")
                    return True
                b = _cli_parse_on_off(parts[2])
                if b is None:
                    logging.warning("Expected on|off (or 1|0) after melody %s", sub)
                    return True
                strength = None
                if len(parts) >= 4:
                    try:
                        strength = float(parts[3])
                    except Exception:
                        logging.warning("Invalid strength; expected 0..1")
                        return True
                    strength = max(0.0, min(1.0, float(strength)))
                if sub == "pos":
                    setattr(comp, "melody_position_conditioning_enabled", bool(b))
                    if strength is not None:
                        setattr(comp, "melody_position_conditioning_strength", float(strength))
                elif sub == "rpc":
                    setattr(comp, "melody_rhythm_pitch_coupling_enabled", bool(b))
                    if strength is not None:
                        setattr(comp, "melody_rhythm_pitch_coupling_strength", float(strength))
                else:
                    setattr(comp, "melody_voiceleading_rerank_enabled", bool(b))
                    if strength is not None:
                        setattr(comp, "melody_voiceleading_rerank_strength", float(strength))
                logging.info(
                    "melody %s=%s%s",
                    sub,
                    bool(b),
                    f" strength={float(strength):.2f}" if strength is not None else "",
                )
                return True
            logging.warning("Usage: melody | melody show | melody pos|rpc|vl on|off [strength]")
            return True

        if op in {"presets", "preset-list"}:
            try:
                from presets import list_presets

                ps = list_presets()
                if not ps:
                    logging.info("No meta presets found in .audiogen/presets")
                else:
                    logging.info("Meta presets (%d): %s", len(ps), ", ".join(ps))
            except Exception:
                logging.exception("Failed to list meta presets")
            return True

        if op in {"forms", "form-list"}:
            forms = self._available_forms()
            cur = str(getattr(getattr(self.config, "composition", None), "arranged_song_mode", "default") or "default")
            logging.info("Forms (%d): %s", len(forms), ", ".join(forms))
            logging.info("Current form: %s", cur)
            return True

        if op in {"form", "arrangement", "arr"}:
            forms = self._available_forms()
            if len(parts) == 1:
                cur = str(getattr(getattr(self.config, "composition", None), "arranged_song_mode", "default") or "default")
                logging.info("Current form: %s | Available: %s", cur, ", ".join(forms))
                return True
            mode = str(parts[1]).strip().lower()
            if mode not in set(forms):
                logging.warning("Unknown form '%s'. Try: forms", mode)
                return True
            self._set_form_mode(mode)
            logging.info("Form set: %s (applies on next arranged sections)", mode)
            return True

        if op in {"arpboost", "arp-boost"}:
            if len(parts) == 1:
                cur = self._get_arp_volume()
                logging.info(
                    "arpboost: %.1f dB (arp volume=%.3f base=%.3f). Usage: arpboost [off|on|<db>]",
                    float(self._arp_boost_db),
                    float(cur),
                    float(self._arp_base_volume),
                )
                return True
            v = str(parts[1]).strip().lower()
            if v in {"off", "0", "reset"}:
                vol = self._set_arp_boost_db(0.0)
                logging.info("arpboost: off (0.0 dB, arp volume=%.3f)", float(vol))
                return True
            if v in {"on", "up", "boost"}:
                vol = self._set_arp_boost_db(6.0)
                logging.info("arpboost: on (+6.0 dB, arp volume=%.3f)", float(vol))
                return True
            try:
                db = float(parts[1])
            except Exception:
                logging.warning("Usage: arpboost [off|on|<db>]  (example: arpboost 8)")
                return True
            vol = self._set_arp_boost_db(db)
            logging.info("arpboost: %.1f dB (arp volume=%.3f)", float(self._arp_boost_db), float(vol))
            return True

        if op in {"preset", "meta"} and len(parts) >= 2:
            name = " ".join(parts[1:]).strip()
            if not name:
                logging.warning("Usage: preset <name>")
                return True
            try:
                from presets import load_preset
                from presets.config_applier import apply_macros_snapshot, apply_preset_to_config

                p = load_preset(str(name))
                apply_preset_to_config(self.config, p)
                apply_macros_snapshot(self.config, dict(getattr(p, "macros", {}) or {}))
                try:
                    self.config.rebuild_samplers()
                except Exception:
                    pass
                try:
                    self.container.apply_audio_config(self.config)
                except Exception:
                    pass
                # Keep the continuous drone loop stable: refresh other samplers so they adopt
                # the new preset/pack, but don't drop the loaded drone sampler instance.
                try:
                    if hasattr(self.player, "refresh_samplers_after_preset_change"):
                        self.player.refresh_samplers_after_preset_change(keep={"drone"})
                except Exception:
                    pass
                logging.info(
                    "Applied meta preset '%s' (pack=%s style=%s convo=%s fx=%s macros=%s)",
                    str(getattr(p, "name", name)),
                    str(getattr(p, "sample_pack", getattr(self.config, "active_sample_pack", ""))),
                    str(getattr(p, "style_profile", getattr(self.config, "active_style_profile", ""))),
                    str(
                        getattr(
                            p,
                            "conversation_preset",
                            getattr(self.config, "active_conversation_preset", ""),
                        )
                    ),
                    str(getattr(p, "fx_preset", getattr(self.config, "active_post_process_preset", ""))),
                    dict(getattr(p, "macros", {}) or {}),
                )
            except Exception:
                logging.exception("Failed to apply meta preset '%s'", name)
            return True

        logging.warning("Unknown command '%s'. Try: help", c)
        return True
