"""Control and menu names in each note's "Try this" steps that appear nowhere in the Live 12 manual.

A name is a quoted phrase, a run of 2-4 Title Case words inside a sentence, or the words right before button, switch,
toggle, knob, slider, menu, tab, mode, section, chooser or field. Device and brand names KENN knows are allowed.

    check_note_ui_names.py live12_manual.txt apps/backend/src/kenn/Training_Data_Notes report.json

The manual text comes from the owner's PDF (pypdf); it isn't kept in the repo. A flagged name is a lead, not a verdict:
"Crackle Density" is Vinyl Distortion's Crackle section plus its Density control. Read each one against the manual.
"""
import json, re, sys, collections
from pathlib import Path
manual = " ".join(Path(sys.argv[1]).read_text(errors="replace").split()).casefold()
squashed = re.sub(r"[^a-z0-9]+", "", manual)
notes_dir = Path(sys.argv[2])
UI_NOUN = r"(?:button|switch|toggle|knob|slider|menu|tab|mode|section|chooser|field|dropdown|drop-down)"
TITLE = re.compile(r"(?<=[a-z,;(] )((?:[A-Z][a-zA-Z0-9/&+-]*\s){1,3}[A-Z][a-zA-Z0-9/&+-]*)")
BEFORE_NOUN = re.compile(rf"(?:the|a|an)\s+((?:[A-Z][\w/&+-]*\s){{1,3}})(?={UI_NOUN}\b)")
QUOTED = re.compile(r"[\"“]([A-Za-z][^\"“”\n]{1,40}?)[\"”]")
ALLOWED = re.compile(r"^(?:Ableton|Live|Mac|Windows|Win|Cmd|Ctrl|Alt|Option|Shift|Push|Max|MIDI|VST|AU|OSC|MPE|DAW|EQ|LFO|BPM|CPU|USB)\b")

def section(raw, name):
    m = re.search(rf"^{name}:\s*\n(.*?)(?=^\w[\w ]+:\s*$|\Z)", raw, re.M | re.S)
    return m.group(1) if m else ""

rows = []
for path in sorted(notes_dir.glob("*.md")):
    raw = path.read_text(errors="replace")
    if not re.search(r"^Status:\s*approved", raw, re.M | re.I):
        continue
    source = (re.search(r"^Source:\s*(.+)$", raw, re.M) or [None, ""])[1].strip()
    if not (path.name.startswith(("ableton12-", "ableton-")) or "Reference Manual" in source):
        continue
    steps = section(raw, "Try this")
    names = set()
    for rx in (QUOTED, TITLE, BEFORE_NOUN):
        names.update(m.group(1).strip(" .,") for m in rx.finditer(steps))
    missing = sorted({n for n in names if len(n) > 3 and not ALLOWED.match(n)
                      and n.casefold() not in manual and re.sub(r"[^a-z0-9]+", "", n.casefold()).rstrip("s") not in squashed})
    rows.append({"note": path.name, "source": source, "names": len(names), "missing": missing})
Path(sys.argv[3]).write_text(json.dumps(rows, indent=1))
bad = [r for r in rows if r["missing"]]
print("notes:", len(rows), "flagged:", len(bad), "names checked:", sum(r["names"] for r in rows), "missing:", sum(len(r["missing"]) for r in rows))
print(collections.Counter(("generated" if r["note"].startswith("ableton12-") else "other") for r in bad))
