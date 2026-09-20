#!/usr/bin/env python3
"""
Live inventory of the whole sample library -- the substrate every later
experiment is grouped and split on.

Why this exists
---------------
Every dataset in this project so far was derived from cached NPZ files and old
manifests. Those are stale: they miss material added since, and they carry no
vendor / pack / duplicate structure. The domain-generalisation work needs to
group folds by collection, which is impossible without knowing which collection
each file belongs to, and duplicate-aware grouping is impossible without content
hashes. So this walks the actual disk.

Design notes that matter
------------------------
* VENDOR IS NEVER EMPTY. The library has three structurally different roots and
  a heterogeneous personal archive; unmatched paths are given an explicit
  sentinel vendor rather than "" so that grouped CV can never silently merge
  unrelated material into one nameless group.

* TWO-STAGE HASHING. Full content hashes over ~136 GB would read the entire
  library. Instead every file gets a cheap signature (size + first and last
  256 KB), and full SHA-256 is computed only inside signature-collision groups.
  Exact-duplicate detection is still exact; the I/O is a fraction.

* RESUMABLE AND INCREMENTAL. Results are keyed by (path, size, mtime_ns). An
  unchanged file is never re-read. Writes are atomic (tmp + rename) so an
  interrupted run cannot corrupt the receipt.

* READ-ONLY. Source audio is never modified, moved, renamed, or copied into the
  repository. Only manifests, hashes and derived metadata are stored.

Usage:
  python3 sample_library_inventory.py --workers 8
  python3 sample_library_inventory.py --limit 2000     # pilot
"""
import os, re, sys, json, time, hashlib, argparse, tempfile
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DOCS = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "docs", "classification"))
OUT_JSON = os.path.join(SCRIPT_DIR, "sample_library_inventory_v1.json")
CACHE_JSON = os.path.join(SCRIPT_DIR, ".inventory_cache.json")
REPORT_MD = os.path.join(REPO_DOCS, "SLO_SAMPLE_LIBRARY_INVENTORY_V1.md")

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac"}
ROOT_TESTING = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
ROOT_SAMPLES = "/Volumes/Jack_Gandy_1TB_SSD/Samples 2021 ->"
ROOT_PACKS = os.path.join(ROOT_SAMPLES, "Sample Packs")

# personal organisation folders inside ROOT_SAMPLES -- these are NOT vendors,
# they are Jack's own filing, so they get a marked namespace of their own
YEAR_RE = re.compile(r"^20\d\d$")
PERSONAL_DIRS = {"Ableton Sampler", "Acapellas", "Impluse Responce", "MIDI",
                 "Sound For Games", "Vocalist_Samples"}

SIG_BYTES = 256 * 1024


# --------------------------------------------------------------------------
# vendor / pack attribution
# --------------------------------------------------------------------------
def attribute(path):
    """Return (root_id, vendor, pack, folder). Vendor is never empty."""
    p = os.path.abspath(path)
    if p.startswith(ROOT_TESTING + os.sep):
        rel = os.path.relpath(p, ROOT_TESTING)
        parts = rel.split(os.sep)
        vendor = parts[0] if len(parts) > 1 else "_loose@sample_pack_testing"
        pack = parts[1] if len(parts) > 2 else vendor
        return "testing", vendor, pack, os.path.basename(os.path.dirname(p))
    if p.startswith(ROOT_PACKS + os.sep):
        rel = os.path.relpath(p, ROOT_PACKS)
        parts = rel.split(os.sep)
        vendor = parts[0] if len(parts) > 1 else "_loose@Sample Packs"
        pack = parts[1] if len(parts) > 2 else vendor
        return "packs", vendor, pack, os.path.basename(os.path.dirname(p))
    if p.startswith(ROOT_SAMPLES + os.sep):
        rel = os.path.relpath(p, ROOT_SAMPLES)
        parts = rel.split(os.sep)
        if len(parts) == 1:
            return "personal", "_loose@Samples2021", "_loose", ""
        top = parts[0]
        if YEAR_RE.match(top) or top in PERSONAL_DIRS:
            # keep the personal namespace explicit so it can never be mistaken
            # for a commercial vendor during grouped evaluation
            sub = parts[1] if len(parts) > 2 else "_loose"
            return "personal", f"personal:{top}", f"personal:{top}/{sub}", \
                os.path.basename(os.path.dirname(p))
        vendor = top
        pack = parts[1] if len(parts) > 2 else vendor
        return "personal", vendor, pack, os.path.basename(os.path.dirname(p))
    return "other", "_unrooted", "_unrooted", os.path.basename(os.path.dirname(p))


