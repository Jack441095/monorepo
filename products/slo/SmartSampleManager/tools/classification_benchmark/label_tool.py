#!/usr/bin/env python3
"""
Fast keyboard-driven audio labelling tool. Stdlib-only server (nothing to
install); transcodes any format to WAV for universal browser playback; saves
each label immediately so it is crash-safe and resumable.

Why this exists
---------------
Every accuracy figure in this project is agreement with filename-derived
keyword labels, not ground truth. Production only consults ML where filenames
give no answer, and the keyword labeller has known problems (Percussion is a
catch-all; Foley is provenance, not sound). This produces BY-EAR ground truth
for a stratified sample so the real numbers can finally be measured.

Two sample sets:
  --set drums        kick/snare/hi-hat/clap, to verify the atonal-hit
                     detector's confidence-gated ~97% precision claim.
  --set no_evidence  files with no filename keyword -- the population ML
                     actually decides -- to measure real deployment accuracy.

Usage:
  python3 label_tool.py --set drums --n 400
  python3 label_tool.py --set fft_physics \
      --manifest receipts/fft_physics_label_manifest_200_v1.json \
      --csv receipts/fft_physics_labels_reviewed_v1.csv
  # open http://localhost:8747 , label by ear, results in verified_<set>.csv

Keys in the browser: number keys assign a class, [space] replays,
[<-] goes back, [s] skips (unsure). Auto-advances after each label.
"""
import os, sys, io, csv, json, time, argparse, random, importlib.util, threading, webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import numpy as np
import soundfile as sf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HYBRID_NPZ = os.path.join(SCRIPT_DIR, "slo_all_packs_hybrid_v4.npz")

# candidate classes offered per set (the key the user presses -> label)
SETS = {
    "drums": ["Kick", "Snare", "Rimshot", "Hi-Hat", "Crash", "Clap", "Percussion", "Foley", "Kick Loop", "Snare Loop", "Drum Loop", "Top Loop", "Hi-Hat Loop", "Percussion Loop", "Bass Loop", "Foley Loop", "Loop", "Chord Loop", "Other/none", "Misc/Review", "Bass Reese", "Synth One-Shot", "Vocal One-Shot", "Vocal Loop", "SFX", "Riser", "Impact", "Pad", "Atmosphere", "Weather/Nature Atmos", "Drum Fill", "Synth Loop", "Bass Hit"],
    # The non-drum taxonomy v2.0 planned but never labelled. Building these
    # classes without by-ear data means validating against ~72%-accurate folder
    # labels, which is the trap the drum cycle was spent escaping.
    "tonal": ["Bass One-Shot", "Sub Bass", "Bass Loop", "Synth", "Pad", "Pluck",
              "Lead", "Piano/Keys", "Guitar", "Strings", "Brass", "Organ",
              "Chord Loop", "Melody Loop", "Arp Loop", "Vocal One-Shot",
              "Vocal Loop", "Riser", "Impact", "Atmosphere/Texture",
              "Other/none", "Misc/Review"],
    # Percussion subtype sprint. Deliberately mixes FORM (loop vs one-shot) and
    # FAMILY (shaker, tom, metallic) because that is the distinction the ear
    # actually makes on this material; the axes are separated afterwards.
    # Bass sprint. The four bass mechanisms are physically DISTINCT -- an 808 has
    # a downward pitch glide at the attack, Sub Bass has none, a Reese has
    # detuned beating between partials, a Bass Hit has a hit-like envelope -- so
    # they are offered as separate answers rather than one "Bass" bucket, which
    # is what makes the physics claim testable. "Not Bass" and "Unknown" are
    # escape hatches: the percussion sprint showed that a missing option
    # manufactures fake Unknowns.
    "bass": ["Reese Bass", "Sub Bass", "Synth Bass Sustained", "808",
             "Bass Hit", "Kick", "Bass Loop", "Not Bass", "Other/none",
             "Unknown"],
    "percussion_subtype": ["Percussion One-Shot", "Shaker/Tambourine",
                           "Tom/Conga/Bongo", "Metallic Percussion",
                           "Foley Percussion", "Percussion Loop", "Top Loop",
                           "Hi-Hat Loop", "Drum Loop", "Other/none", "Unknown"],
    "no_evidence": ["Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass",
                    "Synth", "Vocal", "FX", "Foley", "Riser/Impact", "Loop", "Other/none"],
    # Candidate-hidden FFT/physics review.  The manifest carries no predicted
    # class or feature values; the reviewer chooses from the frozen taxonomy
    # plus explicit escape hatches.  Keeping this as a separate set prevents
    # the evidence queue from being mistaken for an existing verified corpus.
    "fft_physics": ["Bass Hit", "Bass Loop", "Bass Reese", "Chord Loop",
                    "Clap", "Crash", "Drum Loop", "Foley", "Foley Loop",
                    "Hi-Hat", "Hi-Hat Loop", "Impact", "Kick", "Kick Loop",
                    "Other/none", "Pad", "Percussion", "Percussion Loop",
                    "Rimshot", "Riser", "SFX", "Snare", "Synth Loop",
                    "Synth One-Shot", "Top Loop", "Vocal Loop",
                    "Vocal One-Shot", "Weather/Nature Atmos", "Unknown",
                    "Not in list", "Not enough info", "Taxonomy gap"],
}


