#!/usr/bin/env python3
"""Build read-only physical definition cards for a label manifest.

The cards describe measurable signal properties only. They do not create a
semantic label, alter the blind label manifest, or modify source audio. The
worker is a real module entry point so this remains compatible with macOS's
``spawn`` multiprocessing start method.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
CARD_MODULE = SCRIPT_DIR / "audio_definition_card.py"


def _load_card_module():
    spec = importlib.util.spec_from_file_location("slo_audio_definition_card", CARD_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CARD_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analyse_one(item: tuple[int, str]) -> dict[str, Any]:
    queue_id, path = item
    try:
        card = _load_card_module().analyse_file(path)
        card["queue_id"] = queue_id
        return {"ok": True, "card": card}
    except Exception as exc:  # keep one unreadable file from losing the batch
        return {"ok": False, "queue_id": queue_id, "path": path, "error": str(exc)}


def build(manifest_path: Path, out_path: Path, workers: int) -> dict[str, Any]:
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest must be a non-empty JSON list")
    paths: list[tuple[int, str]] = []
    seen: set[str] = set()
    for expected_id, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("id") != expected_id:
            raise ValueError("manifest ids must be contiguous and deterministic")
        path = str(row.get("path", ""))
        if not Path(path).is_absolute() or path in seen:
            raise ValueError(f"manifest path is missing, relative, or duplicated: {path}")
        seen.add(path)
        paths.append((expected_id, path))

    results: list[dict[str, Any]] = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=max(1, workers)) as pool:
        for result in pool.imap(analyse_one, paths, chunksize=2):
            results.append(result)

    cards = [result["card"] for result in results if result.get("ok")]
    errors = [{k: result[k] for k in ("queue_id", "path", "error")}
              for result in results if not result.get("ok")]
    payload = {
        "record_type": "slo_label_queue_audio_definition_cards",
        "schema_version": "1.0.0",
        "feature_version": "audio_definition_card_v1",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_manifest": str(manifest_path.resolve()),
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "n_requested": len(paths),
        "n_cards": len(cards),
        "n_errors": len(errors),
        "safety": {
            "read_only": True,
            "source_files_modified": False,
            "semantic_labels_created": False,
            "rename_actions": False,
        },
        "cards": cards,
        "errors": errors,
    }
    if out_path.exists():
        raise ValueError(f"refusing to overwrite existing output: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=float) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    result = build(args.manifest, args.out, args.workers)
    print(json.dumps({k: result[k] for k in ("n_requested", "n_cards", "n_errors")}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