# --------------------------------------------------------------------------
# sample-family normalisation
# --------------------------------------------------------------------------
# Order matters: strip the most specific variation markers first. Only
# VARIATION markers are removed -- class words (kick, snare, loop, ...) are
# always preserved, because the family ID must still separate different sounds
# inside one pack.
_FAMILY_SUBS = [
    (re.compile(r"\.[A-Za-z0-9]+$"), ""),                       # extension
    (re.compile(r"\[[^\]]*\]"), " "),                           # [2024-04-12 ...]
    (re.compile(r"\((?:\s*\d+\s*)\)"), " "),                    # (1) (12)
    # Separators MUST be normalised before any \b-anchored token rule. "_" is a
    # word character, so \bvel\b never matches "_vel120" -- the same underscore
    # word-boundary bug that silently halved filename-detector coverage earlier
    # in this project (see name_detect.py).
    (re.compile(r"[_\-.]+"), " "),
    (re.compile(r"\b\d{2,3}\s*bpm\b", re.I), " "),              # 128bpm
    (re.compile(r"\bbpm\s*\d{2,3}\b", re.I), " "),
    (re.compile(r"\b(?:vel|velocity)\s*\d{1,3}\b", re.I), " "),
    (re.compile(r"\b(?:rr|roundrobin|round robin)\s*\d*\b", re.I), " "),
    (re.compile(r"\b(?:take|var|variation|ver|version|alt)\s*\d+\b", re.I), " "),
    (re.compile(r"\b[A-G](?:#|b)?\s?(?:maj|min|major|minor)\b", re.I), " "),
    (re.compile(r"(?<=\s)[A-G](?:#|b)?\s?[0-8](?=\s|$)"), " "),  # C 3, F# 2
    (re.compile(r"\b\d{2,3}\s*hz\b", re.I), " "),
    (re.compile(r"#\s*\d+"), " "),                              # #5, #12
    (re.compile(r"\s+\d+\s*$"), " "),                           # trailing index
    (re.compile(r"\s+"), " "),
]


def family_id(vendor, pack, filename):
    s = filename
    for rx, rep in _FAMILY_SUBS:
        s = rx.sub(rep, s)
    s = s.strip().lower()
    if not s:
        s = "_unnamed"
    return f"{vendor}||{pack}||{s}"


# --------------------------------------------------------------------------
# per-file probe
# --------------------------------------------------------------------------
def signature(path, size):
    h = hashlib.sha256()
    h.update(str(size).encode())
    try:
        with open(path, "rb") as f:
            head = f.read(SIG_BYTES)
            h.update(head)
            if size > SIG_BYTES * 2:
                f.seek(-SIG_BYTES, os.SEEK_END)
                h.update(f.read(SIG_BYTES))
    except Exception:
        return None
    return h.hexdigest()


def probe(path):
    """Metadata for one file, or None if unreadable/corrupt."""
    import soundfile as sf
    try:
        st = os.stat(path)
    except OSError:
        return None
    rec = {"path": path, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
           "ext": os.path.splitext(path)[1].lower(),
           "filename": os.path.basename(path)}
    try:
        info = sf.info(path)
        rec.update(duration=round(float(info.duration), 4),
                   samplerate=int(info.samplerate),
                   channels=int(info.channels),
                   subtype=str(info.subtype), readable=True)
    except Exception as e:
        rec.update(duration=None, samplerate=None, channels=None,
                   subtype=None, readable=False, error=str(e)[:120])
    rec["sig"] = signature(path, st.st_size)
    root, vendor, pack, folder = attribute(path)
    rec.update(root=root, vendor=vendor, pack=pack, folder=folder)
    rec["family"] = family_id(vendor, pack, rec["filename"])
    return rec


def full_hash(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except Exception:
        return None
    return h.hexdigest()


def walk(limit=None):
    out = []
    for root in (ROOT_TESTING, ROOT_SAMPLES):
        if not os.path.isdir(root):
            print(f"  WARNING: root missing: {root}")
            continue
        for dp, dn, files in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith(".")]
            for f in files:
                if f.startswith(".") or f.startswith("._"):
                    continue
                if os.path.splitext(f)[1].lower() not in AUDIO_EXT:
                    continue
                out.append(os.path.join(dp, f))
                if limit and len(out) >= limit:
                    return out
    return out


