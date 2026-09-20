from __future__ import annotations

import json
from pathlib import Path


DEFAULT_MIX_GOAL = "premaster"
MIX_GOALS = {
    "premaster": {
        "label": "Premaster",
        "description": "A mix export before mastering, judged for headroom, balance, dynamics, and translation.",
        "target": "Leave headroom, avoid clipping, keep the centre image stable, and make broad tonal decisions against a reference.",
    },
    "club": {
        "label": "Club / electronic",
        "description": "Bass-forward electronic music where low-end translation, punch, and mono safety matter.",
        "target": "Keep kick and bass powerful but controlled, preserve punch, and keep sub/bass mostly mono.",
    },
    "pop_vocal": {
        "label": "Pop vocal",
        "description": "A vocal-led production where intelligibility, brightness control, and depth are priorities.",
        "target": "Keep the vocal present without harshness, avoid low-mid masking, and check effects depth.",
    },
    "rap_vocal": {
        "label": "Rap vocal",
        "description": "A vocal-forward mix where the lead needs to stay clear over dense drums and bass.",
        "target": "Protect lyric clarity, control sibilance, and keep kick/bass from masking the vocal body.",
    },
    "podcast": {
        "label": "Podcast / dialogue",
        "description": "Speech material judged for clarity, consistency, noise, and listener comfort.",
        "target": "Prioritise even loudness, clear presence, low noise, and no harsh S/T consonants.",
    },
    "game_audio": {
        "label": "Game audio",
        "description": "Interactive or implementation-ready audio judged for headroom and playback translation.",
        "target": "Keep export headroom, avoid clipping, control low-end buildup, and ensure consistent playback level.",
    },
    "master": {
        "label": "Master",
        "description": "A finished master checked for loudness, true peak, translation, and tonal balance.",
        "target": "Check true peak safety, integrated loudness, tonal translation, and whether limiting is damaging punch.",
    },
}

