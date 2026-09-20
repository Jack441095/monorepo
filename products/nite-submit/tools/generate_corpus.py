#!/usr/bin/env python3
"""NITE_SUBMIT_PDF_CORPUS_V1 — deterministic synthetic PDF corpus generator.

Generates 220+ labelled cases as JSON manifests (page text lines + ground truth)
plus real PDFs for all text cases. Deterministic (fixed seed).
Output: Tests/NiteSubmitCoreTests/Fixtures/corpus/manifest.json
        Tests/NiteSubmitCoreTests/Fixtures/corpus/pdf/<case_id>.pdf
"""
import json
import os
import random

from fpdf import FPDF

OUT_JSON = os.path.join(os.path.dirname(__file__),
                        "..", "Sources", "NiteSubmitTests", "Fixtures", "corpus")
OUT_PDF = os.path.join(OUT_JSON, "pdf")

rng = random.Random(20260823)

FIRST = ["Jack", "Amara", "Sofia", "Liam", "Noor", "Chen", "Priya",
         "Tomas", "Zoe", "Ethan", "Fatima", "Oskar"]
LAST = ["Gandy", "Okonkwo", "Rossi", "Murphy", "Haddad", "Wei", "Sharma",
        "Silva", "Muller", "Kowalski", "Bennett", "Novak"]
PROJECTS = [
    "Interactive Audio Systems", "Adaptive Game Audio", "Machine Listening Report",
    "Final Major Project", "Soundscape Composition Study", "Reverb Network Analysis",
]
MODULE_TITLES = ["Interactive Audio Systems", "Digital Signal Processing",
                 "Creative Sound Practice"]
UNIS = ["UWE Bristol", "University of the West of England", "Bath Spa University",
        "Cardiff University", "University of Southampton"]
STAFF = [("Dr", "Whitfield"), ("Prof.", "Alvarez"), ("Dr", "Osei")]

cases = []


def add(case_id, pages, truth, meta=None, generate_pdf=True):
    cases.append({"id": case_id, "pages": pages, "truth": truth,
                  "meta": meta or {}, "generate_pdf": generate_pdf})


def cover_sheet(name, sid, uni, module_code, module_title, project,
                staff=None, extra_lines=None):
    lines = [uni, "Faculty of Arts, Design and Humanities", ""]
    if staff:
        lines += [f"Module Leader: {staff[0]} {staff[1]}", ""]
    lines += [
        f"Student Name: {name}",
        f"Student Number: {sid}",
        f"Module Code: {module_code}",
        f"Module Title: {module_title}",
        f"Project Title: {project}",
        "",
        "Declaration: This work is my own.",
    ]
    if extra_lines:
        lines += extra_lines
    return [lines]


# ---------------------------------------------------------------- clear sheets
for i in range(90):
    n = rng.choice(FIRST); l = rng.choice(LAST)
    name = f"{n} {l}"; sid = str(rng.randint(10000000, 99999999))
    proj = PROJECTS[i % len(PROJECTS)]; mod = MODULE_TITLES[i % len(MODULE_TITLES)]
    code = f"UFM{chr(65 + i % 26)}{chr(65 + (i * 7) % 26)}X-30-{1 + i % 3}"
    uni = UNIS[i % len(UNIS)]
    staff = STAFF[i % len(STAFF)]
    add(f"clear_{i:03d}", cover_sheet(name, sid, uni, code, mod, proj, staff),
        {"student_name": name, "student_id": sid, "university": uni,
         "module_code": code, "project_title": proj})


