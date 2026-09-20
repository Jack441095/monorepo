# utils/rt_bar_profiler.py
# Optional realtime bar profiling (wall splits + slow-bar cProfile dumps).

from __future__ import annotations

import cProfile
import io
import logging
import os
import pstats
from typing import Optional


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def log_rt_bar_timing_if_enabled(
    logger: logging.Logger,
    *,
    prepare_ms: float,
    render_ms: float,
    total_ms: float,
) -> None:
    if not _env_truthy("AUDIOGEN_RT_BAR_LOG"):
        return
    try:
        logger.info(
            "rt_bar_timing prepare=%.2fms render=%.2fms total=%.2fms",
            float(prepare_ms),
            float(render_ms),
            float(total_ms),
        )
    except Exception:
        pass


def start_rt_cprofile_if_enabled() -> Optional[cProfile.Profile]:
    if not _env_truthy("AUDIOGEN_RT_CPROFILE"):
        return None
    pr = cProfile.Profile()
    pr.enable()
    return pr


def finish_rt_cprofile_if_slow(
    pr: Optional[cProfile.Profile],
    logger: logging.Logger,
    wall_seconds: float,
    bar_seconds: float,
) -> None:
    if pr is None:
        return
    try:
        pr.disable()
    except Exception:
        return
    try:
        ratio = float(os.environ.get("AUDIOGEN_RT_PROFILE_SLOW_RATIO", "0.85") or "0.85")
    except Exception:
        ratio = 0.85
    ratio = max(0.05, min(0.999, float(ratio)))
    bar_seconds = max(0.05, float(bar_seconds))
    if float(wall_seconds) < max(0.25, float(bar_seconds) * float(ratio)):
        return
    try:
        topn = int(os.environ.get("AUDIOGEN_RT_CPROFILE_TOPN", "25") or "25")
    except Exception:
        topn = 25
    topn = max(5, min(80, int(topn)))
    buf = io.StringIO()
    try:
        pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(topn)
    except Exception as exc:
        logger.warning("rt_cprofile: failed to format stats: %s", exc)
        return
    try:
        logger.warning(
            "rt_cprofile slow bar wall=%.1fms bar=%.1fms ratio_th=%.2f\n%s",
            float(wall_seconds) * 1000.0,
            float(bar_seconds) * 1000.0,
            float(ratio),
            buf.getvalue(),
        )
    except Exception:
        pass
