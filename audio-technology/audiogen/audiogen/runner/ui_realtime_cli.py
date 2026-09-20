import logging
import random
import re
import select
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from data.music_data import EMOTIONS
from app_controller import AppController

def prompt_mode_selection() -> str:
    while True:
        try:
            sys.stdout.write("Select mode: [G]enerative or [O]ffline (default=G): ")
            sys.stdout.flush()
            line = sys.stdin.readline()
        except Exception:
            return "generative"
        if not line:
            return "generative"
        choice = (line or "").strip().lower()
        if choice in {"", "g"}:
            return "generative"
        if choice == "o":
            return "offline"
        logging.info("Unrecognized choice %r. Please enter G or O.", choice)


def prompt_preset_selection(*, current: Optional[str]) -> Optional[str]:
    try:
        if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
            return None
    except Exception:
        return None
    try:
        from presets import list_presets
        presets_list = sorted(str(x) for x in (list_presets() or []) if str(x).strip())
    except Exception:
        presets_list = []
    if not presets_list:
        return None

    cur = str(current).strip() if current else ""
    cur_l = cur.lower()
    try:
        cur_idx = next((i for i, p in enumerate(presets_list) if str(p).lower() == cur_l), None)
    except Exception:
        cur_idx = None

    sys.stdout.write("\n")
    sys.stdout.write("Select preset (meta preset in .audiogen/presets)\n")
    if cur:
        sys.stdout.write(f"Current: {cur}\n")
    sys.stdout.write("Enter a number, or press Enter to keep current.\n")
    for i, p in enumerate(presets_list):
        mark = " *" if (cur_idx is not None and int(i) == int(cur_idx)) else ""
        sys.stdout.write(f"{i:2d}) {p}{mark}\n")
    sys.stdout.flush()
    while True:
        try:
            sys.stdout.write("preset #: ")
            sys.stdout.flush()
            line = sys.stdin.readline()
        except Exception:
            return None
        if not line:
            return None
        s = (line or "").strip()
        if s == "":
            return None
        try:
            idx = int(s)
        except Exception:
            logging.info("Invalid preset selection %r. Enter a number 0-%d.", s, len(presets_list) - 1)
            continue
        if 0 <= idx < len(presets_list):
            return str(presets_list[idx])
        logging.info("Preset selection out of range: %r. Enter 0-%d.", s, len(presets_list) - 1)


def prompt_style_selection(config, *, current: Optional[str]) -> Optional[str]:
    try:
        if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
            return None
    except Exception:
        return None
    try:
        styles = sorted(str(k) for k in (getattr(config, "style_profiles", {}) or {}).keys())
    except Exception:
        styles = []
    styles = [s for s in styles if str(s).strip()]
    if not styles:
        return None

    cur = str(current).strip() if current else ""
    cur_l = cur.lower()
    try:
        cur_idx = next((i for i, p in enumerate(styles) if str(p).lower() == cur_l), None)
    except Exception:
        cur_idx = None

    sys.stdout.write("\n")
    sys.stdout.write("Select style profile\n")
    if cur:
        sys.stdout.write(f"Current: {cur}\n")
    sys.stdout.write("Enter a number, or press Enter to keep current.\n")
    for i, p in enumerate(styles):
        mark = " *" if (cur_idx is not None and int(i) == int(cur_idx)) else ""
        sys.stdout.write(f"{i:2d}) {p}{mark}\n")
    sys.stdout.flush()
    while True:
        try:
            sys.stdout.write("style #: ")
            sys.stdout.flush()
            line = sys.stdin.readline()
        except Exception:
            return None
        if not line:
            return None
        s = (line or "").strip()
        if s == "":
            return None
        try:
            idx = int(s)
        except Exception:
            logging.info("Invalid style selection %r. Enter a number 0-%d.", s, len(styles) - 1)
            continue
        if 0 <= idx < len(styles):
            return str(styles[idx])
        logging.info("Style selection out of range: %r. Enter 0-%d.", s, len(styles) - 1)


