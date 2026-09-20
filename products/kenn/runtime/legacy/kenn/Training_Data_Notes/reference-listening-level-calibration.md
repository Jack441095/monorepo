Type: Monitoring reference
Tags: monitoring, reference level, spl, calibration, pink noise, listening level, mix translation, ear fatigue
Status: Approved
Source title: EBU Tech 3343 — Guidelines for Production of Programmes in accordance with EBU R 128
Source creator: European Broadcasting Union (EBU), PLOUD group
Source URL: https://tech.ebu.ch/publications/tech3343
Source version: V4, November 2023 (§ 8.2 Acoustical Alignment, Listening Level)
Reviewed: 2026-07-06

# Setting a Consistent Reference Monitoring Level

Short answer:
Pick one fixed monitor volume and always mix at it. A wandering monitor level is one of the most common hidden causes of inconsistent low-end and top-end decisions between sessions — turn it up and bass/air sound thin so you add more; turn it down and the same mix sounds boomy so you cut. EBU's broadcast calibration method (pink noise, mono, at a known reference) is the cleanest way to find that one level and return to it every session.

Try this:
1. Generate mono pink noise filtered to roughly 500 Hz–2000 Hz (many DAWs/plugins can do this, or use a calibration test-tone file).
2. Feed it to one speaker at a time at your intended reference loudness level in your DAW (broadcast standard is -23 LUFS integrated; for music mixing, picking any consistent reference like -18 to -20 dBFS RMS works just as well — the point is consistency, not matching broadcast spec exactly).
3. Using an SPL meter (C-weighted, slow response) at your mix position, raise or lower the monitor's physical volume knob until you read the same target SPL from each speaker (EBU uses 73 dB C SPL per speaker as its reference point).
4. Mark that knob position physically (tape, marker, or a recalled preset on a monitor controller) so you can return to it instantly.
5. Do all critical tonal-balance decisions (EQ, low-end weight, brightness) at that marked level. Use louder or quieter levels only for spot-checks (compression pumping, translation) — not for the actual tonal-balance calls.

Why it matters:
Human hearing's frequency response isn't flat — it changes with SPL (the same mix sounds bass-and-treble-boosted when played loud and thinner when played quiet). If your monitor level drifts between sessions, you're not evaluating the mix, you're partly evaluating today's volume knob position. A fixed reference level removes that variable entirely, the same way a fixed listening level lets a broadcast mixer make repeatable loudness decisions across programmes.

Common mistakes:
- Mixing loud because it "feels better," then being surprised the mix sounds thin or harsh at normal home/car volume.
- Never actually measuring the level — "about here" on the knob drifts over weeks without anyone noticing.
- Using a different reference level for tracking/comping than for critical mix decisions, then wondering why balance calls feel inconsistent.

When this does not apply:
Genre- or reference-matching sessions where you deliberately A/B against a client's reference track at a specific loudness are a different, temporary use case — return to your fixed reference level afterward.

Related questions:
- Why does my mix sound different at different volumes?
- What SPL should I mix at?
- How do I stop myself from over-boosting bass?
- Why do professional studios calibrate their monitors?
