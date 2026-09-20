# NITE Submit — Frequently Asked Questions (FAQ)

### Q1: Does NITE Submit upload my coursework or PDF to any server?
**No. Never.** All PDF text parsing, field extraction, and SHA-256 byte verification happen locally on your Mac — your coursework and extracted data never leave the app or touch the network. There is zero cloud upload and zero analytics telemetry. The one network request in the app is the optional **Check for Updates…** menu item, which fetches a small release feed to check for a newer version — it contains no document content and only runs when you click it.

---

### Q2: Will Turnitin, Canvas, Blackboard, or Moodle accept NITE Submit files?
**Yes.** Online submission portals frequently reject uploaded PDFs if the filename contains special punctuation, slashes, control characters, or illegal spaces. NITE Submit automatically sanitizes all file names against cross-platform OS standards (macOS, Windows, Linux), guaranteeing your file uploads cleanly without rejection errors.

---

### Q3: Does NITE Submit modify my original PDF file?
**No.** By default, NITE Submit operates in non-destructive **Create Copy** mode. It reads your original PDF, computes its pre-operation SHA-256 hash, writes a renamed copy to your designated output folder, and verifies that the output hash matches bit-for-bit. Your original submission file is never altered or overwritten.

---

### Q4: What if my PDF has no text (e.g. a scanned document)?
NITE Submit includes a bounded, local **Vision Framework OCR Engine**. For scanned assignment pages, NITE Submit performs English OCR on the first few pages locally on your Mac. If confidence is low, you can type your student number or project title directly into the editable input grid.

---

### Q5: How does Anonymous Marking compliance work?
If your university department requires blind/anonymous grading (`Anonymous — name prohibited`), select the **Anonymous candidate number** preset. NITE Submit checks the extracted PDF text for student name labels and alerts you if personal identity markers are found on title pages before you export.

---

### Q6: Can I save my student number so I don't have to re-enter it?
**Yes.** You can save your student ID in the **Saved student number** field. NITE Submit will automatically use it whenever a PDF does not contain an explicit student number on page 1. Your saved ID is stored locally in macOS user defaults and can be cleared at any time.

---

### Q7: What are the system requirements for NITE Submit?
- **Operating System:** macOS 13.0 (Ventura) or later (macOS 14 Sonoma & macOS 15 Sequoia supported).
- **Architecture:** Apple Silicon (M1/M2/M3/M4) only — no Intel Mac build currently exists.
- **Disk Space:** About 15 MB.
