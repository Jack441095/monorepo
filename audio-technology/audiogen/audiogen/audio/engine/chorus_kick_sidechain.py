# audio/engine/chorus_kick_sidechain.py
# ---------------------------------------------------------------------------
# Chorus-only: 4/4 kick + envelope follower ducking (sidechain-style).
# Ducks all mixer strips except drone and the kick strip; kick audio is written to
# the dedicated kick mixer channel (same summing path as MIDI stems).
#
# Kick source: procedural pulse, or optional ``samples/kick.wav`` (see ``ChorusKickSidechainConfig``).
# ---------------------------------------------------------------------------
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np

from audiogen_core.mixer_config import CHANNEL_NAMES, KICK_MIXER_CHANNEL_INDEX

# Try to use Numba; fall back to pure Python (matches sampler/utils.py's convention).
try:
    from numba import njit

    _NUMBA_AVAILABLE = True
except ImportError:
    _NUMBA_AVAILABLE = False

_COUNTER_MELODY_CH = next((ch for ch, name in CHANNEL_NAMES.items() if name == "counter_melody"), 5)

_KICK_SHOT_CACHE_LOCK = threading.Lock()
# (resolved_path, mtime, target_sr, max_ms_key) -> mono float32 one-shot
_KICK_SHOT_CACHE: Dict[Tuple[str, float, int, int], np.ndarray] = {}


def parse_chorus_roles(raw: Any) -> Set[str]:
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(x).strip().lower() for x in raw if str(x).strip()}
    s = str(raw).strip()
    if not s:
        return set()
    return {p.strip().lower() for p in s.replace(";", ",").split(",") if p.strip()}


def _pcm_to_float32(audio: np.ndarray) -> np.ndarray:
    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        scale = max(abs(info.min), info.max)
        return audio.astype(np.float32) / float(scale)
    return audio.astype(np.float32, copy=False)


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    """Shape (n,) or (n, ch) -> (n,) mono float32."""
    x = _pcm_to_float32(np.asarray(audio))
    if x.ndim == 1:
        return x.astype(np.float32, copy=False)
    if x.ndim == 2:
        if x.shape[1] == 1:
            return x[:, 0].astype(np.float32, copy=False)
        # Downmix many channels to mono; stereo uses mean.
        return np.mean(x, axis=1).astype(np.float32, copy=False)
    return np.asarray(x.reshape(-1), dtype=np.float32)


def _resample_mono(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or int(len(x)) <= 0:
        return x.astype(np.float32, copy=False)
    try:
        import scipy.signal as sig  # type: ignore[import]
    except Exception:
        # Linear fallback (good enough for short kicks if SciPy missing).
        ratio = float(dst_sr) / float(max(1, src_sr))
        n_out = int(max(1, round(float(len(x)) * ratio)))
        t_in = np.linspace(0.0, 1.0, num=int(len(x)), endpoint=False, dtype=np.float64)
        t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float64)
        return np.interp(t_out, t_in, x.astype(np.float64)).astype(np.float32)
    win = ("kaiser", 8.6)
    return sig.resample_poly(x.astype(np.float32, copy=False), int(dst_sr), int(src_sr), axis=0, window=win).astype(
        np.float32, copy=False
    )


def resolve_chorus_kick_sample_path(raw: str) -> Path:
    p = Path(str(raw or "").strip())
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        return p.resolve()
    except Exception:
        return p


