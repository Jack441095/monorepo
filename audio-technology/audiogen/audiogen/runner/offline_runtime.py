from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


def export_song_outputs(
    *,
    config,
    song_events: List[tuple],
    total_bars: int,
    song_render,
    export_dir: Path,
    name_prefix: str,
    wav: bool = True,
    midi: bool = False,
    report: bool = False,
    meta: bool = True,
) -> Dict[str, str]:
    """
    Public wrapper around the offline renderer used by realtime/offline flows.

    Returns a dict with keys: wav/json/midi/meta (empty strings when disabled).
    """
    return _write_offline_song_outputs(
        config=config,
        song_events=list(song_events or []),
        total_bars=int(total_bars),
        song_render=song_render,
        export_dir=Path(export_dir),
        name_prefix=str(name_prefix),
        write_wav=bool(wav),
        write_midi=bool(midi),
        write_report=bool(report),
        write_meta=bool(meta),
    )


def _write_offline_song_outputs(
    *,
    config,
    song_events: List[tuple],
    total_bars: int,
    song_render,
    export_dir: Path,
    name_prefix: str,
    write_wav: bool = True,
    write_midi: bool = True,
    write_report: bool = True,
    write_meta: bool = True,
) -> Dict[str, str]:
    """
    Render arranged-song events to stereo WAV (+ MIDI/report sidecars) in export_dir.
    """
    from composition.song_generator import SongRender
    from tools.full_song_render import write_full_song_outputs

    export_dir.mkdir(parents=True, exist_ok=True)

    safe_prefix = "".join(c if (str(c).isalnum() or c in {"-", "_"}) else "_" for c in str(name_prefix))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_prefix}_{stamp}" if safe_prefix else f"song_{stamp}"

    if song_render is None:
        song_render = SongRender(sections=[], events=list(song_events or []), tempo_map=[], metadata={})

    out_core = write_full_song_outputs(
        config=config,
        song_events=list(song_events or []),
        total_bars=int(total_bars),
        song_render=song_render,
        export_dir=export_dir,
        name_prefix=str(name_prefix),
        stem=str(stem),
        write_wav=bool(write_wav),
        write_midi=bool(write_midi),
        write_report=bool(write_report),
    )

    wav_path = Path(str(out_core.get("wav", "") or ""))
    json_path = Path(str(out_core.get("report_json", "") or ""))
    midi_path = Path(str(out_core.get("midi", "") or ""))
    bars_i = max(0, int(total_bars))

    # Per-channel stats help debug "missing" parts like arps.
    channel_names = {}
    try:
        from audiogen_core.mixer_config import CHANNEL_NAMES as _CH_NAMES

        channel_names = {int(k): str(v) for k, v in dict(_CH_NAMES or {}).items()}
    except Exception:
        channel_names = {}
    ch_stats = {}
    for ev in list(song_events or []):
        if not ev or len(ev) != 6:
            continue
        try:
            ch, _midi, vel, _st, dur, notes = ev
            chi = int(ch)
        except Exception:
            continue
        row = ch_stats.get(chi) or {
            "channel": int(chi),
            "name": channel_names.get(int(chi), ""),
            "events": 0,
            "notes": 0,
            "velocity_sum": 0,
            "velocity_min": None,
            "velocity_max": None,
            "total_duration_beats": 0.0,
        }
        row["events"] = int(row["events"]) + 1
        try:
            vv = int(vel)
            row["velocity_sum"] = int(row["velocity_sum"]) + vv
            row["velocity_min"] = vv if row["velocity_min"] is None else int(min(int(row["velocity_min"]), vv))
            row["velocity_max"] = vv if row["velocity_max"] is None else int(max(int(row["velocity_max"]), vv))
        except Exception:
            pass
        try:
            row["total_duration_beats"] = float(row["total_duration_beats"]) + abs(float(dur))
        except Exception:
            pass
        try:
            if isinstance(notes, list):
                row["notes"] = int(row["notes"]) + int(len(notes))
            else:
                row["notes"] = int(row["notes"]) + 1
        except Exception:
            row["notes"] = int(row["notes"]) + 1
        ch_stats[int(chi)] = row
    # Compute velocity_mean post-hoc.
    for _chi, row in list(ch_stats.items()):
        try:
            row["velocity_mean"] = float(row["velocity_sum"]) / float(max(1, int(row["events"])))
        except Exception:
            row["velocity_mean"] = None
        try:
            del row["velocity_sum"]
        except Exception:
            pass

    sidecar_path = export_dir / f"{stem}.meta.json"
    if bool(write_meta):
        sidecar = {
            "wav_path": str(wav_path) if bool(write_wav) else "",
            "json_path": str(json_path) if bool(write_report) else "",
            "midi_path": str(midi_path) if (bool(write_midi) and str(midi_path)) else "",
            "bars": int(bars_i),
            "events": int(len(list(song_events or []))),
            "channels": [ch_stats[k] for k in sorted(ch_stats.keys())],
        }
        try:
            sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass
    return {
        "wav": str(wav_path) if bool(write_wav) else "",
        "json": str(json_path) if bool(write_report) else "",
        "midi": str(midi_path) if (bool(write_midi) and str(midi_path)) else "",
        "meta": str(sidecar_path) if bool(write_meta) else "",
    }


