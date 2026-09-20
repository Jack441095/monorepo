Type: Advanced metering reference
Tags: itu bs 1770, true peak, dbtp, inter-sample peak, oversampling, reconstruction, headroom, mastering
Status: Approved
Source title: Recommendation ITU-R BS.1770-5, Annex 2
Source creator: International Telecommunication Union
Source URL: https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I%21%21PDF-E.pdf
Source version: BS.1770-5, November 2023
Reviewed: 2026-07-01

# ITU BS.1770 True-Peak Measurement


Short answer:
True-peak measurement estimates the maximum continuous-time waveform peak that reconstruction can produce between stored samples. A sample-peak meter only inspects stored sample values and can therefore miss playback or conversion overloads.

Try this:
1. Place a BS.1770-compatible true-peak meter after the final gain-changing processor.
2. Measure the complete rendered deliverable rather than relying solely on the live master bus.
3. Recheck after sample-rate or lossy-codec conversion because reconstructed peaks can change.
4. Use the delivery specification's dBTP ceiling and document the meter revision.
5. If a compliant ceiling still sounds distorted, reduce upstream clipping or limiting rather than only lowering output gain.

Why it matters:
True peak describes reconstruction headroom more accurately than sample peak. It helps prevent clipping in conversion, decoding, D/A reconstruction, and downstream processing.

Common mistakes:
- Treating dBFS sample peak and dBTP as interchangeable.
- Assuming a true-peak limiter repairs distortion already printed into the source.

When this does not apply:
True peak is a safety measurement, not a complete assessment of audible quality, dynamics, or codec artefacts.

Related questions:
- Why can a file below 0 dBFS exceed 0 dBTP?
- Should I measure true peak before or after encoding?
- Can a true-peak meter detect existing distortion?
- What is reconstruction headroom?

Editor notes: The excerpt provided focuses on the concept and application of True-Peak measurement as per ITU-R BS.1770-5, Annex 2. It aims to guide users in implementing this measurement effectively by placing it after final processing steps and rechecking post-conversion or sample-rate changes. The text also highlights common pitfalls such as misinterpreting dBFS and dBTP measurements and emphasizes the true peak's role as a safety measure rather than an assessment of audible quality.