# Visual grouping for the key pad. Choosing 1-of-22 from a flat list means
# scanning every option; grouping into short labelled rows lets the eye jump
# straight to the family. Ordering here does not change the classes offered,
# only how they are drawn, so labels stay comparable across sessions.
GROUPS = {
    "bass": [
        ("sustained", ["Reese Bass", "Sub Bass", "Synth Bass Sustained"]),
        ("hit",       ["808", "Bass Hit", "Kick"]),
        ("other",     ["Bass Loop", "Not Bass", "Other/none", "Unknown"]),
    ],
    "tonal": [
        ("bass",   ["Bass One-Shot", "Sub Bass", "Bass Loop"]),
        ("synth",  ["Synth", "Pad", "Pluck", "Lead", "Organ"]),
        ("played", ["Piano/Keys", "Guitar", "Strings", "Brass"]),
        ("phrase", ["Chord Loop", "Melody Loop", "Arp Loop"]),
        ("vocal",  ["Vocal One-Shot", "Vocal Loop"]),
        ("fx",     ["Riser", "Impact", "Atmosphere/Texture"]),
        ("none",   ["Other/none", "Misc/Review"]),
    ],
    "percussion_subtype": [
        ("one-shot", ["Percussion One-Shot", "Shaker/Tambourine",
                      "Tom/Conga/Bongo", "Metallic Percussion",
                      "Foley Percussion"]),
        ("loop",     ["Percussion Loop", "Top Loop", "Hi-Hat Loop", "Drum Loop"]),
        ("none",     ["Other/none", "Unknown"]),
    ],
    "drums": [
        ("one-shot", ["Kick", "Snare", "Rimshot", "Hi-Hat", "Crash", "Clap",
                      "Percussion", "Foley"]),
        ("loop",     ["Kick Loop", "Snare Loop", "Drum Loop", "Top Loop",
                      "Hi-Hat Loop", "Percussion Loop", "Bass Loop",
                      "Foley Loop", "Loop", "Chord Loop"]),
        ("none",     ["Other/none", "Misc/Review"]),
        # Added mid-session at Jack's request. It goes LAST so every existing
        # key assignment is untouched -- keys are handed out in grouped order,
        # so appending is the only edit that cannot disturb muscle memory.
        ("tonal",    ["Bass Reese", "Synth One-Shot"]),
        ("vocal",    ["Vocal One-Shot", "Vocal Loop"]),
        ("fx",       ["SFX", "Riser", "Impact"]),
        ("sustain",  ["Pad", "Atmosphere", "Weather/Nature Atmos"]),
        # Appended, not inserted next to the drum loops where it belongs
        # visually, because inserting would shift every key after it.
        ("fill",     ["Drum Fill"]),
        ("more",     ["Synth Loop", "Bass Hit"]),
    ],
    "fft_physics": [
        ("bass", ["Bass Hit", "Bass Loop", "Bass Reese"]),
        ("loop", ["Chord Loop", "Drum Loop", "Foley Loop", "Hi-Hat Loop",
                  "Kick Loop", "Percussion Loop", "Synth Loop", "Top Loop",
                  "Vocal Loop"]),
        ("drum", ["Clap", "Crash", "Hi-Hat", "Kick", "Rimshot", "Snare",
                  "Percussion"]),
        ("tonal", ["Foley", "Pad", "Synth One-Shot", "Vocal One-Shot"]),
        ("fx", ["Impact", "Riser", "SFX", "Weather/Nature Atmos"]),
        ("other", ["Other/none", "Unknown", "Not in list", "Not enough info",
                    "Taxonomy gap"]),
    ],
}


# The granularity sprint runs one bucket at a time, each with its own short
# option list. The runner injects the active set through this env var rather
# than hardcoding six more entries into SETS/GROUPS.
def _load_injected_set():
    p = os.environ.get("SLO_GRAN_SET")
    if not p or not os.path.exists(p):
        return
    try:
        d = json.load(open(p))
        SETS[d["set"]] = d["flat"]
        GROUPS[d["set"]] = [tuple(g) for g in d["groups"]]
    except Exception:
        pass


_load_injected_set()


def grouped_classes(which):
    """Return [(group_name, [class,...])], falling back to one unnamed group."""
    g = GROUPS.get(which)
    if not g:
        return [("", list(SETS[which]))]
    flat = [c for _, cs in g for c in cs]
    missing = [c for c in SETS[which] if c not in flat]
    if missing:
        g = g + [("other", missing)]
    return g


def _canonical_id(value):
    """Keep legacy numeric ids numeric while allowing content manifests to use strings."""
    text = str(value)
    try:
        return int(text)
    except (TypeError, ValueError):
        return text


def load_review_items(path):
    """Load either the legacy list manifest or a candidate-hidden receipt.

    The FFT/physics builder intentionally writes a receipt object with rows
    whose ids are content-addressed strings. Normalising only the transport
    shape here lets the existing crash-safe UI and CSV writer consume it while
    preserving the id exactly in the output CSV.
    """
    payload = json.load(open(path, encoding="utf-8"))
    if isinstance(payload, dict):
        if payload.get("record_type") != "slo_fft_physics_label_manifest":
            raise ValueError("manifest receipt has an unexpected record type")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ValueError("manifest receipt must contain non-empty rows")
        out = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("path") or not row.get("id"):
                raise ValueError("manifest rows require id and path")
            # Do not copy evidence, candidate classes, or labels into the UI
            # item. The reviewer must remain blind to those values.
            out.append({"id": _canonical_id(row["id"]), "path": row["path"],
                        "hint": "", "display_name": f"Review item {row['id']}"})
        return out
    if not isinstance(payload, list):
        raise ValueError("manifest must be a list or a supported receipt object")
    return payload


