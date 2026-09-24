#!/usr/bin/env python3
"""Draft KENN device notes from Live 12 manual excerpts on the GPU 1 notes model.

Runs on the GPU box next to gpu1_manual_note_pipeline.py (/mnt/data/kenn-notes-gpu1):
    python3 draft_device_notes_gpu.py <packs_dir> <out_dir>

Same endpoint, model and headings as gpu1_manual_note_pipeline.py. Input is one
<Device>.manual.txt per device (plus optional <Device>.live_facts.txt measured
in Live). Output notes are marked Draft for owner review, never Approved.
"""
import json, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ENDPOINT = "http://127.0.0.1:11436/api/chat"
MODEL_ID = "kenn-notes-qwen3-4b-gpu1"
REQUIRED = ("Short answer:", "Try this:", "Why it matters:", "Common mistakes:", "Related questions:")
PACKS = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)

def normalise(body):
    """Strip markdown and put each required heading in its canonical form."""
    body = body.replace("**", "").replace("__", "")
    body = re.sub(r"(?m)^#+\s*", "", body)
    for heading in REQUIRED:
        body = re.sub(r"(?im)^\s*" + re.escape(heading[:-1]) + r"[ \t]*:?[ \t]*$", heading, body)
        body = re.sub(r"(?im)^\s*" + re.escape(heading[:-1]) + r"[ \t]*:", heading, body)
    return body


def ask(system, user):
    payload = {"model": MODEL_ID, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "options": {"num_predict": 900, "temperature": 0.2}}
    req = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    for _ in range(30):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
            time.sleep(10)  # the notes server takes one request at a time
    raise RuntimeError("notes server stayed busy")

for manual in sorted(PACKS.glob("*.manual.txt")):
    device = manual.name[:-len(".manual.txt")].replace("_", " ")
    slug = "ableton-" + device.lower().replace(" ", "-") + "-device"
    out = OUT / f"{slug}.md"
    if out.exists():
        print(f"skip {device} (exists)", flush=True); continue
    facts_path = PACKS / manual.name.replace(".manual.txt", ".live_facts.txt")
    facts = facts_path.read_text() if facts_path.exists() else ""
    system = (
        f"Write a practical KENN knowledge note about Ableton Live 12 {device} using ONLY the manual excerpt"
        + (" and the measured Live facts" if facts else "") + ". Do not invent controls, parameter names, ranges or behaviours; "
        "use the exact parameter names from the sources. Use these exact headings in order: Short answer:, Try this:, "
        "Why it matters:, Common mistakes:, Related questions:. Under Try this: give numbered steps, one per line. "
        "Plain text. Under 400 words.")
    user = f"Manual excerpt ({device}):\n{manual.read_text()[:18000]}"
    if facts:
        user += f"\n\nMeasured Live facts:\n{facts}"
    body = ""
    for attempt in range(4):
        try:
            body = ask(system, user)
            if "</think>" in body:
                body = body.split("</think>", 1)[1].strip()
            body = normalise(body)
            if all(h in body for h in REQUIRED):
                break
            print(f"  {device}: missing {[h for h in REQUIRED if h not in body]}, retry {attempt + 1}", flush=True)
            (OUT / f"_raw_{slug}_{attempt + 1}.txt").write_text(body, encoding="utf-8")
        except Exception as exc:
            print(f"  {device}: {exc}, retry {attempt + 1}", flush=True); time.sleep(5 * (attempt + 1))
    if not all(h in body for h in REQUIRED):
        print(f"FAILED {device}", flush=True); continue
    header = (f"# Ableton {device} Device\n\nType: Ableton device reference\nTags: ableton, {device.lower()}, device\n"
              "Status: Draft (owner review pending)\n"
              "Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)"
              + ("; Live 12.4.6 parameter readout 2026-09-24" if facts else "") + "\n"
              "Drafted: 2026-09-24 on the GPU 1 notes model (kenn-notes-qwen3-4b-gpu1)\n\n")
    out.write_text(header + body + "\n", encoding="utf-8")
    print(f"wrote {out.name} ({len(body)} chars)", flush=True)
print("ALL DONE", flush=True)