def _safe_training_tag(tag: str) -> str:
    raw = str(tag or "").strip().lower()
    if not raw:
        raw = time.strftime("train_%Y%m%d_%H%M%S")
    raw = re.sub(r"[^a-z0-9_.-]+", "_", raw)
    raw = raw.strip("._-")
    return raw or time.strftime("train_%Y%m%d_%H%M%S")


def _run_command_for_offline_training(cmd: List[str], *, cwd: Path) -> Dict[str, object]:
    logging.info("Offline training command: %s", " ".join(str(x) for x in cmd))
    started = time.time()
    proc = subprocess.run(cmd, cwd=str(cwd), text=True)
    elapsed = time.time() - started
    return {
        "cmd": [str(x) for x in cmd],
        "returncode": int(proc.returncode),
        "elapsed_seconds": float(elapsed),
    }


def run_offline_training(args) -> int:
    job = str(getattr(args, "offline_train", "none") or "none").strip().lower()
    if job in {"", "none"}:
        return 0

    root = Path(__file__).resolve().parent.parent
    tag = _safe_training_tag(str(getattr(args, "offline_train_tag", "") or ""))
    base_dir = Path(str(getattr(args, "offline_train_dir", ".cache/offline_training") or ".cache/offline_training")).expanduser()
    if not base_dir.is_absolute():
        base_dir = root / base_dir
    run_dir = base_dir / tag
    run_dir.mkdir(parents=True, exist_ok=True)

    jsonl = Path(str(getattr(args, "offline_train_jsonl", ".cache/live_melody_training.jsonl") or ".cache/live_melody_training.jsonl")).expanduser()
    if not jsonl.is_absolute():
        jsonl = root / jsonl

    min_notes = int(getattr(args, "offline_train_min_notes", 4) or 4)
    min_accept = float(getattr(args, "offline_train_min_accept", 0.0) or 0.0)
    outputs: Dict[str, str] = {}
    commands: List[Dict[str, object]] = []

    needs_jsonl = job in {"markov", "logit", "all"}
    if needs_jsonl and not jsonl.is_file():
        logging.error("Offline training JSONL not found: %s", str(jsonl))
        return 2

    def _run(cmd: List[str]) -> int:
        result = _run_command_for_offline_training(cmd, cwd=root)
        commands.append(result)
        rc_obj = result.get("returncode", 0)
        try:
            return int(rc_obj)  # type: ignore[arg-type]
        except Exception:
            return int(0)

    if needs_jsonl and not bool(getattr(args, "offline_train_skip_eval", False)):
        eval_cmd = [
            sys.executable,
            str(root / "scripts" / "melody_eval_gate.py"),
            str(jsonl),
            "--min-lines",
            str(int(getattr(args, "offline_train_min_lines", 1) or 1)),
            "--max-rest-rate",
            str(float(getattr(args, "offline_train_max_rest_rate", 0.55) or 0.55)),
            "--min-mean-accept",
            str(float(min_accept)),
        ]
        if bool(getattr(args, "offline_train_require_metadata", False)):
            eval_cmd.append("--require-metadata")
        min_emotions = int(getattr(args, "offline_train_min_emotions", 0) or 0)
        if min_emotions > 0:
            eval_cmd.extend(["--min-emotions", str(min_emotions)])
        min_roles = int(getattr(args, "offline_train_min_section_roles", 0) or 0)
        if min_roles > 0:
            eval_cmd.extend(["--min-section-roles", str(min_roles)])
        max_share = float(getattr(args, "offline_train_max_emotion_share", 1.0) or 1.0)
        if max_share < 1.0:
            eval_cmd.extend(["--max-emotion-share", str(max_share)])
        rc = _run(eval_cmd)
        if rc != 0:
            logging.error("Offline training eval gate failed with code %s", rc)
            return rc

    if job in {"markov", "all"}:
        markov_out = run_dir / f"{tag}_melody_markov.pkl"
        outputs["markov_pickle"] = str(markov_out)
        cmd = [
            sys.executable,
            str(root / "scripts" / "melody_jsonl_retrain.py"),
            str(jsonl),
            "-o",
            str(markov_out),
            "--manifest-output",
            str(run_dir / f"{tag}_melody_markov.manifest.json"),
            "--min-notes",
            str(min_notes),
            "--min-accept",
            str(min_accept),
            "--grouped",
            str(getattr(args, "offline_train_grouped", "both") or "both"),
            "--min-group-melodies",
            str(int(getattr(args, "offline_train_min_group_melodies", 8) or 8)),
            "--seed",
            str(int(getattr(args, "offline_train_seed", 0) or 0)),
        ]
        if bool(getattr(args, "offline_train_dedup", False)):
            cmd.append("--dedup")
        rc = _run(cmd)
        if rc != 0:
            return rc

        chord_out = run_dir / f"{tag}_chord_markov.pkl"
        outputs["chord_markov_pickle"] = str(chord_out)
        cmd = [
            sys.executable,
            str(root / "scripts" / "chord_jsonl_retrain.py"),
            str(jsonl),
            "-o",
            str(chord_out),
            "--manifest-output",
            str(run_dir / f"{tag}_chord_markov.manifest.json"),
            "--order",
            str(int(getattr(args, "offline_train_chord_order", 3) or 3)),
            "--smoothing",
            str(float(getattr(args, "offline_train_chord_smoothing", 0.01) or 0.01)),
            "--backoff-decay",
            str(float(getattr(args, "offline_train_chord_backoff_decay", 0.84) or 0.84)),
            "--seed",
            str(int(getattr(args, "offline_train_seed", 0) or 0)),
        ]
        rc = _run(cmd)
        if rc != 0:
            return rc

    if job in {"logit", "all"}:
        logit_out = run_dir / f"{tag}_melody_logit_residual.npz"
        outputs["logit_residual"] = str(logit_out)
        cmd = [
            sys.executable,
            str(root / "scripts" / "train_melody_logit_residual.py"),
            str(jsonl),
            "-o",
            str(logit_out),
            "--min-notes",
            str(min_notes),
            "--min-accept",
            str(min_accept),
            "--order",
            str(int(getattr(args, "offline_train_logit_order", 6) or 6)),
            "--ridge",
            str(float(getattr(args, "offline_train_logit_ridge", 1e-2) or 1e-2)),
        ]
        rc = _run(cmd)
        if rc != 0:
            return rc

    if job in {"dataset", "all"}:
        dataset_dir = run_dir / "emotion_dataset"
        validation_report = dataset_dir / "validation_report.json"
        outputs["emotion_dataset"] = str(dataset_dir)
        outputs["emotion_dataset_validation_report"] = str(validation_report)
        rc = _run([sys.executable, str(root / "scripts" / "export_emotion_dataset.py"), "--out-dir", str(dataset_dir)])
        if rc != 0:
            return rc
        rc = _run([
            sys.executable,
            str(root / "scripts" / "validate_emotion_dataset.py"),
            str(dataset_dir),
            "--report",
            str(validation_report),
        ])
        if rc != 0:
            return rc

    manifest = {
        "schema_version": 1,
        "tag": tag,
        "job": job,
        "jsonl": str(jsonl) if needs_jsonl else "",
        "run_dir": str(run_dir),
        "outputs": outputs,
        "commands": commands,
    }
    manifest_path = run_dir / f"{tag}_offline_training_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logging.info("Offline training complete: %s", str(manifest_path))
    for key, value in outputs.items():
        logging.info("Offline training output %s: %s", str(key), str(value))
    return 0


