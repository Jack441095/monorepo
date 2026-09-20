"""Deterministic, dependency-free serialization + JSON Schema derivation.

Rules:
- enums serialize as their string values
- tuples serialize as JSON arrays
- dict keys are sorted for deterministic output
- None fields are preserved (callers may strip them)
- no arbitrary objects are serialized (ValueError on unsupported types)
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, get_args, get_origin, get_type_hints


def dataclass_to_dict(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, enum.Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: dataclass_to_dict(getattr(obj, f.name))
            for f in sorted(dataclasses.fields(obj), key=lambda f: f.name)
        }
    if isinstance(obj, (list, tuple)):
        return [dataclass_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): dataclass_to_dict(v) for k, v in sorted(obj.items())}
    raise ValueError(f"Cannot deterministically serialize object of type {type(obj)!r}")


_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def json_schema_for(cls: type) -> dict:
    """Derive a minimal JSON Schema from a (frozen) dataclass."""
    if not dataclasses.is_dataclass(cls) or not isinstance(cls, type):
        raise TypeError("json_schema_for expects a dataclass")
    hints = get_type_hints(cls)
    props: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        props[f.name] = _schema_for(hints[f.name])
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = sorted(required)
    return schema


def _schema_for(tp: Any) -> dict:
    if tp is None:
        return {}
    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}
    origin = get_origin(tp)
    if origin is None and isinstance(tp, type) and issubclass(tp, enum.Enum):
        return {"type": "string", "enum": [m.value for m in tp]}
    args = [a for a in get_args(tp) if a is not type(None)]
    if origin in (list, tuple):
        item = args[0] if args else Any
        return {"type": "array", "items": _schema_for(item)}
    if origin is dict:
        return {"type": "object"}
    if args:  # Optional[X] / unions — permissive for now
        subs = [_schema_for(a) for a in args]
        return {"anyOf": subs} if len(subs) > 1 else subs[0]
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return json_schema_for(tp)
    return {}


__all__ = ["dataclass_to_dict", "json_schema_for"]