# ------------------------------------------------------- label / ID variants
# "Candidate No." is deliberately included here even though it is not a student-ID
# label — it's a real candidate-number label, kept so id_variant_01/06/11/16 double as
# the fixtures run_pdf_matrix_check.sh uses to test candidate-number/anonymous-marking
# detection. Ground truth below must NOT claim a student_id for that one: the detector
# correctly keeps candidate numbers and student IDs distinct (see FieldDetector's
# candidateNumberLabels vs studentIdLabels), so expecting student_id here was simply
# wrong ground truth, not a detector gap.
id_variants = [
    ("12345678", "Student ID: {}"), ("A12345678", "Candidate No. {}"),
    ("87654321", "Registration Number : {}"), ("24012345", "ID number - {}"),
    ("B09876543", "student id:{}"),
]
for j, (sid, tmpl) in enumerate(id_variants * 4):
    name = f"{FIRST[j % len(FIRST)]} {LAST[j % len(LAST)]}"
    page = [[
        "University of the West of England",
        tmpl.format(sid),
        f"Name: {name}",
        f"Module: UFMGGT-15-2",
        f"Assignment Title: Soundscape Study {j}",
    ]]
    truth = {"student_name": name,
             "university": "University of the West of England",
             "module_code": "UFMGGT-15-2",
             "project_title": f"Soundscape Study {j}"}
    if "Candidate No" not in tmpl:
        truth["student_id"] = sid
    add(f"id_variant_{j:02d}", page, truth)

# ------------------------------------------------------------ module formats
module_formats = ["CS101", "MUSC4001", "UFMXYZ-30-3", "ENG2087A", "DA101"]
for k, code in enumerate(module_formats * 4):
    name = f"{FIRST[k % len(FIRST)]} {LAST[(k + 3) % len(LAST)]}"
    sid = f"2{k:07d}"
    page = [[
        "Cardiff University",
        f"Student Name: {name}",
        f"Student Number: {sid}",
        f"Unit Code: {code}",
        f"Project: Adaptive Game Audio {k}",
    ]]
    add(f"module_format_{k:02d}", page,
        {"student_name": name, "student_id": sid,
         "university": "Cardiff University", "module_code": code,
         "project_title": f"Adaptive Game Audio {k}"})

# ------------------------------------------- adversarial: lecturer above student
for m in range(10):
    s = STAFF[m % len(STAFF)]
    name = f"{FIRST[m % len(FIRST)]} {LAST[m % len(LAST)]}"
    sid = f"3{m:07d}"
    proj = PROJECTS[m % len(PROJECTS)]
    page = [[
        "University of Southampton",
        f"Lecturer: {s[0]} {s[1]}",
        f"Supervisor: {s[0]} {STAFF[(m + 1) % len(STAFF)][1]}",
        f"Student Name: {name}",
        f"Student Number: {sid}",
        f"Module Code: UFMABC-30-{m % 9 + 1}",
        f"Project Title: {proj}",
    ]]
    add(f"adversarial_staff_{m:02d}", page,
        {"student_name": name, "student_id": sid,
         "university": "University of Southampton", "project_title": proj,
         "module_code": f"UFMABC-30-{m % 9 + 1}"})

# ------------------------------------------------ adversarial: IDs in references
for p in range(6):
    name = f"{FIRST[p]} {LAST[p]}"
    sid = f"4{p:07d}"
    page = [[
        "Bath Spa University",
        f"Student Name: {name}",
        f"Student Number: {sid}",
        f"Project Title: Reverb Network Analysis {p}",
        "",
        "References",
        "Smith, J. (2019). Candidate number 55555555 appears in citation metrics.",
        "Doe, A. (2020). Student number 99999999 cited erroneously.",
    ]]
    add(f"adversarial_refs_{p:02d}", page,
        {"student_name": name, "student_id": sid,
         "university": "Bath Spa University",
         "project_title": f"Reverb Network Analysis {p}"})

# ------------------------------------------------------ implicit title variants
for q in range(40):
    name = f"{FIRST[q % len(FIRST)]} {LAST[q % len(LAST)]}"
    sid = f"5{q:07d}"
    proj = f"Implicit Study {q}: Sonic Environments"
    pages = [
        ["University of the West of England",
         "A report on interactive sound"],
        [proj,
         f"Student Name: {name}",
         f"Student Number: {sid}",
         "Module Code: UFMSND-15-1"],
    ]
    add(f"implicit_title_{q:02d}", pages,
        {"student_name": name, "student_id": sid,
         "university": "University of the West of England",
         "module_code": "UFMSND-15-1",
         "project_title": proj})