def interactive_choose_conversation_style(config, args) -> None:
    if getattr(args, "conversation", None):
        return
    if bool(getattr(args, "ambient01", False)):
        return
    if bool(getattr(args, "quiet", False)):
        return
    if bool(getattr(args, "no_choose_style", False)):
        return
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return
    except Exception:
        return

    from runner.session import safe_sorted_str_keys
    names = safe_sorted_str_keys(getattr(config, "conversation_presets", {}))
    if not names:
        return

    current = str(getattr(config, "active_conversation_preset", "") or "").strip()
    print()
    print("Choose style")
    print("(conversation presets — Enter keeps current)")
    print()
    for i, name in enumerate(names, start=1):
        mark = "  ← current" if name == current else ""
        print(f"  {i:>3}  {name}{mark}")
    print()
    try:
        raw = input("Number or preset name: ").strip()
    except EOFError:
        return
    if not raw:
        return

    chosen = None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(names):
            chosen = names[idx - 1]
    if chosen is None:
        low = raw.lower()
        for n in names:
            if str(n).lower() == low:
                chosen = n
                break
    if chosen is None:
        print(f"Unknown '{raw}', keeping '{current}'.")
        return
    try:
        config.set_conversation_preset(chosen)
        print(f"Style set to: {chosen}")
    except Exception as exc:
        logging.warning("Could not apply conversation preset %s: %s", chosen, exc)


def interactive_choose_drums(config, args, *, mode: str) -> None:
    if str(mode or "").strip().lower() != "generative":
        return
    if bool(getattr(args, "quiet", False)):
        return
    if bool(getattr(args, "no_choose_drums", False)):
        return
    drums_arg = getattr(args, "drums", None)
    if drums_arg is not None:
        return
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return
    except Exception:
        return

    from runner.session import apply_drums_enabled
    sc = getattr(getattr(config, "audio", None), "chorus_kick_sidechain", None)
    current_on = bool(getattr(sc, "enabled", True)) if sc is not None else True
    print()
    print("Drums (chorus 4/4 kick + pump on other layers)")
    print("  1  yes — kick and sidechain on chorus sections")
    print("  2  no  — no kick, no pumping")
    print(f"  Enter keeps {'yes' if current_on else 'no'}")
    print()
    try:
        raw = input("Drums [1/2]: ").strip().lower()
    except EOFError:
        return
    if not raw:
        apply_drums_enabled(config, current_on)
        return
    if raw in {"1", "y", "yes", "on", "true"}:
        apply_drums_enabled(config, True)
        return
    if raw in {"2", "n", "no", "off", "false"}:
        apply_drums_enabled(config, False)
        return
    print(f"Unknown '{raw}', keeping {'yes' if current_on else 'no'}.")
    apply_drums_enabled(config, current_on)


def emotion_index_by_name(name: str) -> int:
    key = (name or "").strip().lower()
    idx0 = next((i for i, em in enumerate(EMOTIONS) if str(em.name).lower() == key), None)
    return int(idx0) if idx0 is not None else 0


def timed_input(prompt: str, timeout_s: float) -> Optional[str]:
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


def select_emotion_compact(*, default_name: str = "neutral") -> int:
    neutral_idx = emotion_index_by_name(str(default_name))
    neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(EMOTIONS) else 0
    try:
        if not sys.stdin.isatty():
            return int(neutral_idx)
    except Exception:
        return int(neutral_idx)

    def _print_emotions() -> None:
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
            if 0 <= idx < len(EMOTIONS) and idx <= 27:
                return int(idx)
            sys.stdout.write("Out of range. Use 0-27 (or '?' to list).\n")
            sys.stdout.flush()
            continue
        idx_by_name = emotion_index_by_name(s)
        if 0 <= int(idx_by_name) < len(EMOTIONS):
            return int(idx_by_name)
        sys.stdout.write("Unknown emotion. Type '?' to list.\n")
        sys.stdout.flush()


