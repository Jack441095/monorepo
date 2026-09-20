import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List
import numpy as np

def slice_events_for_bar(events: List[tuple], *, bar_index: int, beats_per_bar: float = 4.0) -> List[tuple]:
    out: List[tuple] = []
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    bar_start = float(bar_index) * bpb
    bar_end = bar_start + bpb
    for ev in list(events or []):
        if not ev or len(ev) != 6:
            continue
        try:
            ch, midi, vel, st, dur, notes = ev
            stf = float(st)
            durf = float(dur)
        except Exception:
            continue
        if durf <= 1e-9:
            continue
        ev_end = stf + durf
        if ev_end <= bar_start or stf >= bar_end:
            continue
        local_start = max(stf, bar_start) - bar_start
        local_end = min(ev_end, bar_end) - bar_start
        local_dur = float(local_end - local_start)
        if local_dur <= 1e-9:
            continue
        try:
            out.append((int(ch), midi, int(vel), float(local_start), float(local_dur), list(notes)))
        except Exception:
            continue
    return out


def tempo_for_beat(tempo_map: List[tuple], beat: float, *, fallback_bpm: float = 70.0) -> float:
    bpm = float(fallback_bpm)
    for tp in list(tempo_map or []):
        try:
            start_beat, this_bpm = float(tp[0]), float(tp[1])
        except Exception:
            continue
        if start_beat <= float(beat):
            bpm = float(this_bpm)
        else:
            break
    return max(20.0, min(260.0, float(bpm)))


def arrangement_role_for_export_bar(song_render, bar_index: int) -> str:
    if song_render is None:
        return ""
    try:
        sections = list(getattr(song_render, "sections", []) or [])
        md = getattr(song_render, "metadata", None) or {}
        roles = list(md.get("section_roles") or [])
    except Exception:
        return ""
    bi = int(bar_index)
    start_bar = 0
    for i, sec in enumerate(sections):
        try:
            bars = int(getattr(sec, "bars", 0) or 0)
        except Exception:
            bars = 0
        if bars <= 0:
            continue
        if start_bar <= bi < start_bar + bars:
            if i < len(roles):
                return str(roles[i] or "").strip().lower()
            return ""
        start_bar += bars
    return ""


def arrangement_pre_chorus_last_bar_for_export(song_render, bar_index: int) -> bool:
    if song_render is None:
        return False
    try:
        sections = list(getattr(song_render, "sections", []) or [])
        md = getattr(song_render, "metadata", None) or {}
        roles = list(md.get("section_roles") or [])
    except Exception:
        return False
    bi = int(bar_index)
    start_bar = 0
    for i, sec in enumerate(sections):
        try:
            bars = int(getattr(sec, "bars", 0) or 0)
        except Exception:
            bars = 0
        if bars <= 0:
            continue
        if start_bar <= bi < start_bar + bars:
            role = str(roles[i] if i < len(roles) else "").strip().lower()
            if role == "pre_chorus" and bi == start_bar + bars - 1:
                return True
            return False
        start_bar += bars
    return False


