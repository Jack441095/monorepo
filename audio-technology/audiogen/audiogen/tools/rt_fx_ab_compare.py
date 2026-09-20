#!/usr/bin/env python3
"""
Offline A/B: master FX variants (reverb tier × multiband) on the same bar events.

Writes WAV clips + timing/metrics JSON for listening and comparison.

  .venv/bin/python tools/rt_fx_ab_compare.py
  .venv/bin/python tools/rt_fx_ab_compare.py --bars 2 --output-dir .cache/rt_fx_ab
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


@dataclass(frozen=True)
class FxVariant:
    slug: str
    reverb_tier: str
    skip_multiband: bool
    fast_master: bool
    skip_master_eq: bool = False


DEFAULT_VARIANTS = [
    FxVariant("reverb_balanced_no_mb", "balanced", True, True),
    FxVariant("reverb_high_rt_no_mb", "high_rt", True, True),
    FxVariant("reverb_high_no_mb", "high", True, True),
    FxVariant("reverb_high_rt_with_mb", "high_rt", False, True),
    FxVariant("reverb_high_with_mb", "high", False, True),
    FxVariant("reverb_high_full_inserts", "high", False, False, skip_master_eq=False),
]


def _audio_metrics(audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim == 2 and x.shape[1] >= 2:
        mono = 0.5 * (x[:, 0] + x[:, 1])
    else:
        mono = x.reshape(-1)
    mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)
    if mono.size == 0:
        return {"peak": 0.0, "rms": 0.0, "crest_db": 0.0}
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono * mono) + 1e-12))
    crest = float(20.0 * np.log10(max(1e-9, peak / max(1e-9, rms))))
    return {"peak": peak, "rms": rms, "crest_db": crest}


def _collect_bar_events(emotion, root: int, bar_idx: int) -> tuple[List, float, int]:
    from composition.engine import CompositionGenerator
    from audiogen_core.config import CONFIG

    gen = CompositionGenerator(enable_perf_monitoring=False)
    events = gen.generate_section(emotion, root, max(4, int(bar_idx) + 2))
    tempo = float(getattr(CONFIG.composition, "default_tempo", 70.0) or 70.0)
    bar_seconds = 4.0 * 60.0 / max(1.0, tempo)
    samples = int(bar_seconds * int(CONFIG.audio.sample_rate))
    bar_start = float(bar_idx) * 4.0
    bar_end = bar_start + 4.0
    bar_events = []
    for ev in events:
        if len(ev) < 6:
            continue
        start = float(ev[3])
        duration = float(ev[4])
        if start < bar_end and start + duration > bar_start:
            ev2 = list(ev)
            if start < bar_start:
                ev2[3] = 0.0
                ev2[4] = min(duration, bar_end - bar_start)
            else:
                ev2[3] = start - bar_start
                ev2[4] = min(duration, bar_end - start)
            if float(ev2[4]) > 0:
                bar_events.append(tuple(ev2))
    return bar_events, tempo, samples


def _render_variant(
    variant: FxVariant,
    bar_events: List,
    tempo: float,
    samples: int,
    *,
    warmup: bool,
) -> Dict[str, Any]:
    from audio.audio_container import AudioContainer
    from audiogen_core.config import CONFIG

    from audio.RT_player.renderer import AudioRenderer
    from sampler import SamplerEngine as SamplerSynthesisEngine

    CONFIG.set_performance_mode("high")
    container = AudioContainer.create_from_config(CONFIG)
    engine = SamplerSynthesisEngine(CONFIG)
    renderer = AudioRenderer(
        synthesis_engine=engine,
        mixer=container.mixer,
        sample_rate=container.sample_rate,
        reverb_processor=container.reverb,
        master_bus=getattr(container, "master_bus", None),
    )

    if warmup:
        try:
            renderer.render_bar(
                bar_events,
                tempo,
                samples,
                fast_master=True,
                skip_multiband=True,
                skip_master_eq=False,
                reverb_quality_tier="balanced",
            )
        except Exception:
            pass

    t0 = time.perf_counter()
    audio = renderer.render_bar(
        bar_events,
        tempo,
        samples,
        fast_master=bool(variant.fast_master),
        skip_multiband=bool(variant.skip_multiband),
        skip_master_eq=bool(variant.skip_master_eq),
        skip_master_inserts=bool(variant.skip_multiband and variant.skip_master_eq),
        reverb_quality_tier=str(variant.reverb_tier),
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    stages = dict(getattr(renderer, "last_stage_timing_ms", {}) or {})
    return {
        "wall_ms": float(wall_ms),
        "stages_ms": stages,
        "audio_metrics": _audio_metrics(audio, int(container.sample_rate)),
        "audio": audio,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=".cache/rt_fx_ab")
    ap.add_argument("--bars", type=int, default=1, help="Bar index to render (0-based)")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument("--warmup", action="store_true", default=True)
    args = ap.parse_args()

    from audiogen_core.config import CONFIG
    from data.music_data import EMOTION_BY_NAME
    from utils.numba_warmup import warmup_numba_kernels

    try:
        warmup_numba_kernels()
    except Exception:
        pass

    em = EMOTION_BY_NAME.get(str(args.emotion).strip().lower()) or EMOTION_BY_NAME.get("neutral")
    bar_events, tempo, samples = _collect_bar_events(em, int(args.root), int(args.bars))
    if not bar_events:
        print("No events for bar; aborting", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "emotion": getattr(em, "name", str(args.emotion)),
        "root": int(args.root),
        "bar_index": int(args.bars),
        "event_count": len(bar_events),
        "tempo": float(tempo),
        "bar_samples": int(samples),
        "sample_rate": int(CONFIG.audio.sample_rate),
        "variants": [],
    }

    try:
        from scipy.io import wavfile as wavfile
    except Exception as exc:
        print(f"scipy.io.wavfile required: {exc}", file=sys.stderr)
        return 1

    for variant in DEFAULT_VARIANTS:
        row = _render_variant(
            variant,
            bar_events,
            tempo,
            samples,
            warmup=bool(args.warmup),
        )
        audio = row.pop("audio")
        wav_path = out_dir / f"{variant.slug}.wav"
        peak = float(row["audio_metrics"].get("peak", 0.0) or 0.0)
        scaled = np.clip(audio * (0.95 / max(peak, 1e-6)), -1.0, 1.0)
        wav_i16 = (scaled * 32767.0).astype(np.int16)
        wavfile.write(str(wav_path), int(CONFIG.audio.sample_rate), wav_i16)
        row["wav_path"] = str(wav_path)
        row["slug"] = variant.slug
        row["reverb_tier"] = variant.reverb_tier
        row["skip_multiband"] = variant.skip_multiband
        row["fast_master"] = variant.fast_master
        report["variants"].append(row)
        print(
            f"{variant.slug}: wall={row['wall_ms']:.0f}ms "
            f"master={row['stages_ms'].get('master', 0):.0f}ms "
            f"chords={row['stages_ms'].get('chords', 0):.0f}ms "
            f"rms={row['audio_metrics']['rms']:.4f} -> {wav_path.name}",
            file=sys.stderr,
        )

    summary_path = out_dir / "fx_ab_summary.json"
    summary_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"ok": True, "summary": str(summary_path), "wav_dir": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
