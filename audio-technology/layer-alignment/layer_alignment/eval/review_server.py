"""Local blind-review server — stdlib only.

Run:  python3 eval/review_server.py <pack_dir> <votes_out.json> [port]

Serves a minimal UI (PLAY A / PLAY B / vote buttons / reason / NEXT),
hides all algorithm information until the vote is cast, saves every vote
atomically (temp+rename) for crash-resume, and skips already-voted cases.

Keyboard: 1..6 vote, N = next, R = replay current.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading

PACK_DIR = None
VOTES_PATH = None
LOCK = threading.Lock()

HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>NITE Layer Alignment — Blind Review</title>
<style>
body{font-family:-apple-system,Helvetica,sans-serif;background:#101418;color:#e8e8e8;
margin:0;display:flex;flex-direction:column;align-items:center;padding-top:8vh}
.card{background:#1a2027;border-radius:14px;padding:28px 34px;width:min(560px,92vw)}
button{font-size:16px;border:0;border-radius:8px;padding:10px 16px;margin:6px 4px;
background:#2b3542;color:#fff;cursor:pointer}
button:hover{background:#3a4a5c}
.choice{width:100%;margin:8px 0;padding:14px;font-size:17px;text-align:left}
.progress{color:#8fa0b3;margin-bottom:10px;font-size:14px}
.reason{width:100%;box-sizing:border-box;background:#0d1116;color:#ddd;border:1px solid #2b3542;
border-radius:8px;padding:10px;font-size:14px;height:64px;resize:none}
.tag{display:inline-block;background:#24303d;color:#9fb4c8;border-radius:6px;
padding:2px 10px;font-size:13px;margin-right:6px}
.done{font-size:20px}
</style></head><body>
<div class=card id=app><p>Loading…</p></div>
<script>
let cur=null,total=0,done=0;
const fmt=u=>`<audio controls preload=auto src="${u}"></audio>`;
async function api(p,opt){const r=await fetch(p,opt);return r.json();}
async function next(){
 const s=await api('/api/state');
 total=s.total;done=s.done;
 if(s.done_case){document.getElementById('app').innerHTML=
  `<h2>Review complete</h2><p class=done>${s.voted} judgements saved.<br>Thank you.</p>`;return;}
 cur=await api('/api/case');
 if(!cur){return next();}
 document.getElementById('app').innerHTML=`
 <div class=progress>Case ${s.done+1} of ${total} · ${s.voted} voted</div>
 <div style="margin-bottom:12px">
   <span class=tag>${cur.category}</span><span class=tag>${cur.relationship}</span>
 </div>
 <h3 style="margin:6px 0">Version A</h3>${fmt(cur.audio_a)}
 <h3 style="margin:18px 0 6px">Version B</h3>${fmt(cur.audio_b)}
 <hr style="border-color:#2b3542;margin:18px 0">
 <p style="margin:4px 0;color:#aab7c4">Which version has the preferable layer interaction?</p>
 <button class=choice onclick=vote(1)>1 · A clearly better</button>
 <button class=choice onclick=vote(2)>2 · A slightly better</button>
 <button class=choice onclick=vote(3)>3 · Equivalent / no meaningful preference</button>
 <button class=choice onclick=vote(4)>4 · B slightly better</button>
 <button class=choice onclick=vote(5)>5 · B clearly better</button>
 <button class=choice onclick=vote(6)>6 · Cannot judge</button>
 <textarea class=reason id=rs placeholder="optional reason"></textarea><br>
 <button onclick=skip()>Skip</button>
 <button onclick="location.reload()">Refresh</button>`;
}
async function vote(c){
 await api('/api/vote',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({case_id:cur.case_id,choice:c,
   reason:document.getElementById('rs').value})});
 next();
}
async function skip(){
 await api('/api/skip',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({case_id:cur.case_id})});
 next();
}
document.addEventListener('keydown',e=>{
 if(e.key>='1'&&e.key<='6')vote(parseInt(e.key));
 else if(e.key.toLowerCase()==='n')next();
 else if(e.key.toLowerCase()==='r'){const as=document.querySelectorAll('audio');as.forEach(a=>{a.currentTime=0;a.play()});}
});
next();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # silence
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/audio/"):
            f = (PACK_DIR / "audio" / Path(self.path).name)
            if not f.exists():
                self._json({"error": "not found"}, 404)
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            entries, votes = _load()
            done_ids = {v["case_id"] for v in votes}
            remaining = [e for e in entries if e["case_id"] not in done_ids]
            self._json({"total": len(entries), "done": len(done_ids),
                        "voted": len(votes), "done_case": not remaining})
        elif self.path == "/api/case":
            order = json.loads((PACK_DIR / "presentation_order.json").read_text())
            _, votes = _load()
            done_ids = {v["case_id"] for v in votes}
            nxt = next((e for e in order if e["case_id"] not in done_ids), None)
            if not nxt:
                self._json(None)
                return
            self._json({"case_id": nxt["case_id"],
                        "category": nxt.get("category", ""),
                        "relationship": nxt.get("relationship", ""),
                        "audio_a": "/audio/" + nxt["file_a"],
                        "audio_b": "/audio/" + nxt["file_b"],
                        # deliberately NOT exposed: slots, expected benefit,
                        # confidence, offset, action (blind until post-vote)
                        })
        else:
            self._json({"error": "unknown"}, 404)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(ln) or b"{}")
        if self.path == "/api/vote":
            entry = {"case_id": data.get("case_id"),
                     "choice": int(data.get("choice", 0)),
                     "reason": (data.get("reason") or "")[:300]}
            with LOCK:
                _, votes = _load()
                votes.append(entry)
                _save(votes)
            self._json({"ok": True})
        elif self.path == "/api/skip":
            with LOCK:
                _, votes = _load()
                votes.append({"case_id": data.get("case_id"), "choice": 0,
                              "skipped": True})
                _save(votes)
            self._json({"ok": True})
        else:
            self._json({"error": "unknown"}, 404)


def _load():
    p = Path(VOTES_PATH)
    if p.exists():
        return p, json.loads(p.read_text())
    return p, []


def _save(votes):
    p = Path(VOTES_PATH)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(votes, indent=1))
    tmp.replace(p)


if __name__ == "__main__":
    PACK_DIR = Path(sys.argv[1]).resolve()
    VOTES_PATH = Path(sys.argv[2]).resolve()
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
    print(f"review pack: {PACK_DIR}\nopen http://127.0.0.1:{port}/  "
          f"(Ctrl-C to stop; progress auto-saves)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
