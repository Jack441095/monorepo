# KENN Public Beta Tester Guide

Welcome to the KENN Public Beta! KENN is an evidence-grounded mix engineering assistant designed to answer production questions and analyze stereo WAV audio tracks for technical mix faults.

---

## 1. Getting Started

### Accessing the Beta Application
- **Web App**: Open `UX/index.html` in any modern web browser or navigate to the hosted beta URL.
- **Local Server Startup** (if running locally):
  ```bash
  ./scripts/start_server.sh
  ```
  Then open `http://localhost:8090` in your browser.

---

## 2. Using Mix Advice Chat

1. Type your mix-engineering question into the text box at the bottom of the workspace (e.g. *"How do I remove muddy low-mids from a vocal?"*).
2. Click **Ask KENN** or press `Enter`.
3. KENN will return a verified answer along with:
   - **Confidence Level**: High, Medium, or Low.
   - **Verified Sources & Provenance**: Clickable tags citing the approved knowledge notes used to produce the answer.
4. **Honest Abstentions**: If KENN cannot find a verified source to answer your question, it will abstain rather than guessing.

---

## 3. Using WAV Mix Review

1. Locate the **Mix Review (WAV)** panel in the left sidebar.
2. Select a 16-bit or 24-bit PCM `.wav` file (up to 50 MB / 10 minutes in duration).
3. Check the consent box: *"I agree to upload this WAV file for server-side diagnostic analysis."*
4. Click **Analyze WAV**.
5. KENN will calculate signal measurements and report:
   - **Peak Level (dBFS)** & **RMS Level (dBFS)**
   - **Crest Factor (dB)**
   - **Digital Clipping Runs**
   - **Channel Imbalance & Phase / Polarity Compatibility**
   - **DC Offset**
   - **Diagnostic Findings & Action Plan**

---

## 4. Submitting Feedback & Reporting Issues

- After receiving an answer or mix review, rate the response using the 1⭐ to 5⭐ rating buttons in the sidebar.
- Enter optional comments and click **Submit Feedback**.
- If you encounter a bug or unexpected behavior, please submit a report with the `request_id` displayed on your receipt.