GOAL_TARGETS = {
    "premaster": {
        "summary": "Premaster checks favour headroom, translation, and enough dynamics for mastering.",
        "checks": [
            {"label": "Peak headroom", "metric": "peak_dbfs", "max": -1.0, "target": "Peak at or below -1 dBFS", "education": "Premasters need space for mastering moves and delivery encoding."},
            {"label": "True peak safety", "metric": "true_peak_dbfs", "max": -1.0, "target": "True peak at or below -1 dBFS", "education": "Inter-sample peaks can clip even when sample peaks look safe."},
            {"label": "Useful dynamics", "metric": "crest_factor_db", "min": 7.0, "target": "Crest factor above 7 dB", "education": "Some punch left in the mix gives mastering more room to work."},
            {"label": "Low-end proportion", "path": ("tonal_balance", "low_end_share"), "max": 0.52, "target": "Low end below 52% of broad energy", "education": "Too much low end can make a premaster feel loud but small."},
            {"label": "Stereo stability", "metric": "stereo_correlation", "min": 0.2, "target": "Correlation above 0.20", "education": "Important mix elements should survive mono playback."},
            {"label": "Loudness range", "metric": "loudness_range_lu", "min": 5.0, "max": 18.0, "target": "LRA between 5-18 LU", "education": "Premasters should preserve dynamic contrast so the mastering engineer has room to shape the final loudness."},
        ],
    },
    "club": {
        "summary": "Club/electronic checks prioritise controlled bass power, punch, and mono-safe low end.",
        "checks": [
            {"label": "Club low-end weight", "path": ("tonal_balance", "low_end_share"), "min": 0.16, "max": 0.62, "target": "Low end around 16-62%", "education": "Dance mixes can be bass-forward, but the low end still needs control."},
            {"label": "Low-end mono safety", "path": ("stereo_field", "low_side_share"), "max": 0.08, "target": "Sub/bass side energy below 8%", "education": "Club playback usually rewards centred kick and bass foundations."},
            {"label": "Low-band phase", "path": ("stereo_field", "low_band_correlation"), "min": 0.55, "target": "Low-band correlation above 0.55", "education": "Phasey low end can lose weight when summed or played on large systems."},
            {"label": "Punch reserve", "metric": "crest_factor_db", "min": 5.5, "target": "Crest factor above 5.5 dB", "education": "A loud electronic mix still needs enough transient shape to hit."},
            {"label": "Loudness range", "metric": "loudness_range_lu", "min": 4.0, "max": 10.0, "target": "LRA between 4-10 LU", "education": "Club tracks are typically compressed but should still breathe between breakdown and drop."},
        ],
    },
    "pop_vocal": {
        "summary": "Pop vocal checks focus on intelligibility, low-mid masking, and comfortable brightness.",
        "checks": [
            {"label": "Vocal clarity band", "path": ("tonal_balance", "clarity_share"), "min": 0.06, "target": "Presence/air above 6%", "education": "A vocal-led mix needs enough upper-mid information to read at low volume."},
            {"label": "Low-mid masking", "path": ("bands", "low_mids"), "max": 0.34, "target": "Low mids below 34%", "education": "Dense low mids can hide lyric detail and make reverbs feel cloudy."},
            {"label": "Harshness guard", "path": ("tonal_balance", "perceived_clarity_share"), "max": 0.58, "target": "Ear-weighted clarity below 58%", "education": "Brightness should help the vocal speak without making S/T sounds painful."},
            {"label": "Lead translation", "metric": "stereo_correlation", "min": 0.2, "target": "Correlation above 0.20", "education": "A vocal can be wide around the edges, but the lead should stay anchored."},
            {"label": "Loudness range", "metric": "loudness_range_lu", "min": 4.0, "max": 12.0, "target": "LRA between 4-12 LU", "education": "Pop mixes need enough dynamic lift between verse and chorus to stay interesting."},
        ],
    },
    "rap_vocal": {
        "summary": "Rap vocal checks protect lyric focus against dense drums and bass.",
        "checks": [
            {"label": "Lyric clarity band", "path": ("tonal_balance", "clarity_share"), "min": 0.05, "target": "Presence/air above 5%", "education": "Fast vocals need enough edge to stay intelligible over drums."},
            {"label": "Bass masking", "path": ("tonal_balance", "low_end_share"), "max": 0.56, "target": "Low end below 56%", "education": "Kick and 808 energy can mask vocal body when the balance is too low-heavy."},
            {"label": "Low-mid room", "path": ("bands", "low_mids"), "max": 0.36, "target": "Low mids below 36%", "education": "The vocal body needs room around the lower mids without becoming boxy."},
            {"label": "Punch reserve", "metric": "crest_factor_db", "min": 5.0, "target": "Crest factor above 5 dB", "education": "Rap mixes often work loud, but the drum pocket still needs impact."},
        ],
    },
    "podcast": {
        "summary": "Podcast/dialogue checks prioritise stable level, speech clarity, and listener comfort.",
        "checks": [
            {"label": "Consistent level", "path": ("dynamic_profile", "section_range_db"), "max": 8.0, "target": "Section range below 8 dB", "education": "Speech should not force the listener to keep adjusting volume."},
            {"label": "Speech clarity", "path": ("tonal_balance", "clarity_share"), "min": 0.04, "target": "Presence/air above 4%", "education": "Clear consonants help speech translate on phones and laptops."},
            {"label": "Low rumble control", "path": ("tonal_balance", "low_end_share"), "max": 0.38, "target": "Low end below 38%", "education": "Rumble and plosives eat headroom and make dialogue feel muddy."},
            {"label": "Peak safety", "metric": "peak_dbfs", "max": -1.0, "target": "Peak at or below -1 dBFS", "education": "Speech exports still need room for platform encoding."},
            {"label": "Loudness range", "metric": "loudness_range_lu", "min": 3.0, "max": 8.0, "target": "LRA between 3-8 LU", "education": "Podcast audio should be consistent in level so listeners can follow without adjusting volume."},
        ],
    },
    "game_audio": {
        "summary": "Game audio checks favour implementation headroom, reliable playback, and repeatable loudness.",
        "checks": [
            {"label": "Implementation headroom", "metric": "true_peak_dbfs", "max": -1.0, "target": "True peak at or below -1 dBFS", "education": "Interactive playback can stack sounds, so assets need safe headroom."},
            {"label": "Playback consistency", "path": ("dynamic_profile", "section_range_db"), "max": 10.0, "target": "Section range below 10 dB", "education": "Game assets should remain usable across varied playback contexts."},
            {"label": "Low-end control", "path": ("tonal_balance", "low_end_share"), "max": 0.55, "target": "Low end below 55%", "education": "Low-frequency build-up multiplies quickly when several assets play together."},
            {"label": "Mono compatibility", "metric": "stereo_correlation", "min": 0.2, "target": "Correlation above 0.20", "education": "Game audio often reaches mono, phone, TV, and headset playback paths."},
        ],
    },
    "master": {
        "summary": "Master checks focus on delivery safety, loudness damage, and final translation.",
        "checks": [
            {"label": "True peak ceiling", "metric": "true_peak_dbfs", "max": -0.3, "target": "True peak at or below -0.3 dBFS", "education": "A safer ceiling reduces codec and platform clipping risk."},
            {"label": "No clipping", "metric": "clipped_frames_estimate", "max": 0, "target": "No clipped frames", "education": "A finished master should not rely on accidental digital clipping."},
            {"label": "Punch after limiting", "metric": "crest_factor_db", "min": 4.0, "target": "Crest factor above 4 dB", "education": "Very low crest factor can mean limiting is flattening the music."},
            {"label": "Stereo stability", "metric": "stereo_correlation", "min": 0.1, "target": "Correlation above 0.10", "education": "Wide masters still need a stable image and mono compatibility."},
        ],
    },
}


