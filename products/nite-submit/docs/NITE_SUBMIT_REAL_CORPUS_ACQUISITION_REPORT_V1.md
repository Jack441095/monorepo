# NITE SUBMIT — REAL CORPUS ACQUISITION REPORT V1

**Date:** 2026-08-23
**Task:** Autonomous search, licensing audit, download, manifesting & privacy-safe validation corpus build
**Status:** **PASS WITH LIMITATIONS**

---

## 1. Summary

| Metric | Value |
|---|---|
| Documents discovered (candidates) | 30+ across searches |
| Documents downloaded | 21 |
| Documents rejected | 8 rejection classes logged |
| Qualification eligible | 21 / 21 |
| Institutions represented | 17 |
| SHA-256 duplicates | 0 |
| Image-only documents | 0 |
| Encrypted/malformed | 0 |
| Unknown-licence documents in qualification set | **0** |
| Private/student-portal documents | **0** |
| Auth-gated documents collected | **0** |
| Real student IDs intentionally collected | **0** (2 incidental public flags noted) |

## 2. Corpus location

```
real_validation_corpus/
    university_templates/   9 PDFs
    dissertations/          8 PDFs
    project_reports/        3 PDFs
    public_examples/        1 PDF
    manifests/              provenance_v1.json, real_manifest.json,
                            REVIEW_PACK_V1.md, rejection_log_v1.json,
                            first_pass/*.suggest.txt
    rejected/               (empty — nothing hostile retained)
```

PDFs are **gitignored** (`real_validation_corpus/**/*.pdf`). Manifests only are
committable. No third-party PDF is committed or redistributed.

## 3. Documents acquired

### University templates / cover sheets (9)
1. Cambridge applicant written-work cover sheet (Word)
2. Sheffield Hallam research-degree thesis guidelines incl. example title page w/ synthetic author (Word)
3. LSE MC499 dissertation handbook (module code MC499.1) (Word)
4. Southampton "Producing your thesis" quality-handbook guide (Acrobat/Word)
5. Oxford Maths dissertation guidance notes 2025-26 (LaTeX)
6. Rutgers ECE capstone report guidelines/template (Word)
7. UW Tacoma MS CSS capstone guidelines with verbatim cover-sheet template (Word)
8. Edge Hill HEA3183 assignment header — blank NAME/STUDENT NO/MODULE NO fields (Word→Quartz)
9. St Andrews dissertation formatting in Word guide (Word)

### Dissertations / theses (8)
10. White Rose 30585 — Stacey, PhD, Sheffield, CC BY-NC-ND 4.0 (382pp, Word)
11. White Rose 37689 — Junaid, PhD, York, CC BY-NC-ND 4.0 (272pp, Quartz)
12. White Rose 34471 — Newcomb, PhD, Sheffield, CC BY-NC-ND 4.0 (563pp, Word; extreme long title)
13. White Rose 18613 — Long, PhD, Sheffield, CC BY-NC-ND 2.5 (150pp, LaTeX)
14. UTAR FYP 2019 — Meow (92pp, Word; Malaysian layout)
15. UTAR FYP 2022 — Lau (100pp, WPS Writer — unusual generator)
16. UTAR FYP 2023 — Wong (131pp, Acrobat/Word)
17. KCL Research Portal via CORE — Sarkadi, PhD, King's College London, CC BY-NC-ND 4.0 EULA embedded (327pp, LaTeX)

### Project reports / capstones (3)
18. MIT SCM capstone report 2025 — two co-authors (Word→Quartz)
19. AIUB group capstone book 2023 — Bangladesh, DSpace public (Print To PDF)
20. Ashesi applied project 2019 — Ghana, CORE mirror of institutional repo (Word)

### Public examples (1)
21. Berklee Valencia master final paper 2020 — Apple Pages generator, two supervisors

## 4. Institutions (17)

University of Cambridge · Sheffield Hallam · LSE · Southampton · Oxford ·
Rutgers · UW Tacoma · Edge Hill · St Andrews · Sheffield · York · UTAR ·
King's College London · MIT · AIUB · Ashesi · Berklee Valencia.

## 5. Licence / provenance categories