def run_offline_promotion(args) -> int:
    run_dir = str(getattr(args, "offline_promote_run", "") or "").strip()
    if not run_dir:
        return 0
    root = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable,
        str(root / "scripts" / "promote_training_artifact.py"),
        run_dir,
        "--kind",
        str(getattr(args, "offline_promote_kind", "all") or "all"),
        "--active-dir",
        str(getattr(args, "offline_promote_dir", "training_data/active_models") or "training_data/active_models"),
    ]
    manifest = str(getattr(args, "offline_promote_manifest", "") or "").strip()
    if manifest:
        cmd.extend(["--manifest", manifest])
    if bool(getattr(args, "offline_promote_dry_run", False)):
        cmd.append("--dry-run")
    result = _run_command_for_offline_training(cmd, cwd=root)
    rc_obj = result.get("returncode", 0)
    try:
        return int(rc_obj)  # type: ignore[arg-type]
    except Exception:
        return int(0)


def run_log_only(*, adapter, config, emotions, args, gen) -> Optional[int]:
    if not bool(getattr(args, "log_only", False)):
        return None

    try:
        comp0 = getattr(config, "composition", None)
        if comp0 is not None and getattr(args, "note_log", None) is None:
            setattr(comp0, "note_log_enabled", True)
    except Exception:
        pass

    try:
        from composition.note_log import NoteLogContext, format_note_dump, get_note_event_logger
        from audiogen_core.note_event_log import NoteEventLogContext
    except Exception:
        logging.exception("Failed to import note logging utilities")
        return 2

    raw_em = str(getattr(args, "emotion", "") or "").strip()
    # `--log-only` historically documents `--emotion`, but full/offline sweep
    # snippets often pass `--offline-emotion`. Avoid silently falling back to
    # neutral when that is the only explicit emotion selector.
    try:
        offline_em = str(getattr(args, "offline_emotion", "") or "").strip()
    except Exception:
        offline_em = ""
    if (not raw_em or raw_em.lower() == "neutral") and offline_em and offline_em.lower() != "neutral":
        raw_em = str(offline_em)
    idx = None
    if raw_em:
        if raw_em.isdigit() or (raw_em.startswith("-") and raw_em[1:].isdigit()):
            try:
                ii = int(raw_em)
            except Exception:
                ii = None
            if ii is not None and 0 <= int(ii) < len(emotions):
                idx = int(ii)
        else:
            key = raw_em.lower()
            idx0 = next(
                (i for i, em in enumerate(emotions) if str(getattr(em, "name", "") or "").strip().lower() == key),
                None,
            )
            if idx0 is not None:
                idx = int(idx0)
    if idx is None:
        neutral_i = next(
            (i for i, em in enumerate(emotions) if str(getattr(em, "name", "") or "").strip().lower() == "neutral"),
            None,
        )
        idx = int(neutral_i) if neutral_i is not None else 0
    emotion = emotions[int(idx)]
    root0 = int(getattr(args, "root", 60) or 60)
    preview_n = int(max(1, int(getattr(args, "log_only_preview_sections", 2) or 2)))

    try:
        events, _bars = adapter.generate_arranged_preview_events(
            emotion,
            int(root0),
            runtime_mode="offline",
            preview_sections=int(preview_n),
        )
    except Exception:
        logging.exception("log-only generation failed")
        return 2

    try:
        comp = getattr(config, "composition", None)
        note_log_path = str(getattr(comp, "note_log_path", "logs/notes.log") or "logs/notes.log") if comp is not None else "logs/notes.log"
    except Exception:
        note_log_path = "logs/notes.log"
    try:
        seed_val = getattr(gen, "seed", None)
        seed0 = int(seed_val) if seed_val is not None else None
    except Exception:
        seed0 = None
    try:
        logger = get_note_event_logger(note_log_path)
        song_render = getattr(adapter, "_last_arranged_song_render", None)
        md0 = getattr(song_render, "metadata", None) or {}
        roles0 = tuple(str(x or "") for x in list(md0.get("section_roles") or []))
        bars0 = (
            tuple(int(getattr(sec, "bars", 0) or 0) for sec in list(getattr(song_render, "sections", []) or []))
            if song_render is not None
            else ()
        )
        form0 = str(md0.get("arrangement_form", "") or "")
        ctx = NoteEventLogContext(
            emotion_name=str(getattr(emotion, "name", "") or ""),
            section_index=0,
            root_midi=int(root0),
            beats_per_bar=4.0,
            scale_intervals=(),
            seed=seed0,
            run_tag="log_only",
            arrangement_form=str(form0),
            section_roles=tuple(roles0),
            section_bars=tuple(bars0),
        )
        try:
            logger.log_arrangement_markers(ctx, metadata=dict(md0))
        except Exception:
            pass
        n_logged = int(logger.log_created_events(list(events or []), ctx))
    except Exception:
        logging.exception("log-only note log write failed")
        return 2

    try:
        comp = getattr(config, "composition", None)
        console_on = bool(getattr(comp, "note_log_console_enabled", False)) if comp is not None else False
    except Exception:
        console_on = False
    if console_on:
        try:
            dump_ctx = NoteLogContext(
                emotion_name=str(getattr(emotion, "name", "") or ""),
                section_index=0,
                root_midi=int(root0),
                beats_per_bar=4.0,
                seed=seed0,
                run_tag="log_only",
            )
            s = format_note_dump(list(events or []), dump_ctx)
            if s:
                logging.info("%s", s)
        except Exception:
            pass

    logging.info(
        "log-only: emotion=%s root=%d seed=%s preview_sections=%d events=%d notes_logged=%d note_log_path=%r",
        str(getattr(emotion, "name", "") or "neutral"),
        int(root0),
        "-" if seed0 is None else str(int(seed0)),
        int(preview_n),
        len(list(events or [])),
        int(n_logged),
        str(note_log_path),
    )
    return 0


