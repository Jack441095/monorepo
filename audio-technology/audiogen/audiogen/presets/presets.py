from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


def _preset_dir() -> Path:
    # Keep presets writable in sandbox/dev by default (repo-local).
    # Users can override via AUDIOGEN_PRESET_DIR.
    env = str(os.environ.get("AUDIOGEN_PRESET_DIR", "") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / ".audiogen" / "presets"


@dataclass(frozen=True)
class PresetV1:
    """
    Versioned local preset.

    Keep this small: it is a user-facing contract, even in standalone mode.
    """

    version: int = 1
    name: str = "unnamed"

    # Layers
    sample_pack: str = "default"
    style_profile: str = "default"
    conversation_preset: str = "default_ambient_01"
    fx_preset: str = "default"
    arrangement_style: str = "default"  # arranged_song_mode

    # Macros: normalized 0..1
    macros: Dict[str, float] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["macros"] = dict(self.macros or {})
        d["metadata"] = dict(self.metadata or {})
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PresetV1":
        return cls(
            version=int(d.get("version", 1) or 1),
            name=str(d.get("name", "unnamed") or "unnamed"),
            sample_pack=str(d.get("sample_pack", "default") or "default"),
            style_profile=str(d.get("style_profile", "default") or "default"),
            conversation_preset=str(d.get("conversation_preset", "default_ambient_01") or "default_ambient_01"),
            fx_preset=str(d.get("fx_preset", "default") or "default"),
            arrangement_style=str(d.get("arrangement_style", "default") or "default"),
            macros={str(k): float(v) for k, v in (d.get("macros", {}) or {}).items()},
            metadata=dict(d.get("metadata", {}) or {}),
        )


def migrate_preset(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migration pipeline (V1 only for now).
    Returns a dict compatible with PresetV1.from_dict.
    """

    v = int(d.get("version", 1) or 1)
    if v == 1:
        return dict(d)
    # Unknown future versions: best-effort downcast by stripping unknown keys.
    out = dict(d)
    out["version"] = 1
    return out


def list_presets() -> List[str]:
    p = _preset_dir()
    if not p.exists():
        return []
    return sorted(x.stem for x in p.glob("*.json") if x.is_file())


def load_preset(name: str) -> PresetV1:
    p = _preset_dir() / f"{name}.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw = migrate_preset(dict(raw))
    return PresetV1.from_dict(raw)


def save_preset(preset: PresetV1) -> Path:
    pdir = _preset_dir()
    pdir.mkdir(parents=True, exist_ok=True)
    out = pdir / f"{preset.name}.json"
    out.write_text(json.dumps(preset.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return out