# ------------------------------------------------------------- missing fields
for r in range(10):
    page = [["Some University", f"Student Name: {FIRST[r]} {LAST[r]}", "No other details."]]
    add(f"missing_fields_{r:02d}", page, {"student_name": f"{FIRST[r]} {LAST[r]}",
                                          "university": "Some University"})

for t in range(5):
    add(f"image_only_{t:02d}", [[]], {}, {"image_only": "true"}, generate_pdf=False)

# --------------------------------------------------------------- weird content
add("weird_unicode_00", [[
    "University of the West of England",
    "Student Name: Zoe Muller",
    "Student Number: 66778899",
    "Module Code: UFMUNI-30-3",
    "Project Title: Etude for Spatial Audio",
]], {"student_name": "Zoe Muller", "student_id": "66778899",
     "university": "University of the West of England",
     "module_code": "UFMUNI-30-3", "project_title": "Etude for Spatial Audio"})

add("weird_path_title_00", [[
    "University of the West of England",
    "Student Name: Jack Gandy",
    "Student Number: 11223344",
    "Module Code: UFMPTH-30-3",
    "Project Title: Final Report v2",
]], {"student_name": "Jack Gandy", "student_id": "11223344",
     "university": "University of the West of England",
     "module_code": "UFMPTH-30-3", "project_title": "Final Report v2"})

add("long_title_00", [[
    "Cardiff University",
    "Student Name: Amara Okonkwo",
    "Student Number: 22334455",
    "Module Code: MUSC4001",
    "Project Title: An Extended Investigation into Spatial Audio Perception and Binaural Rendering Techniques for Interactive Virtual Environments with Particular Reference to Game Audio Middleware Integration Practices",
]], {"student_name": "Amara Okonkwo", "student_id": "22334455",
     "university": "Cardiff University", "module_code": "MUSC4001"})

add("multi_institution_00", [[
    "University of the West of England",
    "In partnership with Cardiff University",
    "Student Name: Liam Murphy",
    "Student Number: 33445566",
    "Module Code: UFMXXX-30-3",
    "Project Title: Dual Institution Study",
]], {"student_name": "Liam Murphy", "student_id": "33445566",
     "university": "University of the West of England",
     "module_code": "UFMXXX-30-3"})

add("whitespace_00", [[
    "Bath Spa University",
    "Student Name : Sofia Rossi",
    "Student Number: 55667788",
    "Module Code: BSP222",
    "Project Title: Messy Whitespace Study",
]], {"student_name": "Sofia Rossi", "student_id": "55667788",
     "university": "Bath Spa University", "module_code": "BSP222"})

add("metadata_only_title_00", [[
    "University of Southampton",
    "Student Name: Noor Haddad",
    "Student Number: 77889900",
]], {"student_name": "Noor Haddad", "student_id": "77889900",
     "university": "University of Southampton",
     "project_title": "Metadata Sourced Project Title"},
    {"title": "Metadata Sourced Project Title"})

add("malformed_00", [], {}, {"malformed": "true"}, generate_pdf=False)

# ------------------------------------------------------------------ long report
report_body = [
    "University of the West of England",
    "Student Name: Ethan Bennett",
    "Student Number: 88990011",
    "Module Code: UFMLNG-40-3",
    "Project Title: Long Form Dissertation on Acoustics",
]
for ch in range(50):
    report_body += [f"Chapter {ch + 1}.", "Body text " * 20, ""]
pages = [report_body[i:i + 40] for i in range(0, len(report_body), 40)]
add("long_report_00", pages,
    {"student_name": "Ethan Bennett", "student_id": "88990011",
     "university": "University of the West of England",
     "module_code": "UFMLNG-40-3",
     "project_title": "Long Form Dissertation on Acoustics"})

# ------------------------------------------------- V1.1 anonymised regressions
# Structural patterns derived from real-world academic document analysis.
# No private content — synthesised from generic academic conventions.