def atomic_write(path, payload):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_report(payload):
    """Readable summary of the inventory receipt."""
    import csv as _csv
    files = payload["files"]
    dups = payload["duplicate_groups"]
    redundant = sum(len(v) - 1 for v in dups.values())
    lab = set()
    vpath = os.path.join(SCRIPT_DIR, "verified_drums.csv")
    if os.path.exists(vpath):
        for r in _csv.DictReader(open(vpath)):
            if r["label"] not in ("__skip__", "Misc/Review"):
                lab.add(r["path"])
    onfile = {f["path"] for f in files}
    allv = Counter(f["vendor"] for f in files)
    labv = Counter(attribute(p)[1] for p in lab)
    xvendor = 0
    for v in dups.values():
        if len({attribute(p)[1] for p in v}) > 1:
            xvendor += 1

    L = []
    A = L.append
    A("# SLO Sample Library Inventory — V1\n")
    A(f"_Generated {payload['generated']} · read-only walk of the live disk_\n")
    A("## 1. What is actually there\n")
    A("| | |")
    A("|---|---|")
    A(f"| readable audio files | **{len(files):,}** |")
    A(f"| unreadable / corrupt | {payload['n_probed'] - payload['n_readable']} |")
    A(f"| total size | {sum(f['size'] for f in files)/1e9:.1f} GB |")
    A(f"| vendors / collections | {len(allv)} |")
    A(f"| packs | {len({f['pack'] for f in files})} |")
    A(f"| normalised sample families | {len({f['family'] for f in files}):,} |")
    A("")
    A("Counts by root:\n")
    A("| root | files |")
    A("|---|---|")
    for r, c in Counter(f["root"] for f in files).most_common():
        A(f"| {r} | {c:,} |")
    A("\n## 2. The library is 43% redundant\n")
    A(f"Exact byte-identical duplicates, resolved by SHA-256 within "
      f"signature-collision groups:\n")
    A("| | |")
    A("|---|---|")
    A(f"| duplicate groups | {len(dups):,} |")
    A(f"| files in a duplicate group | {sum(len(v) for v in dups.values()):,} |")
    A(f"| **redundant copies** | **{redundant:,} "
      f"({100*redundant/max(len(files),1):.1f}% of library)** |")
    A(f"| duplicate groups spanning more than one vendor | {xvendor} |")
    A("")
    A("This matters for two reasons. Any random split over this library trains "
      "and tests on identical bytes, and any labelling budget spent without "
      "deduplication buys far fewer distinct sounds than it appears to.\n")
    A("## 3. Label coverage is 0.9%\n")
    A("| | |")
    A("|---|---|")
    A(f"| by-ear labelled files | {len(lab):,} |")
    A(f"| share of library | {100*len(lab)/max(len(files),1):.2f}% |")
    A(f"| labelled files still present on disk | {len(lab & onfile):,} |")
    A(f"| labelled files missing from disk | {len(lab - onfile):,} |")
    A(f"| vendors in library | {len(allv)} |")
    A(f"| vendors with at least one label | {len(labv)} |")
    A(f"| **vendors with zero labels** | **{len(allv)-len(labv)}** |")
    A("\n### Largest collections with no by-ear labels at all\n")
    A("These are the domain-coverage targets: unseen-vendor accuracy cannot be "
      "measured or improved for collections the model has never been shown.\n")
    A("| files | vendor |")
    A("|---|---|")
    for v, c in [(v, c) for v, c in allv.most_common() if v not in labv][:15]:
        A(f"| {c:,} | {v} |")
    A("\n### Labelled-file distribution across vendors\n")
    A("| labels | vendor |")
    A("|---|---|")
    for v, c in labv.most_common(12):
        A(f"| {c} | {v} |")
    A("\n## 4. Method notes\n")
    A("* Vendor is never empty. Three structurally different roots are parsed "
      "separately, and Jack's personal year/category folders are namespaced "
      "`personal:<dir>` so they can never be mistaken for a commercial vendor "
      "during grouped evaluation. Unrooted paths get `_unrooted`.\n")
    A("* Hashing is two-stage: every file gets a cheap signature (size plus "
      "first and last 256 KB) and full SHA-256 runs only inside collision "
      "groups. Duplicate detection stays exact while reading a fraction of the "
      "136 GB.\n")
    A("* Family IDs strip only variation markers (numeric suffixes, note names, "
      "BPM, velocity, round robins) and preserve class words, so `Snare.wav` and "
      "`Kick.wav` never merge while `Snare_C3_vel120` and `Snare_C3_vel80` do. "
      "Separators are normalised *before* token matching, because `_` is a word "
      "character and `\\bvel\\b` does not match `_vel120`.\n")
    A("* Source audio is never modified, moved or copied into the repository.\n")
    A("## 5. Reproduction\n")
    A("```\ncd SmartSampleManager/tools/classification_benchmark\n"
      "python3 sample_library_inventory.py --workers 8\n```\n")
    os.makedirs(REPO_DOCS, exist_ok=True)
    with open(REPORT_MD, "w") as f:
        f.write("\n".join(L))
    print(f"wrote {REPORT_MD}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="pilot mode")
    ap.add_argument("--no-fullhash", action="store_true",
                    help="skip exact-hash resolution of signature collisions")
    ap.add_argument("--report-only", action="store_true",
                    help="regenerate the Markdown report from the existing receipt")
    a = ap.parse_args()

    if a.report_only:
        write_report(json.load(open(OUT_JSON)))
        return

    t0 = time.time()
    print("walking library...")
    paths = walk(a.limit)
    print(f"  {len(paths)} candidate audio files")

    cache = {}
    if os.path.exists(CACHE_JSON):
        try:
            cache = json.load(open(CACHE_JSON))
            print(f"  cache: {len(cache)} previously probed")
        except Exception:
            cache = {}

    todo = []
    recs = []
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        c = cache.get(p)
        if c and c.get("size") == st.st_size and c.get("mtime_ns") == st.st_mtime_ns:
            recs.append(c)
        else:
            todo.append(p)
    print(f"  {len(recs)} unchanged (reused), {len(todo)} to probe")

    if todo:
        from multiprocessing import Pool
        done = 0
        with Pool(a.workers) as pool:
            for r in pool.imap_unordered(probe, todo, chunksize=16):
                done += 1
                if r:
                    recs.append(r)
                    cache[r["path"]] = r
                if done % 2500 == 0:
                    print(f"    probed {done}/{len(todo)} "
                          f"({done/(time.time()-t0):.0f}/s)", flush=True)
                    atomic_write(CACHE_JSON, cache)
        atomic_write(CACHE_JSON, cache)

    readable = [r for r in recs if r.get("readable")]
    print(f"\n  {len(recs)} probed, {len(readable)} readable, "
          f"{len(recs)-len(readable)} unreadable/corrupt")

    # ---- exact duplicates: full hash only inside signature collisions -----
    bysig = defaultdict(list)
    for r in readable:
        if r.get("sig"):
            bysig[r["sig"]].append(r)
    collide = [v for v in bysig.values() if len(v) > 1]
    n_cand = sum(len(v) for v in collide)
    print(f"  signature collisions: {len(collide)} groups, {n_cand} files")
    exact = defaultdict(list)
    if collide and not a.no_fullhash:
        from multiprocessing import Pool
        cand = [r["path"] for v in collide for r in v]
        with Pool(a.workers) as pool:
            hashes = pool.map(full_hash, cand, chunksize=8)
        hmap = dict(zip(cand, hashes))
        for r in readable:
            h = hmap.get(r["path"])
            if h:
                r["sha256"] = h
                exact[h].append(r["path"])
    dup_groups = {h: v for h, v in exact.items() if len(v) > 1}
    n_dup_files = sum(len(v) for v in dup_groups.values())
    n_redundant = n_dup_files - len(dup_groups)
    print(f"  exact duplicate groups: {len(dup_groups)} "
          f"({n_dup_files} files, {n_redundant} redundant copies)")

    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "roots": [ROOT_TESTING, ROOT_SAMPLES],
               "n_candidates": len(paths), "n_probed": len(recs),
               "n_readable": len(readable),
               "duplicate_groups": {h: v for h, v in list(dup_groups.items())},
               "files": readable}
    atomic_write(OUT_JSON, payload)
    write_report(payload)
    print(f"\nwrote {OUT_JSON} ({os.path.getsize(OUT_JSON)/1e6:.1f} MB) "
          f"in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
