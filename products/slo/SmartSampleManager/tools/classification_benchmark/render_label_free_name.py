#!/usr/bin/env python3
"""Render review-only structured filename candidates from label-free evidence.

This renderer composes a human-readable candidate name from an ensemble
suggestion and optional physical definition card. It does not write metadata,
rename files, or promote a semantic label; every output remains a review
candidate with explicit provenance and safety fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


VERSION = "label_free_name_renderer_v1"
FORM_MAP = {
    "possibly_one_shot": "one-shot",
    "possibly_loop": "loop",
    "possibly_sustained": "sustained",
    "possibly_ambience_or_sustain": "ambience-sustain",
}
ATTRIBUTE_ORDER = (
    "low_end_heavy", "bright", "dark", "tonal_or_harmonic",
    "noisy_or_inharmonic", "transient_dense", "mostly_mono",
    "wide_or_decorrelated",
)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", str(value).strip().lower()).strip("-")
    return value or "unknown"


def _load_jsonl(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("ensemble receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") != "slo_label_free_ensemble_receipt":
        raise ValueError("input is not a label-free ensemble receipt")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("ensemble receipt is not read-only")
    rows: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("ensemble row has no path")
        if row["path"] in rows:
            raise ValueError(f"duplicate ensemble path: {row['path']}")
        if row.get("semantic_label") is not None:
            raise ValueError("ensemble receipt contains semantic labels")
        rows[row["path"]] = row
    return header, rows


def _load_cards(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") not in {
        "slo_audio_definition_cards",
        "slo_label_queue_audio_definition_cards",
        "slo_label_free_physical_cards",
    }:
        raise ValueError("physical evidence is not a definition-card payload")
    safety = payload.get("safety") or {}
    if safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("physical evidence payload is not read-only")
    cards: dict[str, dict[str, Any]] = {}
    for card in payload.get("cards", []):
        if not isinstance(card, dict) or not card.get("path"):
            continue
        path_value = str(Path(card["path"]).resolve())
        if path_value in cards:
            raise ValueError(f"duplicate definition card path: {path_value}")
        cards[path_value] = card
    return cards


def _candidate(row: dict[str, Any], card: dict[str, Any] | None) -> dict[str, Any]:
    path = str(row["path"])
    source_hash = row.get("content_sha256") or hashlib.sha256(path.encode()).hexdigest()
    label = row.get("ensemble_suggestion")
    if not label:
        alternatives = [str(value) for value in
                        (row.get("model_a_suggestion"), row.get("model_b_suggestion"))
                        if value]
        if len(alternatives) == 2 and alternatives[0] != alternatives[1]:
            label = f"{alternatives[0]}-or-{alternatives[1]}"
    fields: dict[str, Any] = {
        "family_or_role": label,
        "form": None,
        "pitch_hz": None,
        "attributes": [],
    }
    evidence: dict[str, Any] = {
        "ensemble_suggestion": label,
        "model_agreement": row.get("model_agreement"),
        "model_a_score": row.get("model_a_score"),
        "model_b_score": row.get("model_b_score"),
        "model_a_margin": row.get("model_a_margin"),
        "model_b_margin": row.get("model_b_margin"),
    }
    if card:
        temporal = card.get("temporal") or {}
        fields["form"] = FORM_MAP.get(str(temporal.get("form_hint")))
        pitch = card.get("pitch") or {}
        voiced = pitch.get("voiced_frame_fraction")
        if isinstance(pitch.get("median_f0_hz"), (int, float)) and isinstance(voiced, (int, float)) and voiced >= 0.6:
            fields["pitch_hz"] = round(float(pitch["median_f0_hz"]), 1)
        tags = set(card.get("heuristic_tags") or [])
        fields["attributes"] = [tag for tag in ATTRIBUTE_ORDER if tag in tags]
        evidence["physical_feature_version"] = card.get("feature_version")
        evidence["heuristic_tags"] = sorted(tags)
        evidence["uncertainty_reasons"] = card.get("uncertainty_reasons", [])
    state_prefix = ["review"] if row.get("status") != "suggest" else []
    tokens = [*state_prefix, _slug(label or "review"),
              *([_slug(fields["form"])] if fields["form"] else [])]
    tokens.extend(_slug(tag) for tag in fields["attributes"])
    if fields["pitch_hz"] is not None:
        tokens.append(f"f0-{fields['pitch_hz']:g}hz")
    tokens.append(f"id-{str(source_hash)[:8]}")
    extension = Path(path).suffix.lower() or ".wav"
    return {
        "path": path,
        "semantic_label": None,
        "name_state": "suggested_review_required" if row.get("status") == "suggest" else "review_required",
        "candidate_filename": "_".join(tokens) + extension,
        "name_fields": fields,
        "evidence": evidence,
        "source_status": row.get("status"),
        "safety": {
            "read_only": True,
            "semantic_label_created": False,
            "rename_applied": False,
            "metadata_written": False,
            "human_approval_required": True,
        },
    }


def render(receipt: Path, out: Path, cards: Path | None = None,
            limit: int | None = None) -> dict[str, Any]:
    header, rows = _load_jsonl(receipt)
    card_map = _load_cards(cards)
    selected = list(rows.values())
    if cards is not None:
        # A physical-card packet is often an active-learning subset.  Restrict
        # rendering to its paths so a --limit cannot accidentally select
        # unrelated receipt rows with no physical evidence.
        card_paths = set(card_map)
        selected = [row for row in selected
                    if str(Path(row["path"]).resolve()) in card_paths]
    if limit is not None:
        selected = selected[: max(0, limit)]
    rendered = [_candidate(row, card_map.get(str(Path(row["path"]).resolve()))) for row in selected]
    payload = {
        "record_type": "slo_label_free_name_candidates",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_method_version": header.get("method_version"),
        "n_candidates": len(rendered),
        "n_suggested": sum(x["name_state"] == "suggested_review_required" for x in rendered),
        "n_review": sum(x["name_state"] == "review_required" for x in rendered),
        "physical_cards": str(cards.resolve()) if cards else None,
        "rows": rendered,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "metadata_written": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--cards", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = render(args.receipt, args.out, args.cards, args.limit)
    print(json.dumps({"out": str(args.out), "n_candidates": result["n_candidates"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