for g in range(10):
    # Generic heading penalty: a big "FINAL REPORT" banner must not be chosen
    # over the student's actual title.
    name = f"{FIRST[g % len(FIRST)]} {LAST[(g + 5) % len(LAST)]}"
    sid = f"9{g:07d}"
    proj = f"Spatial Audio Research {g}"
    pages = [
        ["University of the West of England",
         "FINAL REPORT",
         f"Student Name: {name}",
         f"Student Number: {sid}",
         "Module Code: UFMGEN-30-3"],
        [proj,
         "Introduction to the study follows."],
    ]
    add(f"v2_generic_heading_{g:02d}", pages,
        {"student_name": name, "student_id": sid,
         "university": "University of the West of England",
         "module_code": "UFMGEN-30-3", "project_title": proj})

for h in range(10):
    # Group submission: several plausible names must cap confidence at MEDIUM
    # and surface candidates rather than silently choosing one.
    n1 = f"{FIRST[h % len(FIRST)]} {LAST[h % len(LAST)]}"
    n2 = f"{FIRST[(h + 4) % len(FIRST)]} {LAST[(h + 8) % len(LAST)]}"
    sid = f"A{7000000 + h}"
    page = [[
        "Cardiff University",
        f"Student Name: {n1}",
        f"Student Name: {n2}",
        f"Student Number: {sid}",
        "Module Code: MANGTBL-20-2",
        f"Project Title: Group Portfolio {h}",
    ]]
    add(f"v2_group_names_{h:02d}", page,
        {"student_name": n1, "student_id": sid,
         "university": "Cardiff University", "module_code": "MANGTBL-20-2",
         "project_title": f"Group Portfolio {h}"})

for i in range(10):
    # Colon-separated / subtitle titles must survive sanitisation intact.
    name = f"{FIRST[i % len(FIRST)]} {LAST[i % len(LAST)]}"
    sid = f"C{8000000 + i}"
    proj = f"Binaural Rendering {i}: Perception and Practice"
    page = [[
        "Bath Spa University",
        f"Student Name: {name}",
        f"Student Number: {sid}",
        "Module Code: BSPSND-15-1",
        f"Project Title: {proj}",
    ]]
    add(f"v2_colon_title_{i:02d}", page,
        {"student_name": name, "student_id": sid,
         "university": "Bath Spa University", "module_code": "BSPSND-15-1",
         "project_title": proj})

print(f"Built {len(cases)} case definitions")


def write_json():
    os.makedirs(OUT_JSON, exist_ok=True)
    with open(os.path.join(OUT_JSON, "manifest.json"), "w") as f:
        json.dump({"corpus_id": "NITE_SUBMIT_PDF_CORPUS_V1",
                   "generator_seed": 20260823,
                   "cases": [{"id": c["id"], "truth": c["truth"],
                              "meta": c["meta"]} for c in cases]}, f, indent=1)


def write_pdfs():
    os.makedirs(OUT_PDF, exist_ok=True)
    made = 0
    for c in cases:
        if not c.get("generate_pdf", True):
            continue
        pdf = FPDF()
        pdf.set_auto_page_break(False)
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        for page_lines in c["pages"]:
            for ln in page_lines:
                try:
                    safe = ln.encode("latin-1", "replace").decode("latin-1")
                    pdf.cell(0, 6, txt=safe, ln=1)
                except Exception:
                    pass
            pdf.add_page()
        path = os.path.join(OUT_PDF, c["id"] + ".pdf")
        with open(path, "wb") as fh:
            fh.write(bytes(pdf.output()))
        if c["meta"].get("title"):
            try:
                from pypdf import PdfReader, PdfWriter
                rd = PdfReader(path)
                wr = PdfWriter()
                wr.append(rd)
                wr.add_metadata({"/Title": c["meta"]["title"]})
                with open(path, "wb") as fh:
                    wr.write(fh)
            except Exception:
                pass
        made += 1
    print(f"Wrote {made} PDFs")


if __name__ == "__main__":
    write_json()
    write_pdfs()
