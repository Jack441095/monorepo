"""What is installed on this Mac, read from disk, so advice can name devices the producer actually has.

Built-in devices come from the Live app's own device folders, saved racks from the User Library, packs from Live's
Factory Packs folder, and third-party plug-ins from the standard VST3 / Audio Unit / VST folders. Only names are read,
nothing is loaded, and nothing leaves the machine. A plug-in's category is a guess from its name, and the answer says so.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from kenn.core import live_setup

CATEGORY_DIRS = ("Instruments", "Audio Effects", "MIDI Effects")
PLUGIN_DIRS = (("VST3", "Library/Audio/Plug-Ins/VST3", ".vst3"), ("Audio Unit", "Library/Audio/Plug-Ins/Components", ".component"),
               ("VST", "Library/Audio/Plug-Ins/VST", ".vst"))
CACHE_SECONDS = 600
MAX_RACKS = 200

# What a producer asks about, and the words that put a device name in that group.
CATEGORIES: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {
    "eq": (re.compile(r"\b(?:eq|equali[sz]er|equali[sz]ation|equali[sz]e)\b", re.I),
           re.compile(r"\beq\b|equali[sz]er|filter|pro-?q\b", re.I)),
    "compressor": (re.compile(r"\b(?:compress\w*|glue|sidechain|dynamics)\b", re.I),
                   re.compile(r"compress|\bglue\b|dynamics|\bcomp\b|squash", re.I)),
    "limiter": (re.compile(r"\blimit\w*\b", re.I), re.compile(r"limit|maxim", re.I)),
    "reverb": (re.compile(r"\b(?:reverb\w*|verb)\b", re.I), re.compile(r"reverb|verb\b|convolution|space|room|hall", re.I)),
    "delay": (re.compile(r"\b(?:delay\w*|echo\w*)\b", re.I), re.compile(r"delay|echo", re.I)),
    "saturation": (re.compile(r"\b(?:saturat\w*|distort\w*|overdrive|warmth|crunch)\b", re.I),
                   re.compile(r"saturat|distort|overdrive|roar|drum buss|pedal|tape|tube|drive", re.I)),
}

_cache: dict[str, Any] = {"at": 0.0, "value": None}


def _names(folder: Path, suffixes: tuple[str, ...], depth: int = 1) -> list[str]:
    found: set[str] = set()
    if not folder.is_dir():
        return []
    for entry in folder.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.suffix.lower() in suffixes:
            found.add(entry.stem)
        elif entry.is_dir() and depth > 0 and not entry.suffix:
            found.update(_names(entry, suffixes, depth - 1))
    return sorted(found)


def builtin_devices(app: Path) -> list[str]:
    resources = app / "Contents" / "App-Resources"
    names: set[str] = set()
    for category in CATEGORY_DIRS:
        for base in ("Builtin/Devices", "Core Library/Devices"):
            folder = resources / base / category
            if folder.is_dir():
                for entry in folder.iterdir():
                    name = entry.name.replace(".adv", "").replace(".amxd", "")
                    if not name.startswith(".") and name not in {"Ableton Folder Info", "Legacy"} and not name.startswith("Max "):
                        names.add(name)
    return sorted(names)


def scan(*, applications: Path = Path("/Applications"), home: Path | None = None, library: Path | None = None,
         system_root: Path = Path("/")) -> dict[str, Any]:
    home = home or Path.home()
    apps = live_setup.live_apps(applications)
    library = library or live_setup.user_library(home=home)
    plugins = []
    for label, relative, suffix in PLUGIN_DIRS:
        for root in (system_root / relative, home / relative):
            plugins += [{"name": name, "format": label} for name in _names(root, (suffix,), depth=0)]
    packs_root = library.parent / "Factory Packs"
    return {
        "live": apps[-1].name.removesuffix(".app") if apps else "",
        "builtin": builtin_devices(apps[-1]) if apps else [],
        "racks": _names(library / "Presets" / "Audio Effects", (".adg", ".adv"), depth=2)[:MAX_RACKS],
        "packs": sorted(p.name for p in packs_root.iterdir() if p.is_dir() and not p.name.startswith(".")) if packs_root.is_dir() else [],
        "plugins": sorted({(p["name"], p["format"]): p for p in plugins}.values(), key=lambda p: (p["name"].casefold(), p["format"])),
    }


def inventory(*, refresh: bool = False, **paths: Any) -> dict[str, Any]:
    """The scan, kept for ten minutes (plug-in folders can hold hundreds of entries)."""
    if paths or refresh or _cache["value"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
        value = scan(**paths)
        if paths:
            return value
        _cache.update(at=time.time(), value=value)
    return _cache["value"]


def categories_in(question: str) -> list[str]:
    return [name for name, (asked, _named) in CATEGORIES.items() if asked.search(question or "")]


def _cap(names: list[str], limit: int = 6) -> str:
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def your_set_note(question: str, installed: dict[str, Any], session: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A short factual line about what the producer has for the kind of device they asked about, or None."""
    wanted = categories_in(question)
    if not wanted or not (installed.get("builtin") or installed.get("plugins")):
        return None
    matches = lambda name: any(CATEGORIES[c][1].search(name) for c in wanted)  # noqa: E731
    builtin = [n for n in installed.get("builtin", []) if matches(n)]
    racks = [n for n in installed.get("racks", []) if matches(n)]
    plugins = [f"{p['name']} ({p['format']})" for p in installed.get("plugins", []) if matches(p["name"])]
    on_tracks = []
    for track in (session or {}).get("tracks") or []:
        for device in track.get("devices") or []:
            name = str(device.get("name") or "")
            if name and matches(name):
                on_tracks.append(f"{name} on {track.get('name')}")
    parts = []
    if builtin:
        parts.append(f"built into {installed.get('live') or 'Live'}: {_cap(builtin)}")
    if plugins:
        parts.append(f"plug-ins whose names match: {_cap(plugins)}")
    if racks:
        parts.append(f"your saved racks: {_cap(racks)}")
    if on_tracks:
        parts.append(f"already on your tracks: {_cap(on_tracks)}")
    if not parts:
        return None
    return {"line": "In your Live, " + "; ".join(parts) + ".", "categories": wanted, "evidence_class": "observed_session_fact",
            "builtin": builtin, "plugins": plugins, "racks": racks, "on_tracks": on_tracks}
