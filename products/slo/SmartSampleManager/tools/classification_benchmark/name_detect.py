#!/usr/bin/env python3
"""
Filename synonym detector. Ordered, word-boundary, most-specific-first.
Returns (class, matched_token) or (None, None).

Validated against by-ear ground truth (verified_drums.csv), so each token's
real precision is known rather than assumed -- the previous keyword labeller
was only 71.9% accurate on drums because it matched folders fuzzily and had a
thin vocabulary. High-precision tokens here can be trusted outright; the rest
defer to the acoustic detector.
"""
import re

# (class, [regex tokens]). ORDER MATTERS: specific loop combos before bare
# instrument tokens, bare "loop" last. \b word boundaries avoid substring
# accidents (e.g. 'kick' inside a word). Matched case-insensitively.
RULES = [
    # --- specific loop combinations first ---
    ("Kick Loop",       [r"kick\s*loop", r"808\s*loop"]),
    ("Snare Loop",      [r"snare\s*loop"]),
    ("Top Loop",        [r"top\s*loop", r"drum\s*top", r"\btoploop\b"]),   # bare "tops" removed: collided with Hi-Hat Loop
    ("Drum Loop",       [r"drum\s*loop", r"beat\s*loop", r"\bbreak\b", r"drum\s*break", r"full\s*(drum|beat)"]),
    ("Hi-Hat Loop",     [r"(hi[\s-]*hat|hat|hh)\s*loop", r"hat\s*groove"]),
    ("Percussion Loop", [r"perc(ussion)?\s*loop", r"(conga|bongo|shaker|tamb|cajon|clave|perc)\s*loop", r"perc\s*groove"]),
    ("Bass Loop",       [r"bass\s*loop", r"(bass|808|sub)\s*(line|riff|groove)", r"bassline"]),
    ("Foley Loop",      [r"foley\s*loop", r"(texture|ambience|ambient)\s*loop"]),
    ("Chord Loop",      [r"chord\s*loop", r"chord\s*prog", r"(melody|melodic|harmony)\s*loop",
                         r"\bprogression\b"]),   # bare "chord(s)" removed: 0.0% precision, usually a synth sound

    # --- Vocal specific ---
    ("Vocal Chop",      [r"vocal\s*chop", r"vox\s*chop", r"\bchop\b"]),
    ("Vocal Lead",      [r"vocal\s*lead", r"vox\s*lead", r"vocal\s*hook", r"\bacapella\b", r"vocal\s*stem"]),

    # --- Instrument specific (melodic/tonal) ---
    ("Pad",             [r"\bpad\b", r"synth\s*pad", r"\bdrone\b", r"ambient\s*pad", r"atmosphere\s*pad"]),
    ("Piano",           [r"\bpiano\b", r"\bkeys?\b", r"\brhodes\b", r"\bwurlitzer\b", r"\bclav(inet)?\b"]),
    ("Guitar",          [r"\bguit(ar)?\b", r"\bgt[r1-9]?\b", r"electric\s*guit", r"acoustic\s*guit"]),
    ("Pluck",           [r"\bpluck\b", r"\bmarimba\b", r"\bkalimba\b", r"\bharp\b", r"\bkoto\b"]),
    ("Lead",            [r"\blead\b", r"synth\s*lead", r"solo\s*lead"]),
    ("Brass",           [r"\bbrass\b", r"\bhorn\b", r"\btrumpet\b", r"\bsax(ophone)?\b", r"\btrombone\b"]),
    ("Strings",         [r"\bstrings?\b", r"\bviolin\b", r"\bcello\b", r"\bviola\b", r"\borchestra\b"]),
    ("Organ",           [r"\borgan\b", r"\bhammond\b", r"\bb3\b"]),

    # --- Sound Design / FX ---
    ("Riser",           [r"\briser\b", r"\buplift(er)?\b", r"sweep\s*up", r"build\s*up"]),
    ("Downlifter",      [r"\bdownlift(er)?\b", r"\bfall(er)?\b", r"sub\s*drop"]),
    ("Impact",          [r"\bimpact\b", r"sub\s*hit", r"cinematic\s*impact",
                         r"\bboom\b", r"\bdownlifter?\b"]),   # "hit" removed: 38.5% precision, it fires on any percussive hit

    # --- One-shots (specific drums & perc) ---
    ("Rimshot",         [r"\brim\s*shot\b", r"\brimshot\b", r"\brim\b", r"cross\s*stick", r"x[\s-]*stick"]),
    ("Kick",            [r"\bkick\b", r"\bkik\b", r"\bbd\b", r"bass\s*drum", r"\b808\b(?!.*loop)"]),
    ("Snare",           [r"\bsnare\b", r"\bsn\b", r"\bsnr\b"]),
    # "sd" REMOVED: measured 0% precision on the by-ear corpus -- 6 of its 8
    # files are KICKS, not snares. That is an identity error, not a granularity
    # one, and it was actively steering kicks into Snare.
    ("Clap",            [r"\bclap\b", r"\bclp\b", r"hand\s*clap"]),
    # "snap" REMOVED: measured 14% precision -- 6 of 7 are recorded Foley
    # snaps, not claps. This was the single largest source of filename
    # overriding correct audio.
    ("Crash",           [r"\bcrash\b", r"\bsplash\b", r"\bchina\b", r"\bcymbal\b"]),
    ("Ride",            [r"\bride\b", r"ride\s*cymbal"]),
        ("Hi-Hat",          [r"\bhi[\s-]*hat\b", r"\bhat\b", r"\bhh\b", r"\bchh\b", r"\bohh\b", r"open\s*hat", r"closed\s*hat"]),
    ("Drum Fill",       [r"drum\s*fill", r"snare\s*fill", r"\bfill\b"]),
    ("Percussion",   # includes tom tokens: Tom is a SUBTYPE of Percussion, not a class
           [r"\bperc(ussion)?\b", r"\bconga\b", r"\bbongo\b", r"\bshaker\b", r"\bshake\b",
                         r"\btamb(ourine)?\b", r"\bcowbell\b", r"\bclave\b", r"\bwoodblock\b",
                         r"\bguiro\b", r"\bcabasa\b", r"\bagogo\b", r"\bdjembe\b", r"\bcajon\b", r"\btimbale\b", r"\btom\b", r"\btoms\b", r"floor\s*tom", r"rack\s*tom"]),
    ("Foley",           [r"\bfoley\b", r"found\s*sound", r"\bfield\b", r"household", r"footstep", r"\bdoor\b", r"\bwater\b"]),
    # --- generic loop last ---
    ("Loop",            [r"\bloop\b", r"\bgroove\b", r"\d{2,3}\s*bpm", r"\bbpm\b"]),
]
COMPILED = [(c, [re.compile(t, re.I) for t in toks]) for c, toks in RULES]

