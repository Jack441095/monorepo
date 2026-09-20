#!/usr/bin/env python3
"""
Regression tests for the labelling tool.

The schema extension touches the file that holds the only ground truth in this
project. The risk is not that a new field fails to save -- it is that a rewrite
path silently drops a column, or that an existing CSV stops loading. These test
the properties that protect Jack's existing 597 labels.

Run:  python3 test_label_tool.py
"""
import os, sys, csv, json, shutil, tempfile, threading
import urllib.request as U

SD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SD)
import label_tool as lt   # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def serve(state, port):
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", port), lt.make_handler(state, lt.Decoded()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def post(port, path, obj):
    r = U.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
                  headers={"Content-Type": "application/json"})
    try:
        return U.urlopen(r).status
    except U.HTTPError as e:
        # A refused escape hatch is a 422 and is an EXPECTED outcome here, not a
        # transport failure. urlopen raises on 4xx, so unwrap it.
        return e.code


def main():
    tmp = tempfile.mkdtemp()
    items = json.load(open(os.path.join(SD, "label_manifest_drums.json")))[:8]

    print("1. primary key order is unchanged (protects muscle memory)")
    flat = [c for _, cs in lt.grouped_classes("drums") for c in cs]
    check("drums key order identical to SETS order", flat == lt.SETS["drums"])
    check("tonal covers all classes",
          sorted(c for _, cs in lt.grouped_classes("tonal") for c in cs)
          == sorted(lt.SETS["tonal"]))

    print("\n2. a legacy 4-column CSV still loads")
    legacy = os.path.join(tmp, "legacy.csv")
    with open(legacy, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "label", "path", "hint"])
        w.writerow([0, "Kick", items[0]["path"], "Kick"])
        w.writerow([1, "Snare", items[1]["path"], ""])
    st = lt.State(items, legacy, lt.SETS["drums"])
    check("legacy rows recognised as done", len(st.done) == 2, f"{len(st.done)}")
    check("legacy labels preserved", st.done.get(0) == "Kick")

    print("\n3. appending upgrades the file without losing legacy rows")
    st.record(2, "Clap")
    rows = list(csv.DictReader(open(legacy)))
    hdr = open(legacy).readline().strip().split(",")
    check("header is now the full schema", hdr == lt.SCHEMA, f"{len(hdr)} cols")
    check("legacy rows survived upgrade", len(rows) == 3, f"{len(rows)} rows")
    check("legacy label intact after upgrade",
          any(r["label"] == "Kick" and r["id"] == "0" for r in rows))
    check("legacy path intact after upgrade",
          any(r["path"] == items[0]["path"] for r in rows))

    print("\n4. new optional fields are written and derived automatically")
    st.record(3, "Percussion", {"percussion_subtype": "Tom",
                                "human_confidence": "high"})
    rows = list(csv.DictReader(open(legacy)))
    r3 = [r for r in rows if r["id"] == "3"][0]
    check("percussion_subtype saved", r3["percussion_subtype"] == "Tom")
    check("human_confidence saved", r3["human_confidence"] == "high")
    check("collection derived automatically", r3["collection"] != "")
    check("sample_family_id derived automatically", r3["sample_family_id"] != "")
    check("labelling_session stamped", r3["labelling_session"] != "")

    print("\n5. rewrite paths preserve every column (the real risk)")
    st.requeue(3)
    rows = list(csv.DictReader(open(legacy)))
    check("requeue removed only the requeued row", len(rows) == 3)
    kick = [r for r in rows if r["id"] == "0"][0]
    check("requeue kept legacy label", kick["label"] == "Kick")
    st.record(3, "Percussion", {"percussion_subtype": "Hand Drum"})
    st.go_back()
    rows = list(csv.DictReader(open(legacy)))
    check("go_back kept full schema",
          open(legacy).readline().strip().split(",") == lt.SCHEMA)
    check("go_back preserved other rows' new fields",
          all(set(r.keys()) == set(lt.SCHEMA) for r in rows))

    print("\n6. rejection material is NOT given acoustic subtypes")
    check("Other/none offers reasons, not acoustic classes",
          "noise or texture" in lt.REJECTION_REASONS
          and not any(x in lt.REJECTION_REASONS for x in ("Tom", "Shaker/Tambourine")))
    check("Percussion offers the agreed subtypes",
          lt.PERCUSSION_SUBTYPES == ["Tom", "Shaker/Tambourine", "Hand Drum",
                                     "Other Percussive Hit", "Unsure"])

    print("\n7. end-to-end over HTTP, including a skipped refinement")
    csv2 = os.path.join(tmp, "e2e.csv")
    st2 = lt.State(items, csv2, lt.SETS["drums"],
                   [[g, cs] for g, cs in lt.grouped_classes("drums")])
    srv = serve(st2, 8794)
    meta = json.loads(U.urlopen("http://127.0.0.1:8794/meta").read())
    check("meta exposes subtypes", meta.get("perc_subtypes") == lt.PERCUSSION_SUBTYPES)
    check("meta exposes reasons", meta.get("reject_reasons") == lt.REJECTION_REASONS)
    nx = json.loads(U.urlopen("http://127.0.0.1:8794/next").read())
    check("label POST with extras", post(8794, "/label",
          {"id": nx["id"], "label": "Percussion",
           "extras": {"percussion_subtype": "Shaker/Tambourine"}}) == 200)
    nx2 = json.loads(U.urlopen("http://127.0.0.1:8794/next").read())
    check("label POST with SKIPPED refinement (empty extras)",
          post(8794, "/label", {"id": nx2["id"], "label": "Percussion",
                                "extras": {}}) == 200)
    rows = list(csv.DictReader(open(csv2)))
    check("skipped refinement still saves the primary label",
          rows[1]["label"] == "Percussion" and rows[1]["percussion_subtype"] == "")
    srv.shutdown()

    print("\n8. the real corpus file is untouched and still loads")
    real = os.path.join(SD, "verified_drums.csv")
    before = os.path.getmtime(real)
    n = len(list(csv.DictReader(open(real))))
    check("verified_drums.csv still parses", n > 500, f"{n} rows")
    check("verified_drums.csv not modified by tests",
          os.path.getmtime(real) == before)

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n9. escape hatches cannot be submitted empty (the 48-row defect)")
    tmp = tempfile.mkdtemp()          # section 8 tears the previous one down
    # The granularity sprint lost 48 rows because "Not in list" recorded only
    # that the option list was wrong. Adding a note PROMPT did not fix it -- the
    # prompt was skippable. These test the enforcement, not the prompt.
    esc = os.path.join(tmp, "escape.csv")
    st5 = lt.State(list(items), esc, lt.SETS["drums"])
    for cls in lt.NOTE_REQUIRED:
        try:
            st5.record(st5.next_item()["id"], cls, {})
            ok = False
        except lt.EscapeHatchError:
            ok = True
        check(f"'{cls}' with no note is refused", ok)
        try:
            st5.record(st5.next_item()["id"], cls, {"note": "   "})
            ok = False
        except lt.EscapeHatchError:
            ok = True
        check(f"'{cls}' with whitespace-only note is refused", ok)
    check("nothing was written by the refused calls",
          not os.path.exists(esc) or len(list(csv.DictReader(open(esc)))) == 0)

    # A named alternative is itself a recovery, so it satisfies the requirement
    # even without prose.
    st5.record(st5.next_item()["id"], "Not in list", {"not_in_list_label": "Bongo"})
    rows = list(csv.DictReader(open(esc)))
    check("'Not in list' with not_in_list_label is accepted", len(rows) == 1)

    st5.record(st5.next_item()["id"], "Unknown",
               {"note": "sounds like a conga loop, low and hand-played"})
    rows = list(csv.DictReader(open(esc)))
    check("note text is preserved verbatim",
          rows[-1]["note"] == "sounds like a conga loop, low and hand-played")
    check("note is parsed into a recoverable candidate",
          rows[-1]["not_in_list_label"] == "Hand Drum", rows[-1]["not_in_list_label"])
    check("note form hint is captured", rows[-1]["temporal_form"] == "loop",
          rows[-1]["temporal_form"])

    print("\n10. 'Not enough info' stays optional and distinct")
    st5.record(st5.next_item()["id"], "Not enough info", {})
    check("'Not enough info' is accepted without a note",
          len(list(csv.DictReader(open(esc)))) == 3)
    check("'Not enough info' is prompted but not required",
          "Not enough info" in lt.NOTE_CLASSES
          and "Not enough info" not in lt.NOTE_REQUIRED)

    print("\n11. Other/none is a different thing from Not in list")
    # Other/none = "this is not a supported sound". Not in list = "it IS a
    # supported sound, your list just had no key for it". Conflating them turns
    # real rejections into taxonomy complaints and vice versa.
    check("Other/none does not require a note",
          "Other/none" not in lt.NOTE_REQUIRED)
    check("Other/none is not in the note-prompt set either",
          "Other/none" not in lt.NOTE_CLASSES)
    check("Other/none gets a rejection reason, Not in list does not",
          "Other/none" not in lt.NOTE_CLASSES and bool(lt.REJECTION_REASONS))
    st5.record(st5.next_item()["id"], "Other/none", {"rejection_reason": "mixed/full music"})
    rows = list(csv.DictReader(open(esc)))
    check("Other/none row carries its reason and no note",
          rows[-1]["rejection_reason"] == "mixed/full music" and rows[-1]["note"] == "")

    print("\n12. the note parser proposes candidates, never certainties")
    cases = [("its a rimshot", "Rimshot"), ("open hat", "Hi-Hat"),
             ("bass drum, quite soft", "Kick"), ("reese", "Reese Bass"),
             ("some kind of tabla", "Hand Drum"), ("808 slide", "808")]
    for note, want in cases:
        got = lt.parse_note(note)["candidates"]
        check(f"parse {note!r} -> {want}", got and got[0] == want, str(got))
    check("an unparseable note yields no candidate",
          lt.parse_note("no idea what this is")["candidates"] == [])
    check("an empty note yields no candidate", lt.parse_note("")["candidates"] == [])
    # whole-word matching: "that" must not fire "hat"
    check("'that' does not match 'hat'",
          "Hi-Hat" not in lt.parse_note("no idea what that was")["candidates"])

    print("\n13. the HTTP layer refuses an empty escape hatch too")
    # The browser is a convenience; a stale tab or a replayed request must not
    # be able to write a row the schema forbids.
    hp = os.path.join(tmp, "http_escape.csv")
    st6 = lt.State(list(items), hp, lt.SETS["drums"])
    srv2 = serve(st6, 8791)
    try:
        first = st6.next_item()["id"]
        code = post(8791, "/label", {"id": first, "label": "Not in list", "extras": {}})
        check("empty 'Not in list' over HTTP returns 422", code == 422, str(code))
        check("the queue did not advance", st6.next_item()["id"] == first)
        code = post(8791, "/label", {"id": first, "label": "Not in list",
                                     "extras": {"note": "clave, wooden"}})
        check("the same row with a note returns 200", code == 200, str(code))
        check("the queue advanced once accepted", st6.next_item()["id"] != first)
        meta = json.loads(U.urlopen("http://127.0.0.1:8791/meta").read())
        check("/meta advertises note_required to the client",
              sorted(meta.get("note_required", [])) == sorted(lt.NOTE_REQUIRED))
    finally:
        srv2.shutdown()

    print("\n14. the browser cannot skip a required note either")
    js = lt.HTML
    check("Escape cancels rather than commits a required note",
          "if(!save){hideNote();return;}" in js)
    check("a blank required note is refused in the UI",
          "if(!txt){document.getElementById('noteerr')" in js)
    check("a server refusal reopens the note box instead of advancing",
          "if(!r.ok){" in js and "showNote(c); document.getElementById('noteerr')" in js)

    print("\n15. candidate-hidden FFT/physics receipt loads with string ids")
    fft_manifest = os.path.join(tmp, "fft_manifest.json")
    json.dump({"record_type": "slo_fft_physics_label_manifest",
               "rows": [{"id": "fftphys-0001", "path": items[0]["path"],
                          "review_prompt": "listen", "human_label": "",
                          "content_sha256": "abc"}]}, open(fft_manifest, "w"))
    fft_items = lt.load_review_items(fft_manifest)
    check("receipt rows are reduced to blind UI fields",
          fft_items == [{"id": "fftphys-0001", "path": items[0]["path"],
                         "hint": "", "display_name": "Review item fftphys-0001"}])
    fft_csv = os.path.join(tmp, "fft_labels.csv")
    fft_state = lt.State(fft_items, fft_csv, lt.SETS["fft_physics"],
                         [[g, cs] for g, cs in lt.grouped_classes("fft_physics")])
    fft_srv = serve(fft_state, 8792)
    try:
        fft_next = json.loads(U.urlopen("http://127.0.0.1:8792/next").read())
        check("string id survives /next", fft_next["id"] == "fftphys-0001")
        check("source filename is hidden", fft_next["name"] == "Review item fftphys-0001")
        check("string id can be labelled over HTTP",
              post(8792, "/label", {"id": "fftphys-0001", "label": "Kick",
                                     "extras": {}}) == 200)
        check("string id is persisted", list(csv.DictReader(open(fft_csv)))[0]["id"]
              == "fftphys-0001")
    finally:
        fft_srv.shutdown()

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}")
        return 1
    print("all label tool tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
