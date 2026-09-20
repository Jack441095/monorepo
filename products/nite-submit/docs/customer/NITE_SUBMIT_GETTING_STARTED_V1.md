# NITE Submit — Getting Started

**Product version:** 0.2.0 (Private Beta RC1)
**Audience:** Beta testers and customers
**Last reviewed:** 2026-08-25
**Applies to:** macOS 13 or later, Apple Silicon Macs
**Evidence boundary:** Describes shipped behaviour only. Features not in your build are not documented here.

---

## What NITE Submit is

NITE Submit reads a university assignment PDF on your Mac, detects likely identifying details (your name, student number, university, module code/title, project title), shows you exactly what it found, and — after you approve the details — creates a correctly named copy of your file.

**Your assignment never leaves your computer.** There is no upload, no account, and no analytics. The only network request in the app is the optional "Check for Updates…" menu item, which just checks for a newer version — it never sends your documents or data anywhere, and only runs when you click it.

## What NITE Submit is not

- It does **not** submit work anywhere. You still submit through your university's own system.
- It does **not** know your university's official rules. Presets are generic, editable starting points.
- It does **not** guarantee perfect detection. Every field is editable, and you approve before anything happens.

## 1. Install

Beta builds are provided as a manual download with a SHA-256 checksum in the beta handoff note.

1. Unzip the download and drag **Submit.app** to your Applications folder.
2. Verify the checksum if one was provided with your invite.
3. First launch: because beta builds are not yet notarised, macOS may say the app "cannot be opened." Right-click (or Control-click) the app and choose **Open**, then confirm **Open** again. You only need to do this once.
4. If macOS still blocks the app: open **System Settings → Privacy & Security**, scroll to the Security section, and click **Open Anyway**.

> During private beta the app is ad-hoc signed. Public releases will be Developer ID signed and notarised, which removes this step.

## 2. First workflow

1. **Open Submit.**
2. *(Optional, first launch)* Enter your **student number** if you want it reused when a PDF does not contain one. It is stored locally on your Mac and can be cleared at any time from the app.
3. **Drop your assignment PDF** onto the window, or click the drop zone to browse for it.
4. **Check the detected details.** Each field shows a status:
   - ✓ Found — high confidence, extracted from a clear label
   - ? Check — plausible; please verify before approving
   - ! Missing — not found; type it yourself
5. If a field offers alternatives, choose one from that field's **Use…** menu, or edit any field directly. The app never invents a value.
6. Click **Approve details**. Creating a file stays disabled until you approve the required fields for the current document.
7. Choose a naming rule (preset or your own template), check the live preview, then click **Create Renamed Copy**.

Your original file is left untouched by default.

## 3. Preparing files for best results

NITE Submit is designed for **text-based assignment PDFs** — the kind produced by Word, Google Docs, LaTeX, or most departmental templates.

Best results come from PDFs where:

- the title page contains clearly labelled fields (`Name:`, `Student ID:`, `Module:`, …) or a conventional cover-page layout;
- text is selectable (you can click and select text in Preview);
- the document's first pages carry the identity information.

If your PDF is scanned or image-only, NITE Submit attempts bounded local OCR on the first few pages and marks every OCR-derived field **for review** — it never skips the approval step. For difficult scans or handwriting, simply fill the fields in manually; renaming works exactly the same way.

## 4. Naming rules

Pick a preset from the menu or type a template. The safe default is:

```
{student_id}_{project_title}
```

If your department requires the module code, use an explicit module-bearing
rule such as `{student_id}_{module_code}_{project_title}` instead.

Presets include Generic, Harvard-style, UK coursework, UK assignment code, US coursework, US assignment code, Chicago-style, ID + student name, Anonymous candidate number, and Group ID + Project. These are generic, editable patterns based on current public examples — they are **not** an official university-wide convention. Use the student-name profiles only for non-anonymous submissions, and always follow the rule your department actually gives you. For group work, enter or confirm an explicit group identifier; NITE Submit will not invent one from student names.

The **Anonymous candidate number** profile uses a separately detected candidate number and will never substitute your saved student number for it. If the candidate number is missing, you must enter or confirm it before a preview appears.

The **Document identity** setting is separate from the filename rule. Choose
**Name required in document** when the brief requires the student's name on the
submission, **Anonymous — name prohibited** when anonymous marking forbids it,
or **No rule (check brief)** when neither rule is specified. NITE Submit checks
the first two pages for a required title-page name. For anonymous work it also
flags explicit identity labels on later extracted pages, while leaving
unlabelled cited names for manual review rather than calling them student
identity automatically.

## 5. Next steps

- Worked walkthroughs of every stage: see the **User Guide**.
- Common questions: see the **FAQ**.
- Something wrong or unclear: contact `support@nitedsp.co.uk` (see the FAQ entry "How do I report a problem safely?" before attaching anything).

---

*NITE Submit helps you prepare a file. It does not submit work for you, and it cannot guarantee that your university's rules match any preset. Always review the final filename before submitting.*