def detect(filename):
    # Normalise separators: underscores/dots/dashes are word chars to regex, so
    # '808_kick' would fail \bkick\b and 'Drum_Loop' would fail 'drum\s*loop'.
    # Collapsing them to spaces makes \b and \s* behave as intended.
    import re as _re
    filename = _re.sub(r'[_.\-]+', ' ', filename)
    for c, toks in COMPILED:
        for t in toks:
            m = t.search(filename)
            if m: return c, m.group(0)
    return None, None

if __name__ == "__main__":
    import csv, os
    from collections import defaultdict, Counter
    rows = [r for r in csv.DictReader(open("verified_drums.csv")) if r["label"] not in ("__skip__","Misc/Review")]
    per = defaultdict(lambda: [0,0])   # class -> [correct, total matched]
    tokstat = defaultdict(lambda: [0,0])
    matched = agree = 0
    confusion = defaultdict(Counter)
    for r in rows:
        name = os.path.basename(r["path"])
        pred, tok = detect(name)
        if pred is None: continue
        matched += 1
        ok = (pred == r["label"])
        agree += ok
        per[pred][1] += 1; per[pred][0] += ok
        tokstat[tok.lower()][1] += 1; tokstat[tok.lower()][0] += ok
        if not ok: confusion[pred][r["label"]] += 1
    print(f"filename detector: matched {matched}/{len(rows)} files "
          f"({100*matched/len(rows):.0f}% coverage), {100*agree/matched:.1f}% precision vs ear\n")
    print("per predicted class:")
    for c in sorted(per, key=lambda k:-per[k][1]):
        ok,tot = per[c]
        bad = ", ".join(f"{k}:{v}" for k,v in confusion[c].most_common(2))
        print(f"  {c:>16} {tot:4d} matched  {100*ok/tot:5.1f}%   {('misses: '+bad) if bad else ''}")
    print("\nlowest-precision tokens (defer these to acoustic):")
    weak=[(t,s) for t,s in tokstat.items() if s[1]>=3 and s[0]/s[1]<0.7]
    for t,s in sorted(weak, key=lambda x:x[1][0]/x[1][1])[:10]:
        print(f"  '{t}': {100*s[0]/s[1]:.0f}% ({s[0]}/{s[1]})")