def load_chorus_kick_one_shot_mono(path: Path, target_sr: int, max_ms: float) -> Optional[np.ndarray]:
    """
    Load WAV from ``path``, resample to ``target_sr``, return mono float32 truncated
    to the first ``max_ms`` milliseconds. Returns None if missing/unreadable.
    """
    try:
        if not path.is_file():
            return None
        st = path.stat()
        mtime = float(getattr(st, "st_mtime", 0.0) or 0.0)
    except Exception:
        return None

    max_ms_f = float(max(1.0, min(4000.0, float(max_ms or 450.0))))
    max_ms_key = int(round(max_ms_f))
    cache_key = (str(path), mtime, int(target_sr), max_ms_key)
    with _KICK_SHOT_CACHE_LOCK:
        hit = _KICK_SHOT_CACHE.get(cache_key)
    if hit is not None:
        return np.array(hit, dtype=np.float32, copy=True)

    try:
        from scipy.io import wavfile  # type: ignore[import]

        sr_file, raw = wavfile.read(str(path))
    except Exception:
        return None

    try:
        sr_i = int(sr_file)
    except Exception:
        return None

    mono = _to_mono_float32(raw)
    mono = _resample_mono(mono, sr_i, int(max(1, target_sr)))

    max_samps = int(round(max_ms_f * 1e-3 * float(max(1, target_sr))))
    max_samps = max(8, min(int(len(mono)), max_samps))
    mono = mono[:max_samps].astype(np.float32, copy=False)

    peak = float(np.max(np.abs(mono))) + 1e-12
    if peak < 1e-8:
        return None
    mono = (mono / peak).astype(np.float32, copy=False)

    with _KICK_SHOT_CACHE_LOCK:
        _KICK_SHOT_CACHE[cache_key] = np.array(mono, dtype=np.float32, copy=True)
        if len(_KICK_SHOT_CACHE) > 32:
            try:
                for k in list(_KICK_SHOT_CACHE.keys())[:8]:
                    _KICK_SHOT_CACHE.pop(k, None)
            except Exception:
                pass

    return np.array(mono, dtype=np.float32, copy=True)


def clear_chorus_kick_sample_cache() -> None:
    """Test hook / hot-reload helper."""
    with _KICK_SHOT_CACHE_LOCK:
        _KICK_SHOT_CACHE.clear()


if _NUMBA_AVAILABLE:

    @njit(cache=True)
    def _envelope_follower_loop_nb(s32: np.ndarray, aa: float, ar: float) -> np.ndarray:
        n = s32.shape[0]
        out = np.empty(n, dtype=np.float32)
        env = 0.0
        for i in range(n):
            x = abs(s32[i])
            if x > env:
                env = aa * env + (1.0 - aa) * x
            else:
                env = ar * env + (1.0 - ar) * x
            out[i] = env
        return out


def _envelope_follower_abs_mono(sig: np.ndarray, sample_rate: int, attack_ms: float, release_ms: float) -> np.ndarray:
    # 2026-07-04 (docs/AUDIOGEN_COMPOSITION_PLAN.md latency work): same per-sample
    # sequential envelope shape as `sampler/pitch_filter.py::DynamicLowPass.process` --
    # JIT-compiled with numba the same way, numerically verified identical.
    n = int(sig.shape[0])
    sr = max(1, int(sample_rate))
    dt = 1.0 / float(sr)
    ta = max(5e-4, float(attack_ms) / 1000.0)
    tr = max(5e-4, float(release_ms) / 1000.0)
    aa = float(np.exp(-dt / ta))
    ar = float(np.exp(-dt / tr))
    s32 = sig.astype(np.float32, copy=False)

    if _NUMBA_AVAILABLE:
        return _envelope_follower_loop_nb(s32, aa, ar)

    out = np.empty(n, dtype=np.float32)
    env = 0.0
    for i in range(n):
        x = float(abs(s32[i]))
        if x > env:
            env = aa * env + (1.0 - aa) * x
        else:
            env = ar * env + (1.0 - ar) * x
        out[i] = env
    return out


