from __future__ import annotations

import logging
import random
import re
import select
import sys
import threading
import time
from queue import Empty, Queue
from typing import Optional

from audio.audio_container import AudioContainer
from audio.RT_player.player import PolyphonicPlayer
from realtime_cli import RealtimeCliHandler


def run_realtime(*, adapter, config, emotions, args, gen, drums_mix_on: bool, launch_seed: int) -> int:
    """
    Realtime runner loop extracted from `main.py`.

    This keeps the legacy behavior (interactive CLI + arranged-song flow) but
    isolates orchestration code into `runner/` so `main.py` can become a shim.
    """

    # Realtime arranged playback: ensure we stop after exactly one full arrangement cycle.
    #
    # The realtime scheduler only marks `player.song_finished=True` for *finite* arranged timelines
    # (loop disabled). Without this, realtime can continuously pre-generate the next iteration and
    # never return control to the "next song" selection path.
    try:
        comp = getattr(config, "composition", None)
        if comp is not None:
            # Make sure arranged timelines are enabled in realtime.
            setattr(comp, "arranged_songs_default", True)
            # Prefer generating/playing the full form (incl. outro) rather than a short preview.
            setattr(comp, "arranged_realtime_full_timeline", True)
            # Never replace arranged generation with preview chunks under stress.
            setattr(comp, "arranged_realtime_preview_on_stress", False)
            # Critical: do not loop the arranged song; allow the scheduler to signal song_finished.
            setattr(comp, "arranged_song_loop", False)
    except Exception:
        pass

    container = AudioContainer.create_from_config(config)
    player = PolyphonicPlayer(adapter, config, container=container)
    player.start()

    def _emotion_index_by_name(name: str) -> int:
        key = (name or "").strip().lower()
        idx0 = next((i for i, em in enumerate(emotions) if str(em.name).lower() == key), None)
        return int(idx0) if idx0 is not None else 0

    def _timed_input(prompt: str, timeout_s: float) -> Optional[str]:
        """Read a line from stdin with a timeout. Returns None on timeout/EOF."""
        try:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            rlist, _, _ = select.select([sys.stdin], [], [], float(timeout_s))
            if not rlist:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return None
            line = sys.stdin.readline()
        except Exception:
            return None
        if not line:
            return None
        return line.strip()

    def _fade_out_master_bus(player_obj, *, duration_s: float = 1.35) -> float:
        mb = None
        try:
            mb = getattr(getattr(player_obj, "container", None), "master_bus", None)
        except Exception:
            mb = None
        if mb is None:
            return 1.0
        try:
            start_v = float(getattr(mb, "master_volume", 1.0) or 1.0)
        except Exception:
            start_v = 1.0
        try:
            start_v = float(max(0.0, min(2.0, start_v)))
        except Exception:
            start_v = 1.0
        try:
            dur = float(duration_s)
        except Exception:
            dur = 1.35
        if dur <= 0.0:
            try:
                mb.set_master_volume(0.0)
            except Exception:
                pass
            return float(start_v)
        steps = int(max(12, min(90, round(dur / 0.03))))
        try:
            for i in range(steps):
                t = float(i + 1) / float(steps)
                v = float(start_v) * float(max(0.0, 1.0 - t))
                try:
                    mb.set_master_volume(v)
                except Exception:
                    try:
                        setattr(mb, "master_volume", float(v))
                    except Exception:
                        break
                time.sleep(float(dur) / float(steps))
        except Exception:
            pass
        try:
            mb.set_master_volume(0.0)
        except Exception:
            try:
                setattr(mb, "master_volume", 0.0)
            except Exception:
                pass
        return float(start_v)

    def _select_emotion_compact(*, default_name: str = "neutral") -> int:
        neutral_idx = _emotion_index_by_name(str(default_name))
        neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(emotions) else 0
        try:
            if not sys.stdin.isatty():
                return int(neutral_idx)
        except Exception:
            return int(neutral_idx)

        def _print_emotions() -> None:
            try:
                sys.stdout.write("\nEmotions:\n")
                sys.stdout.write(f"  0: {emotions[int(neutral_idx)].name} (neutral)\n")
                max_display_index = min(27, len(emotions) - 1)
                for i in range(1, max_display_index + 1):
                    sys.stdout.write(f"  {i}: {getattr(emotions[int(i)], 'name', f'emo-{i}')}\n")
                sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception:
                pass

        _print_emotions()

        while True:
            try:
                sys.stdout.write("select emotion (name/index, '?' to list, Enter=neutral): ")
                sys.stdout.flush()
                line = sys.stdin.readline()
            except Exception:
                return int(neutral_idx)
            if not line:
                return int(neutral_idx)
            s = (line or "").strip()
            if s == "":
                return int(neutral_idx)
            if s in {"?", "list", "ls"}:
                _print_emotions()
                continue
            if re.fullmatch(r"-?\d+", s):
                try:
                    idx = int(s)
                except Exception:
                    idx = int(neutral_idx)
                if idx == 0:
                    return int(neutral_idx)
                if 0 <= idx < len(emotions) and idx <= 27:
                    return int(idx)
                sys.stdout.write("Out of range. Use 0-27 (or '?' to list).\n")
                sys.stdout.flush()
                continue
            idx_by_name = _emotion_index_by_name(s)
            if 0 <= int(idx_by_name) < len(emotions):
                return int(idx_by_name)
            sys.stdout.write("Unknown emotion. Type '?' to list.\n")
            sys.stdout.flush()

    def _select_emotion_required() -> int:
        neutral_idx = _emotion_index_by_name("neutral")
        neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(emotions) else 0
        try:
            if not sys.stdin.isatty():
                return int(neutral_idx)
        except Exception:
            return int(neutral_idx)

        max_display_index = 27
        logging.info("Available emotions (indices 0-27):")
        neutral_name = emotions[int(neutral_idx)].name if 0 <= int(neutral_idx) < len(emotions) else "neutral"
        logging.info("  0: %s (neutral)", neutral_name)

        index_map = {0: int(neutral_idx)}
        for display_idx in range(1, max_display_index + 1):
            if display_idx >= len(emotions):
                break
            name = str(getattr(emotions[display_idx], "name", f"emo-{display_idx}"))
            logging.info("  %d: %s", int(display_idx), name)
            index_map[display_idx] = int(display_idx)

        while True:
            try:
                sys.stdout.write(f"select emotion (0-{max_display_index}): ")
                sys.stdout.flush()
                s = sys.stdin.readline()
            except Exception:
                s = ""
            if not s:
                logging.info("No input received; defaulting to neutral.")
                return int(neutral_idx)
            s = s.strip()
            try:
                choice = int(s)
            except Exception:
                logging.info("Invalid selection %r. Please enter a number 0-%d.", s, int(max_display_index))
                continue
            if choice not in index_map:
                logging.info("Out of range. Please enter a number 0-%d.", int(max_display_index))
                continue
            return int(index_map[choice])

    rng = random.Random()
    startup_verbose = bool(getattr(args, "verbose", False))
    start_idx = _select_emotion_required() if startup_verbose else _select_emotion_compact(default_name="neutral")
    rt_cli = RealtimeCliHandler(
        player=player,
        config=config,
        emotions=emotions,
        container=container,
        root_default=int(args.root),
        emotion_index_by_name=_emotion_index_by_name,
        rng=rng,
    )

    try:
        tty = bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        tty = False
    if tty:
        try:
            comp0 = getattr(config, "composition", None)
            per_emo_id = bool(getattr(comp0, "per_emotion_song_identity_enabled", True)) if comp0 is not None else True
        except Exception:
            per_emo_id = True
        if per_emo_id:
            try:
                sys.stdout.write("\n")
                sys.stdout.write("Startup: would you like a random new song, or choose a form?\n")
                sys.stdout.write("  [Enter] keep cached song for this emotion\n")
                sys.stdout.write("  r = random new song (fresh seed)\n")
                sys.stdout.write("  f = choose form\n")
                sys.stdout.flush()
                ans = input("Choice [Enter/r/f]: ").strip().lower()
            except Exception:
                ans = ""
            if ans in {"r", "rand", "random", "fresh", "new"}:
                try:
                    if hasattr(rt_cli, "_force_fresh_song_seed"):
                        rt_cli._force_fresh_song_seed()  # type: ignore[attr-defined]
                except Exception:
                    pass
            elif ans in {"f", "form", "forms"}:
                try:
                    forms = []
                    if hasattr(rt_cli, "_available_forms"):
                        forms = list(rt_cli._available_forms() or [])  # type: ignore[attr-defined]
                    if not forms:
                        forms = ["default", "dialogue (call and responce) WIP", "swing"]
                    sys.stdout.write("Available forms: " + ", ".join(forms) + "\n")
                    sys.stdout.flush()
                    raw = input("Form: ").strip().lower()
                except Exception:
                    raw = ""
                if raw:
                    try:
                        if hasattr(rt_cli, "_set_form_mode"):
                            rt_cli._set_form_mode(str(raw))  # type: ignore[attr-defined]
                    except Exception:
                        pass

    try:
        rt_cli._prepare_emotion_switch_timeline(int(start_idx))
    except Exception:
        pass
    player.load_emotion(int(start_idx), int(args.root))

    def _print_realtime_command_cheatsheet(*, full: bool) -> None:
        try:
            sys.stdout.write("\n")
            sys.stdout.write("Realtime commands:\n")
            if full:
                sys.stdout.write(
                    "  <index> | list | e <name|index> | n | root <midi> | fresh (or r) |\n"
                    "  presets | preset <name> | forms | form <name> |\n"
                    "  arpboost [off|on|<db>] |\n"
                    "  pause | resume | p (toggle pause) |\n"
                    "  boundary <bars> | handoff <bars|on|off> |\n"
                    "  dialogue <0..1> | dialogue preset <off|tight|strong|experimental|clear> |\n"
                    "  melody | melody show | melody pos|rpc|vl on|off [strength] |\n"
                    "  stats (buffer/tier) | health [log_path] | help | q\n"
                )
            else:
                sys.stdout.write("  help | list | e <name|index> | fresh (r) | pause | resume | q\n")
            sys.stdout.flush()
        except Exception:
            pass

    _print_realtime_command_cheatsheet(full=True)

    try:
        cmd_q: "Queue[str]" = Queue()
        stop_evt = threading.Event()
        awaiting_end_choice = False
        awaiting_end_emotion = False
        printed_end_prompt = False

        def _stdin_thread() -> None:
            while not stop_evt.is_set():
                try:
                    line = sys.stdin.readline()
                except Exception:
                    break
                if not line:
                    break
                cmd_q.put(line.strip())

        threading.Thread(target=_stdin_thread, name="cli-stdin", daemon=True).start()

        def _enter_end_of_song_prompt() -> None:
            nonlocal awaiting_end_choice, awaiting_end_emotion, printed_end_prompt
            if awaiting_end_choice or awaiting_end_emotion:
                return
            awaiting_end_choice = True
            awaiting_end_emotion = False
            printed_end_prompt = False
            try:
                _fade_out_master_bus(player, duration_s=1.10)
            except Exception:
                pass
            try:
                player.pause()
            except Exception:
                pass

        def _print_end_of_song_prompt_once() -> None:
            nonlocal printed_end_prompt
            if printed_end_prompt:
                return
            printed_end_prompt = True
            try:
                cur_emo = str(getattr(getattr(player, "emotion", None), "name", "") or "").strip() or "unknown"
            except Exception:
                cur_emo = "unknown"
            try:
                cur_seed = int(getattr(getattr(getattr(player, "composer", None), "gen", None), "seed", 0) or 0)
            except Exception:
                cur_seed = 0
            try:
                sys.stdout.write("\n")
                sys.stdout.write(f"Song finished (emotion={cur_emo}, seed={cur_seed}). What next?\n")
                sys.stdout.write("  [E] select new emotion\n")
                sys.stdout.write("  [S] new seed (same emotion)\n")
                sys.stdout.write("  [R] replay (same seed)\n")
                sys.stdout.write("  [Q] quit\n")
                sys.stdout.write("\n")
                sys.stdout.write("Choice [E/S/R/Q]: ")
                sys.stdout.flush()
            except Exception:
                pass

        def _start_new_song_for_emotion_index(idx: int) -> None:
            # Ensure the next timeline starts from bar 0 (cold start) after a finite song ended.
            try:
                player.reset_for_new_song()
            except Exception:
                pass
            try:
                rt_cli._prepare_emotion_switch_timeline(int(idx))
            except Exception:
                pass
            try:
                root_now = int(getattr(player, "root", int(args.root)) or int(args.root))
            except Exception:
                root_now = int(args.root)
            player.load_emotion(int(idx), int(root_now))
            try:
                player.resume()
            except Exception:
                pass

        # Main command loop (mirrors legacy behavior).
        while True:
            try:
                cmd = cmd_q.get(timeout=0.05)
            except Empty:
                cmd = None
            if cmd is None:
                # If a finite arranged song completed, prompt for what to do next.
                try:
                    finished = bool(getattr(player, "song_finished", False))
                except Exception:
                    finished = False
                if finished:
                    _enter_end_of_song_prompt()
                    _print_end_of_song_prompt_once()
                continue
            c = (cmd or "").strip()
            if not c:
                continue
            # End-of-song interactive state machine: read choices from the same stdin thread queue
            # to avoid racing multiple readers on sys.stdin.
            if awaiting_end_choice or awaiting_end_emotion:
                if awaiting_end_choice:
                    choice = str(c).strip().lower()
                    if choice in {"q", "quit", "exit"}:
                        raise KeyboardInterrupt()
                    if choice in {"s", "seed", "fresh", "r"}:
                        # "fresh" command already rolls seed + reset_for_new_song() + resumes.
                        awaiting_end_choice = False
                        awaiting_end_emotion = False
                        printed_end_prompt = False
                        rt_cli.execute_command("fresh")
                        continue
                    if choice in {"replay", "repeat"}:
                        awaiting_end_choice = False
                        awaiting_end_emotion = False
                        printed_end_prompt = False
                        rt_cli.execute_command("replay")
                        continue
                    if choice in {"e", "emo", "emotion"}:
                        awaiting_end_choice = False
                        awaiting_end_emotion = True
                        printed_end_prompt = False
                        try:
                            sys.stdout.write("\nSelect emotion (name/index, '?' to list, Enter=neutral): ")
                            sys.stdout.flush()
                        except Exception:
                            pass
                        continue
                    # Unknown choice -> reprint prompt.
                    printed_end_prompt = False
                    _print_end_of_song_prompt_once()
                    continue

                if awaiting_end_emotion:
                    token = str(c).strip()
                    if token in {"q", "quit", "exit"}:
                        raise KeyboardInterrupt()
                    if token in {"?", "list", "ls"}:
                        try:
                            rt_cli.execute_command("list")
                        except Exception:
                            pass
                        try:
                            sys.stdout.write("Select emotion (name/index, '?' to list, Enter=neutral): ")
                            sys.stdout.flush()
                        except Exception:
                            pass
                        continue
                    if token == "":
                        idx2 = _emotion_index_by_name("neutral")
                    elif re.fullmatch(r"-?\d+", token):
                        try:
                            idx2 = int(token)
                        except Exception:
                            idx2 = _emotion_index_by_name("neutral")
                    else:
                        idx2 = _emotion_index_by_name(token)
                    if not (0 <= int(idx2) < len(emotions)):
                        try:
                            sys.stdout.write("Unknown emotion. Type '?' to list.\n")
                            sys.stdout.write("Select emotion (name/index, '?' to list, Enter=neutral): ")
                            sys.stdout.flush()
                        except Exception:
                            pass
                        continue
                    awaiting_end_choice = False
                    awaiting_end_emotion = False
                    printed_end_prompt = False
                    _start_new_song_for_emotion_index(int(idx2))
                    continue
            if not rt_cli.execute_command(c):
                raise KeyboardInterrupt()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass
        try:
            player.stop()
        except Exception:
            pass
    return 0

