#!/usr/bin/env python3
"""Local audio review UI for a taxonomy-gap CSV batch.

This is an owner-decision aid, not an automatic relabeller. It serves only
localhost, restricts each row to its candidate parent options (plus OOD),
requires a written note and reviewer ID, and writes a separate completed CSV.
The source queue is never modified. The resulting CSV can be passed directly
to ``import_taxonomy_gap_adjudication.py``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from label_tool import Decoded  # noqa: E402

FIELDS = [
    "batch_row", "id", "path", "content_sha256", "observed_label",
    "candidate_parent_options", "collection", "pack", "sample_family_id",
    "label_source", "owner_label", "owner_note", "owner_reviewer",
    "decision_status",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_queue(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(FIELDS[1:]).issubset(reader.fieldnames):
            raise ValueError("taxonomy review CSV is missing required fields")
        rows = list(reader)
    seen_ids: set[str] = set(); seen_paths: set[str] = set()
    for index, row in enumerate(rows):
        ident = (row.get("id") or "").strip()
        raw_path = (row.get("path") or "").strip()
        if not ident or ident in seen_ids:
            raise ValueError(f"queue has missing or duplicate id at row {index}")
        path = Path(raw_path).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"queue source path does not exist: {raw_path}")
        resolved = str(path.resolve())
        if resolved in seen_paths:
            raise ValueError(f"queue has duplicate path: {resolved}")
        expected = (row.get("content_sha256") or "").strip().lower()
        if len(expected) != 64 or sha256_file(path) != expected:
            raise ValueError(f"queue content hash mismatch for id {ident}")
        options = [x.strip() for x in (row.get("candidate_parent_options") or "").split("|") if x.strip()]
        if not options:
            raise ValueError(f"queue id {ident} has no candidate options")
        row["id"] = ident; row["path"] = resolved
        row["candidate_parent_options"] = "|".join(options)
        seen_ids.add(ident); seen_paths.add(resolved)
    return rows


def load_evidence(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evidence must be a JSON object")
    if payload.get("record_type") != "slo_taxonomy_gap_ai_option_filtered_receipt":
        raise ValueError("evidence is not an option-filtered taxonomy receipt")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("owner_labels_created") or safety.get("rename_actions")):
        raise ValueError("evidence receipt is not review-only")
    result: dict[str, dict[str, object]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("content_sha256"), str):
            raise ValueError("evidence row is missing content_sha256")
        content_hash = row["content_sha256"].lower()
        if len(content_hash) != 64 or content_hash in result:
            raise ValueError("evidence has missing or duplicate content hash")
        if row.get("semantic_label") is not None:
            raise ValueError("evidence contains a semantic label")
        result[content_hash] = {
            "label": row.get("ai_candidate_label"),
            "score": row.get("ai_candidate_score"),
            "margin": row.get("ai_candidate_margin"),
            "alternatives": row.get("ai_allowed_alternatives", []),
            "view_agreement": row.get("ai_view_agreement"),
        }
    return result


class ReviewState:
    def __init__(self, queue: list[dict[str, str]], output: Path, reviewer: str,
                 evidence: dict[str, dict[str, object]] | None = None):
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer ID is required")
        self.queue = queue; self.output = output.resolve(); self.reviewer = reviewer
        self.evidence = evidence or {}
        self.lock = threading.Lock(); self.done: dict[str, dict[str, str]] = {}
        if self.output.exists():
            with self.output.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or not set(FIELDS[1:]).issubset(reader.fieldnames):
                    raise ValueError("completed review CSV is missing required fields")
                for row in reader:
                    ident = (row.get("id") or "").strip()
                    if ident in self.done:
                        raise ValueError(f"completed review CSV has duplicate id: {ident}")
                    self.done[ident] = row
        queue_by_id = {row["id"]: row for row in queue}
        unknown = sorted(set(self.done) - set(queue_by_id))
        if unknown:
            raise ValueError(f"completed review CSV contains IDs not in queue: {unknown[:5]}")
        for ident, row in self.done.items():
            if row.get("content_sha256", "").lower() != queue_by_id[ident]["content_sha256"].lower():
                raise ValueError(f"completed review hash mismatch for id {ident}")
            label = (row.get("owner_label") or "").strip()
            note = (row.get("owner_note") or "").strip()
            reviewer_value = (row.get("owner_reviewer") or "").strip()
            status = (row.get("decision_status") or "").strip().lower()
            options = {x.strip() for x in queue_by_id[ident]["candidate_parent_options"].split("|") if x.strip()}
            normalized = "OOD" if label.upper() in {"OOD", "UNKNOWN"} else label
            if not label or not note or not reviewer_value or status not in {"approved", "adjudicated", "complete"}:
                raise ValueError(f"completed review row {ident} is incomplete")
            if normalized != "OOD" and normalized not in options:
                raise ValueError(f"completed review row {ident} has an invalid owner label")
        self.order = [row for row in queue if row["id"] not in self.done]

    def next_item(self) -> dict[str, str] | None:
        with self.lock:
            return dict(self.order[0]) if self.order else None

    def record(self, ident: str, label: str, note: str) -> None:
        ident = str(ident).strip(); label = str(label).strip(); note = str(note).strip()
        with self.lock:
            row = next((item for item in self.order if item["id"] == ident), None)
            if row is None:
                raise ValueError("row is not pending or does not exist")
            options = {x.strip() for x in row["candidate_parent_options"].split("|") if x.strip()}
            normalized = "OOD" if label.upper() in {"OOD", "UNKNOWN"} else label
            if normalized != "OOD" and normalized not in options:
                raise ValueError(f"label {label!r} is not an option for row {ident}")
            if not note:
                raise ValueError("a written owner note is required")
            saved = dict(row)
            saved.update({"owner_label": normalized, "owner_note": note,
                          "owner_reviewer": self.reviewer, "decision_status": "approved"})
            self.done[ident] = saved; self.order.pop(0); self._rewrite()

    def _rewrite(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader()
            for source in self.queue:
                row = self.done.get(source["id"], source)
                writer.writerow({field: row.get(field, "") for field in FIELDS})


HTML = """<!doctype html><meta charset=utf-8><title>SLO taxonomy review</title>
<style>body{font:16px system-ui;background:#111;color:#eee;text-align:center;margin:0}#app{max-width:900px;margin:auto;padding:22px}.muted{color:#888;font-size:13px}#name{color:#9cf;word-break:break-all;margin:14px}#advisory{color:#b9a7ff;font-size:13px;min-height:20px;margin:8px}canvas{background:#000;border-radius:8px}#opts{display:flex;flex-wrap:wrap;gap:9px;justify-content:center;margin:18px auto}button{background:#222;color:#eee;border:1px solid #555;border-radius:8px;padding:11px 14px;font-size:15px;cursor:pointer}button:hover{background:#333}#note{width:min(650px,90vw);padding:11px;background:#181818;color:#eee;border:1px solid #555;border-radius:7px}#err{color:#ff7474;min-height:22px;margin:8px}</style>
<div id=app><div id=prog></div><div id=name></div><div id=advisory></div><canvas id=wave width=760 height=140></canvas><audio id=au controls></audio><div class=muted>Choose only what you hear. Every decision requires a note. Space replays.</div><div id=opts></div><input id=note placeholder="Owner note (required: what you heard and why)" autocomplete=off><div id=err></div><div class=muted>Reviewer: <span id=reviewer></span></div></div>
<script>let cur=null;const au=document.getElementById('au'),cv=document.getElementById('wave'),cx=cv.getContext('2d');async function boot(){let m=await(await fetch('/meta')).json();document.getElementById('reviewer').textContent=m.reviewer;next()}function paint(a){cx.clearRect(0,0,cv.width,cv.height);cx.strokeStyle='#0a84ff';cx.beginPath();a.forEach((v,i)=>{let x=i/a.length*cv.width,y=70-v*65;i?cx.lineTo(x,y):cx.moveTo(x,y)});cx.stroke()}async function next(){let r=await fetch('/next');if(r.status===204){document.getElementById('app').innerHTML='<h2>All rows reviewed</h2>';return}cur=await r.json();document.getElementById('prog').textContent='reviewed '+cur.done+' / '+cur.total;document.getElementById('name').textContent=cur.name;let a=cur.advisory;document.getElementById('advisory').textContent=a&&a.label?'AI advisory only — '+a.label+' (confirm by ear; score '+Number(a.score).toFixed(3)+')':'AI advisory: no allowed candidate; review by ear';au.src='/audio/'+cur.id;au.play().catch(()=>{});try{paint(await(await fetch('/wave/'+cur.id)).json())}catch(e){}let o=document.getElementById('opts');o.innerHTML='';cur.options.forEach((x,i)=>{let b=document.createElement('button');b.textContent=(i+1)+'. '+x;b.onclick=()=>save(x);o.appendChild(b)})}async function save(label){let note=document.getElementById('note').value.trim();let r=await fetch('/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:cur.id,label,note})});if(!r.ok){let j=await r.json();document.getElementById('err').textContent=j.error||'refused';return}document.getElementById('note').value='';document.getElementById('err').textContent='';next()}document.onkeydown=e=>{if(e.target===document.getElementById('note'))return;if(e.key===' '){e.preventDefault();au.currentTime=0;au.play()}else{let n=parseInt(e.key,10);if(n>=1&&n<=((cur||{}).options||[]).length)save(cur.options[n-1])}};boot();</script>"""


def make_handler(state: ReviewState, decoder: Decoded):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def send_json(self, code: int, value: object):
            body = json.dumps(value).encode(); self.send_response(code)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                body = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if path == "/meta": self.send_json(200, {"total": len(state.queue), "done": len(state.done), "reviewer": state.reviewer}); return
            if path == "/next":
                item = state.next_item()
                if item is None: self.send_response(204); self.end_headers(); return
                evidence = state.evidence.get(item["content_sha256"].lower())
                self.send_json(200, {"id": item["id"], "name": Path(item["path"]).name, "options": item["candidate_parent_options"].split("|"), "advisory": evidence, "done": len(state.done), "total": len(state.queue)}); return
            if path.startswith("/audio/") or path.startswith("/wave/"):
                ident = path.rsplit("/", 1)[-1]; item = next((row for row in state.queue if row["id"] == ident), None)
                if item is None: self.send_response(404); self.end_headers(); return
                wav, peaks = decoder.get(item["path"])
                if path.startswith("/audio/"):
                    if wav is None: self.send_response(404); self.end_headers(); return
                    self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(wav))); self.end_headers(); self.wfile.write(wav)
                else: self.send_json(200, json.loads(peaks))
                return
            self.send_response(404); self.end_headers()
        def do_POST(self):
            if urlparse(self.path).path != "/label": self.send_response(404); self.end_headers(); return
            length = int(self.headers.get("Content-Length", 0)); data = json.loads(self.rfile.read(length) or b"{}")
            try: state.record(data.get("id", ""), data.get("label", ""), data.get("note", ""))
            except ValueError as exc: self.send_json(422, {"ok": 0, "error": str(exc)}); return
            self.send_json(200, {"ok": 1})
    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True); parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reviewer", required=True); parser.add_argument("--port", type=int, default=8751)
    parser.add_argument("--evidence", type=Path, help="optional filtered AI-advisory receipt")
    args = parser.parse_args(argv)
    same_source = args.out.resolve() == args.queue.resolve()
    if args.out.exists() and args.queue.exists():
        try:
            same_source = same_source or os.path.samefile(args.out, args.queue)
        except OSError:
            pass
    if same_source:
        raise ValueError("review output must be different from the source queue")
    state = ReviewState(load_queue(args.queue), args.out, args.reviewer,
                        load_evidence(args.evidence) if args.evidence else None)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state, Decoded()))
    print(f"reviewing {len(state.queue)} rows; {len(state.done)} already complete")
    print(f"open http://localhost:{args.port} (output: {state.output})")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nreview stopped; completed rows are saved")
    finally: server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