def synthesize_kick_four_four(
    bar_samples: int,
    sample_rate: int,
    *,
    beats_per_bar: int = 4,
    level: float = 0.32,
    pulse_ms: float = 14.0,
) -> np.ndarray:
    """Mono kick: one short pulse per beat (4/4)."""
    n = int(max(0, bar_samples))
    out = np.zeros(n, dtype=np.float32)
    if n <= 0:
        return out
    bpb = max(1, int(beats_per_bar))
    sr = max(1, int(sample_rate))
    pulse_len = max(3, int(float(pulse_ms) * sr / 1000.0))
    amp = float(max(0.0, level))
    period = float(n) / float(bpb)
    phase_scale = 2.0 * np.pi * 58.0 / float(sr)
    for b in range(bpb):
        start = int(round(b * period))
        if start >= n:
            break
        lim = min(pulse_len, n - start)
        for k in range(lim):
            t = float(k) / float(max(1, pulse_len - 1))
            atk = float(np.sin(0.5 * np.pi * min(1.0, (1.0 - t) * 6.0)) ** 2) if k < max(1, pulse_len // 3) else float((1.0 - t) ** 2.2)
            ph = phase_scale * float(k) * (1.0 + 0.35 * t)
            body = float(np.sin(ph)) * atk
            click = 0.18 * float(np.exp(-float(k) * 18.0 / float(max(6, pulse_len))))
            out[start + k] += amp * float(body + click)
    return out


def kick_four_four_from_one_shot(
    one_shot: np.ndarray,
    bar_samples: int,
    *,
    beats_per_bar: int = 4,
    level: float = 0.32,
) -> np.ndarray:
    """Place mono one-shot at each beat (4/4 by default); overlaps sum."""
    n = int(max(0, bar_samples))
    out = np.zeros(n, dtype=np.float32)
    shot = np.asarray(one_shot, dtype=np.float32).reshape(-1)
    if n <= 0 or shot.size <= 0:
        return out
    bpb = max(1, int(beats_per_bar))
    amp = float(max(0.0, level))
    period = float(n) / float(bpb)
    klen = int(shot.shape[0])
    for b in range(bpb):
        start = int(round(b * period))
        if start >= n:
            break
        end = min(n, start + klen)
        seg_len = end - start
        if seg_len <= 0:
            continue
        out[start:end] += shot[:seg_len] * np.float32(amp)
    return out


def _dbfs_to_linear(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def duck_gain_from_kick(
    kick: np.ndarray,
    sample_rate: int,
    *,
    attack_ms: float,
    release_ms: float,
    threshold_db: float,
    max_depth: float,
) -> np.ndarray:
    """
    Per-sample linear gain in (0, 1] applied to non-drone stems. ``threshold_db`` is
    interpreted relative to the bar's peak kick envelope (same shape as a dBFS-style
    floor on a normalized detector).
    """
    env = _envelope_follower_abs_mono(kick, sample_rate, attack_ms, release_ms)
    peak = float(np.max(env)) + 1e-12
    thr = _dbfs_to_linear(threshold_db) * peak
    excess = np.maximum(env.astype(np.float64) - thr, 0.0) / (peak - thr + 1e-12)
    excess = np.clip(excess, 0.0, 1.0).astype(np.float32)
    depth = float(np.clip(max_depth, 0.0, 0.95))
    return np.clip(1.0 - depth * excess, 0.05, 1.0).astype(np.float32)


def _build_kick_mono_bar(
    *,
    bar_samples: int,
    sample_rate: int,
    bpb: int,
    k_level: float,
    pulse_ms: float,
    sidechain_cfg: Any,
) -> np.ndarray:
    try:
        use_file = bool(getattr(sidechain_cfg, "sample_enabled", False))
    except Exception:
        use_file = False

    if use_file:
        try:
            raw_path = str(getattr(sidechain_cfg, "sample_path", "") or "").strip()
        except Exception:
            raw_path = ""
        try:
            max_ms = float(getattr(sidechain_cfg, "sample_max_ms", 450.0) or 450.0)
        except Exception:
            max_ms = 450.0
        if raw_path:
            path = resolve_chorus_kick_sample_path(raw_path)
            shot = load_chorus_kick_one_shot_mono(path, int(sample_rate), max_ms)
            if shot is not None and int(shot.shape[0]) > 0:
                return kick_four_four_from_one_shot(
                    shot,
                    int(bar_samples),
                    beats_per_bar=bpb,
                    level=k_level,
                )

    return synthesize_kick_four_four(
        int(bar_samples),
        int(sample_rate),
        beats_per_bar=bpb,
        level=k_level,
        pulse_ms=pulse_ms,
    )


def apply_chorus_kick_sidechain(
    channel_audio: Dict[int, np.ndarray],
    *,
    sample_rate: int,
    bar_samples: int,
    sidechain_cfg: Any,
) -> None:
    """
    Ducks non-drone / non-kick channels in-place and writes the kick stem to the kick
    mixer strip (``mixer_channel``), same path as MIDI channels through ``mix_audio``.
    """
    if bar_samples <= 0:
        return
    try:
        on = bool(getattr(sidechain_cfg, "enabled", False))
    except Exception:
        on = False
    if not on:
        return
    try:
        kick_on = bool(getattr(sidechain_cfg, "kick_enabled", True))
    except Exception:
        kick_on = True
    try:
        duck_on = bool(getattr(sidechain_cfg, "sidechain_enabled", True))
    except Exception:
        duck_on = True
    if not kick_on and not duck_on:
        return

    try:
        bpb = int(getattr(sidechain_cfg, "beats_per_bar", 4) or 4)
    except Exception:
        bpb = 4
    bpb = max(1, min(16, bpb))

    try:
        k_level = float(getattr(sidechain_cfg, "kick_level_linear", 0.32) or 0.32)
    except Exception:
        k_level = 0.32
    try:
        pulse_ms = float(getattr(sidechain_cfg, "kick_pulse_ms", 14.0) or 14.0)
    except Exception:
        pulse_ms = 14.0

    try:
        atk = float(getattr(sidechain_cfg, "attack_ms", 1.0) or 1.0)
        rel = float(getattr(sidechain_cfg, "release_ms", 28.0) or 28.0)
        thr_db = float(getattr(sidechain_cfg, "threshold_db", -32.0) or -32.0)
        depth = float(getattr(sidechain_cfg, "max_depth", 0.52) or 0.52)
    except Exception:
        atk, rel, thr_db, depth = 1.0, 28.0, -32.0, 0.52

    try:
        drone_ch = int(getattr(sidechain_cfg, "drone_channel", 4) or 4)
    except Exception:
        drone_ch = 4
    try:
        kick_ch = int(getattr(sidechain_cfg, "mixer_channel", KICK_MIXER_CHANNEL_INDEX) or KICK_MIXER_CHANNEL_INDEX)
    except Exception:
        kick_ch = int(KICK_MIXER_CHANNEL_INDEX)

    kick = _build_kick_mono_bar(
        bar_samples=int(bar_samples),
        sample_rate=int(sample_rate),
        bpb=bpb,
        k_level=k_level,
        pulse_ms=pulse_ms,
        sidechain_cfg=sidechain_cfg,
    )
    gain = None
    if duck_on:
        gain = duck_gain_from_kick(
            kick,
            int(sample_rate),
            attack_ms=atk,
            release_ms=rel,
            threshold_db=thr_db,
            max_depth=depth,
        )

    try:
        cm_relief = float(getattr(sidechain_cfg, "counter_melody_sidechain_relief", 0.0) or 0.0)
    except Exception:
        cm_relief = 0.0
    cm_relief = float(max(0.0, min(1.0, cm_relief)))

    n = int(bar_samples)
    if duck_on and gain is not None:
        for ch, buf in list(channel_audio.items()):
            try:
                ci = int(ch)
            except Exception:
                continue
            if ci == int(drone_ch) or ci == int(kick_ch):
                continue
            if buf is None or getattr(buf, "ndim", 0) != 2:
                continue
            if int(buf.shape[0]) != n:
                continue
            duck = gain
            if cm_relief > 1e-9 and ci == int(_COUNTER_MELODY_CH):
                # Blend duck curve toward unity so counter survives kick pumping.
                duck = gain.astype(np.float64, copy=False) + (1.0 - gain.astype(np.float64, copy=False)) * cm_relief
                duck = duck.astype(np.float32, copy=False)
            buf[:, 0] *= duck
            buf[:, 1] *= duck

    if kick_on:
        kb = channel_audio.get(int(kick_ch))
        if kb is not None and getattr(kb, "ndim", 0) == 2 and int(kb.shape[0]) == n:
            k32 = kick.astype(np.float32, copy=False)
            kb[:, 0] = k32
            kb[:, 1] = k32


def should_apply_chorus_kick_sidechain(*, arrangement_role: str, sidechain_cfg: Any) -> bool:
    role = str(arrangement_role or "").strip().lower()
    if not role:
        return False
    try:
        if not bool(getattr(sidechain_cfg, "enabled", False)):
            return False
    except Exception:
        return False
    try:
        kick_on = bool(getattr(sidechain_cfg, "kick_enabled", True))
    except Exception:
        kick_on = True
    try:
        duck_on = bool(getattr(sidechain_cfg, "sidechain_enabled", True))
    except Exception:
        duck_on = True
    if not kick_on and not duck_on:
        return False
    roles = parse_chorus_roles(getattr(sidechain_cfg, "roles", ("b", "chorus", "hook", "tag")))
    return role in roles
