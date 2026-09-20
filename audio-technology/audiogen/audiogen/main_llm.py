# main_llm.py - J K Gandy 2026
#
# One-shot LLM integration entry point:
#   generate a random-seed chorus loop for an emotion, play 8 bars, then exit.
#
# Examples:
#   python main_llm.py --emotion joy
#   python main_llm.py --emotion 17 --seed 42
#   python main_llm.py --list-emotions-json
#   python main_llm.py --emotion love --no-play --include-events
#   python main_llm.py --emotion love --no-play --wav-out /tmp/love_chorus.wav
#   python main_llm.py --schema-json
#
# For long-running JSONL control and realtime arranged playback, use main_llm_chorus_only.py.

from __future__ import annotations

import argparse
import json
import secrets
import sys
from typing import Any, Dict, Optional

import numpy as np

DEFAULT_LOOP_BARS = 8

MAIN_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "audiogen_chorus_loop",
    "description": "Generate and optionally play or export one random-seed chorus loop for an emotion.",
    "entrypoint": "main_llm.py",
    "protocol": "spawn_process_read_last_stdout_json_line",
    "arguments": {
        "emotion": {"type": "string", "required": True, "description": "Emotion name or index (0-27)."},
        "seed": {"type": "integer", "required": False, "description": "Deterministic seed; random if omitted."},
        "bars": {"type": "integer", "default": DEFAULT_LOOP_BARS, "description": "Chorus length in bars (1-24)."},
        "root": {"type": "integer", "default": 60, "description": "MIDI root note."},
        "no_play": {"type": "boolean", "default": False, "description": "Skip realtime playback (headless)."},
        "wav_out": {"type": "string", "required": False, "description": "Write rendered stereo WAV to this path."},
        "include_events": {"type": "boolean", "default": False, "description": "Include symbolic events in JSON."},
    },
    "response_type": "chorus_loop_playback",
    "discovery": {"list_emotions_flag": "--list-emotions-json", "schema_flag": "--schema-json"},
}