def run_offline_export(*, adapter, config, emotions, args) -> Optional[int]:
    if str(getattr(args, "mode", "") or "").strip().lower() != "offline":
        return None

    def _parse_offline_outputs(raw: str) -> Dict[str, bool]:
        tokens = [t.strip().lower() for t in str(raw or "").split(",") if t.strip()]
        if not tokens:
            tokens = ["wav", "midi"]
        if any(t in {"all", "*"} for t in tokens):
            return {"wav": True, "midi": True, "report": True, "meta": True}
        if any(t in {"none", "0", "off"} for t in tokens):
            return {"wav": False, "midi": False, "report": False, "meta": False}
        out = {"wav": False, "midi": False, "report": False, "meta": False}
        for t in tokens:
            if t in {"wav", "wave"}:
                out["wav"] = True
            elif t in {"midi", "mid"}:
                out["midi"] = True
            elif t in {"report", "json"}:
                out["report"] = True
            elif t in {"meta", "metadata"}:
                out["meta"] = True
        if any(out.values()) and not out["meta"]:
            out["meta"] = True
        return out

    def _prompt_offline_outputs_tty(current: Dict[str, bool]) -> Dict[str, bool]:
        try:
            if not sys.stdin.isatty():
                return dict(current or {})
        except Exception:
            return dict(current or {})
        cur = dict(current or {})
        cur_str = ",".join([k for k in ("wav", "midi", "report", "meta") if bool(cur.get(k))]) or "none"
        sys.stdout.write(f"\nOffline outputs (current: {cur_str})\n")
        sys.stdout.write("  Enter to keep | all | none | wav,midi,report,meta (comma-separated)\n\n")
        sys.stdout.flush()
        try:
            raw = input("Outputs: ").strip()
        except EOFError:
            return cur
        if raw == "":
            return cur
        return _parse_offline_outputs(raw)

    def _prompt_offline_form_tty(current: Optional[str]) -> Optional[str]:
        try:
            if not sys.stdin.isatty():
                return current
        except Exception:
            return current
        cur = str(current or "").strip() or "default"
        sys.stdout.write(f"\nOffline arrangement form (current: {cur})\n")
        sys.stdout.write("  Enter to keep | e.g. default, \"dialogue (call and responce) WIP\", swing\n\n")
        sys.stdout.flush()
        try:
            raw = input("Form: ").strip()
        except EOFError:
            return current
        if raw == "":
            return current
        return str(raw).strip()

    def _emotion_index_by_name_offline(name: str) -> int:
        key = (name or "").strip().lower()
        idx0 = next((i for i, em in enumerate(emotions) if str(getattr(em, "name", "")).strip().lower() == key), None)
        return int(idx0) if idx0 is not None else 0

    def _select_emotion_offline(*, default_name: str = "neutral") -> Optional[int]:
        default_idx = _emotion_index_by_name_offline(str(default_name))
        default_idx = int(default_idx) if 0 <= int(default_idx) < len(emotions) else 0
        try:
            if not sys.stdin.isatty():
                return int(default_idx)
        except Exception:
            return int(default_idx)

        sys.stdout.write("\nSelect emotion for next song (Enter to quit)\n\n")
        for i, em in enumerate(emotions):
            nm = str(getattr(em, "name", "") or "").strip() or f"emotion_{i}"
            mark = "  ← default" if int(i) == int(default_idx) else ""
            sys.stdout.write(f"  {i:>3}  {nm}{mark}\n")
        sys.stdout.write("\n")
        sys.stdout.flush()
        try:
            raw = input("Emotion (name or index): ").strip()
        except EOFError:
            return None
        if raw == "":
            return None
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(emotions):
                return int(idx)
            sys.stdout.write(f"Out of range: {raw}\n")
            sys.stdout.flush()
            return None
        idx = _emotion_index_by_name_offline(raw)
        if 0 <= int(idx) < len(emotions):
            return int(idx)
        sys.stdout.write(f"Unknown emotion: {raw}\n")
        sys.stdout.flush()
        return None

    out_dir = Path(str(getattr(args, "offline_export_dir", "songs") or "songs")).expanduser()
    if not out_dir.is_absolute():
        out_dir = Path(__file__).resolve().parent.parent / out_dir
    prefix_base = str(getattr(args, "offline_export_prefix", "song") or "song").strip() or "song"
    root_note = int(getattr(args, "root", 60) or 60)
    outputs = _parse_offline_outputs(str(getattr(args, "offline_outputs", "wav,midi") or "wav,midi"))
    batch_n = int(getattr(args, "offline_count", 0) or 0)

    if batch_n <= 0:
        try:
            if sys.stdin.isatty():
                outputs = _prompt_offline_outputs_tty(outputs)
        except Exception:
            pass

    try:
        comp = getattr(config, "composition", None)
        if comp is not None:
            current_form = str(getattr(comp, "arranged_song_mode", "default") or "default")
            offline_form = str(getattr(args, "offline_arrangement_form", "") or "").strip()
            if not offline_form and batch_n <= 0:
                offline_form = str(_prompt_offline_form_tty(current_form) or "").strip()
            if offline_form:
                setattr(comp, "arranged_song_mode", str(offline_form))
            if getattr(args, "offline_arranged_seconds", None) is not None:
                setattr(comp, "arranged_song_seconds", float(getattr(args, "offline_arranged_seconds")))
            if getattr(args, "offline_arranged_max_bars", None) is not None:
                setattr(comp, "arranged_song_max_bars", int(getattr(args, "offline_arranged_max_bars")))
            if getattr(args, "offline_arranged_bars_per_section", None) is not None:
                setattr(comp, "bars_per_section", int(getattr(args, "offline_arranged_bars_per_section")))
    except Exception:
        pass

    default_emotion_name = str(getattr(args, "offline_emotion", "neutral") or "neutral").strip() or "neutral"
    emotion_cycle = [e.strip() for e in str(default_emotion_name).split(",") if e.strip()]
    if not emotion_cycle:
        emotion_cycle = ["neutral"]
    first = True
    song_i = 0
    while True:
        if batch_n > 0:
            pick = emotion_cycle[int(song_i) % int(len(emotion_cycle))]
            idx = _emotion_index_by_name_offline(str(pick))
        else:
            idx = _select_emotion_offline(default_name=default_emotion_name)
        if idx is None:
            break
        if not first:
            try:
                default_emotion_name = str(getattr(emotions[int(idx)], "name", "neutral") or "neutral")
            except Exception:
                default_emotion_name = "neutral"
        first = False

        emotion_obj = emotions[int(idx)]
        try:
            events, total_bars = adapter.generate_arranged_song_events(emotion_obj, root_note, runtime_mode="normal")
        except Exception:
            events, total_bars = [], 0
        logging.info(
            "Offline mode: generated arranged song (emotion=%s root=%s events=%d bars=%d).",
            getattr(emotion_obj, "name", "neutral"),
            root_note,
            len(events or []),
            int(total_bars),
        )
        try:
            emo_name = str(getattr(emotion_obj, "name", "") or "").strip().lower() or "emotion"
        except Exception:
            emo_name = "emotion"
        prefix = f"{prefix_base}_{emo_name}"
        try:
            out = _write_offline_song_outputs(
                config=config,
                song_events=list(events or []),
                total_bars=int(total_bars),
                song_render=getattr(adapter, "_last_arranged_song_render", None),
                export_dir=out_dir,
                name_prefix=prefix,
                write_wav=bool(outputs.get("wav", True)),
                write_midi=bool(outputs.get("midi", True)),
                write_report=bool(outputs.get("report", True)),
                write_meta=bool(outputs.get("meta", True)),
            )
            if out.get("wav"):
                logging.info("Offline export WAV: %s", out.get("wav", ""))
            if out.get("midi"):
                logging.info("Offline export MIDI: %s", out.get("midi", ""))
            if out.get("json"):
                logging.info("Offline export report: %s", out.get("json", ""))
            if out.get("meta"):
                logging.info("Offline export metadata: %s", out.get("meta", ""))
        except Exception:
            logging.exception("Offline export failed")

        if batch_n > 0:
            batch_n -= 1
            song_i += 1
            if batch_n <= 0:
                break
            continue

        try:
            if not sys.stdin.isatty():
                break
        except Exception:
            break
        song_i += 1

    return 0