def normalize_mix_goal(value: str) -> str:
    goal = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "electronic": "club",
        "club_electronic": "club",
        "pop": "pop_vocal",
        "vocal": "pop_vocal",
        "rap": "rap_vocal",
        "dialogue": "podcast",
        "dialog": "podcast",
        "speech": "podcast",
        "game": "game_audio",
    }
    goal = aliases.get(goal, goal)
    return goal if goal in MIX_GOALS else DEFAULT_MIX_GOAL


def mix_goal_info(value: str) -> dict:
    key = normalize_mix_goal(value)
    return {"key": key, **MIX_GOALS[key]}


def normalize_target_check(spec: dict) -> dict | None:
    if not isinstance(spec, dict):
        return None
    label = str(spec.get("label") or "").strip()
    target = str(spec.get("target") or "").strip()
    education = str(spec.get("education") or "").strip()
    metric = str(spec.get("metric") or "").strip()
    path = spec.get("path")
    if isinstance(path, str):
        path = [part.strip() for part in path.split(".") if part.strip()]
    if not label or (not metric and not path):
        return None
    normalized: dict = {
        "label": label,
        "target": target,
        "education": education,
    }
    if metric:
        normalized["metric"] = metric
    elif isinstance(path, list) and all(isinstance(part, str) and part for part in path):
        normalized["path"] = path
    else:
        return None
    for key in ("min", "max"):
        if key in spec and spec[key] not in {None, ""}:
            try:
                normalized[key] = float(spec[key])
            except (TypeError, ValueError):
                return None
    return normalized


def validated_goal_targets(raw: dict) -> dict:
    targets = {
        key: {
            "summary": str(value.get("summary", "")),
            "checks": [dict(check) for check in value.get("checks", []) if isinstance(check, dict)],
        }
        for key, value in GOAL_TARGETS.items()
    }
    goals = raw.get("goals", raw) if isinstance(raw, dict) else {}
    if not isinstance(goals, dict):
        return targets
    for key in MIX_GOALS:
        config = goals.get(key)
        if not isinstance(config, dict):
            continue
        summary = str(config.get("summary") or targets[key].get("summary") or "")
        checks = [check for check in (normalize_target_check(item) for item in config.get("checks", [])) if check]
        if checks:
            targets[key] = {"summary": summary, "checks": checks}
        else:
            targets[key]["summary"] = summary
    return targets


def load_goal_targets(path: Path) -> dict:
    config_path = path
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return validated_goal_targets({})
    return validated_goal_targets(raw)


def get_mix_review_targets(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"goals": load_goal_targets(path)}


def save_mix_review_targets(targets: dict, *, path: Path) -> dict:
    try:
        # Validate first to make sure structure is sane
        validated = validated_goal_targets(targets)
        # Write back to file formatted
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "goals": validated}, indent=2) + "\n", encoding="utf-8")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