def _json_out(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _resolve_seed(cli_seed: Optional[int]) -> int:
    if cli_seed is not None:
        return int(cli_seed)
    return int(secrets.randbelow(2**31 - 1))


def _fallback_bpm_for_emotion(emotion: Any) -> float:
    try:
        mult = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
    except Exception:
        mult = 1.0
    mult = max(0.5, min(2.0, float(mult)))
    return max(20.0, min(260.0, 70.0 * mult))


def _play_stereo_blocking(audio: np.ndarray, sample_rate: int) -> Optional[str]:
    if audio.size <= 0:
        return "empty_audio"
    try:
        import sounddevice as sd
    except Exception:
        return "sounddevice_unavailable"
    sd.play(np.asarray(audio, dtype=np.float32), int(sample_rate))
    sd.wait()
    return None


def _write_wav_file(path: str, audio: np.ndarray, sample_rate: int) -> Optional[str]:
    if audio.size <= 0:
        return "empty_audio"
    try:
        from scipy.io import wavfile
    except Exception:
        return "scipy_unavailable"
    wav_i16 = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype(np.int16)
    wavfile.write(str(path), int(sample_rate), wav_i16)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and play one random-seed chorus loop (default 8 bars) for an emotion, then exit.",
    )
    parser.add_argument("--emotion", default=None, help="Emotion name or index (0–27).")
    parser.add_argument("--seed", type=int, default=None, help="Optional integer seed (random if omitted).")
    parser.add_argument("--root", type=int, default=60, help="MIDI root note (default 60).")
    parser.add_argument(
        "--bars",
        type=int,
        default=DEFAULT_LOOP_BARS,
        help=f"Chorus loop length in bars (default {DEFAULT_LOOP_BARS}).",
    )
    parser.add_argument("--preset", default="", help="Optional preset name.")
    parser.add_argument("--performance", default="high", help="Performance mode (default high).")
    parser.add_argument("--list-emotions-json", action="store_true", help="Print emotion index list as JSON and exit.")
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Generate (and optionally export events) without opening the audio device.",
    )
    parser.add_argument(
        "--include-events",
        action="store_true",
        help="Include symbolic chorus events in the JSON response.",
    )
    parser.add_argument(
        "--wav-out",
        default="",
        help="Write rendered stereo WAV to this path (works with --no-play for headless export).",
    )
    parser.add_argument(
        "--schema-json",
        action="store_true",
        help="Print integration tool schema as JSON and exit.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if bool(getattr(args, "list_emotions_json", False)):
        from data.music_data import EMOTIONS

        _json_out(
            {
                "type": "emotions",
                "ok": True,
                "emotions": [{"index": i, "name": str(getattr(e, "name", "") or "")} for i, e in enumerate(EMOTIONS)],
            }
        )
        return 0

    if bool(getattr(args, "schema_json", False)):
        _json_out({"type": "tool_schema", "ok": True, "schema": MAIN_LLM_TOOL_SCHEMA})
        return 0

    from main import _setup_logging
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongRender
    from audiogen_core.config import CONFIG
    from data.music_data import EMOTIONS
    from main_llm_chorus_only import (
        _apply_llm_chorus_only_config,
        _emotion_from_cli_string,
        _generate_chorus_phrase_events,
        _install_chorus_only_mixer_guard,
        _serialize_event_for_json,
    )
    from tools.full_song_render import render_song_events_to_audio

    _setup_logging(verbose=bool(args.verbose), quiet=bool(args.quiet))
    _install_chorus_only_mixer_guard(CONFIG)
    CONFIG.set_performance_mode(str(args.performance or "high"))
    if str(args.preset or "").strip():
        from main_llm_chorus_only import _apply_preset_if_requested

        applied = _apply_preset_if_requested(preset_name=str(args.preset).strip(), config=CONFIG)
        if applied:
            try:
                CONFIG.rebuild_samplers()
            except Exception:
                pass
    _apply_llm_chorus_only_config(config=CONFIG, args=args)

    emo, em_err = _emotion_from_cli_string(EMOTIONS, str(args.emotion or ""))
    if emo is None:
        _json_out(
            {
                "type": "chorus_loop_playback",
                "ok": False,
                "error": em_err or "missing_emotion",
                "hint": "Pass --emotion <name|index> or use --list-emotions-json.",
            }
        )
        return 2

    try:
        bars = max(1, min(24, int(args.bars or DEFAULT_LOOP_BARS)))
    except Exception:
        bars = int(DEFAULT_LOOP_BARS)
    root = int(args.root or 60)
    seed = _resolve_seed(getattr(args, "seed", None))
    emotion_name = str(getattr(emo, "name", "") or "")

    gen = CompositionGenerator(enable_perf_monitoring=False)
    events, gen_err = _generate_chorus_phrase_events(
        gen,
        emo,
        root=root,
        bars=bars,
        seed=int(seed),
    )
    if gen_err:
        _json_out(
            {
                "type": "chorus_loop_playback",
                "ok": False,
                "error": gen_err,
                "emotion": emotion_name,
                "seed": int(seed),
                "bars": int(bars),
                "root": int(root),
            }
        )
        return 2

    song_render = SongRender(
        sections=[],
        events=list(events or []),
        tempo_map=[],
        metadata={"section_roles": ["b"], "section_bars": [int(bars)]},
    )
    fallback_bpm = _fallback_bpm_for_emotion(emo)

    play_err: Optional[str] = None
    wav_err: Optional[str] = None
    duration_s = 0.0
    sample_rate = 44100
    wav_path = str(getattr(args, "wav_out", "") or "").strip()
    need_audio = (not bool(args.no_play)) or bool(wav_path)
    if need_audio:
        try:
            audio, sample_rate = render_song_events_to_audio(
                config=CONFIG,
                song_events=list(events or []),
                total_bars=int(bars),
                song_render=song_render,
                fallback_bpm=float(fallback_bpm),
            )
            duration_s = float(len(audio)) / float(max(1, int(sample_rate)))
            if wav_path:
                wav_err = _write_wav_file(wav_path, audio, int(sample_rate))
            if not bool(args.no_play):
                play_err = _play_stereo_blocking(audio, int(sample_rate))
        except Exception as exc:
            err = f"render_failed:{exc.__class__.__name__}:{exc}"
            if not bool(args.no_play):
                play_err = err
            elif wav_path:
                wav_err = err
            else:
                play_err = err

    out_ev = [_serialize_event_for_json(ev) for ev in list(events or [])]
    out_ev = [x for x in out_ev if x is not None]
    ok = True
    if not bool(args.no_play) and play_err is not None:
        ok = False
    if wav_path and wav_err is not None:
        ok = False
    payload: Dict[str, Any] = {
        "type": "chorus_loop_playback",
        "ok": ok,
        "emotion": emotion_name,
        "seed": int(seed),
        "bars": int(bars),
        "root": int(root),
        "beats_per_bar": 4,
        "section_role": "b",
        "section_duration_beats": float(bars) * 4.0,
        "event_count": len(out_ev),
        "played": not bool(args.no_play) and play_err is None,
        "duration_seconds": round(float(duration_s), 4),
        "sample_rate": int(sample_rate),
    }
    if wav_path:
        payload["wav_path"] = wav_path
        payload["wav_written"] = wav_err is None
    if play_err:
        payload["playback_error"] = str(play_err)
    if wav_err:
        payload["wav_error"] = str(wav_err)
    if bool(args.include_events):
        payload["events"] = out_ev

    _json_out(payload)
    return 0 if payload.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