| Class | Count |
|---|---|
| OPEN_LICENSE (CC BY-NC-ND stated) | 5 |
| INSTITUTIONALLY_PUBLISHED_PUBLIC_DOCUMENT | 6 |
| PUBLIC_REPOSITORY_RESEARCH_DOCUMENT | 7 |
| TEMPLATE_FOR_PUBLIC_USE | 3 |
| UNKNOWN in qualification set | **0** |

Every item has source URL, domain, licence reference, download date, SHA-256,
and notes in `real_validation_corpus/manifests/provenance_v1.json` and
`docs/NITE_SUBMIT_REAL_CORPUS_MANIFEST_V1.json`.

## 6. Generator diversity

WORD ×10 · WORD_ACROBAT ×2 · LATEX ×3 · WORD_PRINT ×2 · PRINT_QUARTZ ×1 ·
WPS_WRITER ×1 · PRINT_TO_PDF ×1 · PAGES ×1.

## 7. Rejections (see `rejection_log_v1.json`)

- DOWNLOAD_FAILED ×5: Bristol annex (404); CSUSM scholarworks (403 bot-gate);
  MSState + Governors State bepress (202 bot-challenge); ECU Research Online
  (202 bot-challenge).
- PRIVACY_RISK ×1: Universidad de Sevilla TFG — contains author DNI national ID;
  excluded before download.
- AUTH_REQUIRED ×1 class: TAR UMT repository FYPs — restricted to registered users.
- SOURCE_UNTRUSTED ×1 class: CourseHero/Chegg/StuDocu/Scribd never queried.
- MALFORMED ×0. DUPLICATE ×0. NON_PDF ×0.

## 8. First-pass extraction (READ-ONLY — engine untouched)

Ran `.build/release/nitesubmit-cli suggest` on all 21 documents
(`manifests/first_pass/*.suggest.txt`). Headline observations (not ground truth):

- student_name: MISSING on all 21 first-pass cases — biggest real-world gap.
- module_code: correct on Edge Hill HEA3183 blank cover sheet.
- university misfires observed: "Fudan University" from a reference inside the
  LSE handbook; title text detected as university on MIT capstone and UTAR FYPs.
- project_title: strong on AIUB ("SMART WATER METERING AND QUALITY MONITORING")
  and KCL ("Deception"); wrong-field case at Ashesi (author line read as title).

No tuning was performed. These feed V1.2 evidence only.

## 9. Privacy observations

- All names present are intentionally published (institutional repositories,
  publisher pages, official templates). No portal/LMS/gated content used.
- Two incidental flags (kept, flagged, not sought): UTAR 4719 shows author ID No
  on the institution's own submission form inside the published copy; UTAR 5904
  has an ID-style number in the repository filename. Owner may drop either case
  before qualification if uncomfortable.
- One candidate was excluded pre-download for containing a national ID (Seville TFG).
- No emails/addresses/phone numbers were searched or recorded beyond document content.

## 10. Limitations

- Several US bepress/bot-guarded repositories blocked non-interactive download
  (CSUSM, MSState, GSU, ECU) — owner browser download could add these later.
- CORE mirrors used for KCL/Ashesi/Berklee where institutional originals were
  CDN-blocked; licence context recorded per item.
- 0 image-only/scanned items acquired — manual-entry fallback remains validated
  by synthetic corpus only.
- Module-code coverage relies mostly on 2 template docs (+ synthetic corpus).
- Truth values marked UNREVIEWED require owner confirmation before metrics count.

## 11. Owner handoff

- Eligible documents: **21**
- Estimated owner review time: **20–30 minutes**
- Review pack: `real_validation_corpus/manifests/REVIEW_PACK_V1.md`
- Harness manifest: `real_validation_corpus/manifests/real_manifest.json`
- After confirming truths (replace UNREVIEWED), launch:

```sh
.build/release/nitesubmit-cli validate --manifest real_validation_corpus/manifests/real_manifest.json \
    --out real_validation_corpus/manifests/validation_results.json
.build/release/nitesubmit-cli review --manifest real_validation_corpus/manifests/real_manifest.json \
    --progress real_validation_corpus/manifests/review_progress.json
```

## 12. Compliance statements

Extraction engine modified: **NO** · Product code modified: **NO** · Other repos
modified: **NO** · Source PDFs committed/pushed: **NO** · AI attribution added:
**NONE**
