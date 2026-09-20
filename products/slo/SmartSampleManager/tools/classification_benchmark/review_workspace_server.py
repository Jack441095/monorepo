#!/usr/bin/env python3
"""Local-only review workspace for SLO's derived evidence artifacts.

The workspace exposes review collections and controlled text search over
localhost. It never serves source audio, changes classifier decisions, or
applies rename actions. Feedback is written only to the append-only typed
event ledger when a reviewer explicitly submits it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SD = Path(__file__).resolve().parent
VERSION = "review_workspace_v2"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ReviewWorkspace:
    def __init__(self, collections_path: Path, feedback_log: Path,
                 content_index_path: Path | None = None,
                 duplicate_guard_path: Path | None = None,
                 approval_gate_path: Path | None = None,
                 embeddings_path: Path | None = None,
                 class_gate_queue_path: Path | None = None,
                 class_gate_fusion_path: Path | None = None,
                 evidence_packet_path: Path | None = None,
                 name_calibration_path: Path | None = None,
                 calibration_sample_path: Path | None = None):
        self.collections_path = collections_path.resolve()
        self.feedback_log = feedback_log.resolve()
        self.content_index_path = content_index_path.resolve() if content_index_path else None
        self.payload = json.loads(self.collections_path.read_text(encoding="utf-8"))
        if self.payload.get("record_type") != "slo_review_collections":
            raise ValueError("collections input must be slo_review_collections")
        self.evidence_packet = None
        self.evidence_by_path = {}
        self.evidence_packet_sha256 = None
        if evidence_packet_path is not None:
            evidence_path = evidence_packet_path.resolve()
            evidence_bytes = evidence_path.read_bytes()
            evidence_payload = json.loads(evidence_bytes)
            if evidence_payload.get("record_type") != "slo_label_free_evidence_packet":
                raise ValueError("evidence packet has an unexpected record_type")
            safety = evidence_payload.get("safety") or {}
            if (not safety.get("read_only") or safety.get("semantic_labels_created")
                    or safety.get("rename_actions") or safety.get("source_audio_modified")):
                raise ValueError("evidence packet is not read-only")
            for row in evidence_payload.get("rows", []):
                path = row.get("path") if isinstance(row, dict) else None
                if not isinstance(path, str) or not os.path.isabs(path):
                    raise ValueError("evidence packet row path must be absolute")
                if path in self.evidence_by_path:
                    raise ValueError(f"duplicate evidence packet path: {path}")
                if row.get("semantic_label") is not None:
                    raise ValueError("evidence packet contains a semantic label")
                self.evidence_by_path[path] = row
            self.evidence_packet = {
                "path": str(evidence_path),
                "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                "n_rows": len(self.evidence_by_path),
                "coverage": evidence_payload.get("coverage", {}),
            }
            self.evidence_packet_sha256 = self.evidence_packet["sha256"]
        self.name_calibration = None
        if name_calibration_path is not None:
            calibration_path = name_calibration_path.resolve()
            calibration_payload = json.loads(calibration_path.read_text(encoding="utf-8"))
            if calibration_payload.get("record_type") != "slo_label_free_name_calibration":
                raise ValueError("name calibration has an unexpected record_type")
            safety = calibration_payload.get("safety") or {}
            if (not safety.get("read_only") or safety.get("auto_action_allowed")
                    or safety.get("rename_actions")):
                raise ValueError("name calibration is not advisory/read-only")
            self.name_calibration = {
                "path": str(calibration_path),
                "n_adjudicated_paths": calibration_payload.get("n_adjudicated_paths", 0),
                "slices": calibration_payload.get("slices", {}),
                "promotion_candidate_slices": calibration_payload.get(
                    "promotion_candidate_slices", []),
            }
        self.calibration_sample = None
        self.calibration_sample_rows = []
        if calibration_sample_path is not None:
            sample_path = calibration_sample_path.resolve()
            sample_payload = json.loads(sample_path.read_text(encoding="utf-8"))
            if sample_payload.get("record_type") != "slo_label_free_calibration_sample_manifest":
                raise ValueError("calibration sample has an unexpected record_type")
            if sample_payload.get("method_version") != "label_free_calibration_sample_v2":
                raise ValueError("calibration sample must be regenerated with the v2 integrity contract")
            safety = sample_payload.get("safety") or {}
            if (not safety.get("read_only") or safety.get("semantic_labels_created")
                    or safety.get("rename_actions") or safety.get("audio_modified")
                    or not safety.get("human_ear_review_required_for_calibration")):
                raise ValueError("calibration sample is not a read-only review manifest")
            rows = sample_payload.get("rows", [])
            if not isinstance(rows, list):
                raise ValueError("calibration sample rows are invalid")
            seen_paths = set()
            for row in rows:
                if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                        or not os.path.isabs(row["path"])
                        or row.get("semantic_label") is not None):
                    raise ValueError("calibration sample rows are invalid or contain labels")
                if row["path"] in seen_paths:
                    raise ValueError(f"calibration sample contains duplicate path: {row['path']}")
                seen_paths.add(row["path"])
            if int(sample_payload.get("n_selected", len(rows))) != len(rows):
                raise ValueError("calibration sample n_selected does not match rows")
            exclusions = sample_payload.get("exclusions")
            if not isinstance(exclusions, dict):
                raise ValueError("calibration sample is missing exclusion metadata")
            sealed_collections = exclusions.get("sealed_holdout_collections")
            duplicate_content_excluded = exclusions.get("duplicate_content_rows_excluded")
            if (not isinstance(sealed_collections, list)
                    or any(not isinstance(name, str) or not name for name in sealed_collections)
                    or not isinstance(duplicate_content_excluded, int)
                    or duplicate_content_excluded < 0):
                raise ValueError("calibration sample exclusion metadata is invalid")
            source_packet = sample_payload.get("source_packet")
            source_packet_sha256 = sample_payload.get("source_packet_sha256")
            if source_packet_sha256 is not None:
                if not isinstance(source_packet, str) or not os.path.isabs(source_packet):
                    raise ValueError("calibration sample source packet path is invalid")
                source_path = Path(source_packet)
                if not source_path.is_file():
                    raise ValueError("calibration sample source packet is unavailable")
                actual_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if actual_sha256 != source_packet_sha256:
                    raise ValueError("calibration sample source packet hash does not match")
                if (self.evidence_packet_sha256 is not None
                        and source_packet_sha256 != self.evidence_packet_sha256):
                    raise ValueError("calibration sample does not match loaded evidence packet")
            self.calibration_sample = {
                "path": str(sample_path),
                "n_source_rows": sample_payload.get("n_source_rows", 0),
                "n_selected": sample_payload.get("n_selected", len(rows)),
                "source_packet_sha256": source_packet_sha256,
                "manifest_integrity_verified": True,
                "lane_counts": sample_payload.get("lane_counts", {}),
                "domain_counts": sample_payload.get("domain_counts", {}),
            }
            self.calibration_sample_rows = rows
        self.content_by_path = {}
        if content_index_path is not None:
            content_payload = json.loads(content_index_path.read_text(encoding="utf-8"))
            if content_payload.get("record_type") != "slo_content_addressed_embedding_index":
                raise ValueError("content index has an unexpected record type")
            for record in content_payload.get("records", []):
                identity = {
                    "content_sha256": record.get("content_sha256"),
                    "canonical_path": record.get("canonical_path"),
                    "alias_paths": record.get("paths", []),
                }
                for path in record.get("paths", []):
                    self.content_by_path[os.path.abspath(path)] = identity
            self.content_index = {"n_content_ids": content_payload.get("n_content_ids"), "n_alias_paths": content_payload.get("n_alias_paths")}
        else:
            self.content_index = None
        self.guard_by_path = {}
        if duplicate_guard_path is not None:
            guard_payload = json.loads(duplicate_guard_path.read_text(encoding="utf-8"))
            if guard_payload.get("record_type") != "slo_rename_duplicate_guard_audit":
                raise ValueError("duplicate guard has an unexpected record type")
            self.guard_by_path = {os.path.abspath(row["path"]): row for row in guard_payload.get("rows", [])}
        self.approval_by_path = {}
        self.approval_counts = {}
        self.approval_payload = None
        if approval_gate_path is not None:
            approval_payload = json.loads(approval_gate_path.read_text(encoding="utf-8"))
            if approval_payload.get("record_type") != "slo_rename_approval_gate_audit":
                raise ValueError("approval gate has an unexpected record type")
            self.approval_payload = approval_payload
            self.approval_by_path = {os.path.abspath(row["path"]): row for row in approval_payload.get("rows", [])}
            self.approval_counts = approval_payload.get("counts", {})
        self.feedback = _load("review_feedback_events", "review_feedback_events.py")
        self.describe = _load("describe_sound_query", "describe_sound_query.py")
        self.query_by_example = _load("query_by_example", "query_by_example.py") if embeddings_path else None
        self.embeddings_path = embeddings_path.resolve() if embeddings_path else None
        self.class_gate_queue_path = class_gate_queue_path.resolve() if class_gate_queue_path else None
        self.class_gate_payload = None
        if class_gate_queue_path is not None:
            self.class_gate_payload = json.loads(class_gate_queue_path.read_text(encoding="utf-8"))
            if self.class_gate_payload.get("record_type") != "slo_class_conditional_gate_testing_review":
                raise ValueError("class-gate queue has an unexpected record type")
        self.class_gate_fusion_path = class_gate_fusion_path.resolve() if class_gate_fusion_path else None
        self.class_gate_fusion_payload = None
        if class_gate_fusion_path is not None:
            self.class_gate_fusion_payload = json.loads(class_gate_fusion_path.read_text(encoding="utf-8"))
            if self.class_gate_fusion_payload.get("record_type") != "slo_class_gate_fusion_review_packet":
                raise ValueError("class-gate fusion packet has an unexpected record type")
            if self.class_gate_fusion_payload.get("safety", {}).get("auto_approved", False):
                raise ValueError("class-gate fusion packet must remain review-only")
        self._lock = threading.Lock()

    def summary(self) -> dict:
        return {
            "record_type": "slo_review_workspace_summary",
            "method_version": VERSION,
            "collections": self.payload.get("summary", {}),
            "n_plan_rows": self.payload.get("n_plan_rows", 0),
            "n_joined_evidence": self.payload.get("n_joined_evidence", 0),
            "evidence_packet": self.evidence_packet,
            "name_calibration": self.name_calibration,
            "calibration_sample": self.calibration_sample,
            "feedback_events": len(self.feedback.read_events(self.feedback_log)),
            "content_index": self.content_index,
            "duplicate_guard_flags": sum(bool(row.get("flags")) for row in self.guard_by_path.values()),
            "approval_gate_counts": self.approval_counts,
            "approval_gate_qualification": (self.approval_payload or {}).get("qualification_summary", {}),
            "similarity_search": self.embeddings_path is not None,
            "class_gate_review": {
                "enabled": self.class_gate_payload is not None,
                "n_candidates": (self.class_gate_payload or {}).get("testing_summary", {}).get("n_review_candidates", 0),
                "classes": (self.class_gate_payload or {}).get("candidate_classes", {}),
            },
            "class_gate_fusion_review": {
                "enabled": self.class_gate_fusion_payload is not None,
                "n_candidates": (self.class_gate_fusion_payload or {}).get("summary", {}).get("n_rows", 0),
                "fusion_states": (self.class_gate_fusion_payload or {}).get("summary", {}).get("fusion_states", {}),
                "decision": (self.class_gate_fusion_payload or {}).get("decision", "review-only"),
            },
            "safety": {
                "localhost_only": True,
                "source_audio_served": False,
                "source_audio_modified": False,
                "labels_created": False,
                "rename_actions": False,
                "feedback_promoted_to_gold": False,
            },
        }

    def items(self, action: str, limit: int = 100) -> dict:
        allowed = {"auto_rename", "suggest", "review", "never_act"}
        if action not in allowed:
            raise ValueError(f"unknown collection: {action}")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.payload.get("collections", {}).get(action, [])[:limit]
        enriched = []
        for original in rows:
            item = dict(original)
            path = os.path.abspath(str(item.get("path", "")))
            if path in self.content_by_path:
                item["content_identity"] = self.content_by_path[path]
            if path in self.guard_by_path:
                item["duplicate_guard"] = {
                    "flags": self.guard_by_path[path].get("flags", []),
                    "exact_group": self.guard_by_path[path].get("exact_group"),
                    "near_duplicate_group_indices": self.guard_by_path[path].get("near_duplicate_group_indices", []),
                }
            if path in self.approval_by_path:
                item["approval_gate"] = self.approval_by_path[path]
            enriched.append(item)
        # Return derived evidence only; paths are identifiers and audio is never
        # read or streamed by this server.
        return {"collection": action, "n_returned": len(enriched), "items": enriched,
                "safety": {"source_audio_served": False, "rename_actions": False}}

    def evidence_items(self, limit: int = 100) -> dict:
        if self.evidence_packet is None:
            raise ValueError("evidence packet is not configured")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = list(self.evidence_by_path.values())[:limit]
        return {"n_returned": len(rows), "items": rows,
                "safety": {"source_audio_served": False, "source_audio_modified": False,
                           "labels_created": False, "rename_actions": False}}

    def name_calibration_report(self) -> dict:
        if self.name_calibration is None:
            raise ValueError("name calibration is not configured")
        return {**self.name_calibration,
                "safety": {"read_only": True, "auto_action_allowed": False,
                           "rename_actions": False}}

    def calibration_sample_items(self, lane: str | None = None,
                                 domain: str | None = None,
                                 limit: int = 100) -> dict:
        if self.calibration_sample is None:
            raise ValueError("calibration sample is not configured")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.calibration_sample_rows
        if lane:
            rows = [row for row in rows if row.get("lane") == lane]
        if domain:
            rows = [row for row in rows if row.get("domain") == domain]
        rows = rows[:limit]
        enriched = []
        for row in rows:
            item = dict(row)
            evidence = self.evidence_by_path.get(os.path.abspath(str(row.get("path", ""))))
            if evidence is not None:
                # Expose only bounded, read-only candidate evidence needed for
                # adjudication.  Do not copy arbitrary packet fields (which
                # could accidentally turn this review endpoint into an audio
                # or metadata transport).
                evidence_view = {}
                for key in ("domain_route", "ensemble", "specialist", "name_candidate",
                            "fused_decision", "physical", "segments"):
                    value = evidence.get(key)
                    if isinstance(value, dict):
                        if key != "segments":
                            evidence_view[key] = value
                            continue
                        # Segment packets may contain thousands of windows;
                        # expose a compact review summary plus a small prefix.
                        # The full packet remains available to the native
                        # evidence viewer and is never streamed as audio.
                        segment_view = {
                            field: value[field] for field in
                            ("n_scored_windows", "status", "semantic_label")
                            if field in value
                        }
                        windows = value.get("segments")
                        if isinstance(windows, list):
                            segment_view["segments"] = windows[:32]
                            segment_view["n_returned_windows"] = min(len(windows), 32)
                        evidence_view[key] = segment_view
                if evidence_view:
                    item["evidence"] = evidence_view
            enriched.append(item)
        return {
            "n_returned": len(enriched),
            "items": enriched,
            "safety": {
                "read_only": True,
                "source_audio_served": False,
                "labels_created": False,
                "rename_actions": False,
                "human_ear_review_required": True,
            },
        }

    def search(self, text: str, limit: int = 100) -> dict:
        if not text.strip():
            raise ValueError("query must not be empty")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        return self.describe.search(self.payload, text, limit)

    def similar(self, path: str, top_k: int = 20, evidence_k: int = 10, dedupe_content: bool = True) -> dict:
        if self.query_by_example is None or self.embeddings_path is None:
            raise ValueError("similarity search is not configured")
        return self.query_by_example.build_search(
            path, self.embeddings_path, top_k, evidence_k,
            self.content_index_path, dedupe_content
        )

    def class_gate_items(self, class_name: str | None = None, limit: int = 100) -> dict:
        if self.class_gate_payload is None:
            raise ValueError("class-gate review is not configured")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.class_gate_payload.get("rows", [])
        if class_name:
            rows = [row for row in rows if row.get("candidate_class") == class_name]
        rows = rows[:limit]
        return {
            "n_returned": len(rows),
            "items": rows,
            "safety": {"source_audio_served": False, "rename_actions": False,
                       "auto_approved": False},
        }

    def class_gate_fusion_items(self, class_name: str | None = None,
                                fusion_state: str | None = None,
                                limit: int = 100) -> dict:
        if self.class_gate_fusion_payload is None:
            raise ValueError("class-gate fusion review is not configured")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.class_gate_fusion_payload.get("rows", [])
        if class_name:
            rows = [row for row in rows if row.get("candidate_class") == class_name]
        if fusion_state:
            rows = [row for row in rows if row.get("fusion_state") == fusion_state]
        rows = rows[:limit]
        return {
            "n_returned": len(rows),
            "items": rows,
            "safety": {"source_audio_served": False, "rename_actions": False,
                       "auto_approved": False, "labels_created": False},
        }

    def approval_items(self, status: str | None = None,
                       reason: str | None = None,
                       exclude_reason: str | None = None,
                       limit: int = 100) -> dict:
        if self.approval_payload is None:
            raise ValueError("approval-gate review is not configured")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.approval_payload.get("rows", [])
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if reason:
            rows = [row for row in rows if reason in row.get("reasons", [])]
        if exclude_reason:
            excluded = {part for part in exclude_reason.split(",") if part}
            rows = [row for row in rows if not any(part in row.get("reasons", []) for part in excluded)]
        rows = rows[:limit]
        return {
            "n_returned": len(rows),
            "items": rows,
            "safety": {"source_audio_served": False, "rename_actions": False,
                       "approval_granted": False},
        }

    def record_feedback(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("feedback body must be an object")
        path = body.get("path")
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("feedback path must be absolute")
        lookup = None
        for values in self.payload.get("collections", {}).values():
            for item in values:
                if item.get("path") == path:
                    lookup = item
                    break
            if lookup:
                break
        if lookup is None:
            lookup = self.evidence_by_path.get(path)
        if lookup is None and self.calibration_sample is not None:
            # Calibration manifests may intentionally be a strict subset of
            # the legacy review collections.  Permit notes/decisions for those
            # rows while still requiring candidate binding below whenever a
            # candidate-specific event is submitted.
            lookup = next((row for row in self.calibration_sample_rows
                           if row.get("path") == path), None)
        elif (body.get("event_type") in {"accept_name_candidate", "correct_name_candidate",
                                           "reject_name_candidate", "accept_fused_candidate",
                                           "correct_fused_candidate", "reject_fused_candidate"}
              and not isinstance(lookup.get("name_candidate"), dict)
              and path in self.evidence_by_path):
            # A path may appear in both a legacy review collection and the
            # newer AI packet. Prefer the packet for filename feedback because
            # it is the source of the candidate being reviewed.
            lookup = self.evidence_by_path[path]
        if lookup is None:
            raise ValueError("feedback path is not in the loaded review collections")
        event = dict(body)
        event.setdefault("event_id", str(uuid.uuid4()))
        event.setdefault("created_at", _now())
        event.setdefault("actor", "local_reviewer")
        event.setdefault("source_plan_sha256", self.payload.get("source_plan_sha256", "unknown"))
        if self.evidence_packet_sha256 is not None:
            event.setdefault("source_packet_sha256", self.evidence_packet_sha256)
        event.setdefault("previous_decision", lookup.get("action", lookup.get("review_state", "unknown")))
        if event.get("event_type") in {"accept_name_candidate", "correct_name_candidate",
                                        "reject_name_candidate"}:
            candidate = lookup.get("name_candidate") if isinstance(lookup, dict) else None
            expected = candidate.get("candidate_filename") if isinstance(candidate, dict) else None
            if not isinstance(expected, str) or not expected:
                raise ValueError("feedback path has no structured name candidate")
            supplied = event.get("candidate_filename", expected)
            if supplied != expected:
                raise ValueError("candidate filename does not match evidence packet")
            event["candidate_filename"] = expected
        if event.get("event_type") in {"accept_fused_candidate", "correct_fused_candidate",
                                        "reject_fused_candidate"}:
            fused = lookup.get("fused_decision") if isinstance(lookup, dict) else None
            if not isinstance(fused, dict):
                raise ValueError("feedback path has no fused decision")
            expected = fused.get("candidate_label") or fused.get("domain_candidate_label")
            if not isinstance(expected, str) or not expected:
                raise ValueError("fused decision has no candidate")
            supplied = event.get("candidate_label", expected)
            if supplied != expected:
                raise ValueError("candidate label does not match evidence packet")
            event["candidate_label"] = expected
        with self._lock:
            return self.feedback.append_event(self.feedback_log, event)


HTML = """<!doctype html>
<meta charset=utf-8><title>SLO Review Workspace</title>
<style>body{font:15px system-ui;max-width:1000px;margin:32px auto;padding:0 18px}input,button{font:inherit;padding:7px}pre{white-space:pre-wrap;background:#f4f4f4;padding:12px;border-radius:6px}.safe{color:#185c37}</style>
<h1>SLO Review Workspace</h1>
<p class=safe>Local review only. Source audio is never served or modified. Similarity and text search are not labels.</p>
<p><button onclick="summary()">Load summary</button> <button onclick="evidence()">AI evidence</button> <button onclick="calibration()">Name calibration</button> <button onclick="calSample()">Calibration sample</button> <input id=q placeholder="dark transient percussion loop" size=40><button onclick="search()">Describe search</button> <button onclick="classGate()">Class-gate candidates</button> <button onclick="classGateFusion()">Fused gate review</button> <button onclick="approvalGate()">Approval gate</button></p>
<p><input id=path placeholder="/absolute/path/to/sample.wav" size=72><button onclick="similar()">Find similar</button></p>
<pre id=out>Ready.</pre>
<script>
async function summary(){out.textContent=JSON.stringify(await (await fetch('/api/summary')).json(),null,2)}
async function evidence(){out.textContent=JSON.stringify(await (await fetch('/api/evidence?limit=100')).json(),null,2)}
async function calibration(){out.textContent=JSON.stringify(await (await fetch('/api/name-calibration')).json(),null,2)}
async function calSample(){out.textContent=JSON.stringify(await (await fetch('/api/calibration-sample?limit=100')).json(),null,2)}
async function search(){out.textContent=JSON.stringify(await (await fetch('/api/search?q='+encodeURIComponent(q.value))).json(),null,2)}
async function similar(){out.textContent=JSON.stringify(await (await fetch('/api/similar?path='+encodeURIComponent(path.value))).json(),null,2)}
async function classGate(){out.textContent=JSON.stringify(await (await fetch('/api/class-gate?limit=100')).json(),null,2)}
async function classGateFusion(){out.textContent=JSON.stringify(await (await fetch('/api/class-gate-fusion?limit=100')).json(),null,2)}
async function approvalGate(){out.textContent=JSON.stringify(await (await fetch('/api/approval-gate?limit=100')).json(),null,2)}
</script>
"""


def make_handler(workspace: ReviewWorkspace):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, value, content_type="application/json"):
            raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    return self._send(200, HTML, "text/html; charset=utf-8")
                if parsed.path == "/api/health":
                    return self._send(200, {"ok": True, "method_version": VERSION})
                if parsed.path == "/api/summary":
                    return self._send(200, workspace.summary())
                if parsed.path == "/api/items":
                    query = parse_qs(parsed.query)
                    action = query.get("action", ["review"])[0]
                    limit = int(query.get("limit", [100])[0])
                    return self._send(200, workspace.items(action, limit))
                if parsed.path == "/api/evidence":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.evidence_items(
                        int(query.get("limit", [100])[0])))
                if parsed.path == "/api/name-calibration":
                    return self._send(200, workspace.name_calibration_report())
                if parsed.path == "/api/calibration-sample":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.calibration_sample_items(
                        query.get("lane", [None])[0],
                        query.get("domain", [None])[0],
                        int(query.get("limit", [100])[0]),
                    ))
                if parsed.path == "/api/search":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.search(query.get("q", [""])[0], int(query.get("limit", [100])[0])))
                if parsed.path == "/api/similar":
                    query = parse_qs(parsed.query)
                    path = query.get("path", [""])[0]
                    return self._send(200, workspace.similar(
                        path,
                        int(query.get("top_k", [20])[0]),
                        int(query.get("evidence_k", [10])[0]),
                        query.get("dedupe_content", ["1"])[0] != "0",
                    ))
                if parsed.path == "/api/class-gate":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.class_gate_items(
                        query.get("class", [None])[0],
                        int(query.get("limit", [100])[0]),
                    ))
                if parsed.path == "/api/class-gate-fusion":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.class_gate_fusion_items(
                        query.get("class", [None])[0],
                        query.get("fusion_state", [None])[0],
                        int(query.get("limit", [100])[0]),
                    ))
                if parsed.path == "/api/approval-gate":
                    query = parse_qs(parsed.query)
                    return self._send(200, workspace.approval_items(
                        query.get("status", [None])[0],
                        query.get("reason", [None])[0],
                        query.get("exclude_reason", [None])[0],
                        int(query.get("limit", [100])[0]),
                    ))
                return self._send(404, {"error": "not found"})
            except (ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/api/feedback":
                return self._send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                return self._send(201, workspace.record_feedback(body))
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": str(exc)})

        def log_message(self, *_args):
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collections", type=Path, required=True)
    parser.add_argument("--feedback-log", type=Path, required=True)
    parser.add_argument("--content-index", type=Path)
    parser.add_argument("--duplicate-guard", type=Path)
    parser.add_argument("--approval-gate", type=Path)
    parser.add_argument("--embeddings", type=Path)
    parser.add_argument("--class-gate-queue", type=Path)
    parser.add_argument("--class-gate-fusion", type=Path)
    parser.add_argument("--evidence-packet", type=Path,
                        help="optional label-free evidence packet for AI review")
    parser.add_argument("--name-calibration", type=Path,
                        help="optional advisory name calibration report")
    parser.add_argument("--calibration-sample", type=Path,
                        help="optional stratified, label-free calibration sample manifest")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    workspace = ReviewWorkspace(args.collections, args.feedback_log, args.content_index,
                                args.duplicate_guard, args.approval_gate, args.embeddings,
                                args.class_gate_queue, args.class_gate_fusion,
                                args.evidence_packet, args.name_calibration,
                                args.calibration_sample)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(workspace))
    print(f"SLO review workspace: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