# Backward-compatible label schema. "label" remains the PRIMARY label column
# under its original name: renaming it to primary_label would break every
# existing CSV and every script that reads them, which the extension is
# explicitly required not to do. Everything after "hint" is optional and is
# written empty for rows that predate it, so old files load unchanged and new
# columns simply appear blank.
SCHEMA = ["id", "label", "path", "hint", "note",
          # Generic subtype. percussion_subtype stays for backward
          # compatibility -- existing rows use it and must keep loading -- but
          # bass and loop families now need subtypes too, so new work writes
          # the family-agnostic field.
          "subtype",
          # Escape hatches. The percussion sprint proved that an option list
          # without one manufactures fake Unknowns: 11 of 47 files were marked
          # Unknown while carrying a written note that named the sound exactly,
          # because the list had no key for a plain Hi-Hat, Rimshot or SFX.
          "not_in_list_label",     # the label the reviewer wanted but could not pick
          "not_enough_info",       # true when the audio does not settle it
          "taxonomy_gap",          # true when SLO's taxonomy has no right answer
          "percussion_subtype", "rejection_reason",
          "acceptable_secondary_label", "ambiguous", "human_confidence",
          "function_family", "temporal_form", "source_attributes",
          "collection", "pack", "sample_family_id", "labelling_session"]

# Optional refinements, offered only after the relevant primary label and always
# skippable so primary labelling speed is preserved.
PERCUSSION_SUBTYPES = ["Tom", "Shaker/Tambourine", "Hand Drum",
                       "Other Percussive Hit", "Unsure"]
# Other/none is REJECTION material, not an acoustic family. Its heterogeneity is
# intended, so no acoustic subtype is requested -- only an optional reason.
# Classes that open a free-text note instead of a fixed-choice refinement.
#
# "Not in list" MUST be here. It was not, and the granularity sprint paid for
# it: 43 of 80 files in the rejection bucket were marked "Not in list" with no
# note, which records only that the option list was wrong -- not what the file
# actually is. Those 43 labels are unrecoverable. An escape hatch that does not
# capture the escape is just a skip button with a misleading name.
# An escape hatch that does not capture the escape is just a skip button with a
# misleading name. Adding these classes to the note PROMPT was not enough -- the
# prompt was skippable with Escape and acceptable with an empty box, so the
# recorded row still said only "the option list was wrong". The requirement is
# therefore enforced in State.record(), not in the browser: the UI is a
# convenience, the server is the contract.
NOTE_REQUIRED = ("Unknown", "Not in list", "Taxonomy gap")
# Prompted but skippable. "Not enough info" is a verdict about the AUDIO, not a
# complaint about the option list, so it is self-explanatory on its own; a note
# adds detail but its absence does not make the row meaningless.
NOTE_OPTIONAL = ("Not enough info",)
NOTE_CLASSES = NOTE_REQUIRED + NOTE_OPTIONAL
REJECTION_REASONS = ["unsupported instrument", "mixed/full music",
                     "noise or texture", "ambiguous", "corrupt or unusable",
                     "other"]


# Synonyms a reviewer actually types. Kept deliberately small and literal: this
# parser proposes a CANDIDATE for later human confirmation, it never assigns a
# label. A wrong guess that looks confident is worse than no guess at all.
NOTE_SYNONYMS = {
    "Kick": ["kick", "bd", "bass drum", "kik"],
    "Snare": ["snare", "snr"],
    "Rimshot": ["rimshot", "rim shot", "rim"],
    "Hi-Hat": ["hi-hat", "hihat", "hi hat", "hat", "closed hat", "open hat"],
    "Crash": ["crash", "cymbal", "ride"],
    "Clap": ["clap", "clp"],
    "Tom": ["tom"],
    "Shaker/Tambourine": ["shaker", "tambourine", "tamb"],
    "Hand Drum": ["conga", "bongo", "djembe", "hand drum", "tabla"],
    "Foley": ["foley"],
    "Impact": ["impact", "boom", "slam"],
    "Riser": ["riser", "uplifter", "sweep up"],
    "SFX": ["sfx", "fx", "sound effect"],
    "Atmosphere": ["atmos", "atmosphere", "ambience", "drone"],
    "Pad": ["pad"],
    "Bass Hit": ["bass hit", "bass stab"],
    "808": ["808"],
    "Sub Bass": ["sub bass", "sine bass"],
    "Reese Bass": ["reese"],
    "Vocal One-Shot": ["vocal", "vox", "voice"],
    "Synth One-Shot": ["synth", "stab", "lead", "pluck"],
    "Piano": ["piano", "keys", "rhodes"],
    "Guitar": ["guitar", "gtr"],
    "String": ["string", "violin", "cello"],
    "Brass": ["brass", "horn", "trumpet", "sax"],
    "Other/none": ["music", "full track", "loop of a song", "not a sample"],
}
FORM_HINTS = {"loop": ["loop", "bar", "phrase", "groove", "beat"],
              "one-shot": ["one shot", "one-shot", "single hit", "oneshot"]}


def parse_note(note):
    """Turn a free-text note into recoverable label candidates.

    Returns {"candidates": [...], "form": str|None, "matched": [...]}. Longest
    synonym wins so "bass drum" is not swallowed by "bass hit", and matching is
    whole-word so "hat" does not fire inside "that".
    """
    import re as _re
    text = " " + _re.sub(r"[^a-z0-9 ]+", " ", (note or "").lower()) + " "
    text = _re.sub(r"\s+", " ", text)
    hits = []
    for cls, syns in NOTE_SYNONYMS.items():
        for syn in syns:
            if _re.search(r"(?<![a-z0-9])" + _re.escape(syn) + r"(?![a-z0-9])", text):
                hits.append((len(syn), cls, syn))
    hits.sort(reverse=True)
    cands, matched, seen = [], [], set()
    for _, cls, syn in hits:
        if cls not in seen:
            seen.add(cls); cands.append(cls); matched.append(syn)
    form = None
    for f, syns in FORM_HINTS.items():
        if any(_re.search(r"(?<![a-z0-9])" + _re.escape(x) + r"(?![a-z0-9])", text)
               for x in syns):
            form = f; break
    return {"candidates": cands, "form": form, "matched": matched}


