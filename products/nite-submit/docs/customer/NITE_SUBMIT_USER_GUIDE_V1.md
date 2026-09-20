# NITE Submit v1.0 — User Guide & Assessment Pre-Flight Manual

Welcome to **NITE Submit**, the native macOS application designed to help university students and academic staff prepare, standardize, and organize assignment submissions with zero stress and 100% privacy.

---

## 1. Quick Start (3-Step Submission Preparation)

1. **Drag & Drop Your File:**  
   Drag your assignment PDF (or `.zip` portfolio) onto the NITE Submit drop zone. NITE Submit instantly reads the first 2 pages on-device in under 0.05 seconds.

2. **Verify Extracted Metadata:**  
   Inspect your detected **Student Number**, **Student Name**, **Module Code**, and **Project Title**.  
   - 🟢 **VERIFIED (Green):** High-confidence extraction.
   - 🟠 **CHECK (Amber):** Medium-confidence or candidate menu available. Select from the dropdown menu or edit the text directly.
   - 🔴 **REQUIRED (Red):** Field is needed by your selected naming rule but was missing from the PDF. Type the value directly into the text box.

3. **Approve & Create Renamed Copy:**  
   Click **Approve Details** to verify your details, then click **Approve & Create Renamed Copy** (`Enter`). NITE Submit creates a perfectly formatted, safely renamed copy of your assignment in your target folder.

---

## 2. Naming Rules & Preset Profiles

NITE Submit includes pre-configured naming rules for common UK and US university standards:

- **UK Coursework (Generic):** `{module_code}_{student_id}_{project_title}.pdf`  
  *Example:* `DSP402_75589_Laser_Controlled_Devices.pdf`
- **US Coursework (Generic):** `{last_name}_{first_name}_{project_title}.pdf`  
  *Example:* `Gandy_Jack_Laser_Controlled_Devices.pdf`
- **Anonymous Candidate Number:** `{candidate_number}_{project_title}.pdf`  
  *Example:* `C10948_Laser_Controlled_Devices.pdf`
- **Custom Template:** Build your own custom template using tokens like `{student_id}`, `{first_name}`, `{last_name}`, `{full_name}`, `{module_code}`, `{project_title}`, `{assignment_code}`, and `{group_id}`.

### Sharing Naming Rules (.submitrule.json)
- **Exporting a Rule:** Click **Export…** to save your current template and required fields to a `.submitrule.json` file.
- **Importing a Rule:** Click **Import…** to load a custom rule distributed by your course leader or university department.

---

## 3. Privacy, Safety & Data Guarantees

- **On-Mac Privacy:** All document processing happens locally. Your coursework, student number, and personal details never leave your Mac. The only network request in the app is the optional "Check for Updates…" menu item, which checks for a newer app version and sends none of your data — it only runs when you click it.
- **Bit-Identical Byte Preservation:** NITE Submit writes output copies to a staging area and calculates a chunked **SHA-256 hash** before and after the operation. Your original submission PDF bytes remain untouched.
- **Anonymous Marking Compliance:** If your assessment requires anonymous marking (`name_prohibited`), NITE Submit checks for prohibited student name labels and alerts you before exporting.

---

## 4. Keyboard Shortcuts & Tips

- **`Cmd + Shift + U`**: Check for Software Updates.
- **`Enter`**: Approve details and trigger **Create Renamed Copy**.
- **`Cmd + Q`**: Quit NITE Submit.
- **Copy Filename Only:** Click **Copy Filename** if you only want the sanitized string on your clipboard without creating a new file on disk.

---

## 5. Troubleshooting & Support

- **"Unsafe Punctuation Normalised"**: Special characters like `/`, `:`, `\`, `*`, `?`, `"`, `<`, `>`, `|` are automatically replaced with underscores or safe spaces so Turnitin and online portals accept the file cleanly.
- **Scanned Image PDFs**: Scanned image sheets receive automatic, local English OCR on the first few pages. Hover over amber status LEDs to view alternative candidate words.