def select_emotion_required() -> int:
    neutral_idx = emotion_index_by_name("neutral")
    neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(EMOTIONS) else 0
    try:
        if not sys.stdin.isatty():
            return int(neutral_idx)
    except Exception:
        return int(neutral_idx)

    max_display_index = 27
    logging.info("Available emotions (indices 0-27):")
    neutral_name = EMOTIONS[int(neutral_idx)].name if 0 <= int(neutral_idx) < len(EMOTIONS) else "neutral"
    logging.info("  0: %s (neutral)", neutral_name)

    index_map = {0: int(neutral_idx)}
    for display_idx in range(1, max_display_index + 1):
        if display_idx >= len(EMOTIONS):
            break
        name = str(getattr(EMOTIONS[display_idx], "name", f"emo-{display_idx}"))
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


def run_generative_mode(args, config, gen, adapter, launch_seed: int, preset_name: Optional[str]) -> int:
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer


    container = AudioContainer.create_from_config(config)
    player = PolyphonicPlayer(adapter, config, container=container)
    player.start()

    rng = random.Random()
    startup_verbose = bool(getattr(args, "verbose", False))
    start_idx = select_emotion_required() if startup_verbose else select_emotion_compact(default_name="neutral")
    player.load_emotion(int(start_idx), int(args.root))

    if startup_verbose:
        logging.info(
            "Running (preset=%s pack=%s style=%s convo=%s fx=%s emotion=%s root=%s). Ctrl-C to stop.",
            args.preset,
            getattr(config, "active_sample_pack", None),
            getattr(config, "active_style_profile", None),
            getattr(config, "active_conversation_preset", None),
            getattr(config, "active_post_process_preset", None),
            EMOTIONS[int(start_idx)].name if 0 <= int(start_idx) < len(EMOTIONS) else "neutral",
            int(getattr(player, "root", args.root) or args.root),
        )
        try:
            logging.info("Generation seed: %s", int(getattr(gen, "seed", launch_seed)))
        except Exception:
            pass
        try:
            b = int(getattr(getattr(config, "audio", None), "emotion_transition_boundary_bars", 1) or 1)
        except Exception:
            b = 1
        try:
            bb = int(getattr(getattr(config, "composition", None), "transition_blend_bars", 0) or 0)
        except Exception:
            bb = 0
        logging.info(
            "Tip: for smoother manual emotion switches, set CONFIG.audio.emotion_transition_boundary_bars=4 (current=%d).",
            int(max(1, b)),
        )
        logging.info(
            "Tip: for smoother musical morph, set CONFIG.composition.transition_blend_bars=8 (current=%d).",
            int(max(0, bb)),
        )
        logging.info(
            "Type commands anytime: <index> | list | e <name|index> | n | root <midi> | "
            "presets | preset <name> | "
            "forms | form <name> | "
            "arpboost [off|on|<db>] | "
            "menu | replay | save wav|midi | "
            "drums [show|on|off] | "
            "pause | resume | p (toggle pause) | "
            "boundary <bars> | handoff <bars|on|off> | "
            "dialogue <0..1> | dialogue preset <off|tight|strong|experimental|clear> | "
            "melody | melody show | melody pos|rpc|vl on|off [strength] | "
            "stats (buffer/tier) | health [log_path] | help | q"
        )
    else:
        try:
            preset_s = str(args.preset or "") if getattr(args, "preset", None) is not None else ""
        except Exception:
            preset_s = ""
        try:
            style_s = str(getattr(config, "active_style_profile", None) or "").strip()
        except Exception:
            style_s = ""
        emo_s = EMOTIONS[int(start_idx)].name if 0 <= int(start_idx) < len(EMOTIONS) else "neutral"
        root_s = int(getattr(player, "root", args.root) or args.root)
        sys.stdout.write("\n")
        sys.stdout.write("Ready.\n")
        sys.stdout.write(f"  preset={preset_s or '-'}  style={style_s or '-'}  emotion={emo_s}  root={root_s}\n")
        sys.stdout.write("  commands: help | list | e <name|index> | replay | save wav | save midi | pause | resume | q\n")
        sys.stdout.flush()

    controller = AppController(
        player=player,
        config=config,
        emotions=EMOTIONS,
        container=container,
        root_default=int(args.root),
        emotion_index_by_name=emotion_index_by_name,
        rng=rng,
    )

    def _song_export_dir() -> Path:
        out_dir = Path(str(getattr(args, "offline_export_dir", "songs") or "songs")).expanduser()
        if not out_dir.is_absolute():
            out_dir = Path(__file__).resolve().parent.parent / out_dir
        return out_dir

    def _completed_song_payload():
        sch = getattr(player, "section_scheduler", None)
        if sch is None:
            return [], 0, None, None, None, None
        events = list(getattr(sch, "last_completed_arranged_song_events", []) or [])
        bars = int(getattr(sch, "last_completed_arranged_song_bars", 0) or 0)
        segs = getattr(sch, "last_completed_arranged_song_segments", None)
        render = getattr(sch, "last_completed_arranged_song_render", None)
        emotion = getattr(sch, "last_completed_arranged_song_emotion", None)
        root = getattr(sch, "last_completed_arranged_song_root", None)
        if not events:
            try:
                events = list(getattr(sch, "current_section_events", []) or [])
                bars = int(getattr(sch, "current_section_bars", 0) or 0)
                segs = getattr(sch, "current_arrangement_segments", None)
                render = getattr(sch, "current_arranged_song_render", None)
                emotion = getattr(player, "emotion", None)
                root = getattr(player, "root", None)
            except Exception:
                events, bars, segs, render, emotion, root = [], 0, None, None, None, None
        return events, int(bars), segs, render, emotion, root

    def _song_prefix(emotion=None) -> str:
        try:
            emo = str(getattr(emotion, "name", "") or getattr(getattr(player, "emotion", None), "name", "") or "song")
        except Exception:
            emo = "song"
        try:
            mode_s = str(getattr(config.composition, "arranged_song_mode", "") or "").strip()
        except Exception:
            mode_s = ""
        raw = f"{emo}_{mode_s}" if mode_s else str(emo)
        return raw.strip("_") or "song"

    def _export_song_outputs(kind: str = "both") -> bool:
        from runner.offline import write_offline_song_outputs
        events, bars, _segs, render, emotion, _root = _completed_song_payload()
        if not events or int(bars) <= 0:
            logging.warning("No completed/current song is available to export yet.")
            return True
        out_dir = _song_export_dir()
        kind_l = str(kind or "both").strip().lower()
        if kind_l in {"midi", "mid"}:
            try:
                from composition.song_generator import SongGenerator, SongRender
                out_dir.mkdir(parents=True, exist_ok=True)
                safe_prefix = "".join(c if (str(c).isalnum() or c in {"-", "_"}) else "_" for c in _song_prefix(emotion))
                stem = f"{safe_prefix}_{time.strftime('%Y%m%d_%H%M%S')}"
                song_render = render if render is not None else SongRender(sections=[], events=list(events), tempo_map=[], metadata={})
                midi_path = out_dir / f"{stem}.mid"
                SongGenerator.export_to_midi(song_render, out_path=str(midi_path))
                logging.info("Saved MIDI: %s", str(midi_path))
            except Exception:
                logging.exception("MIDI export failed")
            return True
        try:
            out = write_offline_song_outputs(
                config=config,
                song_events=list(events),
                total_bars=int(bars),
                song_render=render,
                export_dir=out_dir,
                name_prefix=_song_prefix(emotion),
            )
            if kind_l in {"wav", "wave"}:
                logging.info("Saved WAV: %s", out.get("wav", ""))
            else:
                logging.info("Saved song: wav=%s midi=%s report=%s", out.get("wav", ""), out.get("midi", ""), out.get("json", ""))
        except Exception:
            logging.exception("Song export failed")
        return True

    def _replay_completed_song() -> bool:
        events, bars, segs, render, emotion, root = _completed_song_payload()
        if not events or int(bars) <= 0:
            logging.warning("No completed/current song is available to replay yet.")
            return True
        sch = getattr(player, "section_scheduler", None)
        if sch is None:
            logging.warning("No section scheduler available for replay.")
            return True
        try:
            with player.section_lock:
                sch.current_section_events = list(events)
                sch.current_section_bars = int(bars)
                sch.current_arrangement_segments = [dict(s) for s in list(segs or []) if isinstance(s, dict)] if isinstance(segs, list) else None
                sch.current_arranged_song_render = render
                sch.next_bar_index = 0
                sch.bars_played_this_section = 0
                sch.next_section_ready = False
                sch.next_section_events = None
                sch.next_section_bars = 0
                sch.next_arrangement_segments = None
                sch.next_arranged_song_render = None
                sch._arranged_completion_armed = bool(isinstance(sch.current_arrangement_segments, list) and len(sch.current_arrangement_segments) > 0)
                try:
                    sch._invalidate_bar_event_index()
                except Exception:
                    pass
            try:
                if emotion is not None:
                    with player.state_lock:
                        player._emotion = emotion
                        if root is not None:
                            player._root = int(root)
            except Exception:
                pass
            try:
                player.buffer.clear()
            except Exception:
                pass
            player.resume()
            logging.info("Replaying last completed song.")
        except Exception:
            logging.exception("Replay failed")
        return True

    def _print_song_end_menu() -> None:
        try:
            sys.stdout.write("\n\nSong finished. Choose an action:\n")
            sys.stdout.write("  1 / replay          replay this song\n")
            sys.stdout.write("  2 / save wav        save this song to WAV\n")
            sys.stdout.write("  3 / save midi       save this song to MIDI\n")
            sys.stdout.write("  save                save WAV + MIDI + report\n")
            sys.stdout.write("  4 / new <name|idx>  choose a new emotion\n")
            sys.stdout.write("  e <name|index>      choose a new emotion\n")
            sys.stdout.write("  list                show emotions\n")
            sys.stdout.write("  q                   quit\n\n")
            sys.stdout.flush()
        except Exception:
            pass

    end_menu_active = False

    def _handle_song_menu_command(cmd: str):
        nonlocal end_menu_active
        c = str(cmd or "").strip()
        if not c:
            return False, True
        parts = c.split()
        op = parts[0].strip().lower()
        if op in {"menu", "song", "actions"}:
            _print_song_end_menu()
            end_menu_active = True
            return True, True
        if op in {"1", "2", "3", "4"} and not bool(end_menu_active):
            return False, True
        if op in {"1", "replay", "again"}:
            end_menu_active = False
            return True, _replay_completed_song()
        if op in {"2", "wav", "wave"} or (op == "save" and len(parts) >= 2 and parts[1].strip().lower() in {"wav", "wave"}):
            return True, _export_song_outputs("wav")
        if op in {"3", "midi", "mid"} or (op == "save" and len(parts) >= 2 and parts[1].strip().lower() in {"midi", "mid"}):
            return True, _export_song_outputs("midi")
        if op in {"save", "export"}:
            return True, _export_song_outputs("both")
        if op in {"4", "new"}:
            if len(parts) >= 2:
                end_menu_active = False
                return True, controller.execute_command("e " + " ".join(parts[1:]))
            logging.info("Use: e <emotion name|index>  (or type list)")
            return True, True
        return False, True

    try:
        cmd_q: "Queue[str]" = Queue()
        stop_evt = threading.Event()

        def _arrangement_state_line(total_bars_played: int) -> str:
            try:
                segs = getattr(adapter, "_last_arranged_song_segments", None)
                if not isinstance(segs, list) or not segs:
                    return ""
                bar = max(0, int(total_bars_played))
                seg = next((s for s in segs if int(s.get("start_bar", 0)) <= bar < int(s.get("end_bar", 0))), None)
                if not isinstance(seg, dict):
                    return ""
                role = str(seg.get("role_label", "") or "").strip()
                idx = int(seg.get("index", 0))
                start = int(seg.get("start_bar", 0))
                bars = int(seg.get("bars", 0))
                pos = (bar - start) + 1
                emo = str(seg.get("emotion_name", "") or "").strip()
                mode = ""
                try:
                    mode = str(getattr(config.composition, "arranged_song_mode", "") or "").strip()
                except Exception:
                    mode = ""
                mode_s = f"{mode} " if mode else ""
                role_s = f"{role} " if role else ""
                emo_s = f" emo={emo}" if emo else ""
                return f"ARR[{mode_s}sec={idx} {role_s}{pos}/{max(1, bars)}{emo_s}]"
            except Exception:
                return ""

        def _status_thread() -> None:
            nonlocal end_menu_active
            last = ""
            last_bar_dbg = -1
            last_completed_song_count = 0
            while not stop_evt.is_set():
                try:
                    st = player.get_stats()
                    emo = str(getattr(player.emotion, "name", "") or "neutral")
                    root = int(getattr(player, "root", args.root) or args.root)
                    bars = int(st.get("total_bars", 0) or 0)
                    arr = _arrangement_state_line(bars)
                    line = f"emo={emo} root={root} bar={bars}"
                    if arr:
                        line = f"{line} {arr}"
                    if line != last:
                        pad = " " * max(0, 10)
                        sys.stdout.write("\r" + line + pad)
                        sys.stdout.flush()
                        last = line

                    try:
                        sch = getattr(player, "section_scheduler", None)
                        completed = int(getattr(sch, "completed_arranged_song_count", 0) or 0) if sch is not None else 0
                    except Exception:
                        completed = 0
                    if completed > int(last_completed_song_count):
                        last_completed_song_count = int(completed)
                        try:
                            if sys.stdin.isatty():
                                player.pause()
                                end_menu_active = True
                        except Exception:
                            pass
                        try:
                            if sys.stdin.isatty():
                                _print_song_end_menu()
                        except Exception:
                            pass

                    try:
                        comp = getattr(config, "composition", None)
                        dbg_print = bool(getattr(comp, "realtime_debug_trace_print_enabled", False)) if comp is not None else False
                    except Exception:
                        dbg_print = False
                    if dbg_print and int(bars) != int(last_bar_dbg):
                        last_bar_dbg = int(bars)
                        try:
                            trace = getattr(gen, "_last_section_debug_trace_by_bar", None)
                        except Exception:
                            trace = None
                        if isinstance(trace, list) and 0 <= int(bars) < len(trace):
                            try:
                                row = dict(trace[int(bars)] or {})
                            except Exception:
                                row = {}
                            hm = row.get("harmony_markov") if isinstance(row, dict) else None
                            fixes = row.get("stability_fixes") if isinstance(row, dict) else None
                            if isinstance(hm, dict):
                                try:
                                    ent = float(hm.get("entropy_bits", 0.0) or 0.0)
                                except Exception:
                                    ent = 0.0
                                try:
                                    top5 = list(hm.get("top5", []) or [])
                                except Exception:
                                    top5 = []
                                top2 = ", ".join(
                                    f"{str(k)}={float(v):.2f}"
                                    for (k, v) in (top5[:2] if isinstance(top5, list) else [])
                                )
                                cf = ""
                                if isinstance(fixes, dict):
                                    try:
                                        cf = f" fixes(chord1note={int(fixes.get('chord_one_note_fixes', 0) or 0)}, arpRuns={int(fixes.get('arp_repeat_runs', 0) or 0)})"
                                    except Exception:
                                        cf = ""
                                logging.info("dbg[bar=%d] harmony_entropy=%.2f top=%s%s", int(bars), float(ent), str(top2), str(cf))
                except Exception:
                    pass
                time.sleep(0.10)

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
        threading.Thread(target=_status_thread, name="rt-status", daemon=True).start()

        while True:
            time.sleep(0.25)
            try:
                cmd = cmd_q.get_nowait()
            except Empty:
                continue

            c = (cmd or "").strip()
            if not c:
                continue
            handled, keep_running = _handle_song_menu_command(c)
            if handled:
                if not keep_running:
                    raise KeyboardInterrupt()
                continue
            if not controller.execute_command(c):
                raise KeyboardInterrupt()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop_evt.set()
        except Exception:
            pass
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