class EscapeHatchError(ValueError):
    """Raised when an escape-hatch label arrives with nothing to recover from."""


def derive_meta(path):
    """Collection/pack/family, derived automatically -- no labelling effort."""
    try:
        import sample_library_inventory as si
        _, vendor, pack, _ = si.attribute(path)
        return {"collection": vendor, "pack": pack,
                "sample_family_id": si.family_id(vendor, pack,
                                                 os.path.basename(path))}
    except Exception:
        return {"collection": "", "pack": "", "sample_family_id": ""}


def load_labeller():
    spec = importlib.util.spec_from_file_location("lb", os.path.join(SCRIPT_DIR, "build_all_packs_dataset_v2.py"))
    m = importlib.util.module_from_spec(spec); sys.modules["lb"] = m
    try: spec.loader.exec_module(m)
    except SystemExit: pass
    return m.classify_relpath_and_name


def build_manifest(which, n, seed):
    import build_hybrid_v4_dataset as dsp
    fn_map = dsp.build_filename_map(dsp.SOURCE_ROOT)
    d = np.load(HYBRID_NPZ, allow_pickle=True)
    fns = d["filenames"]; labs = np.array([str(v) for v in d["labels"]])
    rng = random.Random(seed)
    items = []

    if which == "drums":
        # stratified across the four drum classes, keyword-label as hint only
        per = max(1, n // 4)
        for c in ["Kick", "Snare", "Hi-Hat", "Clap"]:
            idx = [i for i in np.where(labs == c)[0] if str(fns[i]) in fn_map]
            rng.shuffle(idx)
            for i in idx[:per]:
                items.append({"path": fn_map[str(fns[i])], "hint": c})
    elif which == "tonal":
        # Surface plausible candidates per class via filename hints, balanced.
        # The hint is NOT shown at label time -- these only decide what gets
        # queued, so the ear stays the judge.
        import re as _re
        SEEDS = {
            "Bass":    r"\bbass\b|\b808\b|\bsub\b|reese",
            "Synth":   r"synth|saw\b|square|analog",
            "Pad":     r"\bpad\b|drone|warm|lush",
            "Pluck":   r"pluck|mallet|marimba|kalimba",
            "Lead":    r"\blead\b|arp\b|melody|melodic",
            "Keys":    r"piano|keys|rhodes|wurli|epiano",
            "Guitar":  r"guitar|\bgtr\b|acoustic",
            "Strings": r"string|violin|cello|viola",
            "Brass":   r"brass|horn|trumpet|\bsax\b|trombone",
            "Organ":   r"organ|hammond",
            "Chord":   r"chord|prog",
            "Vocal":   r"vocal|\bvox\b|acapella|choir|sing",
            "Riser":   r"riser|uplift|sweep|build",
            "Impact":  r"impact|\bboom\b|downlift|cinematic",
            "Texture": r"atmos|texture|ambien|drone|noise|field",
        }
        per = max(8, n // len(SEEDS))
        buckets = {k: [] for k in SEEDS}
        roots = [dsp.SOURCE_ROOT, "/Volumes/Jack_Gandy_1TB_SSD/Samples 2021 ->"]
        for root in roots:
            if not os.path.isdir(root): continue
            for dp, dn, files in os.walk(root):
                dn[:] = [x for x in dn if not x.startswith(".")]
                for f in files:
                    if os.path.splitext(f)[1].lower() not in {".wav",".aif",".aiff",".flac"}: continue
                    hay = f"{os.path.basename(dp)}/{f}"
                    for k, rx in SEEDS.items():
                        if len(buckets[k]) < per * 3 and _re.search(rx, hay, _re.I):
                            buckets[k].append(os.path.join(dp, f)); break
        for k, v in buckets.items():
            rng.shuffle(v)
            for path in v[:per]:
                items.append({"path": path, "hint": ""})
    else:  # no_evidence
        classify = load_labeller()
        # reproduce pack-relative no-evidence detection
        pool = []
        for root in [dsp.SOURCE_ROOT, "/Volumes/Jack_Gandy_1TB_SSD/Samples 2021 ->"]:
            if not os.path.isdir(root): continue
            for pack in sorted(os.listdir(root)):
                pdir = os.path.join(root, pack)
                if pack.startswith(".") or not os.path.isdir(pdir): continue
                for dp, dn, files in os.walk(pdir):
                    dn[:] = [x for x in dn if not x.startswith(".")]
                    rel = os.path.relpath(dp, pdir)
                    for f in files:
                        if os.path.splitext(f)[1].lower() in {".wav", ".aif", ".aiff", ".flac"} \
                                and classify(rel, f) is None:
                            pool.append(os.path.join(dp, f))
        rng.shuffle(pool)
        items = [{"path": p, "hint": ""} for p in pool[:n]]

    rng.shuffle(items)
    for k, it in enumerate(items):
        it["id"] = k
    return items


HTML = """<!doctype html><html><head><meta charset=utf-8><title>SLO Labeller</title>
<style>
body{font-family:system-ui;margin:0;background:#111;color:#eee;text-align:center}
#top{padding:18px}#prog{color:#888;font-size:14px}
#name{font-size:15px;color:#9cf;margin:10px;word-break:break-all}
#hint{color:#fa0;font-size:13px;margin-bottom:8px}
#keys{max-width:900px;margin:14px auto}
.grp{display:flex;align-items:center;gap:10px;margin:7px 0}
.glab{width:66px;text-align:right;color:#777;font-size:12px;text-transform:uppercase;letter-spacing:.5px;flex:none}
.gwrap{display:flex;flex-wrap:wrap;gap:8px;flex:1}
.k{background:#222;border:1px solid #444;border-radius:8px;padding:10px 13px;font-size:14px;cursor:pointer}
.k b{display:inline-block;background:#0a84ff;color:#fff;border-radius:5px;padding:1px 8px;margin-right:8px}
.k:hover{background:#333}
canvas{background:#000;border-radius:8px;margin:10px}
/* The overlay MUST be positioned from CSS, not an inline style: an inline
   display:flex overrides the [hidden] attribute, which left the dimmer
   permanently on top of the UI and made the tool unusable. */
#notebox{position:fixed;inset:0;background:rgba(0,0,0,.88);display:flex;
  flex-direction:column;align-items:center;justify-content:center;z-index:10}
#notebox[hidden]{display:none!important}
#refine{position:fixed;inset:0;background:rgba(0,0,0,.88);display:flex;
  flex-direction:column;align-items:center;justify-content:center;z-index:9}
#refine[hidden]{display:none!important}
[hidden]{display:none!important}
#done{font-size:22px;color:#4c9;margin-top:40px}
#help{color:#666;font-size:13px;margin-top:16px}
</style></head><body>
<div id=top>
<div id=prog></div>
<div id=name></div><div id=hint></div>
<canvas id=wave width=760 height=140></canvas>
<audio id=au></audio>
<div id=keys></div>
<div id=help>[space] replay &nbsp; [&larr;] back &nbsp; [s] skip/unsure &nbsp; label auto-advances</div>
<div id=recent style="margin-top:16px;font-size:12px;color:#888">recent (click to redo):</div>
<div id=recentlist style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;max-width:820px;margin:6px auto"></div>
</div>
<div id=notebox hidden>
  <div id=notetitle style="font-size:17px;margin-bottom:4px">Why unsure?</div>
  <div id=notehelp style="color:#888;font-size:12px;margin-bottom:12px"></div>
  <div id=noteerr style="color:#ff6b6b;font-size:13px;margin-bottom:10px;min-height:18px"></div>
  <input id=noteinput type=text autocomplete=off
     style="width:min(560px,80vw);padding:11px 13px;font-size:15px;border-radius:8px;
            border:1px solid #555;background:#181818;color:#eee">
</div>
<div id=refine hidden>
  <div id=reftitle style="font-size:17px;margin-bottom:4px"></div>
  <div style="color:#888;font-size:12px;margin-bottom:14px">
    optional &mdash; [enter] or [esc] to skip and move on</div>
  <div id=refkeys style="display:flex;flex-wrap:wrap;gap:9px;justify-content:center;max-width:640px"></div>
</div>
<div id=done hidden>All done — labels saved to the CSV. You can close this tab.</div>
<script>
let CLASSES=[], KEYS=[], cur=null, total=0, doneCount=0;
const au=document.getElementById('au'), cv=document.getElementById('wave'), cx=cv.getContext('2d');
async function boot(){
  const m=await (await fetch('/meta')).json();
  total=m.total; doneCount=m.done;
  // key order follows the GROUPED order so the pad reads left-to-right
  CLASSES=[]; (m.groups||[["",m.classes]]).forEach(g=>g[1].forEach(c=>CLASSES.push(c)));
  PERC=m.perc_subtypes||[]; REJ=m.reject_reasons||[]; NOTEC=m.note_classes||[]; NOTEREQ=m.note_required||[];
  KEYS='1234567890qwertyuiopadfghjklzxcvbnm'.split('').slice(0,CLASSES.length);  // no 's': reserved for skip/unsure
  const kd=document.getElementById('keys'); let i=0;
  (m.groups||[["",m.classes]]).forEach(g=>{
    const row=document.createElement('div'); row.className='grp';
    if(g[0]){const lb=document.createElement('div');lb.className='glab';lb.textContent=g[0];row.appendChild(lb);}
    const wrap=document.createElement('div'); wrap.className='gwrap';
    g[1].forEach(c=>{const d=document.createElement('div');d.className='k';
      d.innerHTML='<b>'+KEYS[i].toUpperCase()+'</b>'+c;d.onclick=()=>label(c);
      wrap.appendChild(d); i++;});
    row.appendChild(wrap); kd.appendChild(row);});
  next();
}
// Prefetch upcoming items so playback is instant. The sample drive is the
// slowest part of the loop; waiting on it once per label is the single biggest
// drag on labelling throughput.
const PRE={};           // id -> {url, peaks}
async function prefetch(){
  try{
    const ups=await (await fetch('/upcoming?n=5')).json();
    for(const u of ups){
      if(PRE[u.id])continue;
      PRE[u.id]={url:null,peaks:null};
      fetch('/audio/'+u.id).then(r=>r.blob())
        .then(b=>{if(PRE[u.id])PRE[u.id].url=URL.createObjectURL(b);}).catch(()=>{});
      fetch('/wave/'+u.id).then(r=>r.json())
        .then(j=>{if(PRE[u.id])PRE[u.id].peaks=j;}).catch(()=>{});
    }
    for(const k of Object.keys(PRE))
      if(!ups.some(u=>String(u.id)===k)){
        if(PRE[k]&&PRE[k].url)URL.revokeObjectURL(PRE[k].url);
        delete PRE[k];
      }
  }catch(e){}
}
async function next(){
  const r=await fetch('/next'); if(r.status===204){finish();return;}
  cur=await r.json();
  document.getElementById('prog').textContent='labelled '+doneCount+' / '+total;
  document.getElementById('name').textContent=cur.name;
  document.getElementById('hint').textContent=cur.hint?('evidence hint: '+cur.hint+'  (label what you HEAR)'):'';
  const p=PRE[cur.id];
  au.src=(p&&p.url)?p.url:('/audio/'+cur.id);
  au.play().catch(()=>{});
  if(p&&p.peaks)paint(p.peaks); else drawWave(cur.id);
  prefetch();
}
function paint(b){
  cx.clearRect(0,0,cv.width,cv.height);cx.strokeStyle='#0a84ff';cx.beginPath();
  b.forEach((v,i)=>{const x=i/b.length*cv.width,y=cv.height/2-(v*cv.height/2);
    i?cx.lineTo(x,y):cx.moveTo(x,y);});cx.stroke();
}
async function drawWave(id){
  try{paint(await (await fetch('/wave/'+id)).json());}catch(e){}
}
let PERC=[], REJ=[], NOTEC=[], NOTEREQ=[], pending=null, notePending=null;
function noteRequired(c){return NOTEREQ.indexOf(c)>=0;}
function showNote(c){
  notePending=c;
  const req=noteRequired(c);
  const el=document.getElementById('noteinput'); el.value='';
  document.getElementById('noteerr').textContent='';
  document.getElementById('notetitle').textContent =
    req ? ('"'+c+'" \u2014 what IS it? (required)') : ('"'+c+'" \u2014 why? (optional)');
  document.getElementById('notehelp').textContent = req
    ? 'Name the sound in plain words. [enter] saves \u00b7 [esc] cancels and returns to the labels.'
    : '[enter] saves \u00b7 [esc] skips the note';
  document.getElementById('notebox').hidden=false;
  setTimeout(()=>el.focus(),30);
}
function finishNote(save){
  const c=notePending;
  const el=document.getElementById('noteinput');
  const txt=el.value.trim();
  // A required note cannot be escaped and cannot be blank. Escape CANCELS the
  // label outright rather than committing an empty escape hatch -- the reviewer
  // is returned to the key pad with the file still queued.
  if(noteRequired(c)){
    if(!save){hideNote();return;}
    if(!txt){document.getElementById('noteerr').textContent=
      '"'+c+'" needs a note. Say what the sound is, or press [esc] to pick a different label.';
      el.focus();return;}
  }
  hideNote();
  if(c) commit(c, txt?{note:txt}:null);
}
function hideNote(){
  notePending=null;
  document.getElementById('notebox').hidden=true;
  document.getElementById('noteerr').textContent='';
}
async function commit(c,extras){
  if(!cur)return;
  const r=await fetch('/label',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:cur.id,label:c,extras:extras||{}})});
  if(!r.ok){
    // The server refused. Do NOT advance: reopen the note box with the reason,
    // so a refused row can never be mistaken for a saved one.
    let m='label refused'; try{m=(await r.json()).error||m;}catch(e){}
    showNote(c); document.getElementById('noteerr').textContent=m;
    return;
  }
  doneCount++; next(); refreshRecent();
}
function showRefine(c){
  // Optional refinement. Percussion gets acoustic subtypes because it is an
  // incoherent POSITIVE class; Other/none gets only a rejection reason, because
  // it is rejection material and its heterogeneity is intended.
  const isPerc = (c==='Percussion');
  const opts = isPerc?PERC:REJ;
  if(!opts.length){commit(c,null);return;}
  pending={cls:c, field:isPerc?'percussion_subtype':'rejection_reason', opts:opts};
  document.getElementById('reftitle').textContent =
    isPerc?('Percussion \u2014 which kind?'):('Other/none \u2014 why? (optional)');
  const kd=document.getElementById('refkeys'); kd.innerHTML='';
  opts.forEach((o,i)=>{const d=document.createElement('div');d.className='k';
    d.innerHTML='<b>'+(i+1)+'</b>'+o;d.onclick=()=>pickRefine(i);kd.appendChild(d);});
  document.getElementById('refine').hidden=false;
}
function pickRefine(i){
  const p=pending; hideRefine();
  if(!p)return;
  const e={}; if(i>=0&&i<p.opts.length) e[p.field]=p.opts[i];
  commit(p.cls, e);
}
function hideRefine(){document.getElementById('refine').hidden=true;}
async function label(c){
  if(!cur)return;
  if(NOTEC.indexOf(c)>=0){showNote(c);return;}
  if(c==='Percussion'||c==='Other/none'){showRefine(c);return;}
  commit(c,null);
}
async function refreshRecent(){
  const r=await (await fetch('/recent')).json(); const el=document.getElementById('recentlist');
  el.innerHTML='';
  r.forEach(x=>{const c=document.createElement('span');
    c.style.cssText='background:#222;border:1px solid #444;border-radius:6px;padding:4px 8px;cursor:pointer';
    c.textContent=x.label+' · '+x.name.slice(0,22);
    c.title='click to re-label '+x.name;
    c.onclick=async()=>{await fetch('/requeue',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:x.id})});doneCount=Math.max(0,doneCount-1);next();refreshRecent();};
    el.appendChild(c);});
}
async function back(){const r=await fetch('/back',{method:'POST'});
  if(r.ok){doneCount=Math.max(0,doneCount-1);next();}}
function finish(){document.getElementById('top').hidden=true;document.getElementById('done').hidden=false;}
document.onkeydown=e=>{
  if(notePending!==null){
    if(e.key==='Enter'){e.preventDefault();finishNote(true);}
    else if(e.key==='Escape'){e.preventDefault();finishNote(false);}
    return;                       // let every other key type into the box
  }
  if(pending&&!document.getElementById('refine').hidden){
    e.preventDefault();
    if(e.key==='Enter'||e.key==='Escape'){pickRefine(-1);return;}   // skip
    const n=parseInt(e.key,10);
    if(n>=1&&n<=pending.opts.length){pickRefine(n-1);}
    return;
  }
  if(e.key===' '){e.preventDefault();au.currentTime=0;au.play();}
  else if(e.key==='ArrowLeft')back();
  else if(e.key==='s'||e.key==='S')label('__skip__');
  else{const k=e.key.toLowerCase();const idx=KEYS.indexOf(k);if(idx>=0)label(CLASSES[idx]);}
};
boot();refreshRecent();prefetch();
</script></body></html>"""


class State:
    def __init__(self, items, csv_path, classes, groups=None):
        self.items = items; self.csv_path = csv_path; self.classes = classes
        self.groups = groups or [["", list(classes)]]
        self.session = time.strftime("%Y%m%dT%H%M%S")
        self.done = {}
        if os.path.exists(csv_path):
            with open(csv_path) as f:
                for row in csv.DictReader(f):
                    self.done[_canonical_id(row["id"])] = row["label"]
        self.order = [it for it in items if it["id"] not in self.done]
        self.history = []
        self.lock = threading.Lock()

    def next_item(self):
        with self.lock:
            return self.order[0] if self.order else None

    def record(self, _id, label, extras=None):
        # THE contract. The browser also refuses an empty escape hatch, but the
        # browser is not the guarantee: a stale tab, a replayed request or a
        # future UI edit would reopen the exact hole that cost the granularity
        # sprint 48 rows. Nothing reaches the CSV without passing here.
        _id = _canonical_id(_id)
        extras = extras or {}
        if label in NOTE_REQUIRED:
            note = (extras.get("note") or "").strip()
            alt = (extras.get("not_in_list_label") or "").strip()
            if not note and not alt:
                raise EscapeHatchError(
                    f"'{label}' requires a written note saying what the sound "
                    f"actually is. Without one the row records only that the "
                    f"option list was wrong, which is unrecoverable.")
        with self.lock:
            it = next((x for x in self.order if x["id"] == _id), None)
            if not it: return
            self.order.pop(0); self.history.append(it)
            self.done[_id] = label
            row = {"id": _id, "label": label, "path": it["path"],
                   "hint": it["hint"], "labelling_session": self.session}
            row.update(derive_meta(it["path"]))
            for k, v in extras.items():
                if k in SCHEMA and v not in (None, ""):
                    row[k] = v
            # Park the parsed candidates in the row so recovery does not depend
            # on re-running the parser over a CSV months later.
            if label in NOTE_CLASSES and (row.get("note") or "").strip():
                pr = parse_note(row["note"])
                if pr["candidates"] and not (row.get("not_in_list_label") or ""):
                    row["not_in_list_label"] = pr["candidates"][0]
                if pr["form"] and not (row.get("temporal_form") or ""):
                    row["temporal_form"] = pr["form"]
            self._append(row)

    def _append(self, row):
        """Append one row, upgrading a legacy 4-column file in place first."""
        need_upgrade = False
        if os.path.exists(self.csv_path):
            with open(self.csv_path) as f:
                hdr = f.readline().strip().split(",")
            need_upgrade = hdr != SCHEMA
        else:
            with open(self.csv_path, "w", newline="") as f:
                csv.DictWriter(f, SCHEMA).writeheader()
        if need_upgrade:
            self._rewrite(list(csv.DictReader(open(self.csv_path))))
        with open(self.csv_path, "a", newline="") as f:
            csv.DictWriter(f, SCHEMA, extrasaction="ignore").writerow(
                {k: row.get(k, "") for k in SCHEMA})

    def _rewrite(self, rows):
        """Rewrite the whole file in SCHEMA order, preserving unknown-blank
        values. Used by upgrade, requeue and go-back so none of them can silently
        drop columns the way the old hardcoded 4-column writer did."""
        with open(self.csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, SCHEMA, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: (r.get(k) or "") for k in SCHEMA})

    def recent(self, n=15):
        with self.lock:
            if not os.path.exists(self.csv_path): return []
            rows=list(csv.DictReader(open(self.csv_path)))
            out=[]
            for r in rows[-n:][::-1]:
                out.append({"id":_canonical_id(r["id"]),"label":r["label"],
                            "name":os.path.basename(r["path"])})
            return out

    def requeue(self, _id):
        # move a previously-labelled item back to the front so it can be redone,
        # and drop its saved label. Works regardless of in-memory history.
        _id = _canonical_id(_id)
        with self.lock:
            it=next((x for x in self.items if x["id"]==_id), None)
            if not it: return False
            self.done.pop(_id, None)
            self.order=[x for x in self.order if x["id"]!=_id]
            self.order.insert(0, it)
            rows=[r for r in csv.DictReader(open(self.csv_path))] if os.path.exists(self.csv_path) else []
            rows=[r for r in rows if _canonical_id(r["id"])!=_id]
            self._rewrite(rows)
            return True

    def go_back(self):
        with self.lock:
            if not self.history: return False
            it = self.history.pop(); self.order.insert(0, it)
            self.done.pop(it["id"], None)
            # rewrite csv without the last entry
            rows = [r for r in csv.DictReader(open(self.csv_path))] if os.path.exists(self.csv_path) else []
            rows = [r for r in rows if _canonical_id(r["id"]) != it["id"]]
            self._rewrite(rows)
            return True


MAX_PREVIEW_SECONDS = 20.0
CACHE_MAX = 48


class Decoded:
    """Decode each file ONCE and serve both the audio and the waveform from it.

    The original code read every file twice per item -- once for /audio and again
    for /wave -- and did it only when the browser asked, so each label paid two
    round trips to the sample drive while the user waited. Labelling throughput
    is now the whole game (selection strategy was measured and does not matter),
    so this caches decoded results and warms them ahead of the cursor.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.cache = OrderedDict()

    def get(self, path):
        with self.lock:
            hit = self.cache.get(path)
            if hit is not None:
                self.cache.move_to_end(path)
                return hit
        try:
            y, sr = sf.read(path, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(1)
            if len(y) > int(sr * MAX_PREVIEW_SECONDS):
                y = y[: int(sr * MAX_PREVIEW_SECONDS)]
            buf = io.BytesIO()
            sf.write(buf, y, sr, format="WAV", subtype="PCM_16")
            step = max(1, len(y) // 760)
            peaks = [float(y[i]) for i in range(0, len(y), step)][:760]
            val = (buf.getvalue(), json.dumps(peaks).encode())
        except Exception:
            val = (None, b"[]")
        with self.lock:
            self.cache[path] = val
            while len(self.cache) > CACHE_MAX:
                self.cache.popitem(last=False)
        return val


def start_prefetcher(state, decoder, depth=6):
    """Warm the cache for the items just ahead of the cursor, continuously."""
    def loop():
        while True:
            try:
                with state.lock:
                    ahead = [x["path"] for x in state.order[:depth]]
                for p in ahead:
                    decoder.get(p)
            except Exception:
                pass
            time.sleep(0.35)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def make_handler(state, decoder):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, ctype, body):
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            u = urlparse(self.path); p = u.path
            if p == "/":
                self._send(200, "text/html", HTML.encode())
            elif p == "/meta":
                self._send(200, "application/json", json.dumps(
                    {"classes": state.classes, "total": len(state.items),
                     "done": len(state.done), "groups": state.groups,
                     "perc_subtypes": PERCUSSION_SUBTYPES,
                     "reject_reasons": REJECTION_REASONS,
                     "note_classes": list(NOTE_CLASSES),
                     "note_required": list(NOTE_REQUIRED)}).encode())
            elif p == "/recent":
                self._send(200, "application/json", json.dumps(state.recent()).encode())
            elif p == "/next":
                it = state.next_item()
                if not it: self.send_response(204); self.end_headers(); return
                self._send(200, "application/json", json.dumps(
                    {"id": it["id"], "name": it.get("display_name", os.path.basename(it["path"])),
                     "hint": it["hint"]}).encode())
            elif p == "/upcoming":
                k = int((parse_qs(u.query).get("n") or ["5"])[0])
                with state.lock:
                    ups = [{"id": x["id"], "name": x.get("display_name", os.path.basename(x["path"])),
                            "hint": x["hint"]} for x in state.order[:k]]
                self._send(200, "application/json", json.dumps(ups).encode())
            elif p.startswith("/audio/"):
                self._serve_audio(_canonical_id(p.split("/")[-1]))
            elif p.startswith("/wave/"):
                self._serve_wave(_canonical_id(p.split("/")[-1]))
            else:
                self.send_response(404); self.end_headers()
        def do_POST(self):
            u = urlparse(self.path); ln = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(ln) if ln else b"{}"
            if u.path == "/label":
                d = json.loads(body)
                try:
                    state.record(d["id"], d["label"], d.get("extras"))
                except EscapeHatchError as e:
                    self._send(422, "application/json",
                               json.dumps({"ok": 0, "error": str(e)}).encode())
                    return
                self._send(200, "application/json", b'{"ok":1}')
            elif u.path == "/back":
                ok = state.go_back()
                self.send_response(200 if ok else 400); self.end_headers()
            elif u.path == "/requeue":
                d = json.loads(body); ok = state.requeue(_canonical_id(d["id"]))
                self.send_response(200 if ok else 400); self.end_headers()
            else:
                self.send_response(404); self.end_headers()
        def _item(self, _id):
            _id = _canonical_id(_id)
            return next((x for x in state.items if x["id"] == _id), None)
        def _serve_audio(self, _id):
            it = self._item(_id)
            if not it: self.send_response(404); self.end_headers(); return
            wav, _ = decoder.get(it["path"])
            if wav is None: self.send_response(404); self.end_headers(); return
            self._send(200, "audio/wav", wav)
        def _serve_wave(self, _id):
            it = self._item(_id)
            if not it: self._send(200, "application/json", b"[]"); return
            _, peaks = decoder.get(it["path"])
            self._send(200, "application/json", peaks)
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="which", choices=list(SETS), default="drums")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--port", type=int, default=8747)
    ap.add_argument("--manifest", default=None,
                    help="explicit manifest path (e.g. the domain-coverage batch)")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after the first N manifest items (non-destructive: "
                         "the manifest file is untouched, so raising the limit "
                         "later resumes exactly where it left off)")
    ap.add_argument("--csv", default=None,
                    help="explicit output CSV; keep new batches in their own file "
                         "so ids cannot collide with an existing corpus")
    a = ap.parse_args()

    manifest_path = a.manifest or os.path.join(SCRIPT_DIR,
                                               f"label_manifest_{a.which}.json")
    if os.path.exists(manifest_path):
        items = load_review_items(manifest_path)
        print(f"loaded existing manifest: {len(items)} items")
    else:
        if a.which == "fft_physics":
            raise SystemExit("--manifest is required for --set fft_physics")
        print(f"building '{a.which}' manifest of ~{a.n} files...")
        items = build_manifest(a.which, a.n, a.seed)
        json.dump(items, open(manifest_path, "w"))
        print(f"manifest: {len(items)} files -> {manifest_path}")

    if a.limit and a.limit < len(items):
        items = items[:a.limit]
        print(f"capped at {a.limit} items (manifest file unchanged)")

    csv_path = a.csv or os.path.join(SCRIPT_DIR, f"verified_{a.which}.csv")
    state = State(items, csv_path, SETS[a.which],
                  [[g, cs] for g, cs in grouped_classes(a.which)])
    print(f"resuming: {len(state.done)}/{len(items)} already labelled" if state.done
          else f"fresh start: {len(items)} to label")

    decoder = Decoded()
    start_prefetcher(state, decoder)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(state, decoder))
    url = f"http://localhost:{a.port}"
    print(f"\n  Open {url}\n  labels save live to {os.path.basename(csv_path)} (Ctrl-C to stop; resumable)\n")
    try: webbrowser.open(url)
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped; progress saved.")


if __name__ == "__main__":
    main()
