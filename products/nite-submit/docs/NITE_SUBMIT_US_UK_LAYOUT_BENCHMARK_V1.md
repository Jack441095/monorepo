# NITE Submit: US/UK university layout benchmark v1

Research date: 25 August 2026
Scope: English-language written submissions, with emphasis on US and UK university guidance.

## Executive finding

There is no single US or UK filename standard. The course, department, assessment platform, and anonymity policy usually decide the required filename. The recurring safe pattern is a stable identifier first, followed by a short assessment or work title:

`{student_id}_{project_title}.pdf`

Where the institution requires identity in the name, a second pattern can be offered:

`{student_id}_{last_name}_{first_name}_{module_code}_{project_title}.pdf`

The student number should remain the first component because several university instructions use it as the primary lookup key, while Harvard data-management guidance recommends putting the most important sorting/search field first. Names, titles, module codes, and dates are useful secondary fields, but they must not be assumed to be required everywhere.

## Current source spot-check

The following authoritative pages were rechecked on 25 August 2026. They
support the benchmark, but they do not establish one shared university-wide
filename standard:

- [Harvard Medical School Data Management — File Naming Conventions](https://datamanagement.hms.harvard.edu/plan-design/file-naming-conventions)
  recommends putting the most important searchable metadata first, separating
  fields with underscores or dashes, avoiding spaces and special characters,
  documenting the convention, and using an explicit version suffix where
  needed. This is research-data guidance, not a universal coursework rule.
- [University of Chicago Library — Sample Title Pages](https://www.lib.uchicago.edu/research/scholar/phd/students/sample-title-pages/)
  specifies title-page presentation such as uppercase, non-bold text, the
  diploma name, and a month/year line. It is a title-page layout reference,
  not evidence that Chicago requires a particular filename.
- [Leeds Conservatoire — Chapter 5: File Naming and Labelling](https://students.leedsconservatoire.ac.uk/assignment-guidelines/chapter-5/)
  gives a concrete UK coursework convention: assignment code and student
  number, with additional content information when needed. Its ePortfolio
  guidance adds the title after those identifiers.
- [University of Washington GIS assignment guidelines](https://courses.washington.edu/gis250/assignments/index.html)
  gives a concrete US coursework example: the filename is `LASTNAME_A#`,
  while the PDF itself is signed with name, email, course, quarter/year, and
  assignment number.

Product conclusion: the app should offer editable patterns and a visible
approval preview, while asking the student to follow the current assessment
brief. Harvard and Chicago remain useful labelled starting points; neither is
presented as an official filename database or a universal rule.

## What official guidance shows

| Region / institution | Document type | Repeated layout or naming signal | Product implication |
| --- | --- | --- | --- |
| Harvard T.H. Chan School of Public Health | Doctoral thesis | Centered title, student name, degree statement, school, Harvard University, location, month/year | Recognise a centred title block and a degree statement; do not mistake the degree or school for the work title. |
| Harvard Law School | Writing-prize submission | Submission instructions are assessment-specific and may require an anonymous filename/identifier | Treat local assessment instructions as authoritative; support ID-only/anonymised output. |
| Harvard University research-data guidance | Research files | Important metadata first; use underscores/dashes, avoid spaces/special characters, document the convention, and add version/date only where useful | Keep the sanitizer conservative and provide a visible preview plus a documented template. |
| University of Chicago Library | Dissertation title pages | Uppercase, non-bold title-page text; diploma name; degree-quarter month and year | Accept uppercase title and “By” + name layouts; do not treat uppercase as evidence of a title or name by itself. |
| Stanford | PhD dissertation | Centred uppercase title page; department/program; month/year of submission | Search the first title-page block before body headings; capture department/program as optional metadata. |
| University of Illinois Chicago | Thesis/dissertation | Approved title and author name; exact degree/program statement; institution and year | Prefer labelled/positioned title-page evidence and preserve the recorded name form. |
| University of Washington | Coursework assignments | Filename can be `LASTNAME_A#`; the paper itself carries name, email, course, quarter/year, and assignment number | Coursework may have no formal title page; inspect the first page for header fields and assignment number. |
| University of Leeds Conservatoire | Coursework/ePortfolio | Assignment code + student number; title may be added when multiple pieces are submitted | Add a module/assignment-code-first profile and support titles as optional suffixes. |
| UCL | Doctoral thesis | Official title, registered full name, UCL, degree; declaration follows title page | Separate title-page identity from supervisor/declaration text; keep full registered name. |
| University of Bristol | Dissertation | Title, student name, degree/faculty/school statement, month/year, and word count | Treat word count/date as optional fields, never as a student name or project title. |
| University of Birmingham | Thesis | Title, author, degree, department/school, university, month of submission | Strong match for the current title-page detector and first-page evidence model. |
| Cardiff University | Research-degree thesis | Title/subtitle, candidate full name as on student record, degree, Cardiff University, month/year | Handle subtitles and a “candidate” label; preserve the full name. |

Sources: [Harvard Chan thesis title page](https://content.sph.harvard.edu/wwwhsph/sites/1496/2020/09/Doctoral-Thesis-Title-Page.pdf), [Harvard Law submission instructions](https://hls.harvard.edu/academics/fellowships-and-prizes/prizes/writing-prizes/submission-instructions/), [Harvard file-naming guidance](https://datamanagement.hms.harvard.edu/plan-design/file-naming-conventions), [Chicago sample title pages](https://www.lib.uchicago.edu/research/scholar/phd/students/sample-title-pages/), [Stanford title-page guidance](https://studentservices.stanford.edu/my-academics/earn-my-degree/graduate-degree-progress/dissertations-and-theses/prepare-your-work-1), [UIC thesis manual](https://grad.uic.edu/academic-support/thesis/thesis-manual/), [Washington assignment guidelines](https://courses.washington.edu/gis250/assignments/index.html), [Leeds Conservatoire file naming](https://students.leedsconservatoire.ac.uk/assignment-guidelines/chapter-5/), [UCL thesis preparation](https://www.ucl.ac.uk/study/doctoral-school/regulations/essential-procedures-and-policies/thesis-preparation-submission-and-publishing), [Bristol dissertation format](https://www.bristol.ac.uk/academic-quality/pg/code-of-practice/assessment/content-format/), [Birmingham thesis formatting](https://www.intranet.birmingham.ac.uk/student/libraries/research/thesis/thesis-formatting.aspx), [Cardiff thesis submission guidance](https://www.cardiff.ac.uk/__data/assets/pdf_file/0010/1467235/Submission-and-Presentation-of-Research-Degree-Theses.pdf).

## Layout patterns NITE Submit should expect

### Research theses and dissertations

The first page commonly contains, in some order:

1. Work title, sometimes split across multiple centred or uppercase lines.
2. Author/candidate name, often introduced by `By`, `Author`, or `Candidate`.
3. Degree statement, such as “submitted in partial fulfilment…” or “for the degree of…”.
4. Department, school/faculty, and institution.
5. Month/year or year.
6. Supervisor, committee, approval, declaration, copyright, or repository text.

The order varies. A supervisor appearing near the author is not proof that the following name is staff; an explicit `By` marker and title-page position should take precedence.

### Coursework and essays

Coursework often has a compact first-page header rather than a formal title page. Common fields are:

- student name or candidate number;
- module/course code;
- assignment/assessment number or title;
- tutor/instructor;
- word count and date.

Some courses request a creative work title rather than “Essay 1” or “Final Paper.” Generic labels should therefore be treated as document-type clues, not as the project title.

### Anonymous submissions

Anonymity changes the filename requirement. An assessment may deliberately require only a candidate number or assignment code. NITE Submit must not force a personal name into an anonymised profile. The UI should explain that a missing name is expected when the selected profile does not require it.

### Group submissions

US guidance sometimes uses multiple surnames in a filename; cover sheets may list numbered students with IDs. The detector retains the first candidate plus alternatives, and the UI now exposes an explicit Group ID field and Group ID + Project rule. A group identifier is accepted only from a labelled field or manual entry; names are never silently joined into one.

## Recommended NITE Submit profiles

The current Harvard-style and Chicago-style options are useful product profiles, but they should be described as naming profiles rather than universal university rules:

| Profile | Template | Use |
| --- | --- | --- |
| ID + title (default) | `{student_id}_{project_title}` | Safest general profile; works with a saved student number and anonymous workflows. |
| Identity + title | `{first_name}_{last_name}_{project_title}` | Human-readable personal archive; only use where identity is permitted. |
| ID + identity + title | `{student_id}_{full_name}_{project_title}` | Institution or department requests both machine lookup and the complete readable student identity. |
| Assignment-code profile | `{assignment_code}_{student_id}_{project_title}` | UK-style coursework where the assignment code is the routing key. |
| Module-code profile | `{module_code}_{student_id}_{project_title}` | UK-style coursework where the module code is the routing key. |
| US coursework (generic) | `{last_name}_{first_name}_{project_title}` | Ordinary, non-anonymous coursework where the local instructions ask for the student’s name in the filename. |
| US assignment-code profile | `{last_name}_{assignment_code}` | Coursework shorthand such as `LASTNAME_A#`, where the brief supplies an assignment code. |
| Group profile | `{group_id}_{project_title}` or a reviewed list of surnames | Avoid silently inventing a group name from one member. |

Every profile should:

- show the exact preview before writing;
- block missing required fields;
- show evidence and confidence for every inferred field;
- make group/name/title alternatives selectable as an explicit user choice;
- keep the original file untouched by default;
- use underscores or hyphens, remove unsafe punctuation, and avoid spaces;
- append a counter on collision rather than overwriting;
- support a deliberate version suffix such as `_v02` when the user selects it.

## Extraction backlog

1. Add explicit labels: `author`, `candidate`, `submitted by`, `registration number`, `candidate number`, `assignment number`, `assessment number`, `word count`, and `date submitted`.
2. Keep title-page scanning limited to the first two or three pages, but recognise repository wrappers and licence pages so their prose cannot become the title.
3. Recombine titles split across uppercase/centred lines and keep subtitles joined with a stable separator.
4. Detect `By` on its own line, including PDF text layers that split a first-name initial from the remaining letters.
5. Improve document-type classification: thesis, dissertation, essay, report, portfolio, presentation, audio/video, and template/guide.
6. Treat university, department, module title, word count, date, supervisor, and committee as optional metadata unless a selected naming profile requires them.
7. Add OCR as a separate, clearly marked path for image-only PDFs. OCR output must remain review-required until the user confirms the critical fields.
8. Add multilingual label dictionaries without changing the internal canonical keys (`student_id`, `full_name`, `project_title`, and so on).

## English-first, multilingual-ready design

The internal model should remain language-neutral. Localise only the labels, explanatory text, date formatting, and profile names:

- canonical field keys stay stable across languages;
- each locale supplies label variants and common degree/document terms;
- extracted values remain in their source spelling unless the user explicitly asks for transliteration;
- preserve accents and non-Latin scripts in metadata, while making filename transliteration an opt-in profile;
- store the source phrase and page/evidence location so a reviewer can verify a translated label;
- keep confidence and review status independent of language;
- allow bilingual title pages, where the official title may appear in both the local language and English.

This keeps the current English detector useful while avoiding an English-only data model that would have to be rebuilt later.