def write_offline_song_outputs(
    *,
    config,
    song_events: List[tuple],
    total_bars: int,
    song_render,
    export_dir: Path,
    name_prefix: str,
) -> Dict[str, str]:
    from audio.RT_player.renderer import AudioRenderer
    from audio.audio_container import AudioContainer
    from composition.song_generator import SongRender, SongGenerator
    from sampler import SamplerEngine as SamplerSynthesisEngine
    from scipy.io import wavfile

    export_dir.mkdir(parents=True, exist_ok=True)
    sample_rate = int(getattr(getattr(config, "audio", None), "sample_rate", 44100) or 44100)

    container = AudioContainer.create_from_config(config)
    synth = SamplerSynthesisEngine(config)
    try:
        synth.preload_samplers(["bass", "chords", "melody", "arp", "drone", "counter_melody"])
    except Exception:
        pass
    renderer = AudioRenderer(
        synthesis_engine=synth,
        mixer=container.mixer,
        sample_rate=container.sample_rate,
        reverb_processor=container.reverb,
        master_bus=getattr(container, "master_bus", None),
    )

    safe_prefix = "".join(c if (str(c).isalnum() or c in {"-", "_"}) else "_" for c in str(name_prefix))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_prefix}_{stamp}" if safe_prefix else f"song_{stamp}"

    if song_render is None:
        song_render = SongRender(sections=[], events=list(song_events or []), tempo_map=[], metadata={})
    json_path = Path("")
    midi_path = Path("")
    try:
        json_path = Path(SongGenerator.export_report(song_render, out_path=str(export_dir / f"{stem}.json")))
    except Exception:
        json_path = Path("")
    try:
        midi_path = export_dir / f"{stem}.mid"
        SongGenerator.export_to_midi(song_render, out_path=str(midi_path))
    except Exception:
        midi_path = Path("")

    tempo_map = []
    try:
        tempo_map = list(getattr(song_render, "tempo_map", []) or [])
    except Exception:
        tempo_map = []
    fallback_bpm = 70.0
    if tempo_map:
        try:
            fallback_bpm = float(tempo_map[0][1])
        except Exception:
            fallback_bpm = 70.0

    bars_i = max(0, int(total_bars))
    rendered_bars = []
    for bar_idx in range(bars_i):
        if int(bar_idx) == 0 or int(bar_idx) % 4 == 0 or int(bar_idx) == int(bars_i) - 1:
            try:
                logging.info("Offline render: bar %d/%d", int(bar_idx) + 1, int(bars_i))
            except Exception:
                pass
        beat = float(bar_idx) * 4.0
        bpm = tempo_for_beat(tempo_map, beat, fallback_bpm=float(fallback_bpm))
        bar_samples = int(round((4.0 * 60.0 / max(1.0, float(bpm))) * float(sample_rate)))
        bar_samples = max(1, int(bar_samples))
        ev_bar = slice_events_for_bar(list(song_events or []), bar_index=int(bar_idx), beats_per_bar=4.0)
        role_bar = arrangement_role_for_export_bar(song_render, int(bar_idx))
        export_fx_scale = 1.0
        try:
            _aexp = getattr(config, "audio", None)
            if _aexp is not None and bool(getattr(_aexp, "arrangement_fx_return_automation_enabled", True)):
                from data.arrangement_curves import arrangement_role_fx_return_mult
                _st = float(getattr(_aexp, "arrangement_fx_return_strength", 1.0) or 1.0)
                export_fx_scale = float(arrangement_role_fx_return_mult(str(role_bar or ""), strength=_st))
        except Exception:
            export_fx_scale = 1.0
        export_vel_ride = 1.0
        try:
            _aexp2 = getattr(config, "audio", None)
            if _aexp2 is not None and bool(
                getattr(_aexp2, "arrangement_velocity_ride_enabled", True)
            ):
                from data.arrangement_curves import arrangement_role_velocity_ride_mult
                _vst2 = float(
                    getattr(_aexp2, "arrangement_velocity_ride_strength", 1.0) or 1.0
                )
                _pcl_m = arrangement_pre_chorus_last_bar_for_export(
                    song_render, int(bar_idx)
                )
                _sw2 = bool(
                    getattr(
                        _aexp2, "arrangement_pre_chorus_last_bar_swell_enabled", True
                    )
                )
                _pss2 = float(
                    getattr(
                        _aexp2, "arrangement_pre_chorus_last_bar_swell_strength", 1.0
                    )
                    or 1.0
                )
                export_vel_ride = float(
                    arrangement_role_velocity_ride_mult(
                        str(role_bar or ""),
                        strength=_vst2,
                        pre_chorus_last_bar=(_pcl_m and _sw2),
                        pre_chorus_swell_strength=_pss2,
                    )
                )
        except Exception:
            export_vel_ride = 1.0
        try:
            audio_bar = renderer.render_bar(
                ev_bar,
                tempo=float(bpm),
                bar_samples=int(bar_samples),
                velocity_multiplier=float(export_vel_ride),
                arrangement_role=str(role_bar or ""),
                fx_return_scale=float(export_fx_scale),
            )
            rendered_bars.append(audio_bar.astype("float32", copy=False))
        except Exception:
            logging.exception("Offline render failed at bar %d/%d", int(bar_idx) + 1, int(bars_i))
            break

    if rendered_bars:
        audio = np.concatenate(rendered_bars, axis=0).astype("float32", copy=False)
    else:
        audio = np.zeros((1, 2), dtype="float32")

    wav_path = export_dir / f"{stem}.wav"
    try:
        wav_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("int16")
        wavfile.write(str(wav_path), int(sample_rate), wav_i16)
    except Exception:
        logging.exception("Offline WAV write failed")
        wav_path = Path("")

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

    for chi, row in list(ch_stats.items()):
        try:
            row["velocity_mean"] = float(row["velocity_sum"]) / float(max(1, int(row["events"])))
        except Exception:
            row["velocity_mean"] = None
        try:
            del row["velocity_sum"]
        except Exception:
            pass

    sidecar = {
        "wav_path": str(wav_path),
        "json_path": str(json_path),
        "midi_path": str(midi_path) if str(midi_path) else "",
        "bars": int(bars_i),
        "events": int(len(list(song_events or []))),
        "channels": [ch_stats[k] for k in sorted(ch_stats.keys())],
    }
    sidecar_path = export_dir / f"{stem}.meta.json"
    try:
        sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass
    return {
        "wav": str(wav_path),
        "json": str(json_path),
        "midi": str(midi_path) if str(midi_path) else "",
        "meta": str(sidecar_path),
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
        return int(result["returncode"])

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
        rc = _run([
            sys.executable,
            str(root / "scripts" / "export_emotion_dataset.py"),
            "--out-dir",
            str(dataset_dir),
        ])
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
    return int(result["returncode"])


def run_offline_mode_generation(args, config, adapter) -> int:
    from data.music_data import EMOTIONS
    try:
        neutral_idx = next(
            (i for i, em in enumerate(EMOTIONS) if str(getattr(em, "name", "")).strip().lower() == "neutral"),
            0,
        )
    except Exception:
        neutral_idx = 0
    neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(EMOTIONS) else 0
    neutral_emotion = EMOTIONS[int(neutral_idx)]
    root_note = int(args.root)
    try:
        events, total_bars = adapter.generate_arranged_song_events(neutral_emotion, root_note, runtime_mode="normal")
    except Exception:
        events, total_bars = [], 0
    logging.info(
        "Offline mode: generated arranged song (emotion=%s root=%s events=%d bars=%d).",
        getattr(neutral_emotion, "name", "neutral"),
        root_note,
        len(events or []),
        int(total_bars),
    )
    out_dir = Path(str(getattr(args, "offline_export_dir", "songs") or "songs")).expanduser()
    if not out_dir.is_absolute():
        out_dir = Path(__file__).resolve().parent.parent / out_dir
    try:
        prefix = str(getattr(args, "offline_export_prefix", "song") or "song").strip() or "song"
        out = write_offline_song_outputs(
            config=config,
            song_events=list(events or []),
            total_bars=int(total_bars),
            song_render=getattr(adapter, "_last_arranged_song_render", None),
            export_dir=out_dir,
            name_prefix=prefix,
        )
        logging.info("Offline export complete: wav=%s", out.get("wav", ""))
        if out.get("midi"):
            logging.info("Offline export MIDI: %s", out.get("midi", ""))
        if out.get("json"):
            logging.info("Offline export report: %s", out.get("json", ""))
        if out.get("meta"):
            logging.info("Offline export metadata: %s", out.get("meta", ""))
    except Exception:
        logging.exception("Offline export failed")
    return 0
